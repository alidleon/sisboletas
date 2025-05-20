# boletas/forms.py
from django import forms
from .models import PlantillaBoleta

class PlantillaBoletaForm(forms.ModelForm):
    class Meta:
        model = PlantillaBoleta
        fields = ['nombre', 'descripcion', 'es_predeterminada'] # Añade otros campos si los tienes
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3}),
            'es_predeterminada': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'es_predeterminada': 'Usar como plantilla predeterminada al generar boletas'
        }