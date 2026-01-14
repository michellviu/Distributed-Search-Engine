#!/bin/bash
# =============================================================================
# Script para ejecutar el Cliente GUI dentro de Docker
# Permite resolver hostnames internos (coordinator1, manual_coord_3, etc.)
# =============================================================================

echo "=========================================="
echo "  Cliente GUI - Docker (Red Overlay)"
echo "=========================================="
echo ""

# Verificar si estamos en el directorio correcto
if [ ! -f "Dockerfile.client" ]; then
    echo "❌ Error: Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Nombre de la imagen
IMAGE_NAME="search-engine-client:gui"
CONTAINER_NAME="search_client_gui"
NETWORK="search_search-network"

# Construir imagen si no existe o si se pide
if [ "$1" == "--build" ] || [ "$(docker images -q $IMAGE_NAME 2>/dev/null)" == "" ]; then
    echo "🔨 Construyendo imagen del cliente..."
    docker build -f Dockerfile.client -t $IMAGE_NAME .
    if [ $? -ne 0 ]; then
        echo "❌ Error construyendo la imagen"
        exit 1
    fi
    echo "✅ Imagen construida"
    echo ""
fi

# Verificar que la red existe
if ! docker network ls | grep -q "$NETWORK"; then
    echo "❌ Error: La red '$NETWORK' no existe."
    echo "   Primero despliega el stack: docker stack deploy -c docker-compose.yml search"
    exit 1
fi

# Eliminar contenedor anterior si existe
docker rm -f $CONTAINER_NAME 2>/dev/null

# Permitir acceso X11 local para Docker
echo "🖥️  Configurando acceso X11..."
xhost +local:docker 2>/dev/null || true

echo ""
echo "📋 Configuración:"
echo "   - Red: $NETWORK"
echo "   - Display: $DISPLAY"
echo "   - Coordinadores iniciales: coordinator1:5000, coordinator2:5000"
echo ""
echo "🚀 Iniciando cliente..."
echo ""

# Ejecutar el cliente en la red del stack
# Usa client_config_docker.json que tiene hostnames internos (coordinator1, coordinator2)
docker run -it --rm \
    --name $CONTAINER_NAME \
    --network $NETWORK \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$(pwd)/downloads:/home/app/downloads" \
    -v "$(pwd)/config:/home/app/config" \
    $IMAGE_NAME python3 src/client/client_gui.py --config config/client_config_docker.json

# Restaurar permisos X11
xhost -local:docker 2>/dev/null || true

echo ""
echo "✅ Cliente terminado"
