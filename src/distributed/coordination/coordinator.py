"""
Coordinador del cluster con elección de líder usando Bully Algorithm
"""
import socket
import json
import threading
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class NodeRole(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    COORDINATOR = "coordinator"


@dataclass
class CoordinatorState:
    """Estado del coordinador actual"""
    node_id: str
    host: str
    port: int
    elected_at: float


class LeaderElection:
    """
    Implementación del Bully Algorithm para elección de líder.
    El nodo con el ID más alto gana.
    """
    
    ELECTION_TIMEOUT = 5  # segundos para esperar respuesta
    
    def __init__(self, node_id: str, discovery):
        self.node_id = node_id
        self.discovery = discovery
        self.current_leader: Optional[CoordinatorState] = None
        self.role = NodeRole.FOLLOWER
        self.election_in_progress = False
        self._lock = threading.Lock()
        self.logger = logging.getLogger(f"Election-{node_id}")
        
        # Callbacks para notificar cambios de liderazgo
        self.on_became_leader: List[callable] = []
        self.on_leader_changed: List[callable] = []
        
    def start_election(self):
        """Inicia proceso de elección"""
        with self._lock:
            if self.election_in_progress:
                return
            self.election_in_progress = True
            self.role = NodeRole.CANDIDATE
            
        self.logger.info("🗳️ Iniciando elección de líder...")
        
        # Obtener nodos con ID mayor al nuestro
        active_nodes = self.discovery.get_active_nodes()
        higher_nodes = [n for n in active_nodes if n.node_id > self.node_id]
        
        if not higher_nodes:
            # Somos el nodo con ID más alto, nos convertimos en líder
            self._become_leader()
            return
            
        # Enviar mensaje ELECTION a nodos superiores
        responses_received = False
        threads = []
        results = []

        def ask_node(node):
            try:
                resp = self._send_election_message(node)
                if resp and resp.get('status') == 'ok':
                    results.append(True)
                    self.logger.info(f"Nodo {node.node_id} respondió a elección")
            except Exception:
                pass

        for node in higher_nodes:
            t = threading.Thread(target=ask_node, args=(node,))
            t.start()
            threads.append(t)

        # Esperar a que terminen (máximo el tiempo del timeout del socket)
        for t in threads:
            t.join()

        if any(results):
            # Esperar a que un nodo superior se declare líder
            self.role = NodeRole.FOLLOWER
            with self._lock:
                self.election_in_progress = False
        else:
            # Ningún nodo superior respondió, somos el líder
            self._become_leader()
                
    def _become_leader(self):
        """Convertirse en el coordinador del cluster"""
        self.role = NodeRole.COORDINATOR
        self.current_leader = CoordinatorState(
            node_id=self.node_id,
            host=self.discovery.host,
            port=self.discovery.port,
            elected_at=time.time()
        )
        
        with self._lock:
            self.election_in_progress = False
            
        self.logger.info(f"👑 Este nodo es ahora el COORDINADOR")
        
        # Anunciar a todos los nodos
        self._announce_leadership()
        
        # Notificar callbacks
        for callback in self.on_became_leader:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error en callback on_became_leader: {e}")
                
    def _announce_leadership(self):
        """Anuncia a todos los nodos que somos el líder"""
        active_nodes = self.discovery.get_active_nodes()
        
        for node in active_nodes:
            if node.node_id == self.node_id:
                continue
            try:
                self._send_coordinator_message(node)
            except Exception as e:
                self.logger.debug(f"Error anunciando liderazgo a {node.node_id}: {e}")
                
    def _send_election_message(self, node) -> Optional[Dict]:
        """Envía mensaje de elección a un nodo"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.ELECTION_TIMEOUT)
                sock.connect((node.host, node.port))
                
                request = {
                    'action': 'election',
                    'from_node': self.node_id
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Esperar respuesta
                header = sock.recv(8).decode().strip()
                if header:
                    response_data = sock.recv(int(header)).decode()
                    return json.loads(response_data)
                    
        except Exception as e:
            self.logger.debug(f"Error en mensaje de elección: {e}")
        return None
        
    def _send_coordinator_message(self, node):
        """Anuncia que somos el nuevo coordinador"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((node.host, node.port))
                
                request = {
                    'action': 'coordinator',
                    'coordinator_id': self.node_id,
                    'coordinator_host': self.discovery.host,
                    'coordinator_port': self.discovery.port
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
        except Exception as e:
            self.logger.debug(f"Error anunciando coordinador: {e}")
            
    def handle_election_message(self, from_node: str) -> Dict:
        """Maneja mensaje de elección recibido"""
        self.logger.info(f"Recibido mensaje de elección de {from_node}")
        
        # Si nuestro ID es mayor, respondemos OK y empezamos nuestra propia elección
        if self.node_id > from_node:
            # Iniciar nuestra propia elección en background
            threading.Thread(target=self.start_election, daemon=True).start()
            return {'status': 'ok', 'message': 'Higher node taking over'}
        
        return {'status': 'ok', 'message': 'Acknowledged'}
        
    def handle_coordinator_message(self, coordinator_id: str, host: str, port: int):
        """Maneja anuncio de nuevo coordinador"""
        self.logger.info(f"👑 Nuevo coordinador: {coordinator_id}")
        
        self.current_leader = CoordinatorState(
            node_id=coordinator_id,
            host=host,
            port=port,
            elected_at=time.time()
        )
        self.role = NodeRole.FOLLOWER
        
        # Notificar callbacks
        for callback in self.on_leader_changed:
            try:
                callback(self.current_leader)
            except Exception as e:
                self.logger.error(f"Error en callback on_leader_changed: {e}")
                
    def is_leader(self) -> bool:
        """Verifica si este nodo es el líder"""
        return self.role == NodeRole.COORDINATOR
        
    def get_leader(self) -> Optional[CoordinatorState]:
        """Obtiene información del líder actual"""
        return self.current_leader


class LoadBalancer:
    """
    Balanceador de carga usando Round-Robin con health awareness.
    Solo el coordinador ejecuta esto activamente.
    """
    
    def __init__(self, discovery, heartbeat):
        self.discovery = discovery
        self.heartbeat = heartbeat
        self.current_index = 0
        self._lock = threading.Lock()
        self.logger = logging.getLogger("LoadBalancer")
        
    def get_next_node(self):
        """
        Obtiene el siguiente nodo saludable usando Round-Robin.
        Retorna None si no hay nodos disponibles.
        """
        healthy_node_ids = set(self.heartbeat.get_healthy_nodes())
        active_nodes = [
            n for n in self.discovery.get_active_nodes() 
            if n.node_id in healthy_node_ids
        ]
        
        if not active_nodes:
            self.logger.warning("No hay nodos saludables disponibles")
            return None
            
        with self._lock:
            self.current_index = self.current_index % len(active_nodes)
            selected = active_nodes[self.current_index]
            self.current_index += 1
            
        self.logger.debug(f"Balanceando a nodo: {selected.node_id}")
        return selected
        
    def get_nodes_for_query(self, count: int = 3) -> List:
        """
        Obtiene múltiples nodos para búsqueda distribuida.
        """
        healthy_node_ids = set(self.heartbeat.get_healthy_nodes())
        active_nodes = [
            n for n in self.discovery.get_active_nodes() 
            if n.node_id in healthy_node_ids
        ]
        
        return active_nodes[:count] if len(active_nodes) >= count else active_nodes