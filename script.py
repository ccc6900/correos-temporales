import os
import time
import random
import string
import re
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
OUTLOOK_USER = os.environ.get("OUTLOOK_USER")
OUTLOOK_PASS = os.environ.get("OUTLOOK_PASS")

def generar_nombre_aleatorio():
    return "user_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def main():
    if not OUTLOOK_USER or not OUTLOOK_PASS:
        raise Exception("[-] Faltan las credenciales OUTLOOK_USER o OUTLOOK_PASS en los secretos.")

    nuevo_alias_local = generar_nombre_aleatorio()
    dominio_outlook = OUTLOOK_USER.split("@")[1]
    correo_alias = f"{nuevo_alias_local}@{dominio_outlook}"
    
    print(f"[+] Alias limpio generado para Hotmail: {correo_alias}")

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # -------------------------------------------------------------
            # PASO 1: Crear el alias automáticamente en Hotmail
            # -------------------------------------------------------------
            print("[*] Iniciando sesión en Microsoft para añadir el alias limpio...")
            page.goto("https://account.live.com/names/manage")
            page.wait_for_timeout(4000)

            if page.locator("input[name='loginfmt']").is_visible():
                page.locator("input[name='loginfmt']").fill(OUTLOOK_USER)
                page.locator("input[id='idSIButton9']").click()
                page.wait_for_timeout(4000)
            
            if page.locator("input[name='passwd']").is_visible():
                page.locator("input[name='passwd']").fill(OUTLOOK_PASS)
                page.locator("input[id='idSIButton9']").click()
                page.wait_for_timeout(5000)
                
            if page.locator("input[id='idSIButton9']").is_visible():
                page.locator("input[id='idSIButton9']").click()
                page.wait_for_timeout(6000)

            print("[*] Añadiendo alias a la cuenta...")
            page.goto("https://account.live.com/addassocid")
            page.wait_for_timeout(4000)
            
            input_alias = page.locator("input[name='iNewAccountAlias'], input[id='iNewAccountAlias']").first
            input_alias.fill(nuevo_alias_local)
            
            page.locator("input[id='iAddAliasButton'], button:has-text('Añadir alias')").first.click()
            page.wait_for_timeout(6000)
            print("[+] ¡Alias añadido correctamente!")

            # -------------------------------------------------------------
            # PASO 2: Registro en la página web con el nuevo alias
            # -------------------------------------------------------------
            print(f"[*] Entrando en la web objetivo: {TARGET_URL}")
            page.goto(TARGET_URL)
            page.wait_for_timeout(4000)

            email_input = page.locator("input[type='email'], input[type='text']").first
            email_input.click()
            email_input.press("Control+A")
            email_input.press("Backspace")
            email_input.fill(correo_alias)
            print(f"[*] Correo introducido con éxito: {correo_alias}")

            page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                if (buttons.length > 0) {
                    buttons[0].click();
                } else {
                    throw new Error('No se encontró el botón');
                }
            }""")
            print("[*] Clic ejecutado en el botón de registro. Esperando correo de verificación...")

            # Guardamos la página del registro para volver a ella después
            registro_page = page

            # -------------------------------------------------------------
            # PASO 3: Leer el correo de verificación en Outlook Web
            # -------------------------------------------------------------
            print("[*] Abriendo la bandeja de entrada de Outlook en una pestaña nueva...")
            mail_page = context.new_page()
            mail_page.goto("https://outlook.live.com/owa/")
            mail_page.wait_for_timeout(8000)

            codigo_verificacion = None
            enlace_verificacion = None

            for intento in range(1, 12):
                print(f"[*] Comprobando bandeja de Outlook (Intento {intento}/11)...")
                mail_page.wait_for_timeout(5000)
                
                clicked = mail_page.evaluate("""() => {
                    const items = document.querySelectorAll('div[role="row"], div[aria-label*="Mensaje"], .ms-List-cell');
                    for (let item of items) {
                        if (item.innerText && item.innerText.length > 5) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                
                if clicked:
                    print("[+] ¡Correo de verificación detectado y abierto!")
                    mail_page.wait_for_timeout(4000)
                    
                    # Extraer texto y enlaces del correo
                    cuerpo_correo = mail_page.locator("div[aria-label*='Cuerpo del mensaje'], div[role='region']").inner_text()
                    
                    # Buscar un código numérico de 4 a 6 dígitos o un enlace de verificación
                    match_codigo = re.search(r'\b\d{4,6}\b', cuerpo_correo)
                    if match_codigo:
                        codigo_verificacion = match_codigo.group(0)
                        print(f"[+] Código de verificación encontrado: {codigo_verificacion}")

                    # Buscar enlace de activación si lo hubiera
                    links = mail_page.locator("a").all_inner_texts()
                    for link in links:
                        if "verify" in link.lower() or "confirm" in link.lower() or "activar" in link.lower():
                            # Intentamos capturar el atributo href del enlace
                            enlace_verificacion = mail_page.locator(f"a:has-text('{link}')").first.get_attribute("href")
                            break
                    break

            # -------------------------------------------------------------
            # PASO 4: Volver a poner la verificación en la web
            # -------------------------------------------------------------
            if codigo_verificacion or enlace_verificacion:
                print("[*] Volviendo a la página de registro para aplicar la verificación...")
                registro_page.bring_to_front()
                registro_page.wait_for_timeout(3000)

                if codigo_verificacion:
                    # Si la web pide introducir un código por teclado
                    print(f"[*] Introduciendo el código {codigo_verificacion} en la web...")
                    code_input = registro_page.locator("input[type='text'], input[name*='code'], input[id*='code']").first
                    code_input.fill(codigo_verificacion)
                    registro_page.keyboard.press("Enter")
                    registro_page.wait_for_timeout(5000)
                elif enlace_verificacion:
                    # Si la web usa un enlace directo de confirmación
                    print(f"[*] Navegando al enlace de verificación: {enlace_verificacion}")
                    registro_page.goto(enlace_verificacion)
                    registro_page.wait_for_timeout(5000)

                # Devolver el enlace final de la sesión o estado actual
                enlace_final = registro_page.url
                print(f"\n==========================================")
                print(f"[ éxito ] ¡Proceso completado con éxito!")
                print(f"[ i ] Enlace final de la cuenta/web: {enlace_final}")
                print(f"==========================================\n")
            else:
                print("[-] No se pudo extraer ningún código o enlace de verificación del correo.")

        except Exception as e:
            print(f"[-] Ocurrió un error durante el proceso: {e}")

        finally:
            # -------------------------------------------------------------
            # PASO 5: Limpieza (Borrar el alias temporal de Microsoft)
            # -------------------------------------------------------------
            print("[*] Procediendo a eliminar el alias temporal de Microsoft...")
            try:
                page.goto("https://account.live.com/names/manage")
                page.wait_for_timeout(5000)
                
                eliminado = page.evaluate(f"""(alias) => {{
                    const links = document.querySelectorAll('a, button');
                    for (let el of links) {{
                        if (el.innerText.includes('Quitar') || el.innerText.includes('Eliminar') || el.innerText.includes('Remove')) {{
                            let row = el.closest('div');
                            if (row && row.innerText.includes(alias)) {{
                                el.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}""", correo_alias)
                
                if eliminado:
                    page.wait_for_timeout(3000)
                    page.evaluate("""() => {
                        const confirmBtn = document.querySelector('input[id*="Save"], button[id*="Save"], button:has-text("Quitar"), button:has-text("Remove")');
                        if (confirmBtn) confirmBtn.click();
                    }""")
                    print(f"[+] ¡Alias {correo_alias} eliminado correctamente de la cuenta!")
            except Exception as e:
                print(f"[-] Error menor en la limpieza del alias: {e}")

            browser.close()

if __name__ == "__main__":
    main()
