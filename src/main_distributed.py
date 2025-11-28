#!/usr/bin/env python3
"""
Script principal para ejecutar un nodo del sistema distribuido.

Uso:
    python main_distributed.py [opciones]

Opciones:
    --node-id, -n     ID único del nodo (default: auto-generado)
    --host, -H        Host del nodo (default: 0.0.0.0)
    --port, -p        Puerto TCP (default: 5000)
    --index-path, -i  Directorio de archivos (default: shared_files)
    --peers           Lista de peers iniciales (host:port,host:port,...)

Descubrimiento:
    El sistema usa UDP Multicast (239.255.255.250:5007) para descubrir nodos
    automáticamente. También puede usar seed nodes para conexión directa.
"""
import sys
import os
import logging
import argparse
import socket
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

from distributed.node.peer_node import PeerNode

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
    
    try:
        # Método 2: conectar a un socket externo para obtener nuestra IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        pass
    
    return "0.0.0.0"


def get_node_id():
    """Genera un ID único para el nodo basado en hostname"""
    hostname = os.environ.get('HOSTNAME', socket.gethostname())
    # Usar los últimos 12 caracteres del hostname para IDs más cortos
    short_id = hostname[-12:] if len(hostname) > 12 else hostname
    return f"node_{short_id}"


def main():
    parser = argparse.ArgumentParser(
        description='Nodo del sistema de búsqueda distribuido',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Iniciar primer nodo
  python main_distributed.py -n node1 -p 5000
  
  # Iniciar segundo nodo conectándose al primero
  python main_distributed.py -n node2 -p 5001 --peers 192.168.1.100:5000
  
  # Iniciar nodo con múltiples seeds
  python main_distributed.py --peers 10.0.0.1:5000,10.0.0.2:5000
"""
    )
    parser.add_argument('--node-id', '-n', type=str, default=None,
                        help='ID único del nodo (default: auto-generado)')
    parser.add_argument('--port', '-p', type=int, default=5000,
                        help='Puerto TCP (default: 5000)')
    parser.add_argument('--host', '-H', type=str, default='0.0.0.0',
                        help='Host/IP para bind (default: 0.0.0.0)')
    parser.add_argument('--index-path', '-i', type=str, default='shared_files',
                        help='Directorio de archivos (default: shared_files)')
    parser.add_argument('--peers', type=str, default=None,
                        help='Seed peers: host1:port1,host2:port2,...')
    
    args = parser.parse_args()
    
    # Obtener IP real para anunciarse
    announce_host = get_container_ip() if args.host == '0.0.0.0' else args.host
    node_id = args.node_id or get_node_id()
    
    # Parsear peers iniciales
    seed_nodes = []
    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                if ':' in peer:
                    host, port = peer.split(':')
                    seed_nodes.append((host.strip(), int(port.strip())))
                else:
                    seed_nodes.append((peer.strip(), 5000))
    
    # También obtener peers de variable de entorno
    env_peers = os.environ.get('SEED_NODES', '')
    if env_peers:
        for peer in env_peers.split(','):
            peer = peer.strip()
            if peer:
                if ':' in peer:
                    host, port = peer.split(':')
                    seed_nodes.append((host.strip(), int(port.strip())))
                else:
                    seed_nodes.append((peer.strip(), 5000))
    
    print("=" * 60)
    print("   SISTEMA DE BÚSQUEDA DISTRIBUIDO")
    print("   Descubrimiento: UDP Multicast + Seed Nodes")
    print("=" * 60)
    print(f"   Node ID:       {node_id}")
    print(f"   Bind Host:     {args.host}")
    print(f"   Announce Host: {announce_host}")
    print(f"   Port:          {args.port}")
    print(f"   Index Path:    {args.index_path}")
    print(f"   Seed Nodes:    {seed_nodes if seed_nodes else 'Ninguno'}")
    print(f"   Multicast:     239.255.255.250:5007")
    print("=" * 60)
    
    # Crear y arrancar nodo
    # Usar 0.0.0.0 para bind (aceptar conexiones de cualquier interfaz)
    # pero announce_host para anunciarse a otros nodos
    node = PeerNode(
        node_id=node_id,
        host=args.host,  # 0.0.0.0 para bind
        port=args.port,
        index_path=args.index_path,
        seed_nodes=seed_nodes,
        announce_host=announce_host  # IP real para anunciarse
    )
    
    try:
        node.start()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupción recibida...")
    finally:
        node.stop()


if __name__ == '__main__':
    main()
