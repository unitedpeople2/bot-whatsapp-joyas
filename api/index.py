# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime
import re # NUEVO: Importamos el módulo de expresiones regulares para validaciones

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
# 2. ÁREA DE CONFIGURACIÓN DEL NEGOCIO (Aquí es donde modifico todo en el futuro)
# ==============================================================================

INFO_NEGOCIO = {
    # MODIFICADO: Ahora 'productos' puede tener múltiples entradas fácilmente.
    "productos": {
        "producto_1": {
            "nombre_completo": "Collar Mágico Sol Radiant",
            "precio": "S/ 69.00",
            "material": "Acero inoxidable quirúrgico de alta calidad",
            "propiedades": "Piedra termocrómica que cambia de color con la temperatura.",
            "palabras_clave": ["1", "sol radiant", "collar mágico", "collar que cambia color"]
        },
        # NUEVO: Añadimos un segundo producto para demostrar la escalabilidad.
        "producto_2": {
            "nombre_completo": "Aretes Constelación Lunar",
            "precio": "S/ 59.00",
            "material": "Acero inoxidable con incrustaciones de zircón.",
            "propiedades": "Brillan sutilmente en la oscuridad después de exponerse a la luz.",
            "palabras_clave": ["2", "aretes", "lunar", "constelación", "brillan"]
        }
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
    texto_normalizado = texto.replace('.', '').replace(',', '') # Limpiamos un poco el texto
    
    for distrito in COBERTURA_DELIVERY_LIMA:
        if distrito in texto_normalizado:
            return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        # Usamos word boundaries (\b) para evitar coincidencias parciales (ej: 'ves' en 'a veces')
        if re.search(r'\b' + re.escape(abreviatura) + r'\b', texto_normalizado):
            return nombre_completo.title()
    return None

# NUEVO: Función para buscar qué producto mencionó el usuario
def buscar_producto(texto_usuario):
    """Busca y devuelve el producto que coincide con el texto del usuario."""
    texto = texto_usuario.lower()
    for key, producto_info in INFO_NEGOCIO["productos"].items():
        for palabra in producto_info["palabras_clave"]:
            if palabra in texto:
                return producto_info # Devuelve el diccionario completo del producto
    return None

def generate_response(text, name, from_number):
    """Genera respuestas para consultas simples o inicia el flujo de ventas."""
    text = text.lower()
    
    # MODIFICADO: Flujo de compra mejorado
    if any(palabra in text for palabra in ['comprar', 'pedido', 'coordinar', 'quiero uno']):
        user_sessions[from_number] = {'state': 'awaiting_product_selection'}
        
        # Genera la lista de productos dinámicamente
        productos_disponibles = [f"{idx+1}️⃣ {prod['nombre_completo']}" for idx, prod in enumerate(INFO_NEGOCIO['productos'].values())]
        texto_productos = "\n".join(productos_disponibles)
        
        return (f"¡Excelente decisión, {name}! ✨\n\n"
                f"Estos son los productos que tenemos disponibles:\n{texto_productos}\n\n"
                "¿Cuál de ellos te gustaría llevar? Por favor, indícame el número o nombre.")

    distrito_encontrado = verificar_cobertura(text)
    if distrito_encontrado:
        return f"¡Buenas noticias, {name}! Sí tenemos cobertura de delivery contra entrega en {distrito_encontrado}. 🎉 Puedes iniciar tu pedido escribiendo 'comprar'."

    # MODIFICADO: Búsqueda dinámica de productos
    producto_encontrado = buscar_producto(text)
    if producto_encontrado:
        return (f"¡Te refieres a nuestro increíble {producto_encontrado['nombre_completo']}! ☀️\n\n"
                f"Es una joya única con estas características: {producto_encontrado['propiedades']}.\n"
                f"Material: {producto_encontrado['material']}.\n"
                f"Precio: {producto_encontrado['precio']}.\n\n"
                f"Para ordenarlo, solo escribe 'comprar'.")

    # Respuestas generales (sin cambios mayores)
    if any(palabra in text for palabra in ['envío', 'delivery', 'entrega', 'shalom']):
        return ("Manejamos delivery contra entrega para la mayoría de distritos de Lima y envíos por Shalom para provincias. Para saber tu caso, dime tu distrito o escribe 'comprar' para iniciar.")
    if any(palabra in text for palabra in ['pago', 'pagar', 'yape', 'plin', 'métodos']):
        return (f"Aceptamos Yape, Plin, efectivo y transferencia. Los detalles te los damos al coordinar tu pedido. Escribe 'comprar' para empezar.")
    if 'garantia' in text: return INFO_NEGOCIO['datos_generales']['garantia']
    if 'material' in text: return INFO_NEGOCIO['datos_generales']['material_joyas']
    if any(palabra in text for palabra in ['medida', 'tamaño', 'largo', 'cadena']): return INFO_NEGOCIO['datos_generales']['medida_cadena']
    if any(palabra in text for palabra in ['empaque', 'caja', 'regalo']): return INFO_NEGOCIO['datos_generales']['empaque']
    if any(palabra in text for palabra in ['tienda', 'física', 'local', 'ubicacion']): return INFO_NEGOCIO['datos_generales']['tienda_fisica']

    # MODIFICADO: Saludo inicial dinámico
    saludos_comunes = ['hola', 'hila', 'ola', 'buenos', 'buenas', 'bnas', 'qué tal', 'q tal', 'info']
    if any(saludo in text for saludo in saludos_comunes):
        productos_disponibles = [f"{idx+1}️⃣ {INFO_NEGOCIO['productos'][key]['nombre_completo']}" for idx, key in enumerate(INFO_NEGOCIO['productos'])]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Hola {name}! 👋✨ Soy tu asesora virtual de Daaqui Joyas. ¡Bienvenid@!\n\n"
                f"Actualmente tenemos en stock estas joyas mágicas con envío gratis:\n\n{texto_productos}\n\n"
                f"Escribe el número o el nombre del producto que te gustaría conocer. También puedes preguntar por 'envío' o 'pagos'.")

    else:
        return f"¡Hola {name}! 👋 No entendí muy bien tu consulta. Puedes preguntar sobre:\n\n- Nuestros productos (ej: 'collar sol radiant')\n- Métodos de envío\n- Cobertura de delivery"


# MODIFICADO: Flujo de ventas reestructurado para ser más lógico
def handle_sales_flow(user_id, user_name, user_message):
    """Maneja la conversación del flujo de ventas paso a paso."""
    session = user_sessions.get(user_id, {})
    current_state = session.get('state')

    if current_state == 'awaiting_product_selection':
        producto_seleccionado = buscar_producto(user_message)
        if producto_seleccionado:
            session.update({'state': 'awaiting_district', 'producto': producto_seleccionado['nombre_completo']})
            return f"¡Confirmado: {producto_seleccionado['nombre_completo']}! Ahora, por favor, indícame tu distrito para coordinar el envío."
        else:
            return "No pude identificar el producto. Por favor, intenta con el número o nombre exacto que te mostré."

    elif current_state == 'awaiting_district':
        distrito = verificar_cobertura(user_message)
        if distrito:
            session.update({'state': 'delivery_confirmation', 'distrito': distrito})
            return (f"¡Perfecto, delivery para {distrito}! 🎉 El pago es contra entrega.\n\n"
                    "Para confirmar, por favor, envíame en un solo mensaje:\n"
                    "- Tu nombre completo\n"
                    "- Tu DNI\n"
                    "- Tu número de celular de contacto")
        else:
            session.update({'state': 'shalom_confirmation', 'distrito': user_message.title()})
            return (f"Entendido. Para {user_message.title()} el envío es por Shalom. Se requiere un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}.\n\n"
                    "Si estás de acuerdo, envíame en un solo mensaje:\n"
                    "- Tu nombre completo\n"
                    "- Tu DNI\n"
                    "- Tu número de celular de contacto")

    elif current_state in ['delivery_confirmation', 'shalom_confirmation']:
        logger.info(f"NUEVA VENTA ({current_state}): Producto: {session.get('producto', 'No especificado')}, Cliente: {user_message}, Distrito: {session.get('distrito', 'No especificado')}")
        del user_sessions[user_id] # Limpiamos la sesión al finalizar
        return "¡Excelente! Hemos registrado tu pedido. Un asesor se pondrá en contacto contigo en breve para coordinar los últimos detalles. ¡Gracias por tu compra en Daaqui Joyas! 💖"
    
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
        if message_type != 'text': return

        contact_name = next((contact.get('profile', {}).get('name', 'Usuario') for contact in contacts if contact.get('wa_id') == from_number), 'Usuario')
        text_body = message.get('text', {}).get('body', '')
        
        logger.info(f"Procesando de {contact_name} ({from_number}): '{text_body}'")
        
        # MODIFICADO: La lógica de decisión es más limpia
        response_text = None
        if from_number in user_sessions:
            response_text = handle_sales_flow(from_number, contact_name, text_body)
        
        if response_text is None: # Si no hubo respuesta del flujo de ventas, o no estaba en uno.
            response_text = generate_response(text_body, contact_name, from_number)
        
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