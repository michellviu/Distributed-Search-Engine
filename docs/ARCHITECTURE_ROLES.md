# Arquitectura del Sistema Distribuido

## Descripción General

El sistema distribuido utiliza **dos roles claramente separados**:

1. **Nodo Coordinador (Coordinator Node)**: Gestiona el cluster, NO almacena datos
2. **Nodo de Procesamiento (Processing Node)**: Almacena datos y ejecuta búsquedas

```
                         ┌─────────────────────────────────────┐
                         │           COORDINADOR               │
                         │  - Registro de nodos (ID -> IP)     │
                         │  - Índice de archivos (file -> nodes)│
                         │  - Heartbeat monitoring             │
                         │  - Balanceo de carga                │
                         │  - Asignación por carga             │
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
    │    datos        │         │    datos        │         │    datos        │
    │  - Indexación   │         │  - Indexación   │         │  - Indexación   │
    │  - Búsqueda     │         │  - Búsqueda     │         │  - Búsqueda     │
    │    local        │         │    local        │         │    local        │
    └─────────────────┘         └─────────────────┘         └─────────────────┘
```

## Asignación de Almacenamiento

El coordinador:

1. **Mantiene un índice explícito** de qué archivos están en qué nodos
2. **Asigna nuevos archivos por balanceo de carga**: los nodos con menos archivos reciben los nuevos
3. **Recibe confirmación** de los nodos cuando almacenan un archivo

### Flujo de Almacenamiento

```
1. Cliente solicita almacenar archivo al coordinador
2. Coordinador consulta su índice:
   - Si el archivo existe: devuelve las ubicaciones actuales
   - Si es nuevo: selecciona los N nodos menos cargados
3. Coordinador devuelve lista de nodos destino al cliente
4. Cliente envía archivo a cada nodo destino
5. Cada nodo almacena, indexa, y notifica al coordinador
6. Coordinador actualiza su índice de ubicaciones
```

## Componentes

### 1. Nodo Coordinador (`CoordinatorNode`)

**Ubicación:** `src/distributed/node/coordinator_node.py`

**Responsabilidades:**

- Mantener registro de nodos de procesamiento (mapeo ID -> IP)
- Mantener índice de archivos (mapeo archivo -> nodos)
- Monitorear la salud de los nodos (heartbeats)
- Coordinar búsquedas distribuidas
- Asignar almacenamiento por balanceo de carga
- Verificar y mantener factor de replicación

**Iniciar:**
```bash
python src/main_coordinator.py --port 5000
```

### 2. Nodo de Procesamiento (`ProcessingNode`)

**Ubicación:** `src/distributed/node/processing_node.py`

**Responsabilidades:**

- Almacenar archivos indexados
- Ejecutar búsquedas locales
- Responder a queries del coordinador
- Enviar heartbeats al coordinador
- Notificar al coordinador cuando almacena un archivo
- Replicar archivos a otros nodos cuando se solicite

**Iniciar:**
```bash
python src/main_processing.py --port 5001 --coordinator localhost:5000
```

### 3. Registro de Nodos (`NodeRegistry`)

**Ubicación:** `src/distributed/registry/node_registry.py`

El registro de nodos proporciona:

- Mapeo simple ID -> (IP, Puerto)
- Índice de archivos por nodo
- Selección de nodos por balanceo de carga
- Estadísticas de replicación

## Flujo de Operaciones

### Registro de Nodo de Procesamiento

```
1. Nodo de procesamiento inicia
2. Se conecta al coordinador y envía 'register'
3. Coordinador registra nodo en NodeRegistry
4. Nodo comienza a enviar heartbeats periódicos
```

### Búsqueda de Archivos (OPTIMIZADA)

**La búsqueda es por nombre y extensión de archivo, NO por contenido.**

El coordinador conoce todos los nombres de archivos registrados, por lo que
puede hacer la búsqueda **localmente** sin consultar los nodos de procesamiento:

```
1. Cliente envía query al coordinador (ej: "test", ".txt")
2. Coordinador busca en su registro de archivos (local, O(n))
   - Coincidencia por substring en nombre
   - Filtro opcional por extensión
3. Coordinador devuelve resultados con ubicaciones de nodos
4. Si el cliente quiere descargar, contacta directamente al nodo
```

**Ventajas de esta optimización:**
- No hay comunicación con nodos de procesamiento para búsquedas
- Latencia mínima (búsqueda local)
- No importa cuántos nodos hay, la búsqueda es igual de rápida
- Los nodos de procesamiento solo se contactan para descargar archivos

### Almacenamiento de Archivo

```
1. Cliente solicita almacenar archivo
2. Coordinador selecciona nodos por balanceo de carga
3. Cliente envía archivo a los nodos seleccionados
4. Cada nodo almacena e indexa el archivo
5. Cada nodo notifica al coordinador (file_stored)
6. Coordinador actualiza su índice de ubicaciones
```

### Replicación Automática

```
1. Coordinador verifica periódicamente el factor de replicación
2. Si un archivo tiene menos réplicas de las necesarias:
   a. Selecciona un nodo fuente (que tiene el archivo)
   b. Selecciona nodos destino (menos cargados)
   c. Solicita al nodo fuente que replique a los destinos
3. Los nodos destino notifican al coordinador cuando terminan
```

## Despliegue con Docker

### Usando docker-compose

```bash
# Construir imágenes
docker-compose -f docker-compose-roles.yml build

# Iniciar cluster (1 coordinador + 3 nodos de procesamiento)
docker-compose -f docker-compose-roles.yml up -d

# Ver logs
docker-compose -f docker-compose-roles.yml logs -f

# Escalar nodos de procesamiento (ejemplo: 5 nodos)
docker-compose -f docker-compose-roles.yml up -d --scale processing1=1 --scale processing2=1 --scale processing3=1
```

### Dockerfiles

- `Dockerfile.coordinator`: Para nodos coordinadores (sin directorio de datos)
- `Dockerfile.processing`: Para nodos de procesamiento (con directorio de datos)

## Configuración

### Variables de Entorno - Coordinador

| Variable | Descripción | Default |
|----------|-------------|---------|
| `COORDINATOR_ID` | ID único del coordinador | Auto-generado |
| `COORDINATOR_PORT` | Puerto TCP | 5000 |

### Variables de Entorno - Nodo de Procesamiento

| Variable | Descripción | Default |
|----------|-------------|---------|
| `NODE_ID` | ID único del nodo | Auto-generado |
| `NODE_PORT` | Puerto TCP | 5001 |
| `INDEX_PATH` | Directorio de archivos | /app/shared_files |
| `COORDINATOR_ADDRESS` | Dirección del coordinador (host:port) | - |

## Tolerancia a Fallos

### Resumen de Tolerancia

| Componente | Tolerancia | Mecanismo |
|------------|------------|-----------|
| Archivos | Caída de 2 nodos | Replicación factor 3 + re-replicación automática |
| Coordinador | Caída de coordinador | Múltiples coordinadores con elección de líder |
| Cliente | Caída del coordinador actual | Failover automático a otro coordinador |

### Caída de un Nodo de Procesamiento

Con **factor de replicación 3**, el sistema tolera la **caída de hasta 2 nodos** sin pérdida de datos:

```
1. Coordinador detecta ausencia de heartbeats (15 segundos)
2. Coordinador verifica con health check directo
3. Coordinador elimina nodo del registro y DNS
4. Coordinador identifica archivos afectados
5. RE-REPLICACIÓN URGENTE:
   - Identifica archivos con < 3 réplicas
   - Selecciona nodo fuente (que tiene el archivo)
   - Selecciona nodo destino (menos cargado)
   - Solicita replicación en paralelo
6. Archivos vuelven a tener 3 réplicas
```

### Caída de un Coordinador

El sistema soporta **múltiples coordinadores** con elección de líder usando **algoritmo Bully**:

```
Algoritmo Bully - El nodo con MAYOR ID gana:

    ┌─────────────────┐
    │   LÍDER         │ ◄── Mayor ID, procesa requests
    │   Coordinador 3 │
    └────────┬────────┘
             │ Replica estado
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐     ┌─────────┐
│ FOLLOWER│     │ FOLLOWER│
│ Coord 1 │     │ Coord 2 │
└─────────┘     └─────────┘
```

**Algoritmo Bully - Flujo de elección:**
```
1. Nodo P detecta que el líder no responde
2. P envía mensaje ELECTION a todos los nodos con ID > P
3. Si P recibe OK de algún nodo:
   - P espera mensaje COORDINATOR (timeout 8s)
   - Si no llega COORDINATOR, reinicia elección
4. Si P NO recibe OK (nadie con mayor ID responde):
   - P se declara LÍDER
   - P envía mensaje COORDINATOR a TODOS los nodos
5. Todos los nodos aceptan al nuevo líder
```

**Mensajes del algoritmo Bully:**
| Mensaje | Descripción |
|---------|-------------|
| `ELECTION` | Nodo inicia elección, enviado a nodos con mayor ID |
| `OK` | Respuesta a ELECTION: "hay alguien con mayor ID" |
| `COORDINATOR` | Anuncio de nuevo líder a todos los nodos |

### Cliente con Failover

El cliente distribuido mantiene lista de coordinadores y reconecta automáticamente:

```python
from src.client.distributed_client import DistributedClientWithFailover

# Cliente conoce múltiples coordinadores
client = DistributedClientWithFailover([
    "coordinator1:5000",
    "coordinator2:5000",
    "coordinator3:5000"
])

# Las operaciones tienen failover automático
results = client.search("documento")  # Si coord1 cae, intenta con coord2
```

**Características del cliente:**
- Reintentos con backoff exponencial
- Detección de líder
- Health checks periódicos
- Reconexión transparente

### Persistencia del Estado

El coordinador persiste su estado a disco para recuperarse de reinicios:

```
Estado persistido:
- Registro de nodos de procesamiento
- Índice de ubicación de archivos
- Estadísticas

Ubicación: /app/state/
- nodes_{coordinator_id}.json
- files_{coordinator_id}.json
- meta_{coordinator_id}.json
```

**Flujo de recuperación:**
1. Coordinador inicia y carga estado desde disco
2. Verifica qué nodos siguen vivos (health checks)
3. Actualiza registro según respuestas
4. Dispara re-replicación si es necesario

### Factor de Replicación

- Por defecto: 3 réplicas por archivo
- Verificación periódica cada 30 segundos
- Replicación automática cuando faltan réplicas

## API del Coordinador

### Acciones Soportadas

| Acción | Descripción |
|--------|-------------|
| `register` | Registrar nodo de procesamiento |
| `heartbeat` | Actualizar estado de nodo |
| `search` | Búsqueda distribuida |
| `store` | Determinar nodos para almacenamiento (por balanceo) |
| `file_stored` | Confirmar almacenamiento de archivo |
| `get_nodes` | Listar nodos activos |
| `get_file_locations` | Obtener nodos donde está un archivo |
| `health` | Health check |
| `cluster_status` | Estado completo del cluster |

### Ejemplo de Request/Response

**Almacenamiento (sin consistent hashing):**
```json
// Request
{
    "action": "store",
    "file_name": "document.txt",
    "file_size": 1024
}

// Response - nodos seleccionados por balanceo de carga
{
    "status": "success",
    "file_name": "document.txt",
    "target_nodes": [
        {"node_id": "proc1", "host": "10.0.0.2", "port": 5001},
        {"node_id": "proc2", "host": "10.0.0.3", "port": 5001},
        {"node_id": "proc3", "host": "10.0.0.4", "port": 5001}
    ],
    "replication_factor": 3,
    "already_exists": false
}
```

**Confirmación de almacenamiento:**
```json
// Request (del nodo de procesamiento al coordinador)
{
    "action": "file_stored",
    "file_name": "document.txt",
    "node_id": "proc1"
}

// Response
{
    "status": "success",
    "message": "File location registered: document.txt -> proc1"
}
```

## Ejemplo de Uso Local

### Terminal 1 (Coordinador):
```bash
cd src
python main_coordinator.py -n coord1 -p 5000
```

### Terminal 2 (Nodo de Procesamiento 1):
```bash
cd src
python main_processing.py -n proc1 -p 5001 -c localhost:5000
```

### Terminal 3 (Nodo de Procesamiento 2):
```bash
cd src
python main_processing.py -n proc2 -p 5002 -c localhost:5000
```

### Terminal 4 (Cliente):
```bash
cd src
python main_client.py -H localhost -p 5000
# El cliente se conecta al coordinador
```

## Estructura de Archivos

```
src/
├── distributed/
│   ├── __init__.py
│   ├── node/
│   │   ├── __init__.py
│   │   ├── coordinator_node.py   # Nodo coordinador
│   │   └── processing_node.py    # Nodo de procesamiento
│   └── registry/
│       ├── __init__.py
│       └── node_registry.py      # Registro de nodos (sin CHORD)
├── main_coordinator.py           # Script para iniciar coordinador
└── main_processing.py            # Script para iniciar nodo de procesamiento
```
