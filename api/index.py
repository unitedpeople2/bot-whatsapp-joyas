# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
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

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

# ==========================================================
# INICIALIZACIÓN DE FIREBASE Y REGLAS DE NEGOCIO
# ==========================================================
db = None
BUSINESS_RULES = {}
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
RUC_EMPRESA = "10700761130"
TITULAR_YAPE = "Hedinson Rojas Mattos"
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]

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
        logger.info(f"Mensaje enviado a {to_number}.")
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
        
        # Preparar datos para la venta
        sale_data = {
            "fecha": firestore.SERVER_TIMESTAMP,
            "producto_id": session_data.get('product_id'),
            "producto_nombre": session_data.get('product_name'),
            "precio_venta": session_data.get('product_price'),
            "tipo_envio": session_data.get('tipo_envio'),
            "provincia": session_data.get('provincia'),
            "distrito": session_data.get('distrito'),
            "detalles_cliente": session_data.get('detalles_cliente'),
            "cliente_id": customer_id,
            "estado_pedido": "Pagado"
        }
        db.collection('ventas').document(sale_id).set(sale_data)
        logger.info(f"Venta {sale_id} guardada en Firestore.")

        # Preparar y guardar/actualizar datos del cliente
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

        return True, sale_id
    except Exception as e:
        logger.error(f"Error guardando venta y cliente en Firestore: {e}")
        return False, None

# ==============================================================================
# 5. FUNCIONES AUXILIARES DE LÓGICA DE NEGOCIO
# ==============================================================================
def normalize_and_check_district(text):
    clean_text = text.lower().strip()
    abreviaturas = BUSINESS_RULES.get('abreviaturas_distritos', {})
    for abbr, full_name in abreviaturas.items():
        if abbr == clean_text:
            clean_text = full_name
            break
    distritos_cobertura = BUSINESS_RULES.get('distritos_cobertura_delivery', [])
    for distrito in distritos_cobertura:
        if re.search(r'\b' + re.escape(distrito) + r'\b', clean_text):
            return distrito.title(), 'CON_COBERTURA'
    distritos_totales = BUSINESS_RULES.get('distritos_lima_total', [])
    for distrito in distritos_totales:
        if re.search(r'\b' + re.escape(distrito) + r'\b', clean_text):
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
    if weekday < 5: # Lunes a Viernes
        return BUSINESS_RULES.get('mensaje_dia_habil', 'mañana')
    else: # Sábado y Domingo
        return BUSINESS_RULES.get('mensaje_fin_semana', 'el Lunes')

def guardar_pedido_en_sheet(sale_data, sale_id):
    try:
        logger.info("[Sheets] Iniciando proceso de guardado...")
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not creds_json_str or not sheet_name:
            logger.error("[Sheets] ERROR: Faltan variables de entorno para Google Sheets.")
            return False
        
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open(sheet_name)
        worksheet = spreadsheet.sheet1
        
        nueva_fila = [
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            sale_id,
            sale_data.get('producto_nombre', 'N/A'),
            sale_data.get('precio_venta', 'N/A'),
            sale_data.get('tipo_envio', 'N/A'),
            sale_data.get('provincia', 'N/A'),
            sale_data.get('distrito', 'N/A'),
            sale_data.get('detalles_cliente', 'N/A'),
            sale_data.get('cliente_id', 'N/A')
        ]
        worksheet.append_row(nueva_fila)
        logger.info(f"[Sheets] ¡ÉXITO! Pedido {sale_id} guardado.")
        return True
    except Exception as e:
        logger.error(f"[Sheets] ERROR INESPERADO: {e}")
        return False

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS)
# ==============================================================================
def handle_initial_message(from_number, user_name, text):
    product_id, product_data = find_product_by_keywords(text)
    if product_data:
        nombre_producto = product_data.get('nombre', 'nuestro producto')
        descripcion_corta = product_data.get('descripcion_corta', 'es simplemente increíble.')
        precio = product_data.get('precio_base', 0)
        url_imagen_principal = product_data.get('imagenes', {}).get('principal')

        if url_imagen_principal:
            send_image_message(from_number, url_imagen_principal)
            time.sleep(2)

        mensaje_inicial = (
            f"¡Hola {user_name}! 🌞 El *{nombre_producto}* {descripcion_corta}\n\n"
            f"Por nuestra campaña del 21 de Septiembre, llévatelo a un precio especial de *S/ {precio:.2f}* "
            "(¡incluye envío gratis a todo el Perú! 🚚).\n\n"
            "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?"
        )
        send_text_message(from_number, mensaje_inicial)

        new_session = {
            "state": "awaiting_occasion_response", "product_id": product_id,
            "product_name": nombre_producto, "product_price": precio,
            "user_name": user_name, "whatsapp_id": from_number
        }
        save_session(from_number, new_session)
    else:
        send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")

# ==============================================================================
# 7. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA)
# ==============================================================================
def handle_sales_flow(from_number, text, session):
    if any(keyword in text.lower() for keyword in KEYWORDS_GIRASOL) and session.get('state') != 'awaiting_occasion_response':
        logger.info(f"Usuario {from_number} está reiniciando el flujo.")
        delete_session(from_number)
        handle_initial_message(from_number, session.get("user_name", "Usuario"), text)
        return

    current_state = session.get('state')
    product_id = session.get('product_id')
    if not product_id:
        send_text_message(from_number, "Hubo un problema, no sé qué producto estás comprando. Por favor, empieza de nuevo.")
        delete_session(from_number)
        return
        
    product_doc = db.collection('productos').document(product_id).get()
    if not product_doc.exists:
        send_text_message(from_number, "Lo siento, parece que este producto ya no está disponible.")
        delete_session(from_number)
        return
    product_data = product_doc.to_dict()

    # --- Flujo de venta principal ---

    if current_state == 'awaiting_occasion_response':
        # ... (código para enviar el segundo mensaje de persuasión)
        save_session(from_number, {"state": "awaiting_purchase_decision"})
    
    elif current_state == 'awaiting_purchase_decision':
        if 'si' in text.lower() or 'sí' in text.lower():
            oferta_upsell = product_data.get('oferta_upsell')
            if oferta_upsell and oferta_upsell.get('activo'):
                # ... (código para enviar el upsell)
                save_session(from_number, {"state": "awaiting_upsell_decision"})
            else:
                save_session(from_number, {"state": "awaiting_location"})
                send_text_message(from_number, "¡Perfecto! Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?")
        else:
            delete_session(from_number)
            send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré. ¡Que tengas un buen día! 😊")

    elif current_state == 'awaiting_upsell_decision':
        oferta_upsell = product_data.get('oferta_upsell', {})
        if 'oferta' in text.lower():
            session['product_name'] = oferta_upsell.get('nombre_producto_oferta', session['product_name'])
            session['product_price'] = oferta_upsell.get('precio_oferta', session['product_price'])
            send_text_message(from_number, "¡Genial! Has elegido la oferta. ✨")
        else: 
            send_text_message(from_number, "¡Perfecto! Continuamos con tu collar individual. ✨")
        save_session(from_number, {"state": "awaiting_location"})
        send_text_message(from_number, "Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?")

    elif current_state == 'awaiting_location':
        # ... (código para manejar Lima/Provincia)
        
    elif current_state == 'awaiting_province_district':
        provincia, distrito = parse_province_district(text)
        session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Provincia Shalom", "provincia": provincia, "distrito": distrito})
        # ... (código para justificar y pedir adelanto de Shalom)

    elif current_state == 'awaiting_lima_district':
        distrito, status = normalize_and_check_district(text)
        if status == 'CON_COBERTURA':
            session.update({"state": "awaiting_delivery_details", "tipo_envio": "Lima Contra Entrega", "provincia": "Lima", "distrito": distrito})
            # ... (código para pedir detalles de Lima Contra Entrega)
        elif status == 'SIN_COBERTURA':
            session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Lima Shalom", "provincia": "Lima", "distrito": distrito})
            # ... (código para justificar y pedir adelanto de Shalom)
        else:
            send_text_message(from_number, "No pude reconocer ese distrito. Por favor, intenta escribirlo de nuevo.")

    # ... (Resto de los estados: awaiting_shalom_agreement, awaiting_shalom_experience, awaiting_delivery_details, awaiting_final_confirmation, awaiting_payment_proof)
    # En el estado final (awaiting_payment_proof), se llamarían a las funciones:
    # save_completed_sale_and_customer(session)
    # guardar_pedido_en_sheet(session_data_para_sheet, sale_id)
    # delete_session(from_number)

    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar, escribe 'cancelar'.")

# ==============================================================================
# 8. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    # ... (código del webhook no cambia)

def process_message(message, contacts):
    # ... (código del procesador de mensajes no cambia)

@app.route('/')
def home():
    return jsonify({'status': 'Bot Daaqui Activo - V4 Final'})

if __name__ == '__main__':
    app.run(debug=True)