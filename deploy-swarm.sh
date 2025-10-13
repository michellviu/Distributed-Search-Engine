#!/bin/bash
# Script de Despliegue Rápido - Docker Swarm

echo "================================================"
echo "  Despliegue Rápido - Motor de Búsqueda"
echo "  Docker Swarm - 2 PCs"
echo "================================================"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Función para mensajes
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar que estamos en el directorio correcto
if [ ! -f "Dockerfile" ]; then
    error "No se encontró Dockerfile. Ejecuta este script desde la raíz del proyecto."
    exit 1
fi

info "Paso 1: Verificando Docker..."
if ! command -v docker &> /dev/null; then
    error "Docker no está instalado"
    exit 1
fi
info "✓ Docker está instalado: $(docker --version)"

info "Paso 2: Construyendo imagen..."
docker build -t search-engine:latest .
if [ $? -ne 0 ]; then
    error "Fallo al construir la imagen"
    exit 1
fi
info "✓ Imagen construida correctamente"

info "Paso 3: Probando imagen localmente..."
docker run -d --name test-search -p 5000:5000 search-engine:latest
sleep 5

# Verificar que el contenedor está corriendo
if docker ps | grep -q test-search; then
    info "✓ Contenedor de prueba iniciado correctamente"
    docker logs test-search
    docker stop test-search
    docker rm test-search
else
    error "El contenedor no pudo iniciar"
    docker logs test-search
    docker rm test-search
    exit 1
fi

info "Paso 4: Verificando Swarm..."
if docker info | grep -q "Swarm: active"; then
    info "✓ Docker Swarm ya está activo"
    docker node ls
else
    warn "Docker Swarm no está inicializado"
    echo ""
    echo "Para inicializar el swarm, ejecuta:"
    echo "  docker swarm init --advertise-addr <TU_IP>"
    echo ""
    echo "Luego, en el otro PC ejecuta el comando 'docker swarm join' que se muestra."
    exit 0
fi

echo ""
info "Paso 5: ¿Desplegar el stack ahora? (s/n)"
read -r response

if [[ "$response" == "s" || "$response" == "S" ]]; then
    info "Desplegando stack..."
    docker stack deploy -c docker-stack.yml search-app
    
    echo ""
    info "Esperando a que los servicios se inicien..."
    sleep 10
    
    info "Estado de los servicios:"
    docker stack services search-app
    
    echo ""
    info "Réplicas desplegadas:"
    docker service ps search-app_search-server
    
    echo ""
    info "✓ Stack desplegado correctamente"
    info "Accede al servidor en: http://localhost:5000"
    info "Para ver logs: docker service logs search-app_search-server"
else
    info "Para desplegar manualmente, ejecuta:"
    echo "  docker stack deploy -c docker-stack.yml search-app"
fi

echo ""
info "¡Listo! 🚀"
