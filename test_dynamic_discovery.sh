#!/bin/bash
# =============================================================================
# Script de Prueba del Sistema de Descubrimiento Dinámico
# =============================================================================

echo "=========================================="
echo "  🧪 PRUEBA DESCUBRIMIENTO DINÁMICO"
echo "=========================================="
echo ""

# Configurar PYTHONPATH para importar módulos del proyecto
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

# Verificar que estamos en el directorio correcto
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Función para esperar a que un contenedor esté listo
wait_for_container() {
    local container=$1
    local max_attempts=30
    local attempt=1

    echo "⏳ Esperando que $container esté listo..."
    while [ $attempt -le $max_attempts ]; do
        if docker exec $container nc -z localhost 5000 2>/dev/null; then
            echo "✅ $container está listo"
            return 0
        fi
        echo "   Intento $attempt/$max_attempts..."
        sleep 2
        ((attempt++))
    done

    echo "❌ $container no respondió después de $max_attempts intentos"
    return 1
}

# Función para probar resolución DNS usando CoordinatorDiscovery
test_dns_resolution() {
    local container=$1
    echo "🔍 Probando descubrimiento DNS desde $container usando CoordinatorDiscovery..."

    # Ejecutar Python dentro del contenedor para usar el módulo de descubrimiento
    docker exec $container sh -c "cd /home/app && PYTHONPATH=/home/app/src python3 -c \"
import sys
import os
print('Current dir:', os.getcwd())
try:
    from client.coordinator_discovery import CoordinatorDiscovery
    print('Import successful')
    # Crear instancia de descubrimiento (sin direcciones iniciales para forzar DNS)
    discovery = CoordinatorDiscovery()
    # Obtener coordinadores descubiertos
    coordinators = discovery.get_coordinators()
    print(f'Coordinadores descubiertos: {coordinators}')
    if coordinators:
        print('✅ Descubrimiento DNS exitoso')
        sys.exit(0)
    else:
        print('❌ No se encontraron coordinadores via DNS')
        sys.exit(1)
except Exception as e:
    print(f'❌ Error en descubrimiento: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
\""

    if [ $? -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Función para probar conexión al coordinador
test_coordinator_connection() {
    local container=$1
    echo "🔗 Probando conexión a coordinador desde $container..."

    # Intentar conectar usando Python
    docker exec $container python3 -c "
import socket
import sys
try:
    # Intentar conectar a 'coordinator:5000'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex(('coordinator', 5000))
    sock.close()
    if result == 0:
        print('✅ Conexión exitosa a coordinator:5000')
        sys.exit(0)
    else:
        print('❌ No se pudo conectar a coordinator:5000')
        sys.exit(1)
except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
" 2>/dev/null

    if [ $? -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

echo "📋 PASO 1: Verificando estado de la red"
echo "----------------------------------------"
docker network inspect search-network >/dev/null 2>&1 || {
    echo "❌ La red 'search-network' no existe"
    echo "💡 Crea la red con: docker network create search-network"
    exit 1
}
echo "✅ Red 'search-network' existe"

echo ""
echo "📋 PASO 2: Verificando contenedores coordinadores"
echo "--------------------------------------------------"

# Buscar contenedores coordinadores
COORDINATORS=$(docker ps --filter "network=search-network" --filter "name=coordinator" --format "{{.Names}}" | grep -E "^coordinator[0-9]+$")

if [ -z "$COORDINATORS" ]; then
    echo "❌ No se encontraron contenedores coordinadores activos"
    echo "💡 Levanta coordinadores con: ./manual_add_coordinator.sh <ID> <PUERTO>"
    echo ""
    echo "Ejemplos:"
    echo "  ./manual_add_coordinator.sh 1 5000"
    echo "  ./manual_add_coordinator.sh 2 5001 coordinator1:5000"
    exit 1
fi

echo "✅ Coordinadores encontrados: $COORDINATORS"

echo ""
echo "📋 PASO 3: Verificando configuración de red"
echo "--------------------------------------------"

for coord in $COORDINATORS; do
    echo "🔍 Verificando $coord..."

    # Verificar que tenga el alias correcto
    ALIAS=$(docker inspect $coord --format '{{range $k, $v := .NetworkSettings.Networks}}{{if eq $k "search-network"}}{{range $v.Aliases}}{{.}} {{end}}{{end}}{{end}}')

    if echo "$ALIAS" | grep -q "coordinator"; then
        echo "   ✅ Alias 'coordinator' configurado"
    else
        echo "   ❌ Alias 'coordinator' NO configurado"
        echo "   💡 Usa --network-alias coordinator al crear el contenedor"
    fi

    # Verificar que esté en la red correcta
    NETWORK=$(docker inspect $coord --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep search-network || true)

    if [ -n "$NETWORK" ]; then
        echo "   ✅ Conectado a 'search-network'"
    else
        echo "   ❌ NO conectado a 'search-network'"
    fi

    # Esperar a que esté listo
    wait_for_container $coord

    echo ""
done

echo "📋 PASO 4: Probando resolución DNS"
echo "-----------------------------------"

# Usar el primer coordinador como cliente de prueba
FIRST_COORD=$(echo $COORDINATORS | awk '{print $1}')

if test_dns_resolution $FIRST_COORD; then
    echo "✅ Resolución DNS funciona"
else
    echo "❌ Resolución DNS falló"
    echo "💡 Verifica que todos los coordinadores tengan --network-alias coordinator"
fi

echo ""
echo "📋 PASO 5: Probando conexión cliente-coordinador"
echo "--------------------------------------------------"

if test_coordinator_connection $FIRST_COORD; then
    echo "✅ Conexión cliente-coordinador funciona"
else
    echo "❌ Conexión cliente-coordinador falló"
fi

echo ""
echo "📋 PASO 6: Probando cliente GUI"
echo "---------------------------------"

echo "🚀 Levantando cliente GUI para prueba final..."
echo "💡 El cliente debería descubrir automáticamente los coordinadores"
echo ""

# Verificar que la imagen del cliente existe
docker images | grep -q search-engine-client 2>/dev/null || {
    echo "❌ Imagen 'search-engine-client' no encontrada"
    echo "💡 Construye con: docker build -f Dockerfile.client -t search-engine-client:gui ."
    exit 1
}

# Nota: No ejecutamos el cliente automáticamente porque requiere interfaz gráfica
echo "✅ Todo listo para probar el cliente"
echo ""
echo "Para probar el cliente GUI:"
echo "  ./start_client_docker.sh"
echo ""
echo "El cliente debería mostrar automáticamente todos los coordinadores descubiertos."

echo ""
echo "=========================================="
echo "  ✅ PRUEBA COMPLETADA"
echo "=========================================="