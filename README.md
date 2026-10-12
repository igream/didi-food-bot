# 🤖 Monitor DiDi Food - Bot de Telegram

Bot automatizado en Python para monitorear en tiempo real el estado de una tienda de **DiDi Food** (en este caso **THE TREE**) y recibir alertas instantáneas en tu Telegram cuando pase de **Cerrada** a **Abierta**.

---

## 📁 Estructura del Proyecto

* **`config.py`**: Configuración centralizada (Token del Bot, Chat ID, ID de la tienda DiDi, intervalo de monitoreo en segundos).
* **`notifier.py`**: Módulo de mensajería con la API oficial de Telegram (con formato HTML, alertas enriquecidas y enlaces directos).
* **`login_didi.py`** / **`iniciar_login.bat`**: Asistente interactivo para iniciar sesión en DiDi Food **una sola vez**. Guarda la sesión en el perfil local `chrome_profile/`.
* **`monitor.py`** / **`iniciar_monitor.bat`**: Motor de monitoreo continuo en segundo plano. Intercepta los datos de DiDi Food y notifica cambios a Telegram.

---

## ⚙️ ¿Por qué este enfoque y no un simple `requests`?

DiDi Food protege sus endpoints mediante una firma criptográfica dinámica (`wsgsig`) y desafíos WAF (`status 522`). Además, su plataforma web restringe la información completa del restaurante a usuarios con sesión activa (`errno: 50002`). 

Este bot resuelve ambos obstáculos de forma automática usando **Playwright**:
1. Ejecuta el navegador en segundo plano (headless).
2. Genera las firmas legítimas de DiDi sin ser bloqueado.
3. Lee el estado exacto del restaurante directamente de los paquetes JSON (`cShopStatus` y `cShopStatusDesc`).

---

## 🚀 Pasos para Puesta en Marcha

### Paso 1: Iniciar Sesión (Solo la primera vez)
1. Haz doble clic en **`iniciar_login.bat`** (o ejecuta `python login_didi.py` en tu terminal).
2. Se abrirá una ventana de Chrome con la página de DiDi Food.
3. Ingresa tu número de teléfono y el código de verificación para entrar a tu cuenta de DiDi.
4. Regresa a la consola y presiona **ENTER**. ¡Tu sesión quedará guardada de forma permanente en la carpeta `chrome_profile/`!

### Paso 2: Iniciar el Monitoreo
1. Haz doble clic en **`iniciar_monitor.bat`** (o ejecuta `python monitor.py`).
2. El bot te enviará un mensaje a Telegram confirmando que el monitor está activo y el estado actual de la tienda.
3. Cada 60 segundos revisará el restaurante. En cuanto detecte que abrió, recibirás una alerta prioritaria con el enlace directo para ordenar.
