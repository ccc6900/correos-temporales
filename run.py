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
    "alberto.soler@gmx.es",
    "david.ortega@gmx.es",
    "elena.garrido2@gmx.es",
    "lucia.mendez2@gmx.es",
    "mateo.iglesias@gmx.es",
    "sofia.navarro@gmx.es"
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
    
    if not disponibles:
        print("[!] ¡Se han agotado todos los alias!")
        return None, usados
        
    alias = random.choice(disponibles)
    print(f"\n[+] -> ALIAS SELECCIONADO: {alias}\n")
    return alias, usados

def leer_correo_imap(user, password, timeout_segundos=60):
    print("[*] Conectando al IMAP de GMX...")
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
                if ids:
                    ultimo_id = ids[-1]
                    res, msg_data = mail.fetch(ultimo_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            cuerpo = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() in ["text/plain", "text/html"]:
                                        cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                cuerpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            mail.logout()
                            return cuerpo
            mail.logout()
        except Exception as e:
            print(f"[-] Error IMAP: {e}")
        time.sleep(5)
    return None

def main():
    if not TARGET_URL or not GMX_USER or not GMX_PASS:
        raise Exception("[-] Faltan secretos.")

    usados = cargar_estado()
    alias_correo, _ = seleccionar_alias()

    if not alias_correo:
        resultado = {"estado": "AGOTADO", "mensaje": "¡Todos los alias se han agotado!"}
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

        email_input = page.locator("input[type='email'], input[type='text']").first
        email_input.click()
        email_input.fill(alias_correo)
        
        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            if (buttons.length > 0) buttons[0].click();
        }""")
        print("[*] Esperando correo de verificación...")

        cuerpo_correo = leer_correo_imap(GMX_USER, GMX_PASS)
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
            
            # Esperar a que cargue la pantalla final
            page.wait_for_timeout(10000)

        # DIAGNOSTICO: Imprimir todo el texto visible de la página en los logs de GitHub
        texto_pantalla = page.inner_text("body")
        print("\n--- TEXTO ENCONTRADO EN LA PANTALLA FINAL ---")
        print(texto_pantalla)
        print("----------------------------------------------\n")

        # Intentar buscar enlaces reales con expresiones regulares más amplias
        urls_encontradas = re.findall(r'https?://[^\s<>"]+', texto_pantalla)
        
        m3u_plus = ""
        m3u_standard = ""

        for u in urls_encontradas:
            if "m3u" in u.lower() or "get.php" in u.lower() or "playlist" in u.lower():
                if "plus" in u.lower() or "type=m3u_plus" in u.lower():
                    m3u_plus = u
                elif not m3u_standard:
                    m3u_standard = u

        resultado = {
            "estado": "OK",
            "alias": alias_correo,
            "url_final": page.url,
            "m3u_plus": m3u_plus if m3u_plus else "NO_ENCONTRADO_REVISAR_LOGS",
            "m3u_standard": m3u_standard if m3u_standard else "NO_ENCONTRADO_REVISAR_LOGS",
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=4, ensure_ascii=False)

        browser.close()

if __name__ == "__main__":
    main()
