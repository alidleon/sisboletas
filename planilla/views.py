from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Planilla, DetalleBonoTe
from datetime import date
from django.contrib import messages
from .forms import DetalleBonoTeForm
from .forms import PlanillaForm  # Necesitas crear un formulario para editar la planilla
from datetime import datetime
from django.core.exceptions import ValidationError
from .models import PrincipalPersonal # ¡Importa el nuevo modelo!

@login_required
def seleccionar_tipo_planilla(request):
    """
    Vista para seleccionar el tipo de planilla (Planta, Contrato, Consultor) para Bono TE.
    Redirige a la vista 'crear_planilla' con el tipo seleccionado.
    """
    if request.method == 'POST':  # Verifica si es una solicitud POST
        tipo = request.POST.get('tipo')  # Obtiene el tipo seleccionado del formulario

        # Validación básica del tipo
        tipos_validos = dict(Planilla.TIPO_CHOICES).keys()
        if tipo in tipos_validos:
            # Redirige a la vista 'crear_planilla' con el tipo como parámetro
            return redirect('crear_planilla', tipo=tipo)
        else:
            # Maneja el caso en que el tipo seleccionado no es válido
            context = {
                'tipos_planilla': Planilla.TIPO_CHOICES,
                'error_message': 'Seleccione un tipo de planilla válido.',
            }
            return render(request, 'planillas/seleccionar_tipo_planilla.html', context)

    else:  # Si es una solicitud GET, muestra el formulario de selección
        context = {
            'tipos_planilla': Planilla.TIPO_CHOICES,
        }
        return render(request, 'planillas/seleccionar_tipo_planilla.html', context)



# ----------------------------------------------------------------

@login_required
def crear_planilla(request, tipo):
    now = datetime.now()
    mes_actual = now.month
    anio_actual = now.year
    planillas_con_bono_te = Planilla.objects.filter(detalles_bono_te__isnull=False, tipo=tipo).distinct()

    if request.method == 'POST':
        planilla_form = PlanillaForm(request.POST)

        if planilla_form.is_valid():
            mes = planilla_form.cleaned_data['mes']
            anio = planilla_form.cleaned_data['anio']
            dias_habiles = planilla_form.cleaned_data['dias_habiles'] # Recuperamos el valor de dias_habiles
            planilla_base_id = request.POST.get('planilla_base')

            # Verificar si ya existe una planilla con el mismo mes, año y tipo
            existing_planilla = Planilla.objects.filter(mes=mes, anio=anio, tipo=tipo).first()
            if existing_planilla:
                planilla_form.add_error(None, 'Ya existe una planilla con el mismo mes, año y tipo.')
                return render(request, 'planillas/crear_planilla.html', {
                    'planilla_form': planilla_form,
                    'tipo': tipo,
                    'planillas_con_bono_te': planillas_con_bono_te,
                    'mes_actual': mes_actual,
                    'anio_actual': anio_actual,
                })

            # CREACIÓN DE LA PLANILLA
            planilla = Planilla.objects.create(
                mes=mes,
                anio=anio,
                tipo=tipo,
                dias_habiles=dias_habiles, # Asignamos el valor de dias_habiles
                usuario_elaboracion=request.user,
                bono_te=True,
                estado='pendiente'
            )

            messages.success(request, 'Planilla creada correctamente')
            return redirect('lista_planillas')
        else:
            return render(request, 'planillas/crear_planilla.html', {
                'planilla_form': planilla_form,
                'tipo': tipo,
                'planillas_con_bono_te': planillas_con_bono_te,
                'mes_actual': mes_actual,
                'anio_actual': anio_actual,
            })

    else:
        planilla_form = PlanillaForm(initial={'mes': mes_actual, 'anio': anio_actual})

    return render(request, 'planillas/crear_planilla.html', {
        'planilla_form': planilla_form,
        'tipo': tipo,
        'planillas_con_bono_te': planillas_con_bono_te,
        'mes_actual': mes_actual,
        'anio_actual': anio_actual,
    })

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

####----------------------------------------------------------------

#---------------------------------------------------------------
#llenar tabla bono te



@login_required
def llenar_detalle_bono_te(request, planilla_id):
    planilla = get_object_or_404(Planilla, pk=planilla_id)

    if request.method == 'POST':
        form = DetalleBonoTeForm(request.POST)  # No pasamos instance
        if form.is_valid():
            # Imprimir los datos del formulario
            print("Datos del formulario:", form.cleaned_data)
            detalle_bono_te = form.save(commit=False) # No guardamos inmediatamente
            detalle_bono_te.id_planilla = planilla # Asignamos la planilla
            detalle_bono_te.dias_habiles = planilla.dias_habiles
            # Asignar los valores del formulario al objeto
            detalle_bono_te.mes = form.cleaned_data['mes']
            
            detalle_bono_te.faltas = form.cleaned_data['faltas']
            detalle_bono_te.vacacion = form.cleaned_data['vacacion']
            detalle_bono_te.viajes = form.cleaned_data['viajes']
            detalle_bono_te.bajas_medicas = form.cleaned_data['bajas_medicas']
            detalle_bono_te.pcgh = form.cleaned_data['pcgh']
            detalle_bono_te.psgh = form.cleaned_data['psgh']
            detalle_bono_te.perm_excep = form.cleaned_data['perm_excep']
            detalle_bono_te.asuetos = form.cleaned_data['asuetos']
            detalle_bono_te.pcgh_embar_enf_base = form.cleaned_data['pcgh_embar_enf_base']
            detalle_bono_te.descuentos = form.cleaned_data['descuentos']
            try:
                detalle_bono_te.save()# Guardamos ahora
                messages.success(request, 'Detalle Bono TE creado correctamente.')
                return redirect('lista_planillas')
            except ValidationError as e:
                form.add_error(None, e.message) # Agrega el error al formulario
                messages.error(request, 'Por favor, corrige los errores en el formulario.')
        else:
            # Mostrar los errores del formulario al usuario
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error en el campo {field}: {error}")
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = DetalleBonoTeForm(initial={
            'mes': planilla.mes,
            'dias_habiles': planilla.dias_habiles, # Inicializamos dias_habiles
        })

    return render(request, 'planillas/llenar_detalle_bono_te.html', {
        'form': form,
        'planilla': planilla,
        'dias_habiles': planilla.dias_habiles, # Pasamos dias_habiles al contexto
    })

#---------------------------------------------------------------
#lista de bonote
def lista_bono_te(request):
    detalles_bono_te = DetalleBonoTe.objects.all() # Obtiene todos los DetalleBonoTe
    return render(request, 'planillas/lista_bono_te.html', {'detalles_bono_te': detalles_bono_te})

#edtiar y borrar bonote
@login_required
def editar_bono_te(request, detalle_id):
    detalle_bono_te = get_object_or_404(DetalleBonoTe, pk=detalle_id)
    planilla_id = detalle_bono_te.id_planilla.id  # Obtener el ID de la planilla antes del POST
    if request.method == 'POST':
        form = DetalleBonoTeForm(request.POST, instance=detalle_bono_te)
        if form.is_valid():
            form.save()
            messages.success(request, 'Detalle Bono TE editado correctamente.')
            # Redirige a ver_detalles_bono_te con el ID de la planilla
            return redirect('ver_detalles_bono_te', planilla_id=planilla_id)
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = DetalleBonoTeForm(instance=detalle_bono_te)
    return render(request, 'planillas/editar_bono_te.html', {'form': form, 'detalle_bono_te': detalle_bono_te})

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
# ver bonotes
@login_required
def ver_detalles_bono_te(request, planilla_id):
    planilla = get_object_or_404(Planilla, pk=planilla_id)
    detalles_bono_te = DetalleBonoTe.objects.filter(id_planilla=planilla)

    return render(request, 'planillas/ver_detalles_bono_te.html', {
        'planilla': planilla,
        'detalles_bono_te': detalles_bono_te,
    })




#  ----------------------------------------------------------------
# consulta a la base de datos externa

# --- Añade esto a tu archivo planilla/views.py ---


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