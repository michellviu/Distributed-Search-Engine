#!/usr/bin/env python3
"""
Script para inicializar datos en el cluster distribuido.

En vez de montar archivos directamente, este script sube los archivos
al cluster usando el protocolo de indexación, lo que garantiza que
se repliquen correctamente según el hash ring.

Uso:
    python init_cluster_data.py --host localhost --port 6000 --dir shared_files
"""

import socket
import json
import argparse
import os
from pathlib import Path


def send_file_to_cluster(host: str, port: int, file_path: Path, consistency: str = 'QUORUM') -> bool:
    """Sube un archivo al cluster para que sea indexado y replicado con Quorum."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # Enviar request de indexación con nivel de consistencia
        request = {
            'action': 'index',
            'file_name': file_path.name,
            'file_size': len(content),
            'consistency': consistency  # Nivel de consistencia: ONE, QUORUM, ALL
        }
        
        req_json = json.dumps(request)
        sock.sendall(f"{len(req_json):<8}".encode())
        sock.sendall(req_json.encode())
        sock.sendall(content)
        
        # Leer respuesta
        header = sock.recv(8).decode().strip()
        if header:
            response = json.loads(sock.recv(int(header)).decode())
            if response.get('status') == 'success':
                quorum = "🔐 QUORUM" if response.get('quorum_enabled') else "📦 Direct"
                print(f"✅ {file_path.name} - {quorum} replicación iniciada")
                return True
            else:
                print(f"❌ {file_path.name} - error: {response.get('message')}")
                return False
        
        sock.close()
        return True
        
    except Exception as e:
        print(f"❌ {file_path.name} - error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Inicializar datos en el cluster')
    parser.add_argument('--host', default='localhost', help='Host del nodo')
    parser.add_argument('--port', type=int, default=5000, help='Puerto del nodo')
    parser.add_argument('--dir', default='shared_files', help='Directorio con archivos')
    parser.add_argument('--consistency', choices=['ONE', 'QUORUM', 'ALL'], default='QUORUM',
                        help='Nivel de consistencia (default: QUORUM)')
    args = parser.parse_args()
    
    directory = Path(args.dir)
    if not directory.exists():
        print(f"❌ Directorio {directory} no existe")
        return 1
    
    files = [f for f in directory.iterdir() if f.is_file()]
    print(f"\n📁 Subiendo {len(files)} archivos al cluster en {args.host}:{args.port}")
    print(f"🔐 Nivel de consistencia: {args.consistency}\n")
    
    success = 0
    for file_path in files:
        if send_file_to_cluster(args.host, args.port, file_path, args.consistency):
            success += 1
    
    print(f"\n📊 Resultado: {success}/{len(files)} archivos subidos correctamente")
    print("   Los archivos se replican con consistencia Quorum.\n")
    
    return 0 if success == len(files) else 1


if __name__ == '__main__':
    exit(main())
