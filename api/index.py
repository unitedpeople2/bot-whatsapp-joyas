# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de variables de entorno de WhatsApp
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

# Diccionario para guardar el estado de la conversación de cada usuario (la "memoria" del bot)
user_sessions = {}


# ==============================================================================
# 2. ÁREA DE CONFIGURACIÓN DEL NEGOCIO (Aquí es donde modificas TODO en el futuro)
# ==============================================================================

INFO_NEGOCIO = {
    "productos": {
        "producto_1": {
            "nombre_completo": "Collar Mágico Sol Radiant",
            "precio": "S/ 69.00",
            "material": "Acero inoxidable quirúrgico de alta calidad",
            "propiedades": "Piedra termocrómica que cambia de color con la temperatura.",
            "palabras_clave": [
                "1",
                "sol radiant", 
                "collar mágico", 
                "collar que cambia color",
                "precio y es ideal para regalo"
            ]
        }
        # Para agregar más productos, copia el bloque "producto_1", pégalo aquí
        # y cámbialo a "producto_2" con sus nuevos datos.
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
# 3. FUNCIONES DE LÓGICA DEL BOT (El "cerebro" del bot)
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

def generate_response(text, name, from_number):
    """Genera respuestas para consultas simples o inicia el flujo de ventas."""
    text = text.lower()
    
    # --- ACTIVADOR DEL FLUJO DE VENTAS ---
    if any(palabra in text for palabra in ['comprar', 'pedido', 'coordinar', 'quiero uno']):
        user_sessions[from_number] = {'state': 'awaiting_district'}
        return "¡Perfecto! ✨ Para empezar a coordinar tu pedido, por favor, indícame tu distrito."

    # --- Verificación de Cobertura (Consulta simple) ---
    distrito_encontrado = verificar_cobertura(text)
    if distrito_encontrado:
        return f"¡Buenas noticias, {name}! Sí tenemos cobertura de delivery contra entrega en {distrito_encontrado}. 🎉 Puedes iniciar tu pedido escribiendo 'comprar'."

    # --- Consultas de Productos ---
    producto_1 = INFO_NEGOCIO['productos']['producto_1']
    if any(palabra in text for palabra in producto_1['palabras_clave']):
        return (f"¡Te refieres a nuestro increíble {producto_1['nombre_completo']}! ☀️\n\n"
                f"Es una joya única con una {producto_1['propiedades']}.\n"
                f"Material: {producto_1['material']}.\n"
                f"Precio: {producto_1['precio']}.\n\n"
                f"Para ordenarlo, solo escribe 'comprar'.")

    # --- Consultas Generales ---
    if any(palabra in text for palabra in ['envío', 'delivery', 'entrega', 'shalom']):
        return ("Manejamos delivery contra entrega para la mayoría de distritos de Lima y envíos por Shalom para provincias. Para saber tu caso, dime tu distrito o escribe 'comprar' para iniciar.")
    if any(palabra in text for palabra in ['pago', 'pagar', 'yape', 'plin', 'métodos']):
        return (f"Aceptamos Yape, Plin, efectivo y transferencia. Los detalles te los damos al coordinar tu pedido. Escribe 'comprar' para empezar.")
    if 'garantia' in text: return INFO_NEGOCIO['datos_generales']['garantia']
    if 'material' in text: return INFO_NEGOCIO['datos_generales']['material_joyas']
    if any(palabra in text for palabra in ['medida', 'tamaño', 'largo', 'cadena']): return INFO_NEGOCIO['datos_generales']['medida_cadena']
    if any(palabra in text for palabra in ['empaque', 'caja', 'regalo']): return INFO_NEGOCIO['datos_generales']['empaque']
    if any(palabra in text for palabra in ['tienda', 'física', 'local', 'ubicacion']): return INFO_NEGOCIO['datos_generales']['tienda_fisica']

    # --- Saludos y Bienvenida ---
    saludos_comunes = ['hola', 'hila', 'ola', 'buenos', 'buenas', 'bnas', 'qué tal', 'q tal', 'info']
    if any(saludo in text for saludo in saludos_comunes):
        productos_disponibles = [f"1️⃣ {INFO_NEGOCIO['productos']['producto_1']['nombre_completo']}"]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Hola {name}! 👋✨ Soy tu asesora virtual de Daaqui Joyas. ¡Bienvenid@!\n\n"
                f"Actualmente tenemos en stock estas joyas mágicas con envío gratis:\n\n{texto_productos}\n\n"
                f"Escribe el número o el nombre del collar que te gustaría conocer. También puedes preguntar por 'envío' o 'pagos'.")

    # --- Respuesta por Defecto ---
    else:
        return f"¡Hola {name}! 👋 No entendí muy bien tu consulta. Puedes preguntar sobre:\n\n- El 'collar sol radiant'\n- Métodos de envío\n- Cobertura de delivery"


def handle_sales_flow(user_id, user_name, user_message):
    """Maneja la conversación del flujo de ventas paso a paso."""
    current_state = user_sessions.get(user_id, {}).get('state')

    if current_state == 'awaiting_district':
        distrito = verificar_cobertura(user_message)
        if distrito:
            user_sessions[user_id].update({'state': 'delivery_confirmation', 'distrito': distrito})
            return f"¡Perfecto, delivery para {distrito}! 🎉 El pago es contra entrega. Para confirmar, por favor, envíame tu nombre completo, DNI y número de celular."
        else:
            user_sessions[user_id].update({'state': 'shalom_confirmation', 'distrito': user_message.title()})
            return f"Entendido. Para {user_message.title()} el envío es por Shalom. Se requiere un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}. Si estás de acuerdo, envíame tu nombre completo, DNI y celular."

    elif current_state == 'delivery_confirmation' or current_state == 'shalom_confirmation':
        # --- AQUÍ IRÍA LA LÓGICA PARA GUARDAR EN GOOGLE SHEETS ---
        logger.info(f"NUEVA VENTA ({current_state}): Cliente {user_message}, Distrito: {user_sessions[user_id]['distrito']}")
        del user_sessions[user_id]
        return "¡Excelente! Hemos registrado tu pedido. Un asesor se pondrá en contacto contigo en breve para coordinar los últimos detalles. ¡Gracias por tu compra en Daaqui Joyas!"
    
    return None

# ==============================================================================
# 4. FUNCIONES INTERNAS DEL BOT (Normalmente no se tocan)
# ==============================================================================

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode, token, challenge = request.args.get('hub.mode'), request.args.get('hub.verify_token'), request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("Webhook verificado exitosamente")
            return challenge
        else:
            logger.warning(f"Verificación fallida")
            return 'Forbidden', 403
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        value = change.get('value', {})
                        if change.get('field') == 'messages' and value.get('messages'):
                            for message in value.get('messages'):
                                process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    """Decide si es una consulta simple o parte de un flujo y la procesa."""
    try:
        from_number = message.get('from')
        message_type = message.get('type')
        if message_type != 'text': return # Solo procesamos mensajes de texto

        contact_name = next((contact.get('profile', {}).get('name', 'Usuario') for contact in contacts if contact.get('wa_id') == from_number), 'Usuario')
        text_body = message.get('text', {}).get('body', '')
        
        logger.info(f"Procesando de {contact_name} ({from_number}): '{text_body}'")
        
        response_text = handle_sales_flow(from_number, contact_name, text_body) if from_number in user_sessions else generate_response(text_body, contact_name, from_number)
        
        if response_text:
            send_whatsapp_message(from_number, {"type": "text", "text": {"body": response_text}})
    except Exception as e:
        logger.error(f"Error en process_message: {e}")

def send_whatsapp_message(to_number, message_data):
    """Envía un mensaje de WhatsApp."""
    if not WHATSAPP_TOKEN or not WHATSAPP_API_URL:
        logger.error("Token de WhatsApp o URL de API no configurados.")
        return
    
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}', 'Content-Type': 'application/json'}
    data = {"messaging_product": "whatsapp", "to": to_number, **message_data}
    
    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Mensaje enviado a {to_number}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje: {e.response.text if e.response else e}")

@app.route('/')
def home():
    return jsonify({'status': 'Bot Daaqui Activo'})

if __name__ == '__main__':
    app.run(debug=True)