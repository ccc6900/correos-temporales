import os
import time
import random
import json
import imaplib
import email
import re
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
GMX_USER = os.environ.get("GMX_USER")
GMX_PASS = os.environ.get("GMX_PASS")

ALIAS_TOTALES = [
    "alicia.morales2@gmx.es",
    "andres.navas@gmx.es",
    "beatriz.robles@gmx.es",
    "diego.pastor2@gmx.es",
    "irene.castello@gmx.es",
    "marcos.solis@gmx.es",
    "natalia.vega2@gmx.es",
    "pablo.cabrera@gmx.es",
    "valeria.guerrero@gmx.es"
]

ARCHIVO_ESTADO = "usados.json"

def cargar_estado():
    if os.path.exists(ARCHIVO_ESTADO):
        try:
            with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_estado(usados):
    with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(usados, f, indent=4, ensure_ascii=False)

def seleccionar_alias():
    usados = cargar_estado()
    disponibles = [a for a in ALIAS_TOTALES if a not in usados]
    
    print(f"[*] Alias ya usados registrados: {usados}")
    print(f"[*] Alias disponibles en este ciclo: {disponibles}")

    if not disponibles:
        print("[!] ¡Atención: Se han agotado todos los alias!")
        return None, usados
        
    alias = random.choice(disponibles)
    print(f"\n[+] -> ALIAS SELECCIONADO PARA ESTA SESIÓN: {alias}\n")
    return alias, usados

def leer_correo_imap_para_alias(user, password, alias_objetivo, timeout_segundos=60):
    print(f"[*] Conectando al IMAP de GMX buscando correo para: {alias_objetivo}...")
    inicio = time.time()
    servidor_imap = "imap.gmx.es" if user.endswith(".es") else "imap.gmx.com"
    
    while time.time() - inicio < timeout_segundos:
        try:
            mail = imaplib.IMAP4_SSL(servidor_imap, 993)
            mail.login(user, password)
            mail.select("INBOX")
            
            status, messages = mail.search(None, 'ALL')
            if status == 'OK' and messages[0]:
                ids = messages[0].split()
                for msg_id in reversed(ids):
                    res, msg_data = mail.fetch(msg_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            destinatario = msg.get("To", "")
                            
                            if alias_objetivo.lower() in destinatario.lower():
                                cuerpo = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() in ["text/plain", "text/html"]:
                                            cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                            break
                                else:
                                    cuerpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                
                                mail.logout()
                                print(f"[+] ¡Correo encontrado y validado para {alias_objetivo}!")
                                return cuerpo
            mail.logout()
        except Exception as e:
            print(f"[-] Error reconectando IMAP: {e}")
        time.sleep(5)
    return None

def extraer_enlaces(texto):
    p_plus, p_std = "", ""
    texto_limpio = texto.replace('%3F', '?').replace('%26', '&').replace('%3D', '=')
    urls = re.findall(r'https?://[^\s<>"\']+', texto_limpio)
    
    for u in urls:
        if "m3u" in u.lower() or "get.php" in u.lower():
            if "plus" in u.lower() or "type=m3u_plus" in u.lower():
                if not p_plus: p_plus = u
            elif "type=m3u" in u.lower() and "plus" not in u.lower():
                if not p_std: p_std = u
            elif not p_std and "plus" not in u.lower():
                p_std = u
    return p_plus, p_std

def main():
    if not TARGET_URL or not GMX_USER or not GMX_PASS:
        raise Exception("[-] Faltan secretos requeridos.")

    usados = cargar_estado()
    alias_correo, _ = seleccionar_alias()

    if not alias_correo:
        resultado = {
            "estado": "AGOTADO",
            "mensaje": "¡Todos los alias de GMX se han agotado!",
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=4, ensure_ascii=False)
        return

    if alias_correo not in usados:
        usados.append(alias_correo)
        guardar_estado(usados)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"[*] Accediendo a: {TARGET_URL}")
        page.goto(TARGET_URL)
        page.wait_for_timeout(4000)

        # SELECCIÓN PRECISA: Buscar el campo de email de forma exacta
        email_input = page.locator("input[type='email'], input[name*='email'], input[placeholder*='correo'], input[placeholder*='email']").first
        if email_input.count() == 0:
            email_input = page.locator("input[type='text']").first

        email_input.click()
        email_input.press("Control+A")
        email_input.press("Backspace")
        email_input.fill(alias_correo)
        
        # VERIFICACIÓN EN LOGS: Comprobar que la web ha registrado el valor exacto
        valor_en_web = email_input.input_value()
        print(f"[*] Verificación input web -> Escrito: '{alias_correo}' | Detectado en campo: '{valor_en_web}'")

        # BUSCAR BOTÓN DE ENVÍO ESPECÍFICO (evitando clics en elementos erróneos)
        submit_btn = page.locator("button[type='submit'], input[type='submit'], button:has-text('Enviar'), button:has-text('Generar'), button:has-text('Continuar'), button:has-text('Registrar')").first
        if submit_btn.count() > 0:
            submit_btn.click()
        else:
            page.keyboard.press("Enter")

        print("[*] Formulario enviado. Esperando correo de verificación específico...")

        cuerpo_correo = leer_correo_imap_para_alias(GMX_USER, GMX_PASS, alias_correo)

        codigo = None
        if cuerpo_correo:
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

        if codigo:
            print(f"[*] Código aplicado: {codigo}")
            page.wait_for_timeout(3000)
            selector_codigo = "input[type='text'], input[type='number'], input[type='tel'], input[name*='code'], input[id*='code']"
            try:
                campo = page.locator(selector_codigo).first
                campo.wait_for(state="visible", timeout=15000)
                campo.fill(codigo)
                page.keyboard.press("Enter")
            except Exception:
                inputs = page.locator("input").all()
                for idx, char in enumerate(codigo):
                    if idx < len(inputs):
                        inputs[idx].fill(char)
                page.keyboard.press("Enter")
            
            try:
                print("[*] Esperando pantalla final (/plan/)...")
                page.wait_for_url("**/plan/**", timeout=15000)
            except Exception:
                page.wait_for_timeout(10000)

        texto_pantalla = page.inner_text("body")
        
        m3u_plus, m3u_standard = extraer_enlaces(texto_pantalla)

        if (not m3u_plus or not m3u_standard) and cuerpo_correo:
            correo_plus, correo_std = extraer_enlaces(cuerpo_correo)
            if not m3u_plus: m3u_plus = correo_plus
            if not m3u_standard: m3u_standard = correo_std

        url_final = page.url

        if not m3u_plus:
            m3u_plus = "NO_ENCONTRADO_REVISAR_LOGS"
        if not m3u_standard:
            m3u_standard = "NO_ENCONTRADO_REVISAR_LOGS"

        resultado = {
            "estado": "OK",
            "alias": alias_correo,
            "url_final": url_final,
            "m3u_plus": m3u_plus,
            "m3u_standard": m3u_standard,
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=4, ensure_ascii=False)
        print("[+] Archivo result.json generado con éxito.")

        browser.close()

if __name__ == "__main__":
    main()
