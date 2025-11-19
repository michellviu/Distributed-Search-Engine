# src/distributed/discovery/node_discovery.py
import socket
import json
import threading
import time
from typing import Dict, Callable, List
from dataclasses import dataclass, asdict

@dataclass
class NodeInfo:
    """Información de un nodo"""
    node_id: str
    host: str
    port: int
    node_type: str  # 'peer' o 'coordinator'
    last_seen: float
    load: int = 0  # Número de documentos indexados
    
class NodeDiscovery:
    """
    Descubrimiento automático de nodos usando UDP Broadcast
    """
    
    BROADCAST_PORT = 5555
    ANNOUNCE_INTERVAL = 5  # segundos
    NODE_TIMEOUT = 15      # segundos
    
    def __init__(self, node_id: str, node_type: str, 
                 host: str, port: int):
        self.node_id = node_id
        self.node_type = node_type
        self.host = host
        self.port = port
        
        # Registro de nodos conocidos
        self.nodes: Dict[str, NodeInfo] = {}
        
        # Callbacks cuando hay cambios
        self.on_node_discovered: List[Callable] = []
        self.on_node_lost: List[Callable] = []
        
        self.running = False
        self._lock = threading.Lock()
        
    def start(self):
        """Iniciar descubrimiento"""
        self.running = True
        
        # Thread 1: Anunciar este nodo
        threading.Thread(target=self._announce_loop, daemon=True).start()
        
        # Thread 2: Escuchar anuncios
        threading.Thread(target=self._listen_loop, daemon=True).start()
        
        # Thread 3: Limpiar nodos muertos
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        
    def stop(self):
        self.running = False
        
    def _announce_loop(self):
        """Anunciar existencia por broadcast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        while self.running:
            message = {
                'type': 'NODE_ANNOUNCE',
                'node_id': self.node_id,
                'node_type': self.node_type,
                'host': self.host,
                'port': self.port,
                'timestamp': time.time()
            }
            
            try:
                sock.sendto(
                    json.dumps(message).encode(),
                    ('<broadcast>', self.BROADCAST_PORT)
                )
            except Exception as e:
                print(f"Error anunciando: {e}")
                
            time.sleep(self.ANNOUNCE_INTERVAL)
            
    def _listen_loop(self):
        """Escuchar anuncios de otros nodos"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.BROADCAST_PORT))
        sock.settimeout(1.0)
        
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                message = json.loads(data.decode())
                
                if message['type'] == 'NODE_ANNOUNCE':
                    self._handle_node_announce(message)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error escuchando: {e}")
                
    def _handle_node_announce(self, message: dict):
        """Procesar anuncio de nodo"""
        node_id = message['node_id']
        
        # Ignorarnos a nosotros mismos
        if node_id == self.node_id:
            return
            
        with self._lock:
            is_new = node_id not in self.nodes
            
            node_info = NodeInfo(
                node_id=node_id,
                node_type=message['node_type'],
                host=message['host'],
                port=message['port'],
                last_seen=time.time()
            )
            
            self.nodes[node_id] = node_info
            
            if is_new:
                print(f"✓ Nodo descubierto: {node_id} ({message['host']}:{message['port']})")
                for callback in self.on_node_discovered:
                    callback(node_info)
                    
    def _cleanup_loop(self):
        """Eliminar nodos que no responden"""
        while self.running:
            current_time = time.time()
            
            with self._lock:
                dead_nodes = []
                for node_id, node_info in list(self.nodes.items()):
                    if current_time - node_info.last_seen > self.NODE_TIMEOUT:
                        dead_nodes.append(node_id)
                        
                for node_id in dead_nodes:
                    node_info = self.nodes.pop(node_id)
                    print(f"✗ Nodo perdido: {node_id}")
                    for callback in self.on_node_lost:
                        callback(node_info)
                        
            time.sleep(5)
            
    def get_active_nodes(self) -> List[NodeInfo]:
        """Obtener lista de nodos activos"""
        with self._lock:
            return list(self.nodes.values())
            
    def get_node(self, node_id: str) -> NodeInfo:
        """Obtener información de un nodo específico"""
        with self._lock:
            return self.nodes.get(node_id)