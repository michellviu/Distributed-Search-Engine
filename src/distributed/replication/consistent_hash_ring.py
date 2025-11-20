import hashlib
import bisect

class ConsistentHashRing:
    def __init__(self, replicas=3):
        self.replicas = replicas  # Nodos virtuales para mejor distribución
        self.ring = {}            # Mapa: Hash -> NodeID
        self.sorted_keys = []     # Lista ordenada de hashes

    def add_node(self, node_id):
        """Añade un nodo al anillo (con réplicas virtuales)"""
        for i in range(self.replicas):
            key = self._hash(f"{node_id}:{i}")
            self.ring[key] = node_id
            bisect.insort(self.sorted_keys, key)

    def remove_node(self, node_id):
        """Elimina un nodo del anillo"""
        keys_to_remove = []
        for key, node in self.ring.items():
            if node == node_id:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.ring[key]
            self.sorted_keys.remove(key)

    def get_node(self, key_string):
        """Devuelve el nodo responsable para una clave dada (archivo)"""
        if not self.ring:
            return None
        
        key_hash = self._hash(key_string)
        
        # Encontrar el primer nodo con hash mayor o igual al del archivo
        idx = bisect.bisect(self.sorted_keys, key_hash)
        
        # Si llegamos al final, damos la vuelta al principio (anillo)
        if idx == len(self.sorted_keys):
            idx = 0
            
        return self.ring[self.sorted_keys[idx]]

    def get_nodes_for_replication(self, key_string, n=3):
        """
        Devuelve los N nodos responsables para replicar un archivo.
        Recorre el anillo para encontrar N nodos distintos.
        """
        if not self.ring:
            return []

        primary_node = self.get_node(key_string)
        nodes = [primary_node]
        
        # Buscar los siguientes nodos distintos en el anillo
        key_hash = self._hash(key_string)
        start_idx = bisect.bisect(self.sorted_keys, key_hash)
        
        current_idx = start_idx
        while len(nodes) < n and len(nodes) < len(set(self.ring.values())):
            if current_idx >= len(self.sorted_keys):
                current_idx = 0
            
            node_hash = self.sorted_keys[current_idx]
            node_id = self.ring[node_hash]
            
            if node_id not in nodes:
                nodes.append(node_id)
            
            current_idx += 1
            
        return nodes

    def _hash(self, key):
        """Genera un hash MD5 entero"""
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)