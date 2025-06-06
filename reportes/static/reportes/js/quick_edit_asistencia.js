// static/reportes/js/quick_edit_asistencia.js

$(document).ready(function() {
    // --- NUEVO LOG: Inicio de ejecución ---
    console.log("Document ready. Intentando adjuntar listeners...");

    // --- Selección de Elementos del DOM ---
    const tableBody = $('#asistencia-table-body');

    // --- NUEVO LOG: Verificar si se encontró el tbody ---
    if (tableBody.length > 0) {
        console.log("Elemento #asistencia-table-body encontrado. Procediendo a adjuntar listener.");
    } else {
        // Si no se encuentra el tbody, los listeners delegados no funcionarán.
        console.error("¡ERROR CRÍTICO! Elemento #asistencia-table-body NO encontrado. El listener de clic en botones no funcionará. Verifica el ID en tu HTML.");
    }

    const quickEditPanel = $('#quick-edit-panel');
    const quickEditForm = $('#quick-edit-form');
    const quickEditPersonName = $('#quick-edit-person-name');
    const quickEditErrorMessage = $('#quick-edit-error-message');
    const saveButton = $('#quick-edit-save-btn');
    const saveNextButton = $('#quick-edit-save-next-btn');
    const cancelButton = $('#quick-edit-cancel-btn');
    const closeButton = $('#quick-edit-close'); // Botón 'X' del panel

    let currentEditingId = null; // Guarda el ID del detalle que se está editando
    let isSaving = false; // Flag para evitar doble envío

    // --- Funciones Auxiliares ---

    // Obtener CSRF token (Django estándar)
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    // Aplicar clases de Bootstrap a los campos del formulario (llamada después de poblar)
    function applyBootstrapClassesToQuickEditForm() {
        // console.log("Aplicando clases de Bootstrap al formulario de edición rápida...");
        quickEditForm.find('input[type="number"], input[type="text"], textarea, select').each(function() {
            if (!$(this).hasClass('form-control-sm')) { $(this).addClass('form-control-sm'); }
            if (!$(this).hasClass('form-control')) { $(this).addClass('form-control'); }
            if ($(this).is('select') && !$(this).hasClass('form-select-sm')) { $(this).addClass('form-select-sm'); }
        });
    }

    // Limpiar mensajes y estilos de error del formulario
    function clearFormErrors() {
        quickEditForm.find('.is-invalid').removeClass('is-invalid');
        // Buscar el div de error por ID construido dinámicamente y vaciarlo
        quickEditForm.find('[id^="error_id_"]').text(''); // Vaciar divs de error específicos
        quickEditErrorMessage.hide().empty(); // Ocultar y vaciar mensaje general
    }

    // Mostrar errores de validación del formulario recibidos del backend
    function showFormErrors(errors) {
        clearFormErrors();
        let firstErrorField = null;
        console.log("Mostrando errores de formulario:", errors);
        for (const fieldName in errors) {
            const fieldElement = $(`#id_${fieldName}`); // <-- CORREGIDO: Buscar ID estándar
            const errorElement = $(`#error_id_${fieldName}`); // <-- CORREGIDO: Buscar ID de error estándar

            if (fieldElement.length) {
                fieldElement.addClass('is-invalid');
                if (errorElement.length) {
                    const errorMessage = Array.isArray(errors[fieldName])
                                        ? errors[fieldName].map(e => e.message || e).join(' ')
                                        : errors[fieldName];
                    errorElement.text(errorMessage);
                    // No necesitamos .show() aquí si invalid-feedback de Bootstrap funciona como se espera
                } else {
                    console.warn(`Div de error #error_id_${fieldName} no encontrado para el campo ${fieldName}`);
                }
                if (!firstErrorField) {
                    firstErrorField = fieldElement;
                }
            } else {
                 // Manejar errores generales (__all__) o errores de campos no encontrados
                console.warn(`Campo de error '${fieldName}' no encontrado en el formulario (ID esperado: #id_${fieldName}). Mostrando en área general.`);
                const generalErrorMessage = Array.isArray(errors[fieldName])
                                            ? errors[fieldName].map(e => e.message || e).join('<br>')
                                            : errors[fieldName];
                // Añadir al div general de errores
                quickEditErrorMessage.append(`<div><strong>${fieldName === '__all__' ? 'Error General' : fieldName}:</strong> ${generalErrorMessage}</div>`);
            }
        }
        // Mostrar el div general solo si tiene contenido
        if (quickEditErrorMessage.html() !== '') {
            quickEditErrorMessage.show();
        }
        // Enfocar el primer campo con error
        if (firstErrorField) {
            firstErrorField.focus();
        } else if (quickEditErrorMessage.is(':visible')) {
            // Scroll al mensaje de error general si es el único
            quickEditPanel.animate({ scrollTop: 0 }, "fast");
        }
    }

    // Resaltar fila y quitar resaltado de otras
    function highlightTableRow(detalleId) {
        tableBody.find('tr.table-info').removeClass('table-info');
        if(detalleId) {
            const rowToHighlight = $(`#detalle-row-${detalleId}`);
            if(rowToHighlight.length) {
                rowToHighlight.addClass('table-info');
            } else {
                console.warn(`No se encontró la fila #detalle-row-${detalleId} para resaltar.`);
            }
        }
    }

    // Cargar datos en el formulario fijo vía AJAX GET
    function fetchAndLoadDetail(detalleId) {
        if (!detalleId) {
            console.error("fetchAndLoadDetail llamado sin detalleId.");
            return;
        }
        console.log(`FUNC fetchAndLoadDetail: Iniciando carga para ID: ${detalleId}`);

        quickEditForm.find('button').prop('disabled', true);
        highlightTableRow(null);

        if (typeof getDetalleJsonUrlBase === 'undefined' || !getDetalleJsonUrlBase) {
             console.error("¡ERROR CRÍTICO! getDetalleJsonUrlBase no está definida. Revisa el script en la plantilla HTML.");
             alert("Error de configuración: No se puede obtener la URL base para cargar datos.");
             quickEditForm.find('button').prop('disabled', false);
             return;
        }
        const url = getDetalleJsonUrlBase + detalleId + '/';
        console.log(`FUNC fetchAndLoadDetail: URL de petición GET: ${url}`);

        $.ajax({
            url: url,
            type: 'GET',
            dataType: 'json',
            success: function(data) {
                console.log(`FUNC fetchAndLoadDetail: Datos recibidos para ID ${detalleId}:`, data);
                clearFormErrors();

                console.log("--- Antes del bucle .each() para poblar formulario ---");
                const foundIds = quickEditForm.find('[id^="id_"]').map(function() { return this.id; }).get();
                console.log("IDs encontrados dentro del form #quick-edit-form que empiezan con 'id_':", foundIds);
                let camposPoblados = 0;

                quickEditForm.find('[name]').each(function() {
                    camposPoblados++;
                    const fieldName = $(this).attr('name');
                    const inputId = `id_${fieldName}`; // <-- CORREGIDO: Usar ID estándar
                    const fieldElement = $(`#${inputId}`); // <-- CORREGIDO: Buscar ID estándar

                    // No mostrar log para csrf o el hidden ref
                    if(fieldName !== 'csrfmiddlewaretoken' && fieldName !== 'detalle_id_hidden_field_ref') {
                        console.log(`--> Dentro del bucle: Procesando campo con name="${fieldName}" (ID esperado: ${inputId})`);
                    }

                    if (!fieldElement.length) {
                        if(fieldName !== 'csrfmiddlewaretoken' && fieldName !== 'detalle_id_hidden_field_ref') {
                            console.warn(`    WARN: Elemento HTML con ID #${inputId} NO ENCONTRADO en el DOM.`);
                        }
                    }

                    if (!data.hasOwnProperty(fieldName)) {
                         if (fieldElement.length) {
                            console.warn(`    WARN: Campo ${fieldName} (ID: ${inputId}) encontrado en el form, pero NO recibido en los datos JSON.`);
                         }
                    }

                    if (fieldElement.length && data.hasOwnProperty(fieldName)) {
                        const valorRecibido = data[fieldName];
                         // No mostrar log para csrf
                         if(fieldName !== 'csrfmiddlewaretoken') {
                             console.log(`    OK: Poblando campo ${fieldName} (ID: ${inputId}) con valor:`, valorRecibido);
                         }

                        try {
                            if (fieldElement.is(':checkbox')) {
                                fieldElement.prop('checked', valorRecibido);
                            } else {
                                fieldElement.val(valorRecibido === null ? '' : valorRecibido);
                            }
                            fieldElement.removeClass('is-invalid');
                        } catch (e) {
                            console.error(`    ERROR JS: Error al intentar asignar valor al campo ${fieldName} (ID: ${inputId})`, e);
                        }
                    }
                });

                console.log(`--- Después del bucle .each(). Iteraciones realizadas: ${camposPoblados} ---`);
                if (camposPoblados <= 2) {
                     console.error("¡ERROR! El selector quickEditForm.find('[name]') no encontró campos de formulario editables con atributo 'name'. Revisa el HTML del panel y cómo se renderizan los campos con {{ field }}.");
                }

                applyBootstrapClassesToQuickEditForm(); // Aplicar clases después

                quickEditForm.attr('data-detalle-id', detalleId);
                $('#quick-edit-detalle-id-hidden').val(detalleId);
                currentEditingId = detalleId;

                quickEditPersonName.text(`${data.nombre_completo_externo || `ID Ext: ${detalleId}`} (CI: ${data.ci_externo || 'N/A'})`);

                if (!quickEditPanel.is(':visible')) {
                    console.log("FUNC fetchAndLoadDetail: Mostrando panel...");
                    quickEditPanel.slideDown(function() {
                         console.log("FUNC fetchAndLoadDetail: Panel mostrado, poniendo foco...");
                         quickEditForm.find('input:not([type=hidden]):not(:disabled):first, textarea:not(:disabled):first, select:not(:disabled):first').focus();
                    });
                } else {
                     console.log("FUNC fetchAndLoadDetail: Panel ya visible, poniendo foco...");
                     quickEditForm.find('input:not([type=hidden]):not(:disabled):first, textarea:not(:disabled):first, select:not(:disabled):first').focus();
                }

                $('html, body').animate({
                    scrollTop: quickEditPanel.offset().top - 70
                }, 300);

                highlightTableRow(detalleId);

            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error(`FUNC fetchAndLoadDetail: Error en AJAX GET para ID ${detalleId}. Status: ${textStatus}, Error: ${errorThrown}`, jqXHR.responseText);
                alert(`Error al cargar los datos del registro ${detalleId}. Verifique la consola.`);
                quickEditPanel.slideUp();
                highlightTableRow(null);
            },
            complete: function() {
                quickEditForm.find('button').prop('disabled', false);
            }
        });
    }

    // Actualizar los datos en la fila correspondiente de la tabla
    function updateTableRow(detalleId, updatedData) {
        const row = $(`#detalle-row-${detalleId}`);
        if (row.length) {
            console.log(`FUNC updateTableRow: Actualizando fila ${detalleId} con datos:`, updatedData);
            row.find('td[data-field]').each(function() {
                const fieldName = $(this).data('field');
                if (updatedData.hasOwnProperty(fieldName)) {
                    let newValue = updatedData[fieldName];
                    // Formateo
                     if (typeof newValue === 'number' || (typeof newValue === 'string' && newValue !== '' && !isNaN(parseFloat(newValue)))) {
                         if (['omision_sancion', 'abandono_dias', 'abandono_sancion', 'faltas_dias', 'faltas_sancion', 'atrasos_sancion', 'vacacion', 'viajes', 'bajas_medicas', 'pcgh', 'perm_excep', 'asuetos', 'psgh', 'pcgh_embar_enf_base', 'actividad_navidad', 'iza_bandera'].includes(fieldName)) {
                             const num = parseFloat(newValue);
                             if (!isNaN(num)) {
                                 newValue = num.toFixed(2);
                             }
                         }
                    }
                    newValue = (newValue === null ? "" : newValue);
                    $(this).text(newValue);

                    if (fieldName === 'observaciones') {
                         const obsText = newValue || "";
                         $(this).attr('title', obsText);
                         $(this).text(obsText.substring(0, 20) + (obsText.length > 20 ? '...' : ''));
                    }
                }
            });
            row.addClass('table-success').delay(1500).queue(function(next) {
                $(this).removeClass('table-success');
                next();
            });
        } else {
            console.warn(`FUNC updateTableRow: No se encontró la fila #detalle-row-${detalleId} para actualizar.`);
        }
    }

    // Guardar los datos vía AJAX POST
    function saveDetail(andLoadNext = false) {
        if (isSaving) {
             console.warn("FUNC saveDetail: Intento de doble envío bloqueado.");
             return;
        }
        const detalleId = quickEditForm.attr('data-detalle-id');
        if (!detalleId) {
            alert("Error: No hay un registro seleccionado para guardar (data-detalle-id no encontrado en el form).");
            return;
        }

        console.log(`FUNC saveDetail: Iniciando guardado para ID: ${detalleId}. Cargar siguiente: ${andLoadNext}`);

        isSaving = true;
        clearFormErrors();
        saveButton.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Guardando...');
        saveNextButton.prop('disabled', true);
        cancelButton.prop('disabled', true);

        if (typeof saveDetalleUrlBase === 'undefined' || !saveDetalleUrlBase) {
             console.error("¡ERROR CRÍTICO! saveDetalleUrlBase no está definida. Revisa el script en la plantilla HTML.");
             alert("Error de configuración: No se puede obtener la URL base para guardar datos.");
             isSaving = false;
             saveButton.prop('disabled', false).html('<i class="fa fa-save"></i> Guardar Cambios');
             saveNextButton.prop('disabled', false);
             cancelButton.prop('disabled', false);
             return;
        }
        const url = saveDetalleUrlBase + detalleId + '/';
        const formData = quickEditForm.serialize();
        console.log(`FUNC saveDetail: URL de petición POST: ${url}`);

        $.ajax({
            url: url,
            type: 'POST',
            data: formData,
            dataType: 'json',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(response) {
                console.log(`FUNC saveDetail: Respuesta recibida para ID ${detalleId}:`, response);
                if (response.status === 'success') {
                    updateTableRow(detalleId, response.updated_data);
                    console.log("FUNC saveDetail: Guardado exitoso.");

                    if (andLoadNext) {
                        loadNextDetail();
                    }
                } else {
                    console.error("FUNC saveDetail: Error de validación del backend.", response.errors);
                    showFormErrors(response.errors || {'_error': 'Error desconocido del servidor.'});
                }
            },
            error: function(jqXHR, textStatus, errorThrown) { // <--- ESTA ES LA SECCIÓN A MODIFICAR/ASEGURAR
                 console.error(`FUNC saveDetail: Error en AJAX POST para ID ${detalleId}. Status Code: ${jqXHR.status}, TextStatus: ${textStatus}, ErrorThrown: ${errorThrown}`, jqXHR.responseText);
                 
                 let errorMessage = "Ocurrió un error inesperado al intentar guardar.";
                 // Intentar obtener el mensaje de la respuesta JSON del servidor
                 if (jqXHR.responseJSON && jqXHR.responseJSON.message) {
                     errorMessage = jqXHR.responseJSON.message;
                 } else if (jqXHR.statusText && jqXHR.status !== 0) { 
                     errorMessage = `Error ${jqXHR.status}: ${jqXHR.statusText}`;
                 }

                 // --- MANEJO ESPECÍFICO PARA ERROR DE ESTADO (403) ---
                 if (jqXHR.status === 403) { // 403 Forbidden (nuestro caso para control de estado)
                     // Mostrar el mensaje de error en el panel de edición rápida
                     quickEditErrorMessage.html(`<strong>Acción no permitida:</strong> ${errorMessage}`).show();
                     // Opcional: usar un alert si prefieres
                     // alert(`Acción no permitida: ${errorMessage}`);
                     
                     // Opcional: cerrar el panel y limpiar, ya que la edición no es posible
                     // quickEditPanel.slideUp(); 
                     // highlightTableRow(null); 
                     // currentEditingId = null;
                     // clearFormErrors(); 
                 } else if (jqXHR.responseJSON && jqXHR.responseJSON.errors) {
                     // Si el backend devuelve errores de formulario estructurados en un error HTTP (ej. 400)
                     showFormErrors(jqXHR.responseJSON.errors);
                 } else {
                     // Error genérico de red o servidor
                     quickEditErrorMessage.html(`<strong>Error de Red/Servidor:</strong> ${errorMessage}`).show();
                 }
            },
            complete: function() {
                console.log(`FUNC saveDetail: Petición AJAX POST para ID ${detalleId} completada.`);
                isSaving = false;
                saveButton.prop('disabled', false).html('<i class="fa fa-save"></i> Guardar Cambios');
                saveNextButton.prop('disabled', false);
                cancelButton.prop('disabled', false);
            }
        });
    }

    // Cargar el siguiente detalle en la secuencia visible
    function loadNextDetail() {
         console.log("FUNC loadNextDetail: Intentando cargar el siguiente...");
        if (typeof visibleDetailIds === 'undefined' || !Array.isArray(visibleDetailIds) || visibleDetailIds.length === 0) {
            console.warn("FUNC loadNextDetail: visibleDetailIds no disponible o vacío.");
            alert("No hay más registros visibles para cargar.");
            return;
        }
        if (currentEditingId === null) {
            console.warn("FUNC loadNextDetail: No hay ID actual (currentEditingId es null).");
            return;
        }

        const currentIdInt = parseInt(currentEditingId);
        const currentIndex = visibleDetailIds.indexOf(currentIdInt);
        console.log(`FUNC loadNextDetail: ID actual: ${currentIdInt}, Índice: ${currentIndex}, Lista IDs:`, visibleDetailIds);

        if (currentIndex !== -1 && currentIndex < visibleDetailIds.length - 1) {
            const nextId = visibleDetailIds[currentIndex + 1];
            console.log(`FUNC loadNextDetail: Cargando siguiente ID: ${nextId}`);
            fetchAndLoadDetail(nextId); // Llamada para cargar el siguiente
        } else {
            console.log("FUNC loadNextDetail: Se alcanzó el final o ID actual no encontrado en la lista.");
            alert("Ha llegado al final de los registros visibles en esta página/filtro.");
            quickEditPanel.slideUp();
            highlightTableRow(null);
            currentEditingId = null;
        }
    }

    // --- Event Listeners ---
    console.log("Adjuntando listener de clic a #asistencia-table-body para .quick-edit-btn...");

    tableBody.on('click', '.quick-edit-btn', function(event) {
        console.log("Listener delegado: ¡CLIC EN BOTÓN .quick-edit-btn DETECTADO!");
        const detalleId = $(this).data('detalle-id');
        console.log("Listener delegado: Detalle ID obtenido:", detalleId);
        if (detalleId) {
             fetchAndLoadDetail(detalleId);
        } else {
             console.error("Listener delegado: No se pudo obtener el atributo data-detalle-id del botón.");
             alert("Error: No se pudo identificar el registro a editar.");
        }
    });

    console.log("Listener de clic para .quick-edit-btn adjuntado.");

    quickEditForm.on('submit', function(e) {
        console.log("Listener submit: Formulario #quick-edit-form enviado.");
        e.preventDefault();
        saveDetail(false);
    });

    saveNextButton.on('click', function() {
        console.log("Listener click: Botón #quick-edit-save-next-btn presionado.");
        saveDetail(true);
    });

    cancelButton.on('click', function() {
        console.log("Listener click: Botón #quick-edit-cancel-btn presionado.");
        quickEditPanel.slideUp();
        highlightTableRow(null);
        currentEditingId = null;
        clearFormErrors();
    });

    closeButton.on('click', function() {
        console.log("Listener click: Botón #quick-edit-close presionado.");
        quickEditPanel.slideUp();
        highlightTableRow(null);
        currentEditingId = null;
        clearFormErrors();
    });

    console.log("Todos los listeners adjuntados. Script listo.");

}); // Fin $(document).ready