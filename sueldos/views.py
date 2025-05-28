# sueldos/views.py (COMPLETO Y MODIFICADO)

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import PlanillaSueldo, DetalleSueldo, EstadoMensualEmpleado, CierreMensual
from .forms import CrearPlanillaSueldoForm, EditarPlanillaSueldoForm, SubirExcelSueldosForm, EditarDetalleSueldoForm, GenerarEstadoMensualForm
from decimal import Decimal, InvalidOperation # Importar Decimal e InvalidOperation
from .utils import get_processed_sueldo_details # Importar la nueva utilidad
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models import Q # Para consultas complejas si son necesarias
from collections import defaultdict # Para agrupar designaciones
from django.core.exceptions import ValidationError, FieldDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


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

try:
    from reportes.models import PlanillaAsistencia, DetalleAsistencia
    REPORTES_APP_AVAILABLE = True
except ImportError:
    PlanillaAsistencia, DetalleAsistencia = None, None
    REPORTES_APP_AVAILABLE = False
    logging.warning("SUELDOS VIEWS: No se pudo importar modelos de 'reportes'. La comparación con asistencia no estará disponible.")
# --- Fin Importaciones ---

logger = logging.getLogger(__name__)

# --- Vistas para la Cabecera (PlanillaSueldo) ---
# (Estas vistas permanecen igual que antes)
@login_required
@permission_required('sueldos.add_planillasueldos', raise_exception=True)
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
@permission_required('sueldos.view_planillasueldo', raise_exception=True)
def lista_planillas_sueldo(request):
    planillas = PlanillaSueldo.objects.all().order_by('-anio', '-mes', 'tipo')
    context = {
        'planillas_sueldo': planillas,
        'titulo_pagina': 'Planillas de Sueldos Generadas'
    }
    return render(request, 'sueldos/lista_planillas_sueldo.html', context)

# --- Vista Principal ACTUALIZADA: Carga y Procesamiento del Excel con Pandas ---
@login_required
@permission_required('sueldos.change_planillasueldo', raise_exception=True)
def subir_excel_sueldos(request, planilla_id):
    planilla = get_object_or_404(PlanillaSueldo, pk=planilla_id)

    if not PLANILLA_APP_AVAILABLE: messages.error(request, "Error: Componente de personal no disponible."); return redirect('lista_planillas_sueldo')
    if not PANDAS_AVAILABLE: messages.error(request, "Error: Librería 'pandas' no instalada."); return redirect('lista_planillas_sueldo')
    if not REPORTES_APP_AVAILABLE: messages.info(request, "Nota: App de reportes no disponible, no se harán comparaciones.")
    if planilla.estado not in ['borrador', 'error_carga']: messages.warning(request, f"Planilla {planilla} con estado '{planilla.get_estado_display()}'. No se puede recargar."); return redirect('lista_planillas_sueldo')

    if request.method == 'POST':
        form = SubirExcelSueldosForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['archivo_excel']
            logger.info(f"Archivo Excel '{excel_file.name}' recibido para PlanillaSueldo ID {planilla.id}")

            errores_carga = []; advertencias_carga = []; detalles_a_crear = []
            filas_procesadas_ok = 0; filas_omitidas_personal = 0; filas_omitidas_datos = 0; filas_omitidas_formato = 0
            personal_procesado_en_archivo = set()
            planilla_asistencia_validada = None; detalles_asistencia_dict = {}

            if REPORTES_APP_AVAILABLE:
                try:
                    planilla_asistencia_validada = PlanillaAsistencia.objects.get(mes=planilla.mes, anio=planilla.anio, tipo=planilla.tipo, estado='validado')
                    logger.info(f"Comparación: Encontrada PlanillaAsistencia validada ID {planilla_asistencia_validada.id}.")
                    detalles_asistencia_qs = DetalleAsistencia.objects.filter(planilla_asistencia=planilla_asistencia_validada)
                    detalles_asistencia_dict = {da.personal_externo_id: da for da in detalles_asistencia_qs if da.personal_externo_id}
                    logger.info(f"Comparación: Cargados {len(detalles_asistencia_dict)} detalles de asistencia.")
                except PlanillaAsistencia.DoesNotExist: logger.info("Comparación: No se encontró PlanillaAsistencia validada."); messages.info(request, "No se encontró reporte de asistencia validado para comparar.")
                except Exception as e_pa: logger.error(f"Error buscando PlanillaAsistencia validada: {e_pa}"); messages.warning(request, f"Error buscando reporte de asistencia: {e_pa}")

            # --- Bloque TRY principal para leer y procesar el Excel ---
            try:
                df = pd.read_excel(excel_file, sheet_name=0, header=None, dtype=str)
                filas_leidas_excel = len(df); logger.info(f"Pandas leyó {filas_leidas_excel} filas.")

                COL_ITEM=0; COL_CI=1; COL_NOMBRE=2; COL_CARGO=3; COL_FECHA_ING=4; COL_DIAS_TRAB=5; COL_HABER_BASICO=6;
                COL_CATEGORIA=7; COL_TOTAL_GANADO=8; COL_RC_IVA=9; COL_GESTORA=10; COL_APORTE_SOL=11; COL_COOP=12;
                COL_FALTAS=13; COL_MEMOS=14; COL_OTROS_DESC=15; COL_TOTAL_DESC=16; COL_LIQUIDO=17;
                FILA_INICIO_DATOS = 11

                def safe_to_decimal(value, default=Decimal('0.00')):
                    if pd.isna(value) or value is None or str(value).strip() == '': return default
                    try: return Decimal(value)
                    except:
                        try: return Decimal(str(value).replace('$', '').replace('Bs', '').replace('.', '').replace(',', '.').strip())
                        except: return default
                def safe_to_date(value):
                     if pd.isna(value) or value is None: return None
                     try:
                         if isinstance(value, pd.Timestamp): return value.date()
                         return pd.to_datetime(value).date()
                     except: return None

                for indice_fila, fila in df.iloc[FILA_INICIO_DATOS:].iterrows():
                    numero_fila_excel = indice_fila + 1; ci_excel_raw = fila.iloc[COL_CI]
                    if pd.isna(ci_excel_raw) or str(ci_excel_raw).strip() == "": filas_omitidas_formato += 1; continue
                    item_raw = fila.iloc[COL_ITEM]
                    if pd.isna(item_raw) or not str(item_raw).strip().isdigit():
                        if pd.isna(fila.iloc[COL_NOMBRE]): filas_omitidas_formato += 1; logger.debug(f"Fila {numero_fila_excel}: Omitida, formato."); continue
                    ci_excel = str(ci_excel_raw).strip()

                    personal_externo = None
                    try: personal_externo = PrincipalPersonalExterno.objects.using('personas_db').get(ci__iexact=ci_excel)
                    except PrincipalPersonalExterno.DoesNotExist: msg = f"Fila {numero_fila_excel}: Omitida (CI '{ci_excel}' NO encontrado)."; logger.warning(msg); errores_carga.append(msg); filas_omitidas_personal += 1; continue
                    except Exception as e_db: msg = f"Fila {numero_fila_excel}: Omitida (Error BD CI '{ci_excel}': {e_db})."; logger.error(msg, exc_info=True); errores_carga.append(msg); filas_omitidas_personal += 1; continue

                    if personal_externo.id in personal_procesado_en_archivo: msg = f"Fila {numero_fila_excel}: Omitida (ADVERTENCIA: CI '{ci_excel}' duplicado archivo)."; logger.warning(msg); advertencias_carga.append(msg); filas_omitidas_datos += 1; continue
                    personal_procesado_en_archivo.add(personal_externo.id)

                    if planilla_asistencia_validada and personal_externo:
                        detalle_asistencia = detalles_asistencia_dict.get(personal_externo.id)
                        if detalle_asistencia:
                            faltas_asistencia_dias = detalle_asistencia.faltas_dias or Decimal('0'); faltas_excel_monto = safe_to_decimal(fila.iloc[COL_FALTAS])
                            if faltas_asistencia_dias > 0 and faltas_excel_monto == 0: advertencias_carga.append(f"Fila {numero_fila_excel} (CI {ci_excel}): {faltas_asistencia_dias} día(s) falta Asist., desc. 0 Excel.")
                            elif faltas_asistencia_dias == 0 and faltas_excel_monto > 0: advertencias_carga.append(f"Fila {numero_fila_excel} (CI {ci_excel}): Desc. Faltas ({faltas_excel_monto}) Excel, 0 días Asist.")
                            memos_excel_monto = safe_to_decimal(fila.iloc[COL_MEMOS])
                            if memos_excel_monto > 0: advertencias_carga.append(f"Fila {numero_fila_excel} (CI {ci_excel}): Desc. Memos ({memos_excel_monto}) Excel (verif. Asist.).")
                        else: advertencias_carga.append(f"Fila {numero_fila_excel} (CI {ci_excel}): En Excel Sueldos pero NO en Asist. Validada.")

                    try:
                        dias_t=safe_to_decimal(fila.iloc[COL_DIAS_TRAB]); haber_b=safe_to_decimal(fila.iloc[COL_HABER_BASICO]); cat=safe_to_decimal(fila.iloc[COL_CATEGORIA]);
                        total_g=safe_to_decimal(fila.iloc[COL_TOTAL_GANADO]); rc_iva=safe_to_decimal(fila.iloc[COL_RC_IVA]); gestora=safe_to_decimal(fila.iloc[COL_GESTORA]);
                        aporte_sol=safe_to_decimal(fila.iloc[COL_APORTE_SOL]); coop=safe_to_decimal(fila.iloc[COL_COOP]); desc_faltas=safe_to_decimal(fila.iloc[COL_FALTAS]); # Re-convertir por si falla safe_to_decimal
                        desc_memos=safe_to_decimal(fila.iloc[COL_MEMOS]); otros_d=safe_to_decimal(fila.iloc[COL_OTROS_DESC]); total_d=safe_to_decimal(fila.iloc[COL_TOTAL_DESC]);
                        liquido=safe_to_decimal(fila.iloc[COL_LIQUIDO]);
                        item_ref=fila.iloc[COL_ITEM]; item_ref_int = int(item_ref) if pd.notna(item_ref) and str(item_ref).strip().isdigit() else None;
                        nombre_ref=fila.iloc[COL_NOMBRE]; nombre_ref_str = str(nombre_ref).strip() if pd.notna(nombre_ref) else None;
                        cargo_ref=fila.iloc[COL_CARGO]; cargo_ref_str = str(cargo_ref).strip() if pd.notna(cargo_ref) else None;
                        fecha_ing_ref=safe_to_date(fila.iloc[COL_FECHA_ING]);
                        if pd.notna(fila.iloc[COL_ITEM]) and item_ref_int is None: advertencias_carga.append(f"Fila {numero_fila_excel} (CI {ci_excel}): Item '{item_ref}' no numérico.")
                        # Aquí podrías añadir más validaciones si es necesario antes de crear

                        detalle = DetalleSueldo(
                            planilla_sueldo=planilla, personal_externo_id=personal_externo.id,
                            dias_trab=dias_t, haber_basico=haber_b, categoria=cat, total_ganado=total_g, rc_iva_retenido=rc_iva,
                            gestora_publica=gestora, aporte_nac_solidario=aporte_sol, cooperativa=coop, faltas=desc_faltas,
                            memorandums=desc_memos, otros_descuentos=otros_d, total_descuentos=total_d, liquido_pagable=liquido,
                            item_referencia=item_ref_int, nombre_completo_referencia=nombre_ref_str, cargo_referencia=cargo_ref_str,
                            fecha_ingreso_referencia=fecha_ing_ref, fila_excel=numero_fila_excel
                        )
                        detalles_a_crear.append(detalle); filas_procesadas_ok += 1
                    except Exception as e_parse: msg = f"Fila {numero_fila_excel}: Omitida (Error datos CI '{ci_excel}': {e_parse})."; logger.error(msg, exc_info=False); errores_carga.append(msg); filas_omitidas_datos += 1; personal_procesado_en_archivo.discard(personal_externo.id); continue
                # --- Fin Bucle Filas ---
                logger.info(f"Procesamiento Excel finalizado. OK:{filas_procesadas_ok}, NoPers:{filas_omitidas_personal}, NoData:{filas_omitidas_datos}, Formato:{filas_omitidas_formato}.")

            # --- Bloques EXCEPT con INDENTACIÓN CORREGIDA ---
            except InvalidFileException:
                # Este código ahora está INDENTADO correctamente
                logger.error(f"Error cargando archivo Excel '{excel_file.name}' para Planilla {planilla.id}. Formato inválido.", exc_info=True)
                messages.error(request, "El archivo Excel parece estar corrupto o no es un formato .xlsx válido.")
                return redirect('subir_excel_sueldos', planilla_id=planilla.id)
            except Exception as e_general:
                # Este código ahora está INDENTADO correctamente
                logger.error(f"Error inesperado procesando Excel '{excel_file.name}' para Planilla {planilla.id}: {e_general}", exc_info=True)
                messages.error(request, f"Ocurrió un error inesperado al procesar el archivo: {e_general}")
                planilla.estado = 'error_carga'
                # Generar resumen simple del error para observaciones
                obs_error = f"Error General Procesando Excel: {e_general}\n"
                if errores_carga: obs_error += "Primeros errores encontrados:\n" + "\n".join(errores_carga[:5])
                planilla.observaciones = obs_error
                try:
                    planilla.save(update_fields=['estado', 'observaciones']) # Guardar solo estado y obs
                except Exception as e_save_err:
                    logger.error(f"Error adicional guardando estado de error para Planilla {planilla.id}: {e_save_err}")
                return redirect('subir_excel_sueldos', planilla_id=planilla.id)
            # --- FIN Bloques EXCEPT ---

            # --- Guardar Resultados en Base de Datos ---
            if detalles_a_crear:
                try:
                    with transaction.atomic(using='default'):
                        DetalleSueldo.objects.filter(planilla_sueldo=planilla).delete(); logger.info(f"Detalles antiguos para Planilla ID {planilla.id} borrados.")
                        DetalleSueldo.objects.bulk_create(detalles_a_crear); logger.info(f"{len(detalles_a_crear)} nuevos detalles creados.")
                        planilla.estado = 'cargado'; planilla.fecha_carga_excel = timezone.now()
                        planilla.archivo_excel_cargado.save(excel_file.name, excel_file, save=False)
                        obs_resumen = f"Carga Excel ({timezone.now().strftime('%Y-%m-%d %H:%M')}):\n- Filas OK: {filas_procesadas_ok}\n";
                        if filas_omitidas_personal: obs_resumen += f"- Omitidas (No Pers): {filas_omitidas_personal}\n"
                        if filas_omitidas_datos: obs_resumen += f"- Omitidas (Dato/Dupl): {filas_omitidas_datos}\n"
                        if filas_omitidas_formato: obs_resumen += f"- Omitidas (Formato): {filas_omitidas_formato}\n"
                        if advertencias_carga: obs_resumen += f"\nAdvertencias ({len(advertencias_carga)}):\n" + "\n".join(advertencias_carga[:5]) + ("\n..." if len(advertencias_carga)>5 else "")
                        if errores_carga: obs_resumen += f"\nErrores ({len(errores_carga)}):\n" + "\n".join(errores_carga[:5]) + ("\n..." if len(errores_carga)>5 else "")
                        planilla.observaciones = obs_resumen; planilla.save()
                    messages.success(request, f"Archivo procesado. Registros cargados: {filas_procesadas_ok}.")
                    num_problemas = len(advertencias_carga) + len(errores_carga);
                    if num_problemas > 0: messages.warning(request, f"Se encontraron {num_problemas} advertencias/errores (ver obs.).")
                    return redirect('lista_planillas_sueldo')
                except IntegrityError as e_int: logger.error(...); messages.error(request, f"Error BD: {e_int}"); planilla.estado='error_carga'; planilla.observaciones = f"Error BD: {e_int}"; planilla.save()
                except Exception as e_save: logger.error(...); messages.error(request, f"Error guardando: {e_save}"); planilla.estado='error_carga'; planilla.observaciones = f"Error Guardando: {e_save}"; planilla.save()
            else:
                 messages.error(request, "No se procesó ningún registro válido del archivo Excel."); num_problemas = len(advertencias_carga) + len(errores_carga)
                 if num_problemas > 0: messages.warning(request, f"Se encontraron {num_problemas} problemas.")
                 planilla.estado = 'error_carga'; obs_error = "Ninguna fila procesada OK.\n"; # ... (añadir adv/err a obs_error) ...
                 planilla.observaciones = obs_error; planilla.save()
            return redirect('subir_excel_sueldos', planilla_id=planilla.id)
        else: messages.error(request, "Error en formulario. Seleccione archivo .xlsx.")
    else: form = SubirExcelSueldosForm()
    context = { 'form': form, 'planilla_sueldo': planilla, 'titulo_pagina': f'Cargar Excel Sueldos - {planilla}' }
    return render(request, 'sueldos/subir_excel.html', context)

# sueldos/views.py
# ... (importaciones existentes: logging, render, redirect, get_object_or_404, etc.)
# ... (importar PlanillaSueldo, PlanillaSueldoForm, SubirExcelSueldosForm)

# --- Vistas para la Cabecera (PlanillaSueldo) ---
# ... (vista crear_planilla_sueldo y lista_planillas_sueldo como antes) ...

@login_required
@permission_required('sueldos.change_planillasueldo', raise_exception=True)
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
@permission_required('sueldos.delete_planillasueldo', raise_exception=True)
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
@permission_required('sueldos.view_detallesueldo', raise_exception=True)
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
@permission_required('sueldos.change_detallesueldo', raise_exception=True)
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
@permission_required('sueldos.delete_detallesueldo', raise_exception=True)
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



# sueldos/views.py
# ... (importaciones existentes: logging, render, redirect, etc.) ...






EXTERNAL_TYPE_MAP = {
    'planta': 'ASEGURADO',
    'contrato': 'CONTRATO', # Ajusta si el valor real es diferente
    'consultor': 'CONSULTOR EN LINEA', # Ajusta si el valor real es diferente
}

@login_required
@permission_required('sueldos.add_cierremensualdeestado', raise_exception=True)
@transaction.atomic
def generar_estado_mensual_form(request):
    if request.method == 'POST':
        form = GenerarEstadoMensualForm(request.POST)
        if form.is_valid():
            mes_actual = form.cleaned_data['mes']; anio_actual = form.cleaned_data['anio']
            tipo_planilla = form.cleaned_data['tipo_planilla']
            tipo_planilla_display = dict(PlanillaSueldo.TIPO_CHOICES).get(tipo_planilla, tipo_planilla)

            logger.info(f"Solicitud para generar estado: {mes_actual}/{anio_actual} - {tipo_planilla_display}")

            cierre, created = CierreMensual.objects.update_or_create(
                mes=mes_actual, anio=anio_actual, tipo_planilla=tipo_planilla,
                defaults={'usuario_generacion': request.user, 'estado_proceso': 'EN_PROCESO', 'fecha_generacion': timezone.now(), 'resumen_proceso': 'Iniciando...'}
            )
            if not created: EstadoMensualEmpleado.objects.filter(cierre_mensual=cierre).delete(); logger.info(f"Borrados estados anteriores para Cierre ID {cierre.id}.")
            else: logger.info(f"Creado nuevo CierreMensual ID {cierre.id}.")

            errores_proceso = []; advertencias_proceso = []; conteo_estados = defaultdict(int)

            try: # <--- INICIO DEL BLOQUE TRY PRINCIPAL
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - Iniciando bloque TRY principal.") # LOG INICIO TRY

                # --- 1. Validar y Obtener Datos Mes Actual ---
                planilla_actual = PlanillaSueldo.objects.get(mes=mes_actual, anio=anio_actual, tipo=tipo_planilla)
                if planilla_actual.estado not in ['cargado', 'validado', 'pagado']:
                    msg = f"Planilla sueldos {mes_actual}/{anio_actual} ({tipo_planilla_display}) no cargada/validada."; messages.error(request, msg); cierre.estado_proceso = 'ERROR'; cierre.resumen_proceso = msg; cierre.save(); return redirect('generar_estado_mensual_form')
                
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - Planilla actual encontrada: {planilla_actual.id}")
                detalles_actuales_qs = DetalleSueldo.objects.filter(planilla_sueldo=planilla_actual)
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - Número de DetalleSueldo para planilla actual: {detalles_actuales_qs.count()}")

                if not detalles_actuales_qs.exists():
                    msg = f"No hay detalles sueldo cargados para {mes_actual}/{anio_actual}."; messages.error(request, msg); cierre.estado_proceso = 'ERROR'; cierre.resumen_proceso = msg; cierre.save(); return redirect('generar_estado_mensual_form')
                
                detalle_sueldo_actual_map = {d.personal_externo_id: d for d in detalles_actuales_qs if d.personal_externo_id}
                ids_actual = set(detalle_sueldo_actual_map.keys())
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - IDs en DetalleSueldo actual (ids_actual): {len(ids_actual)}. Primeros 5: {list(ids_actual)[:5]}")


                # --- 2. Calcular y Obtener Datos Mes Anterior ---
                mes_anterior = mes_actual - 1; anio_anterior = anio_actual
                if mes_anterior == 0: mes_anterior = 12; anio_anterior -= 1
                estados_anteriores_map = {}; ids_anterior = set()
                cierre_anterior = CierreMensual.objects.filter(mes=mes_anterior, anio=anio_anterior, tipo_planilla=tipo_planilla, estado_proceso__startswith='COMPLETADO').first()
                if cierre_anterior:
                    estados_anteriores_qs = EstadoMensualEmpleado.objects.filter(cierre_mensual=cierre_anterior)
                    estados_anteriores_map = {em.personal_externo_id: em for em in estados_anteriores_qs}; ids_anterior = set(estados_anteriores_map.keys())
                    logger.info(f"[GENERAR ESTADO {cierre.id}] - Encontrados {len(ids_anterior)} estados anteriores desde Cierre ID {cierre_anterior.id}.")
                else: logger.warning(f"[GENERAR ESTADO {cierre.id}] - No se encontró CierreMensual COMPLETADO para {mes_anterior}/{anio_anterior}.")
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - IDs en EstadoMensual del mes anterior (ids_anterior): {len(ids_anterior)}. Primeros 5: {list(ids_anterior)[:5]}")

                # --- 3. Identificar Conjuntos de IDs ---
                ids_ingresan = ids_actual - ids_anterior; ids_retirados = ids_anterior - ids_actual; ids_permanecen = ids_anterior & ids_actual; ids_todos = ids_actual | ids_anterior
                logger.info(f"[GENERAR ESTADO {cierre.id}] - IDs - Actuales:{len(ids_actual)}, Ants:{len(ids_anterior)}, Ing:{len(ids_ingresan)}, Ret:{len(ids_retirados)}, Perm:{len(ids_permanecen)}, Todos:{len(ids_todos)}")
                logger.debug(f"[GENERAR ESTADO {cierre.id}] - Total IDs a procesar (ids_todos): {len(ids_todos)}. Primeros 5: {list(ids_todos)[:5]}")
                
                # --- 4. Consultar Información Externa ---
                personas_externas_map = {}; designaciones_map = defaultdict(list)
                if PLANILLA_APP_AVAILABLE and ids_todos:
                    logger.debug(f"[GENERAR ESTADO {cierre.id}] - Iniciando consulta a BD externa para {len(ids_todos)} IDs.")
                    try:
                        personas_qs = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_todos).only('id', 'ci', 'nombre', 'apellido_paterno', 'apellido_materno')
                        personas_externas_map = {p.id: p for p in personas_qs}
                        logger.info(f"[GENERAR ESTADO {cierre.id}] - Obtenidas {len(personas_externas_map)} personas BD ext.")
                        
                        tipo_externo = EXTERNAL_TYPE_MAP.get(tipo_planilla)
                        if not tipo_externo: raise ValueError(f"Mapeo externo inválido para {tipo_planilla}")
                        
                        campos_designacion = ['id', 'personal_id', 'item', 'estado', 'tipo_designacion', 'cargo__nombre_cargo', 'unidad__nombre_unidad', 'unidad__secretaria__nombre_secretaria', 'fecha_ingreso', 'fecha_conclusion']
                        designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db').select_related('cargo', 'unidad__secretaria').filter(personal_id__in=ids_todos, tipo_designacion=tipo_externo).order_by('personal_id', '-id').only(*campos_designacion)
                        
                        # Iterar para poblar el mapa (esto ejecuta la consulta)
                        count_desig = 0
                        for desig in designaciones_qs:
                            if desig.personal_id: 
                                designaciones_map[desig.personal_id].append(desig)
                                count_desig += 1
                        logger.info(f"[GENERAR ESTADO {cierre.id}] - Obtenidas {count_desig} designaciones para {len(designaciones_map)} personas BD ext.")

                    except FieldDoesNotExist as e_field: msg = f"Error BD externa: Falta campo '{e_field}' en modelo."; logger.error(msg, exc_info=True); errores_proceso.append(msg); raise
                    except Exception as e_ext: msg = f"Error BD externa: {e_ext}."; logger.error(msg, exc_info=True); errores_proceso.append(msg); raise
                else:
                    logger.warning(f"[GENERAR ESTADO {cierre.id}] - Omitiendo consulta a BD externa (PLANILLA_APP_AVAILABLE={PLANILLA_APP_AVAILABLE} o ids_todos vacío).")


                # --- 5. Procesar Cada Empleado y Determinar Estado ---
                resultados_a_guardar = []
                contador_bucle_principal = 0
                logger.info(f"[GENERAR ESTADO {cierre.id}] - Iniciando bucle principal para {len(ids_todos)} IDs.") # LOG INICIO BUCLE
                for id_personal in ids_todos:
                    contador_bucle_principal += 1
                    logger.debug(f"--- INICIO BUCLE ({contador_bucle_principal}/{len(ids_todos)}) ID: {id_personal} ---") # LOG INICIO ITERACIÓN

                    estado_final = 'ERROR_INESPERADO'; notas_proceso_actual = []; item_final = None; cargo_final = None; unidad_final = None; secretaria_final = None; fecha_ingreso = None; fecha_conclusion = None
                    detalle_sueldo_actual = detalle_sueldo_actual_map.get(id_personal); estado_anterior = estados_anteriores_map.get(id_personal)
                    persona_ext = personas_externas_map.get(id_personal); lista_designaciones = designaciones_map.get(id_personal, [])
                    logger.debug(f"ID: {id_personal} - Datos iniciales: detalle_actual={detalle_sueldo_actual is not None}, estado_ant={estado_anterior is not None}, persona_ext={persona_ext is not None}, num_desig={len(lista_designaciones)}")

                    if not persona_ext:
                        notas_proceso_actual.append("ERROR: No se encontraron datos básicos en BD externa."); estado_final = 'INCONSISTENTE_BD'
                        if estado_anterior: item_final=estado_anterior.item; cargo_final=estado_anterior.cargo; unidad_final=estado_anterior.unidad_nombre; secretaria_final=estado_anterior.secretaria_nombre
                        logger.warning(f"ID: {id_personal} - Sin datos persona_ext.")
                    else:
                        desig_activa = next((d for d in lista_designaciones if d.estado and d.estado.strip().upper() == 'ACTIVO'), None) # strip() añadido
                        desig_relevante = desig_activa if desig_activa else (lista_designaciones[0] if lista_designaciones else None)
                        logger.debug(f"ID: {id_personal} - Desig. Activa: {desig_activa is not None}. Desig. Relevante: {desig_relevante.id if desig_relevante else 'None'}")

                        # --- Lógica de Decisión ---
                        if id_personal in ids_ingresan:
                            estado_final = 'NUEVO_INGRESO'
                            if desig_relevante: fecha_ingreso = getattr(desig_relevante, 'fecha_ingreso', None)
                            notas_proceso_actual.append(f"Detectado Nuevo Ingreso (Fec.Ing Puesto BD: {fecha_ingreso or 'N/A'}).")
                            if not desig_relevante: notas_proceso_actual.append("Advertencia: Sin designación en BD ext.")
                            elif desig_relevante.estado and desig_relevante.estado.strip().upper() != 'ACTIVO': notas_proceso_actual.append(f"Advertencia: Estado BD ext. es '{desig_relevante.estado}'.")
                        elif id_personal in ids_retirados:
                            estado_final = 'RETIRO_DETECTADO'
                            if desig_relevante: fecha_conclusion = getattr(desig_relevante, 'fecha_conclusion', None)
                            notas_proceso_actual.append(f"Detectado como Retiro (Fec.Conclusión BD: {fecha_conclusion or 'N/A'}).")
                            if desig_relevante and desig_relevante.estado and desig_relevante.estado.strip().upper() == 'ACTIVO':
                                notas_proceso_actual.append("¡INCONSISTENCIA! Retiro (no sueldos) pero BD ext. sigue 'ACTIVO'."); estado_final = 'INCONSISTENTE_BD'
                            if estado_anterior: item_final=estado_anterior.item; cargo_final=estado_anterior.cargo; unidad_final=estado_anterior.unidad_nombre; secretaria_final=estado_anterior.secretaria_nombre
                        elif id_personal in ids_permanecen:
                            if not desig_relevante: estado_final = 'INCONSISTENTE_BD'; notas_proceso_actual.append("¡INCONSISTENCIA! Permanente pero sin designación en BD ext.")
                            elif not estado_anterior: estado_final = 'ACTIVO'; notas_proceso_actual.append("Primer registro de estado.")
                            else:
                                estado_bd_actual = desig_relevante.estado.strip().upper() if desig_relevante.estado else None; fecha_conclusion_bd_actual = getattr(desig_relevante, 'fecha_conclusion', None); fecha_ingreso_bd_actual = getattr(desig_relevante, 'fecha_ingreso', None)
                                logger.debug(f"ID: {id_personal} - Permanente. Estado BD actual: '{estado_bd_actual}'")
                                if estado_bd_actual == 'CONCLUIDO' and fecha_conclusion_bd_actual and fecha_conclusion_bd_actual.year == anio_actual and fecha_conclusion_bd_actual.month == mes_actual:
                                    estado_final = 'RETIRO_DETECTADO'; notas_proceso_actual.append(f"Retiro procesado. Conclusión BD: {fecha_conclusion_bd_actual}"); fecha_conclusion = fecha_conclusion_bd_actual; item_final = estado_anterior.item; cargo_final = estado_anterior.cargo; unidad_final=estado_anterior.unidad_nombre; secretaria_final=estado_anterior.secretaria_nombre
                                elif estado_bd_actual != 'ACTIVO': estado_final = 'INCONSISTENTE_BD'; notas_proceso_actual.append(f"Permanente, pero estado BD ext. '{desig_relevante.estado}'. Revisar.")
                                else:
                                    cambio_detectado = False; cargo_actual_str = desig_relevante.cargo.nombre_cargo if desig_relevante.cargo else None; unidad_actual_str = desig_relevante.unidad.nombre_unidad if hasattr(desig_relevante,'unidad') and desig_relevante.unidad else None; secretaria_actual_str = desig_relevante.unidad.secretaria.nombre_secretaria if hasattr(desig_relevante,'unidad') and desig_relevante.unidad and hasattr(desig_relevante.unidad,'secretaria') and desig_relevante.unidad.secretaria else None
                                    if desig_relevante.item != estado_anterior.item: cambio_detectado = True; notas_proceso_actual.append(f"Item: {estado_anterior.item or 'N/A'} -> {desig_relevante.item or 'N/A'}")
                                    if cargo_actual_str != estado_anterior.cargo: cambio_detectado = True; notas_proceso_actual.append(f"Cargo: '{estado_anterior.cargo or 'N/A'}' -> '{cargo_actual_str or 'N/A'}'")
                                    if unidad_actual_str != estado_anterior.unidad_nombre: cambio_detectado = True; notas_proceso_actual.append(f"Unidad: '{estado_anterior.unidad_nombre or 'N/A'}' -> '{unidad_actual_str or 'N/A'}'")
                                    if secretaria_actual_str != estado_anterior.secretaria_nombre: cambio_detectado = True; notas_proceso_actual.append(f"Secretaría: '{estado_anterior.secretaria_nombre or 'N/A'}' -> '{secretaria_actual_str or 'N/A'}'")
                                    if cambio_detectado: estado_final = 'CAMBIO_PUESTO'; fecha_ingreso = fecha_ingreso_bd_actual; notas_proceso_actual.append(f"Detectado Cambio (Puesto desde BD: {fecha_ingreso or 'N/A'}).")
                                    else: estado_final = 'ACTIVO'; fecha_ingreso = fecha_ingreso_bd_actual # Asignar fecha de ingreso aunque no haya cambio
                        # --- FIN LÓGICA DE DECISIÓN ---
                        
                        # Fallback si no se asignó estado
                        if estado_final == 'ERROR_INESPERADO':
                            logger.error(f"ID {id_personal}: NO SE PUDO CLASIFICAR. Ingreso={id_personal in ids_ingresan}, Retiro={id_personal in ids_retirados}, Permanece={id_personal in ids_permanecen}")
                            notas_proceso_actual.append("ERROR: No se pudo clasificar el estado del empleado.")


                    # --- Recolectar/Confirmar Datos Finales ---
                    if desig_relevante:
                        if estado_final not in ['RETIRO_DETECTADO'] or item_final is None:
                            item_final = desig_relevante.item; cargo_final = desig_relevante.cargo.nombre_cargo if desig_relevante.cargo else None
                            unidad_final = desig_relevante.unidad.nombre_unidad if hasattr(desig_relevante,'unidad') and desig_relevante.unidad else None
                            secretaria_final = desig_relevante.unidad.secretaria.nombre_secretaria if hasattr(desig_relevante,'unidad') and desig_relevante.unidad and hasattr(desig_relevante.unidad,'secretaria') and desig_relevante.unidad.secretaria else None
                        if not fecha_ingreso and estado_final not in ['RETIRO_DETECTADO']: fecha_ingreso = getattr(desig_relevante, 'fecha_ingreso', None)
                        if not fecha_conclusion and estado_final == 'RETIRO_DETECTADO': fecha_conclusion = getattr(desig_relevante, 'fecha_conclusion', None)
                    # ---- Fin Recolectar ----

                    logger.debug(f"ID: {id_personal} - Datos finales: Estado={estado_final}, Item={item_final}, Cargo='{cargo_final}', Notas='{' / '.join(notas_proceso_actual[:1])}'")
                    estado_obj_data = {
                        'cierre_mensual': cierre, 'personal_externo_id': id_personal, 'estado_final_mes': estado_final,
                        'item': item_final, 'cargo': cargo_final, 'unidad_nombre': unidad_final, 'secretaria_nombre': secretaria_final,
                        'fecha_ingreso_bd': fecha_ingreso, 'fecha_conclusion_bd': fecha_conclusion,
                        'detalle_sueldo': detalle_sueldo_actual_map.get(id_personal),
                        'notas_proceso': "\n".join(notas_proceso_actual) if notas_proceso_actual else None,
                    }
                    resultados_a_guardar.append(EstadoMensualEmpleado(**estado_obj_data))
                    conteo_estados[estado_final] += 1
                    logger.debug(f"--- FIN BUCLE PARA ID: {id_personal}. Estado final: {estado_final} ---") # LOG FIN ITERACIÓN
                # --- Fin del Bucle for id_personal ---
                logger.info(f"Bucle principal completado. Total iteraciones realizadas: {contador_bucle_principal}")

                # --- 6. Guardar Resultados y Actualizar Cierre ---
                if resultados_a_guardar:
                    logger.info(f"[GENERAR ESTADO {cierre.id}] - Iniciando bulk_create para {len(resultados_a_guardar)} registros.") # LOG ANTES BULK
                    EstadoMensualEmpleado.objects.bulk_create(resultados_a_guardar)
                    logger.info(f"[GENERAR ESTADO {cierre.id}] - bulk_create completado. Actualizando cierre...") # LOG DESPUÉS BULK
                    cierre.estado_proceso = 'COMPLETADO_CON_ADVERTENCIAS' if advertencias_proceso or errores_proceso or conteo_estados.get('INCONSISTENTE_BD',0) > 0 or conteo_estados.get('ERROR_INESPERADO',0) > 0 else 'COMPLETADO'
                    res_partes = [f"Generación OK. Registros: {len(resultados_a_guardar)}."];
                    for est, num in conteo_estados.items(): res_partes.append(f"- {dict(EstadoMensualEmpleado.ESTADOS_FINALES).get(est, est)}: {num}")
                    if advertencias_proceso: res_partes.append(f"\nAdvs ({len(advertencias_proceso)}):\n" + "\n".join(advertencias_proceso[:3]) + ("..." if len(advertencias_proceso)>3 else ""))
                    if errores_proceso: res_partes.append(f"\nErrs Proc ({len(errores_proceso)}):\n" + "\n".join(errores_proceso[:3]) + ("..." if len(errores_proceso)>3 else ""))
                    cierre.resumen_proceso = "\n".join(res_partes); cierre.save()
                    logger.info(f"[GENERAR ESTADO {cierre.id}] - Cierre guardado como {cierre.estado_proceso}.") # LOG CIERRE GUARDADO
                    messages.success(request, f"Proceso para {mes_actual}/{anio_actual} ({tipo_planilla_display}) finalizado. {cierre.get_estado_proceso_display()}.")
                    #return redirect('ver_detalle_cierre', cierre_id=cierre.pk)
                    return redirect('lista_cierres_mensuales')
                else:
                    msg = "No se generó ningún registro de estado (¿No había empleados procesables?)."; cierre.estado_proceso = 'ERROR'; cierre.resumen_proceso = msg; cierre.save()
                    logger.warning(f"[GENERAR ESTADO {cierre.id}] - {msg}") # LOG NO RESULTADOS
                    messages.warning(request, msg); return redirect('generar_estado_mensual_form')
            except Exception as e_proc:
                logger.error(f"Error mayor durante generación estado para {cierre}: {e_proc}", exc_info=True)
                try:
                    cierre.estado_proceso = 'ERROR'; cierre.resumen_proceso = f"Error crítico: {e_proc}\n"
                    if errores_proceso: cierre.resumen_proceso += "Errores detectados:\n" + "\n".join(errores_proceso)
                    cierre.save()
                except Exception as e_save_cierre: logger.error(f"Error adicional al guardar CierreMensual en estado ERROR: {e_save_cierre}")
                messages.error(request, f"Error crítico durante la generación: {e_proc}"); return redirect('generar_estado_mensual_form')
        else: messages.error(request, "Corrija errores en el formulario.")
    else: form = GenerarEstadoMensualForm()
    context = {'form': form, 'titulo_pagina': 'Generar Estado Mensual de Empleados'}
    return render(request, 'sueldos/generar_estado_mensual_form.html', context)



#-------------------------------

@login_required
@permission_required('sueldos.view_cierremensualdeestado', raise_exception=True)
def lista_estado_mensual(request):
    """ Muestra los registros de EstadoMensualEmpleado generados, filtrados por periodo y tipo. """
    selected_mes = request.GET.get('mes', '')
    selected_anio = request.GET.get('anio', '')
    selected_tipo = request.GET.get('tipo_planilla', '')

    # Query inicial SIN select_related para personal_externo
    estados_list_qs = EstadoMensualEmpleado.objects.select_related(
        'detalle_sueldo' # Mantener este si quieres el enlace al detalle
    ).all()

    # Aplicar filtros si se proporcionaron
    if selected_mes:
        estados_list_qs = estados_list_qs.filter(mes=selected_mes)
    if selected_anio:
        estados_list_qs = estados_list_qs.filter(anio=selected_anio)
    if selected_tipo:
        estados_list_qs = estados_list_qs.filter(tipo_planilla=selected_tipo)

    # Ordenar por campos locales
    estados_list_qs = estados_list_qs.order_by('-anio', '-mes')

    # --- Paginación ANTES del enriquecimiento ---
    page = request.GET.get('page', 1)
    paginator = Paginator(estados_list_qs, 50) # Paginar el QuerySet original
    try:
        estados_pagina_actual = paginator.page(page)
    except PageNotAnInteger:
        estados_pagina_actual = paginator.page(1)
    except EmptyPage:
        estados_pagina_actual = paginator.page(paginator.num_pages)
    # --- FIN PAGINACIÓN ---

    # --- Enriquecimiento Manual SOLO para la página actual ---
    ids_personal_pagina = [e.personal_externo_id for e in estados_pagina_actual if e.personal_externo_id]
    personas_externas_map = {}

    if PLANILLA_APP_AVAILABLE and ids_personal_pagina:
        try:
            # Consulta optimizada a personas_db
            personas_qs = PrincipalPersonalExterno.objects.using('personas_db') \
                .filter(id__in=ids_personal_pagina) \
                .only('id', 'ci', 'nombre', 'apellido_paterno', 'apellido_materno')
            personas_externas_map = {p.id: p for p in personas_qs}
            logger.debug(f"Lista Estado: Obtenidos datos para {len(personas_externas_map)} personas externas.")
        except Exception as e_ext:
            logger.error(f"Error obteniendo datos externos en lista_estado_mensual: {e_ext}", exc_info=True)
            messages.warning(request, "No se pudieron cargar todos los datos del personal.")

    # Añadir atributos a los objetos de la página actual
    for estado in estados_pagina_actual:
        persona = personas_externas_map.get(estado.personal_externo_id)
        if persona:
            # Usar property si existe, si no, construir nombre
            try:
                estado.nombre_completo_externo = persona.nombre_completo
            except AttributeError:
                 nombre = persona.nombre or ''
                 paterno = persona.apellido_paterno or ''
                 materno = persona.apellido_materno or ''
                 estado.nombre_completo_externo = f"{nombre} {paterno} {materno}".strip().replace('  ',' ')

            estado.ci_externo = persona.ci or "S/CI"
        else:
            estado.nombre_completo_externo = f"ID Ext: {estado.personal_externo_id}"
            estado.ci_externo = "N/A"
    # --- FIN: Enriquecimiento Manual ---

    # Formulario para filtros
    filter_form = GenerarEstadoMensualForm(initial={
        'mes': selected_mes, 'anio': selected_anio, 'tipo_planilla': selected_tipo
    })

    context = {
        'estados_mensuales': estados_pagina_actual, # Pasar la PÁGINA actual enriquecida
        'filter_form': filter_form,
        'titulo_pagina': 'Historial de Estados Mensuales de Empleados'
    }
    return render(request, 'sueldos/lista_estado_mensual.html', context) # Usar plantilla normal


@login_required
@permission_required('sueldos.delete_cierremensualdeestado', raise_exception=True)
def borrar_estado_mensual(request, estado_id):
    """ Permite borrar un registro EstadoMensualEmpleado específico. """
    estado = get_object_or_404(EstadoMensualEmpleado, pk=estado_id)
    # Guardar periodo para posible redirección filtrada (más simple redirigir a lista general)
    mes, anio, tipo = estado.mes, estado.anio, estado.tipo_planilla

    if request.method == 'POST':
        try:
            estado_str = str(estado) # Guardar para mensaje
            estado.delete()
            messages.success(request, f"Registro de estado '{estado_str}' borrado exitosamente.")
            # Redirigir a la lista general (más simple que reconstruir filtros)
            return redirect('lista_estado_mensual')
        except Exception as e_del:
            logger.error(f"Error borrando EstadoMensualEmpleado ID {estado_id}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al borrar el registro: {e_del}")
            # Redirigir de vuelta a la lista si falla
            return redirect('lista_estado_mensual')

    # Si es método GET, mostrar la página de confirmación
    context = {
        'estado': estado,
        'titulo_pagina': f"Confirmar Borrado Estado: {estado}"
    }
    return render(request, 'sueldos/borrar_estado_mensual.html', context)






# --- Vistas para DetalleSueldo (Editar y Borrar - Sin cambios) ---
# ... (código de editar_detalle_sueldo y borrar_detalle_sueldo) ...

@login_required
@permission_required('sueldos.view_cierremensualdeestado', raise_exception=True)
def lista_cierres_mensuales(request):
    """ Muestra una lista de todos los Cierres Mensuales generados. """
    # Obtener parámetros de filtro (opcional, podrías añadir más adelante)
    # selected_mes = request.GET.get('mes', '')
    # selected_anio = request.GET.get('anio', '')
    # selected_tipo = request.GET.get('tipo_planilla', '')

    cierres_list = CierreMensual.objects.all().order_by('-anio', '-mes', 'tipo_planilla')

    # Aplicar filtros si se implementan
    # if selected_mes: cierres_list = cierres_list.filter(mes=selected_mes)
    # ...

    # Paginación
    page = request.GET.get('page', 1)
    paginator = Paginator(cierres_list, 25) # Mostrar 25 cierres por página
    try:
        cierres_paginados = paginator.page(page)
    except PageNotAnInteger:
        cierres_paginados = paginator.page(1)
    except EmptyPage:
        cierres_paginados = paginator.page(paginator.num_pages)

    context = {
        'cierres_mensuales': cierres_paginados,
        'titulo_pagina': 'Historial de Generación de Estados Mensuales'
        # 'filter_form': Un formulario de filtro si lo creas
    }
    return render(request, 'sueldos/lista_cierres_mensuales.html', context)


@login_required
@permission_required('sueldos.delete_cierremensualdeestado', raise_exception=True)
def borrar_cierre_mensual(request, cierre_id):
    """
    Permite borrar un CierreMensual específico y todos los
    EstadoMensualEmpleado asociados (CASCADE).
    Muestra una página de confirmación antes de borrar.
    """
    cierre = get_object_or_404(CierreMensual, pk=cierre_id)
    # Contar cuántos detalles se borrarán para mostrar en la confirmación
    num_estados_asociados = cierre.estados_empleados.count()

    if request.method == 'POST':
        try:
            cierre_str = str(cierre) # Guardar descripción para el mensaje
            # Borrar el CierreMensual. La BD se encargará de borrar los
            # EstadoMensualEmpleado asociados por el CASCADE.
            cierre.delete()
            messages.success(request, f"Cierre Mensual '{cierre_str}' y sus {num_estados_asociados} estados asociados han sido borrados exitosamente.")
            # Redirigir a la lista de cierres
            return redirect('lista_cierres_mensuales')
        except Exception as e_del:
            logger.error(f"Error borrando CierreMensual ID {cierre_id}: {e_del}", exc_info=True)
            messages.error(request, f"Ocurrió un error al intentar borrar el cierre mensual: {e_del}")
            # Redirigir de vuelta a la lista incluso si hay error
            return redirect('lista_cierres_mensuales')

    # Si es método GET, mostrar la página de confirmación
    context = {
        'cierre': cierre,
        'num_estados': num_estados_asociados,
        'titulo_pagina': f"Confirmar Borrado Cierre: {cierre}"
    }
    return render(request, 'sueldos/borrar_cierre_mensual.html', context)


@login_required
@permission_required('sueldos.delete_cierremensualdeestado', raise_exception=True)
def ver_detalle_cierre(request, cierre_id):
    cierre = get_object_or_404(CierreMensual, pk=cierre_id)

    # Obtener los estados asociados a este cierre SIN ordenamiento por campos externos
    estados_list_qs = EstadoMensualEmpleado.objects.filter(cierre_mensual=cierre) \
                                                .order_by('pk') # Ordenar por un campo local o quitar .order_by()

    # Paginación ANTES del enriquecimiento
    page = request.GET.get('page', 1)
    paginator = Paginator(estados_list_qs, 50)
    try:
        estados_pagina_actual_objetos = paginator.page(page) # Renombrar para claridad
    except PageNotAnInteger:
        estados_pagina_actual_objetos = paginator.page(1)
    except EmptyPage:
        estados_pagina_actual_objetos = paginator.page(paginator.num_pages)

    # --- Enriquecimiento Manual ---
    ids_personal_pagina = [e.personal_externo_id for e in estados_pagina_actual_objetos if e.personal_externo_id]
    personas_externas_map = {}
    if PLANILLA_APP_AVAILABLE and ids_personal_pagina:
        try:
            personas_qs = PrincipalPersonalExterno.objects.using('personas_db') \
                .filter(id__in=ids_personal_pagina) \
                .only('id', 'ci', 'nombre', 'apellido_paterno', 'apellido_materno')
            personas_externas_map = {p.id: p for p in personas_qs}
        except Exception as e_ext:
            logger.error(f"Error obteniendo datos externos en ver_detalle_cierre: {e_ext}", exc_info=True)
            messages.warning(request, "No se pudieron cargar todos los datos del personal.")

    # Convertir Page a lista para poder añadir atributos y luego ordenar
    lista_enriquecida = list(estados_pagina_actual_objetos.object_list)

    for estado_obj in lista_enriquecida:
        persona = personas_externas_map.get(estado_obj.personal_externo_id)
        if persona:
            try: estado_obj.nombre_completo_externo = persona.nombre_completo
            except AttributeError: estado_obj.nombre_completo_externo = f"{persona.nombre or ''} {persona.apellido_paterno or ''} {persona.apellido_materno or ''}".strip()
            estado_obj.ci_externo = persona.ci or "S/CI"
        else:
            estado_obj.nombre_completo_externo = f"ID Ext: {estado_obj.personal_externo_id}"
            estado_obj.ci_externo = "N/A"

    # --- Ordenar la lista enriquecida en Python ---
    # (Opcional: si necesitas un orden específico por nombre)
    try:
        lista_enriquecida.sort(key=lambda x: (
            (getattr(x, 'nombre_completo_externo', '') or '').split(' ')[1] if len((getattr(x, 'nombre_completo_externo', '') or '').split(' ')) > 1 else '', # Apellido Paterno
            (getattr(x, 'nombre_completo_externo', '') or '').split(' ')[2] if len((getattr(x, 'nombre_completo_externo', '') or '').split(' ')) > 2 else '', # Apellido Materno
            (getattr(x, 'nombre_completo_externo', '') or '').split(' ')[0]  # Nombre
        ))
    except Exception as e_sort:
         logger.warning(f"No se pudo ordenar la lista enriquecida: {e_sort}")
    # --------------------------------------------

    # Re-construir el objeto Page con la lista ordenada (si se va a usar en la plantilla como tal)
    # O simplemente pasar la lista_enriquecida y ajustar la plantilla
    # Por ahora, pasaremos la lista y ajustaremos el template de paginación si es necesario

    context = {
        'cierre_mensual': cierre,
        'estados_empleados_lista': lista_enriquecida, # Pasar la lista Python enriquecida y ordenada
        'estados_empleados_page_obj': estados_pagina_actual_objetos, # Pasar el objeto Page para la paginación
        'titulo_pagina': f"Detalle Cierre Mensual: {cierre.mes}/{cierre.anio} ({cierre.get_tipo_planilla_display()})"
    }
    return render(request, 'sueldos/ver_detalle_cierre.html', context)