# Dockerfile para Distributed Search Engine
FROM python:3.12-slim

# Crear directorio de trabajo
WORKDIR /home/app

# Copiar todo el proyecto
COPY . /home/app

# Instalar dependencias básicas (solo estándar, sin GUI)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Instalar dependencias GUI opcionales
RUN if [ -f requirements-gui.txt ]; then pip install --no-cache-dir -r requirements-gui.txt; fi

# Crear carpetas necesarias
RUN mkdir -p logs downloads shared_files

# Exponer el puerto del servidor
EXPOSE 5000

# Comando por defecto: iniciar el servidor en 0.0.0.0 para Docker
CMD ["python", "src/main_server.py", "--host", "0.0.0.0", "--port", "5000", "--config", "config/server_config.json"]
