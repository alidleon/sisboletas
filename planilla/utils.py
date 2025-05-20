# planilla/utils.py (Versión Restaurada + Debug Prints)

import logging
from django.shortcuts import get_object_or_404
# Importa los modelos externos necesarios
from .models import (
    Planilla, DetalleBonoTe,
    PrincipalDesignacionExterno, PrincipalPersonalExterno,
    PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
)
from django.db.models import Q
from decimal import Decimal # Para convertir Item

logger = logging.getLogger(__name__)

def get_processed_planilla_details(request, planilla_id):
    """
    Obtiene la planilla, listas de filtros (externos), y los detalles de Bono TE
    (filtrados por unidad/búsqueda externa y enriquecidos con datos externos).
    Incluye prints de depuración.
    """
    result = {
        'planilla': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none(),
        'unidades_for_select': PrincipalUnidadExterna.objects.none(),
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'detalles_enriquecidos': [],
        'search_active': False,
        'error_message': None,
        'search_term': '',
    }

    # --- 0. Obtener la Planilla (Interna) ---
    try:
        planilla = Planilla.objects.get(pk=planilla_id)
        result['planilla'] = planilla
        logger.info(f"[Util] Procesando Planilla ID {planilla.id} (Tipo: {planilla.get_tipo_display()})")
    except Planilla.DoesNotExist:
        logger.error(f"[Util] Planilla con ID={planilla_id} no encontrada.")
        result['error_message'] = f"Planilla ID {planilla_id} no encontrada."
        return result
    except Exception as e_plan:
        logger.error(f"[Util] Error obteniendo Planilla ID {planilla_id}: {e_plan}", exc_info=True)
        result['error_message'] = f"Error inesperado al buscar la planilla: {e_plan}"
        return result

    # --- 1. Obtener Secretarías Externas ---
    try:
        # Consulta a BD externa
        all_secretarias = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
        result['all_secretarias'] = all_secretarias
    except Exception as e_sec:
        logger.error(f"[Util] Error obteniendo secretarías externas: {e_sec}", exc_info=True)
        result['error_message'] = f"No se pudo cargar la lista de secretarías externas: {e_sec}"
        # No es fatal, continuar

    # --- 2. Procesar Filtros GET (Secretaría, Unidad, Búsqueda 'q') ---
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    print(f"\n--- [DEBUG UTIL] ---") # Separador para cada request
    print(f"[DEBUG UTIL] GET Params: secretaria='{filter_secretaria_str}', unidad='{filter_unidad_str}', q='{search_term}'") # LOG 0

    # Marcar si hay filtro/búsqueda activa
    result['search_active'] = bool(filter_secretaria_str or filter_unidad_str or search_term)
    print(f"[DEBUG UTIL] Search Active: {result['search_active']}")

    # --- 3. Cargar Unidades Externas si se seleccionó Secretaría ---
    unidades_qs = PrincipalUnidadExterna.objects.none()
    selected_secretaria_id = None
    if filter_secretaria_str:
        try:
            selected_secretaria_id = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id
            print(f"[DEBUG UTIL] Consultando Unidades Externas para secretaria_id={selected_secretaria_id}") # LOG 3.1
            # Consulta a BD externa
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = unidades_qs
            # print(f"[DEBUG UTIL] Unidades Externas encontradas: {list(unidades_qs.values_list('nombre_unidad', flat=True))}") # LOG 3.2 (Opcional, puede ser largo)
        except (ValueError, TypeError):
             logger.warning(f"[Util] ID de Secretaría externa inválido: '{filter_secretaria_str}'")
             result['selected_secretaria_id'] = None
        except Exception as e_uni:
             logger.error(f"[Util] Error obteniendo unidades externas para sec ID {selected_secretaria_id}: {e_uni}", exc_info=True)
             result['unidades_for_select'] = PrincipalUnidadExterna.objects.none()

    # --- 4. Obtener IDs de Personal Externo Relevantes ---
    personal_ids_to_filter_local = set()
    proceed_with_details = result['search_active'] # Buscar detalles si hay filtro/búsqueda

    personal_ids_in_unidad = set()
    selected_unidad_id = None
    if filter_unidad_str:
        try:
            selected_unidad_id = int(filter_unidad_str)
            result['selected_unidad_id'] = selected_unidad_id
            print(f"[DEBUG UTIL] Filtrando Designaciones Externas por unidad_id={selected_unidad_id} y estado='ACTIVO'") # LOG 1
            # Consulta a BD externa, asumiendo estado='ACTIVO'
            designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                .filter(unidad_id=selected_unidad_id, estado='ACTIVO') \
                .values_list('personal_id', flat=True).distinct()
            personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
            print(f"[DEBUG UTIL] IDs externos encontrados en unidad ({selected_unidad_id}): {personal_ids_in_unidad}") # LOG 2
            logger.info(f"[Util] IDs externos en Unidad {selected_unidad_id} (Activos): {len(personal_ids_in_unidad)}")

        except (ValueError, TypeError):
             logger.warning(f"[Util] ID de Unidad externa inválido: '{filter_unidad_str}'")
             result['error_message'] = "ID de Unidad inválido."
             proceed_with_details = False
        except Exception as e_pers_ids:
            logger.error(f"[Util] Error obteniendo personal_ids externos para Unidad {selected_unidad_id}: {e_pers_ids}", exc_info=True)
            result['error_message'] = "Error al buscar personal externo en la unidad."
            proceed_with_details = False

    # 4.b Búsqueda Externa (CI o Item)
    personal_ids_from_search = set()
    if search_term:
        try:
            item_numeric = None
            try: item_numeric = int(search_term) # O Decimal? Verifica tipo de Item
            except: item_numeric = None
            print(f"[DEBUG UTIL] Buscando por CI='{search_term}' o Item={item_numeric}") # LOG 3.0

            # Consulta CI en Personal Externo
            ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(ci__iexact=search_term) \
                        .values_list('id', flat=True)
            ids_ci = list(ids_ci_qs) # Ejecutar consulta
            personal_ids_from_search.update(ids_ci)
            print(f"[DEBUG UTIL] IDs externos encontrados por CI: {ids_ci}") # LOG 3a

            # Consulta Item en Designacion Externa (Activa)
            if item_numeric is not None:
                ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .filter(item=item_numeric, estado='ACTIVO') \
                            .values_list('personal_id', flat=True).distinct()
                ids_item = list(p_id for p_id in ids_item_qs if p_id is not None) # Ejecutar y filtrar Nones
                personal_ids_from_search.update(ids_item)
                print(f"[DEBUG UTIL] IDs externos encontrados por Item ({item_numeric}, Activo): {ids_item}") # LOG 3b
            else:
                print("[DEBUG UTIL] Término de búsqueda no es numérico, no se busca por Item.")

            print(f"[DEBUG UTIL] IDs externos combinados de búsqueda: {personal_ids_from_search}") # LOG 3c
            logger.info(f"[Util] IDs externos encontrados por búsqueda '{search_term}': {len(personal_ids_from_search)}")

        except Exception as e_search:
            logger.error(f"[Util] Error durante búsqueda externa para '{search_term}': {e_search}", exc_info=True)
            result['error_message'] = "Error durante la búsqueda externa."
            proceed_with_details = False

    # 4.c Combinar resultados
    if filter_unidad_str and search_term:
        personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
        print(f"[DEBUG UTIL] Combinación: Intersección Unidad y Búsqueda")
    elif search_term:
        personal_ids_to_filter_local = personal_ids_from_search
        print(f"[DEBUG UTIL] Combinación: Solo Búsqueda")
    elif filter_unidad_str:
        personal_ids_to_filter_local = personal_ids_in_unidad
        print(f"[DEBUG UTIL] Combinación: Solo Filtro Unidad")
    else:
        print(f"[DEBUG UTIL] Combinación: Sin filtro de unidad ni búsqueda activa")

    print(f"[DEBUG UTIL] IDs externos finales para filtrar DetalleBonoTe: {personal_ids_to_filter_local}") # LOG 4

    # --- 5. Obtener y Enriquecer Detalles Locales ---
    if proceed_with_details:
        if not personal_ids_to_filter_local and result['search_active']:
            logger.info("[Util] Filtro/Búsqueda activa pero no se encontraron IDs externos coincidentes.")
            print("[DEBUG UTIL] No se encontraron IDs externos que coincidan con el filtro/búsqueda.") # LOG 5.1
            result['detalles_enriquecidos'] = []
        elif personal_ids_to_filter_local: # Solo proceder si hay IDs para buscar
            try:
                # PASO A: Filtrar Detalles Locales por Planilla y IDs externos encontrados
                print(f"[DEBUG UTIL] Filtrando DetalleBonoTe por planilla_id={planilla.id} y personal_externo_id__in={personal_ids_to_filter_local}") # LOG 5
                detalles_locales_qs = DetalleBonoTe.objects.filter(
                    id_planilla=planilla,
                    personal_externo_id__in=personal_ids_to_filter_local # Filtrar por FK a externo
                )
                print(f"[DEBUG UTIL] QuerySet DetalleBonoTe filtrado (antes de ejecutar): {detalles_locales_qs.query}") # LOG 6a (Muestra SQL)
                detalles_locales_filtrados = list(detalles_locales_qs) # Convertir a lista para enriquecer
                print(f"[DEBUG UTIL] Detalles Bono Te internos encontrados: {len(detalles_locales_filtrados)}") # LOG 6b

                # PASO B: Enriquecer (si hay detalles locales)
                if detalles_locales_filtrados:
                    ids_needed = {d.personal_externo_id for d in detalles_locales_filtrados if d.personal_externo_id}
                    print(f"[DEBUG UTIL] IDs externos necesarios para enriquecimiento: {ids_needed}") # LOG 7

                    # Diccionarios para info externa
                    personal_info_ext = {}
                    designaciones_info_ext = {}

                    # Consultar info de Personal Externo
                    if ids_needed:
                        try:
                            print("[DEBUG UTIL] Consultando BD Externa: PrincipalPersonalExterno...") # LOG 8
                            personas_externas = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed)
                            personal_info_ext = {p.id: p for p in personas_externas}
                            print(f"[DEBUG UTIL] Info Personal Externo obtenida para {len(personal_info_ext)} IDs.") # LOG 9
                        except Exception as e_pers_f: logger.error(f"Error consultando personal externo para enriquecer: {e_pers_f}")

                    # Consultar info de Designación Externa (ACTIVA y relevante)
                    if ids_needed:
                        try:
                            print(f"[DEBUG UTIL] Consultando BD Externa: PrincipalDesignacionExterno (Activas, para IDs: {ids_needed})...") # LOG 10
                            desig_query_ext = PrincipalDesignacionExterno.objects.using('personas_db') \
                                .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                                .select_related('cargo', 'unidad') \
                                .order_by('personal_id', '-id')

                            # Si se filtró por unidad, añadir filtro externo
                            if selected_unidad_id:
                                print(f"[DEBUG UTIL]   (Añadiendo filtro de unidad_id={selected_unidad_id} a consulta designaciones)") # LOG 10.1
                                desig_query_ext = desig_query_ext.filter(unidad_id=selected_unidad_id)

                            # Tomar la más reciente por persona
                            designaciones_relevantes_ext = {}
                            processed_person_ids_ext = set()
                            # Iterar para obtener las relevantes (ejecuta la consulta)
                            for desig in desig_query_ext:
                                if desig.personal_id not in processed_person_ids_ext:
                                    designaciones_relevantes_ext[desig.personal_id] = desig
                                    processed_person_ids_ext.add(desig.personal_id)
                            print(f"[DEBUG UTIL] Info Designaciones Externas obtenida para {len(designaciones_relevantes_ext)} IDs.") # LOG 11

                            # Crear dict de info externa
                            designaciones_info_ext = {
                                pid: {
                                    'item': desig.item,
                                    'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A',
                                    'unidad_nombre': desig.unidad.nombre_unidad if desig.unidad else 'N/A'
                                } for pid, desig in designaciones_relevantes_ext.items()
                            }
                        except Exception as e_desig_f: logger.error(f"Error consultando designaciones externas para enriquecer: {e_desig_f}")

                    # Bucle de enriquecimiento (añadir atributos con sufijo _externo)
                    enriched_list_temp = []
                    print("[DEBUG UTIL] Iniciando bucle de enriquecimiento...") # LOG 12
                    for detalle in detalles_locales_filtrados:
                        persona_ext = personal_info_ext.get(detalle.personal_externo_id)
                        info_desig_ext = designaciones_info_ext.get(detalle.personal_externo_id)

                        detalle.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                        detalle.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                        detalle.unidad_externa_nombre = info_desig_ext.get('unidad_nombre', 'N/A') if info_desig_ext else 'N/A'
                        detalle.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                        detalle.nombre_completo_externo = persona_ext.nombre_completo if persona_ext else f'No encontrado ({detalle.personal_externo_id})'

                        enriched_list_temp.append(detalle)
                    print("[DEBUG UTIL] Bucle de enriquecimiento finalizado.") # LOG 13

                    # Ordenar (usando los atributos _externo)
                    # --- Lógica de ordenamiento por ITEM  ---
                    def get_sort_key_item_bonote(detalle_obj):
                        item_val_attr = getattr(detalle_obj, 'item_externo', None) # Puede ser int, None, o ''
                        nombre_completo_val = (getattr(detalle_obj, 'nombre_completo_externo', '') or '').strip().upper()
                        
                        item_sort_val = float('inf') # Valor para ítems no válidos, None, o ausentes

                        # Verificar si item_val_attr es None, o un string que (después de strip) está vacío
                        if item_val_attr is not None and str(item_val_attr).strip():
                            try:
                                item_sort_val = int(str(item_val_attr).strip()) # Convertir a int para orden numérico
                            except ValueError:
                                # Si no se puede convertir a int (ej. si fuera 'N/A', 'S/I'), va al final.
                                logger.debug(f"[Util Planilla] Item no numérico '{item_val_attr}' para {nombre_completo_val}, se ordenará al final.")
                                # Mantiene float('inf')
                        
                        # Clave de ordenamiento: primero por ítem numérico, luego por nombre completo
                        return (item_sort_val, nombre_completo_val)

                    enriched_list_temp.sort(key=get_sort_key_item_bonote)
                    logger.info(f"[Util Planilla] Lista de detalles Bono TE ordenada por item_externo (asc) y luego por nombre.")
                    


                    result['detalles_enriquecidos'] = enriched_list_temp
                    logger.info(f"[Util] Enriquecimiento externo completado para {len(enriched_list_temp)} detalles.")

            except Exception as e_filter_enrich:
                 logger.error(f"[Util] Error general durante filtrado/enriquecimiento (externo): {e_filter_enrich}", exc_info=True)
                 result['error_message'] = f"Ocurrió un error al procesar los detalles: {e_filter_enrich}"
                 result['detalles_enriquecidos'] = []
        else: # Caso: Hay filtros activos pero personal_ids_to_filter_local está vacío
             print("[DEBUG UTIL] Filtro/Búsqueda activa, pero no se encontraron IDs externos válidos para buscar detalles internos.")
             result['detalles_enriquecidos'] = []

    else: # Caso: No hay filtros ni búsqueda activa
        print("[DEBUG UTIL] No hay filtros ni búsqueda activa, no se recuperan detalles.")
        result['detalles_enriquecidos'] = []


    print(f"--- [DEBUG UTIL] FIN (Planilla: {planilla_id}) ---") # Separador Fin
    return result