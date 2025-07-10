
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
import os
from decimal import Decimal

# --- Dependencias Externas (igual que antes) ---
try:
    from planilla.models import PrincipalPersonalExterno
    PLANILLA_APP_AVAILABLE = True
except ImportError:
    class PrincipalPersonalExterno:
        pass
    PLANILLA_APP_AVAILABLE = False
    import logging
    logging.warning("ADVERTENCIA (sueldos.models): No se pudo importar 'planilla.models.PrincipalPersonalExterno'.")

# --- Modelo Cabecera: PlanillaSueldo (sin cambios) ---
class PlanillaSueldo(models.Model):
    TIPO_CHOICES = [
        ('planta', 'Personal Permanente'), 
        ('contrato', 'Contrato'),
        #('consultor en linea', 'Consultor en Linea'),
    ]
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('cargado', 'Excel Cargado'),
        ('validado', 'Validado'),
        ('pagado', 'Pagado'),
        ('archivado', 'Archivado'),
        ('error_carga', 'Error en Carga'),
    ]

    mes = models.IntegerField(verbose_name="Mes", help_text="Mes numérico (1-12)")
    anio = models.IntegerField(verbose_name="Año", help_text="Año (ej: 2024)")
    tipo = models.CharField(
        max_length=40, choices=TIPO_CHOICES, verbose_name="Tipo Planilla",
        help_text="Tipo de personal al que corresponde"
    )
    estado = models.CharField(
        max_length=15, choices=ESTADO_CHOICES, default='borrador', verbose_name="Estado",
        help_text="Estado actual de la planilla de sueldos"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha Creación")
    usuario_creacion = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='planillas_sueldo_creadas', verbose_name="Usuario Creación"
    )
    archivo_excel_cargado = models.FileField(
        upload_to='sueldos_excel/%Y/%m/',
        null=True, blank=True,
        verbose_name="Archivo Excel Cargado",
        help_text="Archivo .xlsx original que se procesó"
    )
    fecha_carga_excel = models.DateTimeField(null=True, blank=True, verbose_name="Fecha Carga Excel")
    observaciones = models.TextField(
        blank=True, null=True, verbose_name="Observaciones / Resumen Carga",
        help_text="Notas adicionales o resumen/errores del proceso de carga del Excel"
    )

    class Meta:
        db_table = 'sueldo_planilla'
        verbose_name = "Planilla de Sueldos"
        verbose_name_plural = "Planillas de Sueldos"
        unique_together = ('mes', 'anio', 'tipo')
        ordering = ['-anio', '-mes', 'tipo']

    def __str__(self):
        return f"Sueldos {self.get_tipo_display()} - {self.mes}/{self.anio} ({self.get_estado_display()})"

    def clean(self):
        super().clean()
        if self.mes and not 1 <= self.mes <= 12:
            raise ValidationError({'mes': "El mes debe estar entre 1 y 12."})
        if self.anio and not 2000 <= self.anio <= 2100:
            raise ValidationError({'anio': "El año parece inválido."})
        if not self.tipo:
             raise ValidationError({'tipo': "Debe seleccionar un tipo de planilla."})
        elif self.tipo not in dict(self.TIPO_CHOICES):
             raise ValidationError({'tipo': "Tipo de planilla no válido."})

    def filename(self):
        if self.archivo_excel_cargado:
            return os.path.basename(self.archivo_excel_cargado.name)
        return ""

# --- Modelo Detalle: Datos de sueldo por persona (Nombres de campo ajustados al Excel) ---
class DetalleSueldo(models.Model):
    """ Almacena los detalles de sueldo, usando nombres de campo similares a las
        columnas del Excel y manteniendo el vínculo con personal externo.
    """
    planilla_sueldo = models.ForeignKey(
        PlanillaSueldo,
        on_delete=models.CASCADE,
        related_name='detalles_sueldo',
        verbose_name="Planilla de Sueldos"
    )
    personal_externo = models.ForeignKey(
        'planilla.PrincipalPersonalExterno',
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name='detalles_sueldo',
        verbose_name='Personal Externo',
        db_constraint=False
    )

    # Columna G
    dias_trab = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name="DIAS TRAB.",
        help_text="Columna G del Excel"
    )
    # Columna H
    haber_basico = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="HABER BASICO",
        help_text="Columna H del Excel"
    )
    # Columna I
    categoria = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="CATEGORIA",
        help_text="Columna I del Excel (¿Bono Antigüedad?)"
    )
    lactancia_prenatal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="LACTANCIA PRENATAL",
        help_text="Bono de lactancia o prenatal. No proviene del Excel."
    )
    otros_ingresos = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="OTROS INGRESOS",
        help_text="Otros ingresos adicionales no contemplados en el Excel."
    )
    # Columna J
    total_ganado = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="TOTAL GANADO",
        help_text="Columna J del Excel"
    )
    saldo_credito_fiscal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="SALDO CREDITO FISCAL.",
        help_text="Columna T Saldo RC-IVA."
    )
    # Columna K
    rc_iva_retenido = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="RC-IVA RETENIDO",
        help_text="Columna K del Excel"
    )
    # Columna L
    gestora_publica = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="GESTORA PUBLICA",
        help_text="Columna L del Excel (¿Aporte AFP?)"
    )
    # Columna M
    aporte_nac_solidario = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="APORTE SOLIDARIO NAL.",
        help_text="Columna M del Excel"
    )
    # Columna N
    cooperativa = models.DecimalField( 
        max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="COOPERATIVA",
        help_text="Columna N del Excel"
    )
    # Columna O
    faltas = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="FALTAS",
        help_text="Columna O del Excel (Monto de descuento)"
    )
    # Columna P
    memorandums = models.DecimalField( 
        max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="MEMORANDUMS",
        help_text="Columna P del Excel (Monto de descuento)"
    )
    sanciones = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="SANCIONES",
        help_text="Monto de descuento por sanciones (típico de planillas de contrato)"
    )
    # Columna Q
    otros_descuentos = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="OTROS DESCUENTOS",
        help_text="Columna Q del Excel"
    )
    # Columna R
    total_descuentos = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="TOTAL DESCUENTOS",
        help_text="Columna R del Excel"
    )
    # Columna S
    liquido_pagable = models.DecimalField( 
        max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="LIQUIDO PAGABLE",
        help_text="Columna S del Excel"
    )

    # --- Datos de Referencia (Nombres ajustados) ---
    # Columna B
    item_referencia = models.IntegerField( 
        null=True, blank=True, verbose_name="Item (Referencia Excel)",
        help_text="Columna B del Excel"
    )
    # Columna D
    nombre_completo_referencia = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="Nombre Completo (Referencia Excel)",
        help_text="Columna D del Excel"
    )
    # Columna E
    cargo_referencia = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="Cargo (Referencia Excel)",
        help_text="Columna E del Excel"
    )
    # Columna F
    fecha_ingreso_referencia = models.DateField(
        null=True, blank=True, verbose_name="Fecha Ingreso (Referencia Excel)",
        help_text="Columna F del Excel"
    )
    # Número de fila original
    fila_excel = models.IntegerField(
        null=True, blank=True, verbose_name="Nro Fila Excel",
        help_text="Número de fila original en el archivo Excel"
    )

    class Meta:
        db_table = 'sueldo_detalle'
        verbose_name = "Detalle de Sueldo"
        verbose_name_plural = "Detalles de Sueldo"
        unique_together = ('planilla_sueldo', 'personal_externo')

    def __str__(self):
        # ... (igual que antes) ...
        nombre_display = f"ID Ext: {self.personal_externo_id}"
        if PLANILLA_APP_AVAILABLE and self.personal_externo_id:
            try:
                if hasattr(self, 'personal_externo') and self.personal_externo:
                    nombre_display = self.personal_externo.nombre_completo or nombre_display
            except Exception: pass
        return f"Sueldo {nombre_display} - Planilla ID {self.planilla_sueldo_id}"

    def clean(self):
        super().clean()
        campos_no_negativos = [
            'dias_trab', 'haber_basico', 'categoria', 'total_ganado',
            'rc_iva_retenido', 'gestora_publica', 'aporte_nac_solidario',
            'cooperativa', 'faltas', 'memorandums', 'otros_descuentos',
            'total_descuentos', 'lactancia_prenatal', 'otros_ingresos', 'saldo_credito_fiscal',
        ]
        for campo in campos_no_negativos:
            valor = getattr(self, campo)
            if valor is not None and valor < Decimal('0.00'):
                 raise ValidationError({campo: f"El valor de '{self._meta.get_field(campo).verbose_name}' no puede ser negativo."})
            

class CierreMensual(models.Model):
    """
    Representa la ejecución del proceso de generación de estado mensual
    para un periodo y tipo de planilla específico.
    """
    ESTADOS_PROCESO = [
        ('PENDIENTE', 'Pendiente de Generación'),
        ('EN_PROCESO', 'Generación en Proceso'), 
        ('COMPLETADO', 'Completado Exitosamente'),
        ('COMPLETADO_CON_ADVERTENCIAS', 'Completado con Advertencias'),
        ('ERROR', 'Error durante la Generación'),
    ]

    mes = models.IntegerField(db_index=True)
    anio = models.IntegerField(db_index=True)
    tipo_planilla = models.CharField(max_length=40, choices=PlanillaSueldo.TIPO_CHOICES, db_index=True)

    fecha_generacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora de Generación")
    usuario_generacion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cierres_mensuales_generados'
    )
    estado_proceso = models.CharField(max_length=30, choices=ESTADOS_PROCESO, default='PENDIENTE')
    resumen_proceso = models.TextField(blank=True, null=True, verbose_name="Resumen/Notas del Proceso")
    
    class Meta:
        verbose_name = "Cierre Mensual de Estado"
        verbose_name_plural = "Cierres Mensuales de Estado"
        db_table = 'sueldo_cierre_mensual'
        unique_together = ('mes', 'anio', 'tipo_planilla')
        ordering = ['-anio', '-mes', 'tipo_planilla']

    def __str__(self):
        return f"Cierre {self.mes}/{self.anio} ({self.get_tipo_planilla_display()}) - {self.get_estado_proceso_display()}"


# --- MODELO DETALLE: EstadoMensualEmpleado  ---
class EstadoMensualEmpleado(models.Model):
    """
    Almacena la 'foto' consolidada del estado de un empleado al final
    de un mes procesado, VINCULADO A UN CIERRE MENSUAL.
    """
    ESTADOS_FINALES = [
        ('ACTIVO', 'Activo'),
        ('NUEVO_INGRESO', 'Nuevo Ingreso'),
        ('CAMBIO_PUESTO', 'Cambio de Puesto Detectado'),
        ('RETIRO_DETECTADO', 'Retiro Detectado'),
        ('INCONSISTENTE_BD', 'Requiere Revisión BD'),
    ]

    # --- Vínculo a la Cabecera CierreMensual ---
    cierre_mensual = models.ForeignKey(
        CierreMensual,
        on_delete=models.CASCADE, 
        related_name='estados_empleados', 
        db_index=True
    )
    # -----------------------------------------

    # Vínculo a la persona 
    personal_externo = models.ForeignKey(
        'planilla.PrincipalPersonalExterno',
        on_delete=models.PROTECT,
        db_index=True,
        related_name='estados_mensuales_detalle', 
        db_constraint=False
    )

    estado_final_mes = models.CharField(max_length=25, choices=ESTADOS_FINALES, db_index=True)

    item = models.IntegerField(null=True, blank=True, verbose_name="Último Item Conocido")
    cargo = models.CharField(max_length=300, blank=True, null=True, verbose_name="Último Cargo Conocido")
    unidad_nombre = models.CharField(max_length=150, blank=True, null=True, verbose_name="Última Unidad Conocida")
    secretaria_nombre = models.CharField(max_length=150, blank=True, null=True, verbose_name="Última Secretaría Conocida")

    fecha_ingreso_bd = models.DateField(null=True, blank=True, verbose_name="Fecha Ingreso (BD Externa)")
    fecha_conclusion_bd = models.DateField(null=True, blank=True, verbose_name="Fecha Conclusión (BD Externa)")

    detalle_sueldo = models.OneToOneField(
        DetalleSueldo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='estado_mensual_directo' 
    )

    notas_proceso = models.TextField(blank=True, null=True, verbose_name="Notas del Proceso Específico del Empleado")
    fecha_generacion_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha Creación Registro Estado") # Renombrado

    class Meta:
        verbose_name = "Detalle Estado Mensual Empleado"
        verbose_name_plural = "Detalles Estados Mensuales Empleados"
        db_table = 'sueldo_estado_mensual_detalle' 
        unique_together = ('cierre_mensual', 'personal_externo')
        ordering = ['-cierre_mensual__anio', '-cierre_mensual__mes', 'pk']
        indexes = [
            models.Index(fields=['estado_final_mes']),
        ]

    def __str__(self):
        nombre = f"ID Ext {self.personal_externo_id}"
        return f"{nombre} ({self.cierre_mensual.mes}/{self.cierre_mensual.anio}) - {self.get_estado_final_mes_display()}"
