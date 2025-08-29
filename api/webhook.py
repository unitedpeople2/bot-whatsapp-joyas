from flask import Flask, request, jsonify
import os
import requests
import json

# Configurar credenciales desde variables de entorno
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("WHATSAPP_WEBHOOK_SECRET")

# Importar Google AI
try:
    import google.generativeai as genai
    google_key = os.environ.get("GOOGLE_AI_API_KEY")
    genai.configure(api_key=google_key)
    GOOGLE_AI_AVAILABLE = True
    print("✅ Google AI configurado correctamente")
except Exception as e:
    GOOGLE_AI_AVAILABLE = False
    print(f"⚠ Error configurando Google AI: {e}")

app = Flask(__name__)

def generar_respuesta_con_ia(mensaje_usuario):
    """Genera respuesta usando Google AI o respuesta estática"""
    if GOOGLE_AI_AVAILABLE:
        try:
            model = genai.GenerativeModel('gemini-pro')
            prompt = f"""
            Eres 'Daqui', un asistente de ventas virtual experto en joyería fina para mujeres en Perú. 
            Tu tono es amable, elegante y servicial.
            Tu misión es ayudar a los clientes, responder sus dudas sobre los productos y guiarlos en su compra.
            
            El cliente ha preguntado lo siguiente: '{mensaje_usuario}'
            
            Por favor, genera una respuesta adecuada como asistente de ventas de joyería.
            Mantén el tono profesional pero cálido, y ofrece ayuda específica.
            """
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Error con la API de Google AI: {e}")
            return generar_respuesta_estatica(mensaje_usuario)
    else:
        return generar_respuesta_estatica(mensaje_usuario)

def generar_respuesta_estatica(mensaje_usuario):
    """Respuestas estáticas mientras configuramos la IA"""
    mensaje_lower = mensaje_usuario.lower()
    
    if any(saludo in mensaje_lower for saludo in ['hola', 'buenos', 'buenas', 'hi']):
        return "¡Hola! Soy Daqui, tu asistente personal de joyería fina. ¿En qué puedo ayudarte hoy? Tengo hermosas piezas para mujeres elegantes como tú."
    
    elif any(palabra in mensaje_lower for palabra in ['anillo', 'anillos']):
        return "¡Excelente elección! Nuestros anillos son piezas únicas, perfectas para cualquier ocasión especial. ¿Buscas algo específico? ¿Para compromiso, matrimonio o uso diario?"
    
    elif any(palabra in mensaje_lower for palabra in ['collar', 'collares']):
        return "Los collares son mi especialidad. Tenemos desde piezas delicadas para el día a día hasta diseños llamativos para ocasiones especiales. ¿Prefieres oro, plata o piedras preciosas?"
    
    elif any(palabra in mensaje_lower for palabra in ['precio', 'costo', 'cuanto']):
        return "Nuestros precios varían según el diseño y materiales. Tenemos opciones desde S/.150 hasta piezas exclusivas de S/.2000+. ¿Qué tipo de joya te interesa para darte un precio más exacto?"
    
    elif any(palabra in mensaje_lower for palabra in ['oro', 'plata']):
        return "Trabajamos con oro de 14k y 18k, así como plata 925 de la mejor calidad. Todas nuestras piezas tienen certificado de autenticidad. ¿Te interesa algún metal en particular?"
    
    else:
        return "Gracias por tu consulta. Soy Daqui y estoy aquí para ayudarte con nuestras hermosas joyas. Puedes preguntarme sobre anillos, collares, aretes, precios o cualquier duda que tengas. ¡Estoy para servirte!"

def enviar_mensaje(destinatario, texto):
    """Envía mensaje de WhatsApp"""
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": destinatario,
        "type": "text",
        "text": { "body": texto }
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        print(f"Mensaje enviado a {destinatario}. Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error enviando mensaje: {response.text}")
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

# HANDLER PRINCIPAL PARA VERCEL
def handler(req):
    """Handler principal que maneja tanto GET como POST"""
    if req.method == 'GET':
        # Verificación del webhook
        mode = req.args.get('hub.mode')
        token = req.args.get('hub.verify_token')
        challenge = req.args.get('hub.challenge')
        
        print(f"=== VERIFICACIÓN WEBHOOK ===")
        print(f"Mode: {mode}")
        print(f"Token recibido: '{token}'")
        print(f"Token esperado: '{VERIFY_TOKEN}'")
        print(f"Challenge: {challenge}")
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("✅ Webhook verificado correctamente")
            return challenge, 200
        else:
            print("❌ Verificación falló")
            return 'Forbidden', 403
    
    elif req.method == 'POST':
        # Manejar mensajes entrantes de WhatsApp
        try:
            body = req.get_json()
            print("=== MENSAJE RECIBIDO ===")
            print(json.dumps(body, indent=2))
            
            # Verificar si es un mensaje válido
            if (body.get("object") and 
                body.get("entry") and 
                len(body["entry"]) > 0 and
                body["entry"][0].get("changes") and
                len(body["entry"][0]["changes"]) > 0):
                
                changes = body["entry"][0]["changes"][0]
                
                if (changes.get("value", {}).get("messages") and
                    len(changes["value"]["messages"]) > 0):
                    
                    message_info = changes["value"]["messages"][0]
                    phone_number = message_info.get("from")
                    
                    # Verificar si es mensaje de texto
                    if message_info.get("type") == "text":
                        message_body = message_info.get("text", {}).get("body", "")
                        
                        print(f"📱 Mensaje de {phone_number}: {message_body}")
                        
                        # Generar y enviar respuesta
                        respuesta_ia = generar_respuesta_con_ia(message_body)
                        enviar_mensaje(phone_number, respuesta_ia)
                        
                        print(f"🤖 Respuesta enviada: {respuesta_ia[:50]}...")
            
            return jsonify({'status': 'success'}), 200
        
        except Exception as e:
            print(f"❌ Error procesando mensaje: {e}")
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Method not allowed'}), 405

# Routes para compatibilidad con Vercel
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    return handler(request)

@app.route('/', methods=['GET'])
def home():
    return """
    <h1>🤖 Daqui - WhatsApp Bot</h1>
    <p>Webhook funcionando correctamente!</p>
    <p>Estado: ✅ Activo</p>
    """

# Esta función es la que Vercel llama directamente
def application(environ, start_response):
    return app(environ, start_response)