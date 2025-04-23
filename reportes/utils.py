# reportes/utils.py (Versión Adaptada)

import logging
from django.shortcuts import get_object_or_404
# --- Importaciones Adaptadas ---
from .models import PlanillaAsistencia, DetalleAsistencia # Modelos locales
# Modelos externos (desde planilla)
try:
    from planilla.models import (
        PrincipalDesignacionExterno, PrincipalPersonalExterno,
        PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
    )
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    # Manejo básico si falla la importación
    PrincipalDesignacionExterno = None
    PrincipalPersonalExterno = None
    PrincipalCargoExterno = None
    PrincipalUnidadExterna = None
    PrincipalSecretariaExterna = None
    PLANILLA_APP_AVAILABLE = False
    logging.error("[Util Reportes] ERROR: No se pueden importar modelos externos de 'planilla'.")
# -----------------------------
from django.db.models import Q
from decimal import Decimal

logger = logging.getLogger(__name__)

# --- Función Adaptada ---
def get_processed_asistencia_details(request, planilla_asistencia_id):
    """
    Obtiene la PlanillaAsistencia, listas de filtros (externos), y los
    DetallesAsistencia (filtrados por unidad/búsqueda externa y
    enriquecidos con datos externos).
    """
    result = {
        'planilla_asistencia': None, # Cambiado nombre de clave
        'all_secretarias': PrincipalSecretariaExterna.objects.none(),
        'unidades_for_select': PrincipalUnidadExterna.objects.none(),
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'detalles_asistencia': [], # Cambiado nombre de clave
        'search_active': False,
        'error_message': None,
        'search_term': '',
    }

    if not PLANILLA_APP_AVAILABLE:
         result['error_message'] = "Componentes externos de la app 'planilla' no disponibles."
         return result

    # --- 0. Obtener la PlanillaAsistencia (Interna) ---
    try:
        # Cambiado a PlanillaAsistencia
        planilla = PlanillaAsistencia.objects.get(pk=planilla_asistencia_id)
        result['planilla_asistencia'] = planilla # Actualizada clave
        logger.info(f"[Util Asistencia] Procesando PlanillaAsistencia ID {planilla.id} (Tipo: {planilla.get_tipo_display()})")
    except PlanillaAsistencia.DoesNotExist: # Cambiado modelo
        logger.error(f"[Util Asistencia] PlanillaAsistencia con ID={planilla_asistencia_id} no encontrada.")
        result['error_message'] = f"Reporte de Asistencia ID {planilla_asistencia_id} no encontrado."
        return result
    except Exception as e_plan:
        logger.error(f"[Util Asistencia] Error obteniendo PlanillaAsistencia ID {planilla_asistencia_id}: {e_plan}", exc_info=True)
        result['error_message'] = f"Error inesperado al buscar el reporte de asistencia: {e_plan}"
        return result

    # --- 1. Obtener Secretarías Externas (Sin cambios) ---
    try:
        all_secretarias = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
        result['all_secretarias'] = all_secretarias
    except Exception as e_sec:
        logger.error(f"[Util Asistencia] Error obteniendo secretarías externas: {e_sec}", exc_info=True)
        result['error_message'] = f"No se pudo cargar la lista de secretarías externas: {e_sec}"

    # --- 2. Procesar Filtros GET (Sin cambios lógicos) ---
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    result['search_active'] = bool(filter_secretaria_str or filter_unidad_str or search_term)
    logger.debug(f"[Util Asistencia] GET Params: secretaria='{filter_secretaria_str}', unidad='{filter_unidad_str}', q='{search_term}' | Search Active: {result['search_active']}")

    # --- 3. Cargar Unidades Externas si se seleccionó Secretaría (Sin cambios lógicos) ---
    unidades_qs = PrincipalUnidadExterna.objects.none()
    selected_secretaria_id = None
    if filter_secretaria_str:
        try:
            selected_secretaria_id = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = unidades_qs
        except (ValueError, TypeError):
             logger.warning(f"[Util Asistencia] ID de Secretaría externa inválido: '{filter_secretaria_str}'")
             result['selected_secretaria_id'] = None
        except Exception as e_uni:
             logger.error(f"[Util Asistencia] Error obteniendo unidades externas para sec ID {selected_secretaria_id}: {e_uni}", exc_info=True)
             result['unidades_for_select'] = PrincipalUnidadExterna.objects.none()

    # --- 4. Obtener IDs de Personal Externo Relevantes (Sin cambios lógicos) ---
    personal_ids_to_filter_local = set()
    proceed_with_details = result['search_active']

    personal_ids_in_unidad = set()
    selected_unidad_id = None
    if filter_unidad_str:
        try:
            selected_unidad_id = int(filter_unidad_str)
            result['selected_unidad_id'] = selected_unidad_id
            designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                .filter(unidad_id=selected_unidad_id, estado='ACTIVO') \
                .values_list('personal_id', flat=True).distinct()
            personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
            logger.info(f"[Util Asistencia] IDs externos en Unidad {selected_unidad_id} (Activos): {len(personal_ids_in_unidad)}")
        except (ValueError, TypeError):
             logger.warning(f"[Util Asistencia] ID de Unidad externa inválido: '{filter_unidad_str}'")
             result['error_message'] = "ID de Unidad inválido."
             proceed_with_details = False
        except Exception as e_pers_ids:
            logger.error(f"[Util Asistencia] Error obteniendo personal_ids externos para Unidad {selected_unidad_id}: {e_pers_ids}", exc_info=True)
            result['error_message'] = "Error al buscar personal externo en la unidad."
            proceed_with_details = False

    personal_ids_from_search = set()
    if search_term:
        try:
            item_numeric = None
            try: item_numeric = int(search_term)
            except: item_numeric = None

            ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(ci__iexact=search_term) \
                        .values_list('id', flat=True)
            personal_ids_from_search.update(ids_ci_qs)

            if item_numeric is not None:
                ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .filter(item=item_numeric, estado='ACTIVO') \
                            .values_list('personal_id', flat=True).distinct()
                personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)

            logger.info(f"[Util Asistencia] IDs externos encontrados por búsqueda '{search_term}': {len(personal_ids_from_search)}")
        except Exception as e_search:
            logger.error(f"[Util Asistencia] Error durante búsqueda externa para '{search_term}': {e_search}", exc_info=True)
            result['error_message'] = "Error durante la búsqueda externa."
            proceed_with_details = False

    if filter_unidad_str and search_term:
        personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
    elif search_term:
        personal_ids_to_filter_local = personal_ids_from_search
    elif filter_unidad_str:
        personal_ids_to_filter_local = personal_ids_in_unidad
    else:
        logger.debug("[Util Asistencia] Sin filtro de unidad ni búsqueda activa para IDs externos.")

    logger.debug(f"[Util Asistencia] IDs externos finales para filtrar DetalleAsistencia: {personal_ids_to_filter_local if personal_ids_to_filter_local else 'NINGUNO (se mostrarán todos si no hay búsqueda activa)'}")

    # --- 5. Obtener y Enriquecer Detalles Locales ---
    # Si hay filtro/búsqueda, debe haber IDs externos para mostrar algo
    if result['search_active'] and not personal_ids_to_filter_local:
         logger.info("[Util Asistencia] Filtro/Búsqueda activa pero no se encontraron IDs externos coincidentes.")
         result['detalles_asistencia'] = [] # Cambiada clave
         proceed_with_details = False # No continuar con enriquecimiento
    # Si no hay filtro/búsqueda, mostraremos *todos* los detalles de la planilla
    elif not result['search_active']:
         proceed_with_details = True # Mostraremos todos
         personal_ids_to_filter_local = set() # Sin filtro de IDs

    # Obtenemos y enriquecemos solo si proceed_with_details es True
    if proceed_with_details:
        try:
            # PASO A: Filtrar Detalles Locales por Planilla (y por IDs externos SI APLICA)
            # --- ¡CAMBIO CLAVE AQUÍ! ---
            detalles_locales_qs = DetalleAsistencia.objects.filter(
                planilla_asistencia=planilla # Filtro por cabecera
            )
            # Aplicar filtro de IDs externos solo si venía de búsqueda/unidad
            if personal_ids_to_filter_local:
                logger.debug(f"[Util Asistencia] Aplicando filtro por personal_externo_id__in: {personal_ids_to_filter_local}")
                detalles_locales_qs = detalles_locales_qs.filter(
                    personal_externo_id__in=personal_ids_to_filter_local
                )
            # --------------------------

            detalles_locales_filtrados = list(detalles_locales_qs)
            logger.info(f"[Util Asistencia] Detalles de Asistencia internos encontrados: {len(detalles_locales_filtrados)}")

            # PASO B: Enriquecer (si hay detalles locales)
            if detalles_locales_filtrados:
                ids_needed = {d.personal_externo_id for d in detalles_locales_filtrados if d.personal_externo_id}
                logger.debug(f"[Util Asistencia] IDs externos necesarios para enriquecimiento: {ids_needed}")

                personal_info_ext = {}
                designaciones_info_ext = {} # Para item, cargo, unidad

                # Consultar info de Personal Externo
                if ids_needed:
                    try:
                        personas_externas = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed)
                        personal_info_ext = {p.id: p for p in personas_externas}
                        logger.debug(f"[Util Asistencia] Info Personal Externo obtenida para {len(personal_info_ext)} IDs.")
                    except Exception as e_pers_f: logger.error(f"Error consultando personal externo para enriquecer: {e_pers_f}")

                # Consultar info de Designación Externa (ACTIVA y relevante)
                if ids_needed:
                    try:
                        desig_query_ext = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                            .select_related('cargo', 'unidad') \
                            .order_by('personal_id', '-id') # Más reciente por persona

                        # Aquí podríamos añadir el filtro por unidad si se aplicó
                        # Esto asegura que el item/cargo/unidad mostrados sean los de la unidad filtrada
                        # (si el usuario filtró por unidad).
                        if selected_unidad_id:
                           logger.debug(f"[Util Asistencia]   Añadiendo filtro de unidad_id={selected_unidad_id} a consulta designaciones para enriquecimiento")
                           desig_query_ext = desig_query_ext.filter(unidad_id=selected_unidad_id)

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
                                'unidad_nombre': desig.unidad.nombre_unidad if desig.unidad else 'N/A'
                            } for pid, desig in designaciones_relevantes_ext.items()
                        }
                        logger.debug(f"[Util Asistencia] Info Designaciones Externas obtenida para {len(designaciones_info_ext)} IDs.")
                    except Exception as e_desig_f: logger.error(f"Error consultando designaciones externas para enriquecer: {e_desig_f}")

                # Bucle de enriquecimiento
                enriched_list_temp = []
                for detalle in detalles_locales_filtrados:
                    persona_ext = personal_info_ext.get(detalle.personal_externo_id)
                    info_desig_ext = designaciones_info_ext.get(detalle.personal_externo_id)

                    # Añadir atributos con sufijo _externo
                    detalle.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                    detalle.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                    detalle.unidad_externa_nombre = info_desig_ext.get('unidad_nombre', 'N/A') if info_desig_ext else 'N/A'
                    detalle.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                    detalle.nombre_completo_externo = persona_ext.nombre_completo if persona_ext else f'No encontrado ({detalle.personal_externo_id})'

                    enriched_list_temp.append(detalle)

                # Ordenar (Opcional, igual que antes)
                # ... (código de ordenamiento basado en nombre_completo_externo si se desea) ...
                # Orden simple por ahora:
                enriched_list_temp.sort(key=lambda x: (
                    getattr(x, 'nombre_completo_externo', '').split(' ')[0] or '', # Apellido Paterno Aprox.
                    getattr(x, 'nombre_completo_externo', '').split(' ')[1] if len(getattr(x, 'nombre_completo_externo', '').split(' ')) > 1 else '', # Apellido Materno Aprox.
                    getattr(x, 'nombre_completo_externo', '').split(' ')[-1] or '' # Nombre Aprox.
                 ))


                result['detalles_asistencia'] = enriched_list_temp # Actualizada clave
                logger.info(f"[Util Asistencia] Enriquecimiento externo completado para {len(enriched_list_temp)} detalles.")

        except Exception as e_filter_enrich:
             logger.error(f"[Util Asistencia] Error general durante filtrado/enriquecimiento: {e_filter_enrich}", exc_info=True)
             result['error_message'] = f"Ocurrió un error al procesar los detalles: {e_filter_enrich}"
             result['detalles_asistencia'] = [] # Actualizada clave

    logger.debug(f"--- [Util Asistencia] FIN (PlanillaAsistencia: {planilla_asistencia_id}) ---")
    return result