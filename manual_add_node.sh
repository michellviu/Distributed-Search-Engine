#!/bin/bash
# Script para iniciar un NODO DE PROCESAMIENTO manualmente en un nodo específico
# Uso: ./manual_add_node.sh <ID> <PUERTO_HOST> [COORDINADOR]
#
# El nodo de procesamiento intentará conectarse al coordinador especificado.
# Si el coordinador no está disponible, el nodo esperará y reintentará.

if [ "$#" -lt 2 ]; then
    echo "❌ Error: Faltan argumentos."
    echo ""
    echo "Uso: $0 <ID> <PUERTO_HOST> [COORDINADOR]"
    echo ""
    echo "Parámetros:"
    echo "  ID              - Identificador numérico del nodo (ej: 1, 2)"
    echo "  PUERTO_HOST     - Puerto en el host (ej: 5001, 5002)"
    echo "  COORDINADOR     - (Opcional) Host del coordinador (por defecto: coordinator1)"
    echo ""
    echo "Nota: Este script ejecuta 'docker run' localmente."
    exit 1
fi

ID=$1
PORT=$2
COORD_HOST=${3:-coordinator1}

CONTAINER_NAME="node_$ID"
NETWORK="search-network"

# Directorios locales para persistencia
mkdir -p shared_files
mkdir -p data/node_$ID

echo "=============================================="
echo "🚀 Iniciando Nodo de Procesamiento Manual"
echo "=============================================="
echo "   📦 Nombre:      $CONTAINER_NAME"
echo "   🔌 Puerto:      $PORT"
echo "   🔗 Coordinador: $COORD_HOST"
echo "=============================================="

# Eliminar contenedor anterior
docker rm -f $CONTAINER_NAME 2>/dev/null

# Asegurar red
docker network inspect $NETWORK >/dev/null 2>&1 || docker network create $NETWORK

docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$NETWORK" \
    --restart no \
    -p "$PORT:5000" \
    -v "$(pwd)/shared_files:/home/app/shared_files:ro" \
    -v "$(pwd)/data/node_$ID:/home/app/data" \
    --env NODE_ROLE=processing \
    --env NODE_ID="$CONTAINER_NAME" \
    --env NODE_HOST="0.0.0.0" \
    --env NODE_PORT=5000 \
    --env COORDINATOR_DISCOVERY="auto" \
    --env COORDINATOR_HOST="$COORD_HOST" \
    --env INDEX_PATH=/home/app/shared_files \
    --env DATA_PATH=/home/app/data \
    --env INIT_FILES_PATH=/home/app/shared_files \
    --env AUTO_INDEX=true \
    --env LOG_LEVEL=INFO \
    search-engine:distributed

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Contenedor $CONTAINER_NAME iniciado."
    echo "📝 Logs: docker logs -f $CONTAINER_NAME"
else
    echo "❌ Error al iniciar contenedor."
fi
