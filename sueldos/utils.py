import logging
from django.shortcuts import get_object_or_404
from .models import PlanillaSueldo, DetalleSueldo 
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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
    logging.error("[Util Sueldos] ERROR: No se pueden importar modelos externos de 'planilla'.")
from django.db.models import Q
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_processed_sueldo_details(request, planilla_id, items_por_pagina=25):
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
        'page_obj': None,
        'search_active': False,
        'error_message': None,
        'search_term': '',
    }

    if not PLANILLA_APP_AVAILABLE:
         result['error_message'] = "Componentes externos de personal no disponibles."

    # --- Obtener PlanillaSueldo ---
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
    result['search_active'] = bool(filter_secretaria_str or filter_unidad_str or search_term)
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
    selected_unidad_id = None 

    if apply_external_id_filter and PLANILLA_APP_AVAILABLE:
        logger.debug("[Util Sueldos] Intentando obtener IDs externos para filtrar.")
        personal_ids_in_unidad = set()
        if filter_unidad_str:
            try:
                selected_unidad_id = int(filter_unidad_str)
                result['selected_unidad_id'] = selected_unidad_id
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
                      ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                          .filter(item=item_numeric, estado='ACTIVO') \
                          .values_list('personal_id', flat=True).distinct()
                      personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)
                 logger.info(f"[Util Sueldos] IDs externos encontrados por búsqueda '{search_term}': {len(personal_ids_from_search)}")
             except Exception as e:
                 external_id_search_error = True
                 logger.error(f"[Util Sueldos] Error obteniendo IDs por Búsqueda '{search_term}': {e}", exc_info=True)

        if not external_id_search_error:
            if filter_unidad_str and search_term:
                personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
            elif search_term:
                personal_ids_to_filter_local = personal_ids_from_search
            elif filter_unidad_str:
                personal_ids_to_filter_local = personal_ids_in_unidad
        else:
             apply_external_id_filter = False 
             personal_ids_to_filter_local = set()
             result['error_message'] = (result.get('error_message') or '') + " Error buscando personal externo."

        if apply_external_id_filter and not personal_ids_to_filter_local:
             logger.info("[Util Sueldos] Filtro/Búsqueda no encontró IDs externos coincidentes.")

    else: 
        logger.debug("[Util Sueldos] No se requiere filtro por IDs externos.")
        apply_external_id_filter = False


    # --- 5. Obtener, Filtrar (si aplica) y Enriquecer Detalles Locales ---
    try:
        detalles_locales_qs = DetalleSueldo.objects.filter(planilla_sueldo=planilla)
        logger.debug(f"[Util Sueldos] Queryset inicial: {detalles_locales_qs.count()} detalles.") 

        if apply_external_id_filter:
            if personal_ids_to_filter_local:
                logger.debug(f"[Util Sueldos] Aplicando filtro por ID externo: {personal_ids_to_filter_local}")
                detalles_locales_qs = detalles_locales_qs.filter(
                    personal_externo_id__in=personal_ids_to_filter_local
                )
                logger.debug(f"[Util Sueldos] Queryset TRAS FILTRO IDs: {detalles_locales_qs.count()} detalles.") # LOG AÑADIDO
            else:
                logger.info("[Util Sueldos] Filtro por IDs activo pero sin IDs válidos, forzando resultado vacío.")
                detalles_locales_qs = DetalleSueldo.objects.none()

        detalles_locales_list = list(detalles_locales_qs)
        logger.info(f"[Util Sueldos] Detalles locales encontrados/filtrados: {len(detalles_locales_list)}")

        if detalles_locales_list and PLANILLA_APP_AVAILABLE:
            ids_needed = {d.personal_externo_id for d in detalles_locales_list if d.personal_externo_id}
            logger.debug(f"[Util Sueldos] IDs para enriquecer: {len(ids_needed)} - {list(ids_needed)[:10]}") # LOG AÑADIDO
            personal_info_ext = {}
            designaciones_info_ext = {}

            if ids_needed:
                try:
                    personas_externas = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(id__in=ids_needed) \
                        .only('id', 'nombre', 'apellido_paterno', 'apellido_materno', 'ci')
                    personal_info_ext = {p.id: p for p in personas_externas}
                    logger.debug(f"[Util Sueldos] ENRIQUECIMIENTO: Obtenidos {len(personal_info_ext)} perfiles de personal.") # LOG AÑADIDO
                except Exception as e_pers_f: logger.error(f"Error consulta personal externo: {e_pers_f}")

                try:
                    desig_query_ext = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                        .select_related('cargo') \
                        .order_by('personal_id', '-id') 

                    designaciones_relevantes_ext = {}
                    processed_person_ids_ext = set()
                    for desig in desig_query_ext:
                        if desig.personal_id not in processed_person_ids_ext:
                            designaciones_relevantes_ext[desig.personal_id] = desig
                            processed_person_ids_ext.add(desig.personal_id)

                    designaciones_info_ext = {
                        pid: {
                            'item': desig.item,
                            'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A',
                        } for pid, desig in designaciones_relevantes_ext.items()
                    }
                    logger.debug(f"[Util Sueldos] Info Designaciones Externas obtenida para {len(designaciones_info_ext)} IDs.")
                except Exception as e_desig_f: logger.error(f"Error consulta designaciones externas: {e_desig_f}")

            logger.debug(f"[Util Sueldos] Iniciando enriquecimiento para {len(detalles_locales_list)} detalles...")
            for detalle_obj in detalles_locales_list:
                persona_ext = personal_info_ext.get(detalle_obj.personal_externo_id)
                info_desig_ext = designaciones_info_ext.get(detalle_obj.personal_externo_id)

                detalle_obj.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                detalle_obj.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                detalle_obj.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                detalle_obj.nombre_completo_externo = persona_ext.nombre_completo if (persona_ext and hasattr(persona_ext, 'nombre_completo')) \
                                                     else f'ID:{detalle_obj.personal_externo_id} (No Encontrado)'
            try:
                def get_sort_key_item_sueldo(detalle_obj_sueldo):
                    item_val_attr = getattr(detalle_obj_sueldo, 'item_externo', None)
                    nombre_completo_val = (getattr(detalle_obj_sueldo, 'nombre_completo_externo', '') or '').strip().upper()
                    
                    item_sort_val = float('inf') 

                    if item_val_attr is not None and str(item_val_attr).strip():
                        try:
                            item_sort_val = int(str(item_val_attr).strip())
                        except ValueError:
                            logger.debug(f"[Util Sueldos] Item no numérico '{item_val_attr}' para {nombre_completo_val}, se ordenará al final.")
                    
                    return (item_sort_val, nombre_completo_val)

                detalles_locales_list.sort(key=get_sort_key_item_sueldo)
                logger.debug("[Util Sueldos] Lista de detalles sueldo ordenada por item_externo (asc) y luego por nombre.")

            except Exception as e_sort: logger.error(f"Error ordenando detalles: {e_sort}", exc_info=True)

        # --- APLICAR PAGINACIÓN a la lista ya filtrada, enriquecida y ordenada ---
        page_number_str = request.GET.get('page', '1')
        paginator = Paginator(detalles_locales_list, items_por_pagina)
        logger.debug(f"[Util Sueldos] Paginator: count={paginator.count}, num_pages={paginator.num_pages}, items_por_pagina={items_por_pagina}")

        try:
            page_obj_resultado = paginator.page(page_number_str)
        except PageNotAnInteger:
            page_obj_resultado = paginator.page(1)
            logger.warning(f"[Util Sueldos] Número de página inválido ('{page_number_str}'). Mostrando página 1.")
        except EmptyPage:
            page_obj_resultado = paginator.page(paginator.num_pages)
            logger.warning(f"[Util Sueldos] Página '{page_number_str}' fuera de rango. Mostrando última página {paginator.num_pages}.")

        result['page_obj'] = page_obj_resultado 

        if page_obj_resultado:
            result['detalle_ids_order'] = [d.id for d in page_obj_resultado.object_list]
            logger.debug(f"[Util Sueldos] Página actual: {page_obj_resultado.number}, Items en página: {len(page_obj_resultado.object_list)}")
        else:
            result['detalle_ids_order'] = []

    except Exception as e_general:
         logger.error(f"[Util Sueldos] Error INESPERADO obteniendo/procesando detalles: {e_general}", exc_info=True)
         result['error_message'] = (result.get('error_message') or '') + f" Error procesando detalles: {e_general}"
         result['detalles_sueldo'] = []
    logger.debug(f"[Util Sueldos] Retornando contexto. Detalles: {len(result.get('detalles_sueldo', []))}")
    return result