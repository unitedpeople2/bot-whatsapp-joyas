import os
import json
import requests

def handler(event, context):
    """Función handler para Vercel"""
    
    # Variables de entorno
    ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    VERIFY_TOKEN = os.environ.get("WHATSAPP_WEBHOOK_SECRET")
    
    # Configurar Google AI
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GOOGLE_AI_API_KEY"))
        google_ai_available = True
    except:
        google_ai_available = False
    
    # Obtener método HTTP
    method = event.get('httpMethod', 'GET')
    
    # GET - Verificación del webhook
    if method == 'GET':
        query_params = event.get('queryStringParameters', {}) or {}
        mode = query_params.get('hub.mode')
        token = query_params.get('hub.verify_token')
        challenge = query_params.get('hub.challenge')
        
        print(f"Verificación: mode={mode}, token={token}")
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return {
                'statusCode': 200,
                'body': challenge
            }
        else:
            return {
                'statusCode': 403,
                'body': 'Forbidden'
            }
    
    # POST - Procesar mensaje
    if method == 'POST':
        try:
            body = json.loads(event.get('body', '{}'))
            
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
                    
                    if text and from_number:
                        # Generar respuesta
                        if google_ai_available:
                            response_text = generar_respuesta_ai(text)
                        else:
                            response_text = generar_respuesta_simple(text)
                        
                        # Enviar mensaje
                        enviar_whatsapp(from_number, response_text, ACCESS_TOKEN, PHONE_NUMBER_ID)
            
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'success'})
            }
            
        except Exception as e:
            print(f"Error: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }
    
    return {
        'statusCode': 405,
        'body': json.dumps({'error': 'Method not allowed'})
    }

def generar_respuesta_ai(texto):
    """Generar respuesta con Google AI"""
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""Eres 'Daqui', asistente de joyería fina en Perú. 
        Responde de forma amable y profesional a: {texto}"""
        
        response = model.generate_content(prompt)
        return response.text
    except:
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
        print(f"Mensaje enviado: {response.status_code}")
    except Exception as e:
        print(f"Error enviando: {e}")

# Para compatibilidad con diferentes formatos de Vercel
def main(request):
    """Función alternativa"""
    return handler(request, None)

# Export default para Vercel
default = handler