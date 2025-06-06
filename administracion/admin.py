# administracion/admin.py
from django.contrib import admin
from auditlog.models import LogEntry
from auditlog.admin import LogEntryAdmin as DefaultLogEntryAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
import json # Import json

class CustomLogEntryAdmin(DefaultLogEntryAdmin):
    """
    ModelAdmin personalizado para mostrar las entradas de LogEntry de django-auditlog.
    """

    # Define explícitamente las columnas y los métodos que se usarán.
    list_display = [
        'created',              # Campo del modelo LogEntry
        'actor_link',           # Método de DefaultLogEntryAdmin (o nuestro si lo redefinimos)
        'action_description',   # Nuestro método
        'resource_url_or_repr', # Nuestro método
        'formatted_changes',    # Nuestro método para mostrar detalles/descripción
        'shortened_remote_addr' # Nuestro método para la IP
    ]

    # Campos para la búsqueda
    search_fields = [
        'actor__first_name', 
        'actor__last_name', 
        'actor__username', 
        'object_repr', 
        'changes',  # Permite buscar en nuestras descripciones y en el JSON de cambios
        'remote_addr'
    ]

    # Heredar filtros del admin por defecto de auditlog podría ser útil
    # Si no, puedes definir los tuyos: ['created', 'action', 'content_type']
    # list_filter = DefaultLogEntryAdmin.list_filter

    # --- Nuestros Métodos Personalizados para las Columnas ---

    def actor_link(self, obj):
        """
        Intenta crear un enlace al actor en el admin de Django.
        Si no puede, devuelve el nombre de usuario del actor.
        Este método replica o mejora la funcionalidad de 'actor_link'
        del DefaultLogEntryAdmin para asegurar que funcione.
        """
        if obj.actor:
            try:
                from django.urls import reverse, NoReverseMatch
                # Asumiendo que User está en el admin y su app_label es 'auth' y model_name es 'user'
                url = reverse('admin:auth_user_change', args=[obj.actor.pk])
                return format_html('<a href="{}">{}</a>', url, obj.actor.get_username())
            except NoReverseMatch: # Si el usuario no tiene una URL de admin (raro para User)
                return obj.actor.get_username()
            except Exception: # Otros errores
                return obj.actor.get_username() # Fallback seguro
        return _("Sistema") # O algún placeholder si el actor es None
    actor_link.short_description = _('Usuario') # Cambiado de 'Actor' a 'Usuario'
    actor_link.admin_order_field = 'actor'

    def action_description(self, obj):
        """Devuelve la descripción legible de la acción."""
        return obj.get_action_display()
    action_description.short_description = _('Acción')
    action_description.admin_order_field = 'action'

    def resource_url_or_repr(self, obj):
        """
        Intenta crear un enlace al objeto afectado en el admin de Django.
        Si no puede, devuelve la representación en string del objeto.
        """
        if obj.content_type and obj.object_id: # object_id es el PK numérico
            try:
                from django.urls import reverse, NoReverseMatch
                admin_url_name = f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change'
                url = reverse(admin_url_name, args=[obj.object_id])
                return format_html('<a href="{}">{}</a>', url, obj.object_repr)
            except NoReverseMatch:
                return obj.object_repr
            except Exception: # Para cualquier otro error inesperado
                return obj.object_repr
        return obj.object_repr
    resource_url_or_repr.short_description = _('Recurso Afectado')
    resource_url_or_repr.admin_order_field = 'object_repr'

    def formatted_changes(self, obj):
        """
        Muestra los detalles de los cambios o la descripción de la acción.
        """
        changes_data = obj.changes # Campo TextField

        if obj.action == LogEntry.Action.UPDATE:
            try:
                if changes_data and isinstance(changes_data, str) and changes_data.startswith('{') and changes_data.endswith('}'):
                    data_dict = json.loads(changes_data)
                    # Ejemplo: listar los campos cambiados
                    # changed_fields_list = [f"{k}: {v[0]} → {v[1]}" for k, v in data_dict.items()]
                    # summary = "; ".join(changed_fields_list)
                    # return (summary[:100] + '...') if len(summary) > 100 else summary
                    return f"{len(data_dict.keys())} campo(s) cambiado(s)" # Más simple para la lista
                return (changes_data[:100] + '...') if changes_data and len(changes_data) > 100 else (changes_data or "-")
            except (json.JSONDecodeError, TypeError): # TypeError si changes_data es None
                return (str(changes_data)[:100] + '...') if changes_data and len(str(changes_data)) > 100 else (str(changes_data) if changes_data else "-")
            except Exception:
                 return "Error al mostrar cambios"

        elif obj.action == LogEntry.Action.ACCESS: # Para nuestras acciones personalizadas
            if changes_data:
                max_len = 100
                return (changes_data[:max_len] + '...') if len(changes_data) > max_len else changes_data
            return "-"
        
        elif obj.action == LogEntry.Action.CREATE:
            # Para CREATE, 'changes' es un JSON string de los campos iniciales.
            try:
                if changes_data and isinstance(changes_data, str) and changes_data.startswith('{') and changes_data.endswith('}'):
                    data_dict = json.loads(changes_data)
                    return f"Creado con {len(data_dict.keys())} campo(s) inicial(es)"
                return "Objeto creado"
            except Exception:
                return "Objeto creado (detalle no disp.)"

        elif obj.action == LogEntry.Action.DELETE:
            return "Objeto eliminado"
            
        return (str(changes_data)[:100] + '...') if changes_data and len(str(changes_data)) > 100 else (str(changes_data) if changes_data else "-")
    formatted_changes.short_description = _('Detalles / Descripción')
    formatted_changes.admin_order_field = 'changes'


    def shortened_remote_addr(self, obj):
        """Acorta la dirección IP si es IPv6 mapeada a IPv4."""
        if obj.remote_addr and obj.remote_addr.startswith('::ffff:'):
            return obj.remote_addr[7:]
        return obj.remote_addr or "-" # Devolver "-" si es None
    shortened_remote_addr.short_description = _('IP Remota')
    shortened_remote_addr.admin_order_field = 'remote_addr'

# Desregistrar el LogEntryAdmin por defecto y registrar el nuestro.
if admin.site.is_registered(LogEntry):
    admin.site.unregister(LogEntry)
admin.site.register(LogEntry, CustomLogEntryAdmin)