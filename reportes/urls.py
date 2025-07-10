from django.urls import path
from . import views

urlpatterns = [

    path('asistencia/crear/', views.crear_planilla_asistencia, name='crear_planilla_asistencia'),
    path('asistencia/lista/', views.lista_planillas_asistencia, name='lista_planillas_asistencia'),
    path('asistencia/editar/<int:pk>/', views.editar_planilla_asistencia, name='editar_planilla_asistencia'),
    path('asistencia/borrar/<int:pk>/', views.borrar_planilla_asistencia, name='borrar_planilla_asistencia'),
    path('asistencia/detalles/<int:pk>/', views.ver_detalles_asistencia, name='ver_detalles_asistencia'),
    path('asistencia/<int:planilla_asistencia_id>/detalle/add/', views.add_detalle_asistencia, name='add_detalle_asistencia'),
    path('asistencia/exportar/pdf/<int:pk>/', views.exportar_planilla_asistencia_pdf, name='exportar_planilla_asistencia_pdf'),
    path('asistencia/detalles/exportar/pdf/<int:pk>/', views.exportar_detalles_filtrados_pdf, name='exportar_detalles_filtrados_pdf'),
    path('asistencia/detalle/editar/<int:detalle_id>/', views.editar_detalle_asistencia, name='editar_detalle_asistencia'),
    path('asistencia/detalle/json/<int:detalle_id>/', views.get_detalle_asistencia_json, name='get_detalle_asistencia_json'),
    path('asistencia/detalle/borrar/<int:detalle_id>/', views.borrar_detalle_asistencia, name='borrar_detalle_asistencia'),
]