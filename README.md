# Distributed-Search-Engine

📖 **Proyecto de Sistema de Búsqueda Distribuida**

Este proyecto implementa un motor de búsqueda de documentos centralizado, desarrollado como parte del curso de Sistemas Distribuidos.

## Descripción General

El Motor de Búsqueda Distribuida es un sistema para buscar y acceder a documentos a través de múltiples computadoras. Este repositorio contiene la **versión centralizada** del sistema, que implementa una arquitectura cliente-servidor donde:

- Un servidor central gestiona la indexación de documentos y consultas de búsqueda
- Los clientes pueden buscar documentos, indexar archivos y descargarlos
- Los archivos se indexan automáticamente por nombre y tipo para búsquedas eficientes
- Los archivos duplicados se detectan utilizando identificación basada en hash
- El servidor indexa automáticamente `shared_files/` al iniciar

## Características

- 🔍 **Búsqueda de Documentos**: Buscar archivos por nombre y tipo
- 📂 **Indexación Automática**: Indexación automática de directorios compartidos al arranque
- � **Operaciones Múltiples**: Búsqueda, indexación, listado y descarga de archivos
- 🔄 **Transferencia de Archivos**: Descarga confiable con manejo de errores y reintentos
- 🔐 **Detección de Duplicados**: Identificación de archivos duplicados basada en hash
- ⚙️ **Configurable**: Sistema de configuración basado en JSON
- 📝 **Logging**: Registro completo para depuración y monitoreo
- 🧪 **Probado**: Suite completa de pruebas unitarias e integración

## Estructura del Proyecto

```text
Distributed-Search-Engine/
├── src/                      # Código fuente
│   ├── server/              # Implementación del servidor
│   ├── client/              # Implementación del cliente
│   │   └── client_interactive.py  # Cliente interactivo CLI
│   ├── indexer/             # Indexación de documentos
│   ├── search/              # Motor de búsqueda
│   ├── transfer/            # Transferencia de archivos
│   ├── utils/               # Utilidades (config, logging)
│   ├── main_server.py       # Punto de entrada del servidor
│   └── main_client.py       # Punto de entrada del cliente
├── config/                   # Archivos de configuración JSON
├── tests/                    # Pruebas unitarias y de integración
├── docs/                     # Documentación detallada
│   ├── QUICKSTART.md        # Guía de inicio rápido (muy detallada)
│   ├── ARCHITECTURE.md      # Documentación de arquitectura
│   └── PROJECT_STRUCTURE.md # Estructura completa del proyecto
├── shared_files/             # Directorio indexado automáticamente
├── logs/                     # Logs generados en tiempo de ejecución
├── start_server.sh           # Script de inicio rápido del servidor
├── requirements.txt          # Dependencias de Python
└── setup.py                 # Script de instalación con entry points
```

Para documentación detallada de arquitectura, consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Para una guía completa de inicio rápido, ve a [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Requisitos

- Python 3.10 o superior (recomendado)
- `pip` actualizado
- Sin dependencias externas en producción (usa la biblioteca estándar de Python)
- Para desarrollo: `pytest` (instalado con `pip install -e .[dev]`)

## Instalación

### Opción 1: Instalación Editable (Recomendada para desarrollo)

```bash
# Clonar el repositorio
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine

# Crear entorno virtual (opcional pero recomendado)
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar el paquete con herramientas de desarrollo
pip install -e .[dev]
```

Esto instala el paquete y expone los comandos:

- `search-server` - Iniciar el servidor
- `search-client` - Ejecutar el cliente

### Opción 2: Uso Directo sin Instalación

```bash
# Clonar el repositorio
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine

# Instalar solo dependencias mínimas (vacías actualmente)
pip install -r requirements.txt
```

## Uso Rápido

### Iniciar el Servidor

#### Opción 1: Script de Inicio (Más Fácil)

```bash
./start_server.sh
```

El script:

- Crea directorios necesarios (`logs/`, `downloads/`)
- Genera archivos de ejemplo en `shared_files/` si está vacío
- Indexa automáticamente todos los archivos al iniciar
- Inicia el servidor en `localhost:5000`

#### Opción 2: Comando Directo

```bash
# Desde el directorio raíz del proyecto
python3 src/main_server.py --config config/server_config.json

# O, si instalaste el paquete:
search-server --config config/server_config.json
```

**Opciones del Servidor:**

- `--config <path>`: Ruta al archivo de configuración
- `--host <address>`: Dirección del servidor (default: `localhost`)
- `--port <number>`: Puerto del servidor (default: `5000`)
- `--index-path <path>`: Directorio a indexar (default: `shared_files`)

### Usar el Cliente

### Cliente Interactivo (Recomendado)

```bash
python3 src/client/client_interactive.py
```

Comandos disponibles en la sesión interactiva:

- `search <query> [extension]` - Buscar documentos
- `list` - Listar todos los archivos indexados
- `index <ruta>` - Indexar un archivo nuevo
- `download <nombre> <destino>` - Descargar archivo
- `quit` - Salir

### Cliente CLI (después de instalar el paquete)

```bash
# Buscar archivos
search-client --query "python"

# Descargar un archivo
search-client --download python_doc.txt --output ./downloads/

# Con opciones de conexión personalizadas
search-client --query "documento" --host localhost --port 5000
```

### Cliente Programático (sin instalación)

```bash
# Buscar archivos
python3 src/main_client.py --query "documento"

# Descargar un archivo
python3 src/main_client.py --download archivo.txt --output ./downloads/archivo.txt
```

**Opciones del Cliente:**

- `--config <path>`: Ruta al archivo de configuración
- `--host <address>`: Dirección del servidor (default: `localhost`)
- `--port <number>`: Puerto del servidor (default: `5000`)
- `--query <text>`: Consulta de búsqueda
- `--download <name>`: Nombre del archivo a descargar
- `--output <path>`: Ruta destino para el archivo descargado

## Configuración

Los archivos de configuración están ubicados en el directorio `config/`:

- `server_config.json`: Configuración del servidor (host, puerto, indexación)
- `client_config.json`: Configuración del cliente (conexión, logging)

**Ejemplo de configuración del servidor:**

```json
{
    "server": {
        "host": "localhost",
        "port": 5000,
        "max_connections": 5
    },
    "indexer": {
        "base_path": "shared_files",
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

**Características de Configuración:**

- **Auto-indexación**: El servidor indexa automáticamente `shared_files/` al iniciar
- **Rutas relativas**: Todas las rutas son relativas al directorio raíz del proyecto
- **Transferencia configurable**: Tamaño de chunk, reintentos y timeout ajustables
- **Logging flexible**: Nivel de log configurable (DEBUG, INFO, WARNING, ERROR)

## Desarrollo

### Ejecutar Pruebas

```bash
# Instalar dependencias de prueba (si no usaste pip install -e .[dev])
pip install pytest pytest-cov

# Ejecutar todas las pruebas
pytest

# Ejecutar pruebas con cobertura
pytest --cov=src tests/

# Ejecutar pruebas específicas
pytest tests/test_indexer.py
pytest tests/test_search.py

# Ejecutar prueba de integración guiada
python3 tests/test_integration.py
```

### Estructura de las Pruebas

- `tests/test_indexer.py` - Pruebas del módulo de indexación
- `tests/test_search.py` - Pruebas del motor de búsqueda
- `tests/test_integration.py` - Pruebas de integración extremo a extremo

### Añadir Archivos para Indexar

Simplemente coloca archivos en el directorio `shared_files/` y reinicia el servidor:

```bash
cp mi_documento.txt shared_files/
./start_server.sh
```

El servidor los indexará automáticamente al iniciar.

## Especificaciones del Proyecto

Este proyecto implementa un sistema de búsqueda de documentos distribuido con las siguientes características:

- **Arquitectura Centralizada**: Modelo cliente-servidor con servidor central de indexación
- **Búsqueda de Archivos**: Búsqueda por nombre de archivo y tipo
- **Indexación Automática**: El servidor indexa `shared_files/` al arranque
- **Operaciones Múltiples**: SEARCH, INDEX, DOWNLOAD, LIST
- **Detección de Duplicados**: Identifica archivos duplicados con diferentes nombres usando hash
- **Manejo de Errores**: Manejo robusto de errores de red y transferencia de archivos
- **Búsqueda Eficiente**: Algoritmos de búsqueda optimizados con puntuación de relevancia
- **Transferencia Confiable**: Transferencia por chunks con verificación de integridad y reintentos
- **Patrones de Diseño**: Repository Pattern y Command Pattern para extensibilidad

Para las especificaciones completas del proyecto, consulta [buscador.pdf](buscador.pdf).

## Documentación

- 📖 [**QUICKSTART.md**](docs/QUICKSTART.md) - Guía detallada de instalación, configuración y uso
- 📖 [**ARCHITECTURE.md**](docs/ARCHITECTURE.md) - Documentación de arquitectura y componentes
- 📖 [**PROJECT_STRUCTURE.md**](docs/PROJECT_STRUCTURE.md) - Estructura completa y descripción de módulos

## Mejoras Futuras

- Arquitectura distribuida peer-to-peer
- Descubrimiento automático de nodos
- Replicación de índices entre nodos
- Selección inteligente de fuentes para descarga de archivos
- Mecanismos de tolerancia a fallos
- Búsqueda por contenido (no solo nombre)
- Interfaz web

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| `Connection refused` | Asegúrate de que el servidor esté ejecutándose con `./start_server.sh` |
| `No module named 'src'` | Ejecuta los comandos desde el directorio raíz del proyecto |
| `Permission denied` | Otorga permisos de ejecución: `chmod +x start_server.sh` |
| Archivos no aparecen | Verifica que estén en `shared_files/` y reinicia el servidor |
| Ver logs del servidor | `tail -f logs/server.log` |

## Licencia

Este proyecto es creado con fines educativos como parte del curso de Sistemas Distribuidos.

## Contribuidores

Desarrollado como parte del proyecto del curso de Sistemas Distribuidos.

---

**¿Necesitas ayuda?** Consulta la [Guía de Inicio Rápido](docs/QUICKSTART.md) para instrucciones detalladas.
