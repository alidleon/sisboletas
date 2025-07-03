from django.urls import path
from . import views

urlpatterns = [
    path('descargar/manual/', views.descargar_manual_pdf, name='descargar_manual_pdf'),
]