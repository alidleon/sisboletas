# Generated by Django 5.1.4 on 2025-04-10 03:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0024_alter_planilla_tipo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='planilla',
            name='bono_te',
        ),
        migrations.RemoveField(
            model_name='planilla',
            name='impositiva',
        ),
        migrations.AlterField(
            model_name='planilla',
            name='tipo',
            field=models.CharField(blank=True, choices=[('planta', 'Asegurado'), ('contrato', 'Contrato'), ('consultor', 'Consultor en Linea')], max_length=40, null=True),
        ),
    ]
