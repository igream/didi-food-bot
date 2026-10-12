import os
import sys
import time
from playwright.sync_api import sync_playwright
import config

def login():
    print("=" * 60)
    print("      INICIO DE SESIÓN EN DIDI FOOD PARA EL MONITOR")
    print("=" * 60)
    print("\nAbriendo el navegador Chrome...")
    print("1. En la ventana que se abrirá, inicia sesión con tu número de teléfono.")
    print("2. Una vez que hayas iniciado sesión y veas la tienda, vuelve a esta")
    print("   consola y presiona ENTER para guardar la sesión.\n")

    os.makedirs(config.PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser_args = {
            "user_data_dir": config.PROFILE_DIR,
            "headless": False,
            "viewport": {"width": 1280, "height": 850},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        }
        if os.path.exists(config.CHROME_PATH):
            browser_args["executable_path"] = config.CHROME_PATH

        context = p.chromium.launch_persistent_context(**browser_args)
        page = context.new_page()

        print(f"Cargando la tienda: {config.STORE_URL}...")
        page.goto(config.STORE_URL, wait_until="domcontentloaded", timeout=45000)

        print("\nEsperando inicio de sesión...")
        input(">>> PRESIONA ENTER AQUÍ CUANDO YA HAYAS INICIADO SESIÓN EN LA VENTANA: ")

        print("\nVerificando sesión...")
        time.sleep(2)
        cookies = context.cookies()
        print(f"Se han guardado {len(cookies)} cookies en el perfil local '{config.PROFILE_DIR}'.")
        print("¡Sesión guardada exitosamente!")
        context.close()

if __name__ == "__main__":
    login()
