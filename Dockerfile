FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    postgresql-client \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY backend/requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Playwright browsers
RUN playwright install --with-deps chromium

# Copiar código
COPY . .

# Crear directorios necesarios
RUN mkdir -p logs data/downloads data/cache

# Exponer puerto
EXPOSE 8000

# Comando de inicio
CMD ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]
