from django.db import models
from django.conf import settings 
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    # --- ENLACE AL USER DE DJANGO ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,    
        related_name='profile',     
        primary_key=True 
    )

    
    ci = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True,
        null=True,
        verbose_name="Cédula de Identidad"
    )
    
    telefono = models.CharField(
        max_length=25,               
        blank=True, 
        null=True, 
        verbose_name="Teléfono"
    )
    
    foto = models.ImageField(
        upload_to='fotos_perfil/',
        blank=True,
        null=True,
        verbose_name="Foto de Perfil"
    )


    def __str__(self):
        return f"Perfil de {self.user.username}"

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile_on_user_creation(sender, instance, created, **kwargs):
    """
    Cuando un nuevo objeto User es creado (created=True),
    esta función crea automáticamente un UserProfile asociado a él.
    """
    if created:
        UserProfile.objects.create(user=instance)


