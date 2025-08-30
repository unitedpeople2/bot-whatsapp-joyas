# api/google_sheets_handler.py

import gspread
import os
import json
from datetime import datetime
import logging

# Configuración del logger para que los mensajes aparezcan en los logs de Vercel
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def init_gspread():
    """Inicializa y devuelve un cliente autenticado de gspread."""
    try:
        logger.info("Iniciando conexión con Google Sheets...")
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        if not creds_json_str:
            logger.error("Error Crítico: La variable de entorno GOOGLE_CREDENTIALS_JSON está vacía o no existe.")
            return None
        
        # MODIFICADO: Imprimimos una parte para verificar que se está leyendo bien
        logger.info("Variable de entorno GOOGLE_CREDENTIALS_JSON leída correctamente.")
        
        creds_dict = json.loads(creds_json_str)
        
        # MODIFICADO: Verificamos que el email del cliente exista en las credenciales
        client_email = creds_dict.get("client_email")
        if not client_email:
            logger.error("Error Crítico: El JSON de credenciales no contiene la clave 'client_email'.")
            return None
        
        logger.info(f"Autenticando con la cuenta de servicio: {client_email}")
        
        # Usamos service_account_from_dict que es más directo
        gc = gspread.service_account_from_dict(creds_dict)
        logger.info("Cliente de gspread autenticado exitosamente.")
        return gc

    except json.JSONDecodeError:
        logger.error("Error Crítico: El contenido de GOOGLE_CREDENTIALS_JSON no es un JSON válido.")
        return None
    except Exception as e:
        logger.error(f"Error inesperado durante la inicialización de gspread: {e}")
        return None

def guardar_pedido(datos_pedido):
    """Guarda los datos de un pedido en una nueva fila de la hoja de cálculo."""
    gc = init_gspread()
    if not gc:
        logger.error("No se pudo inicializar el cliente de gspread. Abortando guardado en Sheets.")
        return False

    try:
        spreadsheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not spreadsheet_name:
            logger.error("Error: La variable de entorno GOOGLE_SHEET_NAME no está configurada.")
            return False
            
        logger.info(f"Intentando abrir la hoja de cálculo: '{spreadsheet_name}'")
        sh = gc.open(spreadsheet_name).sheet1
        
        logger.info(f"Hoja de cálculo '{spreadsheet_name}' abierta correctamente. Añadiendo fila...")
        
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
        logger.error(f"ERROR CRÍTICO: No se encontró la hoja de cálculo llamada '{spreadsheet_name}'.")
        logger.error("POSIBLES CAUSAS:")
        logger.error("1. El nombre en la variable GOOGLE_SHEET_NAME no es EXACTAMENTE igual al de tu archivo en Google Drive.")
        logger.error(f"2. No has compartido la hoja de cálculo con el email: {gc.auth.service_account.email}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al guardar en Google Sheets: {e}")
        return False