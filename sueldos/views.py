# sueldos/views.py (COMPLETO Y MODIFICADO)

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import PlanillaSueldo, DetalleSueldo
from .forms import CrearPlanillaSueldoForm, EditarPlanillaSueldoForm, SubirExcelSueldosForm, EditarDetalleSueldoForm
from decimal import Decimal, InvalidOperation # Importar Decimal e InvalidOperation
from .utils import get_processed_sueldo_details # Importar la nueva utilidad
from django.urls import reverse
from urllib.parse import urlencode

# --- Importar modelos externos y librerías ---
try:
    from planilla.models import PrincipalPersonalExterno, PrincipalDesignacionExterno
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    PrincipalDesignacionExterno = None
    PrincipalPersonalExterno = None
    PLANILLA_APP_AVAILABLE = False
    logging.error("SUELDOS VIEWS: No se pudo importar PrincipalPersonalExterno.")

try:
    import pandas as pd # Importar pandas
    from openpyxl.utils.exceptions import InvalidFileException # Para error de archivo corrupto
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.error("SUELDOS VIEWS: La librería 'pandas' no está instalada.")

logger = logging.getLogger(__name__)

# --- Vistas para la Cabecera (PlanillaSueldo) ---
# (Estas vistas permanecen igual que antes)
@login_required
def crear_planilla_sueldo(request):
    if request.method == 'POST':
        # Usar el nuevo forms.Form
        form = CrearPlanillaSueldoForm(request.POST)
        if form.is_valid():
            # Extraer datos
            mes = form.cleaned_data['mes']
            anio = form.cleaned_data['anio']
            tipo = form.cleaned_data['tipo']
            observaciones = form.cleaned_data['observaciones']

            # Verificar duplicados ANTES de crear
            if PlanillaSueldo.objects.filter(mes=mes, anio=anio, tipo=tipo).exists():
                messages.warning(request, f"Ya existe una planilla de sueldos para {dict(PlanillaSueldo.TIPO_CHOICES).get(tipo)} {mes}/{anio}.")
            else:
                try:
                    # Crear instancia manualmente
                    planilla = PlanillaSueldo(
                        mes=mes,
                        anio=anio,
                        tipo=tipo,
                        observaciones=observaciones,
                        estado='borrador', # Estado inicial por defecto
                        usuario_creacion=request.user
                    )
                    planilla.save() # Guardar el objeto
                    messages.success(request, f"Planilla de sueldos para {planilla.get_tipo_display()} {mes}/{anio} creada. Ahora puedes cargar el archivo Excel.")
                    return redirect('subir_excel_sueldos', planilla_id=planilla.pk)
                except Exception as e:
                    logger.error(f"Error creando PlanillaSueldo: {e}", exc_info=True)
                    messages.error(request, f"Error inesperado al crear la planilla: {e}")
        else:
             messages.error(request, "El formulario contiene errores.")
    else: # GET
        # Usar el nuevo forms.Form
        form = CrearPlanillaSueldoForm()

    context = {
        'form': form,
        'titulo_pagina': 'Crear Nueva Planilla de Sueldos'
    }
    return render(request, 'sueldos/crear_planilla_sueldo.html', context)


@login_required
def lista_planillas_sueldo(request):
    planillas = PlanillaSueldo.objects.all().order_by('-anio', '-mes', 'tipo')
    context = {
        'planillas_sueldo': planillas,
        'titulo_pagina': 'Planillas de Sueldos Generadas'
    }
    return render(request, 'sueldos/lista_planillas_sueldo.html', context)

# --- Vista Principal ACTUALIZADA: Carga y Procesamiento del Excel con Pandas ---
@login_required
def subir_excel_sueldos(request, planilla_id):
    planilla = get_object_or_404(PlanillaSueldo, pk=planilla_id)

    # Verificar dependencias cruciales
    if not PLANILLA_APP_AVAILABLE:
        messages.error(request, "Error crítico: Componente de personal ('planilla') no disponible.")
        return redirect('lista_planillas_sueldo')
    if not PANDAS_AVAILABLE:
        messages.error(request, "Error crítico: Librería 'pandas' no instalada. Ejecuta 'pip install pandas openpyxl'.")
        return redirect('lista_planillas_sueldo')

    # Validar estado de la planilla
    if planilla.estado not in ['borrador', 'error_carga']:
        messages.warning(request, f"La planilla {planilla} ya tiene un estado '{planilla.get_estado_display()}' y no se puede volver a cargar el Excel.")
        # Considera redirigir a una vista de detalles si existe
        return redirect('lista_planillas_sueldo')

    if request.method == 'POST':
        form = SubirExcelSueldosForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['archivo_excel']
            logger.info(f"Archivo Excel '{excel_file.name}' recibido para PlanillaSueldo ID {planilla.id}")

            # --- Variables para el procesamiento ---
            errores_carga = []
            advertencias_carga = []
            filas_leidas_excel = 0
            filas_procesadas_ok = 0
            filas_omitidas_personal = 0
            filas_omitidas_datos = 0
            filas_omitidas_formato = 0 # Renombrado para claridad
            detalles_a_crear = []
            personal_procesado_en_archivo = set()

            try:
                # --- LEER EXCEL CON PANDAS ---
                df = pd.read_excel(excel_file, sheet_name=0, header=None, dtype=str)
                filas_leidas_excel = len(df)
                logger.info(f"Pandas leyó {filas_leidas_excel} filas del Excel.")

                # --- MAPEADO DE COLUMNAS (Índice basado en 0) CORREGIDO ---
                COL_ITEM = 0         # Columna A
                COL_CI = 1         # Columna B
                COL_NOMBRE = 2     # Columna C
                COL_CARGO = 3      # Columna D
                COL_FECHA_ING = 4  # Columna E
                COL_DIAS_TRAB = 5  # Columna F
                COL_HABER_BASICO = 6 # Columna G
                COL_CATEGORIA = 7    # Columna H
                COL_TOTAL_GANADO = 8 # Columna I
                COL_RC_IVA = 9     # Columna J
                COL_GESTORA = 10    # Columna K
                COL_APORTE_SOL = 11 # Columna L
                COL_COOP = 12       # Columna M
                COL_FALTAS = 13     # Columna N
                COL_MEMOS = 14      # Columna O
                COL_OTROS_DESC = 15 # Columna P
                COL_TOTAL_DESC = 16 # Columna Q
                COL_LIQUIDO = 17    # Columna R

                # Fila donde empiezan los datos REALES (índice basado en 0)
                FILA_INICIO_DATOS = 11 # Fila 12 del Excel

                # --- PROCESAR FILAS DEL DATAFRAME ---
                for indice_fila, fila in df.iloc[FILA_INICIO_DATOS:].iterrows():
                    numero_fila_excel = indice_fila + 1

                    # --- Validar y Limpiar Fila ---
                    ci_excel_raw = fila.iloc[COL_CI]
                    if pd.isna(ci_excel_raw) or str(ci_excel_raw).strip() == "":
                        filas_omitidas_formato += 1
                        continue # Saltar fila vacía o sin CI

                    item_raw = fila.iloc[COL_ITEM]
                    if pd.isna(item_raw) or not str(item_raw).strip().isdigit():
                        if pd.isna(fila.iloc[COL_NOMBRE]): # Doble chequeo si no hay Item ni Nombre
                            filas_omitidas_formato += 1
                            logger.debug(f"Fila {numero_fila_excel}: Omitida, parece subtotal o vacía.")
                            continue # Saltar fila de subtotal/formato

                    ci_excel = str(ci_excel_raw).strip()

                    # --- Buscar Personal Externo por CI ---
                    personal_externo = None
                    try:
                        # Usar filtro exacto (case-insensitive si es necesario en tu BD)
                        personal_externo = PrincipalPersonalExterno.objects.using('personas_db').get(ci__iexact=ci_excel)
                    except PrincipalPersonalExterno.DoesNotExist:
                        msg = f"Fila {numero_fila_excel}: Omitida (Personal CI '{ci_excel}' NO encontrado en BD externa)."
                        logger.warning(msg)
                        errores_carga.append(msg)
                        filas_omitidas_personal += 1
                        continue
                    except Exception as e_db:
                        msg = f"Fila {numero_fila_excel}: Omitida (Error BD buscando CI '{ci_excel}': {e_db})."
                        logger.error(msg, exc_info=True)
                        errores_carga.append(msg)
                        filas_omitidas_personal += 1
                        continue

                    # --- Verificar Duplicados en el Archivo ---
                    if personal_externo.id in personal_procesado_en_archivo:
                        msg = f"Fila {numero_fila_excel}: Omitida (ADVERTENCIA: Personal CI '{ci_excel}' duplicado en este archivo)."
                        logger.warning(msg)
                        advertencias_carga.append(msg)
                        filas_omitidas_datos += 1
                        continue
                    personal_procesado_en_archivo.add(personal_externo.id)

                    # --- Extraer y Convertir Datos de Columnas ---
                    try:
                        # Funciones auxiliares (igual que antes)
                        def safe_to_decimal(value, default=Decimal('0.00')):
                            if pd.isna(value) or value is None or str(value).strip() == '': return default
                            try: return Decimal(value)
                            except (InvalidOperation, ValueError, TypeError):
                                try:
                                    clean_val = str(value).replace('$', '').replace('Bs', '').replace('.', '').replace(',', '.').strip()
                                    return Decimal(clean_val)
                                except (InvalidOperation, ValueError, TypeError):
                                    logger.warning(f"Fila {numero_fila_excel}, CI {ci_excel}: No se pudo convertir '{value}' a Decimal.")
                                    advertencias_carga.append(f"Fila {numero_fila_excel} (CI: {ci_excel}): Valor '{value}' no es decimal válido.")
                                    return default # Retorna default pero registra advertencia

                        def safe_to_date(value):
                            if pd.isna(value) or value is None: return None
                            try:
                                if isinstance(value, pd.Timestamp): return value.date()
                                return pd.to_datetime(value).date()
                            except (ValueError, TypeError):
                                logger.warning(f"Fila {numero_fila_excel}, CI {ci_excel}: No se pudo convertir '{value}' a Fecha.")
                                advertencias_carga.append(f"Fila {numero_fila_excel} (CI: {ci_excel}): Valor '{value}' no es fecha válida.")
                                return None

                        # Mapeo y Conversión usando las COL_* correctas
                        dias_t = safe_to_decimal(fila.iloc[COL_DIAS_TRAB])
                        haber_b = safe_to_decimal(fila.iloc[COL_HABER_BASICO])
                        cat = safe_to_decimal(fila.iloc[COL_CATEGORIA])
                        total_g = safe_to_decimal(fila.iloc[COL_TOTAL_GANADO])
                        rc_iva = safe_to_decimal(fila.iloc[COL_RC_IVA])
                        gestora = safe_to_decimal(fila.iloc[COL_GESTORA])
                        aporte_sol = safe_to_decimal(fila.iloc[COL_APORTE_SOL])
                        coop = safe_to_decimal(fila.iloc[COL_COOP])
                        desc_faltas = safe_to_decimal(fila.iloc[COL_FALTAS])
                        desc_memos = safe_to_decimal(fila.iloc[COL_MEMOS])
                        otros_d = safe_to_decimal(fila.iloc[COL_OTROS_DESC])
                        total_d = safe_to_decimal(fila.iloc[COL_TOTAL_DESC])
                        liquido = safe_to_decimal(fila.iloc[COL_LIQUIDO])

                        item_ref = fila.iloc[COL_ITEM]
                        item_ref_int = int(item_ref) if pd.notna(item_ref) and str(item_ref).strip().isdigit() else None
                        if pd.notna(item_ref) and item_ref_int is None: # Si había algo pero no era dígito
                             advertencias_carga.append(f"Fila {numero_fila_excel} (CI: {ci_excel}): Item '{item_ref}' no es numérico.")


                        nombre_ref = fila.iloc[COL_NOMBRE]
                        nombre_ref_str = str(nombre_ref).strip() if pd.notna(nombre_ref) else None

                        cargo_ref = fila.iloc[COL_CARGO]
                        cargo_ref_str = str(cargo_ref).strip() if pd.notna(cargo_ref) else None

                        fecha_ing_ref = safe_to_date(fila.iloc[COL_FECHA_ING])

                        # --- Crear Instancia DetalleSueldo ---
                        detalle = DetalleSueldo(
                            planilla_sueldo=planilla,
                            personal_externo_id=personal_externo.id,
                            dias_trab=dias_t,
                            haber_basico=haber_b,
                            categoria=cat,
                            total_ganado=total_g,
                            rc_iva_retenido=rc_iva,
                            gestora_publica=gestora,
                            aporte_nac_solidario=aporte_sol,
                            cooperativa=coop,
                            faltas=desc_faltas,
                            memorandums=desc_memos,
                            otros_descuentos=otros_d,
                            total_descuentos=total_d,
                            liquido_pagable=liquido,
                            item_referencia=item_ref_int,
                            nombre_completo_referencia=nombre_ref_str,
                            cargo_referencia=cargo_ref_str,
                            fecha_ingreso_referencia=fecha_ing_ref,
                            fila_excel=numero_fila_excel
                        )
                        detalles_a_crear.append(detalle)
                        filas_procesadas_ok += 1

                    except Exception as e_parse:
                        msg = f"Fila {numero_fila_excel}: Omitida (Error procesando datos para CI '{ci_excel}': {e_parse})."
                        logger.error(msg, exc_info=False)
                        errores_carga.append(msg)
                        filas_omitidas_datos += 1
                        personal_procesado_en_archivo.discard(personal_externo.id)
                        continue

                # --- Fin Bucle Filas ---
                logger.info(f"Procesamiento Excel finalizado. {filas_procesadas_ok} filas OK, "
                            f"{filas_omitidas_personal} omitidas (personal), "
                            f"{filas_omitidas_datos} omitidas (datos/duplicado), "
                            f"{filas_omitidas_formato} omitidas (formato).")

            except InvalidFileException:
                logger.error(f"Error cargando archivo Excel '{excel_file.name}' para Planilla {planilla.id}. Formato inválido.", exc_info=True)
                messages.error(request, "El archivo Excel parece estar corrupto o no es un formato .xlsx válido.")
                return redirect('subir_excel_sueldos', planilla_id=planilla.id)
            except Exception as e_general:
                logger.error(f"Error inesperado procesando Excel '{excel_file.name}' para Planilla {planilla.id}: {e_general}", exc_info=True)
                messages.error(request, f"Ocurrió un error inesperado al procesar el archivo: {e_general}")
                planilla.estado = 'error_carga'
                planilla.observaciones = f"Error General Procesando: {e_general}\n" + "\n".join(errores_carga[:5])
                planilla.save()
                return redirect('subir_excel_sueldos', planilla_id=planilla.id)

            # --- Guardar Resultados en Base de Datos ---
            if detalles_a_crear:
                try:
                    with transaction.atomic(using='default'):
                        detalles_antiguos = DetalleSueldo.objects.filter(planilla_sueldo=planilla)
                        if detalles_antiguos.exists():
                            count_deleted = detalles_antiguos.delete()[0]
                            logger.info(f"{count_deleted} detalles antiguos para PlanillaSueldo ID {planilla.id} borrados.")

                        DetalleSueldo.objects.bulk_create(detalles_a_crear)
                        logger.info(f"{len(detalles_a_crear)} nuevos detalles de sueldo creados para Planilla ID {planilla.id}.")

                        planilla.estado = 'cargado'
                        planilla.fecha_carga_excel = timezone.now()
                        planilla.archivo_excel_cargado.save(excel_file.name, excel_file, save=False)

                        obs_resumen = f"Carga Excel ({timezone.now().strftime('%Y-%m-%d %H:%M')}):\n"
                        obs_resumen += f"- Filas procesadas OK: {filas_procesadas_ok}\n"
                        if filas_omitidas_personal > 0: obs_resumen += f"- Omitidas (Personal no encontrado): {filas_omitidas_personal}\n"
                        if filas_omitidas_datos > 0: obs_resumen += f"- Omitidas (Datos inválidos/Duplicados): {filas_omitidas_datos}\n"
                        if filas_omitidas_formato > 0: obs_resumen += f"- Omitidas (Formato/Subtotal/Blanco): {filas_omitidas_formato}\n"

                        if advertencias_carga:
                             obs_resumen += "\nAdvertencias (Primeras 5):\n" + "\n".join(advertencias_carga[:5]) + ("\n..." if len(advertencias_carga) > 5 else "")
                        if errores_carga:
                             obs_resumen += "\nErrores (Primeros 5):\n" + "\n".join(errores_carga[:5]) + ("\n..." if len(errores_carga) > 5 else "")

                        planilla.observaciones = obs_resumen
                        planilla.save()

                    messages.success(request, f"Archivo Excel procesado exitosamente. Se cargaron {filas_procesadas_ok} registros.")
                    if advertencias_carga or errores_carga:
                        num_problemas = len(advertencias_carga) + len(errores_carga)
                        messages.warning(request, f"Se encontraron {num_problemas} advertencias/errores durante la carga (ver observaciones).")

                    return redirect('lista_planillas_sueldo') # Redirigir a la lista después de cargar

                except IntegrityError as e_int:
                    logger.error(f"Error de integridad guardando detalles Planilla {planilla.id}: {e_int}", exc_info=True)
                    messages.error(request, f"Error de base de datos: {e_int}. Verifique CIs duplicados o problemas de datos.")
                    planilla.estado = 'error_carga'; planilla.observaciones = f"Error Integridad BD: {e_int}"; planilla.save()
                except Exception as e_save:
                    logger.error(f"Error guardando detalles/planilla {planilla.id}: {e_save}", exc_info=True)
                    messages.error(request, f"Error inesperado al guardar los resultados: {e_save}")
                    planilla.estado = 'error_carga'; planilla.observaciones = f"Error Guardando BD: {e_save}"; planilla.save()
            else:
                messages.error(request, "No se procesó ningún registro válido del archivo Excel.")
                if errores_carga or advertencias_carga: messages.warning(request, f"Se encontraron {len(errores_carga) + len(advertencias_carga)} problemas.")
                planilla.estado = 'error_carga'
                obs_error = "Ninguna fila procesada exitosamente.\n"
                if advertencias_carga: obs_error += "\nAdvertencias:\n" + "\n".join(advertencias_carga[:5]) + ("..." if len(advertencias_carga)>5 else "")
                if errores_carga: obs_error += "\nErrores:\n" + "\n".join(errores_carga[:5]) + ("..." if len(errores_carga)>5 else "")
                planilla.observaciones = obs_error
                planilla.save()

            return redirect('subir_excel_sueldos', planilla_id=planilla.id) # Redirigir de vuelta si hubo error al guardar o no había datos

        else:
            messages.error(request, "Error en el formulario. Asegúrate de seleccionar un archivo .xlsx.")

    # Método GET
    else:
        form = SubirExcelSueldosForm()

    context = {
        'form': form,
        'planilla_sueldo': planilla,
        'titulo_pagina': f'Cargar Excel Sueldos - {planilla}'
    }
    return render(request, 'sueldos/subir_excel.html', context)

# sueldos/views.py
# ... (importaciones existentes: logging, render, redirect, get_object_or_404, etc.)
# ... (importar PlanillaSueldo, PlanillaSueldoForm, SubirExcelSueldosForm)

# --- Vistas para la Cabecera (PlanillaSueldo) ---
# ... (vista crear_planilla_sueldo y lista_planillas_sueldo como antes) ...

@login_required
def editar_planilla_sueldo(request, planilla_id):
    planilla = get_object_or_404(PlanillaSueldo, pk=planilla_id)
    if request.method == 'POST':
        # Usar el nuevo ModelForm de edición (que NO incluye 'tipo')
        form = EditarPlanillaSueldoForm(request.POST, instance=planilla)
        if form.is_valid():
            # Verificar duplicados (basado en mes/año del form y tipo original)
            mes = form.cleaned_data['mes']
            anio = form.cleaned_data['anio']
            tipo_original = planilla.tipo

            if PlanillaSueldo.objects.filter(mes=mes, anio=anio, tipo=tipo_original).exclude(pk=planilla.pk).exists():
                 messages.error(request, f"Ya existe otra planilla para {planilla.get_tipo_display()} {mes}/{anio}.")
            else:
                try:
                    # Guardar los campos incluidos en el form ('mes', 'anio', 'estado', 'observaciones')
                    planilla_editada = form.save()
                    messages.success(request, f"Planilla '{planilla_editada}' actualizada.")
                    return redirect('lista_planillas_sueldo')
                except Exception as e:
                    logger.error(f"Error guardando edición de PlanillaSueldo ID {planilla_id}: {e}", exc_info=True)
                    messages.error(request, f"Ocurrió un error al guardar: {e}")
        else:
            messages.error(request, "El formulario contiene errores.")
    else: # GET
        # Usar el nuevo ModelForm de edición
        form = EditarPlanillaSueldoForm(instance=planilla)

    context = {
        'form': form,
        'planilla': planilla, # Pasar la planilla para mostrar info estática
        'titulo_pagina': f"Editar Planilla Sueldos - {planilla}"
    }
    return render(request, 'sueldos/editar_planilla_sueldo.html', context)




@login_required
def borrar_planilla_sueldo(request, planilla_id):
    """ Permite borrar una PlanillaSueldo (cabecera) y sus detalles asociados. """
    planilla = get_object_or_404(PlanillaSueldo, pk=planilla_id)
    # Guardar datos para el mensaje antes de borrar
    planilla_str = str(planilla)
    # Contar detalles asociados (CASCADE los borrará automáticamente)
    num_detalles = planilla.detalles_sueldo.count()

    # No permitir borrar si ya está en estados avanzados (opcional)
    # if planilla.estado in ['pagado', 'archivado']:
    #     messages.warning(request, f"No se puede borrar una planilla en estado '{planilla.get_estado_display()}'.")
    #     return redirect('lista_planillas_sueldo')

    if request.method == 'POST':
        try:
            # Eliminar la planilla. CASCADE se encargará de los DetalleSueldo.
            planilla.delete()
            messages.success(request, f"Planilla '{planilla_str}' y sus {num_detalles} detalles asociados han sido borrados exitosamente.")
            return redirect('lista_planillas_sueldo') # Volver a la lista
        except Exception as e_del:
            logger.error(f"Error borrando PlanillaSueldo ID {planilla_id}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar la planilla: {e_del}")
            # Redirigir de vuelta a la lista incluso si hay error
            return redirect('lista_planillas_sueldo')

    # Si es método GET, mostrar la página de confirmación
    context = {
        'planilla': planilla,
        'num_detalles': num_detalles, # Para mostrar en la confirmación
        'titulo_pagina': f"Confirmar Borrado: {planilla}"
    }
    return render(request, 'sueldos/borrar_planilla_sueldo.html', context)



# --- Vistas Pendientes ---
# ... (código comentado para ver_detalles_sueldo, etc.) ...


@login_required
def ver_detalles_sueldo(request, planilla_id):
    """ Muestra los detalles de sueldo filtrados y enriquecidos para una planilla. """
    logger.debug(f"Vista ver_detalles_sueldo llamada para planilla_id={planilla_id}")
    try:
        # 1. Obtener todos los datos procesados desde la utilidad
        processed_data = get_processed_sueldo_details(request, planilla_id)

        # 2. Manejar errores fatales (planilla no encontrada)
        if processed_data.get('error_message') and not processed_data.get('planilla_sueldo'):
            messages.error(request, processed_data['error_message'])
            return redirect('lista_planillas_sueldo')

        # 3. Mostrar warnings por errores no fatales (ej: error cargando secretarías)
        elif processed_data.get('error_message'):
             messages.warning(request, processed_data['error_message'])

        # 4. Preparar contexto final para la plantilla
        # (Añadir form_edit si implementas edición rápida más adelante)
        context = {
            # Datos de la cabecera y filtros (vienen de processed_data)
            'planilla_sueldo': processed_data.get('planilla_sueldo'),
            'all_secretarias': processed_data.get('all_secretarias', []),
            'unidades_for_select': processed_data.get('unidades_for_select', []),
            'selected_secretaria_id': processed_data.get('selected_secretaria_id'),
            'selected_unidad_id': processed_data.get('selected_unidad_id'),
            'search_term': processed_data.get('search_term', ''),
            'search_active': processed_data.get('search_active', False),

            # La lista de detalles enriquecidos
            'detalles_sueldo': processed_data.get('detalles_sueldo', []),

            # Datos para JS si hay edición rápida (ejemplo)
            # 'visible_ids_list': processed_data.get('detalle_ids_order', []),
            # 'form_edit': DetalleSueldoForm() # Si creas este form

            'titulo_pagina': f"Detalles Sueldos - {processed_data.get('planilla_sueldo')}" if processed_data.get('planilla_sueldo') else "Detalles Sueldos"
        }

        # 5. Renderizar la plantilla (que crearemos a continuación)
        return render(request, 'sueldos/ver_detalles_sueldo.html', context)

    # Manejo de excepciones generales en la vista
    except Exception as e_view:
        logger.error(f"Error inesperado en vista ver_detalles_sueldo ID {planilla_id}: {e_view}", exc_info=True)
        messages.error(request, "Ocurrió un error inesperado al mostrar los detalles de sueldo.")
        return redirect('lista_planillas_sueldo')





@login_required
def editar_detalle_sueldo(request, detalle_id):
    """ Permite editar los campos de un DetalleSueldo existente, preservando filtros al redirigir. """
    detalle = get_object_or_404(
        DetalleSueldo.objects.select_related('planilla_sueldo'),
        pk=detalle_id
    )
    planilla_sueldo = detalle.planilla_sueldo

    # Obtener información externa para mostrar
    persona_externa = None
    item_cargo_externo = {"item": "N/A", "cargo": "N/A"}
    if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
        try:
            persona_externa = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
            designacion = PrincipalDesignacionExterno.objects.using('personas_db') \
                .select_related('cargo') \
                .filter(personal_id=detalle.personal_externo_id, estado='ACTIVO') \
                .order_by('-id').first()
            if designacion:
                item_cargo_externo["item"] = designacion.item if designacion.item is not None else 'N/A'
                item_cargo_externo["cargo"] = designacion.cargo.nombre_cargo if designacion.cargo else 'N/A'
        except PrincipalPersonalExterno.DoesNotExist:
            logger.warning(f"Personal externo ID {detalle.personal_externo_id} no encontrado (Editar Detalle Sueldo)")
        except Exception as e_ext:
            logger.error(f"Error consultando datos externos para DetalleSueldo ID {detalle_id}: {e_ext}", exc_info=True)
            # No añadir mensaje flash aquí para no interferir con mensajes de formulario

    # --- CONSTRUIR URL DE RETORNO (para Cancelar y Éxito) ---
    # Usar los parámetros GET que llegaron a esta vista de edición
    redirect_params = {
        'secretaria': request.GET.get('secretaria', ''),
        'unidad': request.GET.get('unidad', ''),
        'q': request.GET.get('q', ''),
    }
    if request.GET.get('buscar'): # Preservar el flag 'buscar'
        redirect_params['buscar'] = 'true'
    redirect_params = {k: v for k, v in redirect_params.items() if v} # Limpiar vacíos

    base_url = reverse('ver_detalles_sueldo', kwargs={'planilla_id': planilla_sueldo.pk})
    if redirect_params:
        query_string = urlencode(redirect_params)
        return_url = f"{base_url}?{query_string}"
    else:
        return_url = base_url
    # --- FIN CONSTRUCCIÓN URL RETORNO ---

    if request.method == 'POST':
        form = EditarDetalleSueldoForm(request.POST, instance=detalle)
        if form.is_valid():
            try:
                detalle_guardado = form.save()
                # Obtener nombre para mensaje (reutilizando lógica)
                nombre_display = persona_externa.nombre_completo if persona_externa else f"ID Externo {detalle_guardado.personal_externo_id}"
                messages.success(request, f"Detalle de sueldo para '{nombre_display}' actualizado.")
                # Redirigir a la URL de retorno construida
                return redirect(return_url)
            except Exception as e_save:
                logger.error(f"Error guardando DetalleSueldo ID {detalle_id}: {e_save}", exc_info=True)
                messages.error(request, f"Ocurrió un error al guardar los cambios: {e_save}")
                # Si hay error, se renderiza el form de nuevo abajo
        else:
            messages.error(request, "El formulario contiene errores. Por favor, corrígelos.")
            # El form con errores se renderiza abajo
    else: # Método GET
        form = EditarDetalleSueldoForm(instance=detalle)

    context = {
        'form': form,
        'detalle': detalle,
        'planilla_sueldo': planilla_sueldo,
        'persona_externa': persona_externa,
        'item_externo': item_cargo_externo["item"],
        'cargo_externo': item_cargo_externo["cargo"],
        'cancel_url': return_url, # <-- Pasar URL para botón Cancelar
        'titulo_pagina': f"Editar Detalle Sueldo - {persona_externa.nombre_completo if persona_externa else f'ID Ext {detalle.personal_externo_id}'}"
    }
    return render(request, 'sueldos/editar_detalle_sueldo.html', context)



@login_required
def borrar_detalle_sueldo(request, detalle_id):
    """ Permite borrar un registro DetalleSueldo específico, preservando filtros al redirigir. """
    detalle = get_object_or_404(
        DetalleSueldo.objects.select_related('planilla_sueldo'),
        pk=detalle_id
    )
    planilla_sueldo = detalle.planilla_sueldo
    planilla_sueldo_id = planilla_sueldo.pk # Guardar ID antes de posible borrado

    # Obtener nombre para el mensaje de confirmación
    persona_nombre = f"ID Externo {detalle.personal_externo_id}" # Fallback
    if PLANILLA_APP_AVAILABLE and detalle.personal_externo_id:
        try:
            persona = PrincipalPersonalExterno.objects.using('personas_db').get(pk=detalle.personal_externo_id)
            persona_nombre = persona.nombre_completo or persona_nombre
        except Exception:
            pass # Ignorar errores al obtener nombre para el mensaje

    # --- CONSTRUIR URL DE RETORNO (para Cancelar y Éxito) ---
    # Usar los parámetros GET que llegaron a esta vista de borrado
    redirect_params = {
        'secretaria': request.GET.get('secretaria', ''),
        'unidad': request.GET.get('unidad', ''),
        'q': request.GET.get('q', ''),
    }
    if request.GET.get('buscar'):
        redirect_params['buscar'] = 'true'
    redirect_params = {k: v for k, v in redirect_params.items() if v}

    base_url = reverse('ver_detalles_sueldo', kwargs={'planilla_id': planilla_sueldo_id})
    if redirect_params:
        query_string = urlencode(redirect_params)
        return_url = f"{base_url}?{query_string}"
    else:
        return_url = base_url
    # --- FIN CONSTRUCCIÓN URL RETORNO ---

    if request.method == 'POST':
        try:
            nombre_para_mensaje = persona_nombre # Guardar antes de borrar
            detalle.delete()
            messages.success(request, f"Detalle de sueldo para '{nombre_para_mensaje}' borrado exitosamente.")
            # Redirigir a la URL de retorno construida
            return redirect(return_url)
        except Exception as e_del:
             logger.error(f"Error borrando DetalleSueldo ID {detalle_id}: {e_del}", exc_info=True)
             messages.error(request, f"Ocurrió un error al intentar borrar el registro: {e_del}")
             # Fallback: ir a la lista general si falla el borrado
             return redirect('lista_planillas_sueldo')

    # Método GET: Mostrar la página de confirmación
    context = {
        'detalle': detalle,
        'planilla_sueldo': planilla_sueldo,
        'persona_nombre': persona_nombre,
        'cancel_url': return_url, # <-- Pasar URL para botón Cancelar
        'titulo_pagina': f"Confirmar Borrado Detalle Sueldo: {persona_nombre}"
    }
    return render(request, 'sueldos/borrar_detalle_sueldo.html', context)
