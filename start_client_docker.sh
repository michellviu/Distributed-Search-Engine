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

# Variables de entorno
export IMAGE_NAME="search-engine-client:gui"
CONTAINER_NAME="search_client_gui"
NETWORK="search-network"

# Construir imagen SIEMPRE para asegurar que usamos Dockerfile.client y código actualizado
# (El usuario puede haber sobrescrito el tag con otra imagen manualmente)
echo "🔨 Construyendo/Actualizando imagen del cliente (Dockerfile.client)..."
docker build -f Dockerfile.client -t $IMAGE_NAME .
if [ $? -ne 0 ]; then
    echo "❌ Error construyendo la imagen"
    exit 1
fi
echo "✅ Imagen lista"
echo ""

# Verificar que la red existe
docker network inspect $NETWORK >/dev/null 2>&1 || docker network create $NETWORK
if [ $? -ne 0 ]; then
    echo "❌ Error: La red '$NETWORK' no se pudo crear/verificar."
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
echo "   - Tus archivos: /mnt/host_home"
echo ""
echo "🚀 Iniciando cliente..."
echo ""

# Ejecutar el cliente en la red del stack
# IMPORTANTE: Usar --entrypoint python3 para evitar que se ejecute start.sh (servidor)
# Usa client_config_docker.json que tiene hostnames internos (coordinator1, coordinator2)
docker run -it --rm \
    --name $CONTAINER_NAME \
    --network $NETWORK \
    --entrypoint python3 \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$(pwd)/downloads:/home/app/downloads" \
    -v "$(pwd)/config:/home/app/config" \
    -v "$HOME:/mnt/host_home" \
    -v "$HOME/.distributed-search-client:/root/.distributed-search-client" \
    $IMAGE_NAME \
    src/client/client_gui.py --config config/client_config_docker.json

# Restaurar permisos X11
xhost -local:docker 2>/dev/null || true

echo ""
echo "✅ Cliente terminado"
echo ""
echo "💡 NOTA: Tus archivos personales están disponibles en /mnt/host_home"
