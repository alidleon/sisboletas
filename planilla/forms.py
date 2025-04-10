from django import forms
from .models import DetalleBonoTe, Planilla
from django.core.exceptions import ValidationError

class DetalleBonoTeForm(forms.ModelForm):
    # El campo sigue declarado aquí para que aparezca en el form
    dias_habiles = forms.DecimalField(
        label='Días Hábiles (Planilla)',
        required=False, # Es informativo, no requerido por el usuario
        widget=forms.NumberInput(attrs={'readonly': 'readonly'}) # Hacemos explícito que es readonly
    )
    # ... otros campos explícitos si los hay ...

    class Meta:
        model = DetalleBonoTe
        # Asegúrate de que 'dias_habiles' NO esté en esta lista
        fields = ['mes', 'faltas', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'psgh', 'perm_excep', 'asuetos',
                  'pcgh_embar_enf_base', 'descuentos'] # Añade aquí los campos del *modelo* que SÍ deben editarse

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'mes' in self.fields:
            self.fields['mes'].widget.attrs['readonly'] = True
        # La configuración de readonly para dias_habiles ya está en la declaración del campo.


class PlanillaForm(forms.ModelForm):
    class Meta:
        model = Planilla
        fields = ['mes', 'anio', 'tipo', 'dias_habiles'] # Agregamos 'dias_habiles'

    def clean_mes(self):
        mes = self.cleaned_data['mes']
        if mes < 1 or mes > 12:
            raise ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean_anio(self):
        anio = self.cleaned_data['anio']
        if anio < 2000 or anio > 2100:
            raise ValidationError("El año debe estar entre 2000 y 2100.")
        return anio

    def clean_dias_habiles(self):
        dias_habiles = self.cleaned_data['dias_habiles']
        if dias_habiles is not None:
            if dias_habiles < 0:
                raise ValidationError("Los días hábiles no pueden ser negativos.")
            if dias_habiles > 31:
                raise ValidationError("Los días hábiles no pueden ser mayores a 31.")
        return dias_habiles