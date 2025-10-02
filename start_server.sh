#!/bin/bash
# Script de inicio rápido para el servidor de búsqueda distribuida

echo "=========================================="
echo "  Servidor de Búsqueda Distribuida"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d "src" ]; then
    echo "Error: Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Crear directorios necesarios
echo "Creando directorios necesarios..."
mkdir -p logs
mkdir -p downloads
mkdir -p shared_files

# Verificar si hay archivos en shared_files
if [ -z "$(ls -A shared_files)" ]; then
    echo ""
    echo "Advertencia: El directorio 'shared_files' está vacío."
    echo "Creando archivos de ejemplo..."
    
    echo "Este es un documento de ejemplo sobre Python" > shared_files/python_doc.txt
    echo "Este es un documento de ejemplo sobre búsqueda distribuida" > shared_files/search_doc.txt
    echo "Documento de prueba para el sistema de indexación" > shared_files/test_doc.txt
    
    echo "✓ Archivos de ejemplo creados"
fi

echo ""
echo "Iniciando servidor..."
echo ""
echo "Configuración:"
echo "  - Host: localhost"
echo "  - Puerto: 5000"
echo "  - Directorio de archivos: ./shared_files"
echo "  - Log: ./logs/server.log"
echo ""
echo "Presiona Ctrl+C para detener el servidor"
echo ""

# Iniciar el servidor (desde el directorio raíz)
python3 src/main_server.py --config config/server_config.json
