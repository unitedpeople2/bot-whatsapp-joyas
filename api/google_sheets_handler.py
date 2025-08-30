# Reemplaza la función guardar_pedido con esta:

def guardar_pedido(datos_pedido):
    """
    Guarda los datos de un pedido en una nueva fila de la hoja de cálculo.
    'datos_pedido' debe ser un diccionario con los datos.
    """
    gc = init_gspread()
    if not gc:
        return False

    try:
        # Esto ya lo tienes configurado perfectamente
        spreadsheet_name = "Pedidos Bot WhatsApp - Daaqui"
        sh = gc.open(spreadsheet_name).sheet1

        # ### CAMBIO IMPORTANTE ###
        # Ahora preparamos la fila para que coincida EXACTAMENTE con tus 10 columnas
        nueva_fila = [
            datos_pedido.get('fecha', datetime.now().strftime("%Y-%m-%d %H:%M:%S")), # A: Fecha
            datos_pedido.get('nombre_completo', ''),    # B: Nombre
            datos_pedido.get('direccion', ''),          # C: Direccion
            datos_pedido.get('referencia', ''),         # D: Referencia
            datos_pedido.get('distrito', ''),           # E: Destino
            datos_pedido.get('dni', ''),                # F: DNI
            datos_pedido.get('forma_pago', ''),         # G: Forma de pago
            datos_pedido.get('celular', ''),            # H: Celular
            datos_pedido.get('producto_seleccionado', ''), # I: Pedido
            datos_pedido.get('total', '')               # J: Total
        ]
        
        sh.append_row(nueva_fila)
        print(f"Pedido guardado exitosamente en '{spreadsheet_name}'")
        return True
    except Exception as e:
        print(f"Error al guardar en Google Sheets: {e}")
        return False