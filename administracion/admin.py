from django.contrib import admin
from auditlog.models import LogEntry
from auditlog.admin import LogEntryAdmin as DefaultLogEntryAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
import json

class CustomLogEntryAdmin(DefaultLogEntryAdmin):
    """
    ModelAdmin personalizado para mostrar las entradas de LogEntry de django-auditlog.
    """
    list_display = [
        'created',  
        'actor_link',
        'action_description',
        'resource_url_or_repr',
        'formatted_changes',
        'shortened_remote_addr'
    ]
    search_fields = [
        'actor__first_name', 
        'actor__last_name', 
        'actor__username', 
        'object_repr', 
        'changes', 
        'remote_addr'
    ]

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
                url = reverse('admin:auth_user_change', args=[obj.actor.pk])
                return format_html('<a href="{}">{}</a>', url, obj.actor.get_username())
            except NoReverseMatch:
                return obj.actor.get_username()
            except Exception:
                return obj.actor.get_username()
        return _("Sistema")
    actor_link.short_description = _('Usuario')
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
        if obj.content_type and obj.object_id:
            try:
                from django.urls import reverse, NoReverseMatch
                admin_url_name = f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change'
                url = reverse(admin_url_name, args=[obj.object_id])
                return format_html('<a href="{}">{}</a>', url, obj.object_repr)
            except NoReverseMatch:
                return obj.object_repr
            except Exception:
                return obj.object_repr
        return obj.object_repr
    resource_url_or_repr.short_description = _('Recurso Afectado')
    resource_url_or_repr.admin_order_field = 'object_repr'

    def formatted_changes(self, obj):
        """
        Muestra los detalles de los cambios o la descripción de la acción.
        """
        changes_data = obj.changes

        if obj.action == LogEntry.Action.UPDATE:
            try:
                if changes_data and isinstance(changes_data, str) and changes_data.startswith('{') and changes_data.endswith('}'):
                    data_dict = json.loads(changes_data)
                    return f"{len(data_dict.keys())} campo(s) cambiado(s)"
                return (changes_data[:100] + '...') if changes_data and len(changes_data) > 100 else (changes_data or "-")
            except (json.JSONDecodeError, TypeError):
                return (str(changes_data)[:100] + '...') if changes_data and len(str(changes_data)) > 100 else (str(changes_data) if changes_data else "-")
            except Exception:
                 return "Error al mostrar cambios"

        elif obj.action == LogEntry.Action.ACCESS:
            if changes_data:
                max_len = 100
                return (changes_data[:max_len] + '...') if len(changes_data) > max_len else changes_data
            return "-"
        
        elif obj.action == LogEntry.Action.CREATE:
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
        return obj.remote_addr or "-" 
    shortened_remote_addr.short_description = _('IP Remota')
    shortened_remote_addr.admin_order_field = 'remote_addr'
if admin.site.is_registered(LogEntry):
    admin.site.unregister(LogEntry)
admin.site.register(LogEntry, CustomLogEntryAdmin)