import os
from dotenv import load_dotenv

# Cargar variables desde archivo .env local si existe
load_dotenv()

# --- TELEGRAM CONFIG ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- STORE CONFIG ---
SHOP_ID = os.getenv("SHOP_ID", "")
STORE_URL = f"https://www.didi-food.com/es-MX/food/store/{SHOP_ID}/" if SHOP_ID else ""
STORE_NAME_DEFAULT = os.getenv("STORE_NAME", "Restaurante")

# Intervalo entre revisiones (en segundos)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))

# --- BROWSER CONFIG ---
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")
SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.json")
