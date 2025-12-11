#!/bin/bash
# Docker entrypoint para el sistema distribuido

set -e

# Generar NODE_ID único si no está definido
if [ -z "$NODE_ID" ] || [ "$NODE_ID" = "node-1" ]; then
    # Usar hostname del contenedor que incluye el slot de Swarm
    CONTAINER_ID=$(hostname)
    NODE_ID="${NODE_ROLE}-${CONTAINER_ID}"
fi

echo "============================================"
echo "   Distributed Search Engine - Starting"
echo "============================================"
echo "NODE_ROLE:        $NODE_ROLE"
echo "NODE_ID:          $NODE_ID"
echo "NODE_HOST:        $NODE_HOST"
echo "NODE_PORT:        $NODE_PORT"
echo "COORDINATOR_HOST: $COORDINATOR_HOST"
echo "COORDINATOR_PORT: $COORDINATOR_PORT"
echo "ANNOUNCE_HOST:    $ANNOUNCE_HOST"
echo "INDEX_PATH:       $INDEX_PATH"
echo "INIT_FILES_PATH:  $INIT_FILES_PATH"
echo "AUTO_INDEX:       $AUTO_INDEX"
echo "============================================"

# Función para esperar a que el coordinador esté listo
wait_for_coordinator() {
    if [ "$NODE_ROLE" = "processing" ]; then
        echo "⏳ Esperando a que el coordinador esté disponible..."
        max_attempts=30
        attempt=0
        while [ $attempt -lt $max_attempts ]; do
            if nc -z "$COORDINATOR_HOST" "$COORDINATOR_PORT" 2>/dev/null; then
                echo "✅ Coordinador disponible en $COORDINATOR_HOST:$COORDINATOR_PORT"
                return 0
            fi
            attempt=$((attempt + 1))
            echo "   Intento $attempt/$max_attempts - Esperando coordinador..."
            sleep 2
        done
        echo "⚠️  Coordinador no disponible después de $max_attempts intentos"
        echo "   Continuando de todos modos..."
    fi
}

# Función para copiar archivos iniciales al directorio de trabajo
copy_init_files() {
    if [ -n "$INIT_FILES_PATH" ] && [ -d "$INIT_FILES_PATH" ] && [ "$NODE_ROLE" = "processing" ]; then
        echo "📋 Copiando archivos iniciales de $INIT_FILES_PATH a $INDEX_PATH..."
        cp -r "$INIT_FILES_PATH"/* "$INDEX_PATH"/ 2>/dev/null || true
        file_count=$(find "$INDEX_PATH" -type f 2>/dev/null | wc -l)
        echo "   Copiados $file_count archivos"
    fi
}

# Función para auto-indexar archivos en shared_files
auto_index_files() {
    if [ "$AUTO_INDEX" = "true" ] && [ "$NODE_ROLE" = "processing" ]; then
        echo "📁 Auto-indexando archivos en $INDEX_PATH..."
        file_count=$(find "$INDEX_PATH" -type f 2>/dev/null | wc -l)
        echo "   Encontrados $file_count archivos para indexar"
    fi
}

# Preparar el directorio de índice
mkdir -p "$INDEX_PATH"
mkdir -p logs

# Determinar el host de anuncio
if [ -z "$ANNOUNCE_HOST" ]; then
    # Intentar obtener la IP del contenedor
    ANNOUNCE_HOST=$(hostname -i 2>/dev/null | awk '{print $1}' || echo "$NODE_HOST")
fi

export ANNOUNCE_HOST

echo "📡 Host de anuncio: $ANNOUNCE_HOST"

# Ejecutar según el rol
case "$NODE_ROLE" in
    "coordinator")
        echo "🎯 Iniciando como COORDINADOR..."
        exec python -m src.main_distributed \
            --role coordinator \
            --id "$NODE_ID" \
            --host "$NODE_HOST" \
            --port "$NODE_PORT" \
            --announce-host "$ANNOUNCE_HOST"
        ;;
    
    "processing")
        wait_for_coordinator
        copy_init_files
        auto_index_files
        
        echo "⚙️  Iniciando como NODO DE PROCESAMIENTO..."
        exec python -m src.main_distributed \
            --role processing \
            --id "$NODE_ID" \
            --host "$NODE_HOST" \
            --port "$NODE_PORT" \
            --coordinator-host "$COORDINATOR_HOST" \
            --coordinator-port "$COORDINATOR_PORT" \
            --announce-host "$ANNOUNCE_HOST" \
            --index-path "$INDEX_PATH"
        ;;
    
    *)
        echo "❌ NODE_ROLE no válido: $NODE_ROLE"
        echo "   Usa 'coordinator' o 'processing'"
        exit 1
        ;;
esac
