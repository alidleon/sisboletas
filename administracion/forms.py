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

    def get_help_text(self):
        return _(
            "Su contraseña debe contener al menos %(min_length)d caracteres."
            % {'min_length': self.min_length}
        )
    
    def get_edit_help_text(self):
        return _(
            "Su contraseña debe contener al menos %(min_length)d caracteres. "
            "Deje vacío si no desea cambiarla."
            % {'min_length': self.min_length}
        )


name_validator = RegexValidator(
    regex=r'^[a-zA-ZñÑáéíóúÁÉÍÓÚ\s\-]+$',
    message="Este campo solo puede contener letras, espacios y guiones."
)

ci_validator = RegexValidator(
    regex=r'^\d{1,10}$',
    message="La Cédula de Identidad debe contener solo números y tener máximo 10 dígitos."
)

phone_validator = RegexValidator(
    regex=r'^\d{1,10}$', 
    message="El teléfono debe contener solo números y tener máximo 10 dígitos."
)




class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True, 
        help_text="Requerido. Se usará para notificaciones y posible recuperación de contraseña."
    )
    first_name = forms.CharField(
        max_length=150, 
        required=True,
        label="Nombres Reales",
        validators=[name_validator]
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Apellidos Reales",
        validators=[name_validator]
    )

    # --- Campos del Modelo UserProfile ---
    ci = forms.CharField(
        max_length=10,
        required=True,
        label="Cédula de Identidad (CI)",
        validators=[ci_validator]
    )
    telefono = forms.CharField(
        max_length=10,
        required=False,
        label="Teléfono",
        validators=[phone_validator]
    )
    foto = forms.ImageField(
        required=False,
        label="Foto de Perfil"
    )

    rol = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        label="Rol del Usuario en el Sistema",
        empty_label=None,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    password1 = forms.CharField(
        label=_("Contraseña"),
        widget=forms.PasswordInput,
        strip=False,
        help_text=MinimumLengthValidator().get_help_text(),
    )
    password2 = forms.CharField(
        label=_("Confirmación de contraseña"),
        strip=False,
        widget=forms.PasswordInput,
        help_text=_("Introduzca la misma contraseña que antes, para su verificación."),
    )

    class Meta(UserCreationForm.Meta):
        model = User 
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name', 'ci', 'telefono', 'foto', 'rol')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].validators = [MinimumLengthValidator()]
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        self.fields['email'].widget.attrs.update({'class': 'form-control'})
        self.fields['first_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['ci'].widget.attrs.update({'class': 'form-control'})
        self.fields['telefono'].widget.attrs.update({'class': 'form-control'})
        

    def clean_ci(self):
        ci_data = self.cleaned_data.get('ci')
        if ci_data:
            if UserProfile.objects.filter(ci=ci_data).exists():
                raise forms.ValidationError("Esta Cédula de Identidad ya está registrada para otro usuario.")
        return ci_data

    def save(self, commit=True):
        # 1. Guardar el User (esto también disparará la señal para crear el UserProfile vacío)
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.is_active = True
        if commit:
            user.save()
            # 2. Poblar el UserProfile con los datos del formulario
            try:
                profile = user.profile
                profile.ci = self.cleaned_data["ci"]
                profile.telefono = self.cleaned_data["telefono"]
                profile.foto = self.cleaned_data["foto"]
                profile.save()
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(
                    user=user,
                    ci=self.cleaned_data["ci"],
                    telefono=self.cleaned_data["telefono"],
                    foto=self.cleaned_data["foto"]
                )
            except Exception as e:
                print(f"Error al guardar el perfil para {user.username}: {e}")

            # 3. Asignar el Rol/Grupo
            rol_seleccionado = self.cleaned_data.get('rol')
            if rol_seleccionado:
                user.groups.clear()
                user.groups.add(rol_seleccionado)
        
        return user
#------------------------------------------------
class CustomUserChangeForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True, label="Nombres Reales", validators=[name_validator])
    last_name = forms.CharField(max_length=150, required=True, label="Apellidos Reales", validators=[name_validator])
    is_active = forms.BooleanField(required=False, label="¿Usuario Activo?")
    rol = forms.ModelChoiceField(queryset=Group.objects.all(), required=True, label="Rol Principal del Usuario")

    password_new1 = forms.CharField(
        label=_("Nueva Contraseña"), required=False, widget=forms.PasswordInput, strip=False,
        help_text=MinimumLengthValidator().get_edit_help_text(),
        validators=[MinimumLengthValidator()]
    )
    password_new2 = forms.CharField(
        label=_("Confirmar Nueva Contraseña"), required=False, strip=False, widget=forms.PasswordInput,
        help_text=_("Introduzca la misma contraseña nueva para su verificación.")
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'is_active', 'rol', 'password_new1', 'password_new2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.PasswordInput, forms.Select, forms.ClearableFileInput)):
                attrs = field.widget.attrs
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
        max_length=10,
        required=True,
        label="Cédula de Identidad (CI)",
        validators=[ci_validator]
    )
    telefono = forms.CharField(
        max_length=10,
        required=False,
        label="Teléfono",
        validators=[phone_validator]
    )

    class Meta:
        model = UserProfile
        fields = ('ci', 'telefono', 'foto')
        labels = {
            'ci': "Cédula de Identidad (CI)",
        }
        widgets = {
            #'ci': forms.TextInput(attrs={'class': 'form-control'}),
            #'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        }

    def clean_ci(self):
        ci_data = self.cleaned_data.get('ci')
        if ci_data:
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
            'name'
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Permisos para este Grupo"
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']
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
        if self.instance and self.instance.pk:
            print(f"DEBUG (Form __init__): Editando grupo: {self.instance.name}")
            self.fields['permissions'].initial = list(self.instance.permissions.values_list('pk', flat=True)) 
