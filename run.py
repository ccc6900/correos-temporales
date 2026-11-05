import os
import time
import json
import imaplib
import email
import re
import html
import quopri
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("TARGET_URL")
GMX_USER = os.environ.get("GMX_USER")
GMX_PASS = os.environ.get("GMX_PASS")

# Se utiliza una única dirección autorizada para la prueba.
# Si necesitas cambiarla, sustituye este valor por otro alias válido de tu cuenta.
ALIAS_CORREO = "auto.notifier.es@gmx.es"

ARCHIVO_ESTADO = "usados.json"
TIMEOUT_CORREO = 120
INTERVALO_CONSULTA = 5


def guardar_resultado(datos):
    datos["fecha"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)


def decodificar_cabecera(valor):
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:
        return str(valor)


def obtener_cuerpo(msg):
    partes = []
    if msg.is_multipart():
        for parte in msg.walk():
            if parte.get_content_maintype() == "multipart":
                continue
            if parte.get_content_disposition() == "attachment":
                continue
            if parte.get_content_type() not in ("text/plain", "text/html"):
                continue
            contenido = parte.get_payload(decode=True)
            if contenido is None:
                continue
            charset = parte.get_content_charset() or "utf-8"
            partes.append(contenido.decode(charset, errors="replace"))
    else:
        contenido = msg.get_payload(decode=True)
        if contenido is not None:
            charset = msg.get_content_charset() or "utf-8"
            partes.append(contenido.decode(charset, errors="replace"))
    return "\n".join(partes)


def fecha_mensaje(msg):
    valor = msg.get("Date")
    if not valor:
        return None
    try:
        fecha = parsedate_to_datetime(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.timestamp()
    except Exception:
        return None


def mensaje_es_para_alias(msg, alias):
    campos = ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To")
    destinatarios = " ".join(str(msg.get(campo, "")) for campo in campos)
    return alias.lower() in destinatarios.lower()


def leer_correo_nuevo(alias, desde, timeout_segundos=TIMEOUT_CORREO, descripcion="correo"):
    servidor = "imap.gmx.es" if GMX_USER.lower().endswith(".es") else "imap.gmx.com"
    fin = time.time() + timeout_segundos
    print(f"[*] Esperando {descripcion} nuevo para {alias}...")

    while time.time() < fin:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(servidor, 993)
            mail.login(GMX_USER, GMX_PASS)
            estado, _ = mail.select("INBOX")
            if estado != "OK":
                raise RuntimeError("No se pudo abrir la bandeja INBOX.")

            estado, datos = mail.search(None, "ALL")
            if estado == "OK" and datos and datos[0]:
                ids = datos[0].split()[-40:]
                for msg_id in reversed(ids):
                    estado_fetch, contenido = mail.fetch(msg_id, "(RFC822)")
                    if estado_fetch != "OK":
                        continue
                    for elemento in contenido:
                        if not isinstance(elemento, tuple):
                            continue
                        msg = email.message_from_bytes(elemento[1])
                        timestamp = fecha_mensaje(msg)
                        if timestamp is None or timestamp < desde:
                            continue
                        if not mensaje_es_para_alias(msg, alias):
                            continue
                        cuerpo = obtener_cuerpo(msg)
                        asunto = decodificar_cabecera(msg.get("Subject", ""))
                        print(f"[+] Correo nuevo encontrado: {asunto}")
                        return cuerpo
        except Exception as exc:
            print(f"[-] Error IMAP: {exc}")
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass
        time.sleep(INTERVALO_CONSULTA)

    print(f"[-] No llegó el {descripcion} dentro del tiempo de espera.")
    return None


def leer_correo_con_enlaces(alias, desde, timeout_segundos=180):
    """Busca el correo de resultados desde el inicio de la prueba.
    No usa la hora posterior a la verificación: el mensaje puede haber llegado antes.
    """
    servidor = "imap.gmx.com" if GMX_USER.lower().endswith(".es") else "imap.gmx.com"
    fin = time.time() + timeout_segundos
    print(f"[*] Buscando el correo de resultados recibido desde el inicio de la prueba para {alias}...")

    while time.time() < fin:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(servidor, 993)
            mail.login(GMX_USER, GMX_PASS)
            estado, _ = mail.select("INBOX")
            if estado != "OK":
                raise RuntimeError("No se pudo abrir la bandeja INBOX.")

            estado, datos = mail.search(None, "ALL")
            if estado == "OK" and datos and datos[0]:
                ids = datos[0].split()[-60:]
                for msg_id in reversed(ids):
                    estado_fetch, contenido = mail.fetch(msg_id, "(RFC822)")
                    if estado_fetch != "OK":
                        continue
                    for elemento in contenido:
                        if not isinstance(elemento, tuple):
                            continue
                        msg = email.message_from_bytes(elemento[1])
                        timestamp = fecha_mensaje(msg)
                        if timestamp is None or timestamp < desde:
                            continue
                        if not mensaje_es_para_alias(msg, alias):
                            continue

                        cuerpo = obtener_cuerpo(msg)
                        asunto = decodificar_cabecera(msg.get("Subject", ""))
                        plus, standard = extraer_enlaces(cuerpo)
                        if plus or standard:
                            print(f"[+] Correo con enlaces localizado: {asunto}")
                            return cuerpo
                        print(f"[*] Correo recibido para el alias, pero sin enlaces M3U: {asunto}")

        except Exception as exc:
            print(f"[-] Error buscando correo de resultados por IMAP: {exc}")
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass
        time.sleep(INTERVALO_CONSULTA)

    print("[-] No se localizó un correo nuevo que contenga enlaces M3U.")
    return None


def extraer_codigo(texto):
    if not texto:
        return None
    texto = html.unescape(texto)
    patrones = [
        r"(?:c[oó]digo|code|verificaci[oó]n|verification)[^0-9]{0,50}(\d{4,8})",
        r"\b(\d{6})\b",
        r"\b(\d{4,5})\b",
    ]
    for patron in patrones:
        coincidencia = re.search(patron, texto, re.IGNORECASE)
        if coincidencia:
            return coincidencia.group(1)
    return None


def extraer_enlaces(texto):
    if not texto:
        return "", ""
    texto = html.unescape(texto)
    texto = unquote(texto)
    texto = texto.replace("\\/", "/")
    urls = re.findall(r"""https?://[^\s<>"']+""", texto, flags=re.IGNORECASE)
    plus = ""
    standard = ""

    for url in urls:
        url = url.rstrip(".,);]}")
        bajo = url.lower()
        parece_m3u = "m3u" in bajo or "get.php" in bajo
        if not parece_m3u:
            continue
        if "plus" in bajo or "type=m3u_plus" in bajo:
            if not plus:
                plus = url
        elif not standard:
            standard = url

    return plus, standard


def main():
    if not TARGET_URL or not GMX_USER or not GMX_PASS:
        raise RuntimeError("Faltan los Secrets TARGET_URL, GMX_USER o GMX_PASS.")

    resultado = {
        "estado": "INCOMPLETO",
        "alias": ALIAS_CORREO,
        "url_final": "",
        "m3u_plus": "",
        "m3u_standard": "",
        "mensaje": "",
    }

    inicio_prueba = time.time()

    try:
        with sync_playwright() as playwright:
            navegador = playwright.firefox.launch(headless=True)
            contexto = navegador.new_context()
            pagina = contexto.new_page()

            print(f"[*] Abriendo la página configurada: {TARGET_URL}")
            pagina.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(3000)

            campo_email = pagina.locator(
                "input[type='email'], input[name*='email' i], "
                "input[placeholder*='correo' i], input[placeholder*='email' i]"
            ).first

            if campo_email.count() == 0:
                raise RuntimeError("No se encontró el campo de correo electrónico.")

            campo_email.fill(ALIAS_CORREO)
            if campo_email.input_value().strip().lower() != ALIAS_CORREO.lower():
                raise RuntimeError("La página no conserva la dirección escrita.")

            boton = pagina.locator(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Enviar'), button:has-text('Continuar')"
            ).first
            if boton.count():
                boton.click()
            else:
                campo_email.press("Enter")

            correo_verificacion = leer_correo_nuevo(
                ALIAS_CORREO, inicio_prueba, descripcion="correo de verificación"
            )
            codigo = extraer_codigo(correo_verificacion)

            if not codigo:
                resultado["mensaje"] = (
                    "No se recibió un correo de verificación nuevo o no se pudo "
                    "identificar su código."
                )
                resultado["url_final"] = pagina.url
                navegador.close()
                guardar_resultado(resultado)
                return

            print("[+] Código de verificación localizado.")
            pagina.wait_for_timeout(2000)
            selector_codigo = (
                "input[name*='code' i], input[id*='code' i], "
                "input[autocomplete='one-time-code'], input[type='number'], "
                "input[type='tel']"
            )
            campo_codigo = pagina.locator(selector_codigo).first
            campo_codigo.wait_for(state="visible", timeout=20000)
            campo_codigo.fill(codigo)

            boton_codigo = pagina.locator(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Verificar'), button:has-text('Continuar'), "
                "button:has-text('Confirmar')"
            ).first
            if boton_codigo.count():
                boton_codigo.click()
            else:
                campo_codigo.press("Enter")

            # Esperar el segundo correo: los enlaces pueden no aparecer en pantalla.
            correo_resultados = leer_correo_con_enlaces(
                ALIAS_CORREO,
                inicio_prueba,
                timeout_segundos=180,
            )

            pagina.wait_for_timeout(4000)
            try:
                texto_pantalla = pagina.locator("body").inner_text(timeout=10000)
            except Exception:
                texto_pantalla = ""

            plus, standard = extraer_enlaces(texto_pantalla)
            correo_plus, correo_standard = extraer_enlaces(correo_resultados or "")

            resultado["m3u_plus"] = plus or correo_plus
            resultado["m3u_standard"] = standard or correo_standard
            resultado["url_final"] = pagina.url

            if resultado["m3u_plus"] and resultado["m3u_standard"]:
                resultado["estado"] = "OK"
                resultado["mensaje"] = "Se encontraron los dos enlaces."
            else:
                faltan = []
                if not resultado["m3u_plus"]:
                    faltan.append("M3U Plus")
                if not resultado["m3u_standard"]:
                    faltan.append("M3U estándar")
                resultado["mensaje"] = (
                    "Proceso realizado, pero faltan enlaces: " + ", ".join(faltan)
                    + ". Comprueba el correo recibido y la página final."
                )

            navegador.close()

    except Exception as exc:
        resultado["estado"] = "INCOMPLETO"
        resultado["mensaje"] = f"{type(exc).__name__}: {exc}"

    guardar_resultado(resultado)
    print(f"[*] Estado final: {resultado['estado']}")
    print(f"[*] Diagnóstico: {resultado['mensaje']}")
    print("[+] result.json guardado.")


if __name__ == "__main__":
    main()
