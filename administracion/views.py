import logging
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin # Para vistas basadas en clases


from django.contrib import messages
from .forms import CustomUserCreationForm, UserProfileForm, CustomUserChangeForm, UserProfile # Importa el formulario que acabamos de crear


from .forms import CustomUserCreationForm, GroupForm, Permission 
from django.contrib.auth.models import Group, User



logger = logging.getLogger(__name__)


# --- DEFINIR FUNCIONES DE TEST DE PERMISOS AQUÍ ARRIBA ---
def puede_crear_usuarios(user): 
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name='Administradores').exists() # Ajusta el nombre del grupo

def puede_ver_lista_usuarios(user): 
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name='Administradores').exists()

def puede_ver_detalle_usuario(viewer_user, target_user):
    # Condición 1: El usuario que mira debe estar autenticado.
    if not viewer_user.is_authenticated:
        return False
    
    # Condición 2: Si el usuario está viendo su propio perfil, siempre tiene permiso.
    if viewer_user.pk == target_user.pk:
        return True
    
    # Condición 3: Si el usuario es superusuario o del grupo Administradores, puede ver cualquier perfil.
    if viewer_user.is_superuser or viewer_user.groups.filter(name='Administradores').exists():
        return True
    
    # Si ninguna de las condiciones anteriores se cumple, se deniega el acceso.
    return False

def puede_editar_usuario(editor, usuario_a_editar):
    if not editor.is_authenticated: return False
    if editor.id == usuario_a_editar.id:
        return True
    if editor.is_superuser: return True 
    if editor.groups.filter(name='Administradores').exists() and not usuario_a_editar.is_superuser:
        return True
    return False

def puede_eliminar_usuario(editor, usuario_a_eliminar):
    if not editor.is_authenticated: return False
    # Nadie se elimina a sí mismo con este botón
    if editor.id == usuario_a_eliminar.id: return False 
    # Solo un superadmin puede eliminar a otro superadmin (o decidir que no se puede en absoluto)
    if usuario_a_eliminar.is_superuser and not editor.is_superuser: return False 
    if editor.is_superuser: return True # Superadmin puede eliminar (excepto a sí mismo)
    # Admin puede eliminar a otros si no son superusuarios
    if editor.groups.filter(name='Administradores').exists() and not usuario_a_eliminar.is_superuser:
        return True
    return False

def puede_gestionar_grupos(user): 
    return user.is_superuser 
#----------------------------------------------------
@login_required 
@permission_required('auth.add_user', raise_exception=True)
def crear_usuario_view(request): 
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                nuevo_usuario = form.save() 
                rol_asignado = form.cleaned_data.get('rol')
                messages.success(request, f"¡Usuario '{nuevo_usuario.username}' creado exitosamente y asignado al rol '{rol_asignado.name if rol_asignado else 'N/A'}'!")
                return redirect('lista_usuarios') 
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear el usuario: {e}")
                logger.error(f"Error inesperado en crear_usuario_view al guardar: {e}", exc_info=True)
    else: 
        form = CustomUserCreationForm()
    context = {
        'form': form,
        'titulo_vista': "Registrar Nuevo Usuario del Sistema"
    }
    return render(request, 'administracion/crear_usuario.html', context)
#---------------------------------------------
@login_required
@permission_required('auth.view_user', raise_exception=True)
def lista_usuarios_view(request):
    usuarios = User.objects.all().select_related('profile').prefetch_related('groups').order_by('username')  
    context = {
        'usuarios': usuarios,
        'titulo_vista': "Gestión de Usuarios del Sistema"
    }
    return render(request, 'administracion/lista_usuarios.html', context)
#------------------------------------------------
@login_required
@permission_required('auth.change_user', raise_exception=True)
def editar_usuario_view(request, user_id):
    usuario_a_editar = get_object_or_404(User, pk=user_id)
    user_profile, created = UserProfile.objects.get_or_create(user=usuario_a_editar)

    if not puede_editar_usuario(request.user, usuario_a_editar):
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios')

    if request.method == 'POST':
        user_form = CustomUserChangeForm(request.POST, instance=usuario_a_editar)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=user_profile)

        print(f"POST data para user_form: {request.POST}") # DEBUG
        print(f"FILES data para profile_form: {request.FILES}") # DEBUG
        
        if user_form.is_valid() and profile_form.is_valid():
            try:
                with transaction.atomic():
                    edited_user = user_form.save(commit=False)
                    edited_user.email = user_form.cleaned_data['email']
                    edited_user.first_name = user_form.cleaned_data['first_name']
                    edited_user.last_name = user_form.cleaned_data['last_name']
                    edited_user.is_active = user_form.cleaned_data['is_active']
                    edited_user.save()
                    profile_form.save() 
                    rol_seleccionado = user_form.cleaned_data.get('rol')
                    if rol_seleccionado:
                        edited_user.groups.clear()
                        edited_user.groups.add(rol_seleccionado)
                
                messages.success(request, f"Usuario '{edited_user.username}' actualizado exitosamente.")
                print(f"Redirigiendo a lista_usuarios para {edited_user.username}") # DEBUG
                return redirect('lista_usuarios')
            except Exception as e:
                messages.error(request, f"Error al actualizar el usuario: {e}")
                print(f"Excepción durante el guardado: {e}") # DEBUG
                logger.error(f"Error al actualizar usuario {usuario_a_editar.username}: {e}", exc_info=True)
        else:
            print("Formularios NO válidos.") # DEBUG
            if not user_form.is_valid():
                print(f"Errores en user_form: {user_form.errors.as_json()}") # DEBUG
            if not profile_form.is_valid():
                print(f"Errores en profile_form: {profile_form.errors.as_json()}") # DEBUG
            messages.error(request, "Por favor, corrija los errores en el formulario.")
            
    else:
        current_group = usuario_a_editar.groups.first()
        user_form = CustomUserChangeForm(instance=usuario_a_editar, initial={'rol': current_group})
        profile_form = UserProfileForm(instance=user_profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'usuario_editado': usuario_a_editar,
        'titulo_vista': f"Editar Usuario: {usuario_a_editar.username}"
    }
    return render(request, 'administracion/editar_usuario.html', context)


#-----------------------------------------------

@login_required
@permission_required('auth.delete_user', raise_exception=True)
def eliminar_usuario_view(request, user_id):
    usuario_a_eliminar = get_object_or_404(User, pk=user_id)

    if not puede_eliminar_usuario(request.user, usuario_a_eliminar):
        messages.error(request, "Acceso denegado o acción no permitida.")
        return redirect('lista_usuarios')

    if request.method == 'POST':
        try:
            username_eliminado = usuario_a_eliminar.username
            usuario_a_eliminar.delete()
            messages.success(request, f"Usuario '{username_eliminado}' eliminado exitosamente.")
            return redirect('lista_usuarios')
        except Exception as e:
            messages.error(request, f"Error al eliminar usuario: {e}")
            return redirect('lista_usuarios')
            
    context = {
        'usuario_a_eliminar': usuario_a_eliminar,
        'titulo_vista': f"Confirmar Eliminación: {usuario_a_eliminar.username}"
    }
    return render(request, 'administracion/confirmar_eliminar_usuario.html', context)

#------------------------------------------------
@login_required
@permission_required('auth.change_user', raise_exception=True)
def activar_usuario_view(request, user_id):
    if not puede_editar_usuario(request.user, get_object_or_404(User, pk=user_id)):
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios')

    usuario_a_modificar = get_object_or_404(User, pk=user_id)
    if request.method == 'POST': 
        usuario_a_modificar.is_active = True
        usuario_a_modificar.save(update_fields=['is_active'])
        messages.success(request, f"Usuario '{usuario_a_modificar.username}' ha sido activado.")
    else:
        messages.warning(request, "Acción no permitida por GET.")
    return redirect('lista_usuarios')

#--------------------------------------------------------------------
@login_required
@permission_required('auth.change_user', raise_exception=True)
def desactivar_usuario_view(request, user_id):
    if not puede_editar_usuario(request.user, get_object_or_404(User, pk=user_id)):
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios')
    
    usuario_a_modificar = get_object_or_404(User, pk=user_id)
    if request.user.id == usuario_a_modificar.id:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect('lista_usuarios')

    if usuario_a_modificar.is_superuser and not request.user.is_superuser:
        messages.error(request, "No puedes desactivar a un superusuario.")
        return redirect('lista_usuarios')

    if request.method == 'POST':
        usuario_a_modificar.is_active = False
        usuario_a_modificar.save(update_fields=['is_active'])
        messages.success(request, f"Usuario '{usuario_a_modificar.username}' ha sido desactivado (dado de baja).")
    else:
        messages.warning(request, "Acción no permitida por GET.")
    return redirect('lista_usuarios')


#--------------------------------------------
@login_required
def ver_detalle_usuario_view(request, user_id):
    usuario_a_ver = get_object_or_404(User, pk=user_id)

    # Llamamos a nuestra función de permisos mejorada
    if not puede_ver_detalle_usuario(request.user, usuario_a_ver):
        # Este mensaje es más específico
        messages.error(request, "No tiene permisos para ver los detalles de este usuario.")
        # Redirigir a la página de inicio es más amigable que a la lista de usuarios
        # para un usuario normal que no debería ver esa lista.
        return redirect('index')

    user_profile, created = UserProfile.objects.get_or_create(user=usuario_a_ver)
    if created:
        logger.info(f"Se creó un UserProfile para {usuario_a_ver.username} al intentar ver sus detalles.")

    grupos_del_usuario = usuario_a_ver.groups.all()
    permiso_para_editar = puede_editar_usuario(request.user, usuario_a_ver)
    permiso_para_eliminar = puede_eliminar_usuario(request.user, usuario_a_ver)
    es_perfil_propio = (request.user.id == usuario_a_ver.id)
    context = {
        'usuario_detalle': usuario_a_ver,
        'perfil_detalle': user_profile,
        'grupos_del_usuario': grupos_del_usuario,
        'titulo_vista': f"Detalles del Usuario: {usuario_a_ver.username}",
        'puede_editar_este_usuario': permiso_para_editar,
        'puede_eliminar_este_usuario': permiso_para_eliminar,
        'es_perfil_propio': es_perfil_propio, # <-- AÑADIMOS LA NUEVA VARIABLE
    }
    if es_perfil_propio:
        context['titulo_vista'] = "Mi Perfil"
    return render(request, 'administracion/ver_detalle_usuario.html', context)


#----------------------------------------------

@login_required
def ver_perfil_propio(request):
    """
    Muestra la página de perfil del usuario actualmente logueado.
    Esta vista simplemente redirige a la vista de detalle de usuario
    existente, pasándole el ID del usuario actual.
    """
    # Obtenemos el ID del usuario que ha iniciado sesión
    usuario_actual_id = request.user.id
    
    # Llamamos a la otra vista internamente y devolvemos su respuesta
    return ver_detalle_usuario_view(request, user_id=usuario_actual_id)

#-------------------------------------------------
@login_required
@permission_required('auth.view_group', raise_exception=True)
def lista_grupos_view(request):
    grupos = Group.objects.all().order_by('name')
    context = {
        'grupos': grupos,
        'titulo_vista': "Gestión de Grupos (Roles)"
    }
    return render(request, 'administracion/lista_grupos.html', context)
@login_required
@permission_required('auth.add_group', raise_exception=True)
def crear_grupo_view(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            try:
                grupo = form.save()
                messages.success(request, f"Grupo '{grupo.name}' creado exitosamente.")
                return redirect('lista_grupos')
            except Exception as e:
                messages.error(request, f"Error al crear el grupo: {e}")
    else:
        form = GroupForm()
    todos_los_permisos = Permission.objects.all().select_related('content_type').order_by(
        'content_type__app_label', 
        'content_type__model',
        'name'
    )
    context = {
        'form': form,
        'titulo_vista': "Crear Nuevo Grupo (Rol)",
        'todos_los_permisos_para_template': todos_los_permisos
    }
    return render(request, 'administracion/form_grupo.html', context)
@login_required
@permission_required('auth.change_group', raise_exception=True)
def editar_grupo_view(request, group_id):
    

    grupo = get_object_or_404(Group, pk=group_id)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=grupo)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Grupo '{grupo.name}' actualizado exitosamente.")
                return redirect('lista_grupos')
            except Exception as e:
                messages.error(request, f"Error al actualizar el grupo: {e}")
    else:
        form = GroupForm(instance=grupo)
    
    todos_los_permisos = Permission.objects.all().select_related('content_type').order_by(
        'content_type__app_label', 
        'content_type__model',
        'name'
        
    )

    context = {
        'form': form,
        'grupo': grupo,
        'titulo_vista': f"Editar Grupo (Rol): {grupo.name}",
        'todos_los_permisos_para_template': todos_los_permisos,
    }
    return render(request, 'administracion/form_grupo.html', context)
#-----------------------------------------------------------
@login_required
@permission_required('auth.delete_group', raise_exception=True)
def eliminar_grupo_view(request, group_id):
    grupo = get_object_or_404(Group, pk=group_id)
    usuarios_en_el_grupo = grupo.user_set.count()

    if request.method == 'POST':
        try:
            nombre_grupo_eliminado = grupo.name
            grupo.delete()
            messages.success(request, f"El grupo '{nombre_grupo_eliminado}' ha sido eliminado exitosamente.")
            return redirect('lista_grupos')
        except Exception as e:
            messages.error(request, f"Ocurrió un error al intentar eliminar el grupo '{grupo.name}': {e}")
            return redirect('lista_grupos') 

    context = {
        'grupo': grupo,
        'usuarios_en_el_grupo': usuarios_en_el_grupo,
        'titulo_vista': f"Confirmar Eliminación del Grupo: {grupo.name}"
    }
    return render(request, 'administracion/confirmar_eliminar_grupo.html', context)