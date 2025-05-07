# sueldos/forms.py

from django import forms
from .models import PlanillaSueldo # Importar el modelo de cabecera
from django.core.exceptions import ValidationError
import os
from .models import DetalleSueldo
from decimal import Decimal
from django.db import models

class CrearPlanillaSueldoForm(forms.Form):
    """ Recopila los datos iniciales para crear una PlanillaSueldo. """
    mes = forms.IntegerField(
        label="Mes de la Planilla",
        min_value=1, max_value=12, required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 5', 'min': '1', 'max': '12', 'class': 'form-control form-control-sm'}),
        help_text='Ingrese el número del mes (1-12).'
    )
    anio = forms.IntegerField(
        label="Año de la Planilla",
        min_value=2000, max_value=2100, required=True, # Rango ajustado
        widget=forms.NumberInput(attrs={'placeholder': 'Ej: 2024', 'min': '2000', 'max': '2100', 'class': 'form-control form-control-sm'}),
        help_text='Ingrese el año (4 dígitos).'
    )
    tipo = forms.ChoiceField(
        label="Tipo de Personal",
        choices=PlanillaSueldo.TIPO_CHOICES, # Obtener choices del modelo
        required=True,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}), # Clase Bootstrap
        help_text='Seleccione el tipo de personal para esta planilla.'
    )
    observaciones = forms.CharField(
        label="Observaciones Iniciales (Opcional)",
        required=False, # Hacerlo opcional
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-sm'})
    )

    # Puedes mantener las validaciones clean aquí si prefieres
    def clean_mes(self):
        mes = self.cleaned_data.get('mes')
        if mes and not 1 <= mes <= 12: raise ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean_anio(self):
        anio = self.cleaned_data.get('anio')
        if anio and not 2000 <= anio <= 2100: raise ValidationError("Ingrese un año válido (4 dígitos).")
        return anio


# --- Formulario para EDITAR (Similar a reportes.EditarPlanillaAsistenciaForm) ---
class EditarPlanillaSueldoForm(forms.ModelForm):
    """ Edita los campos permitidos de una PlanillaSueldo existente. """
    class Meta:
        model = PlanillaSueldo
        # Campos EDITABLES: mes, año, estado, observaciones. TIPO se omite.
        fields = ['mes', 'anio', 'estado', 'observaciones']
        widgets = {
            'mes': forms.NumberInput(attrs={'placeholder': 'Ej: 5', 'min': '1', 'max': '12', 'class': 'form-control form-control-sm'}),
            'anio': forms.NumberInput(attrs={'placeholder': 'Ej: 2024', 'min': '2000', 'max': '2100', 'class': 'form-control form-control-sm'}),
            'estado': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-sm'}),
        }
        labels = { # Ajustar etiquetas si es necesario
            'mes': 'Mes',
            'anio': 'Año',
            'estado': 'Estado',
            'observaciones': 'Observaciones',
        }
        help_texts = { # Ajustar ayuda si es necesario
            'mes': 'Mes de la planilla (1-12).',
            'anio': 'Año de la planilla (4 dígitos).',
            'estado': 'Estado actual de la planilla.',
        }

    # Ya NO necesitamos el __init__ complejo para manejar 'tipo_display'

    # Validaciones clean (puedes mantenerlas)
    def clean_mes(self):
        mes = self.cleaned_data.get('mes')
        # ... (validación igual) ...
        if mes is not None:
            if not 1 <= mes <= 12: raise ValidationError("El mes debe estar entre 1 y 12.")
        return mes

    def clean_anio(self):
        anio = self.cleaned_data.get('anio')
        # ... (validación igual) ...
        if anio is not None:
             if not 2000 <= anio <= 2100: raise ValidationError("Ingrese un año válido (4 dígitos).")
        return anio


class SubirExcelSueldosForm(forms.Form):
    """
    Formulario simple para el campo de subida de archivo Excel.
    Se usa en la vista 'subir_excel_sueldos'.
    """
    archivo_excel = forms.FileField(
        label="Seleccionar archivo Excel (.xlsx)",
        required=True,
        # Usar ClearableFileInput para que muestre el nombre y permita limpiar
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx', # Restringir tipos de archivo en el navegador
            'class': 'form-control form-control-sm' # Clase Bootstrap
            }),
        help_text="Solo se permiten archivos con formato .xlsx"
    )

    def clean_archivo_excel(self):
        """ Validación específica para el archivo subido. """
        archivo = self.cleaned_data.get('archivo_excel')
        if archivo:
            # Validar extensión del archivo
            ext = os.path.splitext(archivo.name)[1] # Obtiene la extensión (ej: '.xlsx')
            if not ext.lower() == '.xlsx':
                raise ValidationError("Formato de archivo no válido. Solo se permiten archivos .xlsx")

            # Opcional: Validar tamaño máximo del archivo (ej: 5MB)
            # max_size = 5 * 1024 * 1024 # 5 MB
            # if archivo.size > max_size:
            #     raise ValidationError(f"El archivo es demasiado grande (Máximo permitido: {max_size // 1024 // 1024} MB).")
        # Si no hay archivo (porque no es requerido o falló antes), simplemente retornamos None
        # Pero como es 'required=True', Django ya debería haber fallado si no se subió nada.
        return archivo
    
class EditarDetalleSueldoForm(forms.ModelForm):
    """ Permite editar los campos de un DetalleSueldo existente. """
    class Meta:
        model = DetalleSueldo
        # Incluir TODOS los campos que se cargaron del Excel y que podrían editarse manualmente
        # Excluir: id, planilla_sueldo, personal_externo (se manejan por separado)
        # Excluir: campos de referencia (_referencia, fila_excel)
        fields = [
            'dias_trab',
            'haber_basico',
            'categoria',
            'total_ganado', # Podría ser readonly si se calcula
            'rc_iva_retenido',
            'gestora_publica',
            'aporte_nac_solidario',
            'cooperativa',
            'faltas',
            'memorandums',
            'otros_descuentos',
            'total_descuentos', # Podría ser readonly si se calcula
            'liquido_pagable',  # Podría ser readonly si se calcula
        ]
        widgets = {
            # Aplicar clases y step para mejor UI (similar a reportes)
            'dias_trab': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'haber_basico': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
            'categoria': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control form-control-sm'}),
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
        labels = {
            # Puedes personalizar etiquetas si quieres que sean diferentes al verbose_name del modelo
            'dias_trab': 'Días Trabajados',
            'rc_iva_retenido': 'RC-IVA',
            'gestora_publica': 'AFP/Gestora',
            'aporte_nac_solidario': 'Ap. Solidario',
            # ... otras etiquetas personalizadas ...
        }

    # Opcional: Método clean para convertir vacíos a 0 (similar a DetalleAsistenciaForm)
    def clean(self):
        cleaned_data = super().clean()
        campos_numericos = self.Meta.fields # Tomar todos los campos definidos
        for field_name in campos_numericos:
            valor = cleaned_data.get(field_name)
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                 # Asignar Decimal(0) si el campo es DecimalField en el modelo
                 try:
                     model_field = self.instance._meta.get_field(field_name)
                     if isinstance(model_field, models.DecimalField):
                         cleaned_data[field_name] = Decimal('0.00')
                     elif isinstance(model_field, models.IntegerField): # Por si añades IntegerFields editables
                         cleaned_data[field_name] = 0
                 except Exception: # Si el campo no existe o hay error
                     pass # Ignorar si no se puede determinar el tipo
        return cleaned_data

    # Podrías añadir validaciones clean_<campo> si necesitas lógica específica

class GenerarEstadoMensualForm(forms.Form):
    mes = forms.IntegerField(label="Mes a Procesar", min_value=1, max_value=12, required=True, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    anio = forms.IntegerField(label="Año a Procesar", min_value=2000, max_value=2100, required=True, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'}))
    tipo_planilla = forms.ChoiceField(label="Tipo de Planilla", choices=PlanillaSueldo.TIPO_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    # Podríamos añadir un checkbox tipo "Sobreescribir si ya existe?"