# planilla/views.py (Versión Original con BD Externa)

import logging
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
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
from decimal import Decimal, InvalidOperation


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



from .forms import DetalleBonoTeForm, PlanillaForm

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
@login_required
def crear_planilla(request, tipo):
    """
    Crea la Planilla (Bono TE) y sus Detalles, obteniendo los datos
    de asistencia desde un Reporte de Asistencia validado.
    """
    # Verificar disponibilidad de apps externas
    if not REPORTES_APP_AVAILABLE:
        messages.error(request, "Error interno: La funcionalidad de reportes de asistencia no está disponible.")
        return redirect('seleccionar_tipo_planilla') # O a un home

    if tipo not in EXTERNAL_TYPE_MAP:
        messages.error(request, f"Tipo de planilla '{tipo}' no es válido.")
        return redirect('seleccionar_tipo_planilla')

    # Consultar planillas para copiar (sin cambios)
    try:
        planillas_para_copiar = Planilla.objects.filter(tipo=tipo).order_by('-anio', '-mes')
    except Exception as e_qs:
         logger.error(f"Error obteniendo 'planillas_para_copiar' para {tipo}: {e_qs}", exc_info=True)
         messages.error(request, "Error interno preparando formulario (copia).")
         return redirect('lista_planillas') # Redirigir a lista principal Bono TE


    if request.method == 'POST':
        planilla_form = PlanillaForm(request.POST)

        if planilla_form.is_valid():
            mes = planilla_form.cleaned_data['mes']
            anio = planilla_form.cleaned_data['anio']

            # Validación Duplicados Planilla Bono TE (sin cambios)
            if Planilla.objects.filter(mes=mes, anio=anio, tipo=tipo).exists():
                messages.warning(request, f"¡Atención! Ya existe planilla Bono TE '{dict(Planilla.TIPO_CHOICES).get(tipo)}' para {mes}/{anio}.")
                # ... (renderizar de nuevo el form con error) ...
                context_duplicado = {
                    'planilla_form': planilla_form, 'tipo': tipo,
                    'planillas_para_copiar': planillas_para_copiar, 'error_duplicado': True
                }
                return render(request, 'planillas/crear_planilla.html', context_duplicado)

            # --- INICIO: Lógica de Integración con Reportes ---
            plan_asistencia_validada = None
            detalles_asistencia_dict = {}

            try:
                # 1. Buscar PlanillaAsistencia VALIDADA para el mismo periodo/tipo
                plan_asistencia_validada = PlanillaAsistencia.objects.get(
                    mes=mes,
                    anio=anio,
                    tipo=tipo,
                    estado='validado' # ¡Solo usar las validadas!
                )
                logger.info(f"Encontrada PlanillaAsistencia validada ID {plan_asistencia_validada.id} para {tipo} {mes}/{anio}.")

                # 2. Cargar sus Detalles de Asistencia en un diccionario para búsqueda rápida
                detalles_asist_qs = DetalleAsistencia.objects.filter(planilla_asistencia=plan_asistencia_validada)
                # Usamos personal_externo_id como clave
                detalles_asistencia_dict = {da.personal_externo_id: da for da in detalles_asist_qs if da.personal_externo_id}
                logger.info(f"Cargados {len(detalles_asistencia_dict)} detalles de asistencia desde el reporte validado.")

            except PlanillaAsistencia.DoesNotExist:
                # --- Manejo de Error: Reporte No Encontrado o No Validado ---
                # Usaremos la Opción A (Estricta): Impedir creación.
                logger.error(f"No se encontró un Reporte de Asistencia VALIDADO para {tipo} {mes}/{anio}.")
                messages.error(request, f"¡Error! No se encontró un Reporte de Asistencia 'Validado' para el periodo {mes}/{anio} y tipo '{dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)}'. "
                                         f"Por favor, cree y valide el reporte de asistencia antes de generar la planilla de Bono TE.")
                # Volver a mostrar el formulario de creación de Bono TE
                context_error_asistencia = {
                    'planilla_form': planilla_form, 'tipo': tipo,
                    'planillas_para_copiar': planillas_para_copiar
                }
                return render(request, 'planillas/crear_planilla.html', context_error_asistencia)

            except Exception as e_asist:
                logger.error(f"Error inesperado buscando/cargando datos de asistencia para {tipo} {mes}/{anio}: {e_asist}", exc_info=True)
                messages.error(request, f"Ocurrió un error al intentar obtener los datos de asistencia validados: {e_asist}")
                context_error_asistencia = {
                    'planilla_form': planilla_form, 'tipo': tipo,
                    'planillas_para_copiar': planillas_para_copiar
                }
                return render(request, 'planillas/crear_planilla.html', context_error_asistencia)
            # --- FIN: Lógica de Integración con Reportes ---


            # Si llegamos aquí, tenemos plan_asistencia_validada y detalles_asistencia_dict listos

            # Iniciar Proceso de Creación Planilla Bono TE
            try:
                with transaction.atomic(using='default'):
                    # 1. Crear Planilla (Cabecera Bono TE)
                    planilla_bonote = planilla_form.save(commit=False)
                    planilla_bonote.usuario_elaboracion = request.user
                    planilla_bonote.tipo = tipo
                    # ¡Importante! Guardar primero la cabecera para tener su PK
                    planilla_bonote.save()
                    logger.info(f"Creada Planilla (Bono TE) ID {planilla_bonote.id} para {tipo} {mes}/{anio}.")

                    # 2. Consultar Personal Externo (igual que antes)
                    target_external_type = EXTERNAL_TYPE_MAP.get(tipo)
                    logger.info(f"Consultando personal externo ACTIVO tipo '{target_external_type}' en 'personas_db'...")
                    designaciones_externas_filtradas = []
                    try:
                        consulta_externa = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .select_related('personal') \
                            .filter(
                                tipo_designacion=target_external_type,
                                estado='ACTIVO'
                            ) \
                            .order_by('personal__apellido_paterno', 'personal__apellido_materno', 'personal__nombre')
                        designaciones_externas_filtradas = list(consulta_externa)
                        logger.info(f"Consulta externa Bono TE ejecutada. Encontradas: {len(designaciones_externas_filtradas)}")
                    except Exception as e_ext:
                        logger.error(f"Error CRÍTICO consultando 'personas_db' para Bono TE ({tipo} {mes}/{anio}): {e_ext}", exc_info=True)
                        # Rollback ocurrirá, pero es bueno poner mensaje específico
                        messages.error(request, f"Se creó cabecera Bono TE (ID:{planilla_bonote.id}), pero ERROR al consultar personal externo: {e_ext}.")
                        raise e_ext # Re-lanzar para rollback

                    # 3. Crear Detalles Bono TE usando Datos de Asistencia
                    detalles_bonote_a_crear = []
                    personas_procesadas = set()
                    personas_sin_asistencia = [] # Para reportar al final

                    if not designaciones_externas_filtradas:
                        messages.warning(request, f"Planilla Bono TE creada (ID: {planilla_bonote.id}), pero no se encontró personal externo ACTIVO para el tipo '{dict(Planilla.TIPO_CHOICES).get(tipo)}'.")
                    else:
                        logger.info(f"Preparando {len(designaciones_externas_filtradas)} potenciales registros DetalleBonoTe...")
                        for designacion in designaciones_externas_filtradas:
                            if designacion.personal and designacion.personal.id not in personas_procesadas:
                                personal_id_actual = designacion.personal.id
                                personas_procesadas.add(personal_id_actual)

                                # --- Buscar datos de asistencia para esta persona ---
                                detalle_asistencia_origen = detalles_asistencia_dict.get(personal_id_actual)

                                if detalle_asistencia_origen:
                                    # --- Crear DetalleBonoTe COPIANDO datos ---
                                    detalle_bt = DetalleBonoTe(
                                        id_planilla=planilla_bonote,
                                        personal_externo_id=personal_id_actual,
                                        mes=planilla_bonote.mes, # Heredar mes de la planilla Bono TE

                                        # Copiar campos de asistencia
                                        faltas=detalle_asistencia_origen.faltas_dias, # Nombre puede diferir
                                        vacacion=detalle_asistencia_origen.vacacion,
                                        viajes=detalle_asistencia_origen.viajes,
                                        bajas_medicas=detalle_asistencia_origen.bajas_medicas,
                                        pcgh=detalle_asistencia_origen.pcgh,
                                        psgh=detalle_asistencia_origen.psgh, # Nombre coincide
                                        perm_excep=detalle_asistencia_origen.perm_excep,
                                        asuetos=detalle_asistencia_origen.asuetos,
                                        pcgh_embar_enf_base=detalle_asistencia_origen.pcgh_embar_enf_base,
                                        abandono_dias=detalle_asistencia_origen.abandono_dias, # Nombre coincide
                                        observaciones_asistencia=detalle_asistencia_origen.observaciones,

                                        # Campos específicos de Bono TE (inicializar o dejar default)
                                        descuentos=Decimal('0'), # O si tienes otra lógica
                                        # Los campos calculados (dias_no_pagados, etc.) se calcularán después
                                    )
                                    detalles_bonote_a_crear.append(detalle_bt)
                                else:
                                    # --- Manejo si NO se encontró asistencia para esta persona ---
                                    logger.warning(f"No se encontró DetalleAsistencia para personal_id {personal_id_actual} en el reporte validado. Se omitirá o creará con ceros para Bono TE.")
                                    personas_sin_asistencia.append(f"{designacion.personal.nombre_completo} (ID: {personal_id_actual})")
                                    # DECISIÓN: ¿Qué hacer?
                                    # Opción 1: Omitir (no añadir a detalles_bonote_a_crear)
                                    # Opción 2: Crear con ceros (como hacía antes)
                                    # detalle_bt = DetalleBonoTe(
                                    #     id_planilla=planilla_bonote,
                                    #     personal_externo_id=personal_id_actual,
                                    #     mes=planilla_bonote.mes,
                                    #     # ... todos los campos de asistencia en 0 ...
                                    # )
                                    # detalles_bonote_a_crear.append(detalle_bt)
                                    # Por ahora, OMITIREMOS para ser consistentes con la obligatoriedad del reporte.

                            elif not designacion.personal:
                                 logger.warning(f"Designación Externa ID {designacion.id} sin personal. Se omite para Bono TE.")

                        # --- Fin Bucle ---

                        if personas_sin_asistencia:
                             # Mensaje de advertencia si algunas personas no tenían asistencia
                             msg_adv = f"Se procesaron {len(detalles_bonote_a_crear)} registros. ADVERTENCIA: No se encontraron datos de asistencia validados para las siguientes personas (no se incluyeron en Bono TE): {', '.join(personas_sin_asistencia[:5])}"
                             if len(personas_sin_asistencia) > 5:
                                 msg_adv += f" y {len(personas_sin_asistencia) - 5} más."
                             messages.warning(request, msg_adv)

                        if detalles_bonote_a_crear:
                            logger.info(f"Intentando crear {len(detalles_bonote_a_crear)} registros DetalleBonoTe en lote...")
                            try:
                                # --- Crear en Lote (SIN llamar a save/calcular_valores) ---
                                DetalleBonoTe.objects.bulk_create(detalles_bonote_a_crear)
                                logger.info(f"Creados {len(detalles_bonote_a_crear)} registros DetalleBonoTe para Planilla {planilla_bonote.id}.")

                                # --- ¡PASO ADICIONAL IMPORTANTE! ---
                                # Recalcular valores para los detalles recién creados
                                logger.info(f"Recalculando valores para {len(detalles_bonote_a_crear)} detalles Bono TE...")
                                detalles_creados_ids = [d.id for d in detalles_bonote_a_crear] # Obtener IDs si bulk_create no los retorna directamente
                                # Si bulk_create retorna objetos (depende de BD y versión Django):
                                # detalles_creados = detalles_bonote_a_crear
                                # Si no, necesitamos recuperarlos:
                                detalles_creados = DetalleBonoTe.objects.filter(id_planilla=planilla_bonote) # O filtrar por IDs

                                detalles_a_actualizar = []
                                for detalle_bt in detalles_creados:
                                    detalle_bt.calcular_valores() # Calcula los campos
                                    detalles_a_actualizar.append(detalle_bt)

                                # Actualizar en lote los campos calculados
                                campos_a_actualizar = ['dias_no_pagados', 'dias_pagados', 'total_ganado', 'liquido_pagable']
                                DetalleBonoTe.objects.bulk_update(detalles_a_actualizar, campos_a_actualizar)
                                logger.info(f"Valores recalculados y actualizados para {len(detalles_a_actualizar)} detalles Bono TE.")
                                # ---------------------------------------

                                messages.success(request, f"Planilla Bono TE {dict(Planilla.TIPO_CHOICES).get(tipo)} {mes}/{anio} creada con {len(detalles_bonote_a_crear)} registros usando datos de asistencia validados.")

                            except IntegrityError as e_bulk:
                                logger.error(f"Error integridad ({e_bulk}) al crear DetalleBonoTe.", exc_info=True)
                                messages.error(request, f"Se creó cabecera Bono TE, ERROR al guardar detalles ({e_bulk}).")
                                raise e_bulk # Rollback
                            # ... (otros manejos de error para bulk_create/bulk_update) ...
                        else:
                             logger.warning(f"No se prepararon detalles DetalleBonoTe (posiblemente por falta de asistencia para todos).")
                             if not personas_sin_asistencia: # Si no hubo advertencia previa
                                 messages.warning(request, "Planilla Bono TE creada, pero no se preparó ningún detalle individual (verificar logs).")

                # Si se llega aquí, la transacción fue exitosa
                return redirect('lista_planillas') # Redirigir a lista Bono TE

            except Exception as e_proc:
                 logger.error(f"Error procesando creación planilla Bono TE {tipo} {mes}/{anio} (post-asistencia): {e_proc}", exc_info=True)
                 if not messages.get_messages(request):
                      messages.error(request, f"Ocurrió un error inesperado durante la creación del Bono TE: {e_proc}")
                 # Rollback ocurrió automáticamente
                 # ¿Redirigir a lista o mostrar form de nuevo? Lista es más seguro.
                 return redirect('lista_planillas')

        else: # Formulario POST NO válido
            logger.warning(f"Formulario creación Planilla Bono TE inválido: {planilla_form.errors.as_json()}")
            messages.error(request, "Formulario contiene errores. Corrígelos.")

    else: # GET
        planilla_form = PlanillaForm() # Formulario vacío

    context_final = {
        'planilla_form': planilla_form,
        'tipo': tipo,
        'planillas_para_copiar': planillas_para_copiar
    }
    return render(request, 'planillas/crear_planilla.html', context_final)


@login_required
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
def editar_planilla(request, planilla_id):
    # Sin cambios si solo edita Planilla
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    if request.method == 'POST':
        form = PlanillaForm(request.POST, instance=planilla)
        if form.is_valid():
            form.save()
            messages.success(request, 'Planilla editada correctamente.')
            return redirect('lista_planillas')
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = PlanillaForm(instance=planilla)
    return render(request, 'planillas/editar_planilla.html', {'form': form, 'planilla': planilla})

@login_required
def borrar_planilla(request, planilla_id):
    # Sin cambios si solo borra Planilla
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    if request.method == 'POST':
        planilla.delete()
        messages.success(request, 'Planilla borrada correctamente.')
        return redirect('lista_planillas')
    return render(request, 'planillas/borrar_planilla.html', {'planilla': planilla})

@login_required
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