import logging
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone 
from django.apps import apps

try:
    from planilla.models import PrincipalPersonalExterno, Planilla as PlanillaBonoTE
except ImportError:
    PrincipalPersonalExterno = None
    PlanillaBonoTE = None
    print("ADVERTENCIA: No se pudieron importar modelos de la app 'planilla'. "
          "Esto puede ser normal durante las migraciones iniciales.")

logger_model = logging.getLogger(__name__)

class PlanillaAsistencia(models.Model):
    TIPO_CHOICES = [
        ('planta', 'Asegurado'),
        ('contrato', 'Contrato'),
        ('consultor', 'Consultor en Linea'),
    ]
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        
        ('validado', 'Validado'),
        
        ('archivado', 'Archivado'),
    ]

    mes = models.IntegerField(verbose_name="Mes", help_text="Mes al que corresponde la asistencia (1-12).")
    anio = models.IntegerField(verbose_name="Año", help_text="Año al que corresponde la asistencia.")
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, verbose_name="Tipo de Planilla", help_text="Tipo de personal al que aplica esta asistencia.")
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='borrador', verbose_name="Estado del Reporte", help_text="Estado actual del proceso de recopilación de asistencia.")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    usuario_creacion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_asistencia_creadas', verbose_name="Usuario Creación")
    fecha_validacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Validación")
    usuario_validacion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_asistencia_validadas', verbose_name="Usuario Validación")
    observaciones_generales = models.TextField(blank=True, null=True, verbose_name="Observaciones Generales", help_text="Notas adicionales sobre esta planilla de asistencia.")

    class Meta:
        db_table = 'reporte_planilla_asistencia'
        verbose_name = "Planilla de Asistencia"
        verbose_name_plural = "Planillas de Asistencia"
        unique_together = ('mes', 'anio', 'tipo')
        ordering = ['-anio', '-mes', 'tipo']

    def __str__(self):
        return f"Asistencia {self.get_tipo_display()} - {self.mes}/{self.anio} ({self.get_estado_display()})"

    def clean(self):
        super().clean()
        if self.mes and not 1 <= self.mes <= 12:
            raise ValidationError({'mes': "El mes debe estar entre 1 y 12."})
        if self.anio and not 2000 <= self.anio <= 2100:
            raise ValidationError({'anio': "El año parece inválido."})
        if PlanillaBonoTE and not self.tipo:
             raise ValidationError({'tipo': "Debe seleccionar un tipo de planilla."})
        elif PlanillaBonoTE and self.tipo not in dict(self.TIPO_CHOICES):
             raise ValidationError({'tipo': "Tipo de planilla no válido."})

    def marcar_como_validado(self, usuario):
        logger_model.info(f"MODELO Planilla ID {self.id}: Intentando marcar como validado. Estado actual ANTES de cambio: '{self.estado}'")
        if self.estado in ['borrador', 'completo']:
            self.estado = 'validado'
            self.usuario_validacion = usuario
            self.fecha_validacion = timezone.now() 
            self.save(update_fields=['estado', 'usuario_validacion', 'fecha_validacion']) 
            return True
        logger_model.warning(f"MODELO Planilla ID {self.id}: NO SE PUDO marcar como validado. Condición de estado no cumplida (estado actual: '{self.estado}')")
        return False


class DetalleAsistencia(models.Model):
    """
    Representa el registro detallado de asistencia, incidencias y permisos
    para una persona específica dentro de una PlanillaAsistencia.
    """
    planilla_asistencia = models.ForeignKey(
        PlanillaAsistencia,
        on_delete=models.CASCADE,
        related_name='detalles_asistencia',
        verbose_name="Planilla de Asistencia"
    )
    personal_externo = models.ForeignKey(
        'planilla.PrincipalPersonalExterno',
        on_delete=models.SET_NULL, 
        null=True,
        blank=False,
        related_name='registros_asistencia',
        verbose_name='Personal Externo',
        db_constraint=False 
    )
    omision_cant = models.IntegerField(default=0, verbose_name='Nro. Omisiones Marcado', help_text="Cantidad de veces que omitió marcar entrada/salida.")
    omision_sancion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Sanción Omisión', help_text="Valor de la sanción por omisión (monetario o factor).")
    abandono_dias = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Abandono (días)', help_text="Días registrados como abandono de trabajo.")
    abandono_sancion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Sanción Abandono', help_text="Valor de la sanción por abandono (monetario o factor)." )
    faltas_dias = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Faltas (días)',help_text="Días de falta injustificada.")
    faltas_sancion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Sanción Faltas', help_text="Valor de la sanción por faltas (monetario o factor).")
    atrasos_minutos = models.IntegerField(default=0, verbose_name='Atrasos (minutos)',help_text="Total de minutos de atraso acumulados en el periodo.")
    atrasos_sancion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Sanción Atrasos', help_text="Valor de la sanción por atrasos (monetario o factor).")
    vacacion = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Vacación (días)')
    viajes = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Viajes (días)', help_text="Días en viaje oficial o comisión.")
    bajas_medicas = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Bajas Médicas (días)')
    pcgh = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='PCGH (días)', help_text="Permiso Con Goce de Haber.")
    perm_excep = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Perm. Excep. (días)', help_text="Permiso Excepcional (con o sin goce, según normativa).")
    asuetos = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Asuetos (días)', help_text="Días de asueto oficial reconocidos.")
    psgh = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='PSGH (días)', help_text="Permiso Sin Goce de Haber.")
    pcgh_embar_enf_base = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='PCGH Emb/Enf Base (días)')
    actividad_navidad = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Act. Navidad (días)', help_text="Días relacionados con actividad navideña (permiso, asistencia, etc.).")
    iza_bandera = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Iza Bandera (días)', help_text="Días relacionados con la iza de bandera (permiso, asistencia, etc.)." )
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones Específicas", help_text="Notas sobre este registro de asistencia en particular.")

    class Meta:
        db_table = 'reporte_detalle_asistencia'
        verbose_name = "Detalle de Asistencia"
        verbose_name_plural = "Detalles de Asistencia"
        unique_together = ('planilla_asistencia', 'personal_externo')

    def __str__(self):     
        planilla_id_display = self.planilla_asistencia_id if self.planilla_asistencia_id is not None else "N/A"
        
        if self.personal_externo_id is not None:
            personal_display = f"Personal ID Externo: {self.personal_externo_id}"
        else:
            personal_display = "Personal No Asignado"
        
        return f"Asistencia para {personal_display} en Planilla ID {planilla_id_display}"

    def clean(self):
        super().clean()
        campos_numericos = [
            'omision_cant', 'omision_sancion', 'abandono_dias', 'abandono_sancion',
            'faltas_dias', 'faltas_sancion', 'atrasos_minutos', 'atrasos_sancion',
            'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep',
            'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad', 'iza_bandera'
        ]
        for campo in campos_numericos:
            valor = getattr(self, campo)
            if valor is not None and valor < 0:
                raise ValidationError({campo: f"El valor de '{self._meta.get_field(campo).verbose_name}' no puede ser negativo."})

        if not PrincipalPersonalExterno:
             print(f"ADVERTENCIA (clean DetalleAsistencia): PrincipalPersonalExterno no está cargado.")