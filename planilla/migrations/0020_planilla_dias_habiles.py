# Generated by Django 5.1.4 on 2025-03-28 15:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0019_alter_detallebonote_asuetos_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='planilla',
            name='dias_habiles',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Días Hábiles'),
        ),
    ]
