# reportes/utils.py
import logging
from django.shortcuts import get_object_or_404
from .models import PlanillaAsistencia, DetalleAsistencia
try:
    from planilla.models import (
        PrincipalDesignacionExterno, PrincipalPersonalExterno,
        PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
    )
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalDesignacionExterno, PrincipalPersonalExterno, PrincipalCargoExterno = None, None, None
    PrincipalUnidadExterna, PrincipalSecretariaExterna = None, None
    PLANILLA_APP_AVAILABLE = False
    logging.error("[Util Reportes] ERROR: No se pueden importar modelos externos de 'planilla'.")
from django.db.models import Q
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_processed_asistencia_details(request, planilla_asistencia_id):
    """
    Obtiene la PlanillaAsistencia, listas de filtros (externos), y los
    DetallesAsistencia (filtrados por unidad/búsqueda externa si aplica, y
    enriquecidos con datos externos). Genera la lista ordenada de IDs
    para la funcionalidad de edición rápida.
    """
    result = {
        'planilla_asistencia': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none(),
        'unidades_for_select': PrincipalUnidadExterna.objects.none(),
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'detalles_asistencia': [],
        'detalle_ids_order': [], # Asegurar que se inicializa
        'search_active': False, # Indica si el *usuario* activó un filtro/búsqueda
        'error_message': None,
        'search_term': '',
    }

    if not PLANILLA_APP_AVAILABLE:
         result['error_message'] = "Componentes externos de la app 'planilla' no disponibles."
         logger.critical("[Util Asistencia] PLANILLA_APP_AVAILABLE es False.")
         # return result # Opcional: detener si es crítico

    # --- 0. Obtener PlanillaAsistencia ---
    try:
        planilla = PlanillaAsistencia.objects.get(pk=planilla_asistencia_id)
        result['planilla_asistencia'] = planilla
        logger.info(f"[Util Asistencia] Procesando PlanillaAsistencia ID {planilla.id}")
    except PlanillaAsistencia.DoesNotExist:
        logger.error(f"[Util Asistencia] PlanillaAsistencia ID={planilla_asistencia_id} no encontrada.")
        result['error_message'] = f"Reporte Asistencia ID {planilla_asistencia_id} no encontrado."
        return result
    except Exception as e_plan:
        logger.error(f"[Util Asistencia] Error obteniendo PlanillaAsistencia ID {planilla_asistencia_id}: {e_plan}", exc_info=True)
        result['error_message'] = "Error buscando el reporte."
        return result

    # --- 1. Obtener Secretarías Externas ---
    if PLANILLA_APP_AVAILABLE:
        try:
            all_secretarias = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
            result['all_secretarias'] = all_secretarias
        except Exception as e_sec:
            logger.error(f"[Util Asistencia] Error obteniendo secretarías: {e_sec}", exc_info=True)
            result['error_message'] = (result.get('error_message') or '') + " Error cargando secretarías."

    # --- 2. Procesar Filtros GET ---
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    result['search_active'] = bool(request.GET.get('buscar')) # Basado en si se envió el botón/param
    logger.debug(f"[Util Asistencia] GET Params: sec='{filter_secretaria_str}', un='{filter_unidad_str}', q='{search_term}' | Search Active: {result['search_active']}")

    # --- 3. Cargar Unidades si aplica ---
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
        logger.debug("[Util Asistencia] Intentando obtener IDs externos para filtrar.")
        personal_ids_in_unidad = set()
        if filter_unidad_str:
            try:
                selected_unidad_id = int(filter_unidad_str)
                result['selected_unidad_id'] = selected_unidad_id # Guardar el ID válido
                # ... (consulta designaciones por unidad_id) ...
                designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(unidad_id=selected_unidad_id, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
            except Exception as e: external_id_search_error = True; logger.error(f"Error IDs por Unidad {selected_unidad_id}: {e}")

        personal_ids_from_search = set()
        if search_term and not external_id_search_error:
             try:
                 # ... (consulta por CI y/o Item) ...
                 item_numeric = None
                 try: item_numeric = int(search_term)
                 except: pass
                 ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(ci__iexact=search_term).values_list('id', flat=True)
                 personal_ids_from_search.update(ids_ci_qs)
                 if item_numeric is not None:
                      ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(item=item_numeric, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                      personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)
             except Exception as e: external_id_search_error = True; logger.error(f"Error IDs por Búsqueda '{search_term}': {e}")

        if not external_id_search_error:
            if filter_unidad_str and search_term: personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
            elif search_term: personal_ids_to_filter_local = personal_ids_from_search
            elif filter_unidad_str: personal_ids_to_filter_local = personal_ids_in_unidad
        else:
             apply_external_id_filter = False # No filtrar si hubo error obteniendo IDs
             personal_ids_to_filter_local = set()

        if apply_external_id_filter and not personal_ids_to_filter_local:
             logger.info("[Util Asistencia] Filtro/Búsqueda no encontró IDs externos coincidentes.")
             # Forzaremos resultado vacío en el siguiente paso

    else: # Si no hay filtro unidad ni búsqueda
        logger.debug("[Util Asistencia] No se requiere filtro por IDs externos.")
        apply_external_id_filter = False


    # --- 5. Obtener, Filtrar (si aplica) y Enriquecer Detalles Locales ---
    try:
        # Obtener query base de detalles locales
        detalles_locales_qs = DetalleAsistencia.objects.filter(
            planilla_asistencia=planilla
        )

        # Aplicar filtro por IDs externos si es necesario
        if apply_external_id_filter:
            if personal_ids_to_filter_local:
                logger.debug(f"[Util Asistencia] Aplicando filtro por ID externo: {personal_ids_to_filter_local}")
                detalles_locales_qs = detalles_locales_qs.filter(
                    personal_externo_id__in=personal_ids_to_filter_local
                )
            else:
                # Si se debía filtrar pero no hay IDs, forzar vacío
                logger.info("[Util Asistencia] Filtro por IDs activo pero sin IDs válidos, forzando resultado vacío.")
                detalles_locales_qs = DetalleAsistencia.objects.none()

        # Ejecutar consulta y obtener lista
        detalles_locales_list = list(detalles_locales_qs)
        logger.info(f"[Util Asistencia] Detalles locales encontrados/filtrados: {len(detalles_locales_list)}")

        # Enriquecer si hay detalles y la app planilla está disponible
        if detalles_locales_list and PLANILLA_APP_AVAILABLE:
            ids_needed = {d.personal_externo_id for d in detalles_locales_list if d.personal_externo_id}
            personal_info_ext = {}
            designaciones_info_ext = {}

            if ids_needed:
                # Obtener info personal externa
                try:
                    personas_externas = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed)
                    personal_info_ext = {p.id: p for p in personas_externas}
                except Exception as e_pers_f: logger.error(f"Error consulta personal externo: {e_pers_f}")

                # Obtener info designaciones externas
                try:
                    desig_query_ext = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                        .select_related('cargo', 'unidad') \
                        .order_by('personal_id', '-id')
                    if selected_unidad_id: # Aplicar filtro unidad si existe
                       desig_query_ext = desig_query_ext.filter(unidad_id=selected_unidad_id)
                    # ... (procesar desig_query_ext para obtener designaciones_info_ext como antes) ...
                    designaciones_relevantes_ext = {}
                    processed_person_ids_ext = set()
                    for desig in desig_query_ext:
                        if desig.personal_id not in processed_person_ids_ext:
                            designaciones_relevantes_ext[desig.personal_id] = desig
                            processed_person_ids_ext.add(desig.personal_id)
                    designaciones_info_ext = { pid: {'item': d.item, 'cargo': d.cargo.nombre_cargo if d.cargo else 'N/A', 'unidad_nombre': d.unidad.nombre_unidad if d.unidad else 'N/A'} for pid, d in designaciones_relevantes_ext.items() }

                except Exception as e_desig_f: logger.error(f"Error consulta designaciones externas: {e_desig_f}")

            # Bucle de enriquecimiento
            logger.debug(f"[Util Asistencia] Iniciando enriquecimiento para {len(detalles_locales_list)} detalles...")
            for detalle_obj in detalles_locales_list:
                persona_ext = personal_info_ext.get(detalle_obj.personal_externo_id)
                info_desig_ext = designaciones_info_ext.get(detalle_obj.personal_externo_id)
                # Añadir atributos _externo
                detalle_obj.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                detalle_obj.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                # ... (añadir unidad_externa_nombre, ci_externo, nombre_completo_externo) ...
                detalle_obj.unidad_externa_nombre = info_desig_ext.get('unidad_nombre', 'N/A') if info_desig_ext else 'N/A'
                detalle_obj.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                detalle_obj.nombre_completo_externo = persona_ext.nombre_completo if persona_ext else f'ID:{detalle_obj.personal_externo_id} (No Encontrado)'

            # Ordenar la lista ya enriquecida
            try:
                 detalles_locales_list.sort(key=lambda x: ( (getattr(x, 'nombre_completo_externo', '') or '').strip().upper().split(' ') + [''] * 3 )[0:3])
                 logger.debug("[Util Asistencia] Lista de detalles ordenada por nombre.")
            except Exception as e_sort: logger.error(f"Error ordenando detalles: {e_sort}", exc_info=True)

        # --- Asignación final al diccionario result ---
        result['detalles_asistencia'] = detalles_locales_list # Asignar lista (puede estar vacía)

        # Generar lista de IDs A PARTIR de la lista final (detalles_locales_list)
        try:
             ids_generados = [d.id for d in detalles_locales_list]
             result['detalle_ids_order'] = ids_generados
             logger.debug(f"[Util Asistencia] Lista detalle_ids_order GENERADA: {result['detalle_ids_order']}")
        except Exception as e_ids:
             logger.error(f"[Util Asistencia] Error generando lista de IDs: {e_ids}", exc_info=True)
             result['detalle_ids_order'] = [] # Asegurar vacío en error


    except Exception as e_general:
         logger.error(f"[Util Asistencia] Error INESPERADO obteniendo/procesando detalles: {e_general}", exc_info=True)
         result['error_message'] = (result.get('error_message') or '') + f" Error procesando detalles: {e_general}"
         result['detalles_asistencia'] = [] # Asegurar vacío en error
         result['detalle_ids_order'] = [] # Asegurar vacío en error

    # Log final
    logger.debug(f"[Util Asistencia] Retornando contexto. "
                 f"detalles: {len(result.get('detalles_asistencia', []))}, "
                 f"ids_order: {len(result.get('detalle_ids_order', []))}, "
                 f"IDs (5): {result.get('detalle_ids_order', [])[:5]}")

    return result