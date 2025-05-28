import logging
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required

# O puedes crear tu propia función de verificación de decorador:
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin # Para vistas basadas en clases


from django.contrib import messages
from .forms import CustomUserCreationForm, UserProfileForm, CustomUserChangeForm, UserProfile # Importa el formulario que acabamos de crear
# No necesitamos importar User o Group aquí directamente si el form se encarga,
# pero a veces es útil para otras lógicas.

from .forms import CustomUserCreationForm, GroupForm, Permission # Añadir GroupForm
from django.contrib.auth.models import Group, User



logger = logging.getLogger(__name__)


# --- DEFINIR FUNCIONES DE TEST DE PERMISOS AQUÍ ARRIBA ---
def puede_crear_usuarios(user): # La que ya tenías
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name='Administradores').exists() # Ajusta el nombre del grupo

def puede_ver_lista_usuarios(user): # La que ya tenías
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name='Administradores').exists()

def puede_ver_detalle_usuario(viewer_user, target_user): # Modificado para tomar el objeto target_user
    if not viewer_user.is_authenticated:
        return False
    if viewer_user.is_superuser or viewer_user.groups.filter(name='Administradores').exists():
        return True
    # if viewer_user.id == target_user.id: # Si un usuario puede ver su propio detalle
    #     return True
    return False

def puede_editar_usuario(editor, usuario_a_editar):
    if not editor.is_authenticated: return False
    if editor.is_superuser: return True # Superadmin puede editar a cualquiera
    # Admin puede editar a otros si no son superusuarios
    if editor.groups.filter(name='Administradores').exists() and not usuario_a_editar.is_superuser:
        return True
    # Un usuario podría editar su propio perfil/datos básicos (lógica diferente, no aquí)
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

def puede_gestionar_grupos(user): # La que ya tenías
    return user.is_superuser # Ejemplo: Solo superusuarios gestionan grupos

# --- FIN FUNCIONES DE TEST DE PERMISOS ---


# --- Función de Test para Decorador o Mixin (Ejemplo) ---
# Determina quién puede acceder a la creación de usuarios.
# Solo Superusuarios y miembros del grupo "Administradores".



@login_required # Asegurar que el usuario esté logueado
# @permission_required('auth.add_user', login_url='tu_url_de_login_o_error') # Opción 1: Basado en permiso Django
# Si usas la función de test personalizada:
@permission_required('auth.add_user', raise_exception=True)
def crear_usuario_view(request): # Renombré a crear_usuario_view para evitar posible conflicto con un modelo llamado 'crear_usuario'
    # --- Protección de la Vista ---
    

    if request.method == 'POST':
        # Si el método es POST, se están enviando datos del formulario.
        # request.FILES es necesario para manejar la subida de archivos (foto).
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # El método save() de nuestro CustomUserCreationForm ya maneja:
                # 1. Creación del User de Django.
                # 2. Disparo de la señal para crear el UserProfile.
                # 3. Poblado del UserProfile con CI, teléfono, foto.
                # 4. Asignación del User al Grupo (Rol) seleccionado.
                nuevo_usuario = form.save() 
                
                # Mensaje de éxito
                rol_asignado = form.cleaned_data.get('rol')
                messages.success(request, f"¡Usuario '{nuevo_usuario.username}' creado exitosamente y asignado al rol '{rol_asignado.name if rol_asignado else 'N/A'}'!")
                
                # Redirigir a la lista de usuarios (necesitaremos crear esta URL y vista más tarde)
                # Reemplaza 'administracion:lista_usuarios' con el nombre real de tu URL
                return redirect('lista_usuarios') 
            except Exception as e:
                # Capturar cualquier error inesperado durante el save (aunque el form debería manejar la mayoría)
                messages.error(request, f"Ocurrió un error inesperado al crear el usuario: {e}")
                logger.error(f"Error inesperado en crear_usuario_view al guardar: {e}", exc_info=True) # Usar logger
        # else: Si el form no es válido, Django automáticamente pasa el 'form' con errores
        #       a la plantilla cuando se re-renderiza abajo. No es necesario messages.error aquí
        #       porque los errores se mostrarán junto a los campos del formulario.
        #       logger.warning(f"Formulario CustomUserCreationForm inválido: {form.errors.as_json()}")
            
    else: # Método GET (o cualquier otro)
        # Si es una petición GET, se muestra un formulario vacío.
        form = CustomUserCreationForm()

    context = {
        'form': form,
        'titulo_vista': "Registrar Nuevo Usuario del Sistema"
    }
    return render(request, 'administracion/crear_usuario.html', context)



@login_required
@permission_required('auth.view_user', raise_exception=True)
def lista_usuarios_view(request):
    

    # Obtener todos los usuarios. Podrías querer excluir al superusuario de la lista editable,
    # o filtrarlos de alguna manera.
    # Usamos select_related('profile') para obtener el perfil en la misma consulta y evitar N+1.
    # Usamos prefetch_related('groups') para obtener los grupos eficientemente.
    usuarios = User.objects.all().select_related('profile').prefetch_related('groups').order_by('username')
    # O si no quieres mostrar superusuarios en esta lista para administradores normales:
    # if not request.user.is_superuser:
    #     usuarios = usuarios.filter(is_superuser=False)
        
    context = {
        'usuarios': usuarios,
        'titulo_vista': "Gestión de Usuarios del Sistema"
    }
    return render(request, 'administracion/lista_usuarios.html', context)



@login_required
@permission_required('auth.change_user', raise_exception=True)
def editar_usuario_view(request, user_id):
    usuario_a_editar = get_object_or_404(User, pk=user_id)
    
    # Obtener o crear el perfil (por si acaso no se creó con la señal para usuarios muy antiguos)
    user_profile, created = UserProfile.objects.get_or_create(user=usuario_a_editar)

    if not puede_editar_usuario(request.user, usuario_a_editar):
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios') # Sin namespace

    if request.method == 'POST':
        # Pasar 'instance' a ambos formularios
        user_form = CustomUserChangeForm(request.POST, instance=usuario_a_editar)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=user_profile)

        print(f"POST data para user_form: {request.POST}") # DEBUG
        print(f"FILES data para profile_form: {request.FILES}") # DEBUG
        
        if user_form.is_valid() and profile_form.is_valid():
            try:
                with transaction.atomic():
                    edited_user = user_form.save(commit=False)
                    # Username no se guarda desde aquí si es readonly en el form
                    edited_user.email = user_form.cleaned_data['email']
                    edited_user.first_name = user_form.cleaned_data['first_name']
                    edited_user.last_name = user_form.cleaned_data['last_name']
                    edited_user.is_active = user_form.cleaned_data['is_active']
                    # edited_user.is_staff = user_form.cleaned_data.get('is_staff', False)
                    edited_user.save()

                    profile_form.save() # Guarda los cambios del UserProfile

                    # Actualizar el grupo/rol
                    rol_seleccionado = user_form.cleaned_data.get('rol')
                    if rol_seleccionado:
                        edited_user.groups.clear() # Quitar todos los grupos
                        edited_user.groups.add(rol_seleccionado) # Añadir el nuevo rol principal
                
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
            
    else: # GET
        # Al cargar el form, obtener el grupo actual del usuario para preseleccionar 'rol'
        current_group = usuario_a_editar.groups.first() # Asume un usuario tiene un rol principal
        user_form = CustomUserChangeForm(instance=usuario_a_editar, initial={'rol': current_group})
        profile_form = UserProfileForm(instance=user_profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'usuario_editado': usuario_a_editar, # Para mostrar info en el template
        'titulo_vista': f"Editar Usuario: {usuario_a_editar.username}"
    }
    return render(request, 'administracion/editar_usuario.html', context)




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
            usuario_a_eliminar.delete() # Esto también borrará el UserProfile (CASCADE)
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


@login_required
@permission_required('auth.change_user', raise_exception=True)
def activar_usuario_view(request, user_id):
    if not puede_editar_usuario(request.user, get_object_or_404(User, pk=user_id)): # Reutiliza tu lógica de permisos
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios')

    usuario_a_modificar = get_object_or_404(User, pk=user_id)
    if request.method == 'POST': # Usar POST para cambios de estado
        usuario_a_modificar.is_active = True
        usuario_a_modificar.save(update_fields=['is_active'])
        messages.success(request, f"Usuario '{usuario_a_modificar.username}' ha sido activado.")
    else: # GET no debería cambiar estado, pero podrías mostrar una confirmación si quieres.
        messages.warning(request, "Acción no permitida por GET.")
    return redirect('lista_usuarios')

@login_required
@permission_required('auth.change_user', raise_exception=True)
def desactivar_usuario_view(request, user_id):
    if not puede_editar_usuario(request.user, get_object_or_404(User, pk=user_id)):
        messages.error(request, "Acceso denegado.")
        return redirect('lista_usuarios')
    
    usuario_a_modificar = get_object_or_404(User, pk=user_id)

    # No permitir que un usuario se desactive a sí mismo
    if request.user.id == usuario_a_modificar.id:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect('lista_usuarios')
    
    # No permitir desactivar a otros superusuarios si no eres superusuario
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



@login_required
@permission_required('auth.view_user', raise_exception=True)
def ver_detalle_usuario_view(request, user_id):
    usuario_a_ver = get_object_or_404(User, pk=user_id)

    if not puede_ver_detalle_usuario(request.user, usuario_a_ver.id):
        messages.error(request, "Acceso denegado. No tiene permiso para ver los detalles de este usuario.")
        return redirect('lista_usuarios') # O tu dashboard/home

    # Obtener el perfil asociado. get_or_create es útil por si algún usuario antiguo no lo tuviera.
    user_profile, created = UserProfile.objects.get_or_create(user=usuario_a_ver)
    if created:
        # Opcional: loggear o notificar si se tuvo que crear un perfil sobre la marcha
        logger.info(f"Se creó un UserProfile para {usuario_a_ver.username} al intentar ver sus detalles.")

    # Obtener los grupos/roles del usuario
    grupos_del_usuario = usuario_a_ver.groups.all()
    permiso_para_editar = puede_editar_usuario(request.user, usuario_a_ver)
    permiso_para_eliminar = puede_eliminar_usuario(request.user, usuario_a_ver)

    context = {
        'usuario_detalle': usuario_a_ver,
        'perfil_detalle': user_profile,
        'grupos_del_usuario': grupos_del_usuario,
        'titulo_vista': f"Detalles del Usuario: {usuario_a_ver.username}",
        'puede_editar_este_usuario': permiso_para_editar,
        'puede_eliminar_este_usuario': permiso_para_eliminar,
    }
    return render(request, 'administracion/ver_detalle_usuario.html', context)


# --- EJEMPLO DE CÓMO USAR UserPassesTestMixin CON VISTAS BASADAS EN CLASES (OPCIONAL) ---
# class CrearUsuarioView(LoginRequiredMixin, UserPassesTestMixin, View):
#     template_name = 'administracion/crear_usuario.html'
#     form_class = CustomUserCreationForm
#     titulo_vista = "Registrar Nuevo Usuario del Sistema (VBC)"

#     def test_func(self):
#         # La misma lógica de 'puede_crear_usuarios'
#         return self.request.user.is_superuser or self.request.user.groups.filter(name='Administradores').exists()

#     def handle_no_permission(self):
#         messages.error(self.request, "Acceso denegado. No tiene permiso para crear usuarios.")
#         return redirect('nombre_url_dashboard_o_home')

#     def get(self, request, *args, **kwargs):
#         form = self.form_class()
#         context = {'form': form, 'titulo_vista': self.titulo_vista}
#         return render(request, self.template_name, context)

#     def post(self, request, *args, **kwargs):
#         form = self.form_class(request.POST, request.FILES)
#         if form.is_valid():
#             try:
#                 nuevo_usuario = form.save()
#                 rol_asignado = form.cleaned_data.get('rol')
#                 messages.success(request, f"¡Usuario '{nuevo_usuario.username}' creado y asignado a '{rol_asignado.name if rol_asignado else 'N/A'}'!")
#                 return redirect('administracion:lista_usuarios')
#             except Exception as e:
#                 messages.error(request, f"Error al crear usuario: {e}")
#         # Si el form no es válido, se re-renderiza con errores
#         context = {'form': form, 'titulo_vista': self.titulo_vista}
#         return render(request, self.template_name, context)
# --- FIN EJEMPLO VBC ---





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
                grupo = form.save() # ModelForm.save() maneja la asignación de permisos
                messages.success(request, f"Grupo '{grupo.name}' creado exitosamente.")
                return redirect('lista_grupos') # Asume namespace y nombre de URL
            except Exception as e:
                messages.error(request, f"Error al crear el grupo: {e}")
    else: # GET
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
    return render(request, 'administracion/form_grupo.html', context) # Usaremos un template genérico

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
    else: # GET
        form = GroupForm(instance=grupo)
    
    todos_los_permisos = Permission.objects.all().select_related('content_type').order_by(
        'content_type__app_label', 
        'content_type__model',
        'name'
        
    )

    context = {
        'form': form,
        'grupo': grupo, # Para mostrar info del grupo que se edita
        'titulo_vista': f"Editar Grupo (Rol): {grupo.name}",
        'todos_los_permisos_para_template': todos_los_permisos,
    }
    return render(request, 'administracion/form_grupo.html', context) # Reutilizar template

@login_required
@permission_required('auth.delete_group', raise_exception=True)
def eliminar_grupo_view(request, group_id):
    

    grupo = get_object_or_404(Group, pk=group_id)

    # Verificar si el grupo tiene usuarios antes de permitir el borrado (opcional pero recomendado)
    usuarios_en_el_grupo = grupo.user_set.count() # user_set es el related_name por defecto de User a Group

    if request.method == 'POST':
        # Si el usuario confirma la eliminación (enviando el formulario POST)
        try:
            nombre_grupo_eliminado = grupo.name
            grupo.delete()
            messages.success(request, f"El grupo '{nombre_grupo_eliminado}' ha sido eliminado exitosamente.")
            return redirect('lista_grupos') # Redirigir a la lista de grupos (sin namespace)
        except Exception as e:
            messages.error(request, f"Ocurrió un error al intentar eliminar el grupo '{grupo.name}': {e}")
            # Redirigir de vuelta a la lista o a la misma página de confirmación con el error
            return redirect('lista_grupos') 

    # Si es una petición GET, mostrar la página de confirmación
    context = {
        'grupo': grupo,
        'usuarios_en_el_grupo': usuarios_en_el_grupo, # Para mostrar en el template si hay usuarios
        'titulo_vista': f"Confirmar Eliminación del Grupo: {grupo.name}"
    }
    return render(request, 'administracion/confirmar_eliminar_grupo.html', context)