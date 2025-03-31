from django import forms
from .models import DetalleBonoTe, Planilla
from django.core.exceptions import ValidationError

class DetalleBonoTeForm(forms.ModelForm):
    dias_habiles = forms.DecimalField(label='Días Hábiles')
    dias_no_pagados = forms.DecimalField(label='Días No Pagados', initial=0)

    class Meta:
        model = DetalleBonoTe
        fields = ['mes', 'dias_habiles', 'dias_no_pagados', 'faltas', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'psgh', 'perm_excep', 'asuetos',
                  'pcgh_embar_enf_base', 'descuentos']  # Campos omitidos: id_sueldo, id_unidad, fecha_inicio, fecha_fin, rc_iva
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mes'].widget.attrs['readonly'] = True
        self.fields['dias_habiles'].widget.attrs['readonly'] = True


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