
from django import forms
from .models import PlanillaSueldo 
from django.core.exceptions import ValidationError
import os
from .models import DetalleSueldo, CierreMensual
from decimal import Decimal
from django.db import models
from django.urls import reverse
from django.db.models import Q

class CrearPlanillaSueldoForm(forms.Form):

    mes_select = forms.ChoiceField(
        label="Mes (Sugerido)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    mes_manual = forms.IntegerField(
        label="o Mes (Manual)",
        required=False,
        min_value=1, max_value=12,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ej: 7'})
    )

    anio_select = forms.ChoiceField(
        label="Año (Sugerido)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    anio_manual = forms.IntegerField(
        label="o Año (Manual)",
        required=False,
        min_value=2000, max_value=2100,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ej: 2024'})
    )

    # --- Campo Tipo ---
    TIPO_CHOICES_CON_PLACEHOLDER = [('', '-- Seleccione Tipo --')] + PlanillaSueldo.TIPO_CHOICES
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=TIPO_CHOICES_CON_PLACEHOLDER,
        required=True, 
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    observaciones = forms.CharField(
        label="Observaciones Iniciales (Opcional)",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-sm'})
    )

    

    def __init__(self, *args, **kwargs):
        meses_sugeridos = kwargs.pop('meses_sugeridos', [])
        anios_sugeridos = kwargs.pop('anios_sugeridos', [])
        super().__init__(*args, **kwargs)

        if meses_sugeridos:
            self.fields['mes_select'].choices = [('', '-- Seleccione Mes --')] + [(m, m) for m in meses_sugeridos]
        if anios_sugeridos:
            self.fields['anio_select'].choices = [('', '-- Seleccione Año --')] + [(a, a) for a in anios_sugeridos]

    def clean(self):
        cleaned_data = super().clean()
        
        mes_s = cleaned_data.get('mes_select')
        mes_m = cleaned_data.get('mes_manual')
        final_mes = None
        
        if mes_s:
            final_mes = int(mes_s)
        elif mes_m:
            final_mes = mes_m
        else:
            self.add_error(None, "Debe seleccionar un Mes o introducirlo manualmente.")

        anio_s = cleaned_data.get('anio_select')
        anio_m = cleaned_data.get('anio_manual')
        final_anio = None

        if anio_s:
            final_anio = int(anio_s)
        elif anio_m:
            final_anio = anio_m
        else:
            self.add_error(None, "Debe seleccionar un Año o introducirlo manualmente.")
        
        if not self.errors:
            cleaned_data['mes'] = final_mes
            cleaned_data['anio'] = final_anio
        
        return cleaned_data

class EditarPlanillaSueldoForm(forms.ModelForm):
    """
    Formulario para editar una PlanillaSueldo. Los campos clave
    se muestran pero no son editables.
    """
    class Meta:
        model = PlanillaSueldo
        fields = ['mes', 'anio', 'tipo', 'estado', 'observaciones']

        widgets = {
            'estado': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'observaciones': forms.Textarea(attrs={'rows': 4, 'class': 'form-control form-control-sm'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)

        if instance and instance.pk:
            self.fields['mes'].disabled = True
            self.fields['anio'].disabled = True
            self.fields['tipo'].disabled = True
            
            if instance.estado in ['pagado', 'archivado']:
                self.fields['estado'].disabled = True
                self.fields['observaciones'].disabled = True


class SubirExcelSueldosForm(forms.Form):
    """
    Formulario simple para el campo de subida de archivo Excel.
    Se usa en la vista 'subir_excel_sueldos'.
    """
    archivo_excel = forms.FileField(
        label="Seleccionar archivo Excel (.xlsx)",
        required=True,
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx', 
            'class': 'form-control form-control-sm' 
            }),
        help_text="Solo se permiten archivos con formato .xlsx"
    )

    def clean_archivo_excel(self):
        """ Validación específica para el archivo subido. """
        archivo = self.cleaned_data.get('archivo_excel')
        if archivo:
            ext = os.path.splitext(archivo.name)[1] 
            if not ext.lower() == '.xlsx':
                raise ValidationError("Formato de archivo no válido. Solo se permiten archivos .xlsx")
        return archivo
    
class EditarDetalleSueldoForm(forms.ModelForm):
    """ Permite editar los campos de un DetalleSueldo existente. """
    class Meta:
        model = DetalleSueldo
        fields = [
            'dias_trab',
            'haber_basico',
            'categoria',
            'lactancia_prenatal', 
            'otros_ingresos',
            'total_ganado', 
            'rc_iva_retenido',
            'gestora_publica',
            'aporte_nac_solidario',
            'cooperativa',
            'faltas',
            'memorandums',
            'otros_descuentos',
            'total_descuentos', 
            'liquido_pagable',  
            'saldo_credito_fiscal',
        ]
        widgets = {
            'dias_trab': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'haber_basico': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'categoria': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'lactancia_prenatal': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'placeholder': '0.00'}),
            'otros_ingresos': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'placeholder': '0.00'}),
            'saldo_credito_fiscal': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'placeholder': '0.00'}),
            'total_ganado': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'readonly':'readonly'}), # Ejemplo readonly
            'rc_iva_retenido': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'gestora_publica': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'aporte_nac_solidario': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'cooperativa': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'faltas': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'memorandums': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'otros_descuentos': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'total_descuentos': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'readonly':'readonly'}), # Ejemplo readonly
            'liquido_pagable': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm', 'readonly':'readonly'}), # Ejemplo readonly
        }
        

    def clean(self):
        """
        Asegura que los campos numéricos vacíos se guarden como 0 en lugar de NULL
        para mantener la integridad de la base de datos.
        """
        cleaned_data = super().clean()
        for field_name in self.Meta.fields:
            valor = cleaned_data.get(field_name)
            if valor is None:
                try:
                    model_field = self.instance._meta.get_field(field_name)
                    if isinstance(model_field, models.DecimalField):
                        cleaned_data[field_name] = Decimal('0.00')
                    elif isinstance(model_field, (models.IntegerField, models.FloatField)):
                        cleaned_data[field_name] = 0
                except (AttributeError, KeyError):
                    pass
        return cleaned_data


class SeleccionarPlanillaSueldoParaCierreForm(forms.Form):
    """
    Formulario para seleccionar una Planilla de Sueldos existente como base
    para generar el estado mensual.
    """
    planilla_sueldo = forms.ModelChoiceField(
        queryset=PlanillaSueldo.objects.none(), 
        
        label="Seleccionar Planilla de Sueldos Base",
        empty_label="-- Elija una planilla de sueldos --",
        help_text="Solo se muestran planillas cuyo Excel ha sido cargado o validado y que aún no tienen un cierre mensual generado.",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        
        periodos_con_cierre = CierreMensual.objects.values_list('anio', 'mes', 'tipo_planilla')
        condiciones_exclusion = [
            Q(anio=anio, mes=mes, tipo=tipo) for anio, mes, tipo in periodos_con_cierre
        ]

        
        queryset_base = PlanillaSueldo.objects.filter(
            estado__in=['cargado', 'validado']
        )

        if condiciones_exclusion:
            query_exclusion_total = condiciones_exclusion[0]
            for condicion in condiciones_exclusion[1:]:
                query_exclusion_total |= condicion
            
            queryset_filtrado = queryset_base.exclude(query_exclusion_total)
        else:
            queryset_filtrado = queryset_base

        self.fields['planilla_sueldo'].queryset = queryset_filtrado.order_by('-anio', '-mes', 'tipo')

        self.fields['planilla_sueldo'].label_from_instance = lambda obj: (
            f"{obj.mes}/{obj.anio} - {obj.get_tipo_display()} "
            f"(Estado: {obj.get_estado_display()})"
        )
        
    def clean_planilla_sueldo(self):
        planilla_seleccionada = self.cleaned_data.get('planilla_sueldo')
        if planilla_seleccionada:
            if CierreMensual.objects.filter(mes=planilla_seleccionada.mes, anio=planilla_seleccionada.anio, tipo_planilla=planilla_seleccionada.tipo).exists():
                raise forms.ValidationError("Este periodo ya ha sido procesado. Por favor, recargue la página y seleccione otra planilla.")
        return planilla_seleccionada