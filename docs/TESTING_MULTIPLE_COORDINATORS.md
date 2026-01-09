# Guía de Prueba: Múltiples Coordinadores y Failover

## Objetivo

Probar que el cliente puede conectarse dinámicamente a cualquier coordinador disponible y continuar funcionando incluso si los coordinadores fallan.

## Arquitectura

```
┌─────────────────────────────────────────┐
│      3 Coordinadores (replicas)         │
│  - Cada uno es independiente            │
│  - Descubrimiento automático via DNS    │
│  - Alto disponibilidad                  │
└─────────────────┬───────────────────────┘
                  │
        ┌─────────┼─────────┐
        │         │         │
        ▼         ▼         ▼
   [Coord-1]  [Coord-2] [Coord-3]
        ▲         ▲         ▲
        └─────────┼─────────┘
                  │
            ┌─────┴─────┐
            │           │
     [Cliente GUI] [Nodos de Procesamiento]
            
Cliente descubre coordinadores automáticamente
y usa el primero disponible. Si falla, reconecta
automáticamente a otro.
```

## Pasos de Prueba

### 1. Desplegar Sistema desde Cero

```bash
cd /home/michell/Proyectos/Distributed-Search-Engine

# Opción A: Script automático
./test-multiple-coordinators.sh

# Opción B: Manual
docker stack rm search 2>/dev/null || true
sleep 5
docker build -f Dockerfile.distributed -t search-engine:distributed .
docker stack deploy -c docker-compose.distributed.yml search
```

### 2. Verificar 3 Coordinadores Activos

```bash
# Ver servicios
docker stack services search

# Ver contenedores de coordinadores
docker ps --filter "name=search_coordinator"

# Deberías ver 3 contenedores de coordinador activos
```

### 3. Ejecutar Cliente GUI con Descubrimiento Automático

```bash
# Terminal 1: Activar entorno virtual
source ~/mygeneralenv/bin/activate

# Ejecutar sin especificar coordinador (descubrimiento automático)
cd /home/michell/Proyectos/Distributed-Search-Engine
python -m src.client.client_gui

# Deberías ver en la consola:
# 🔍 Usando descubrimiento automático de coordinadores en Docker Swarm...
# ✓ Conectado al coordinador <IP>:5000 (líder)
# Total de coordinadores disponibles: 3
```

### 4. Probar Funcionalidades Básicas

En la GUI:
1. **Búsqueda**: Busca archivos (ej: "test" con tipo ".txt")
2. **Listar**: Ve todos los archivos
3. **Descargar**: Descarga un archivo
4. **Indexar**: Indexa un nuevo archivo

**Verifica que todo funciona correctamente.**

### 5. Simular Fallo de Coordinador #1

En otra terminal:

```bash
# Obtener ID del contenedor del coordinador
COORD_ID=$(docker ps -q --filter "name=search_coordinator" | head -1)

echo "Matando coordinador: $COORD_ID"
docker kill $COORD_ID

# Esperar 10 segundos
sleep 10
```

**En la GUI:**
- El cliente detectará que el coordinador cayó
- Se reconectará automáticamente a otro coordinador
- Las funcionalidades deben seguir siendo accesibles
- Deberías ver en logs: "Reconectando a coordinador..."

**Verifica:**
- ✓ Puedes buscar archivos
- ✓ Puedes descargar archivos
- ✓ Puedes indexar nuevos archivos

### 6. Simular Fallo de Coordinador #2

Repite el paso anterior con otro coordinador:

```bash
# Matar otro coordinador
COORD_ID=$(docker ps -q --filter "name=search_coordinator" | head -1)
docker kill $COORD_ID
sleep 10
```

**Verifica de nuevo que todo funciona.**

### 7. Estado Final

Deberías tener:
- ✓ 3 coordinadores: 1 activo + 2 fallidos (en reinicio)
- ✓ 3 nodos de procesamiento: todos activos
- ✓ Cliente GUI: funcionando sin interrupciones
- ✓ Archivo nuevo indexado: presente y replicado

### 8. Ver Recuperación de Coordinadores

```bash
# Docker Swarm reinicia automáticamente los coordinadores caídos
docker stack services search

# Espera 30 segundos y verifica que vuelvan a estar UP
watch docker stack services search
```

## Código de Descubrimiento Automático

El cliente usa dos métodos:

### Método 1: Docker DNS (Preferido)

```python
# En Docker Swarm:
# search_coordinator → Resuelve a todas las réplicas
resolver = CoordinatorDiscovery()
coordinators = resolver.get_coordinators()
# Resultado: ['10.0.1.5:5000', '10.0.1.6:5000', '10.0.1.7:5000']
```

### Método 2: Fallback a localhost

Si no está en Docker Swarm:
```python
# Fallback automático a localhost
coordinators = ['localhost:5000']
```

## Prueba de Reconexión Manual

```bash
# Terminal 1: Ver intentos de conexión
docker service logs -f search_coordinator

# Terminal 2: Matar coordinador
docker kill $(docker ps -q --filter "name=search_coordinator" | head -1)

# Terminal 3: En la GUI, intenta hacer una búsqueda
# Verás que se reconecta automáticamente
```

## Resultados Esperados

| Escenario | Comportamiento Esperado |
|-----------|------------------------|
| Cliente inicia | Se conecta al primer coordinador disponible |
| Coordinador falla | Cliente se reconecta a otro en <5 segundos |
| 2 coordinadores fallan | Cliente sigue funcionando con el tercero |
| Todos fallan momentáneamente | Docker Swarm reinicia, cliente se reconecta |
| Nuevo coordinador inicia | Cliente puede descubrirlo (refresco cada 30s) |

## Logs Importantes

### Cliente GUI

```
🔍 Usando descubrimiento automático de coordinadores en Docker Swarm...
✓ Conectado al coordinador 10.0.1.5:5000 (líder)
Total de coordinadores disponibles: 3
```

### Coordinador

```
✓ Nodo de procesamiento registrado: processing-xxx (10.0.1.10:5000) - 12 archivos
🔍 Búsqueda: 'test' (tipo: .txt)
📦 Archivo 'nuevo.txt' asignado a nodos: [xxx, yyy, zzz]
```

### Procesamiento

```
✓ Registrado con coordinador en 10.0.1.5:5000
📁 Auto-indexando archivos en /home/app/data...
Encontrados 10 archivos para indexar
```

## Conclusión

Este test valida:
1. ✅ **Descubrimiento dinámico**: Cliente encuentra coordinadores sin configuración previa
2. ✅ **Failover automático**: Reconexión transparente a otro coordinador
3. ✅ **Alta disponibilidad**: Sistema continúa funcionando con pérdida de coordinadores
4. ✅ **Recuperación automática**: Docker Swarm reinicia coordinadores caídos
