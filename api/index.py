from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de variables de entorno
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

# ==============================================================================
# ====> ÁREA DE CONFIGURACIÓN DEL NEGOCIO (Aquí es donde modificas todo) <====
# ==============================================================================

INFO_NEGOCIO = {
    "productos": {
        "producto_1": {
            "nombre_completo": "Collar Mágico Sol Radiant",
            "precio": "S/ 69.00",
            "material": "Acero inoxidable quirúrgico de alta calidad",
            "propiedades": "Piedra termocrómica que cambia de color con la temperatura.",
            "palabras_clave": [
                "1",  # Para responder al menú
                "sol radiant", 
                "collar mágico", 
                "collar que cambia color",
                "precio y es ideal para regalo" # Para el mensaje de la publicidad
            ]
        }
        # Para agregar más productos, solo copia y pega el bloque de "producto_1"
        # y cámbialo a "producto_2", "producto_3", etc.
    },
    "politicas_envio": {
        "delivery_lima": {
            "modalidad": "Pago Contra Entrega a domicilio",
            "costo": "Gratis",
            "adelanto_requerido": "No requiere adelanto",
            "tiempo_entrega": "1 a 2 días hábiles"
        },
        "envio_shalom": {
            "modalidad": "Recojo en agencia Shalom",
            "costo": "Gratis",
            "adelanto_requerido": "S/ 20.00",
            "tiempo_entrega_lima_sin_cobertura": "2 a 3 días hábiles",
            "tiempo_entrega_provincias": "3 a 7 días hábiles",
            "info_adicional": "Todos los envíos a provincias y zonas de Lima sin cobertura son únicamente por Shalom."
        }
    },
    "datos_generales": {
        "tienda_fisica": "No contamos con tienda física. Somos una tienda 100% online para ofrecerte los mejores precios.",
        "garantia": "Ofrecemos una garantía de 15 días por cualquier defecto de fábrica.",
        "material_joyas": "Todas nuestras joyas son de acero inoxidable quirúrgico de alta calidad, son hipoalergénicas y resistentes.",
        "medida_cadena": "El largo estándar de nuestras cadenas es de 45 cm.",
        "empaque": "¡Sí! Todas tus compras incluyen una hermosa cajita de regalo 🎁.",
        "metodos_pago": {
            "contra_entrega": "Para delivery en Lima puedes pagar con Efectivo, Yape o Plin al momento de recibir tu pedido.",
            "adelanto_shalom": "El adelanto para envíos por Shalom puedes realizarlo por Yape, Plin o Transferencia bancaria."
        }
    }
}

COBERTURA_DELIVERY_LIMA = [
    "ate", "barranco", "bellavista", "breña", "callao", "carabayllo", 
    "carmen de la legua", "cercado de lima", "chorrillos", "comas", "el agustino", 
    "independencia", "jesus maria", "la molina", "la perla", "la punta", 
    "la victoria", "lince", "los olivos", "magdalena", "miraflores", 
    "pueblo libre", "puente piedra", "rimac", "san borja", "san isidro", 
    "san juan de lurigancho", "san juan de miraflores", "san luis", 
    "san martin de porres", "san miguel", "santa anita", "surco", 
    "surquillo", "villa el salvador", "villa maria del triunfo"
]

ABREVIATURAS_DISTRITOS = {
    "sjl": "san juan de lurigancho",
    "sjm": "san juan de miraflores",
    "smp": "san martin de porres",
    "vmt": "villa maria del triunfo",
    "ves": "villa el salvador",
    "lima centro": "cercado de lima"
}
# ==============================================================================
# ====> FIN DEL ÁREA DE CONFIGURACIÓN <==== (Normalmente no necesitas tocar nada debajo de esta línea)
# ==============================================================================


def verificar_cobertura(texto_usuario):
    """Verifica si el texto menciona un distrito con cobertura."""
    texto = texto_usuario.lower().strip()
    for distrito in COBERTURA_DELIVERY_LIMA:
        if distrito in texto:
            return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        if f" {abreviatura} " in f" {texto} " or texto == abreviatura:
            return nombre_completo.title()
    return None

# ==============================================================================
# ====> LÓGICA DE RESPUESTAS DEL BOT (El "cerebro" que decide qué responder) <====
# ==============================================================================

def generate_response(text, name):
    """Genera respuestas automáticas utilizando la base de datos del negocio."""
    text = text.lower()
    
    # --- Verificación de Cobertura ---
    distrito_encontrado = verificar_cobertura(text)
    if distrito_encontrado:
        politica_delivery = INFO_NEGOCIO['politicas_envio']['delivery_lima']
        return (f"¡Buenas noticias, {name}! Sí tenemos cobertura de delivery contra entrega en {distrito_encontrado}. 🎉\n\n"
                f"Modalidad: {politica_delivery['modalidad']}\n"
                f"Costo: {politica_delivery['costo']}\n"
                f"Tiempo: {politica_delivery['tiempo_entrega']}\n\n"
                f"¿Te gustaría coordinar tu pedido?")

    # --- Consultas de Productos ---
    producto_1 = INFO_NEGOCIO['productos']['producto_1']
    if any(palabra in text for palabra in producto_1['palabras_clave']):
        return (f"¡Te refieres a nuestro increíble {producto_1['nombre_completo']}! ☀️\n\n"
                f"Es una joya única con una {producto_1['propiedades']}.\n"
                f"Material: {producto_1['material']}.\n"
                f"Precio: {producto_1['precio']}.\n\n"
                f"¡Es perfecto para regalo! ¿Lo quieres para ti o para alguien especial?")

    # --- Consultas de Políticas y Datos Generales ---
    if any(palabra in text for palabra in ['envío', 'delivery', 'entrega', 'shalom', 'cobertura']):
        delivery = INFO_NEGOCIO['politicas_envio']['delivery_lima']
        shalom = INFO_NEGOCIO['politicas_envio']['envio_shalom']
        return (f"¡Claro, {name}! Manejamos dos tipos de envío:\n\n"
                f"1️⃣ *Delivery para Lima (con cobertura):*\n"
                f"- Modalidad: {delivery['modalidad']}\n"
                f"- Costo: {delivery['costo']}\n"
                f"- Tiempo: {delivery['tiempo_entrega']}\n\n"
                f"2️⃣ *Envío Nacional y Lima (sin cobertura):*\n"
                f"- Empresa: Shalom (recojo en agencia)\n"
                f"- Costo: {shalom['costo']}\n"
                f"- Adelanto: {shalom['adelanto_requerido']}\n"
                f"- Tiempo: {shalom['tiempo_entrega_provincias']}\n\n"
                f"Dime tu distrito para confirmarte tu tipo de envío.")

    if any(palabra in text for palabra in ['pago', 'pagar', 'yape', 'plin', 'métodos']):
        pagos = INFO_NEGOCIO['datos_generales']['metodos_pago']
        return (f"¡Claro! Estos son nuestros métodos de pago:\n\n"
                f"💳 *Para Delivery en Lima:*\n{pagos['contra_entrega']}\n\n"
                f"💸 *Para envíos por Shalom:*\n{pagos['adelanto_shalom']}")

    if 'garantia' in text:
        return INFO_NEGOCIO['datos_generales']['garantia']

    if 'material' in text:
        return INFO_NEGOCIO['datos_generales']['material_joyas']
        
    if any(palabra in text for palabra in ['medida', 'tamaño', 'largo', 'cadena']):
        return INFO_NEGOCIO['datos_generales']['medida_cadena']

    if any(palabra in text for palabra in ['empaque', 'caja', 'regalo']):
        return INFO_NEGOCIO['datos_generales']['empaque']
        
    if any(palabra in text for palabra in ['tienda', 'física', 'local', 'ubicacion']):
        return INFO_NEGOCIO['datos_generales']['tienda_fisica']

    # --- Saludos y Respuestas Genéricas (CON SOLUCIÓN PARA ERRORES DE TIPEO) ---
    saludos_comunes = ['hola', 'hila', 'ola', 'buenos', 'buenas', 'bnas', 'qué tal', 'q tal', 'info']
    if any(saludo in text for saludo in saludos_comunes):
        productos_disponibles = []
        if 'producto_1' in INFO_NEGOCIO['productos']:
            productos_disponibles.append("1️⃣ Collar Sol Radiant (Brilla con tu energía)")
        
        texto_productos = "\n".join(productos_disponibles)
        
        return (f"¡Hola {name}! 👋✨ Soy tu asesora virtual de Daaqui Joyas. ¡Bienvenid@!\n\n"
                f"Actualmente tenemos en stock estas joyas mágicas con envío gratis:\n\n"
                f"{texto_productos}\n\n"
                f"Escribe el número o el nombre del collar que te gustaría conocer. También puedes preguntar por 'envío' o 'pagos'.")
        
    if any(palabra in text for palabra in ['gracias', 'grs', 'perfecto', 'genial', 'ok']):
        return f"¡De nada, {name}! 😊✨ Si tienes alguna otra consulta, no dudes en preguntar."
    
    if any(palabra in text for palabra in ['adiós', 'bye', 'hasta luego', 'chao']):
        return f"¡Hasta pronto, {name}! 👋✨ Fue un placer atenderte. Te esperamos en Daaqui Joyas."


    # --- Respuesta por Defecto ---
    else:
        return f"¡Hola {name}! 👋 Gracias por tu mensaje. No entendí muy bien tu consulta. ¿Podrías reformularla? Puedes preguntar sobre:\n\n- El 'collar sol radiant'\n- Métodos de envío\n- Cobertura de delivery\n- Métodos de pago"

# ==============================================================================
# ====> LÓGICA INTERNA DEL BOT (Normalmente no necesitas tocar esto) <====
# ==============================================================================

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("Webhook verificado exitosamente")
            return challenge
        else:
            logger.warning(f"Verificación fallida - Token esperado: {VERIFY_TOKEN}, Token recibido: {token}")
            return 'Forbidden', 403
    elif request.method == 'POST':
        try:
            data = request.get_json()
            logger.info(f"Datos recibidos: {data}")
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        if change.get('field') == 'messages':
                            value = change.get('value', {})
                            for message in value.get('messages', []):
                                process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    """Procesa un mensaje entrante y envía una respuesta."""
    try:
        from_number = message.get('from')
        message_type = message.get('type')
        contact_name = "Usuario"
        for contact in contacts:
            if contact.get('wa_id') == from_number:
                contact_name = contact.get('profile', {}).get('name', 'Usuario')
                break
        
        logger.info(f"Procesando mensaje de {contact_name} ({from_number})")
        
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '').lower()
            logger.info(f"Mensaje de texto: {text_body}")
            
            response_text = generate_response(text_body, contact_name)
            
            if response_text:
                ### CAMBIO 1: Ahora convertimos el texto a un payload ###
                text_payload = {"type": "text", "text": {"body": response_text}}
                send_whatsapp_message(from_number, text_payload)
        
        elif message_type in ['image', 'document', 'audio', 'video']:
            logger.info(f"Mensaje multimedia recibido: {message_type}")
            multimedia_response_payload = {"type": "text", "text": {"body": f"¡Hola {contact_name}! He recibido tu {message_type}. ¿En qué puedo ayudarte con nuestras joyas? 💎✨"}}
            send_whatsapp_message(from_number, multimedia_response_payload)
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")

def send_whatsapp_message(to_number, message_data):
    """Envía un mensaje de WhatsApp usando un payload de datos."""
    if not WHATSAPP_TOKEN or not WHATSAPP_API_URL:
        logger.error("Token de WhatsApp o URL de API no configurados.")
        return False
    
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
    
    ### CAMBIO 2: La función ahora es más flexible ###
    data = {"messaging_product": "whatsapp", "to": to_number}
    data.update(message_data)
    
    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            logger.info(f"Mensaje enviado exitosamente a {to_number}")
            return True
        else:
            logger.error(f"Error enviando mensaje: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Excepción enviando mensaje: {e}")
        return False

# Endpoints adicionales (normalmente no se tocan)
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/api', methods=['GET'])
@app.route('/', methods=['GET'])
def home():
    return jsonify({'message': 'Bot de WhatsApp para Joyería Daaqui', 'status': 'active'})

if __name__ == '__main__':
    app.run(debug=True)