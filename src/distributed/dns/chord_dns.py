"""
DNS basado en CHORD para el sistema distribuido.

Este módulo implementa un sistema de resolución de nombres (DNS) para los nodos
de procesamiento, permitiendo que los nodos coordinadores puedan:
1. Registrar nodos de procesamiento con su ID y dirección IP
2. Buscar la dirección de un nodo dado su ID
3. Búsquedas eficientes O(log N) usando finger tables

El CHORD DNS se utiliza SOLO para localizar nodos (mapeo ID -> IP).
NO se usa para decidir dónde almacenar archivos (eso lo decide el coordinador
por balanceo de carga).
"""
import hashlib
import bisect
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class NodeAddress:
    """Información de dirección de un nodo de procesamiento"""
    node_id: str
    host: str
    port: int
    registered_at: float
    last_seen: float
    
    def to_dict(self) -> dict:
        return {
            'node_id': self.node_id,
            'host': self.host,
            'port': self.port,
            'registered_at': self.registered_at,
            'last_seen': self.last_seen
        }


class ChordDNS:
    """
    Sistema DNS basado en CHORD para resolución de nodos de procesamiento.
    
    Características:
    - Mapeo ID -> (IP, Puerto)
    - Nodos virtuales para distribución uniforme en el anillo
    - Finger table para búsquedas O(log N)
    - Thread-safe para uso concurrente
    
    IMPORTANTE: Este DNS solo se usa para localizar nodos, NO para
    decidir dónde almacenar archivos.
    """
    
    VIRTUAL_NODES = 3  # Nodos virtuales por nodo real para mejor distribución
    M = 160  # Bits del espacio de hash (SHA-1)
    
    def __init__(self, coordinator_id: str):
        self.coordinator_id = coordinator_id
        self.logger = logging.getLogger(f"ChordDNS-{coordinator_id}")
        
        # Tabla principal: node_id -> NodeAddress
        self.nodes: Dict[str, NodeAddress] = {}
        
        # Anillo de hash para organización de nodos
        self.ring: Dict[int, str] = {}  # hash -> node_id
        self.sorted_keys: List[int] = []
        
        # Finger table para búsquedas rápidas
        self.finger_table: List[Optional[str]] = [None] * self.M
        
        self._lock = threading.RLock()
        
    def _hash(self, key: str) -> int:
        """Genera un hash SHA-1 para una clave"""
        return int(hashlib.sha1(key.encode('utf-8')).hexdigest(), 16)
    
    def register_node(self, node_id: str, host: str, port: int) -> bool:
        """
        Registra un nodo de procesamiento en el DNS.
        
        Args:
            node_id: Identificador único del nodo
            host: Dirección IP del nodo
            port: Puerto TCP del nodo
            
        Returns:
            True si el registro fue exitoso
        """
        with self._lock:
            current_time = time.time()
            
            if node_id in self.nodes:
                # Actualizar nodo existente
                self.nodes[node_id].host = host
                self.nodes[node_id].port = port
                self.nodes[node_id].last_seen = current_time
                self.logger.debug(f"📝 Nodo actualizado en DNS: {node_id} -> {host}:{port}")
            else:
                # Registrar nuevo nodo
                self.nodes[node_id] = NodeAddress(
                    node_id=node_id,
                    host=host,
                    port=port,
                    registered_at=current_time,
                    last_seen=current_time
                )
                self.logger.info(f"✅ Nodo registrado en DNS: {node_id} -> {host}:{port}")
                
                # Añadir al anillo
                self._add_to_ring(node_id)
                
                # Reconstruir finger table
                self._rebuild_finger_table()
            
            return True
    
    def unregister_node(self, node_id: str) -> bool:
        """
        Elimina un nodo de procesamiento del DNS.
        """
        with self._lock:
            if node_id not in self.nodes:
                return False
            
            del self.nodes[node_id]
            self._remove_from_ring(node_id)
            self._rebuild_finger_table()
            
            self.logger.info(f"🗑️ Nodo eliminado del DNS: {node_id}")
            return True
    
    def _add_to_ring(self, node_id: str):
        """Añade un nodo al anillo con nodos virtuales"""
        for i in range(self.VIRTUAL_NODES):
            key = self._hash(f"{node_id}:{i}")
            self.ring[key] = node_id
            bisect.insort(self.sorted_keys, key)
    
    def _remove_from_ring(self, node_id: str):
        """Elimina un nodo del anillo"""
        keys_to_remove = [k for k, v in self.ring.items() if v == node_id]
        for key in keys_to_remove:
            del self.ring[key]
            self.sorted_keys.remove(key)
    
    def _rebuild_finger_table(self):
        """Reconstruye la finger table para búsquedas O(log N)"""
        if not self.sorted_keys:
            self.finger_table = [None] * self.M
            return
        
        my_hash = self._hash(self.coordinator_id)
        max_value = 2 ** self.M
        
        for i in range(self.M):
            target = (my_hash + (2 ** i)) % max_value
            successor = self._find_successor(target)
            self.finger_table[i] = successor
    
    def _find_successor(self, target_hash: int) -> Optional[str]:
        """Encuentra el nodo sucesor para un hash dado"""
        if not self.sorted_keys:
            return None
        
        idx = bisect.bisect(self.sorted_keys, target_hash)
        if idx == len(self.sorted_keys):
            idx = 0
        
        return self.ring.get(self.sorted_keys[idx])
    
    def lookup(self, node_id: str) -> Optional[NodeAddress]:
        """Busca la información completa de un nodo por su ID"""
        with self._lock:
            return self.nodes.get(node_id)
    
    def resolve(self, node_id: str) -> Optional[Tuple[str, int]]:
        """Resuelve un node_id a su dirección (host, port)"""
        with self._lock:
            node = self.nodes.get(node_id)
            if node:
                return (node.host, node.port)
            return None
    
    def get_all_nodes(self) -> List[NodeAddress]:
        """Obtiene lista de todos los nodos registrados"""
        with self._lock:
            return list(self.nodes.values())
    
    def get_active_nodes(self, max_age_seconds: float = 30.0) -> List[NodeAddress]:
        """Obtiene nodos activos (vistos recientemente)"""
        with self._lock:
            current_time = time.time()
            return [
                node for node in self.nodes.values()
                if (current_time - node.last_seen) <= max_age_seconds
            ]
    
    def update_last_seen(self, node_id: str) -> bool:
        """Actualiza el timestamp de último contacto de un nodo"""
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].last_seen = time.time()
                return True
            return False
    
    def get_stats(self) -> dict:
        """Obtiene estadísticas del DNS"""
        with self._lock:
            return {
                'total_nodes': len(self.nodes),
                'ring_size': len(self.sorted_keys),
                'virtual_nodes_per_real': self.VIRTUAL_NODES,
                'nodes': [n.to_dict() for n in self.nodes.values()]
            }
    
    def __str__(self) -> str:
        with self._lock:
            return f"ChordDNS(coordinator={self.coordinator_id}, nodes={len(self.nodes)})"
