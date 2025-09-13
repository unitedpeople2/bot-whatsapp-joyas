# -*- coding: utf-8 -*-
# ==========================================================
# BOT DAAQUI JOYAS - V10.1 - REFACTORIZADO FINAL
# Archivo principal: maneja la configuración inicial y los webhooks.
# ==========================================================
from flask import Flask, request, jsonify
import logging
from logging import getLogger
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
import time

# --- Importaciones de nuestros nuevos módulos ---
from bot_utils import find_key_in_sheet, send_text_message, get_session, delete_session
from bot_logic import handle_initial_message, handle_sales_flow

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

# ==========================================================
# INICIALIZACIÓN DE FIREBASE Y CARGA DE CONFIGURACIÓN
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
        logger.info("✅ Conexión con Firebase establecida.")

        if (rules_doc := db.collection('configuracion').document('reglas_envio').get()).exists:
            BUSINESS_RULES = rules_doc.to_dict()
            logger.info("✅ Reglas del negocio cargadas.")
        else:
            logger.error("❌ Documento de reglas de envío no encontrado.")

        if (faq_doc := db.collection('configuracion').document('respuestas_faq').get()).exists:
            FAQ_RESPONSES = faq_doc.to_dict()
            logger.info("✅ Respuestas FAQ cargadas.")
        else:
            logger.error("❌ Documento de respuestas_faq no encontrado.")
    else:
        logger.error("❌ Variable de entorno FIREBASE_SERVICE_ACCOUNT_JSON no configurada.")
except Exception as e:
    logger.error(f"❌ Error crítico en inicialización: {e}")

app = Flask(__name__)

# ==========================================================
# CARGA DE VARIABLES DE ENTORNO
# ==========================================================
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
ADMIN_WHATSAPP_NUMBER = os.environ.get('ADMIN_WHATSAPP_NUMBER')
MAKE_SECRET_TOKEN = os.environ.get('MAKE_SECRET_TOKEN')
RUC_EMPRESA = "10700761130"
TITULAR_YAPE = "Hedinson Rojas Mattos"
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]
FAQ_KEYWORD_MAP = {
    'precio': ['precio', 'valor', 'costo'], 'envio': ['envío', 'envio', 'delivery', 'mandan', 'entrega'],
    'pago': ['pago', 'pagar', 'métodos de pago', 'contraentrega', 'yape', 'plin'], 'tienda': ['tienda', 'local', 'ubicación'],
    'transferencia': ['transferencia', 'banco', 'bcp', 'interbank', 'cuenta'], 'material': ['material', 'acero', 'alergia'],
    'cuidados': ['mojar', 'agua', 'oxida', 'negro', 'cuidar'], 'garantia': ['garantía', 'garantia', 'falla', 'roto'],
    'cambios_devoluciones': ['cambio', 'cambiar', 'devolución'], 'stock': ['stock', 'disponible', 'tienen', 'hay']
}

# ==============================================================================
# 8. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
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

        if from_number == ADMIN_WHATSAPP_NUMBER and text_body.lower().startswith('clave '):
            parts = text_body.split()
            if len(parts) == 3:
                target_number, secret_key = parts[1], parts[2]
                if target_number.isdigit():
                    msg = (f"¡Gracias por confirmar tu pago! ✨\n\n"
                           f"Aquí tienes tu clave secreta para recoger tu pedido:\n\n"
                           f"🔑 *CLAVE:* {secret_key}\n\n¡Que disfrutes tu joya!")
                    send_text_message(target_number, msg)
                    send_text_message(from_number, f"✅ Clave '{secret_key}' enviada a {target_number}.")
                else:
                    send_text_message(from_number, f"❌ Error: El número '{target_number}' no parece válido.")
            else:
                send_text_message(from_number, "❌ Error: Usa: clave <numero> <clave>")
            return

        if db and (ventas_pendientes := db.collection('ventas').where('cliente_id', '==', from_number).where('estado_pedido', '==', 'Adelanto Pagado').limit(1).get()) and message_type == 'image':
            clave_encontrada = find_key_in_sheet(from_number)
            
            # Mensaje 1: La información
            notificacion_info = (f"🔔 *¡Atención! Posible Pago Final Recibido* 🔔\n\n"
                                 f"*Cliente:* {user_name}\n*WA ID:* {from_number}\n")
            
            if clave_encontrada:
                notificacion_info += f"*Clave Encontrada:* `{clave_encontrada}`"
                # Mensaje 2: El comando listo para copiar
                comando_listo = f"clave {from_number} {clave_encontrada}"
                
                send_text_message(ADMIN_WHATSAPP_NUMBER, notificacion_info)
                time.sleep(1) 
                send_text_message(ADMIN_WHATSAPP_NUMBER, comando_listo)
            else:
                notificacion_info += ("*Clave:* No encontrada en Sheet.\n\n"
                                      f"Busca la clave y envíala con:\n`clave {from_number} LA_CLAVE_SECRETA`")
                send_text_message(ADMIN_WHATSAPP_NUMBER, notificacion_info)
            return

        if any(palabra in text_body.lower() for palabra in PALABRAS_CANCELACION):
            if get_session(from_number):
                delete_session(from_number)
                send_text_message(from_number, "Hecho. He cancelado el proceso. Si necesitas algo más, escríbeme. 😊")
            return

        if not (session := get_session(from_number)):
            handle_initial_message(from_number, user_name, text_body if message_type == 'text' else "collar girasol", FAQ_KEYWORD_MAP, FAQ_RESPONSES, KEYWORDS_GIRASOL)
        else:
            handle_sales_flow(from_number, text_body if message_type == 'text' else "COMPROBANTE_RECIBIDO", session, FAQ_KEYWORD_MAP, FAQ_RESPONSES, KEYWORDS_GIRASOL, BUSINESS_RULES, RUC_EMPRESA, TITULAR_YAPE, ADMIN_WHATSAPP_NUMBER)
            
    except Exception as e:
        logger.error(f"Error fatal en process_message: {e}")

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

        message_1 = (f"¡Hola {customer_name}! 👋🏽✨\n\n¡Excelentes noticias! Tu pedido de Daaqui Joyas ha sido enviado. 🚚\n\n"
                     f"Datos para seguimiento Shalom:\n👉🏽 *Nro. de Orden:* {nro_orden}" +
                     (f"\n👉🏽 *Código de Recojo:* {codigo_recojo}" if codigo_recojo else "") +
                     "\n\nA continuación, los pasos a seguir:")
        send_text_message(str(to_number), message_1)
        time.sleep(2)
        message_2 = ("*Pasos para una entrega exitosa:* 👇\n\n"
                     "*1. HAZ EL SEGUIMIENTO:* 📲\nDescarga la app *\"Mi Shalom\"*. Si eres nuevo, regístrate. Con los datos de arriba, podrás ver el estado de tu paquete.\n\n"
                     "*2. PAGA EL SALDO CUANDO LLEGUE:* 💳\nCuando la app confirme que tu pedido llegó a la agencia, yapea o plinea el saldo restante. Haz este paso *antes de ir a la agencia*.\n\n"
                     "*3. AVISA Y RECIBE TU CLAVE:* 🔑\nApenas nos envíes la captura de tu pago, lo validaremos y te daremos la *clave secreta de recojo*. ¡La necesitarás junto a tu DNI! 🎁")
        send_text_message(str(to_number), message_2)
        time.sleep(2)
        message_3 = ("✨ *¡Ya casi es tuya! Tu último paso es el más importante.* ✨\n\n"
                     "Para darte atención prioritaria, responde este chat con la **captura de tu pago**.\n\n"
                     "¡Estaremos atentos para enviarte tu clave al instante! La necesitarás junto a tu DNI para recibir tu joya. 🎁")
        send_text_message(str(to_number), message_3)

        return jsonify({'status': 'mensajes enviados'}), 200
    except Exception as e:
        logger.error(f"Error crítico en send_tracking_code: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/')
def home():
    return jsonify({'status': 'Bot Daaqui Activo - V10.1 - REFACTORIZADO FINAL'})