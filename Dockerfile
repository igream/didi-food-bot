FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Puerto dinámico asignado por Render (por defecto 10000)
ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
