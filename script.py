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

def generar_correo_limpio_con_puntos(email_base):
    """
    Genera una variante única y limpia con puntos aleatorios (ej: a.lfredito25@gmx.es).
    No usa el signo '+' y es 100% aceptada por cualquier página web.
    """
    usuario, dominio = email_base.split("@")
    letras = list(usuario)
    nueva_cadena = [letras[0]]
    
    for letra in letras[1:]:
        if random.choice([True, False]):
            nueva_cadena.append('.')
        nueva_cadena.append(letra)
        
    correo_generado = "".join(nueva_cadena) + "@" + dominio
    print(f"[+] Correo limpio generado para esta ejecución: {correo_generado}")
    return correo_generado

def leer_correo_imap_gmx(user, password, timeout_segundos=60):
    print("[*] Conectando al servidor IMAP de GMX...")
    inicio = time.time()
    servidor_imap = "imap.gmx.es" if user.endswith(".es") else "imap.gmx.com"
    
    while time.time() - inicio < timeout_segundos:
        try:
            mail = imaplib.IMAP4_SSL(servidor_imap, 993)
            mail.login(user, password)
            mail.select("INBOX")
            
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

    correo_registro = generar_correo_limpio_con_puntos(GMX_USER)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # 1. Registro en la web con el correo único de GMX
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

        # 2. Leer el correo de confirmación directamente por IMAP en GMX
        cuerpo_correo = leer_correo_imap_gmx(GMX_USER, GMX_PASS)

        if cuerpo_correo:
            print("[+] ¡Correo de confirmación recibido en GMX!")
            
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

            match_link = re.search(r'https?://[^\s<>"]+(?:verify|confirm|activat)[^\s<>"]*', cuerpo_correo, re.IGNORECASE)
            enlace = match_link.group(0) if match_link else None

            # 3. Aplicar la verificación en la web
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

            url_final = page.url
            print(f"\n==========================================")
            print(f"[ ÉXITO ] Registro completado con el correo: {correo_registro}")
            print(f"[ i ] URL Final: {url_final}")
            print(f"==========================================\n")
        else:
            print("[-] No se recibió el correo de verificación en el tiempo límite.")

        browser.close()

if __name__ == "__main__":
    main()
