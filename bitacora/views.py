from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from auditlog.models import LogEntry
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.utils.translation import gettext_lazy as _ 
import json 
from django.http import HttpResponse 
import datetime
from .utils import generar_respuesta_csv, generar_respuesta_pdf, generar_respuesta_excel


@login_required
@permission_required('auditlog.view_logentry', raise_exception=True) 
def lista_registros_log_view(request):
    log_entries_queryset = LogEntry.objects.select_related('actor', 'content_type').order_by('-timestamp')
    
    # --- Lógica de Filtros y Búsqueda  ---
    selected_actor_id_str = request.GET.get('actor')
    selected_action_str = request.GET.get('action')
    selected_content_type_id_str = request.GET.get('content_type')
    fecha_desde_str = request.GET.get('fecha_desde')
    fecha_hasta_str = request.GET.get('fecha_hasta')
    search_query = request.GET.get('q', '').strip()

    selected_actor_id = int(selected_actor_id_str) if selected_actor_id_str and selected_actor_id_str.isdigit() else None
    selected_action = int(selected_action_str) if selected_action_str and selected_action_str.isdigit() else None
    selected_content_type_id = int(selected_content_type_id_str) if selected_content_type_id_str and selected_content_type_id_str.isdigit() else None

    if selected_actor_id:
        log_entries_queryset = log_entries_queryset.filter(actor_id=selected_actor_id)
    if selected_action is not None:
        log_entries_queryset = log_entries_queryset.filter(action=selected_action)
    if selected_content_type_id:
        log_entries_queryset = log_entries_queryset.filter(content_type_id=selected_content_type_id)
    if fecha_desde_str:
        log_entries_queryset = log_entries_queryset.filter(timestamp__date__gte=fecha_desde_str)
    if fecha_hasta_str:
        log_entries_queryset = log_entries_queryset.filter(timestamp__date__lte=fecha_hasta_str)
    if search_query:
        log_entries_queryset = log_entries_queryset.filter(
            Q(object_repr__icontains=search_query) |
            Q(changes__icontains=search_query) |
            Q(actor__username__icontains=search_query) |
            Q(actor__first_name__icontains=search_query) |
            Q(actor__last_name__icontains=search_query) |
            Q(remote_addr__icontains=search_query)
        ).distinct()


    # --- INICIO: MANEJO EXPORTACIONES ---
    export_type = request.GET.get('export_type') 
    if export_type == 'csv':
        return generar_respuesta_csv(log_entries_queryset) 
    elif export_type == 'excel': 
        return generar_respuesta_excel(log_entries_queryset)
    elif export_type == 'pdf': 
        return generar_respuesta_pdf(log_entries_queryset)
    

    # --- Paginación ---
    page_number = request.GET.get('page', 1)
    paginator = Paginator(log_entries_queryset, 25)
    try:
        log_entries_page = paginator.page(page_number)
    except PageNotAnInteger:
        log_entries_page = paginator.page(1)
    except EmptyPage:
        log_entries_page = paginator.page(paginator.num_pages)

    # --- Datos para los Select de Filtros  ---
    actors_for_filter = User.objects.filter(pk__in=LogEntry.objects.values_list('actor_id', flat=True).distinct().exclude(actor_id=None)).order_by('username')
    if hasattr(LogEntry.Action, 'choices') and callable(getattr(LogEntry.Action, 'choices', None)):
        action_choices_for_filter = LogEntry.Action.choices
    else:
        action_choices_for_filter = [(LogEntry.Action.CREATE, _('Crear')),(LogEntry.Action.UPDATE, _('Actualizar')),(LogEntry.Action.DELETE, _('Eliminar')),(LogEntry.Action.ACCESS, _('Acceso/Uso')),]
    content_types_for_filter = ContentType.objects.filter(pk__in=LogEntry.objects.values_list('content_type_id', flat=True).distinct().exclude(content_type_id=None)).order_by('app_label', 'model')
    
    context = {
        'log_entries_page': log_entries_page,
        'actors_for_filter': actors_for_filter,
        'action_choices_for_filter': action_choices_for_filter,
        'content_types_for_filter': content_types_for_filter,
        'selected_actor_id': selected_actor_id,
        'selected_action': selected_action,
        'selected_content_type_id': selected_content_type_id,
        'fecha_desde_str': fecha_desde_str,
        'fecha_hasta_str': fecha_hasta_str,
        'search_query': search_query,
        'titulo_vista': "Bitácora del Sistema",
    }
    return render(request, 'bitacora/lista_registros_log.html', context)


@login_required
@permission_required('auditlog.view_logentry', raise_exception=True)
def detalle_registro_log_view(request, log_id):
    log_entry = get_object_or_404(
        LogEntry.objects.select_related('actor', 'content_type'), 
        pk=log_id
    )

    changes_dict = None
    if log_entry.changes and isinstance(log_entry.changes, str):
        try:
            parsed_changes = json.loads(log_entry.changes)
            if isinstance(parsed_changes, dict):
                changes_dict = parsed_changes
        except json.JSONDecodeError:
            pass 
    
    context = {
        'log_entry': log_entry,
        'changes_dict': changes_dict,
        'titulo_vista': f"Detalle de Registro de Bitácora #{log_entry.pk}",
    }
    return render(request, 'bitacora/detalle_registro_log.html', context)
