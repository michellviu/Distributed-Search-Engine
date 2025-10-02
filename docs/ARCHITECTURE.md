# Estructura del Proyecto - Versión Centralizada

## Descripción General

Este proyecto implementa un buscador de documentos distribuidos en su versión centralizada. El sistema permite indexar, buscar y transferir archivos a través de una arquitectura cliente-servidor.

## Estructura de Directorios

```text
Distributed-Search-Engine/
├── src/                      # Código fuente principal
│   ├── server/              # Módulo del servidor
│   │   ├── __init__.py
│   │   └── server.py       # Implementación del servidor
│   ├── client/              # Módulo del cliente
│   │   ├── __init__.py
│   │   └── client.py       # Implementación del cliente
│   ├── indexer/             # Módulo de indexación
│   │   ├── __init__.py
│   │   └── indexer.py      # Indexación de documentos
│   ├── search/              # Módulo de búsqueda
│   │   ├── __init__.py
│   │   └── search_engine.py # Motor de búsqueda
│   ├── transfer/            # Módulo de transferencia
│   │   ├── __init__.py
│   │   └── file_transfer.py # Transferencia de archivos
│   ├── utils/               # Utilidades
│   │   ├── __init__.py
│   │   ├── config.py       # Gestión de configuración
│   │   └── logger.py       # Configuración de logging
│   ├── main_server.py      # Punto de entrada del servidor
│   └── main_client.py      # Punto de entrada del cliente
├── config/                  # Archivos de configuración
│   ├── server_config.json  # Configuración del servidor
│   └── client_config.json  # Configuración del cliente
├── tests/                   # Pruebas unitarias
├── docs/                    # Documentación
│   └── ARCHITECTURE.md     # Este archivo
├── requirements.txt         # Dependencias de Python
├── setup.py                # Script de instalación
└── README.md               # Documentación principal
```

## Componentes Principales

### 1. Servidor (`src/server/`)

- **Función**: Gestiona las conexiones de clientes y coordina las búsquedas
- **Características**:
  - Acepta múltiples conexiones concurrentes
  - Procesa solicitudes de búsqueda
  - Coordina la transferencia de archivos

### 2. Cliente (`src/client/`)

- **Función**: Permite a los usuarios buscar y descargar archivos
- **Características**:
  - Envía consultas de búsqueda al servidor
  - Descarga archivos encontrados
  - Manejo de errores de conexión

### 3. Indexador (`src/indexer/`)

- **Función**: Indexa documentos para búsqueda eficiente
- **Características**:
  - Indexa archivos por nombre y tipo
  - Calcula hashes para detectar duplicados
  - Actualización dinámica del índice

### 4. Motor de Búsqueda (`src/search/`)

- **Función**: Procesa consultas y devuelve resultados relevantes
- **Características**:
  - Búsqueda por nombre de archivo
  - Filtrado por tipo de archivo
  - Puntuación de relevancia

### 5. Transferencia de Archivos (`src/transfer/`)

- **Función**: Gestiona la transferencia segura de archivos
- **Características**:
  - Transferencia por chunks
  - Verificación de integridad
  - Manejo de errores de red

### 6. Utilidades (`src/utils/`)

- **Función**: Proporciona funcionalidades comunes
- **Características**:
  - Gestión de configuración (JSON)
  - Sistema de logging configurable
  - Constantes y helpers

## Uso

### Iniciar el Servidor

```bash
# Desde la raíz del proyecto
./start_server.sh

# Alternativa manual
python src/main_server.py --config config/server_config.json

# Tras instalar el paquete (pip install -e .)
search-server --config config/server_config.json
```

### Ejecutar el Cliente

```bash
# Cliente interactivo sin instalación
python src/client/client_interactive.py

# Cliente CLI empaquetado
search-client --query "documento" --host localhost --port 5000

# Cliente programático
python3 src/main_client.py --query "documento"
```

### Descargar un Archivo

```bash
cd src
python main_client.py --download FILE_ID --output ./downloads/file.txt
```

## Configuración

Los archivos de configuración en formato JSON permiten personalizar:

- Dirección y puerto del servidor
- Directorio de archivos compartidos
- Nivel de logging
- Parámetros de transferencia

El servidor utiliza `shared_files/` como base (`auto_index=true`) para indexar automáticamente el contenido cada vez que arranca.

## Características Implementadas

1. ✅ Arquitectura cliente-servidor centralizada
2. ✅ Búsqueda por nombre de archivo
3. ✅ Filtrado por tipo de archivo
4. ✅ Detección de archivos duplicados (por hash)
5. ✅ Transferencia de archivos con verificación
6. ✅ Manejo de errores de conexión
7. ✅ Sistema de logging
8. ✅ Configuración flexible

## Próximos Pasos (Versión Distribuida)

- Implementar arquitectura peer-to-peer
- Descubrimiento automático de nodos
- Replicación de índices
- Selección inteligente de fuentes
- Tolerancia a fallos
