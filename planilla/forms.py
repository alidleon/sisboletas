from django import forms
from .models import DetalleBonoTe, Planilla 
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
            self.fields['mes'].widget.attrs['class'] = 'form-control form-control-sm' 
        
        for field_name, field in self.fields.items():
            if field_name != 'dias_habiles' and field_name != 'mes': 
                if isinstance(field.widget, forms.NumberInput):
                    field.widget.attrs.update({'class': 'form-control form-control-sm', 'step': '1.00'})
                elif isinstance(field.widget, forms.Textarea):
                    field.widget.attrs.update({'class': 'form-control form-control-sm', 'rows': 2})
                elif not field.widget.attrs.get('class'): 
                    field.widget.attrs.update({'class': 'form-control form-control-sm'})


class PlanillaForm(forms.ModelForm):
    """
    Formulario para crear una Planilla de Bono TE.
    El usuario primero filtra por tipo (en el template, con recarga GET),
    luego selecciona una PlanillaAsistencia base de las opciones filtradas,
    e ingresa los días hábiles.
    """
    planilla_asistencia_base_selector = forms.ModelChoiceField(
        queryset=PlanillaAsistencia.objects.none(), 
        label="Planilla de Asistencia Validada Base",
        required=False, 
        empty_label="Seleccione un tipo de planilla arriba para ver opciones",
        help_text="Solo se muestran planillas de asistencia validadas y no usadas para el tipo seleccionado."
    )

    dias_habiles = forms.DecimalField(
        label='Días Hábiles del Mes para Bono TE',
        required=False, 
        max_digits=5,
        decimal_places=2,
        min_value=0, 
    )

    class Meta:
        model = Planilla
        fields = ['dias_habiles']

    def __init__(self, *args, **kwargs):
        self.tipo_filtro = kwargs.pop('tipo_filtro', None)
        super().__init__(*args, **kwargs)

        self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled'] = True

        if self.tipo_filtro:
            self.fields['planilla_asistencia_base_selector'].empty_label = "--- Elija una Planilla de Asistencia ---"
            try:
                planillas_asistencia_usadas_ids = Planilla.objects.filter(
                    planilla_asistencia_base__isnull=False
                ).values_list('planilla_asistencia_base_id', flat=True)

                qs = PlanillaAsistencia.objects.filter(
                    estado='validado',
                    tipo=self.tipo_filtro
                ).exclude(
                    id__in=planillas_asistencia_usadas_ids
                ).order_by('-anio', '-mes')

                self.fields['planilla_asistencia_base_selector'].queryset = qs

                if qs.exists():
                    del self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled']
                    self.fields['planilla_asistencia_base_selector'].required = True
                else:
                    tipo_display = dict(Planilla.TIPO_CHOICES).get(self.tipo_filtro, self.tipo_filtro)
                    self.fields['planilla_asistencia_base_selector'].empty_label = f"No hay asistencias disponibles para el tipo '{tipo_display}'"
            
            except Exception as e:
                print(f"ERROR en PlanillaForm __init__: {e}")
                self.fields['planilla_asistencia_base_selector'].queryset = PlanillaAsistencia.objects.none()
                self.fields['planilla_asistencia_base_selector'].empty_label = "Error al cargar asistencias"
                self.fields['planilla_asistencia_base_selector'].widget.attrs['disabled'] = True

        if self.fields['planilla_asistencia_base_selector'].widget.attrs.get('disabled', False):
            self.fields['dias_habiles'].widget.attrs['disabled'] = True
            self.fields['dias_habiles'].required = False
        else:
            if 'disabled' in self.fields['dias_habiles'].widget.attrs:
                 del self.fields['dias_habiles'].widget.attrs['disabled']
            self.fields['dias_habiles'].required = True

        self.fields['planilla_asistencia_base_selector'].widget.attrs.update(
            {'class': 'form-control'}
        )
        self.fields['dias_habiles'].widget.attrs.update(
            {'class': 'form-control'}
        )

    def clean(self):
        cleaned_data = super().clean()
        
        asistencia_selector_disabled = self.fields['planilla_asistencia_base_selector'].widget.attrs.get('disabled', False)
        pa_base_seleccionada = cleaned_data.get('planilla_asistencia_base_selector')
        dias_habiles_valor = cleaned_data.get('dias_habiles')

        if not asistencia_selector_disabled:
            if not pa_base_seleccionada:
                self.add_error('planilla_asistencia_base_selector', "Debe seleccionar una Planilla de Asistencia base.")
            
            if pa_base_seleccionada:
                if dias_habiles_valor is None:
                    self.add_error('dias_habiles', "Debe ingresar los días hábiles.")
                elif dias_habiles_valor < 0:
                    self.add_error('dias_habiles', "Los días hábiles no pueden ser un número negativo.")
                elif dias_habiles_valor > 31:
                    self.add_error('dias_habiles', "Los días hábiles no pueden ser mayores a 31.")
        
        return cleaned_data


class EditarPlanillaForm(forms.ModelForm):
    """
    Formulario para editar campos específicos de una Planilla de Bono TE existente.
    Solo permite modificar 'dias_habiles' y 'estado'.
    """
    class Meta:
        model = Planilla
        fields = ['dias_habiles', 'estado']
        widgets = {
         }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)       
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.PasswordInput, forms.URLInput, forms.DateInput, forms.TimeInput, forms.DateTimeInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-control custom-select'}) 
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, forms.Textarea):
                 field.widget.attrs.update({'class': 'form-control', 'rows': 3})
    def clean_dias_habiles(self):
        dias_habiles = self.cleaned_data.get('dias_habiles')
        if dias_habiles is not None:
            if dias_habiles < 0:
                raise forms.ValidationError("Los días hábiles no pueden ser un número negativo.")
            if dias_habiles > 31: 
                raise forms.ValidationError("Los días hábiles no pueden ser mayores a 31.")
        return dias_habiles