from flask import Flask, request
import os
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv

# Carga las variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)

# Configura las credenciales desde las variables de entorno
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

# Esta es la función principal que Vercel ejecutará
def handler(request):
    # Lógica para la verificación del Webhook (cuando Meta te pida verificar)
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")

    # Lógica para procesar un mensaje de WhatsApp entrante
    body = request.get_json()
    try:
        if body["object"]:
            if (body["entry"] and body["entry"][0]["changes"] and body["entry"][0]["changes"][0]["value"]["messages"] and body["entry"][0]["changes"][0]["value"]["messages"][0]):
                phone_number = body['entry'][0]['changes'][0]['value']['messages'][0]['from']
                message_body = body['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
                
                # Genera una respuesta usando Google Gemini
                respuesta_ia = generar_respuesta_con_ia(message_body)
                
                # Envía la respuesta de vuelta al usuario
                enviar_mensaje(phone_number, respuesta_ia)
    except Exception as e:
        # Imprime el error si algo falla (lo veremos en los logs de Vercel)
        print(f"Error procesando el mensaje: {e}")
    
    return "OK", 200

def generar_respuesta_con_ia(mensaje_usuario):
    try:
        model = genai.GenerativeModel('gemini-pro')
        # ¡Este es el cerebro de tu bot! Modifica este prompt para que se ajuste a tu negocio.
        prompt = f"""
        Eres 'Daqui', un asistente de ventas virtual experto en joyería fina para mujeres en Perú. Tu tono es amable, elegante y servicial.
        Tu misión es ayudar a los clientes, responder sus dudas sobre los productos y guiarlos en su compra.
        El cliente ha preguntado lo siguiente: '{mensaje_usuario}'
        Por favor, genera una respuesta adecuada.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error con la API de Google AI: {e}")
        return "Lo siento, estoy teniendo un problema técnico en este momento. Por favor, intenta de nuevo en un momento."

def enviar_mensaje(destinatario, texto):
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
    requests.post(url, headers=headers, data=json.dumps(data))

# El siguiente código es para que Flask maneje las peticiones cuando se despliega en Vercel
@app.route("/api/webhook", methods=['GET', 'POST'])
def flask_handler():
    return handler(request)