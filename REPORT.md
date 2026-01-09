# Informe de Diseño: Sistema de Búsqueda Distribuido

## 1. Arquitectura

### Diseño del Sistema

El sistema utiliza una arquitectura **Coordinador/Nodos de Procesamiento** con roles claramente separados:

1. **Nodo Coordinador**: Gestiona el cluster, mantiene metadatos, NO almacena datos
2. **Nodos de Procesamiento**: Almacenan archivos, ejecutan búsquedas locales

### Diagrama de Arquitectura

```
                    ┌─────────────────────────────────────┐
                    │           COORDINADOR               │
                    │  - NodeRegistry (nodos activos)     │
                    │  - Índice archivo → nodos           │
                    │  - CHORD DNS (localización)         │
                    │  - QuorumManager (consistencia)     │
                    │  - Heartbeat Monitor                │
                    │  - Balanceo de carga                │
                    └────────────────┬────────────────────┘
                                     │ TCP (puerto 5000)
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  PROCESAMIENTO  │         │  PROCESAMIENTO  │         │  PROCESAMIENTO  │
│  - SearchEngine │         │  - SearchEngine │         │  - SearchEngine │
│  - Indexer      │         │  - Indexer      │         │  - Indexer      │
│  - FileTransfer │         │  - FileTransfer │         │  - FileTransfer │
│  - Heartbeats   │         │  - Heartbeats   │         │  - Heartbeats   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Roles del Sistema

| Rol | Responsabilidades | Almacena Datos |
|-----|-------------------|----------------|
| **Coordinador** | Registro de nodos, índice de archivos, balanceo de carga, coordinar búsquedas | NO |
| **Procesamiento** | Almacenar archivos, indexar, ejecutar búsquedas locales, heartbeats | SÍ |
| **Cliente** | Conectar al coordinador, realizar búsquedas/descargas/indexación | NO |

---

## 2. Componentes Principales

### 2.1 CoordinatorNode (`src/distributed/node/coordinator_node.py`)

Nodo central que gestiona el cluster sin almacenar datos.

**Subcomponentes:**
- `NodeRegistry`: Mapeo node_id → (IP, puerto) y archivo → lista de nodos
- `ChordDNS`: Resolución de nombres con finger table O(log N)
- `QuorumManager`: Protocolo de quorum para consistencia

**Funciones principales:**
```python
- register_node(node_id, host, port, files)  # Registrar nodo de procesamiento
- handle_search(query, file_type)            # Coordinar búsqueda distribuida
- handle_store(filename, content)            # Asignar nodos y distribuir archivo
- handle_download(file_id)                   # Obtener archivo de un nodo
- monitor_heartbeats()                       # Detectar nodos caídos
```

### 2.2 ProcessingNode (`src/distributed/node/processing_node.py`)

Nodo que almacena y procesa datos localmente.

**Subcomponentes:**
- `SearchEngine`: Motor de búsqueda local
- `DocumentIndexer`: Indexación de documentos
- `FileTransfer`: Transferencia de archivos

**Funciones principales:**
```python
- auto_index()                    # Indexar archivos locales al iniciar
- handle_search(query, file_type) # Búsqueda en índice local
- handle_store(filename, content) # Almacenar archivo recibido
- handle_download(file_id)        # Enviar archivo solicitado
- send_heartbeat()                # Notificar salud al coordinador
```

### 2.3 NodeRegistry (`src/distributed/registry/node_registry.py`)

Registro de nodos y ubicación de archivos.

**Estructuras de datos:**
```python
nodes: Dict[str, NodeInfo]           # node_id → información del nodo
file_locations: Dict[str, Set[str]]  # filename → set de node_ids
```

**Funciones principales:**
```python
- register_node(node_id, host, port)     # Registrar nodo
- get_nodes_for_storage(replication_factor)  # Nodos menos cargados
- register_file(filename, node_id)       # Registrar ubicación de archivo
- get_file_locations(filename)           # Obtener nodos con el archivo
```

### 2.4 ChordDNS (`src/distributed/dns/chord_dns.py`)

Sistema de nombres basado en CHORD para localización de nodos.

**Características:**
- Nodos virtuales (3 por nodo real) para distribución uniforme
- Finger table para búsquedas O(log N)
- Solo se usa para localizar nodos, NO para asignar almacenamiento

### 2.5 QuorumManager (`src/distributed/consistency/quorum.py`)

Protocolo de quorum para consistencia de datos replicados.

**Niveles de consistencia:**
| Nivel | Descripción |
|-------|-------------|
| `ONE` | Al menos 1 nodo confirma |
| `QUORUM` | Mayoría de réplicas (N/2 + 1) |
| `ALL` | Todas las réplicas confirman |

### 2.6 CoordinatorCluster (`src/distributed/coordination/coordinator_cluster.py`)

Soporte para múltiples coordinadores con elección de líder.

**Algoritmo Bully:**
1. Nodo detecta que el líder cayó
2. Envía ELECTION a nodos con ID mayor
3. Si recibe OK, espera
4. Si no recibe OK, se declara líder
5. Envía COORDINATOR a todos

---

## 3. Procesos y Concurrencia

### Modelo de Concurrencia

El sistema usa **Threading** para manejar múltiples conexiones y tareas:

| Thread | Función |
|--------|---------|
| **Main** | Inicialización y servidor TCP |
| **TCP Handler** | Un thread por conexión entrante |
| **Heartbeat Sender** | Envío periódico de heartbeats (procesamiento) |
| **Heartbeat Monitor** | Verificación de nodos (coordinador) |
| **Replication Checker** | Verificar factor de replicación (coordinador) |

### Sincronización

- `threading.RLock` para acceso a estructuras compartidas
- Operaciones atómicas en registros

---

## 4. Comunicación

### Protocolo TCP

Todas las comunicaciones usan TCP con el formato:
```
[8 bytes ASCII: longitud][payload JSON]
```

### Mensajes del Coordinador

```python
# Registro de nodo
{"action": "register_node", "node_id": "...", "host": "...", "port": 5000, "files": [...]}

# Búsqueda
{"action": "search", "query": "python", "file_type": ".txt"}

# Almacenar archivo
{"action": "store", "filename": "doc.txt", "file_content": "<base64>"}

# Descargar archivo
{"action": "download", "file_id": "doc.txt"}

# Estado del cluster
{"action": "cluster_status"}

# Heartbeat
{"action": "heartbeat", "node_id": "...", "files": [...]}
```

### Mensajes del Procesamiento

```python
# Búsqueda local
{"action": "search", "query": "...", "file_type": "..."}

# Almacenar
{"action": "store", "filename": "...", "file_content": "<base64>"}

# Descargar
{"action": "download", "file_id": "..."}
```

---

## 5. Consistencia y Replicación

### Estrategia de Replicación

- **Factor de replicación**: Configurable (default: 3)
- **Asignación**: Por balanceo de carga (nodos menos cargados)
- **Verificación**: Thread periódico verifica factor de replicación

### Flujo de Almacenamiento

```
1. Cliente envía archivo al Coordinador
2. Coordinador selecciona N nodos menos cargados
3. Coordinador envía archivo a cada nodo seleccionado
4. Cada nodo almacena, indexa, y confirma
5. Coordinador actualiza índice de ubicaciones
6. Coordinador responde al cliente con resultado
```

### Quorum

```python
# Escritura con quorum QUORUM (mayoría)
required = replication_factor // 2 + 1  # Ej: 3 réplicas → 2 confirmaciones

# Lectura con quorum ONE (cualquier réplica)
# Se lee del primer nodo disponible
```

---

## 6. Tolerancia a Fallos

### Detección de Fallos

| Mecanismo | Frecuencia | Acción |
|-----------|------------|--------|
| **Heartbeats** | Cada 5 segundos | Nodo envía heartbeat al coordinador |
| **Timeout** | 15 segundos | Nodo marcado como inactivo |
| **Health Check** | Bajo demanda | Cliente verifica coordinador |

### Recuperación

| Fallo | Respuesta |
|-------|-----------|
| **Nodo de procesamiento cae** | Datos disponibles en réplicas, coordinador actualiza registro |
| **Coordinador cae (Docker Swarm)** | Swarm reinicia automáticamente, nodos se re-registran |
| **Coordinador cae (múltiples coords)** | Algoritmo Bully elige nuevo líder |

### Docker Swarm

```yaml
deploy:
  restart_policy:
    condition: on-failure
    delay: 5s
    max_attempts: 3
```

---

## 7. Despliegue con Docker

### Arquitectura de Despliegue

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Swarm Cluster                      │
├─────────────────────────────────────────────────────────────┤
│   ┌─────────────────┐                                        │
│   │   Coordinator   │ ◄── Puerto 5000 expuesto               │
│   │   (1 réplica)   │                                        │
│   └────────┬────────┘                                        │
│            │                                                 │
│   ┌────────┴────────────────────────────────────┐           │
│   │              Overlay Network                 │           │
│   │            (search-network)                  │           │
│   └─────────┬───────────┬───────────┬───────────┘           │
│             │           │           │                        │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│   │ Processing  │ │ Processing  │ │ Processing  │           │
│   │   Node 1    │ │   Node 2    │ │   Node 3    │           │
│   └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Volúmenes

| Volumen | Uso |
|---------|-----|
| `shared-files` | Archivos iniciales (solo lectura) |
| `processing-data` | Datos de nodos de procesamiento |
| `coordinator-logs` | Logs del coordinador |
| `processing-logs` | Logs de procesamiento |

### Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `NODE_ROLE` | `coordinator` o `processing` | `processing` |
| `NODE_ID` | ID único del nodo | Auto-generado |
| `NODE_PORT` | Puerto TCP | `5000` |
| `COORDINATOR_HOST` | Host del coordinador | `coordinator` |
| `INDEX_PATH` | Directorio de archivos | `/home/app/data` |
| `AUTO_INDEX` | Indexar al iniciar | `true` |

---

## 8. Cliente GUI

### Características

- Interfaz moderna con CustomTkinter (o Tkinter estándar)
- Búsqueda con filtro por tipo de archivo
- Listado de archivos del cluster
- Descarga de archivos
- Indexación de nuevos archivos
- Reconexión automática

### Uso

```bash
# Con CustomTkinter (interfaz moderna)
pip install customtkinter
python -m src.client.client_gui

# Sin CustomTkinter (interfaz estándar)
python -m src.client.client_gui
```

---

## 9. Resumen de Tecnologías

| Categoría | Tecnología |
|-----------|------------|
| **Lenguaje** | Python 3.9+ |
| **Comunicación** | TCP Sockets + JSON |
| **Concurrencia** | threading |
| **Contenedores** | Docker + Docker Swarm |
| **GUI** | CustomTkinter / Tkinter |
| **Consistencia** | Quorum (ONE/QUORUM/ALL) |
| **Nombrado** | CHORD DNS |
| **Elección de líder** | Algoritmo Bully |
