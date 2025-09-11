# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
import os
import re
import json
import firebase_admin
from firebase_admin import credentials, firestore

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
# Las variables de entorno se obtienen al inicio para claridad
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
ADMIN_WHATSAPP_NUMBER = os.environ.get('ADMIN_WHATSAPP_NUMBER')
RUC_EMPRESA = "10700761130" # RUC de la empresa para mensajes de confianza
KEYWORDS_GIRASOL = ["girasol", "radiant", "precio", "cambia de color"]

# Listas para la lógica de envíos en Lima (se reintroducen para el flujo de venta)
TODOS_LOS_DISTRITOS_LIMA = [ "ancón", "ate", "barranco", "breña", "carabayllo", "chaclacayo", "chorrillos", "cieneguilla", "comas", "el agustino", "independencia", "jesús maría", "la molina", "la victoria", "lince", "los olivos", "lurigancho-chosica", "chosica", "lurín", "magdalena del mar", "miraflores", "pachacámac", "pucusana", "pueblo libre", "puente piedra", "punta hermosa", "punta negra", "rímac", "san bartolo", "san borja", "san isidro", "san juan de lurigancho", "san juan de miraflores", "san luis", "san martín de porres", "san miguel", "santa anita", "santa maría del mar", "santa rosa", "santiago de surco", "surquillo", "villa el salvador", "villa maría del triunfo", "cercado de lima", "bellavista", "carmen de la legua", "la perla", "la punta", "ventanilla", "callao" ]
COBERTURA_DELIVERY_LIMA = [ "ate", "barranco", "bellavista", "breña", "callao", "carabayllo", "carmen de la legua", "cercado de lima", "chorrillos", "comas", "el agustino", "independencia", "jesus maria", "la molina", "la perla", "la punta", "la victoria", "lince", "los olivos", "magdalena", "miraflores", "pueblo libre", "puente piedra", "rimac", "san borja", "san isidro", "san juan de lurigancho", "san juan de miraflores", "san luis", "san martin de porres", "san miguel", "santa anita", "surco", "surquillo", "villa el salvador", "villa maria del triunfo" ]
ABREVIATURAS_DISTRITOS = { "sjl": "san juan de lurigancho", "sjm": "san juan de miraflores", "smp": "san martin de porres", "vmt": "villa maria del triunfo", "ves": "villa el salvador", "lima centro": "cercado de lima" }
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
        logger.info(f"Mensaje enviado a {to_number}. Respuesta: {response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a {to_number}: {e.response.text if e.response else e}")

def send_text_message(to_number, text):
    """Envía un mensaje de texto."""
    message_data = {"type": "text", "text": {"body": text}}
    send_whatsapp_message(to_number, message_data)

def send_image_message(to_number, image_url, caption=""):
    """Envía una imagen con una descripción opcional."""
    message_data = {"type": "image", "image": {"link": image_url, "caption": caption}}
    send_whatsapp_message(to_number, message_data)

# ==============================================================================
# 4. FUNCIONES DE INTERACCIÓN CON FIRESTORE (BASE DE DATOS)
# ==============================================================================
def get_session(user_id):
    """Obtiene la sesión de un usuario desde Firestore."""
    if not db: return None
    try:
        doc_ref = db.collection('sessions').document(user_id)
        doc = doc_ref.get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error obteniendo sesión para {user_id}: {e}")
        return None

def save_session(user_id, session_data):
    """Guarda o actualiza la sesión de un usuario en Firestore."""
    if not db: return
    try:
        db.collection('sessions').document(user_id).set(session_data, merge=True)
    except Exception as e:
        logger.error(f"Error guardando sesión para {user_id}: {e}")

def delete_session(user_id):
    """Elimina la sesión de un usuario de Firestore."""
    if not db: return
    try:
        db.collection('sessions').document(user_id).delete()
    except Exception as e:
        logger.error(f"Error eliminando sesión para {user_id}: {e}")

def find_product_by_keywords(text):
    """Busca un producto en Firestore que coincida con las palabras clave."""
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
# 5. FUNCIONES AUXILIARES DE LÓGICA DE VENTA
# ==============================================================================
def es_distrito_de_lima(texto_usuario):
    """Verifica si un texto contiene un distrito de Lima."""
    texto = texto_usuario.lower().strip()
    for distrito in TODOS_LOS_DISTRITOS_LIMA:
        if re.search(r'\b' + re.escape(distrito) + r'\b', texto):
            return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        if re.search(r'\b' + re.escape(abreviatura) + r'\b', texto):
            return nombre_completo.title()
    return None

def verificar_cobertura_delivery(distrito):
    """Verifica si un distrito tiene cobertura de delivery contra entrega."""
    return distrito.lower() in COBERTURA_DELIVERY_LIMA

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS INICIAL)
# ==============================================================================
def handle_initial_message(from_number, user_name, text):
    """Maneja el primer mensaje de un usuario (cuando no hay sesión activa)."""
    
    product_id, product_data = find_product_by_keywords(text)

    if product_data:
        # Se encontró un producto, iniciamos el embudo de ventas.
        nombre_producto = product_data.get('nombre', 'nuestro producto')
        descripcion_corta = product_data.get('descripcion_corta', 'es simplemente increíble.')
        precio = product_data.get('precio_base', 0)
        url_imagen_principal = product_data.get('imagenes', {}).get('principal')

        if url_imagen_principal:
            send_image_message(from_number, url_imagen_principal)

        mensaje_inicial = (
            f"¡Hola {user_name}! 🌞 El *{nombre_producto}* {descripcion_corta}\n\n"
            f"Por nuestra campaña del 21 de Septiembre, llévatelo a un precio especial de *S/ {precio:.2f}* "
            "(¡incluye envío gratis a todo el Perú! 🚚).\n\n"
            "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?"
        )
        send_text_message(from_number, mensaje_inicial)

        new_session = {
            "state": "awaiting_occasion_response",
            "product_id": product_id,
            "product_name": nombre_producto,
            "product_price": precio,
            "user_name": user_name
        }
        save_session(from_number, new_session)

    else:
        send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")

# ==============================================================================
# 7. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA GUIADO)
# ==============================================================================
def handle_sales_flow(from_number, text, session):
    """Maneja la conversación de un usuario con una sesión activa."""
    
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
        send_text_message(from_number, "Tuvimos un problema al encontrar los detalles de tu producto. Por favor, intenta de nuevo.")
        delete_session(from_number)
        return

    # --- INICIO DEL FLUJO DE VENTA ---
    if current_state == 'awaiting_occasion_response':
        url_imagen_empaque = product_data.get('imagenes', {}).get('empaque')
        detalles = product_data.get('detalles', {})
        material = detalles.get('material', 'material de alta calidad')
        magia = "Su piedra central es termocromática, cambia de color con tu temperatura."
        presentacion = detalles.get('empaque', 'viene en una hermosa caja de regalo')

        if url_imagen_empaque:
            send_image_message(from_number, url_imagen_empaque)

        mensaje_persuasion = (
            "¡Maravillosa elección! ✨ El *Collar Mágico Girasol Radiant* es pura energía. Aquí tienes todos los detalles:\n\n"
            f"💎 *Material:* {material} ¡Hipoalergénico y no se oscurece!\n"
            f"🔮 *La Magia:* {magia}\n"
            f"🎁 *Presentación:* {presentacion}, ¡lista para sorprender!\n\n"
            f"Para tu total seguridad, somos Daaqui Joyas, un negocio formal con *RUC {RUC_EMPRESA}*. ¡Tu compra es 100% segura! 🇵🇪\n\n"
            "¿Te gustaría coordinar tu pedido ahora para asegurar el tuyo?"
        )
        send_text_message(from_number, mensaje_persuasion)
        
        save_session(from_number, {"state": "awaiting_purchase_decision"})

    elif current_state == 'awaiting_purchase_decision':
        if 'si' in text.lower() or 'sí' in text.lower() or 'continuamos' in text.lower():
            # Aquí va la lógica del UPSELL
            # Por ahora, la información del upsell está en el código. En el futuro, puede venir de Firestore.
            upsell_message = (
                "¡Excelente elección! Pero espera, antes de continuar... por haber decidido llevar tu collar, ¡acabas de desbloquear una oferta exclusiva! ✨\n\n"
                "Llévate un *segundo Collar Mágico* por solo *S/ 20 adicionales* y te incluimos de regalo *dos cadenas de diseño italiano* para que combines tus dijes como quieras.\n\n"
                "En resumen, tendrías:\n"
                "✅ 2 Collares Mágicos\n"
                "✅ 2 Cadenas de Regalo\n"
                "✅ Todo por solo *S/ 89.00*\n\n"
                "Para continuar, por favor, respóndeme con una de estas dos palabras:\n"
                "👉🏽 Escribe *\"oferta\"* para ampliar tu pedido.\n"
                "👉🏽 Escribe *\"continuar\"* para llevar solo un collar."
            )
            send_text_message(from_number, upsell_message)
            save_session(from_number, {"state": "awaiting_upsell_decision"})
        else:
            delete_session(from_number)
            send_text_message(from_number, "Entendido. Si cambias de opinión o necesitas algo más, aquí estaré para ayudarte. ¡Que tengas un buen día! 😊")

    elif current_state == 'awaiting_upsell_decision':
        if 'oferta' in text.lower():
            session['product_name'] = "Oferta 2x Collares Mágicos + Cadenas"
            session['product_price'] = 89.00
            send_text_message(from_number, "¡Genial! Has elegido la oferta. ✨")
        else: # Asumimos 'continuar' o cualquier otra respuesta positiva
            send_text_message(from_number, "¡Perfecto! Continuamos con tu collar individual. ✨")
        
        session['state'] = 'awaiting_location'
        save_session(from_number, session)
        send_text_message(from_number, "Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?")

    elif current_state == 'awaiting_location':
        if 'provincia' in text.lower():
             # Flujo de Provincia
            session['state'] = 'awaiting_shalom_agreement'
            session['tipo_envio'] = 'Shalom'
            session['distrito'] = 'Provincia' # Placeholder
            save_session(from_number, session)
            mensaje = ("¡Perfecto! Para envíos a provincia, usamos la agencia *Shalom* para que tu joya llegue de forma segura. ✨\n\n"
                       "Para separar tu producto y gestionar el envío, requerimos un adelanto de *S/ 20.00*. Este monto funciona como un *compromiso para el recojo del pedido* en la agencia.\n\n"
                       "¿Estás de acuerdo para continuar? (Sí/No)")
            send_text_message(from_number, mensaje)

        elif 'lima' in text.lower():
            session['state'] = 'awaiting_lima_district'
            save_session(from_number, session)
            send_text_message(from_number, "¡Genial! ✨ Para empezar a coordinar la entrega de tu joya, por favor, dime: ¿en qué *distrito* te encuentras? 📍")
        
        else:
            send_text_message(from_number, "¿Eres de *Lima* o de *provincia*? Por favor, responde con una de esas dos opciones.")

    # (Aquí continuaría toda la lógica de los 3 flujos de venta que ya habíamos construido antes...)
    # Por brevedad en esta actualización, se omiten los estados:
    # awaiting_lima_district, awaiting_delivery_details, awaiting_shalom_agreement, etc.
    # Se implementarán en el siguiente paso.

    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar tu pedido, escribe 'cancelar' y vuelve a empezar.")

# ==============================================================================
# 8. WEBHOOK PRINCIPAL Y PROCESADOR DE MENSAJES
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge
        else:
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
    """Procesa un mensaje entrante de WhatsApp."""
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

