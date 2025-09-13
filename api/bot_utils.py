# -*- coding: utf-8 -*-
# ==========================================================
# BOT DAAQUI - UTILIDADES
# Contiene todas las funciones de soporte: comunicación con APIs, helpers, etc.
# ==========================================================
import os
import re
import json
import time
import uuid
import gspread
import requests
import logging
import unicodedata
from datetime import datetime
from logging import getLogger
from firebase_admin import firestore

# Configuración del logger
logger = getLogger(__name__)

# ==============================================================================
# 3. FUNCIONES DE COMUNICACIÓN CON WHATSAPP
# ==============================================================================
def send_whatsapp_message(to_number, message_data):
    WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        logger.error("Token de WhatsApp o ID de número de teléfono no configurados.")
        return
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    data = {"messaging_product": "whatsapp", "to": to_number, **message_data}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Mensaje enviado exitosamente a {to_number}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a {to_number}: {e.response.text if e.response else e}")

def send_text_message(to_number, text):
    send_whatsapp_message(to_number, {"type": "text", "text": {"body": text}})

def send_image_message(to_number, image_url):
    send_whatsapp_message(to_number, {"type": "image", "image": {"link": image_url}})

# ==============================================================================
# 4. FUNCIONES DE INTERACCIÓN CON FIRESTORE
# ==============================================================================
def get_session(user_id):
    db = firestore.client()
    if not db: return None
    try:
        doc = db.collection('sessions').document(user_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error obteniendo sesión para {user_id}: {e}")
        return None

def save_session(user_id, session_data):
    db = firestore.client()
    if not db: return
    try:
        db.collection('sessions').document(user_id).set(session_data, merge=True)
    except Exception as e:
        logger.error(f"Error guardando sesión para {user_id}: {e}")

def delete_session(user_id):
    db = firestore.client()
    if not db: return
    try:
        db.collection('sessions').document(user_id).delete()
    except Exception as e:
        logger.error(f"Error eliminando sesión para {user_id}: {e}")

def find_product_by_keywords(text, KEYWORDS_GIRASOL):
    db = firestore.client()
    if not db: return None, None
    try:
        if any(keyword in text.lower() for keyword in KEYWORDS_GIRASOL):
            product_id = "collar-girasol-radiant-01"
            product_doc = db.collection('productos').document(product_id).get()
            if product_doc.exists and product_doc.to_dict().get('activo'):
                return product_id, product_doc.to_dict()
    except Exception as e:
        logger.error(f"Error buscando producto por palabras clave: {e}")
    return None, None

def save_completed_sale_and_customer(session_data):
    db = firestore.client()
    if not db: return False, None
    try:
        sale_id = str(uuid.uuid4())
        customer_id = session_data.get('whatsapp_id')
        precio_total = session_data.get('product_price', 0)
        adelanto = session_data.get('adelanto', 0)
        saldo_restante = precio_total - adelanto
        sale_data = {
            "fecha": firestore.SERVER_TIMESTAMP,
            "id_venta": sale_id,
            "producto_id": session_data.get('product_id'),
            "producto_nombre": session_data.get('product_name'),
            "precio_venta": precio_total,
            "tipo_envio": session_data.get('tipo_envio'),
            "metodo_pago": session_data.get('metodo_pago'),
            "provincia": session_data.get('provincia'),
            "distrito": session_data.get('distrito'),
            "detalles_cliente": session_data.get('detalles_cliente'),
            "cliente_id": customer_id,
            "estado_pedido": "Adelanto Pagado",
            "adelanto_recibido": adelanto,
            "saldo_restante": saldo_restante
        }
        db.collection('ventas').document(sale_id).set(sale_data)
        logger.info(f"Venta {sale_id} guardada en Firestore.")
        customer_data = {
            "nombre_perfil_wa": session_data.get('user_name'),
            "provincia_ultimo_envio": session_data.get('provincia'),
            "distrito_ultimo_envio": session_data.get('distrito'),
            "detalles_ultimo_envio": session_data.get('detalles_cliente'),
            "total_compras": firestore.Increment(1),
            "fecha_ultima_compra": firestore.SERVER_TIMESTAMP
        }
        db.collection('clientes').document(customer_id).set(customer_data, merge=True)
        logger.info(f"Cliente {customer_id} creado/actualizado.")
        return True, sale_data
    except Exception as e:
        logger.error(f"Error guardando venta y cliente en Firestore: {e}")
        return False, None

# ==============================================================================
# 5. FUNCIONES AUXILIARES DE LÓGICA DE NEGOCIO
# ==============================================================================
def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def normalize_and_check_district(text, BUSINESS_RULES):
    clean_text = re.sub(r'soy de|vivo en|estoy en|es en|de', '', text, flags=re.IGNORECASE).strip()
    normalized_input = strip_accents(clean_text.lower())
    abreviaturas = BUSINESS_RULES.get('abreviaturas_distritos', {})
    for abbr, full_name in abreviaturas.items():
        if abbr in normalized_input:
            normalized_input = strip_accents(full_name.lower())
            break
    distritos_cobertura = BUSINESS_RULES.get('distritos_cobertura_delivery', [])
    for distrito in distritos_cobertura:
        if normalized_input in strip_accents(distrito.lower()):
            return distrito.title(), 'CON_COBERTURA'
    distritos_totales = BUSINESS_RULES.get('distritos_lima_total', [])
    for distrito in distritos_totales:
        if normalized_input in strip_accents(distrito.lower()):
            return distrito.title(), 'SIN_COBERTURA'
    return None, 'NO_ENCONTRADO'

def parse_province_district(text):
    clean_text = re.sub(r'soy de|vivo en|mi ciudad es|el distrito es', '', text, flags=re.IGNORECASE).strip()
    separators = [',', '-', '/']
    for sep in separators:
        if sep in clean_text:
            parts = [part.strip() for part in clean_text.split(sep, 1)]
            return parts[0].title(), parts[1].title()
    return clean_text.title(), clean_text.title()

def get_delivery_day_message(BUSINESS_RULES):
    weekday = datetime.now().weekday()
    if weekday < 5:
        return BUSINESS_RULES.get('mensaje_dia_habil', 'mañana')
    else:
        return BUSINESS_RULES.get('mensaje_fin_semana', 'el Lunes')

def guardar_pedido_en_sheet(sale_data):
    try:
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not creds_json_str or not sheet_name:
            logger.error("[Sheets] Faltan variables de entorno para Google Sheets.")
            return False
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open(sheet_name)
        worksheet = spreadsheet.sheet1
        nueva_fila = [
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            sale_data.get('id_venta', 'N/A'),
            sale_data.get('producto_nombre', 'N/A'),
            sale_data.get('precio_venta', 0),
            sale_data.get('tipo_envio', 'N/A'),
            sale_data.get('metodo_pago', 'N/A'),
            sale_data.get('adelanto_recibido', 0),
            sale_data.get('saldo_restante', 0),
            sale_data.get('provincia', 'N/A'),
            sale_data.get('distrito', 'N/A'),
            sale_data.get('detalles_cliente', 'N/A'),
            sale_data.get('cliente_id', 'N/A')
        ]
        worksheet.append_row(nueva_fila)
        logger.info(f"[Sheets] Pedido {sale_data.get('id_venta')} guardado.")
        return True
    except Exception as e:
        logger.error(f"[Sheets] ERROR INESPERADO: {e}")
        return False

def find_key_in_sheet(cliente_id):
    try:
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not creds_json_str or not sheet_name:
            logger.error("[Sheets] Faltan variables de entorno para buscar clave.")
            return None
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open(sheet_name)
        worksheet = spreadsheet.sheet1
        cell = worksheet.find(cliente_id, in_column=12) # Columna L para WhatsApp ID
        if cell:
            clave = worksheet.cell(cell.row, 15).value # Columna O para Clave
            logger.info(f"[Sheets] Clave encontrada para {cliente_id}: {'Sí' if clave else 'No'}")
            return clave
        else:
            logger.warning(f"[Sheets] No se encontró la fila para el cliente {cliente_id}.")
            return None
    except Exception as e:
        logger.error(f"[Sheets] ERROR buscando la clave: {e}")
        return None

def get_last_question(state):
    questions = {
        "awaiting_occasion_response": "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?",
        "awaiting_purchase_decision": "¿Te gustaría coordinar tu pedido ahora para asegurar el tuyo? (Sí/No)",
        "awaiting_upsell_decision": "Para continuar, por favor, respóndeme con una de estas dos palabras:\n👉🏽 Escribe *oferta* para ampliar tu pedido.\n👉🏽 Escribe *continuar* para llevar solo un collar.",
        "awaiting_location": "Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?",
        "awaiting_lima_district": "¡Genial! ✨ Para saber qué tipo de envío te corresponde, por favor, dime: ¿en qué distrito te encuentras? 📍",
        "awaiting_province_district": "¡Entendido! Para continuar, por favor, indícame tu *provincia y distrito*. ✍🏽\n\n📝 *Ej: Arequipa, Arequipa*",
        "awaiting_shalom_agreement": "¿Estás de acuerdo con el adelanto? (Sí/No)",
        "awaiting_lima_payment_agreement": "¿Procedemos con la confirmación del adelanto? (Sí/No)",
        "awaiting_lima_payment": "Una vez realizado, por favor, envíame la *captura de pantalla* para validar tu pedido.",
        "awaiting_shalom_payment": "Una vez realizado, por favor, envíame la *captura de pantalla* para validar tu pedido."
    }
    return questions.get(state)

def find_key_in_sheet(cliente_id):
    try:
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not creds_json_str or not sheet_name:
            logger.error("[Sheets] Faltan variables de entorno para buscar clave.")
            return None

        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open(sheet_name)
        worksheet = spreadsheet.sheet1

        # Asumimos que el WhatsApp ID (cliente_id) está en la columna 12 (L)
        # y la Clave está en la columna 15 (O)
        cell = worksheet.find(cliente_id, in_column=12) 
        if cell:
            clave = worksheet.cell(cell.row, 15).value
            logger.info(f"[Sheets] Clave encontrada para {cliente_id}: {'Sí' if clave else 'No'}")
            return clave
        else:
            logger.warning(f"[Sheets] No se encontró la fila para el cliente {cliente_id}.")
            return None
    except Exception as e:
        logger.error(f"[Sheets] ERROR buscando la clave: {e}")
        return None