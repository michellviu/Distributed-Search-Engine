#!/bin/bash
# Script para desplegar el sistema distribuido con Docker Swarm
# 
# Uso:
#   ./deploy-distributed.sh          # Despliegue básico (1 coord, 3 processing)
#   ./deploy-distributed.sh --scale 5  # Despliegue con 5 nodos de procesamiento

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

STACK_NAME="search"
PROCESSING_REPLICAS=3

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --scale)
            PROCESSING_REPLICAS="$2"
            shift 2
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        *)
            echo "Uso: $0 [--scale N] [--clean]"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   Distributed Search Engine - Deploy${NC}"
echo -e "${BLUE}============================================${NC}"

# Limpiar si se solicita
if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}🧹 Limpiando despliegue anterior...${NC}"
    docker stack rm "$STACK_NAME" 2>/dev/null || true
    sleep 5
    docker volume prune -f 2>/dev/null || true
fi

# Verificar si Docker Swarm está inicializado
if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
    echo -e "${YELLOW}⚠️  Docker Swarm no está activo. Inicializando...${NC}"
    docker swarm init 2>/dev/null || true
fi

# Construir la imagen
echo -e "${GREEN}🔨 Construyendo imagen Docker...${NC}"
docker build -f Dockerfile.distributed -t search-engine:distributed .

# Copiar archivos de prueba al volumen
echo -e "${GREEN}📁 Preparando archivos de prueba...${NC}"

# Crear volumen y copiar archivos
docker volume create shared-files 2>/dev/null || true

# Usar un contenedor temporal para copiar archivos
docker run --rm \
    -v shared-files:/data \
    -v "$SCRIPT_DIR/shared_files:/source:ro" \
    alpine sh -c "cp -r /source/* /data/ 2>/dev/null || true"

echo -e "${GREEN}   ✓ Archivos copiados a volumen shared-files${NC}"

# Desplegar el stack
echo -e "${GREEN}🚀 Desplegando stack '$STACK_NAME'...${NC}"
docker stack deploy -c docker-compose.yml "$STACK_NAME"

# Esperar a que los servicios estén listos
echo -e "${YELLOW}⏳ Esperando a que los servicios inicien...${NC}"
sleep 10

# Escalar nodos de procesamiento si se especificó
if [ "$PROCESSING_REPLICAS" != "3" ]; then
    echo -e "${GREEN}📈 Escalando nodos de procesamiento a $PROCESSING_REPLICAS...${NC}"
    docker service scale "${STACK_NAME}_processing=$PROCESSING_REPLICAS"
    sleep 5
fi

# Mostrar estado
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   Estado del Despliegue${NC}"
echo -e "${BLUE}============================================${NC}"
docker stack services "$STACK_NAME"

echo ""
echo -e "${GREEN}✅ Despliegue completado${NC}"
echo ""
echo -e "${BLUE}Comandos útiles:${NC}"
echo "  Ver servicios:     docker stack services $STACK_NAME"
echo "  Ver logs coord:    docker service logs -f ${STACK_NAME}_coordinator"
echo "  Ver logs proc:     docker service logs -f ${STACK_NAME}_processing"
echo "  Escalar nodos:     docker service scale ${STACK_NAME}_processing=N"
echo "  Eliminar stack:    docker stack rm $STACK_NAME"
echo ""
echo -e "${BLUE}Probar el sistema:${NC}"
echo "  ./test-distributed.sh"
echo ""
echo -e "${BLUE}Coordinador disponible en:${NC} http://localhost:5000"
