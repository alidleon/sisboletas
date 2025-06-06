# sisboletas/administracion/apps.py
from django.apps import AppConfig

class AdministracionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'administracion'

    def ready(self):
        # Primero, importa tus modelos para asegurar que están cargados
        # Esto es importante si tus modelos tienen decoradores o lógica que se ejecuta al importar.
        # La señal para UserProfile ya se conecta al importar models.py
        import administracion.models # Esto ya lo tenías y es correcto

        # Ahora, registra los modelos de esta app con django-auditlog
        # Importa los modelos específicos que quieres registrar y auditlog
        from django.contrib.auth.models import User, Group # Modelos de Django
        from .models import UserProfile # Tu modelo UserProfile
        
        try:
            from auditlog.registry import auditlog
            
            auditlog.register(User)
            # Podrías considerar si quieres auditar Group directamente aquí
            # o si la gestión de grupos se hace a través de una interfaz que ya audita User.
            # Por consistencia, auditarlo es buena idea si hay cambios directos a Group.
            auditlog.register(Group) 
            auditlog.register(UserProfile)

            # Si tuvieras más modelos en la app 'administracion' para auditar, los añades aquí:
            # from .models import OtroModeloAdministracion
            # auditlog.register(OtroModeloAdministracion)

        except ImportError:
            # auditlog podría no estar instalado durante ciertas fases (ej. makemigrations iniciales sin dependencias)
            # o si decides hacerlo opcional.
            pass 
            # O podrías lanzar un warning:
            # import warnings
            # warnings.warn("django-auditlog no está instalado. La auditoría no estará activa para la app 'administracion'.")

        # Si tuvieras un archivo signals.py separado, también lo importarías aquí
        # import administracion.signals