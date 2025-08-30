# api/google_sheets_handler.py

import gspread
import os
import json
from datetime import datetime

# ¡AÑADIMOS UN LOGGER PARA VER ERRORES!
import logging
logger = logging.getLogger(__name__)

def init_gspread():
    """Inicializa y devuelve un cliente autenticado de gspread."""
    try:
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if not creds_json_str:
            logger.error("Error Crítico: La variable de entorno GOOGLE_CREDENTIALS_JSON no está configurada.")
            return None
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        logger.error(f"Error al inicializar gspread: {e}")
        return None

def guardar_pedido(datos_pedido):
    """Guarda los datos de un pedido en una nueva fila de la hoja de cálculo."""
    gc = init_gspread()
    if not gc:
        return False

    try:
        # Asegúrate de que este nombre sea exacto al de tu hoja
        spreadsheet_name = "Pedidos Bot WhatsApp - Daaqui"
        sh = gc.open(spreadsheet_name).sheet1
        
        # El orden debe coincidir con tus columnas en la hoja
        nueva_fila = [
            datos_pedido.get('fecha', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            datos_pedido.get('nombre_completo', ''),
            datos_pedido.get('direccion', ''),
            datos_pedido.get('referencia', ''),
            datos_pedido.get('distrito', ''),
            datos_pedido.get('dni', ''),
            datos_pedido.get('forma_pago', ''),
            datos_pedido.get('celular', ''),
            datos_pedido.get('producto_seleccionado', ''),
            datos_pedido.get('total', '')
        ]
        
        sh.append_row(nueva_fila)
        logger.info(f"Pedido guardado exitosamente en '{spreadsheet_name}'")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"ERROR: No se encontró la hoja de cálculo llamada '{spreadsheet_name}'. Revisa el nombre y los permisos de compartir.")
        return False
    except Exception as e:
        logger.error(f"Error al guardar en Google Sheets: {e}")
        return False