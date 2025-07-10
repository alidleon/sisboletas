from django.urls import path
from . import views



urlpatterns = [
    path('plantillas/', views.lista_plantillas_boleta, name='lista_plantillas_boleta'),
    path('plantillas/crear/', views.crear_editar_plantilla_boleta, name='crear_plantilla_boleta'),
    path('plantillas/<int:plantilla_id>/editar/', views.crear_editar_plantilla_boleta, name='editar_plantilla_boleta'),
    path('plantillas/<int:plantilla_id>/eliminar/', views.eliminar_plantilla_boleta, name='eliminar_plantilla_boleta'),
    path('plantillas/preview/', views.preview_boleta_view, name='preview_plantilla_boleta'),
    path('plantillas/<int:plantilla_id>/obtener-diseno-json/', views.obtener_diseno_plantilla_json, name='obtener_diseno_plantilla_json'),
    path('generar-pdf/planilla-sueldo/<int:planilla_sueldo_id>/', views.generar_pdf_boletas_por_planilla, name='generar_pdf_boletas_por_planilla'),
    path('generar-boleta-individual/', views.vista_generar_boleta_individual_buscar, name='generar_boleta_individual_buscar'),
    path('generar-pdf/empleado/<int:personal_externo_id>/periodo/<int:anio>/<int:mes>/', views.vista_generar_pdf_boleta_unica, name='generar_pdf_boleta_unica'),
    
]

    