# sueldos/urls.py

from django.urls import path
from . import views # Importar las vistas de la app sueldos

# Este nombre es opcional pero recomendado para usar con {% url 'sueldos:nombre_ruta' %}


urlpatterns = [
    # --- URLs para PlanillaSueldo (Cabecera) ---
    path('crear/', views.crear_planilla_sueldo, name='crear_planilla_sueldo'),
    path('lista/', views.lista_planillas_sueldo, name='lista_planillas_sueldo'),

    path('<int:planilla_id>/editar/', views.editar_planilla_sueldo, name='editar_planilla_sueldo'), 
    path('<int:planilla_id>/borrar/', views.borrar_planilla_sueldo, name='borrar_planilla_sueldo'), 

    # --- URL para la Vista de Carga de Excel ---
    # Recibe el ID de la planilla a la que se cargará el excel
    path('<int:planilla_id>/subir_excel/', views.subir_excel_sueldos, name='subir_excel_sueldos'),
    path('<int:planilla_id>/detalles/', views.ver_detalles_sueldo, name='ver_detalles_sueldo'),
    path('detalle/<int:detalle_id>/editar/', views.editar_detalle_sueldo, name='editar_detalle_sueldo'), # <-- NUEVA
    path('detalle/<int:detalle_id>/borrar/', views.borrar_detalle_sueldo, name='borrar_detalle_sueldo'), # <-- NUEVA

    path('generar_estado/', views.generar_estado_mensual_form, name='generar_estado_mensual_form'),

    path('cierre/lista/', views.lista_cierres_mensuales, name='lista_cierres_mensuales'), # <-- NUEVA
    path('cierre/<int:cierre_id>/detalles/', views.ver_detalle_cierre, name='ver_detalle_cierre'), # <-- NUEVA
    path('cierre/<int:cierre_id>/borrar/', views.borrar_cierre_mensual, name='borrar_cierre_mensual'),

    #path('estado/lista/', views.lista_estado_mensual, name='lista_estado_mensual'), # <-- NUEVA URL para listar
    #path('estado/<int:estado_id>/borrar/', views.borrar_estado_mensual, name='borrar_estado_mensual'), # <-- NUEVA URL para borrar
    #path('estado/lista/', views.lista_estado_mensual_simple, name='lista_estado_mensual'),

    
]