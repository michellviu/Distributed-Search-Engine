# Distributed-Search-Engine

📖 **Proyecto de Sistema de Búsqueda Distribuida**

Este proyecto implementa un motor de búsqueda de documentos **totalmente distribuido**, desarrollado como parte del curso de Sistemas Distribuidos.

## Descripción General

El Motor de Búsqueda Distribuida es un sistema robusto y escalable para buscar y acceder a documentos a través de múltiples nodos. A diferencia de una arquitectura centralizada, este sistema utiliza una arquitectura **P2P (Peer-to-Peer) Estructurada** donde:

- **Arquitectura P2P:** Todos los nodos colaboran para almacenar y buscar información.
- **Coordinador Dinámico:** Se elige automáticamente un líder para tareas de gestión, con recuperación automática ante fallos.
- **Consistent Hashing:** Los datos se distribuyen uniformemente en un anillo lógico.
- **Replicación y Tolerancia a Fallos:** Cada documento se replica en múltiples nodos (Factor N=3) para garantizar disponibilidad incluso si caen nodos.

## Características Principales

### 🌐 Arquitectura Distribuida

- **Diseño P2P Estructurado**: Organización en anillo mediante Consistent Hashing.
- **Elección de Líder**: Algoritmo Bully para elegir automáticamente un nuevo coordinador si el actual falla.
- **Descubrimiento Automático**: Los nodos se encuentran entre sí mediante **IP Cache Discovery** con escaneo de subred y propagación de peers.

### 🛡️ Fiabilidad y Tolerancia a Fallos

- **Replicación de Datos**: Estrategia de replicación en cadena (Chain Replication) con factor configurable (default: 3).
- **Heartbeat Monitoring**: Detección continua de la salud de los nodos.
- **Auto-Curación**: Redistribución automática de datos cuando un nodo entra o sale del cluster.
- **Quorum**: Consistencia garantizada en operaciones de lectura y escritura.

### 🔍 Funcionalidades de Búsqueda

- **Búsqueda Distribuida**: Las consultas se propagan eficientemente por el cluster.
- **Indexación Automática**: Detección e indexación de archivos en tiempo real.
- **Transferencia Resiliente**: Descarga de archivos desde cualquier réplica disponible.

## Estructura del Proyecto

```text
Distributed-Search-Engine/
├── src/
│   ├── distributed/         # Lógica del sistema distribuido
│   │   ├── coordination/    # Elección de líder (Bully)
│   │   ├── consistency/     # Quorum y consistencia
│   │   ├── discovery/       # IP Cache Discovery y Heartbeats
│   │   ├── node/            # Implementación del Nodo P2P
│   │   ├── replication/     # Consistent Hashing y Replication Manager
│   │   └── search/          # Motor de búsqueda distribuido
│   ├── server/              # Servidor TCP/RPC
│   ├── client/              # Cliente interactivo y CLI
│   ├── indexer/             # Indexación local de documentos
│   ├── search/              # Motor de búsqueda local
│   └── main_distributed.py  # Punto de entrada del nodo distribuido
├── config/                  # Configuración JSON
├── docs/                    # Documentación detallada
├── shared_files/            # Directorio de archivos compartidos
└── deploy-distributed.sh    # Script de despliegue
```

## Requisitos

- Python 3.9+
- Docker (opcional, para despliegue en contenedores)
- Red TCP/IP estándar

## Instalación y Uso

### 1. Instalación Local

```bash
# Clonar el repositorio
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Despliegue Rápido (Docker Swarm)

La forma más fácil de probar el sistema distribuido es usando el stack de Docker incluido:

```bash
# Iniciar el cluster (3 nodos por defecto)
./deploy-swarm.sh
```

### 3. Ejecución Manual de Nodos

Puedes levantar múltiples nodos en diferentes terminales:

```bash
# Nodo 1 (Seed)
python3 src/main_distributed.py --node-id node1 --port 5000

# Nodo 2 (se une al cluster)
python3 src/main_distributed.py --node-id node2 --port 5001

# Nodo 3
python3 src/main_distributed.py --node-id node3 --port 5002
```

### 4. Uso del Cliente

El cliente puede conectarse a cualquier nodo del cluster:

```bash
# Iniciar cliente interactivo
python3 src/client/client_interactive.py --host localhost --port 5000
```

Comandos disponibles:

- `search <query>`: Buscar en todo el cluster.
- `upload <archivo>`: Subir e indexar un archivo (se replicará automáticamente).
- `download <archivo>`: Descargar un archivo.
- `cluster_status`: Ver estado de nodos, líder y replicación.

## Arquitectura Técnica

### Comunicación

- **TCP (JSON-RPC):** Para operaciones críticas (búsqueda, indexación, replicación).
- **TCP (IP Cache):** Para descubrimiento automático de nodos mediante escaneo de subred y registro bidireccional.

### Distribución de Datos

El sistema utiliza **Consistent Hashing** para asignar archivos a nodos.

1. Se calcula `hash(nombre_archivo)`.
2. El archivo se asigna al nodo con `hash(nodo) >= hash(archivo)`.
3. Se crean réplicas en los `N-1` nodos siguientes del anillo.

### Tolerancia a Fallos

- Si un nodo cae, el sistema lo detecta vía Heartbeat.
- Si era el líder, se inicia una elección (Bully Algorithm).
- Los datos perdidos se regeneran automáticamente desde las réplicas restantes para mantener el factor de replicación.

## Documentación Adicional

- 📄 [**REPORT.md**](REPORT.md): Informe detallado de diseño y arquitectura.
- 📖 [**QUICKSTART.md**](docs/QUICKSTART.md): Guía paso a paso para usuarios.

## Contribuidores

Desarrollado como proyecto final para el curso de Sistemas Distribuidos.
