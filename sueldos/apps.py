# sisboletas/sueldos/apps.py
from django.apps import AppConfig

class SueldosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sueldos' # Nombre de tu aplicación

    def ready(self):
        # Si tienes señales específicas de la app 'sueldos' que se conectan
        # al importar modelos, puedes hacerlo aquí.
        # import sueldos.models 
        # import sueldos.signals # Si tienes un archivo signals.py

        # Registrar modelos locales de esta app con django-auditlog
        try:
            from auditlog.registry import auditlog
            
            # Importa los modelos locales específicos de ESTA APP que quieres auditar
            from .models import PlanillaSueldo
            from .models import DetalleSueldo
            from .models import CierreMensual
            from .models import EstadoMensualEmpleado
            # from .models import OtroModeloDeSueldos # Si tuvieras más

            auditlog.register(PlanillaSueldo)
            auditlog.register(DetalleSueldo)
            auditlog.register(CierreMensual)
            auditlog.register(EstadoMensualEmpleado)
            # auditlog.register(OtroModeloDeSueldos)
            
            print(f"Auditlog: Modelos de la app '{self.name}' registrados para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            # Es bueno capturar cualquier excepción durante el registro para no romper el inicio de Django
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")