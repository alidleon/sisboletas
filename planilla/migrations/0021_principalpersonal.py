# Generated by Django 5.1.4 on 2025-04-04 04:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planilla', '0020_planilla_dias_habiles'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrincipalPersonal',
            fields=[
                ('id', models.AutoField(db_column='id', primary_key=True, serialize=False)),
                ('nombre', models.CharField(blank=True, db_column='Nombre', max_length=150, null=True)),
                ('apellido_paterno', models.CharField(blank=True, db_column='A_Paterno', max_length=100, null=True)),
                ('apellido_materno', models.CharField(blank=True, db_column='A_Materno', max_length=100, null=True)),
                ('ci', models.CharField(blank=True, db_column='CI', max_length=20, null=True, unique=True)),
                ('fecha_nacimiento', models.DateField(blank=True, db_column='Fecha_nac', null=True)),
            ],
            options={
                'db_table': 'principal_personal',
                'managed': False,
            },
        ),
    ]
