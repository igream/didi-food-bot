import requests
import time
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(message: str, parse_mode: str = "HTML") -> bool:
    """
    Envía un mensaje a Telegram a través del Bot API oficial.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload, timeout=12)
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            return True
        else:
            print(f"[Telegram Error]: {data}")
            return False
    except Exception as e:
        print(f"[Telegram Excepción]: {e}")
        return False

def test_telegram_connection() -> bool:
    """Envía un mensaje de prueba para verificar la comunicación."""
    hora = time.strftime("%H:%M:%S")
    mensaje = f"🤖 <b>Bot conectado con éxito</b>\n\nPrueba de comunicación a las <code>{hora}</code>."
    return send_telegram_message(mensaje)

if __name__ == "__main__":
    print("Probando envío a Telegram...")
    if test_telegram_connection():
        print("Mensaje enviado correctamente a Telegram!")
    else:
        print("Hubo un error al enviar el mensaje.")
