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

            # 4. Ir a ProtonMail y comprobar estado
            page.goto("https://mail.proton.me/u/1/inbox")
            page.wait_for_timeout(6000)
            
            print(f"[*] URL actual en navegador: {page.url}")
            print(f"[*] Título de la página: {page.title()}")
            
            correo_encontrado = False
            for intento_correo in range(1, 10):
                print(f"[*] Comprobando bandeja de ProtonMail (Intento {intento_correo}/9)...")
                
                # Búsqueda ampliada mediante JS para detectar cualquier elemento interactivo en la lista
                clicked = page.evaluate("""() => {
                    // Buscamos filas, contenedores o elementos de lista genéricos en Proton
                    const items = document.querySelectorAll('div[class*="item"], div[role="row"], article, li');
                    for (let item of items) {
                        // Filtramos elementos que parezcan filas de correo (que tengan un tamaño razonable y texto)
                        if (item.innerText && item.innerText.length > 5 && (item.clientHeight > 20 || item.getBoundingClientRect().height > 20)) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                
                if clicked:
                    print("[+] ¡Elemento de correo detectado y abierto con éxito!")
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
        # 5. Limpieza del alias en SimpleLogin
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
