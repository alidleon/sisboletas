
from django.apps import AppConfig

class PlanillaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'planilla' # Nombre de tu aplicación

    def ready(self):
        # Si tienes señales específicas de la app 'planilla' que se conectan
        # al importar modelos, puedes hacerlo aquí.
        # import planilla.models
        # import planilla.signals # Si tienes un archivo signals.py

        # Registrar modelos locales de esta app con django-auditlog
        try:
            from auditlog.registry import auditlog
            
            # Importa los modelos locales específicos de ESTA APP que quieres auditar
            from .models import Planilla 
            from .models import DetalleBonoTe
            # from .models import OtroModeloLocalDePlanilla # Si tuvieras más

            auditlog.register(Planilla)
            auditlog.register(DetalleBonoTe)
            # auditlog.register(OtroModeloLocalDePlanilla)
            
            print(f"Auditlog: Modelos 'Planilla' y 'DetalleBonoTe' de la app '{self.name}' registrados para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            # Es bueno capturar cualquier excepción durante el registro para no romper el inicio de Django
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")
