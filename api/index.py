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
import gspread

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de variables de entorno de WhatsApp
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
ADMIN_WHATSAPP_NUMBER = os.environ.get('ADMIN_WHATSAPP_NUMBER') 
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

# Diccionario para guardar el estado de la conversación
user_sessions = {}


# ==============================================================================
# 2. ÁREA DE CONFIGURACIÓN DEL NEGOCIO
# ==============================================================================
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
TODOS_LOS_DISTRITOS_LIMA = [
    "ancón", "ate", "barranco", "breña", "carabayllo", "chaclacayo", "chorrillos", 
    "cieneguilla", "comas", "el agustino", "independencia", "jesús maría", "la molina", 
    "la victoria", "lince", "los olivos", "lurigancho-chosica", "lurín", "magdalena del mar", 
    "miraflores", "pachacámac", "pucusana", "pueblo libre", "puente piedra", "punta hermosa", 
    "punta negra", "rímac", "san bartolo", "san borja", "san isidro", "san juan de lurigancho", 
    "san juan de miraflores", "san luis", "san martín de porres", "san miguel", "santa anita", 
    "santa maría del mar", "santa rosa", "santiago de surco", "surquillo", "villa el salvador", 
    "villa maría del triunfo", "cercado de lima",
    # Callao
    "bellavista", "carmen de la legua", "la perla", "la punta", "ventanilla", "callao"
]
COBERTURA_DELIVERY_LIMA = [ "ate", "barranco", "bellavista", "breña", "callao", "carabayllo", "carmen de la legua", "cercado de lima", "chorrillos", "comas", "el agustino", "independencia", "jesus maria", "la molina", "la perla", "la punta", "la victoria", "lince", "los olivos", "magdalena", "miraflores", "pueblo libre", "puente piedra", "rimac", "san borja", "san isidro", "san juan de lurigancho", "san juan de miraflores", "san luis", "san martin de porres", "san miguel", "santa anita", "surco", "surquillo", "villa el salvador", "villa maria del triunfo" ]
ABREVIATURAS_DISTRITOS = { "sjl": "san juan de lurigancho", "sjm": "san juan de miraflores", "smp": "san martin de porres", "vmt": "villa maria del triunfo", "ves": "villa el salvador", "lima centro": "cercado de lima" }
PALABRAS_CANCELACION = ["cancelar", "cancelo", "ya no quiero", "ya no", "mejor no", "detener", "no gracias"]

# ==============================================================================
# 3. FUNCIONES DE GOOGLE SHEETS
# ==============================================================================
def guardar_pedido_en_sheet(datos_pedido):
    try:
        logger.info("[Sheets] Iniciando proceso de guardado...")
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
        if not creds_json_str or not sheet_name:
            logger.error("[Sheets] ERROR: Faltan variables de entorno.")
            return False
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open(sheet_name)
        sh = spreadsheet.sheet1
        nueva_fila = [
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            datos_pedido.get('producto_seleccionado', 'N/A'),
            datos_pedido.get('precio_producto', 'N/A'),
            datos_pedido.get('tipo_envio', 'N/A'),
            datos_pedido.get('distrito', 'N/A'),
            datos_pedido.get('detalles_cliente', 'N/A'),
            datos_pedido.get('whatsapp_id', 'N/A')
        ]
        sh.append_row(nueva_fila)
        logger.info(f"[Sheets] ¡ÉXITO! Pedido guardado.")
        return True
    except Exception as e:
        logger.error(f"[Sheets] ERROR INESPERADO: {e}")
        return False

# ==============================================================================
# 4. FUNCIONES DE LÓGICA DEL BOT
# ==============================================================================
def verificar_cobertura(texto_usuario):
    texto = texto_usuario.lower().strip().replace('.', '').replace(',', '')
    for distrito in COBERTURA_DELIVERY_LIMA:
        if re.search(r'\b' + re.escape(distrito) + r'\b', texto):
            return distrito.title()
    for abreviatura, nombre_completo in ABREVIATURAS_DISTRITOS.items():
        if re.search(r'\b' + re.escape(abreviatura) + r'\b', texto):
            return nombre_completo.title()
    return None

def es_distrito_de_lima(texto_usuario):
    texto = texto_usuario.lower().strip().replace('.', '').replace(',', '')
    for distrito in TODOS_LOS_DISTRITOS_LIMA:
        if re.search(r'\b' + re.escape(distrito) + r'\b', texto):
            return distrito.title()
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
    text = user_message.lower().strip()
    if any(palabra in text for palabra in PALABRAS_CANCELACION):
        del user_sessions[user_id]
        return "Entendido, he cancelado el proceso. Si cambias de opinión o necesitas algo más, no dudes en escribirme. ¡Que tengas un buen día! 😊"
    producto_seleccionado = session.get('producto_seleccionado')
    if producto_seleccionado:
        producto_info = buscar_producto(producto_seleccionado)
        if producto_info and any(palabra in text for palabra in ['precio', 'costo', 'cuesta', 'material', 'medida', 'tamaño']):
            respuesta_pregunta = (f"¡Claro! Sobre el {producto_info['nombre_completo']}:\n" f"- Precio: {producto_info['precio']}\n" f"- Material: {producto_info['material']}\n" f"- Propiedades: {producto_info['propiedades']}\n\n" "Continuemos donde nos quedamos. ¿Listo para seguir?")
            return respuesta_pregunta
    if current_state == 'awaiting_product_selection':
        producto_key, producto_info = buscar_producto(text, return_key=True)
        if producto_info:
            session.update({'state': 'awaiting_location', 'producto_seleccionado': producto_info['nombre_completo'], 'precio_producto': producto_info['precio']})
            return f"¡Confirmado: {producto_info['nombre_completo']}! Para continuar, por favor, dime: ¿eres de Lima o de provincia?"
        return "No pude identificar el producto. Por favor, intenta con el número o nombre exacto."
    elif current_state == 'awaiting_location':
        distrito_lima = es_distrito_de_lima(text)
        if distrito_lima:
            if distrito_lima.lower() in COBERTURA_DELIVERY_LIMA:
                session.update({'state': 'awaiting_delivery_details', 'distrito': distrito_lima, 'tipo_envio': 'Contra Entrega'})
                return f"¡Excelente! 🏙️ Tenemos cobertura en {distrito_lima}.\nPara completar tu pedido, necesito que me brindes en un solo mensaje: Nombre Completo, Dirección exacta y Referencia del domicilio. ✍🏼"
            else:
                session.update({'state': 'awaiting_shalom_agreement', 'distrito': distrito_lima, 'tipo_envio': 'Shalom'})
                return (f"Entendido. Para {distrito_lima}, los envíos son por Shalom y requieren un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}. " "¿Estás de acuerdo? (Sí/No)")
        elif 'lima' in text:
            session['state'] = 'awaiting_lima_district'
            return "¡Genial! Para saber qué tipo de envío te corresponde, por favor, indícame tu distrito."
        # MEJORADO: Se añade el nuevo paso para preguntar la provincia
        elif 'provincia' in text:
            session['state'] = 'awaiting_province_name'
            return "¡Genial! Hacemos envios a todo el Peru solo por Shalom, por favor, indícame tu provincia."
        else:
            return "¿Eres de Lima o de provincia? Por favor, responde con una de esas dos opciones."
    
    # NUEVO: Estado para manejar la respuesta de la provincia
    elif current_state == 'awaiting_province_name':
        provincia_cliente = user_message.title()
        session.update({
            'state': 'awaiting_shalom_agreement', 
            'distrito': provincia_cliente, # Usamos 'distrito' para guardar la ubicación
            'tipo_envio': 'Shalom'
        })
        return (f"Entendido. Para {provincia_cliente}, los envíos son por agencia Shalom y requieren un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}. "
                "¿Estás de acuerdo? (Sí/No)")

    elif current_state == 'awaiting_lima_district':
        distrito_cobertura = verificar_cobertura(text)
        if distrito_cobertura:
            session.update({'state': 'awaiting_delivery_details', 'distrito': distrito_cobertura, 'tipo_envio': 'Contra Entrega'})
            return f"¡Excelente! 🏙️ Tenemos cobertura en {distrito_cobertura}.\nPara completar tu pedido, necesito que me brindes en un solo mensaje: Nombre Completo, Dirección exacta y Referencia del domicilio. ✍🏼"
        else:
            distrito_sin_cobertura = user_message.title()
            session.update({'state': 'awaiting_shalom_agreement', 'distrito': distrito_sin_cobertura, 'tipo_envio': 'Shalom'})
            return (f"Entendido. Para {distrito_sin_cobertura}, los envíos son por Shalom y requieren un adelanto de {INFO_NEGOCIO['politicas_envio']['envio_shalom']['adelanto_requerido']}. " "¿Estás de acuerdo? (Sí/No)")
    elif current_state == 'awaiting_shalom_agreement':
        if 'si' in text or 'sí' in text or 'de acuerdo' in text:
            session.update({'state': 'awaiting_shalom_experience', 'tipo_envio': 'Shalom'})
            return "¿Alguna vez has recogido un pedido en una agencia Shalom? (Sí/No)"
        else:
            del user_sessions[user_id]
            return "Entiendo. Si cambias de opinión, aquí estaremos. ¡Gracias!"
    elif current_state == 'awaiting_shalom_experience':
        if 'si' in text or 'sí' in text:
            session['state'] = 'awaiting_shalom_details'
            return "¡Perfecto! Bríndame en un solo mensaje tu Nombre Completo, DNI y la dirección de la agencia Shalom donde recoges.✍🏼"
        else:
            session['state'] = 'awaiting_shalom_agency_knowledge'
            explicacion_shalom = (
                "¡No te preocupes! Te explico rápidamente cómo funciona:\n\n"
                "🏪 *Shalom* es una empresa de envíos muy confiable.\n"
                "🆔 Solo necesitas tu *DNI* para recoger tu paquete.\n"
                "🔑 Te daremos un *código de seguridad* para que puedas recoger tu pedido.\n"
                "🔒 Es un método *súper seguro y rápido*.\n\n"
                "Como ves, es muy fácil. ¿Conoces la ubicación de alguna agencia Shalom donde podrías recoger tu pedido? (Sí/No)"
            )
            return explicacion_shalom
    elif current_state == 'awaiting_shalom_agency_knowledge':
        if 'si' in text or 'sí' in text:
            session['state'] = 'awaiting_shalom_details'
            return "¡Genial! Bríndame en un solo mensaje tu Nombre, DNI y la dirección de la agencia Shalom.✍🏼"
        else:
            del user_sessions[user_id]
            return "Entiendo. Te recomendamos buscar tu agencia más cercana en la página de Shalom para una futura compra. ¡Gracias!"
    elif current_state in ['awaiting_delivery_details', 'awaiting_shalom_details']:
        session['detalles_cliente'] = user_message 
        session['state'] = 'awaiting_final_confirmation'
        resumen = (
            "¡Perfecto, ya casi terminamos! ✅\n"
            "Revisa que tus datos sean correctos:\n\n"
            f"Pedido: 1x {session.get('producto_seleccionado', '')}\n"
            f"Total: {session.get('precio_producto', '')}\n"
            f"Lugar de Envío: {session.get('distrito', 'No especificado')}\n\n"
            f"Datos de Envío:\n{session.get('detalles_cliente', '')}\n\n"
            "¿Confirmas que todo es correcto? (Sí/No)"
        )
        return resumen
    elif current_state == 'awaiting_final_confirmation':
        if 'si' in text or 'sí' in text or 'correcto' in text:
            datos_del_pedido = {
                'producto_seleccionado': session.get('producto_seleccionado'),
                'precio_producto': session.get('precio_producto'),
                'tipo_envio': session.get('tipo_envio'),
                'distrito': session.get('distrito'),
                'detalles_cliente': session.get('detalles_cliente'),
                'whatsapp_id': user_id
            }
            guardado_exitoso = guardar_pedido_en_sheet(datos_del_pedido)
            if guardado_exitoso:
                if ADMIN_WHATSAPP_NUMBER:
                    mensaje_notificacion = (
                        f"🎉 ¡Nueva Venta Registrada! 🎉\n\n"
                        f"Producto: {datos_del_pedido.get('producto_seleccionado')}\n"
                        f"Precio: {datos_del_pedido.get('precio_producto')}\n"
                        f"Tipo de Envío: {datos_del_pedido.get('tipo_envio')}\n"
                        f"Distrito/Prov: {datos_del_pedido.get('distrito')}\n"
                        f"Cliente WA ID: {datos_del_pedido.get('whatsapp_id')}\n\n"
                        f"Detalles:\n{datos_del_pedido.get('detalles_cliente')}"
                    )
                    send_whatsapp_message(ADMIN_WHATSAPP_NUMBER, {"type": "text", "text": {"body": mensaje_notificacion}})
                del user_sessions[user_id]
                return "¡Excelente! Hemos registrado tu pedido con éxito. Un asesor se pondrá en contacto contigo en breve. ¡Gracias por tu compra! 💖"
            else:
                return "¡Uy! Tuvimos un problema al registrar tu pedido. Por favor, intenta confirmar nuevamente."
        elif 'no' in text:
            tipo_envio = session.get('tipo_envio')
            previous_state = 'awaiting_delivery_details' if tipo_envio == 'Contra Entrega' else 'awaiting_shalom_details'
            session['state'] = previous_state
            return "Entendido. Para corregirlo, por favor, envíame *toda la información de envío de nuevo* en un solo mensaje."
        else:
            return "Por favor, responde con 'Sí' para confirmar o 'No' para corregir."
    return None

# ==============================================================================
# 5. FUNCIONES INTERNAS DEL BOT
# ==============================================================================
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
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
    try:
        from_number = message.get('from')
        if message.get('type') != 'text': return
        contact_name = next((c.get('profile', {}).get('name', 'Usuario') for c in contacts if c.get('wa_id') == from_number), 'Usuario')
        text_body = message.get('text', {}).get('body', '')
        logger.info(f"Procesando de {contact_name} ({from_number}): '{text_body}'")
        session_exists = from_number in user_sessions
        text_lower = text_body.lower()
        if session_exists:
            response_text = handle_sales_flow(from_number, contact_name, text_body)
        elif not session_exists and any(palabra in text_lower for palabra in ['comprar', 'pedido', 'coordinar', 'quiero uno']):
            user_sessions[from_number] = {'state': 'awaiting_product_selection'}
            productos_disponibles = [f"{idx+1}️⃣ {prod['nombre_completo']}" for idx, prod in enumerate(INFO_NEGOCIO['productos'].values())]
            texto_productos = "\n".join(productos_disponibles)
            response_text = (f"¡Excelente decisión, {contact_name}! ✨\n\n"
                           f"Estos son los productos que tenemos disponibles:\n{texto_productos}\n\n"
                           "¿Cuál de ellos te gustaría llevar?")
        else:
            response_text = generate_response(text_body, contact_name, from_number)
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

