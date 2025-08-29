from flask import Flask, request, jsonify
import requests
import logging
import os
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración - Corregidas las variables de entorno
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'JoyasBot2025!')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" if PHONE_NUMBER_ID else None

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Verificación del webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        logger.info(f"Verificación recibida - Mode: {mode}, Token: {token}")
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("Webhook verificado exitosamente")
            return challenge
        else:
            logger.warning(f"Verificación fallida - Token esperado: {VERIFY_TOKEN}, Token recibido: {token}")
            return 'Forbidden', 403
    
    elif request.method == 'POST':
        # Procesar mensajes entrantes
        try:
            data = request.get_json()
            logger.info(f"Datos recibidos: {data}")
            
            # Verificar si hay mensajes
            if 'entry' in data:
                for entry in data['entry']:
                    if 'changes' in entry:
                        for change in entry['changes']:
                            if change.get('field') == 'messages':
                                value = change.get('value', {})
                                if 'messages' in value:
                                    for message in value['messages']:
                                        process_message(message, value.get('contacts', []))
            
            return jsonify({'status': 'success'}), 200
            
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return jsonify({'error': str(e)}), 500

def process_message(message, contacts):
    """Procesar mensaje individual"""
    try:
        # Obtener información del mensaje
        from_number = message.get('from')
        message_type = message.get('type')
        timestamp = message.get('timestamp')
        
        # Obtener nombre del contacto
        contact_name = "Usuario"
        for contact in contacts:
            if contact.get('wa_id') == from_number:
                contact_name = contact.get('profile', {}).get('name', 'Usuario')
                break
        
        logger.info(f"Procesando mensaje de {contact_name} ({from_number})")
        
        # Procesar según el tipo de mensaje
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '').lower()
            logger.info(f"Mensaje de texto: {text_body}")
            
            # Generar respuesta basada en el mensaje
            response_text = generate_response(text_body, contact_name)
            
            if response_text:
                send_whatsapp_message(from_number, response_text)
        
        elif message_type in ['image', 'document', 'audio', 'video']:
            logger.info(f"Mensaje multimedia recibido: {message_type}")
            send_whatsapp_message(from_number, f"¡Hola {contact_name}! He recibido tu {message_type}. ¿En qué puedo ayudarte con nuestras joyas? 💎✨")
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")

def generate_response(text, name):
    """Generar respuesta automática basada en el mensaje"""
    text = text.lower()
    
    # Saludos
    if any(saludo in text for saludo in ['hola', 'hi', 'hello', 'buenos días', 'buenas tardes', 'buenas noches']):
        return f"¡Hola {name}! 👋✨ Bienvenid@ a nuestra joyería. Somos especialistas en joyas únicas y elegantes. ¿En qué puedo ayudarte hoy? 💎"
    
    # Consultas sobre productos
    elif any(palabra in text for palabra in ['anillo', 'anillos', 'sortija']):
        return f"¡Excelente elección {name}! 💍 Tenemos una hermosa colección de anillos:\n\n• Anillos de compromiso 💕\n• Alianzas de matrimonio 👫\n• Anillos de moda ✨\n• Anillos con piedras preciosas 💎\n\n¿Te interesa algún estilo en particular?"
    
    elif any(palabra in text for palabra in ['collar', 'collares', 'cadena']):
        return f"¡Perfecto {name}! ✨ Nuestros collares son únicos:\n\n• Collares de oro 🏆\n• Collares de plata 🌟\n• Collares con dijes 💫\n• Gargantillas elegantes 💎\n\n¿Qué estilo buscas?"
    
    elif any(palabra in text for palabra in ['arete', 'aretes', 'pendiente', 'zarcillo']):
        return f"¡Genial {name}! 👂✨ Tenemos aretes espectaculares:\n\n• Aretes de perlas 🤍\n• Aretes de oro/plata 🌟\n• Aretes largos elegantes 💫\n• Aretes minimalistas 🎯\n\n¿Cuál es tu estilo favorito?"
    
    elif any(palabra in text for palabra in ['pulsera', 'pulseras', 'brazalete']):
        return f"¡Hermosa elección {name}! 💪✨ Nuestras pulseras:\n\n• Pulseras de tennis 💎\n• Pulseras de eslabones 🔗\n• Pulseras con charms 🍀\n• Brazaletes statement 👑\n\n¿Qué tipo prefieres?"
    
    # Consultas sobre materiales
    elif any(palabra in text for palabra in ['oro', 'dorado']):
        return f"¡El oro es eterno {name}! 🏆 Trabajamos con:\n\n• Oro 14k y 18k 💛\n• Oro blanco elegante 🤍\n• Oro rosa romántico 🌹\n• Diseños exclusivos ✨\n\n¿Te interesa ver nuestra colección?"
    
    elif any(palabra in text for palabra in ['plata', 'plateado']):
        return f"¡La plata es versátil {name}! 🌟 Ofrecemos:\n\n• Plata 925 de calidad 💫\n• Diseños modernos 🎯\n• Acabados especiales ✨\n• Precios accesibles 👍\n\n¿Qué tipo de joya buscas?"
    
    elif any(palabra in text for palabra in ['diamante', 'brillante']):
        return f"¡Los diamantes son únicos {name}! 💎 Contamos con:\n\n• Diamantes certificados 📜\n• Diferentes tallas ✨\n• Montajes exclusivos 👑\n• Garantía de calidad 🛡️\n\n¿Es para una ocasión especial?"
    
    # Consultas comerciales
    elif any(palabra in text for palabra in ['precio', 'costo', 'cuanto', 'valor']):
        return f"¡Tenemos opciones para todos {name}! 💰\n\n• Financiamiento disponible 💳\n• Promociones especiales 🎉\n• Descuentos por volumen 📦\n• Planes de pago flexibles ⏰\n\n¿Te gustaría ver alguna colección específica?"
    
    elif any(palabra in text for palabra in ['envío', 'entrega', 'delivery']):
        return f"¡Enviamos a todo el país {name}! 🚚✨\n\n• Envío gratis en compras +$200 🎁\n• Entrega 2-5 días hábiles ⚡\n• Empaque especial y seguro 📦\n• Seguimiento en tiempo real 📱\n\n¿Desde qué ciudad nos escribes?"
    
    elif any(palabra in text for palabra in ['garantía', 'certificado', 'calidad']):
        return f"¡La calidad es nuestra prioridad {name}! 🏆\n\n• Garantía de 1 año 🛡️\n• Certificados de autenticidad 📜\n• Materiales premium ⭐\n• Servicio post-venta 🤝\n\n¿Qué joya te interesa?"
    
    # Ocasiones especiales
    elif any(palabra in text for palabra in ['matrimonio', 'boda', 'casamiento']):
        return f"¡Qué emoción {name}! 👰✨ Para tu boda tenemos:\n\n• Anillos de compromiso 💍\n• Alianzas matrimoniales 👫\n• Aretes para novia 👂\n• Sets completos 💎\n\n¡Hagamos tu día perfecto!"
    
    elif any(palabra in text for palabra in ['regalo', 'obsequio', 'presente']):
        return f"¡Qué lindo detalle {name}! 🎁✨ Tenemos regalos perfectos:\n\n• Joyas para mamá 👩‍❤️‍👨\n• Regalos románticos 💕\n• Joyas para amigas 👯‍♀️\n• Empaque regalo gratis 🎀\n\n¿Para quién es el regalo?"
    
    elif any(palabra in text for palabra in ['cumpleaños', 'aniversario']):
        return f"¡Celebremos juntos {name}! 🎂🎉 Para ocasiones especiales:\n\n• Joyas personalizadas 💎\n• Grabado incluido ✏️\n• Diseños únicos ⭐\n• Entrega express 🚀\n\n¿Qué fecha necesitas la entrega?"
    
    # Información de contacto
    elif any(palabra in text for palabra in ['dirección', 'ubicación', 'donde', 'tienda']):
        return f"¡Te esperamos {name}! 📍✨\n\n📍 Dirección: [Tu dirección aquí]\n⏰ Horario: Lun-Sáb 9AM-7PM\n📱 WhatsApp: Este mismo número\n🌐 Web: [tu-web.com]\n\n¿Te gustaría agendar una cita?"
    
    elif any(palabra in text for palabra in ['horario', 'hora', 'abierto', 'cerrado']):
        return f"Nuestros horarios {name}! ⏰\n\n📅 Lunes a Sábado: 9:00 AM - 7:00 PM\n🔒 Domingos: Cerrado\n📱 WhatsApp: 24/7 disponible\n🛏️ Citas especiales: Previa coordinación\n\n¿Cuándo te gustaría visitarnos?"
    
    # Agradecimientos
    elif any(palabra in text for palabra in ['gracias', 'thank you', 'genial', 'perfecto']):
        return f"¡De nada {name}! 😊✨ Estamos aquí para ayudarte. ¿Hay algo más en lo que pueda asistirte? Recuerda que tenemos:\n\n💎 Joyas únicas y elegantes\n🎁 Empaque regalo gratuito\n🚚 Envíos a nivel nacional\n💳 Financiamiento disponible"
    
    # Despedidas
    elif any(palabra in text for palabra in ['adiós', 'bye', 'hasta luego', 'nos vemos']):
        return f"¡Hasta pronto {name}! 👋✨ Fue un placer atenderte. Recuerda que estamos aquí cuando necesites nuestras hermosas joyas. ¡Que tengas un día brillante como nuestros diamantes! 💎🌟"
    
    # Respuesta genérica
    else:
        return f"¡Hola {name}! 👋✨ Gracias por contactarnos. Somos especialistas en:\n\n💍 Anillos y alianzas\n✨ Collares elegantes\n👂 Aretes únicos\n💎 Pulseras premium\n\n¿En qué joya puedo ayudarte hoy?"

def send_whatsapp_message(to_number, message):
    """Enviar mensaje de WhatsApp"""
    if not WHATSAPP_TOKEN:
        logger.error("Token de WhatsApp no configurado")
        return False
    
    if not WHATSAPP_API_URL:
        logger.error("Phone Number ID no configurado")
        return False
    
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": message}
    }
    
    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            logger.info(f"Mensaje enviado exitosamente a {to_number}")
            return True
        else:
            logger.error(f"Error enviando mensaje: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error enviando mensaje: {e}")
        return False

@app.route('/api/health', methods=['GET'])
def health():
    """Endpoint de salud"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/api', methods=['GET'])
@app.route('/', methods=['GET'])
def home():
    """Página de inicio"""
    return jsonify({
        'message': 'Bot de WhatsApp para Joyería',
        'status': 'active',
        'endpoints': {
            'webhook': '/api/webhook',
            'health': '/api/health'
        }
    })

if __name__ == '__main__':
    app.run(debug=True)