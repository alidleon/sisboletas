from django.db import models
from django.contrib.auth.models import  User 
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
# Create your models here.


#tabla planilla

class Planilla(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
    ]
    TIPO_CHOICES = [
        ('planta', 'Planta'),
        ('contrato', 'Contrato'),
        ('consultor', 'Consultor'),
    ]
    mes = models.IntegerField()
    anio = models.IntegerField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    fecha_elaboracion = models.DateField(auto_now_add=True)
    fecha_aprobacion = models.DateField(null=True, blank=True)
    fecha_revision = models.DateField(null=True, blank=True)
    usuario_elaboracion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_elaboradas') #ForeignKey al modelo User
    usuario_aprobacion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_aprobadas') #ForeignKey al modelo User
    usuario_revision = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_revisadas') #ForeignKey al modelo User
    ufvi = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    ufvf = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    smn = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_dias = models.IntegerField(null=True, blank=True)
    importe_diario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, null=True, blank=True) # Usamos el choices
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    impositiva = models.BooleanField(default=False)
    bono_te = models.BooleanField(default=False)
    dias_habiles = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Días Hábiles') # Agregamos el campo dias_habiles

    def __str__(self):
        return f"Planilla {self.mes}/{self.anio} - Estado: {self.estado}"

    @classmethod
    def crear_planilla(cls, mes, anio, usuario_elaboracion, fecha_inicio, fecha_fin, tipo, estado='pendiente'):
        """
        Crea una nueva instancia de Planilla.

        Args:
            mes (int): El mes de la planilla.
            anio (int): El año de la planilla.
            usuario_elaboracion (User): El usuario que elabora la planilla.
            fecha_inicio (date): La fecha de inicio de la planilla.
            fecha_fin (date): La fecha de fin de la planilla.
            tipo (str): El tipo de la planilla
            estado (str, optional): El estado inicial de la planilla. Defaults to 'pendiente'.

        Returns:
            Planilla: La nueva instancia de Planilla creada.
        """
        planilla = cls(
            mes=mes,
            anio=anio,
            estado=estado,
            usuario_elaboracion=usuario_elaboracion,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo=tipo,  # Pasamos el tipo a la instancia de Planilla
        )
        planilla.save()
        return planilla
#tabla estado
class Estado(models.Model):
    planilla = models.ForeignKey(Planilla, on_delete=models.CASCADE, related_name='estados')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'estado'
        app_label = 'planillas'

    def __str__(self):
        return f'Estado {self.id}: {self.activo} en {self.fecha}'

    


#tabla personal
class Personal(models.Model):
    TIPO_PERSONAL_CHOICES = [
        ('planta', 'Planta'),
        ('contrato', 'Contrato'),
        
    ]
    id_personal = models.AutoField(primary_key=True, verbose_name='ID Personal')
    tipo_personal = models.CharField(max_length=10, choices=TIPO_PERSONAL_CHOICES, verbose_name='Tipo Personal')
    def __str__(self):
        return (self.id_personal, self.tipo_personal)

class Unidad(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return (self.id, self.nombre)

    
class DetalleSueldo(models.Model):

    TIPO_SEGURO_CHOICES = [
        ('salud', 'Salud'),
        ('riesgo', 'Riesgo'),
        ('otro', 'Otro'),
    ]
    TIPO_AFP_CHOICES = [
      ('futuro', 'Futuro'),
      ('prevision', 'Previsión')
    ]
    
    MODO_CANCELACION_CHOICES = [
        ('banco', 'Banco'),
        ('efectivo', 'Efectivo')
    ]

    id_personal = models.ForeignKey('Personal', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_sueldo', verbose_name="Personal")
    nitem = models.CharField(max_length=50, null=True, blank=True, verbose_name='NITEM')
    cargo = models.CharField(max_length=150, null=True, blank=True, verbose_name='Cargo')
    fecha_ingreso = models.DateField(null=True, blank=True, verbose_name='Fecha de Ingreso')
    dias_trabajados = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Trabajados')
    haber_basico = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Haber Básico')
    categoria = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Categoría')
    lac_pre_natal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Lactancia Prenatal')
    afp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='AFP')
    rc_iva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='RC-IVA')
    cooperativa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Cooperativa')
    faltas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Faltas')
    memos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Memos')
    otros_descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Otros Descuentos')
    tipo_seguro = models.CharField(max_length=40, choices=TIPO_SEGURO_CHOICES, null=True, blank=True, verbose_name='Tipo de Seguro')
    id_planilla = models.ForeignKey('Planilla', on_delete=models.CASCADE, null=True, blank=True, related_name='detalles_sueldo', verbose_name='Planilla')
    fecha_inicio = models.DateField(null=True, blank=True, verbose_name='Fecha de Inicio')
    fecha_fin = models.DateField(null=True, blank=True, verbose_name='Fecha de Fin')
    total_ganado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Total Ganado')
    total_descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Total Descuentos')
    liquido_pagable = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Líquido Pagable')
    haber_basico_base = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Haber Básico Base')
    id_unidad = models.ForeignKey('Unidad', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_sueldo', verbose_name='Unidad')
    tipo_afp = models.CharField(max_length=10, choices=TIPO_AFP_CHOICES, null=True, blank=True, verbose_name="Tipo de AFP")
    modo_cancelacion = models.CharField(max_length=20, choices=MODO_CANCELACION_CHOICES, null=True, blank=True, verbose_name='Modo de Cancelación')
    hospital = models.CharField(max_length=10, null=True, blank=True, verbose_name='Hospital')
    bono_solidario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Bono Solidario')
    num_faltas = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Número de Faltas')
    num_sanciones = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Número de Sanciones')
    
    class Meta:
        db_table = 'detalle_sueldos'  # Especifica el nombre de la tabla si no usas el predeterminado

    def __str__(self):
      return f"Detalle de sueldo para {self.id_personal} en planilla {self.id_planilla}"



    #tabla impositiva


class DetalleImpositiva(models.Model):
    id_personal = models.ForeignKey('Personal', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_impositiva', verbose_name="Personal")
    total_ganado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Total Ganado')
    sueldo_neto = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Sueldo Neto')
    f110 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='F110')
    saldo_fisco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Fisco')
    saldo_dependiente = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Dependiente')
    saldo_anterior = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Anterior')
    saldo_total_dependiente = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Total Dependiente')
    saldo_utilizado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Utilizado')
    impuesto_retenido = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Impuesto Retenido')
    saldo_proximo_mes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Saldo Próximo Mes')
    id_planilla = models.ForeignKey('Planilla', on_delete=models.CASCADE, null=True, blank=True, related_name='detalles_impositiva', verbose_name='Planilla')
    id_sueldo = models.ForeignKey('DetalleSueldo', on_delete=models.CASCADE, null=True, blank=True, related_name='detalles_impositiva', verbose_name="Detalle de Sueldo")
    id_unidad = models.ForeignKey('Unidad', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_impositiva', verbose_name='Unidad')
    
    class Meta:
        db_table = 'detalle_impositiva'  # Especifica el nombre de la tabla si no usas el predeterminado

    def __str__(self):
        return f"Detalle impositivo para {self.id_personal} en planilla {self.id_planilla}"


    #tabla bono te


class DetalleBonoTe(models.Model):


    id_personal = models.ForeignKey('Personal', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_bono_te', verbose_name="Personal")
    
    mes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Mes')
    
    
    faltas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Faltas')
    viajes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Viajes')
    pcgh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='PCGH')
    psgh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='PSGH')
    perm_excep = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Perm_Excep')
    asuetos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Asuetos')
    pcgh_embar_enf_base = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='PCGH Embarazada Efermedad de Base')
    dias_habiles = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Dias Habiles')
    dias_no_pagados = models.DecimalField(max_digits=10, decimal_places=2, null=True,blank=True, verbose_name='Dias no Pagados')
    dias_pagados = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Dias Pagados')
    vacacion = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Vacación')
    bajas_medicas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Bajas Médicas')
    dias_cancelados = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Cancelados')
    otros_descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Otros Descuentos')
    liquido_pagable = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Líquido Pagable')
    id_planilla = models.ForeignKey('Planilla', on_delete=models.CASCADE, null=True, blank=True, related_name='detalles_bono_te', verbose_name='Planilla')
    id_sueldo = models.ForeignKey('DetalleSueldo', on_delete=models.CASCADE, null=True, blank=True, related_name='detalles_bono_te', verbose_name="Detalle de Sueldo")
    rc_iva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='RC-IVA')
    dias_total_trab = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Total Trabajados')
    id_unidad = models.ForeignKey('Unidad', on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_bono_te', verbose_name='Unidad')
    total_ganado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Total Ganado')
    descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Descuentos')
    fecha_inicio = models.DateField(null=True, blank=True, verbose_name='Fecha de Inicio')
    fecha_fin = models.DateField(null=True, blank=True, verbose_name='Fecha de Fin')
    


    class Meta:
        db_table = 'detalle_bono_te'  # Especifica el nombre de la tabla si no usas el predeterminado

    def __str__(self):
        return f"Detalle Bono TE para {self.id_personal} en planilla {self.id_planilla}"
    
    def save(self, *args, **kwargs):
        
        

        # Calcula dias_no_pagados
        self.dias_no_pagados = (
            (self.faltas or 0) +
            (self.vacacion or 0) +
            (self.viajes or 0) +
            (self.bajas_medicas or 0) +
            (self.pcgh or 0) +
            (self.psgh or 0) +
            (self.perm_excep or 0) +
            (self.asuetos or 0) +
            (self.pcgh_embar_enf_base or 0)
        )
        # Imprimir los valores de los campos antes de guardar
        print("Valores antes de guardar:")
        print("dias_habiles:", self.dias_habiles)
        print("dias_no_pagados:", self.dias_no_pagados)
        # Validar que dias_no_pagados no sea mayor que dias_habiles
        if (self.dias_no_pagados or 0) > (self.dias_habiles or 0):
            raise ValidationError("Los días no pagados no pueden ser mayores que los días hábiles.")
        
        # Calcula dias_pagados (MODIFICADO)
        self.dias_pagados = (self.dias_habiles or 0) - (self.dias_no_pagados or 0)
        if self.dias_pagados < 0:
            self.dias_pagados = 0  # O puedes lanzar una excepción
        
        # Calcula total ganado
        self.total_ganado = (self.dias_pagados or 0) * 18

        # Calcula liquido_pagable
        self.liquido_pagable = (self.total_ganado or 0) - (self.descuentos or 0)
        if self.liquido_pagable < 0:
            self.liquido_pagable = 0  # O puedes lanzar una excepción

        super().save(*args, **kwargs)  # Llama al método save() original