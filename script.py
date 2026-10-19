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

def generar_nombre_alias():
    """Genera un sufijo aleatorio único para el alias (ej: alfredito_x8k2p1)"""
    usuario = GMX_USER.split("@")[0]
    sufijo = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{usuario}_{sufijo}"

def crear_alias_en_gmx_web(page, nuevo_alias_local):
    """
    Inicia sesión en GMX.es y crea un nuevo alias de correo en la configuración oficial.
    """
    print("[*] Iniciando sesión en GMX para crear un nuevo alias oficial...")
    page.goto("https://www.gmx.es/")
    page.wait_for_timeout(3000)

    # Clic en el botón de login si está presente
    if page.locator("a:has-text('Iniciar sesión'), button:has-text('Iniciar sesión')").is_visible():
        page.locator("a:has-text('Iniciar sesión'), button:has-text('Iniciar sesión')").first.click()
        page.wait_for_timeout(2000)

    # Rellenar credenciales de GMX
    page.locator("input[name='login'], input[type='email']").first.fill(GMX_USER)
    page.locator("input[name='password'], input[type='password']").first.fill(GMX_PASS)
    page.keyboard.press("Enter")
    page.wait_for_timeout(6000)

    print("[*] Navegando a la sección de Configuración de Alias en GMX...")
    # Ir a Ajustes -> Direcciones de e-mail / Alias
    page.goto("https://account.gmx.es/mail/aliases")
    page.wait_for_timeout(4000)

    print(f"[*] Creando alias: {nuevo_alias_local}...")
    # Introducir el nuevo nombre de alias local
    alias_input = page.locator("input[name*='alias'], input[id*='alias'], input[type='text']").first
    alias_input.fill(nuevo_alias_local)
    
    # Hacer clic en guardar / añadir alias
    page.locator("button:has-text('Guardar'), button:has-text('Añadir'), button:has-text('Crear')").first.click()
    page.wait_for_timeout(4000)

    dominio = GMX_USER.split("@")[1]
    correo_completo = f"{nuevo_alias_local}@{dominio}"
    print(f"[+] Alias creado correctamente en GMX: {correo_completo}")
    return correo_completo

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

    nuevo_alias_local = generar_nombre_alias()

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # 1. Crear Alias en GMX mediante automatización web
        try:
            alias_correo = crear_alias_en_gmx_web(page, nuevo_alias_local)
        except Exception as e:
            print(f"[-] No se pudo crear el alias automático en GMX web: {e}")
            print("[*] Usando fallback con sufijo directo...")
            dominio = GMX_USER.split("@")[1]
            alias_correo = f"{nuevo_alias_local}@{dominio}"

        # 2. Registrarse en la web objetivo con el nuevo alias
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

        # 3. Leer el correo mediante IMAP (con las credenciales principales)
        cuerpo_correo = leer_correo_imap_gmx(GMX_USER, GMX_PASS)

        if cuerpo_correo:
            print("[+] ¡Correo de confirmación recibido en la bandeja principal!")
            
            match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
            codigo = match_codigo.group(0) if match_codigo else None

            match_link = re.search(r'https?://[^\s<>"]+(?:verify|confirm|activat)[^\s<>"]*', cuerpo_correo, re.IGNORECASE)
            enlace = match_link.group(0) if match_link else None

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

if __name__ == "__main__":
    main()
