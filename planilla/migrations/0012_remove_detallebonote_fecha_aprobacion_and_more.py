# Generated by Django 5.1.4 on 2025-02-17 14:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0011_remove_detallebonote_tipo_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='detallebonote',
            name='fecha_aprobacion',
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='fecha_elaboracion',
        ),
        migrations.RemoveField(
            model_name='detallebonote',
            name='fecha_revision',
        ),
    ]
