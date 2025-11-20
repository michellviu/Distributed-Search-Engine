import socket
import json
import logging
import threading
from typing import List
from pathlib import Path
from consistent_hash_ring import ConsistentHashRing

class ReplicationManager:
    """
    Gestiona la replicación usando Consistent Hashing.
    Determina determinísticamente dónde va cada archivo.
    """
    
    REPLICATION_FACTOR = 3  # Total de copias deseadas (1 primaria + 2 backups)
    
    def __init__(self, discovery, node_id):
        self.discovery = discovery
        self.node_id = node_id
        self.logger = logging.getLogger(f"Replication-{node_id}")
        self.hash_ring = ConsistentHashRing()
        self._update_ring() # Inicializar anillo

    def _update_ring(self):
        """Actualiza el anillo de hash con los nodos activos actuales"""
        # Nota: En un sistema real, esto debería ser reactivo a eventos de discovery
        # Por simplicidad, lo reconstruimos al necesitarlo o periódicamente
        active_nodes = self.discovery.get_active_nodes()
        
        # Reiniciar anillo (simple approach)
        self.hash_ring = ConsistentHashRing()
        
        # Añadirnos a nosotros mismos
        self.hash_ring.add_node(self.node_id)
        
        # Añadir pares
        for node in active_nodes:
            self.hash_ring.add_node(node.node_id)

    def check_redundancy(self):
        """
        Método de Auto-Curación.
        Se llama cuando un nodo muere.
        Recorre todos los archivos locales y verifica si necesitan ser replicados
        a nuevos nodos debido al cambio en la topología del anillo.
        """
        self.logger.info("Verificando redundancia de archivos locales...")
        self._update_ring() # Actualizar anillo sin el nodo muerto
        
        # Obtener lista de archivos locales (desde el disco o repositorio)
        # Asumimos que están en la carpeta 'shared_files'
        shared_dir = Path('shared_files')
        if not shared_dir.exists():
            return

        files = [f for f in shared_dir.iterdir() if f.is_file()]
        
        for file_path in files:
            file_name = file_path.name
            try:
                # Calcular dónde DEBERÍA estar este archivo ahora
                target_nodes = self.hash_ring.get_nodes_for_replication(file_name, self.REPLICATION_FACTOR)
                target_ids = [n for n in target_nodes]
                
                # Si yo tengo el archivo, soy responsable de asegurar que las réplicas existan.
                # Simplemente volvemos a ejecutar la replicación.
                # Los nodos que ya lo tengan simplemente lo sobrescribirán (idempotencia).
                # Los nodos nuevos (que reemplazan al muerto) lo recibirán por primera vez.
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                    
                self.replicate_file(file_name, content)
                
            except Exception as e:
                self.logger.error(f"Error verificando redundancia para {file_name}: {e}")

    def replicate_file(self, file_name: str, file_content: bytes):
        """
        Replica el archivo a los nodos que dicta el Hashing Consistente.
        """
        self._update_ring() # Asegurar que tenemos la vista actual de la red
        
        # Obtener los nodos responsables según el nombre del archivo
        target_node_ids = self.hash_ring.get_nodes_for_replication(file_name, self.REPLICATION_FACTOR)
        
        self.logger.info(f"Archivo '{file_name}' debe estar en: {target_node_ids}")
        
        # Filtrar: No enviarnos a nosotros mismos si ya somos responsables
        targets_to_send = []
        active_nodes_map = {n.node_id: n for n in self.discovery.get_active_nodes()}
        
        for target_id in target_node_ids:
            if target_id == self.node_id:
                continue # Ya lo tenemos (somos el origen o nos tocó guardarlo)
            
            if target_id in active_nodes_map:
                targets_to_send.append(active_nodes_map[target_id])

        # Enviar réplicas
        threads = []
        for target_node in targets_to_send:
            t = threading.Thread(target=self._send_replica, args=(target_node, file_name, file_content))
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()

    def _send_replica(self, target_node, file_name: str, file_content: bytes):
        """Envía el archivo a un nodo específico"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((target_node.host, target_node.port))
                
                request = {
                    'action': 'replicate',
                    'file_name': file_name,
                    'file_size': len(file_content)
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                sock.sendall(file_content)
                
                self.logger.info(f"Réplica enviada a {target_node.node_id}")
                
        except Exception as e:
            self.logger.error(f"Fallo al replicar a {target_node.node_id}: {e}")