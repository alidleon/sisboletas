# planilla/models.py (Versión Original con BD Externa)

from django.db import models
from django.contrib.auth.models import User # Asegúrate si usas este o settings.AUTH_USER_MODEL
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from reportes.models import PlanillaAsistencia
# Create your models here.

# --- Modelos para BD Externa ('personas_db') ---

# Modelo externo principal_personal
class PrincipalPersonalExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # ¡Verifica PK y db_column!
    nombre = models.CharField(max_length=50, db_column='Nombre', blank=True, null=True)
    apellido_paterno = models.CharField(max_length=50, db_column='A_Paterno', blank=True, null=True)
    apellido_materno = models.CharField(max_length=50, db_column='A_Materno', blank=True, null=True)
    ci = models.CharField(max_length=10, db_column='CI', unique=True, blank=True, null=True)
    # ... Añade aquí OTROS CAMPOS que necesites de principal_personal con sus db_column correctos
    # Ejemplo (si lo tenías):
    # fecha_nacimiento = models.DateField(blank=True, null=True, db_column='Fecha_nac')

    class Meta:
        managed = False # No gestionar esta tabla con migraciones Django
        db_table = 'principal_personal' # Nombre exacto de la tabla externa
        # app_label = 'planilla' # Opcional si está en la app correcta

    @property
    def nombre_completo(self):
        parts = [self.apellido_paterno, self.apellido_materno, self.nombre]
        return " ".join(part for part in parts if part).strip()

    def __str__(self):
        return self.nombre_completo or f"Persona Externa ID {self.id}"

# Modelo externo principal_cargo
class PrincipalCargoExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # ¡Verifica PK y db_column!
    nombre_cargo = models.CharField(max_length=80, db_column='Nombre_cargo', blank=True, null=True)
    # ... Añade aquí OTROS CAMPOS que necesites de principal_cargo con sus db_column correctos

    class Meta:
        managed = False
        db_table = 'principal_cargo'
        # app_label = 'planilla'

    def __str__(self):
        return self.nombre_cargo or f"Cargo Externo ID {self.id}"

# Modelo externo principal_secretaria
class PrincipalSecretariaExterna(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # Ajusta PK/db_column
    nombre_secretaria = models.CharField(
        max_length=100,
        db_column='Nombre_secretaria', # Ajusta db_column
        blank=True, null=True
    )
    # ... otros campos ...

    class Meta:
        managed = False
        db_table = 'principal_secretaria' # Ajusta nombre tabla
        # app_label = 'planilla'

    def __str__(self):
        return self.nombre_secretaria or f"Secretaria Externa ID {self.id}"

# Modelo externo principal_unidad
class PrincipalUnidadExterna(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # Ajusta PK/db_column
    nombre_unidad = models.CharField(
        max_length=86,
        db_column='Nombre_unidad', # Ajusta db_column
        blank=True, null=True
    )
    # Clave Foránea a PrincipalSecretariaExterna
    secretaria = models.ForeignKey(
        PrincipalSecretariaExterna,
        on_delete=models.DO_NOTHING,
        db_column='id_secretaria_id', # Ajusta nombre columna FK
        related_name='unidades',
        db_constraint=False, # ¡MUY IMPORTANTE!
        null=True, blank=True
    )
    # ... otros campos ...

    class Meta:
        managed = False
        db_table = 'principal_unidad' # Ajusta nombre tabla
        # app_label = 'planilla'

    def __str__(self):
        return self.nombre_unidad or f"Unidad Externa ID {self.id}"


# Modelo externo principal_designacion
class PrincipalDesignacionExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # Ajusta PK/db_column
    item = models.IntegerField(db_column='Item', null=True, blank=True)
    tipo_designacion = models.CharField( # Nombre original del campo tipo
        max_length=50, # Ajusta tamaño
        db_column='tipo', # Nombre exacto de la columna externa
        blank=True, null=True
    )
    estado = models.CharField( # Nombre original del campo estado
        max_length=20, # Ajusta tamaño ('RESTRUCTURACION', 'ACTIVO', etc)
        db_column='Estado', # Nombre EXACTO de la columna externa
        blank=True, null=True
    )

    fecha_conclusion = models.DateField(
        db_column='Fecha_conclusion', # <-- ¡Poner aquí el NOMBRE EXACTO de la columna en personas_db!
        null=True, blank=True # Debe permitir nulos si no todos tienen fecha
    )
    # -----------------------------------

    # --- Campo Fecha Ingreso (Asegúrate que también exista y esté correcto) ---
    fecha_ingreso = models.DateField(
         db_column='Fecha_ingreso', # <-- ¡Verifica este nombre de columna también!
         null=True, blank=True
    )
    # Claves Foráneas
    personal = models.ForeignKey(
        PrincipalPersonalExterno,
        on_delete=models.DO_NOTHING,
        db_column='id_personal', # Ajusta columna FK a personal
        related_name='+', # Sin relación inversa necesaria aquí
        db_constraint=False, # ¡Importante!
    )
    cargo = models.ForeignKey(
        PrincipalCargoExterno,
        on_delete=models.DO_NOTHING,
        db_column='id_cargo_id', # Ajusta columna FK a cargo
        related_name='+',
        db_constraint=False, # ¡Importante!
    )
    unidad = models.ForeignKey(
        PrincipalUnidadExterna,
        on_delete=models.DO_NOTHING,
        db_column='id_unidad_id', # Ajusta columna FK a unidad
        related_name='designaciones',
        db_constraint=False, # ¡Importante!
        null=True, blank=True
    )
    # ... otros campos ...

    class Meta:
        managed = False
        db_table = 'principal_designacion' # Ajusta nombre tabla
        # app_label = 'planilla'

    def __str__(self):
        return (f"Designacion Externa ID {self.id} (Tipo: {self.tipo_designacion}, Estado: {self.estado}, "
                f"Item: {self.item}, Personal: {self.personal_id}, Unidad: {self.unidad_id})")


# --- Modelos Internos (BD 'default') ---

class Planilla(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
    ]
    # Revertir a choices originales si los tenías diferentes
    TIPO_CHOICES = [
        ('planta', 'Asegurado'),    # Valor original 'planta'?
        ('contrato', 'Contrato'),   # Valor original 'contrato'?
        ('consultor', 'Consultor en Linea'), # Valor original 'consultor'?
    ]
    mes = models.IntegerField()
    anio = models.IntegerField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    fecha_elaboracion = models.DateField(auto_now_add=True)
    fecha_aprobacion = models.DateField(null=True, blank=True) # Estaba antes?
    fecha_revision = models.DateField(null=True, blank=True) # Estaba antes?
    usuario_elaboracion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_elaboradas')
    usuario_aprobacion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_aprobadas')
    usuario_revision = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_revisadas')
    ufvi = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    ufvf = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    smn = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_dias = models.IntegerField(null=True, blank=True)
    importe_diario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Revertir tipo a max_length y choices originales
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, null=True, blank=True)
    planilla_asistencia_base = models.OneToOneField(PlanillaAsistencia, on_delete=models.PROTECT, related_name='planilla_bono_te_generada', verbose_name="Planilla de Asistencia Base", null=True, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    dias_habiles = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Días Hábiles del Mes')

    def __str__(self):
        return f"Planilla {self.get_tipo_display()} {self.mes}/{self.anio} - {self.get_estado_display()}"

    def clean(self):
        super().clean()

        if self.planilla_asistencia_base:
            if hasattr(self, 'mes') and self.mes != self.planilla_asistencia_base.mes:
                raise ValidationError({'mes': f"El mes ({self.mes}) no coincide con el de la Planilla de Asistencia base ({self.planilla_asistencia_base.mes})."})
            if hasattr(self, 'anio') and self.anio != self.planilla_asistencia_base.anio:
                raise ValidationError({'anio': f"El año ({self.anio}) no coincide con el de la Planilla de Asistencia base ({self.planilla_asistencia_base.anio})."})
            if hasattr(self, 'tipo') and self.tipo != self.planilla_asistencia_base.tipo:
                tipo_base_display = self.planilla_asistencia_base.get_tipo_display() if hasattr(self.planilla_asistencia_base, 'get_tipo_display') else self.planilla_asistencia_base.tipo
                tipo_actual_display = self.get_tipo_display() if hasattr(self, 'get_tipo_display') else self.tipo
                raise ValidationError({'tipo': f"El tipo ({tipo_actual_display}) no coincide con el de la Planilla de Asistencia base ({tipo_base_display})."})

        if self.planilla_asistencia_base_id:
            queryset = Planilla.objects.filter(planilla_asistencia_base_id=self.planilla_asistencia_base_id)
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)
            
            if queryset.exists():
                raise ValidationError(
                    {'planilla_asistencia_base': 'Esta Planilla de Asistencia ya ha sido utilizada como base para otra Planilla de Bono TE.'}
                )

# --- Modelo DetalleBonoTe ---
class DetalleBonoTe(models.Model):
    id_planilla = models.ForeignKey(
        'Planilla',
        on_delete=models.CASCADE,
        null=True, # Era True originalmente? O False? Verifica tu estado anterior.
        blank=False, # Era False?
        related_name='detalles_bono_te',
        verbose_name='Planilla'
    )
    # --- VINCULO A PERSONAL EXTERNO ---
    personal_externo = models.ForeignKey(
        PrincipalPersonalExterno, # Apunta al modelo externo
        on_delete=models.SET_NULL, # O PROTECT? Verifica tu estado anterior
        null=True,                 # Permitir Null si se borra el externo
        blank=False, # Era False?
        related_name='detalles_bono_te',
        verbose_name='Personal Externo',
        db_constraint=False # ¡MUY IMPORTANTE!
    )
    # ---------------------------------------------------------------


    mes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Mes (Heredado)')

    # Campos de ausencias/permisos (sin cambios estructurales)
    abandono_dias = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Abandono (días)', help_text="Días registrados como abandono de trabajo.")
    faltas = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Faltas (días)')
    viajes = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Viajes (días)')
    pcgh = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PCGH (días)')
    psgh = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PSGH (días)')
    perm_excep = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Perm. Excep. (días)')
    asuetos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Asuetos (días)')
    pcgh_embar_enf_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PCGH Emb/Enf Base (días)')
    vacacion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Vacación (días)')
    bajas_medicas = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Bajas Médicas (días)')

    # Campos calculados (sin cambios estructurales)
    dias_no_pagados = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Días No Pagados (Calculado)')
    dias_pagados = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Días Pagados (Calculado)')
    total_ganado = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Total Ganado Bono (Calculado)')

    # Otros campos (restaurar si los tenías)
    descuentos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Otros Descuentos al Bono')
    liquido_pagable = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Líquido Pagable Bono (Calculado)')
    rc_iva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='RC-IVA (¿Aplica al bono?)') # Estaba?
    dias_cancelados = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Cancelados') # Estaba?
    otros_descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Otros Descuentos (Duplicado?)') # Estaba?
    observaciones_asistencia = models.TextField(
        blank=True, null=True,
        verbose_name="Observaciones (Copiado de Asistencia)",
        help_text="Notas registradas en el detalle de asistencia para este periodo."
    )

    observaciones_bono = models.TextField(
        blank=True, null=True,
        verbose_name="Observaciones (Bono TE)",
        help_text="Notas específicas sobre este registro de Bono TE o ediciones realizadas."
    )

    class Meta:
        db_table = 'detalle_bono_te' # Mantenemos nombre si ya existía
        verbose_name = "Detalle de Bono TE"
        verbose_name_plural = "Detalles de Bono TE"
        # unique_together no funcionaba bien con FK externa null
        # unique_together = ('id_planilla', 'personal_externo')

    def __str__(self):
        # Versión original que maneja la posibilidad de no encontrar el externo
        nombre_persona = f"ID Externo: {self.personal_externo_id}"
        if self.personal_externo_id:
             try:
                 # Intenta cargar el objeto externo si es posible (puede ser costoso)
                 # persona = PrincipalPersonalExterno.objects.using('personas_db').get(pk=self.personal_externo_id)
                 # nombre_persona = persona.nombre_completo or nombre_persona
                 # Alternativa más segura: Solo mostrar el ID
                 pass # Dejar como ID Externo por defecto
             except PrincipalPersonalExterno.DoesNotExist:
                  nombre_persona = f"ID Externo: {self.personal_externo_id} (No encontrado)"
             except Exception: # Captura otros errores de BD externa
                  nombre_persona = f"ID Externo: {self.personal_externo_id} (Error consulta)"

        return f"Detalle Bono TE para {nombre_persona} en Planilla ID {self.id_planilla_id}"

    # La función calcular_valores() no cambia su lógica interna esencialmente,
    # solo necesita acceso a self.id_planilla.dias_habiles
    def calcular_valores(self):
        VALOR_DIA_BONO_TE = 18 # Valor original
        # ... (resto de la lógica igual que antes) ...
        dias_habiles_planilla = self.id_planilla.dias_habiles if self.id_planilla else None
        self.dias_no_pagados = sum(filter(None, [
            self.abandono_dias, self.faltas, self.vacacion, self.viajes, self.bajas_medicas,
            self.pcgh, self.psgh, self.perm_excep, self.asuetos,
            self.pcgh_embar_enf_base
        ]))
        if dias_habiles_planilla is not None and self.dias_no_pagados is not None:
            dias_no_pagados_ajustado = min(self.dias_no_pagados, dias_habiles_planilla)
            self.dias_pagados = dias_habiles_planilla - dias_no_pagados_ajustado
            self.dias_pagados = max(self.dias_pagados, 0)
        else:
            self.dias_pagados = 0
        if self.dias_pagados is not None:
            self.total_ganado = self.dias_pagados * VALOR_DIA_BONO_TE
        else:
            self.total_ganado = 0
        if self.total_ganado is not None:
            self.liquido_pagable = self.total_ganado - (self.descuentos or 0)
            self.liquido_pagable = max(self.liquido_pagable, 0)
        else:
             self.liquido_pagable = 0

    def save(self, *args, **kwargs):
        self.calcular_valores()
        super().save(*args, **kwargs)

# --- Restaurar DetalleSueldo y DetalleImpositiva si los tenías ---
# class DetalleSueldo(models.Model):
#      ... (pegar definición original si existía) ...
# class DetalleImpositiva(models.Model):
#      ... (pegar definición original si existía) ...

# --- Modelo PrincipalPersonal (Probablemente duplicado accidental) ---
# Si tenías este modelo ADEMÁS de PrincipalPersonalExterno, restáuralo,
# pero lo más probable es que fuera un error y deberías eliminarlo.
# class PrincipalPersonal(models.Model):
#     ...

