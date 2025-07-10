from django.urls import path
from . import views



urlpatterns = [
    path('registros/', views.lista_registros_log_view, name='lista_registros_log'),
    path('registros/<int:log_id>/', views.detalle_registro_log_view, name='detalle_registro_log'),
]