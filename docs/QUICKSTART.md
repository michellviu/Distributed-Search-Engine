# 🚀 Inicio Rápido - Servidor de Búsqueda Distribuida

## Instalación

### 1. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 2. Verificar Estructura

Asegúrate de que la estructura del proyecto sea correcta:

```text
Distributed-Search-Engine/
├── src/
│   ├── server/
│   ├── client/
│   ├── indexer/
│   ├── search/
│   ├── transfer/
│   └── utils/
├── config/
├── shared_files/
└── logs/
```

## Uso Básico

### Opción 1: Script de Inicio Rápido (Recomendado)

El método más fácil para iniciar el servidor:

```bash
./start_server.sh
```

Este script:

- ✅ Crea los directorios necesarios
- ✅ Genera archivos de ejemplo si `shared_files` está vacío
- ✅ Inicia el servidor con la configuración por defecto

### Opción 2: Inicio Manual

```bash
# Desde el directorio raíz
cd src
python3 main_server.py
```

Con opciones personalizadas:

```bash
python3 main_server.py --host 0.0.0.0 --port 8080 --index-path /ruta/a/archivos
```

## Uso del Cliente

### Cliente Interactivo (Recomendado)

```bash
./client_interactive.py
```

Comandos disponibles:

- `search <query> [tipo]` - Buscar documentos
- `index <ruta>` - Indexar un archivo
- `download <id> <destino>` - Descargar archivo
- `list` - Listar todos los archivos
- `help` - Ver ayuda
- `quit` - Salir

### Ejemplo de Sesión

```text
> search python
🔍 Buscando: 'python'

✓ Encontrados 2 resultados:

 1. python_doc.txt
    📄 Ruta: /home/user/shared_files/python_doc.txt
    📊 Score: 0.85 | Tamaño: 1.2 KB

 2. tutorial_python.txt
    📄 Ruta: /home/user/shared_files/tutorial_python.txt
    📊 Score: 0.72 | Tamaño: 3.4 KB

> download python_doc.txt ./downloads/
📥 Descargando: python_doc.txt
   Destino: /home/user/downloads/
✓ Archivo descargado correctamente
  Tamaño: 1.2 KB

> quit
¡Hasta luego! 👋
```

### Cliente Programático

```python
from src.client.client import SearchClient

# Crear cliente
client = SearchClient('localhost', 5000)

# Buscar documentos
results = client.search('python')
for result in results:
    print(f"{result['name']}: {result['score']}")

# Indexar archivo
success = client.index_file('/ruta/al/archivo.txt')

# Descargar archivo
client.download_file('archivo.txt', './downloads/')

# Listar archivos
files = client.list_files()
print(f"Total: {len(files)} archivos")
```

## Pruebas de Integración

Ejecutar todas las pruebas:

```bash
./test_integration.py
```

Esto probará:

- ✅ Búsqueda de documentos
- ✅ Indexación de archivos
- ✅ Descarga de archivos
- ✅ Listado de archivos

## Configuración

### Archivo de Configuración: `config/server_config.json`

```json
{
    "server": {
        "host": "localhost",
        "port": 5000,
        "max_connections": 5
    },
    "indexer": {
        "base_path": "./shared_files",
        "auto_index": true,
        "watch_changes": true
    },
    "transfer": {
        "chunk_size": 4096,
        "max_retries": 3,
        "timeout": 30
    },
    "logging": {
        "level": "INFO",
        "file": "logs/server.log",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    }
}
```

### Opciones de Línea de Comandos

```bash
python3 src/main_server.py [opciones]

Opciones:
  --config PATH       Ruta al archivo de configuración
  --host HOST         Dirección del servidor (ej: 0.0.0.0)
  --port PORT         Puerto del servidor (ej: 5000)
  --index-path PATH   Directorio a indexar
```

## Arquitectura

### Patrones de Diseño

El servidor implementa dos patrones principales:

1. **Repository Pattern** - Abstracción de datos
   - Fácil migración a MongoDB
   - Desacoplamiento de la capa de persistencia

2. **Command Pattern** - Encapsulación de operaciones
   - Extensibilidad para nuevas operaciones
   - Logging y validación centralizada

### Estructura del Código

```text
src/server/server.py
├── DocumentRepository (ABC)         # Interfaz abstracta
│   ├── InMemoryDocumentRepository   # Implementación actual
│   └── MongoDocumentRepository      # Futura implementación
│
├── Command (ABC)                    # Comando base
│   ├── SearchCommand                # Buscar
│   ├── IndexCommand                 # Indexar
│   ├── DownloadCommand              # Descargar
│   └── ListCommand                  # Listar
│
├── CommandFactory                   # Crea comandos
│
└── SearchServer                     # Servidor principal
```

## Operaciones Disponibles

### 1. SEARCH - Buscar Documentos

```python
client.search("python", file_type=".txt")
```

**Respuesta:**

```json
{
    "status": "success",
    "action": "search",
    "count": 2,
    "results": [...]
}
```

### 2. INDEX - Indexar Archivo

```python
client.index_file("/ruta/al/archivo.txt")
```

**Respuesta:**

```json
{
    "status": "success",
    "action": "index",
    "message": "File indexed successfully"
}
```

### 3. DOWNLOAD - Descargar Archivo

```python
client.download_file("documento.txt", "./downloads/")
```

**Respuesta:**

```json
{
    "status": "success",
    "action": "download",
    "file_info": {...}
}
```

### 4. LIST - Listar Archivos

```python
files = client.list_files()
```

**Respuesta:**

```json
{
    "status": "success",
    "action": "list",
    "count": 10,
    "files": [...]
}
```

## Solución de Problemas

### Error: "Connection refused"

El servidor no está ejecutándose:

```bash
./start_server.sh
```

### Error: "No module named 'src'"

Ejecutar desde el directorio raíz:

```bash
cd /home/michell/Proyectos/Distributed-Search-Engine
./client_interactive.py
```

### Error: "File not found"

Verificar que el archivo existe:

```bash
ls -la shared_files/
```

### Ver Logs del Servidor

```bash
tail -f logs/server.log
```

## Documentación Adicional

- 📖 [Arquitectura del Servidor](docs/SERVER_ARCHITECTURE.md)
- 📖 [Estructura del Proyecto](docs/PROJECT_STRUCTURE.md)

## Ejemplos Avanzados

### Búsqueda con Filtro de Tipo

```python
# Solo archivos .txt
results = client.search("importante", file_type=".txt")

# Solo archivos .pdf
results = client.search("reporte", file_type=".pdf")
```

### Indexación Masiva

```python
from pathlib import Path

client = SearchClient('localhost', 5000)

# Indexar todos los archivos en un directorio
directory = Path('/ruta/a/documentos')
for file_path in directory.rglob('*.txt'):
    print(f"Indexando: {file_path}")
    client.index_file(str(file_path))
```

### Descarga Masiva

```python
# Obtener lista de archivos
files = client.list_files()

# Descargar archivos con cierta extensión
for file_info in files:
    if file_info['type'] == '.pdf':
        client.download_file(file_info['name'], './downloads/')
        print(f"Descargado: {file_info['name']}")
```

## Contribuir

1. Fork del repositorio
2. Crear una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commit de cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear un Pull Request

## Licencia

Este proyecto es parte del curso de Sistemas Distribuidos.

## Contacto

Para preguntas o problemas, crear un issue en el repositorio.
