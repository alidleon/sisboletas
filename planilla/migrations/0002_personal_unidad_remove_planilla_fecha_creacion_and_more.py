# Generated by Django 5.1.4 on 2025-01-16 22:11

import datetime
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Personal',
            fields=[
                ('id_personal', models.AutoField(primary_key=True, serialize=False, verbose_name='ID Personal')),
                ('tipo_personal', models.CharField(choices=[('planta', 'Planta'), ('contrato', 'Contrato')], max_length=10, verbose_name='Tipo Personal')),
            ],
        ),
        migrations.CreateModel(
            name='Unidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
            ],
        ),
        migrations.RemoveField(
            model_name='planilla',
            name='fecha_creacion',
        ),
        migrations.AddField(
            model_name='planilla',
            name='anio',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='planilla',
            name='bono_te',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_aprobacion',
            field=models.DateField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_baja',
            field=models.DateField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_elaboracion',
             field=models.DateField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_fin',
            field=models.DateField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_inicio',
            field=models.DateField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name='planilla',
            name='fecha_revision',
            field=models.DateField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name='planilla',
            name='importe_diario',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='impositiva',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='planilla',
            name='mes',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='planilla',
            name='smn',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='tipo',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='total_dias',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='ufvf',
            field=models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='ufvi',
            field=models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name='planilla',
            name='usuario_aprobacion',
             field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='planillas_aprobadas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='planilla',
             field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='planillas_elaboradas', to=settings.AUTH_USER_MODEL),
            name='usuario_elaboracion',
        ),
        migrations.AddField(
            model_name='planilla',
             field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='planillas_revisadas', to=settings.AUTH_USER_MODEL),
            name='usuario_revision',
        ),
        migrations.AlterField(
            model_name='planilla',
            name='estado',
            field=models.CharField(choices=[('pendiente', 'Pendiente'), ('aprobado', 'Aprobado'), ('rechazado', 'Rechazado')], default='pendiente', max_length=10),
        ),
        migrations.CreateModel(
            name='DetalleSueldo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nitem', models.CharField(blank=True, max_length=50, null=True, verbose_name='NITEM')),
                ('cargo', models.CharField(blank=True, max_length=150, null=True, verbose_name='Cargo')),
                ('fecha_ingreso', models.DateField(blank=True, null=True, verbose_name='Fecha de Ingreso')),
                ('dias_trabajados', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Días Trabajados')),
                ('haber_basico', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Haber Básico')),
                ('categoria', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Categoría')),
                ('lac_pre_natal', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Lactancia Prenatal')),
                ('afp', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='AFP')),
                ('rc_iva', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='RC-IVA')),
                ('cooperativa', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Cooperativa')),
                ('faltas', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Faltas')),
                ('memos', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Memos')),
                ('otros_descuentos', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Otros Descuentos')),
                ('tipo_seguro', models.CharField(blank=True, choices=[('salud', 'Salud'), ('riesgo', 'Riesgo'), ('otro', 'Otro')], max_length=40, null=True, verbose_name='Tipo de Seguro')),
                ('fecha_inicio', models.DateField(blank=True, null=True, verbose_name='Fecha de Inicio')),
                ('fecha_fin', models.DateField(blank=True, null=True, verbose_name='Fecha de Fin')),
                ('total_ganado', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Total Ganado')),
                ('total_descuentos', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Total Descuentos')),
                ('liquido_pagable', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Líquido Pagable')),
                ('haber_basico_base', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Haber Básico Base')),
                ('tipo_afp', models.CharField(blank=True, choices=[('futuro', 'Futuro'), ('prevision', 'Previsión')], max_length=10, null=True, verbose_name='Tipo de AFP')),
                ('modo_cancelacion', models.CharField(blank=True, choices=[('banco', 'Banco'), ('efectivo', 'Efectivo')], max_length=20, null=True, verbose_name='Modo de Cancelación')),
                ('hospital', models.CharField(blank=True, max_length=10, null=True, verbose_name='Hospital')),
                ('bono_solidario', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Bono Solidario')),
                ('num_faltas', models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Número de Faltas')),
                ('num_sanciones', models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Número de Sanciones')),
                 ('id_planilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_sueldo', to='planilla.planilla', verbose_name='Planilla')),
                ('id_personal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_sueldo', to='planilla.personal', verbose_name='Personal')),
                ('id_unidad', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_sueldo', to='planilla.unidad', verbose_name='Unidad')),
            ],
            options={
                'db_table': 'detalle_sueldos',
            },
        ),
        migrations.CreateModel(
            name='DetalleImpositiva',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_ganado', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Total Ganado')),
                ('sueldo_neto', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Sueldo Neto')),
                ('f110', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='F110')),
                ('saldo_fisco', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Fisco')),
                ('saldo_dependiente', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Dependiente')),
                ('saldo_anterior', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Anterior')),
                ('saldo_total_dependiente', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Total Dependiente')),
                ('saldo_utilizado', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Utilizado')),
                ('impuesto_retenido', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Impuesto Retenido')),
                ('saldo_proximo_mes', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Saldo Próximo Mes')),
                 ('id_planilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_impositiva', to='planilla.planilla', verbose_name='Planilla')),
                ('id_sueldo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_impositiva', to='planilla.detallesueldo', verbose_name='Detalle de Sueldo')),
                ('id_personal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_impositiva', to='planilla.personal', verbose_name='Personal')),
                 ('id_unidad', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_impositiva', to='planilla.unidad', verbose_name='Unidad')),
            ],
            options={
                'db_table': 'detalle_impositiva',
            },
        ),
        migrations.CreateModel(
            name='DetalleBonoTe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nitem', models.CharField(blank=True, max_length=50, null=True, verbose_name='NITEM')),
                ('cargo', models.CharField(max_length=80, verbose_name='Cargo')),
                ('faltas', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Faltas')),
                ('pcgh', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='PCGH')),
                ('vacacion', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Vacación')),
                ('dias_comiciones', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Días Comisiones')),
                ('bajas_medicas', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Bajas Médicas')),
                ('dias_cancelados', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Días Cancelados')),
                ('rc_iva', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='RC-IVA')),
                ('otros_descuentos', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Otros Descuentos')),
                ('liquido_pagable', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Líquido Pagable')),
                ('dias_total', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Días Total')),
                 ('total_ganado', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Total Ganado')),
                ('total_descuentos', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Total Descuentos')),
                 ('id_planilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_bono_te', to='planilla.planilla', verbose_name='Planilla')),
                 ('id_sueldo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_bono_te', to='planilla.detallesueldo', verbose_name='Detalle de Sueldo')),
                ('id_personal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_bono_te', to='planilla.personal', verbose_name='Personal')),
                ('id_unidad', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_bono_te', to='planilla.unidad', verbose_name='Unidad')),
            ],
            options={
                'db_table': 'detalle_bono_te',
            },
        ),
    ]