from django.urls import path
from . import views

urlpatterns = [
    path('bono_te/crear/', views.crear_planilla_bono_te, name='crear_planilla_bono_te'),
    path('lista/', views.lista_planillas, name='lista_planillas'),
    path('editar/<int:planilla_id>/', views.editar_planilla, name='editar_planilla'),  
    path('borrar/<int:planilla_id>/', views.borrar_planilla, name='borrar_planilla'), 
    path('lista_bono_te/', views.lista_bono_te, name='lista_bono_te'),
    path('editar_bono_te/<int:detalle_id>/', views.editar_bono_te, name='editar_bono_te'), 
    path('borrar_bono_te/<int:detalle_id>/', views.borrar_bono_te, name='borrar_bono_te'),
    path('ver_detalles_bono_te/<int:planilla_id>/', views.ver_detalles_bono_te, name='ver_detalles_bono_te'),
    path('exportar_xlsx/<int:planilla_id>/', views.exportar_planilla_xlsx, name='exportar_planilla_xlsx'),
    path('exportar/detalles-bonote/pdf/<int:planilla_id>/', views.export_detalles_bonote_pdf, name='export_detalles_bonote_pdf'),
     path('exportar/lista-planillas/pdf/', views.export_lista_planillas_pdf, name='export_lista_planillas_pdf'),
]



