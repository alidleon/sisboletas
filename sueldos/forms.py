# sueldos/forms.py

from django import forms
from .models import PlanillaSueldo # Importar el modelo de cabecera
from django.core.exceptions import ValidationError
import os
from .models import DetalleSueldo
from decimal import Decimal
from django.db import models

class CrearPlanillaSueldoForm(forms.Form):
    # --- Campos Visibles para el Usuario ---
    # Los hacemos no requeridos a nivel de campo, la lógica central estará en clean()
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
        required=True, # Este sí es requerido siempre
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    observaciones = forms.CharField(
        label="Observaciones Iniciales (Opcional)",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-sm'})
    )

    # Ya no definimos los campos 'mes' y 'anio' aquí.

    def __init__(self, *args, **kwargs):
        # Extraemos las listas dinámicas que pasaremos desde la vista
        meses_sugeridos = kwargs.pop('meses_sugeridos', [])
        anios_sugeridos = kwargs.pop('anios_sugeridos', [])
        super().__init__(*args, **kwargs)

        # Poblamos los choices de los selects dinámicamente
        if meses_sugeridos:
            self.fields['mes_select'].choices = [('', '-- Seleccione Mes --')] + [(m, m) for m in meses_sugeridos]
        if anios_sugeridos:
            self.fields['anio_select'].choices = [('', '-- Seleccione Año --')] + [(a, a) for a in anios_sugeridos]

    def clean(self):
        cleaned_data = super().clean()
        
        # Prioridad al SELECT. Si no, usamos el MANUAL.
        mes_s = cleaned_data.get('mes_select')
        mes_m = cleaned_data.get('mes_manual')
        final_mes = None
        
        if mes_s:
            final_mes = int(mes_s)
        elif mes_m:
            final_mes = mes_m
        else:
            # Añadimos un error general al formulario si no se proporciona mes
            self.add_error(None, "Debe seleccionar un Mes o introducirlo manualmente.")

        anio_s = cleaned_data.get('anio_select')
        anio_m = cleaned_data.get('anio_manual')
        final_anio = None

        if anio_s:
            final_anio = int(anio_s)
        elif anio_m:
            final_anio = anio_m
        else:
            # Añadimos un error general al formulario si no se proporciona año
            self.add_error(None, "Debe seleccionar un Año o introducirlo manualmente.")
        
        # Si no hubo errores hasta ahora, poblamos cleaned_data con los valores finales
        # para que la vista pueda acceder a ellos.
        if not self.errors:
            cleaned_data['mes'] = final_mes
            cleaned_data['anio'] = final_anio
        
        return cleaned_data


# --- Formulario para EDITAR (Similar a reportes.EditarPlanillaAsistenciaForm) ---
# sueldos/forms.py

class EditarPlanillaSueldoForm(forms.ModelForm):
    """
    Formulario para editar una PlanillaSueldo. Los campos clave
    se muestran pero no son editables.
    """
    class Meta:
        model = PlanillaSueldo
        # Incluimos TODOS los campos relevantes en el formulario
        fields = ['mes', 'anio', 'tipo', 'estado', 'observaciones']

        widgets = {
            'estado': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'observaciones': forms.Textarea(attrs={'rows': 4, 'class': 'form-control form-control-sm'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)

        if instance and instance.pk:
            # Hacemos que mes, año y tipo no sean editables
            self.fields['mes'].disabled = True
            self.fields['anio'].disabled = True
            self.fields['tipo'].disabled = True
            
            # Y mantenemos la lógica de seguridad para estados finales
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