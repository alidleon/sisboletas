import logging
from django import forms
from django.db import models 
from .models import DetalleAsistencia, PlanillaAsistencia
from decimal import Decimal 
from decimal import Decimal, InvalidOperation
from django.core.exceptions import FieldDoesNotExist
from datetime import date

logger = logging.getLogger(__name__)

class PlanillaAsistenciaForm(forms.Form):
    """
    Formulario para seleccionar los parámetros para crear
    una nueva Planilla de Asistencia.
    """    
    ANIO_ACTUAL = date.today().year
    ANIO_MINIMO_PERMITIDO = 2020 
    ANIO_MAXIMO_PERMITIDO = ANIO_ACTUAL + 100 

    anio = forms.IntegerField(
        label="Año",
        required=True,
        min_value=ANIO_MINIMO_PERMITIDO, 
        max_value=ANIO_MAXIMO_PERMITIDO, 
        initial=ANIO_ACTUAL, 
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': f'Ej: {ANIO_ACTUAL}'
        }),
        help_text=f"Ingrese un año entre {ANIO_MINIMO_PERMITIDO} y {ANIO_MAXIMO_PERMITIDO}."
    )

    CHOICES_MESES = [('', '--- Seleccione Mes ---')] + [(str(i), str(i)) for i in range(1, 13)]
    
    mes = forms.ChoiceField(
        label="Mes",
        choices=CHOICES_MESES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}) 
    )

    CHOICES_TIPO_CON_VACIO = [('', '--- Seleccione Tipo ---')] + list(PlanillaAsistencia.TIPO_CHOICES)
    
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=CHOICES_TIPO_CON_VACIO,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}) 
    )

    def clean_anio(self):
        data_anio = self.cleaned_data.get('anio')
        if data_anio is not None: 
            if not (self.ANIO_MINIMO_PERMITIDO <= data_anio <= self.ANIO_MAXIMO_PERMITIDO):
                raise forms.ValidationError(
                    f"El año debe estar entre {self.ANIO_MINIMO_PERMITIDO} y {self.ANIO_MAXIMO_PERMITIDO}."
                )
        return data_anio 

    def clean_mes(self):
        data_mes_str = self.cleaned_data.get('mes')
        if not data_mes_str: 
            raise forms.ValidationError("Debe seleccionar un mes.")
        try:
            mes_int = int(data_mes_str)
            if not 1 <= mes_int <= 12: 
                raise forms.ValidationError("Mes seleccionado no es válido.")
            return mes_int 
        except (ValueError, TypeError):
            raise forms.ValidationError("Mes seleccionado no es válido.") 

    def clean_tipo(self):
        data_tipo = self.cleaned_data.get('tipo')
        if not data_tipo: 
            raise forms.ValidationError("Debe seleccionar un tipo de personal.")
        return data_tipo



class EditarPlanillaAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar la cabecera de una PlanillaAsistencia.
    Solo el estado y las observaciones son editables, con lógica de transición de estado.
    Mes, Año y Tipo se muestran como solo lectura.
    """

    anio = forms.IntegerField(label="Año", required=False)
    mes = forms.IntegerField(label="Mes", required=False)
    tipo = forms.CharField(label="Tipo de Personal", required=False) 

    class Meta:
        model = PlanillaAsistencia
        fields = ['anio', 'mes', 'tipo', 'estado', 'observaciones_generales']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'observaciones_generales': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)
        
        logger.debug(f"FORM EditarPlanillaAsistenciaForm __init__: instance={self.instance}, instance.pk={self.instance.pk if self.instance else 'No instance'}")
        logger.debug(f"FORM __init__: is_bound={self.is_bound}")


        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            self.fields['anio'].initial = instance.anio
            self.fields['anio'].widget.attrs['readonly'] = True
            self.fields['anio'].widget.attrs['class'] = 'form-control-plaintext' 
            self.fields['anio'].disabled = True 

            self.fields['mes'].initial = instance.mes
            self.fields['mes'].widget.attrs['readonly'] = True
            self.fields['mes'].widget.attrs['class'] = 'form-control-plaintext'
            self.fields['mes'].disabled = True

            self.fields['tipo'].initial = instance.get_tipo_display()
            self.fields['tipo'].widget = forms.TextInput(attrs={ 
                'readonly': True, 
                'class': 'form-control-plaintext'
            })
            self.fields['tipo'].disabled = True

            if not self.is_bound or not self.is_valid():
                current_estado = instance.estado
                estado_choices_disponibles = []
                TRANSICIONES_PERMITIDAS = {
                    'borrador': [('borrador', 'Mantener como Borrador'), ('validado', 'Validar Planilla')],
                    'validado': [('validado', 'Mantener como Validado'), ('archivado', 'Archivar Planilla')],
                    'archivado': [('archivado', 'Archivado (No se puede cambiar)')],
                }
                if current_estado == 'validado' and self.user and self.user.is_superuser:
                    if 'validado' not in [val for val, disp in TRANSICIONES_PERMITIDAS['validado']]: 
                         TRANSICIONES_PERMITIDAS['validado'].insert(0,('validado', 'Mantener como Validado'))
                    TRANSICIONES_PERMITIDAS['validado'].append(('borrador', 'Reabrir a Borrador (Admin)'))

                if current_estado in TRANSICIONES_PERMITIDAS:
                    estado_choices_disponibles = TRANSICIONES_PERMITIDAS[current_estado]
                else: 
                    estado_choices_disponibles = [(current_estado, f"Mantener como {instance.get_estado_display()}")]

                self.fields['estado'].choices = estado_choices_disponibles
                logger.debug(f"FORM __init__: Estado actual='{current_estado}', Choices para estado: {estado_choices_disponibles}")
            
            if instance.estado == 'archivado':
                self.fields['estado'].widget.attrs['disabled'] = True
                self.fields['observaciones_generales'].widget.attrs['disabled'] = True
        else:
            for field_name in self.fields:
                if field_name not in ['anio', 'mes', 'tipo']: 
                    self.fields[field_name].disabled = True


class DetalleAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar los campos de un registro DetalleAsistencia.
    Convierte campos numéricos vacíos a 0 antes de validar/guardar.
    """
    class Meta:
        model = DetalleAsistencia
        fields = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad',
            'iza_bandera', 'observaciones',
        ]
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3}),
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
        campos_numericos_a_cero = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad',
            'iza_bandera'
        ]

        for field_name in campos_numericos_a_cero:
            valor = cleaned_data.get(field_name)
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                try:
                    model_field = self.instance._meta.get_field(field_name)
                    if isinstance(model_field, models.DecimalField):
                        cleaned_data[field_name] = Decimal('0.00')
                    elif isinstance(model_field, (models.IntegerField, models.PositiveIntegerField, models.SmallIntegerField)):
                        cleaned_data[field_name] = 0
                    elif isinstance(model_field, models.FloatField): 
                        cleaned_data[field_name] = 0.0
                    else:

                        cleaned_data[field_name] = 0
                        logger.debug(f"Campo '{field_name}' vacío, establecido a 0 (tipo no específico detectado).")

                except FieldDoesNotExist:
                    
                     logger.error(f"Error en form clean: El campo '{field_name}' no existe en el modelo DetalleAsistencia.")
                except Exception as e:
                     logger.error(f"Error inesperado procesando campo vacío '{field_name}' en form clean: {e}")

        return cleaned_data
    
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