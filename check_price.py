#!/usr/bin/env python3
"""
Vigila el precio de un producto de Shopify y avisa por Telegram.

Solo usa la libreria estandar: no hay que instalar nada.

Variables de entorno:
  TELEGRAM_BOT_TOKEN   (obligatoria) token que te da @BotFather
  TELEGRAM_CHAT_ID     (obligatoria) tu chat id
  PRODUCT_URL          url del producto, sin el .js del final
  THRESHOLD_EUR        avisa cuando el precio baje de esto (por defecto 100)
  NOTIFY_ON_ANY_CHANGE "true" para avisar de cualquier cambio de precio
  STATE_FILE           donde se guarda la memoria entre ejecuciones
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

PRODUCT_URL = os.environ.get(
    "PRODUCT_URL", "https://yepoda.es/products/the-yepoda-advent-calendar-2026"
)
THRESHOLD_EUR = float(os.environ.get("THRESHOLD_EUR", "100"))
NOTIFY_ON_ANY_CHANGE = os.environ.get("NOTIFY_ON_ANY_CHANGE", "false").lower() == "true"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")

# Si falla varias veces seguidas no queremos un aviso por ejecucion.
ERROR_REMINDER_HOURS = 24

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# --------------------------------------------------------------------------
# Estado (para no repetir el mismo aviso en cada ejecucion)
# --------------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en las variables de entorno."
        )

    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token, data=payload
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)

    if not body.get("ok"):
        raise RuntimeError("Telegram devolvio un error: %s" % body)
    print("  -> aviso enviado a Telegram")


# --------------------------------------------------------------------------
# Lectura del precio
# --------------------------------------------------------------------------

def fetch_product():
    """Devuelve (precio_en_euros, disponible, titulo). Lanza excepcion si algo falla."""
    url = PRODUCT_URL.rstrip("/") + ".js"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})

    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError("La web respondio con HTTP %s" % resp.status)
        data = json.loads(resp.read().decode("utf-8"))

    # Shopify da el precio en centimos. Si este campo desaparece, preferimos
    # fallar con un aviso antes que devolver un precio inventado.
    if "price" not in data:
        raise RuntimeError("El JSON ya no trae el campo 'price'. La web ha cambiado.")

    price = data["price"] / 100.0
    if price <= 0:
        raise RuntimeError("Precio sospechoso (%s). Mejor revisarlo a mano." % price)

    return price, bool(data.get("available", False)), data.get("title", "el producto")


# --------------------------------------------------------------------------

def handle_error(state, message):
    """Avisa de que el bot esta roto, pero como mucho una vez cada 24h."""
    print("ERROR: %s" % message)
    now = datetime.now(timezone.utc)
    last_raw = state.get("last_error_notified_at")

    should_notify = True
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
            should_notify = now - last > timedelta(hours=ERROR_REMINDER_HOURS)
        except ValueError:
            should_notify = True

    if should_notify:
        try:
            send_telegram(
                "⚠️ <b>El vigilante de precios ha fallado</b>\n\n"
                "<code>%s</code>\n\n"
                "No estoy pudiendo leer el precio, asi que <b>no te fies del silencio</b>.\n"
                "%s" % (message, PRODUCT_URL)
            )
            state["last_error_notified_at"] = now.isoformat()
        except Exception as exc:  # noqa: BLE001
            print("Ademas, no he podido avisar por Telegram: %s" % exc)

    save_state(state)


def main():
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        print("ERROR: faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID.")
        print("En local: exportalas en tu terminal.")
        print("En GitHub: Settings > Secrets and variables > Actions.")
        return 2

    if "--test" in sys.argv:
        try:
            send_telegram(
                "✅ <b>Prueba correcta</b>\n\nEl bot puede escribirte. Ya esta todo conectado."
            )
        except Exception as exc:  # noqa: BLE001
            print("ERROR: no he podido escribirte: %s" % exc)
            print("Revisa el token, el chat id, y que hayas pulsado /start")
            print("en la conversacion con tu bot.")
            return 2
        return 0

    state = load_state()

    try:
        price, available, title = fetch_product()
    except Exception as exc:  # noqa: BLE001
        handle_error(state, "%s: %s" % (type(exc).__name__, exc))
        return 1

    print("Precio actual: %.2f EUR | disponible: %s | umbral: %.2f EUR"
          % (price, available, THRESHOLD_EUR))

    previous = state.get("last_price")
    already_warned = state.get("below_threshold_notified", False)

    # Una lectura correcta borra cualquier aviso de error pendiente.
    state.pop("last_error_notified_at", None)

    try:
        stock = "✅ disponible" if available else "❌ agotado"

        if price < THRESHOLD_EUR and not already_warned:
            ahorro = ""
            if previous:
                ahorro = "\nAntes estaba a %.2f €." % previous
            send_telegram(
                "\U0001f525 <b>¡Ha bajado de %.0f €!</b>\n\n"
                "<b>%s</b>\nAhora: <b>%.2f €</b>%s\nStock: %s\n\n%s"
                % (THRESHOLD_EUR, title, price, ahorro, stock, PRODUCT_URL)
            )
            state["below_threshold_notified"] = True

        elif price >= THRESHOLD_EUR and already_warned:
            # Ha vuelto a subir: rearmamos el aviso para la proxima bajada.
            send_telegram(
                "↗️ <b>Ha vuelto a subir</b>\n\n<b>%s</b>\nAhora: <b>%.2f €</b>\n\n"
                "Te vuelvo a avisar si baja de %.0f €." % (title, price, THRESHOLD_EUR)
            )
            state["below_threshold_notified"] = False

        elif NOTIFY_ON_ANY_CHANGE and previous is not None and price != previous:
            flecha = "\U0001f4c9" if price < previous else "\U0001f4c8"
            send_telegram(
                "%s <b>Cambio de precio</b>\n\n<b>%s</b>\n%.2f € → <b>%.2f €</b>\n"
                "Stock: %s\n\n(Tu aviso sigue puesto en %.0f €.)\n\n%s"
                % (flecha, title, previous, price, stock, THRESHOLD_EUR, PRODUCT_URL)
            )

        else:
            print("  -> sin novedad, no envio nada")
    except Exception as exc:  # noqa: BLE001
        # Importante: si el envio falla NO marcamos el aviso como dado.
        # Al no guardar el estado, la proxima ejecucion lo reintenta.
        print("ERROR: no he podido enviarte el aviso: %s" % exc)
        print("Lo reintentare en la proxima ejecucion.")
        return 1

    state["last_price"] = price
    state["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
