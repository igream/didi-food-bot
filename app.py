import os
import time
import json
from fastapi import FastAPI, BackgroundTasks
from playwright.async_api import async_playwright
import config
from notifier import send_telegram_message

app = FastAPI(title="Store Status Monitor API", version="1.1.0")

# Archivo para persistir el estado entre reinicios o suspensiones de Render
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")

def load_saved_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Error leyendo state.json: {e}")
    return {
        "shop_name": config.STORE_NAME_DEFAULT,
        "last_category": None,      # 'OPEN' o 'CLOSED'
        "last_status_desc": None,   # 'Abierta', 'Cerrada', etc.
        "last_status_code": None,
        "last_check_time": None,
        "total_checks": 0
    }

def save_state(state_data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] No se pudo guardar state.json: {e}")

# Cargar estado guardado al iniciar
state = load_saved_state()

# Restaurar sesión desde variable de entorno de Render si existe
session_env = os.getenv("DIDI_SESSION_DATA")
if session_env and not os.path.exists(config.SESSION_FILE):
    try:
        with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(session_env)
        print("[INIT] Sesión restaurada desde la variable de entorno DIDI_SESSION_DATA.")
    except Exception as e:
        print(f"[INIT ERROR] No se pudo restaurar la sesión: {e}")

def classify_store_state(status_desc: str, status_code: int, order_available: int) -> str:
    """
    Clasifica de manera inteligente si la tienda está ABIERTA o CERRADA.
    """
    desc = (status_desc or "").lower()
    
    # Indicadores definitivos de cerrado
    if "cerrad" in desc or "fuera de horario" in desc or status_code == 2:
        return "CLOSED"
    
    # Indicadores de abierto
    if "abiert" in desc or status_code == 1 or order_available == 1:
        return "OPEN"
    
    # Casos como 'Fuera del límite de entrega' o restricciones temporales
    if "fuera del límite" in desc or status_code == 3:
        return "OPEN"

    return "UNKNOWN"

async def check_didi_status(force_notify: bool = False):
    """Realiza la consulta a DiDi Food con Playwright optimizado para bajo consumo de RAM."""
    timestamp = time.strftime("%H:%M:%S")
    state["total_checks"] = state.get("total_checks", 0) + 1
    state["last_check_time"] = timestamp

    if not config.STORE_URL:
        return {
            "success": False,
            "error": "missing_config",
            "message": "Falta la variable de entorno SHOP_ID en Render."
        }

    # Banderas optimizadas para bajo consumo de RAM
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
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

        launch_kwargs = {
            "headless": True,
            "args": browser_args
        }
        # En Windows local usamos Chrome instalado; en Render Docker usa el Chromium interno
        if os.path.exists(config.CHROME_PATH):
            launch_kwargs["executable_path"] = config.CHROME_PATH

        browser = await p.chromium.launch(**launch_kwargs)
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
            await page.wait_for_timeout(3000)
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
    order_available = api_data.get("isRealTimeOrderAvailableV3", 0)
    address = api_data.get("addr", "")

    current_category = classify_store_state(status_desc, status_code, order_available)
    previous_category = state.get("last_category")
    previous_desc = state.get("last_status_desc")

    notificado = False
    notif_type = None

    # Lógica inteligente de cambio de estado
    if previous_category is None:
        # Primer chequeo tras arranque o reinicio del servicio: Notificar estado actual
        if current_category == "OPEN":
            alerta = (
                f"🟢 <b>Monitor DiDi Food Operativo</b>\n\n"
                f"🏪 <b>{shop_name}</b>\n"
                f"✨ <b>Estado actual:</b> <code>{status_desc}</code> (¡Ya está abierta!)\n"
                f"📍 <i>{address}</i>\n\n"
                f"👉 <a href='{config.STORE_URL}'>Abrir DiDi Food y pedir ahora</a>"
            )
        else:
            alerta = (
                f"🟢 <b>Monitor DiDi Food Operativo</b>\n\n"
                f"🏪 <b>{shop_name}</b>\n"
                f"📊 <b>Estado actual:</b> <code>{status_desc}</code>\n"
                f"📍 <i>{address}</i>\n\n"
                f"<i>Servicio iniciado en la nube. Te avisaré inmediatamente cuando abra o cierre.</i>"
            )
        print(f"[{timestamp}] Notificación de inicio/reinicio enviada a Telegram.")
        send_telegram_message(alerta)
        notificado = True
        notif_type = "initial_startup"

    elif previous_category != current_category:
        # Hubo una transición real de estado
        if current_category == "OPEN":
            # TIENDA ABRIÓ
            alerta = (
                f"🚨 <b>¡LA TIENDA YA ESTÁ ABIERTA EN DIDI FOOD!</b> 🚨\n\n"
                f"🏪 <b>{shop_name}</b>\n"
                f"📍 <i>{address}</i>\n"
                f"✨ Estado actual: <b>{status_desc}</b>\n\n"
                f"👉 <a href='{config.STORE_URL}'>Haz clic aquí para ordenar ahora</a>"
            )
            print(f"[{timestamp}] ALERTA ENVIADA: Tienda ABIERTA.")
            send_telegram_message(alerta)
            notificado = True
            notif_type = "opened"

        elif current_category == "CLOSED":
            # TIENDA CERRÓ
            alerta = (
                f"🔴 <b>LA TIENDA HA CERRADO EN DIDI FOOD</b> 🔴\n\n"
                f"🏪 <b>{shop_name}</b>\n"
                f"📊 Estado actual: <code>{status_desc}</code>\n\n"
                f"<i>La tienda ya no está recibiendo pedidos por ahora. Te avisaré cuando vuelva a abrir.</i>"
            )
            print(f"[{timestamp}] ALERTA ENVIADA: Tienda CERRADA.")
            send_telegram_message(alerta)
            notificado = True
            notif_type = "closed"

    elif force_notify:
        send_telegram_message(
            f"ℹ️ <b>Revisión manual:</b>\n"
            f"🏪 <b>{shop_name}</b>: <code>{status_desc}</code> (categoría: {current_category})"
        )
        notificado = True
        notif_type = "forced"

    # Actualizar estado y guardarlo persistentemente en state.json
    state["shop_name"] = shop_name
    state["last_category"] = current_category
    state["last_status_desc"] = status_desc
    state["last_status_code"] = status_code
    state["last_check_time"] = timestamp
    save_state(state)

    return {
        "success": True,
        "shop": shop_name,
        "current_state": current_category,
        "previous_state": previous_category,
        "status_desc": status_desc,
        "status_code": status_code,
        "is_open": (current_category == "OPEN"),
        "address": address,
        "notified_telegram": notificado,
        "notification_type": notif_type,
        "timestamp": timestamp
    }

@app.get("/")
@app.get("/health")
def health():
    return {
        "status": "online",
        "service": "Store Status Monitor API",
        "store": state.get("shop_name", config.STORE_NAME_DEFAULT),
        "last_category": state.get("last_category"),
        "last_status": state.get("last_status_desc"),
        "last_check": state.get("last_check_time"),
        "total_checks": state.get("total_checks", 0)
    }

is_checking = False

async def run_check_task(force_notify: bool):
    global is_checking
    if is_checking:
        print("[CHECK] Ya hay una consulta en curso. Omitiendo duplicado.")
        return
    is_checking = True
    try:
        await check_didi_status(force_notify=force_notify)
    finally:
        is_checking = False

@app.get("/check")
@app.post("/check")
async def check_endpoint(background_tasks: BackgroundTasks, wait: bool = False, notify: bool = False):
    """
    Endpoint principal llamado periódicamente por cron-job.org o tu celular.
    Por defecto responde inmediatamente en milisegundos (200 OK) y realiza
    la consulta en segundo plano para evitar cualquier timeout de red.
    """
    if wait:
        return await check_didi_status(force_notify=notify)

    background_tasks.add_task(run_check_task, force_notify=notify)
    return {
        "status": "check_scheduled",
        "message": "Consulta ejecutándose en segundo plano. Se notificará a Telegram si hay cambios.",
        "last_status": state.get("last_status_desc"),
        "last_category": state.get("last_category"),
        "timestamp": time.strftime("%H:%M:%S")
    }

@app.get("/test-telegram")
def test_telegram(tipo: str = "ambos"):
    """
    Envía mensajes de prueba inmediatos a Telegram para verificar formato.
    tipo puede ser: 'abierta', 'cerrada' o 'ambos'.
    """
    hora = time.strftime("%H:%M:%S")
    shop = state.get("shop_name", config.STORE_NAME_DEFAULT)

    if tipo in ["abierta", "ambos"]:
        send_telegram_message(
            f"🚨 <b>[PRUEBA] ¡LA TIENDA YA ESTÁ ABIERTA EN DIDI FOOD!</b> 🚨\n\n"
            f"🏪 <b>{shop}</b>\n"
            f"✨ Estado: <b>Abierta</b> (Prueba a las {hora})\n\n"
            f"👉 <a href='{config.STORE_URL}'>Haz clic aquí para ordenar ahora</a>"
        )
    if tipo in ["cerrada", "ambos"]:
        send_telegram_message(
            f"🔴 <b>[PRUEBA] LA TIENDA HA CERRADO EN DIDI FOOD</b> 🔴\n\n"
            f"🏪 <b>{shop}</b>\n"
            f"📊 Estado actual: <code>Cerrada</code> (Prueba a las {hora})\n\n"
            f"<i>La tienda ya no está recibiendo pedidos. Te avisaré cuando vuelva a abrir.</i>"
        )
    return {"status": "ok", "tested_types": tipo, "time": hora}

@app.get("/debug-telegram")
def debug_telegram():
    """Diagnóstico detallado de la conexión con Telegram desde Render."""
    import requests
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return {
            "error": "missing_credentials",
            "message": "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no están configurados en Render.",
            "token_present": bool(token),
            "chat_id_present": bool(chat_id)
        }
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🔍 <b>Mensaje de diagnóstico</b>: Verificación directa desde el servidor de Render.",
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return {
            "token_masked": token[:8] + "..." + token[-4:] if len(token) > 12 else "INVALID",
            "chat_id": chat_id,
            "status_code": r.status_code,
            "telegram_response": r.json()
        }
    except Exception as e:
        return {
            "token_masked": token[:8] + "..." + token[-4:] if len(token) > 12 else "INVALID",
            "chat_id": chat_id,
            "error": str(e)
        }
