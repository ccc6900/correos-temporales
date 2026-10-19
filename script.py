import os
import time
import requests
import imaplib
import email
import re
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
SIMPLELOGIN_API_KEY = os.environ.get("SIMPLELOGIN_API_KEY")
GMX_USER = os.environ.get("GMX_USER")
GMX_PASS = os.environ.get("GMX_PASS")

def crear_alias_simplelogin_limpio():
    """Genera un alias limpio automático en SimpleLogin con reintentos si salta el error 429"""
    url = "https://app.simplelogin.io/api/alias/random/new"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    
    print("[*] Generando alias limpio automático en SimpleLogin...")
    for intento in range(1, 6):
        response = requests.post(url, headers=headers)
        if response.status_code == 201:
            data = response.json()
            print(f"[+] Alias limpio creado con éxito: {data['alias']}")
            return data['alias'], data.get('id')
        elif response.status_code == 429:
            espera = intento * 20
            print(f"[-] Límite de peticiones alcanzado (429). Esperando {espera} segundos para reintentar...")
            time.sleep(espera)
        else:
            print(f"[-] Error en SimpleLogin (Código {response.status_code}): {response.text}")
            time.sleep(5)
            
    raise Exception("[-] No se pudo generar el alias en SimpleLogin tras varios intentos.")

def borrar_alias_simplelogin(alias_id):
    """Borra el alias de SimpleLogin al finalizar para mantener todo limpio"""
    if not alias_id:
        return
    try:
        url = f"https://app.simplelogin.io/api/aliases/{alias_id}"
        requests.delete(url, headers={"Authentication": f"{SIMPLELOGIN_API_KEY}"})
        print("[+] Alias temporal eliminado correctamente de SimpleLogin.")
    except Exception as e:
        print(f"[-] No se pudo borrar el alias de SimpleLogin: {e}")

def leer_correo_imap(user, password, timeout_segundos=60):
    print("[*] Conectando al buzón para leer el correo de confirmación...")
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
    if not SIMPLELOGIN_API_KEY or not GMX_USER or not GMX_PASS:
        raise Exception("[-] Faltan secretos necesarios (SIMPLELOGIN_API_KEY, GMX_USER o GMX_PASS).")

    alias_correo, alias_id = crear_alias_simplelogin_limpio()

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 1. Registro en la web con el alias limpio de SimpleLogin
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

            # 2. Leer el correo que SimpleLogin habrá reenviado a tu bandeja GMX
            cuerpo_correo = leer_correo_imap(GMX_USER, GMX_PASS)

            if cuerpo_correo:
                print("[+] ¡Correo de confirmación recibido a través de SimpleLogin!")
                
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
                print(f"[ ÉXITO ] Registro completado con el alias: {alias_correo}")
                print(f"[ i ] URL Final: {url_final}")
                print(f"==========================================\n")
            else:
                print("[-] No se recibió el correo de verificación en el tiempo límite.")

            browser.close()
    finally:
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
