# administracion/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm # Heredaremos de este
from django.contrib.auth.models import User, Group, Permission
from .models import UserProfile # Importamos nuestro modelo de perfil
from django.core.validators import RegexValidator # Para validaciones con regex
import re # Módulo de expresiones regulares de Python
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _ 

class MinimumLengthValidator:
    def __init__(self, min_length=8):
        self.min_length = min_length

    def __call__(self, value):
        if len(value) < self.min_length:
            raise ValidationError(
                _("Su contraseña debe contener al menos %(min_length)d caracteres."),
                code='password_too_short',
                params={'min_length': self.min_length},
            )

    def get_help_text(self): # Para CustomUserCreationForm
        return _(
            "Su contraseña debe contener al menos %(min_length)d caracteres."
            % {'min_length': self.min_length}
        )
    
    def get_edit_help_text(self): # Para CustomUserChangeForm
        return _(
            "Su contraseña debe contener al menos %(min_length)d caracteres. "
            "Deje vacío si no desea cambiarla."
            % {'min_length': self.min_length}
        )


name_validator = RegexValidator(
    regex=r'^[a-zA-ZñÑáéíóúÁÉÍÓÚ\s\-]+$',
    message="Este campo solo puede contener letras, espacios y guiones."
)

# Validador para CI (exactamente 10 dígitos numéricos, por ejemplo)
# Si es MAX 10, sería r'^\d{1,10}$'
# Si es EXACTAMENTE 10, sería r'^\d{10}$' - ajusta según tu necesidad
# Asumiré MÁXIMO 10 dígitos por ahora, como lo indicaste
ci_validator = RegexValidator(
    regex=r'^\d{1,10}$', # Solo dígitos, de 1 a 10 caracteres
    message="La Cédula de Identidad debe contener solo números y tener máximo 10 dígitos."
)

# Validador para Teléfono (exactamente 10 dígitos numéricos, por ejemplo)
# Asumiré MÁXIMO 10 dígitos por ahora
phone_validator = RegexValidator(
    regex=r'^\d{1,10}$', # Solo dígitos, de 1 a 10 caracteres
    message="El teléfono debe contener solo números y tener máximo 10 dígitos."
)




class CustomUserCreationForm(UserCreationForm):
    
    # --- Campos del Modelo User que queremos en el formulario de creación ---
    # UserCreationForm por defecto solo tiene username, password1, password2.
    # Añadimos email, first_name, last_name.
    email = forms.EmailField(
        required=True, 
        help_text="Requerido. Se usará para notificaciones y posible recuperación de contraseña."
    )
    first_name = forms.CharField(
        max_length=150, 
        required=True, # Hacemos los nombres reales obligatorios
        label="Nombres Reales",
        validators=[name_validator]
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Apellidos Reales",
        validators=[name_validator] # Aplicamos el validador
    )

    # --- Campos del Modelo UserProfile ---
    ci = forms.CharField(
        max_length=10, # Actualizamos max_length
        required=True,
        label="Cédula de Identidad (CI)",
        validators=[ci_validator] # Aplicamos el validador
    )
    telefono = forms.CharField(
        max_length=10, # Actualizamos max_length
        required=False,
        label="Teléfono",
        validators=[phone_validator] # Aplicamos el validador (incluso si es opcional, si se llena debe ser válido)
    )
    foto = forms.ImageField(
        required=False, # Foto opcional
        label="Foto de Perfil"
    )

    # --- Campo para seleccionar el Rol/Grupo ---
    rol = forms.ModelChoiceField(
        queryset=Group.objects.all(), # Mostrar todos los grupos disponibles
        required=True,
        label="Rol del Usuario en el Sistema",
        empty_label=None, # Forzar una selección
        widget=forms.Select(attrs={'class': 'form-control'}) # Añadir clase para Bootstrap
    )
    password1 = forms.CharField(
        label=_("Contraseña"),
        widget=forms.PasswordInput,
        strip=False, # No eliminar espacios en blanco iniciales/finales de la contraseña
        help_text=MinimumLengthValidator().get_help_text(), # Usar el help_text de nuestro validador
    )
    password2 = forms.CharField(
        label=_("Confirmación de contraseña"),
        strip=False,
        widget=forms.PasswordInput,
        help_text=_("Introduzca la misma contraseña que antes, para su verificación."),
    )

    class Meta(UserCreationForm.Meta):
        model = User # Sigue siendo para el modelo User
        # Campos que UserCreationForm ya maneja: username, password1, password2
        # Añadimos los nuestros:
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name', 'ci', 'telefono', 'foto', 'rol')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].validators = [MinimumLengthValidator()]
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        # También para los campos que añades, si no usas un widget que ya la ponga:
        self.fields['email'].widget.attrs.update({'class': 'form-control'})
        self.fields['first_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['ci'].widget.attrs.update({'class': 'form-control'})
        self.fields['telefono'].widget.attrs.update({'class': 'form-control'})
        

    def clean_ci(self):
        ci_data = self.cleaned_data.get('ci')
        # La validación de formato (números, longitud) ya la hizo el RegexValidator
        # Ahora verificamos unicidad si el CI fue proporcionado y es válido hasta ahora
        if ci_data:
            # Comprobar si existe otro UserProfile con este CI
            # Excluimos el perfil del usuario actual si estamos editando (no aplica en CreationForm)
            if UserProfile.objects.filter(ci=ci_data).exists():
                raise forms.ValidationError("Esta Cédula de Identidad ya está registrada para otro usuario.")
        return ci_data

    def save(self, commit=True):
        # 1. Guardar el User (esto también disparará la señal para crear el UserProfile vacío)
        user = super().save(commit=False) # No guardar a la BD aún si commit=False

        # Poblar first_name y last_name del User desde los campos del form
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        # Podrías poner valores por defecto aquí para el User si es necesario:
        # user.is_staff = False # Por ejemplo
        user.is_active = True   # Por defecto, los usuarios se crean activos

        if commit:
            user.save() # Guardar el User a la BD. La señal crea el UserProfile.

            # 2. Poblar el UserProfile con los datos del formulario
            # El UserProfile ya debería existir gracias a la señal post_save.
            try:
                profile = user.profile # Acceder usando el related_name 'profile'
                profile.ci = self.cleaned_data["ci"]
                profile.telefono = self.cleaned_data["telefono"]
                profile.foto = self.cleaned_data["foto"] # Django maneja el guardado del archivo
                profile.save()
            except UserProfile.DoesNotExist:
                # Esto sería muy raro si la señal está funcionando, pero como respaldo:
                UserProfile.objects.create(
                    user=user,
                    ci=self.cleaned_data["ci"],
                    telefono=self.cleaned_data["telefono"],
                    foto=self.cleaned_data["foto"]
                )
            except Exception as e:
                # Manejar otros posibles errores al guardar el perfil
                print(f"Error al guardar el perfil para {user.username}: {e}") # Usar logging

            # 3. Asignar el Rol/Grupo
            rol_seleccionado = self.cleaned_data.get('rol')
            if rol_seleccionado:
                user.groups.clear() # Limpiar cualquier grupo previo (no debería haber en creación)
                user.groups.add(rol_seleccionado)
        
        return user

class CustomUserChangeForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True, label="Nombres Reales", validators=[name_validator])
    last_name = forms.CharField(max_length=150, required=True, label="Apellidos Reales", validators=[name_validator])
    is_active = forms.BooleanField(required=False, label="¿Usuario Activo?")
    rol = forms.ModelChoiceField(queryset=Group.objects.all(), required=True, label="Rol Principal del Usuario")

    password_new1 = forms.CharField(
        label=_("Nueva Contraseña"), required=False, widget=forms.PasswordInput, strip=False,
        help_text=MinimumLengthValidator().get_edit_help_text(), # Usar help_text para edición
        validators=[MinimumLengthValidator()]
    )
    password_new2 = forms.CharField(
        label=_("Confirmar Nueva Contraseña"), required=False, strip=False, widget=forms.PasswordInput,
        help_text=_("Introduzca la misma contraseña nueva para su verificación.")
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'is_active', 'rol', 'password_new1', 'password_new2')
        # El widget para username ya se define con 'readonly' en el template, pero para asegurar que la clase se aplica:
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacemos username no requerido ya que es readonly y no queremos que falle la validación si no se envía
        
        
        # Aplicar clases a otros campos si es necesario (algunos ya las tienen por el widget por defecto)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.PasswordInput, forms.Select, forms.ClearableFileInput)):
                attrs = field.widget.attrs
                # Añadir 'form-control' si no es un checkbox o radio y no lo tiene ya
                if 'class' not in attrs or 'form-control' not in attrs['class']:
                    attrs['class'] = (attrs.get('class', '') + ' form-control').strip()
                if isinstance(field.widget, forms.ClearableFileInput) and 'form-control-file' not in attrs['class']:
                     attrs['class'] = (attrs.get('class', '') + ' form-control-file').strip()
                field.widget.attrs = attrs


    def clean_password_new2(self):
        password_new1 = self.cleaned_data.get("password_new1")
        password_new2 = self.cleaned_data.get("password_new2")
        if password_new1:
            if not password_new2: raise forms.ValidationError(_("Debe confirmar la nueva contraseña."))
            if password_new1 != password_new2: raise forms.ValidationError(_("Las dos contraseñas nuevas no coinciden."))
        return password_new2

    def save(self, commit=True):
        user = super().save(commit=False)
        password_new1 = self.cleaned_data.get("password_new1")
        if password_new1:
            user.set_password(password_new1)
        if commit: user.save()
        return user

class UserProfileForm(forms.ModelForm):
    """Formulario para editar los campos del UserProfile."""

    ci = forms.CharField(
        max_length=10, # Actualizamos max_length
        required=True, # Asumo que CI sigue siendo requerido en el perfil
        label="Cédula de Identidad (CI)",
        validators=[ci_validator] # Reutilizamos validador
    )
    telefono = forms.CharField(
        max_length=10, # Actualizamos max_length
        required=False,
        label="Teléfono",
        validators=[phone_validator] # Reutilizamos validador
    )

    class Meta:
        model = UserProfile
        fields = ('ci', 'telefono', 'foto') # Campos del UserProfile
        labels = {
            'ci': "Cédula de Identidad (CI)",
        }
        widgets = {
            #'ci': forms.TextInput(attrs={'class': 'form-control'}),
            #'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control-file'}), # Widget para ImageField
        }

    def clean_ci(self):
        ci_data = self.cleaned_data.get('ci')
        if ci_data:
            # Al editar, debemos excluir el perfil del usuario actual de la comprobación de unicidad
            # self.instance es el objeto UserProfile que se está editando
            query = UserProfile.objects.filter(ci=ci_data)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                raise forms.ValidationError("Esta Cédula de Identidad ya está registrada para otro usuario.")
        return ci_data


#------------------------------------------
class GroupForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all().select_related('content_type').order_by(
            'content_type__app_label', 
            'content_type__model',
            'name' # o 'codename'
        ),
        widget=forms.CheckboxSelectMultiple, # Aunque lo renderizaremos manualmente, el widget base es este
        required=False,
        label="Permisos para este Grupo"
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions'] # Campos que queremos en el formulario
        labels = {
            'name': "Nombre del Grupo (Rol)",
        }
        help_texts = {
            'name': "Ej: Administradores, Editores Contenido, Usuarios Básicos",
            'permissions': "Seleccione los permisos que tendrán los usuarios pertenecientes a este grupo.",
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si estás editando un grupo existente, 'instance' estará presente.
        # Podemos preseleccionar los permisos que el grupo ya tiene.
        if self.instance and self.instance.pk:
            print(f"DEBUG (Form __init__): Editando grupo: {self.instance.name}")
            self.fields['permissions'].initial = list(self.instance.permissions.values_list('pk', flat=True)) 

    # El guardado de ModelForm ya maneja las relaciones ManyToMany si 'commit=True'
    # pero si haces commit=False, necesitas llamar a form.save_m2m() después.
    # No necesitamos sobrescribir save() aquí a menos que haya lógica muy específica.