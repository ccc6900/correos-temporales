import os
import time
import requests
from playwright.sync_api import sync_playwright

# Obtenemos los datos desde las variables de entorno de GitHub
SIMPLELOGIN_API_KEY = os.environ.get("SIMPLELOGIN_API_KEY")
TARGET_URL = os.environ.get("TARGET_URL")
PROTON_USER = os.environ.get("PROTON_USER")
PROTON_PASS = os.environ.get("PROTON_PASS")

def crear_alias_simplelogin():
    url = "https://app.simplelogin.io/api/alias/random/new"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    
    print("[*] Esperando 5 segundos antes de contactar con SimpleLogin...")
    time.sleep(5)

    for intento in range(1, 4):
        response = requests.post(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 201:
            data = response.json()
            print(f"[+] Alias creado: {data['alias']}")
            return data['alias'], data.get('id')
        elif response.status_code == 429:
            print(f"[-] Rate limit de SimpleLogin alcanzado. Esperando 60 segundos (Intento {intento}/3)...")
            time.sleep(60)
        else:
            raise Exception(f"Error creando alias: {response.text}")
            
    raise Exception("[-] Demasiadas peticiones a SimpleLogin. Rate limit persistente.")

def borrar_alias_simplelogin(alias_id):
    if not alias_id:
        return
    url = f"https://app.simplelogin.io/api/aliases/{alias_id}"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    requests.delete(url, headers=headers)
    print("[+] Alias eliminado correctamente de SimpleLogin.")

def main():
    if not PROTON_USER or not PROTON_PASS:
        raise Exception("[-] Faltan las credenciales PROTON_USER o PROTON_PASS en las variables de entorno.")

    alias, alias_id = crear_alias_simplelogin()

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 1. Entrar a la web objetivo y registrar el alias
            print(f"[*] Entrando en la web: {TARGET_URL}")
            page.goto(TARGET_URL)
            page.wait_for_timeout(4000)

            email_input = page.locator("input[type='email'], input[type='text']").first
            email_input.click()
            email_input.press("Control+A")
            email_input.press("Backspace")
            email_input.fill(alias)
            print(f"[*] Correo cambiado con éxito a: {alias}")

            page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                if (buttons.length > 0) {
                    buttons[0].click();
                } else {
                    throw new Error('No se encontró el botón');
                }
            }""")
            print("[*] Clic ejecutado en el botón principal.")

            # 2. Iniciar sesión automáticamente en ProtonMail de forma robusta
            print("[*] Iniciando sesión en ProtonMail...")
            page.goto("https://account.proton.me/login")
            page.wait_for_timeout(4000)

            # Rellenar usuario, contraseña y presionar Enter
            page.locator("input[id='username'], input[name='username']").fill(PROTON_USER)
            password_field = page.locator("input[id='password'], input[name='password']")
            password_field.fill(PROTON_PASS)
            
            # Pulsamos Enter en el campo de contraseña para forzar el envío del formulario
            password_field.press("Enter")
            print("[*] Credenciales enviadas con Enter. Esperando acceso al buzón...")

            # Esperamos a que la URL cambie al buzón de correo
            try:
                page.wait_for_url("**/mail**", timeout=30000)
                print("[+] ¡Acceso al buzón de Proton confirmado por URL!")
            except:
                print("[-] No redirigió automáticamente por URL, forzando navegación al inbox...")
                page.goto("https://mail.proton.me/u/1/inbox")

            page.wait_for_timeout(6000)
            
            # 3. Buscar el correo de confirmación asegurándonos de que ya no estamos en la página de login
            correo_encontrado = False
            for intento_correo in range(1, 10):
                print(f"[*] Comprobando bandeja de ProtonMail (Intento {intento_correo}/9)...")
                
                # Verificación extra: si por algún motivo seguimos en el login, saltamos este intento
                current_title = page.title().lower()
                if "sign-in" in current_title or "login" in page.url.lower():
                    print("[-] Seguimos en la pantalla de login, esperando redirección...")
                    page.wait_for_timeout(5000)
                    continue

                clicked = page.evaluate("""() => {
                    const items = document.querySelectorAll('div[class*="item"], div[role="row"], .item-row');
                    for (let item of items) {
                        if (item.innerText && item.innerText.length > 5 && item.clientHeight > 15) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                
                if clicked:
                    print("[+] ¡Mensaje detectado y abierto con éxito!")
                    page.wait_for_timeout(4000)
                    
                    try:
                        cuerpo = page.locator(".message-content").inner_text()
                    except:
                        cuerpo = page.inner_text("body")
                        
                    print(f"\n--- CONTENIDO DEL CORREO ---\n{cuerpo}\n----------------------------\n")
                    correo_encontrado = True
                    break
                
                page.wait_for_timeout(5000)

            if not correo_encontrado:
                print("[-] No se encontró ningún correo nuevo en el tiempo límite.")

            browser.close()
    finally:
        # 4. Limpieza del alias en SimpleLogin
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
