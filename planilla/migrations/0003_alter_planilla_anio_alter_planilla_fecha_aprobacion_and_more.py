# Generated by Django 5.1.4 on 2025-01-22 22:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0002_personal_unidad_remove_planilla_fecha_creacion_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planilla',
            name='anio',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='fecha_aprobacion',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='fecha_baja',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='fecha_fin',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='fecha_inicio',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='fecha_revision',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='mes',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='planilla',
            name='tipo',
            field=models.CharField(blank=True, choices=[('planta', 'Planta'), ('contrato', 'Contrato')], max_length=40, null=True),
        ),
    ]
