# -*- coding: utf-8 -*-
# ==========================================================
# BOT DAAQUI JOYAS - V6.6 - PULIDO FINAL DE MENSAJES
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
RUC_EMPRESA = "10700761130"
TITULAR_YAPE = "Hedinson Rojas Mattos"
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]

FAQ_KEYWORD_MAP = {
    'precio': ['precio', 'valor', 'costo'],
    'envio': ['envío', 'envio', 'delivery', 'mandan', 'entrega', 'cuesta el envío'],
    'pago': ['pago', 'pagar', 'contraentrega', 'contra entrega', 'yape', 'plin'],
    'tienda': ['tienda', 'local', 'ubicación', 'ubicacion', 'dirección', 'direccion'],
    'material': ['material', 'acero', 'alergia', 'hipoalergenico'],
    'cuidados': ['mojar', 'agua', 'oxida', 'negro', 'cuidar', 'limpiar', 'cuidados'],
    'garantia': ['garantía', 'garantia', 'falla', 'defectuoso', 'roto', 'cambio', 'cambiar'],
    'transferencia': ['transferencia', 'banco', 'bcp', 'interbank', 'cuenta', 'transferir']
}

# ==============================================================================
# 3. FUNCIONES DE COMUNICACIÓN CON WHATSAPP
# ==============================================================================
# ... (Esta sección no cambia)
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
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a {to_number}: {e.response.text if e.response else e}")

def send_text_message(to_number, text):
    send_whatsapp_message(to_number, {"type": "text", "text": {"body": text}})

def send_image_message(to_number, image_url):
    send_whatsapp_message(to_number, {"type": "image", "image": {"link": image_url}})
# ...

# ==============================================================================
# 4. FUNCIONES DE INTERACCIÓN CON FIRESTORE
# ==============================================================================
# ... (Esta sección no cambia)
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
# ...

# ==============================================================================
# 5. FUNCIONES AUXILIARES DE LÓGICA DE NEGOCIO
# ==============================================================================
# ... (Esta sección no cambia, excepto una corrección de formato menor en un mensaje)
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
        logger.info(f"[Sheets] ¡ÉXITO! Pedido {sale_data.get('id_venta')} guardado.")
        return True
    except Exception as e:
        logger.error(f"[Sheets] ERROR INESPERADO: {e}")
        return False

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
# ...

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS)
# ==============================================================================
# ... (Esta sección no cambia)
def handle_initial_message(from_number, user_name, text):
    # PRIORIDAD 1: Buscar si el mensaje es sobre un producto específico.
    product_id, product_data = find_product_by_keywords(text)
    if product_data:
        nombre_producto = product_data.get('nombre', 'nuestro producto')
        descripcion_corta = product_data.get('descripcion_corta', 'es simplemente increíble.')
        precio = product_data.get('precio_base', 0)
        url_imagen_principal = product_data.get('imagenes', {}).get('principal')

        if url_imagen_principal:
            send_image_message(from_number, url_imagen_principal)
            time.sleep(1)

        mensaje_inicial = (
            f"¡Hola {user_name}! 🌞 El *{nombre_producto}* {descripcion_corta}\n\n"
            f"Por nuestra campaña del 21 de Septiembre, llévatelo a un precio especial de *S/ {precio:.2f}* "
            "(¡incluye envío gratis a todo el Perú! 🚚).\n\n"
            "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?"
        )
        send_text_message(from_number, mensaje_inicial)

        new_session = {
            "state": "awaiting_occasion_response", "product_id": product_id,
            "product_name": nombre_producto, "product_price": float(precio),
            "user_name": user_name, "whatsapp_id": from_number,
            "is_upsell": False
        }
        save_session(from_number, new_session)
        return

    # PRIORIDAD 2: Si no es sobre un producto, buscar si es una pregunta frecuente.
    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            response_text = FAQ_RESPONSES.get(key)
            if response_text:
                send_text_message(from_number, response_text)
                return

    # PRIORIDAD 3: Si no es ninguna de las anteriores, dar el saludo general.
    send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")
# ...

# ==============================================================================
# 7. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA)
# ==============================================================================
def handle_sales_flow(from_number, text, session):
    # --- INICIO DEL DETECTOR FAQ ---
    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            if key == 'precio' and session.get('product_name'):
                product_name = session.get('product_name')
                product_price = session.get('product_price')
                response_text = f"¡Claro! El precio actual de tu pedido (*{product_name}*) es de *S/ {product_price:.2f}*, con envío gratis. 🚚"
            else:
                response_text = FAQ_RESPONSES.get(key)

            if response_text:
                send_text_message(from_number, response_text)
                time.sleep(1)
                last_question = get_last_question(session.get('state'))
                if last_question:
                    re_prompt = f"¡Espero haber aclarado tu duda! 😊 Continuando con la coordinación de tu pedido...\n\n{last_question}"
                    send_text_message(from_number, re_prompt)
                return
    # --- FIN DEL DETECTOR FAQ ---
    
    # ... (El resto del código se mantiene igual hasta el bloque de pago)

    # <<<--- INICIO DEL BLOQUE DE CÓDIGO CON LOS CAMBIOS ---<<<
    if current_state in ['awaiting_lima_payment', 'awaiting_shalom_payment']:
        if text == "COMPROBANTE_RECIBIDO":
            guardado_exitoso, sale_data = save_completed_sale_and_customer(session)
            if guardado_exitoso:
                guardar_pedido_en_sheet(sale_data)
                
                if ADMIN_WHATSAPP_NUMBER:
                    admin_message = (
                        f"🎉 ¡Nueva Venta Confirmada! 🎉\n\n"
                        f"Producto: {sale_data.get('producto_nombre')}\n"
                        f"Precio: S/ {sale_data.get('precio_venta'):.2f}\n"
                        f"Tipo: {sale_data.get('tipo_envio')}\n"
                        f"Adelanto: S/ {sale_data.get('adelanto_recibido'):.2f}\n"
                        f"Cliente WA ID: {sale_data.get('cliente_id')}\n"
                        f"Detalles:\n{sale_data.get('detalles_cliente')}"
                    )
                    send_text_message(ADMIN_WHATSAPP_NUMBER, admin_message)

                if session.get('tipo_envio') == 'Lima Contra Entrega':
                    total = sale_data.get('precio_venta', 0)
                    adelanto = sale_data.get('adelanto_recibido', 0)
                    restante = total - adelanto
                    dia_entrega = get_delivery_day_message()
                    horario = BUSINESS_RULES.get('horario_entrega_lima', 'durante el día')
                    
                    mensaje_final = (
                        "¡Adelanto confirmado! ✨ Hemos agendado tu pedido.\n\n"
                        "*Resumen Financiero:*\n"
                        f"💸 Total del pedido: S/ {total:.2f}\n"
                        f"✅ Adelanto: - S/ {adelanto:.2f}\n"
                        "--------------------\n"
                        f"💵 Pagarás al recibir: S/ {restante:.2f}\n\n"
                        f"🗓️ Lo estarás recibiendo *{dia_entrega}*, en el rango de *{horario}*.\n\n"
                        "Para garantizar una entrega exitosa, te agradecemos asegurar que alguien esté disponible para recibir tu joya.\n\n"
                        "¡Gracias por tu compra en Daaqui Joyas! 🎉"
                    )
                    send_text_message(from_number, mensaje_final)
                else: # Shalom (Lima sin cobertura o Provincia)
                    total = sale_data.get('precio_venta', 0)
                    adelanto = sale_data.get('adelanto_recibido', 0)
                    restante = total - adelanto
                    
                    mensaje_financiero = (
                        "*Resumen Financiero:*\n"
                        f"💸 Total del pedido: S/ {total:.2f}\n"
                        f"✅ Adelanto: - S/ {adelanto:.2f}\n"
                        "--------------------\n"
                        f"💵 Saldo restante: S/ {restante:.2f}\n\n"
                    )
                    
                    mensaje_base = f"¡Adelanto confirmado! ✨ Hemos agendado tu envío.\n\n{mensaje_financiero}Te enviaremos tu código de seguimiento por aquí en las próximas *24h hábiles*. "
                    
                    if session.get('tipo_envio') == 'Lima Shalom':
                        mensaje_final = mensaje_base + "A partir del momento en que recibas tu código, el tiempo de entrega en la agencia es de *1 a 2 días hábiles*."
                    else: # Provincia Shalom
                        mensaje_final = mensaje_base + "A partir del momento en que recibas tu código, el tiempo de entrega en la agencia es de *3 a 5 días hábiles*."
                    
                    send_text_message(from_number, mensaje_final)
                
                delete_session(from_number)
            else:
                send_text_message(from_number, "¡Uy! Hubo un problema al registrar tu pedido. Un asesor se pondrá en contacto contigo pronto.")
        else:
            send_text_message(from_number, "Estoy esperando la *captura de pantalla* de tu pago. 😊")

    elif current_state == 'awaiting_province_district':
        provincia, distrito = parse_province_district(text)
        session.update({
            "state": "awaiting_shalom_agreement", "tipo_envio": "Provincia Shalom", 
            "metodo_pago": "Adelanto y Saldo (Yape/Plin)", "provincia": provincia, "distrito": distrito
        })
        save_session(from_number, session)
        adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
        mensaje = (
            f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}*. "
            f"Este monto funciona como un *compromiso para el recojo del pedido*. 🤝\n\n"
            "¿Estás de acuerdo? (Sí/No)"
        )
        send_text_message(from_number, mensaje)
        
    elif current_state == 'awaiting_lima_district':
        distrito, status = normalize_and_check_district(text)
        if status != 'NO_ENCONTRADO':
            session['distrito'] = distrito
            if status == 'CON_COBERTURA':
                # ... código sin cambios ...
                session.update({
                    "state": "awaiting_delivery_details", "tipo_envio": "Lima Contra Entrega",
                    "metodo_pago": "Contra Entrega (Efectivo/Yape/Plin)"
                })
                save_session(from_number, session)
                mensaje = (
                    "¡Excelente! Tenemos cobertura en *{distrito}*. 🏙️\n\n"
                    "Para registrar tu pedido, por favor, envíame en *un solo mensaje* tu *Nombre Completo*, *Dirección exacta* y una *Referencia* (muy importante para el motorizado).\n\n"
                    "📝 *Ej: Ana Pérez, Jr. Gamarra 123, Depto 501, La Victoria. Al lado de la farmacia Inkafarma.*"
                )
                send_text_message(from_number, mensaje.format(distrito=distrito))
            elif status == 'SIN_COBERTURA':
                # ... código con formato corregido ...
                session.update({
                    "state": "awaiting_shalom_agreement", "tipo_envio": "Lima Shalom",
                    "metodo_pago": "Adelanto y Saldo (Yape/Plin)", "distrito": distrito
                })
                save_session(from_number, session)
                adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
                mensaje = (
                    f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}*. "
                    f"Este monto funciona como un *compromiso para el recojo del pedido*. 🤝\n\n"
                    "¿Estás de acuerdo? (Sí/No)"
                )
                send_text_message(from_number, mensaje)
        else:
            send_text_message(from_number, "No pude reconocer ese distrito. Por favor, intenta escribirlo de nuevo.")
    
    # ... (El resto de los estados se mantienen sin cambios lógicos)
    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar, escribe 'cancelar'.")


# ==============================================================================
# 8. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
# ... (Esta sección no cambia)
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
        
        message_type = message.get('type')
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '')
        elif message_type == 'image':
            text_body = "COMPROBANTE_RECIBIDO"
        else:
            send_text_message(from_number, "Por ahora solo puedo procesar mensajes de texto e imágenes de comprobantes. 😊")
            return

        logger.info(f"Procesando de {user_name} ({from_number}): '{text_body}'")

        if text_body.lower() in PALABRAS_CANCELACION:
            if get_session(from_number):
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
    return jsonify({'status': 'Bot Daaqui Activo - V6.6 - PULIDO FINAL'})