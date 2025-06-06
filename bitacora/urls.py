# sisboletas/bitacora/urls.py
from django.urls import path
from . import views



urlpatterns = [
    path('registros/', views.lista_registros_log_view, name='lista_registros_log'),
    # Si decides añadir una vista de detalle más adelante:
    path('registros/<int:log_id>/', views.detalle_registro_log_view, name='detalle_registro_log'),
]