# planilla/forms.py (Versión Original)

from django import forms
from .models import DetalleBonoTe, Planilla # Solo modelos internos
from django.core.exceptions import ValidationError

class DetalleBonoTeForm(forms.ModelForm):
    # Campo informativo dias_habiles (igual que antes)
    dias_habiles = forms.DecimalField(
        label='Días Hábiles (Planilla)',
        required=False,
        widget=forms.NumberInput(attrs={'readonly': 'readonly'}) # O disabled=True
    )

    class Meta:
        model = DetalleBonoTe
        # Campos editables originales (verifica si eran estos)
        fields = ['mes', 'abandono_dias', 'faltas', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'psgh', 'perm_excep', 'asuetos',
                  'pcgh_embar_enf_base', 'descuentos', 'observaciones_bono'] # Excluye personal_externo, id_planilla, calculados

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer 'mes' readonly si no debe editarse
        if 'mes' in self.fields:
            self.fields['mes'].widget.attrs['readonly'] = True
            # O self.fields['mes'].disabled = True


class PlanillaForm(forms.ModelForm):
    class Meta:
        model = Planilla
        # Campos originales (verifica si incluía tipo, dias_habiles, etc.)
        fields = ['mes', 'anio', 'tipo', 'dias_habiles'] # ¿Eran estos?
        # Revertir widgets si eran diferentes

    # Validaciones originales (sin cambios si solo validan mes, anio, dias_habiles)
    def clean_mes(self):
        mes = self.cleaned_data['mes']
        if not 1 <= mes <= 12:
            raise ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean_anio(self):
        anio = self.cleaned_data['anio']
        if not 2000 <= anio <= 2100: # Ajusta rango original
            raise ValidationError("El año debe estar entre 2000 y 2100.")
        return anio

    def clean_dias_habiles(self):
        dias_habiles = self.cleaned_data.get('dias_habiles')
        if dias_habiles is not None:
            if dias_habiles < 0: raise ValidationError("Los días hábiles no pueden ser negativos.")
            if dias_habiles > 31: raise ValidationError("Los días hábiles no pueden ser mayores a 31.")
        return dias_habiles