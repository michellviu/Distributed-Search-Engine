# Guía de Despliegue con Docker Swarm

Esta guía explica cómo desplegar el sistema distribuido de búsqueda usando Docker Swarm.

## Prerrequisitos

- Docker Engine 20.10+
- Docker Compose v2
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
│   │   (coordinator) │                                        │
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

## Volúmenes

- `shared-files`: Archivos compartidos para indexar
- `coordinator-logs`: Logs del coordinador
- `processing-logs`: Logs de nodos de procesamiento
- `processing-data-N`: Datos de cada nodo de procesamiento

## Pruebas

### Ejecutar suite de pruebas

```bash
./test-distributed.sh
```

### Modo interactivo (para probar fallos)

```bash
./test-failover-interactive.sh
```

Este modo permite:
- Ver estado del cluster en tiempo real
- Escalar nodos dinámicamente
- Simular caída de nodos
- Probar búsquedas manualmente
- Ver logs en tiempo real

## Comandos Útiles

### Ver estado de servicios

```bash
docker stack services search
```

### Ver logs del coordinador

```bash
docker service logs -f search_coordinator
```

### Ver logs de procesamiento

```bash
docker service logs -f search_processing
```

### Escalar nodos de procesamiento

```bash
# Escalar a 5 nodos
docker service scale search_processing=5

# Reducir a 2 nodos
docker service scale search_processing=2
```

### Simular caída de un nodo

```bash
# Obtener ID de un contenedor
docker ps --filter "name=search_processing"

# Matar el contenedor (Swarm lo reiniciará automáticamente)
docker kill <container_id>
```

### Eliminar el despliegue

```bash
docker stack rm search
```

## Verificar Funcionalidad

### 1. Health Check

```bash
echo '{"action": "health"}' | nc localhost 5000
```

### 2. Estado del Cluster

```bash
echo '{"action": "cluster_status"}' | nc localhost 5000
```

### 3. Listar Archivos

```bash
echo '{"action": "list"}' | nc localhost 5000
```

### 4. Buscar Archivos

```bash
echo '{"action": "search", "query": "test"}' | nc localhost 5000
```

## Usar la GUI

```bash
# Desde fuera de Docker
python -m src.client.client_gui --coordinators localhost:5000

# O con múltiples coordinadores para failover
python -m src.client.client_gui --coordinators coord1:5000 coord2:5001 coord3:5002
```

## Tolerancia a Fallos

### Caída de nodo de procesamiento

1. Docker Swarm detecta el fallo
2. Reinicia automáticamente el contenedor
3. El nodo se re-registra con el coordinador
4. Los archivos se re-replican si es necesario

### Caída del coordinador

1. Docker Swarm detecta el fallo
2. Reinicia automáticamente el contenedor
3. Los nodos de procesamiento se reconectan

### Pérdida de datos

- Con factor de replicación 3, el sistema tolera la pérdida de 2 nodos
- Los archivos se re-replican automáticamente cuando hay nodos disponibles

## Troubleshooting

### El coordinador no inicia

```bash
# Ver logs de error
docker service logs search_coordinator

# Verificar que el puerto no está en uso
netstat -tlnp | grep 5000
```

### Los nodos de procesamiento no se conectan

```bash
# Verificar red overlay
docker network ls | grep search

# Verificar DNS interno
docker run --rm --network search_search-network alpine nslookup coordinator
```

### Los archivos no se indexan

```bash
# Verificar volumen de archivos compartidos
docker volume inspect shared-files

# Verificar contenido del volumen
docker run --rm -v shared-files:/data alpine ls -la /data
```
