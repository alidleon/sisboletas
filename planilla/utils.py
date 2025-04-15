# --- planilla/utils.py ---

import logging
from django.shortcuts import get_object_or_404
# Importa los modelos necesarios
from .models import (
    Planilla, DetalleBonoTe, PrincipalDesignacionExterno, PrincipalPersonalExterno,
    PrincipalCargoExterno, PrincipalUnidadExterna, PrincipalSecretariaExterna
)
# Importa Q para consultas OR (buscar por CI O por Item)
from django.db.models import Q
from decimal import Decimal # Para convertir Item si es numérico

logger = logging.getLogger(__name__)

def get_processed_planilla_details(request, planilla_id):
    """
    Obtiene la planilla, listas de filtros, y los detalles de personal
    (filtrados y enriquecidos) basados en los parámetros GET, incluyendo búsqueda.
    """
    result = {
        'planilla': None,
        'all_secretarias': PrincipalSecretariaExterna.objects.none(),
        'unidades_for_select': PrincipalUnidadExterna.objects.none(),
        'selected_secretaria_id': None,
        'selected_unidad_id': None,
        'detalles_enriquecidos': [],
        'search_active': False,
        'error_message': None,
        'search_term': '', # <-- NUEVO: Guardar término de búsqueda
    }

    # --- 0. Obtener la Planilla ---
    try:
        planilla = Planilla.objects.get(pk=planilla_id)
        result['planilla'] = planilla
        logger.info(f"[Util] Procesando Planilla ID {planilla.id} (Tipo: {planilla.get_tipo_display()})")
    except Planilla.DoesNotExist:
        logger.error(f"[Util] Planilla con ID={planilla_id} no encontrada.")
        result['error_message'] = f"Planilla ID {planilla_id} no encontrada."
        return result
    except Exception as e_plan:
        logger.error(f"[Util] Error obteniendo Planilla ID {planilla_id}: {e_plan}", exc_info=True)
        result['error_message'] = f"Error inesperado al buscar la planilla: {e_plan}"
        return result

    # --- 1. Obtener Secretarías ---
    # ... (código igual que antes) ...
    try:
        all_secretarias = PrincipalSecretariaExterna.objects.using('personas_db').order_by('nombre_secretaria')
        result['all_secretarias'] = all_secretarias
    except Exception as e_sec:
        logger.error(f"[Util] Error obteniendo secretarías externas: {e_sec}", exc_info=True)
        result['error_message'] = f"No se pudo cargar la lista de secretarías: {e_sec}"


    # --- 2. Procesar Filtros GET (Secretaría, Unidad Y BÚSQUEDA) ---
    filter_secretaria_str = request.GET.get('secretaria', None)
    filter_unidad_str = request.GET.get('unidad', None)
    # *** NUEVO: Obtener término de búsqueda (usamos 'q' como nombre estándar) ***
    search_term = request.GET.get('q', '').strip() # Eliminar espacios extra
    result['search_term'] = search_term # Guardarlo para el template

    result['search_active'] = request.GET.get('buscar') is not None or filter_unidad_str is not None or bool(search_term)

    # Cargar Unidades si se seleccionó Secretaría
    unidades_qs = PrincipalUnidadExterna.objects.none()
    if filter_secretaria_str:
        try:
            selected_secretaria_id = int(filter_secretaria_str)
            result['selected_secretaria_id'] = selected_secretaria_id
            unidades_qs = PrincipalUnidadExterna.objects.using('personas_db') \
                                .filter(secretaria_id=selected_secretaria_id) \
                                .order_by('nombre_unidad')
            result['unidades_for_select'] = unidades_qs
        except (ValueError, Exception) as e_uni: # Capturar errores
             logger.warning(f"[Util] Error procesando secretaría/unidad: {e_uni}")
             # Resetear si hay error
             result['selected_secretaria_id'] = None
             result['unidades_for_select'] = PrincipalUnidadExterna.objects.none()


    # --- 3. Obtener IDs de Personal Externo Relevantes (Combinando Filtros y Búsqueda) ---
    personal_ids_to_filter_local = set() # Set final de IDs para filtrar DetalleBonoTe
    proceed_with_details = False # Bandera para saber si debemos buscar detalles

    # 3.a Filtrar por Unidad (si aplica)
    personal_ids_in_unidad = set()
    selected_unidad_id = None # Reiniciar para asegurar
    if filter_unidad_str:
        try:
            selected_unidad_id = int(filter_unidad_str)
            result['selected_unidad_id'] = selected_unidad_id
            estado_activo = 'ACTIVO' # O el valor que uses

            if not hasattr(PrincipalDesignacionExterno, 'estado'):
                 raise AttributeError("Modelo PrincipalDesignacionExterno no tiene campo 'estado'.")

            designaciones_qs = PrincipalDesignacionExterno.objects.using('personas_db') \
                .filter(unidad_id=selected_unidad_id, estado=estado_activo) \
                .values_list('personal_id', flat=True).distinct()
            personal_ids_in_unidad = set(pid for pid in designaciones_qs if pid is not None)
            logger.info(f"[Util] IDs en Unidad {selected_unidad_id} (Activos): {len(personal_ids_in_unidad)}")
            proceed_with_details = True # Si se filtró por unidad, queremos mostrar detalles

        except ValueError:
             logger.warning(f"[Util] ID de Unidad inválido: '{filter_unidad_str}'")
             result['error_message'] = "ID de Unidad inválido."
             proceed_with_details = False # No podemos continuar sin unidad válida
        except AttributeError as attr_err_desig:
             logger.error(f"[Util] Error de Atributo en filtro Unidad: {attr_err_desig}", exc_info=True)
             result['error_message'] = f"Error de configuración ({attr_err_desig})."
             proceed_with_details = False
        except Exception as e_pers_ids:
            logger.error(f"[Util] Error obteniendo personal_ids para Unidad {selected_unidad_id}: {e_pers_ids}", exc_info=True)
            result['error_message'] = "Error al buscar personal en la unidad."
            proceed_with_details = False # No podemos continuar

    # 3.b Filtrar por Término de Búsqueda (CI o Item)
    personal_ids_from_search = set()
    if search_term:
        proceed_with_details = True # Si hay búsqueda, queremos mostrar resultados
        try:
            # Intentar convertir a número para buscar por Item (si Item es numérico)
            item_numeric = None
            try:
                # Asumiendo que item es Decimal o Int en el modelo. Ajusta si es CharField.
                item_numeric = Decimal(search_term)
                # O int(search_term) si es IntegerField
            except (ValueError, Decimal.InvalidOperation):
                item_numeric = None # No es un número válido

            # Construir consulta Q para buscar por CI (exacto) o Item (exacto)
            search_query_pers = Q(ci__iexact=search_term) # Búsqueda CI (case-insensitive)
            search_query_desig = Q()
            if item_numeric is not None:
                 # Asegúrate que el campo 'item' existe y el tipo es correcto
                 if hasattr(PrincipalDesignacionExterno, 'item'):
                     search_query_desig = Q(item=item_numeric)
                 else:
                      logger.warning("Campo 'item' no existe en PrincipalDesignacionExterno, no se puede buscar por item.")

            # Buscar IDs de personal por CI
            ids_ci = PrincipalPersonalExterno.objects.using('personas_db') \
                        .filter(search_query_pers) \
                        .values_list('id', flat=True)
            personal_ids_from_search.update(ids_ci)

            # Buscar IDs de personal por Item (si aplica y es numérico)
            if search_query_desig: # Solo buscar si creamos la Q para item
                # Aplicar también filtro de estado ACTIVO al buscar por item
                estado_activo = 'ACTIVO'
                if hasattr(PrincipalDesignacionExterno, 'estado'):
                    ids_item = PrincipalDesignacionExterno.objects.using('personas_db') \
                                .filter(search_query_desig, estado=estado_activo) \
                                .values_list('personal_id', flat=True).distinct()
                    personal_ids_from_search.update(p_id for p_id in ids_item if p_id is not None)
                else:
                     logger.warning("Campo 'estado' no existe, no se puede aplicar filtro activo en búsqueda por item.")


            logger.info(f"[Util] IDs encontrados por búsqueda '{search_term}': {len(personal_ids_from_search)}")

        except Exception as e_search:
            logger.error(f"[Util] Error durante búsqueda externa para '{search_term}': {e_search}", exc_info=True)
            result['error_message'] = "Error durante la búsqueda."
            # Si la búsqueda falla, es mejor no mostrar resultados erróneos
            proceed_with_details = False

    # 3.c Combinar resultados de filtros y búsqueda
    if search_term and selected_unidad_id:
        # Intersección: personal que está EN LA UNIDAD Y coincide con la búsqueda
        personal_ids_to_filter_local = personal_ids_in_unidad.intersection(personal_ids_from_search)
        logger.info(f"[Util] Intersección Unidad y Búsqueda: {len(personal_ids_to_filter_local)} IDs")
    elif search_term:
        # Solo búsqueda: personal que coincide con la búsqueda (en cualquier unidad activa con ese item)
        personal_ids_to_filter_local = personal_ids_from_search
    elif selected_unidad_id:
        # Solo filtro de unidad
        personal_ids_to_filter_local = personal_ids_in_unidad
    # else: (ni filtro de unidad ni búsqueda -> no mostrar detalles por defecto,
    #        a menos que cambies la lógica para mostrar todos si no hay filtro)


    # --- 4. Obtener y Enriquecer Detalles Locales (SI procede) ---
    if proceed_with_details and not personal_ids_to_filter_local and (selected_unidad_id or search_term):
        # Si se aplicó un filtro/búsqueda pero no se encontraron IDs coincidentes,
        # no hay necesidad de consultar/enriquecer, simplemente mostrar mensaje vacío.
        logger.info("[Util] Filtro/Búsqueda activa pero no se encontraron IDs de personal coincidentes.")
        result['detalles_enriquecidos'] = [] # Lista vacía
    elif proceed_with_details and personal_ids_to_filter_local:
        # Si tenemos IDs y debemos proceder
        try:
            # PASO A: Filtrar Detalles Locales por Planilla y IDs encontrados
            detalles_locales_filtrados = list(DetalleBonoTe.objects.filter(
                id_planilla=planilla,
                personal_externo_id__in=personal_ids_to_filter_local
            ))
            logger.info(f"[Util] Filtrados {len(detalles_locales_filtrados)} detalles locales.")

            # PASO B: Enriquecer los Detalles Filtrados (si hay)
            if detalles_locales_filtrados:
                # Obtener solo los IDs necesarios para enriquecer
                ids_needed = {d.personal_externo_id for d in detalles_locales_filtrados if d.personal_externo_id}

                personal_info_f = {}
                designaciones_info_f = {}

                # Consultar info de Personal
                if ids_needed:
                    try:
                        personas_externas_f = PrincipalPersonalExterno.objects.using('personas_db').filter(id__in=ids_needed)
                        personal_info_f = {p.id: p for p in personas_externas_f}
                    except Exception as e_pers_f: logger.error(...) # Log error

                # Consultar info de Designación (ACTIVA y relevante)
                if ids_needed:
                    try:
                        estado_activo = 'ACTIVO'
                        # Crear consulta base para designaciones
                        desig_query = PrincipalDesignacionExterno.objects.using('personas_db') \
                            .filter(personal_id__in=ids_needed, estado=estado_activo) \
                            .select_related('cargo', 'unidad') \
                            .order_by('personal_id', '-id') # Ordenar para obtener la más reciente por persona

                        # Si se filtró por unidad, añadir ese filtro a la consulta de designación también
                        if selected_unidad_id:
                            desig_query = desig_query.filter(unidad_id=selected_unidad_id)

                        # Obtener la designación más relevante por persona (la primera después de ordenar)
                        designaciones_relevantes = {}
                        for desig in desig_query:
                            if desig.personal_id not in designaciones_relevantes: # Tomar solo la primera (más reciente)
                                designaciones_relevantes[desig.personal_id] = desig

                        # Crear diccionario de info para acceso rápido
                        designaciones_info_f = {
                            pid: {
                                'item': desig.item,
                                'cargo': desig.cargo.nombre_cargo if desig.cargo else 'N/A',
                                'unidad_nombre': desig.unidad.nombre_unidad if desig.unidad else 'N/A'
                            } for pid, desig in designaciones_relevantes.items()
                        }
                    except Exception as e_desig_f: logger.error(...) # Log error


                # Bucle de enriquecimiento
                enriched_list_temp = []
                for detalle in detalles_locales_filtrados:
                    persona = personal_info_f.get(detalle.personal_externo_id)
                    info_desig = designaciones_info_f.get(detalle.personal_externo_id)

                    detalle.item_externo = info_desig.get('item', 'N/A') if info_desig else 'N/A'
                    detalle.cargo_externo = info_desig.get('cargo', 'N/A') if info_desig else 'N/A'
                    detalle.unidad_externa_nombre = info_desig.get('unidad_nombre', 'N/A') if info_desig else 'N/A' # Podría ser útil mostrarla
                    detalle.ci_externo = persona.ci if persona else 'N/A'
                    detalle.nombre_completo_externo = persona.nombre_completo if persona else 'No encontrado'
                    enriched_list_temp.append(detalle)

                # Ordenar resultados finales (opcional)
                try:
                     enriched_list_temp.sort(key=lambda d: (
                         getattr(d, 'nombre_completo_externo', '').split()[-2] if len(getattr(d, 'nombre_completo_externo', '').split()) > 1 else '', # Apellido Paterno aprox
                         getattr(d, 'nombre_completo_externo', '').split()[-1] if len(getattr(d, 'nombre_completo_externo', '').split()) > 0 else '', # Apellido Materno aprox
                         getattr(d, 'nombre_completo_externo', '').split()[0] if len(getattr(d, 'nombre_completo_externo', '').split()) > 0 else '' # Nombre aprox
                     ))
                except Exception as e_sort:
                     logger.warning(f"Error al ordenar detalles enriquecidos: {e_sort}")


                result['detalles_enriquecidos'] = enriched_list_temp
                logger.info(f"[Util] Enriquecimiento completado para {len(enriched_list_temp)} detalles.")

        except Exception as e_filter_enrich:
             logger.error(f"[Util] Error general durante filtrado/enriquecimiento: {e_filter_enrich}", exc_info=True)
             result['error_message'] = f"Ocurrió un error al procesar los detalles: {e_filter_enrich}"
             result['detalles_enriquecidos'] = [] # Asegurar lista vacía

    # else: (Si proceed_with_details es False)
    #    Los detalles se quedan como lista vacía por defecto.

    return result