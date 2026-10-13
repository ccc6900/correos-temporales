import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURACIÓN ---
# Reemplaza esto con tu API Key real de SimpleLogin o ponla como variable de entorno
SIMPLELOGIN_API_KEY = "TU_API_KEY_DE_SIMPLELOGIN"
TARGET_URL = "https://tu-pagina-de-prueba.com"

def crear_alias_simplelogin():
    url = "https://app.simplelogin.io/api/alias/random/new"
    headers = {"Authentication": SIMPLELOGIN_API_KEY}
    response = requests.post(url, headers=headers)
    if response.status_code == 201:
        data = response.json()
        print(f"[+] Alias creado: {data['alias']}")
        return data['alias'], data.get('id')
    else:
        raise Exception(f"Error creando alias: {response.text}")

def borrar_alias_simplelogin(alias_id):
    if not alias_id:
        return
    url = f"https://app.simplelogin.io/api/aliases/{alias_id}"
    headers = {"Authentication": SIMPLELOGIN_API_KEY}
    requests.delete(url, headers=headers)
    print("[+] Alias eliminado correctamente de SimpleLogin.")

def main():
    alias, alias_id = crear_alias_simplelogin()
    
    if not os.path.exists("state.json"):
        print("[-] Error: No se encuentra el archivo state.json")
        return
        
    with open("state.json", "r") as f:
        storage_state = json.load(f)

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            # 1. Entrar a la web y registrar el alias
            print(f"[*] Entrando en la web: {TARGET_URL}")
            page.goto(TARGET_URL)
            
            # Ajusta estos selectores según los campos de la web de la prueba
            page.fill("input[type='email']", alias)
            page.click("button:has-text('Obtener prueba')")
            print("[*] Correo enviado. Esperando correo en Proton...")

            # 2. Ir a ProtonMail a leer el correo
            page.goto("https://mail.proton.me/u/1/inbox")
            page.wait_for_timeout(10000)

            correo = page.get_by_text(alias, exact=False)
            if correo.count() > 0:
                correo.first.click()
                page.wait_for_timeout(3000)
                cuerpo = page.locator(".message-content").inner_text()
                print(f"\n--- CONTENIDO DEL CORREO ---\n{cuerpo}\n----------------------------\n")
            else:
                print("[-] No se encontró el correo todavía.")

            input("\nPulsa ENTER para cerrar y limpiar...")
            browser.close()
    finally:
        borrar_alias_simplelogin(alias_id)

if __name__ == "__main__":
    main()
