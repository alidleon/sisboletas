from django.test import TestCase
from django.core.exceptions import ValidationError
from planilla.models import DetalleBonoTe, Planilla
from django.contrib.auth.models import User
from .forms import DetalleBonoTeForm


class DetalleBonoTeTests(TestCase):
    
    def setUp(self):
        # Crear un usuario y una planilla para usar en los tests
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.planilla = Planilla.objects.create(mes=1, anio=2024, usuario_elaboracion=self.user, tipo='planta', fecha_inicio='2024-01-01', fecha_fin='2024-01-31')


    def test_dias_no_pagados_mayor_que_dias_habiles(self):
        form_data = {'dias_habiles': 20, 'dias_no_pagados': 25, 'mes': 1,
                    'faltas': 0, 'vacacion': 0, 'viajes': 0, 'bajas_medicas': 0, 'pcgh': 0,
                    'psgh': 0, 'perm_excep': 0, 'asuetos': 0, 'pcgh_embar_enf_base': 0,
                    'descuentos': 0}
        print("Datos del formulario:", form_data)
        form = DetalleBonoTeForm(data=form_data)
        self.assertTrue(form.is_valid())

        # Crear el objeto DetalleBonoTe utilizando el formulario
        detalle = form.save(commit=False)  # No guardar en la base de datos todavía
        detalle.id_planilla = self.planilla  # ASIGNAR la planilla al detalle

        with self.assertRaises(ValidationError) as context:
            detalle.save()  # Guardar el objeto (debería fallar la validación)
        self.assertEqual(str(context.exception), "Los días no pagados no pueden ser mayores que los días hábiles.")
        
    def test_dias_no_pagados_menor_que_dias_habiles(self):
        form_data = {'dias_habiles': 20, 'dias_no_pagados': 15, 'mes': 1,
                     'faltas': 0, 'vacacion': 0, 'viajes': 0, 'bajas_medicas': 0, 'pcgh': 0,
                     'psgh': 0, 'perm_excep': 0, 'asuetos': 0, 'pcgh_embar_enf_base': 0,
                     'descuentos': 0}  # Agrega 'mes'
        # Imprimir los datos que se están pasando al formulario
        print("Datos del formulario:", form_data)
        form = DetalleBonoTeForm(data=form_data)
        self.assertTrue(form.is_valid())  # El formulario debe ser válido antes de guardar

        # Crear el objeto DetalleBonoTe utilizando el formulario
        detalle = form.save(commit=False)
        detalle.id_planilla = self.planilla
        # Llamar al método save() del formulario
        #form.save() # Eliminar la segunda llamada al método save()
        self.assertEqual(detalle.dias_habiles, 20)
        self.assertEqual(detalle.dias_no_pagados, 15)

    def test_dias_no_pagados_igual_que_dias_habiles(self):
        form_data = {'dias_habiles': 20, 'dias_no_pagados': 20, 'mes': 1,
                     'faltas': 0, 'vacacion': 0, 'viajes': 0, 'bajas_medicas': 0, 'pcgh': 0,
                     'psgh': 0, 'perm_excep': 0, 'asuetos': 0, 'pcgh_embar_enf_base': 0,
                     'descuentos': 0}  # Agrega 'mes'
        # Imprimir los datos que se están pasando al formulario
        print("Datos del formulario:", form_data)
        form = DetalleBonoTeForm(data=form_data)
        self.assertTrue(form.is_valid())  # El formulario debe ser válido antes de guardar

        # Crear el objeto DetalleBonoTe utilizando el formulario
        detalle = form.save(commit=False)
        detalle.id_planilla = self.planilla
        # Llamar al método save() del formulario
        #form.save() # Eliminar la segunda llamada al método save()
        self.assertEqual(detalle.dias_habiles, 20)
        self.assertEqual(detalle.dias_no_pagados, 20)