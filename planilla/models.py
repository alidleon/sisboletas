from django.db import models
from django.contrib.auth.models import  User 
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
# Create your models here.

# Modelo externo principal_personal
class PrincipalPersonalExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # ¡Verifica PK y db_column!
    nombre = models.CharField(max_length=50, db_column='Nombre', blank=True, null=True)
    apellido_paterno = models.CharField(max_length=50, db_column='A_Paterno', blank=True, null=True)
    apellido_materno = models.CharField(max_length=50, db_column='A_Materno', blank=True, null=True)
    ci = models.CharField(max_length=10, db_column='CI', unique=True, blank=True, null=True)
    # ... Añade aquí OTROS CAMPOS que necesites de principal_personal con sus db_column correctos

    class Meta:
        managed = False # No gestionar esta tabla con migraciones Django
        db_table = 'principal_personal' # Nombre exacto de la tabla externa
        app_label = 'planilla' # Agrupar bajo la app planilla lógicamente

    @property
    def nombre_completo(self):
        parts = [self.apellido_paterno, self.apellido_materno, self.nombre]
        return " ".join(part for part in parts if part).strip()

    def __str__(self):
        return self.nombre_completo or f"Persona Externa ID {self.id}"

# Modelo externo principal_cargo (¡ASEGÚRATE que los db_column son correctos!)
class PrincipalCargoExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # ¡Verifica PK y db_column!
    nombre_cargo = models.CharField(max_length=80, db_column='Nombre_cargo', blank=True, null=True)
    # ... Añade aquí OTROS CAMPOS que necesites de principal_cargo con sus db_column correctos

    class Meta:
        managed = False
        db_table = 'principal_cargo'
        app_label = 'planilla'

    def __str__(self):
        return self.nombre_cargo or f"Cargo Externo ID {self.id}"
    
#--------------------------------------------------------------
# --- NUEVO: Modelo para principal_secretaria ---
class PrincipalSecretariaExterna(models.Model):
    # Asumiendo que la PK en principal_secretaria es 'id' y es numérica.
    # ¡¡AJUSTA 'id' si se llama diferente!!
    id = models.AutoField(primary_key=True, db_column='id')

    # Campo para el nombre de la secretaría
    # ¡¡AJUSTA db_column si se llama diferente a 'Nombre_secretaria'!!
    nombre_secretaria = models.CharField(
        max_length=100,
        db_column='Nombre_secretaria', # Nombre de columna que proporcionaste
        blank=True, null=True          # Ser flexible con datos externos
    )
    # Añade aquí otros campos de principal_secretaria si los necesitas

    class Meta:
        managed = False                 # No crear/modificar tabla con migrate
        db_table = 'principal_secretaria' # Nombre EXACTO de la tabla externa
        app_label = 'planilla'          # Agrupar bajo la app 'planilla'

    def __str__(self):
        return self.nombre_secretaria or f"Secretaria Externa ID {self.id}"

# --- NUEVO/MODIFICADO: Modelo para principal_unidad ---
class PrincipalUnidadExterna(models.Model):
    # Asumiendo PK 'id' numérica para principal_unidad. ¡¡AJUSTA si es diferente!!
    id = models.AutoField(primary_key=True, db_column='id')

    # Campo para el nombre de la unidad
    # ¡¡AJUSTA db_column si se llama diferente a 'Nombre_unidad'!!
    nombre_unidad = models.CharField(
        max_length=86,
        db_column='Nombre_unidad',     # Nombre de columna que proporcionaste
        blank=True, null=True
    )

    # --- Clave Foránea (FK) a PrincipalSecretariaExterna ---
    # ¡¡AJUSTA db_column si se llama diferente a 'id_secretaria_id'!!
    # NOTA: Aunque dijiste varchar(50), es EXTREMADAMENTE raro que una FK
    #       sea varchar. Lo modelamos como ForeignKey asumiendo que la columna
    #       'id_secretaria_id' en 'principal_unidad' contiene el ID numérico
    #       de la secretaría. Si REALMENTE es varchar, necesitaremos otro enfoque.
    secretaria = models.ForeignKey(
        PrincipalSecretariaExterna,
        on_delete=models.DO_NOTHING,   # Política segura para datos externos
        db_column='id_secretaria_id',  # Nombre de columna FK que proporcionaste
        related_name='unidades',       # Para acceder a unidades desde secretaria (opcional)
        db_constraint=False,           # ¡¡CRUCIAL!! No crear restricción FK física
        null=True, blank=True          # Permitir unidades sin secretaría si es posible
    )
    # ------------------------------------------------------

    # Añade aquí otros campos de principal_unidad si los necesitas

    class Meta:
        managed = False
        db_table = 'principal_unidad'    # Nombre EXACTO de la tabla externa
        app_label = 'planilla'

    def __str__(self):
        return self.nombre_unidad or f"Unidad Externa ID {self.id}"


# Modelo externo principal_designacion (¡ASEGÚRATE que los db_column son correctos!)
class PrincipalDesignacionExterno(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # PK de designacion
    item = models.IntegerField(db_column='Item', null=True, blank=True)
    tipo_designacion = models.CharField(
        max_length=50, # Ajusta tamaño
        db_column='tipo', # ¡Nombre exacto de la columna externa!
        blank=True, null=True
    )
    estado = models.CharField(
        max_length=20, # Ajusta el tamaño si es necesario ('RESTRUCTURACION' es largo)
        db_column='Estado', # ¡Nombre EXACTO de la columna externa!
        blank=True, null=True # Permitir null/blanco si es posible en la BD
    )

    # Claves Foráneas (¡ASEGURA db_column!)
    # Usamos related_name='+' para no crear relación inversa que no necesitamos aquí
    personal = models.ForeignKey(
        PrincipalPersonalExterno,
        on_delete=models.DO_NOTHING, # O PROTECT. No usar CASCADE con datos externos.
        db_column='id_personal',     # ¡Nombre exacto de la columna FK en principal_designacion!
        related_name='+'
    )
    cargo = models.ForeignKey(
        PrincipalCargoExterno,
        on_delete=models.DO_NOTHING,
        db_column='id_cargo_id',    # ¡Nombre exacto de la columna FK en principal_designacion!
        related_name='+'
    )
    # id_unidad_id = models.IntegerField(db_column='id_unidad_id', ...) # Si lo necesitas
    unidad = models.ForeignKey(
        PrincipalUnidadExterna,
        on_delete=models.DO_NOTHING,   # Política segura
        db_column='id_unidad_id',      # Nombre de columna FK que mencionaste
        related_name='designaciones',  # Para acceder a designaciones desde unidad (opcional)
        db_constraint=False,           # ¡¡CRUCIAL!!
        null=True, blank=True          # Permitir designaciones sin unidad si es posible
    )

    class Meta:
        managed = False
        db_table = 'principal_designacion'
        app_label = 'planilla'

    def __str__(self):
        # Actualizado para incluir unidad_id
        return (f"Designacion ID {self.id} (Tipo: {self.tipo_designacion}, Estado: {self.estado}, "
                f"Item: {self.item}, Personal: {self.personal_id}, Unidad: {self.unidad_id})")


#tabla planilla

class Planilla(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
    ]
    TIPO_CHOICES = [
        ('planta', 'Asegurado'),
        ('contrato', 'Contrato'),
        ('consultor', 'Consultor en Linea'),
        
    ]
    mes = models.IntegerField()
    anio = models.IntegerField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    fecha_elaboracion = models.DateField(auto_now_add=True)
    fecha_aprobacion = models.DateField(null=True, blank=True)
    fecha_revision = models.DateField(null=True, blank=True)
    usuario_elaboracion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_elaboradas')
    usuario_aprobacion = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_aprobadas')
    usuario_revision = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='planillas_revisadas')
    ufvi = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    ufvf = models.DecimalField(max_digits=8, decimal_places=5, null=True, blank=True)
    smn = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_dias = models.IntegerField(null=True, blank=True) # ¿Se usa? ¿O usamos dias_habiles?
    importe_diario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, null=True, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True) # ¿Calcular basado en mes/año?
    fecha_fin = models.DateField(null=True, blank=True)   # ¿Calcular basado en mes/año?
    fecha_baja = models.DateField(null=True, blank=True)
    #impositiva = models.BooleanField(default=False) # ¿Se usa para tipo Bono TE?
   

    # --- Campo clave: Días Hábiles de la Planilla ---
    dias_habiles = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Días Hábiles del Mes')

    def __str__(self):
        return f"Planilla {self.get_tipo_display()} {self.mes}/{self.anio} - {self.get_estado_display()}"

    @classmethod
    def crear_planilla(cls, mes, anio, usuario_elaboracion, fecha_inicio, fecha_fin, tipo, dias_habiles, estado='pendiente'):
        """ Método helper para crear planilla (si aún lo usas) """
        planilla = cls(
            mes=mes,
            anio=anio,
            estado=estado,
            usuario_elaboracion=usuario_elaboracion,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo=tipo,
            dias_habiles=dias_habiles, # Asegúrate de pasar los días hábiles
            
        )
        planilla.save()
        return planilla


    



    
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
    
    
    class Meta:
        db_table = 'detalle_impositiva'  # Especifica el nombre de la tabla si no usas el predeterminado

    def __str__(self):
        return f"Detalle impositivo para {self.id_personal} en planilla {self.id_planilla}"


    #tabla bono te


class DetalleBonoTe(models.Model):
    id_planilla = models.ForeignKey(
        'Planilla',
        on_delete=models.CASCADE,
        null=True, # Debería ser False si siempre pertenece a una planilla
        blank=False,
        related_name='detalles_bono_te',
        verbose_name='Planilla'
    )
    # --- VINCULO DIRECTO A PERSONAL EXTERNO (BD SOLO LECTURA) ---
    personal_externo = models.ForeignKey(
        PrincipalPersonalExterno,
        on_delete=models.SET_NULL, # O PROTECT si prefieres error al borrar externo
        null=True,
        blank=False, # ¿Debería ser obligatorio tener personal? Probablemente sí.
        related_name='detalles_bono_te',
        verbose_name='Personal Externo',
        db_constraint=False # ¡MUY IMPORTANTE! No crear FK física entre BDs
    )
    # ---------------------------------------------------------------
    # Campo id_sueldo se mantiene por si acaso, pero no lo usaremos para vincular persona ahora
    id_sueldo = models.ForeignKey(
        'DetalleSueldo',
        on_delete=models.SET_NULL, # O CASCADE si el detalle de sueldo es el 'master'
        null=True,
        blank=True,
        related_name='+', # No necesitamos la relación inversa desde DetalleSueldo por ahora
        verbose_name="Detalle de Sueldo Asociado (Opcional)"
    )

    mes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Mes (Heredado)') # ¿Realmente necesario si está en Planilla?

    # Campos de ausencias y permisos (valores a llenar)
    faltas = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Faltas (días)')
    viajes = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Viajes (días)')
    pcgh = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PCGH (días)')
    psgh = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PSGH (días)')
    perm_excep = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Perm. Excep. (días)')
    asuetos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Asuetos (días)')
    pcgh_embar_enf_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='PCGH Emb/Enf Base (días)')
    vacacion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Vacación (días)')
    bajas_medicas = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Bajas Médicas (días)')

    # --- ¡CAMPO dias_habiles ELIMINADO DE AQUÍ! --- Se toma de la Planilla

    # Campos calculados (se actualizan en save)
    dias_no_pagados = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Días No Pagados (Calculado)')
    dias_pagados = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Días Pagados (Calculado)')
    total_ganado = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Total Ganado Bono (Calculado)')

    # Otros campos
    descuentos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Otros Descuentos al Bono') # ¿Aplica al bono?
    liquido_pagable = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Líquido Pagable Bono (Calculado)')
    rc_iva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='RC-IVA (¿Aplica al bono?)')
    dias_cancelados = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Cancelados') # ¿Cómo se diferencia de dias_pagados?
    otros_descuentos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Otros Descuentos (Duplicado?)')

    # Campos informativos (¿Se necesitan aquí si están en Planilla?)
    # fecha_inicio = models.DateField(null=True, blank=True, verbose_name='Fecha Inicio Periodo')
    # fecha_fin = models.DateField(null=True, blank=True, verbose_name='Fecha Fin Periodo')
    # dias_total_trab = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Días Total Trabajados') # ¿Se usa?

    class Meta:
        db_table = 'detalle_bono_te'
        verbose_name = "Detalle de Bono TE"
        verbose_name_plural = "Detalles de Bono TE"
        # Considera añadir una restricción única a nivel de base de datos si es posible
        # O manejarla en la lógica de la vista/formulario para evitar duplicados
        # unique_together = ('id_planilla', 'personal_externo') # ¡CUIDADO! No funciona bien si personal_externo puede ser NULL

    def __str__(self):
        nombre_persona = "Personal no asignado"
        if self.personal_externo:
            # Intentamos obtener el nombre completo, pero puede que el objeto no esté cargado
            # Es más seguro referenciar el ID o hacer un select_related en la consulta que obtiene este objeto
            try:
                nombre_persona = self.personal_externo.nombre_completo or f"ID Externo: {self.personal_externo_id}"
            except PrincipalPersonalExterno.DoesNotExist:
                 nombre_persona = f"ID Externo: {self.personal_externo_id} (No encontrado)"
            except AttributeError: # Si personal_externo es None
                 nombre_persona = f"ID Externo: {self.personal_externo_id}"

        return f"Detalle Bono TE para {nombre_persona} en Planilla ID {self.id_planilla_id}"

    def calcular_valores(self):
        """
        Método para calcular los campos derivados.
        Puede ser llamado desde save() o externamente si es necesario.
        """
        VALOR_DIA_BONO_TE = 18 # Considera mover a settings.py o a un modelo de configuración

        # Obtener días hábiles de la planilla asociada
        dias_habiles_planilla = None
        if self.id_planilla:
            dias_habiles_planilla = self.id_planilla.dias_habiles

        # Calcular días no pagados sumando todas las ausencias/permisos
        # Usamos filter(None, [...]) para ignorar Nones y sumamos
        self.dias_no_pagados = sum(filter(None, [
            self.faltas, self.vacacion, self.viajes, self.bajas_medicas,
            self.pcgh, self.psgh, self.perm_excep, self.asuetos,
            self.pcgh_embar_enf_base
        ]))

        # Calcular días pagados
        if dias_habiles_planilla is not None and self.dias_no_pagados is not None:
             # Asegurar que dias_no_pagados no exceda dias_habiles para el cálculo
            dias_no_pagados_ajustado = min(self.dias_no_pagados, dias_habiles_planilla)
            self.dias_pagados = dias_habiles_planilla - dias_no_pagados_ajustado
            if self.dias_pagados < 0: # Seguridad extra
                self.dias_pagados = 0
        else:
            self.dias_pagados = 0 # O None si prefieres indicar que no se pudo calcular

        # Calcular total ganado
        if self.dias_pagados is not None:
            self.total_ganado = self.dias_pagados * VALOR_DIA_BONO_TE
        else:
            self.total_ganado = 0 # O None

        # Calcular líquido pagable
        if self.total_ganado is not None:
            self.liquido_pagable = self.total_ganado - (self.descuentos or 0) # Asegúrate que 'descuentos' es el campo correcto
            if self.liquido_pagable < 0: # Seguridad extra
                self.liquido_pagable = 0
        else:
             self.liquido_pagable = 0 # O None

    def save(self, *args, **kwargs):
        # Llamar a la lógica de cálculo antes de guardar
        self.calcular_valores()

        # Validar que dias_no_pagados no sea mayor que dias_habiles (Opcional, informativo)
        # Es mejor validar esto en el formulario antes de guardar si es posible
        # dias_habiles_planilla = self.id_planilla.dias_habiles if self.id_planilla else None
        # if dias_habiles_planilla is not None and self.dias_no_pagados is not None:
        #     if self.dias_no_pagados > dias_habiles_planilla:
        #         # En lugar de ValidationError (que no funciona bien con bulk_create)
        #         # podrías loggear una advertencia o manejarlo en la vista.
        #         print(f"ADVERTENCIA: Días no pagados ({self.dias_no_pagados}) exceden días hábiles ({dias_habiles_planilla}) para Detalle ID {self.pk}")
        #         # raise ValidationError("Los días no pagados no pueden ser mayores que los días hábiles.")

        super().save(*args, **kwargs) # Llama al método save() original del padre



#----------------------------------------------------------------

# --- En planilla/models.py ---

class PrincipalPersonal(models.Model):
    id = models.AutoField(primary_key=True, db_column='id') # Suponiendo que se llama 'id'
    nombre = models.CharField(max_length=150, blank=True, null=True, db_column='Nombre') # Ya sabemos que esta es 'Nombre'
    apellido_paterno = models.CharField(max_length=100, blank=True, null=True, db_column='A_Paterno') # ¡EJEMPLO! Usa el nombre real
    apellido_materno = models.CharField(max_length=100, blank=True, null=True, db_column='A_Materno') # ¡EJEMPLO! Usa el nombre real
    ci = models.CharField(max_length=20, blank=True, null=True, unique=True, db_column='CI') # ¡EJEMPLO! Usa el nombre real
    fecha_nacimiento = models.DateField(blank=True, null=True, db_column='Fecha_nac') # ¡EJEMPLO! Usa el nombre real
    # ... ajusta db_column para TODOS los demás campos ...

    class Meta:
        managed = False
        db_table = 'principal_personal'
        app_label = 'planilla'

    # ... __str__ y nombre_completo se quedan igual ...

#----------------------------------------------------------------




