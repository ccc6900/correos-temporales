import os
import time
import random
import string
import imaplib
import email
import re
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
GMX_USER = os.environ.get("GMX_USER")
GMX_PASS = os.environ.get("GMX_PASS")

def generar_alias_gmx(email_base):
    # Genera un alias sin usar el '+' si prefieres, o con subdirección
    usuario, dominio = email_base.split("@")
    sufijo = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{usuario}+{sufijo}@{dominio}"

def leer_correo_imap_gmx(user, password, timeout_segundos=60):
    print("[*] Conectando al servidor IMAP de GMX...")
    inicio = time.time()
    
    while time.time() - inicio < timeout_segundos:
        try:
            # Servidor IMAP oficial de GMX
            mail = imaplib.IMAP4_SSL("imap.gmx.com", 993)
            mail.login(user, password)
            mail.select("INBOX")
            
            # Buscar correos no leídos
            status, messages = mail.search(None, 'UNSEEN')
            if status == 'OK' and messages[0]:
                lista_ids = messages[0].split()
                # Tomar el último correo recibido
                ultimo_id = lista_ids[-1]
                res, msg_data = mail.fetch(ultimo_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        cuerpo = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if content_type in ["text/plain", "text/html"]:
                                    cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                        else:
                            cuerpo = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
                        mail.logout()
                        return cuerpo
            mail.logout()
        except Exception as e:
            print(f"[-] Reintentando conexión IMAP: {e}")
            
        time.sleep(5)
    return None

def main():
    if not GMX_USER or not GMX_PASS:
        raise Exception("[-] Faltan las credenciales GMX_USER o GMX_PASS.")

    correo_registro = generar_alias_gmx(GMX_USER)
    print(f"[+] Correo generado para el registro: {correo_registro}")

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # 1. Registro en la web
        print(f"[*] Entrando en la web objetivo: {TARGET_URL}")
        page.goto(TARGET_URL)
        page.wait_for_timeout(4000)

        email_input = page.locator("input[type='email'], input[type='text']").first
        email_input.click()
        email_input.press("Control+A")
        email_input.press("Backspace")
        email_input.fill(correo_registro)
        print(f"[*] Correo introducido con éxito: {correo_registro}")

        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            if (buttons.length > 0) {
                buttons[0].click();
            } else {
                throw new Error('No se encontró el botón');
            }
        }""")
        print("[*] Clic ejecutado en el botón de registro. Esperando correo...")

        # 2. Leer el correo mediante IMAP
        cuerpo_correo = leer_correo_imap_gmx(GMX_USER, GMX_PASS)

        if cuerpo_correo:
            print("[+] ¡Correo de confirmación recibido con éxito!")
            
            # Buscar código numérico de 4 a 6 dígitos
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

            # Buscar enlaces de activación
            match_link = re.search(r'https?://[^\s<>"]+(?:verify|confirm|activat)[^\s<>"]*', cuerpo_correo, re.IGNORECASE)
            enlace = match_link.group(0) if match_link else None

            # 3. Aplicar la verificación en la página web
            if codigo:
                print(f"[*] Aplicando código de verificación: {codigo}")
                code_input = page.locator("input[type='text'], input[name*='code'], input[id*='code']").first
                code_input.fill(codigo)
                page.keyboard.press("Enter")
                page.wait_for_timeout(5000)
            elif enlace:
                print(f"[*] Navegando al enlace de activación: {enlace}")
                page.goto(enlace)
                page.wait_for_timeout(5000)

            # Devolver el enlace final obtenido
            url_final = page.url
            print(f"\n==========================================")
            print(f"[ ÉXITO ] Registro completado con éxito.")
            print(f"[ i ] URL Final: {url_final}")
            print(f"==========================================\n")
        else:
            print("[-] No se recibió el correo de verificación en el tiempo límite.")

        browser.close()

if __name__ == "__main__":
    main()
