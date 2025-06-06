
from django.apps import AppConfig

class ReportesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reportes' # Nombre de tu aplicación

    def ready(self):
        # Registrar modelos locales de esta app con django-auditlog
        try:
            from auditlog.registry import auditlog
            
            # Importa los modelos locales específicos de ESTA APP que quieres auditar
            # Reemplaza con tus nombres de modelos reales de la app 'reportes'
            from .models import PlanillaAsistencia 
            from .models import DetalleAsistencia 
            # from .models import OtroModeloDeReportes # Si tuvieras más

            auditlog.register(PlanillaAsistencia)
            auditlog.register(DetalleAsistencia)
            # auditlog.register(OtroModeloDeReportes)
            
            print(f"Auditlog: Modelos de la app '{self.name}' registrados para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")