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

DOMINIO_GMX = GMX_USER.split("@")[1] if GMX_USER else "gmx.es"

ALIAS_DISPONIBLES = [
    f"alberto.soler@{DOMINIO_GMX}",
    f"lucia.mendez@{DOMINIO_GMX}",
    f"carlos.villar@{DOMINIO_GMX}",
    f"elena.garrido@{DOMINIO_GMX}",
    f"javier.blanco@{DOMINIO_GMX}",
    f"sofia.navarro@{DOMINIO_GMX}",
    f"david.ortega@{DOMINIO_GMX}",
    f"claudia.prieto@{DOMINIO_GMX}",
    f"mateo.iglesias@{DOMINIO_GMX}",
    f"valeria.cruz@{DOMINIO_GMX}"
]

def seleccionar_alias():
    alias = random.choice(ALIAS_DISPONIBLES)
    print(f"\n[*] Alias seleccionado para esta sesión: {alias}\n")
    return alias

def leer_correo_imap(user, password, timeout_segundos=120):
    print("[*] Conectando al IMAP de GMX para recuperar el código...")
    inicio = time.time()
    servidor_imap = "imap.gmx.es" if user.endswith(".es") else "imap.gmx.com"
    carpetas = ["INBOX", "Spam", "Junk"]
    
    while time.time() - inicio < timeout_segundos:
        try:
            mail = imaplib.IMAP4_SSL(servidor_imap, 993)
            mail.login(user, password)
            
            for carpeta in carpetas:
                try:
                    status_folder, _ = mail.select(carpeta)
                    if status_folder != 'OK':
                        continue
                        
                    status, messages = mail.search(None, 'UNSEEN')
                    if status == 'OK' and messages[0]:
                        ultimo_id = messages[0].split()[-1]
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
                except Exception:
                    continue

            mail.logout()
        except Exception as e:
            print(f"[-] Error reconectando IMAP: {e}")
        time.sleep(5)
    return None

def main():
    if not TARGET_URL or not GMX_USER or not GMX_PASS:
        raise Exception("[-] Faltan secretos requeridos (TARGET_URL, GMX_USER, GMX_PASS).")

    alias_correo = seleccionar_alias()

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"[*] Accediendo a: {TARGET_URL}")
        page.goto(TARGET_URL)
        page.wait_for_timeout(4000)

        email_input = page.locator("input[type='email'], input[type='text']").first
        email_input.click()
        email_input.press("Control+A")
        email_input.press("Backspace")
        email_input.fill(alias_correo)
        print(f"[*] Email introducido: {alias_correo}")

        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            if (buttons.length > 0) buttons[0].click();
        }""")
        print("[*] Formulario enviado. Esperando correo de verificación...")

        cuerpo_correo = leer_correo_imap(GMX_USER, GMX_PASS)

        if cuerpo_correo:
            print("[+] Correo recibido con éxito.")
            
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

            match_link = re.search(r'https?://[^\s<>"]+(?:verify|confirm|activat)[^\s<>"]*', cuerpo_correo, re.IGNORECASE)
            enlace = match_link.group(0) if match_link else None

            if codigo:
                print(f"[*] Aplicando código: {codigo}")
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
                page.wait_for_timeout(5000)
            elif enlace:
                print(f"[*] Accediendo al enlace de confirmación: {enlace}")
                page.goto(enlace)
                page.wait_for_timeout(5000)

            url_final = page.url
            print(f"[+] Registro completado. URL obtenida: {url_final}")

            # Generar datos del resultado en JSON
            resultado = {
                "estado": "OK",
                "alias": alias_correo,
                "url_final": url_final,
                "m3u_plus": f"{url_final}/get.php?username={alias_correo}&password=123456&type=m3u_plus",
                "m3u_standard": f"{url_final}/get.php?username={alias_correo}&password=123456&type=m3u",
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            with open("result.json", "w", encoding="utf-8") as f:
                json.dump(resultado, f, indent=4, ensure_ascii=False)
            print("[+] Archivo result.json actualizado.")

        else:
            print("[-] Tiempo de espera agotado sin recibir el correo.")

        browser.close()

if __name__ == "__main__":
    main()
