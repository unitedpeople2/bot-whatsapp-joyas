# ==========================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime
import re
import json      # <--- NUEVO: Para manejar las credenciales
import gspread   # <--- NUEVO: La librería de Google Sheets

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de variables de entorno de WhatsApp
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

# Diccionario para guardar el estado de la conversación (la "memoria" del bot)
user_sessions = {}


# ==============================================================================
# 2. ÁREA DE CONFIGURACIÓN DEL NEGOCIO
# ==============================================================================
# (Esta sección no cambia, contiene toda la información de tus productos,
# políticas de envío, distritos, etc.)
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
        "tienda_fisica": "No contamos con tienda física. Somos una tienda 100% online.", "garantia": "Ofrecemos una garantía de 15 días por cualquier defecto de fábrica.", "material_joyas": "Todas nuestras joyas son de acero inoxidable quirúrgico.", "medida_cadena": "El largo estándar de nuestras cadenas es de 45 cm.", "empaque": "¡Sí! Todas tus compras incluyen una hermosa cajita de regalo 🎁.", "metodos_pago": { "contra_entrega": "Para delivery en Lima puedes pagar con Efectivo, Yape o Plin al recibir tu pedido.", "adelanto_shalom": "El adelanto para envíos por Shalom puedes realizarlo por Yape, Plin o Transferencia."}
    }
}
COBERTURA_DELIVERY_LIMA = [ "ate", "barranco", "bellavista", "breña", "callao", "carabayllo", "carmen de la legua", "cercado de lima", "chorrillos", "comas", "el agustino", "independencia", "jesus maria", "la molina", "la perla", "la punta", "la victoria", "lince", "los olivos", "magdalena", "miraflores", "pueblo libre", "puente piedra", "rimac", "san borja", "san isidro", "san juan de lurigancho", "san juan de miraflores", "san luis", "san martin de porres", "san miguel", "santa anita", "surco", "surquillo", "villa el salvador", "villa maria del triunfo" ]
ABREVIATURAS_DISTRITOS = { "sjl": "san juan de lurigancho", "sjm": "san juan de miraflores", "smp": "san martin de porres", "vmt": "villa maria del triunfo", "ves": "villa el salvador", "lima centro": "cercado de lima" }


# ==============================================================================
# NUEVO: 3. FUNCIONES DE GOOGLE SHEETS
# ==============================================================================
def guardar_pedido_en_sheet(datos_pedido):
    """
    Se conecta a Google Sheets usando las credenciales de entorno y guarda
    los datos de un pedido en una nueva fila.
    """
    try:
        logger.info("Intentando guardar pedido en Google Sheets...")
        # Obtiene las credenciales y el nombre de la hoja desde las variables de entorno de Vercel
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')

        if not creds_json_str or not sheet_name:
            logger.error("Error: Faltan las variables de entorno GOOGLE_CREDENTIALS_JSON o GOOGLE_SHEET_NAME.")
            return False

        # Convierte el string JSON de las credenciales a un diccionario y se autentica
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        
        # Abre la hoja de cálculo por su nombre y selecciona la primera hoja
        sh = gc.open(sheet_name).sheet1
        
        # Prepara la fila con los datos del pedido. El orden debe coincidir con tus columnas.
        # Basado en tu captura, el orden es: Fecha, Nombre, Direccion, Referencia, Destino, DNI, Forma de pago, Celular, Pedido, Total
        nueva_fila = [
            datos_pedido.get('fecha', datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
            datos_pedido.get('nombre_cliente', ''), # Columna B: Nombre
            '', # Columna C: Direccion (no la pedimos)
            '', # Columna D: Referencia (no la pedimos)
            datos_pedido.get('distrito', ''), # Columna E: Destino (distrito)
            datos_pedido.get('dni_cliente', ''), # Columna F: DNI
            datos_pedido.get('tipo_envio', ''), # Columna G: Forma de pago
            datos_pedido.get('whatsapp_id', ''), # Columna H: Celular
            datos_pedido.get('producto_seleccionado', ''), # Columna I: Pedido
            datos_pedido.get('precio_producto', '') # Columna J: Total
        ]
        
        # Añade la fila al final de la hoja
        sh.append_row(nueva_fila)
        logger.info(f"¡Éxito! Pedido guardado en la hoja '{sheet_name}'.")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Error Crítico: No se encontró la hoja de cálculo llamada '{sheet_name}'. Revisa el nombre y que la hayas compartido con el email del bot.")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al intentar guardar en Google Sheets: {e}")
        return False

# ==============================================================================
# 4. FUNCIONES DE LÓGICA DEL BOT (El "cerebro" del bot)
# ==============================================================================

def verificar_cobertura(texto_usuario):
    # (Función sin cambios)
    texto = texto_usuario.lower().strip().replace('.', '').replace(',', '')
    for distrito in COBERTURA_DELIVERY_LIMA:
        if distrito in texto: return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        if re.search(r'\b' + re.escape(abreviatura) + r'\b', texto): return nombre_completo.title()
    return None

def buscar_producto(texto_usuario, return_key=False):
    # (Función sin cambios)
    texto = texto_usuario.lower()
    for key, producto_info in INFO_NEGOCIO["productos"].items():
        for palabra in producto_info["palabras_clave"]:
            if palabra in texto:
                return (key, producto_info) if return_key else producto_info
    return (None, None) if return_key else None

def generate_response(text, name, from_number):
    # (Función sin cambios)
    text = text.lower()
    if any(palabra in text for palabra in ['comprar', 'pedido', 'coordinar', 'quiero uno']):
        user_sessions[from_number] = {'state': 'awaiting_product_selection'}
        productos_disponibles = [f"{idx+1}️⃣ {prod['nombre_completo']}" for idx, prod in enumerate(INFO_NEGOCIO['productos'].values())]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Excelente decisión, {name}! ✨\n\nEstos son los productos que tenemos disponibles:\n{texto_productos}\n\n"
                "¿Cuál de ellos te gustaría llevar? Por favor, indícame el número o nombre.")
    distrito_encontrado = verificar_cobertura(text)
    if distrito_encontrado: return f"¡Buenas noticias, {name}! Sí tenemos cobertura de delivery contra entrega en {distrito_encontrado}. 🎉 Puedes iniciar tu pedido escribiendo 'comprar'."
    producto_encontrado = buscar_producto(text)
    if producto_encontrado: return (f"¡Te refieres a nuestro increíble {producto_encontrado['nombre_completo']}! ☀️\n\n" f"Características: {producto_encontrado['propiedades']}.\n" f"Material: {producto_encontrado['material']}.\nPrecio: {producto_encontrado['precio']}.\n\n" f"Para ordenarlo, solo escribe 'comprar'.")
    saludos_comunes = ['hola', 'hila', 'ola', 'buenos', 'buenas', 'bnas', 'qué tal', 'q tal', 'info']
    if any(saludo in text for saludo in saludos_comunes):
        productos_disponibles = [f"{idx+1}️⃣ {INFO_NEGOCIO['productos'][key]['nombre_completo']}" for idx, key in enumerate(INFO_NEGOCIO['productos'])]
        texto_productos = "\n".join(productos_disponibles)
        return (f"¡Hola {name}! 👋✨ Soy tu asesora virtual de Daaqui Joyas.\n\n" f"Tenemos en stock estas joyas mágicas con envío gratis:\n\n{texto_productos}\n\n" f"Escribe el número o el nombre del producto que te gustaría conocer.")
    return f"¡Hola {name}! 👋 No entendí tu consulta. Puedes preguntar sobre nuestros productos, 'envío' o 'pagos'."

def handle_sales_flow(user_id, user_name, user_message):
    session = user_sessions.get(user_id, {})
    current_state = session.get('state')

    if current_state == 'awaiting_product_selection':
        producto_key, producto_info = buscar_producto(user_message, return_key=True)
        if producto_info:
            session.update({
                'state': 'awaiting_district', 
                'producto_seleccionado': producto_info['nombre_completo'],
                'precio_producto': producto_info['precio']
            })
            return f"¡Confirmado: {producto_info['nombre_completo']}! Ahora, por favor, indícame tu distrito para coordinar el envío."
        return "No pude identificar el producto. Por favor, intenta con el número o nombre exacto."

    elif current_state == 'awaiting_district':
        distrito = verificar_cobertura(user_message)
        if distrito:
            session.update({'state': 'delivery_confirmation', 'distrito': distrito})
            return (f"¡Perfecto, delivery para {distrito}! 🎉 El pago es contra entrega.\n\nPara confirmar, por favor, envíame en un solo mensaje:\n- Tu nombre completo\n- Tu DNI")
        else:
            session.update({'state': 'shalom_confirmation', 'distrito': user_message.title()})
            return (f"Entendido. Para {user_message.title()} el envío es por Shalom. Se requiere un adelanto.\n\nSi estás de acuerdo, envíame en un solo mensaje:\n- Tu nombre completo\n- Tu DNI")

    elif current_state in ['delivery_confirmation', 'shalom_confirmation']:
        tipo_envio = "Contra Entrega" if current_state == 'delivery_confirmation' else "Adelanto Shalom"
        
        # MODIFICADO: Extraemos Nombre y DNI del mensaje del usuario
        try:
            nombre_cliente = user_message.split('\n')[0].strip()
            dni_cliente = next((line.strip() for line in user_message.split('\n') if 'dni' in line.lower()), '').split()[-1]
        except:
            nombre_cliente = user_message # Si falla, guardamos todo el mensaje
            dni_cliente = ''

        # Prepara los datos del pedido
        datos_del_pedido = {
            'producto_seleccionado': session.get('producto_seleccionado'),
            'precio_producto': session.get('precio_producto'),
            'tipo_envio': tipo_envio,
            'distrito': session.get('distrito'),
            'nombre_cliente': nombre_cliente,
            'dni_cliente': dni_cliente,
            'whatsapp_id': user_id
        }
        
        # Llama a la función para guardar en Google Sheets
        guardar_pedido_en_sheet(datos_del_pedido)
        
        # Limpia la sesión del usuario
        del user_sessions[user_id]
        return "¡Excelente! Hemos registrado tu pedido. Un asesor se pondrá en contacto contigo en breve. ¡Gracias por tu compra en Daaqui Joyas! 💖"
    
    return None


# ==============================================================================
# 5. FUNCIONES INTERNAS DEL BOT (El "motor" que no se toca)
# ==============================================================================

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    # (Función sin cambios)
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
                        value = change.get('value', {})
                        if change.get('field') == 'messages' and value.get('messages'):
                            for message in value.get('messages'):
                                process_message(message, value.get('contacts', []))
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    # (Función sin cambios)
    try:
        from_number = message.get('from')
        if message.get('type') != 'text': return
        contact_name = next((c.get('profile', {}).get('name', 'Usuario') for c in contacts if c.get('wa_id') == from_number), 'Usuario')
        text_body = message.get('text', {}).get('body', '')
        logger.info(f"Procesando de {contact_name} ({from_number}): '{text_body}'")
        response_text = handle_sales_flow(from_number, contact_name, text_body) if from_number in user_sessions else generate_response(text_body, contact_name, from_number)
        if response_text: send_whatsapp_message(from_number, {"type": "text", "text": {"body": response_text}})
    except Exception as e:
        logger.error(f"Error en process_message: {e}")

def send_whatsapp_message(to_number, message_data):
    # (Función sin cambios)
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
    # (Función sin cambios)
    return jsonify({'status': 'Bot Daaqui Activo'})

if __name__ == '__main__':
    app.run(debug=True)

