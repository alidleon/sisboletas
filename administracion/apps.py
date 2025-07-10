from django.apps import AppConfig

class AdministracionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'administracion'

    def ready(self):
        import administracion.models
        import administracion.signals
        from django.contrib.auth.models import User, Group 
        from .models import UserProfile 
        
        try:
            from auditlog.registry import auditlog            
            auditlog.register(User)
            auditlog.register(Group) 
            auditlog.register(UserProfile)
        except ImportError:
            pass 