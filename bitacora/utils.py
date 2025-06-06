# sisboletas/bitacora/utils.py
import csv
import datetime
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _ # Para los encabezados, si los traduces
from django.utils.html import strip_tags

# --- Imports para PDF ---
import io
from reportlab.lib.pagesizes import A4, landscape, letter # Usaremos landscape para más espacio
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm # Para unidades más intuitivas
from django.utils import timezone

# --- Imports para Excel ---
try:
    import openpyxl # Importación directa
    # No necesitamos save_virtual_workbook de openpyxl.writer.excel en versiones recientes
    from openpyxl.styles import Font, Alignment, Border, Side 
    OPENPYXL_AVAILABLE = True
    print("[DEBUG utils.py] openpyxl y componentes de estilo importados.")
except ImportError as e:
    OPENPYXL_AVAILABLE = False
    print(f"[ERROR utils.py] No se pudo importar openpyxl o sus componentes: {e}")
    # Guardar el error para mostrarlo al usuario si es necesario
    GENERAR_EXCEL_IMPORT_ERROR = str(e) 
else:
    GENERAR_EXCEL_IMPORT_ERROR = None


def generar_respuesta_csv(queryset_logs, nombre_archivo_base="bitacora_export"):
    """
    Toma un queryset de LogEntry y devuelve una HttpResponse con el CSV.
    El queryset_logs ya debe venir filtrado desde la vista.
    """
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{nombre_archivo_base}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'},
    )

    # Usar ; como delimitador para mejor compatibilidad con Excel en algunas configuraciones regionales
    writer = csv.writer(response, delimiter=';') 
    
    # Escribir encabezados del CSV (puedes personalizarlos)
    writer.writerow([
        _('Timestamp'), 
        _('Usuario (Nombre Completo)'), 
        _('Usuario (Username)'), 
        _('Acción'), 
        _('Tipo Recurso (App)'), 
        _('Tipo Recurso (Modelo)'),
        _('ID Objeto'), 
        _('Repr. Objeto'), 
        _('Detalles/Cambios'), 
        _('IP Remota')
    ])

    # Escribir datos
    for log_entry in queryset_logs:
        actor_username = log_entry.actor.username if log_entry.actor else "Sistema"
        actor_fullname = log_entry.actor.get_full_name() if log_entry.actor and log_entry.actor.get_full_name() else actor_username
        
        content_app = log_entry.content_type.app_label if log_entry.content_type else ""
        content_model = log_entry.content_type.model if log_entry.content_type else "" # nombre del modelo en minúsculas

        # Formatear timestamp para incluir zona horaria si está disponible
        # o al menos un formato ISO claro.
        timestamp_str = ""
        if log_entry.timestamp:
            try:
                # Intenta obtenerlo con zona horaria
                timestamp_str = log_entry.timestamp.strftime("%Y-%m-%d %H:%M:%S %Z") 
                if not log_entry.timestamp.tzinfo: # Si es naive, no tendrá %Z
                    timestamp_str = log_entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            except AttributeError: # Por si timestamp es None o no es datetime
                timestamp_str = str(log_entry.timestamp)


        writer.writerow([
            timestamp_str,
            actor_fullname,
            actor_username,
            log_entry.get_action_display(), # Muestra la etiqueta legible de la acción
            content_app,
            content_model,
            log_entry.object_pk, # El ID del objeto como string
            log_entry.object_repr, # El str(objeto)
            log_entry.changes, # El campo de texto/JSON de cambios
            log_entry.remote_addr
        ])
        
    return response



def generar_respuesta_pdf(queryset_logs, nombre_archivo_base="bitacora_export"):
    """
    Toma un queryset de LogEntry y devuelve una HttpResponse con el archivo PDF.
    """
    try:
        buffer = io.BytesIO()
        # Usar landscape para que quepan más columnas, márgenes más pequeños
        page_size = landscape(letter) 
        doc = SimpleDocTemplate(buffer, pagesize=page_size,
                                topMargin=1.5*cm, bottomMargin=1.5*cm,
                                leftMargin=1.5*cm, rightMargin=1.5*cm)
        
        styles = getSampleStyleSheet()
        # Estilo personalizado para celdas de tabla (más pequeño)
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=7, # Tamaño de fuente pequeño para que quepan más datos
            leading=9,
        )
        header_cell_style = ParagraphStyle(
            'HeaderCellStyle',
            parent=cell_style,
            fontName='Helvetica-Bold',
            alignment=1 # Centrado
        )

        elements = []

        # Título del Reporte
        title_style = styles['h2']
        title_style.alignment = 1 # Centrado
        title = Paragraph("Bitácora del Sistema", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.5*cm)) # Espacio después del título

        # Información de Filtros (si se pasara esta info, por ahora omitido para simplicidad)
        # Podrías añadir aquí los filtros aplicados si los pasas a esta función

        # Preparar datos para la tabla
        # Encabezados más cortos para PDF
        data = [
            [
                Paragraph("Timestamp", header_cell_style), 
                Paragraph("Usuario", header_cell_style), 
                Paragraph("Acción", header_cell_style), 
                Paragraph("Recurso", header_cell_style), 
                Paragraph("ID Obj.", header_cell_style),
                Paragraph("Detalles", header_cell_style), 
                Paragraph("IP", header_cell_style)
            ]
        ]

        for log_entry in queryset_logs:
            actor_display = log_entry.actor.username if log_entry.actor else "Sistema"
            # Limpiar HTML del object_repr y truncar
            resource_repr = strip_tags(log_entry.object_repr)
            resource_display = (resource_repr[:40] + '...') if len(resource_repr) > 40 else resource_repr
            
            # Limpiar HTML de changes y truncar
            changes_clean = strip_tags(log_entry.changes)
            changes_display = (changes_clean[:60] + '...') if len(changes_clean) > 60 else changes_clean
            
            # Convertir timestamp a string sin zona horaria explícita para el PDF, o manejarlo
            ts_display = log_entry.timestamp.strftime("%d/%m/%y %H:%M") if log_entry.timestamp else ""

            data.append([
                Paragraph(ts_display, cell_style),
                Paragraph(actor_display, cell_style),
                Paragraph(log_entry.get_action_display(), cell_style),
                Paragraph(resource_display, cell_style),
                Paragraph(str(log_entry.object_pk or ""), cell_style), # Asegurar que es string
                Paragraph(changes_display, cell_style),
                Paragraph(log_entry.remote_addr or "-", cell_style)
            ])

        if len(data) == 1: # Solo encabezados
            elements.append(Paragraph("No hay registros para mostrar con los filtros actuales.", styles['Normal']))
        else:
            # Definir anchos de columna (ajustar según necesidad)
            # A4 landscape width is 29.7cm. Margins 1.5+1.5=3cm. Available width = 26.7cm
            # Total de 7 columnas
            available_width = doc.width 
            col_widths = [
                available_width * 0.15, # Timestamp
                available_width * 0.15, # Usuario
                available_width * 0.10, # Acción
                available_width * 0.20, # Recurso
                available_width * 0.08, # ID Obj
                available_width * 0.22, # Detalles
                available_width * 0.10  # IP
            ]
            
            table = Table(data, colWidths=col_widths, repeatRows=1) # repeatRows=1 para repetir encabezado en cada página
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#40516F")), # Color oscuro para encabezado
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'), # Alinear a la izquierda por defecto
                ('ALIGN', (0, 0), (0, -1), 'CENTER'), # Timestamp centrado
                ('ALIGN', (2, 0), (2, -1), 'CENTER'), # Acción centrada
                ('ALIGN', (4, 0), (4, -1), 'CENTER'), # ID Obj centrado
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8), # Tamaño de fuente para encabezado
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#E6E6E6")), # Color claro para filas de datos
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elements.append(table)

        doc.build(elements)
        buffer.seek(0)
        
        response = HttpResponse(
            buffer, 
            content_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{nombre_archivo_base}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'}
        )
        return response
    except ImportError:
        return HttpResponse("La librería 'reportlab' es necesaria para exportar a PDF. Por favor, instálala.", status=501)
    except Exception as e:
        # logger.error(f"Error generando PDF de bitácora: {e}", exc_info=True) # Necesitarías pasar logger o importarlo aquí
        print(f"Error generando PDF de bitácora: {e}") # Para debug rápido
        return HttpResponse(f"Error al generar el PDF: {e}", status=500)
    

def generar_respuesta_excel(queryset_logs, nombre_archivo_base="bitacora_export"):
    """
    Toma un queryset de LogEntry y devuelve una HttpResponse con el archivo Excel (.xlsx).
    """
    if not OPENPYXL_AVAILABLE:
        error_message = "La librería 'openpyxl' es necesaria para exportar a Excel. Por favor, instálala (pip install openpyxl)."
        if GENERAR_EXCEL_IMPORT_ERROR: # Si capturamos un error específico al importar
            error_message += f" Detalle del error de importación: {GENERAR_EXCEL_IMPORT_ERROR}"
        return HttpResponse(error_message, status=501)

    workbook = openpyxl.Workbook() # Uso directo de openpyxl
    sheet = workbook.active
    sheet.title = "BitacoraLogs"

    # --- Estilos (Opcional, pero mejora la legibilidad) ---
    header_font = Font(name='Calibri', size=12, bold=True, color='FFFFFFFF') # Texto blanco
    header_fill = openpyxl.styles.PatternFill(start_color='40516F', end_color='40516F', fill_type='solid') # Azul oscuro
    center_alignment = Alignment(horizontal='center', vertical='center')
    left_alignment = Alignment(horizontal='left', vertical='center', wrap_text=True) # wrap_text para celdas con mucho texto
    
    thin_border = Border(left=Side(style='thin'), 
                         right=Side(style='thin'), 
                         top=Side(style='thin'), 
                         bottom=Side(style='thin'))

    # --- Encabezados ---
    headers = [
        'Timestamp', 'Usuario (Nombre Completo)', 'Usuario (Username)', 'Acción', 
        'Tipo Recurso (App)', 'Tipo Recurso (Modelo)',
        'ID Objeto', 'Repr. Objeto', 'Detalles/Cambios', 'IP Remota'
    ]
    sheet.append(headers)

    # Aplicar estilo a la fila de encabezado
    for col_num, header_title in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_alignment
        cell.border = thin_border

    # --- Datos ---
    row_num = 2 # Empezar desde la fila 2 para los datos
    for log_entry in queryset_logs:
        actor_username = log_entry.actor.username if log_entry.actor else "Sistema"
        actor_fullname = log_entry.actor.get_full_name() if log_entry.actor and log_entry.actor.get_full_name() else actor_username
        content_app = log_entry.content_type.app_label if log_entry.content_type else ""
        content_model = log_entry.content_type.model if log_entry.content_type else ""
        
        # Formatear timestamp para Excel: openpyxl maneja bien objetos datetime de Python.
        # Si es "aware", es mejor convertirlo a "naive" en UTC o en la zona horaria local
        # para evitar problemas de interpretación de zona horaria en Excel.
        # Aquí lo pasamos como naive en la zona horaria del settings (America/La_Paz) si es aware.
        timestamp_excel = None
        if log_entry.timestamp:
            if log_entry.timestamp.tzinfo: # Es aware
                timestamp_excel = log_entry.timestamp.astimezone(None) # Convertir a naive en la zona horaria local configurada
            else: # Ya es naive
                timestamp_excel = log_entry.timestamp
        
        # Limpiar HTML del campo changes si es necesario (si tus descripciones pueden tenerlo)
        changes_cleaned = strip_tags(log_entry.changes)

        # --- MANEJO DEL TIMESTAMP (MÁS ROBUSTO) ---
        timestamp_excel = None
        if log_entry.timestamp:
            # 1. Asegurar que es 'aware' en la zona horaria por defecto de Django (America/La_Paz)
            #    Si ya es 'aware', lo convierte a la TIME_ZONE. Si es 'naive', lo asume en TIME_ZONE.
            #    Esto es por si acaso viene de algún lugar como 'naive' pero representando la hora local.
            #    Pero si viene de la BD con USE_TZ=True, ya es 'aware' en UTC.
            
            # Opción más segura: convertir a la zona horaria de Django y luego hacerlo naive
            local_dt = timezone.localtime(log_entry.timestamp) # Convierte a TIME_ZONE si es aware UTC, o localiza si es naive
            timestamp_excel = local_dt.replace(tzinfo=None)    # Hacerlo naive
            
            # Alternativa (siempre convertir a UTC naive):
            # if log_entry.timestamp.tzinfo is not None:
            #     timestamp_excel = log_entry.timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            # else: # Si es naive, asumimos que es UTC o la hora deseada y lo dejamos como está
            #     timestamp_excel = log_entry.timestamp 
        # --- FIN MANEJO DEL TIMESTAMP ---

        data_row = [
            timestamp_excel,
            actor_fullname,
            actor_username,
            log_entry.get_action_display(),
            content_app,
            content_model,
            log_entry.object_pk,
            log_entry.object_repr,
            changes_cleaned, # Usar la versión limpia
            log_entry.remote_addr
        ]
        sheet.append(data_row)

        # Aplicar estilo a las celdas de datos
        for col_num in range(1, len(data_row) + 1):
            cell = sheet.cell(row=row_num, column=col_num)
            cell.alignment = left_alignment
            cell.border = thin_border
            if col_num == 1 and timestamp_excel: # Formato de fecha para la columna Timestamp
                 cell.number_format = 'DD/MM/YYYY HH:MM:SS'
        row_num += 1

    # --- Ajustar Ancho de Columnas (Opcional) ---
    # Esto es un ejemplo, puedes ajustarlo o hacerlo más dinámico
    column_widths = {'A': 22, 'B': 25, 'C': 20, 'D': 15, 'E': 20, 'F': 20, 'G': 12, 'H': 40, 'I': 60, 'J': 18}
    for col_letter, width in column_widths.items():
        sheet.column_dimensions[col_letter].width = width
    
    # Guardar el workbook en un buffer en memoria
    excel_buffer = io.BytesIO()
    workbook.save(excel_buffer) # Guardar el workbook directamente en el buffer
    excel_buffer.seek(0)
    
    response = HttpResponse(
        excel_buffer.getvalue(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    timestamp_export = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo_base}_{timestamp_export}.xlsx"'
    return response