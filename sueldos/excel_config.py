# sueldos/excel_config.py

# --- Configuración para el Excel de PERSONAL PERMANENTE (PLANTA) ---
# Esto se basa en la lógica que ya tenías.
CONFIG_PLANTA = {
    'fila_inicio_datos': 11,  # Fila 12 en Excel
    'columnas': {
        # Clave (campo en DetalleSueldo) : Valor (índice de columna en Excel, empieza en 0)
        'item_referencia': 0,           # Col A
        'ci': 1,                        # Col B (usaremos 'ci' como clave interna)
        'nombre_completo_referencia': 2,# Col C
        'cargo_referencia': 3,          # Col D
        'fecha_ingreso_referencia': 4,  # Col E
        'dias_trab': 5,                 # Col F
        'haber_basico': 6,              # Col G
        'categoria': 7,                 # Col H
        'total_ganado': 8,              # Col I
        'rc_iva_retenido': 9,           # Col J
        'gestora_publica': 10,          # Col K
        'aporte_nac_solidario': 11,     # Col L
        'cooperativa': 12,              # Col M
        'faltas': 13,                   # Col N
        'memorandums': 14,              # Col O
        'otros_descuentos': 15,         # Col P
        'total_descuentos': 16,         # Col Q
        'liquido_pagable': 17,          # Col R
        'saldo_credito_fiscal': 18,     # Col S
    }
}


# --- Configuración para el Excel de CONTRATO ---
CONFIG_CONTRATO = {
    'fila_inicio_datos': 10,   
    'columnas': {
        # Clave (campo en DetalleSueldo) : Valor (índice de columna en Excel)
        'ci': 0,                        # CI en Col A
        'nombre_completo_referencia': 1,# Nombre en Col B
        'cargo_referencia': 2,          #Cargo en Col C
        'item_referencia': 3,           # Nro Contrato en Col D         
        # 'fecha_ingreso_referencia' no existe en este formato
        'dias_trab': 4,
        'haber_basico': 5,
        'categoria': 6,
        'total_ganado': 7,
        'rc_iva_retenido': 8,
        'gestora_publica': 9,
        'cooperativa': 10,
        'sanciones': 11,
        'memorandums': 12,
        'otros_descuentos': 13,
        'total_descuentos': 14,
        'liquido_pagable': 15,
        'saldo_credito_fiscal': 16,     # Col Q
    }
}


# --- Diccionario Principal de Procesadores ---
# Mapea el valor del campo 'tipo' de PlanillaSueldo a su configuración.
PROCESADORES_EXCEL = {
    'planta': CONFIG_PLANTA,
    'contrato': CONFIG_CONTRATO,
    # 'consultor en linea': lo ignoramos por ahora
}