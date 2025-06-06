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
from collections import defaultdict

# Imports para ReportLab (asegúrate de que estén aquí o ya importados arriba)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.utils import ImageReader
import os
from django.conf import settings
from decimal import Decimal, InvalidOperation
import io
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

logger = logging.getLogger(__name__)

def get_processed_asistencia_details(request, planilla_asistencia_id, items_por_pagina=25): # Añadido items_por_pagina
    """
    Obtiene la PlanillaAsistencia, listas de filtros (externos), y los
    DetallesAsistencia PAGINADOS (filtrados por unidad/búsqueda externa si aplica, y
    enriquecidos con datos externos). Genera la lista ordenada de IDs de la página actual
    para la funcionalidad de edición rápida.
    BASADO EN TU CÓDIGO ORIGINAL FUNCIONAL.
    """
    result = {
        'planilla_asistencia': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none() if PLANILLA_APP_AVAILABLE else [], # Inicializar como queryset vacío o lista
        'unidades_for_select': PrincipalUnidadExterna.objects.none() if PLANILLA_APP_AVAILABLE else [], # Inicializar
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'page_obj': None, # REEMPLAZA a 'detalles_asistencia'
        'detalle_ids_order': [], 
        'search_active': False,
        'error_message': None,
        'search_term': '',
    }
    logger.info(f"--- UTIL: INICIO get_processed_asistencia_details para Planilla ID: {planilla_asistencia_id} ---")
    logger.debug(f"UTIL: Request GET params: {request.GET.urlencode()}")


    # --- 0. Obtener PlanillaAsistencia --- (Tu lógica original)
    try:
        planilla = PlanillaAsistencia.objects.get(pk=planilla_asistencia_id)
        result['planilla_asistencia'] = planilla
    except PlanillaAsistencia.DoesNotExist:
        result['error_message'] = f"Reporte Asistencia ID {planilla_asistencia_id} no encontrado."
        logger.error(result['error_message'])
        return result
    except Exception as e_plan:
        result['error_message'] = "Error buscando el reporte."
        logger.error(f"UTIL: Error obteniendo PlanillaAsistencia ID {planilla_asistencia_id}: {e_plan}", exc_info=True)
        return result

    if not PLANILLA_APP_AVAILABLE:
        # No es un error fatal para los datos locales, pero sí para el enriquecimiento y filtros externos.
        msg_warn = "Componentes externos de la app 'planilla' no disponibles. El enriquecimiento y algunos filtros no funcionarán."
        result['error_message'] = (result.get('error_message') or '') + msg_warn
        logger.warning(f"UTIL: {msg_warn}")
        # No retornamos, intentaremos mostrar datos locales.

    # --- 1. Obtener Secretarías Externas --- (Tu lógica original)
    if PLANILLA_APP_AVAILABLE:
        try:
            all_secretarias_qs = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
            result['all_secretarias'] = list(all_secretarias_qs) # Convertir a lista
        except Exception as e_sec:
            logger.error(f"UTIL: Error obteniendo secretarías: {e_sec}", exc_info=True)
            result['error_message'] = (result.get('error_message') or '') + " Error cargando secretarías."
    
    # --- 2. Procesar Filtros GET --- (Tu lógica original)
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    result['search_active'] = bool(request.GET.get('buscar')) # Solo si el botón 'buscar' se presionó

    logger.debug(f"UTIL: Filtros GET: sec='{filter_secretaria_str}', un='{filter_unidad_str}', q='{search_term}' | Search Active (por botón 'buscar'): {result['search_active']}")

    # --- 3. Cargar Unidades si aplica --- (Tu lógica original)
    selected_secretaria_id_int = None
    if filter_secretaria_str and PLANILLA_APP_AVAILABLE:
        try:
            selected_secretaria_id_int = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id_int
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id_int) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = list(unidades_qs) # Convertir a lista
        except (ValueError, TypeError):
             logger.warning(f"UTIL: ID Secretaría inválido: '{filter_secretaria_str}'")
             result['selected_secretaria_id'] = None
        except Exception as e_uni:
             logger.error(f"UTIL: Error obteniendo unidades para sec ID {selected_secretaria_id_int}: {e_uni}", exc_info=True)
             result['error_message'] = (result.get('error_message') or '') + " Error cargando unidades."
    
    # --- 4. Obtener IDs Externos (Solo si filtro unidad o búsqueda, Y search_active es True) --- (Tu lógica original)
    # apply_external_id_filter se basaba en (filter_unidad_str or search_term) en tu original.
    # Vamos a mantener esa lógica: si hay un filtro de unidad O un término de búsqueda, intentamos filtrar por IDs externos.
    # Y adicionalmente, solo si PLANILLA_APP_AVAILABLE.
    
    attempt_external_filter = (filter_unidad_str or search_term) and PLANILLA_APP_AVAILABLE
    personal_ids_to_filter_local = set()
    selected_unidad_id_int_filter = None # Para el ID de unidad usado en el filtro

    if attempt_external_filter:
        logger.debug("UTIL: Intentando obtener IDs externos para filtrar (porque hay filtro de unidad o término de búsqueda).")
        # ... (COPIA AQUÍ TU LÓGICA ORIGINAL COMPLETA para llenar 'personal_ids_to_filter_local'
        #      basada en filter_unidad_str y search_term. Esto incluye las sub-consultas
        #      a PrincipalDesignacionExterno y PrincipalPersonalExterno de TU CÓDIGO ORIGINAL) ...
        # --- INICIO LÓGICA ORIGINAL (ADAPTADA) PARA OBTENER IDS EXTERNOS ---
        personal_ids_in_unidad = set()
        if filter_unidad_str:
            try:
                selected_unidad_id_int_filter = int(filter_unidad_str)
                result['selected_unidad_id'] = selected_unidad_id_int_filter # Guardar el ID válido
                designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(unidad_id=selected_unidad_id_int_filter, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
                logger.debug(f"UTIL: IDs por unidad '{filter_unidad_str}': {len(personal_ids_in_unidad)} IDs - {list(personal_ids_in_unidad)[:5]}")
            except (ValueError, TypeError): logger.warning(f"UTIL: ID Unidad para filtro inválido: '{filter_unidad_str}'")
            except Exception as e: logger.error(f"UTIL: Error IDs por Unidad {selected_unidad_id_int_filter}: {e}", exc_info=True)

        personal_ids_from_search = set()
        if search_term:
             try:
                 item_numeric = None
                 try: item_numeric = int(search_term)
                 except (ValueError, TypeError): pass # No es un error si no es numérico, simplemente no se busca por ítem.
                 
                 ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(ci__iexact=search_term).values_list('id', flat=True)
                 personal_ids_from_search.update(ids_ci_qs)
                 
                 if item_numeric is not None:
                      ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(item=item_numeric, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                      personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)
                 logger.debug(f"UTIL: IDs por búsqueda '{search_term}': {len(personal_ids_from_search)} IDs - {list(personal_ids_from_search)[:5]}")
             except Exception as e: logger.error(f"UTIL: Error IDs por Búsqueda '{search_term}': {e}", exc_info=True)
        
        # Combinación según tu lógica original:
        if filter_unidad_str and search_term: 
            personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
        elif search_term: 
            personal_ids_to_filter_local = personal_ids_from_search
        elif filter_unidad_str: 
            personal_ids_to_filter_local = personal_ids_in_unidad
        # Nota: Si solo se filtra por secretaría, no por unidad específica, esta lógica no captura
        # los IDs de todas las unidades de esa secretaría. Tu código original no parecía tener esa parte aquí.
        # Si es necesario, se debería añadir aquí.

        if not personal_ids_to_filter_local and (filter_unidad_str or search_term): # Si se intentó filtrar pero no se encontraron IDs externos
             logger.info("UTIL: Filtro/Búsqueda externa no encontró IDs de personal coincidentes.")
        logger.debug(f"UTIL: personal_ids_to_filter_local (final para filtro de QS): {len(personal_ids_to_filter_local)} IDs - {list(personal_ids_to_filter_local)[:5]}")
        # --- FIN LÓGICA ORIGINAL (ADAPTADA) PARA OBTENER IDS EXTERNOS ---
    else:
        logger.debug("UTIL: No se requiere filtro por IDs externos (no hay filtro de unidad ni término de búsqueda, o app planilla no disponible).")


    # --- 5. Obtener, Filtrar (si aplica), Enriquecer y PAGINAR Detalles Locales ---
    try:
        detalles_locales_qs = DetalleAsistencia.objects.filter(planilla_asistencia=planilla)
        logger.debug(f"UTIL: COUNT detalles_locales_qs INICIAL: {detalles_locales_qs.count()}")

        # Aplicar filtro por IDs externos SI SE INTENTÓ filtrar por unidad o búsqueda Y la app planilla está disponible
        if attempt_external_filter: # (filter_unidad_str or search_term) and PLANILLA_APP_AVAILABLE
            # Si personal_ids_to_filter_local está vacío, el filter() resultará en un queryset vacío,
            # lo cual es correcto si no hay personal que coincida con los filtros.
            logger.debug(f"UTIL: Aplicando filtro por personal_externo_id__in con IDs: {list(personal_ids_to_filter_local)[:10]}")
            detalles_locales_qs = detalles_locales_qs.filter(
                personal_externo_id__in=list(personal_ids_to_filter_local) # Convertir set a lista
            )
            logger.debug(f"UTIL: COUNT detalles_locales_qs DESPUÉS de filtro ID externo: {detalles_locales_qs.count()}")
        
        # Convertir a lista DESPUÉS de todos los filtros de QuerySet
        all_filtered_detalles_list = list(detalles_locales_qs) # Ejecutar la consulta
        logger.info(f"UTIL: Detalles locales filtrados (ANTES de enriquecer y paginar): {len(all_filtered_detalles_list)}")

        # Enriquecer (Tu lógica original)
        if all_filtered_detalles_list and PLANILLA_APP_AVAILABLE:
            # ... (COPIA AQUÍ TU LÓGICA DE ENRIQUECIMIENTO ORIGINAL COMPLETA, que opera sobre all_filtered_detalles_list) ...
            # Esta parte es crucial y debe ser idéntica a tu versión funcional.
            # Ejemplo (debes usar la tuya completa):
            ids_needed = {d.personal_externo_id for d in all_filtered_detalles_list if d.personal_externo_id}
            personal_info_ext = {}
            designaciones_info_ext = {}
            if ids_needed:
                try:
                    personas_externas_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed) # .only(...) si sabes los campos
                    personal_info_ext = {p.id: p for p in personas_externas_qs}
                except Exception as e: logger.error(f"UTIL: Error enriqueciendo (personal): {e}")
                try:
                    desig_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                        .select_related('cargo', 'unidad') \
                        .order_by('personal_id', '-id')
                    temp_desig = {}
                    for d_ext in desig_qs:
                        if d_ext.personal_id not in temp_desig: temp_desig[d_ext.personal_id] = d_ext
                    designaciones_info_ext = {pid: {'item': d.item, 
                                                     'cargo': d.cargo.nombre_cargo if d.cargo else 'N/A', 
                                                     'unidad_nombre': d.unidad.nombre_unidad if d.unidad and d.unidad.nombre_unidad else 'SIN UNIDAD ESPECÍFICA'} 
                                               for pid, d in temp_desig.items()}
                except Exception as e: logger.error(f"UTIL: Error enriqueciendo (designaciones): {e}")

            for detalle_obj in all_filtered_detalles_list:
                persona_ext_data = personal_info_ext.get(detalle_obj.personal_externo_id)
                info_desig_ext_data = designaciones_info_ext.get(detalle_obj.personal_externo_id)
                detalle_obj.item_externo = info_desig_ext_data.get('item', '') if info_desig_ext_data else ''
                detalle_obj.cargo_externo = info_desig_ext_data.get('cargo', 'N/A') if info_desig_ext_data else 'N/A'
                detalle_obj.unidad_externa_nombre = info_desig_ext_data.get('unidad_nombre', 'SIN UNIDAD ESPECÍFICA') if info_desig_ext_data else 'SIN UNIDAD ESPECÍFICA'
                detalle_obj.ci_externo = persona_ext_data.ci if persona_ext_data else 'N/A'
                detalle_obj.nombre_completo_externo = persona_ext_data.nombre_completo if persona_ext_data else f'ID:{detalle_obj.personal_externo_id} (No Encontrado)'
            logger.debug(f"UTIL: Enriquecimiento completado para {len(all_filtered_detalles_list)} detalles.")


        # Ordenar la lista COMPLETA ya enriquecida (Tu lógica original)
        try:
            def get_sort_key_item(detalle_obj): # Tu función de ordenamiento
                item_val = getattr(detalle_obj, 'item_externo', None)
                nombre_completo_val = (getattr(detalle_obj, 'nombre_completo_externo', '') or '').strip().upper()
                item_sort_val = float('inf') 
                if item_val is not None and str(item_val).strip():
                    try: item_sort_val = int(str(item_val).strip())
                    except ValueError: pass 
                return (item_sort_val, nombre_completo_val)
            all_filtered_detalles_list.sort(key=get_sort_key_item)
            logger.debug("UTIL: Lista COMPLETA FILTRADA Y ENRIQUECIDA ordenada.")
        except Exception as e_sort: 
            logger.error(f"UTIL: Error ordenando lista completa: {e_sort}", exc_info=True)

        # --- APLICAR PAGINACIÓN ---
        page_number_str = request.GET.get('page', '1')
        paginator = Paginator(all_filtered_detalles_list, items_por_pagina)
        logger.debug(f"UTIL: Paginator: count={paginator.count}, num_pages={paginator.num_pages}, items_por_pagina={items_por_pagina}")

        try:
            page_obj_resultado = paginator.page(page_number_str)
        except PageNotAnInteger:
            page_obj_resultado = paginator.page(1)
            logger.warning(f"UTIL: Número de página inválido ('{page_number_str}'). Mostrando página 1.")
        except EmptyPage:
            page_obj_resultado = paginator.page(paginator.num_pages)
            logger.warning(f"UTIL: Página '{page_number_str}' fuera de rango. Mostrando última página {paginator.num_pages}.")
        
        result['page_obj'] = page_obj_resultado
        
        if page_obj_resultado:
            result['detalle_ids_order'] = [d.id for d in page_obj_resultado.object_list] # IDs de la página actual
            logger.debug(f"UTIL: Página actual: {page_obj_resultado.number}, Items en página: {len(page_obj_resultado.object_list)}, IDs para JS: {len(result['detalle_ids_order'])}")
        else:
             result['detalle_ids_order'] = []

    except Exception as e_general:
         logger.error(f"UTIL: Error INESPERADO obteniendo/procesando detalles: {e_general}", exc_info=True)
         result['error_message'] = (result.get('error_message') or '') + f" Error procesando detalles: {e_general}"
         result['page_obj'] = None 
         result['detalle_ids_order'] = []

    logger.info(f"--- UTIL: FIN get_processed_asistencia_details para Planilla ID: {planilla_asistencia_id} ---")
    return result




# --- NUEVA FUNCIÓN PARA OBTENER DATOS DE PLANILLA PARA EXPORTACIÓN ---
def get_planilla_data_for_export(planilla_asistencia_id):
    """
    Obtiene todos los datos necesarios de una PlanillaAsistencia y sus detalles
    enriquecidos para ser usados en funciones de exportación (PDF, Excel, etc.).

    Retorna un diccionario con:
        'planilla_asistencia': Objeto PlanillaAsistencia.
        'detalles_asistencia': Lista de objetos DetalleAsistencia enriquecidos.
        'error_message': Mensaje de error si algo falla.
    """
    result = {
        'planilla_asistencia': None,
        'detalles_agrupados_por_unidad': {}, # Cambiado
        'orden_unidades': [],                # Nuevo
        'error_message': None
    }
    logger.info(f"[Util Export] Solicitud de datos para exportar PlanillaAsistencia ID {planilla_asistencia_id}")

    if not PLANILLA_APP_AVAILABLE:
        result['error_message'] = "Componentes externos de la app 'planilla' no disponibles."
        logger.critical("[Util Export] PLANILLA_APP_AVAILABLE es False.")
        # Podríamos no retornar aquí y dejar que intente cargar los datos locales.
        # Dependerá de si los datos externos son absolutamente críticos para la exportación.

    # 1. Obtener PlanillaAsistencia (cabecera)
    try:
        planilla = PlanillaAsistencia.objects.get(pk=planilla_asistencia_id)
        result['planilla_asistencia'] = planilla
    except PlanillaAsistencia.DoesNotExist:
        logger.error(f"[Util Export] PlanillaAsistencia ID={planilla_asistencia_id} no encontrada.")
        result['error_message'] = f"Reporte Asistencia ID {planilla_asistencia_id} no encontrado."
        return result
    except Exception as e_plan:
        logger.error(f"[Util Export] Error obteniendo PlanillaAsistencia ID {planilla_asistencia_id}: {e_plan}", exc_info=True)
        result['error_message'] = "Error buscando el reporte."
        return result

    # 2. Obtener todos los detalles locales
    try:
        detalles_locales_qs = DetalleAsistencia.objects.filter(planilla_asistencia=planilla)
        detalles_locales_list = list(detalles_locales_qs) # Ejecutar consulta
        logger.info(f"[Util Export] {len(detalles_locales_list)} detalles locales encontrados para PlanillaAsistencia ID {planilla.id}")

        # 3. Enriquecer detalles con datos externos (similar a get_processed_asistencia_details)
        if detalles_locales_list and PLANILLA_APP_AVAILABLE:
            ids_needed_for_enrichment = {d.personal_externo_id for d in detalles_locales_list if d.personal_externo_id}
            personal_info_ext = {}
            designaciones_info_ext = {} # Guardará la info de la designación más relevante

            if ids_needed_for_enrichment:
                # Obtener info de PrincipalPersonalExterno
                try:
                    # Traer solo los campos necesarios para el reporte
                    campos_persona = ['id', 'nombre', 'apellido_paterno', 'apellido_materno', 'ci']
                    personas_externas = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(id__in=ids_needed_for_enrichment) \
                        .only(*campos_persona)
                    personal_info_ext = {p.id: p for p in personas_externas}
                    logger.debug(f"[Util Export] {len(personal_info_ext)} registros de PrincipalPersonalExterno obtenidos.")
                except Exception as e_pers_f:
                    logger.error(f"[Util Export] Error consultando PrincipalPersonalExterno: {e_pers_f}", exc_info=True)
                    result['error_message'] = (result.get('error_message') or '') + " Error al obtener datos personales externos."

                # Obtener info de PrincipalDesignacionExterno (item, cargo, unidad)
                # Queremos la designación ACTIVA más relevante (ej. la última por ID si hay varias)
                try:
                    # Traer campos necesarios y relacionados
                    designaciones_query = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed_for_enrichment, estado='ACTIVO') \
                        .select_related('cargo', 'unidad') \
                        .order_by('personal_id', '-id') # Importante para obtener la más reciente por persona

                    # Procesar para obtener solo una designación por personal_id
                    processed_person_ids_for_desig = set()
                    for desig in designaciones_query:
                        if desig.personal_id not in processed_person_ids_for_desig:
                            designaciones_info_ext[desig.personal_id] = {
                                'item': desig.item,
                                'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A',
                                'unidad_nombre': desig.unidad.nombre_unidad if desig.unidad else 'N/A'
                            }
                            processed_person_ids_for_desig.add(desig.personal_id)
                    logger.debug(f"[Util Export] {len(designaciones_info_ext)} registros de PrincipalDesignacionExterno procesados.")
                except Exception as e_desig_f:
                    logger.error(f"[Util Export] Error consultando PrincipalDesignacionExterno: {e_desig_f}", exc_info=True)
                    result['error_message'] = (result.get('error_message') or '') + " Error al obtener datos de designación externos."

            # Bucle de enriquecimiento
            for detalle_obj in detalles_locales_list:
                persona_ext = personal_info_ext.get(detalle_obj.personal_externo_id)
                info_desig_ext = designaciones_info_ext.get(detalle_obj.personal_externo_id)

                # Nombre completo (manejando None)
                if persona_ext:
                    nombre = getattr(persona_ext, 'nombre', '') or ''
                    paterno = getattr(persona_ext, 'apellido_paterno', '') or ''
                    materno = getattr(persona_ext, 'apellido_materno', '') or ''
                    detalle_obj.nombre_completo_externo = f"{nombre} {paterno} {materno}".strip().replace('  ', ' ')
                    detalle_obj.ci_externo = persona_ext.ci if persona_ext.ci else 'N/A'
                else:
                    detalle_obj.nombre_completo_externo = f'ID:{detalle_obj.personal_externo_id} (No Encontrado)'
                    detalle_obj.ci_externo = 'N/A'

                # Item, Cargo, Unidad
                if info_desig_ext:
                    detalle_obj.item_externo = info_desig_ext.get('item', '')
                    detalle_obj.cargo_externo = info_desig_ext.get('cargo', 'N/A')
                    detalle_obj.unidad_externa_nombre = info_desig_ext.get('unidad_nombre', 'SIN UNIDAD ESPECÍFICA')
                else:
                    detalle_obj.item_externo = ''
                    detalle_obj.cargo_externo = 'N/A'
                    detalle_obj.unidad_externa_nombre = 'SIN UNIDAD ESPECÍFICA'

        # 4. AGRUPAR DETALLES POR UNIDAD
        detalles_agrupados = defaultdict(list)
        for detalle_obj in detalles_locales_list:
            # Usar un valor por defecto si unidad_externa_nombre no está o es None
            unidad_nombre = getattr(detalle_obj, 'unidad_externa_nombre', 'SIN UNIDAD ESPECÍFICA')
            if unidad_nombre is None or not str(unidad_nombre).strip(): # Doble chequeo por si acaso
                unidad_nombre = 'SIN UNIDAD ESPECÍFICA'
            detalles_agrupados[unidad_nombre].append(detalle_obj)

        # 5. ORDENAR DETALLES DENTRO DE CADA UNIDAD Y OBTENER ORDEN DE UNIDADES
        orden_unidades = sorted(detalles_agrupados.keys()) # Ordenar nombres de unidades alfabéticamente
        
        def get_sort_key_empleado(detalle): # Clave para ordenar empleados dentro de una unidad
            item_val = getattr(detalle, 'item_externo', None)
            nombre_val = (getattr(detalle, 'nombre_completo_externo', '') or '').strip().upper()
            item_sort_val = float('inf')
            if item_val is not None and str(item_val).strip():
                try:
                    item_sort_val = int(str(item_val).strip())
                except ValueError:
                    pass 
            return (item_sort_val, nombre_val)

        for unidad_nombre in orden_unidades:
            detalles_agrupados[unidad_nombre].sort(key=get_sort_key_empleado)
            
        result['detalles_agrupados_por_unidad'] = dict(detalles_agrupados) # Convertir de defaultdict a dict
        result['orden_unidades'] = orden_unidades
        logger.debug(f"[Util Export] Detalles agrupados por unidad. Unidades: {len(orden_unidades)}")

    except Exception as e_general:
        logger.error(f"[Util Export] Error INESPERADO obteniendo/procesando detalles para exportación: {e_general}", exc_info=True)
        result['error_message'] = (result.get('error_message') or '') + f" Error general procesando detalles: {e_general}"
        # Asegurar valores por defecto en error
        result['detalles_agrupados_por_unidad'] = {}
        result['orden_unidades'] = []

    return result

# --- FIN NUEVA FUNCIÓN ---

# --- NUEVA FUNCIÓN REFACTORIZADA PARA GENERAR EL PDF ---
def generar_pdf_asistencia(
    output_buffer, 
    planilla_cabecera, 
    detalles_agrupados, # Diccionario {nombre_unidad: [lista_detalles]}
    orden_unidades,     # Lista de nombres de unidad para el orden
    column_definitions  # Lista de tuplas definiendo columnas (texto_header, ancho, clave_campo)
    ):
    """
    Genera el contenido de un PDF de asistencia en el output_buffer proporcionado.
    Este PDF estará agrupado por unidad.
    """
    logger.info(f"Iniciando generación de PDF para Planilla ID: {planilla_cabecera.pk}")

    PAGE_WIDTH, PAGE_HEIGHT = landscape(letter)
    
    doc = SimpleDocTemplate(output_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
                            rightMargin=0.25*inch, leftMargin=0.25*inch,
                            topMargin=1.2*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    story = []

    # --- Estilos de Párrafo ---
    style_titulo_principal = ParagraphStyle(name='TituloPrincipal', parent=styles['h1'], alignment=TA_CENTER, fontSize=12, spaceAfter=0.15*inch)
    style_subtitulo_principal = ParagraphStyle(name='SubtituloPrincipal', parent=styles['h2'], alignment=TA_CENTER, fontSize=10, spaceAfter=0.1*inch)
    style_nombre_unidad = ParagraphStyle(name='NombreUnidad', parent=styles['h3'], fontSize=9, fontName='Helvetica-Bold', spaceBefore=0.15*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, leading=10)
    style_tabla_header = ParagraphStyle(name='TablaHeader', parent=styles['Normal'], alignment=TA_CENTER, fontSize=6, fontName='Helvetica-Bold', leading=7)
    style_tabla_cell = ParagraphStyle(name='TablaCell', parent=styles['Normal'], alignment=TA_LEFT, fontSize=5, leading=6)
    style_tabla_cell_num = ParagraphStyle(name='TablaCellNum', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=5, leading=6)
    style_tabla_cell_center = ParagraphStyle(name='TablaCellCenter', parent=styles['Normal'], alignment=TA_CENTER, fontSize=5, leading=6)

    # --- Función para el encabezado de la primera página (exactamente como la tenías) ---
    def primera_pagina_encabezado(canvas, doc_obj): # Renombrado 'doc' a 'doc_obj' para evitar conflicto con el 'doc' exterior
        canvas.saveState()
        text_y_start = PAGE_HEIGHT - 0.5*inch
        line_height = 12
        canvas.setFont('Helvetica', 8)
        canvas.drawString(0.5*inch, text_y_start, "GOBIERNO AUTÓNOMO DEPARTAMENTAL DE POTOSÍ")
        canvas.drawString(0.5*inch, text_y_start - line_height, "SECRETARÍA DEPTAL. ADMINISTRATIVA FINANCIERA")
        canvas.drawString(0.5*inch, text_y_start - 2*line_height, "UNIDAD DE RECURSOS HUMANOS")
        try:
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'gadp.png') # ¡VERIFICA ESTA RUTA!
            if os.path.exists(logo_path):
                logo_height = 0.9*inch
                img = ImageReader(logo_path)
                img_width_orig, img_height_orig = img.getSize()
                aspect_ratio = img_width_orig / float(img_height_orig)
                logo_width = logo_height * aspect_ratio
                
                margen_superior_logo = 0.3*inch 
                logo_y = PAGE_HEIGHT - margen_superior_logo - logo_height
                logo_x = PAGE_WIDTH - doc_obj.rightMargin - logo_width # Usar doc_obj.rightMargin
                
                canvas.drawImage(logo_path, logo_x, logo_y, width=logo_width, height=logo_height, mask='auto')
            else:
                logger.warning(f"Logo no encontrado en: {logo_path}")
                canvas.drawString(PAGE_WIDTH - 2*inch, text_y_start, "[Logo no encontrado]")
        except Exception as e_logo:
            logger.error(f"Error al cargar o dibujar el logo: {e_logo}", exc_info=True) # exc_info=True para traceback
            canvas.drawString(PAGE_WIDTH - 2*inch, text_y_start, "[Error logo]")
        canvas.restoreState()

    nombres_meses = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }
    nombre_mes = nombres_meses.get(planilla_cabecera.mes, str(planilla_cabecera.mes))
    
    # Título general del reporte
    story.append(Paragraph(f"REPORTE DE CONTROL DE ASISTENCIA DEL PERSONAL {planilla_cabecera.get_tipo_display().upper()}", style_titulo_principal))
    story.append(Paragraph(f"Correspondiente al mes {nombre_mes}      de {planilla_cabecera.anio}", style_subtitulo_principal))
    #story.append(Spacer(1, 0.1*inch))
    # Preparar encabezados de tabla y anchos (se reciben de column_definitions)
    table_headers_styled = [Paragraph(col_def[0], style_tabla_header) for col_def in column_definitions]
    col_widths = [col_def[1] for col_def in column_definitions]

    # Iterar sobre las unidades agrupadas
    for unidad_idx, nombre_unidad in enumerate(orden_unidades):
        detalles_de_esta_unidad = detalles_agrupados[nombre_unidad]
        if not detalles_de_esta_unidad: continue

        if unidad_idx > 0: story.append(Spacer(1, 0.15*inch))
        story.append(Paragraph(nombre_unidad.upper(), style_nombre_unidad))
        
        data_pdf_unidad = [table_headers_styled]
        for i, detalle in enumerate(detalles_de_esta_unidad):
            fila = []
            for idx_col, (header_text, col_w, field_key) in enumerate(column_definitions):
                if field_key == 'nro':
                    cell_value = str(i + 1)
                    cell_style = style_tabla_cell_center
                else:
                    cell_value_raw = getattr(detalle, field_key, None)
                    if field_key in ['omision_sancion', 'abandono_dias', 'abandono_sancion', 'faltas_dias', 'faltas_sancion', 'atrasos_sancion','vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep','asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad', 'iza_bandera']:
                        try: cell_value = f"{Decimal(cell_value_raw if cell_value_raw is not None else 0):.2f}"
                        except (TypeError, ValueError, InvalidOperation): cell_value = "0.00" 
                    elif isinstance(cell_value_raw, int) or field_key in ['omision_cant', 'atrasos_minutos']:
                         cell_value = str(cell_value_raw if cell_value_raw is not None else '0')
                    else: cell_value = str(cell_value_raw or '')

                    is_numeric_display_field = field_key not in ['nro', 'item_externo','ci_externo','nombre_completo_externo','cargo_externo']
                    if is_numeric_display_field: cell_style = style_tabla_cell_num
                    elif field_key in ['item_externo', 'ci_externo', 'nro']: cell_style = style_tabla_cell_center
                    else: cell_style = style_tabla_cell
                fila.append(Paragraph(cell_value, cell_style))
            data_pdf_unidad.append(fila)
        
        tabla_unidad = Table(data_pdf_unidad, colWidths=col_widths, repeatRows=1)
        try:
            nombre_col_idx = [i for i, col_def in enumerate(column_definitions) if col_def[2] == 'nombre_completo_externo'][0]
            cargo_col_idx = [i for i, col_def in enumerate(column_definitions) if col_def[2] == 'cargo_externo'][0]
        except IndexError:
            logger.error("Error al encontrar índices de col para TableStyle (Nombre/Cargo). Usando defaults.")
            nombre_col_idx = 3; cargo_col_idx = 4
        tabla_unidad.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#14FFFF")),('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),('GRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('ALIGN', (nombre_col_idx, 1), (nombre_col_idx, -1), 'LEFT'),
            ('ALIGN', (cargo_col_idx, 1), (cargo_col_idx, -1), 'LEFT'),
        ]))
        story.append(tabla_unidad)

    # Construir el documento PDF
    try:
        doc.build(story, onFirstPage=primera_pagina_encabezado)
        logger.info(f"Contenido PDF construido en buffer para Planilla ID: {planilla_cabecera.pk}")
    except Exception as e_build:
        logger.error(f"Error final al construir el PDF en buffer para Planilla ID {planilla_cabecera.pk}: {e_build}", exc_info=True)
        raise # Re-lanzar la excepción para que la vista la maneje