# -*- coding: utf-8 -*-
# ==========================================================
# BOT DAAQUI - LÓGICA DE CONVERSACIÓN
# Contiene el flujo principal de la venta.
# ==========================================================
import time
from firebase_admin import firestore
from bot_utils import (
    send_text_message, send_image_message, save_session, delete_session,
    find_product_by_keywords, normalize_and_check_district, parse_province_district,
    get_last_question, save_completed_sale_and_customer, guardar_pedido_en_sheet,
    get_delivery_day_message
)

# ==============================================================================
# 6. LÓGICA DE LA CONVERSACIÓN - ETAPA 1 (EMBUDO DE VENTAS)
# ==============================================================================
def handle_initial_message(from_number, user_name, text, FAQ_KEYWORD_MAP, FAQ_RESPONSES, KEYWORDS_GIRASOL):
    product_id, product_data = find_product_by_keywords(text, KEYWORDS_GIRASOL)
    if product_data:
        nombre_producto = product_data.get('nombre', 'nuestro producto')
        desc_corta = product_data.get('descripcion_corta', 'es simplemente increíble.')
        precio = product_data.get('precio_base', 0)
        url_img = product_data.get('imagenes', {}).get('principal')
        
        if url_img:
            send_image_message(from_number, url_img)
            time.sleep(1)
        
        msg = (f"¡Hola {user_name}! 🌞 El *{nombre_producto}* {desc_corta}\n\n"
               f"Por campaña, llévatelo a *S/ {precio:.2f}* (¡incluye envío gratis a todo el Perú! 🚚).\n\n"
               "Cuéntame, ¿es un tesoro para ti o un regalo para alguien especial?")
        send_text_message(from_number, msg)
        
        new_session = {
            "state": "awaiting_occasion_response", "product_id": product_id,
            "product_name": nombre_producto, "product_price": float(precio),
            "user_name": user_name, "whatsapp_id": from_number, "is_upsell": False
        }
        save_session(from_number, new_session)
        return

    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            if response_text := FAQ_RESPONSES.get(key):
                send_text_message(from_number, response_text)
                return
    
    send_text_message(from_number, f"¡Hola {user_name}! 👋🏽✨ Bienvenida a *Daaqui Joyas*. Si deseas información sobre nuestro *Collar Mágico Girasol Radiant*, solo pregunta por él. 😊")

# ==============================================================================
# 7. LÓGICA DE LA CONVERSACIÓN - ETAPA 2 (FLUJO DE COMPRA)
# ==============================================================================
def handle_sales_flow(from_number, text, session, FAQ_KEYWORD_MAP, FAQ_RESPONSES, KEYWORDS_GIRASOL, BUSINESS_RULES, RUC_EMPRESA, TITULAR_YAPE, ADMIN_WHATSAPP_NUMBER):
    db = firestore.client()
    text_lower = text.lower()
    for key, keywords in FAQ_KEYWORD_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            response_text = FAQ_RESPONSES.get(key)
            if key == 'precio' and session.get('product_name'):
                response_text = f"¡Claro! El precio de tu pedido (*{session['product_name']}*) es de *S/ {session['product_price']:.2f}*, con envío gratis. 🚚"
            elif key == 'stock' and session.get('product_name'):
                response_text = f"¡Sí, claro! Aún tenemos unidades del *{session['product_name']}*. ✨ ¿Iniciamos tu pedido?"
            
            if response_text:
                send_text_message(from_number, response_text)
                time.sleep(1)
                if last_question := get_last_question(session.get('state')):
                    send_text_message(from_number, f"¡Espero haber aclarado tu duda! 😊 Continuando...\n\n{last_question}")
                return

    if any(keyword in text.lower() for keyword in KEYWORDS_GIRASOL) and session.get('state') not in ['awaiting_occasion_response', 'awaiting_purchase_decision']:
        delete_session(from_number)
        handle_initial_message(from_number, session.get("user_name", "Usuario"), text, FAQ_KEYWORD_MAP, FAQ_RESPONSES, KEYWORDS_GIRASOL)
        return

    current_state, product_id = session.get('state'), session.get('product_id')
    if not product_id or not (product_doc := db.collection('productos').document(product_id).get()).exists:
        send_text_message(from_number, "Lo siento, este producto ya no está disponible. Por favor, empieza de nuevo.")
        delete_session(from_number)
        return
    product_data = product_doc.to_dict()

    if current_state == 'awaiting_occasion_response':
        url_imagen_empaque = product_data.get('imagenes', {}).get('empaque')
        detalles = product_data.get('detalles', {})
        material = detalles.get('material', 'material de alta calidad')
        presentacion = detalles.get('empaque', 'viene en una hermosa caja de regalo')
        if url_imagen_empaque:
            send_image_message(from_number, url_imagen_empaque)
            time.sleep(1)
        mensaje_persuasion_1 = (
            "¡Maravillosa elección! ✨ El *Collar Mágico Girasol Radiant* es pura energía. Aquí tienes todos los detalles:\n\n"
            f"💎 *Material:* {material} ¡Hipoalergénico y no se oscurece!\n"
            f"🔮 *La Magia:* Su piedra central es termocromática, cambia de color con tu temperatura.\n"
            f"🎁 *Presentación:* {presentacion}"
        )
        send_text_message(from_number, mensaje_persuasion_1)
        time.sleep(1.5)
        mensaje_persuasion_2 = (
            f"Para tu total seguridad, somos Daaqui Joyas, un negocio formal con *RUC {RUC_EMPRESA}*. ¡Tu compra es 100% segura! 🇵🇪\n\n"
            "¿Te gustaría coordinar tu pedido ahora para asegurar el tuyo? (Sí/No)"
        )
        send_text_message(from_number, mensaje_persuasion_2)
        session['state'] = 'awaiting_purchase_decision'
        save_session(from_number, session)
    
    elif current_state == 'awaiting_purchase_decision':
        if 'si' in text.lower() or 'sí' in text.lower():
            url_imagen_upsell = product_data.get('imagenes', {}).get('upsell')
            if url_imagen_upsell:
                send_image_message(from_number, url_imagen_upsell)
                time.sleep(1)
            upsell_message_1 = (
                "¡Excelente elección! Pero espera... por decidir llevar tu collar, ¡acabas de desbloquear una oferta exclusiva! ✨\n\n"
                "Añade un segundo Collar Mágico y te incluimos de regalo dos cadenas de diseño italiano.\n\n"
                "Tu pedido se ampliaría a:\n"
                "✨ 2 Collares Mágicos\n🎁 2 Cadenas de Regalo\n🎀 2 Cajitas Premium\n"
                "💎 Todo por un único pago de S/ 99.00"
            )
            send_text_message(from_number, upsell_message_1)
            time.sleep(1.5)
            upsell_message_2 = (
                "Para continuar, por favor, respóndeme:\n"
                "👉🏽 Escribe *oferta* para ampliar tu pedido.\n"
                "👉🏽 Escribe *continuar* para llevar solo un collar."
            )
            send_text_message(from_number, upsell_message_2)
            session['state'] = 'awaiting_upsell_decision'
            save_session(from_number, session)
        else:
            delete_session(from_number)
            send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré. ¡Que tengas un buen día! 😊")

    elif current_state == 'awaiting_upsell_decision':
        if 'oferta' in text.lower():
            session.update({"product_name": "Oferta 2x Collares Mágicos + Cadenas", "product_price": 99.00, "is_upsell": True})
            send_text_message(from_number, "¡Genial! Has elegido la oferta. ✨")
        else: 
            session['is_upsell'] = False
            send_text_message(from_number, "¡Perfecto! Continuamos con tu collar individual. ✨")
        session['state'] = 'awaiting_location'
        save_session(from_number, session)
        time.sleep(1)
        send_text_message(from_number, "Para empezar a coordinar el envío, por favor, dime: ¿eres de *Lima* o de *provincia*?")

    elif current_state == 'awaiting_location':
        if 'lima' in text.lower():
            session.update({"state": "awaiting_lima_district", "provincia": "Lima"})
            save_session(from_number, session)
            send_text_message(from_number, "¡Genial! ✨ Para saber qué tipo de envío te corresponde, por favor, dime: ¿en qué distrito te encuentras? 📍")
        elif 'provincia' in text.lower():
            session['state'] = 'awaiting_province_district'
            save_session(from_number, session)
            send_text_message(from_number, "¡Entendido! Para continuar, indícame tu *provincia y distrito*. ✍🏽\n\n📝 *Ej: Arequipa, Arequipa*")
        else:
            send_text_message(from_number, "No te entendí bien. Por favor, dime si tu envío es para *Lima* o para *provincia*.")
    
    elif current_state == 'awaiting_province_district':
        provincia, distrito = parse_province_district(text)
        session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Provincia Shalom", "metodo_pago": "Adelanto y Saldo (Yape/Plin)", "provincia": provincia, "distrito": distrito})
        save_session(from_number, session)
        adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
        mensaje = (f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}* como compromiso de recojo. 🤝\n\n"
                   "¿Estás de acuerdo? (Sí/No)")
        send_text_message(from_number, mensaje)
        
    elif current_state == 'awaiting_lima_district':
        distrito, status = normalize_and_check_district(text, BUSINESS_RULES)
        if status != 'NO_ENCONTRADO':
            session['distrito'] = distrito
            if status == 'CON_COBERTURA':
                session.update({"state": "awaiting_delivery_details", "tipo_envio": "Lima Contra Entrega", "metodo_pago": "Contra Entrega (Efectivo/Yape/Plin)"})
                save_session(from_number, session)
                mensaje = (f"¡Excelente! Tenemos cobertura en *{distrito}*. 🏙️\n\n"
                           "Para registrar tu pedido, envíame en *un solo mensaje* tu *Nombre Completo, Dirección exacta* y una *Referencia*.\n\n"
                           "📝 *Ej: Ana Pérez, Jr. Gamarra 123, Depto 501, La Victoria. Al lado de la farmacia.*")
                send_text_message(from_number, mensaje)
            elif status == 'SIN_COBERTURA':
                session.update({"state": "awaiting_shalom_agreement", "tipo_envio": "Lima Shalom", "metodo_pago": "Adelanto y Saldo (Yape/Plin)"})
                save_session(from_number, session)
                adelanto = BUSINESS_RULES.get('adelanto_shalom', 20)
                mensaje = (f"Entendido. ✅ Para *{distrito}*, los envíos son por agencia *Shalom* y requieren un adelanto de *S/ {adelanto:.2f}* como compromiso de recojo. 🤝\n\n"
                           "¿Estás de acuerdo? (Sí/No)")
                send_text_message(from_number, mensaje)
        else:
            send_text_message(from_number, "No pude reconocer ese distrito. Por favor, intenta escribirlo de nuevo.")

    elif current_state in ['awaiting_delivery_details', 'awaiting_shalom_details']:
        session.update({"state": "awaiting_final_confirmation", "detalles_cliente": text})
        save_session(from_number, session)
        resumen = ("¡Gracias! Revisa que todo esté correcto:\n\n"
                   "*Resumen del Pedido*\n"
                   f"💎 {session.get('product_name', '')}\n"
                   f"💵 Total: S/ {session.get('product_price', 0):.2f}\n"
                   f"🚚 Envío: {session.get('distrito', session.get('provincia', ''))} - ¡Gratis!\n"
                   f"💳 Pago: {session.get('metodo_pago', '')}\n\n"
                   "*Datos de Entrega*\n"
                   f"{session.get('detalles_cliente', '')}\n\n"
                   "¿Confirmas que todo es correcto? (Sí/No)")
        send_text_message(from_number, resumen)

    elif current_state == 'awaiting_shalom_agreement':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_experience'
            save_session(from_number, session)
            send_text_message(from_number, "¡Genial! Para hacer el proceso más fácil, cuéntame: ¿alguna vez has recogido un pedido en una agencia Shalom? 🙋🏽‍♀️ (Sí/No)")
        else:
            delete_session(from_number); send_text_message(from_number, "Comprendo. Si cambias de opinión, aquí estaré. ¡Gracias! 😊")

    elif current_state == 'awaiting_shalom_experience':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_details'
            save_session(from_number, session)
            mensaje = ("¡Excelente! Entonces ya conoces el proceso. ✅\n\n"
                       "Para terminar, bríndame en un solo mensaje tu *Nombre Completo, DNI* y la *dirección exacta de la agencia Shalom* donde recogerás. ✍🏽")
            send_text_message(from_number, mensaje)
        else:
            session['state'] = 'awaiting_shalom_agency_knowledge'
            save_session(from_number, session)
            mensaje = ("¡No te preocupes! Te explico: Shalom es una empresa de envíos. Te damos un código de seguimiento, y cuando tu pedido llega a la agencia, nos yapeas el saldo restante. Apenas confirmemos, te damos la clave secreta para el recojo. ¡Es 100% seguro! 🔒\n\n"
                       "¿Conoces la dirección de alguna agencia Shalom cerca a ti? (Sí/No)")
            send_text_message(from_number, mensaje)
            
    elif current_state == 'awaiting_shalom_agency_knowledge':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_shalom_details'
            save_session(from_number, session)
            mensaje = ("¡Perfecto! Por favor, bríndame en un solo mensaje tu *Nombre Completo, DNI* y la *dirección de esa agencia Shalom*. ✍🏽")
            send_text_message(from_number, mensaje)
        else:
            delete_session(from_number); send_text_message(from_number, "Entiendo. 😔 Te recomiendo buscar en Google 'Shalom agencias' para encontrar la más cercana. ¡Gracias por tu interés!")
            
    elif current_state == 'awaiting_final_confirmation':
        if 'si' in text.lower() or 'sí' in text.lower():
            if session.get('tipo_envio') == 'Lima Contra Entrega':
                adelanto = float(BUSINESS_RULES.get('adelanto_lima_delivery', 10))
                session.update({'adelanto': adelanto, 'state': 'awaiting_lima_payment_agreement'})
                save_session(from_number, session)
                mensaje = (f"¡Perfecto! ✅ Como último paso, solicitamos un adelanto de *S/ {adelanto:.2f}* para confirmar el compromiso de recojo. 🤝 Este monto se descuenta del total, por supuesto.\n\n"
                           "¿Procedemos? (Sí/No)")
                send_text_message(from_number, mensaje)
            else: # Shalom
                adelanto = float(BUSINESS_RULES.get('adelanto_shalom', 20))
                session.update({'adelanto': adelanto, 'state': 'awaiting_shalom_payment'})
                save_session(from_number, session)
                mensaje = (f"¡Genial! Puedes realizar el adelanto de *S/ {adelanto:.2f}* a nuestra cuenta:\n\n"
                           f"💳 *YAPE / PLIN:* {BUSINESS_RULES.get('yape_numero', 'No configurado')}\n"
                           f"👤 *Titular:* {TITULAR_YAPE}\n"
                           f"🔒 Tu compra es 100% segura (*RUC {RUC_EMPRESA}*).\n\n"
                           "Una vez realizado, envíame la *captura de pantalla* para validar tu pedido.")
                send_text_message(from_number, mensaje)
        else:
            previous_state = 'awaiting_delivery_details' if session.get('tipo_envio') == 'Lima Contra Entrega' else 'awaiting_shalom_details'
            session['state'] = previous_state
            save_session(from_number, session)
            send_text_message(from_number, "¡Claro, lo corregimos! 😊 Por favor, envíame nuevamente la información de envío completa en un solo mensaje.")

    elif current_state == 'awaiting_lima_payment_agreement':
        if 'si' in text.lower() or 'sí' in text.lower():
            session['state'] = 'awaiting_lima_payment'
            save_session(from_number, session)
            mensaje = (f"¡Genial! Puedes realizar el adelanto de *S/ {session.get('adelanto', 10):.2f}* a:\n\n"
                       f"💳 *YAPE / PLIN:* {BUSINESS_RULES.get('yape_numero', 'No configurado')}\n"
                       f"👤 *Titular:* {TITULAR_YAPE}\n\n"
                       "Una vez realizado, envíame la *captura de pantalla* para validar.")
            send_text_message(from_number, mensaje)
        else:
            delete_session(from_number); send_text_message(from_number, "Entendido. Si cambias de opinión, aquí estaré. ¡Gracias!")

    elif current_state in ['awaiting_lima_payment', 'awaiting_shalom_payment']:
        if text == "COMPROBANTE_RECIBIDO":
            guardado_exitoso, sale_data = save_completed_sale_and_customer(session)
            if guardado_exitoso:
                guardar_pedido_en_sheet(sale_data)
                if ADMIN_WHATSAPP_NUMBER:
                    admin_message = (f"🎉 ¡Nueva Venta Confirmada! 🎉\n\n"
                                     f"Producto: {sale_data.get('producto_nombre')}\n"
                                     f"Tipo: {sale_data.get('tipo_envio')}\n"
                                     f"Cliente WA ID: {sale_data.get('cliente_id')}\n"
                                     f"Detalles:\n{sale_data.get('detalles_cliente')}")
                    send_text_message(ADMIN_WHATSAPP_NUMBER, admin_message)
                if session.get('tipo_envio') == 'Lima Contra Entrega':
                    restante = sale_data.get('saldo_restante', 0)
                    dia_entrega = get_delivery_day_message(BUSINESS_RULES)
                    horario = BUSINESS_RULES.get('horario_entrega_lima', 'durante el día')
                    mensaje_final = (f"¡Adelanto confirmado! ✨ Tu pedido ha sido agendado. Lo recibirás *{dia_entrega}* entre *{horario}*.\n\n"
                                     f"💵 Pagarás al recibir: *S/ {restante:.2f}*.\n\n"
                                     "¡Gracias por tu compra! 🎉")
                    send_text_message(from_number, mensaje_final)
                else: # Shalom
                    mensaje_base = "¡Adelanto confirmado! ✨ Agendamos tu envío. Te enviaremos tu código de seguimiento por aquí en las próximas 24h hábiles. "
                    if session.get('tipo_envio') == 'Lima Shalom': msg_final = mensaje_base + "El tiempo de entrega en agencia es de 1-2 días hábiles."
                    else: msg_final = mensaje_base + "El tiempo de entrega en agencia es de 3-5 días hábiles."
                    send_text_message(from_number, msg_final)
                delete_session(from_number)
            else:
                send_text_message(from_number, "¡Uy! Hubo un problema al registrar tu pedido. Un asesor se pondrá en contacto contigo.")
        else:
            send_text_message(from_number, "Estoy esperando la *captura de pantalla* de tu pago. 😊")
    else:
        send_text_message(from_number, "Estoy un poco confundido. Si deseas reiniciar, escribe 'cancelar'.")