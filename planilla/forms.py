# planilla/forms.py (Versión Original)

from django import forms
from .models import DetalleBonoTe, Planilla # Solo modelos internos
from django.core.exceptions import ValidationError
from reportes.models import PlanillaAsistencia

class DetalleBonoTeForm(forms.ModelForm):
    dias_habiles = forms.DecimalField(
        label='Días Hábiles (Planilla)',
        required=False,
        widget=forms.NumberInput(attrs={'readonly': 'readonly', 'class':'form-control form-control-sm'}) # Añadir clases
    )

    class Meta:
        model = DetalleBonoTe
        fields = [
            'mes', 
            
            'faltas', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'psgh', 
            'perm_excep', 'asuetos', 'pcgh_embar_enf_base', 
            'descuentos', 'observaciones_bono'
        ]
        # Opcional: definir widgets para añadir clases de Bootstrap
        widgets = {
            'faltas': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'vacacion': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'viajes': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'bajas_medicas': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'pcgh': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'psgh': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'perm_excep': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'asuetos': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'pcgh_embar_enf_base': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'descuentos': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
            'observaciones_bono': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'mes' in self.fields:
            self.fields['mes'].widget.attrs['readonly'] = True
            self.fields['mes'].widget.attrs['class'] = 'form-control form-control-sm' # Añadir clase
        
        # Aplicar clases a otros campos si no se definieron en Meta.widgets
        for field_name, field in self.fields.items():
            if field_name != 'dias_habiles' and field_name != 'mes': # Estos ya tienen widgets o se manejan arriba
                if isinstance(field.widget, forms.NumberInput):
                    field.widget.attrs.update({'class': 'form-control form-control-sm', 'step': '1.00'})
                elif isinstance(field.widget, forms.Textarea):
                    field.widget.attrs.update({'class': 'form-control form-control-sm', 'rows': 2})
                elif not field.widget.attrs.get('class'): # Si no tiene clase, añadir una genérica
                    field.widget.attrs.update({'class': 'form-control form-control-sm'})


class PlanillaForm(forms.ModelForm):
    """
    Formulario para crear una Planilla de Bono TE.
    El usuario primero filtra por tipo (en el template, con recarga GET),
    luego selecciona una PlanillaAsistencia base de las opciones filtradas,
    e ingresa los días hábiles.
    """
    planilla_asistencia_base_selector = forms.ModelChoiceField(
        queryset=PlanillaAsistencia.objects.none(), # Se poblará dinámicamente en __init__
        label="Planilla de Asistencia Validada Base",
        required=False, # Inicialmente no es requerido; se ajusta en __init__ y se valida en clean()
        empty_label="Seleccione un tipo de planilla arriba para ver opciones",
        help_text="Solo se muestran planillas de asistencia validadas y no usadas para el tipo seleccionado."
    )

    # dias_habiles se toma de los fields del modelo en Meta, pero definimos su 'required' aquí
    # para que sea False si el selector de asistencia está deshabilitado.
    # Alternativamente, se puede dejar required=True y el form solo validará si no está disabled.
    # La lógica en clean() es más robusta.
    dias_habiles = forms.DecimalField(
        label='Días Hábiles del Mes para Bono TE',
        required=False, # Inicialmente no es requerido; se ajusta en clean()
        max_digits=5,
        decimal_places=2,
        min_value=0, # Validación básica a nivel de campo
        # widget=forms.NumberInput(attrs={'step': '0.01'}) # Opcional para UX
    )

    class Meta:
        model = Planilla
        fields = [
            # Nota: 'planilla_asistencia_base_selector' NO es un campo del modelo Planilla.
            # Es un campo del FORMULARIO. El campo del modelo es 'planilla_asistencia_base'.
            # Por lo tanto, no se lista en 'fields' si queremos definirlo explícitamente arriba.
            # Si lo listáramos aquí Y lo definiéramos arriba, el de arriba tomaría precedencia.
            # Lo correcto es definirlo arriba y NO listarlo aquí, o listarlo aquí y
            # modificar self.fields['nombre_campo_modelo'] en __init__.
            # Para claridad, lo definimos explícitamente y no lo ponemos en fields.
            # Los campos que SÍ son del modelo y queremos en el form son:
            'dias_habiles',
            # 'ufvi', # Si los tenías y son manuales, añádelos aquí.
            # 'ufvf',
            # 'smn',
        ]
        # No incluimos 'mes', 'anio', 'tipo', 'planilla_asistencia_base' aquí
        # ya que se derivan/asignan en la vista.

    def __init__(self, *args, **kwargs):
        # Obtener 'tipo_filtro' pasado desde la vista ANTES de llamar al super()
        # para que no interfiera con los campos del ModelForm.
        self.tipo_filtro = kwargs.pop('tipo_filtro', None)
        super().__init__(*args, **kwargs)

        # Configurar el campo del formulario 'planilla_asistencia_base_selector'
        # (que es diferente del campo del modelo 'planilla_asistencia_base')
        
        # Por defecto, el selector de asistencia está deshabilitado.
        self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled'] = True
        # 'required' ya es False por la definición del campo arriba.

        if self.tipo_filtro:
            # Si se proporcionó un tipo_filtro, intentar poblar el queryset
            self.fields['planilla_asistencia_base_selector'].empty_label = "--- Elija una Planilla de Asistencia ---"
            try:
                planillas_asistencia_usadas_ids = Planilla.objects.filter(
                    planilla_asistencia_base__isnull=False
                ).values_list('planilla_asistencia_base_id', flat=True)

                qs = PlanillaAsistencia.objects.filter(
                    estado='validado',
                    tipo=self.tipo_filtro # Filtrar por el tipo proporcionado
                ).exclude(
                    id__in=planillas_asistencia_usadas_ids
                ).order_by('-anio', '-mes') # Ya no es necesario ordenar por 'tipo' aquí

                self.fields['planilla_asistencia_base_selector'].queryset = qs

                if qs.exists():
                    # Si hay opciones, habilitar el selector
                    del self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled']
                    self.fields['planilla_asistencia_base_selector'].required = True # Ahora es obligatorio
                else:
                    # Si no hay opciones para el tipo filtrado, mantener deshabilitado
                    tipo_display = dict(Planilla.TIPO_CHOICES).get(self.tipo_filtro, self.tipo_filtro)
                    self.fields['planilla_asistencia_base_selector'].empty_label = f"No hay asistencias disponibles para el tipo '{tipo_display}'"
            
            except Exception as e:
                # En caso de error al construir el queryset (ej. DB no disponible)
                print(f"ERROR en PlanillaForm __init__ (al poblar selector con tipo_filtro='{self.tipo_filtro}'): {e}") # Usar logging
                # Mantener el selector deshabilitado y con mensaje de error
                self.fields['planilla_asistencia_base_selector'].queryset = PlanillaAsistencia.objects.none()
                self.fields['planilla_asistencia_base_selector'].empty_label = "Error al cargar asistencias"
                self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled'] = True
        # else: Si no hay tipo_filtro, el selector permanece deshabilitado con su mensaje inicial.

        # Configurar el campo 'dias_habiles'
        # Por defecto, está deshabilitado si el selector de asistencia lo está.
        if self.fields['planilla_asistencia_base_selector'].widget.attrs.get('disabled', False):
            self.fields['dias_habiles'].widget.attrs['disabled'] = True
            self.fields['dias_habiles'].required = False
        else:
            # Si el selector de asistencia está habilitado, días hábiles también debería estarlo
            # y ser requerido (ya lo es por su definición si no se pone disabled).
            if 'disabled' in self.fields['dias_habiles'].widget.attrs:
                 del self.fields['dias_habiles'].widget.attrs['disabled']
            self.fields['dias_habiles'].required = True


    def clean(self):
        cleaned_data = super().clean()
        
        # Validaciones condicionales basadas en el estado de los campos
        asistencia_selector_disabled = self.fields['planilla_asistencia_base_selector'].widget.attrs.get('disabled', False)
        pa_base_seleccionada = cleaned_data.get('planilla_asistencia_base_selector')
        dias_habiles_valor = cleaned_data.get('dias_habiles')

        # Si el selector de asistencia NO está deshabilitado (es decir, se esperaba una selección)
        if not asistencia_selector_disabled:
            if not pa_base_seleccionada:
                self.add_error('planilla_asistencia_base_selector', "Debe seleccionar una Planilla de Asistencia base.")
            
            # Si se seleccionó una asistencia, entonces días hábiles es obligatorio y debe ser válido
            if pa_base_seleccionada: # Implica que el selector estaba habilitado y se eligió algo
                if dias_habiles_valor is None: # Si es None (porque el campo es opcional y se dejó vacío)
                    self.add_error('dias_habiles', "Debe ingresar los días hábiles.")
                elif dias_habiles_valor < 0:
                    self.add_error('dias_habiles', "Los días hábiles no pueden ser un número negativo.")
                elif dias_habiles_valor > 31: # O un límite más específico si lo tienes
                    self.add_error('dias_habiles', "Los días hábiles no pueden ser mayores a 31.")
        
        return cleaned_data


class EditarPlanillaForm(forms.ModelForm):
    """
    Formulario para editar campos específicos de una Planilla de Bono TE existente.
    Solo permite modificar 'dias_habiles' y 'estado'.
    """
    class Meta:
        model = Planilla
        fields = ['dias_habiles', 'estado'] # Solo estos campos serán editables
        widgets = {
            # Opcional: puedes definir widgets específicos si lo deseas
            # 'estado': forms.Select(attrs={'class': 'form-control'}),
            # 'dias_habiles': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No hay lógica especial de __init__ necesaria aquí a menos que quieras
        # deshabilitar campos condicionalmente basado en el estado de la instancia,
        # pero para solo dos campos, generalmente no es necesario.
        
        # Aplicar clases de Bootstrap si es tu estilo
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.PasswordInput, forms.URLInput, forms.DateInput, forms.TimeInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-control custom-select'}) # O solo 'form-control'
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, forms.Textarea):
                 field.widget.attrs.update({'class': 'form-control', 'rows': 3})


    # Mantener las validaciones para los campos que son editables
    def clean_dias_habiles(self):
        dias_habiles = self.cleaned_data.get('dias_habiles')
        if dias_habiles is not None:
            if dias_habiles < 0:
                raise forms.ValidationError("Los días hábiles no pueden ser un número negativo.")
            if dias_habiles > 31: # O tu límite más específico
                raise forms.ValidationError("Los días hábiles no pueden ser mayores a 31.")
        # Si el campo es opcional en el modelo y se permite dejarlo vacío en edición:
        # elif dias_habiles is None and self.instance and self.instance.pk:
        #     pass # Permitir borrar el valor si es una edición y el campo es nullable
        # else:
        #     raise forms.ValidationError("Este campo es requerido.") # Si es obligatorio
        return dias_habiles