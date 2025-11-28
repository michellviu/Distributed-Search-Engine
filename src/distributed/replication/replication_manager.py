import socket
import json
import logging
import threading
from typing import List
from pathlib import Path
from .consistent_hash_ring import ConsistentHashRing

class ReplicationManager:
    """
    Gestiona la replicación usando Consistent Hashing.
    Determina determinísticamente dónde va cada archivo.
    
    TOLERANCIA A FALLOS:
    - Con REPLICATION_FACTOR = 3, cada documento está en 3 nodos
    - Esto permite tolerar la caída de hasta 2 nodos sin perder datos
    - Si hay menos de 3 nodos en el cluster, se replica a todos los disponibles
      pero el sistema advierte que no hay tolerancia completa a fallos
    """
    
    REPLICATION_FACTOR = 3  # Total de copias deseadas (1 primaria + 2 backups)
    MIN_NODES_FOR_FAULT_TOLERANCE = 3  # Mínimo de nodos para tolerar caída de 2
    
    def __init__(self, discovery, node_id, repository=None):
        self.discovery = discovery
        self.node_id = node_id
        self.repository = repository
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
        Se llama cuando:
        - Un nodo muere (redistribuir a nodos supervivientes)
        - Un nodo se recupera o se une nuevo (redistribuir para balancear)
        - Al inicio del nodo (sincronizar con el cluster)
        
        Recorre todos los archivos locales y verifica si necesitan ser replicados
        a nuevos nodos debido al cambio en la topología del anillo.
        
        IMPORTANTE: Garantiza que cada archivo esté en al menos REPLICATION_FACTOR
        nodos (3 por defecto) para tolerar la caída de hasta 2 nodos.
        """
        self.logger.info("Verificando redundancia de archivos locales...")
        self._update_ring() # Actualizar anillo con la topología actual
        
        # Verificar estado del cluster
        unique_nodes = len(set(self.hash_ring.ring.values()))
        if unique_nodes < self.MIN_NODES_FOR_FAULT_TOLERANCE:
            self.logger.warning(
                f"⚠️ ALERTA: Solo hay {unique_nodes} nodos en el cluster. "
                f"Se requieren al menos {self.MIN_NODES_FOR_FAULT_TOLERANCE} para "
                f"tolerar la caída de 2 nodos."
            )
        else:
            self.logger.info(
                f"✅ Cluster con {unique_nodes} nodos - tolerancia a 2 fallos garantizada"
            )
        
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
        
        El archivo se replica a REPLICATION_FACTOR nodos (por defecto 3).
        Si hay menos nodos disponibles, se replica a todos los que haya
        pero se registra una advertencia.
        """
        self._update_ring() # Asegurar que tenemos la vista actual de la red
        
        # Verificar cuántos nodos únicos hay en el anillo
        unique_nodes = len(set(self.hash_ring.ring.values()))
        
        # Obtener los nodos responsables según el nombre del archivo
        target_node_ids = self.hash_ring.get_nodes_for_replication(file_name, self.REPLICATION_FACTOR)
        
        # Advertir si no hay suficientes nodos para la tolerancia a fallos deseada
        if len(target_node_ids) < self.REPLICATION_FACTOR:
            self.logger.warning(
                f"⚠️ Archivo '{file_name}': Solo {len(target_node_ids)} réplicas posibles "
                f"(se necesitan {self.REPLICATION_FACTOR} para tolerar 2 caídas). "
                f"Nodos disponibles: {unique_nodes}"
            )
        
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

    def get_replication_status(self) -> dict:
        """
        Devuelve el estado de replicación de todos los archivos locales.
        Útil para monitoreo y verificación de tolerancia a fallos.
        
        Returns:
            dict: {
                'cluster_status': 'OK' | 'DEGRADED' | 'CRITICAL',
                'total_nodes': int,
                'required_nodes': int,
                'files': [
                    {
                        'file_name': str,
                        'target_nodes': list[str],
                        'replica_count': int,
                        'meets_requirement': bool
                    }
                ]
            }
        """
        self._update_ring()
        
        unique_nodes = len(set(self.hash_ring.ring.values()))
        
        # Determinar estado del cluster
        if unique_nodes >= self.REPLICATION_FACTOR:
            cluster_status = 'OK'
        elif unique_nodes >= 2:
            cluster_status = 'DEGRADED'  # Puede tolerar 1 caída
        else:
            cluster_status = 'CRITICAL'  # Sin tolerancia a fallos
        
        files_status = []
        shared_dir = Path('shared_files')
        
        if shared_dir.exists():
            for file_path in shared_dir.iterdir():
                if file_path.is_file():
                    file_name = file_path.name
                    target_nodes = self.hash_ring.get_nodes_for_replication(
                        file_name, self.REPLICATION_FACTOR
                    )
                    files_status.append({
                        'file_name': file_name,
                        'target_nodes': target_nodes,
                        'replica_count': len(target_nodes),
                        'meets_requirement': len(target_nodes) >= self.REPLICATION_FACTOR
                    })
        
        return {
            'cluster_status': cluster_status,
            'total_nodes': unique_nodes,
            'required_nodes': self.REPLICATION_FACTOR,
            'fault_tolerance': max(0, unique_nodes - 1),  # Cuántos nodos pueden caer
            'files': files_status
        }