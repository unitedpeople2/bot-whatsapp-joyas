from http.server import BaseHTTPRequestHandler
import os
import json
import requests

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Maneja las peticiones GET para verificación del webhook"""
        try:
            from urllib.parse import urlparse, parse_qs
            
            # Variables de entorno
            VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
            
            # Parsear la URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            mode = query_params.get('hub.mode', [None])[0]
            token = query_params.get('hub.verify_token', [None])[0]
            challenge = query_params.get('hub.challenge', [None])[0]
            
            print(f"GET - Verificación: mode={mode}, token={token}")
            
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(challenge.encode())
            else:
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Forbidden'}).encode())
                
        except Exception as e:
            print(f"Error en GET: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_POST(self):
        """Maneja las peticiones POST para procesar mensajes"""
        try:
            # Variables de entorno
            ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
            PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
            
            # Configurar Google AI
            google_ai_available = False
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
                google_ai_available = True
            except Exception as e:
                print(f"Google AI no disponible: {e}")
            
            # Leer el body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            
            print(f"POST - Body recibido: {json.dumps(body, indent=2)}")
            
            # Extraer mensaje
            if (body.get('entry') and 
                len(body['entry']) > 0 and
                body['entry'][0].get('changes') and 
                len(body['entry'][0]['changes']) > 0):
                
                changes = body['entry'][0]['changes'][0]
                messages = changes.get('value', {}).get('messages', [])
                
                if messages:
                    message = messages[0]
                    from_number = message.get('from')
                    text = message.get('text', {}).get('body', '')
                    
                    print(f"Mensaje de {from_number}: {text}")
                    
                    if text and from_number:
                        # Generar respuesta
                        if google_ai_available:
                            response_text = generar_respuesta_ai(text)
                        else:
                            response_text = generar_respuesta_simple(text)
                        
                        # Enviar mensaje
                        enviar_whatsapp(from_number, response_text, ACCESS_TOKEN, PHONE_NUMBER_ID)
            
            # Respuesta exitosa
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'success'}).encode())
            
        except Exception as e:
            print(f"Error en POST: {e}")
            import traceback
            traceback.print_exc()
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

def generar_respuesta_ai(texto):
    """Generar respuesta con Google AI"""
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""Eres 'Daqui', asistente de joyería fina en Perú. 
        Responde de forma amable y profesional a: {texto}"""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error en Google AI: {e}")
        return generar_respuesta_simple(texto)

def generar_respuesta_simple(texto):
    """Respuestas básicas"""
    texto = texto.lower()
    
    if 'hola' in texto or 'hi' in texto:
        return "¡Hola! Soy Daqui, tu asistente de joyería. ¿En qué puedo ayudarte?"
    
    if 'anillo' in texto:
        return "Tenemos hermosos anillos. ¿Buscas algo específico?"
    
    if 'collar' in texto:
        return "Nuestros collares son únicos. ¿Prefieres oro o plata?"
    
    if 'precio' in texto:
        return "Los precios van desde S/.150. ¿Qué tipo de joya te interesa?"
    
    return "Gracias por contactarnos. Soy Daqui, ¿en qué puedo ayudarte con nuestras joyas?"

def enviar_whatsapp(numero, mensaje, token, phone_id):
    """Enviar mensaje de WhatsApp"""
    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "text": {"body": mensaje}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Mensaje enviado: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error enviando mensaje: {e}")
        return False