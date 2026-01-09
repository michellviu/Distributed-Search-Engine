# Guía: Despliegue en Dos Computadoras con Docker Swarm

## ¿Cambia mucho el escenario?

**No cambia mucho**, pero hay algunas consideraciones importantes:

| Aspecto | Una PC | Dos PCs |
|---------|--------|---------|
| Red | `overlay` local | `overlay` distribuida |
| Descubrimiento | DNS local | DNS de Swarm |
| Imágenes | Una copia | Debe estar en ambas PCs |
| Cliente | `localhost:5000` | IP del Manager o cualquier nodo |
| Failover | Mismo host | Funciona igual |

## Arquitectura con Dos PCs

```
┌──────────────────────────────────────────────────────────────────┐
│                     Docker Swarm Cluster                         │
├──────────────────────────────────┬───────────────────────────────┤
│         PC1 (Manager)            │         PC2 (Worker)          │
│         192.168.1.100            │         192.168.1.101         │
├──────────────────────────────────┼───────────────────────────────┤
│  ┌─────────────────────────┐     │   ┌─────────────────────────┐ │
│  │  Coordinador 1          │     │   │  Coordinador 2          │ │
│  │  (search_coordinator)   │     │   │  (si escalas a 2)       │ │
│  └─────────────────────────┘     │   └─────────────────────────┘ │
│                                  │                               │
│  ┌─────────────────────────┐     │   ┌─────────────────────────┐ │
│  │  Procesamiento 1        │     │   │  Procesamiento 2        │ │
│  └─────────────────────────┘     │   └─────────────────────────┘ │
│                                  │                               │
│  ┌─────────────────────────┐     │   ┌─────────────────────────┐ │
│  │  Procesamiento 3        │     │   │  Procesamiento 4        │ │
│  │  (si escalas)           │     │   │  (si escalas)           │ │
│  └─────────────────────────┘     │   └─────────────────────────┘ │
└──────────────────────────────────┴───────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
               [Cliente PC1]       [Cliente PC2]
               Conecta a:          Conecta a:
               localhost:5000      192.168.1.100:5000
                   o                   o
               192.168.1.100:5000  192.168.1.101:5000
```

## Preparación Previa (Ambas PCs)

### En AMBAS PCs:

```bash
# 1. Instalar Docker
sudo apt-get update
sudo apt-get install docker.io docker-compose-plugin

# 2. Agregar usuario al grupo docker
sudo usermod -aG docker $USER
newgrp docker

# 3. Verificar Docker
docker --version
docker info
```

## Paso 1: Configurar Swarm (PC1 - Manager)

```bash
# En PC1 (será el Manager)
cd ~/Proyectos/Distributed-Search-Engine

# Obtener tu IP (ej: 192.168.1.100)
ip addr show | grep "inet " | grep -v 127.0.0.1
# Anota la IP de tu interfaz de red principal (ej: eth0, wlan0)

# Inicializar Swarm con tu IP
docker swarm init --advertise-addr 192.168.1.100

# IMPORTANTE: Guarda el comando que aparece, algo como:
# docker swarm join --token SWMTKN-1-xxxxx 192.168.1.100:2377
```

## Paso 2: Unir PC2 al Swarm (PC2 - Worker)

```bash
# En PC2, pegar el comando del paso anterior:
docker swarm join --token SWMTKN-1-xxxxx 192.168.1.100:2377

# Verificar que se unió
docker info | grep "Swarm:"
# Debe decir: Swarm: active
```

## Paso 3: Verificar Nodos (PC1)

```bash
# En PC1
docker node ls

# Deberías ver algo como:
# ID          HOSTNAME   STATUS   AVAILABILITY   MANAGER STATUS
# abc123 *    pc1        Ready    Active         Leader
# def456      pc2        Ready    Active
```

## Paso 4: Transferir Imagen a PC2

La imagen Docker debe existir en AMBAS PCs. Opciones:

### Opción A: Exportar e Importar (más rápido en LAN)

```bash
# En PC1: Exportar imagen
docker save search-engine:distributed | gzip > search-engine.tar.gz

# Copiar a PC2 (usa scp, pendrive, o cualquier método)
scp search-engine.tar.gz usuario@192.168.1.101:~/

# En PC2: Importar imagen
cd ~
gunzip -c search-engine.tar.gz | docker load

# Verificar
docker images | grep search-engine
```

### Opción B: Construir en PC2 (más lento pero no necesita transferencia)

```bash
# En PC2
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine
docker build -f Dockerfile.distributed -t search-engine:distributed .
```

### Opción C: Usar Registry (más profesional)

```bash
# En PC1: Crear registry local
docker run -d -p 5001:5000 --restart=always --name registry registry:2

# Subir imagen
docker tag search-engine:distributed 192.168.1.100:5001/search-engine:distributed
docker push 192.168.1.100:5001/search-engine:distributed

# En PC2: Descargar imagen
docker pull 192.168.1.100:5001/search-engine:distributed
docker tag 192.168.1.100:5001/search-engine:distributed search-engine:distributed
```

## Paso 5: Desplegar Stack (PC1)

```bash
# En PC1
cd ~/Proyectos/Distributed-Search-Engine

# Preparar volumen
docker volume create shared-files
docker run --rm \
    -v shared-files:/data \
    -v "$PWD/shared_files:/source:ro" \
    alpine sh -c "cp -r /source/* /data/"

# Desplegar stack
docker stack deploy -c docker-compose.distributed.yml search

# Ver estado
docker stack services search
```

## Paso 6: Verificar Distribución de Contenedores

```bash
# En PC1
docker stack ps search

# Verás algo como:
# NAME                      NODE   DESIRED STATE   CURRENT STATE
# search_coordinator.1      pc1    Running         Running 2 min
# search_processing.1       pc1    Running         Running 2 min
# search_processing.2       pc2    Running         Running 1 min
# search_processing.3       pc1    Running         Running 1 min
```

Los contenedores se distribuyen automáticamente entre las PCs.

## Paso 7: Ejecutar Cliente

### Desde PC1 (Manager):

```bash
# El cliente puede conectar a localhost porque el puerto 5000 está expuesto
source ~/mygeneralenv/bin/activate
python -m src.client.client_gui
# Conectará automáticamente a localhost:5000
```

### Desde PC2 (Worker):

```bash
# El cliente debe conectar a la IP del Manager
source ~/mygeneralenv/bin/activate
python -m src.client.client_gui --coordinators "192.168.1.100:5000"

# O si hay coordinador local (cuando escalas a 2)
python -m src.client.client_gui --coordinators "192.168.1.100:5000,192.168.1.101:5000"
```

### Desde una PC externa (sin Docker):

```bash
# Puede conectar a cualquier IP del Swarm
python -m src.client.client_gui --coordinators "192.168.1.100:5000"
```

## Paso 8: Pruebas Paso a Paso

### 8.1 Verificar Estado Inicial

```bash
# En PC1
docker stack services search
# Debería mostrar: 1 coordinador, 1 procesamiento
```

### 8.2 Escalar Nodos de Procesamiento

```bash
# Agregar segundo nodo (puede desplegarse en PC1 o PC2)
docker service scale search_processing=2
sleep 10
docker stack ps search

# Agregar tercero
docker service scale search_processing=3
sleep 10
docker stack ps search

# Ver distribución
docker stack ps search --format "table {{.Name}}\t{{.Node}}\t{{.CurrentState}}"
```

### 8.3 Probar en la GUI

1. Ejecutar GUI en PC1
2. Buscar archivos → Debe funcionar
3. Indexar archivo nuevo → Debe replicarse
4. Verificar en logs que se replica a múltiples nodos

### 8.4 Simular Fallo de Nodo de Procesamiento

```bash
# Matar un nodo de procesamiento
docker kill $(docker ps -q --filter "name=search_processing" | head -1)

# Esperar
sleep 10

# Ver estado
docker stack ps search
# El nodo fallido debería reiniciarse automáticamente

# Probar en GUI: buscar y descargar archivos
# Debe seguir funcionando
```

### 8.5 Agregar Segundo Coordinador

```bash
# Escalar coordinadores
docker service scale search_coordinator=2
sleep 15
docker stack ps search

# Ahora hay 2 coordinadores
# El cliente puede conectar a cualquiera
```

### 8.6 Probar Failover del Cliente

```bash
# En PC1: Mantén la GUI abierta

# Identificar coordinador al que está conectada la GUI
# (ver mensajes en consola de la GUI)

# Matar el coordinador
docker kill $(docker ps -q --filter "name=search_coordinator" | head -1)

# Observar la GUI:
# - Debería detectar la caída
# - Reconectar automáticamente al otro coordinador
# - Continuar funcionando
```

### 8.7 Probar Caída de PC2 Completa (Opcional)

```bash
# En PC2: Simular desconexión
sudo systemctl stop docker

# En PC1: Ver cómo el Swarm maneja la caída
docker node ls
docker stack ps search

# El Swarm reubicará los contenedores de PC2 a PC1
# (si hay recursos disponibles)

# Reconectar PC2
# En PC2:
sudo systemctl start docker

# Los nodos volverán a estar disponibles
```

## Diferencias Clave con Una PC

| Aspecto | Una PC | Dos PCs |
|---------|--------|---------|
| **Red** | Overlay local | Overlay sobre red física |
| **Latencia** | ~0ms | ~1-10ms (LAN) |
| **Imagen** | Una copia | Debe existir en ambas |
| **Cliente** | `localhost:5000` | IP de cualquier nodo |
| **Fallo de nodo** | Simulado con `docker kill` | Puede ser real (apagar PC) |
| **Distribución** | Todos en mismo host | Docker decide distribución |

## Troubleshooting

### El nodo no se une al Swarm

```bash
# Verificar conectividad
ping 192.168.1.100

# Verificar firewall
sudo ufw allow 2377/tcp
sudo ufw allow 7946/tcp
sudo ufw allow 7946/udp
sudo ufw allow 4789/udp
```

### Los contenedores no inician en PC2

```bash
# Verificar que la imagen existe
docker images | grep search-engine

# Si no existe, transferir desde PC1
```

### El cliente no puede conectar desde PC2

```bash
# Verificar que el puerto está expuesto
docker service inspect search_coordinator --format '{{json .Endpoint.Ports}}'

# Verificar firewall en PC1
sudo ufw allow 5000/tcp

# Probar conectividad
nc -z 192.168.1.100 5000 && echo "Puerto abierto" || echo "Puerto cerrado"
```

### Los archivos no se replican

```bash
# Verificar logs del coordinador
docker service logs search_coordinator | grep -i replic

# Verificar que hay suficientes nodos
docker service ls
# processing debe tener al menos 3 réplicas para replicación completa
```

## Resumen de Comandos

```bash
# === PC1 (Manager) ===
docker swarm init --advertise-addr <IP_PC1>
docker node ls
docker stack deploy -c docker-compose.distributed.yml search
docker stack services search
docker stack ps search
docker service scale search_processing=3
docker service scale search_coordinator=2
docker service logs -f search_coordinator

# === PC2 (Worker) ===
docker swarm join --token <TOKEN> <IP_PC1>:2377
docker ps

# === Cliente ===
python -m src.client.client_gui  # Desde PC1
python -m src.client.client_gui --coordinators "<IP_PC1>:5000"  # Desde PC2 u otra PC

# === Simular fallos ===
docker kill $(docker ps -q --filter "name=search_coordinator" | head -1)
docker kill $(docker ps -q --filter "name=search_processing" | head -1)
```
