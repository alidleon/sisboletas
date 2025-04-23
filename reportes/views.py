# reportes/views.py

import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.urls import reverse_lazy # Usaremos reverse_lazy para el redirect
from .forms import EditarPlanillaAsistenciaForm 
# Importar modelos y formularios necesarios
from django.shortcuts import get_object_or_404
from .models import PlanillaAsistencia, DetalleAsistencia
from .forms import PlanillaAsistenciaForm
from .utils import get_processed_asistencia_details
from .forms import AddDetalleAsistenciaForm # Importar el nuevo form


# Importar modelos externos de la app 'planilla'
try:
    from planilla.models import PrincipalDesignacionExterno, PrincipalPersonalExterno
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalDesignacionExterno = None
    PrincipalPersonalExterno = None
    PLANILLA_APP_AVAILABLE = False
    logging.error("ERROR CRÍTICO: No se pueden importar modelos de la app 'planilla'.")

logger = logging.getLogger(__name__)

# Mapeo de tipo interno a tipo_designacion externo (similar al de planilla.views)
# ¡Asegúrate de que estos valores coincidan con tu BD externa!
EXTERNAL_TYPE_MAP = {
    'planta': 'ASEGURADO',
    'contrato': 'CONTRATO',
    'consultor': 'CONSULTOR EN LINEA',
}

@login_required
# transaction.atomic asegura que la creación de la cabecera y los detalles
# se realice como una sola operación en la base de datos 'default'.
@transaction.atomic(using='default')
def crear_planilla_asistencia(request):
    """
    Vista para crear una nueva PlanillaAsistencia (cabecera) y poblar
    automáticamente los DetallesAsistencia iniciales basados en el personal
    activo de la base de datos externa.
    """
    # Verificar si los modelos externos están disponibles
    if not PLANILLA_APP_AVAILABLE:
        messages.error(request, "Error interno: La aplicación 'planilla' no está accesible.")
        # Redirigir a una página segura, como el dashboard o la lista de reportes si existiera
        return redirect('lista_planillas_asistencia') # O cambiar a un 'home' general

    if request.method == 'POST':
        form = PlanillaAsistenciaForm(request.POST)
        if form.is_valid():
            mes = form.cleaned_data['mes']
            anio = form.cleaned_data['anio']
            tipo = form.cleaned_data['tipo']

            # 1. Verificar duplicados
            if PlanillaAsistencia.objects.filter(mes=mes, anio=anio, tipo=tipo).exists():
                messages.warning(request, f"¡Atención! Ya existe un reporte de asistencia para {dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)} - {mes}/{anio}.")
                # No usamos return HttpResponse, re-renderizamos el template con el mensaje
            else:
                # Si no hay duplicados, procedemos dentro de la transacción
                try:
                    # 2. Crear la Cabecera (PlanillaAsistencia)
                    pa_cabecera = PlanillaAsistencia(
                        mes=mes,
                        anio=anio,
                        tipo=tipo,
                        estado='borrador', # Estado inicial
                        usuario_creacion=request.user
                    )
                    pa_cabecera.save()
                    logger.info(f"Creada PlanillaAsistencia ID {pa_cabecera.id} para {tipo} {mes}/{anio} por usuario {request.user.username}.")

                    # 3. Consultar Personal Externo Activo
                    target_external_type = EXTERNAL_TYPE_MAP.get(tipo)
                    if not target_external_type:
                         # Esto no debería pasar si el form valida bien, pero por si acaso
                         messages.error(request, f"Error interno: Mapeo no encontrado para tipo '{tipo}'.")
                         # Forzamos un rollback lanzando una excepción dentro del atomic block
                         raise ValueError(f"Mapeo externo no encontrado para {tipo}")

                    logger.info(f"Consultando personal externo ACTIVO tipo '{target_external_type}' en 'personas_db'...")
                    designaciones_externas = []
                    try:
                        # Consultamos usando 'personas_db' y pre-cargamos 'personal'
                        consulta_externa = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('personal') \
                            .filter(
                                tipo_designacion=target_external_type,
                                estado='ACTIVO' # Asumimos que solo queremos personal activo
                            ) \
                            .order_by('personal__apellido_paterno', 'personal__apellido_materno', 'personal__nombre') # Opcional: ordenar

                        designaciones_externas = list(consulta_externa) # Ejecutar la consulta
                        logger.info(f"Se encontraron {len(designaciones_externas)} designaciones externas activas.")

                    except Exception as e_ext:
                        logger.error(f"Error CRÍTICO consultando 'personas_db' para {tipo} {mes}/{anio}: {e_ext}", exc_info=True)
                        messages.error(request, f"Se creó la cabecera del reporte (ID: {pa_cabecera.id}), pero HUBO UN ERROR al consultar el personal externo: {e_ext}. No se generaron detalles.")
                        # Forzamos rollback
                        raise e_ext # Re-lanzamos para que transaction.atomic haga rollback

                    # 4. Preparar y Crear Detalles (DetalleAsistencia)
                    detalles_a_crear = []
                    personas_procesadas = set() # Para evitar duplicados si alguien tiene >1 designación activa del mismo tipo

                    if not designaciones_externas:
                        messages.warning(request, f"Reporte creado (ID: {pa_cabecera.id}), pero no se encontró personal externo ACTIVO para el tipo '{dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)}' en el periodo.")
                    else:
                        logger.info(f"Preparando {len(designaciones_externas)} potenciales registros DetalleAsistencia...")
                        for designacion in designaciones_externas:
                            # Verificar que la designación tenga personal asociado y que no lo hayamos procesado ya
                            if designacion.personal and designacion.personal.id not in personas_procesadas:
                                detalle = DetalleAsistencia(
                                    planilla_asistencia=pa_cabecera,
                                    personal_externo_id=designacion.personal.id, # Guardamos solo el ID externo
                                    # El resto de campos (faltas, viajes, etc.) toman su valor default=0
                                )
                                detalles_a_crear.append(detalle)
                                personas_procesadas.add(designacion.personal.id)
                            elif not designacion.personal:
                                logger.warning(f"Designación externa ID {designacion.id} sin personal asociado. Se omite.")
                            # else: # Ya procesado, omitir duplicado silenciosamente

                        if detalles_a_crear:
                            logger.info(f"Intentando crear {len(detalles_a_crear)} registros DetalleAsistencia en lote...")
                            try:
                                DetalleAsistencia.objects.bulk_create(detalles_a_crear)
                                logger.info(f"Creados {len(detalles_a_crear)} registros DetalleAsistencia para PlanillaAsistencia ID {pa_cabecera.id}.")
                                messages.success(request, f"Reporte de asistencia para {dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)} {mes}/{anio} creado exitosamente con {len(detalles_a_crear)} registros iniciales.")
                            except IntegrityError as e_bulk:
                                logger.error(f"Error de integridad al crear detalles de asistencia en lote: {e_bulk}", exc_info=True)
                                messages.error(request, f"Se creó la cabecera del reporte, pero ERROR al guardar los detalles ({e_bulk}).")
                                # Forzamos rollback
                                raise e_bulk
                            except Exception as e_bulk_other:
                                logger.error(f"Error inesperado al crear detalles de asistencia en lote: {e_bulk_other}", exc_info=True)
                                messages.error(request, f"Se creó la cabecera del reporte, pero ERROR inesperado al guardar los detalles ({e_bulk_other}).")
                                # Forzamos rollback
                                raise e_bulk_other
                        else:
                            # Esto podría pasar si todas las designaciones encontradas no tenían personal o eran duplicados
                            logger.warning(f"No se prepararon detalles de asistencia válidos a pesar de encontrar designaciones.")
                            messages.warning(request, f"Reporte creado (ID: {pa_cabecera.id}), pero no se pudo generar ningún detalle de asistencia individual (verificar personal asociado en BD externa).")

                    # 5. Redirección en caso de éxito
                    # Redirigir a una vista que liste las Planillas de Asistencia (necesitamos crearla)
                    # O redirigir a la vista de edición de esta planilla recién creada
                    return redirect('lista_planillas_asistencia') # ¡NECESITAREMOS CREAR ESTA URL/VISTA!

                # Captura errores generales dentro del bloque 'try' (después del duplicado)
                except Exception as e_proc:
                     # Los errores específicos (BD externa, bulk create) ya deberían haber puesto un mensaje
                     # Este es un catch-all por si algo más falla
                     logger.error(f"Error no controlado procesando creación de planilla asistencia {tipo} {mes}/{anio}: {e_proc}", exc_info=True)
                     if not messages.get_messages(request): # Solo añadir mensaje si no hay uno específico ya
                          messages.error(request, f"Ocurrió un error inesperado durante la creación: {e_proc}")
                     # La transacción ya hizo rollback automáticamente al salir del 'with' con una excepción

        # Si el formulario POST no es válido o si hubo un error (excepto redirección)
        else:
            messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
            # El contexto se preparará abajo y se re-renderizará la plantilla

    # Si es método GET o si el formulario POST no fue válido
    else:
        form = PlanillaAsistenciaForm() # Formulario vacío para GET

    context = {
        'form': form,
        'titulo_pagina': "Crear Nuevo Reporte de Asistencia" # Ejemplo de variable extra
    }
    return render(request, 'reportes/crear_planilla_asistencia.html', context)

#-------------------------------


@login_required
def lista_planillas_asistencia(request):
    """
    Muestra una lista de todas las Planillas de Asistencia creadas.
    """
    # Consultamos todas las planillas de asistencia, ordenadas
    planillas = PlanillaAsistencia.objects.all().order_by('-anio', '-mes', 'tipo')

    context = {
        'planillas_asistencia': planillas,
        'titulo_pagina': "Reportes de Asistencia Creados"
    }
    return render(request, 'reportes/lista_planillas_asistencia.html', context)

@login_required
def editar_planilla_asistencia(request, pk): # Usamos 'pk' como en Django admin/generic views
    """
    Permite editar los campos de la cabecera de una PlanillaAsistencia existente.
    """
    planilla = get_object_or_404(PlanillaAsistencia, pk=pk)

    if request.method == 'POST':
        # Pasamos instance para indicar que es edición
        form = EditarPlanillaAsistenciaForm(request.POST, instance=planilla)
        if form.is_valid():
            try:
                planilla_editada = form.save()
                messages.success(request, f"Cabecera del reporte {planilla_editada} actualizada correctamente.")
                # Redirigir de vuelta a la lista
                return redirect('lista_planillas_asistencia')
            except Exception as e_save:
                logger.error(f"Error guardando cabecera PlanillaAsistencia ID {pk}: {e_save}", exc_info=True)
                messages.error(request, f"Ocurrió un error al guardar los cambios: {e_save}")
        else:
            messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
            # Se re-renderiza abajo con el form con errores

    # Si es GET o el POST no fue válido
    else:
        form = EditarPlanillaAsistenciaForm(instance=planilla) # Llenar con datos actuales

    context = {
        'form': form,
        'planilla': planilla, # Pasamos el objeto para mostrar info si es necesario
        'titulo_pagina': f"Editar Reporte {planilla}"
    }
    return render(request, 'reportes/editar_planilla_asistencia.html', context)

#----------------------------

# reportes/views.py

# ... (imports existentes: logging, render, redirect, messages, login_required, get_object_or_404) ...
# ... (modelos, formularios, otras vistas) ...

@login_required
def borrar_planilla_asistencia(request, pk):
    """
    Permite borrar una PlanillaAsistencia existente y todos sus detalles asociados.
    """
    # Obtener la planilla a borrar
    planilla = get_object_or_404(PlanillaAsistencia, pk=pk)

    # Guardamos los datos para el mensaje antes de borrar
    planilla_str = str(planilla) # Ej: "Asistencia Asegurado - 5/2024 (Borrador)"
    num_detalles = planilla.detalles_asistencia.count() # Contar detalles antes de borrar

    if request.method == 'POST':
        try:
            # Eliminar el objeto PlanillaAsistencia
            # Esto disparará CASCADE y borrará los DetalleAsistencia
            planilla.delete()
            messages.success(request, f"Reporte '{planilla_str}' y sus {num_detalles} detalles asociados han sido borrados exitosamente.")
            # Redirigir a la lista
            return redirect('lista_planillas_asistencia')
        except Exception as e_del:
            logger.error(f"Error borrando PlanillaAsistencia ID {pk}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar el reporte: {e_del}")
            # Redirigir de vuelta a la lista incluso si hay error
            return redirect('lista_planillas_asistencia')

    # Si es método GET, mostrar página de confirmación
    context = {
        'planilla': planilla,
        'num_detalles': num_detalles,
        'titulo_pagina': f"Confirmar Borrado: {planilla}"
    }
    return render(request, 'reportes/borrar_planilla_asistencia.html', context)

#-----------------------------------------------

@login_required
def ver_detalles_asistencia(request, pk):
    """
    Muestra los detalles de asistencia filtrados y enriquecidos para
    una PlanillaAsistencia específica. Usa la función de utilidad.
    """
    logger.debug(f"Vista ver_detalles_asistencia llamada para planilla_asistencia_id={pk}")
    try:
        # Llamada a la función de utils adaptada
        processed_data = get_processed_asistencia_details(request, pk)

        # Manejar error si la planilla no se encontró en la utilidad
        if processed_data.get('error_message') and not processed_data.get('planilla_asistencia'):
            messages.error(request, processed_data['error_message'])
            return redirect('lista_planillas_asistencia') # Redirigir a la lista

        # Mensaje de error no fatal (ej. error al cargar secretarías)
        elif processed_data.get('error_message'):
             messages.warning(request, processed_data['error_message'])

        # Construir el contexto para la plantilla con los datos devueltos
        context = {
            # Usamos los nombres de clave definidos en la utilidad
            'planilla_asistencia': processed_data.get('planilla_asistencia'),
            'all_secretarias': processed_data.get('all_secretarias'),
            'unidades_for_select': processed_data.get('unidades_for_select'),
            'selected_secretaria_id': processed_data.get('selected_secretaria_id'),
            'selected_unidad_id': processed_data.get('selected_unidad_id'),
            'search_term': processed_data.get('search_term', ''),
            'detalles_asistencia': processed_data.get('detalles_asistencia'), # Clave adaptada
            'search_active': processed_data.get('search_active', False),
            'titulo_pagina': f"Detalles Asistencia - {processed_data.get('planilla_asistencia')}"
        }
        return render(request, 'reportes/ver_detalles_asistencia.html', context)

    except Exception as e_view:
        logger.error(f"Error inesperado en vista ver_detalles_asistencia ID {pk}: {e_view}", exc_info=True)
        messages.error(request, "Ocurrió un error inesperado al mostrar los detalles.")
        return redirect('lista_planillas_asistencia')


#-------------------------------------------

# reportes/views.py


from django.urls import reverse_lazy, reverse # Importar reverse


# Modelos y Formularios locales

from .forms import ( PlanillaAsistenciaForm, EditarPlanillaAsistenciaForm,
                    DetalleAsistenciaForm ) # <-- Importar DetalleAsistenciaForm

# Modelos externos y flag
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
def editar_detalle_asistencia(request, detalle_id):
    """
    Permite editar los campos de un registro DetalleAsistencia específico.
    """
    detalle = get_object_or_404(
        DetalleAsistencia.objects.select_related('planilla_asistencia'),
        pk=detalle_id
    )
    planilla_asistencia = detalle.planilla_asistencia

    # --- Obtener Datos Externos para Contexto ---
    persona_externa = None
    item_externo = "N/A"
    cargo_externo = "N/A"
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
            logger.warning(f"No se encontró PrincipalPersonalExterno ID {detalle.personal_externo_id} para DetalleAsistencia ID {detalle.id}")
            # No bloqueamos, pero el template debe manejar persona_externa=None
        except Exception as e_ext:
            logger.error(f"Error consultando datos externos para DetalleAsistencia ID {detalle.id}: {e_ext}", exc_info=True)
            messages.warning(request, "Advertencia: No se pudieron cargar todos los datos complementarios del personal.")
    # --- Fin Obtener Datos Externos ---

    # --- Manejo de parámetros GET para redirección ---
    # Capturamos los parámetros de filtro que venían de la vista de detalles
    redirect_params = {
        'secretaria': request.GET.get('secretaria', ''),
        'unidad': request.GET.get('unidad', ''),
        'q': request.GET.get('q', ''),
        'buscar': 'true' # Para reactivar la búsqueda en la vista de detalles
    }
    # Limpiamos parámetros vacíos
    redirect_params = {k: v for k, v in redirect_params.items() if v}

    # Construimos la URL de retorno a la vista de detalles
    try:
        # Usamos reverse para construir la URL base
        base_redirect_url = reverse('ver_detalles_asistencia', kwargs={'pk': planilla_asistencia.pk})
        # Añadimos los parámetros GET si existen
        from urllib.parse import urlencode
        redirect_url = f"{base_redirect_url}?{urlencode(redirect_params)}" if redirect_params else base_redirect_url
    except Exception as e_url:
        logger.error(f"Error generando URL de redirección para ver_detalles_asistencia {planilla_asistencia.pk}: {e_url}")
        # Fallback a la lista general si falla la generación de URL específica
        redirect_url = reverse('lista_planillas_asistencia')


    if request.method == 'POST':
        form = DetalleAsistenciaForm(request.POST, instance=detalle)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Asistencia para '{persona_externa.nombre_completo if persona_externa else f'ID Ext {detalle.personal_externo_id}'}' actualizada.")
                # Redirigir a la vista de detalles, manteniendo los filtros
                return redirect(redirect_url)

            except Exception as e_save:
                 logger.error(f"Error guardando DetalleAsistencia ID {detalle.id}: {e_save}", exc_info=True)
                 messages.error(request, f"Ocurrió un error al guardar los cambios: {e_save}")
        else:
            messages.error(request, "El formulario contiene errores.")

    else: # GET
        form = DetalleAsistenciaForm(instance=detalle)

    context = {
        'form': form,
        'detalle': detalle,
        'planilla_asistencia': planilla_asistencia,
        'persona_externa': persona_externa,
        'item_externo': item_externo,
        'cargo_externo': cargo_externo,
        'redirect_params': redirect_params, # Pasamos params para botones/links
        'cancel_url': redirect_url, # URL para el botón Cancelar
        'titulo_pagina': f"Editar Asistencia - {persona_externa.nombre_completo if persona_externa else f'ID Ext {detalle.personal_externo_id}'} ({planilla_asistencia.mes}/{planilla_asistencia.anio})"
    }
    return render(request, 'reportes/editar_detalle_asistencia.html', context)


#----------------------------------------------

# reportes/views.py

# ... (imports existentes: logging, render, redirect, messages, login_required, get_object_or_404, Http404, reverse) ...
# ... (modelos, formularios, otras vistas) ...

@login_required
def borrar_detalle_asistencia(request, detalle_id):
    """
    Permite borrar un registro DetalleAsistencia específico.
    """
    detalle = get_object_or_404(
        DetalleAsistencia.objects.select_related('planilla_asistencia'), # Incluir planilla para redirect
        pk=detalle_id
    )
    planilla_asistencia = detalle.planilla_asistencia
    # Guardamos el ID de la planilla para la redirección
    planilla_asistencia_id = planilla_asistencia.pk

    # --- Obtener nombre para el mensaje de confirmación ---
    persona_nombre = f"ID Externo {detalle.personal_externo_id}" # Valor por defecto
    if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
        try:
            persona = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
            persona_nombre = persona.nombre_completo or persona_nombre
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"Al borrar DetalleAsistencia ID {detalle.id}, no se encontró PrincipalPersonalExterno ID {detalle.personal_externo_id}")
        except Exception as e_ext:
            logger.error(f"Error consultando datos externos al intentar borrar DetalleAsistencia ID {detalle.id}: {e_ext}", exc_info=True)
            messages.warning(request, "Advertencia: No se pudo cargar la información completa del personal para la confirmación.")
    # --- Fin obtener nombre ---

    if request.method == 'POST':
        try:
            # Guardar nombre para mensaje antes de borrar
            nombre_para_mensaje = persona_nombre
            detalle.delete()
            messages.success(request, f"Registro de asistencia para '{nombre_para_mensaje}' borrado exitosamente.")
            # Redirigir a la vista de detalles de la planilla a la que pertenecía
            return redirect('ver_detalles_asistencia', pk=planilla_asistencia_id)
        except Exception as e_del:
            logger.error(f"Error borrando DetalleAsistencia ID {detalle_id}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar el registro: {e_del}")
            # Redirigir de vuelta a los detalles de la planilla si falla
            return redirect('ver_detalles_asistencia', pk=planilla_asistencia_id)

    # Si es método GET, mostrar página de confirmación
    context = {
        'detalle': detalle,
        'planilla_asistencia': planilla_asistencia,
        'persona_nombre': persona_nombre, # Pasar nombre obtenido
        'titulo_pagina': f"Confirmar Borrado Asistencia: {persona_nombre}"
    }
    return render(request, 'reportes/borrar_detalle_asistencia.html', context)



#-----------------------------------------------------


@login_required
def add_detalle_asistencia(request, planilla_asistencia_id):
    """
    Añade manualmente un nuevo registro DetalleAsistencia a una
    PlanillaAsistencia existente, buscando al personal por CI o Item.
    """
    planilla_asistencia = get_object_or_404(PlanillaAsistencia, pk=planilla_asistencia_id)

    # Verificar si la app planilla está disponible
    if not PLANILLA_APP_AVAILABLE:
        messages.error(request, "Error interno: Componentes externos no disponibles.")
        return redirect('lista_planillas_asistencia')

    # --- Verificar si la planilla está en estado editable ---
    if planilla_asistencia.estado in ['validado', 'archivado']:
         messages.warning(request, f"No se pueden añadir registros a un reporte que está '{planilla_asistencia.get_estado_display()}'.")
         return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)
    # --- Fin verificación estado ---

    if request.method == 'POST':
        form = AddDetalleAsistenciaForm(request.POST)
        if form.is_valid():
            ci_o_item = form.cleaned_data['ci_o_item'].strip()
            personal_externo_encontrado = None
            personal_externo_id = None

            # --- Buscar en BD Externa ---
            try:
                # Intentar buscar por CI primero
                try:
                    personal_externo_encontrado = PrincipalPersonalExterno.objects.using('personas_db').get(ci__iexact=ci_o_item)
                    personal_externo_id = personal_externo_encontrado.id
                    logger.info(f"Personal encontrado por CI '{ci_o_item}' (ID: {personal_externo_id}) para añadir a PlanillaAsistencia {planilla_asistencia.id}")
                except PrincipalPersonalExterno.DoesNotExist:
                    # Si no se encuentra por CI, intentar buscar por Item (activo)
                    logger.debug(f"No encontrado por CI '{ci_o_item}', buscando por Item...")
                    try:
                        item_num = int(ci_o_item) # Convertir a número para buscar item
                        # Buscamos la designación activa más reciente con ese item
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
                             raise PrincipalPersonalExterno.DoesNotExist # Para el mensaje de error general

                    except (ValueError, TypeError): # Si ci_o_item no es un número válido para item
                         logger.warning(f"'{ci_o_item}' no es un número de Item válido.")
                         raise PrincipalPersonalExterno.DoesNotExist # Para el mensaje de error general
                    except Exception as e_item_search:
                        logger.error(f"Error buscando por Item '{ci_o_item}': {e_item_search}", exc_info=True)
                        raise PrincipalPersonalExterno.DoesNotExist # Error genérico

            except PrincipalPersonalExterno.DoesNotExist:
                messages.error(request, f"No se encontró personal activo en la base de datos externa con el CI o Item '{ci_o_item}'.")
                # Volver a renderizar el form con el error
                return render(request, 'reportes/add_detalle_asistencia.html', {'form': form, 'planilla_asistencia': planilla_asistencia})
            except Exception as e_db_ext:
                 logger.error(f"Error consultando BD externa para CI/Item '{ci_o_item}': {e_db_ext}", exc_info=True)
                 messages.error(request, f"Error al consultar la base de datos externa: {e_db_ext}")
                 return render(request, 'reportes/add_detalle_asistencia.html', {'form': form, 'planilla_asistencia': planilla_asistencia})
            # --- Fin Búsqueda Externa ---


            # --- Si se encontró, verificar duplicado interno ---
            if personal_externo_id:
                if DetalleAsistencia.objects.filter(planilla_asistencia=planilla_asistencia, personal_externo_id=personal_externo_id).exists():
                    messages.warning(request, f"El personal '{personal_externo_encontrado.nombre_completo if personal_externo_encontrado else ci_o_item}' ya existe en este reporte de asistencia.")
                else:
                    # --- Crear el DetalleAsistencia ---
                    try:
                        with transaction.atomic(using='default'): # Asegurar atomicidad
                            nuevo_detalle = DetalleAsistencia(
                                planilla_asistencia=planilla_asistencia,
                                personal_externo_id=personal_externo_id
                                # Los campos de asistencia toman default 0
                            )
                            nuevo_detalle.save()
                            messages.success(request, f"Se añadió exitosamente el registro de asistencia para '{personal_externo_encontrado.nombre_completo if personal_externo_encontrado else ci_o_item}'.")
                            # Redirigir a la vista de detalles de esta planilla
                            return redirect('ver_detalles_asistencia', pk=planilla_asistencia.pk)
                    except Exception as e_save:
                        logger.error(f"Error al guardar nuevo DetalleAsistencia para pers_id {personal_externo_id} en plan_id {planilla_asistencia.id}: {e_save}", exc_info=True)
                        messages.error(request, f"Error al guardar el nuevo registro: {e_save}")

        # Si el form no es válido (solo pasaría si ci_o_item está vacío o es muy largo)
        else:
             messages.error(request, "Por favor, ingrese un CI o Número de Item.")


    # Si es método GET o si hubo algún error que no redirigió
    else:
        form = AddDetalleAsistenciaForm()

    context = {
        'form': form,
        'planilla_asistencia': planilla_asistencia,
        'titulo_pagina': f"Añadir Registro a Reporte {planilla_asistencia}"
    }
    return render(request, 'reportes/add_detalle_asistencia.html', context)
