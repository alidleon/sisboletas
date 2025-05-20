# sueldos/utils.py (NUEVO ARCHIVO - Adaptado de reportes/utils.py)
import logging
from django.shortcuts import get_object_or_404
from .models import PlanillaSueldo, DetalleSueldo # Modelos locales

try:
    # Modelos externos necesarios para filtros y enriquecimiento
    from planilla.models import (
        PrincipalDesignacionExterno, PrincipalPersonalExterno,
        PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
    )
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    # Definir clases falsas si planilla no está disponible
    PrincipalDesignacionExterno, PrincipalPersonalExterno, PrincipalCargoExterno = None, None, None
    PrincipalUnidadExterna, PrincipalSecretariaExterna = None, None
    PLANILLA_APP_AVAILABLE = False
    logging.error("[Util Sueldos] ERROR: No se pueden importar modelos externos de 'planilla'.")
from django.db.models import Q
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_processed_sueldo_details(request, planilla_id):
    """
    Obtiene PlanillaSueldo, filtros externos, y detalles de sueldo
    filtrados y enriquecidos con datos externos.
    """
    result = {
        'planilla_sueldo': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none() if PLANILLA_APP_AVAILABLE else [],
        'unidades_for_select': PrincipalUnidadExterna.objects.none() if PLANILLA_APP_AVAILABLE else [],
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'detalles_sueldo': [], # Lista de objetos DetalleSueldo enriquecidos
        # 'detalle_ids_order': [], # Podríamos añadir si implementamos edición rápida
        'search_active': False,
        'error_message': None,
        'search_term': '',
    }

    if not PLANILLA_APP_AVAILABLE:
         result['error_message'] = "Componentes externos de personal no disponibles."
         # Podríamos retornar aquí si es crítico

    # --- 0. Obtener PlanillaSueldo ---
    try:
        planilla = PlanillaSueldo.objects.get(pk=planilla_id)
        result['planilla_sueldo'] = planilla
        logger.info(f"[Util Sueldos] Procesando PlanillaSueldo ID {planilla.id}")
    except PlanillaSueldo.DoesNotExist:
        logger.error(f"[Util Sueldos] PlanillaSueldo ID={planilla_id} no encontrada.")
        result['error_message'] = f"Planilla de Sueldos ID {planilla_id} no encontrada."
        return result
    except Exception as e_plan:
        logger.error(f"[Util Sueldos] Error obteniendo PlanillaSueldo ID {planilla_id}: {e_plan}", exc_info=True)
        result['error_message'] = "Error buscando la planilla."
        return result

    # --- 1. Obtener Secretarías Externas (para el filtro) ---
    if PLANILLA_APP_AVAILABLE:
        try:
            all_secretarias = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
            result['all_secretarias'] = all_secretarias
        except Exception as e_sec:
            logger.error(f"[Util Sueldos] Error obteniendo secretarías: {e_sec}", exc_info=True)
            result['error_message'] = (result.get('error_message') or '') + " Error cargando secretarías."

    # --- 2. Procesar Filtros GET ---
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    # Determinar si se activó la búsqueda/filtro
    result['search_active'] = bool(request.GET.get('buscar') or filter_secretaria_str or filter_unidad_str or search_term)
    logger.debug(f"[Util Sueldos] GET Params: sec='{filter_secretaria_str}', un='{filter_unidad_str}', q='{search_term}' | Search Active: {result['search_active']}")

    # --- 3. Cargar Unidades si se seleccionó Secretaría ---
    selected_secretaria_id = None
    if filter_secretaria_str and PLANILLA_APP_AVAILABLE:
        try:
            selected_secretaria_id = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = unidades_qs
        except (ValueError, TypeError):
             logger.warning(f"ID Secretaría inválido: '{filter_secretaria_str}'")
             result['selected_secretaria_id'] = None
        except Exception as e_uni:
             logger.error(f"Error obteniendo unidades para sec ID {selected_secretaria_id}: {e_uni}", exc_info=True)
             result['error_message'] = (result.get('error_message') or '') + " Error cargando unidades."

    # --- 4. Obtener IDs Externos (Solo si filtro unidad o búsqueda) ---
    apply_external_id_filter = bool(filter_unidad_str or search_term)
    personal_ids_to_filter_local = set()
    external_id_search_error = False
    selected_unidad_id = None # Asegurar inicialización

    if apply_external_id_filter and PLANILLA_APP_AVAILABLE:
        logger.debug("[Util Sueldos] Intentando obtener IDs externos para filtrar.")
        personal_ids_in_unidad = set()
        if filter_unidad_str:
            try:
                selected_unidad_id = int(filter_unidad_str)
                result['selected_unidad_id'] = selected_unidad_id
                # Buscar personal ACTIVO en esa unidad
                designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                    .filter(unidad_id=selected_unidad_id, estado='ACTIVO') \
                    .values_list('personal_id', flat=True).distinct()
                personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
                logger.info(f"[Util Sueldos] IDs externos en Unidad {selected_unidad_id}: {len(personal_ids_in_unidad)}")
            except (ValueError, TypeError):
                logger.warning(f"[Util Sueldos] ID de Unidad inválido: '{filter_unidad_str}'")
                external_id_search_error = True
            except Exception as e:
                external_id_search_error = True
                logger.error(f"[Util Sueldos] Error obteniendo IDs por Unidad {selected_unidad_id}: {e}", exc_info=True)

        personal_ids_from_search = set()
        if search_term and not external_id_search_error:
             try:
                 item_numeric = None
                 try: item_numeric = int(search_term)
                 except ValueError: pass

                 q_filter = Q(ci__iexact=search_term)
                 ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(q_filter).values_list('id', flat=True)
                 personal_ids_from_search.update(ids_ci_qs)

                 if item_numeric is not None:
                      # Buscar por Item en designaciones ACTIVAS
                      ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                          .filter(item=item_numeric, estado='ACTIVO') \
                          .values_list('personal_id', flat=True).distinct()
                      personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)
                 logger.info(f"[Util Sueldos] IDs externos encontrados por búsqueda '{search_term}': {len(personal_ids_from_search)}")
             except Exception as e:
                 external_id_search_error = True
                 logger.error(f"[Util Sueldos] Error obteniendo IDs por Búsqueda '{search_term}': {e}", exc_info=True)

        if not external_id_search_error:
            # Combinar resultados de filtros
            if filter_unidad_str and search_term:
                personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
            elif search_term:
                personal_ids_to_filter_local = personal_ids_from_search
            elif filter_unidad_str:
                personal_ids_to_filter_local = personal_ids_in_unidad
        else:
             apply_external_id_filter = False # No filtrar si hubo error
             personal_ids_to_filter_local = set()
             result['error_message'] = (result.get('error_message') or '') + " Error buscando personal externo."

        if apply_external_id_filter and not personal_ids_to_filter_local:
             logger.info("[Util Sueldos] Filtro/Búsqueda no encontró IDs externos coincidentes.")
             # Forzaremos resultado vacío en el siguiente paso

    else: # Si no hay filtro unidad ni búsqueda
        logger.debug("[Util Sueldos] No se requiere filtro por IDs externos.")
        apply_external_id_filter = False


    # --- 5. Obtener, Filtrar (si aplica) y Enriquecer Detalles Locales ---
    try:
        # Query base: detalles de la planilla actual
        detalles_locales_qs = DetalleSueldo.objects.filter(planilla_sueldo=planilla)

        # Aplicar filtro por IDs externos si es necesario
        if apply_external_id_filter:
            if personal_ids_to_filter_local:
                logger.debug(f"[Util Sueldos] Aplicando filtro por ID externo: {personal_ids_to_filter_local}")
                # Filtramos por la ForeignKey usando __in
                detalles_locales_qs = detalles_locales_qs.filter(
                    personal_externo_id__in=personal_ids_to_filter_local
                )
            else:
                # Si se debía filtrar pero no hay IDs, forzar vacío
                logger.info("[Util Sueldos] Filtro por IDs activo pero sin IDs válidos, forzando resultado vacío.")
                detalles_locales_qs = DetalleSueldo.objects.none()

        # Pre-cargar datos relacionados de la BD externa para eficiencia
        # Usamos select_related para la FK directa 'personal_externo'
        # ¡OJO! Esto asume que 'personal_externo' se define en la BD 'default'
        # Si 'personal_externo' realmente vive en 'personas_db', select_related no funcionará
        # y tendremos que hacer el enriquecimiento manual después.
        # **Quitamos select_related ya que personal_externo está en otra BD**
        # detalles_locales_qs = detalles_locales_qs.select_related('personal_externo')

        # Ejecutar consulta y obtener lista
        detalles_locales_list = list(detalles_locales_qs)
        logger.info(f"[Util Sueldos] Detalles locales encontrados/filtrados: {len(detalles_locales_list)}")

        # Enriquecer si hay detalles y la app planilla está disponible
        if detalles_locales_list and PLANILLA_APP_AVAILABLE:
            # Obtener los IDs externos necesarios
            ids_needed = {d.personal_externo_id for d in detalles_locales_list if d.personal_externo_id}
            personal_info_ext = {}
            designaciones_info_ext = {}

            if ids_needed:
                # Obtener info personal externa (Nombre, CI)
                try:
                    # Traer solo campos necesarios
                    personas_externas = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(id__in=ids_needed) \
                        .only('id', 'nombre', 'apellido_paterno', 'apellido_materno', 'ci')
                    personal_info_ext = {p.id: p for p in personas_externas}
                    logger.debug(f"[Util Sueldos] Info Personal Externo obtenida para {len(personal_info_ext)} IDs.")
                except Exception as e_pers_f: logger.error(f"Error consulta personal externo: {e_pers_f}")

                # Obtener info designaciones externas (Item, Cargo) - Solo ACTIVAS
                try:
                    desig_query_ext = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                        .select_related('cargo') \
                        .order_by('personal_id', '-id') # Tomar la más reciente por si hay varias

                    # Procesar para obtener la más reciente por persona
                    designaciones_relevantes_ext = {}
                    processed_person_ids_ext = set()
                    for desig in desig_query_ext:
                        if desig.personal_id not in processed_person_ids_ext:
                            designaciones_relevantes_ext[desig.personal_id] = desig
                            processed_person_ids_ext.add(desig.personal_id)

                    # Crear dict de info externa (Item, Cargo)
                    designaciones_info_ext = {
                        pid: {
                            'item': desig.item,
                            'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A',
                        } for pid, desig in designaciones_relevantes_ext.items()
                    }
                    logger.debug(f"[Util Sueldos] Info Designaciones Externas obtenida para {len(designaciones_info_ext)} IDs.")
                except Exception as e_desig_f: logger.error(f"Error consulta designaciones externas: {e_desig_f}")

            # Bucle de enriquecimiento: Añadir atributos al objeto DetalleSueldo
            logger.debug(f"[Util Sueldos] Iniciando enriquecimiento para {len(detalles_locales_list)} detalles...")
            for detalle_obj in detalles_locales_list:
                persona_ext = personal_info_ext.get(detalle_obj.personal_externo_id)
                info_desig_ext = designaciones_info_ext.get(detalle_obj.personal_externo_id)

                # Añadir atributos _externo (serán usados en la plantilla)
                detalle_obj.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                detalle_obj.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                detalle_obj.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                # Usar la property 'nombre_completo' del modelo externo si existe
                detalle_obj.nombre_completo_externo = persona_ext.nombre_completo if (persona_ext and hasattr(persona_ext, 'nombre_completo')) \
                                                     else f'ID:{detalle_obj.personal_externo_id} (No Encontrado)'

            # Ordenar la lista ya enriquecida por nombre completo externo
            try:
                def get_sort_key_item_sueldo(detalle_obj_sueldo):
                    item_val_attr = getattr(detalle_obj_sueldo, 'item_externo', None)
                    nombre_completo_val = (getattr(detalle_obj_sueldo, 'nombre_completo_externo', '') or '').strip().upper()
                    
                    item_sort_val = float('inf') # Valor para ítems no válidos, None, o ausentes

                    if item_val_attr is not None and str(item_val_attr).strip():
                        try:
                            item_sort_val = int(str(item_val_attr).strip())
                        except ValueError:
                            logger.debug(f"[Util Sueldos] Item no numérico '{item_val_attr}' para {nombre_completo_val}, se ordenará al final.")
                            # Mantiene float('inf')
                    
                    return (item_sort_val, nombre_completo_val)

                detalles_locales_list.sort(key=get_sort_key_item_sueldo)
                logger.debug("[Util Sueldos] Lista de detalles sueldo ordenada por item_externo (asc) y luego por nombre.")

            except Exception as e_sort: logger.error(f"Error ordenando detalles: {e_sort}", exc_info=True)

        # --- Asignación final al diccionario result ---
        result['detalles_sueldo'] = detalles_locales_list # Asignar lista (puede estar vacía)

        # Generar lista de IDs si implementaremos edición rápida
        # result['detalle_ids_order'] = [d.id for d in detalles_locales_list]

    except Exception as e_general:
         logger.error(f"[Util Sueldos] Error INESPERADO obteniendo/procesando detalles: {e_general}", exc_info=True)
         result['error_message'] = (result.get('error_message') or '') + f" Error procesando detalles: {e_general}"
         result['detalles_sueldo'] = []
         # result['detalle_ids_order'] = []

    logger.debug(f"[Util Sueldos] Retornando contexto. Detalles: {len(result.get('detalles_sueldo', []))}")
    return result