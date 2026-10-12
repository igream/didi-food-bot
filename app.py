import os
import time
import json
from fastapi import FastAPI
from playwright.async_api import async_playwright
import config
from notifier import send_telegram_message

app = FastAPI(title="DiDi Food Monitor API", version="1.0.0")

# Si se configuró la sesión por variable de entorno (Render Secret)
session_env = os.getenv("DIDI_SESSION_DATA")
if session_env and not os.path.exists(config.SESSION_FILE):
    try:
        with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(session_env)
        print("[INIT] Sesión restaurada desde la variable de entorno DIDI_SESSION_DATA.")
    except Exception as e:
        print(f"[INIT ERROR] No se pudo restaurar la sesión: {e}")

# Estado en memoria
state = {
    "shop_name": config.STORE_NAME_DEFAULT,
    "last_status_desc": "Desconocido",
    "last_status_code": None,
    "last_check_time": None,
    "total_checks": 0
}

async def check_didi_status():
    """Realiza la consulta a DiDi Food con Playwright de forma asíncrona."""
    timestamp = time.strftime("%H:%M:%S")
    state["total_checks"] += 1
    state["last_check_time"] = timestamp

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--single-process"
    ]

    api_data = {}
    error_info = {}

    async with async_playwright() as p:
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 800}
        }
        if os.path.exists(config.SESSION_FILE):
            context_kwargs["storage_state"] = config.SESSION_FILE

        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        async def handle_route(route):
            try:
                response = await route.fetch()
                if "shop/index" in route.request.url and response.status == 200:
                    try:
                        res_json = await response.json()
                        errno = res_json.get("errno")
                        if errno == 0:
                            api_data.update(res_json.get("data", {}).get("shopInfo", {}))
                        elif errno == 50002:
                            error_info["need_login"] = True
                    except Exception as e:
                        error_info["json_error"] = str(e)
                await route.fulfill(response=response)
            except Exception:
                pass

        await page.route("**/shop/index*", handle_route)

        try:
            await page.goto(config.STORE_URL, wait_until="load", timeout=30000)
            await page.wait_for_timeout(3500)
        except Exception as e:
            print(f"[{timestamp}] Advertencia al cargar página: {e}")

        await browser.close()

    if error_info.get("need_login"):
        return {
            "success": False,
            "error": "need_login",
            "message": "La sesión expiró o no se configuró DIDI_SESSION_DATA."
        }

    if not api_data:
        return {
            "success": False,
            "error": "no_data",
            "message": "No se recibieron datos de la API de DiDi."
        }

    shop_name = api_data.get("shopName", config.STORE_NAME_DEFAULT)
    status_desc = api_data.get("cShopStatusDesc", "Desconocido")
    status_code = api_data.get("cShopStatus")
    address = api_data.get("addr", "")

    state["shop_name"] = shop_name
    esta_abierta = (status_desc.lower() != "cerrada" and status_code != 2)

    notificado = False
    if state["last_status_desc"] != status_desc:
        if esta_abierta:
            alerta = (
                f"🚨 <b>¡LA TIENDA YA ESTÁ ABIERTA EN DIDI FOOD!</b> 🚨\n\n"
                f"🏪 <b>{shop_name}</b>\n"
                f"📍 <i>{address}</i>\n"
                f"✨ Estado: <b>{status_desc}</b>\n\n"
                f"👉 <a href='{config.STORE_URL}'>Abrir DiDi Food y pedir ahora</a>"
            )
            send_telegram_message(alerta)
            notificado = True
        elif state["last_status_desc"] not in ["Desconocido", None]:
            alerta = (
                f"🔴 <b>La tienda {shop_name} ahora está CERRADA.</b>\n\n"
                f"Estado actual: <i>{status_desc}</i>\n"
                f"Seguiré monitoreando para avisarte cuando vuelva a abrir."
            )
            send_telegram_message(alerta)
            notificado = True

        state["last_status_desc"] = status_desc
        state["last_status_code"] = status_code

    return {
        "success": True,
        "shop": shop_name,
        "status_desc": status_desc,
        "status_code": status_code,
        "is_open": esta_abierta,
        "address": address,
        "notified_telegram": notificado,
        "timestamp": timestamp
    }

@app.get("/")
@app.get("/health")
def health():
    return {
        "status": "online",
        "service": "DiDi Food Monitor Bot",
        "store": config.STORE_NAME_DEFAULT,
        "last_status": state["last_status_desc"],
        "last_check": state["last_check_time"],
        "total_checks": state["total_checks"]
    }

@app.get("/check")
@app.post("/check")
async def check_endpoint():
    """Endpoint llamado por cron-job.org, tu celular o un webhook."""
    result = await check_didi_status()
    return result
