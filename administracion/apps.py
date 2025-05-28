from django.apps import AppConfig


class AdministracionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'administracion'

    def ready(self):
        # Importar los modelos (que a su vez importa y registra las señales)
        # cuando la aplicación está completamente cargada.
        import administracion.models 
        # Si tuvieras un archivo signals.py separado, importarías ese:
        # import administracion.signals
