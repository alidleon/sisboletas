
from django.apps import AppConfig

class PlanillaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'planilla' 

    def ready(self):
        
        try:
            from auditlog.registry import auditlog
            from .models import Planilla 
            from .models import DetalleBonoTe
            auditlog.register(Planilla)
            auditlog.register(DetalleBonoTe)
            print(f"Auditlog: Modelos 'Planilla' y 'DetalleBonoTe' de la app '{self.name}' registrados para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")
