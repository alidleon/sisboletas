# Generated by Django 5.1.4 on 2025-05-30 03:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0002_planilla_planilla_asistencia_base'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='detallebonote',
            name='abandono_dias',
        ),
    ]
