from django.urls import path
from . import views

urlpatterns = [
    path('seleccionar_tipo/', views.seleccionar_tipo_planilla, name='seleccionar_tipo_planilla'),
    path('crear/<str:tipo>/', views.crear_planilla, name='crear_planilla'),
    path('lista/', views.lista_planillas, name='lista_planillas'),
    path('editar/<int:planilla_id>/', views.editar_planilla, name='editar_planilla'),  # Nueva URL para editar
    path('borrar/<int:planilla_id>/', views.borrar_planilla, name='borrar_planilla'),  # Nueva URL para borrar
    path('lista_bono_te/', views.lista_bono_te, name='lista_bono_te'), # Nueva URL para listar DetalleBonoTe
    path('editar_bono_te/<int:detalle_id>/', views.editar_bono_te, name='editar_bono_te'), # Nueva URL para editar
    path('borrar_bono_te/<int:detalle_id>/', views.borrar_bono_te, name='borrar_bono_te'), # Nueva URL para borrar
    path('ver_detalles_bono_te/<int:planilla_id>/', views.ver_detalles_bono_te, name='ver_detalles_bono_te'),
    path('personal_externo/', views.listar_personal_externo, name='listar_personal_externo'),
    path('probar_consulta_externa/<str:tipo_planilla>/', views.probar_consulta_designaciones, name='probar_consulta_designaciones'),

]




