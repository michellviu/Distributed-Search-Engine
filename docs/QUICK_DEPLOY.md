# 🚀 Guía Rápida - Docker Swarm

## ⚡ PASOS RÁPIDOS (30 minutos)

### 📋 Preparación (Ambos PCs)

### 🏗️ PC 1 (Manager) - Construcción y Setup

```bash
# 1. Ir al proyecto
cd ~/Proyectos/Distributed-Search-Engine

# 2. Construir imagen
docker build -t search-engine:latest .

# 3. Obtener IP
ip addr show | grep "inet " | grep -v 127.0.0.1
# Anota tu IP (ej: 192.168.1.100)

# 4. Inicializar Swarm (REEMPLAZA con tu IP)
docker swarm init --advertise-addr 192.168.1.100

# 5. COPIAR el comando "docker swarm join" que aparece
# Lo necesitarás para el PC 2
```

### 🔗 PC 2 (Worker) - Unirse al Swarm

```bash
# 1. Pegar el comando que copiaste del PC 1
docker swarm join --token SWMTKN-1-xxx... 192.168.1.100:2377
```

### 📤 PC 1 - Transferir Imagen a PC 2

```bash
# Opción A: Transferir por red (más rápido)
docker save search-engine:latest | gzip > search-engine.tar.gz
scp search-engine.tar.gz usuario@IP_PC2:~/
```

### 📥 PC 2 - Cargar Imagen

```bash
# En PC 2
cd ~
gunzip -c search-engine.tar.gz | docker load
docker images | grep search-engine
```

### 🚀 PC 1 - Desplegar

```bash
# En PC 1 (Manager)
cd ~/Proyectos/Distributed-Search-Engine

# Desplegar el stack
docker stack deploy -c docker-stack.yml search-app

# Ver estado
docker stack services search-app
docker service ps search-app_search-server
```

### 🖥️ Ejecutar GUI (En PC 1)

```bash
# Activar entorno
source ~/mygeneralenv/bin/activate

# Ejecutar GUI
python3 src/client/client_gui.py
```

## ✅ Verificación Rápida

```bash
# Ver nodos
docker node ls

# Ver servicios
docker stack services search-app

# Ver réplicas
docker service ps search-app_search-server

# Ver logs
docker service logs search-app_search-server
```

## 🎯 Para la Demostración

1. **Mostrar el cluster**:
   ```bash
   docker node ls
   ```

2. **Mostrar las 2 réplicas**:
   ```bash
   docker service ps search-app_search-server
   ```

3. **Usar la GUI**:
   - Buscar archivos
   - Descargar archivos
   - Mostrar que funciona

4. **Escalar**:
   ```bash
   docker service scale search-app_search-server=4
   ```

5. **Ver logs en tiempo real**:
   ```bash
   docker service logs -f search-app_search-server
   ```

