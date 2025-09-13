# -*- coding: utf-8 -*-
# ==========================================================
# BOT DAAQUI JOYAS - V9.1 - CÓDIGO FINAL COMPLETO
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
from logging import getLogger
import os
import re
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import uuid
import gspread
import unicodedata

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

# ==========================================================
# INICIALIZACIÓN DE FIREBASE Y REGLAS DE NEGOCIO
# ==========================================================
db = None
BUSINESS_RULES = {}
FAQ_RESPONSES = {}
try:
    service_account_info_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    if service_account_info_str:
        service_account_info = json.loads(service_account_info_str)
        cred = credentials.Certificate(service_account_info)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Conexión con Firebase establecida correctamente.")

        rules_doc = db.collection('configuracion').document('reglas_envio').get()
        if rules_doc.exists:
            BUSINESS_RULES = rules_doc.to_dict()
            logger.info("✅ Reglas del negocio cargadas desde Firestore.")
        else:
            logger.error("❌ Documento de reglas de envío no encontrado en Firestore.")

        faq_doc = db.collection('configuracion').document('respuestas_faq').get()
        if faq_doc.exists:
            FAQ_RESPONSES = faq_doc.to_dict()
            logger.info("✅ Respuestas FAQ cargadas desde Firestore.")
        else:
            logger.error("❌ Documento de respuestas_faq no encontrado en Firestore.")
    else:
        logger.error("❌ La variable de entorno FIREBASE_SERVICE_ACCOUNT_JSON no está configurada.")
except Exception as e:
    logger.error(f"❌ Error crítico inicializando Firebase o cargando reglas: {e}")

app = Flask(__name__)

# ==========================================================
# 2. CONFIGURACIÓN DEL NEGOCIO Y VARIABLES GLOBALES
# ==========================================================
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ADMIN_WHATSAPP_NUMBER = os.environ.get('ADMIN_WHATSAPP_NUMBER')
MAKE_SECRET_TOKEN = os.environ.get('MAKE_SECRET_TOKEN')
RUC_EMPRESA = "10700761130"
TITULAR_YAPE = "Hedinson Rojas Mattos"
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]

FAQ_KEYWORD_MAP = {
    'precio': ['precio', 'valor', 'costo'],
    'envio': ['envío', 'envio', 'delivery', 'mandan', 'entrega', 'cuesta el envío'],
    'pago': ['pago', 'métodos de pago', 'contraentrega', 'contra entrega', 'yape', 'plin'],
    'tienda': ['tienda', 'local', 'ubicación', 'ubicacion', 'dirección', 'direccion'],
    'transferencia': ['transferencia', 'banco', 'bcp', 'interbank', 'cuenta', 'transferir'],
    'material': ['material', 'acero', 'alergia', 'hipoalergenico'],
    'cuidados': ['mojar', 'agua', 'oxida', 'negro', 'cuidar', 'limpiar', 'cuidados'],
    'garantia': ['garantía', 'garantia', 'falla', 'defectuoso', 'roto'],
    'cambios_devoluciones': ['cambio', 'cambiar', 'devolución', 'devoluciones', 'devuelvo'],
    'stock': ['stock', 'disponible', 'tienen', 'hay', 'unidades']
}

# ==============================================================================
# 3. FUNCIONES DE COMUNICACIÓN CON WHATSAPP
# ==============================================================================
def send_whatsapp_message(to_number, message_data):
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
    if not db: return None
    try:
        doc = db.collection('sessions').document(user_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error obteniendo sesión para {user_id}: {e}")
        return None

def save_session(user_id, session_data):
    if not db: return
    try:
        db.collection('sessions').document(user_id).set(session_data, merge=True)
    except Exception as e:
        logger.error(f"Error guardando sesión para {user_id}: {e}")

def delete_session(user_id):
    if not db: return
    try:
        db.collection('sessions').document(user_id).delete()
    except Exception as e:
        logger.error(f"Error eliminando sesión para {user_id}: {e}")

def find_product_by_keywords(text):
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

def normalize_and_check_district(text):
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

def get_delivery_day_message():
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

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS)
# ==============================================================================
def handle_initial_message(from_number, user_name, text):
    product_id, product_data = find_product_by_keywords(text)
    if product_data:
        nombre_producto, desc_corta, precio, url_img = product_data.get('nombre', ''), product_data.get('descripcion_corta', ''), product_data.get('precio_base', 0), product_data.get('imagenes', {}).get('principal')
        if url_img: send_image_message(from_number, url_img); time.sleep(1)
        msg = (f"¡Hola {user_name}! 🌞 El *{nombre_producto}* {desc_corta}\n\n"
               f"Por campaña, llévatelo a *S/ {precio:.2f}* (¡incluye envío gratis a todo el Perú! 🚚).\n\n"
               "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?")
        send_text_message(from_number, msg)
        save_session(from_number, {"state": "awaiting_occasion_response", "product_id": product_id, "product_name": nombre_producto, "product_price": float(precio), "user_name": user_name, "whatsapp_id": from_number, "is_upsell": False})
        return
    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            if response_text := FAQ_RESPONSES.get(key): send_text_message(from_number, response_text); return
    send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")

# ==============================================================================
# 7. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA)
# ==============================================================================
def handle_sales_flow(from_number, text, session):
    # --- DETECTOR DE FAQ DURANTE EL FLUJO ---
    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            response_text = FAQ_RESPONSES.get(key)
            if key == 'precio' and session.get('product_name'): response_text = f"¡Claro! El precio de tu pedido (*{session['product_name']}*) es de *S/ {session['product_price']:.2f}*, con envío gratis. 🚚"
            elif key == 'stock' and session.get('product_name'): response_text = f"¡Sí, claro! Aún tenemos unidades del *{session['product_name']}*. ✨ ¿Iniciamos tu pedido?"
            if response_text:
                send_text_message(from_number, response_text)
                time.sleep(1)
                if last_question := get_last_question(session.get('state')):
                    send_text_message(from_number, f"¡Espero haber aclarado tu duda! 😊 Continuando...\n\n{last_question}")
                return

    if any(keyword in text.lower() for keyword in KEYWORDS_GIRASOL) and session.get('state') not in ['awaiting_occasion_response', 'awaiting_purchase_decision']:
        logger.info(f"Usuario {from_number} reiniciando flujo.")
        delete_session(from_number); handle_initial_message(from_number, session.get("user_name", "Usuario"), text); return

    current_state, product_id = session.get('state'), session.get('product_id')
    if not product_id or not (product_doc := db.collection('productos').document(product_id).get()).exists:
        send_text_message(from_number, "Lo siento, este producto ya no está disponible. Por favor, empieza de nuevo.")
        delete_session(from_number); return
    product_data = product_doc.to_dict()

    if current_state == 'awaiting_occasion_response':
        url_imagen_empaque = product_data.get('imagenes', {}).get('empaque')
        detalles = product_data.get('detalles', {})
        material = detalles.get('material', 'material de alta calidad')
        presentacion = detalles.get('empaque', 'viene en una hermosa caja de regalo')
        if url_imagen_empaque:
            send_image_message(from_number, url_imagen_empaque)
            time.sleep(1)
        mensaje_persuasion_1 = (
            "¡Maravillosa elección! ✨ El *Collar Mágico Girasol Radiant* es pura energía. Aquí tienes todos los detalles:\n\n"
            f"💎 *Material:* {material} ¡Hipoalergénico y no se oscurece!\n"
            f"🔮 *La Magia:* Su piedra central es termocromática, cambia de color con tu temperatura.\n"
            f"🎁 *Presentación:* {presentacion}"
        )
        send_text_message(from_number, mensaje_persuasion_1)
        time.sleep(1.5)
        mensaje_persuasion_2 = (
            f"Para tu total seguridad, somos Daaqui Joyas, un negocio formal con *RUC {RUC_EMPRESA}*. ¡Tu compra es 100% segura! 🇵🇪\n\n"
            "¿Te gustaría coordinar tu pedido ahora para asegurar el tuyo? (Sí/No)"
        )
        send_text_message(from_number, mensaje_persuasion_2)
        session['state'] = 'awaiting_purchase_decision'
        save_session(from_number, session)
    
    elif current_state == 'awaiting_purchase_decision':
        if 'si' in text.lower() or 'sí' in text.lower():
            url_imagen_upsell = product_data.get('imagenes', {}).get('upsell')
            if url_imagen_upsell:
                send_image_message(from_number, url_imagen_upsell)
                time.sleep(1)
            upsell_message_1 = (
                "¡Excelente elección! Pero espera... por decidir llevar tu collar, ¡acabas de desbloquear una oferta exclusiva! ✨\n\n"
                "Añade un segundo Collar Mágico y te incluimos de regalo dos cadenas de diseño italiano.\n\n"
                "Tu pedido se ampliaría a:\n"
                "✨ 2 Collares Mágicos\n🎁 2 Cadenas de Regalo\n🎀 2 Cajitas Premium\n"
                "💎 Todo por un único pago de S/ 99.00"
            )
            send_text_message(from_number, upsell_message_1)
            time.sleep(1.5)
            upsell_message_2 = (
                "Para continuar, por favor, respóndeme:\n"
                "👉🏽 Escribe *oferta* para ampliar tu pedido.\n"
                "👉🏽 Escribe *continuar* para llevar solo un collar."
            )
            send_text_message(from_number, upsell_message_2)
            session['state'] = 'awaiting_upsell_decision'
            save_session(from_number, session)
        else:
            delete_session(from_number)
            send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré. ¡Que tengas un buen día! 😊")

    elif current_state == 'awaiting_upsell_decision':
        if 'oferta' in text.lower():
            session.update({"product_name": "Oferta 2x Collares Mágicos + Cadenas", "product_price": 99.00, "is_upsell": True})
            send_text_message(from_number, "¡Genial! Has elegido la oferta. ✨")
        else: 
            session['is_upsell'] = False
            send_text_message(from_number, "¡Perfecto! Continuamos con tu collar individual. ✨")
        session['state'] = 'awaiting_location'
        save_session(from_number, session)
        time.sleep(1)
        send_text_message(from_number, "Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?")

    elif current_state == 'awaiting_location':
        if 'lima' in text.lower():
            session.update({"state": "awaiting_lima_district", "provincia": "Lima"})
            save_session(from_number, session)
            send_text_message(from_number, "¡Genial! ✨ Para saber qué tipo de envío te corresponde, por favor, dime: ¿en qué distrito te encuentras? 📍")
        elif 'provincia' in text.lower():
            session['state'] = 'awaiting_province_district'
            save_session(from_number, session)
            send_text_message(from_number, "¡Entendido! Para continuar, indícame tu *provincia y distrito*. ✍🏽\n\n📝 *Ej: Arequipa, Arequipa*")
        else:
            send_text_message(from_number, "No te entendí bien. Por favor, dime si tu envío es para *Lima* o para *provincia*.")
    
    elif current_state == 'awaiting_province_district':
        provincia, distrito = parse_province_district(text)
        session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Provincia Shalom", "metodo_pago": "Adelanto y Saldo (Yape/Plin)", "provincia": provincia, "distrito": distrito})
        save_session(from_number, session)
        adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
        mensaje = (f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}* como compromiso de recojo. 🤝\n\n"
                   "¿Estás de acuerdo? (Sí/No)")
        send_text_message(from_number, mensaje)
        
    elif current_state == 'awaiting_lima_district':
        distrito, status = normalize_and_check_district(text)
        if status != 'NO_ENCONTRADO':
            session['distrito'] = distrito
            if status == 'CON_COBERTURA':
                session.update({"state": "awaiting_delivery_details", "tipo_envio": "Lima Contra Entrega", "metodo_pago": "Contra Entrega (Efectivo/Yape/Plin)"})
                save_session(from_number, session)
                mensaje = (f"¡Excelente! Tenemos cobertura en *{distrito}*. 🏙️\n\n"
                           "Para registrar tu pedido, envíame en *un solo mensaje* tu *Nombre Completo, Dirección exacta* y una *Referencia*.\n\n"
                           "📝 *Ej: Ana Pérez, Jr. Gamarra 123, Depto 501, La Victoria. Al lado de la farmacia.*")
                send_text_message(from_number, mensaje)
            elif status == 'SIN_COBERTURA':
                session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Lima Shalom", "metodo_pago": "Adelanto y Saldo (Yape/Plin)"})
                save_session(from_number, session)
                adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
                mensaje = (f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}* como compromiso de recojo. 🤝\n\n"
                           "¿Estás de acuerdo? (Sí/No)")
                send_text_message(from_number, mensaje)
        else:
            send_text_message(from_number, "No pude reconocer ese distrito. Por favor, intenta escribirlo de nuevo.")

    elif current_state in ['awaiting_delivery_details', 'awaiting_shalom_details']:
        session.update({"state": "awaiting_final_confirmation", "detalles_cliente": text})
        save_session(from_number, session)
        resumen = ("¡Gracias! Revisa que todo esté correcto:\n\n"
                   "*Resumen del Pedido*\n"
                   f"💎 {session.get('product_name', '')}\n"
                   f"💵 Total: S/ {session.get('product_price', 0):.2f}\n"
                   f"🚚 Envío: {session.get('distrito', session.get('provincia', ''))} - ¡Gratis!\n"
                   f"💳 Pago: {session.get('metodo_pago', '')}\n\n"
                   "*Datos de Entrega*\n"
                   f"{session.get('detalles_cliente', '')}\n\n"
                   "¿Confirmas que todo es correcto? (Sí/No)")
        send_text_message(from_number, resumen)

    elif current_state == 'awaiting_shalom_agreement':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_experience'
            save_session(from_number, session)
            send_text_message(from_number, "¡Genial! Para hacer el proceso más fácil, cuéntame: ¿alguna vez has recogido un pedido en una agencia Shalom? 🙋🏽‍♀️ (Sí/No)")
        else:
            delete_session(from_number); send_text_message(from_number, "Comprendo. Si cambias de opinión, aquí estaré. ¡Gracias! 😊")

    elif current_state == 'awaiting_shalom_experience':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_details'
            save_session(from_number, session)
            mensaje = ("¡Excelente! Entonces ya conoces el proceso. ✅\n\n"
                       "Para terminar, bríndame en un solo mensaje tu *Nombre Completo, DNI* y la *dirección exacta de la agencia Shalom* donde recogerás. ✍🏽")
            send_text_message(from_number, mensaje)
        else:
            session['state'] = 'awaiting_shalom_agency_knowledge'
            save_session(from_number, session)
            mensaje = ("¡No te preocupes! Te explico: Shalom es una empresa de envíos. Te damos un código de seguimiento, y cuando tu pedido llega a la agencia, nos yapeas el saldo restante. Apenas confirmemos, te damos la clave secreta para el recojo. ¡Es 100% seguro! 🔒\n\n"
                       "¿Conoces la dirección de alguna agencia Shalom cerca a ti? (Sí/No)")
            send_text_message(from_number, mensaje)
            
    elif current_state == 'awaiting_shalom_agency_knowledge':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_details'
            save_session(from_number, session)
            mensaje = ("¡Perfecto! Por favor, bríndame en un solo mensaje tu *Nombre Completo, DNI* y la *dirección de esa agencia Shalom*. ✍🏽")
            send_text_message(from_number, mensaje)
        else:
            delete_session(from_number); send_text_message(from_number, "Entiendo. 😔 Te recomiendo buscar en Google 'Shalom agencias' para encontrar la más cercana. ¡Gracias por tu interés!")
            
    elif current_state == 'awaiting_final_confirmation':
        if 'si' in text.lower() or 'sí' in text.lower():
            if session.get('tipo_envio') == 'Lima Contra Entrega':
                adelanto = float(BUSINESS_RULES.get('adelanto_lima_delivery', 10))
                session.update({'adelanto': adelanto, 'state': 'awaiting_lima_payment_agreement'})
                save_session(from_number, session)
                mensaje = (f"¡Perfecto! ✅ Como último paso, solicitamos un adelanto de *S/ {adelanto:.2f}* para confirmar el compromiso de recojo. 🤝 Este monto se descuenta del total, por supuesto.\n\n"
                           "¿Procedemos? (Sí/No)")
                send_text_message(from_number, mensaje)
            else: # Shalom
                adelanto = float(BUSINESS_RULES.get('adelanto_shalom', 20))
                session.update({'adelanto': adelanto, 'state': 'awaiting_shalom_payment'})
                save_session(from_number, session)
                mensaje = (f"¡Genial! Puedes realizar el adelanto de *S/ {adelanto:.2f}* a nuestra cuenta:\n\n"
                           f"💳 *YAPE / PLIN:* {BUSINESS_RULES.get('yape_numero', 'No configurado')}\n"
                           f"👤 *Titular:* {TITULAR_YAPE}\n"
                           f"🔒 Tu compra es 100% segura (*RUC {RUC_EMPRESA}*).\n\n"
                           "Una vez realizado, envíame la *captura de pantalla* para validar tu pedido.")
                send_text_message(from_number, mensaje)
        else:
            previous_state = 'awaiting_delivery_details' if session.get('tipo_envio') == 'Lima Contra Entrega' else 'awaiting_shalom_details'
            session['state'] = previous_state
            save_session(from_number, session)
            send_text_message(from_number, "¡Claro, lo corregimos! 😊 Por favor, envíame nuevamente la información de envío completa en un solo mensaje.")

    elif current_state == 'awaiting_lima_payment_agreement':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_lima_payment'
            save_session(from_number, session)
            mensaje = (f"¡Genial! Puedes realizar el adelanto de *S/ {session.get('adelanto', 10):.2f}* a:\n\n"
                       f"💳 *YAPE / PLIN:* {BUSINESS_RULES.get('yape_numero', 'No configurado')}\n"
                       f"👤 *Titular:* {TITULAR_YAPE}\n\n"
                       "Una vez realizado, envíame la *captura de pantalla* para validar.")
            send_text_message(from_number, mensaje)
        else:
            delete_session(from_number); send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré. ¡Gracias!")

    elif current_state in ['awaiting_lima_payment', 'awaiting_shalom_payment']:
        if text == "COMPROBANTE_RECIBIDO":
            guardado_exitoso, sale_data = save_completed_sale_and_customer(session)
            if guardado_exitoso:
                guardar_pedido_en_sheet(sale_data)
                if ADMIN_WHATSAPP_NUMBER:
                    admin_message = (f"🎉 ¡Nueva Venta Confirmada! 🎉\n\n"
                                     f"Producto: {sale_data.get('producto_nombre')}\n"
                                     f"Tipo: {sale_data.get('tipo_envio')}\n"
                                     f"Cliente WA ID: {sale_data.get('cliente_id')}\n"
                                     f"Detalles:\n{sale_data.get('detalles_cliente')}")
                    send_text_message(ADMIN_WHATSAPP_NUMBER, admin_message)
                if session.get('tipo_envio') == 'Lima Contra Entrega':
                    restante = sale_data.get('saldo_restante', 0)
                    dia_entrega = get_delivery_day_message()
                    horario = BUSINESS_RULES.get('horario_entrega_lima', 'durante el día')
                    mensaje_final = (f"¡Adelanto confirmado! ✨ Tu pedido ha sido agendado. Lo recibirás *{dia_entrega}* entre *{horario}*.\n\n"
                                     f"💵 Pagarás al recibir: *S/ {restante:.2f}*.\n\n"
                                     "¡Gracias por tu compra! 🎉")
                    send_text_message(from_number, mensaje_final)
                else: # Shalom
                    mensaje_base = "¡Adelanto confirmado! ✨ Agendamos tu envío. Te enviaremos tu código de seguimiento por aquí en las próximas 24h hábiles. "
                    if session.get('tipo_envio') == 'Lima Shalom': msg_final = mensaje_base + "El tiempo de entrega en agencia es de 1-2 días hábiles."
                    else: msg_final = mensaje_base + "El tiempo de entrega en agencia es de 3-5 días hábiles."
                    send_text_message(from_number, msg_final)
                delete_session(from_number)
            else:
                send_text_message(from_number, "¡Uy! Hubo un problema al registrar tu pedido. Un asesor se pondrá en contacto contigo.")
        else:
            send_text_message(from_number, "Estoy esperando la *captura de pantalla* de tu pago. 😊")
    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar, escribe 'cancelar'.")


# ==============================================================================
# 8. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode, token, challenge = request.args.get('hub.mode'), request.args.get('hub.verify_token'), request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN: return challenge
        return 'Forbidden', 403
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        if change.get('field') == 'messages' and (value := change.get('value', {})):
                            if messages := value.get('messages'):
                                for message in messages:
                                    process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}"); return jsonify({'error': str(e)}), 500

# ==========================================================
# PROCESADOR DE MENSAJES (LÓGICA PRINCIPAL) - V9.1
# ==========================================================
def process_message(message, contacts):
    try:
        from_number = message.get('from')
        user_name = next((c.get('profile', {}).get('name', 'Usuario') for c in contacts if c.get('wa_id') == from_number), 'Usuario')
        message_type = message.get('type')
        text_body = ""
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '')
        elif message_type == 'image':
            text_body = "_Imagen Recibida_"
        else:
            send_text_message(from_number, "Por ahora solo puedo procesar mensajes de texto e imágenes. 😊")
            return
        logger.info(f"Procesando de {user_name} ({from_number}): '{text_body}'")

        # --- FILTRO 1: COMANDO DE ADMINISTRADOR (MÁXIMA PRIORIDAD) ---
        if from_number == ADMIN_WHATSAPP_NUMBER and text_body.lower().startswith('clave '):
            logger.info(f"Comando de admin detectado de {from_number}")
            parts = text_body.split()
            if len(parts) == 3:
                target_number, secret_key = parts[1], parts[2]
                if target_number.isdigit() and len(target_number) > 8:
                    msg = (f"¡Gracias por confirmar tu pago! ✨\n\n"
                           f"Aquí tienes tu clave secreta para recoger tu pedido en la agencia:\n\n"
                           f"🔑 *CLAVE:* {secret_key}\n\n"
                           "¡Que disfrutes tu joya!")
                    send_text_message(target_number, msg)
                    send_text_message(from_number, f"✅ Clave '{secret_key}' enviada a {target_number}.")
                else:
                    send_text_message(from_number, f"❌ Error: El número '{target_number}' no parece válido.")
            else:
                send_text_message(from_number, "❌ Error: Usa: clave <numero> <clave>")
            return

        # --- FILTRO 2: NOTIFICACIÓN INTELIGENTE DE PAGO FINAL (ALTA PRIORIDAD) ---
        if db:
            ventas_pendientes = db.collection('ventas').where('cliente_id', '==', from_number).where('estado_pedido', '==', 'Adelanto Pagado').limit(1).get()
            if ventas_pendientes and message_type == 'image':
                logger.info(f"Posible pago final (imagen) detectado de {from_number}.")
                clave_encontrada = find_key_in_sheet(from_number)
                
                notificacion = (
                    f"🔔 *¡Atención! Posible Pago Final Recibido* 🔔\n\n"
                    f"Un cliente con un pedido pendiente acaba de enviar una imagen.\n\n"
                    f"*Cliente:* {user_name}\n"
                    f"*WA ID:* {from_number}\n"
                )
                if clave_encontrada:
                    notificacion += (
                        f"*Clave Encontrada en Sheet:* `{clave_encontrada}`\n\n"
                        f"*Si el pago es correcto, copia y pega el comando:*\n"
                        f"`clave {from_number} {clave_encontrada}`"
                    )
                else:
                    notificacion += (
                        f"*Clave:* No encontrada en el Sheet.\n\n"
                        f"Por favor, valida el pago, busca la clave y envíala con el comando:\n"
                        f"`clave {from_number} LA_CLAVE_SECRETA`"
                    )
                send_text_message(ADMIN_WHATSAPP_NUMBER, notificacion)
                return

        # --- FILTRO 3: PALABRAS DE CANCELACIÓN ---
        if any(palabra in text_body.lower() for palabra in PALABRAS_CANCELACION):
            if session := get_session(from_number):
                delete_session(from_number)
                send_text_message(from_number, "Hecho. He cancelado el proceso. Si necesitas algo más, escríbeme. 😊")
            return

        # --- LÓGICA PRINCIPAL: FLUJO DE VENTA O MENSAJE INICIAL ---
        if not (session := get_session(from_number)):
            # Usar text_body original para la búsqueda de producto
            handle_initial_message(from_number, user_name, text_body if message_type == 'text' else "collar girasol")
        else:
            # Usar text_body original para el flujo de ventas
            handle_sales_flow(from_number, text_body if message_type == 'text' else text_body.replace('_', ' ').replace(' Recibida', ''), session)
            
    except Exception as e:
        logger.error(f"Error fatal en process_message: {e}")

@app.route('/')
def home():
    return jsonify({'status': 'Bot Daaqui Activo - V9.1 - CÓDIGO FINAL COMPLETO'})

# ==============================================================================
# 9. ENDPOINT PARA AUTOMATIZACIONES (MAKE.COM)
# ==============================================================================
@app.route('/api/send-tracking', methods=['POST'])
def send_tracking_code():
    if (auth_header := request.headers.get('Authorization')) is None or auth_header != f'Bearer {MAKE_SECRET_TOKEN}':
        logger.warning("Acceso no autorizado a /api/send-tracking")
        return jsonify({'error': 'No autorizado'}), 401
    
    data = request.get_json()
    to_number, nro_orden, codigo_recojo = data.get('to_number'), data.get('nro_orden'), data.get('codigo_recojo')
    
    if not to_number or not nro_orden:
        logger.error("Faltan parámetros en la solicitud de Make.com")
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    try:
        customer_name = "cliente"
        if db and (customer_doc := db.collection('clientes').document(str(to_number)).get()).exists:
            customer_name = customer_doc.to_dict().get('nombre_perfil_wa', 'cliente')

        # --- MENSAJES AUTOMÁTICOS DE SEGUIMIENTO ---
        message_1 = (f"¡Hola {customer_name}! 👋🏽✨\n\n¡Excelentes noticias! Tu pedido de Daaqui Joyas ha sido enviado y ya está en camino. 🚚\n\n"
                     f"Aquí tienes los datos para el seguimiento con la agencia Shalom:\n👉🏽 *Nro. de Orden:* {nro_orden}" +
                     (f"\n👉🏽 *Código de Recojo:* {codigo_recojo}" if codigo_recojo else "") +
                     "\n\nA continuación, te explico los pasos a seguir:")
        send_text_message(str(to_number), message_1)
        time.sleep(2)

        message_2 = ("*Por favor, sigue estos pasos para una entrega exitosa:* 👇\n\n"
                     "*1. HAZ EL SEGUIMIENTO:* 📲\nTe recomendamos descargar la app *\"Mi Shalom\"*. Si eres cliente nuevo, necesitarás registrarte. Con los datos de arriba, podrás ver en tiempo real dónde se encuentra tu paquete.\n\n"
                     "*2. PAGA EL SALDO CUANDO LLEGUE:* 💳\nCuando la app confirme que tu pedido llegó a la agencia, por favor, yapea o plinea el saldo restante. Haz este paso *antes de ir a la agencia*. ¡Así tu recojo será súper rápido! 💨\n\n"
                     "*3. AVISA Y RECIBE TU CLAVE:* 🔑\nApenas nos envíes la captura de tu pago, lo validaremos y te responderemos con la *clave secreta de recojo*. ¡La necesitarás junto a tu DNI para recibir tu joya! 🎁")
        send_text_message(str(to_number), message_2)
        time.sleep(2)

        message_3 = ("✨ *¡Ya casi es tuya! Tu último paso es el más importante.* ✨\n\n"
                     "Para que podamos darte atención prioritaria, por favor, responde a este chat con la **captura de tu pago**.\n\n"
                     "¡Estaremos súper atentos para enviarte tu clave secreta al instante! La necesitarás junto a tu DNI para recibir tu joya. 🎁")
        send_text_message(str(to_number), message_3)

        logger.info(f"Mensajes de envío (3) enviados a {to_number} por Make.com")
        return jsonify({'status': 'mensajes enviados'}), 200
    except Exception as e:
        logger.error(f"Error crítico en send_tracking_code: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500