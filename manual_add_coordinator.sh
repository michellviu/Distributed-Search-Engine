#!/bin/bash
# Script para iniciar un COORDINADOR manualmente en un nodo específico del Swarm
# Uso: ./manual_add_coordinator.sh <ID> <PUERTO_HOST> <HOSTNAME_DESTINO> [SEED_PEER]
#
# El coordinador usará gossip para descubrir otros coordinadores a partir del seed.
# Si el seed no está disponible, el coordinador funcionará como líder independiente.

if [ "$#" -lt 2 ]; then
    echo "❌ Error: Faltan argumentos."
    echo ""
    echo "Uso: $0 <ID> <PUERTO_HOST> [SEED_PEER]"
    echo ""
    echo "Parámetros:"
    echo "  ID              - Identificador numérico del coordinador (ej: 1, 2)"
    echo "  PUERTO_HOST     - Puerto en el host (ej: 5003, 5004)"
    echo "  SEED_PEER       - (Opcional) Peer semilla host:port (ej: coordinator1:5000)"
    echo ""
    echo "Nota: Este script ejecuta 'docker run' en la máquina local."
    echo "      Debes estar conectado a la red 'search-network'."
    exit 1
fi

ID=$1
PORT=$2
# El tercer argumento ahora es opcional (Seed), y el destino se elimina porque es local
SEED_PEER=${3:-} 

CONTAINER_NAME="coordinator$ID"
NETWORK="search-network"

# Crear directorio de logs local si no existe para montar
mkdir -p logs

echo "=============================================="
echo "🚀 Iniciando Coordinador Manual (Docker Run)"
echo "=============================================="
echo "   🎯 Nombre:      $CONTAINER_NAME"
echo "   🔌 Puerto:      $PORT"
if [ -n "$SEED_PEER" ]; then
    echo "   🌱 Seed Peer:   $SEED_PEER"
else
    echo "   🌱 Seed Peer:   (Coordinador Semilla/Líder)"
fi

# Eliminar contenedor previo si existe
docker rm -f $CONTAINER_NAME 2>/dev/null

# Asegurar que la red existe
docker network inspect $NETWORK >/dev/null 2>&1 || docker network create $NETWORK

docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$NETWORK" \
    --network-alias coordinator \
    --restart no \
    -p "$PORT:5000" \
    -v "$(pwd)/logs:/home/app/logs" \
    --env NODE_ROLE=coordinator \
    --env NODE_ID="$CONTAINER_NAME" \
    --env NODE_HOST="0.0.0.0" \
    --env NODE_PORT=5000 \
    --env PEER_DISCOVERY=manual \
    --env PEER_COORDINATORS="$SEED_PEER" \
    --env REPLICATION_FACTOR=3 \
    --env LOG_LEVEL=INFO \
    search-engine:distributed

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Contenedor $CONTAINER_NAME iniciado."
    echo "📝 Logs: docker logs -f $CONTAINER_NAME"
else
    echo "❌ Error al iniciar el contenedor."
fi
