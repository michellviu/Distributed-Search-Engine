# Guía de Despliegue con Docker Swarm

Esta guía explica cómo desplegar el sistema distribuido de búsqueda usando Docker Swarm.

## Prerrequisitos

- Docker Engine 20.10+
- Al menos 2GB de RAM disponible

## Despliegue Rápido

```bash
# 1. Hacer el script ejecutable
chmod +x deploy-distributed.sh

# 2. Desplegar el sistema (1 coordinador + 3 nodos de procesamiento)
./deploy-distributed.sh

# 3. Verificar el estado
docker stack services search
```

## Despliegue Personalizado

### Escalar nodos al desplegar

```bash
# Desplegar con 5 nodos de procesamiento
./deploy-distributed.sh --scale 5
```

### Limpiar y redesplegar

```bash
# Eliminar despliegue anterior y volver a desplegar
./deploy-distributed.sh --clean
```

## Arquitectura del Despliegue

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Swarm Cluster                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────┐                                        │
│   │   Coordinator   │ ◄── Puerto 5000 expuesto               │
│   │   (1 réplica)   │                                        │
│   └────────┬────────┘                                        │
│            │                                                 │
│            ▼                                                 │
│   ┌─────────────────────────────────────────────┐           │
│   │              Overlay Network                 │           │
│   │            (search-network)                  │           │
│   └─────────┬───────────┬───────────┬───────────┘           │
│             │           │           │                        │
│             ▼           ▼           ▼                        │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│   │ Processing  │ │ Processing  │ │ Processing  │           │
│   │   Node 1    │ │   Node 2    │ │   Node 3    │           │
│   └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Archivos de Configuración

### docker-compose.distributed.yml

Define el stack completo:
- **Servicio `coordinator`**: 1 réplica, puerto 5000 expuesto
- **Servicio `processing`**: 3+ réplicas, escalable dinámicamente
- **Red `search-network`**: Overlay network para comunicación interna

### Dockerfile.distributed

Imagen única que soporta ambos roles:
- Variable `NODE_ROLE` determina el comportamiento
- Incluye todas las dependencias necesarias

### docker-entrypoint.sh

Script de entrada que:
1. Genera ID único basado en hostname del contenedor
2. Espera a que el coordinador esté disponible (nodos de procesamiento)
3. Copia archivos iniciales al directorio de trabajo
4. Inicia el rol correspondiente

## Volúmenes

| Volumen | Descripción | Acceso |
|---------|-------------|--------|
| `shared-files` | Archivos iniciales para indexar | Solo lectura |
| `processing-data` | Datos de cada nodo de procesamiento | Lectura/Escritura |
| `coordinator-logs` | Logs del coordinador | Lectura/Escritura |
| `processing-logs` | Logs de nodos de procesamiento | Lectura/Escritura |

## Variables de Entorno

### Coordinador

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `NODE_ROLE` | `coordinator` | Rol del nodo |
| `NODE_ID` | `coordinator-1` | ID único |
| `NODE_PORT` | `5000` | Puerto TCP |

### Procesamiento

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `NODE_ROLE` | `processing` | Rol del nodo |
| `COORDINATOR_HOST` | `coordinator` | Hostname del coordinador |
| `COORDINATOR_PORT` | `5000` | Puerto del coordinador |
| `INDEX_PATH` | `/home/app/data` | Directorio de archivos |
| `AUTO_INDEX` | `true` | Indexar automáticamente al iniciar |

## Comandos Útiles

### Gestión del Stack

```bash
# Ver servicios
docker stack services search

# Ver tareas (contenedores)
docker stack ps search

# Escalar nodos de procesamiento
docker service scale search_processing=5

# Eliminar stack
docker stack rm search
```

### Logs

```bash
# Logs del coordinador
docker service logs -f search_coordinator

# Logs de procesamiento
docker service logs -f search_processing

# Logs de un contenedor específico
docker logs -f <container_id>
```

### Debugging

```bash
# Entrar a un contenedor
docker exec -it <container_id> bash

# Ver red
docker network ls
docker network inspect search_search-network

# Ver volúmenes
docker volume ls
```

## Pruebas del Sistema

### Verificar Estado del Cluster

```bash
# Usando Python
python3 -c "
import socket
import json

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(('localhost', 5000))
    request = json.dumps({'action': 'cluster_status'})
    s.sendall(f'{len(request):<8}'.encode() + request.encode())
    length = int(s.recv(8).decode().strip())
    response = json.loads(s.recv(length).decode())
    print(json.dumps(response, indent=2))
"
```

### Probar Búsqueda

```bash
python3 -c "
import socket
import json

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(('localhost', 5000))
    request = json.dumps({'action': 'search', 'query': 'test', 'file_type': '.txt'})
    s.sendall(f'{len(request):<8}'.encode() + request.encode())
    length = int(s.recv(8).decode().strip())
    response = json.loads(s.recv(length).decode())
    print(f'Resultados: {len(response.get(\"results\", []))}')
"
```

## Tolerancia a Fallos

### Nodo de Procesamiento Cae

```bash
# Simular caída de un nodo
docker kill $(docker ps -q --filter "name=search_processing" | head -1)

# Docker Swarm reiniciará automáticamente el nodo
# Los datos siguen disponibles en las réplicas
```

### Coordinador Cae

```bash
# Simular caída del coordinador
docker kill $(docker ps -q --filter "name=search_coordinator")

# Docker Swarm reinicia automáticamente
# Los nodos de procesamiento se re-registran
```

## Solución de Problemas

### Los nodos no se registran

1. Verificar que el coordinador esté activo:
   ```bash
   docker service logs search_coordinator
   ```

2. Verificar conectividad de red:
   ```bash
   docker exec -it <processing_container> nc -z coordinator 5000
   ```

### Archivos no aparecen

1. Verificar que los archivos se copiaron:
   ```bash
   docker exec -it <processing_container> ls -la /home/app/data
   ```

2. Verificar logs de indexación:
   ```bash
   docker service logs search_processing | grep -i index
   ```

### Puerto 5000 ocupado

```bash
# Verificar qué está usando el puerto
sudo lsof -i :5000

# Eliminar stack anterior
docker stack rm search
sleep 10
./deploy-distributed.sh
```
