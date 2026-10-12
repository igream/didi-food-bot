import os
import sys
import time
import json
from playwright.sync_api import sync_playwright
import config
from notifier import send_telegram_message

class DiDiFoodMonitor:
    def __init__(self):
        self.store_url = config.STORE_URL
        self.shop_id = config.SHOP_ID
        self.interval = config.CHECK_INTERVAL_SECONDS
        self.last_status_desc = None
        self.last_status_code = None
        self.shop_name = config.STORE_NAME_DEFAULT
        self.is_running = True

    def _ensure_profile_exists(self):
        if not os.path.exists(config.PROFILE_DIR) or not os.listdir(config.PROFILE_DIR):
            print("\n" + "=" * 65)
            print("  ¡ATENCIÓN: NO SE HA INICIADO SESIÓN EN DIDI FOOD TODAVÍA!")
            print("=" * 65)
            print("Para poder consultar los datos del restaurante en DiDi Food,")
            print("necesitas iniciar sesión una sola vez.")
            print("\nEjecuta en tu terminal:")
            print("    python login_didi.py\n")
            print("Luego de iniciar sesión, vuelve a ejecutar este monitor.")
            print("=" * 65 + "\n")
            
            send_telegram_message(
                "⚠️ <b>Monitor DiDi Food:</b> No se encontró sesión guardada.\n"
                "Ejecuta en tu computadora <code>python login_didi.py</code> para ingresar a DiDi Food."
            )
            return False
        return True

    def check_store_status(self, page) -> dict:
        """
        Navega a la tienda e intercepta la respuesta JSON de la API /shop/index.
        Retorna un dict con la información del local.
        """
        api_data = {}
        error_info = {}

        def handle_route(route):
            try:
                response = route.fetch()
                if "shop/index" in route.request.url and response.status == 200:
                    try:
                        res_json = response.json()
                        errno = res_json.get("errno")
                        if errno == 0:
                            api_data.update(res_json.get("data", {}).get("shopInfo", {}))
                        elif errno == 50002:
                            error_info["need_login"] = True
                            error_info["errmsg"] = res_json.get("errmsg", "Sesión requerida")
                    except Exception as e:
                        error_info["json_error"] = str(e)
                route.fulfill(response=response)
            except Exception as e:
                # Si la petición de fondo fue abortada durante la navegación
                pass

        page.route("**/shop/index*", handle_route)

        try:
            page.goto(self.store_url, wait_until="load", timeout=35000)
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Aviso de carga en navegador: {e}")

        # Limpiar interceptor para la siguiente vuelta
        try:
            page.unroute("**/shop/index*")
        except Exception:
            pass

        if error_info.get("need_login"):
            return {"error": "need_login", "errmsg": error_info.get("errmsg")}

        if api_data:
            return {
                "success": True,
                "shopName": api_data.get("shopName", self.shop_name),
                "cShopStatus": api_data.get("cShopStatus"),
                "cShopStatusDesc": api_data.get("cShopStatusDesc", "Desconocido"),
                "isRealTimeOrderAvailable": api_data.get("isRealTimeOrderAvailableV3", 0),
                "address": api_data.get("addr", "")
            }

        # Fallback: Inspeccionar DOM de la página por si la API cambió
        try:
            dom_text = page.inner_text("body").lower()
            if "cerrad" in dom_text or "fuera de horario" in dom_text:
                return {
                    "success": True,
                    "shopName": self.shop_name,
                    "cShopStatus": 2,
                    "cShopStatusDesc": "Cerrada",
                    "isRealTimeOrderAvailable": 0
                }
            elif "inicio de sesión" in dom_text or "ingresar con contraseña" in dom_text:
                return {"error": "need_login", "errmsg": "Redirigido a pantalla de login"}
        except Exception:
            pass

        return {"error": "no_data"}

    def run(self):
        print("=" * 60)
        print("       MONITOR DE DIDI FOOD - BOT DE TELEGRAM")
        print("=" * 60)
        print(f"Tienda objetivo : {self.store_url}")
        print(f"ID de Tienda    : {self.shop_id}")
        print(f"Intervalo       : Cada {self.interval} segundos")
        print(f"Perfil de Chrome: {config.PROFILE_DIR}")
        print("=" * 60)

        if not self._ensure_profile_exists():
            return

        with sync_playwright() as p:
            browser_args = {
                "user_data_dir": config.PROFILE_DIR,
                "headless": True,
                "viewport": {"width": 1280, "height": 800},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            }
            if os.path.exists(config.CHROME_PATH):
                browser_args["executable_path"] = config.CHROME_PATH

            print("Iniciando navegador en segundo plano...")
            try:
                context = p.chromium.launch_persistent_context(**browser_args)
                page = context.new_page()
            except Exception as e:
                print(f"[Error crítico al iniciar navegador]: {e}")
                print("Asegúrate de que no haya otra ventana de Chrome usando este mismo perfil.")
                return

            print("Verificando estado inicial...")
            primer_check = True

            while self.is_running:
                timestamp = time.strftime("%H:%M:%S")
                result = self.check_store_status(page)

                if result.get("error") == "need_login":
                    msg = (
                        "⚠️ <b>Alerta Monitor DiDi:</b> Se requiere iniciar sesión.\n"
                        "Tu sesión expiró o no se inició correctamente.\n"
                        "Ejecuta en tu terminal: <code>python login_didi.py</code>"
                    )
                    print(f"[{timestamp}] ERROR: Se requiere iniciar sesión en DiDi Food.")
                    send_telegram_message(msg)
                    # Esperar más tiempo para no saturar si no está logueado
                    time.sleep(180)
                    continue

                if not result.get("success"):
                    print(f"[{timestamp}] No se pudo obtener el estado (reintentando en {self.interval}s)...")
                    time.sleep(self.interval)
                    continue

                shop_name = result.get("shopName")
                status_desc = result.get("cShopStatusDesc")
                status_code = result.get("cShopStatus")
                self.shop_name = shop_name

                print(f"[{timestamp}] {shop_name} -> Estado: '{status_desc}' (código: {status_code})")

                # Es abierta si la descripción es distinta de 'Cerrada' o el código no es 2
                esta_abierta = (status_desc.lower() != "cerrada" and status_code != 2)

                if primer_check:
                    inicio_msg = (
                        f"🟢 <b>Monitor DiDi Food Activo</b>\n\n"
                        f"🏪 <b>Tienda:</b> {shop_name}\n"
                        f"📊 <b>Estado actual:</b> <code>{status_desc}</code>\n"
                        f"⏱ <b>Intervalo:</b> Cada {self.interval} segundos\n\n"
                        f"<i>Te enviaré una alerta inmediata cuando abra.</i>"
                    )
                    send_telegram_message(inicio_msg)
                    primer_check = False
                    self.last_status_desc = status_desc
                    self.last_status_code = status_code

                elif self.last_status_desc != status_desc:
                    # Hubo un cambio de estado
                    if esta_abierta:
                        alerta = (
                            f"🚨 <b>¡LA TIENDA YA ESTÁ ABIERTA EN DIDI FOOD!</b> 🚨\n\n"
                            f"🏪 <b>{shop_name}</b>\n"
                            f"📍 <i>{result.get('address', '')}</i>\n"
                            f"✨ Estado: <b>{status_desc}</b>\n\n"
                            f"👉 <a href='{self.store_url}'>Abrir DiDi Food y pedir ahora</a>"
                        )
                        print(f"\n[{timestamp}] ¡¡¡TIENDA ABIERTA!!! Enviando alerta a Telegram...")
                        send_telegram_message(alerta)
                    else:
                        alerta = (
                            f"🔴 <b>La tienda {shop_name} ahora está CERRADA.</b>\n\n"
                            f"Estado actual: <i>{status_desc}</i>\n"
                            f"Seguiré monitoreando para avisarte cuando vuelva a abrir."
                        )
                        print(f"\n[{timestamp}] La tienda ha cerrado. Notificando a Telegram...")
                        send_telegram_message(alerta)

                    self.last_status_desc = status_desc
                    self.last_status_code = status_code

                time.sleep(self.interval)

            context.close()

if __name__ == "__main__":
    monitor = DiDiFoodMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nMonitor detenido por el usuario.")
