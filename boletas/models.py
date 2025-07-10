
from django.db import models
from django.conf import settings
from reportlab.lib import pagesizes

class PlantillaBoleta(models.Model):
    nombre = models.CharField(max_length=255, unique=True, verbose_name="Nombre de la Plantilla")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")
    # Usar JSONField si tu BD lo soporta (PostgreSQL, MySQL 5.7.8+), sino TextField
    datos_diseno_json = models.JSONField(default=dict, verbose_name="Datos del Diseño (JSON)")
    TAMANO_PAGINA_CHOICES = [
        ('LETTER', 'Carta (8.5 x 11 pulgadas)'),
        ('LEGAL', 'Oficio / Legal (8.5 x 14 pulgadas)'),
        ('A4', 'A4 (210 x 297 mm)'),
    ]
    tamano_pagina = models.CharField(
        max_length=20,
        choices=TAMANO_PAGINA_CHOICES,
        default='LETTER',  # Default a Carta
        verbose_name="Tamaño de Página"
    )

    usuario_creador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plantillas_boleta_creadas',
        verbose_name="Usuario Creador"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_modificacion = models.DateTimeField(auto_now=True, verbose_name="Última Modificación")
    es_predeterminada = models.BooleanField(default=False, verbose_name="Usar como predeterminada")


    class Meta:
        verbose_name = "Plantilla de Boleta"
        verbose_name_plural = "Plantillas de Boletas"
        ordering = ['nombre']
    
    

    def __str__(self):
        return self.nombre
