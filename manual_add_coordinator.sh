#!/bin/bash
# Script para iniciar un COORDINADOR manualmente en un nodo específico del Swarm
# Uso: ./manual_add_coordinator.sh <ID> <PUERTO_HOST> <HOSTNAME_DESTINO>

if [ "$#" -ne 3 ]; then
    echo "❌ Error: Faltan argumentos."
    echo "Uso: $0 <ID> <PUERTO_HOST> <HOSTNAME_DESTINO>"
    echo "Ejemplo: $0 3 5003 michell"
    exit 1
fi

ID=$1
PORT=$2
TARGET_NODE=$3
SEED_PEER=${4:-coordinator1:5000}  # Nodo semilla por defecto

SERVICE_NAME="manual_coord_$ID"
NETWORK="search_search-network"

echo "🚀 Creando Coordinador Manual $ID en nodo '$TARGET_NODE'..."
echo "   🌱 Seed Peer: $SEED_PEER"

docker service create \
    --name "$SERVICE_NAME" \
    --network "$NETWORK" \
    --restart-condition none \
    --constraint "node.hostname == $TARGET_NODE" \
    --publish "$PORT:5000" \
    --env NODE_ROLE=coordinator \
    --env NODE_ID="manual-coord-$ID" \
    --env NODE_HOST="0.0.0.0" \
    --env NODE_PORT=5000 \
    --env PEER_DISCOVERY=manual \
    --env PEER_COORDINATORS="$SEED_PEER" \
    --env REPLICATION_FACTOR=3 \
    --env LOG_LEVEL=INFO \
    search-engine:distributed

if [ $? -eq 0 ]; then
    echo "✅ Servicio $SERVICE_NAME creado exitosamente."
    echo "   📍 Nodo Destino: $TARGET_NODE"
    echo "   🔌 Puerto: $PORT"
    echo "   📝 Para eliminarlo: docker service rm $SERVICE_NAME"
    echo "   💀 Para simular crash: Busca el contenedor en '$TARGET_NODE' y haz 'docker kill'"
else
    echo "❌ Error al crear el servicio."
fi
