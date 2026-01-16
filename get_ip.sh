#!/bin/bash
# Obtiene la IP de un contenedor por su nombre
if [ -z "$1" ]; then
    echo "Uso: ./get_ip.sh <nombre_contenedor>"
    exit 1
fi
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $1
