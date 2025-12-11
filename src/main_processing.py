#!/usr/bin/env python3
"""
Script para iniciar un Nodo de Procesamiento del sistema distribuido.

El nodo de procesamiento SÍ almacena datos. Sus responsabilidades son:
- Almacenar archivos indexados
- Ejecutar búsquedas locales
- Responder a queries del coordinador
- Enviar heartbeats al coordinador

Uso:
    python main_processing.py [opciones]

Opciones:
    --id, -n            ID único del nodo (default: auto-generado)
    --host, -H          Host para bind (default: 0.0.0.0)
    --port, -p          Puerto TCP (default: 5001)
    --index-path, -i    Directorio de archivos (default: shared_files)
    --coordinator, -c   Dirección del coordinador (host:port)

Ejemplos:
    # Iniciar nodo de procesamiento conectado a coordinador
    python main_processing.py -p 5001 -c localhost:5000
    
    # Iniciar nodo con ID específico
    python main_processing.py -n proc1 -p 5001 -c 192.168.1.100:5000
"""
import sys
import os
import logging
import argparse
import socket
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

from distributed.node.processing_node import ProcessingNode

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


def get_node_id():
    """Genera un ID único para el nodo de procesamiento"""
    hostname = os.environ.get('HOSTNAME', socket.gethostname())
    short_id = hostname[-8:] if len(hostname) > 8 else hostname
    return f"proc_{short_id}"


def main():
    parser = argparse.ArgumentParser(
        description='Nodo de Procesamiento del sistema de búsqueda distribuido',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Iniciar nodo de procesamiento conectado a coordinador local
  python main_processing.py -c localhost:5000
  
  # Iniciar nodo con ID específico
  python main_processing.py -n proc1 -p 5001 -c 192.168.1.100:5000
  
  # Iniciar nodo con directorio de archivos específico
  python main_processing.py -i /data/files -c coordinator:5000
"""
    )
    parser.add_argument('--id', '-n', type=str, default=None,
                        help='ID único del nodo (default: auto-generado)')
    parser.add_argument('--port', '-p', type=int, default=5001,
                        help='Puerto TCP (default: 5001)')
    parser.add_argument('--host', '-H', type=str, default='0.0.0.0',
                        help='Host/IP para bind (default: 0.0.0.0)')
    parser.add_argument('--index-path', '-i', type=str, default='shared_files',
                        help='Directorio de archivos (default: shared_files)')
    parser.add_argument('--coordinator', '-c', type=str, default=None,
                        help='Coordinador: host:port (default: localhost:5000)')
    
    args = parser.parse_args()
    
    # Obtener IP real para anunciarse
    announce_host = get_container_ip() if args.host == '0.0.0.0' else args.host
    node_id = args.id or get_node_id()
    
    # También obtener ID de variable de entorno
    if not args.id:
        env_id = os.environ.get('NODE_ID')
        if env_id:
            node_id = env_id
    
    # Parsear coordinador
    coordinator_host = None
    coordinator_port = 5000
    
    # Primero de variable de entorno
    env_coordinator = os.environ.get('COORDINATOR_ADDRESS')
    if env_coordinator:
        if ':' in env_coordinator:
            coordinator_host, port_str = env_coordinator.split(':')
            coordinator_port = int(port_str)
        else:
            coordinator_host = env_coordinator
    
    # Luego de argumento (override)
    if args.coordinator:
        if ':' in args.coordinator:
            coordinator_host, port_str = args.coordinator.split(':')
            coordinator_port = int(port_str)
        else:
            coordinator_host = args.coordinator
    
    print("=" * 60)
    print("   NODO DE PROCESAMIENTO - Sistema de Búsqueda Distribuido")
    print("=" * 60)
    print(f"   Node ID:         {node_id}")
    print(f"   Bind Host:       {args.host}")
    print(f"   Announce Host:   {announce_host}")
    print(f"   Port:            {args.port}")
    print(f"   Index Path:      {args.index_path}")
    if coordinator_host:
        print(f"   Coordinator:     {coordinator_host}:{coordinator_port}")
    else:
        print("   Coordinator:     No configurado (modo standalone)")
    print("=" * 60)
    print("   Rol: PROCESAMIENTO (almacena datos)")
    print("   - Almacena y indexa archivos")
    print("   - Ejecuta búsquedas locales")
    print("   - Responde al coordinador")
    print("=" * 60)
    
    # Crear y arrancar nodo
    node = ProcessingNode(
        node_id=node_id,
        host=args.host,
        port=args.port,
        index_path=args.index_path,
        coordinator_host=coordinator_host,
        coordinator_port=coordinator_port,
        announce_host=announce_host
    )
    
    try:
        node.start()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupción recibida...")
    finally:
        node.stop()


if __name__ == '__main__':
    main()
