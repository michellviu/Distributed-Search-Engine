#!/bin/bash
# Script para iniciar el cliente GUI

echo "=========================================="
echo "  Cliente GUI - Motor de Búsqueda"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d "src" ]; then
    echo "Error: Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Intentar activar entorno virtual si existe
if [ -d "$HOME/mygeneralenv" ]; then
    echo "🔧 Activando entorno virtual..."
    source $HOME/mygeneralenv/bin/activate
    echo "✓ Entorno virtual activado"
    echo ""
elif [ -d ".venv" ]; then
    echo "🔧 Activando entorno virtual local..."
    source .venv/bin/activate
    echo "✓ Entorno virtual activado"
    echo ""
fi

# Verificar tkinter (base)
python3 -c "import tkinter" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Error: Tkinter no está instalado."
    echo ""
    echo "Instala tkinter con:"
    echo "   sudo apt-get install python3-tk"
    echo ""
    exit 1
fi

# Verificar si customtkinter está instalado
python3 -c "import customtkinter" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠ Advertencia: CustomTkinter no está instalado."
    echo "   Se usará Tkinter estándar (menos moderno)."
    echo ""
    echo "Para una mejor experiencia visual, instala:"
    echo "   pip install customtkinter"
    echo ""
else
    echo "✓ CustomTkinter detectado - usando interfaz moderna"
    echo ""
fi

echo "Iniciando cliente GUI (Modo Distribuido)..."
echo ""
echo "Configuración:"
echo "  - Coordinadores: localhost:5000, localhost:5001"
echo "  - Config: config/client_config.json"
echo ""

# Iniciar el cliente GUI
# Nota: La lista de coordinadores por defecto está en config/client_config.json
# Si deseas sobreescribirla, usa: --coordinators host1:port1 host2:port2
python3 src/client/client_gui.py --config config/client_config.json
