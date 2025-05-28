# planilla/views.py (Versión Original con BD Externa)

import logging
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.contrib.auth.decorators import login_required, permission_required
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
from decimal import Decimal, InvalidOperation
from django.utils import timezone # Para fecha_elaboracion


from calendar import month_name
from openpyxl.drawing.image import Image

from django.db import transaction, IntegrityError       # Para transacciones y manejo de errores BD
from django.db.models import Q  
 

# --- Importaciones de Modelos Originales ---
from .models import (
    Planilla,
    DetalleBonoTe,
    # DetalleSueldo,      # Si lo usabas
    # DetalleImpositiva,  # Si lo usabas
    # Modelos Externos
    PrincipalDesignacionExterno,
    PrincipalPersonalExterno,
    PrincipalCargoExterno,
    PrincipalUnidadExterna,
    PrincipalSecretariaExterna,
    # PrincipalPersonal # Si tenías el duplicado
)

# Importar utils original (¡también debe ser restaurado!)
from .utils import get_processed_planilla_details

# Importaciones y configuración de Openpyxl (igual que antes)
try:
    import openpyxl
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.drawing.image import Image
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    class Font: pass
    class Alignment: pass
    class PatternFill: pass
    class Border: pass
    class Side: pass
    class Image: pass

logger = logging.getLogger(__name__)



from .forms import DetalleBonoTeForm, PlanillaForm, EditarPlanillaForm

# --- ¡IMPORTANTE! Importar Modelos de Reportes ---
try:
    from reportes.models import PlanillaAsistencia, DetalleAsistencia
    REPORTES_APP_AVAILABLE = True
except ImportError:
    PlanillaAsistencia = None
    DetalleAsistencia = None
    REPORTES_APP_AVAILABLE = False
    logging.error("ERROR CRÍTICO: No se pueden importar modelos de la app 'reportes'.")


# ---------------------------------

@login_required
def seleccionar_tipo_planilla(request):
    # Usar choices originales de Planilla
    tipos_disponibles = Planilla.TIPO_CHOICES # ('planta', 'contrato', 'consultor')
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        tipos_validos_keys = dict(tipos_disponibles).keys()
        if tipo in tipos_validos_keys:
            return redirect('crear_planilla', tipo=tipo) # Redirige a la vista de creación
        else:
            messages.error(request, 'Seleccione un tipo de planilla válido.')
            return render(request, 'planillas/seleccionar_tipo_planilla.html', {'tipos_planilla': tipos_disponibles})
    else: # GET
        context = {
            'tipos_planilla': tipos_disponibles,
        }
        return render(request, 'planillas/seleccionar_tipo_planilla.html', context)




#-------------------------------------------------------------------------

EXTERNAL_TYPE_MAP = {
        'planta': 'ASEGURADO',       # Verifica estos mapeos
        'contrato': 'CONTRATO',
        'consultor': 'CONSULTOR EN LINEA',
    }
# planilla/views.py









logger = logging.getLogger(__name__)

# Ya no se necesita EXTERNAL_TYPE_MAP aquí si el tipo viene de PlanillaAsistencia
# EXTERNAL_TYPE_MAP = { ... }

# planilla/views.py
# ... (importaciones como en el mensaje anterior) ...

@login_required
@permission_required('planilla.add_planilla', raise_exception=True)
def crear_planilla_bono_te(request):
    if not REPORTES_APP_AVAILABLE:
        messages.error(request, "Error crítico: La funcionalidad de reportes de asistencia no está disponible.")
        return redirect('lista_planillas')

    # Obtener el tipo_filtro de los parámetros GET de la URL actual
    tipo_filtro_seleccionado = request.GET.get('tipo_filtro', None)

    if request.method == 'POST':
        # Al hacer POST, instanciamos el form con los datos POST
        # y también con el tipo_filtro que se usó para renderizar el form (por si lo necesitamos para re-renderizar con errores)
        form = PlanillaForm(request.POST, tipo_filtro=tipo_filtro_seleccionado) # tipo_filtro para __init__
        if form.is_valid():
            selected_pa_base = form.cleaned_data['planilla_asistencia_base_selector']
            dias_habiles_ingresados = form.cleaned_data['dias_habiles']
            
            mes_derivado = selected_pa_base.mes
            anio_derivado = selected_pa_base.anio
            tipo_planilla_derivado = selected_pa_base.tipo # El tipo REAL de la planilla de bono

            # --- Comprobación adicional: si el tipo derivado no coincide con el filtro (no debería pasar si el form está bien) ---
            if tipo_filtro_seleccionado and tipo_planilla_derivado != tipo_filtro_seleccionado:
                messages.error(request, "Error: El tipo de la planilla de asistencia seleccionada no coincide con el tipo filtrado.")
                # Re-renderizar con el formulario (que ya tendrá el tipo_filtro de la request.GET)
                # O podrías forzar de nuevo el tipo_filtro al form aquí:
                form_con_error = PlanillaForm(request.POST, tipo_filtro=tipo_filtro_seleccionado) # Reinstanciar con el filtro original
                context_error = {
                    'planilla_form': form_con_error,
                    'tipos_planilla_choices': Planilla.TIPO_CHOICES, # Para el selector de filtro
                    'tipo_filtro_actual': tipo_filtro_seleccionado,
                    'titulo_vista': f"Crear Planilla Bono TE (Filtrado por: {dict(Planilla.TIPO_CHOICES).get(tipo_filtro_seleccionado,'Todos') if tipo_filtro_seleccionado else 'Todos los Tipos'})"
                }
                return render(request, 'planillas/crear_planilla.html', context_error)
            # --- Fin comprobación ---

            # ... (resto de la lógica POST para crear Planilla y DetalleBonoTe, SIN CAMBIOS desde el mensaje anterior) ...
            # ... (bloque try-except con transaction.atomic, etc.) ...
            # INICIO LÓGICA POST (copiada y verificada del mensaje anterior)
            plan_asistencia_validada = selected_pa_base
            detalles_asistencia_dict = {}
            try:
                detalles_asist_qs = DetalleAsistencia.objects.filter(planilla_asistencia=plan_asistencia_validada)
                detalles_asistencia_dict = {
                    da.personal_externo_id: da for da in detalles_asist_qs if da.personal_externo_id is not None
                }
                logger.info(f"Cargados {len(detalles_asistencia_dict)} detalles de asistencia desde la PlanillaAsistencia ID {plan_asistencia_validada.id}.")
            except Exception as e_asist:
                logger.error(f"Error inesperado cargando detalles de asistencia de PA ID {plan_asistencia_validada.id}: {e_asist}", exc_info=True)
                messages.error(request, f"Ocurrió un error al obtener los detalles de la asistencia seleccionada: {e_asist}")
                context_error = {'planilla_form': PlanillaForm(request.POST, tipo_filtro=tipo_filtro_seleccionado), 'titulo_vista': "Crear Planilla Bono TE", 'tipos_planilla_choices': Planilla.TIPO_CHOICES, 'tipo_filtro_actual': tipo_filtro_seleccionado}
                return render(request, 'planillas/crear_planilla.html', context_error)

            try:
                with transaction.atomic(using='default'):
                    planilla_bonote = Planilla(
                        planilla_asistencia_base=plan_asistencia_validada,
                        mes=mes_derivado,
                        anio=anio_derivado,
                        tipo=tipo_planilla_derivado,
                        dias_habiles=dias_habiles_ingresados,
                        estado='pendiente',
                        usuario_elaboracion=request.user,
                        fecha_elaboracion=timezone.now().date()
                    )
                    planilla_bonote.full_clean()
                    planilla_bonote.save()
                    logger.info(f"Creada Planilla (Bono TE) ID {planilla_bonote.id} para PA Base ID {plan_asistencia_validada.id}.")

                    detalles_bonote_a_crear = []
                    if not detalles_asistencia_dict:
                        messages.warning(request, f"Planilla Bono TE creada (ID: {planilla_bonote.id}), pero la Planilla de Asistencia base seleccionada no contenía detalles de personal.")
                    else:
                        logger.info(f"Preparando {len(detalles_asistencia_dict)} registros DetalleBonoTe desde la asistencia base...")
                        for personal_id_asistencia, detalle_asistencia_origen in detalles_asistencia_dict.items():
                            detalle_bt = DetalleBonoTe(
                                id_planilla=planilla_bonote,
                                personal_externo_id=personal_id_asistencia,
                                mes=planilla_bonote.mes,
                                faltas=getattr(detalle_asistencia_origen, 'faltas_dias', 0),
                                vacacion=getattr(detalle_asistencia_origen, 'vacacion', 0),
                                viajes=getattr(detalle_asistencia_origen, 'viajes', 0),
                                bajas_medicas=getattr(detalle_asistencia_origen, 'bajas_medicas', 0),
                                pcgh=getattr(detalle_asistencia_origen, 'pcgh', 0),
                                psgh=getattr(detalle_asistencia_origen, 'psgh', 0),
                                perm_excep=getattr(detalle_asistencia_origen, 'perm_excep', 0),
                                asuetos=getattr(detalle_asistencia_origen, 'asuetos', 0),
                                pcgh_embar_enf_base=getattr(detalle_asistencia_origen, 'pcgh_embar_enf_base', 0),
                                abandono_dias=getattr(detalle_asistencia_origen, 'abandono_dias', 0),
                                observaciones_asistencia=getattr(detalle_asistencia_origen, 'observaciones', ''),
                            )
                            detalles_bonote_a_crear.append(detalle_bt)

                        if detalles_bonote_a_crear:
                            DetalleBonoTe.objects.bulk_create(detalles_bonote_a_crear)
                            logger.info(f"Creados {len(detalles_bonote_a_crear)} registros DetalleBonoTe para Planilla {planilla_bonote.id}.")
                            detalles_creados_para_recalculo = DetalleBonoTe.objects.filter(id_planilla=planilla_bonote)
                            detalles_a_actualizar_con_calculos = []
                            for detalle_bt_creado in detalles_creados_para_recalculo:
                                detalle_bt_creado.calcular_valores()
                                detalles_a_actualizar_con_calculos.append(detalle_bt_creado)
                            campos_calculados = ['dias_no_pagados', 'dias_pagados', 'total_ganado', 'liquido_pagable']
                            DetalleBonoTe.objects.bulk_update(detalles_a_actualizar_con_calculos, campos_calculados)
                            logger.info(f"Valores recalculados y actualizados para {len(detalles_a_actualizar_con_calculos)} detalles Bono TE.")
                            messages.success(request, f"Planilla Bono TE ({planilla_bonote.get_tipo_display()} {planilla_bonote.mes}/{planilla_bonote.anio}) creada exitosamente con {len(detalles_bonote_a_crear)} registros, basada en la asistencia seleccionada.")
                        else:
                             messages.warning(request, f"Planilla Bono TE creada, pero no se generaron detalles.")
                return redirect('lista_planillas')
            except ValidationError as e_model_validation:
                logger.warning(f"Error de validación del modelo al crear Planilla Bono TE: {e_model_validation.message_dict}")
                for field, errors in e_model_validation.message_dict.items():
                    form_field_name = 'planilla_asistencia_base_selector' if field == 'planilla_asistencia_base' else field
                    for error_msg in errors:
                        form.add_error(form_field_name, error_msg) # El form aquí es el request.POST
            except IntegrityError as e_db_integrity:
                logger.error(f"Error de integridad en la BD al crear Planilla/Detalles Bono TE: {e_db_integrity}", exc_info=True)
                form.add_error(None, f"Error de base de datos. ({e_db_integrity})")
            except Exception as e_general_processing:
                 logger.error(f"Error general procesando la creación: {e_general_processing}", exc_info=True)
                 form.add_error(None, f"Error inesperado: {e_general_processing}")
            # Si hubo error, 'form' (el de request.POST) ahora tiene los errores y se re-renderizará abajo.
    else: # GET request
        # Instanciar el formulario pasando el tipo_filtro para que __init__ lo use
        form = PlanillaForm(tipo_filtro=tipo_filtro_seleccionado)

    context = {
        'planilla_form': form,
        'tipos_planilla_choices': Planilla.TIPO_CHOICES, # Para el selector de filtro
        'tipo_filtro_actual': tipo_filtro_seleccionado,  # Para mantener el estado del filtro en el template
        'titulo_vista': f"Crear Planilla Bono TE (Filtrando por: {dict(Planilla.TIPO_CHOICES).get(tipo_filtro_seleccionado,'Todos los Tipos') if tipo_filtro_seleccionado else 'Todos los Tipos'})"
    }
    return render(request, 'planillas/crear_planilla.html', context)


@login_required
@permission_required('planilla.view_planilla', raise_exception=True)
def lista_planillas(request):
    # Sin cambios si solo consulta Planilla
    planillas = Planilla.objects.all().order_by('-anio', '-mes', 'tipo')
    return render(request, 'planillas/lista_planillas.html', {'planillas': planillas})

# Vista original lista_bono_te (simple)
# def lista_bono_te(request):
#     detalles_bono_te = DetalleBonoTe.objects.all()
#     return render(request, 'planillas/lista_bono_te.html', {'detalles_bono_te': detalles_bono_te})
# O la versión mejorada si ya la tenías:
@login_required
@permission_required('planilla.view_detallebonote', raise_exception=True)
def lista_bono_te(request):
    # Selecciona relacionados internos, pero necesitará info externa si la muestra
    detalles_bono_te = DetalleBonoTe.objects.select_related('id_planilla').all()
    # Aquí necesitarías un bucle para añadir info externa si la plantilla la muestra
    # for detalle in detalles_bono_te:
    #    try:
    #       detalle.persona_obj = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
    #    except:
    #       detalle.persona_obj = None
    return render(request, 'planillas/lista_bono_te.html', {'detalles_bono_te': detalles_bono_te})

@login_required
@permission_required('planilla.change_detallebonote', raise_exception=True)
def editar_bono_te(request, detalle_id):
    # Obtener detalle interno
    detalle_bono_te = get_object_or_404(
        DetalleBonoTe.objects.select_related('id_planilla'), # Solo planilla es interna
        pk=detalle_id
    )
    planilla = detalle_bono_te.id_planilla
    dias_habiles_planilla = planilla.dias_habiles if planilla else None

    # --- Obtener datos externos (BD 'personas_db') ---
    persona_externa = None
    item_externo = 'N/A'
    cargo_externo = 'N/A'
    personal_externo_id = detalle_bono_te.personal_externo_id

    if personal_externo_id:
        try:
            persona_externa = PrincipalPersonalExterno.objects.using('personas_db').get(pk=personal_externo_id)
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"No se encontró PrincipalPersonalExterno ID {personal_externo_id} en 'personas_db'")
        except Exception as e_pers:
            logger.error(f"Error consultando PrincipalPersonalExterno ID {personal_externo_id}: {e_pers}", exc_info=True)

        # Buscar designación externa (asumiendo estado='ACTIVO')
        try:
            designacion = PrincipalDesignacionExterno.objects.using('personas_db') \
                .select_related('cargo') \
                .filter(personal_id=personal_externo_id, estado='ACTIVO') \
                .order_by('-id').first() # O la lógica original que tuvieras

            if designacion:
                item_externo = designacion.item if designacion.item is not None else 'N/A'
                cargo_externo = designacion.cargo.nombre_cargo if designacion.cargo else 'N/A'
            else:
                 logger.warning(f"No se encontró designación externa ACTIVA para Persona ID {personal_externo_id} en 'personas_db'.")
        except Exception as e_desig:
            logger.error(f"Error consultando PrincipalDesignacionExterno para Persona ID {personal_externo_id}: {e_desig}", exc_info=True)

    # --- Fin Obtener datos externos ---

    if request.method == 'POST':
        form = DetalleBonoTeForm(request.POST, instance=detalle_bono_te) # Form original
        if form.is_valid():
            form.save()
            messages.success(request, 'Detalle Bono TE editado correctamente.')
            # Lógica de redirección original
            redirect_secretaria = request.POST.get('redirect_secretaria', '')
            redirect_unidad = request.POST.get('redirect_unidad', '')
            redirect_q = request.POST.get('redirect_q', '')
            base_url = reverse('ver_detalles_bono_te', kwargs={'planilla_id': planilla.id})
            params = {}
            if redirect_secretaria: params['secretaria'] = redirect_secretaria
            if redirect_unidad: params['unidad'] = redirect_unidad
            if redirect_q: params['q'] = redirect_q
            if params: params['buscar'] = 'true'
            redirect_url = f"{base_url}?{urlencode(params)}" if params else base_url
            return redirect(redirect_url)
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else: # GET
        form = DetalleBonoTeForm(
            instance=detalle_bono_te,
            initial={'dias_habiles': dias_habiles_planilla} # Pasar días hábiles
        )

    context = {
        'form': form,
        'detalle_bono_te': detalle_bono_te, # Pasa el objeto DetalleBonoTe
        'dias_habiles': dias_habiles_planilla,
        # --- Pasar datos externos al contexto ---
        'persona_externa': persona_externa, # Pasa el objeto externo (o None)
        'item_externo': item_externo,
        'cargo_externo': cargo_externo,
        # --- Pasar params para redirect ---
        'redirect_secretaria': request.GET.get('secretaria', ''),
        'redirect_unidad': request.GET.get('unidad', ''),
        'redirect_q': request.GET.get('q', ''),
    }
    return render(request, 'planillas/editar_bono_te.html', context)

@login_required
@permission_required('planilla.delete_detallebonote', raise_exception=True)
def borrar_bono_te(request, detalle_id):
    detalle_bono_te = get_object_or_404(DetalleBonoTe, pk=detalle_id)
    planilla_id = detalle_bono_te.id_planilla_id

    # Obtener nombre para mensaje (puede fallar si BD externa no está)
    persona_nombre = f"ID Externo {detalle_bono_te.personal_externo_id}"
    try:
         if detalle_bono_te.personal_externo_id:
              persona = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle_bono_te.personal_externo_id)
              persona_nombre = persona.nombre_completo or persona_nombre
    except:
        pass # Mantener el ID si falla

    if request.method == 'POST':
        detalle_bono_te.delete()
        messages.success(request, f'Detalle Bono TE para {persona_nombre} borrado correctamente.')
        # Redirigir a detalles de la planilla
        return redirect('ver_detalles_bono_te', planilla_id=planilla_id)

    return render(request, 'planillas/borrar_bono_te.html', {
        'detalle_bono_te': detalle_bono_te,
        'persona_nombre': persona_nombre # Pasar nombre obtenido
        })

@login_required
@permission_required('planilla.change_planilla', raise_exception=True)
def editar_planilla(request, planilla_id):
    # Obtener la instancia de la planilla que se va a editar
    planilla_instancia = get_object_or_404(Planilla, pk=planilla_id)

    # Opcional: Lógica para restringir la edición basada en el estado actual
    # if planilla_instancia.estado == 'aprobado':
    #     messages.error(request, "No se puede editar una planilla que ya ha sido aprobada.")
    #     return redirect('lista_planillas')

    if request.method == 'POST':
        # Crear una instancia del formulario con los datos del POST y la instancia de la planilla
        form = EditarPlanillaForm(request.POST, instance=planilla_instancia)
        if form.is_valid():
            try:
                # Guardar los cambios en la planilla
                planilla_editada = form.save(commit=False)
                
                # Lógica adicional si la edición de 'dias_habiles' debe recalcular detalles:
                # Esto es CRUCIAL. Si cambias dias_habiles, los DetalleBonoTe deben recalcularse.
                if 'dias_habiles' in form.changed_data:
                    logger.info(f"Días hábiles cambiados para Planilla ID {planilla_editada.id}. Se recalcularán los detalles.")
                    # Necesitas guardar la planilla_editada primero para que los detalles tengan la FK correcta
                    # y los nuevos días hábiles.
                    planilla_editada.save() # Guardar cabecera primero

                    detalles_a_recalcular = DetalleBonoTe.objects.filter(id_planilla=planilla_editada)
                    detalles_a_actualizar_bulk = []
                    for detalle in detalles_a_recalcular:
                        detalle.calcular_valores() # Asume que calcular_valores() usa self.id_planilla.dias_habiles
                        detalles_a_actualizar_bulk.append(detalle)
                    
                    if detalles_a_actualizar_bulk:
                        campos_calculados = ['dias_no_pagados', 'dias_pagados', 'total_ganado', 'liquido_pagable']
                        DetalleBonoTe.objects.bulk_update(detalles_a_actualizar_bulk, campos_calculados)
                        logger.info(f"Recalculados {len(detalles_a_actualizar_bulk)} detalles para Planilla ID {planilla_editada.id}.")
                    
                    form.save_m2m() # Si tuvieras campos ManyToMany
                else:
                    planilla_editada.save() # Guardar si no hubo cambios en dias_habiles que requieran recalcular
                    form.save_m2m()

                messages.success(request, f'Planilla "{planilla_editada}" actualizada correctamente.')
                return redirect('lista_planillas') # O a 'ver_detalles_bono_te' para esta planilla
            except Exception as e:
                logger.error(f"Error al guardar la planilla editada ID {planilla_instancia.id}: {e}", exc_info=True)
                messages.error(request, f"Ocurrió un error al guardar los cambios: {e}")
        else:
            # El formulario no es válido, se re-renderizará con errores
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else: # Método GET
        # Crear una instancia del formulario con los datos de la planilla existente
        form = EditarPlanillaForm(instance=planilla_instancia)

    context = {
        'form': form,
        'planilla': planilla_instancia, # Pasar la instancia completa para mostrar datos no editables
        'titulo_vista': f"Editar Planilla Bono TE: {planilla_instancia.mes}/{planilla_instancia.anio} ({planilla_instancia.get_tipo_display()})"
    }
    return render(request, 'planillas/editar_planilla.html', context)


@login_required
@permission_required('planilla.delete_planilla', raise_exception=True)
def borrar_planilla(request, planilla_id):
    # Sin cambios si solo borra Planilla
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    if request.method == 'POST':
        planilla.delete()
        messages.success(request, 'Planilla borrada correctamente.')
        return redirect('lista_planillas')
    return render(request, 'planillas/borrar_planilla.html', {'planilla': planilla})

@login_required
@permission_required('planilla.view_detallebonote', raise_exception=True)
def ver_detalles_bono_te(request, planilla_id):
    """ Vista que usa utils.get_processed_planilla_details """
    logger.debug(f"Vista ver_detalles_bono_te llamada para planilla_id={planilla_id}")
    try:
        # Llamada a la función de utils (¡ASEGÚRATE DE RESTAURAR UTILS.PY!)
        processed_data = get_processed_planilla_details(request, planilla_id)

        if processed_data.get('error_message'):
            messages.error(request, processed_data['error_message'])
            if not processed_data.get('planilla'):
                 return redirect('lista_planillas')

        # El contexto se arma con los datos devueltos por la util
        context = {
            'planilla': processed_data.get('planilla'),
            'all_secretarias': processed_data.get('all_secretarias'),
            'unidades_for_select': processed_data.get('unidades_for_select'),
            'selected_secretaria_id': processed_data.get('selected_secretaria_id'),
            'selected_unidad_id': processed_data.get('selected_unidad_id'),
            'search_term': processed_data.get('search_term', ''), # Término de búsqueda
            'detalles_bono_te': processed_data.get('detalles_enriquecidos'), # Usa el nombre original del contexto
            'search_active': processed_data.get('search_active', False)
        }
        return render(request, 'planillas/ver_detalles_bono_te.html', context)

    except Exception as e_view:
        logger.error(f"Error inesperado en vista ver_detalles_bono_te ID {planilla_id}: {e_view}", exc_info=True)
        messages.error(request, "Ocurrió un error inesperado.")
        return redirect('lista_planillas')

@login_required
@permission_required('planilla.view_planilla', raise_exception=True)
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


# Vista de prueba original (si la tenías)
# from django.http import HttpResponse
# def probar_consulta_designaciones(request, tipo_planilla="TODOS"):
#     ... (pegar código original de esta vista) ...