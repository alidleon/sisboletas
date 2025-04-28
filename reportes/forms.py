# reportes/forms.py
import logging
from django import forms
from django.db import models # Necesario para isinstance(..., models.DecimalField) etc.
from .models import DetalleAsistencia, PlanillaAsistencia
from decimal import Decimal # Necesario para asignar Decimal('0.00')
from decimal import Decimal, InvalidOperation
from django.core.exceptions import FieldDoesNotExist

logger = logging.getLogger(__name__)

class PlanillaAsistenciaForm(forms.Form):
    """
    Formulario para seleccionar los parámetros para crear
    una nueva Planilla de Asistencia. (Lo incluyo por contexto, sin cambios)
    """
    # ... (tu código para PlanillaAsistenciaForm) ...
    mes = forms.IntegerField(
        label="Mes",
        min_value=1,
        max_value=12,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 4'})
    )
    anio = forms.IntegerField(
        label="Año",
        # min_value=date.today().year - 10, # Puedes ajustar rangos si quieres
        # max_value=date.today().year + 1,
        # initial=date.today().year,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 2024'})
    )
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=PlanillaAsistencia.TIPO_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class EditarPlanillaAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar los campos de la cabecera de una PlanillaAsistencia.
    (Lo incluyo por contexto, sin cambios)
    """
    # ... (tu código para EditarPlanillaAsistenciaForm) ...
    class Meta:
        model = PlanillaAsistencia
        fields = ['mes', 'anio', 'estado']
        # ... (widgets y método clean si los tienes) ...


# --- Inicio DetalleAsistenciaForm Modificado ---
class DetalleAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar los campos de un registro DetalleAsistencia.
    Convierte campos numéricos vacíos a 0 antes de validar/guardar.
    """
    class Meta:
        model = DetalleAsistencia
        # Lista completa de campos editables desde el panel
        fields = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad',
            'iza_bandera', 'observaciones',
        ]
        # Widgets opcionales para mejorar la entrada
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            # Ejemplo de cómo añadir 'step' para inputs numéricos HTML5
            'omision_cant': forms.NumberInput(attrs={'step': '1'}),
            'atrasos_minutos': forms.NumberInput(attrs={'step': '1'}),
            'omision_sancion': forms.NumberInput(attrs={'step': '0.01'}),
            'abandono_dias': forms.NumberInput(attrs={'step': '0.01'}),
            'abandono_sancion': forms.NumberInput(attrs={'step': '0.01'}),
            'faltas_dias': forms.NumberInput(attrs={'step': '0.01'}),
            'faltas_sancion': forms.NumberInput(attrs={'step': '0.01'}),
            'atrasos_sancion': forms.NumberInput(attrs={'step': '0.01'}),
            'vacacion': forms.NumberInput(attrs={'step': '0.01'}),
            'viajes': forms.NumberInput(attrs={'step': '0.01'}),
            'bajas_medicas': forms.NumberInput(attrs={'step': '0.01'}),
            'pcgh': forms.NumberInput(attrs={'step': '0.01'}),
            'perm_excep': forms.NumberInput(attrs={'step': '0.01'}),
            'asuetos': forms.NumberInput(attrs={'step': '0.01'}),
            'psgh': forms.NumberInput(attrs={'step': '0.01'}),
            'pcgh_embar_enf_base': forms.NumberInput(attrs={'step': '0.01'}),
            'actividad_navidad': forms.NumberInput(attrs={'step': '0.01'}),
            'iza_bandera': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def clean(self):
        """
        Limpia los datos del formulario.
        Convierte campos numéricos vacíos a 0.
        """
        cleaned_data = super().clean()

        # Lista de campos numéricos que por defecto serán 0 si están vacíos
        # Asegúrate que estos nombres coincidan con los 'fields' de arriba
        campos_numericos_a_cero = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad',
            'iza_bandera'
        ]

        for field_name in campos_numericos_a_cero:
            # Usamos .get() para evitar KeyError si el campo no pasó la validación inicial
            valor = cleaned_data.get(field_name)

            # Verificar si el valor es None (no enviado o inválido inicialmente) o un string vacío
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                try:
                    # Obtener la instancia del campo del *modelo* para saber su tipo
                    model_field = self.instance._meta.get_field(field_name)

                    # Asignar el tipo correcto de cero
                    if isinstance(model_field, models.DecimalField):
                        cleaned_data[field_name] = Decimal('0.00')
                    elif isinstance(model_field, (models.IntegerField, models.PositiveIntegerField, models.SmallIntegerField)):
                        cleaned_data[field_name] = 0
                    elif isinstance(model_field, models.FloatField): # Si usaras FloatField
                        cleaned_data[field_name] = 0.0
                    else:
                        # Si por alguna razón un campo no numérico está en la lista,
                        # podrías querer asignar None o un valor por defecto diferente.
                        # Por ahora, lo dejamos como 0 genérico si no es de los tipos comunes.
                        cleaned_data[field_name] = 0
                        logger.debug(f"Campo '{field_name}' vacío, establecido a 0 (tipo no específico detectado).")

                except FieldDoesNotExist:
                     # Esto no debería pasar si la lista 'campos_numericos_a_cero'
                     # coincide con los 'fields' del Meta, pero es una guarda.
                     logger.error(f"Error en form clean: El campo '{field_name}' no existe en el modelo DetalleAsistencia.")
                except Exception as e:
                     # Capturar otros posibles errores al obtener el campo del modelo
                     logger.error(f"Error inesperado procesando campo vacío '{field_name}' en form clean: {e}")


            # Opcional: Re-validar que no sean negativos (si el modelo no lo hace ya)
            # elif isinstance(valor, (int, Decimal, float)) and valor < 0:
            #    self.add_error(field_name, "Este valor no puede ser negativo.")


        # Importante: Siempre devolver el diccionario cleaned_data completo
        return cleaned_data

# --- Fin DetalleAsistenciaForm Modificado ---


class AddDetalleAsistenciaForm(forms.Form):
    """
    Formulario para buscar y añadir un nuevo DetalleAsistencia.
    (Lo incluyo por contexto, sin cambios)
    """
    ci_o_item = forms.CharField(
        label="CI o Nro. Item del Personal",
        required=True,
        max_length=20,
        widget=forms.TextInput(attrs={'placeholder': 'Ingrese CI o Item a buscar...'}),
        help_text="Ingrese el Carnet de Identidad o el Número de Ítem del personal que desea añadir."
    )