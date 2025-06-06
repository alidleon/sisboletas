# planilla/utils.py (Versión Restaurada + Debug Prints)

import logging
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
# Importa los modelos externos necesarios
from .models import (
    Planilla, DetalleBonoTe,
    PrincipalDesignacionExterno, PrincipalPersonalExterno,
    PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
)
from django.db.models import Q
from decimal import Decimal # Para convertir Item
from collections import defaultdict
from decimal import Decimal, InvalidOperation


# Imports para ReportLab
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.utils import ImageReader
import os
from django.conf import settings
import io
logger = logging.getLogger(__name__)

def get_processed_planilla_details(request, planilla_id, items_por_pagina=25, return_all_for_export=False):
    """
    Obtiene la planilla, listas de filtros (externos), y los detalles de Bono TE
    (PAGINADOS para la vista, o TODOS para exportación).
    """
    result = {
        'planilla': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none(),
        'unidades_for_select': PrincipalUnidadExterna.objects.none(),
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'page_obj': None,
        'search_active': False,
        'error_message': None,
        'search_term': '',
        'all_items_for_export': [], # Para la lista completa en modo exportación
        # Para exportación
        'all_items_for_export_list': [], # Lista plana de todos los detalles filtrados
        'detalles_agrupados_por_unidad_export': {}, # Diccionario para exportación
        'orden_unidades_export': [],             # Lista para orden en exportación
    }
    print(f"\n--- [DEBUG UTIL PLANILLA] INICIO (Planilla ID: {planilla_id}, ExportMode: {return_all_for_export}) ---")
    logger.info(f"[Util Planilla] Procesando Planilla ID {planilla_id}, ExportMode: {return_all_for_export}")

    # --- 0. Obtener la Planilla (Interna) ---
    try:
        planilla_obj = Planilla.objects.get(pk=planilla_id)
        result['planilla'] = planilla_obj
    except Planilla.DoesNotExist:
        logger.error(f"[Util Planilla] Planilla con ID={planilla_id} no encontrada.")
        result['error_message'] = f"Planilla ID {planilla_id} no encontrada."
        return result
    except Exception as e_plan:
        logger.error(f"[Util Planilla] Error obteniendo Planilla ID {planilla_id}: {e_plan}", exc_info=True)
        result['error_message'] = f"Error inesperado al buscar la planilla: {e_plan}"
        return result

    # --- 1. Obtener Secretarías Externas ---
    try:
        all_secretarias_qs = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
        result['all_secretarias'] = list(all_secretarias_qs)
    except Exception as e_sec:
        logger.error(f"[Util Planilla] Error obteniendo secretarías externas: {e_sec}", exc_info=True)
        result['error_message'] = (result.get('error_message') or "") + f" Error cargando secretarías: {e_sec}"

    # --- 2. Procesar Filtros GET ---
    filter_secretaria_str = request.GET.get('secretaria', '').strip()
    filter_unidad_str = request.GET.get('unidad', '').strip()
    search_term = request.GET.get('q', '').strip()
    result['search_term'] = search_term
    print(f"[DEBUG UTIL PLANILLA] GET Params: secretaria='{filter_secretaria_str}', unidad='{filter_unidad_str}', q='{search_term}'")
    result['search_active'] = bool(filter_secretaria_str or filter_unidad_str or search_term)
    print(f"[DEBUG UTIL PLANILLA] Search Active (por cualquier filtro): {result['search_active']}")

    # --- 3. Cargar Unidades Externas si se seleccionó Secretaría ---
    selected_secretaria_id_int = None
    if filter_secretaria_str:
        try:
            selected_secretaria_id_int = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id_int
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id_int) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = list(unidades_qs)
        except (ValueError, TypeError):
             logger.warning(f"[Util Planilla] ID de Secretaría externa inválido: '{filter_secretaria_str}'")
             result['selected_secretaria_id'] = None
        except Exception as e_uni:
             logger.error(f"[Util Planilla] Error obteniendo unidades externas para sec ID {selected_secretaria_id_int}: {e_uni}", exc_info=True)
             result['unidades_for_select'] = PrincipalUnidadExterna.objects.none()

    # --- 4. Obtener IDs de Personal Externo Relevantes SI HAY FILTROS ACTIVOS ---
    personal_ids_para_filtrar_detalles_locales = None 
    if result['search_active']:
        personal_ids_para_filtrar_detalles_locales = set()
        personal_ids_in_unidad = set()
        selected_unidad_id_int_filter = None
        if filter_unidad_str:
            try:
                selected_unidad_id_int_filter = int(filter_unidad_str)
                result['selected_unidad_id'] = selected_unidad_id_int_filter
                designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(unidad_id=selected_unidad_id_int_filter, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
                print(f"[DEBUG UTIL PLANILLA] IDs por unidad '{filter_unidad_str}': {personal_ids_in_unidad}")
            except (ValueError, TypeError): logger.warning(f"ID Unidad para filtro inválido: {filter_unidad_str}")
            except Exception as e: logger.error(f"Error IDs por Unidad {selected_unidad_id_int_filter}: {e}")
        
        personal_ids_from_search = set()
        if search_term:
             try:
                 item_numeric = None
                 try: item_numeric = int(search_term)
                 except: pass
                 ids_ci_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(ci__iexact=search_term).values_list('id', flat=True)
                 personal_ids_from_search.update(ids_ci_qs)
                 if item_numeric is not None:
                      ids_item_qs = PrincipalDesignacionExterno.objects.using('personas_db').filter(item=item_numeric, estado='ACTIVO').values_list('personal_id', flat=True).distinct()
                      personal_ids_from_search.update(p_id for p_id in ids_item_qs if p_id is not None)
                 print(f"[DEBUG UTIL PLANILLA] IDs por búsqueda '{search_term}': {personal_ids_from_search}")
             except Exception as e: logger.error(f"Error IDs por Búsqueda '{search_term}': {e}")
        
        if filter_unidad_str and search_term: 
            personal_ids_para_filtrar_detalles_locales = personal_ids_in_unidad.intersection(personal_ids_from_search)
        elif search_term: 
            personal_ids_para_filtrar_detalles_locales = personal_ids_from_search
        elif filter_unidad_str: 
            personal_ids_para_filtrar_detalles_locales = personal_ids_in_unidad
        elif filter_secretaria_str and not filter_unidad_str and not search_term:
             personal_ids_para_filtrar_detalles_locales = None # No filtrar por personal si solo se especificó secretaría
             print(f"[DEBUG UTIL PLANILLA] Combinación: Solo Filtro Secretaría, no se filtrarán IDs de personal (todos los de la planilla se considerarán).")

        if personal_ids_para_filtrar_detalles_locales is not None and not personal_ids_para_filtrar_detalles_locales:
             print("[DEBUG UTIL PLANILLA] Búsqueda/Filtro externo NO encontró IDs. Los detalles locales se filtrarán a vacío si se aplica este filtro.")
        elif personal_ids_para_filtrar_detalles_locales is not None:
             print(f"[DEBUG UTIL PLANILLA] IDs externos finales para filtrar DetalleBonoTe: {list(personal_ids_para_filtrar_detalles_locales)[:10]}")
    else:
        print("[DEBUG UTIL PLANILLA] No hay filtros activos, no se obtendrán IDs externos específicos para filtrar detalles.")

    # --- 5. Obtener y Enriquecer Detalles Locales ---
    all_filtered_detalles_list = []
    # Inicializar paginator y page_obj_resultado para evitar UnboundLocalError
    paginator = None
    page_obj_resultado = None

    try:
        detalles_locales_qs = DetalleBonoTe.objects.filter(id_planilla=planilla_obj)
        print(f"[DEBUG UTIL PLANILLA] COUNT DetalleBonoTe INICIAL para planilla {planilla_obj.id}: {detalles_locales_qs.count()}")

        # Aplicar filtro de personal_id si se determinó un conjunto de IDs y la búsqueda está activa
        if result['search_active'] and personal_ids_para_filtrar_detalles_locales is not None:
            print(f"[DEBUG UTIL PLANILLA] Aplicando filtro personal_externo_id__in con {len(personal_ids_para_filtrar_detalles_locales)} IDs.")
            detalles_locales_qs = detalles_locales_qs.filter(
                personal_externo_id__in=list(personal_ids_para_filtrar_detalles_locales)
            )
            print(f"[DEBUG UTIL PLANILLA] COUNT DetalleBonoTe DESPUÉS de filtro por ID externo: {detalles_locales_qs.count()}")

        all_filtered_detalles_list_for_processing = list(detalles_locales_qs)
        print(f"[DEBUG UTIL PLANILLA] Detalles Bono Te para procesar (después de filtro de IDs, antes de enriquecer): {len(all_filtered_detalles_list_for_processing)}")

        if all_filtered_detalles_list_for_processing:
            # --- INICIO DE TU LÓGICA DE ENRIQUECIMIENTO ORIGINAL ---
            ids_needed = {d.personal_externo_id for d in all_filtered_detalles_list_for_processing if d.personal_externo_id}
            personal_info_ext = {}
            designaciones_info_ext = {}
            if ids_needed:
                try:
                    personas_externas_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed)
                    personal_info_ext = {p.id: p for p in personas_externas_qs}
                except Exception as e_enrich_pers:
                    logger.error(f"[Util Planilla] Error enriqueciendo (personal): {e_enrich_pers}", exc_info=True)
                try:
                    desig_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                        .filter(personal_id__in=ids_needed, estado='ACTIVO') \
                        .select_related('cargo', 'unidad') \
                        .order_by('personal_id', '-id')
                    temp_desig = {}
                    for d_ext in desig_qs:
                        if d_ext.personal_id not in temp_desig: temp_desig[d_ext.personal_id] = d_ext
                    designaciones_info_ext = {
                        pid: {
                            'item': d.item,
                            'cargo': d.cargo.nombre_cargo if d.cargo else 'N/A',
                            'unidad_nombre': d.unidad.nombre_unidad if d.unidad and d.unidad.nombre_unidad else 'SIN UNIDAD ESPECÍFICA'
                        } for pid, d in temp_desig.items()
                    }
                except Exception as e_enrich_desig:
                    logger.error(f"[Util Planilla] Error enriqueciendo (designaciones): {e_enrich_desig}", exc_info=True)

            for detalle_obj_item in all_filtered_detalles_list_for_processing:
                persona_ext = personal_info_ext.get(detalle_obj_item.personal_externo_id)
                info_desig_ext = designaciones_info_ext.get(detalle_obj_item.personal_externo_id)

                detalle_obj_item.item_externo = info_desig_ext.get('item', '') if info_desig_ext else ''
                detalle_obj_item.cargo_externo = info_desig_ext.get('cargo', 'N/A') if info_desig_ext else 'N/A'
                detalle_obj_item.unidad_externa_nombre = info_desig_ext.get('unidad_nombre', 'SIN UNIDAD ESPECÍFICA') if info_desig_ext else 'SIN UNIDAD ESPECÍFICA'
                detalle_obj_item.ci_externo = persona_ext.ci if persona_ext else 'N/A'
                detalle_obj_item.nombre_completo_externo = persona_ext.nombre_completo if persona_ext else f'ID:{detalle_obj_item.personal_externo_id} (No Encontrado)'
            
            def get_sort_key_item_bonote(detalle_obj_sort):
                item_val_attr = getattr(detalle_obj_sort, 'item_externo', None)
                nombre_completo_val = (getattr(detalle_obj_sort, 'nombre_completo_externo', '') or '').strip().upper()
                item_sort_val = float('inf')
                if item_val_attr is not None and str(item_val_attr).strip():
                    try: item_sort_val = int(str(item_val_attr).strip())
                    except ValueError: pass
                return (item_sort_val, nombre_completo_val)

            all_filtered_detalles_list_for_processing.sort(key=get_sort_key_item_bonote)
            # --- FIN DE TU LÓGICA DE ENRIQUECIMIENTO ORIGINAL ---
            print(f"[DEBUG UTIL PLANILLA] Enriquecimiento y ordenamiento completado para {len(all_filtered_detalles_list_for_processing)} detalles.")

        logger.info(f"[Util Planilla] {len(all_filtered_detalles_list_for_processing)} detalles preparados (filtrados y enriquecidos).")

        if return_all_for_export:
            result['all_items_for_export_list'] = all_filtered_detalles_list_for_processing

            detalles_agrupados_export_temp = defaultdict(list)
            for detalle_export_item in all_filtered_detalles_list_for_processing:
                unidad_nombre_export = getattr(detalle_export_item, 'unidad_externa_nombre', 'SIN UNIDAD ESPECÍFICA')
                if unidad_nombre_export is None or not str(unidad_nombre_export).strip():
                    unidad_nombre_export = 'SIN UNIDAD ESPECÍFICA'
                detalles_agrupados_export_temp[unidad_nombre_export].append(detalle_export_item)

            result['orden_unidades_export'] = sorted(detalles_agrupados_export_temp.keys())
            result['detalles_agrupados_por_unidad_export'] = dict(detalles_agrupados_export_temp)

            logger.info(f"[Util Planilla] Devolviendo {len(all_filtered_detalles_list_for_processing)} items agrupados para exportar.")
        else:
            page_number_str = request.GET.get('page', '1')
            if items_por_pagina <= 0:
                items_por_pagina = 25
                logger.warning(f"[Util Planilla] items_por_pagina era <=0, usando default {items_por_pagina} para paginación.")

            if all_filtered_detalles_list_for_processing:
                paginator = Paginator(all_filtered_detalles_list_for_processing, items_por_pagina)
                logger.debug(f"UTIL Planilla: Paginator creado. Count={paginator.count}, NumPages={paginator.num_pages}, ItemsPerPage={items_por_pagina}")
                try:
                    page_obj_resultado = paginator.page(page_number_str)
                except PageNotAnInteger:
                    page_obj_resultado = paginator.page(1)
                    logger.warning(f"UTIL Planilla: Número de página inválido ('{page_number_str}'). Mostrando página 1.")
                except EmptyPage:
                    page_obj_resultado = paginator.page(paginator.num_pages)
                    logger.warning(f"UTIL Planilla: Página '{page_number_str}' fuera de rango ({paginator.num_pages} páginas). Mostrando última página.")
            else:
                logger.info("[Util Planilla] No hay detalles para paginar.")

        result['page_obj'] = page_obj_resultado

        if result['page_obj']:
            logger.debug(f"UTIL Planilla: Página actual: {result['page_obj'].number}, Items en página: {len(result['page_obj'].object_list)}")

    except Exception as e_general:
         logger.error(f"[Util Planilla] Error INESPERADO obteniendo/procesando detalles Bono TE: {e_general}", exc_info=True)
         result['error_message'] = (result.get('error_message') or '') + f" Error procesando detalles del bono: {e_general}"
         result['page_obj'] = None
         result['all_items_for_export_list'] = []
         result['detalles_agrupados_por_unidad_export'] = {}
         result['orden_unidades_export'] = []

    print(f"--- [DEBUG UTIL PLANILLA] FIN (Planilla: {planilla_id}, ExportMode: {return_all_for_export}, "
          f"Total items for export list: {len(result['all_items_for_export_list'])}, "
          f"Unidades export: {len(result['orden_unidades_export'])}, "
          f"Detalles Paginador: {len(result['page_obj'].object_list) if result['page_obj'] else 0}) ---")
    return result


def generar_pdf_bonote_detalles(
    output_buffer,
    planilla_cabecera_bonote,
    detalles_agrupados_bonote,
    orden_unidades_bonote,
    column_definitions_bonote
    ):
    """
    Genera el contenido de un PDF de Detalles de Bono TE en el output_buffer.
    Agrupado por unidad.
    """
    logger.info(f"Iniciando generación de PDF para Detalles Bono TE de Planilla ID: {planilla_cabecera_bonote.pk}")

    PAGE_WIDTH, PAGE_HEIGHT = landscape(letter)

    doc = SimpleDocTemplate(output_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
                            rightMargin=0.25*inch, leftMargin=0.25*inch,
                            topMargin=1.2*inch, bottomMargin=0.5*inch)

    styles = getSampleStyleSheet()
    story = []

    style_titulo_principal = ParagraphStyle(name='TituloPrincipal', parent=styles['h1'], alignment=TA_CENTER, fontSize=12, spaceAfter=0.15*inch, fontName='Helvetica-Bold')
    style_subtitulo_principal = ParagraphStyle(name='SubtituloPrincipal', parent=styles['h2'], alignment=TA_CENTER, fontSize=10, spaceAfter=0.1*inch, fontName='Helvetica')
    style_nombre_unidad = ParagraphStyle(name='NombreUnidad', parent=styles['h3'], fontSize=9, fontName='Helvetica-Bold', spaceBefore=0.15*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, leading=10,leftIndent=10, rightIndent=10,)
    style_tabla_header = ParagraphStyle(name='TablaHeader', parent=styles['Normal'], alignment=TA_CENTER, fontSize=7, fontName='Helvetica-Bold', leading=8, textColor=colors.black)
    style_tabla_cell = ParagraphStyle(name='TablaCell', parent=styles['Normal'], alignment=TA_LEFT, fontSize=6, leading=7)
    style_tabla_cell_num = ParagraphStyle(name='TablaCellNum', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=6, leading=7)
    style_tabla_cell_center = ParagraphStyle(name='TablaCellCenter', parent=styles['Normal'], alignment=TA_CENTER, fontSize=6, leading=7)

    def primera_pagina_encabezado(canvas, doc_obj):
        canvas.saveState()
        text_y_start = PAGE_HEIGHT - 0.5*inch
        line_height = 12
        canvas.setFont('Helvetica', 8)
        canvas.drawString(0.5*inch, text_y_start, "GOBIERNO AUTÓNOMO DEPARTAMENTAL DE POTOSÍ")
        canvas.drawString(0.5*inch, text_y_start - line_height, "SECRETARÍA DEPTAL. ADMINISTRATIVA FINANCIERA")
        canvas.drawString(0.5*inch, text_y_start - 2*line_height, "UNIDAD DE RECURSOS HUMANOS")
        try:
            logo_path = None
            # Intenta buscar en STATICFILES_DIRS primero si está configurado
            if settings.STATICFILES_DIRS:
                logo_path_candidate = os.path.join(settings.STATICFILES_DIRS[0], 'img', 'gadp.png')
                if os.path.exists(logo_path_candidate):
                    logo_path = logo_path_candidate
            
            # Si no se encontró o STATICFILES_DIRS no está, intenta en /static/img/gadp.png relativo a BASE_DIR
            if not logo_path:
                logo_path_candidate_base = os.path.join(settings.BASE_DIR, 'static', 'img', 'gadp.png')
                if os.path.exists(logo_path_candidate_base):
                    logo_path = logo_path_candidate_base
            
            if logo_path and os.path.exists(logo_path):
                logo_height = 0.9*inch
                img = ImageReader(logo_path)
                img_width_orig, img_height_orig = img.getSize()
                aspect_ratio = img_width_orig / float(img_height_orig)
                logo_width = logo_height * aspect_ratio
                margen_superior_logo = 0.3*inch
                logo_y = PAGE_HEIGHT - margen_superior_logo - logo_height
                logo_x = PAGE_WIDTH - doc_obj.rightMargin - logo_width - 0.25*inch
                canvas.drawImage(logo_path, logo_x, logo_y, width=logo_width, height=logo_height, mask='auto')
                logger.info(f"Logo cargado desde: {logo_path}")
            else:
                logger.warning(f"Logo no encontrado. Rutas intentadas: {settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else 'N/A'}, {os.path.join(settings.BASE_DIR, 'static', 'img', 'gadp.png')}")
        except Exception as e_logo:
            logger.error(f"Error al cargar o dibujar el logo: {e_logo}", exc_info=True)
        canvas.restoreState()

    nombres_meses = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }
    nombre_mes = nombres_meses.get(planilla_cabecera_bonote.mes, str(planilla_cabecera_bonote.mes))

    story.append(Paragraph(f"PLANILLA DE PAGO BONO DE TÉ - PERSONAL {planilla_cabecera_bonote.get_tipo_display().upper()}", style_titulo_principal))
    story.append(Paragraph(f"CORRESPONDIENTE AL MES DE {nombre_mes.upper()} DE {planilla_cabecera_bonote.anio}", style_subtitulo_principal))
    
    table_headers_styled = [Paragraph(col_def[0], style_tabla_header) for col_def in column_definitions_bonote]
    col_widths = [col_def[1] for col_def in column_definitions_bonote]

    nro_general_item = 0

    for unidad_idx, nombre_unidad in enumerate(orden_unidades_bonote):
        detalles_de_esta_unidad = detalles_agrupados_bonote[nombre_unidad]
        if not detalles_de_esta_unidad:
            continue

        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f"UNIDAD: {nombre_unidad.upper()}", style_nombre_unidad))

        data_pdf_unidad = [table_headers_styled]
        nro_item_unidad = 0
        for detalle_bonote in detalles_de_esta_unidad:
            nro_item_unidad += 1
            nro_general_item +=1
            fila = []
            for idx_col, (header_text, col_w, field_key) in enumerate(column_definitions_bonote):
                cell_value_raw = None
                cell_style = style_tabla_cell

                if field_key == 'nro_item':
                    cell_value_raw = str(nro_item_unidad)
                    cell_style = style_tabla_cell_center
                elif field_key == 'dias_habiles_planilla':
                    cell_value_raw = planilla_cabecera_bonote.dias_habiles
                    cell_style = style_tabla_cell_num
                else:
                    cell_value_raw = getattr(detalle_bonote, field_key, None)

                campos_numericos_decimales = ['faltas', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'psgh', 'perm_excep', 'asuetos', 'pcgh_embar_enf_base', 'dias_no_pagados', 'dias_pagados', 'total_ganado', 'descuentos', 'liquido_pagable', 'dias_habiles_planilla']
                campos_texto_largo = ['nombre_completo_externo', 'cargo_externo', 'observaciones_bono', 'observaciones_asistencia']
                campos_centrados = ['item_externo', 'ci_externo', 'nro_item']

                if isinstance(cell_value_raw, Decimal):
                    cell_value = f"{cell_value_raw:.2f}"
                    if field_key not in campos_texto_largo + campos_centrados:
                         cell_style = style_tabla_cell_num
                elif isinstance(cell_value_raw, (int, float)) and field_key not in ['item_externo']:
                    if field_key in campos_numericos_decimales:
                        try: cell_value = f"{Decimal(cell_value_raw):.2f}"
                        except (TypeError, InvalidOperation): cell_value = "0.00"
                    else:
                        cell_value = str(cell_value_raw if cell_value_raw is not None else "")
                    if field_key not in campos_texto_largo + campos_centrados:
                         cell_style = style_tabla_cell_num
                elif cell_value_raw is None:
                    cell_value = ""
                    if field_key in campos_numericos_decimales:
                        cell_value = "0.00"
                        cell_style = style_tabla_cell_num
                else: # Strings
                    cell_value = str(cell_value_raw)
                
                # Ajustar estilo final basado en el tipo de campo
                if field_key in campos_centrados:
                    cell_style = style_tabla_cell_center
                elif field_key in campos_texto_largo:
                    cell_style = style_tabla_cell
                elif field_key not in campos_centrados + campos_texto_largo: # Si no es texto largo ni centrado, es numérico
                    cell_style = style_tabla_cell_num


                fila.append(Paragraph(cell_value, cell_style))
            data_pdf_unidad.append(fila)

        tabla_unidad = Table(data_pdf_unidad, colWidths=col_widths, repeatRows=1)

        table_style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00FFFF")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 6),
            ('LEFTPADDING', (0, 1), (-1, -1), 2),
            ('RIGHTPADDING', (0, 1), (-1, -1), 2),
        ]

        for i, col_def in enumerate(column_definitions_bonote):
            if col_def[2] in campos_texto_largo:
                table_style_cmds.append(('ALIGN', (i, 1), (i, -1), 'LEFT'))
            elif col_def[2] not in campos_centrados + campos_texto_largo: # Numéricos
                 table_style_cmds.append(('ALIGN', (i, 1), (i, -1), 'RIGHT'))
            # Los centrados ya están por el ALIGN general de la tabla

        tabla_unidad.setStyle(TableStyle(table_style_cmds))
        story.append(tabla_unidad)
        story.append(Spacer(1, 0.05*inch))

    try:
        doc.build(story, onFirstPage=primera_pagina_encabezado)
        logger.info(f"Contenido PDF de Detalles Bono TE construido en buffer para Planilla ID: {planilla_cabecera_bonote.pk}")
    except Exception as e_build:
        logger.error(f"Error final al construir el PDF de Detalles Bono TE en buffer para Planilla ID {planilla_cabecera_bonote.pk}: {e_build}", exc_info=True)
        
        

def generar_pdf_lista_planillas(
    output_buffer,
    planillas_qs, # QuerySet o lista de objetos Planilla
    column_definitions_lista, # Definición de columnas para esta tabla
    titulo_reporte="LISTA DE PLANILLAS DE BONO DE TÉ GENERADAS" # Título general
    ):
    """
    Genera un PDF con la lista de Planillas de Bono de Té.
    """
    logger.info(f"Iniciando generación de PDF para la lista de planillas. Total: {len(planillas_qs) if hasattr(planillas_qs, '__len__') else 'Desconocido'}")

    # Usaremos tamaño carta vertical (portrait) para una lista simple.
    # Puedes cambiar a landscape(letter) si tienes muchas columnas o muy anchas.
    PAGE_WIDTH, PAGE_HEIGHT = letter
    doc = SimpleDocTemplate(output_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
                            rightMargin=0.5*inch, leftMargin=0.5*inch,
                            topMargin=1.2*inch, bottomMargin=0.5*inch)

    styles = getSampleStyleSheet()
    story = []

    # Estilos (puedes personalizarlos más si es necesario)
    style_titulo_principal = ParagraphStyle(name='TituloPrincipalLista', parent=styles['h1'], alignment=TA_CENTER, fontSize=14, spaceAfter=0.2*inch, fontName='Helvetica-Bold')
    style_tabla_header = ParagraphStyle(name='TablaHeaderLista', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9, fontName='Helvetica-Bold', leading=10, textColor=colors.whitesmoke)
    style_tabla_cell = ParagraphStyle(name='TablaCellLista', parent=styles['Normal'], alignment=TA_LEFT, fontSize=8, leading=9)
    style_tabla_cell_center = ParagraphStyle(name='TablaCellListaCenter', parent=style_tabla_cell, alignment=TA_CENTER)
    style_tabla_cell_right = ParagraphStyle(name='TablaCellListaRight', parent=style_tabla_cell, alignment=TA_RIGHT)


    # Función para el encabezado de la primera página (puedes reutilizar la de generar_pdf_bonote_detalles si es idéntica)
    # O definir una específica si necesitas cambios. Por simplicidad, la redefinimos aquí.
    def primera_pagina_encabezado_lista(canvas, doc_obj):
        canvas.saveState()
        text_y_start = PAGE_HEIGHT - 0.5*inch
        line_height = 12
        canvas.setFont('Helvetica', 8)
        canvas.drawString(0.5*inch, text_y_start, "GOBIERNO AUTÓNOMO DEPARTAMENTAL DE POTOSÍ")
        canvas.drawString(0.5*inch, text_y_start - line_height, "SECRETARÍA DEPTAL. ADMINISTRATIVA FINANCIERA")
        canvas.drawString(0.5*inch, text_y_start - 2*line_height, "UNIDAD DE RECURSOS HUMANOS")
        try:
            logo_path = None
            if settings.STATICFILES_DIRS:
                logo_path_candidate = os.path.join(settings.STATICFILES_DIRS[0], 'img', 'gadp.png')
                if os.path.exists(logo_path_candidate): logo_path = logo_path_candidate
            if not logo_path:
                logo_path_candidate_base = os.path.join(settings.BASE_DIR, 'static', 'img', 'gadp.png')
                if os.path.exists(logo_path_candidate_base): logo_path = logo_path_candidate_base
            
            if logo_path and os.path.exists(logo_path):
                logo_height = 0.9*inch
                img = ImageReader(logo_path)
                img_width_orig, img_height_orig = img.getSize()
                aspect_ratio = img_width_orig / float(img_height_orig)
                logo_width = logo_height * aspect_ratio
                margen_superior_logo = 0.3*inch
                logo_y = PAGE_HEIGHT - margen_superior_logo - logo_height
                logo_x = PAGE_WIDTH - doc_obj.rightMargin - logo_width - 0.25*inch
                canvas.drawImage(logo_path, logo_x, logo_y, width=logo_width, height=logo_height, mask='auto')
            else: logger.warning(f"Logo no encontrado para PDF lista planillas.")
        except Exception as e_logo: logger.error(f"Error al cargar/dibujar logo en PDF lista planillas: {e_logo}", exc_info=True)
        canvas.restoreState()

    # Título del reporte
    story.append(Paragraph(titulo_reporte.upper(), style_titulo_principal))
    story.append(Spacer(1, 0.1*inch))

    # Preparar datos para la tabla
    table_data = []
    # Encabezados
    table_headers = [Paragraph(col_def[0], style_tabla_header) for col_def in column_definitions_lista]
    table_data.append(table_headers)

    # Filas de datos
    nro_item = 0
    for planilla_item in planillas_qs:
        nro_item += 1
        row = []
        for header_text, col_width, field_key_or_callable, field_type in column_definitions_lista:
            cell_value = ""
            current_cell_style = style_tabla_cell # Default

            if field_key_or_callable == 'nro_item_lista':
                cell_value = str(nro_item)
                current_cell_style = style_tabla_cell_center
            elif callable(field_key_or_callable): # Si es una función para obtener el valor
                cell_value = field_key_or_callable(planilla_item)
            else: # Si es una clave de atributo
                value_raw = getattr(planilla_item, field_key_or_callable, None)
                if field_key_or_callable == 'fecha_elaboracion' or field_key_or_callable == 'fecha_aprobacion':
                    cell_value = value_raw.strftime("%d/%m/%Y") if value_raw else "-"
                elif field_key_or_callable == 'dias_habiles':
                    cell_value = f"{value_raw:.2f}" if value_raw is not None else "N/A"
                elif field_key_or_callable == 'usuario_elaboracion':
                    cell_value = value_raw.username if value_raw else "-"
                else: # Para mes, anio, tipo, estado
                    cell_value = str(value_raw) if value_raw is not None else "-"
            
            # Ajustar estilo según field_type
            if field_type == 'center':
                current_cell_style = style_tabla_cell_center
            elif field_type == 'right':
                current_cell_style = style_tabla_cell_right
            # else usa style_tabla_cell (left)

            row.append(Paragraph(str(cell_value), current_cell_style))
        table_data.append(row)

    if not planillas_qs: # Si no hay planillas
        table_data.append([Paragraph("No hay planillas para mostrar.", style_tabla_cell_center, colSpan=len(column_definitions_lista))])

    # Anchos de columna
    col_widths = [col_def[1] for col_def in column_definitions_lista]

    # Crear y estilizar la tabla
    lista_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    lista_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#003366")), # Fondo cabecera
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),        # Texto cabecera
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),                  # Alineación general
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),                 # Alineación vertical
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),       # Fuente cabecera
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),          # Rejilla
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),                  # Padding cabecera
        ('TOPPADDING', (0, 0), (-1, 0), 6),                     # Padding cabecera
        ('LEFTPADDING', (0, 1), (-1, -1), 3),                   # Padding datos
        ('RIGHTPADDING', (0, 1), (-1, -1), 3),                  # Padding datos
    ]))
    story.append(lista_table)

    # Construir PDF
    try:
        doc.build(story, onFirstPage=primera_pagina_encabezado_lista)
        logger.info(f"PDF de lista de planillas construido en buffer.")
    except Exception as e_build:
        logger.error(f"Error al construir PDF de lista de planillas: {e_build}", exc_info=True)
        raise