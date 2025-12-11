#!/usr/bin/env python3
"""
Script para iniciar un Nodo Coordinador del sistema distribuido.

El nodo coordinador NO almacena datos. Sus responsabilidades son:
- Mantener registro de nodos de procesamiento (DNS basado en CHORD)
- Monitorear la salud de los nodos de procesamiento
- Coordinar búsquedas distribuidas
- Determinar en qué nodos almacenar datos

Uso:
    python main_coordinator.py [opciones]

Opciones:
    --id, -n        ID único del coordinador (default: auto-generado)
    --host, -H      Host para bind (default: 0.0.0.0)
    --port, -p      Puerto TCP (default: 5000)

Ejemplos:
    # Iniciar coordinador con ID automático
    python main_coordinator.py -p 5000
    
    # Iniciar coordinador con ID específico
    python main_coordinator.py -n coordinator1 -p 5000
"""
import sys
import os
import logging
import argparse
import socket
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

from distributed.node.coordinator_node import CoordinatorNode

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)


def get_container_ip():
    """Obtiene la IP del contenedor/máquina"""
    try:
        # Método 1: usar hostname
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith('127.'):
            return ip
    except:
        pass
    
    # Método 2: obtener todas las IPs
    try:
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2)
        ips = result.stdout.strip().split()
        
        # Priorizar IPs de redes overlay de Docker (10.0.x.x)
        for ip in ips:
            if ip.startswith('10.0.') or ip.startswith('10.1.'):
                return ip
        
        # Fallback a cualquier IP privada
        for ip in ips:
            if ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.'):
                return ip
                
        if ips:
            return ips[0]
    except:
        pass
    
    try:
        # Método 3: conectar a un socket externo para obtener nuestra IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        pass
    
    return "0.0.0.0"


def get_coordinator_id():
    """Genera un ID único para el coordinador"""
    hostname = os.environ.get('HOSTNAME', socket.gethostname())
    short_id = hostname[-8:] if len(hostname) > 8 else hostname
    return f"coord_{short_id}"


def main():
    parser = argparse.ArgumentParser(
        description='Nodo Coordinador del sistema de búsqueda distribuido',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Iniciar coordinador en puerto por defecto
  python main_coordinator.py
  
  # Iniciar coordinador con ID específico
  python main_coordinator.py -n coordinator1 -p 5000
  
  # Especificar host de anuncio
  python main_coordinator.py -H 0.0.0.0 -p 5000
"""
    )
    parser.add_argument('--id', '-n', type=str, default=None,
                        help='ID único del coordinador (default: auto-generado)')
    parser.add_argument('--port', '-p', type=int, default=5000,
                        help='Puerto TCP (default: 5000)')
    parser.add_argument('--host', '-H', type=str, default='0.0.0.0',
                        help='Host/IP para bind (default: 0.0.0.0)')
    
    args = parser.parse_args()
    
    # Obtener IP real para anunciarse
    announce_host = get_container_ip() if args.host == '0.0.0.0' else args.host
    coordinator_id = args.id or get_coordinator_id()
    
    # También obtener ID de variable de entorno
    if not args.id:
        env_id = os.environ.get('COORDINATOR_ID')
        if env_id:
            coordinator_id = env_id
    
    print("=" * 60)
    print("   NODO COORDINADOR - Sistema de Búsqueda Distribuido")
    print("=" * 60)
    print(f"   Coordinator ID:  {coordinator_id}")
    print(f"   Bind Host:       {args.host}")
    print(f"   Announce Host:   {announce_host}")
    print(f"   Port:            {args.port}")
    print("=" * 60)
    print("   Rol: COORDINADOR (no almacena datos)")
    print("   - Registra nodos de procesamiento")
    print("   - Coordina búsquedas distribuidas")
    print("   - Determina almacenamiento con CHORD DNS")
    print("=" * 60)
    
    # Crear y arrancar coordinador
    coordinator = CoordinatorNode(
        coordinator_id=coordinator_id,
        host=args.host,
        port=args.port,
        announce_host=announce_host
    )
    
    try:
        coordinator.start()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupción recibida...")
    finally:
        coordinator.stop()


if __name__ == '__main__':
    main()
