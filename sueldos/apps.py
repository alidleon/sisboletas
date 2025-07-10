from django.apps import AppConfig

class SueldosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sueldos'

    def ready(self):
        
        try:
            from auditlog.registry import auditlog
            
            from .models import PlanillaSueldo
            from .models import DetalleSueldo
            from .models import CierreMensual
            from .models import EstadoMensualEmpleado

            auditlog.register(PlanillaSueldo)
            auditlog.register(DetalleSueldo)
            auditlog.register(CierreMensual)
            auditlog.register(EstadoMensualEmpleado)
            
            print(f"Auditlog: Modelos de la app '{self.name}' registrados para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")