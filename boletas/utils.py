import logging
import json
import math
import io
import base64
import os # Para buscar fuentes

# Importaciones de ReportLab
from reportlab.pdfgen import canvas as pdf_canvas_gen
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm # Podríamos usarlo si las coords Fabric fueran en mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont # Para registrar fuentes TrueType
from reportlab.lib import colors # Para colores predefinidos y HexColor






from reportlab.platypus import Paragraph # Para texto multilinea si es necesario
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY


from decimal import Decimal
# Para texto más complejo (multilinea, estilos mixtos) - opcional al principio
# from reportlab.platypus import Paragraph
# from reportlab.lib.styles import getSampleStyleSheet
logger = logging.getLogger(__name__)
# Para conversión literal (instalar con pip install num2words) - opcional
try:
    from num2words import num2words
    NUM2WORDS_AVAILABLE = True
except ImportError:
    NUM2WORDS_AVAILABLE = False



# boletas/utils.py o en la vista
#PLACEHOLDERS_BOLETA_DEFINICION = [
    # Datos Personales (de PrincipalPersonalExterno via DetalleSueldo.personal_externo)
#    {'id': '{{NOMBRE_COMPLETO}}', 'label': 'Nombre Completo Empleado', 'fuente': 'PrincipalPersonalExterno.nombre_completo'},
#    {'id': '{{CI_EMPLEADO}}', 'label': 'CI Empleado', 'fuente': 'PrincipalPersonalExterno.ci'},
#    {'id': '{{ITEM_EMPLEADO}}', 'label': 'Ítem', 'fuente': 'PrincipalDesignacionExterno.item'},
#    {'id': '{{CARGO_EMPLEADO}}', 'label': 'Cargo', 'fuente': 'PrincipalCargoExterno.nombre_cargo'},
#    {'id': '{{UNIDAD_EMPLEADO}}', 'label': 'Unidad Organizacional', 'fuente': 'PrincipalUnidadExterna.nombre_unidad'},
#    {'id': '{{FECHA_INGRESO_EMPLEADO}}', 'label': 'Fecha Ingreso', 'fuente': 'PrincipalDesignacionExterno.fecha_ingreso'}, # o DetalleSueldo.fecha_ingreso_referencia

    # Datos de la Planilla de Sueldos (Cabecera)
#    {'id': '{{MES_PAGO}}', 'label': 'Mes de Pago', 'fuente': 'PlanillaSueldo.mes'},
#    {'id': '{{ANIO_PAGO}}', 'label': 'Año de Pago', 'fuente': 'PlanillaSueldo.anio'},

    # Conceptos de Sueldo (de DetalleSueldo)
#    {'id': '{{HABER_BASICO}}', 'label': 'Haber Básico', 'fuente': 'DetalleSueldo.haber_basico'},
#    {'id': '{{CATEGORIA_ANTIGUEDAD}}', 'label': 'Categoría/Antigüedad', 'fuente': 'DetalleSueldo.categoria'},
#    {'id': '{{TOTAL_GANADO}}', 'label': 'Total Ganado', 'fuente': 'DetalleSueldo.total_ganado'},
#    {'id': '{{RC_IVA_RETENIDO}}', 'label': 'RC-IVA Retenido', 'fuente': 'DetalleSueldo.rc_iva_retenido'},
#    {'id': '{{GESTORA_PUBLICA_AFP}}', 'label': 'Aporte Gestora/AFP', 'fuente': 'DetalleSueldo.gestora_publica'},
#    {'id': '{{APORTE_SOLIDARIO}}', 'label': 'Aporte Nac. Solidario', 'fuente': 'DetalleSueldo.aporte_nac_solidario'},
#    {'id': '{{COOPERATIVA}}', 'label': 'Desc. Cooperativa', 'fuente': 'DetalleSueldo.cooperativa'},
#    {'id': '{{DESCUENTO_FALTAS}}', 'label': 'Desc. Faltas', 'fuente': 'DetalleSueldo.faltas'},
   # {'id': '{{DESCUENTO_MEMORANDUMS}}', 'label': 'Desc. Memorándums', 'fuente': 'DetalleSueldo.memorandums'},
  #  {'id': '{{OTROS_DESCUENTOS}}', 'label': 'Otros Descuentos', 'fuente': 'DetalleSueldo.otros_descuentos'},
 #   {'id': '{{TOTAL_DESCUENTOS}}', 'label': 'Total Descuentos', 'fuente': 'DetalleSueldo.total_descuentos'},
#    {'id': '{{LIQUIDO_PAGABLE}}', 'label': 'Líquido Pagable', 'fuente': 'DetalleSueldo.liquido_pagable'},
#    {'id': '{{DIAS_TRABAJADOS}}', 'label': 'Días Trabajados', 'fuente': 'DetalleSueldo.dias_trab'},

    # Datos Generales
#    {'id': '{{FECHA_EMISION_BOLETA}}', 'label': 'Fecha Emisión Boleta', 'fuente': 'Calculado'},
    # Podrías añadir aquí placeholders para el logo de la empresa, nombre de la empresa, etc.
    # que pueden ser textos fijos pero útiles de tener en la lista.
#]





# boletas/utils.py (o constants.py)

# Asumiendo que estos son los nombres de campo relevantes en tus modelos
# (Verifica con tus archivos models.py si hay alguna diferencia)

PLACEHOLDERS_BOLETA_DEFINICION = [
    # --- Datos PrincipalPersonalExterno (Accedido via DetalleSueldo.personal_externo) ---
    {'id': '{{nombre}}', 'label': 'Nombres (BD Externa)', 'fuente': 'PrincipalPersonalExterno.nombre'},
    {'id': '{{apellido_paterno}}', 'label': 'Apellido Paterno (BD Externa)', 'fuente': 'PrincipalPersonalExterno.apellido_paterno'},
    {'id': '{{apellido_materno}}', 'label': 'Apellido Materno (BD Externa)', 'fuente': 'PrincipalPersonalExterno.apellido_materno'},
    {'id': '{{nombre_completo}}', 'label': 'Nombre Completo (Calculado)', 'fuente': 'PrincipalPersonalExterno.nombre_completo'}, # Property del modelo
    {'id': '{{ci}}', 'label': 'CI (BD Externa)', 'fuente': 'PrincipalPersonalExterno.ci'},
    # ... otros campos de PrincipalPersonalExterno que necesites ...

    # --- Datos PrincipalDesignacionExterno (Necesitarás buscar la designación activa del empleado) ---
    {'id': '{{item}}', 'label': 'N° Item (BD Externa)', 'fuente': 'PrincipalDesignacionExterno.item'},
    {'id': '{{tipo_designacion}}', 'label': 'Tipo Designación (BD Externa)', 'fuente': 'PrincipalDesignacionExterno.tipo_designacion'},
    {'id': '{{fecha_ingreso}}', 'label': 'Fecha Ingreso (BD Externa)', 'fuente': 'PrincipalDesignacionExterno.fecha_ingreso'},
    {'id': '{{fecha_conclusion}}', 'label': 'Fecha Conclusión (BD Externa)', 'fuente': 'PrincipalDesignacionExterno.fecha_conclusion'},
    # --- Datos de relaciones de PrincipalDesignacionExterno ---
    {'id': '{{cargo_nombre_cargo}}', 'label': 'Cargo (BD Externa)', 'fuente': 'PrincipalCargoExterno.nombre_cargo'}, # A través de designacion.cargo
    {'id': '{{unidad_nombre_unidad}}', 'label': 'Unidad (BD Externa)', 'fuente': 'PrincipalUnidadExterna.nombre_unidad'}, # A través de designacion.unidad
    {'id': '{{secretaria_nombre_secretaria}}', 'label': 'Secretaría (BD Externa)', 'fuente': 'PrincipalSecretariaExterna.nombre_secretaria'}, # A través de designacion.unidad.secretaria

    # --- Datos PlanillaSueldo (Cabecera de la planilla de sueldos) ---
    {'id': '{{planilla_mes}}', 'label': 'Mes Planilla Sueldo', 'fuente': 'PlanillaSueldo.mes'},
    {'id': '{{planilla_anio}}', 'label': 'Año Planilla Sueldo', 'fuente': 'PlanillaSueldo.anio'},
    {'id': '{{planilla_tipo}}', 'label': 'Tipo Planilla Sueldo', 'fuente': 'PlanillaSueldo.tipo'}, # El valor ('planta', 'contrato')
    {'id': '{{planilla_tipo_display}}', 'label': 'Tipo Planilla Sueldo (Display)', 'fuente': 'PlanillaSueldo.get_tipo_display()'}, # El texto ('Personal Permanente')

    # --- Datos DetalleSueldo (El corazón de la boleta) ---
    {'id': '{{dias_trab}}', 'label': 'Días Trab.', 'fuente': 'DetalleSueldo.dias_trab'},
    {'id': '{{haber_basico}}', 'label': 'Haber Básico', 'fuente': 'DetalleSueldo.haber_basico'},
    {'id': '{{categoria}}', 'label': 'Categoría', 'fuente': 'DetalleSueldo.categoria'}, # Bono Antigüedad?
    {'id': '{{total_ganado}}', 'label': 'Total Ganado', 'fuente': 'DetalleSueldo.total_ganado'},
    {'id': '{{rc_iva_retenido}}', 'label': 'RC-IVA Retenido', 'fuente': 'DetalleSueldo.rc_iva_retenido'},
    {'id': '{{gestora_publica}}', 'label': 'Gestora Pública (AFP)', 'fuente': 'DetalleSueldo.gestora_publica'},
    {'id': '{{aporte_nac_solidario}}', 'label': 'Aporte Nac. Solidario', 'fuente': 'DetalleSueldo.aporte_nac_solidario'},
    {'id': '{{cooperativa}}', 'label': 'Cooperativa', 'fuente': 'DetalleSueldo.cooperativa'},
    {'id': '{{faltas}}', 'label': 'Desc. Faltas', 'fuente': 'DetalleSueldo.faltas'},
    {'id': '{{memorandums}}', 'label': 'Desc. Memorandums', 'fuente': 'DetalleSueldo.memorandums'},
    {'id': '{{otros_descuentos}}', 'label': 'Otros Descuentos', 'fuente': 'DetalleSueldo.otros_descuentos'},
    {'id': '{{total_descuentos}}', 'label': 'Total Descuentos', 'fuente': 'DetalleSueldo.total_descuentos'},
    {'id': '{{liquido_pagable}}', 'label': 'Líquido Pagable', 'fuente': 'DetalleSueldo.liquido_pagable'},

    # --- Datos Calculados / Generales (A generar en la vista de PDF) ---
    {'id': '{{literal_liquido}}', 'label': 'Líquido Pagable (Literal)', 'fuente': 'Calculado'},
    {'id': '{{fecha_emision_actual}}', 'label': 'Fecha Emisión Boleta', 'fuente': 'Calculado'},
    {'id': '{{mes_literal_actual}}', 'label': 'Mes Emisión (Literal)', 'fuente': 'Calculado'}, # Ej. MAYO
    # ... otros que puedas necesitar ...
]

# Nota: Para los campos de relaciones (cargo, unidad, secretaria), necesitarás obtener
# el objeto relacionado en tu lógica de generación de PDF para acceder a su nombre.
# Por ejemplo, para {{cargo_nombre_cargo}}, obtendrías la designación, luego designacion.cargo.nombre_cargo.



#REGISTERED_FONTS_CACHE = set()

# TODO: Define esta ruta correctamente en tu settings.py o como variable de entorno
#FONT_DIRECTORY = os.path.join(os.path.dirname(__file__), 'fonts') # Ejemplo: busca en una carpeta 'fonts' dentro de la app 'boletas'
# O podrías usar una ruta absoluta o buscar en carpetas del sistema


def get_reportlab_color(fabric_color_str, default_color=colors.black):
    if not fabric_color_str or fabric_color_str == 'transparent':
        return None # Para que fill=0 en rect
    try:
        # Manejar rgb(r,g,b) y rgba(r,g,b,a) si Fabric los usa
        if isinstance(fabric_color_str, str):
            if fabric_color_str.startswith('#'):
                return colors.HexColor(fabric_color_str)
            elif fabric_color_str.startswith('rgb('):
                parts = fabric_color_str[4:-1].split(',')
                return colors.Color(float(parts[0].strip())/255, float(parts[1].strip())/255, float(parts[2].strip())/255)
            elif fabric_color_str.startswith('rgba('):
                parts = fabric_color_str[5:-1].split(',')
                # La opacidad del color RGBA se maneja mejor con setFillAlpha/setStrokeAlpha globalmente
                return colors.Color(float(parts[0].strip())/255, float(parts[1].strip())/255, float(parts[2].strip())/255)
        return default_color # Fallback
    except Exception as e:
        logger.warning(f"Error convirtiendo color '{fabric_color_str}': {e}")
        return default_color


#--------------------------------------
def numero_a_literal(numero):
    from decimal import Decimal
    if not NUM2WORDS_AVAILABLE: return f"LITERAL ({Decimal(str(numero)):.2f})"
    try:
        numero_dec = Decimal(str(numero)).quantize(Decimal('0.01'))
        entero = int(numero_dec); decimal_part = int((numero_dec - entero) * 100)
        return f"{num2words(entero, lang='es').upper()} {decimal_part:02d}/100 BOLIVIANOS"
    except Exception as e: logger.error(f"Error num a lit ({numero}): {e}"); return f"ERROR LIT ({Decimal(str(numero)):.2f})"
#-------------------------------------------
def dibujar_boleta_en_canvas(pdf_canvas, page_height, diseno_json_dict, datos_empleado):
    if not diseno_json_dict or 'objects' not in diseno_json_dict:
        logger.error("PDF: Diseño JSON inválido o sin objetos para dibujar.")
        return

    stylesheet = getSampleStyleSheet() # Para Paragraph

    for obj_fabric in diseno_json_dict['objects']:
        if obj_fabric.get('isGridLine'):
            continue

        pdf_canvas.saveState() # Estado global para este objeto
        try:
            obj_type = obj_fabric.get('type', 'unknown')

            # Propiedades base de Fabric.js
            f_left = float(obj_fabric.get('left', 0))
            f_top = float(obj_fabric.get('top', 0))
            f_width_base = float(obj_fabric.get('width', 1)) # Ancho ANTES de scaleX
            f_height_base = float(obj_fabric.get('height', 1)) # Alto ANTES de scaleY
            f_angle_degrees = float(obj_fabric.get('angle', 0))
            f_scale_x = float(obj_fabric.get('scaleX', 1)) # Escala X individual del objeto
            f_scale_y = float(obj_fabric.get('scaleY', 1)) # Escala Y individual del objeto
            f_opacity = float(obj_fabric.get('opacity', 1))
            f_origin_x_str = obj_fabric.get('originX', 'left')
            f_origin_y_str = obj_fabric.get('originY', 'top')

            # Dimensiones visuales FINALES del objeto (después de su propia escala)
            obj_visual_width = f_width_base * f_scale_x
            obj_visual_height = f_height_base * f_scale_y

            pdf_canvas.setFillAlpha(f_opacity)
            pdf_canvas.setStrokeAlpha(f_opacity)

            # --- Transformaciones de Posicionamiento y Rotación (COMÚN A TODOS LOS OBJETOS) ---
            # 1. Calcular el centro del objeto en coordenadas Fabric (después de su escala y origen)
            anchor_fab_x = f_left
            anchor_fab_y = f_top

            # Desplazamiento del centro local del objeto (0,0) a su punto de anclaje (originX, originY)
            # Esto es ANTES de la rotación del objeto.
            local_anchor_offset_x_unscaled = 0
            if f_origin_x_str == 'left': local_anchor_offset_x_unscaled = f_width_base / 2
            elif f_origin_x_str == 'right': local_anchor_offset_x_unscaled = -f_width_base / 2

            local_anchor_offset_y_unscaled = 0
            if f_origin_y_str == 'top': local_anchor_offset_y_unscaled = f_height_base / 2
            elif f_origin_y_str == 'bottom': local_anchor_offset_y_unscaled = -f_height_base / 2
            
            # Aplicar la escala individual del objeto a este desplazamiento del anclaje
            local_anchor_offset_x_scaled = local_anchor_offset_x_unscaled * f_scale_x
            local_anchor_offset_y_scaled = local_anchor_offset_y_unscaled * f_scale_y

            # Rotar este desplazamiento del anclaje
            angle_rad = math.radians(f_angle_degrees)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)

            rotated_anchor_offset_x = local_anchor_offset_x_scaled * cos_a - local_anchor_offset_y_scaled * sin_a
            rotated_anchor_offset_y = local_anchor_offset_x_scaled * sin_a + local_anchor_offset_y_scaled * cos_a
            
            # Centro final del objeto en coordenadas Fabric
            center_x_fab = anchor_fab_x + rotated_anchor_offset_x
            center_y_fab = anchor_fab_y + rotated_anchor_offset_y

            # 2. Convertir centro a coordenadas ReportLab y aplicar transformaciones al canvas
            center_x_rl = center_x_fab
            center_y_rl = page_height - center_y_fab # Invertir Y

            pdf_canvas.translate(center_x_rl, center_y_rl)
            pdf_canvas.rotate(-f_angle_degrees) # Rotación en ReportLab es antihoraria
            # Ahora el origen (0,0) del canvas de ReportLab está en el centro del objeto rotado.
            # --- FIN Transformaciones de Posicionamiento y Rotación ---

            # Coordenadas relativas para dibujar el objeto (respecto a su centro ahora en 0,0)
            # Para rect, line, image, este es el bounding box visual.
            draw_rel_x_bbox = -obj_visual_width / 2
            draw_rel_y_bbox = -obj_visual_height / 2

            # --- Dibujo específico por tipo de objeto ---
            if obj_type == 'rect':
                fill_color_str = obj_fabric.get('fill', 'transparent')
                stroke_color_str = obj_fabric.get('stroke', '#000000')
                stroke_width_val = float(obj_fabric.get('strokeWidth', 1))

                rl_fill_color = get_reportlab_color(fill_color_str, default_color=None)
                rl_stroke_color = get_reportlab_color(stroke_color_str)

                pdf_canvas.setStrokeColor(rl_stroke_color if stroke_width_val > 0 else colors.transparent)
                pdf_canvas.setLineWidth(stroke_width_val)
                has_fill = 1 if rl_fill_color else 0
                if rl_fill_color: pdf_canvas.setFillColor(rl_fill_color)

                pdf_canvas.rect(draw_rel_x_bbox, draw_rel_y_bbox, obj_visual_width, obj_visual_height,
                                stroke=(1 if stroke_width_val > 0 else 0), fill=has_fill)

            elif obj_type == 'i-text':
                text_content_original = obj_fabric.get('text', '')
                rendered_text_raw = datos_empleado.get(text_content_original.strip(), text_content_original)
                rendered_text_string = str(rendered_text_raw).strip()

                f_font_family_raw = obj_fabric.get('fontFamily', 'Helvetica').lower()
                f_font_size_base = float(obj_fabric.get('fontSize', 10)) # Tamaño base sin escala Y
                f_fill_color_str = obj_fabric.get('fill', '#000000')
                f_text_align_fabric = obj_fabric.get('textAlign', 'left')
                f_font_weight_val = obj_fabric.get('fontWeight', 'normal')
                f_font_style = obj_fabric.get('fontStyle', 'normal')
                f_underline = obj_fabric.get('underline', False)
                f_line_height_factor = float(obj_fabric.get('lineHeight', 1.16))

                base_font_name = "Helvetica"
                if 'times' in f_font_family_raw or 'serif' in f_font_family_raw: base_font_name = "Times-Roman"
                elif 'courier' in f_font_family_raw or 'mono' in f_font_family_raw: base_font_name = "Courier"
                
                is_b = (f_font_weight_val=='bold' or (isinstance(f_font_weight_val,str) and f_font_weight_val.isdigit() and int(f_font_weight_val)>=700) or (isinstance(f_font_weight_val,(int,float)) and f_font_weight_val>=700))
                is_i = (f_font_style == 'italic')
                rl_fn = base_font_name # Nombre base de la fuente
                if base_font_name == "Helvetica":
                    if is_b and is_i: rl_fn="Helvetica-BoldOblique"
                    elif is_b: rl_fn="Helvetica-Bold"
                    elif is_i: rl_fn="Helvetica-Oblique"
                elif base_font_name == "Times-Roman":
                    if is_b and is_i: rl_fn="Times-BoldItalic"
                    elif is_b: rl_fn="Times-Bold"
                    elif is_i: rl_fn="Times-Italic"
                elif base_font_name == "Courier":
                    if is_b and is_i: rl_fn="Courier-BoldOblique"
                    elif is_b: rl_fn="Courier-Bold"
                    elif is_i: rl_fn="Courier-Oblique"
                
                pdf_canvas.setFont(rl_fn, f_font_size_base) # Usar tamaño de fuente BASE
                rl_text_color = get_reportlab_color(f_fill_color_str)
                if rl_text_color: pdf_canvas.setFillColor(rl_text_color)

                # Aplicar escala X e Y al sistema de coordenadas ANTES de dibujar texto
                # Esto estirará/comprimirá el texto.
                pdf_canvas.saveState() # Estado para la escala del texto
                pdf_canvas.scale(f_scale_x, f_scale_y)

                # Dimensiones para el texto ANTES de aplicar la escala del canvas.
                # El texto se dibujará como si tuviera f_width_base y f_height_base.
                width_for_text_layout = f_width_base
                height_for_text_layout = f_height_base

                if "\n" not in rendered_text_string and "\r" not in rendered_text_string: # Texto de una línea
                    text_width_natural = pdf_canvas.stringWidth(rendered_text_string, rl_fn, f_font_size_base)
                    
                    # Coordenadas de dibujo para drawString, relativas al centro del objeto (0,0 local),
                    # pero el origen del texto es abajo-izquierda.
                    # Estas coordenadas son ANTES de la escala del canvas.
                    text_draw_x = -width_for_text_layout / 2 # Default: izquierda
                    if f_text_align_fabric == 'center':
                        text_draw_x = -text_width_natural / 2
                    elif f_text_align_fabric == 'right':
                        text_draw_x = width_for_text_layout / 2 - text_width_natural
                    
                    # Posición Y: alinear la línea base del texto.
                    # Si el centro del objeto es (0,0), y el texto tiene altura f_font_size_base,
                    # y queremos que el texto esté centrado verticalmente en el f_height_base
                    # La línea base estaría aproximadamente en -f_font_size_base / (factor ~2.5 a 3) desde el centro del texto.
                    # Esta es la parte más tricky.
                    # Si f_height_base es la altura del "cuadro" de texto, y f_font_size_base es la altura de la fuente:
                    # Para centrar: -f_font_size_base / 2 (aproximado para la línea base desde el centro del texto)
                    # Si queremos que la parte inferior del texto toque -height_for_text_layout / 2:
                    text_draw_y = -height_for_text_layout / 2  # Coloca la línea base en la parte inferior del contenedor base
                                                              # Podría necesitar ajuste: + (f_font_size_base * 0.2) por ejemplo para subir la línea base
                    
                    pdf_canvas.drawString(text_draw_x, text_draw_y, rendered_text_string)

                else: # Texto multilínea con Paragraph
                    text_for_para = f"<u>{rendered_text_string}</u>" if f_underline else rendered_text_string
                    alignment_map = {'left':TA_LEFT, 'center':TA_CENTER, 'right':TA_RIGHT, 'justify':TA_JUSTIFY}
                    
                    para_s = ParagraphStyle(
                        f'ParaStyle_{obj_fabric.get("id","txt")}',
                        fontName=rl_fn,
                        fontSize=f_font_size_base,
                        leading=(f_font_size_base * f_line_height_factor),
                        textColor=rl_text_color,
                        alignment=alignment_map.get(f_text_align_fabric, TA_LEFT),
                        splitLongWords=0,
                        # backColor=colors.pink # Para depuración de límites
                    )
                    
                    para = Paragraph(text_for_para, para_s)
                    # wrapOn con dimensiones base (width_for_text_layout, height_for_text_layout)
                    pw_natural, ph_natural = para.wrapOn(pdf_canvas, width_for_text_layout, height_for_text_layout * 1.5) # Dar más alto para wrap

                    para_draw_x = -width_for_text_layout / 2 # Default: izquierda
                    if f_text_align_fabric == 'center':
                        para_draw_x = -pw_natural / 2
                    elif f_text_align_fabric == 'right':
                        para_draw_x = width_for_text_layout / 2 - pw_natural
                    
                    # Alinear la parte INFERIOR del Paragraph con la parte INFERIOR del contenedor base
                    para_draw_y = -height_for_text_layout / 2
                                        
                    para.drawOn(pdf_canvas, para_draw_x, para_draw_y)
                
                pdf_canvas.restoreState() # Restaurar estado después de la escala del texto

            elif obj_type == 'line':
                rl_stroke_color = get_reportlab_color(obj_fabric.get('stroke', '#000000'))
                rl_stroke_width = float(obj_fabric.get('strokeWidth', 1))
                pdf_canvas.setStrokeColor(rl_stroke_color)
                pdf_canvas.setLineWidth(rl_stroke_width)

                # Coordenadas de la línea en Fabric (x1,y1,x2,y2) son relativas al centro de la línea.
                # Y la escala del objeto (f_scale_x, f_scale_y) ya define obj_visual_width/height.
                # El objeto ya está trasladado a su centro y rotado.
                # Debemos dibujar la línea con sus coordenadas locales multiplicadas por su escala individual.
                line_x1_fab_local = float(obj_fabric.get('x1', 0)) 
                line_y1_fab_local = float(obj_fabric.get('y1', 0))
                line_x2_fab_local = float(obj_fabric.get('x2', 0))
                line_y2_fab_local = float(obj_fabric.get('y2', 0))

                # Las coordenadas para pdf_canvas.line son relativas al origen actual (0,0),
                # que es el centro del objeto línea.
                # No necesitamos aplicar f_scale_x y f_scale_y aquí porque las transformaciones
                # generales del objeto ya las consideraron para el obj_visual_width/height.
                # Las coordenadas x1,y1,x2,y2 de Fabric definen la línea dentro de su propio
                # bounding box no escalado. La escala ya se aplicó al transformar el canvas.
                # NO, esto es incorrecto. La escala del objeto individual SÍ debe aplicarse a sus coordenadas locales.
                
                # Las coordenadas de la línea se dan DENTRO del bounding box del objeto línea,
                # y este bounding box (definido por f_width_base, f_height_base) ya fue escalado por f_scale_x, f_scale_y
                # para obtener obj_visual_width, obj_visual_height.
                # Y el canvas ya está en el centro del objeto, con las escalas f_scale_x, f_scale_y aplicadas
                # si hubiéramos hecho pdf_canvas.scale(f_scale_x, f_scale_y) para todos.
                # PERO solo aplicamos scale para texto.
                # Entonces, para la línea, SÍ necesitamos aplicar su escala a sus coordenadas.

                p1_x = line_x1_fab_local * f_scale_x # Aplicar escala del objeto a sus coordenadas locales
                p1_y = line_y1_fab_local * f_scale_y
                p2_x = line_x2_fab_local * f_scale_x
                p2_y = line_y2_fab_local * f_scale_y
                
                pdf_canvas.line(p1_x, p1_y, p2_x, p2_y)

            elif obj_type == 'image':
                img_src_fabric = obj_fabric.get('src', '')
                img_reader = None
                if img_src_fabric.startswith('data:image'):
                    try:
                        header, base64_data_str = img_src_fabric.split(',', 1)
                        image_data_bytes = base64.b64decode(base64_data_str)
                        img_reader = ImageReader(io.BytesIO(image_data_bytes))
                    except Exception as e_b64:
                        logger.error(f"PDF: Error B64 img: {e_b64}", exc_info=True)

                if img_reader:
                    # Dibuja la imagen en el bounding box visual ya calculado (draw_rel_x_bbox, etc.)
                    pdf_canvas.drawImage(img_reader, draw_rel_x_bbox, draw_rel_y_bbox,
                                         width=obj_visual_width, height=obj_visual_height,
                                         mask='auto', preserveAspectRatio=False)
            else:
                logger.warning(f"PDF: Tipo objeto no manejado: {obj_type}")

        except Exception as e_obj_draw:
            obj_id_log = obj_fabric.get("id", "SIN_ID") if isinstance(obj_fabric, dict) else "OBJ_INVALIDO"
            logger.error(f"PDF: Error dibujando objeto Fabric (ID: {obj_id_log}, Tipo: {obj_type}): {e_obj_draw}", exc_info=True)
        finally:
            pdf_canvas.restoreState() # Restaura el estado global de este objeto
            
    logger.debug("PDF: Fin de dibujar_boleta_en_canvas para un empleado.")