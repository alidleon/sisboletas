from django.apps import AppConfig

class BoletasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'boletas' 
    def ready(self):
        try:
            from auditlog.registry import auditlog
            from .models import PlantillaBoleta 

            auditlog.register(PlantillaBoleta)
            
            print(f"Auditlog: Modelo 'PlantillaBoleta' de la app '{self.name}' registrado para auditoría.")

        except ImportError:
            print(f"Advertencia: django-auditlog no está instalado o no se pudo importar. "
                  f"La auditoría no estará activa para los modelos de '{self.name}'.")
        except Exception as e:
            print(f"Error al registrar modelos con auditlog en {self.name}Config: {e}")