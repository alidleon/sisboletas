from django.urls import path
from . import views 

urlpatterns = [
    path('crear/', views.crear_planilla_sueldo, name='crear_planilla_sueldo'),
    path('lista/', views.lista_planillas_sueldo, name='lista_planillas_sueldo'),
    path('<int:planilla_id>/editar/', views.editar_planilla_sueldo, name='editar_planilla_sueldo'), 
    path('<int:planilla_id>/borrar/', views.borrar_planilla_sueldo, name='borrar_planilla_sueldo'), 
    path('<int:planilla_id>/subir_excel/', views.subir_excel_sueldos, name='subir_excel_sueldos'),
    path('<int:planilla_id>/detalles/', views.ver_detalles_sueldo, name='ver_detalles_sueldo'),
    path('detalle/<int:detalle_id>/editar/', views.editar_detalle_sueldo, name='editar_detalle_sueldo'), 
    path('detalle/<int:detalle_id>/borrar/', views.borrar_detalle_sueldo, name='borrar_detalle_sueldo'), 
    path('generar_estado/', views.generar_estado_mensual_form, name='generar_estado_mensual_form'),
    path('cierre/lista/', views.lista_cierres_mensuales, name='lista_cierres_mensuales'), 
    path('cierre/<int:cierre_id>/detalles/', views.ver_detalle_cierre, name='ver_detalle_cierre'), 
    path('cierre/<int:cierre_id>/borrar/', views.borrar_cierre_mensual, name='borrar_cierre_mensual'),
    
]