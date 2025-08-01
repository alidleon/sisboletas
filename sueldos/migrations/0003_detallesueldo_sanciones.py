# Generated by Django 5.1.4 on 2025-06-07 18:49

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sueldos', '0002_alter_estadomensualempleado_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='detallesueldo',
            name='sanciones',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Monto de descuento por sanciones (típico de planillas de contrato)', max_digits=10, verbose_name='Sanciones'),
        ),
    ]
