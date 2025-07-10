from django.urls import path
from . import views

urlpatterns = [
    path('usuarios/crear/', views.crear_usuario_view, name='crear_usuario'),
    path('usuarios/', views.lista_usuarios_view, name='lista_usuarios'),
    path('usuarios/editar/<int:user_id>/', views.editar_usuario_view, name='editar_usuario'),
    path('usuarios/eliminar/<int:user_id>/', views.eliminar_usuario_view, name='eliminar_usuario'),
    path('usuarios/activar/<int:user_id>/', views.activar_usuario_view, name='activar_usuario'),
    path('usuarios/desactivar/<int:user_id>/', views.desactivar_usuario_view, name='desactivar_usuario'),
    path('usuarios/ver/<int:user_id>/', views.ver_detalle_usuario_view, name='ver_detalle_usuario'),    
    path('grupos/', views.lista_grupos_view, name='lista_grupos'),
    path('grupos/crear/', views.crear_grupo_view, name='crear_grupo'),
    path('grupos/editar/<int:group_id>/', views.editar_grupo_view, name='editar_grupo'),
    path('grupos/eliminar/<int:group_id>/', views.eliminar_grupo_view, name='eliminar_grupo'),
    path('perfil/', views.ver_perfil_propio, name='ver_perfil_propio'),
]