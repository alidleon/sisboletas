import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
import os
from django.conf import settings

from django.urls import reverse # <--- Importar reverse
from urllib.parse import urlencode # <--- Importar urlencode

from datetime import date
from django.contrib import messages
from .forms import DetalleBonoTeForm
from .forms import PlanillaForm  # Necesitas crear un formulario para editar la planilla
from datetime import datetime
from django.core.exceptions import ValidationError
from .models import PrincipalPersonal # ¡Importa el nuevo modelo!
from decimal import Decimal, InvalidOperation
from calendar import month_name
from openpyxl.drawing.image import Image

from django.db import transaction, IntegrityError       # Para transacciones y manejo de errores BD
from django.db.models import Q   

from .models import (
    Planilla,
    DetalleBonoTe,
    PrincipalDesignacionExterno,
    PrincipalPersonalExterno, # Ahora necesitamos importar este
    PrincipalCargoExterno,      # Y este si accedes a su nombre directamente
    PrincipalUnidadExterna,      # <--- Modelo de Unidad
    PrincipalSecretariaExterna # <--- Modelo de Secretaría
)


from .utils import get_processed_planilla_details
try:
    import openpyxl
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    # Importar Image aquí; su uso real se manejará con try-except
    from openpyxl.drawing.image import Image
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    # Clases dummy si openpyxl falta, para evitar NameErrors más adelante
    class Font: pass
    class Alignment: pass
    class PatternFill: pass
    class Border: pass
    class Side: pass
    class Image: pass # La clase Image dummy no funcionará, pero evita el NameError
logger = logging.getLogger(__name__)
# ---------------------------------
    


@login_required
def seleccionar_tipo_planilla(request):
    # Usa los choices actualizados del modelo
    tipos_disponibles = Planilla.TIPO_CHOICES
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        # Valida contra las claves internas ('planta', 'contrato', 'consultor')
        tipos_validos_keys = dict(tipos_disponibles).keys()
        if tipo in tipos_validos_keys:
            return redirect('crear_planilla', tipo=tipo) # Redirige a la vista de creación
        else:
            messages.error(request, 'Seleccione un tipo de planilla válido.')
            # Vuelve a mostrar la selección con el error
            return render(request, 'planillas/seleccionar_tipo_planilla.html', {'tipos_planilla': tipos_disponibles})
    else: # GET
        # Muestra el formulario de selección
        context = {
            'tipos_planilla': tipos_disponibles,
        }
        return render(request, 'planillas/seleccionar_tipo_planilla.html', context)



# ----------------------------------------------------------------

@login_required
def crear_planilla(request, tipo):
    # Mapa de tipos Django a tipos de la BD externa
    EXTERNAL_TYPE_MAP = {
        'planta': 'ASEGURADO',
        'contrato': 'CONTRATO',
        'consultor': 'CONSULTOR EN LINEA',
    }

    # Validar que el tipo sea uno de los permitidos
    if tipo not in EXTERNAL_TYPE_MAP.keys():
        messages.error(request, f"Tipo de planilla '{tipo}' no es válido.")
        return redirect('seleccionar_tipo_planilla') # Asume URL/vista existe

    # Obtener el tipo externo a filtrar
    target_external_type = EXTERNAL_TYPE_MAP[tipo]

    # Siempre usamos DetalleBonoTe para guardar (según solicitud)
    target_detail_model = DetalleBonoTe
    logger.warning(f"Advertencia: Planilla '{tipo}', detalles se guardarán en DetalleBonoTe.")

    # Para el dropdown opcional (si se usa en la plantilla)
    try:
        planillas_para_copiar = Planilla.objects.filter(tipo=tipo).order_by('-anio', '-mes')
    except Exception as e_qs:
         logger.error(f"Error obteniendo 'planillas_para_copiar' para {tipo}: {e_qs}", exc_info=True)
         messages.error(request, "Error interno preparando formulario.")
         return redirect('lista_planillas') # O a un dashboard

    if request.method == 'POST':
        planilla_form = PlanillaForm(request.POST)

        if planilla_form.is_valid():
            mes = planilla_form.cleaned_data['mes']
            anio = planilla_form.cleaned_data['anio']
            dias_habiles_planilla = planilla_form.cleaned_data['dias_habiles']

            # Validación Duplicados
            if Planilla.objects.filter(mes=mes, anio=anio, tipo=tipo).exists():
                messages.warning(f"¡Atención! Ya existe planilla '{dict(Planilla.TIPO_CHOICES).get(tipo)}' para {mes}/{anio}.")
                context_duplicado = {
                    'planilla_form': planilla_form, 'tipo': tipo,
                    'planillas_para_copiar': planillas_para_copiar, 'error_duplicado': True
                }
                try:
                    return render(request, 'planillas/crear_planilla.html', context_duplicado)
                except Exception as e_render_dup:
                     logger.error(f"Error RENDER (duplicado): {e_render_dup}", exc_info=True)
                     return HttpResponse("Error al renderizar página (dup).", status=500)

            # Iniciar Proceso de Creación
            try:
                with transaction.atomic(using='default'):
                    # 1. Crear Planilla (Cabecera)
                    planilla = planilla_form.save(commit=False)
                    planilla.usuario_elaboracion = request.user
                    planilla.tipo = tipo
                    planilla.save()
                    logger.info(f"Planilla ID {planilla.id} (Tipo: {planilla.get_tipo_display()}, Periodo: {mes}/{anio}) creada.")

                    # 2. Consultar Personal Externo
                    logger.info(f"Consultando 'personas_db' para Planilla ID {planilla.id}...")
                    try:
                        logger.debug(f"Buscando Tipo Externo: '{target_external_type}'")
                        consulta_externa = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('personal', 'cargo')
                        logger.debug(f"Consulta base. Count inicial (aprox): {consulta_externa.count()}")

                        # A. FILTRO POR TIPO DE DESIGNACIÓN
                        if hasattr(PrincipalDesignacionExterno, 'tipo_designacion'):
                            consulta_externa = consulta_externa.filter(tipo_designacion=target_external_type)
                            logger.debug(f"Count después filtro TIPO (aprox): {consulta_externa.count()}")
                        else:
                            logger.error("¡¡MODELO SIN 'tipo_designacion'!! No se puede filtrar.")
                            raise AttributeError("Falta campo 'tipo_designacion' en modelo externo.")

                        # B. FILTRO POR ACTIVIDAD (Implementado con Estado='ACTIVO')
                        estado_activo_valor = 'ACTIVO' # Valor que indica actividad
                        if hasattr(PrincipalDesignacionExterno, 'estado'):
                            consulta_externa = consulta_externa.filter(estado=estado_activo_valor)
                            # Log después de aplicar el filtro de estado
                            logger.info(f"Filtro ACTIVIDAD aplicado: estado = '{estado_activo_valor}'. Count(aprox): {consulta_externa.count()}")
                        else:
                            logger.error("¡¡MODELO SIN CAMPO 'estado'!! No se puede filtrar por actividad.")
                            raise AttributeError("Falta campo 'estado' en PrincipalDesignacionExterno.")
                        # ---------------------------------------------

                        # Ordenar
                        consulta_externa = consulta_externa.order_by('personal__apellido_paterno', 'personal__apellido_materno', 'personal__nombre')
                        logger.debug("Orden aplicado.")

                        # Log SQL (Opcional pero útil)
                        # try:
                        #     logger.debug(f"SQL (aprox): {str(consulta_externa.query)}")
                        # except Exception: pass

                        # Ejecutar consulta final
                        designaciones_externas_filtradas = list(consulta_externa)
                        logger.info(f"Consulta final ejecutada (CON filtro actividad). Encontradas: {len(designaciones_externas_filtradas)}")

                        # Log para verificar IDs encontrados (Opcional)
                        # if designaciones_externas_filtradas:
                        #     ids_encontrados = [d.id for d in designaciones_externas_filtradas[:5]]
                        #     logger.debug(f"Primeros IDs de designación encontrados: {ids_encontrados}")

                    except AttributeError as attr_err:
                        # Error si falta campo 'tipo_designacion' o 'estado'
                        logger.error(f"Error de atributo en consulta externa: {attr_err}", exc_info=True)
                        messages.error(request, f"Error de configuración del modelo ({attr_err}). Contacte al administrador.")
                        raise Exception(f"Error de Configuración: {attr_err}") # Forzar salida del with/rollback
                    except Exception as e_ext:
                        logger.error(f"Error CRÍTICO consultando 'personas_db': {e_ext}", exc_info=True)
                        messages.error(request, f"Se creó cabecera (ID:{planilla.id}), pero ERROR al consultar personal: {e_ext}. Detalles NO generados.")
                        raise Exception("Error irrecuperable en consulta externa") # Forzar salida del with/rollback

                    # 3. Crear Detalles (SIEMPRE en DetalleBonoTe)
                    detalles_a_crear = []
                    personas_procesadas = set()
                    if not designaciones_externas_filtradas:
                        # El log ya indicó 0 encontradas, aquí solo mensaje al usuario
                        messages.warning(request, f"Se creó cabecera, pero no se encontró personal ACTIVO para tipo '{planilla.get_tipo_display()}'.")
                    else:
                        logger.info(f"Preparando {len(designaciones_externas_filtradas)} registros DetalleBonoTe...")
                        for designacion in designaciones_externas_filtradas:
                            if designacion.personal and designacion.personal_id not in personas_procesadas:
                                detalle = DetalleBonoTe(
                                    id_planilla=planilla,
                                    personal_externo_id=designacion.personal.id,
                                    mes=planilla.mes,
                                    # Otros campos DetalleBonoTe usarán su default
                                )
                                detalles_a_crear.append(detalle)
                                personas_procesadas.add(designacion.personal_id)
                            elif not designacion.personal:
                                 logger.warning(f"Designación ID {designacion.id} sin personal. Se omite.")

                        if detalles_a_crear:
                            try:
                                DetalleBonoTe.objects.bulk_create(detalles_a_crear)
                                logger.info(f"Creados {len(detalles_a_crear)} registros DetalleBonoTe para Planilla {planilla.id}.")
                                messages.success(request, f"Planilla {planilla.get_tipo_display()} {mes}/{anio} creada con {len(detalles_a_crear)} registros asociados (en DetalleBonoTe).")
                            except IntegrityError as e_bulk:
                                logger.error(f"Error integridad ({e_bulk}) al crear DetalleBonoTe.", exc_info=True)
                                messages.error(request, f"Se creó cabecera, ERROR al guardar detalles ({e_bulk}).")
                                raise Exception("Error irrecuperable en bulk_create") # Forzar salida del with/rollback
                        else:
                             # Esto podría pasar si todas las designaciones encontradas no tenían personal asociado
                             logger.warning(f"Aunque se encontraron designaciones, no se prepararon detalles DetalleBonoTe.")
                             messages.warning(request, "Se creó cabecera, pero no se preparó ningún detalle individual (verificar logs).")

                # Si se llega aquí, la transacción fue exitosa
                return redirect('lista_planillas') # Redirigir a la lista

            except Exception as e_proc:
                 # Captura errores de atributo, consulta externa, bulk_create o cualquier otro dentro del try
                 logger.error(f"Error procesando creación planilla {tipo} {mes}/{anio}: {e_proc}", exc_info=True)
                 # Mensaje de error ya debería haberse puesto antes
                 if not messages.get_messages(request):
                      messages.error(request, f"Ocurrió un error inesperado durante la creación: {e_proc}")
                 # La transacción hizo rollback si la excepción ocurrió dentro del 'with'
                 return redirect('lista_planillas') # Ir a la lista después de un error

        else: # Formulario POST NO válido
            logger.warning(f"Formulario inválido: {planilla_form.errors.as_json()}")
            messages.error(request, "Formulario contiene errores. Corrígelos.")
            # Cae al render final

    else: # GET
        planilla_form = PlanillaForm()

    # --- Render Final (GET o POST inválido) ---
    context_final = {
        'planilla_form': planilla_form,
        'tipo': tipo,
        'planillas_para_copiar': planillas_para_copiar
    }
    # logger.debug(f"Renderizando plantilla crear_planilla. Contexto: {context_final.keys()}") # Log opcional
    try:
        return render(request, 'planillas/crear_planilla.html', context_final)
    except Exception as e_render_final:
         logger.error(f"Error RENDER (final) plantilla crear_planilla: {e_render_final}", exc_info=True)
         return HttpResponse("Error crítico al renderizar página de creación.", status=500)


############################################################
@login_required
def lista_planillas(request):
    planillas = Planilla.objects.all()
    return render(request, 'planillas/lista_planillas.html', {'planillas': planillas})
# Función para crear los registros DetalleBonoTe (ejemplo)
def crear_detalle_bono_te(planilla):
    """
    Función de ejemplo para crear los registros DetalleBonoTe asociados a una planilla.
    Esta lógica debe ser adaptada a tus necesidades específicas.
    """
    # TODO: Obtener la lista de empleados que corresponden al tipo de planilla
    # TODO: Iterar sobre la lista de empleados y crear un registro DetalleBonoTe para cada uno.
    pass #Reemplaza este pass con la lógica



#---------------------------------------------------------------
#lista de bonote
def lista_bono_te(request):
    detalles_bono_te = DetalleBonoTe.objects.all() # Obtiene todos los DetalleBonoTe
    return render(request, 'planillas/lista_bono_te.html', {'detalles_bono_te': detalles_bono_te})

#edtiar y borrar bonote
# --- planilla/views.py ---

# ... (otras importaciones y vistas) ...


@login_required
def editar_bono_te(request, detalle_id):
    # Obtener el DetalleBonoTe y su Planilla asociada (BD 'default')
    detalle_bono_te = get_object_or_404(
        DetalleBonoTe.objects.select_related('id_planilla'),
        pk=detalle_id
    )
    planilla = detalle_bono_te.id_planilla
    dias_habiles_planilla = planilla.dias_habiles if planilla else None

    # --- INICIO: Obtener datos externos para mostrar (BD 'personas_db') ---
    persona_externa = None
    item_externo = 'N/A'
    cargo_externo = 'N/A'
    personal_externo_id = detalle_bono_te.personal_externo_id

    if personal_externo_id:
        # 1. Obtener datos de la persona
        try:
            persona_externa = PrincipalPersonalExterno.objects.using('personas_db').get(pk=personal_externo_id)
            logger.debug(f"Persona externa ID {personal_externo_id} encontrada: {persona_externa}")
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"No se encontró PrincipalPersonalExterno con ID {personal_externo_id} en 'personas_db' para DetalleBonoTe ID {detalle_id}")
            persona_externa = None # Asegurarse que es None si no se encuentra
        except Exception as e_pers:
            logger.error(f"Error consultando PrincipalPersonalExterno ID {personal_externo_id} en 'personas_db': {e_pers}", exc_info=True)
            persona_externa = None

        # 2. Obtener datos de la designación (Item, Cargo) - ¡APLICAR MISMOS FILTROS QUE EN CREAR/VER!
        try:
            # Construir la consulta base
            consulta_desig = PrincipalDesignacionExterno.objects.using('personas_db') \
                .filter(personal_id=personal_externo_id) \
                .select_related('cargo') \
                .order_by('-id') # O por fecha si tienes
            

            # ----- !!!!! APLICA AQUÍ LOS MISMOS FILTROS DE ACTIVIDAD/TIPO !!!!! -----
            #       QUE USASTE EN LA VISTA 'crear_planilla' y 'ver_detalles_bono_te'.
            #       Ejemplo (DEBES ADAPTARLO):
            # consulta_desig = consulta_desig.filter(estado='VIGENTE', ...)
            # -----------------------------------------------------------------------

            # Intentar obtener LA designación relevante (puede haber varias históricas)
            # Lo ideal es que los filtros de arriba dejen solo una. Si no, tomamos la primera (o la más reciente si ordenas)
            designacion = consulta_desig.first() # O .latest('fecha_inicio') si tienes fechas

            if designacion:
                logger.debug(f"Designación externa encontrada para Persona ID {personal_externo_id}: Item {designacion.item}, Cargo ID {designacion.cargo_id}")
                item_externo = designacion.item if designacion.item is not None else 'N/A'
                cargo_externo = designacion.cargo.nombre_cargo if designacion.cargo else 'N/A'
            else:
                 logger.warning(f"No se encontró una designación externa *relevante* (según filtros) para Persona ID {personal_externo_id} en 'personas_db'.")

        except Exception as e_desig:
            logger.error(f"Error consultando PrincipalDesignacionExterno para Persona ID {personal_externo_id} en 'personas_db': {e_desig}", exc_info=True)
            # Los valores por defecto 'N/A' se mantendrán

    # --- FIN: Obtener datos externos ---

    if request.method == 'POST':
        form = DetalleBonoTeForm(request.POST, instance=detalle_bono_te)
        if form.is_valid():
            form.save()
            messages.success(request, 'Detalle Bono TE editado correctamente.')
            redirect_secretaria = request.POST.get('redirect_secretaria', '')
            redirect_unidad = request.POST.get('redirect_unidad', '')
            redirect_q = request.POST.get('redirect_q', '')
            base_url = reverse('ver_detalles_bono_te', kwargs={'planilla_id': planilla.id})
            params = {}
            if redirect_secretaria:
                params['secretaria'] = redirect_secretaria
            if redirect_unidad:
                params['unidad'] = redirect_unidad
            if redirect_q: params['q'] = redirect_q

            if params: params['buscar'] = 'true'
            redirect_url = f"{base_url}?{urlencode(params)}" if params else base_url

            logger.debug(f"Redirigiendo a: {redirect_url}")
            return redirect(redirect_url)


        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
            # Se renderizará el template con el form inválido y los datos externos ya cargados
    else: # Método GET
        form = DetalleBonoTeForm(
            instance=detalle_bono_te,
            initial={'dias_habiles': dias_habiles_planilla}
        )

    context = {
        'form': form,
        'detalle_bono_te': detalle_bono_te,
        'dias_habiles': dias_habiles_planilla,
        # --- Pasar datos externos al contexto ---
        'persona_externa': persona_externa, # El objeto completo (o None)
        'item_externo': item_externo,
        'cargo_externo': cargo_externo,
        # ----------------------------------------
    }
    return render(request, 'planillas/editar_bono_te.html', context)

# ... (resto de las vistas) ...



@login_required
def borrar_bono_te(request, detalle_id):
    detalle_bono_te = get_object_or_404(DetalleBonoTe, pk=detalle_id)
    if request.method == 'POST':
        detalle_bono_te.delete()
        messages.success(request, 'Detalle Bono TE borrado correctamente.')
        return redirect('lista_bono_te')  # Redirige al listado
    return render(request, 'planillas/borrar_bono_te.html', {'detalle_bono_te': detalle_bono_te}) # Confirma el borrado






#vistas
#llenar editar borrar bonote



@login_required
def editar_planilla(request, planilla_id):
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    if request.method == 'POST':
        form = PlanillaForm(request.POST, instance=planilla)  # Usamos instance para editar
        if form.is_valid():
            form.save()
            messages.success(request, 'Planilla editada correctamente.')
            return redirect('lista_planillas')  # Redirige al listado
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = PlanillaForm(instance=planilla)  # Mostramos el formulario con los datos actuales
    return render(request, 'planillas/editar_planilla.html', {'form': form, 'planilla': planilla})

@login_required
def borrar_planilla(request, planilla_id):
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    if request.method == 'POST':
        planilla.delete()
        messages.success(request, 'Planilla borrada correctamente.')
        return redirect('lista_planillas')  # Redirige al listado
    return render(request, 'planillas/borrar_planilla.html', {'planilla': planilla})  # Confirma el borrado



################################################################

# Importar la función auxiliar


@login_required
def ver_detalles_bono_te(request, planilla_id):
    """
    Vista que usa la función auxiliar para obtener datos y renderizar la plantilla.
    """
    logger.debug(f"Vista ver_detalles_bono_te llamada para planilla_id={planilla_id}")

    try:
        # Llamar a la función auxiliar para obtener todos los datos procesados
        processed_data = get_processed_planilla_details(request, planilla_id)

        # Verificar si hubo un error grave reportado por la función auxiliar
        if processed_data.get('error_message'):
            # Mostrar el mensaje de error al usuario
            messages.error(request, processed_data['error_message'])
            # Si el error fue que no se encontró la planilla, redirigir
            if not processed_data.get('planilla'):
                 logger.warning(f"Planilla {planilla_id} no encontrada por util, redirigiendo.")
                 return redirect('lista_planillas') # O a donde sea apropiado

        # Preparar el contexto para la plantilla usando los datos devueltos
        context = {
            'planilla': processed_data.get('planilla'),
            'all_secretarias': processed_data.get('all_secretarias'),
            'unidades_for_select': processed_data.get('unidades_for_select'),
            'selected_secretaria_id': processed_data.get('selected_secretaria_id'),
            'selected_unidad_id': processed_data.get('selected_unidad_id'),
            'detalles_bono_te': processed_data.get('detalles_enriquecidos'), # Nombre usado en plantilla
            'search_active': processed_data.get('search_active')
        }

        # Renderizar la plantilla con el contexto
        return render(request, 'planillas/ver_detalles_bono_te.html', context)

    except Exception as e_view:
        # Capturar cualquier error inesperado que ocurra EN LA VISTA (no en la util)
        logger.error(f"Error inesperado en vista ver_detalles_bono_te para ID {planilla_id}: {e_view}", exc_info=True)
        messages.error(request, "Ocurrió un error inesperado al procesar la solicitud.")
        return redirect('lista_planillas') # Redirigir a lugar seguro
    
#---------------------------------------------

# --- NUEVA VISTA PARA EXPORTAR A XLSX ---

@login_required
def exportar_planilla_xlsx(request, planilla_id):
    """
    Genera un archivo XLSX con encabezado institucional (A1:E3), logo (Fila 1),
    encabezado de planilla (desde Fila 4), datos (desde Fila 9).
    """
    # 1. Verificar openpyxl
    if not OPENPYXL_AVAILABLE:
        messages.error(request, "La funcionalidad de exportación a Excel no está disponible (falta 'openpyxl').")
        return redirect('ver_detalles_bono_te', planilla_id=planilla_id)

    logger.info(f"Solicitud de exportación XLSX para Planilla ID {planilla_id}")

    # 2. Obtener datos procesados
    try:
        processed_data = get_processed_planilla_details(request, planilla_id)
    except Exception as e_get_data:
        logger.error(f"Error crítico obteniendo datos para exportar Planilla {planilla_id}: {e_get_data}", exc_info=True)
        messages.error(request, f"No se pudieron obtener los datos para exportar: {e_get_data}")
        return redirect('lista_planillas')

    # 3. Validar datos obtenidos
    if processed_data.get('error_message') and not processed_data.get('detalles_enriquecidos'):
        messages.error(request, f"Error al preparar datos para exportar: {processed_data['error_message']}")
        return redirect('ver_detalles_bono_te', planilla_id=planilla_id)

    planilla = processed_data.get('planilla')
    detalles_filtrados = processed_data.get('detalles_enriquecidos')
    selected_unidad_id = processed_data.get('selected_unidad_id')
    selected_secretaria_id = processed_data.get('selected_secretaria_id')

    if not planilla:
         messages.error(request, "No se pudo encontrar la información de la planilla para exportar.")
         return redirect('lista_planillas')

    if not detalles_filtrados:
         # Advertir si no hay detalles, pero continuar para generar cabecera
         if selected_unidad_id: logger.warning(...); messages.warning(...)
         else: logger.warning(...); messages.warning(...)
         # No retornamos, generamos el archivo vacío

    # --- 4. Crear el archivo XLSX ---
    try:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = f"BonoTE_{planilla.mes}_{planilla.anio}"[:31]

        # --- 5. Definir Estilos ---
        inst_header_bold_font = Font(name='Calibri', size=9, bold=True)
        title_font = Font(name='Calibri', size=14, bold=True, color='FF000080')
        subtitle_font = Font(name='Calibri', size=12, bold=True)
        value_font = Font(name='Calibri', size=10)
        header_font = Font(bold=True, name='Calibri', size=10, color='FFFFFFFF')
        wrap_left_alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
        centered_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left_alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        right_alignment = Alignment(horizontal='right', vertical='center')
        decimal_format = '#,##0.00'; integer_format = '#,##0'
        header_fill = PatternFill(start_color='FF000080', end_color='FF000080', fill_type='solid')
        thin_border_side = Side(border_style="thin", color="FF000000")
        header_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

        # --- 6. Definir Encabezados de Datos y Fila de Inicio ---
        data_headers = [ # Tu lista de encabezados
            'Nro.', 'Item', 'CI', 'Nombre Completo', 'Cargo', 'Mes', 'Días Háb.',
            'Faltas', 'Vacac.', 'Viajes', 'B.Médicas', 'PCGH', 'PSGH', 'P.Excep',
            'Asuetos', 'PCGH Emb/Enf', 'D.No Pag.', 'D. Pag.', 'Total Ganado (Bono)',
            'Desc.', 'Líquido Pag. (Bono)'
        ]
        num_data_columns = len(data_headers)
        # Fila donde empiezan los encabezados 'Nro.', 'Item', etc.
        start_data_row = 8 # (A1:E3) + (Titulo 4) + (Periodo 5) + (Filtro 6) + (Blanco 7) = Inicio 8

        # --- 7. Escribir Encabezado Personalizado (Texto e Imagen) ---

        # 7.a Encabezado Institucional (Combinando A1:E3)
        institucional_text = (
            "GOBIERNO AUTONOMO DEPARTAMENTAL DE POTOSI\n"
            "SECRETARIA DEPTAL. ADMINISTRATIVA FINANCIERA\n"
            "UNIDAD DE RECURSOS HUMANOS"
        )
        num_cols_to_merge_header = 5 # Ajusta el ancho si es necesario
        sheet.merge_cells(start_row=1, start_column=1, end_row=3, end_column=num_cols_to_merge_header)
        # Escribir valor y aplicar estilo a la celda superior izquierda (A1)
        inst_cell = sheet.cell(row=1, column=1, value=institucional_text)
        inst_cell.font = inst_header_bold_font
        inst_cell.alignment = wrap_left_alignment

        # 7.b Añadir Imagen (Logo)
        image_path = None
        try: # Encontrar RUTA
            logo_filename = 'gadp.png'
            potential_path = os.path.join(settings.BASE_DIR, 'static', 'img', logo_filename)
            if os.path.exists(potential_path): image_path = potential_path
            else: logger.warning(f"Logo no encontrado en ruta: {potential_path}")
        except Exception as e_path: logger.error(f"Error determinando ruta del logo: {e_path}")

        if image_path:
            try: # CARGAR Y AÑADIR
                img = Image(image_path)
                # Ajustar tamaño (usa los valores que te funcionaron)
                img.height = 110
                img.width = 100
                # Ancla en la última columna, Fila 1
                anchor_col_letter = get_column_letter(num_data_columns)
                anchor_cell = f'{anchor_col_letter}1' # Anclar en Fila 1
                sheet.add_image(img, anchor_cell)
                logger.info(f"Imagen '{logo_filename}' añadida anclada en {anchor_cell}")
            except Exception as e_img: # Manejo de errores de imagen
                 logger.error(f"Error al procesar o añadir la imagen: {e_img}", exc_info=True)
                 messages.warning(request, f"No se pudo añadir el logo al Excel (Error: {type(e_img).__name__}).")
        # else: (si no se encontró la ruta)
             # messages.warning(request, "Archivo de logo no encontrado, no se incluirá.")

        # 7.c Encabezado de Planilla (Título, Periodo, Filtros) - DESPLAZADOS
        # Fila 4: Título Principal
        sheet.merge_cells(start_row=4, start_column=1, end_row=4, end_column=num_data_columns)
        # *** ASEGURAR column=1 ***
        title_cell = sheet.cell(row=4, column=1, value="PLANILLA DE PAGO BONO TÉ DE REFRIGERIO")
        title_cell.font = title_font
        title_cell.alignment = centered_alignment

        # Fila 5: Periodo
        sheet.merge_cells(start_row=5, start_column=1, end_row=5, end_column=num_data_columns)
        try: nombre_mes = month_name[planilla.mes].upper()
        except: nombre_mes = f"MES {planilla.mes}"
        # *** ASEGURAR column=1 ***
        periodo_cell = sheet.cell(row=5, column=1, value=f"CORRESPONDIENTE AL MES DE {nombre_mes} DE {planilla.anio}")
        periodo_cell.font = subtitle_font
        periodo_cell.alignment = centered_alignment

        # Fila 6: Filtros Aplicados
        sheet.merge_cells(start_row=6, start_column=1, end_row=6, end_column=num_data_columns)
        # Lógica para obtener filter_info
        filter_info = f"Tipo Planilla: {planilla.get_tipo_display()}"
        secretaria_nombre = "Todas"; unidad_nombre = "Todas"
        # ... (obtener nombres secretaria/unidad) ...
        if selected_secretaria_id:
            try: secretaria = PrincipalSecretariaExterna.objects.using('personas_db').get(pk=selected_secretaria_id); secretaria_nombre = secretaria.nombre_secretaria or f"ID {selected_secretaria_id}"
            except: secretaria_nombre = f"ID {selected_secretaria_id} (?)"
        if selected_unidad_id:
            try: unidad = PrincipalUnidadExterna.objects.using('personas_db').get(pk=selected_unidad_id); unidad_nombre = unidad.nombre_unidad or f"ID {selected_unidad_id}"
            except: unidad_nombre = f"ID {selected_unidad_id} (?)"
            filter_info += f" | Secretaría: {secretaria_nombre} | Unidad: {unidad_nombre}"
        elif selected_secretaria_id: filter_info += f" | Secretaría: {secretaria_nombre}"
        # *** ASEGURAR column=1 ***
        filter_cell = sheet.cell(row=6, column=1, value=filter_info)
        filter_cell.font = value_font
        filter_cell.alignment = left_alignment

        # Fila 7: Fila en blanco (implícita)

        # --- 8. Escribir Encabezados de Datos (Ahora en Fila 8) ---
        for col_num, header_title in enumerate(data_headers, 1):
            cell = sheet.cell(row=start_data_row, column=col_num, value=header_title)
            cell.font = header_font
            cell.alignment = centered_alignment
            cell.fill = header_fill
            cell.border = header_border

        # --- 9. Escribir Filas de Datos (Ahora desde Fila 9) ---
        def safe_decimal(value, default=Decimal('0')):
            if value is None: return default; 
        
            try: 
                return Decimal(str(value).strip()); 
        
            except: return default
        def safe_int(value, default=0):
            if value is None: return default; 
            
            try: 
                return int(Decimal(str(value).strip()));
            except: return default

        current_data_row = start_data_row + 1 # Empezar en fila 9
        if detalles_filtrados:
            for i, detalle in enumerate(detalles_filtrados, 1):
                try: # Añadir try/except por fila por si acaso
                    # Extracción de datos
                    mes_val=safe_int(getattr(planilla,'mes',None));dias_habiles_val=safe_decimal(getattr(planilla,'dias_habiles',None));faltas_val=safe_decimal(getattr(detalle,'faltas',None));vacacion_val=safe_decimal(getattr(detalle,'vacacion',None));viajes_val=safe_decimal(getattr(detalle,'viajes',None));bajas_medicas_val=safe_decimal(getattr(detalle,'bajas_medicas',None));pcgh_val=safe_decimal(getattr(detalle,'pcgh',None));psgh_val=safe_decimal(getattr(detalle,'psgh',None));perm_excep_val=safe_decimal(getattr(detalle,'perm_excep',None));asuetos_val=safe_decimal(getattr(detalle,'asuetos',None));pcgh_emb_val=safe_decimal(getattr(detalle,'pcgh_embar_enf_base',None));dias_no_pag_val=safe_decimal(getattr(detalle,'dias_no_pagados',None));dias_pag_val=safe_decimal(getattr(detalle,'dias_pagados',None));total_ganado_val=safe_decimal(getattr(detalle,'total_ganado',None));descuentos_val=safe_decimal(getattr(detalle,'descuentos',None));liquido_pag_val=safe_decimal(getattr(detalle,'liquido_pagable',None));
                    row_data=[i,getattr(detalle,'item_externo',''),getattr(detalle,'ci_externo',''),getattr(detalle,'nombre_completo_externo',''),getattr(detalle,'cargo_externo',''),mes_val,dias_habiles_val,faltas_val,vacacion_val,viajes_val,bajas_medicas_val,pcgh_val,psgh_val,perm_excep_val,asuetos_val,pcgh_emb_val,dias_no_pag_val,dias_pag_val,total_ganado_val,descuentos_val,liquido_pag_val]

                    # Escribir datos y aplicar estilos
                    for col_idx, cell_value in enumerate(row_data, 1):
                        cell = sheet.cell(row=current_data_row, column=col_idx, value=cell_value)
                        header_name = data_headers[col_idx-1]
                        if col_idx <= 5: cell.alignment = left_alignment; cell.font = value_font # Texto
                        else: # Números
                            cell.alignment = right_alignment; cell.font = value_font
                            if header_name == 'Mes': cell.number_format = integer_format
                            elif header_name in ['Días Háb.', 'Faltas', 'Vacac.', 'Viajes', 'B.Médicas', 'PCGH', 'PSGH', 'P.Excep', 'Asuetos', 'PCGH Emb/Enf', 'D.No Pag.', 'D. Pag.']:
                                if isinstance(cell_value, Decimal) and cell_value.normalize().quantize(Decimal('1')) != cell_value: cell.number_format = decimal_format
                                else: cell.number_format = integer_format
                            elif isinstance(cell_value, Decimal): cell.number_format = decimal_format
                    current_data_row += 1 # Incrementar fila para el siguiente registro
                except Exception as e_row:
                    logger.error(f"Error procesando fila {current_data_row} para detalle ID {getattr(detalle, 'id', 'N/A')}: {e_row}", exc_info=True)
                    # Considera qué hacer si una fila falla: continuar, detenerse?
                    # Por ahora, incrementamos y continuamos
                    current_data_row += 1


        # --- 10. AJUSTAR ANCHO DE COLUMNAS ---
        # (Calcula desde start_data_row=8 hacia abajo. Sin ajuste especial Col A)
        logger.debug("Ajustando ancho de columnas...")
        column_widths = {}
        max_row_for_width = max(start_data_row, sheet.max_row)
        for row_idx in range(start_data_row, max_row_for_width + 1):
             for col_idx in range(1, num_data_columns + 1):
                 cell = sheet.cell(row=row_idx, column=col_idx)
                 try: # Calcular ancho necesario
                     text_representation = str(cell.value) if cell.value is not None else ''
                     if cell.number_format == decimal_format and isinstance(cell.value, (Decimal, float, int)): text_representation = f"{Decimal(cell.value):,.2f}"
                     elif cell.number_format == integer_format and isinstance(cell.value, (Decimal, float, int)): text_representation = f"{Decimal(cell.value):,.0f}"
                     cell_width = len(text_representation)
                     if row_idx == start_data_row and cell.font and cell.font.bold: cell_width += 2
                     current_max_width = column_widths.get(col_idx, 0)
                     column_widths[col_idx] = max(current_max_width, cell_width)
                 except Exception: pass
        # Aplicar anchos calculados
        for col_idx, max_width in column_widths.items():
            column_letter = get_column_letter(col_idx)
            adjusted_width = max(5, min(max_width + 2, 60)) # Limitar ancho
            sheet.column_dimensions[column_letter].width = adjusted_width
        logger.debug("Ancho de columnas ajustado.")

    except Exception as e_xlsx:
        # --- Manejo de Errores General ---
        logger.error(f"Error crítico generando archivo XLSX para Planilla {planilla_id}: {e_xlsx}", exc_info=True)
        messages.error(request, f"Error interno al generar el archivo Excel: {e_xlsx}")
        return redirect('ver_detalles_bono_te', planilla_id=planilla_id)

    # --- 11. Crear la Respuesta HTTP ---
    try:
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        # Generar nombre de archivo
        tipo_planilla_safe = "".join(c if c.isalnum() else '_' for c in planilla.get_tipo_display())
        filename = f"BonoTE_{tipo_planilla_safe}_{planilla.mes}_{planilla.anio}"
        # ... (añadir unidad al filename si aplica) ...
        if selected_unidad_id:
             unidad_name_safe = f"UnidadID_{selected_unidad_id}"
             try:
                 if 'unidad_nombre' in locals() and unidad_nombre != f"ID {selected_unidad_id} (?)":
                      unidad_name_safe = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in unidad_nombre)
                 else:
                    unidad = PrincipalUnidadExterna.objects.using('personas_db').get(pk=selected_unidad_id)
                    unidad_name_safe = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in (unidad.nombre_unidad or f"Unidad_{selected_unidad_id}"))
                 filename += f"_Unidad_{unidad_name_safe[:30]}"
             except Exception as e_fname: logger.warning(...)
        filename += ".xlsx"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        # Guardar y devolver
        workbook.save(response)
        logger.info(f"Archivo XLSX '{filename}' generado y enviado para Planilla {planilla.id}.")
        return response

    except Exception as e_resp:
        # --- Manejo de Errores Respuesta ---
        logger.error(f"Error creando o enviando HttpResponse para XLSX (Planilla {planilla_id}): {e_resp}", exc_info=True)
        messages.error(request, f"Error final al preparar la descarga del archivo: {e_resp}")
        return redirect('ver_detalles_bono_te', planilla_id=planilla_id)
#-----------------------------------------------


@login_required
def listar_personal_externo(request):
    # Consultamos la tabla 'principal_personal' en la base de datos 'personas_db'
    try:
        lista_personal = PrincipalPersonal.objects.using('personas_db').all().order_by('apellido_paterno', 'apellido_materno', 'nombre') # Ordena si quieres
        error_msg = None
    except Exception as e:
        # Captura cualquier error de conexión o consulta
        lista_personal = []
        error_msg = f"Error al consultar la base de datos externa: {e}"
        # Considera loggear el error también: import logging; logging.error(error_msg)

    context = {
        'personal_externo': lista_personal,
        'error_message': error_msg,
    }
    return render(request, 'planillas/listar_personal_externo.html', context)


#----------------------------------------------------------------


# --- En planilla/views.py ---

from django.http import HttpResponse



logger = logging.getLogger(__name__)

# El parámetro tipo_planilla ya no se usa, pero podemos dejarlo
def probar_consulta_designaciones(request, tipo_planilla="TODOS"):
    """
    Vista temporal para probar la consulta a principal_designacion externa.
    ¡¡SIN FILTROS!! Obtiene todas las designaciones.
    """
    logger.info(f"Probando consulta SIN FILTROS para designaciones (Tipo '{tipo_planilla}' ignorado)")

    try:
        # --- Construcción de la Consulta (SIN FILTROS) ---
        consulta = PrincipalDesignacionExterno.objects.using('personas_db').select_related(
            'personal', # Trae datos de PrincipalPersonalExterno
            'cargo'     # Trae datos de PrincipalCargoExterno
        )

        # (Sección de filtros eliminada)

        # --- FIN FILTROS ---

        consulta = consulta.order_by('personal__apellido_paterno', 'personal__apellido_materno', 'personal__nombre') # Orden opcional
        designaciones_encontradas = list(consulta) # Ejecuta la consulta
        logger.info(f"Consulta ejecutada. Se encontraron {len(designaciones_encontradas)} designaciones en total.")

        # --- Preparar respuesta HTML ---
        respuesta_html = f"<h1>Resultados de TODAS las Designaciones (Tipo '{tipo_planilla}' ignorado)</h1>"
        if designaciones_encontradas:
            respuesta_html += "<table border='1'><thead><tr><th>Item</th><th>CI</th><th>Nombre Completo</th><th>Cargo</th></tr></thead><tbody>" # Quitamos columnas de filtro
            for desig in designaciones_encontradas:
                persona = desig.personal
                cargo = desig.cargo
                respuesta_html += f"<tr>"
                respuesta_html += f"<td>{desig.item or 'N/A'}</td>"
                respuesta_html += f"<td>{persona.ci if persona else 'N/A'}</td>"
                respuesta_html += f"<td>{persona.nombre_completo if persona else 'N/A'}</td>"
                respuesta_html += f"<td>{cargo.nombre_cargo if cargo else 'N/A'}</td>"
                respuesta_html += f"</tr>"
            respuesta_html += "</tbody></table>"
        else:
            respuesta_html += "<p>No se encontraron designaciones en la tabla externa.</p>"

        return HttpResponse(respuesta_html)

    except Exception as e:
        logger.error(f"Error al ejecutar la consulta de prueba sin filtros: {e}", exc_info=True)
        # Intenta dar más detalles del error si es posible
        db_error_info = ""
        if hasattr(e, 'pgcode') or hasattr(e, 'pgerror'):
             db_error_info = f" (Code: {getattr(e, 'pgcode', 'N/A')}, Error: {getattr(e, 'pgerror', 'N/A')})"
        return HttpResponse(f"<h2>Error durante la consulta</h2><p>{e}{db_error_info}</p>", status=500)