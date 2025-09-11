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

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

# ==========================================================
# INICIALIZACIÓN DE FIREBASE
# ==========================================================
try:
    service_account_info_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    if service_account_info_str:
        service_account_info = json.loads(service_account_info_str)
        cred = credentials.Certificate(service_account_info)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Conexión con Firebase establecida correctamente.")
    else:
        logger.error("❌ La variable de entorno FIREBASE_SERVICE_ACCOUNT_JSON no está configurada.")
        db = None
except Exception as e:
    logger.error(f"❌ Error crítico inicializando Firebase: {e}")
    db = None

app = Flask(__name__)

# ==========================================================
# 2. CONFIGURACIÓN DEL NEGOCIO Y VARIABLES GLOBALES
# ==========================================================
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ADMIN_WHATSAPP_NUMBER = os.environ.get('ADMIN_WHATSAPP_NUMBER')
RUC_EMPRESA = "10700761130"
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]

# ==============================================================================
# 3. FUNCIONES DE COMUNICACIÓN CON WHATSAPP
# ==============================================================================
def send_whatsapp_message(to_number, message_data):
    """Función genérica para enviar mensajes a través de la API de WhatsApp."""
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
    """Envía un mensaje de texto."""
    send_whatsapp_message(to_number, {"type": "text", "text": {"body": text}})

def send_image_message(to_number, image_url):
    """Envía una imagen."""
    send_whatsapp_message(to_number, {"type": "image", "image": {"link": image_url}})

# ==============================================================================
# 4. FUNCIONES DE INTERACCIÓN CON FIRESTORE
# ==============================================================================
def get_session(user_id):
    if not db: return None
    try:
        doc_ref = db.collection('sessions').document(user_id)
        doc = doc_ref.get()
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
            product_ref = db.collection('productos').document(product_id)
            product_doc = product_ref.get()
            if product_doc.exists:
                return product_id, product_doc.to_dict()
    except Exception as e:
        logger.error(f"Error buscando producto por palabras clave: {e}")
    return None, None

# ==============================================================================
# 5. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS)
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
            time.sleep(2) # Pausa estratégica reducida

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
            "user_name": user_name
        }
        save_session(from_number, new_session)
    else:
        send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA)
# ==============================================================================
def handle_sales_flow(from_number, text, session):
    if any(keyword in text.lower() for keyword in KEYWORDS_GIRASOL):
        logger.info(f"Usuario {from_number} está reiniciando el flujo.")
        delete_session(from_number)
        handle_initial_message(from_number, session.get("user_name", "Usuario"), text)
        return

    current_state = session.get('state')
    product_id = session.get('product_id')
    product_ref = db.collection('productos').document(product_id)
    product_data = product_ref.get().to_dict()

    if not product_data:
        send_text_message(from_number, "Hubo un problema al obtener los detalles del producto. Intenta de nuevo.")
        delete_session(from_number)
        return

    if current_state == 'awaiting_occasion_response':
        url_imagen_empaque = product_data.get('imagenes', {}).get('empaque')
        detalles = product_data.get('detalles', {})
        material = detalles.get('material', 'material de alta calidad')
        presentacion = detalles.get('empaque', 'viene en una hermosa caja de regalo')

        if url_imagen_empaque:
            send_image_message(from_number, url_imagen_empaque)
            time.sleep(2) # Pausa estratégica reducida

        # Bloque de mensaje 1: Detalles del producto
        mensaje_persuasion_1 = (
            "¡Maravillosa elección! ✨ El *Collar Mágico Girasol Radiant* es pura energía. Aquí tienes todos los detalles:\n\n"
            f"💎 *Material:* {material} ¡Hipoalergénico y no se oscurece!\n"
            f"🔮 *La Magia:* Su piedra central es termocromática, cambia de color con tu temperatura.\n"
            f"🎁 *Presentación:* {presentacion}, ¡lista para sorprender!"
        )
        send_text_message(from_number, mensaje_persuasion_1)
        time.sleep(2) # Pausa para dar tiempo de lectura

        # Bloque de mensaje 2: Ancla de confianza y llamada a la acción
        mensaje_persuasion_2 = (
            f"Para tu total seguridad, somos Daaqui Joyas, un negocio formal con *RUC {RUC_EMPRESA}*. ¡Tu compra es 100% segura! 🇵🇪\n\n"
            "¿Te gustaría coordinar tu pedido ahora para asegurar el tuyo? (Sí/No)"
        )
        send_text_message(from_number, mensaje_persuasion_2)
        save_session(from_number, {"state": "awaiting_purchase_decision"})

    elif current_state == 'awaiting_purchase_decision':
        if 'si' in text.lower() or 'sí' in text.lower():
            url_imagen_upsell = product_data.get('imagenes', {}).get('upsell')
            
            # Bloque de mensaje 1: La oferta
            upsell_message_1 = (
                "¡Excelente elección! Pero espera, antes de continuar... por haber decidido llevar tu collar, ¡acabas de desbloquear una oferta exclusiva! ✨\n\n"
                "Añade un *segundo Collar Mágico* a tu pedido y te incluimos de regalo *dos cadenas de diseño italiano* para que combines tus dijes como quieras.\n\n"
                "En resumen, tu pedido se ampliaría a:\n"
                "✨ 2 Collares Mágicos\n"
                "🎁 2 Cadenas de Regalo de diseño\n"
                "🎀 2 Cajitas de Regalo Premium Daaqui\n"
                "💎 Todo por un único pago de *S/ 99.00*"
            )
            send_text_message(from_number, upsell_message_1)
            time.sleep(2) # Pausa para dar tiempo de lectura

            # Se envía la imagen de la oferta en medio de los textos
            if url_imagen_upsell:
                send_image_message(from_number, url_imagen_upsell)
                time.sleep(2)

            # Bloque de mensaje 2: Urgencia y llamada a la acción
            upsell_message_2 = (
                "*Esta oferta especial es válida solo para los pedidos confirmados hoy.*\n\n"
                "Para continuar, por favor, respóndeme con una de estas dos palabras:\n"
                "👉🏽 Escribe *\"oferta\"* para ampliar tu pedido.\n"
                "👉🏽 Escribe *\"continuar\"* para llevar solo un collar."
            )
            send_text_message(from_number, upsell_message_2)

            save_session(from_number, {"state": "awaiting_upsell_decision"})
        else:
            delete_session(from_number)
            send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré para ayudarte. ¡Que tengas un buen día! 😊")

    # (Aquí iría el resto del flujo de venta: awaiting_upsell_decision, awaiting_location, etc.)
    # Esto se completará en los siguientes pasos (Paso 3 y 4 del plan).

    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar, escribe 'cancelar'.")

# ==============================================================================
# 7. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode, token, challenge = request.args.get('hub.mode'), request.args.get('hub.verify_token'), request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge
        return 'Forbidden', 403
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        if change.get('field') == 'messages':
                            value = change.get('value', {})
                            if value.get('messages'):
                                for message in value.get('messages'):
                                    process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    try:
        from_number = message.get('from')
        user_name = next((c.get('profile', {}).get('name', 'Usuario') for c in contacts if c.get('wa_id') == from_number), 'Usuario')
        
        if message.get('type') != 'text':
            send_text_message(from_number, "Por ahora solo puedo entender mensajes de texto. 😊")
            return

        text_body = message.get('text', {}).get('body', '')
        logger.info(f"Procesando de {user_name} ({from_number}): '{text_body}'")

        if text_body.lower() in PALABRAS_CANCELACION:
            delete_session(from_number)
            send_text_message(from_number, "Hecho. He cancelado el proceso actual. Si necesitas algo más, no dudes en escribirme. 😊")
            return

        session = get_session(from_number)
        if not session:
            handle_initial_message(from_number, user_name, text_body)
        else:
            handle_sales_flow(from_number, text_body, session)
    except Exception as e:
        logger.error(f"Error en process_message: {e}")

@app.route('/')
def home():
    return jsonify({'status': 'Bot Daaqui Activo - V2 Firestore'})

if __name__ == '__main__':
    app.run(debug=True)

