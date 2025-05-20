// boletas/static/boletas/js/disenador_boleta.js

$(document).ready(function() {
    console.log("--- DOCUMENT READY: Inicio disenador_boleta.js ---");

    // --- 1. Leer datos pasados desde Django ---
    var jsonDataElement = document.getElementById('django-to-js-data');
    var djangoServerData = {}; // Datos crudos del tag script

    if (jsonDataElement) {
        try {
            djangoServerData = JSON.parse(jsonDataElement.textContent);
            console.log("Paso 1: Datos leídos del tag <script>:", JSON.stringify(djangoServerData, null, 2));
        } catch (e) {
            console.error("Paso 1: ERROR al parsear JSON desde el tag <script>:", e);
            console.log("Contenido del tag script que causó el error:", jsonDataElement.textContent);
        }
    } else {
        console.warn("Paso 1: Elemento <script id='django-to-js-data'> NO encontrado en el DOM.");
    }

    // Extraer los strings JSON específicos, con fallback a strings JSON vacíos/por defecto
    var plantillaDiseñoJSONString = djangoServerData.plantillaDiseñoJSONString || '{}';
    var placeholdersDisponiblesJSONString = djangoServerData.placeholdersDisponiblesJSONString || '[]';

    console.log("Paso 2a: String JSON del diseño extraído (primeros 300 chars):", plantillaDiseñoJSONString.substring(0, 300) + (plantillaDiseñoJSONString.length > 300 ? "..." : ""));
    console.log("Paso 2b: String JSON de placeholders extraído:", placeholdersDisponiblesJSONString);

    // --- 2. Parsear los strings JSON a objetos/arrays JavaScript ---
    var plantillaDiseñoObjetoJS; // Para el diseño del canvas de Fabric.js
    var placeholdersArray;       // Para la lista de placeholders

    try {
        plantillaDiseñoObjetoJS = JSON.parse(plantillaDiseñoJSONString);
        console.log("Paso 3a: Objeto JS del diseño PARSEADO:", JSON.stringify(plantillaDiseñoObjetoJS, null, 2));
    } catch (e) {
        console.error("Paso 3a: ERROR al parsear plantillaDiseñoJSONString:", e);
        plantillaDiseñoObjetoJS = {};
    }

    try {
        placeholdersArray = JSON.parse(placeholdersDisponiblesJSONString);
        if (!Array.isArray(placeholdersArray)) placeholdersArray = [];
        console.log("Paso 3b: Array de placeholders PARSEADO:", placeholdersArray);
    } catch (e) {
        console.error("Paso 3b: ERROR al parsear placeholdersDisponiblesJSONString:", e);
        placeholdersArray = [];
    }

    // --- 3. Inicialización del Canvas de Fabric.js ---
    var canvas = new fabric.Canvas('boletaCanvas', {
        width: 595,  // A4 width a ~72 DPI
        height: 842, // A4 height a ~72 DPI
        backgroundColor: '#ffffff' // Fondo blanco
    });
    window.myFabricCanvas = canvas;
    console.log("Paso 4: Canvas de Fabric.js inicializado.");
    $('#canvasWidth').text(canvas.getWidth());
    $('#canvasHeight').text(canvas.getHeight());
    
    // --- Variables de estado para UX ---
    var currentZoom = 1.0;
    var MIN_ZOOM = 0.1; // Permitir más zoom out
    var MAX_ZOOM = 4.0; // Permitir más zoom in
    var ZOOM_STEP = 0.1;
    var gridVisible = false;
    var gridSpacing = 20; // Espaciado lógico
    var gridColor = '#e0e0e0';
    var snapEnabled = false;
    var snapThreshold = gridSpacing / 2; // Snap si está a menos de la mitad del espaciado
    // ***** INICIO: VARIABLES Y FUNCIONES PARA UNDO/REDO *****
    var undoStack = [];
    var redoStack = [];
    var maxHistory = 50; // Limitar el historial a 50 estados
    var currentState = null; // Para evitar guardar estados idénticos consecutivamente
    var propsToIncludeInHistory = ['isGridLine', 'isPlaceholder', 'placeholderOriginalLabel']; // Propiedades 

    function saveCanvasState(actionType) {
    // No guardar estado si es solo un renderizado o una selección sin cambio real
    // O si el nuevo estado es idéntico al anterior (evitar duplicados por renders)
        var newStateJSON = JSON.stringify(canvas.toJSON(propsToIncludeInHistory));
        
        if (currentState === newStateJSON) {
            // console.log("Undo/Redo: Estado idéntico, no guardado.", actionType);
            return;
        }
        
        console.log("Undo/Redo: Guardando estado para acción:", actionType);
        redoStack = []; // Limpiar redoStack en cualquier nueva acción
        if (undoStack.length >= maxHistory) {
            undoStack.shift(); // Eliminar el estado más antiguo si se excede el límite
        }
        undoStack.push(newStateJSON);
        currentState = newStateJSON; // Actualizar el estado actual
        updateUndoRedoButtons();
    }

    function loadStateFromJSON(jsonString, from) {
        console.log(`Undo/Redo: Cargando estado desde ${from}. JSON (primeros 100): ${jsonString.substring(0,100)}...`);
        // Deshabilitar temporalmente el guardado de estado para evitar bucles
        var originalSaveStateEnabled = isSaveStateEnabled;
        isSaveStateEnabled = false;

        canvas.loadFromJSON(jsonString, function() {
            canvas.renderAll();
            console.log("Undo/Redo: Estado cargado y renderizado desde", from);
            // Volver a habilitar el guardado de estado después de un pequeño retraso
            setTimeout(function() {
                isSaveStateEnabled = originalSaveStateEnabled;
                var activeObj = canvas.getActiveObject();
                if (activeObj) {
                    updatePropertiesPanel(activeObj);
                } else {
                    updatePropertiesPanel(null);
                }
            }, 100);
        });
    }

    function undo() {
        if (undoStack.length > 1) {
            var stateToRedo = undoStack.pop();
            redoStack.push(stateToRedo);
            var prevStateJSON = undoStack[undoStack.length - 1];
            loadStateFromJSON(prevStateJSON, "undo");
            currentState = prevStateJSON;
        } else {
            console.log("Undo/Redo: No hay más estados para deshacer o solo queda el inicial.");
        }
        updateUndoRedoButtons();
    }

    function redo() {
        if (redoStack.length > 0) {
            var stateToUndo = redoStack.pop();
            undoStack.push(stateToUndo);
            if (undoStack.length > maxHistory) {
                undoStack.shift();
            }
            loadStateFromJSON(stateToUndo, "redo");
            currentState = stateToUndo;
        } else {
            console.log("Undo/Redo: No hay estados para rehacer.");
        }
        updateUndoRedoButtons();
    }

    function updateUndoRedoButtons() {
        $('#undoCanvas').prop('disabled', undoStack.length <= 1);
        $('#redoCanvas').prop('disabled', redoStack.length === 0);
        console.log(`Undo/Redo: Botones actualizados. Undo: ${undoStack.length}, Redo: ${redoStack.length}`);
    }

    var isSaveStateEnabled = true; // Control para evitar guardar estado durante loadFromJSON
    // ***** FIN: NUEVAS VARIABLES Y FUNCIONES PARA UNDO/REDO *****



    $('#gridSpacingValue').text(gridSpacing); // Mostrar espaciado


    // --- 4. Cargar Diseño Existente en el Canvas ---
    if (plantillaDiseñoObjetoJS && typeof plantillaDiseñoObjetoJS === 'object' && Object.keys(plantillaDiseñoObjetoJS).length > 0 && plantillaDiseñoObjetoJS.hasOwnProperty('objects')) {
        console.log("Paso 5: Intentando cargar diseño en el canvas desde objeto JS...");
        isSaveStateEnabled = false; // ***** AÑADIR/MODIFICAR ESTA LÍNEA *****
        canvas.loadFromJSON(plantillaDiseñoObjetoJS, function() {
            canvas.renderAll();
            console.log("Paso 5a (Callback Principal): Diseño cargado en el lienzo y renderizado.");
            // Guardar el estado inicial DESPUÉS de cargar
            isSaveStateEnabled = true; // ***** AÑADIR ESTA LÍNEA *****
            saveCanvasState("initialLoad"); // ***** AÑADIR ESTA LÍNEA *****
        }, function(o, object) {
            console.log("Paso 5b (Callback por Objeto): Objeto Fabric procesado:", object.type);
        });
    } else {
        console.log("Paso 5: No hay diseño válido para cargar.");
        saveCanvasState("initialEmpty"); // ***** AÑADIR/MODIFICAR ESTA LÍNEA *****
    }

    // ***** INICIO: Eventos del Canvas para Guardar Estado *****
    var modificationEvents = [
        'object:added', 'object:removed', 'object:modified', 
        'object:skewing',
    ];

    modificationEvents.forEach(function(eventName) {
        canvas.on(eventName, function(options) {
            if (isSaveStateEnabled) {
                if (options && options.target && options.target.isGridLine) {
                    return;
                }
                console.log(`Undo/Redo: Evento detectado - ${eventName}`);
                saveCanvasState(eventName);
            }
        });
    });
    // ***** FIN: Eventos del Canvas para Guardar Estado *****


    // --- 5. Guardado del Diseño (Al enviar el formulario) ---
    $('#formPlantilla').on('submit', function(e) {
        // Obtener el objeto JSON, pero EXCLUYENDO las líneas de la cuadrícula
        var canvasJSON = canvas.toJSON(['isGridLine', /* otras propiedades personalizadas si las tienes */]);

        // Filtrar los objetos que son líneas de la cuadrícula ANTES de serializar
        if (canvasJSON && canvasJSON.objects) {
            canvasJSON.objects = canvasJSON.objects.filter(function(obj) {
                return !obj.isGridLine; // Mantener solo los que NO son gridLine
            });
        }

        var canvasJSONString = JSON.stringify(canvasJSON);
        $('#datos_diseno_json_input').val(canvasJSONString);
        console.log("Paso 6 (Evento Submit): Diseño (SIN GRID) guardado en input hidden:", canvasJSONString.substring(0, 300) + "...");
    });

    // --- 6. Herramientas ---

    // Botón Texto Fijo
    $('#addText').on('click', function() {
        console.log("Herramienta: Clic 'Texto Fijo'.");
        var itext = new fabric.IText('Texto Editable', {
            left: 50, top: 50, fontFamily: 'Arial', fontSize: 12, fill: '#000000', padding: 5
        });
        canvas.add(itext);
        canvas.setActiveObject(itext);
        canvas.renderAll();
        updatePropertiesPanel(itext);
        console.log("Herramienta: Texto Fijo añadido.");
        if (isSaveStateEnabled) saveCanvasState("addText-setActive"); // ***** AÑADIR ESTA LÍNEA *****
    });

    // Botón Placeholder
    $('#addPlaceholder').on('click', function() {
        var selectedOption = $('#placeholderSelector option:selected');
        var placeholderId = selectedOption.val();
        var placeholderLabel = selectedOption.data('label') || placeholderId;
        if (!placeholderId) { alert("Seleccione un campo."); return; }
        console.log(`Herramienta: Clic 'Añadir Placeholder'. ID: ${placeholderId}`);
        var placeholderText = new fabric.IText(placeholderId, {
            left: 70, top: 70, fontFamily: 'Courier New', fontSize: 11, fill: '#0000FF',
            isPlaceholder: true, placeholderOriginalLabel: placeholderLabel, padding: 5,
            borderColor: 'blue', cornerColor: 'blue'
        });
        canvas.add(placeholderText);
        canvas.setActiveObject(placeholderText);
        canvas.renderAll();
        updatePropertiesPanel(placeholderText); // <-- LLAMADA EXPLÍCITA
        console.log("Herramienta: Placeholder añadido.");
        if (isSaveStateEnabled) saveCanvasState("addPlaceholder-setActive"); // ***** AÑADIR ESTA LÍNEA *****
    });

    // Botón Línea
    $('#addLine').on('click', function() {
        console.log("Herramienta: Clic 'Línea'.");
        var line = new fabric.Line([50, 100, 250, 100], {
            stroke: '#000000', strokeWidth: 1, selectable: true
        });
        canvas.add(line);
        canvas.setActiveObject(line);
        canvas.renderAll();
        updatePropertiesPanel(line);
        console.log("Herramienta: Línea añadida.");
        if (isSaveStateEnabled) saveCanvasState("addLine-setActive"); // ***** AÑADIR ESTA LÍNEA *****
    });

    // Botón Rectángulo
    $('#addRect').on('click', function() {
        console.log("Herramienta: Clic 'Rectángulo'.");
        var rect = new fabric.Rect({
            left: 100, top: 100, fill: 'transparent', stroke: '#000000',
            strokeWidth: 1, width: 200, height: 100, selectable: true
        });
        canvas.add(rect);
        canvas.setActiveObject(rect);
        canvas.renderAll();
        updatePropertiesPanel(rect); // <-- LLAMADA EXPLÍCITA
        console.log("Herramienta: Rectángulo añadido.");
        if (isSaveStateEnabled) saveCanvasState("addRect-setActive"); // ***** AÑADIR ESTA LÍNEA *****
    });

    // Botón Imagen (disparador)
    $('#addImage').on('click', function() {
        console.log("Herramienta: Clic 'Imagen', disparando input file...");
        $('#imageLoader').click();
        if (isSaveStateEnabled) saveCanvasState("addImage-setActive"); // ***** AÑADIR ESTA LÍNEA *****
    });

    // Manejador input file imagen
    $('#imageLoader').on('change', function(e) {
        console.log("Herramienta: Archivo seleccionado en 'imageLoader'.");
        var file = e.target.files[0];
        if (!file) { console.log("Herramienta: No se seleccionó archivo."); return; }
        console.log("Herramienta: Procesando archivo:", file.name);

        var reader = new FileReader();
        reader.onload = function(f) {
            console.log("Herramienta: FileReader cargó el archivo.");
            var data = f.target.result;
            fabric.Image.fromURL(data, function(img) {
                console.log("Herramienta: Imagen creada por Fabric.js.");
                img.scaleToWidth(150); // Escalar por defecto
                img.set({ left: 100, top: 150 });
                canvas.add(img);
                canvas.setActiveObject(img);
                canvas.renderAll();
                updatePropertiesPanel(img); // <-- LLAMADA EXPLÍCITA
                console.log("Herramienta: Imagen añadida.");
                if (isSaveStateEnabled) saveCanvasState("imageLoader-setActive"); // ***** AÑADIR ESTA LÍNEA *****
            });
        };
        reader.onerror = function(err) { console.error("Herramienta: Error FileReader:", err); alert("Error al cargar imagen."); };
        reader.readAsDataURL(file);
        $(this).val(''); // Reset input
        console.log("Herramienta: Input 'imageLoader' reseteado.");
        
    });

    // Botón Eliminar Seleccionado
    $('#deleteSelected').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (activeObject) {
            if (activeObject.type === 'activeSelection') { // Si es un grupo
                activeObject.forEachObject(function(obj) {
                    canvas.remove(obj); // Dispara 'object:removed' por cada uno
                });
                canvas.discardActiveObject().renderAll();
            } else { // Objeto individual
                canvas.remove(activeObject); // Dispara 'object:removed'
            }
            // No necesitamos llamar a saveCanvasState aquí, 'object:removed' lo hará
            updatePropertiesPanel(null);
            // canvas.renderAll(); // renderAll se hace dentro de object:removed o después
        }
    });

    $('#sendToBack').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (activeObject) {
            // Si es una selección múltiple (grupo), sendToBack se aplica a todos
            if (activeObject.type === 'activeSelection') {
                activeObject.getObjects().forEach(function(obj) {
                    canvas.sendToBack(obj);
                });
            } else {
                canvas.sendToBack(activeObject);
            }
            canvas.discardActiveObject(); // Deseleccionar
            canvas.renderAll();
            // No hay objeto activo para pasar a updatePropertiesPanel después de discard
            // Se llamará cuando el usuario seleccione algo de nuevo o desde 'selection:cleared'
            updatePropertiesPanel(null); 
            console.log("Orden Z: Objeto(s) enviado(s) al fondo.");
        }
    });

    $('#bringToFront').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (activeObject) {
            if (activeObject.type === 'activeSelection') {
                activeObject.getObjects().forEach(function(obj) {
                    canvas.bringToFront(obj);
                });
            } else {
                canvas.bringToFront(activeObject);
            }
            canvas.discardActiveObject();
            canvas.renderAll();
            updatePropertiesPanel(null);
            console.log("Orden Z: Objeto(s) traído(s) al frente.");
        }
    });

    $('#sendBackwards').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (activeObject) {
            // Para 'activeSelection', sendBackwards puede ser complejo o no tener el efecto deseado en todos los objetos del grupo.
            // Fabric.js lo aplica al grupo como un todo si es posible.
            canvas.sendBackwards(activeObject);
            // Es importante re-seleccionar para que el panel se actualice con el objeto correcto
            // y para que el estado de los botones sea correcto.
            var newActiveObject = canvas.getActiveObject(); // Podría haber cambiado si el grupo se rompió
            if (newActiveObject) {
                canvas.setActiveObject(newActiveObject); // Re-seleccionar
            }
            canvas.renderAll();
            updatePropertiesPanel(newActiveObject || null); // Actualizar panel
            console.log("Orden Z: Objeto/Grupo enviado atrás una capa.");
        }
    });

    $('#bringForwards').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (activeObject) {
            canvas.bringForward(activeObject);
            var newActiveObject = canvas.getActiveObject();
            if (newActiveObject) {
                canvas.setActiveObject(newActiveObject);
            }
            canvas.renderAll();
            updatePropertiesPanel(newActiveObject || null);
            console.log("Orden Z: Objeto/Grupo traído adelante una capa.");
        }
    });

    // --- 7. Panel de Propiedades ---

    function updatePropertiesPanel(target) {
        // Ocultar todos los grupos específicos y el botón eliminar
        $('.prop-group:not(.common-props)').hide();
        $('#deleteSelected').hide();
        // Limpiar valores (opcional, pero recomendado)
        $('#propertiesPanel input[type="text"], #propertiesPanel input[type="number"], #propertiesPanel select').val('');
        $('#propertiesPanel input[type="color"]').val('#000000');
        $('.prop-style-button').removeClass('active');
        $('.common-props-extra').hide(); 

        if (!target) {
            console.log("Panel Propiedades: No hay objeto seleccionado.");
            // Limpiar valores explícitamente al deseleccionar
            //$('#propertiesPanel input[type="text"], #propertiesPanel input[type="number"], #propertiesPanel select').val('');
             //$('#propertiesPanel input[type="color"]').val('#000000');
             //$('.prop-style-button').removeClass('active');
            return;
        }

        console.log("Panel Propiedades: Actualizando para tipo:", target.type);
        $('#deleteSelected').show(); // Mostrar botón eliminar

        // Llenar propiedades comunes
        $('.common-props').show();
        $('#propLeft').val(Math.round(target.left));
        $('#propTop').val(Math.round(target.top));
        $('#propLeft, #propTop').prop('disabled', false);
        $('#propLeft').val(Math.round(target.left));
        $('.common-props-extra').show(); // Mostrar botones de orden Z

        // Llenar propiedades específicas y mostrar grupo
        if (target.type === 'i-text') {
            $('.text-props').show();
            $('#propText').val(target.text);
            $('#propFontFamily').val(target.fontFamily || 'Arial'); // Default si no tiene
            $('#propFontSize').val(target.fontSize || 12);
            $('#propFillText').val(target.fill || '#000000');
            $('#propTextAlign').val(target.textAlign || 'left');
            // Actualizar botones de estilo
            target.fontWeight === 'bold' || target.fontWeight >= 700 ? $('#propFontWeight').addClass('active') : $('#propFontWeight').removeClass('active');
            target.fontStyle === 'italic' ? $('#propFontStyle').addClass('active') : $('#propFontStyle').removeClass('active');
            target.underline ? $('#propUnderline').addClass('active') : $('#propUnderline').removeClass('active');

        } else if (target.type === 'line') {
            $('.line-props').show();
            $('#propStrokeLine').val(target.stroke || '#000000');
            $('#propStrokeWidthLine').val(target.strokeWidth || 1);

        } else if (target.type === 'rect') {
            $('.rect-props').show();
            // Habilitar controles de rectángulo
            $('#propSolidFillRect, #propStrokeRect, #propStrokeWidthRect').prop('disabled', false);

            // Comprobar si el relleno NO es transparente o nulo
            var hasSolidFill = target.fill && target.fill !== 'transparent';
            $('#propSolidFillRect').prop('checked', hasSolidFill); // Marcar checkbox si tiene relleno

            // Llenar valores
            // Si tiene relleno sólido, mostrar el color actual, sino default a blanco
            $('#propFillRect').val(hasSolidFill ? target.fill : '#ffffff');
            $('#propStrokeRect').val(target.stroke || '#000000');
            $('#propStrokeWidthRect').val(target.strokeWidth === undefined ? 1 : target.strokeWidth);

            // Habilitar/deshabilitar el color picker de relleno según el checkbox
            $('#propFillRect').prop('disabled', !hasSolidFill);


        } else if (target.type === 'image') {
            $('.image-props').show();
            // Aquí podrías mostrar dimensiones (target.width * target.scaleX)
            // o permitir cambiar la opacidad (target.opacity)
        }

        var objects = canvas.getObjects().filter(obj => !obj.isGridLine && obj.selectable); // Objetos reales seleccionables
        var currentIndex = -1;
        
        // Si el target es parte de una selección activa (grupo), no podemos obtener su índice individual fácilmente
        // así que deshabilitaremos los botones de orden individual para grupos por ahora.
        // O, si el target es el grupo en sí (ActiveSelection).
        if (target && target.type !== 'activeSelection' && objects.includes(target)) {
            currentIndex = objects.indexOf(target);
        } else if (target && target.type === 'activeSelection') {
            // Para grupos, podríamos deshabilitar o implementar lógica de grupo
            // Por ahora, deshabilitamos para simplificar
            currentIndex = -2; // Un valor especial para indicar grupo o no individual
        }


        if (currentIndex === -2) { // Si es un grupo o no se puede determinar el índice individual
            $('#sendToBack').prop('disabled', true);
            $('#sendBackwards').prop('disabled', true);
            $('#bringToFront').prop('disabled', true);
            $('#bringForwards').prop('disabled', true);
        } else {
            $('#sendToBack').prop('disabled', currentIndex === 0 || currentIndex === -1);
            $('#sendBackwards').prop('disabled', currentIndex === 0 || currentIndex === -1);
            $('#bringToFront').prop('disabled', currentIndex === objects.length - 1 || currentIndex === -1);
            $('#bringForwards').prop('disabled', currentIndex === objects.length - 1 || currentIndex === -1);
        }


    }

    // Eventos del Canvas para actualizar panel (sin cambios)
    canvas.on({
        'object:selected': function(e) { updatePropertiesPanel(e.target); },
        'selection:updated': function(e) { updatePropertiesPanel(e.target); },
        'selection:cleared': function(e) { updatePropertiesPanel(null); },
        'mouse:up': function(e) {
            // Este evento se dispara siempre al soltar el clic.
            // e.target contiene el objeto clickeado (si lo hay)
            console.log("Evento: mouse:up", e.target?.type);
            // Llamamos a updatePropertiesPanel OTRA VEZ aquí
            // para asegurarnos de que se actualice incluso si los eventos
            // de selección no se procesaron a tiempo en el primer clic.
            // Si ya se actualizó por object:selected, no pasa nada por llamarlo de nuevo.
            updatePropertiesPanel(e.target || canvas.getActiveObject()); // Usar e.target si existe, sino el objeto activo actual
        }
    });

    // Eventos de los Inputs/Selects del Panel para actualizar Canvas
    $('#propertiesPanel').on('input change', 'input, select', function() {
        var activeObject = canvas.getActiveObject();
        if (!activeObject) return;

        var inputElement = $(this);
        var propertyId = inputElement.attr('id');
        var propertyName = '';
        var value = inputElement.val();
        var isNumeric = false;
        var isCheckbox = inputElement.is(':checkbox'); // Detectar si es checkbox
        var needsRender = true; // Asumir que necesita renderizar

        console.log(`Panel -> Canvas: Cambio en ${propertyId}, Valor: ${value}`);

        // Mapeo ID a propiedad y conversión valor
        switch (propertyId) {
            case 'propLeft': propertyName = 'left'; value = parseFloat(value); break;
            case 'propTop': propertyName = 'top'; value = parseFloat(value); break;
            case 'propText': propertyName = 'text'; break;
            case 'propFontFamily': propertyName = 'fontFamily'; break;
            case 'propFontSize': propertyName = 'fontSize'; value = parseFloat(value); break;
            case 'propFillText': propertyName = 'fill'; break;
            case 'propTextAlign': propertyName = 'textAlign'; break;
            case 'propStrokeLine': propertyName = 'stroke'; break;
            case 'propStrokeWidthLine': propertyName = 'strokeWidth'; value = parseFloat(value); break;
            case 'propSolidFillRect': // Manejo especial para el checkbox
                propertyName = 'fill'; // La propiedad a cambiar es 'fill'
                var isChecked = inputElement.prop('checked');
                if (isChecked) {
                    // Si se marca, usar el color actual del picker o default a blanco
                    value = $('#propFillRect').val() || '#ffffff';
                    $('#propFillRect').prop('disabled', false); // Habilitar color picker
                } else {
                    value = 'transparent'; // Si se desmarca, hacer transparente
                    $('#propFillRect').prop('disabled', true); // Deshabilitar color picker
                }
                break; // Salir del switch para este caso especial
            case 'propFillRect': // El color picker de relleno
                propertyName = 'fill';
                // Solo aplicar si el checkbox está marcado
                if (!$('#propSolidFillRect').prop('checked')) {
                    console.log("Panel->Canvas: Ignorando cambio de color de relleno (checkbox desmarcado).");
                    return; // No hacer nada si el relleno no está activo
                }
                break; // Continuar para aplicar el color
            case 'propStrokeRect': propertyName = 'stroke'; break;
            case 'propStrokeWidthRect': propertyName = 'strokeWidth'; isNumeric = true; break;
            default: console.warn("Panel->Canvas: Cambio no manejado:", propertyId); return;
        }

        // Validar números
        if (isNumeric) {
            value = parseFloat(value);
            if (isNaN(value)) { console.warn(`Panel->Canvas: Valor numérico inválido para ${propertyName}`); return; }
            if (propertyName === 'strokeWidth' && value < 0) value = 0; // Evitar grosor negativo
        }

        try {
            var updatePayload = {};
            updatePayload[propertyName] = value;
            activeObject.set(updatePayload);
            var textRelatedProps = ['text', 'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'textAlign', 'underline'];
            if (textRelatedProps.includes(propertyName) && typeof activeObject.initDimensions === 'function') {
                activeObject.initDimensions();
            }
            canvas.renderAll();
            console.log(`Panel->Canvas: ${activeObject.type} actualizado (${propertyName}=${value}).`);
        } catch(e) { console.error(`Panel->Canvas: Error actualizando ${propertyName}:`, e); }
    });

    // Manejador para botones de estilo (Negrita/Cursiva/Subrayado)
    $('.prop-style-button').on('click', function() {
        var activeObject = canvas.getActiveObject();
        if (!activeObject || activeObject.type !== 'i-text') return;

        var button = $(this);
        var propertyName = button.data('prop'); // fontWeight, fontStyle, underline
        var valueOn = button.data('value-on');
        var valueOff = button.data('value-off');

        if (valueOn === 'true') valueOn = true; // Convertir string 'true' a booleano
        if (valueOff === 'false') valueOff = false; // Convertir string 'false' a booleano

        var currentValue = activeObject.get(propertyName);
        var newValue;

        // Lógica de alternancia (toggle)
        if (propertyName === 'fontWeight') {
             newValue = (currentValue === 'bold' || currentValue >= 700) ? valueOff : valueOn;
        } else { // Para fontStyle y underline
             newValue = (currentValue === valueOn) ? valueOff : valueOn;
        }

        // Actualizar estado visual del botón
        button.toggleClass('active', newValue === valueOn || (propertyName === 'fontWeight' && newValue === 'bold'));


        console.log(`Panel -> Canvas: Clic Botón Estilo. Prop: ${propertyName}, Nuevo Valor: ${newValue}`);

        try {
            var updatePayload = {};
            updatePayload[propertyName] = newValue;
            activeObject.set(updatePayload);

            if (typeof activeObject.initDimensions === 'function') {
                activeObject.initDimensions();
            }
            canvas.renderAll();
            console.log(`Panel -> Canvas: Estilo ${propertyName} actualizado a ${newValue} y renderizado.`);
        } catch(e) {
             console.error(`Panel -> Canvas: Error actualizando estilo ${propertyName}:`, e);
        }
    });

    // --- 8. Funciones y Eventos UX (Zoom, Grid, Snap) ---

    function updateZoomDisplay() { 
    var zoomValue = Math.round(canvas.getZoom() * 100);
    console.log("DEBUG: updateZoomDisplay ejecutado. Zoom actual del canvas:", canvas.getZoom(), "Valor a mostrar:", zoomValue);
    $('#zoomLevel').text(zoomValue); 
    }
    
    function zoomCanvas(delta) {
        var newZoom = canvas.getZoom() + delta * ZOOM_STEP;
        newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom)); // Limitar zoom

        // Hacer zoom hacia el centro del canvas actual
        var center = canvas.getCenter();
        canvas.zoomToPoint({ x: center.left, y: center.top }, newZoom);

        updateZoomDisplay();
        console.log("Zoom aplicado:", newZoom);
        // La cuadrícula se redibujará automáticamente si es necesario
    }

    $('#zoomIn').on('click', function() { zoomCanvas(1); });
    $('#zoomOut').on('click', function() { zoomCanvas(-1); });
    $('#zoomReset').on('click', function() {
        canvas.setZoom(1.0);
        canvas.viewportTransform = [1, 0, 0, 1, 0, 0]; // Resetear pan también
        updateZoomDisplay();
        canvas.renderAll(); // Asegurarse de renderizar después del reset
        console.log("Zoom Reset a 1.0");
    });

    updateZoomDisplay(); // Inicializar display

    // --- Grid (MODIFICADO para usar objetos Line) ---
    var gridLines = []; // Para mantener referencia a las líneas de la grid

    function drawGrid() {
        clearGrid(); // Limpiar grid anterior si existe
        if (!gridVisible) return;

        console.log("DEBUG: Dibujando Grid con objetos Line...");
        var canvasWidth = canvas.getWidth();
        var canvasHeight = canvas.getHeight();
        // El espaciado ahora es siempre el lógico (20px)
        // El zoom afectará visualmente el tamaño, no el número de líneas

        var lineOptions = {
            stroke: gridColor,
            strokeWidth: 1,
            selectable: false, // No seleccionable
            evented: false,    // No dispara eventos
            isGridLine: true   // Propiedad personalizada para identificarla
        };

        // Líneas verticales
        for (var x = gridSpacing; x < canvasWidth; x += gridSpacing) {
            var lineV = new fabric.Line([x, 0, x, canvasHeight], lineOptions);
            canvas.add(lineV);
            gridLines.push(lineV); // Guardar referencia
        }
        // Líneas horizontales
        for (var y = gridSpacing; y < canvasHeight; y += gridSpacing) {
            var lineH = new fabric.Line([0, y, canvasWidth, y], lineOptions);
            canvas.add(lineH);
            gridLines.push(lineH);
        }
        // Enviar las líneas de la cuadrícula al fondo para que no tapen otros objetos
        gridLines.forEach(line => canvas.sendToBack(line));

        canvas.renderAll(); // Renderizar para mostrar la nueva grid
        console.log("DEBUG: Grid dibujada con", gridLines.length, "líneas.");
    }

    function clearGrid() {
        if (gridLines.length > 0) {
             console.log("DEBUG: Limpiando", gridLines.length, "líneas de grid...");
             gridLines.forEach(line => canvas.remove(line));
             gridLines = []; // Vaciar el array de referencias
             canvas.renderAll(); // Renderizar para quitar las líneas
             console.log("DEBUG: Grid limpiada.");
        }
    }

    // Ya NO necesitamos el listener 'after:render' para la grid

    // Toggle Grid Checkbox
    $('#toggleGrid').on('change', function() {
        gridVisible = $(this).is(':checked');
        console.log("DEBUG: Toggle Grid cambiado. Nuevo estado:", gridVisible);
        if (gridVisible) {
            drawGrid();
        } else {
            clearGrid();
        }
    });

    // --- Snap to Grid (Sin cambios, debería funcionar ahora) ---
    $('#toggleSnap').on('change', function() {
        snapEnabled = $(this).is(':checked');
        console.log("DEBUG: Toggle Snap cambiado. Nuevo estado:", snapEnabled);
    });

    canvas.on('object:moving', function(options) {
        if (!snapEnabled) return;
        var target = options.target;
        // No aplicar snap a las líneas de la cuadrícula
        if (target.isGridLine) return;

        var effectiveSpacing = gridSpacing;
        var snappedLeft = Math.round(target.left / effectiveSpacing) * effectiveSpacing;
        var snappedTop = Math.round(target.top / effectiveSpacing) * effectiveSpacing;

        if(target.left !== snappedLeft || target.top !== snappedTop) {
            target.set({ left: snappedLeft, top: snappedTop });
            // Fabric se encarga de renderizar durante el movimiento
            // console.log("DEBUG: Snap aplicado a", snappedLeft, snappedTop);
        }
    });
    // Fin Eventos UX

    // --- 9. Funcionalidad de Previsualización ---
    $('#previewButton').on('click', function() {
        console.log("Clic en Previsualizar");
        var previewButton = $(this);
        var originalButtonText = previewButton.html();
        var previewUrl = previewButton.data('preview-url');
        if (!previewUrl) {
            console.error("Error: No se pudo encontrar la URL de previsualización en el atributo data-preview-url del botón.");
            alert("Error de configuración: Falta la URL de previsualización.");
            return; // Detener si no hay URL
        }
        console.log("URL para previsualización:", previewUrl); // Verificar URL

        // Deshabilitar botón y mostrar indicador (opcional)
        previewButton.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Cargando...');
        $('#previewModalBody').html('<p class="text-center"><i class="fa fa-spinner fa-spin fa-2x"></i><br>Generando previsualización...</p>'); // Limpiar modal
        $('#previewModal').modal('show'); // Mostrar modal

        // Obtener JSON actual del canvas (excluyendo grid)
        var propsToInclude = ['isPlaceholder', 'placeholderOriginalLabel', 'isGridLine'];
        var canvasJSON = canvas.toJSON(propsToInclude);
        if (canvasJSON && canvasJSON.objects) {
            canvasJSON.objects = canvasJSON.objects.filter(obj => !obj.isGridLine);
        }
        var designJSONString = JSON.stringify(canvasJSON);
        console.log("Enviando JSON para previsualizar (primeros 300):", designJSONString.substring(0, 300) + "...");

        // Obtener URL y CSRF token
        var csrfToken = $('input[name="csrfmiddlewaretoken"]').val();
        if (!csrfToken) {
            console.error("Error: No se encontró el token CSRF. Asegúrate que {% csrf_token %} está en el <form>.");
            alert("Error de seguridad: Falta el token CSRF.");
            previewButton.prop('disabled', false).html(originalButtonText); // Rehabilitar botón
            $('#previewModal').modal('hide'); // Ocultar modal
            return;
        }
        // Petición AJAX (usando Fetch API)
        fetch(previewUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json', // Enviar como JSON
                'X-CSRFToken': csrfToken // Incluir token CSRF
            },
            body: designJSONString // Enviar el string JSON directamente
        })
        .then(response => {
            console.log("Respuesta recibida, status:", response.status); // Log status
            if (!response.ok) {
                // Leer el texto del error si es posible
                return response.text().then(text => {
                    throw new Error(`Error HTTP ${response.status}: ${response.statusText}. Detalles: ${text}`);
                });
            }
            return response.text(); // Obtener la respuesta como texto (HTML)
        })
        .then(htmlResult => {
            console.log("Respuesta HTML de previsualización recibida.");
            $('#previewModalBody').html(htmlResult); // Poner HTML en el cuerpo del modal
        })
        .catch(error => {
            console.error('Error durante la previsualización:', error);
            $('#previewModalBody').html(`<div class="alert alert-danger">Error al generar previsualización: ${error.message}</div>`);
        })
        .finally(() => {
            // Volver a habilitar el botón y restaurar texto original
            previewButton.prop('disabled', false).html(originalButtonText);
            console.log("Proceso de previsualización finalizado (éxito o error).");
        });
    });

    $('#undoCanvas').on('click', function() {
        undo();
    });

    $('#redoCanvas').on('click', function() {
        redo();
    });

    // --- Atajos de Teclado (Opcional pero recomendado) ---
    $(document).keydown(function(e) {
        if (e.ctrlKey || e.metaKey) { // Ctrl (Windows/Linux) o Cmd (Mac)
            var activeElement = document.activeElement;
            // Solo interceptar si no estamos escribiendo en un input o textarea
            // excepto para nuestro campo de texto de propiedades
            var elId = $(activeElement).attr('id');
            if (activeElement && 
                (activeElement.tagName === 'INPUT' && $(activeElement).attr('type') === 'text' && elId !== 'propText') || 
                activeElement.tagName === 'TEXTAREA'
            ) {
                // Si es un input de texto (que no sea propText) o un textarea, no interceptar.
                // Permite que propText sea afectado por el undo/redo del canvas.
                return; 
            }

            if (e.key === 'z' || e.key === 'Z') { // Ctrl+Z o Cmd+Z
                e.preventDefault();
                if (!$('#undoCanvas').is(':disabled')) {
                    undo();
                }
            } else if (e.key === 'y' || e.key === 'Y') { // Ctrl+Y o Cmd+Y
                e.preventDefault();
                if (!$('#redoCanvas').is(':disabled')) {
                    redo();
                }
            }
        }
    });
    
    // Inicializar botones de undo/redo
    updateUndoRedoButtons();
    // ***** FIN: Eventos para los botones de Undo/Redo y Atajos *****





    console.log("--- DOCUMENT READY: Fin disenador_boleta.js ---");
}); // Fin de $(document).ready