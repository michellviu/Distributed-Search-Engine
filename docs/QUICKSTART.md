# Quick Start Guide

## Guía Rápida de Inicio - Buscador Centralizado

### 1. Verificación de Requisitos

```bash
# Verificar versión de Python (requiere 3.8+)
python3 --version
```

### 2. Preparación del Entorno

```bash
# Clonar el repositorio
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine

# Crear directorios necesarios (si no existen)
mkdir -p shared_files logs
```

### 3. Preparar Archivos para Compartir

```bash
# Copiar algunos archivos de prueba al directorio compartido
echo "Contenido de prueba 1" > shared_files/documento1.txt
echo "Contenido de prueba 2" > shared_files/documento2.txt
echo "Datos importantes" > shared_files/reporte.pdf
```

### 4. Iniciar el Servidor

En una terminal:

```bash
cd src
python3 main_server.py
```

Salida esperada:
```
Indexing files from ./shared_files...
Indexed 3 unique file names
Starting server on localhost:5000
Server started on localhost:5000
```

### 5. Ejecutar el Cliente (en otra terminal)

```bash
# Buscar archivos
cd src
python3 main_client.py --query documento

# Buscar archivos de un tipo específico
python3 main_client.py --query reporte
```

### 6. Opciones Avanzadas

#### Configurar el servidor con opciones personalizadas:

```bash
python3 main_server.py --host 0.0.0.0 --port 8080 --index-path /path/to/files
```

#### Configurar el cliente para conectarse a un servidor remoto:

```bash
python3 main_client.py --host 192.168.1.100 --port 8080 --query "mi búsqueda"
```

#### Usar archivos de configuración personalizados:

```bash
# Servidor
python3 main_server.py --config /path/to/custom_server_config.json

# Cliente
python3 main_client.py --config /path/to/custom_client_config.json
```

### 7. Ejecutar Pruebas

```bash
# Desde el directorio raíz del proyecto
python3 -m unittest discover tests/ -v
```

### 8. Detener el Servidor

Presionar `Ctrl+C` en la terminal del servidor:

```
^C
Shutting down server...
Server stopped
```

## Solución de Problemas

### El servidor no inicia
- Verificar que el puerto no esté en uso: `netstat -tuln | grep 5000`
- Cambiar el puerto: `python3 main_server.py --port 5001`

### No se encuentran archivos
- Verificar que el directorio `shared_files` existe
- Verificar que hay archivos en el directorio
- Revisar los logs en `logs/server.log`

### Error de conexión del cliente
- Verificar que el servidor está ejecutándose
- Verificar host y puerto: `python3 main_client.py --host localhost --port 5000`
- Verificar firewall y permisos de red

## Siguientes Pasos

1. Revisar la documentación completa en [docs/ARCHITECTURE.md](ARCHITECTURE.md)
2. Explorar el código fuente en el directorio `src/`
3. Modificar los archivos de configuración en `config/`
4. Agregar más funcionalidades según las especificaciones del proyecto
