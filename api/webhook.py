from http.server import BaseHTTPRequestHandler
import os
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv

# Carga las variables de entorno desde el archivo .env (para pruebas locales)
load_dotenv()

# Configura las credenciales desde las variables de entorno
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Procesa la verificación del webhook de Meta
        if self.path.startswith('/api/webhook?'):
            query_components = dict(qc.split("=") for qc in self.path.split('?')[1].split("&"))
            
            mode = query_components.get("hub.mode")
            token = query_components.get("hub.verify_token")
            challenge = query_components.get("hub.challenge")

            if mode == "subscribe" and token == VERIFY_TOKEN:
                self.send_response(200)
                self.send_header('Content-type','text/plain')
                self.end_headers()
                self.wfile.write(challenge.encode('utf-8'))
            else:
                self.send_response(403)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
        return

    def do_POST(self):
        # Procesa los mensajes entrantes de WhatsApp
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        body = json.loads(post_data)

        try:
            if body.get("object"):
                if (body.get("entry") and body["entry"][0].get("changes") and
                    body["entry"][0]["changes"][0].get("value", {}).get("messages") and
                    body["entry"][0]["changes"][0]["value"]["messages"][0]):
                    
                    message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
                    phone_number = message_info["from"]
                    message_body = message_info["text"]["body"]
                    
                    respuesta_ia = self.generar_respuesta_con_ia(message_body)
                    self.enviar_mensaje(phone_number, respuesta_ia)
        except Exception as e:
            print(f"Error procesando el mensaje: {e}")

        self.send_response(200)
        self.end_headers()
        return

    def generar_respuesta_con_ia(self, mensaje_usuario):
        try:
            model = genai.GenerativeModel('gemini-pro')
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

    def enviar_mensaje(self, destinatario, texto):
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