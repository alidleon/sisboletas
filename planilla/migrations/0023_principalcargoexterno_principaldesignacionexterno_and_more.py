# Generated by Django 5.1.4 on 2025-04-07 14:02

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0022_remove_detalleimpositiva_id_personal_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrincipalCargoExterno',
            fields=[
                ('id', models.AutoField(db_column='id', primary_key=True, serialize=False)),
                ('nombre_cargo', models.CharField(blank=True, db_column='Nombre_cargo', max_length=80, null=True)),
            ],
            options={
                'db_table': 'principal_cargo',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PrincipalDesignacionExterno',
            fields=[
                ('id', models.AutoField(db_column='id', primary_key=True, serialize=False)),
                ('item', models.IntegerField(blank=True, db_column='Item', null=True)),
            ],
            options={
                'db_table': 'principal_designacion',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PrincipalPersonalExterno',
            fields=[
                ('id', models.AutoField(db_column='id', primary_key=True, serialize=False)),
                ('nombre', models.CharField(blank=True, db_column='Nombre', max_length=50, null=True)),
                ('apellido_paterno', models.CharField(blank=True, db_column='A_Paterno', max_length=50, null=True)),
                ('apellido_materno', models.CharField(blank=True, db_column='A_Materno', max_length=50, null=True)),
                ('ci', models.CharField(blank=True, db_column='CI', max_length=10, null=True, unique=True)),
            ],
            options={
                'db_table': 'principal_personal',
                'managed': False,
            },
        ),
        migrations.AlterModelOptions(
            name='detallebonote',
            options={'verbose_name': 'Detalle de Bono TE', 'verbose_name_plural': 'Detalles de Bono TE'},
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='dias_habiles',
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='dias_total_trab',
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='fecha_fin',
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='fecha_inicio',
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='asuetos',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Asuetos (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='bajas_medicas',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Bajas Médicas (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='descuentos',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Otros Descuentos al Bono'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='dias_no_pagados',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Días No Pagados (Calculado)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='dias_pagados',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Días Pagados (Calculado)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='faltas',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Faltas (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='id_planilla',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='detalles_bono_te', to='planilla.planilla', verbose_name='Planilla'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='id_sueldo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='planilla.detallesueldo', verbose_name='Detalle de Sueldo Asociado (Opcional)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='liquido_pagable',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Líquido Pagable Bono (Calculado)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='mes',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Mes (Heredado)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='otros_descuentos',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Otros Descuentos (Duplicado?)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='pcgh',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='PCGH (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='pcgh_embar_enf_base',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='PCGH Emb/Enf Base (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='perm_excep',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Perm. Excep. (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='psgh',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='PSGH (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='rc_iva',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='RC-IVA (¿Aplica al bono?)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='total_ganado',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Total Ganado Bono (Calculado)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='vacacion',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Vacación (días)'),
        ),
        migrations.AlterField(
            model_name='detallebonote',
            name='viajes',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Viajes (días)'),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='dias_habiles',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Días Hábiles del Mes'),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='tipo',
            field=models.CharField(blank=True, choices=[('planta', 'Planta'), ('contrato', 'Contrato'), ('consultor', 'Consultor'), ('bono_te', 'Bono TE')], max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='detallebonote',
            name='personal_externo',
            field=models.ForeignKey(db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='detalles_bono_te', to='planilla.principalpersonalexterno', verbose_name='Personal Externo'),
        ),
    ]
