import socket
import json
import logging
import threading
import time
from typing import List, Set
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
    
    BALANCEO DE CARGA:
    - Cada archivo solo está en REPLICATION_FACTOR nodos (no en todos)
    - El hash ring determina qué nodos son responsables de qué archivos
    - Cuando un nodo cae, sus archivos se redistribuyen a los siguientes en el anillo
    """
    
    REPLICATION_FACTOR = 3  # Total de copias deseadas (1 primaria + 2 backups)
    MIN_NODES_FOR_FAULT_TOLERANCE = 3  # Mínimo de nodos para tolerar caída de 2
    
    def __init__(self, discovery, node_id, repository=None):
        self.discovery = discovery
        self.node_id = node_id
        self.repository = repository
        self.logger = logging.getLogger(f"Replication-{node_id}")
        self.hash_ring = ConsistentHashRing()
        self._update_ring()

    def _update_ring(self):
        """Actualiza el anillo de hash con los nodos activos actuales"""
        active_nodes = self.discovery.get_active_nodes()
        
        # Reiniciar anillo
        self.hash_ring = ConsistentHashRing()
        
        # Añadirnos a nosotros mismos
        self.hash_ring.add_node(self.node_id)
        
        # Añadir pares
        for node in active_nodes:
            self.hash_ring.add_node(node.node_id)
    
    def _normalize_node_id(self, node_id: str) -> str:
        """Normaliza el node_id para comparaciones consistentes"""
        # Remover prefijos comunes
        if node_id.startswith("node_"):
            return node_id[5:]  # Quitar "node_"
        return node_id
    
    def _is_responsible_for_file(self, file_name: str) -> bool:
        """
        Verifica si este nodo es responsable de almacenar un archivo.
        Un nodo es responsable si está entre los REPLICATION_FACTOR nodos
        del hash ring para ese archivo.
        """
        target_nodes = self.hash_ring.get_nodes_for_replication(
            file_name, self.REPLICATION_FACTOR
        )
        
        my_normalized = self._normalize_node_id(self.node_id)
        
        for target in target_nodes:
            target_normalized = self._normalize_node_id(target)
            if my_normalized == target_normalized:
                return True
        
        return False

    def check_redundancy(self):
        """
        Método de Auto-Curación.
        
        Se llama cuando:
        - Un nodo muere (redistribuir a nodos supervivientes)
        - Un nodo se recupera o se une nuevo (redistribuir para balancear)
        - Al inicio del nodo (sincronizar con el cluster)
        
        IMPORTANTE: 
        - Solo replica archivos de los cuales SOMOS responsables
        - Elimina archivos que ya no nos corresponden (balanceo)
        """
        self.logger.info("🔄 Verificando redundancia de archivos...")
        self._update_ring()
        
        # Verificar estado del cluster
        unique_nodes = len(set(self.hash_ring.ring.values()))
        if unique_nodes < self.MIN_NODES_FOR_FAULT_TOLERANCE:
            self.logger.warning(
                f"⚠️ ALERTA: Solo hay {unique_nodes} nodos. "
                f"Se requieren {self.MIN_NODES_FOR_FAULT_TOLERANCE} para tolerancia completa."
            )
        else:
            self.logger.info(f"✅ Cluster con {unique_nodes} nodos - tolerancia OK")
        
        shared_dir = Path('shared_files')
        if not shared_dir.exists():
            return

        files = [f for f in shared_dir.iterdir() if f.is_file()]
        files_to_keep = []
        files_to_remove = []
        
        for file_path in files:
            file_name = file_path.name
            
            if self._is_responsible_for_file(file_name):
                files_to_keep.append(file_path)
            else:
                files_to_remove.append(file_path)
        
        # Logs de cambios
        if files_to_remove:
            self.logger.info(f"🗑️ Archivos que ya no nos corresponden: {[f.name for f in files_to_remove]}")
        
        self.logger.info(f"📁 Archivos de los que somos responsables: {len(files_to_keep)}")
        
        # Replicar archivos que nos corresponden a los otros nodos responsables
        for file_path in files_to_keep:
            file_name = file_path.name
            try:
                target_nodes = self.hash_ring.get_nodes_for_replication(
                    file_name, self.REPLICATION_FACTOR
                )
                
                self.logger.debug(f"📦 {file_name} -> nodos: {target_nodes}")
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                    
                self.replicate_file(file_name, content)
                
            except Exception as e:
                self.logger.error(f"Error verificando redundancia para {file_name}: {e}")
        
        # Eliminar archivos que ya no nos corresponden (después de que otro nodo los tenga)
        # NOTA: Solo eliminamos si hay suficientes nodos para garantizar que el archivo
        # está en los nodos correctos
        if unique_nodes >= self.REPLICATION_FACTOR:
            for file_path in files_to_remove:
                try:
                    self.logger.info(f"🗑️ Eliminando {file_path.name} (ya no nos corresponde)")
                    file_path.unlink()
                    # También eliminar del índice
                    if self.repository:
                        self.repository.indexer.remove_file(str(file_path))
                except Exception as e:
                    self.logger.error(f"Error eliminando {file_path.name}: {e}")

    def replicate_file(self, file_name: str, file_content: bytes):
        """
        Replica el archivo a los nodos que dicta el Hashing Consistente.
        Solo envía a nodos que deberían tener el archivo según el hash ring.
        """
        self._update_ring()
        
        unique_nodes = len(set(self.hash_ring.ring.values()))
        target_node_ids = self.hash_ring.get_nodes_for_replication(
            file_name, self.REPLICATION_FACTOR
        )
        
        if len(target_node_ids) < self.REPLICATION_FACTOR:
            self.logger.warning(
                f"⚠️ '{file_name}': Solo {len(target_node_ids)} réplicas posibles "
                f"(se necesitan {self.REPLICATION_FACTOR})"
            )
        
        self.logger.debug(f"'{file_name}' debe estar en: {target_node_ids}")
        
        # Filtrar: No enviarnos a nosotros mismos
        targets_to_send = []
        active_nodes_map = {n.node_id: n for n in self.discovery.get_active_nodes()}
        my_normalized = self._normalize_node_id(self.node_id)
        
        for target_id in target_node_ids:
            target_normalized = self._normalize_node_id(target_id)
            
            if target_normalized == my_normalized:
                continue  # Ya lo tenemos
            
            # Buscar el nodo activo correspondiente
            for active_id, node in active_nodes_map.items():
                if self._normalize_node_id(active_id) == target_normalized:
                    targets_to_send.append(node)
                    break

        # Enviar réplicas en paralelo
        threads = []
        for target_node in targets_to_send:
            t = threading.Thread(
                target=self._send_replica, 
                args=(target_node, file_name, file_content)
            )
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join(timeout=10)

    def _send_replica(self, target_node, file_name: str, file_content: bytes):
        """Envía el archivo a un nodo específico"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((target_node.host, target_node.port))
                
                request = {
                    'action': 'replicate',
                    'file_name': file_name,
                    'file_size': len(file_content),
                    'timestamp': time.time(),
                    'from_node': self.node_id
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                sock.sendall(file_content)
                
                # Leer respuesta
                try:
                    header = sock.recv(8).decode().strip()
                    if header:
                        response = json.loads(sock.recv(int(header)).decode())
                        if response.get('status') == 'success':
                            self.logger.info(f"✅ Réplica enviada a {target_node.node_id}")
                        elif response.get('status') == 'rejected':
                            self.logger.debug(f"⏭️ {target_node.node_id} rechazó réplica (no le corresponde)")
                except:
                    pass  # Respuesta opcional
                
        except Exception as e:
            self.logger.error(f"❌ Fallo al replicar a {target_node.node_id}: {e}")

    def get_replication_status(self) -> dict:
        """
        Devuelve el estado de replicación de todos los archivos locales.
        """
        self._update_ring()
        
        unique_nodes = len(set(self.hash_ring.ring.values()))
        
        if unique_nodes >= self.REPLICATION_FACTOR:
            cluster_status = 'OK'
        elif unique_nodes >= 2:
            cluster_status = 'DEGRADED'
        else:
            cluster_status = 'CRITICAL'
        
        files_status = []
        shared_dir = Path('shared_files')
        
        if shared_dir.exists():
            for file_path in shared_dir.iterdir():
                if file_path.is_file():
                    file_name = file_path.name
                    target_nodes = self.hash_ring.get_nodes_for_replication(
                        file_name, self.REPLICATION_FACTOR
                    )
                    is_responsible = self._is_responsible_for_file(file_name)
                    files_status.append({
                        'file_name': file_name,
                        'target_nodes': target_nodes,
                        'replica_count': len(target_nodes),
                        'is_our_responsibility': is_responsible,
                        'meets_requirement': len(target_nodes) >= self.REPLICATION_FACTOR
                    })
        
        return {
            'cluster_status': cluster_status,
            'total_nodes': unique_nodes,
            'required_nodes': self.REPLICATION_FACTOR,
            'fault_tolerance': max(0, unique_nodes - 1),
            'files': files_status
        }