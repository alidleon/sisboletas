# reportes/forms.py
import logging
from django import forms
from django.db import models # Necesario para isinstance(..., models.DecimalField) etc.
from .models import DetalleAsistencia, PlanillaAsistencia
from decimal import Decimal # Necesario para asignar Decimal('0.00')
from decimal import Decimal, InvalidOperation
from django.core.exceptions import FieldDoesNotExist
from datetime import date

logger = logging.getLogger(__name__)

class PlanillaAsistenciaForm(forms.Form):
    """
    Formulario para seleccionar los parámetros para crear
    una nueva Planilla de Asistencia.
    """
    
    # --- CAMPO AÑO ---
    ANIO_ACTUAL = date.today().year
    ANIO_MINIMO_PERMITIDO = 2020 # O el año que consideres como inicio válido
    ANIO_MAXIMO_PERMITIDO = ANIO_ACTUAL + 100 # Permitir hasta 2 años en el futuro

    anio = forms.IntegerField(
        label="Año",
        required=True,
        min_value=ANIO_MINIMO_PERMITIDO, # Validación básica del widget
        max_value=ANIO_MAXIMO_PERMITIDO, # Validación básica del widget
        initial=ANIO_ACTUAL, # Año actual por defecto
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': f'Ej: {ANIO_ACTUAL}'
        }),
        help_text=f"Ingrese un año entre {ANIO_MINIMO_PERMITIDO} y {ANIO_MAXIMO_PERMITIDO}."
    )

    # --- CAMPO MES ---
    # La opción vacía se define primero
    CHOICES_MESES = [('', '--- Seleccione Mes ---')] + [(str(i), str(i)) for i in range(1, 13)]
    # Si quieres nombres de mes:
    # NOMBRES_MESES_LITERAL_DICT = {
    #     1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    #     5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    #     9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    # }
    # CHOICES_MESES = [('', '--- Seleccione Mes ---')] + [(str(k), v) for k, v in NOMBRES_MESES_LITERAL_DICT.items()]
    
    mes = forms.ChoiceField(
        label="Mes",
        choices=CHOICES_MESES,
        required=True,
        # No establecemos 'initial' aquí para que "--- Seleccione Mes ---" sea la opción por defecto visible.
        # Si el usuario no selecciona nada, la validación 'required' y 'clean_mes' lo detectarán.
        widget=forms.Select(attrs={'class': 'form-control'}) # o 'form-control'
    )

    # --- CAMPO TIPO ---
    CHOICES_TIPO_CON_VACIO = [('', '--- Seleccione Tipo ---')] + list(PlanillaAsistencia.TIPO_CHOICES)
    
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=CHOICES_TIPO_CON_VACIO,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}) # o 'form-control'
    )

    def clean_anio(self):
        data_anio = self.cleaned_data.get('anio')
        if data_anio is not None: # IntegerField ya debería haber validado si es un entero
            if not (self.ANIO_MINIMO_PERMITIDO <= data_anio <= self.ANIO_MAXIMO_PERMITIDO):
                raise forms.ValidationError(
                    f"El año debe estar entre {self.ANIO_MINIMO_PERMITIDO} y {self.ANIO_MAXIMO_PERMITIDO}."
                )
        # Si es None (porque no se proveyó y no era required, o falló la conversión a int),
        # la validación 'required' del campo ya lo habría atrapado.
        # Aquí solo validamos el rango si es un número.
        return data_anio # Devuelve el entero

    def clean_mes(self):
        data_mes_str = self.cleaned_data.get('mes')
        if not data_mes_str: # Si se seleccionó la opción vacía "--- Seleccione Mes ---" (value='')
            raise forms.ValidationError("Debe seleccionar un mes.")
        try:
            mes_int = int(data_mes_str)
            if not 1 <= mes_int <= 12: # Aunque ChoiceField ya lo valida, una doble verificación no hace daño
                raise forms.ValidationError("Mes seleccionado no es válido.")
            return mes_int # Devuelve el entero
        except (ValueError, TypeError):
            raise forms.ValidationError("Mes seleccionado no es válido.") # Si el valor no es un número convertible

    def clean_tipo(self):
        data_tipo = self.cleaned_data.get('tipo')
        if not data_tipo: # Si se seleccionó la opción vacía "--- Seleccione Tipo ---"
            raise forms.ValidationError("Debe seleccionar un tipo de personal.")
        # La validación de que 'data_tipo' sea una de las TIPO_CHOICES válidas
        # ya la realiza el ChoiceField por nosotros.
        return data_tipo



class EditarPlanillaAsistenciaForm(forms.ModelForm):
    """
    Formulario para editar la cabecera de una PlanillaAsistencia.
    Solo el estado y las observaciones son editables, con lógica de transición de estado.
    Mes, Año y Tipo se muestran como solo lectura.
    """
    # Usamos los nombres de campo del modelo para que se vinculen automáticamente a la instancia
    # y se pueblen con los valores existentes. Luego los deshabilitamos.
    anio = forms.IntegerField(label="Año", required=False)
    mes = forms.IntegerField(label="Mes", required=False)
    tipo = forms.CharField(label="Tipo de Personal", required=False) # Se llenará con get_tipo_display

    class Meta:
        model = PlanillaAsistencia
        # Campos que el ModelForm gestionará directamente para el guardado (si no están disabled)
        fields = ['anio', 'mes', 'tipo', 'estado', 'observaciones_generales']
        widgets = {
            # Los widgets para anio, mes, tipo se definirán/modificarán en __init__
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
            # Configurar campos de solo lectura
            self.fields['anio'].initial = instance.anio
            self.fields['anio'].widget.attrs['readonly'] = True
            self.fields['anio'].widget.attrs['class'] = 'form-control-plaintext' # Estilo de solo lectura Bootstrap
            self.fields['anio'].disabled = True # No se enviará en POST

            self.fields['mes'].initial = instance.mes
            self.fields['mes'].widget.attrs['readonly'] = True
            self.fields['mes'].widget.attrs['class'] = 'form-control-plaintext'
            self.fields['mes'].disabled = True

            self.fields['tipo'].initial = instance.get_tipo_display()
            self.fields['tipo'].widget = forms.TextInput(attrs={ # Asegurar que sea TextInput
                'readonly': True, 
                'class': 'form-control-plaintext'
            })
            self.fields['tipo'].disabled = True


            # Lógica para restringir las opciones de estado disponibles en el <select>
            # Solo modificar las choices si el formulario NO está vinculado (GET) o si NO es válido (re-render por error)
            # para asegurar que las choices correctas se usen para la validación del POST.
            if not self.is_bound or not self.is_valid():
                current_estado = instance.estado
                estado_choices_disponibles = []
                TRANSICIONES_PERMITIDAS = {
                    'borrador': [('borrador', 'Mantener como Borrador'), ('validado', 'Validar Planilla')],
                    'validado': [('validado', 'Mantener como Validado'), ('archivado', 'Archivar Planilla')],
                    'archivado': [('archivado', 'Archivado (No se puede cambiar)')],
                }
                # Opción para reabrir desde validado si es superusuario
                if current_estado == 'validado' and self.user and self.user.is_superuser:
                    if 'validado' not in [val for val, disp in TRANSICIONES_PERMITIDAS['validado']]: # Por si acaso
                         TRANSICIONES_PERMITIDAS['validado'].insert(0,('validado', 'Mantener como Validado'))
                    TRANSICIONES_PERMITIDAS['validado'].append(('borrador', 'Reabrir a Borrador (Admin)'))

                if current_estado in TRANSICIONES_PERMITIDAS:
                    estado_choices_disponibles = TRANSICIONES_PERMITIDAS[current_estado]
                else: 
                    # Para estados no contemplados en TRANSICIONES_PERMITIDAS (ej. 'completo', 'rechazado' si aún existen en BD)
                    # Se permite mantener el estado actual.
                    estado_choices_disponibles = [(current_estado, f"Mantener como {instance.get_estado_display()}")]
                    # Podrías decidir deshabilitar el cambio si el estado actual no está en tu flujo simplificado.
                    # self.fields['estado'].widget.attrs['disabled'] = True

                self.fields['estado'].choices = estado_choices_disponibles
                logger.debug(f"FORM __init__: Estado actual='{current_estado}', Choices para estado: {estado_choices_disponibles}")
            
            # Si el estado es archivado, deshabilitar todo lo editable
            if instance.estado == 'archivado':
                self.fields['estado'].widget.attrs['disabled'] = True
                self.fields['observaciones_generales'].widget.attrs['disabled'] = True
        else:
            # Si no hay instancia (ej. error o uso incorrecto del form)
            for field_name in self.fields:
                if field_name not in ['anio', 'mes', 'tipo']: # Estos ya son Char/Integer
                    self.fields[field_name].disabled = True


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