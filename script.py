import os
import time
import requests
from playwright.sync_api import sync_playwright

SIMPLELOGIN_API_KEY = os.environ.get("SIMPLELOGIN_API_KEY")
TARGET_URL = os.environ.get("TARGET_URL")
PROTON_USER = os.environ.get("PROTON_USER")
PROTON_PASS = os.environ.get("PROTON_PASS")

def crear_alias_simplelogin():
    url = "https://app.simplelogin.io/api/alias/random/new"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    
    print("[*] Contactando con SimpleLogin...")

    # Hacemos hasta 5 intentos con espera progresiva si salta el 429
    for intento in range(1, 6):
        response = requests.post(url, headers=headers)
        print(f"Status Code (Intento {intento}/5): {response.status_code}")
        
        if response.status_code == 201:
            data = response.json()
            print(f"[+] Alias creado con éxito: {data['alias']}")
            return data['alias'], data.get('id')
        elif response.status_code == 429:
            # Si nos bloquea, esperamos 45 segundos antes de reintentar
            espera = intento * 45
            print(f"[-] Rate limit (429) alcanzado. Esperando {espera} segundos para reintentar...")
            time.sleep(espera)
        else:
            print(f"Response: {response.text}")
            time.sleep(10)
            
    raise Exception("[-] SimpleLogin sigue bloqueando la IP de GitHub tras varios intentos.")

def borrar_alias_simplelogin(alias_id):
    if not alias_id:
        return
    url = f"https://app.simplelogin.io/api/aliases/{alias_id}"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    try:
        requests.delete(url, headers=headers)
        print("[+] Alias eliminado correctamente de SimpleLogin.")
    except:
        pass

def main():
    if not PROTON_USER or not PROTON_PASS:
        raise Exception("[-] Faltan las credenciales PROTON_USER o PROTON_PASS.")

    alias, alias_id = crear_alias_simplelogin()

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 1. Registro en la web con el alias de SimpleLogin
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

            # 2. Login en ProtonMail para capturar el correo
            print("[*] Iniciando sesión en ProtonMail...")
            page.goto("https://account.proton.me/login")
            page.wait_for_timeout(4000)

            page.locator("input[id='username'], input[name='username']").fill(PROTON_USER)
            password_field = page.locator("input[id='password'], input[name='password']")
            password_field.fill(PROTON_PASS)
            password_field.press("Enter")
            print("[*] Credenciales enviadas. Esperando buzón...")

            try:
                page.wait_for_url("**/mail**", timeout=30000)
                print("[+] ¡Acceso al buzón confirmado!")
            except:
                page.goto("https://mail.proton.me/u/1/inbox")

            page.wait_for_timeout(6000)
            
            # 3. Lectura del correo entrante
            correo_encontrado = False
            for intento_correo in range(1, 10):
                print(f"[*] Comprobando bandeja (Intento {intento_correo}/9)...")
                
                if "sign-in" in page.title().lower() or "login" in page.url.lower():
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
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
