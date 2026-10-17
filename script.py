import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

# Obtenemos los datos desde las variables de entorno de GitHub
SIMPLELOGIN_API_KEY = os.environ.get("SIMPLELOGIN_API_KEY")
TARGET_URL = os.environ.get("TARGET_URL")
PROTON_STATE_RAW = os.environ.get("PROTON_STATE")

def crear_alias_simplelogin():
    url = "https://app.simplelogin.io/api/alias/random/new"
    headers = {
        "Authentication": f"{SIMPLELOGIN_API_KEY}"
    }
    
    # Hacemos una pausa preventiva de 5 segundos antes de la primera llamada
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
    alias, alias_id = crear_alias_simplelogin()
    
    # Cargar el estado de sesión de Proton
    if PROTON_STATE_RAW:
        storage_state = json.loads(PROTON_STATE_RAW)
    elif os.path.exists("state.json"):
        with open("state.json", "r") as f:
            storage_state = json.load(f)
    else:
        raise Exception("[-] No se encuentra el estado de ProtonMail.")

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            # 1. Entrar a la web
            print(f"[*] Entrando en la web: {TARGET_URL}")
            page.goto(TARGET_URL)
            page.wait_for_timeout(4000)

            # 2. Localizar el campo de correo, borrar el texto por defecto y escribir el alias
            email_input = page.locator("input[type='email'], input[type='text']").first
            email_input.click()
            email_input.press("Control+A")
            email_input.press("Backspace")
            email_input.fill(alias)
            print(f"[*] Correo cambiado con éxito a: {alias}")

            # 3. Clic directo por JavaScript al botón principal
            page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                if (buttons.length > 0) {
                    buttons[0].click();
                } else {
                    throw new Error('No se encontró el botón');
                }
            }""")
            print("[*] Clic ejecutado en el botón principal. Esperando correo en ProtonMail...")

            # 4. Ir a ProtonMail a leer el correo recibido
            page.goto("https://mail.proton.me/u/1/inbox")
            page.wait_for_timeout(12000)

            correo = page.get_by_text(alias, exact=False)
            if correo.count() > 0:
                correo.first.click()
                page.wait_for_timeout(3000)
                cuerpo = page.locator(".message-content").inner_text()
                print(f"\n--- CONTENIDO DEL CORREO ---\n{cuerpo}\n----------------------------\n")
            else:
                print("[-] No se encontró el correo todavía en la bandeja de entrada.")

            browser.close()
    finally:
        # 5. Limpieza del alias en SimpleLogin
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
