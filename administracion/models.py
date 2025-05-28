# administracion/models.py
from django.db import models
from django.conf import settings  # Para referenciar el modelo User (settings.AUTH_USER_MODEL)
from django.db.models.signals import post_save # Para la señal de creación automática
from django.dispatch import receiver # Decorador para el receptor de la señal

class UserProfile(models.Model):
    # --- ENLACE AL USER DE DJANGO ---
    # Relación uno a uno con el modelo User estándar de Django.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,    # Si se borra el User, también se borra este Perfil.
        related_name='profile',      # Acceso desde una instancia de User: user.profile
        primary_key=True             # Hace que el campo 'user' (user_id) sea la clave primaria de esta tabla.
                                     # Esto es bueno para perfiles 1-a-1.
    )

    # --- DATOS BIOGRÁFICOS ADICIONALES (CAMPOS PERSONALIZADOS) ---
    # Los campos 'nombre', 'a_paterno', 'a_materno' se manejarán con 
    # User.first_name y User.last_name.
    
    ci = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True,  # Permite vacío en formularios
        null=True,   # Permite NULL en la BD
        verbose_name="Cédula de Identidad"
    )
    
    telefono = models.CharField(
        max_length=25,               # Un poco más de longitud por si acaso (prefijos, etc.)
        blank=True,                  # Puede estar vacío en formularios.
        null=True,                   # Puede ser NULL en la base de datos.
        verbose_name="Teléfono"
    )
    
    foto = models.ImageField(
        upload_to='fotos_perfil/',   # Las imágenes se guardarán en MEDIA_ROOT/fotos_perfil/
        blank=True,
        null=True,
        verbose_name="Foto de Perfil"
    )

    # --- Puedes añadir más campos personalizados aquí si los necesitas en el futuro ---
    # Ejemplo:
    # puesto_laboral = models.CharField(max_length=100, blank=True, null=True, verbose_name="Puesto Laboral")

    def __str__(self):
        # Devuelve una representación en string útil, usando el username del User asociado.
        return f"Perfil de {self.user.username}"

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"
        # ordering = ['user__username'] # Opcional: orden por defecto en consultas


# --- SEÑAL PARA CREAR AUTOMÁTICAMENTE EL UserProfile ---
# Esta función se conectará a la señal 'post_save' del modelo User.
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile_on_user_creation(sender, instance, created, **kwargs):
    """
    Cuando un nuevo objeto User es creado (created=True),
    esta función crea automáticamente un UserProfile asociado a él.
    """
    if created:
        UserProfile.objects.create(user=instance)
        # Opcional: puedes loggear o imprimir un mensaje para debugging
        # print(f"UserProfile creado para el nuevo usuario: {instance.username}")

# (Opcional) Si necesitas que el perfil se guarde/actualice cada vez que el User se guarda,
# podrías tener otra señal o expandir la lógica de la de arriba, pero para campos
# como 'telefono' y 'foto', usualmente se actualizan a través de un formulario de perfil,
# no automáticamente cuando el User se guarda (a menos que copies datos).
# Por ahora, la creación automática es el comportamiento más importante.

