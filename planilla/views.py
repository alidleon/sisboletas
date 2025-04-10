from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from datetime import date
from django.contrib import messages
from .forms import DetalleBonoTeForm
from .forms import PlanillaForm  # Necesitas crear un formulario para editar la planilla
from datetime import datetime
from django.core.exceptions import ValidationError
from .models import PrincipalPersonal # ¡Importa el nuevo modelo!

from django.db import transaction, IntegrityError       # Para transacciones y manejo de errores BD
from django.db.models import Q   

from .models import (
    Planilla,
    DetalleBonoTe,
    PrincipalDesignacionExterno,
    PrincipalPersonalExterno, # Ahora necesitamos importar este
    PrincipalCargoExterno      # Y este si accedes a su nombre directamente
)

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
                .select_related('cargo') # Incluir el cargo

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
            return redirect('ver_detalles_bono_te', planilla_id=planilla.id)
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


@login_required
def ver_detalles_bono_te(request, planilla_id):
    # Obtener la Planilla
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    logger.info(f"Viendo detalles para Planilla ID {planilla.id} (Tipo: {planilla.get_tipo_display()})")

    detalles_bono_te_list = []
    try:
        # Obtener Detalles Locales (DetalleBonoTe)
        detalles_bono_te_qs = DetalleBonoTe.objects.filter(id_planilla=planilla).order_by('id')
        detalles_bono_te_list = list(detalles_bono_te_qs)
        logger.info(f"Obtenidos {len(detalles_bono_te_list)} detalles locales para Planilla {planilla.id}")

    except Exception as e_default:
         logger.error(f"Error obteniendo detalles locales para Planilla {planilla.id}: {e_default}", exc_info=True)
         messages.error(request, f"Error al cargar los detalles base de la planilla: {e_default}")
         detalles_bono_te_list = [] # Asegurar lista vacía si falla

    # Recolectar IDs de personal externo para buscar info
    personal_ids = {d.personal_externo_id for d in detalles_bono_te_list if d.personal_externo_id is not None}

    # Diccionarios para información externa
    personal_info = {}
    designaciones_info = {}

    # Consultar Datos Externos (si hay IDs)
    if personal_ids:
        # 1. Consultar Personal Externo
        logger.info(f"Consultando {len(personal_ids)} registros de personal en 'personas_db'...")
        try:
            personal_externo_qs = PrincipalPersonalExterno.objects.using('personas_db') \
                .filter(id__in=personal_ids)
            for persona in personal_externo_qs:
                personal_info[persona.id] = persona
            logger.info(f"Mapeo 'personal_info' creado con {len(personal_info)} entradas para Planilla {planilla.id}.")
        except Exception as e_pers:
            logger.error(f"Error consultando personal externo en 'personas_db' para Planilla {planilla.id}: {e_pers}", exc_info=True)
            messages.warning(request, f"No se pudo obtener info de nombres/CI: {e_pers}.")
            # personal_info se quedará vacío o incompleto

        # 2. Consultar Designaciones Externas (¡CON FILTRO DE ACTIVIDAD!)
        logger.info(f"Consultando designaciones ACTIVAS en 'personas_db' para {len(personal_ids)} IDs...")
        try:
            consulta_desig_externa = PrincipalDesignacionExterno.objects.using('personas_db') \
                .filter(personal_id__in=personal_ids) \
                .select_related('cargo')

            # ----- APLICAR FILTRO DE ESTADO AQUÍ TAMBIÉN -----
            # Para mostrar Item/Cargo de la designación ACTIVA
            estado_activo_valor = 'ACTIVO'
            if hasattr(PrincipalDesignacionExterno, 'estado'):
                consulta_desig_externa = consulta_desig_externa.filter(estado=estado_activo_valor)
                logger.info(f"Aplicado filtro de actividad: estado = '{estado_activo_valor}' al buscar Item/Cargo.")
            else:
                 logger.error("¡¡MODELO SIN CAMPO 'estado'!! No se pudo filtrar designaciones activas para Item/Cargo.")
                 messages.warning(request,"No se pudo filtrar por estado activo al buscar Item/Cargo (campo 'estado' falta en modelo).")
                 # Se continuará sin filtro de estado, podría mostrar datos de designaciones no activas.
            # --------------------------------------------------

            # ----- (Opcional) Filtro por Tipo -----
            # Si una persona pudiera tener múltiples designaciones ACTIVAS de diferentes tipos,
            # y quisieras mostrar solo la info de la designación del tipo de la planilla.
            # external_type = EXTERNAL_TYPE_MAP.get(planilla.tipo) # Necesitarías EXTERNAL_TYPE_MAP aquí también
            # if external_type and hasattr(PrincipalDesignacionExterno, 'tipo_designacion'):
            #    consulta_desig_externa = consulta_desig_externa.filter(tipo_designacion=external_type)
            #    logger.info(f"Aplicado filtro por tipo '{external_type}' al buscar Item/Cargo.")
            # --------------------------------------

            designaciones_externas = list(consulta_desig_externa)
            logger.info(f"Consulta designaciones externas devolvió {len(designaciones_externas)} registros activos.")
            # Crear mapeo (puede sobrescribir si hay múltiples designaciones activas para la misma persona)
            for desig in designaciones_externas:
                designaciones_info[desig.personal_id] = {
                    'item': desig.item,
                    'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A'
                }
            logger.info(f"Mapeo 'designaciones_info' creado con {len(designaciones_info)} entradas para Planilla {planilla.id}.")
        except Exception as e_desig:
            logger.error(f"Error consultando designaciones externas en 'personas_db' para Planilla {planilla.id}: {e_desig}", exc_info=True)
            messages.warning(request, f"No se pudo obtener la información de item/cargo: {e_desig}.")
            # designaciones_info se quedará vacío o incompleto

    # 3. Enriquecer los detalles locales con la info externa
    detalles_enriquecidos = []
    logger.info(f"Iniciando enriquecimiento para {len(detalles_bono_te_list)} detalles...")
    for detalle in detalles_bono_te_list:
        # Obtener datos de los mapeos (serán None/vacío si hubo error o no se encontró)
        persona_obj = personal_info.get(detalle.personal_externo_id)
        info_designacion_dict = designaciones_info.get(detalle.personal_externo_id)

        # Extraer valores para la plantilla (con manejo de None/errores)
        item_val = info_designacion_dict.get('item', 'N/A') if info_designacion_dict else 'N/A'
        cargo_val = info_designacion_dict.get('cargo', 'N/A') if info_designacion_dict else 'N/A'
        ci_val = 'N/A'
        nombre_val = 'Personal no encontrado' # Valor por defecto más informativo

        if persona_obj:
            try:
                ci_val = persona_obj.ci if hasattr(persona_obj, 'ci') else 'Sin CI'
                nombre_val = persona_obj.nombre_completo if hasattr(persona_obj, 'nombre_completo') else 'Sin NombreC'
            except AttributeError as e_attr_pers:
                logger.warning(f"AttributeError al acceder a datos de Persona ID {detalle.personal_externo_id}: {e_attr_pers}")
                ci_val = 'Error Attr'
                nombre_val = 'Error Attr'

        # Añadir atributos directamente al objeto 'detalle' para usar en la plantilla
        detalle.persona_externa_obj = persona_obj # Útil si necesitas más datos de la persona en la plantilla
        detalle.item_externo = item_val
        detalle.cargo_externo = cargo_val
        detalle.ci_externo = ci_val
        detalle.nombre_completo_externo = nombre_val

        detalles_enriquecidos.append(detalle)

    logger.info(f"Enriquecimiento terminado. {len(detalles_enriquecidos)} detalles enriquecidos.")

    # 4. Opcional: Re-ordenar la lista final
    try:
        detalles_enriquecidos.sort(key=lambda d: (
            getattr(d.persona_externa_obj, 'apellido_paterno', '') or '',
            getattr(d.persona_externa_obj, 'apellido_materno', '') or '',
            getattr(d.persona_externa_obj, 'nombre', '') or ''
        ))
    except Exception as e_sort:
        logger.warning(f"No se pudo re-ordenar la lista de detalles para Planilla {planilla.id}: {e_sort}")

    # 5. Preparar Contexto y Renderizar
    context = {
        'planilla': planilla,
        'detalles_bono_te': detalles_enriquecidos, # Pasar la lista final
    }
    # logger.debug(f"Contexto final listo. 'detalles_bono_te' tiene {len(detalles_enriquecidos)} elementos.") # Log opcional

    try:
        return render(request, 'planillas/ver_detalles_bono_te.html', context)
    except Exception as e_render:
         logger.error(f"Error renderizando plantilla ver_detalles_bono_te para Planilla {planilla.id}: {e_render}", exc_info=True)
         messages.error(request,"Ocurrió un error al intentar mostrar la página de detalles.")
         return redirect('lista_planillas') # O a otra página segura
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
from django.shortcuts import render
from django.http import HttpResponse
from .models import PrincipalDesignacionExterno # Solo necesitamos este modelo externo aquí
import logging

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