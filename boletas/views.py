import logging
from django.shortcuts import render, redirect, get_object_or_404
import locale
from django.contrib import messages
from django.urls import reverse
from .models import PlantillaBoleta
from .forms import PlantillaBoletaForm
from sueldos.models import PlanillaSueldo, DetalleSueldo 
from django.http import HttpResponse, JsonResponse 
from .utils import dibujar_boleta_en_canvas
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas_gen 
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.csrf import csrf_exempt 
from django.utils.html import escape 
from datetime import datetime
from .utils import numero_a_literal, numero_a_literal_con_decimal_y_salto
 
import io
import json
import math 
from decimal import Decimal
from django.http import Http404
logger = logging.getLogger(__name__)
try:
    from planilla.models import PrincipalPersonalExterno, PrincipalDesignacionExterno, PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalPersonalExterno, PrincipalDesignacionExterno, PrincipalCargoExterno = None, None, None
    PrincipalUnidadExterna, PrincipalSecretariaExterna = None, None
    PLANILLA_APP_AVAILABLE = False
    logger.error("GENERACION PDF: No se pudieron importar modelos de la app 'planilla'.")
try:
    from planilla.models import PrincipalPersonalExterno, PrincipalDesignacionExterno
    PLANILLA_APP_AVAILABLE_FOR_SEARCH = True 
except ImportError:
    PrincipalPersonalExterno, PrincipalDesignacionExterno = None, None
    PLANILLA_APP_AVAILABLE_FOR_SEARCH = False
    logger.error("GENERAR BOLETA INDIVIDUAL: No se pudieron importar modelos de la app 'planilla'.")
try:
    from .utils import PLACEHOLDERS_BOLETA_DEFINICION
except ImportError:
    
    print("ADVERTENCIA: No se encontró PLACEHOLDERS_BOLETA_DEFINICION en utils.py, usando definición de fallback.")
    PLACEHOLDERS_BOLETA_DEFINICION = [
        {'id': '{{PLACEHOLDER_EJEMPLO}}', 'label': 'Placeholder Ejemplo'},
    ]
import json 

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType 

@login_required
@permission_required('boletas.view_plantillaboleta', raise_exception=True)
def lista_plantillas_boleta(request):
    plantillas = PlantillaBoleta.objects.all().order_by('nombre')
    context = {
        'plantillas': plantillas,
        'titulo_pagina': "Plantillas de Boletas de Pago"
    }
    return render(request, 'boletas/lista_plantillas.html', context)

@login_required
@permission_required('boletas.change_plantillaboleta', raise_exception=True)
def crear_editar_plantilla_boleta(request, plantilla_id=None):
    logger.debug(f"--- VISTA crear_editar_plantilla_boleta --- Método: {request.method}, Plantilla ID: {plantilla_id}")

    instancia_plantilla = None
    if plantilla_id:
        instancia_plantilla = get_object_or_404(PlantillaBoleta, pk=plantilla_id)
        logger.debug(f"Instancia encontrada para editar: ID {instancia_plantilla.pk}, Nombre: {instancia_plantilla.nombre}")
    else:
        logger.debug("No hay plantilla_id, se creará una nueva plantilla.")

    if request.method == 'POST':
        logger.debug("--- PROCESANDO POST request ---")
        form = PlantillaBoletaForm(request.POST, instance=instancia_plantilla)
        logger.debug(f"Formulario inicializado con POST data.")

        if form.is_valid():
            logger.debug("Formulario ES VÁLIDO.")
            plantilla_guardada = form.save(commit=False)
            
            if not instancia_plantilla:
                plantilla_guardada.usuario_creador = request.user
                logger.debug(f"Nueva plantilla, asignado usuario_creador: {request.user}")
            
            # Obtener string JSON del input hidden, default a string JSON de objeto vacío '{}'
            json_del_canvas_str = request.POST.get('datos_diseno_json_input', '{}')
            logger.debug(f"String JSON recibido del input hidden (primeros 300 chars): {json_del_canvas_str[:300]}...")

            try:
                # Parsear el string JSON a un objeto Python (dict)
                objeto_json_parseado = json.loads(json_del_canvas_str)
                logger.debug(f"Objeto JSON parseado con éxito. Tipo: {type(objeto_json_parseado)}")
                
                # Asignar el objeto Python al campo JSONField del modelo
                plantilla_guardada.datos_diseno_json = objeto_json_parseado
                logger.debug("Objeto JSON parseado asignado a plantilla_guardada.datos_diseno_json.")

            except json.JSONDecodeError as e:
                messages.error(request, f"Error al procesar el diseño del lienzo: {e}. El diseño podría no haberse guardado correctamente.")
                logger.error(f"ERROR json.JSONDecodeError al parsear JSON del canvas: {e}. String recibido: {json_del_canvas_str[:300]}...")
                # No se modifica el campo datos_diseno_json si hay error
                pass
            except Exception as e_general:
                messages.error(request, f"Error inesperado al procesar el diseño: {e_general}.")
                logger.error(f"ERROR GENERAL al procesar JSON del canvas: {e_general}", exc_info=True)
                pass

            try:
                logger.debug(f"Intentando guardar la plantilla (ID: {plantilla_guardada.pk if plantilla_guardada.pk else 'Nuevo'}) en la BD...")
                plantilla_guardada.save()
                logger.debug(f"Plantilla ID {plantilla_guardada.id} guardada/actualizada en BD.")
                messages.success(request, f"Plantilla '{plantilla_guardada.nombre}' guardada exitosamente.")
                logger.debug("--- FIN PROCESO POST (ÉXITO) --- Redirigiendo a lista_plantillas_boleta.")
                return redirect('lista_plantillas_boleta') 
            except Exception as e_save_db:
                messages.error(request, f"Error al guardar la plantilla en la base de datos: {e_save_db}")
                logger.error(f"ERROR al intentar plantilla_guardada.save(): {e_save_db}", exc_info=True)
        
        else: 
            messages.error(request, "Por favor corrige los errores en el formulario.")
            logger.warning(f"Formulario NO ES VÁLIDO. Errores: {form.errors.as_json()}")
            logger.debug("--- FIN PROCESO POST (FORMULARIO INVÁLIDO) ---")
    
    else: 
        logger.debug("--- PROCESANDO GET request ---")
        form = PlantillaBoletaForm(instance=instancia_plantilla)
        logger.debug("Formulario inicializado para GET request.")

    # Preparar datos_diseno_json_actual como un string JSON para el template
    datos_diseno_para_js_str = '{}' # Default string JSON de objeto vacío
    if instancia_plantilla and instancia_plantilla.datos_diseno_json:
        # datos_diseno_json es un dict Python si usas JSONField
        if isinstance(instancia_plantilla.datos_diseno_json, dict):
            try:
                # Convertir el dict Python a un string JSON
                datos_diseno_para_js_str = json.dumps(instancia_plantilla.datos_diseno_json)
                logger.debug(f"GET/FormInválido: Cargando diseño para JS desde plantilla ID {instancia_plantilla.id}. JSON (primeros 300): {datos_diseno_para_js_str[:300]}...")
            except TypeError as e_dump:
                logger.error(f"ERROR json.dumps al preparar datos para JS desde plantilla ID {instancia_plantilla.id}: {e_dump}. Contenido del campo: {instancia_plantilla.datos_diseno_json}", exc_info=True)
                messages.warning(request, f"No se pudo serializar el diseño guardado para la plantilla: {e_dump}")
        else:
            logger.warning(f"GET/FormInválido: El campo datos_diseno_json de la plantilla ID {instancia_plantilla.id} no es un diccionario Python. Tipo: {type(instancia_plantilla.datos_diseno_json)}. Valor: {str(instancia_plantilla.datos_diseno_json)[:200]}")
            messages.warning(request, "El diseño guardado para esta plantilla tiene un formato inesperado.")
    else:
        logger.debug("GET/FormInválido: No hay instancia de plantilla o el campo datos_diseno_json está vacío/nulo.")


    context = {
        'plantilla_form': form,
        'datos_diseno_json_actual': datos_diseno_para_js_str, 
        'placeholders_disponibles': PLACEHOLDERS_BOLETA_DEFINICION, 
        'placeholders_disponibles_json': json.dumps(PLACEHOLDERS_BOLETA_DEFINICION), 
        'titulo_pagina': "Diseñar Plantilla de Boleta"
    }

    if instancia_plantilla:
        context['titulo_pagina'] = f"Editar Plantilla: {instancia_plantilla.nombre}"
    
    logger.debug(f"Renderizando template 'boletas/disenador_plantilla.html' con contexto.")
    return render(request, 'boletas/disenador_plantilla.html', context)



@login_required
@permission_required('boletas.delete_plantillaboleta', raise_exception=True)
def eliminar_plantilla_boleta(request, plantilla_id):
    plantilla = get_object_or_404(PlantillaBoleta, pk=plantilla_id)
    nombre_plantilla = plantilla.nombre
    if request.method == 'POST':
        plantilla.delete()
        messages.success(request, f"Plantilla '{nombre_plantilla}' eliminada exitosamente.")
        return redirect('lista_plantillas_boleta') 
    context = {
        'plantilla': plantilla,
        'titulo_pagina': f"Eliminar Plantilla: {plantilla.nombre}"
    }
    return render(request, 'boletas/eliminar_plantilla_confirmacion.html', context)


# ---- Función Auxiliar para generar HTML (simplificada) ----
def ensure_string(value, default_if_none=""):
    """Asegura que el valor sea un string, o devuelve un default."""
    if value is None:
        return default_if_none
    return str(value)

def render_object_to_html(obj, sample_data):
    fabric_left = obj.get('left', 0)
    fabric_top = obj.get('top', 0)
    fabric_width_base = obj.get('width', 1)  
    fabric_height_base = obj.get('height', 1) 
    fabric_angle = obj.get('angle', 0)
    opacity = obj.get('opacity', 1)
    scale_x = obj.get('scaleX', 1)
    scale_y = obj.get('scaleY', 1)

    origin_x_fabric = obj.get('originX', 'left')
    origin_y_fabric = obj.get('originY', 'top')

    css_transform_origin_x = "0" 
    if origin_x_fabric == 'center':
        css_transform_origin_x = "50%"
    elif origin_x_fabric == 'right':
        css_transform_origin_x = "100%"

    css_transform_origin_y = "0" 
    if origin_y_fabric == 'center':
        css_transform_origin_y = "50%"
    elif origin_y_fabric == 'bottom':
        css_transform_origin_y = "100%"
    
    css_transform_origin = f"{css_transform_origin_x} {css_transform_origin_y}"

    div_width_css = fabric_width_base
    div_height_css = fabric_height_base
    
    obj_type = obj.get('type')

    if obj_type == 'line':
        stroke_w = float(obj.get('strokeWidth', 1))
        if abs(fabric_width_base) < stroke_w :
            div_width_css = stroke_w
        if abs(fabric_height_base) < stroke_w :
            div_height_css = stroke_w
        if abs(fabric_width_base) < stroke_w and abs(fabric_height_base) < stroke_w:
            div_width_css = stroke_w
            div_height_css = stroke_w


    styles = [
        f"position: absolute;",
        f"left: {ensure_string(fabric_left, '0')}px;",
        f"top: {ensure_string(fabric_top, '0')}px;",
        f"width: {ensure_string(div_width_css, '1')}px;",
        f"height: {ensure_string(div_height_css, '1')}px;",
        f"transform-origin: {css_transform_origin};",
        f"transform: rotate({ensure_string(fabric_angle, '0')}deg) scale({ensure_string(scale_x, '1')}, {ensure_string(scale_y, '1')});",
        f"opacity: {ensure_string(opacity, '1')};",
    ]

    tag = 'div'
    content = ''
    classes = f"preview-object preview-{obj_type}"
    additional_attrs_str = ''

    if obj_type == 'i-text':
        text_content_original = obj.get('text', '')
        placeholder_key = text_content_original.strip()
        rendered_text = sample_data.get(placeholder_key, text_content_original)
        content = escape(ensure_string(rendered_text, ''))

        styles.extend([
            f"font-family: {escape(ensure_string(obj.get('fontFamily', 'Arial')))};",
            f"font-size: {ensure_string(obj.get('fontSize', 12), '12')}px;",
            f"color: {escape(ensure_string(obj.get('fill', '#000000')))};",
            f"font-weight: {escape(ensure_string(obj.get('fontWeight', 'normal')))};",
            f"font-style: {escape(ensure_string(obj.get('fontStyle', 'normal')))};",
            f"text-decoration: {'underline' if obj.get('underline') else 'none'};",
            f"text-align: {escape(ensure_string(obj.get('textAlign', 'left')))};",
            f"line-height: {ensure_string(obj.get('lineHeight', 1.16))};", 
            f"white-space: pre-wrap;", 
            f"padding: {ensure_string(obj.get('padding',0), '0')}px;", 
            f"box-sizing: border-box;", 
        ])

    elif obj_type == 'line':
        stroke_color = escape(ensure_string(obj.get('stroke', '#000000')))
        stroke_width_val = float(obj.get('strokeWidth', 1))
        
        # Coordenadas locales de la línea en Fabric (relativas a su centro)
        line_fabric_x1 = obj.get('x1',0)
        line_fabric_y1 = obj.get('y1',0)
        line_fabric_x2 = obj.get('x2',0)
        line_fabric_y2 = obj.get('y2',0)
        
        # El SVG interno usará las dimensiones del div contenedor
        svg_container_w = div_width_css
        svg_container_h = div_height_css

        # Convertir coordenadas de la línea de Fabric (centradas en 0,0 local)
        # a coordenadas para el SVG (esquina superior izquierda es 0,0)
        svg_x1 = ensure_string(line_fabric_x1 + svg_container_w / 2)
        svg_y1 = ensure_string(line_fabric_y1 + svg_container_h / 2)
        svg_x2 = ensure_string(line_fabric_x2 + svg_container_w / 2)
        svg_y2 = ensure_string(line_fabric_y2 + svg_container_h / 2)

        content = (f"<svg width='{ensure_string(svg_container_w, '1')}' height='{ensure_string(svg_container_h, '1')}' "
                   f"xmlns='http://www.w3.org/2000/svg' style='position:absolute;left:0;top:0;overflow:visible;'>"
                   f"<line x1='{svg_x1}' y1='{svg_y1}' x2='{svg_x2}' y2='{svg_y2}' "
                   f"stroke='{stroke_color}' stroke-width='{ensure_string(stroke_width_val)}'/>" 
                   f"</svg>")

    elif obj_type == 'rect':
        styles.extend([
            f"background-color: {escape(ensure_string(obj.get('fill', 'transparent')))};",
            f"border: {ensure_string(obj.get('strokeWidth', 0), '0')}px solid {escape(ensure_string(obj.get('stroke', 'transparent')))};",
            f"box-sizing: border-box;", # Importante si strokeWidth > 0 para que el borde no aumente el tamaño
        ])
    elif obj_type == 'image':
        tag = 'img'
        img_src = obj.get('src', '#')
        additional_attrs_str = f'src="{escape(ensure_string(img_src))}" alt="BoletaImg"'
        styles.append("object-fit: fill;") 
    else:
        content = f"[Tipo: {escape(ensure_string(obj_type, 'desconocido'))}]"
        styles.append("border: 1px dashed red;")

    final_styles_str = " ".join(s for s in styles if s is not None)

    if tag == 'img':
        return f'<img {additional_attrs_str} style="{final_styles_str}" class="{classes}">'
    else:
        return f'<div style="{final_styles_str}" class="{classes}" {additional_attrs_str}>{ensure_string(content)}</div>'

# -----------------------------
@require_POST 
@csrf_exempt 
@login_required
@permission_required('boletas.view_plantillaboleta', raise_exception=True)

def preview_boleta_view(request):
    logger.debug("Recibida solicitud de previsualización")
    try:
        # Leer el JSON del cuerpo de la solicitud POST
        design_data_str = request.body.decode('utf-8')
        if not design_data_str:
            logger.warning("Cuerpo de solicitud POST vacío para previsualización.")
            return HttpResponse("Error: No se recibió diseño.", status=400)

        design_data = json.loads(design_data_str)
        logger.debug(f"JSON de diseño recibido y parseado para previsualización. Objetos: {len(design_data.get('objects', []))}")

        # --- Datos de Ejemplo ---
        sample_data = {
            # --- Datos Personales ---
            '{{nombre}}': 'ANA',
            '{{nombre_completo}}': 'ANA MARTINEZ PRUEBA',
            '{{ci}}': '9876543 CB',
            '{{apellido_paterno}}' : 'MARTINEZ',
            '{{apellido_materno}}': 'PRUEBA',
            # --- Datos de designación ---
            '{{item}}': '1001',
            '{{tipo_designacion}}': 'Asegurado',
            '{{fecha_ingreso}}': '01/01/2025',
            '{{fecha_conclusion}}': '01/01/2025',
            # --- Datos de designación2 ---
            '{{cargo_nombre_cargo}}': 'PROFESIONAL I',
            '{{unidad_nombre_unidad}}': 'AREA DE SISTEMAS',
            '{{secretaria_nombre_secretaria}}': 'UNIDAD FINANCIERA', 
            # --- Datos de planilla sueldo ---
            '{{planilla_mes}}': '1',
            '{{planilla_anio}}': '2025',
            '{{planilla_tipo}}': 'ASEGURADO',
            '{{planilla_tipo_display}}': 'PERSONAL_PERMANENTE',
            # --- Datos boletas ---
            '{{dias_trab}}': '30',
            '{{haber_basico}}': '3500.00',
            '{{categoria}}': '0.00',
            '{{lactancia_prenatal}}': '0.00',
            '{{saldo_credito_fiscal}}': '100.00',
            '{{total_ganado}}': '3600.00',
            '{{rc_iva_retenido}}': '0.00',
            '{{gestora_publica}}': '0.00',
            '{{aporte_nac_solidario}}': '0.00',
            '{{cooperativa}}': '0.00',
            '{{faltas}}': '0.00',
            '{{memorandums}}': '100.00',
            '{{otros_descuentos}}': '3600.00',
            '{{total_descuentos}}': '600.00',
            '{{liquido_pagable}}': '3000.00',
            '{{cargo_referencia}}': 'PROFESIONAL I',

            # --- Datos Calculados ---
            '{{literal_liquido}}': 'TRES MIL BOLIVIANOS',
            '{{fecha_emision_actual}}': datetime.now().strftime('%d/%m/%Y'),
            '{{mes_literal_actual}}': datetime.now().strftime('%B').upper(),
            '{{CODIGO_QR}}': 'QR',
            '{{literal_liquido_extendido}}': 'TRES MIL CON CINCUENTA',
        }
        logger.debug(f"Datos de ejemplo generados: {list(sample_data.keys())}")

        # --- Generar HTML ---
        html_objects = []
        if 'objects' in design_data and isinstance(design_data['objects'], list):
             
            import math
            for obj in design_data['objects']:
                if not obj.get('isGridLine'):
                    html_objects.append(render_object_to_html(obj, sample_data))
            logger.debug(f"Generados {len(html_objects)} elementos HTML para la previsualización.")
        else:
            logger.warning("El JSON de diseño recibido no tiene una lista 'objects'.")


        canvas_width = 612
        canvas_height = 792
        #canvas_width = 595
        #canvas_height = 842
        final_html = f"""
        <div id="preview-container" style="width: {canvas_width}px; height: {canvas_height}px; border: 1px dashed #aaa; position: relative; background-color: white; margin: 10px auto; overflow: hidden;">
            {''.join(html_objects)}
        </div>
        """

        return HttpResponse(final_html)

    except json.JSONDecodeError:
        logger.error("Error al decodificar JSON en previsualización.", exc_info=True)
        return HttpResponse("Error: Diseño inválido.", status=400)
    except Exception as e:
        logger.error(f"Error inesperado en previsualización: {e}", exc_info=True)
        return HttpResponse(f"Error interno: {e}", status=500)
    


# --------------------------
@login_required
@permission_required('sueldos.view_planillasueldo', raise_exception=True)
def generar_pdf_boletas_por_planilla(request, planilla_sueldo_id):
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Spanish')
        except locale.Error:
            logger.warning("Locale para español no encontrado.")
    logger.info(f"Solicitud para generar PDF para PlanillaSueldo ID: {planilla_sueldo_id}")
    # --- 1. Obtener Planilla de Sueldos y Detalles ---
    try:
        planilla_sueldo = PlanillaSueldo.objects.select_related('usuario_creacion').get(pk=planilla_sueldo_id)
        logger.debug(f"Planilla de sueldos encontrada: {planilla_sueldo}")
        detalles_sueldo = DetalleSueldo.objects.filter(planilla_sueldo=planilla_sueldo) 
        if not detalles_sueldo.exists():
            logger.warning(f"No se encontraron detalles de sueldo para la PlanillaSueldo ID: {planilla_sueldo_id}")
            messages.warning(request, f"La planilla de sueldos {planilla_sueldo.mes}/{planilla_sueldo.anio} ({planilla_sueldo.get_tipo_display()}) no tiene empleados cargados.")
            return HttpResponse("No hay detalles para generar.", status=404) 
        logger.info(f"Encontrados {detalles_sueldo.count()} detalles de sueldo para procesar.")
    except PlanillaSueldo.DoesNotExist:
        logger.error(f"PlanillaSueldo con ID={planilla_sueldo_id} no encontrada.")
        raise Http404(f"Planilla de Sueldos no encontrada.")
    except Exception as e:
        logger.error(f"Error obteniendo datos de PlanillaSueldo/DetalleSueldo: {e}", exc_info=True)
        messages.error(request, "Error al obtener los datos de la planilla de sueldos.")
        return HttpResponse("Error interno al obtener datos.", status=500)
    # --- 2. Obtener la Plantilla de Boleta a Usar ---
    try:
        plantilla_boleta = PlantillaBoleta.objects.filter(es_predeterminada=True).first()
        if not plantilla_boleta:
            plantilla_boleta = PlantillaBoleta.objects.first() 
        if not plantilla_boleta:
            logger.error("No se encontró ninguna Plantilla de Boleta en el sistema.")
            messages.error(request, "No hay plantillas de boleta configuradas para generar el PDF.")
            # return redirect('lista_planillas_boleta')
            return HttpResponse("Error: No hay plantillas de boleta.", status=500)

        logger.debug(f"Usando plantilla de boleta: '{plantilla_boleta.nombre}' (ID: {plantilla_boleta.id})")
        # Parsear el diseño JSON una sola vez
        diseno_json_dict = plantilla_boleta.datos_diseno_json or {}
        if not isinstance(diseno_json_dict, dict) or 'objects' not in diseno_json_dict:
             logger.error(f"El JSON de diseño de la plantilla ID {plantilla_boleta.id} está vacío o corrupto.")
             messages.error(request, f"El diseño de la plantilla '{plantilla_boleta.nombre}' está corrupto.")
             # return redirect('lista_planillas_boleta')
             return HttpResponse("Error: Diseño de plantilla corrupto.", status=500)

    except Exception as e:
        logger.error(f"Error obteniendo la Plantilla de Boleta: {e}", exc_info=True)
        messages.error(request, "Error al obtener la plantilla de diseño de boleta.")
        # return redirect('lista_planillas_boleta')
        return HttpResponse("Error interno al obtener plantilla.", status=500)

    # --- 3. Preparar PDF ---
    buffer = io.BytesIO()
    p = pdf_canvas_gen.Canvas(buffer, pagesize=LETTER)
    page_width, page_height = LETTER  # Usar tamaño carta por defecto
    #page_width, page_height = A4 

    logger.debug(f"Canvas PDF creado. Tamaño página: {page_width}x{page_height} puntos.")

    # --- 4. Iterar y Dibujar Cada Boleta ---
    num_boletas_generadas = 0
    errores_empleados = []

    for detalle in detalles_sueldo:
        logger.debug(f"Procesando DetalleSueldo ID: {detalle.id}, Personal Externo ID: {detalle.personal_externo_id}")
        try:
            # --- 4a. Recopilar todos los datos para este empleado ---
            datos_empleado_actual = {}
            personal_ext = None
            designacion_activa = None

            if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
                # Obtener datos de PrincipalPersonalExterno
                try:
                    personal_ext = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
                    datos_empleado_actual['{{nombre}}'] = personal_ext.nombre or ''
                    datos_empleado_actual['{{apellido_paterno}}'] = personal_ext.apellido_paterno or ''
                    datos_empleado_actual['{{apellido_materno}}'] = personal_ext.apellido_materno or ''
                    datos_empleado_actual['{{nombre_completo}}'] = personal_ext.nombre_completo 
                    datos_empleado_actual['{{ci}}'] = personal_ext.ci or 'S/CI'
                except PrincipalPersonalExterno.DoesNotExist:
                     logger.warning(f"No se encontró PrincipalPersonalExterno ID: {detalle.personal_externo_id}")
                     errores_empleados.append(f"ID {detalle.personal_externo_id}: Datos personales no encontrados.")
                     continue # Saltar al siguiente empleado
                except Exception as e_pers:
                     logger.error(f"Error obteniendo datos personales para ID {detalle.personal_externo_id}: {e_pers}")
                     errores_empleados.append(f"ID {detalle.personal_externo_id}: Error datos personales.")
                     continue

                # Obtener datos de la Designación ACTIVA (o la más relevante)
                try:
                    
                    tipo_externo_map = {
                        'planta': 'ASEGURADO',
                        'contrato': 'CONTRATO',
                        'consultor en linea': 'CONSULTOR EN LINEA',
                    }
                    tipo_designacion_busqueda = tipo_externo_map.get(planilla_sueldo.tipo)

                    if tipo_designacion_busqueda:
                        designacion_activa = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('cargo', 'unidad__secretaria') \
                            .filter(
                                personal_id=detalle.personal_externo_id,
                                estado='ACTIVO', 
                                tipo_designacion=tipo_designacion_busqueda
                            ).order_by('-fecha_ingreso').first() 

                    if designacion_activa:
                        datos_empleado_actual['{{item}}'] = str(designacion_activa.item) if designacion_activa.item is not None else ''
                        datos_empleado_actual['{{tipo_designacion}}'] = designacion_activa.tipo_designacion or ''
                        datos_empleado_actual['{{fecha_ingreso}}'] = designacion_activa.fecha_ingreso.strftime('%d/%m/%Y') if designacion_activa.fecha_ingreso else ''
                        datos_empleado_actual['{{fecha_conclusion}}'] = designacion_activa.fecha_conclusion.strftime('%d/%m/%Y') if designacion_activa.fecha_conclusion else ''
                        datos_empleado_actual['{{cargo_nombre_cargo}}'] = designacion_activa.cargo.nombre_cargo if designacion_activa.cargo else ''
                        datos_empleado_actual['{{unidad_nombre_unidad}}'] = designacion_activa.unidad.nombre_unidad if designacion_activa.unidad else ''
                        datos_empleado_actual['{{secretaria_nombre_secretaria}}'] = designacion_activa.unidad.secretaria.nombre_secretaria if designacion_activa.unidad and designacion_activa.unidad.secretaria else ''
                    else:
                        logger.warning(f"No se encontró designación ACTIVA y del tipo correcto para ID: {detalle.personal_externo_id}")
                        # Llenar con vacíos o N/A para evitar errores al reemplazar placeholders
                        datos_empleado_actual['{{item}}'] = 'N/A'
                        datos_empleado_actual['{{tipo_designacion}}'] = 'N/A'
                        errores_empleados.append(f"ID {detalle.personal_externo_id}: Designación no encontrada.")

                except Exception as e_desig:
                     logger.error(f"Error obteniendo datos de designación para ID {detalle.personal_externo_id}: {e_desig}")
                     errores_empleados.append(f"ID {detalle.personal_externo_id}: Error datos designación.")
                     
            else:
                 
                 errores_empleados.append(f"ID {detalle.personal_externo_id}: Módulo Planilla no disponible.")
                 continue


            # --- Añadir datos de PlanillaSueldo ---
            datos_empleado_actual['{{planilla_mes}}'] = str(planilla_sueldo.mes)
            datos_empleado_actual['{{planilla_anio}}'] = str(planilla_sueldo.anio)
            datos_empleado_actual['{{planilla_tipo}}'] = planilla_sueldo.tipo
            datos_empleado_actual['{{planilla_tipo_display}}'] = planilla_sueldo.get_tipo_display()


            # --- Añadir datos de DetalleSueldo (formateados como string) ---
            from decimal import Decimal, ROUND_HALF_UP
            quantizer = Decimal('0.01') 

            datos_empleado_actual['{{cargo_referencia}}'] = detalle.cargo_referencia or '' 
            datos_empleado_actual['{{dias_trab}}'] = str((detalle.dias_trab or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{haber_basico}}'] = str((detalle.haber_basico or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{categoria}}'] = str((detalle.categoria or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{lactancia_prenatal}}'] = str((detalle.lactancia_prenatal or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{otros_ingresos}}'] = str((detalle.otros_ingresos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{saldo_credito_fiscal}}'] = str((detalle.saldo_credito_fiscal or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{total_ganado}}'] = str((detalle.total_ganado or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{rc_iva_retenido}}'] = str((detalle.rc_iva_retenido or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{gestora_publica}}'] = str((detalle.gestora_publica or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{aporte_nac_solidario}}'] = str((detalle.aporte_nac_solidario or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{cooperativa}}'] = str((detalle.cooperativa or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{faltas}}'] = str((detalle.faltas or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{memorandums}}'] = str((detalle.memorandums or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{otros_descuentos}}'] = str((detalle.otros_descuentos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{total_descuentos}}'] = str((detalle.total_descuentos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{liquido_pagable}}'] = str((detalle.liquido_pagable or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))


            # --- Añadir datos calculados ---
            datos_empleado_actual['{{fecha_emision_actual}}'] = datetime.now().strftime('%d/%m/%Y')
            monto_liquido = detalle.liquido_pagable or Decimal(0)
            datos_empleado_actual['{{literal_liquido}}'] = numero_a_literal(monto_liquido)
            datos_empleado_actual['{{literal_liquido_extendido}}'] = numero_a_literal_con_decimal_y_salto(monto_liquido)
            try:
                import calendar
                mes_literal = calendar.month_name[planilla_sueldo.mes].upper()
            except Exception as e_mes:
                logger.warning(f"Error obteniendo nombre del mes para {planilla_sueldo.mes}: {e_mes}")
                mes_literal = f"MES {planilla_sueldo.mes}"
            datos_empleado_actual['{{mes_literal_actual}}'] = mes_literal
            
            # --- 4b. Llamar a la función de dibujo (a crear en utils.py) ---
            logger.debug(f"Llamando a dibujar_boleta_en_canvas para empleado CI: {datos_empleado_actual.get('{{ci}}', 'N/A')}")
            dibujar_boleta_en_canvas(p, page_height, diseno_json_dict, datos_empleado_actual)

            p.showPage() # Crear una nueva página para la siguiente boleta
            logger.debug("Página añadida al PDF.")
            num_boletas_generadas += 1

        except Exception as e_empleado:
            empleado_id_log = f"Detalle ID {detalle.id} / Pers ID {detalle.personal_externo_id}"
            logger.error(f"Error procesando boleta para {empleado_id_log}: {e_empleado}", exc_info=True)
            errores_empleados.append(f"{empleado_id_log}: {e_empleado}")

    # --- 5. Finalizar y Devolver PDF ---
    if num_boletas_generadas > 0:
        logger.info(f"Generación PDF completada. Boletas generadas: {num_boletas_generadas}. Errores: {len(errores_empleados)}.")
        p.save()
         # --- REGISTRAR ACCIÓN EN AUDITLOG  ---
        try:
            content_type_planilla_sueldo = ContentType.objects.get_for_model(PlanillaSueldo)
            log_changes_description = (
                f"Se generó un PDF con {num_boletas_generadas} boletas para la Planilla de Sueldos "
                f"{planilla_sueldo.get_tipo_display()} {planilla_sueldo.mes}/{planilla_sueldo.anio} (ID: {planilla_sueldo.id}). "
                f"Se utilizó la Plantilla de Boleta '{plantilla_boleta.nombre}' (ID: {plantilla_boleta.id})."
            )
            if errores_empleados:
                log_changes_description += f" Hubo {len(errores_empleados)} errores al procesar empleados individuales."

            
            LogEntry.objects.create(
                actor=request.user,
                content_type=content_type_planilla_sueldo,
                object_pk=str(planilla_sueldo.pk), 
                object_id=planilla_sueldo.pk,   
                object_repr=str(planilla_sueldo),
                action=LogEntry.Action.ACCESS, 
                changes=log_changes_description,
                remote_addr=request.META.get('REMOTE_ADDR'), 
                
            )
            logger.info(f"Acción de generación de PDF registrada en auditlog para PlanillaSueldo ID: {planilla_sueldo.id}")
        except Exception as e_audit:
            logger.error(f"Error al registrar la acción de generación de PDF en auditlog: {e_audit}", exc_info=True)


        buffer.seek(0) 
        response = HttpResponse(buffer, content_type='application/pdf')
        filename = f"boletas_{planilla_sueldo.tipo}_{planilla_sueldo.mes}_{planilla_sueldo.anio}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"' 
        return response
    else:
        logger.error("No se generó ninguna boleta exitosamente.")
        messages.error(request, "No se pudo generar ninguna boleta. Revise los logs para más detalles.")
        if errores_empleados:
            messages.warning(request, f"Errores encontrados durante la generación: {'; '.join(errores_empleados[:3])}{'...' if len(errores_empleados)>3 else ''}")

        # --- REGISTRAR INTENTO FALLIDO EN AUDITLOG ---
        try:
            content_type_planilla_sueldo = ContentType.objects.get_for_model(PlanillaSueldo)
            log_failure_description = (
            )
            LogEntry.objects.create(
                actor=request.user,
                content_type=content_type_planilla_sueldo,
                object_pk=str(planilla_sueldo.pk),
                object_id=planilla_sueldo.pk,
                object_repr=str(planilla_sueldo),
                action=LogEntry.Action.ACCESS, 
                changes=log_failure_description,
                remote_addr=request.META.get('REMOTE_ADDR'),
            )
            logger.info(f"Intento fallido de generación de PDF registrado en auditlog para PlanillaSueldo ID: {planilla_sueldo.id}")
        except Exception as e_audit_fail:
            logger.error(f"Error al registrar el intento fallido de generación de PDF en auditlog: {e_audit_fail}", exc_info=True)
        return HttpResponse("Error: No se generaron boletas.", status=500)
    

#---------------------------
@login_required
@permission_required('boletas.view_plantillaboleta', raise_exception=True)
@require_GET
def obtener_diseno_plantilla_json(request, plantilla_id):
    logger.debug(f"Solicitud GET para obtener JSON de diseño para Plantilla ID: {plantilla_id}")
    try:
        plantilla = PlantillaBoleta.objects.get(pk=plantilla_id)
        
        # El campo datos_diseno_json ya es un diccionario Python si usas models.JSONField
        diseno_data = plantilla.datos_diseno_json 
        
        if not diseno_data or not isinstance(diseno_data, dict):
            logger.warning(f"Diseño JSON para plantilla ID {plantilla_id} está vacío o no es un diccionario. Contenido: {diseno_data}")
            return JsonResponse({'objects': [], 'background': 'white'}, status=200) 

        logger.debug(f"Diseño JSON encontrado para plantilla ID {plantilla_id}. Tiene {len(diseno_data.get('objects', []))} objetos.")
        return JsonResponse(diseno_data) # JsonResponse serializa el dict a JSON y establece el Content-Type correcto

    except PlantillaBoleta.DoesNotExist:
        logger.error(f"obtener_diseno_plantilla_json: PlantillaBoleta con ID={plantilla_id} no encontrada.")
        return JsonResponse({'error': 'Plantilla no encontrada'}, status=404)
    except Exception as e:
        logger.error(f"Error en obtener_diseno_plantilla_json para ID {plantilla_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'Error interno del servidor: {str(e)}'}, status=500)


@login_required
@permission_required('boletas.view_plantillaboleta', raise_exception=True) 
def vista_generar_boleta_individual_buscar(request):
    context = {
        'titulo_pagina': "Generar Boleta Individual",
        'empleado_encontrado': None,
        'detalles_sueldo_empleado': None,
        'termino_busqueda': '',
    }
    if request.method == 'GET' and 'termino_busqueda' in request.GET:
        termino = request.GET.get('termino_busqueda', '').strip()
        context['termino_busqueda'] = termino
        if not termino:
            messages.warning(request, "Por favor, ingrese un C.I. o Ítem para buscar.")
            return render(request, 'boletas/generar_boleta_individual_buscar.html', context)
        if not PLANILLA_APP_AVAILABLE_FOR_SEARCH:
            messages.error(request, "La funcionalidad de búsqueda de personal no está disponible (Error de configuración).")
            return render(request, 'boletas/generar_boleta_individual_buscar.html', context)
        personal_encontrado = None
        ci_busqueda = termino.replace(" ", "").upper()
        try:
            personal_encontrado = PrincipalPersonalExterno.objects.using('personas_db').filter(ci__iexact=ci_busqueda).first()
        except Exception as e:
            logger.error(f"Error buscando PrincipalPersonalExterno por CI '{ci_busqueda}': {e}")
            messages.error(request, f"Ocurrió un error al buscar por C.I.: {e}")
        if not personal_encontrado and termino.isdigit():
            try:
                item_busqueda = int(termino)
                designacion = PrincipalDesignacionExterno.objects.using('personas_db').filter(
                    item=item_busqueda
                ).order_by('-fecha_ingreso', '-id').select_related('personal').first() 
                if designacion and designacion.personal:
                    personal_encontrado = designacion.personal
                else:
                    logger.info(f"No se encontró designación o personal asociado para Ítem: {item_busqueda}")
            except ValueError:
                logger.warning(f"El término '{termino}' no es un número válido para búsqueda por Ítem.")
            except Exception as e:
                logger.error(f"Error buscando PrincipalDesignacionExterno por Ítem '{termino}': {e}")
                messages.error(request, f"Ocurrió un error al buscar por Ítem: {e}")
        if personal_encontrado:
            context['empleado_encontrado'] = personal_encontrado
            detalles = DetalleSueldo.objects.filter(
                personal_externo_id=personal_encontrado.id
            ).select_related('planilla_sueldo').order_by(
                '-planilla_sueldo__anio', 
                '-planilla_sueldo__mes'
            )
            if detalles.exists():
                context['detalles_sueldo_empleado'] = detalles
            else:
                messages.info(request, f"El empleado '{personal_encontrado.nombre_completo}' fue encontrado, pero no tiene registros de sueldo en el sistema.")
        else:
            messages.error(request, f"No se encontró ningún empleado con el C.I. o Ítem: '{termino}'.")
    return render(request, 'boletas/generar_boleta_individual_buscar.html', context)


#----------------------------------

@login_required
@permission_required('boletas.view_plantillaboleta', raise_exception=True) 
def vista_generar_pdf_boleta_unica(request, personal_externo_id, anio, mes):
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Spanish')
        except locale.Error:
            logger.warning("Locale para español no encontrado.")
            
    logger.info(f"Solicitud para generar PDF de boleta única. Personal ID: {personal_externo_id}, Periodo: {mes}/{anio}")

    # --- 1. Obtener el Detalle de Sueldo Específico ---
    try:
        detalle_sueldo = DetalleSueldo.objects.select_related(
            'planilla_sueldo', 
        ).get(
            personal_externo_id=personal_externo_id,
            planilla_sueldo__anio=anio,
            planilla_sueldo__mes=mes
        )
        planilla_sueldo_base = detalle_sueldo.planilla_sueldo
        logger.debug(f"Detalle de sueldo encontrado: ID {detalle_sueldo.id} para Planilla {planilla_sueldo_base}")

    except DetalleSueldo.DoesNotExist:
        logger.error(f"DetalleSueldo no encontrado para Personal ID: {personal_externo_id}, Periodo: {mes}/{anio}")
        messages.error(request, "No se encontró el registro de sueldo para el empleado y periodo especificado.")
        # Podrías redirigir a la página de búsqueda o mostrar un Http404
        # return redirect('generar_boleta_individual_buscar') 
        raise Http404("Registro de sueldo no encontrado.")
    except Exception as e:
        logger.error(f"Error obteniendo DetalleSueldo: {e}", exc_info=True)
        messages.error(request, "Error al obtener los datos del sueldo.")
        # return redirect('generar_boleta_individual_buscar')
        return HttpResponse("Error interno al obtener datos del sueldo.", status=500)

    # --- 2. Obtener la Plantilla de Boleta Predeterminada ---
    try:
        plantilla_boleta = PlantillaBoleta.objects.filter(es_predeterminada=True).first()
        if not plantilla_boleta:
            plantilla_boleta = PlantillaBoleta.objects.first()

        if not plantilla_boleta:
            logger.error("PDF ÚNICO: No se encontró ninguna Plantilla de Boleta en el sistema.")
            messages.error(request, "No hay plantillas de boleta configuradas para generar el PDF.")
            return HttpResponse("Error: No hay plantillas de boleta configuradas.", status=500)

        logger.debug(f"PDF ÚNICO: Usando plantilla de boleta: '{plantilla_boleta.nombre}' (ID: {plantilla_boleta.id})")
        diseno_json_dict = plantilla_boleta.datos_diseno_json or {}
        if not isinstance(diseno_json_dict, dict) or 'objects' not in diseno_json_dict:
             logger.error(f"PDF ÚNICO: El JSON de diseño de la plantilla ID {plantilla_boleta.id} está vacío o corrupto.")
             messages.error(request, f"El diseño de la plantilla '{plantilla_boleta.nombre}' está corrupto.")
             return HttpResponse("Error: Diseño de plantilla corrupto.", status=500)

    except Exception as e:
        logger.error(f"PDF ÚNICO: Error obteniendo la Plantilla de Boleta: {e}", exc_info=True)
        messages.error(request, "Error al obtener la plantilla de diseño de boleta.")
        return HttpResponse("Error interno al obtener plantilla de diseño.", status=500)

    # --- 3. Datos del Empleado y Sueldo (Similar a generar_pdf_boletas_por_planilla) ---
    datos_empleado_actual = {}
    personal_ext = None
    designacion_activa = None 

    if PLANILLA_APP_AVAILABLE_FOR_SEARCH and detalle_sueldo.personal_externo_id: 
        try:
            personal_ext = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle_sueldo.personal_externo_id)
            datos_empleado_actual['{{nombre}}'] = personal_ext.nombre or ''
            datos_empleado_actual['{{apellido_paterno}}'] = personal_ext.apellido_paterno or ''
            datos_empleado_actual['{{apellido_materno}}'] = personal_ext.apellido_materno or ''
            datos_empleado_actual['{{nombre_completo}}'] = personal_ext.nombre_completo
            datos_empleado_actual['{{ci}}'] = personal_ext.ci or 'S/CI'
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"PDF ÚNICO: No se encontró PrincipalPersonalExterno ID: {detalle_sueldo.personal_externo_id}")
            messages.error(request, "Datos personales del empleado no encontrados en la base de datos externa.")
            return HttpResponse("Error: Datos personales no encontrados.", status=404)
        except Exception as e_pers:
            logger.error(f"PDF ÚNICO: Error obteniendo datos personales para ID {detalle_sueldo.personal_externo_id}: {e_pers}")
            messages.error(request, "Error al consultar datos personales del empleado.")
            return HttpResponse("Error: Fallo al consultar datos personales.", status=500)

        # Obtener datos de la Designación ACTIVA (o la más relevante para el periodo de la boleta)
        try:
            
            tipo_externo_map = {
                'planta': 'ASEGURADO', 'contrato': 'CONTRATO', 'consultor en linea': 'CONSULTOR EN LINEA',
            }
            tipo_designacion_busqueda = tipo_externo_map.get(planilla_sueldo_base.tipo)

            if tipo_designacion_busqueda:
                
                designacion_activa = PrincipalDesignacionExterno.objects.using('personas_db') \
                    .filter(
                        personal_id=detalle_sueldo.personal_externo_id,
                        tipo_designacion=tipo_designacion_busqueda,
                        estado='ACTIVO' 
                    ).order_by('-fecha_ingreso').select_related('cargo', 'unidad__secretaria').first()


            if designacion_activa:
                datos_empleado_actual['{{item}}'] = str(designacion_activa.item) if designacion_activa.item is not None else (str(detalle_sueldo.item_referencia) if detalle_sueldo.item_referencia is not None else 'S/I')
                datos_empleado_actual['{{tipo_designacion}}'] = designacion_activa.tipo_designacion or ''
                datos_empleado_actual['{{fecha_ingreso}}'] = designacion_activa.fecha_ingreso.strftime('%d/%m/%Y') if designacion_activa.fecha_ingreso else (detalle_sueldo.fecha_ingreso_referencia.strftime('%d/%m/%Y') if detalle_sueldo.fecha_ingreso_referencia else '')
                datos_empleado_actual['{{fecha_conclusion}}'] = designacion_activa.fecha_conclusion.strftime('%d/%m/%Y') if designacion_activa.fecha_conclusion else ''
                datos_empleado_actual['{{cargo_nombre_cargo}}'] = (designacion_activa.cargo.nombre_cargo if designacion_activa.cargo else '') or (detalle_sueldo.cargo_referencia or '')
                datos_empleado_actual['{{unidad_nombre_unidad}}'] = designacion_activa.unidad.nombre_unidad if designacion_activa.unidad else ''
                datos_empleado_actual['{{secretaria_nombre_secretaria}}'] = designacion_activa.unidad.secretaria.nombre_secretaria if designacion_activa.unidad and designacion_activa.unidad.secretaria else ''
            else: 
                logger.warning(f"PDF ÚNICO: No se encontró designación ACTIVA para ID {detalle_sueldo.personal_externo_id}. Usando datos de referencia del sueldo.")
                datos_empleado_actual['{{item}}'] = str(detalle_sueldo.item_referencia) if detalle_sueldo.item_referencia is not None else 'S/I'
                datos_empleado_actual['{{cargo_nombre_cargo}}'] = detalle_sueldo.cargo_referencia or 'N/A'
                datos_empleado_actual['{{fecha_ingreso}}'] = detalle_sueldo.fecha_ingreso_referencia.strftime('%d/%m/%Y') if detalle_sueldo.fecha_ingreso_referencia else 'N/A'
                datos_empleado_actual['{{tipo_designacion}}'] = 'N/A'
                datos_empleado_actual['{{unidad_nombre_unidad}}'] = 'N/A'
                datos_empleado_actual['{{secretaria_nombre_secretaria}}'] = 'N/A'

        except Exception as e_desig:
            logger.error(f"PDF ÚNICO: Error obteniendo datos de designación para ID {detalle_sueldo.personal_externo_id}: {e_desig}")
            datos_empleado_actual['{{item}}'] = str(detalle_sueldo.item_referencia) if detalle_sueldo.item_referencia is not None else 'S/I'
            datos_empleado_actual['{{cargo_nombre_cargo}}'] = detalle_sueldo.cargo_referencia or 'Error Designación'
    else:
        messages.error(request, "Módulo de personal no disponible.")
        return HttpResponse("Error: Módulo de personal no disponible.", status=500)

    # --- Añadir datos de PlanillaSueldo (la planilla base del detalle) ---
    datos_empleado_actual['{{planilla_mes}}'] = str(planilla_sueldo_base.mes)
    datos_empleado_actual['{{planilla_anio}}'] = str(planilla_sueldo_base.anio)
    datos_empleado_actual['{{planilla_tipo}}'] = planilla_sueldo_base.tipo
    datos_empleado_actual['{{planilla_tipo_display}}'] = planilla_sueldo_base.get_tipo_display()

    # --- Añadir datos de DetalleSueldo (formateados como string) ---
    from decimal import Decimal, ROUND_HALF_UP # Asegúrate que esté importado
    quantizer = Decimal('0.01')
    
    datos_empleado_actual['{{cargo_referencia}}'] = detalle_sueldo.cargo_referencia or ''
    datos_empleado_actual['{{dias_trab}}'] = str((detalle_sueldo.dias_trab or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{haber_basico}}'] = str((detalle_sueldo.haber_basico or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{categoria}}'] = str((detalle_sueldo.categoria or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{lactancia_prenatal}}'] = str((detalle_sueldo.lactancia_prenatal or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{otros_ingresos}}'] = str((detalle_sueldo.otros_ingresos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{saldo_credito_fiscal}}'] = str((detalle_sueldo.saldo_credito_fiscal or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{total_ganado}}'] = str((detalle_sueldo.total_ganado or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{rc_iva_retenido}}'] = str((detalle_sueldo.rc_iva_retenido or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{gestora_publica}}'] = str((detalle_sueldo.gestora_publica or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{aporte_nac_solidario}}'] = str((detalle_sueldo.aporte_nac_solidario or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{cooperativa}}'] = str((detalle_sueldo.cooperativa or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{faltas}}'] = str((detalle_sueldo.faltas or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{memorandums}}'] = str((detalle_sueldo.memorandums or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{otros_descuentos}}'] = str((detalle_sueldo.otros_descuentos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{total_descuentos}}'] = str((detalle_sueldo.total_descuentos or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
    datos_empleado_actual['{{liquido_pagable}}'] = str((detalle_sueldo.liquido_pagable or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))

    # --- Añadir datos calculados (fecha emisión, literal, mes literal) ---
    datos_empleado_actual['{{fecha_emision_actual}}'] = datetime.now().strftime('%d/%m/%Y')
    
    from .utils import numero_a_literal 
    monto_liquido = detalle_sueldo.liquido_pagable or Decimal(0)
    datos_empleado_actual['{{literal_liquido}}'] = numero_a_literal(monto_liquido)
    datos_empleado_actual['{{literal_liquido_extendido}}'] = numero_a_literal_con_decimal_y_salto(monto_liquido)

    import calendar 
    try:
        mes_literal_str = calendar.month_name[planilla_sueldo_base.mes].upper()
    except Exception:
        mes_literal_str = f"MES {planilla_sueldo_base.mes}"
    datos_empleado_actual['{{mes_literal_actual}}'] = mes_literal_str
    
    # --- 4. Preparar y Generar PDF ---
    buffer = io.BytesIO()
    p_canvas = pdf_canvas_gen.Canvas(buffer, pagesize=LETTER) # Usar tamaño carta por defecto
    _page_width, page_height = LETTER # Para la función de dibujo

    logger.debug(f"PDF ÚNICO: Llamando a dibujar_boleta_en_canvas para CI: {datos_empleado_actual.get('{{ci}}', 'N/A')}")
    
    dibujar_boleta_en_canvas(p_canvas, page_height, diseno_json_dict, datos_empleado_actual)
    
    p_canvas.showPage() 
    p_canvas.save()
    try:
        
        if personal_ext: 
            content_type_obj = ContentType.objects.get_for_model(PrincipalPersonalExterno)
            obj_pk = str(personal_ext.pk)
            obj_id_numeric = personal_ext.pk
            obj_repr = str(personal_ext)
        elif detalle_sueldo.personal_externo_id: 
           
            content_type_obj = ContentType.objects.get_for_model(DetalleSueldo)
            obj_pk = str(detalle_sueldo.pk)
            obj_id_numeric = detalle_sueldo.pk
            obj_repr = f"Detalle Sueldo ID {detalle_sueldo.pk} (Personal Ext. ID {detalle_sueldo.personal_externo_id})"
        else: 
            content_type_obj = None
            obj_pk = None
            obj_id_numeric = None
            obj_repr = "Boleta Individual (Contexto Desconocido)"

        log_description = (
            f"Generada boleta individual para "
            f"{datos_empleado_actual.get('{{nombre_completo}}', f'Personal ID {detalle_sueldo.personal_externo_id}')} "
            f"(CI: {datos_empleado_actual.get('{{ci}}', 'N/A')}) "
            f"para el periodo {planilla_sueldo_base.mes}/{planilla_sueldo_base.anio}. "
            f"Plantilla utilizada: '{plantilla_boleta.nombre}' (ID: {plantilla_boleta.id})."
        )

        LogEntry.objects.create(
            actor=request.user,
            content_type=content_type_obj,
            object_pk=obj_pk,
            object_id=obj_id_numeric, 
            object_repr=obj_repr,
            action=LogEntry.Action.ACCESS,
            changes=log_description,
            remote_addr=request.META.get('REMOTE_ADDR'),
        )
        logger.info(f"Acción de generación de boleta individual registrada. Target Obj PK: {obj_pk}")
    except Exception as e_audit:
        logger.error(f"Error al registrar la acción de generación de boleta individual en auditlog: {e_audit}", exc_info=True)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    ci_filename_safe = (datos_empleado_actual.get('{{ci}}', 'SIN_CI')).replace(" ", "_").replace("/", "-")
    filename = f"boleta_{ci_filename_safe}_{planilla_sueldo_base.mes}_{planilla_sueldo_base.anio}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"' 
    
    logger.info(f"PDF ÚNICO: Boleta generada exitosamente para {filename}")
    return response