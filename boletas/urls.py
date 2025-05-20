from django.urls import path
from . import views



urlpatterns = [
    path('plantillas/', views.lista_plantillas_boleta, name='lista_plantillas_boleta'),
    path('plantillas/crear/', views.crear_editar_plantilla_boleta, name='crear_plantilla_boleta'),
    path('plantillas/<int:plantilla_id>/editar/', views.crear_editar_plantilla_boleta, name='editar_plantilla_boleta'),
    path('plantillas/<int:plantilla_id>/eliminar/', views.eliminar_plantilla_boleta, name='eliminar_plantilla_boleta'),
    path('plantillas/preview/', views.preview_boleta_view, name='preview_plantilla_boleta'), # NUEVA URL
    # API para guardar (aunque crear_editar_plantilla_boleta podría manejar POST para guardar también)
    # path('api/plantillas/guardar/', views.api_guardar_plantilla, name='api_guardar_plantilla'),

    path('generar-pdf/planilla-sueldo/<int:planilla_sueldo_id>/', views.generar_pdf_boletas_por_planilla, name='generar_pdf_boletas_por_planilla'),]