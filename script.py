import os
import time
import random
import imaplib
import email
import re
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
GMX_USER = os.environ.get("GMX_USER")
GMX_PASS = os.environ.get("GMX_PASS")

# Lista con tus 10 alias oficiales ya creados en GMX
# (Asegúrate de que el dominio @gmx.es o @gmx.com coincida con el tuyo)
DOMINIO_GMX = GMX_USER.split("@")[1]
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

def seleccionar_alias_aleatorio():
    """Selecciona uno de los alias al azar e imprime un aviso destacado"""
    alias_elegido = random.choice(ALIAS_DISPONIBLES)
    print("\n" + "="*50)
    print(f" [O] ALIAS SELECCIONADO PARA ESTA EJECUCIÓN: {alias_elegido}")
    print("="*50 + "\n")
    return alias_elegido

def leer_correo_imap_gmx(user, password, timeout_segundos=120):
    print("[*] Conectando al servidor IMAP de GMX para leer el correo...")
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
                        lista_ids = messages[0].split()
                        ultimo_id = lista_ids[-1]
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
            print(f"[-] Reintentando conexión IMAP: {e}")
        time.sleep(5)
    return None

def main():
    faltantes = []
    if not TARGET_URL: faltantes.append("TARGET_URL")
    if not GMX_USER: faltantes.append("GMX_USER")
    if not GMX_PASS: faltantes.append("GMX_PASS")
    
    if faltantes:
        raise Exception(f"[-] Faltan los siguientes secretos en GitHub: {', '.join(faltantes)}")

    # 1. Seleccionar un alias de la lista precreada
    alias_correo = seleccionar_alias_aleatorio()

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # 2. Registro en la web objetivo con el alias elegido
        print(f"[*] Entrando en la web objetivo: {TARGET_URL}")
        page.goto(TARGET_URL)
        page.wait_for_timeout(4000)

        email_input = page.locator("input[type='email'], input[type='text']").first
        email_input.click()
        email_input.press("Control+A")
        email_input.press("Backspace")
        email_input.fill(alias_correo)
        print(f"[*] Correo introducido con éxito: {alias_correo}")

        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            if (buttons.length > 0) {
                buttons[0].click();
            } else {
                throw new Error('No se encontró el botón');
            }
        }""")
        print("[*] Clic ejecutado en el botón de registro. Esperando correo...")

        # 3. Leer el correo de confirmación por IMAP
        cuerpo_correo = leer_correo_imap_gmx(GMX_USER, GMX_PASS)

        if cuerpo_correo:
            print("[+] ¡Correo de confirmación recibido en GMX!")
            
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

            match_link = re.search(r'https?://[^\s<>"]+(?:verify|confirm|activat)[^\s<>"]*', cuerpo_correo, re.IGNORECASE)
            enlace = match_link.group(0) if match_link else None

            # 4. Introducir el código de verificación
            if codigo:
                print(f"[*] Aplicando código de verificación: {codigo}")
                page.wait_for_timeout(3000)
                
                selector_codigo = "input[type='text'], input[type='number'], input[type='tel'], input[name*='code'], input[id*='code'], input[placeholder*='code']"
                
                try:
                    campo_codigo = page.locator(selector_codigo).first
                    campo_codigo.wait_for(state="visible", timeout=15000)
                    campo_codigo.click()
                    campo_codigo.fill(codigo)
                    page.keyboard.press("Enter")
                except Exception as ex:
                    print(f"[*] Probando introducción carácter a carácter: {ex}")
                    inputs = page.locator("input").all()
                    for idx, char in enumerate(codigo):
                        if idx < len(inputs):
                            inputs[idx].fill(char)
                    page.keyboard.press("Enter")

                page.wait_for_timeout(5000)
            elif enlace:
                print(f"[*] Navegando al enlace de activación: {enlace}")
                page.goto(enlace)
                page.wait_for_timeout(5000)

            url_final = page.url
            print(f"\n==========================================")
            print(f"[ ÉXITO ] Registro completado con el alias: {alias_correo}")
            print(f"[ i ] URL Final: {url_final}")
            print(f"==========================================\n")
        else:
            print("[-] No se recibió el correo de verificación en el tiempo límite.")

        browser.close()

if __name__ == "__main__":
    main()
