from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

TRADUCCIONES = {
    'add':'Puede agregar',
    'change': 'Puede cambiar',
    'delete': 'Puede eliminar',
    'view': 'Puede ver',
}

@receiver(post_migrate)
def traducir_permisos(sender, **kwargs):
    try:
        for permission in Permission.objects.all():
            codename = permission.codename
            parts = codename.split('_')
            if len(parts) != 2:
                continue

            action, model_name = parts

            if action in TRADUCCIONES:
                content_type = permission.content_type
                model_class = content_type.model_class()

                if model_class is None:
                    print(f"ADVERTENCIA: Saltando permiso para un modelo no encontrado (ContenType ID: {content_type.id}, Modelo: {content_type.model})")
                    continue

                model_verbose_name = model_class._meta.verbose_name

                nuevo_nombre = f"{TRADUCCIONES[action]} {model_verbose_name}"

                if permission.name != nuevo_nombre:
                    print(f"Traduciendo permiso: '{permission.name}' -> '{nuevo_nombre}'")
                    permission.name = nuevo_nombre
                    permission.save()
    except Exception as e:
        print(f"Error durante la traduccion de permisos: {e}")