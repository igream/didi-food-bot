import os
from playwright.sync_api import sync_playwright
import config

def export():
    print("Exportando sesión desde chrome_profile...")
    if not os.path.exists(config.PROFILE_DIR):
        print("No existe chrome_profile.")
        return

    with sync_playwright() as p:
        browser_args = {
            "user_data_dir": config.PROFILE_DIR,
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        }
        if os.path.exists(config.CHROME_PATH):
            browser_args["executable_path"] = config.CHROME_PATH

        context = p.chromium.launch_persistent_context(**browser_args)
        
        # Exportar estado de almacenamiento (cookies y localStorage)
        context.storage_state(path="session.json")
        cookies = context.cookies()
        print(f"Estado exportado con éxito a 'session.json' ({len(cookies)} cookies encontradas).")
        context.close()

if __name__ == "__main__":
    export()
