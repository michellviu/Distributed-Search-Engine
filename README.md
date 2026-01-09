# Distributed-Search-Engine

📖 **Sistema de Búsqueda Distribuida**

Motor de búsqueda de documentos distribuido desarrollado para el curso de Sistemas Distribuidos.

## Descripción General

El sistema implementa una arquitectura **Coordinador/Nodos de Procesamiento** donde:

- **Nodo Coordinador**: Gestiona el cluster, mantiene el índice de ubicaciones, NO almacena datos
- **Nodos de Procesamiento**: Almacenan archivos, ejecutan búsquedas locales, reportan al coordinador
- **Replicación**: Cada archivo se replica en N nodos (por defecto N=3) para tolerancia a fallos
- **Balanceo de Carga**: El coordinador asigna archivos a los nodos menos cargados

## Arquitectura

```
                    ┌─────────────────────────────────────┐
                    │           COORDINADOR               │
                    │  - Registro de nodos (ID -> IP)     │
                    │  - Índice de archivos (file -> nodes)│
                    │  - Heartbeat monitoring             │
                    │  - Balanceo de carga                │
                    │  - CHORD DNS (localización)         │
                    │  - Quorum (consistencia)            │
                    │  - NO ALMACENA DATOS                │
                    └────────────────┬────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  PROCESAMIENTO  │         │  PROCESAMIENTO  │         │  PROCESAMIENTO  │
│     Nodo 1      │         │     Nodo 2      │         │     Nodo 3      │
│  - Almacena     │         │  - Almacena     │         │  - Almacena     │
│    archivos     │         │    archivos     │         │    archivos     │
│  - Indexación   │         │  - Indexación   │         │  - Indexación   │
│  - Búsqueda     │         │  - Búsqueda     │         │  - Búsqueda     │
│    local        │         │    local        │         │    local        │
│  - Heartbeats   │         │  - Heartbeats   │         │  - Heartbeats   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

## Características Principales

### 🌐 Arquitectura Distribuida
- **Roles Separados**: Coordinador (gestión) y Procesamiento (almacenamiento)
- **CHORD DNS**: Resolución eficiente de nodos O(log N)
- **Elección de Líder**: Algoritmo Bully para múltiples coordinadores
- **Auto-registro**: Los nodos de procesamiento se registran automáticamente

### 🛡️ Tolerancia a Fallos
- **Replicación**: Factor configurable (default: 3 réplicas por archivo)
- **Heartbeats**: Monitoreo continuo de salud de nodos
- **Quorum**: Consistencia configurable (ONE, QUORUM, ALL)
- **Docker Swarm**: Reinicio automático de servicios caídos

### 🔍 Funcionalidades
- **Búsqueda Distribuida**: Consultas optimizadas usando índice de ubicaciones
- **Indexación Automática**: Al iniciar, cada nodo indexa sus archivos locales
- **Descarga Resiliente**: Obtener archivos desde cualquier réplica disponible
- **Filtrado por Tipo**: Búsqueda por extensión de archivo

## Estructura del Proyecto

```
Distributed-Search-Engine/
├── src/
│   ├── distributed/              # Sistema distribuido
│   │   ├── node/                 # Nodos del sistema
│   │   │   ├── coordinator_node.py   # Nodo coordinador
│   │   │   └── processing_node.py    # Nodo de procesamiento
│   │   ├── registry/             # Registro de nodos
│   │   │   └── node_registry.py      # Gestión de nodos y archivos
│   │   ├── dns/                  # Sistema de nombres
│   │   │   └── chord_dns.py          # CHORD DNS para localización
│   │   ├── consistency/          # Consistencia de datos
│   │   │   └── quorum.py             # Protocolo de quorum
│   │   ├── coordination/         # Coordinación multi-coordinador
│   │   │   └── coordinator_cluster.py # Algoritmo Bully
│   │   └── persistence/          # Persistencia de estado
│   ├── server/                   # Servidor TCP base
│   ├── client/                   # Clientes (GUI e interactivo)
│   ├── indexer/                  # Indexación de documentos
│   ├── search/                   # Motor de búsqueda local
│   ├── transfer/                 # Transferencia de archivos
│   ├── main_distributed.py       # Punto de entrada principal
│   ├── main_coordinator.py       # Iniciar solo coordinador
│   └── main_processing.py        # Iniciar solo procesamiento
├── config/                       # Configuración JSON
├── docs/                         # Documentación
├── shared_files/                 # Archivos de prueba
├── Dockerfile.distributed        # Imagen Docker unificada
├── docker-compose.distributed.yml # Stack de Docker Swarm
├── deploy-distributed.sh         # Script de despliegue
└── docker-entrypoint.sh          # Entrypoint del contenedor
```

## Requisitos

- Python 3.9+
- Docker Engine 20.10+ (para despliegue con Swarm)
- CustomTkinter (opcional, para GUI moderna)

## Instalación y Uso

### Opción 1: Docker Swarm (Recomendado)

```bash
# Desplegar cluster (1 coordinador + 3 nodos de procesamiento)
./deploy-distributed.sh

# Escalar a más nodos
docker service scale search_processing=5

# Ver estado
docker stack services search

# Ver logs
docker service logs -f search_coordinator
```

### Opción 2: Ejecución Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Terminal 1: Iniciar coordinador
python -m src.main_distributed --role coordinator --port 5000

# Terminal 2: Iniciar nodo de procesamiento
python -m src.main_distributed --role processing --port 5001 \
    --coordinator-host localhost --coordinator-port 5000

# Terminal 3: Otro nodo de procesamiento
python -m src.main_distributed --role processing --port 5002 \
    --coordinator-host localhost --coordinator-port 5000
```

### Uso del Cliente GUI

```bash
# Instalar CustomTkinter (opcional, para interfaz moderna)
pip install customtkinter

# Ejecutar GUI
python -m src.client.client_gui

# O usar el script
./start_client_gui.sh
```

## Componentes del Sistema

### 1. CoordinatorNode (`src/distributed/node/coordinator_node.py`)
- Mantiene registro de nodos de procesamiento
- Índice centralizado de ubicación de archivos
- Monitoreo de salud via heartbeats
- Coordina búsquedas distribuidas (optimizadas)
- Asigna almacenamiento por balanceo de carga
- **NO almacena datos**

### 2. ProcessingNode (`src/distributed/node/processing_node.py`)
- Almacena archivos indexados localmente
- Ejecuta búsquedas en su índice local
- Envía heartbeats periódicos al coordinador
- Se auto-registra al iniciar
- **SÍ almacena datos**

### 3. NodeRegistry (`src/distributed/registry/node_registry.py`)
- Mapeo ID → (IP, Puerto) de nodos
- Índice inverso: archivo → lista de nodos
- Asignación por balanceo de carga

### 4. ChordDNS (`src/distributed/dns/chord_dns.py`)
- Resolución de nombres basada en CHORD
- Nodos virtuales para distribución uniforme
- Finger table para búsquedas O(log N)

### 5. QuorumManager (`src/distributed/consistency/quorum.py`)
- Niveles: ONE, QUORUM, ALL
- Control de versiones de archivos
- Escrituras/lecturas consistentes

### 6. CoordinatorCluster (`src/distributed/coordination/coordinator_cluster.py`)
- Soporte para múltiples coordinadores
- Algoritmo Bully para elección de líder
- Replicación de estado entre coordinadores

## Protocolo de Comunicación

Todas las comunicaciones usan TCP con formato:
```
[8 bytes: longitud del mensaje][JSON payload]
```

### Acciones del Coordinador
| Acción | Descripción |
|--------|-------------|
| `health` | Verificar estado del coordinador |
| `cluster_status` | Estado completo del cluster |
| `search` | Buscar archivos (query, file_type) |
| `list` | Listar todos los archivos |
| `store` | Almacenar nuevo archivo |
| `download` | Descargar archivo |
| `register_node` | Registrar nodo de procesamiento |

## Documentación Adicional

- 📄 [REPORT.md](REPORT.md) - Informe técnico detallado
- 🐳 [docs/DOCKER_SWARM_DEPLOY.md](docs/DOCKER_SWARM_DEPLOY.md) - Guía de Docker Swarm
- 🖥️ [docs/GUI_CLIENT.md](docs/GUI_CLIENT.md) - Uso del cliente gráfico

## Licencia

Proyecto académico - Curso de Sistemas Distribuidos
