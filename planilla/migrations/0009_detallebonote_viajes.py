# Generated by Django 5.1.4 on 2025-02-06 02:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0008_remove_detallebonote_viajes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='detallebonote',
            name='viajes',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Viajes'),
        ),
    ]
