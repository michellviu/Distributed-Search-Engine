#!/bin/bash
# Script para iniciar un NODO DE PROCESAMIENTO manualmente en un nodo específico
# Uso: ./manual_add_node.sh <ID> <PUERTO_HOST> <HOSTNAME_DESTINO>

if [ "$#" -ne 3 ]; then
    echo "❌ Error: Faltan argumentos."
    echo "Uso: $0 <ID> <PUERTO_HOST> <HOSTNAME_DESTINO>"
    echo "Ejemplo: $0 5 5005 eveliz"
    exit 1
fi

ID=$1
PORT=$2
TARGET_NODE=$3
COORD_HOST=${4:-coordinator1}

SERVICE_NAME="manual_proc_$ID"
NETWORK="search_search-network"

echo "🚀 Creando Nodo de Procesamiento Manual $ID en nodo '$TARGET_NODE'..."
echo "   🔗 Coordinador: $COORD_HOST"

docker service create \
    --name "$SERVICE_NAME" \
    --network "$NETWORK" \
    --restart-condition none \
    --constraint "node.hostname == $TARGET_NODE" \
    --publish "$PORT:5000" \
    --mount type=volume,source=shared-files,target=/home/app/shared_files \
    --env NODE_ROLE=processing \
    --env NODE_ID="manual-proc-$ID" \
    --env NODE_HOST="0.0.0.0" \
    --env NODE_PORT=5000 \
    --env COORDINATOR_DISCOVERY=manual \
    --env COORDINATOR_HOST="$COORD_HOST" \
    --env INIT_FILES_PATH=/home/app/shared_files \
    --env AUTO_INDEX=true \
    --env LOG_LEVEL=INFO \
    search-engine:distributed

if [ $? -eq 0 ]; then
    echo "✅ Servicio $SERVICE_NAME creado exitosamente."
    echo "   📍 Nodo Destino: $TARGET_NODE"
    echo "   🔌 Puerto: $PORT"
    echo "   📝 Para eliminarlo: docker service rm $SERVICE_NAME"
else
    echo "❌ Error al crear el servicio."
fi
