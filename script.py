import os
import time
import random
import string
import imaplib
import email
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
OUTLOOK_USER = os.environ.get("OUTLOOK_USER")
OUTLOOK_PASS = os.environ.get("OUTLOOK_PASS")

def generar_alias_outlook(email_base):
    usuario, dominio = email_base.split("@")
    sufijo = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{usuario}+{sufijo}@{dominio}"

def leer_correo_imap(user, password, timeout_segundos=60):
    print("[*] Conectando al buzón de Outlook por IMAP para buscar el mensaje...")
    inicio = time.time()
    
    while time.time() - inicio < timeout_segundos:
        try:
            # Conexión segura al servidor IMAP de Outlook
            mail = imaplib.IMAP4_SSL("outlook.office365.com")
            mail.login(user, password)
            mail.select("inbox")
            
            # Buscamos los correos no leídos más recientes
            status, messages = mail.search(None, 'UNSEEN')
            if status == 'OK':
                for num in messages[0].split():
                    res, msg_data = mail.fetch(num, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Extraer el cuerpo del mensaje
                            cuerpo = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    if content_type == "text/plain":
                                        cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                cuerpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                
                            mail.logout()
                            return cuerpo
            mail.logout()
        except Exception as e:
            print(f"[-] Error en la lectura IMAP: {e}")
            
        time.sleep(5)
    return None

def main():
    if not OUTLOOK_USER or not OUTLOOK_PASS:
        raise Exception("[-] Faltan las credenciales OUTLOOK_USER o OUTLOOK_PASS.")

    # Generamos el alias con '+' sobre tu Outlook
    alias = generar_alias_outlook(OUTLOOK_USER)
    print(f"[+] Correo generado para el registro: {alias}")

    # 1. Registro en la web con Playwright
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"[*] Entrando en la web: {TARGET_URL}")
        page.goto(TARGET_URL)
        page.wait_for_timeout(4000)

        email_input = page.locator("input[type='email'], input[type='text']").first
        email_input.click()
        email_input.press("Control+A")
        email_input.press("Backspace")
        email_input.fill(alias)
        print(f"[*] Correo introducido con éxito: {alias}")

        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            if (buttons.length > 0) {
                buttons[0].click();
            } else {
                throw new Error('No se encontró el botón');
            }
        }""")
        print("[*] Clic ejecutado en el botón principal. Esperando correo...")
        browser.close()

    # 2. Leer el correo recibido directamente por IMAP
    contenido = leer_correo_imap(OUTLOOK_USER, OUTLOOK_PASS)
    if contenido:
        print(f"\n--- CONTENIDO DEL CORREO ---\n{contenido}\n----------------------------\n")
    else:
        print("[-] No se recibió ningún correo en el tiempo límite.")

if __name__ == "__main__":
    main()
