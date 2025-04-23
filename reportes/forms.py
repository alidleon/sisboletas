# reportes/forms.py

from django import forms
from django.core.exceptions import ValidationError
from datetime import date

# Importamos el modelo PlanillaAsistencia para usar sus choices y validar
from .models import PlanillaAsistencia, DetalleAsistencia

class PlanillaAsistenciaForm(forms.Form):
    """
    Formulario para seleccionar los parámetros para crear
    una nueva Planilla de Asistencia.
    """
    # Usamos IntegerField para mes y año
    mes = forms.IntegerField(
        label="Mes",
        min_value=1,
        max_value=12,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 4'})
    )
    anio = forms.IntegerField(
        label="Año",
        min_value=date.today().year - 10, # Rango razonable (últimos 10 años)
        max_value=date.today().year + 1,  # Hasta el próximo año
        initial=date.today().year, # Valor inicial por defecto
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 2024'})
    )
    # Usamos ChoiceField y obtenemos las opciones desde el modelo
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=PlanillaAsistencia.TIPO_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}) # Opcional: clase CSS
    )

    # Puedes añadir validaciones adicionales aquí si son necesarias
    # Por ejemplo, clean() para validar combinaciones, aunque la
    # validación de duplicados la haremos en la vista.

class EditarPlanillaAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar los campos de la cabecera de una PlanillaAsistencia.
    Ahora permite editar mes y año, y elimina observaciones generales.
    """
    class Meta:
        model = PlanillaAsistencia
        # Campos editables: mes, anio, estado.
        # Excluimos 'tipo' para evitar complicaciones con el personal asociado.
        # Excluimos campos automáticos y de validación.
        fields = [
            'mes',
            'anio',
            'estado',
            # 'observaciones_generales', # <-- Campo eliminado
        ]
        # Añadir widgets para mes y año si quieres control
        widgets = {
            'mes': forms.NumberInput(attrs={'placeholder': 'Ej: 4'}),
            'anio': forms.NumberInput(attrs={'placeholder': 'Ej: 2024'}),
            # 'observaciones_generales': forms.Textarea(attrs={'rows': 4}), # <-- Eliminado
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        # Deshabilitar campos si el estado es 'validado' o 'archivado'
        if instance and instance.estado in ['validado', 'archivado']:
            for field_name in self.fields:
                # Permitimos editar estado incluso si está validado/archivado?
                # Si no, añadir 'estado' a la lista de deshabilitados.
                # if field_name in ['mes', 'anio', 'estado']: # Ejemplo si estado tampoco se edita
                if field_name in ['mes', 'anio']: # Solo deshabilitar mes y año
                    self.fields[field_name].disabled = True
                    self.fields[field_name].help_text = "No se puede cambiar el periodo de una planilla validada o archivada."

    def clean(self):
        """
        Valida que la combinación mes/año/tipo no exista ya para otra planilla.
        """
        cleaned_data = super().clean()
        mes = cleaned_data.get('mes')
        anio = cleaned_data.get('anio')
        # Obtenemos el tipo de la instancia que estamos editando, ya que no está en el form
        tipo = self.instance.tipo if self.instance else None

        # Solo validamos si los campos necesarios están presentes y si mes o año han cambiado
        # (asumiendo que 'tipo' no cambia)
        if mes and anio and tipo and ('mes' in self.changed_data or 'anio' in self.changed_data):
            # Buscamos si existe OTRA planilla con la misma combinación
            queryset = PlanillaAsistencia.objects.filter(
                mes=mes,
                anio=anio,
                tipo=tipo
            ).exclude(pk=self.instance.pk) # Excluimos la planilla actual

            if queryset.exists():
                # Usamos non_field_errors para un error general del formulario
                raise ValidationError(
                    f"Ya existe un reporte de asistencia para {dict(PlanillaAsistencia.TIPO_CHOICES).get(tipo)} "
                    f"en el periodo {mes}/{anio}. Por favor, elija un periodo diferente.",
                    code='duplicate_period_type'
                )
        return cleaned_data

    # Puedes mantener la validación clean_estado si la tenías o añadir otras
    def clean_estado(self):
        estado = self.cleaned_data.get('estado')
        instance = self.instance # El objeto PlanillaAsistencia que se está editando
        if instance and instance.pk and instance.estado != 'borrador' and estado == 'borrador':
             raise ValidationError("No se puede revertir una planilla a estado 'Borrador'.")
        return estado
    

class DetalleAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar los campos de un registro DetalleAsistencia.
    """
    class Meta:
        model = DetalleAsistencia
        # Incluimos TODOS los campos que el usuario debe poder modificar.
        fields = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh',
            'pcgh_embar_enf_base', 
            'actividad_navidad', 'iza_bandera', 'observaciones',
        ]
        # Opcional: Widgets si quieres personalizar
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }

    # Puedes añadir validaciones clean_fieldname() o clean() aquí
    # def clean_... (tu validación)


    # reportes/forms.py



class AddDetalleAsistenciaForm(forms.Form):
    """
    Formulario para buscar y añadir un nuevo DetalleAsistencia a una
    PlanillaAsistencia existente, buscando por CI o Item.
    """
    # Usamos CharField, la validación de si es CI o Item se hará en la vista/clean
    ci_o_item = forms.CharField(
        label="CI o Nro. Item del Personal",
        required=True,
        max_length=20, # Longitud suficiente para CI o Item
        widget=forms.TextInput(attrs={'placeholder': 'Ingrese CI o Item a buscar...'}),
        help_text="Ingrese el Carnet de Identidad o el Número de Ítem del personal que desea añadir."
    )

    # Opcional: Podríamos añadir campos para valores iniciales de asistencia aquí,
    # pero por ahora, el detalle se creará con ceros por defecto.

    # La validación principal (existencia externa, duplicado interno)
    # la haremos en la vista para poder acceder a la planilla_asistencia y a la BD externa.