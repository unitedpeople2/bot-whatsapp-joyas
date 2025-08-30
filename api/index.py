# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime
import re
import json
import gspread  # <-- MODIFICADO: import añadido aquí

# MODIFICADO: Configuración del logger centralizada
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de variables de entorno de WhatsApp
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

# Diccionario para guardar el estado de la conversación de cada usuario
user_sessions = {}


# ==============================================================================
# 2. ÁREA DE CONFIGURACIÓN DEL NEGOCIO
# ==============================================================================

# ... (Toda tu configuración de INFO_NEGOCIO, COBERTURA_DELIVERY_LIMA, etc., se mantiene exactamente igual) ...
INFO_NEGOCIO = {
    "productos": {
        "producto_1": {
            "nombre_completo": "Collar Mágico Sol Radiant",
            "precio": "S/ 69.00",
            "material": "Acero inoxidable quirúrgico de alta calidad",
            "propiedades": "Piedra termocrómica que cambia de color con la temperatura.",
            "palabras_clave": ["1", "sol radiant", "collar mágico", "collar que cambia color"]
        },
        "producto_2": {
            "nombre_completo": "Aretes Constelación Lunar",
            "precio": "S/ 59.00",
            "material": "Acero inoxidable con incrustaciones de zircón.",
            "propiedades": "Brillan sutilmente en la oscuridad después de exponerse a la luz.",
            "palabras_clave": ["2", "aretes", "lunar", "constelación", "brillan"]
        }
    },
    "politicas_envio": {
        "delivery_lima": { "modalidad": "Pago Contra Entrega a domicilio", "costo": "Gratis", "adelanto_requerido": "No requiere adelanto", "tiempo_entrega": "1 a 2 días hábiles" },
        "envio_shalom": { "modalidad": "Recojo en agencia Shalom", "costo": "Gratis", "adelanto_requerido": "S/ 20.00", "tiempo_entrega_lima_sin_cobertura": "2 a 3 días hábiles", "tiempo_entrega_provincias": "3 a 7 días hábiles", "info_adicional": "Todos los envíos a provincias y zonas de Lima sin cobertura son únicamente por Shalom."}
    },
    "datos_generales": {
        "tienda_fisica": "No contamos con tienda física. Somos una tienda 100% online para ofrecerte los mejores precios.", "garantia": "Ofrecemos una garantía de 15 días por cualquier defecto de fábrica.", "material_joyas": "Todas nuestras joyas son de acero inoxidable quirúrgico de alta calidad, son hipoalergénicas y resistentes.", "medida_cadena": "El largo estándar de nuestras cadenas es de 45 cm.", "empaque": "¡Sí! Todas tus compras incluyen una hermosa cajita de regalo 🎁.", "metodos_pago": { "contra_entrega": "Para delivery en Lima puedes pagar con Efectivo, Yape o Plin al momento de recibir tu pedido.", "adelanto_shalom": "El adelanto para envíos por Shalom puedes realizarlo por Yape, Plin o Transferencia bancaria."}
    }
}
COBERTURA_DELIVERY_LIMA = [ "ate", "barranco", "bellavista", "breña", "callao", "carabayllo", "carmen de la legua", "cercado de lima", "chorrillos", "comas", "el agustino", "independencia", "jesus maria", "la molina", "la perla", "la punta", "la victoria", "lince", "los olivos", "magdalena", "miraflores", "pueblo libre", "puente piedra", "rimac", "san borja", "san isidro", "san juan de lurigancho", "san juan de miraflores", "san luis", "san martin de porres", "san miguel", "santa anita", "surco", "surquillo", "villa el salvador", "villa maria del triunfo" ]
ABREVIATURAS_DISTRITOS = { "sjl": "san juan de lurigancho", "sjm": "san juan de miraflores", "smp": "san martin de porres", "vmt": "villa maria del triunfo", "ves": "villa el salvador", "lima centro": "cercado de lima" }


# ==============================================================================
# 3. FUNCIONES DE LÓGICA DEL BOT (El "cerebro" del bot)
# ==============================================================================

# ================== NUEVO: FUNCIONES DE GOOGLE SHEETS INTEGRADAS ==================
def init_gspread():
    """Inicializa y devuelve un cliente autenticado de gspread."""
    try:
        logger.info("Iniciando conexión con Google Sheets...")
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if not creds_json_str:
            logger.error("Error Crítico: La variable GOOGLE_CREDENTIALS_JSON está vacía.")
            return None
        logger.info("Variable GOOGLE_CREDENTIALS_JSON leída.")
        creds_dict = json.loads(creds_json_str)
        client_email = creds_dict.get("client_email")
        if not client_email:
            logger.error("Error Crítico: JSON de credenciales no contiene 'client_email'.")
            return None
        logger.info(f"Autenticando con: {client_email}")
        gc = gspread.service_account_from_dict(creds_dict)
        logger.info("Cliente gspread autenticado.")
        return gc
    except json.JSONDecodeError:
        logger.error("Error Crítico: GOOGLE_CREDENTIALS_JSON no es un JSON válido.")
        return None
    except Exception as e:
        logger.error(f"Error inesperado en init_gspread: {e}")
        return None

def guardar_pedido_en_sheet(datos_pedido):
    """Guarda los datos de un pedido en una nueva fila de la hoja de cálculo."""
    gc = init_gspread()
    if not gc:
        logger.error("Abortando guardado en Sheets por fallo de inicialización.")
        return False
    try:
        spreadsheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not spreadsheet_name:
            logger.error("Error: Variable GOOGLE_SHEET_NAME no configurada.")
            return False
        logger.info(f"Abriendo hoja: '{spreadsheet_name}'")
        sh = gc.open(spreadsheet_name).sheet1
        logger.info("Hoja abierta. Añadiendo fila...")
        nueva_fila = [
            datos_pedido.get('fecha', ''), datos_pedido.get('nombre_completo', ''),
            datos_pedido.get('direccion', ''), datos_pedido.get('referencia', ''),
            datos_pedido.get('distrito', ''), datos_pedido.get('dni', ''),
            datos_pedido.get('forma_pago', ''), datos_pedido.get('celular', ''),
            datos_pedido.get('producto_seleccionado', ''), datos_pedido.get('total', '')
        ]
        sh.append_row(nueva_fila)
        logger.info(f"Pedido guardado exitosamente en '{spreadsheet_name}'")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"ERROR CRÍTICO: No se encontró la hoja '{spreadsheet_name}'.")
        logger.error("VERIFICA: 1. Nombre exacto. 2. Hoja compartida con el email de servicio.")
        return False
    except Exception as e:
        logger.error(f"Error inesperado en guardar_pedido_en_sheet: {e}")
        return False
# ==============================================================================

def verificar_cobertura(texto_usuario):
    # ... (esta función y las siguientes se mantienen exactamente igual) ...
    texto = texto_usuario.lower().strip().replace('.', '').replace(',', '')
    for distrito in COBERTURA_DELIVERY_LIMA:
        if distrito in texto:
            return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        if re.search(r'\b' + re.escape(abreviatura) + r'\b', texto):
            return nombre_completo.title()
    return None

def buscar_producto(texto_usuario, return_key=False):
    texto = texto_usuario.lower()
    for key, producto_info in INFO_NEGOCIO["productos"].items():
        for palabra in producto_info["palabras_clave"]:
            if palabra in texto:
                return (key, producto_info) if return_key else producto_info
    return (None, None) if return_key else None

def generate_response(text, name, from_number):
    text = text.lower()
    if any(palabra in text for palabra in ['comprar', 'pedido', 'coordinar', 'quiero uno']):
        user_sessions[from_number] = {'state': 'awaiting_product_selection'}
        productos_disponibles = [f"{idx+1}️⃣ {prod['nombre_completo']}" for idx, prod in enumerate(INFO_NEGOCIO['productos'].values())]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Excelente decisión, {name}! ✨\n\nEstos son los productos que tenemos disponibles:\n{texto_productos}\n\n"
                "¿Cuál de ellos te gustaría llevar? Por favor, indícame el número o nombre.")
    distrito_encontrado = verificar_cobertura(text)
    if distrito_encontrado:
        return f"¡Buenas noticias, {name}! Sí tenemos cobertura de delivery contra entrega en {distrito_encontrado}. 🎉 Puedes iniciar tu pedido escribiendo 'comprar'."
    producto_encontrado = buscar_producto(text)
    if producto_encontrado:
        return (f"¡Te refieres a nuestro increíble {producto_encontrado['nombre_completo']}! ☀️\n\n"
                f"Características: {producto_encontrado['propiedades']}.\n"
                f"Material: {producto_encontrado['material']}.\nPrecio: {producto_encontrado['precio']}.\n\n"
                f"Para ordenarlo, solo escribe 'comprar'.")
    saludos_comunes = ['hola', 'hila', 'ola', 'buenos', 'buenas', 'bnas', 'qué tal', 'q tal', 'info']
    if any(saludo in text for saludo in saludos_comunes):
        productos_disponibles = [f"{idx+1}️⃣ {INFO_NEGOCIO['productos'][key]['nombre_completo']}" for idx, key in enumerate(INFO_NEGOCIO['productos'])]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Hola {name}! 👋✨ Soy tu asesora virtual de Daaqui Joyas.\n\n"
                f"Tenemos en stock estas joyas mágicas con envío gratis:\n\n{texto_productos}\n\n"
                f"Escribe el número o el nombre del producto que te gustaría conocer.")
    return f"¡Hola {name}! 👋 No entendí tu consulta. Puedes preguntar sobre:\n\n- Nuestros productos (ej: 'collar sol radiant')\n- 'envío'\n- 'pagos'"

def handle_sales_flow(user_id, user_name, user_message):
    session = user_sessions.get(user_id, {})
    current_state = session.get('state')
    if current_state == 'awaiting_product_selection':
        producto_key, producto_info = buscar_producto(user_message, return_key=True)
        if producto_info:
            session.update({'state': 'awaiting_district', 'producto': producto_info['nombre_completo'], 'producto_key': producto_key})
            return f"¡Confirmado: {producto_info['nombre_completo']}! Ahora, por favor, indícame tu distrito para coordinar el envío."
        else:
            return "No pude identificar el producto. Por favor, intenta con el número o nombre exacto."
    elif current_state == 'awaiting_district':
        distrito = verificar_cobertura(user_message)
        if distrito:
            session.update({'state': 'delivery_confirmation', 'distrito': distrito})
            return (f"¡Perfecto, delivery para {distrito}! 🎉 El pago es contra entrega.\n\nPara confirmar, por favor, envíame en un solo mensaje:\n- Tu nombre completo\n- Tu DNI\n- Tu número de celular de contacto")
        else:
            session.update({'state': 'shalom_confirmation', 'distrito': user_message.title()})
            return (f"Entendido. Para {user_message.title()} el envío es por Shalom. Se requiere un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}.\n\nSi estás de acuerdo, envíame en un solo mensaje:\n- Tu nombre completo\n- Tu DNI\n- Tu número de celular de contacto")
    elif current_state in ['delivery_confirmation', 'shalom_confirmation']:
        producto_key = session.get('producto_key', 'producto_1')
        producto_info = INFO_NEGOCIO['productos'].get(producto_key, {})
        datos_del_pedido = {
            'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'nombre_completo': user_message.split('\n')[0].strip(),
            'dni': next((line.split(':')[1].strip() for line in user_message.split('\n') if 'dni' in line.lower()), 'No especificado'),
            'celular': user_id, 'distrito': session.get('distrito', ''), 'producto_seleccionado': session.get('producto', ''),
            'forma_pago': 'Contra Entrega' if current_state == 'delivery_confirmation' else 'Adelanto Shalom', 'total': producto_info.get('precio', 'N/A'),
            'direccion': '', 'referencia': ''
        }
        # MODIFICADO: Llamada a la nueva función integrada
        exito_al_guardar = guardar_pedido_en_sheet(datos_del_pedido)
        if exito_al_guardar:
            logger.info(f"NUEVA VENTA GUARDADA EN SHEETS: {datos_del_pedido}")
        else:
            logger.error(f"FALLO AL GUARDAR VENTA EN SHEETS para el pedido: {datos_del_pedido}")
        del user_sessions[user_id]
        return "¡Excelente! Hemos registrado tu pedido. Un asesor se pondrá en contacto contigo en breve para coordinar los últimos detalles. ¡Gracias por tu compra en Daaqui Joyas! 💖"
    return None


# ==============================================================================
# 4. FUNCIONES INTERNAS DEL BOT (Normalmente no se tocan)
# ==============================================================================
# ... (Todas las funciones webhook, process_message, send_whatsapp_message, home y el if __name__ == '__main__' se mantienen exactamente igual) ...
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
                        value = change.get('value', {})
                        if change.get('field') == 'messages' and value.get('messages'):
                            for message in value.get('messages'):
                                process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    try:
        from_number = message.get('from')
        if message.get('type') != 'text': return
        contact_name = next((c.get('profile', {}).get('name', 'Usuario') for c in contacts if c.get('wa_id') == from_number), 'Usuario')
        text_body = message.get('text', {}).get('body', '')
        logger.info(f"Procesando de {contact_name} ({from_number}): '{text_body}'")
        response_text = handle_sales_flow(from_number, contact_name, text_body) if from_number in user_sessions else generate_response(text_body, contact_name, from_number)
        if response_text:
            send_whatsapp_message(from_number, {"type": "text", "text": {"body": response_text}})
    except Exception as e:
        logger.error(f"Error en process_message: {e}")

def send_whatsapp_message(to_number, message_data):
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
```
    

