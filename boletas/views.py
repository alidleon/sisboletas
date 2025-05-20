import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import PlantillaBoleta
from .forms import PlantillaBoletaForm
from sueldos.models import PlanillaSueldo, DetalleSueldo # Importar modelos de sueldos
# Importar modelos externos si necesitas info extra no referenciada en DetalleSueldo
#from planilla.models import PrincipalPersonalExterno, PrincipalDesignacionExterno, PrincipalCargoExterno, PrincipalUnidadExterna
from django.http import HttpResponse, JsonResponse # Necesitamos HttpResponse
# ReportLab

from .utils import dibujar_boleta_en_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas_gen 
from django.views.decorators.http import require_POST, require_GET# Para asegurar que sea POST
from django.views.decorators.csrf import csrf_exempt # Temporalmente para AJAX fácil, ¡OJO!
from django.utils.html import escape # Para sanitizar
from datetime import datetime
import io
import json
import math # <--- AÑADIR ESTA LÍNEA
from decimal import Decimal
from django.http import Http404
logger = logging.getLogger(__name__)
try:
    from planilla.models import PrincipalPersonalExterno, PrincipalDesignacionExterno, PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    # Clases dummy o None si no está disponible (manejar errores después)
    PrincipalPersonalExterno, PrincipalDesignacionExterno, PrincipalCargoExterno = None, None, None
    PrincipalUnidadExterna, PrincipalSecretariaExterna = None, None
    PLANILLA_APP_AVAILABLE = False
    logger.error("GENERACION PDF: No se pudieron importar modelos de la app 'planilla'.")
 

try:
    from .utils import PLACEHOLDERS_BOLETA_DEFINICION
except ImportError:
    # Definición de fallback si no existe utils.py o la constante no está definida
    # Es mejor tenerla en utils.py o constants.py
    print("ADVERTENCIA: No se encontró PLACEHOLDERS_BOLETA_DEFINICION en utils.py, usando definición de fallback.")
    PLACEHOLDERS_BOLETA_DEFINICION = [
        {'id': '{{PLACEHOLDER_EJEMPLO}}', 'label': 'Placeholder Ejemplo'},
    ]
# from .forms import PlantillaBoletaForm # Crearemos este formulario después
import json # Para pasar datos a la plantilla JS

# Lista de placeholders (temporalmente aquí, podría ir a utils.py)
# Deberás refinar esta lista basada en los campos exactos que necesites



@login_required
def lista_plantillas_boleta(request):
    plantillas = PlantillaBoleta.objects.all().order_by('nombre')
    context = {
        'plantillas': plantillas,
        'titulo_pagina': "Plantillas de Boletas de Pago"
    }
    return render(request, 'boletas/lista_plantillas.html', context)

@login_required
def crear_editar_plantilla_boleta(request, plantilla_id=None):
    # Usaremos logger en lugar de print para mejor manejo en producción
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
                # form.save_m2m() # Si tuvieras

                logger.debug(f"Plantilla ID {plantilla_guardada.id} guardada/actualizada en BD.")
                messages.success(request, f"Plantilla '{plantilla_guardada.nombre}' guardada exitosamente.")
                logger.debug("--- FIN PROCESO POST (ÉXITO) --- Redirigiendo a lista_plantillas_boleta.")
                return redirect('lista_plantillas_boleta') # Sin namespace
            except Exception as e_save_db:
                messages.error(request, f"Error al guardar la plantilla en la base de datos: {e_save_db}")
                logger.error(f"ERROR al intentar plantilla_guardada.save(): {e_save_db}", exc_info=True)
        
        else: # form no es válido
            messages.error(request, "Por favor corrige los errores en el formulario.")
            logger.warning(f"Formulario NO ES VÁLIDO. Errores: {form.errors.as_json()}")
            logger.debug("--- FIN PROCESO POST (FORMULARIO INVÁLIDO) ---")
    
    else: # GET request
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
        'datos_diseno_json_actual': datos_diseno_para_js_str, # String JSON
        'placeholders_disponibles': PLACEHOLDERS_BOLETA_DEFINICION, # Lista Python
        'placeholders_disponibles_json': json.dumps(PLACEHOLDERS_BOLETA_DEFINICION), # String JSON
        'titulo_pagina': "Diseñar Plantilla de Boleta"
    }

    if instancia_plantilla:
        context['titulo_pagina'] = f"Editar Plantilla: {instancia_plantilla.nombre}"
    
    logger.debug(f"Renderizando template 'boletas/disenador_plantilla.html' con contexto.")
    return render(request, 'boletas/disenador_plantilla.html', context)



@login_required
def eliminar_plantilla_boleta(request, plantilla_id):
    plantilla = get_object_or_404(PlantillaBoleta, pk=plantilla_id)
    nombre_plantilla = plantilla.nombre
    if request.method == 'POST':
        plantilla.delete()
        messages.success(request, f"Plantilla '{nombre_plantilla}' eliminada exitosamente.")
        # CORRECCIÓN:
        return redirect('lista_plantillas_boleta') # Sin 'boletas:'
        # O puedes usar reverse si prefieres ser explícito:
        # return redirect(reverse('lista_plantillas_boleta'))

    context = {
        'plantilla': plantilla,
        'titulo_pagina': f"Eliminar Plantilla: {plantilla.nombre}"
        # Si el template de confirmación tuviera un botón de cancelar que usa una URL generada en la vista:
        # 'cancel_url': reverse('lista_plantillas_boleta') # Sin 'boletas:'
    }
    return render(request, 'boletas/eliminar_plantilla_confirmacion.html', context)


def ensure_string(value, default_if_none=""):
    """Asegura que el valor sea un string, o devuelve un default."""
    if value is None:
        return default_if_none
    return str(value)


# ---- Función Auxiliar para generar HTML (simplificada) ----
def ensure_string(value, default_if_none=""):
    """Asegura que el valor sea un string, o devuelve un default."""
    if value is None:
        return default_if_none
    return str(value)

def render_object_to_html(obj, sample_data):
    fabric_left = obj.get('left', 0)
    fabric_top = obj.get('top', 0)
    fabric_width_base = obj.get('width', 1)  # Ancho base del objeto Fabric
    fabric_height_base = obj.get('height', 1) # Alto base del objeto Fabric
    fabric_angle = obj.get('angle', 0)
    opacity = obj.get('opacity', 1)
    scale_x = obj.get('scaleX', 1)
    scale_y = obj.get('scaleY', 1)

    origin_x_fabric = obj.get('originX', 'left')
    origin_y_fabric = obj.get('originY', 'top')

    css_transform_origin_x = "0" # Default a 'left'
    if origin_x_fabric == 'center':
        css_transform_origin_x = "50%"
    elif origin_x_fabric == 'right':
        css_transform_origin_x = "100%"

    css_transform_origin_y = "0" # Default a 'top'
    if origin_y_fabric == 'center':
        css_transform_origin_y = "50%"
    elif origin_y_fabric == 'bottom':
        css_transform_origin_y = "100%"
    
    css_transform_origin = f"{css_transform_origin_x} {css_transform_origin_y}"

    # Para el div contenedor, usar las dimensiones base de Fabric
    # La transformación de escala se encargará del tamaño visual.
    div_width_css = fabric_width_base
    div_height_css = fabric_height_base
    
    obj_type = obj.get('type')

    # AJUSTE PARA LÍNEAS: Asegurar que el div contenedor tenga un tamaño mínimo
    if obj_type == 'line':
        stroke_w = float(obj.get('strokeWidth', 1))
        # Si el width base es casi cero (línea vertical), darle un ancho mínimo al div
        if abs(fabric_width_base) < stroke_w :
            div_width_css = stroke_w
        # Si el height base es casi cero (línea horizontal), darle un alto mínimo al div
        if abs(fabric_height_base) < stroke_w :
            div_height_css = stroke_w
        # Si ambos son muy pequeños (un punto), darles un tamaño mínimo a ambos
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
            f"white-space: pre-wrap;", # Para respetar saltos de línea en el texto
            f"padding: {ensure_string(obj.get('padding',0), '0')}px;", # Padding de Fabric
            f"box-sizing: border-box;", # El padding no debe aumentar el tamaño total
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
        # styles.append("border: 1px dotted red;") # Descomentar para ver el contenedor SVG si es necesario

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
        # object-fit: fill (estira la imagen para llenar el contenedor)
        # object-fit: contain (escala la imagen para caber manteniendo la proporción)
        # object-fit: cover (cubre el área manteniendo la proporción, puede recortar)
        styles.append("object-fit: fill;") # O 'contain' si prefieres
    else:
        content = f"[Tipo: {escape(ensure_string(obj_type, 'desconocido'))}]"
        styles.append("border: 1px dashed red;")

    final_styles_str = " ".join(s for s in styles if s is not None)

    if tag == 'img':
        return f'<img {additional_attrs_str} style="{final_styles_str}" class="{classes}">'
    else:
        return f'<div style="{final_styles_str}" class="{classes}" {additional_attrs_str}>{ensure_string(content)}</div>'

# --- Vista de Previsualización ---
@csrf_exempt # DESCOMENTAR SOLO PARA PRUEBAS AJAX SIN CONFIGURAR CSRF EN JS
@login_required
@require_POST # Asegurar que solo se acceda por POST
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
        # (Puedes hacerlos más dinámicos o leerlos de alguna configuración)
        # **IMPORTANTE**: Asegúrate que las claves coincidan EXACTAMENTE con los {{PLACEHOLDERS}}
        sample_data = {
            '{{NOMBRE_COMPLETO}}': 'ANA MARTINEZ PRUEBA',
            '{{CI_EMPLEADO}}': '9876543 CB',
            '{{CARGO_EMPLEADO}}': 'Diseñador/a Gráfico/a',
            '{{ITEM_EMPLEADO}}': '1001',
            '{{UNIDAD_EMPLEADO}}': 'DEPTO. CREATIVO',
            '{{FECHA_INGRESO_EMPLEADO}}': '01/01/2024',
            '{{MES_PAGO}}': str(datetime.now().month),
            '{{ANIO_PAGO}}': str(datetime.now().year),
            '{{HABER_BASICO}}': '6500.00',
            '{{CATEGORIA_ANTIGUEDAD}}': '250.00', # Ejemplo
            '{{TOTAL_GANADO}}': '6750.00',
            '{{RC_IVA_RETENIDO}}': '150.50',
            '{{GESTORA_PUBLICA_AFP}}': '700.10',
            '{{APORTE_SOLIDARIO}}': '67.50',
            '{{COOPERATIVA}}': '50.00',
            '{{DESCUENTO_FALTAS}}': '0.00',
            '{{DESCUENTO_MEMORANDUMS}}': '0.00',
            '{{OTROS_DESCUENTOS}}': '25.00',
            '{{TOTAL_DESCUENTOS}}': '993.10',
            '{{LIQUIDO_PAGABLE}}': '5756.90',
            '{{DIAS_TRABAJADOS}}': '30.00',
            '{{FECHA_EMISION_BOLETA}}': datetime.now().strftime('%d/%m/%Y'),
            # Añade aquí CUALQUIER otro placeholder que hayas definido
            '{{LIQUIDO_EN_PALABRAS}}': 'CINCO MIL SETECIENTOS CINCUENTA Y SEIS 90/100 BOLIVIANOS', # Necesitarás una función para esto
            '{{MES_PAGO_LETRAS}}': datetime.now().strftime('%B').upper(), # Nombre del mes actual en mayúsculas
        }
        logger.debug(f"Datos de ejemplo generados: {list(sample_data.keys())}")

        # --- Generar HTML ---
        html_objects = []
        if 'objects' in design_data and isinstance(design_data['objects'], list):
             # Importar math si no está ya importado
             import math
             for obj in design_data['objects']:
                 # No renderizar líneas de grid en la previsualización
                 if not obj.get('isGridLine'):
                      html_objects.append(render_object_to_html(obj, sample_data))
             logger.debug(f"Generados {len(html_objects)} elementos HTML para la previsualización.")
        else:
             logger.warning("El JSON de diseño recibido no tiene una lista 'objects'.")


        # Ensamblar HTML final (simulando el tamaño del canvas)
        # Usamos las mismas dimensiones que el canvas
        canvas_width = 595
        canvas_height = 842
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
    


# --- NUEVA VISTA: Generación de PDF ---
@login_required
def generar_pdf_boletas_por_planilla(request, planilla_sueldo_id):
    logger.info(f"Solicitud para generar PDF para PlanillaSueldo ID: {planilla_sueldo_id}")

    # --- 1. Obtener Planilla de Sueldos y Detalles ---
    try:
        # Usamos select_related para optimizar el acceso a usuario_creacion si lo necesitaras
        planilla_sueldo = PlanillaSueldo.objects.select_related('usuario_creacion').get(pk=planilla_sueldo_id)
        logger.debug(f"Planilla de sueldos encontrada: {planilla_sueldo}")

        # Obtener TODOS los detalles de sueldo para esta planilla
        # Usamos select_related para traer los datos del personal externo en una sola consulta
        # ¡OJO! Esto solo funciona si la relación ForeignKey está definida correctamente y
        # la base de datos externa está configurada en settings.py para permitir consultas JOIN.
        # Si no funciona, quitamos select_related y hacemos consultas individuales después.
        detalles_sueldo = DetalleSueldo.objects.filter(planilla_sueldo=planilla_sueldo) #.select_related('personal_externo') <--- Quitar si da error cross-database

        if not detalles_sueldo.exists():
            logger.warning(f"No se encontraron detalles de sueldo para la PlanillaSueldo ID: {planilla_sueldo_id}")
            messages.warning(request, f"La planilla de sueldos {planilla_sueldo.mes}/{planilla_sueldo.anio} ({planilla_sueldo.get_tipo_display()}) no tiene empleados cargados.")
            # Redirigir a la lista de planillas de sueldo (necesitarás esa URL)
            # return redirect('lista_planillas_sueldo') # Ajusta el nombre de la URL
            return HttpResponse("No hay detalles para generar.", status=404) # O un error simple

        logger.info(f"Encontrados {detalles_sueldo.count()} detalles de sueldo para procesar.")

    except PlanillaSueldo.DoesNotExist:
        logger.error(f"PlanillaSueldo con ID={planilla_sueldo_id} no encontrada.")
        raise Http404(f"Planilla de Sueldos no encontrada.")
    except Exception as e:
        logger.error(f"Error obteniendo datos de PlanillaSueldo/DetalleSueldo: {e}", exc_info=True)
        messages.error(request, "Error al obtener los datos de la planilla de sueldos.")
        # return redirect('lista_planillas_sueldo')
        return HttpResponse("Error interno al obtener datos.", status=500)


    # --- 2. Obtener la Plantilla de Boleta a Usar ---
    try:
        # Buscar la plantilla marcada como predeterminada, o la primera si no hay predeterminada
        plantilla_boleta = PlantillaBoleta.objects.filter(es_predeterminada=True).first()
        if not plantilla_boleta:
            plantilla_boleta = PlantillaBoleta.objects.first() # Fallback a la primera que encuentre

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
    # Crear el canvas de ReportLab. Usar A4 por defecto.
    # El origen (0,0) en ReportLab está en la esquina INFERIOR izquierda.
    p = pdf_canvas_gen.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4 # Obtener dimensiones en puntos

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
                    # Si select_related funcionó antes, ya estaría cargado
                    # personal_ext = detalle.personal_externo
                    # Si no, hacer consulta individual:
                    personal_ext = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
                    datos_empleado_actual['{{nombre}}'] = personal_ext.nombre or ''
                    datos_empleado_actual['{{apellido_paterno}}'] = personal_ext.apellido_paterno or ''
                    datos_empleado_actual['{{apellido_materno}}'] = personal_ext.apellido_materno or ''
                    datos_empleado_actual['{{nombre_completo}}'] = personal_ext.nombre_completo # Usar la property
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
                    # Buscar la designación activa para el tipo y periodo de la planilla
                    # Esto podría necesitar una lógica más compleja si el estado cambia a mitad de mes
                    # Por ahora, buscamos la ACTIVA con el mismo TIPO
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
                                estado='ACTIVO', # Podría necesitar ser más flexible que solo ACTIVO
                                tipo_designacion=tipo_designacion_busqueda
                            ).order_by('-fecha_ingreso').first() # La más reciente activa

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
                        # ... etc para otros campos de designación ...
                        errores_empleados.append(f"ID {detalle.personal_externo_id}: Designación no encontrada.")

                except Exception as e_desig:
                     logger.error(f"Error obteniendo datos de designación para ID {detalle.personal_externo_id}: {e_desig}")
                     errores_empleados.append(f"ID {detalle.personal_externo_id}: Error datos designación.")
                     # Llenar con vacíos para evitar errores
                     # ...
            else:
                 # Manejar caso si planilla.models no está disponible
                 errores_empleados.append(f"ID {detalle.personal_externo_id}: Módulo Planilla no disponible.")
                 continue


            # --- Añadir datos de PlanillaSueldo ---
            datos_empleado_actual['{{planilla_mes}}'] = str(planilla_sueldo.mes)
            datos_empleado_actual['{{planilla_anio}}'] = str(planilla_sueldo.anio)
            datos_empleado_actual['{{planilla_tipo}}'] = planilla_sueldo.tipo
            datos_empleado_actual['{{planilla_tipo_display}}'] = planilla_sueldo.get_tipo_display()


            # --- Añadir datos de DetalleSueldo (formateados como string) ---
            # Usar locale para formato de número si es necesario o Decimal.quantize
            from decimal import Decimal, ROUND_HALF_UP
            quantizer = Decimal('0.01') # Para redondear a 2 decimales
            
            datos_empleado_actual['{{dias_trab}}'] = str((detalle.dias_trab or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{haber_basico}}'] = str((detalle.haber_basico or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
            datos_empleado_actual['{{categoria}}'] = str((detalle.categoria or Decimal(0)).quantize(quantizer, ROUND_HALF_UP))
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
            # Necesitarás una función para convertir número a literal (num2words o similar)
            # from num2words import num2words
            try:
                 monto = detalle.liquido_pagable or Decimal(0)
                 entero = int(monto)
                 decimal_part = int((monto - entero) * 100)
                 # literal = num2words(entero, lang='es').upper() + f" {decimal_part:02d}/100 BOLIVIANOS" # Instalar num2words
                 literal = f"LITERAL DE {monto:.2f} (PENDIENTE)" # Placeholder temporal
            except Exception as e_literal:
                 logger.warning(f"Error generando literal para {monto}: {e_literal}")
                 literal = "LITERAL PENDIENTE"
            datos_empleado_actual['{{literal_liquido}}'] = literal

            try:
                # Requiere configurar locale en el sistema o usar calendar
                import calendar
                # Asegúrate que planilla_sueldo.mes es un entero 1-12
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
            # ¿Continuar con el siguiente o detener todo? Por ahora continuamos.

    # --- 5. Finalizar y Devolver PDF ---
    if num_boletas_generadas > 0:
        logger.info(f"Generación PDF completada. Boletas generadas: {num_boletas_generadas}. Errores: {len(errores_empleados)}.")
        p.save() # Guardar el contenido PDF en el buffer

        buffer.seek(0) # Volver al inicio del buffer para la respuesta
        response = HttpResponse(buffer, content_type='application/pdf')
        # Nombre de archivo sugerido
        filename = f"boletas_{planilla_sueldo.tipo}_{planilla_sueldo.mes}_{planilla_sueldo.anio}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"' # inline para ver en navegador, attachment para descargar
        return response
    else:
        logger.error("No se generó ninguna boleta exitosamente.")
        messages.error(request, "No se pudo generar ninguna boleta. Revise los logs para más detalles.")
        if errores_empleados:
            messages.warning(request, f"Errores encontrados durante la generación: {'; '.join(errores_empleados[:3])}{'...' if len(errores_empleados)>3 else ''}")
        # return redirect('lista_planillas_sueldo') # Ajustar URL
        return HttpResponse("Error: No se generaron boletas.", status=500)