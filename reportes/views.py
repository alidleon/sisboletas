import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction, IntegrityError
from django.urls import reverse_lazy, reverse
from .forms import EditarPlanillaAsistenciaForm 
from django.shortcuts import get_object_or_404, HttpResponse
from .models import PlanillaAsistencia, DetalleAsistencia
from .forms import PlanillaAsistenciaForm
from .utils import get_processed_asistencia_details, get_planilla_data_for_export, generar_pdf_asistencia
from .forms import AddDetalleAsistenciaForm 
from urllib.parse import urlencode
from django.http import JsonResponse, HttpResponseBadRequest, Http404 
from django.template.loader import render_to_string 
from django.views.decorators.http import require_POST, require_GET  
from .forms import DetalleAsistenciaForm 
from django.utils import timezone
from decimal import Decimal, InvalidOperation 
from django.db import models 
from django.http import JsonResponse 
import json 
from reportlab.lib.utils import ImageReader 
import os 
from django.conf import settings 
from reportlab.lib.pagesizes import letter, landscape 
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
import io 
from collections import defaultdict
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

try:
    from planilla.models import PrincipalDesignacionExterno, PrincipalPersonalExterno
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalDesignacionExterno = None
    PrincipalPersonalExterno = None
    PLANILLA_APP_AVAILABLE = False
    logging.error("ERROR CRÍTICO: No se pueden importar modelos de la app 'planilla'.")

logger = logging.getLogger(__name__)

EXTERNAL_TYPE_MAP = {
    'planta': 'ASEGURADO',
    'contrato': 'CONTRATO',
    'consultor': 'CONSULTOR EN LINEA',
}

@login_required
@permission_required('reportes.add_planillaasistencia', raise_exception=True)
@transaction.atomic(using='default')
def crear_planilla_asistencia(request):
    """
    Vista para crear una nueva PlanillaAsistencia (cabecera) y poblar
    automáticamente los DetallesAsistencia iniciales basados en el personal
    activo de la base de datos externa.
    """
    if not PLANILLA_APP_AVAILABLE:
        messages.error(request, "Error interno: La aplicación 'planilla' no está accesible.")
        return redirect('lista_planillas_asistencia') 
    if request.method == 'POST':
        form = PlanillaAsistenciaForm(request.POST)
        if form.is_valid():
            mes = form.cleaned_data['mes']
            anio = form.cleaned_data['anio']
            tipo = form.cleaned_data['tipo']
            if PlanillaAsistencia.objects.filter(mes=mes, anio=anio, tipo=tipo).exists():
                messages.warning(request, f"¡Atención! Ya existe un reporte de asistencia para {dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)} - {mes}/{anio}.")                # No usamos return HttpResponse, re-renderizamos el template con el mensaje
            else:
                try:
                    # 2. Crear la Cabecera (PlanillaAsistencia)
                    pa_cabecera = PlanillaAsistencia(
                        mes=mes,
                        anio=anio,
                        tipo=tipo,
                        estado='borrador', 
                        usuario_creacion=request.user
                    )
                    pa_cabecera.save()
                    logger.info(f"Creada PlanillaAsistencia ID {pa_cabecera.id} para {tipo} {mes}/{anio} por usuario {request.user.username}.")
                    # 3. Consultar Personal Externo Activo
                    target_external_type = EXTERNAL_TYPE_MAP.get(tipo)
                    if not target_external_type:
                         messages.error(request, f"Error interno: Mapeo no encontrado para tipo '{tipo}'.")
                         raise ValueError(f"Mapeo externo no encontrado para {tipo}")
                    logger.info(f"Consultando personal externo ACTIVO tipo '{target_external_type}' en 'personas_db'...")
                    designaciones_externas = []
                    try:
                        consulta_externa = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('personal') \
                            .filter(
                                tipo_designacion=target_external_type,
                                estado='ACTIVO' 
                            ) \
                            .order_by('personal__apellido_paterno', 'personal__apellido_materno', 'personal__nombre') 
                        designaciones_externas = list(consulta_externa) 
                        logger.info(f"Se encontraron {len(designaciones_externas)} designaciones externas activas.")
                    except Exception as e_ext:
                        logger.error(f"Error CRÍTICO consultando 'personas_db' para {tipo} {mes}/{anio}: {e_ext}", exc_info=True)
                        messages.error(request, f"Se creó la cabecera del reporte (ID: {pa_cabecera.id}), pero HUBO UN ERROR al consultar el personal externo: {e_ext}. No se generaron detalles.")
                        raise e_ext 
                    # 4. Preparar y Crear Detalles (DetalleAsistencia)
                    detalles_a_crear = []
                    personas_procesadas = set() 

                    if not designaciones_externas:
                        messages.warning(request, f"Reporte creado (ID: {pa_cabecera.id}), pero no se encontró personal externo ACTIVO para el tipo '{dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)}' en el periodo.")
                    else:
                        logger.info(f"Preparando {len(designaciones_externas)} potenciales registros DetalleAsistencia...")
                        for designacion in designaciones_externas:
                            if designacion.personal and designacion.personal.id not in personas_procesadas:
                                detalle = DetalleAsistencia(
                                    planilla_asistencia=pa_cabecera,
                                    personal_externo_id=designacion.personal.id, 
                                )
                                detalles_a_crear.append(detalle)
                                personas_procesadas.add(designacion.personal.id)
                            elif not designacion.personal:
                                logger.warning(f"Designación externa ID {designacion.id} sin personal asociado. Se omite.")

                        if detalles_a_crear:
                            logger.info(f"Intentando crear {len(detalles_a_crear)} registros DetalleAsistencia en lote...")
                            try:
                                DetalleAsistencia.objects.bulk_create(detalles_a_crear)
                                logger.info(f"Creados {len(detalles_a_crear)} registros DetalleAsistencia para PlanillaAsistencia ID {pa_cabecera.id}.")
                                messages.success(request, f"Reporte de asistencia para {dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)} {mes}/{anio} creado exitosamente con {len(detalles_a_crear)} registros iniciales.")
                            except IntegrityError as e_bulk:
                                logger.error(f"Error de integridad al crear detalles de asistencia en lote: {e_bulk}", exc_info=True)
                                messages.error(request, f"Se creó la cabecera del reporte, pero ERROR al guardar los detalles ({e_bulk}).")
                                raise e_bulk
                            except Exception as e_bulk_other:
                                logger.error(f"Error inesperado al crear detalles de asistencia en lote: {e_bulk_other}", exc_info=True)
                                messages.error(request, f"Se creó la cabecera del reporte, pero ERROR inesperado al guardar los detalles ({e_bulk_other}).")
                                raise e_bulk_other
                        else:
                            logger.warning(f"No se prepararon detalles de asistencia válidos a pesar de encontrar designaciones.")
                            messages.warning(request, f"Reporte creado (ID: {pa_cabecera.id}), pero no se pudo generar ningún detalle de asistencia individual (verificar personal asociado en BD externa).")
                    return redirect('lista_planillas_asistencia') 

                except Exception as e_proc:
                     logger.error(f"Error no controlado procesando creación de planilla asistencia {tipo} {mes}/{anio}: {e_proc}", exc_info=True)
                     if not messages.get_messages(request): 
                          messages.error(request, f"Ocurrió un error inesperado durante la creación: {e_proc}")
        else:
            messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
    else:
        form = PlanillaAsistenciaForm() 
    context = {
        'form': form,
        'titulo_pagina': "Crear Nuevo Reporte de Asistencia" 
    }
    return render(request, 'reportes/crear_planilla_asistencia.html', context)

#-------------------------------


@login_required
@permission_required('reportes.view_planillaasistencia', raise_exception=True)
def lista_planillas_asistencia(request):
    """
    Muestra una lista PAGINADA de todas las Planillas de Asistencia creadas.
    """
    logger.debug(f"Vista lista_planillas_asistencia llamada. GET params: {request.GET.urlencode()}")
    queryset = PlanillaAsistencia.objects.all().order_by('-anio', '-mes', 'tipo')
    filtro_anio = request.GET.get('anio', '').strip()
    filtro_mes = request.GET.get('mes', '').strip()
    filtro_tipo = request.GET.get('tipo', '').strip()
    filtro_estado = request.GET.get('estado', '').strip()
    if filtro_anio:
        try:
            queryset = queryset.filter(anio=int(filtro_anio))
        except (ValueError, TypeError):
            pass
    
    if filtro_mes:
        try:
            queryset = queryset.filter(mes=int(filtro_mes))
        except (ValueError, TypeError):
            pass

    if filtro_tipo:
        queryset = queryset.filter(tipo=filtro_tipo)

    if filtro_estado:
        queryset = queryset.filter(estado=filtro_estado)

    items_por_pagina = 10
    paginator = Paginator(queryset, items_por_pagina)
    page_number_str = request.GET.get('page', '1')
    logger.debug(f"Número de página solicitado: '{page_number_str}'")
    try:
        page_obj_planillas = paginator.page(page_number_str)
    except PageNotAnInteger:
        logger.warning(f"Número de página inválido ('{page_number_str}'). Mostrando página 1.")
        page_obj_planillas = paginator.page(1)
    except EmptyPage:
        logger.warning(f"Página '{page_number_str}' fuera de rango. Mostrando última página {paginator.num_pages}.")
        page_obj_planillas = paginator.page(paginator.num_pages)
    logger.info(f"Mostrando página {page_obj_planillas.number} de {paginator.num_pages} para planillas de asistencia (Total: {paginator.count}).")
    querystring = request.GET.copy()
    if 'page' in querystring:
        del querystring['page']

    querystring = request.GET.copy()
    if 'page' in querystring:
        del querystring['page']
    context = {
        'page_obj': page_obj_planillas,
        'querystring': querystring.urlencode(),
        'titulo_pagina': "REPORTES DE ASISTENCIA",
        'tipos_disponibles': PlanillaAsistencia.TIPO_CHOICES, 
        'estados_disponibles': PlanillaAsistencia.ESTADO_CHOICES,
    }
    return render(request, 'reportes/lista_planillas_asistencia.html', context)

#--------------------------
@login_required
@permission_required('reportes.change_planillaasistencia', raise_exception=True)
def editar_planilla_asistencia(request, pk):
    planilla_obj = get_object_or_404(PlanillaAsistencia, pk=pk)
    logger.debug(f"VISTA: Editando PlanillaAsistencia ID: {pk}, Estado actual al cargar: {planilla_obj.estado}")

    estado_original_al_cargar_pagina = planilla_obj.estado 

    if request.method == 'POST':
        form = EditarPlanillaAsistenciaForm(request.POST, instance=planilla_obj, user=request.user)
        
        if planilla_obj.estado == 'archivado' and estado_original_al_cargar_pagina == 'archivado':
            messages.error(request, "No se pueden guardar cambios en un reporte archivado.")
            return redirect('lista_planillas_asistencia')
        if form.is_valid():
            try:                
                nuevo_estado_seleccionado = form.cleaned_data.get('estado')
                observaciones_nuevas = form.cleaned_data.get('observaciones_generales')
                
                logger.debug(f"VISTA POST: Estado original='{estado_original_al_cargar_pagina}', Estado del form='{nuevo_estado_seleccionado}', Obs del form='{observaciones_nuevas[:50]}...'")
                planilla_a_guardar = form.save(commit=False) 
                
                if nuevo_estado_seleccionado != estado_original_al_cargar_pagina:
                    logger.info(f"Planilla ID {pk}: Aplicando cambio de estado de '{estado_original_al_cargar_pagina}' a '{nuevo_estado_seleccionado}'.")
                    
                    planilla_a_guardar.estado = nuevo_estado_seleccionado 
                    if nuevo_estado_seleccionado == 'validado' and estado_original_al_cargar_pagina == 'borrador':
                        planilla_a_guardar.usuario_validacion = request.user
                        planilla_a_guardar.fecha_validacion = timezone.now()
                    
                    elif nuevo_estado_seleccionado == 'borrador' and estado_original_al_cargar_pagina == 'validado':
                        if request.user.is_superuser: 
                            planilla_a_guardar.usuario_validacion = None
                            planilla_a_guardar.fecha_validacion = None
                        else:
                            messages.error(request, "No tiene permisos para reabrir una planilla validada.")
                            form = EditarPlanillaAsistenciaForm(instance=planilla_obj, user=request.user) 
                            context = {'form': form, 'planilla_obj': planilla_obj, 'titulo_pagina': f"Editar Reporte ({planilla_obj.get_tipo_display()} - {planilla_obj.mes}/{planilla_obj.anio})"}
                            return render(request, 'reportes/editar_planilla_asistencia.html', context)
                
                planilla_a_guardar.save() 

                messages.success(request, f"Reporte '{planilla_a_guardar}' actualizado correctamente.")
                return redirect('lista_planillas_asistencia')

            except Exception as e_save:
                logger.error(f"VISTA: Error guardando cabecera PlanillaAsistencia ID {pk}: {e_save}", exc_info=True)
                messages.error(request, f"Ocurrió un error al guardar los cambios: {e_save}")
        else:
            logger.warning(f"VISTA: Formulario de edición para Planilla ID {pk} no es válido: {form.errors}")
            messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
    else: 
        logger.debug(f"VISTA GET: Creando form con instance ID: {planilla_obj.pk}, Estado: {planilla_obj.estado}")
        form = EditarPlanillaAsistenciaForm(instance=planilla_obj, user=request.user)

    context = {
        'form': form,
        'planilla_obj': planilla_obj,
        'titulo_pagina': f"Editar Reporte ({planilla_obj.get_tipo_display()} - {planilla_obj.mes}/{planilla_obj.anio})"
    }
    return render(request, 'reportes/editar_planilla_asistencia.html', context)

#----------------------------
@login_required
@permission_required('reportes.delete_planillaasistencia', raise_exception=True)
def borrar_planilla_asistencia(request, pk):
    """
    Permite borrar una PlanillaAsistencia existente y todos sus detalles asociados.
    """
    planilla = get_object_or_404(PlanillaAsistencia, pk=pk)

    planilla_str = str(planilla) 
    num_detalles = planilla.detalles_asistencia.count() 

    if request.method == 'POST':
        try:
            planilla.delete()
            messages.success(request, f"Reporte '{planilla_str}' y sus {num_detalles} detalles asociados han sido borrados exitosamente.")
            return redirect('lista_planillas_asistencia')
        except Exception as e_del:
            logger.error(f"Error borrando PlanillaAsistencia ID {pk}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar el reporte: {e_del}")
            return redirect('lista_planillas_asistencia')

    context = {
        'planilla': planilla,
        'num_detalles': num_detalles,
        'titulo_pagina': f"Confirmar Borrado: {planilla}"
    }
    return render(request, 'reportes/borrar_planilla_asistencia.html', context)

#-----------------------------------------------

@login_required
@permission_required('reportes.view_detalleasistencia', raise_exception=True)
def ver_detalles_asistencia(request, pk):
    logger.debug(f"--- VISTA: INICIO ver_detalles_asistencia - Planilla ID: {pk}, GET: {request.GET.urlencode()} ---")    
    try:
        items_por_pagina_vista = 25         
        processed_data = get_processed_asistencia_details(request, pk, items_por_pagina=items_por_pagina_vista)
        planilla_obj_vista = processed_data.get('planilla_asistencia') 
        page_obj_vista = processed_data.get('page_obj')
        error_msg_from_util = processed_data.get('error_message')
        logger.debug(f"VISTA: planilla_obj_vista: {'Sí' if planilla_obj_vista else 'No'}")
        logger.debug(f"VISTA: page_obj_vista: {'Sí' if page_obj_vista else 'No'}")
        if page_obj_vista:
            logger.debug(f"VISTA: page_obj_vista.object_list count: {len(page_obj_vista.object_list)}")
            logger.debug(f"VISTA: page_obj_vista.paginator.count: {page_obj_vista.paginator.count}")
            logger.debug(f"VISTA: page_obj_vista.has_other_pages(): {page_obj_vista.has_other_pages()}")
        logger.debug(f"VISTA: error_msg_from_util: {error_msg_from_util}")
        if not planilla_obj_vista and error_msg_from_util:
            messages.error(request, error_msg_from_util)
            return redirect('lista_planillas_asistencia')
        if not planilla_obj_vista:
            messages.error(request, "Reporte de asistencia no encontrado.")
            return redirect('lista_planillas_asistencia')
        if error_msg_from_util and planilla_obj_vista: 
             messages.warning(request, error_msg_from_util)        
        form_edit_panel = DetalleAsistenciaForm()         
        context = {
            'planilla_asistencia': planilla_obj_vista,
            'all_secretarias': processed_data.get('all_secretarias', []),
            'unidades_for_select': processed_data.get('unidades_for_select', []),
            'selected_secretaria_id': processed_data.get('selected_secretaria_id'),
            'selected_unidad_id': processed_data.get('selected_unidad_id'),
            'search_term': processed_data.get('search_term', ''),
            'search_active': processed_data.get('search_active', False), 
            'page_obj': page_obj_vista, 
            'visible_ids_list': processed_data.get('detalle_ids_order', []), 
            'form_edit': form_edit_panel,
            'titulo_pagina': f"Detalles Asistencia - {planilla_obj_vista.get_tipo_display()} {planilla_obj_vista.mes}/{planilla_obj_vista.anio}",
        }      
        return render(request, 'reportes/ver_detalles_asistencia.html', context)
    except Http404: 
        logger.warning(f"VISTA: PlanillaAsistencia ID {pk} no encontrada (Http404).")
        messages.error(request, "Reporte de asistencia no encontrado.")
        return redirect('lista_planillas_asistencia')
    except Exception as e_view:
        logger.error(f"VISTA: Error inesperado en ver_detalles_asistencia ID {pk}: {e_view}", exc_info=True)
        messages.error(request, "Ocurrió un error inesperado al intentar mostrar los detalles.")
        return redirect('lista_planillas_asistencia')

#-------------------------------------------


from .forms import ( PlanillaAsistenciaForm, EditarPlanillaAsistenciaForm,
                    DetalleAsistenciaForm ) 


try:
    from planilla.models import PrincipalDesignacionExterno, PrincipalPersonalExterno, PrincipalCargoExterno
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalDesignacionExterno, PrincipalPersonalExterno, PrincipalCargoExterno = None, None, None
    PLANILLA_APP_AVAILABLE = False
    logging.error("ERROR CRÍTICO: No se pueden importar modelos de la app 'planilla'.")

logger = logging.getLogger(__name__)


EXTERNAL_TYPE_MAP = {
    'planta': 'ASEGURADO',
    'contrato': 'CONTRATO',
    'consultor': 'CONSULTOR EN LINEA',
}

@login_required
@permission_required('reportes.change_detalleasistencia', raise_exception=True)
def editar_detalle_asistencia(request, detalle_id):
    """
    Permite editar los campos de un registro DetalleAsistencia específico.
    Maneja tanto peticiones normales (renderizando HTML) como AJAX (devolviendo JSON).
    """
    detalle = get_object_or_404(
        DetalleAsistencia.objects.select_related('planilla_asistencia'),
        pk=detalle_id
    )
    planilla_asistencia = detalle.planilla_asistencia
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    ESTADOS_PERMITEN_MODIFICACION_DETALLES = ['borrador']
    if planilla_asistencia.estado not in ESTADOS_PERMITEN_MODIFICACION_DETALLES:
        error_msg = f"No se pueden modificar detalles. El reporte está en estado '{planilla_asistencia.get_estado_display()}'."
        logger.warning(f"Intento de edición de DetalleAsistencia ID {detalle_id} bloqueado. Planilla ID {planilla_asistencia.id} en estado '{planilla_asistencia.estado}'. Usuario: {request.user.username}")
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': error_msg, 'errors': {'__all__': [error_msg]}}, status=403) # 403 Forbidden
        else:
            messages.error(request, error_msg)
            return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)
    persona_externa = None
    item_externo = "N/A"
    cargo_externo = "N/A"
    redirect_url = reverse('lista_planillas_asistencia') 
    if not is_ajax:
        if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
            try:
                persona_externa = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
                designacion = PrincipalDesignacionExterno.objects.using('personas_db') \
                    .select_related('cargo') \
                    .filter(personal_id=detalle.personal_externo_id, estado='ACTIVO') \
                    .order_by('-id').first()
                if designacion:
                    item_externo = designacion.item if designacion.item is not None else 'N/A'
                    cargo_externo = designacion.cargo.nombre_cargo if designacion.cargo else 'N/A'
            except PrincipalPersonalExterno.DoesNotExist:
                logger.warning(f"No se encontró PrincipalPersonalExterno ID {detalle.personal_externo_id} (editar_detalle_asistencia HTML)")
            except Exception as e_ext:
                logger.error(f"Error consultando datos externos para DetalleAsistencia ID {detalle.id} (editar_detalle_asistencia HTML): {e_ext}", exc_info=True)
                messages.warning(request, "Advertencia: No se pudieron cargar todos los datos complementarios del personal.")
        try:
            redirect_params = {
                'secretaria': request.GET.get('secretaria', ''),
                'unidad': request.GET.get('unidad', ''),
                'q': request.GET.get('q', ''),
            }
            redirect_params = {k: v for k, v in redirect_params.items() if v}
            base_redirect_url = reverse('ver_detalles_asistencia', kwargs={'pk': planilla_asistencia.pk})
            redirect_url = f"{base_redirect_url}?{urlencode(redirect_params)}" if redirect_params else base_redirect_url
        except Exception as e_url:
            logger.error(f"Error generando URL de redirección para ver_detalles_asistencia {planilla_asistencia.pk}: {e_url}")
    if request.method == 'POST':
        form = DetalleAsistenciaForm(request.POST, instance=detalle)
        if form.is_valid():
            try:
                detalle_guardado = form.save()
                if is_ajax:
                    updated_data_for_table = {}
                    for field_name in DetalleAsistenciaForm.Meta.fields:
                        value = getattr(detalle_guardado, field_name)
                        if isinstance(value, Decimal):
                            updated_data_for_table[field_name] = str(value)
                        elif value is None and isinstance(detalle_guardado._meta.get_field(field_name), models.TextField):
                             updated_data_for_table[field_name] = ""
                        else:
                            updated_data_for_table[field_name] = value
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Registro actualizado correctamente.',
                        'updated_data': updated_data_for_table
                     })
                else: 
                     nombre_display = persona_externa.nombre_completo if persona_externa else f'ID Ext {detalle.personal_externo_id}'
                     messages.success(request, f"Asistencia para '{nombre_display}' actualizada.")
                     return redirect(redirect_url)
            except Exception as e_save:
                 logger.error(f"Error guardando DetalleAsistencia ID {detalle.id}: {e_save}", exc_info=True)
                 if is_ajax:
                      return JsonResponse({'status': 'error', 'message': f'Error al guardar: {e_save}'}, status=500)
                 else: 
                      messages.error(request, f"Ocurrió un error al guardar los cambios: {e_save}")
        else:
            if is_ajax:
                return JsonResponse({
                    'status': 'error',
                    'message': 'El formulario contiene errores.',
                    'errors': json.loads(form.errors.as_json())
                 }, status=400) 
            else: 
                messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
    else: 
        form = DetalleAsistenciaForm(instance=detalle) 

    if is_ajax and request.method == 'GET':
         logger.error(f"Se recibió un GET AJAX inesperado en editar_detalle_asistencia para ID {detalle_id}")
         return JsonResponse({'error': 'Método GET AJAX no soportado aquí'}, status=405)
    context = {
        'form': form,
        'detalle': detalle,
        'planilla_asistencia': planilla_asistencia,
        'persona_externa': persona_externa, 
        'item_externo': item_externo,       
        'cargo_externo': cargo_externo,     
        'cancel_url': redirect_url,         
        'titulo_pagina': f"Editar Asistencia - {persona_externa.nombre_completo if persona_externa else f'ID Ext {detalle.personal_externo_id}'} ({planilla_asistencia.mes}/{planilla_asistencia.anio})"
    }
    return render(request, 'reportes/editar_detalle_asistencia.html', context)
#----------------------------------------------

@login_required
@permission_required('reportes.delete_detalleasistencia', raise_exception=True)
def borrar_detalle_asistencia(request, detalle_id):
    """
    Permite borrar un registro DetalleAsistencia específico.
    """
    detalle = get_object_or_404(
        DetalleAsistencia.objects.select_related('planilla_asistencia'), 
        pk=detalle_id
    )
    planilla_asistencia = detalle.planilla_asistencia
    planilla_asistencia_id = planilla_asistencia.pk
    ESTADOS_PERMITEN_MODIFICACION_DETALLES = ['borrador']
    if planilla_asistencia.estado not in ESTADOS_PERMITEN_MODIFICACION_DETALLES:
        error_msg = f"No se pueden borrar detalles. El reporte está en estado '{planilla_asistencia.get_estado_display()}'."
        logger.warning(f"Intento de borrado de DetalleAsistencia ID {detalle_id} bloqueado. Planilla ID {planilla_asistencia.id} en estado '{planilla_asistencia.estado}'. Usuario: {request.user.username}")
        messages.error(request, error_msg)
        return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)

    # --- Obtener nombre para el mensaje de confirmación ---
    persona_nombre = f"ID Externo {detalle.personal_externo_id}" 
    if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
        try:
            persona = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
            persona_nombre = persona.nombre_completo or persona_nombre
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"Al borrar DetalleAsistencia ID {detalle.id}, no se encontró PrincipalPersonalExterno ID {detalle.personal_externo_id}")
        except Exception as e_ext:
            logger.error(f"Error consultando datos externos al intentar borrar DetalleAsistencia ID {detalle.id}: {e_ext}", exc_info=True)
            messages.warning(request, "Advertencia: No se pudo cargar la información completa del personal para la confirmación.")

    if request.method == 'POST':
        try:
            nombre_para_mensaje = persona_nombre
            detalle.delete()
            messages.success(request, f"Registro de asistencia para '{nombre_para_mensaje}' borrado exitosamente.")
            return redirect('ver_detalles_asistencia', pk=planilla_asistencia_id)
        except Exception as e_del:
            logger.error(f"Error borrando DetalleAsistencia ID {detalle_id}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar el registro: {e_del}")
            return redirect('ver_detalles_asistencia', pk=planilla_asistencia_id)
    context = {
        'detalle': detalle,
        'planilla_asistencia': planilla_asistencia,
        'persona_nombre': persona_nombre, 
        'titulo_pagina': f"Confirmar Borrado Asistencia: {persona_nombre}"
    }
    return render(request, 'reportes/borrar_detalle_asistencia.html', context)

#-----------------------------------------------------

@login_required
@permission_required('reportes.add_detalleasistencia', raise_exception=True)
def add_detalle_asistencia(request, planilla_asistencia_id):
    """
    Añade manualmente un nuevo registro DetalleAsistencia a una
    PlanillaAsistencia existente, buscando al personal por CI o Item.
    """
    planilla_asistencia = get_object_or_404(PlanillaAsistencia, pk=planilla_asistencia_id)
    ESTADOS_PERMITEN_MODIFICACION_DETALLES = ['borrador']
    if planilla_asistencia.estado not in ESTADOS_PERMITEN_MODIFICACION_DETALLES:
        messages.error(request, f"No se pueden añadir registros a esta planilla porque su estado es '{planilla_asistencia.get_estado_display()}'.")
        return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)

    # Verificar si la app planilla está disponible
    if not PLANILLA_APP_AVAILABLE:
        messages.error(request, "Error interno: Componentes externos no disponibles.")
        return redirect('lista_planillas_asistencia')

    # --- Verificar si la planilla está en estado editable ---
    if planilla_asistencia.estado in ['validado', 'archivado']:
         messages.warning(request, f"No se pueden añadir registros a un reporte que está '{planilla_asistencia.get_estado_display()}'.")
         return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)

    if request.method == 'POST':
        form = AddDetalleAsistenciaForm(request.POST)
        if form.is_valid():
            ci_o_item = form.cleaned_data['ci_o_item'].strip()
            personal_externo_encontrado = None
            personal_externo_id = None
            try:
                try:
                    personal_externo_encontrado = PrincipalPersonalExterno.objects.using('personas_db').get(ci__iexact=ci_o_item)
                    personal_externo_id = personal_externo_encontrado.id
                    logger.info(f"Personal encontrado por CI '{ci_o_item}' (ID: {personal_externo_id}) para añadir a PlanillaAsistencia {planilla_asistencia.id}")
                except PrincipalPersonalExterno.DoesNotExist:
                    logger.debug(f"No encontrado por CI '{ci_o_item}', buscando por Item...")
                    try:
                        item_num = int(ci_o_item) 
                        designacion = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('personal') \
                            .filter(item=item_num, estado='ACTIVO') \
                            .order_by('-id') \
                            .first()
                        if designacion and designacion.personal:
                            personal_externo_encontrado = designacion.personal
                            personal_externo_id = personal_externo_encontrado.id
                            logger.info(f"Personal encontrado por Item '{item_num}' (ID: {personal_externo_id}) para añadir a PlanillaAsistencia {planilla_asistencia.id}")
                        else:
                             logger.warning(f"No se encontró designación ACTIVA con Item '{item_num}' o no tiene personal asociado.")
                             raise PrincipalPersonalExterno.DoesNotExist 

                    except (ValueError, TypeError): 
                         logger.warning(f"'{ci_o_item}' no es un número de Item válido.")
                         raise PrincipalPersonalExterno.DoesNotExist 
                    except Exception as e_item_search:
                        logger.error(f"Error buscando por Item '{ci_o_item}': {e_item_search}", exc_info=True)
                        raise PrincipalPersonalExterno.DoesNotExist 

            except PrincipalPersonalExterno.DoesNotExist:
                messages.error(request, f"No se encontró personal activo en la base de datos externa con el CI o Item '{ci_o_item}'.")
                return render(request, 'reportes/add_detalle_asistencia.html', {'form': form, 'planilla_asistencia': planilla_asistencia})
            except Exception as e_db_ext:
                 logger.error(f"Error consultando BD externa para CI/Item '{ci_o_item}': {e_db_ext}", exc_info=True)
                 messages.error(request, f"Error al consultar la base de datos externa: {e_db_ext}")
                 return render(request, 'reportes/add_detalle_asistencia.html', {'form': form, 'planilla_asistencia': planilla_asistencia})


            # --- Si se encontró, verificar duplicado interno ---
            if personal_externo_id:
                if DetalleAsistencia.objects.filter(planilla_asistencia=planilla_asistencia, personal_externo_id=personal_externo_id).exists():
                    messages.warning(request, f"El personal '{personal_externo_encontrado.nombre_completo if personal_externo_encontrado else ci_o_item}' ya existe en este reporte de asistencia.")
                else:
                    try:
                        with transaction.atomic(using='default'): 
                            nuevo_detalle = DetalleAsistencia(
                                planilla_asistencia=planilla_asistencia,
                                personal_externo_id=personal_externo_id
                            )
                            nuevo_detalle.save()
                            messages.success(request, f"Se añadió exitosamente el registro de asistencia para '{personal_externo_encontrado.nombre_completo if personal_externo_encontrado else ci_o_item}'.")
                            return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)
                    except Exception as e_save:
                        logger.error(f"Error al guardar nuevo DetalleAsistencia para pers_id {personal_externo_id} en plan_id {planilla_asistencia.id}: {e_save}", exc_info=True)
                        messages.error(request, f"Error al guardar el nuevo registro: {e_save}")
        else:
             messages.error(request, "Por favor, ingrese un CI o Número de Item.")
    else:
        form = AddDetalleAsistenciaForm()

    context = {
        'form': form,
        'planilla_asistencia': planilla_asistencia,
        'titulo_pagina': f"Añadir Registro a Reporte {planilla_asistencia}"
    }
    return render(request, 'reportes/add_detalle_asistencia.html', context)


#-----------------------------------------

@login_required
@permission_required('reportes.change_detalleasistencia', raise_exception=True)
def get_detalle_asistencia_json(request, detalle_id):
    """
    Devuelve los datos de un DetalleAsistencia específico en formato JSON
    para ser usados por el panel de edición rápida (AJAX). Incluye manejo
    de errores para la consulta a la base de datos externa.
    """
    try:
        # 1. Obtener el detalle de asistencia local
        detalle = get_object_or_404(DetalleAsistencia, pk=detalle_id)

        # 2. Preparar diccionario con datos del detalle local
        form_fields = DetalleAsistenciaForm.Meta.fields
        data = {}
        for field_name in form_fields:
            value = getattr(detalle, field_name, None) 
            if isinstance(value, Decimal):
                data[field_name] = str(value)
            elif value is None and isinstance(detalle._meta.get_field(field_name), models.TextField):
                 data[field_name] = ""
            else:
                data[field_name] = value
        data['id'] = detalle.pk

        # 3. Intentar obtener y añadir datos básicos del personal externo
        data['nombre_completo_externo'] = f"ID Ext: {detalle.personal_externo_id}" 
        data['ci_externo'] = "N/A" 

        if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
            try:
                campos_a_traer = ['nombre', 'apellido_paterno', 'apellido_materno', 'ci']
                persona_ext = PrincipalPersonalExterno.objects.using('personas_db').only(
                    *campos_a_traer 
                ).get(pk=detalle.personal_externo_id)
                nombre = getattr(persona_ext, 'nombre', '') or ''
                paterno = getattr(persona_ext, 'apellido_paterno', '') or ''
                materno = getattr(persona_ext, 'apellido_materno', '') or ''
                nombre_completo = f"{nombre} {paterno} {materno}".strip().replace('  ', ' ') 

                data['nombre_completo_externo'] = nombre_completo if nombre_completo else f"ID Ext: {detalle.personal_externo_id}"
                data['ci_externo'] = getattr(persona_ext, 'ci', None) or "N/A" 

            except PrincipalPersonalExterno.DoesNotExist:
                logger.warning(f"No se encontró PrincipalPersonalExterno ID {detalle.personal_externo_id} en get_detalle_asistencia_json")
            except AttributeError as e_attr:
                logger.error(f"Error de atributo consultando PrincipalPersonalExterno ID {detalle.personal_externo_id} en get_detalle_asistencia_json: {e_attr}. Verifica los nombres de campo.")
            except Exception as e_ext:
                logger.error(f"Error consultando BD externa ('personas_db') en get_detalle_asistencia_json para ID {detalle.personal_externo_id}: {e_ext}", exc_info=True)
        # 4. Devolver todos los datos recolectados como JSON
        return JsonResponse(data)

    except Http404:
        logger.warning(f"Intento de acceso a DetalleAsistencia ID {detalle_id} no encontrado (get_detalle_asistencia_json).")
        return JsonResponse({'error': 'Registro de asistencia no encontrado.'}, status=404)
    except Exception as e:
        logger.error(f"Error inesperado en get_detalle_asistencia_json para ID {detalle_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Error interno del servidor al procesar la solicitud.'}, status=500)
    


# --- funcion para generar pdf ---
@login_required
@permission_required('reportes.view_planillaasistencia', raise_exception=True)
def exportar_planilla_asistencia_pdf(request, pk):
    logger.info(f"Solicitud de exportación PDF para PlanillaAsistencia ID: {pk}")

    data_export = get_planilla_data_for_export(pk)
    planilla_cabecera = data_export.get('planilla_asistencia')
    detalles_agrupados = data_export.get('detalles_agrupados_por_unidad')
    orden_unidades = data_export.get('orden_unidades')
    error_message = data_export.get('error_message')

    if error_message or not planilla_cabecera:
        logger.error(f"Error al obtener datos para exportar PDF (Planilla ID {pk}): {error_message}")
        messages.error(request, f"No se pudo generar el PDF: {error_message or 'Planilla no encontrada.'}")
        return redirect('lista_planillas_asistencia')


    if not detalles_agrupados or not orden_unidades:
        logger.warning(f"PlanillaAsistencia ID {pk} no tiene detalles agrupados para exportar a PDF.")
        messages.warning(request, "El reporte de asistencia no tiene detalles (o no se pudieron agrupar) para exportar.")
        return redirect('ver_detalles_asistencia', pk=pk) if planilla_cabecera else redirect('lista_planillas_asistencia')

    column_definitions = [
        ('Nro.',    0.3*inch, 'nro'),                         
        ('Ítem',    0.4*inch, 'item_externo'),                
        ('CI',      0.6*inch, 'ci_externo'),                  
        ('Nombre Completo', 1.5*inch, 'nombre_completo_externo'), 
        ('Cargo',   1.56*inch, 'cargo_externo'),                

        ('Om.Ct',   0.33*inch, 'omision_cant'),
        ('Om.Sn',   0.33*inch, 'omision_sancion'),
        ('Ab.Día',  0.33*inch, 'abandono_dias'),
        ('Ab.Sn',   0.33*inch, 'abandono_sancion'),
        ('Fal.Día', 0.33*inch, 'faltas_dias'),
        ('Fal.Sn',  0.33*inch, 'faltas_sancion'),
        ('Atr.Min', 0.33*inch, 'atrasos_minutos'),
        ('Atr.Sn',  0.33*inch, 'atrasos_sancion'),
        ('Vac.',    0.33*inch, 'vacacion'),
        ('Viaj.',   0.33*inch, 'viajes'),
        ('B.Med',   0.33*inch, 'bajas_medicas'),
        ('PCGH',    0.33*inch, 'pcgh'),
        ('P.Exc',   0.33*inch, 'perm_excep'),
        ('Asuet',   0.33*inch, 'asuetos'),
        ('PSGH',    0.33*inch, 'psgh'),
        ('PCGH.E',  0.33*inch, 'pcgh_embar_enf_base'),
        ('Act.Nav', 0.33*inch, 'actividad_navidad'),
        ('Iza.B',   0.33*inch, 'iza_bandera'),
    ]

    # 3. Preparar respuesta HTTP y buffer
    response = HttpResponse(content_type='application/pdf')
    filename = f"asistencia_{planilla_cabecera.mes}_{planilla_cabecera.anio}_{planilla_cabecera.get_tipo_display().replace(' ', '_')}_por_unidad.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    buffer = io.BytesIO()
    # 4. Llamar a la función de utilidad para generar el PDF
    try:
        generar_pdf_asistencia(
            output_buffer=buffer,
            planilla_cabecera=planilla_cabecera,
            detalles_agrupados=detalles_agrupados,
            orden_unidades=orden_unidades,
            column_definitions=column_definitions
        )
    except Exception as e_gen_pdf:
        logger.error(f"Vista: Falla al llamar a generar_pdf_asistencia para Planilla ID {pk}: {e_gen_pdf}", exc_info=True)
        messages.error(request, f"Ocurrió un error crítico al generar el documento PDF: {e_gen_pdf}")
        return redirect('lista_planillas_asistencia')

    # 5. Escribir el PDF en la respuesta
    pdf_data = buffer.getvalue()
    buffer.close()
    response.write(pdf_data)
    
    logger.info(f"Vista: PDF completo generado y enviado para Planilla ID {pk}.")
    return response

#-------------------------------
@login_required
@permission_required('reportes.view_planillaasistencia', raise_exception=True) 
def exportar_detalles_filtrados_pdf(request, pk):
    logger.info(f"Vista: Solicitud de exportación PDF FILTRADO para PlanillaAsistencia ID: {pk} con filtros: {request.GET.urlencode()}")

    # 1. Obtener datos procesados usando la utilidad.
    items_para_vista_web = 25
    processed_data = get_processed_asistencia_details(request, pk, items_por_pagina=items_para_vista_web)

    planilla_cabecera = processed_data.get('planilla_asistencia')
    page_obj_devuelto_por_util = processed_data.get('page_obj') 
    error_message_data = processed_data.get('error_message')

    if error_message_data and not planilla_cabecera:
        logger.error(f"Vista (filtrado): Error al obtener planilla para exportar PDF (ID {pk}): {error_message_data}")
        messages.error(request, f"No se pudo generar el PDF: {error_message_data}")
        return redirect('lista_planillas_asistencia')
    
    if not planilla_cabecera:
        logger.error(f"Vista (filtrado): Planilla ID {pk} no encontrada para exportar PDF.")
        messages.error(request, "Planilla no encontrada.")
        return redirect('lista_planillas_asistencia')

    if page_obj_devuelto_por_util and hasattr(page_obj_devuelto_por_util, 'paginator'):
        todos_los_detalles_filtrados = page_obj_devuelto_por_util.paginator.object_list
        logger.debug(f"Vista (filtrado): Total de detalles filtrados obtenidos del paginador: {len(todos_los_detalles_filtrados)}")
    else:
        todos_los_detalles_filtrados = []
        logger.warning(f"Vista (filtrado): No se pudo obtener page_obj o paginator de la utilidad para Planilla ID {pk}. Datos de detalle podrían estar vacíos.")

    if not todos_los_detalles_filtrados:
        logger.warning(f"Vista (filtrado): Planilla ID {pk} no tiene detalles (o ninguno coincide con los filtros) para exportar.")
        messages.warning(request, "No hay detalles que coincidan con los filtros para exportar.")
        redirect_url = reverse('ver_detalles_asistencia', kwargs={'pk': pk})
        if request.GET:
            redirect_url += '?' + request.GET.urlencode()
        return redirect(redirect_url)

    # 2. Agrupar los detalles filtrados por unidad
    detalles_agrupados_filtrados = defaultdict(list)
    for detalle_obj in todos_los_detalles_filtrados: 
        unidad_nombre = getattr(detalle_obj, 'unidad_externa_nombre', 'SIN UNIDAD ESPECÍFICA')
        if unidad_nombre is None or not str(unidad_nombre).strip(): 
            unidad_nombre = 'SIN UNIDAD ESPECÍFICA'
        detalles_agrupados_filtrados[unidad_nombre].append(detalle_obj)
    
    orden_unidades_filtradas = sorted(detalles_agrupados_filtrados.keys())
    # 3. Definir las columnas para el PDF (usando tus anchos actualizados)
    column_definitions = [
        ('Nro.',    0.3*inch, 'nro'),                         
        ('Ítem',    0.4*inch, 'item_externo'),                
        ('CI',      0.6*inch, 'ci_externo'),                  
        ('Nombre Completo', 1.5*inch, 'nombre_completo_externo'), 
        ('Cargo',   1.56*inch, 'cargo_externo'),                

        ('Om.Ct',   0.33*inch, 'omision_cant'),
        ('Om.Sn',   0.33*inch, 'omision_sancion'),
        ('Ab.Día',  0.33*inch, 'abandono_dias'),
        ('Ab.Sn',   0.33*inch, 'abandono_sancion'),
        ('Fal.Día', 0.33*inch, 'faltas_dias'),
        ('Fal.Sn',  0.33*inch, 'faltas_sancion'),
        ('Atr.Min', 0.33*inch, 'atrasos_minutos'),
        ('Atr.Sn',  0.33*inch, 'atrasos_sancion'),
        ('Vac.',    0.33*inch, 'vacacion'),
        ('Viaj.',   0.33*inch, 'viajes'),
        ('B.Med',   0.33*inch, 'bajas_medicas'),
        ('PCGH',    0.33*inch, 'pcgh'),
        ('P.Exc',   0.33*inch, 'perm_excep'),
        ('Asuet',   0.33*inch, 'asuetos'),
        ('PSGH',    0.33*inch, 'psgh'),
        ('PCGH.E',  0.33*inch, 'pcgh_embar_enf_base'),
        ('Act.Nav', 0.33*inch, 'actividad_navidad'),
        ('Iza.B',   0.33*inch, 'iza_bandera'),
    ] # Suma total de anchos: 0.3+0.4+0.6+2.4+1.56 + (18*0.28) = 5.26 + 5.04 = 10.3 pulgadas.
    # 4. Preparar respuesta HTTP y buffer
    response = HttpResponse(content_type='application/pdf')
    filter_suffix = "_filtrado" if request.GET.get('buscar') or request.GET.get('secretaria') or request.GET.get('unidad') or request.GET.get('q') else ""
    filename = f"asistencia_{planilla_cabecera.mes}_{planilla_cabecera.anio}_{planilla_cabecera.get_tipo_display().replace(' ', '_')}_por_unidad{filter_suffix}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    buffer = io.BytesIO()

    # 5. Llamar a la función de utilidad para generar el PDF
    try:
        generar_pdf_asistencia( 
            output_buffer=buffer,
            planilla_cabecera=planilla_cabecera,
            detalles_agrupados=dict(detalles_agrupados_filtrados),
            orden_unidades=orden_unidades_filtradas,
            column_definitions=column_definitions 
        )
    except Exception as e_gen_pdf:
        logger.error(f"Vista (filtrado): Falla al llamar a generar_pdf_asistencia para Planilla ID {pk}: {e_gen_pdf}", exc_info=True)
        messages.error(request, f"Ocurrió un error crítico al generar el documento PDF (filtrado): {e_gen_pdf}")
        redirect_url = reverse('ver_detalles_asistencia', kwargs={'pk': pk})
        if request.GET:
            redirect_url += '?' + request.GET.urlencode()
        return redirect(redirect_url)

    # 6. Escribir el PDF en la respuesta
    pdf_data = buffer.getvalue()
    buffer.close()
    response.write(pdf_data)
    
    logger.info(f"Vista: PDF FILTRADO generado y enviado para Planilla ID {pk} con {len(todos_los_detalles_filtrados)} detalles.")
    return response