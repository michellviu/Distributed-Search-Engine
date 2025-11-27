"""
Implementación de Quorum para consistencia en lecturas y escrituras.
Garantiza consistencia eventual con lecturas/escrituras quorum.
"""
import socket
import json
import threading
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ConsistencyLevel(Enum):
    ONE = 1          # Solo un nodo (rápido pero menos seguro)
    QUORUM = 2       # Mayoría de nodos (balanceado)
    ALL = 3          # Todos los nodos (lento pero máxima consistencia)


@dataclass
class WriteResult:
    success: bool
    acks_received: int
    acks_required: int
    failed_nodes: List[str]


@dataclass  
class ReadResult:
    success: bool
    data: Any
    responses_received: int
    responses_required: int


class QuorumManager:
    """
    Gestiona operaciones con quorum para garantizar consistencia.
    
    Para N nodos y factor de replicación R:
    - Write Quorum (W): Mínimo de nodos que deben confirmar escritura
    - Read Quorum (R): Mínimo de nodos que deben responder lectura
    - Consistencia garantizada si: W + R > N
    """
    
    OPERATION_TIMEOUT = 5  # segundos
    
    def __init__(self, discovery, node_id: str, replication_factor: int = 3):
        self.discovery = discovery
        self.node_id = node_id
        self.replication_factor = replication_factor
        self.logger = logging.getLogger(f"Quorum-{node_id}")
        
    def calculate_quorum(self, total_nodes: int) -> int:
        """Calcula el quorum necesario (mayoría simple)"""
        return (total_nodes // 2) + 1
        
    def write_with_quorum(self, file_name: str, file_content: bytes, 
                          target_nodes: List, 
                          consistency: ConsistencyLevel = ConsistencyLevel.QUORUM) -> WriteResult:
        """
        Escribe a múltiples nodos y espera confirmación de quorum.
        """
        total_targets = len(target_nodes)
        
        if consistency == ConsistencyLevel.ONE:
            required_acks = 1
        elif consistency == ConsistencyLevel.ALL:
            required_acks = total_targets
        else:  # QUORUM
            required_acks = self.calculate_quorum(total_targets)
            
        self.logger.info(f"Escribiendo '{file_name}' a {total_targets} nodos, requiere {required_acks} ACKs")
        
        # Enviar escrituras en paralelo
        results = {}
        threads = []
        lock = threading.Lock()
        
        def write_to_node(node):
            success = self._send_write(node, file_name, file_content)
            with lock:
                results[node.node_id] = success
                
        for node in target_nodes:
            t = threading.Thread(target=write_to_node, args=(node,))
            t.start()
            threads.append(t)
            
        # Esperar a todos (con timeout)
        for t in threads:
            t.join(timeout=self.OPERATION_TIMEOUT)
            
        # Contar resultados
        acks = sum(1 for success in results.values() if success)
        failed = [node_id for node_id, success in results.items() if not success]
        
        success = acks >= required_acks
        
        if success:
            self.logger.info(f"✅ Escritura exitosa: {acks}/{required_acks} ACKs recibidos")
        else:
            self.logger.warning(f"❌ Escritura fallida: {acks}/{required_acks} ACKs recibidos")
            
        return WriteResult(
            success=success,
            acks_received=acks,
            acks_required=required_acks,
            failed_nodes=failed
        )
        
    def read_with_quorum(self, file_name: str, target_nodes: List,
                         consistency: ConsistencyLevel = ConsistencyLevel.QUORUM) -> ReadResult:
        """
        Lee de múltiples nodos y retorna el valor más reciente.
        Usa timestamps o versiones para resolver conflictos.
        """
        total_targets = len(target_nodes)
        
        if consistency == ConsistencyLevel.ONE:
            required_responses = 1
        elif consistency == ConsistencyLevel.ALL:
            required_responses = total_targets
        else:  # QUORUM
            required_responses = self.calculate_quorum(total_targets)
            
        self.logger.info(f"Leyendo '{file_name}' de {total_targets} nodos, requiere {required_responses} respuestas")
        
        # Leer en paralelo
        responses = []
        threads = []
        lock = threading.Lock()
        
        def read_from_node(node):
            result = self._send_read(node, file_name)
            if result:
                with lock:
                    responses.append(result)
                    
        for node in target_nodes:
            t = threading.Thread(target=read_from_node, args=(node,))
            t.start()
            threads.append(t)
            
        # Esperar respuestas
        for t in threads:
            t.join(timeout=self.OPERATION_TIMEOUT)
            
        if len(responses) < required_responses:
            self.logger.warning(f"❌ Lectura fallida: {len(responses)}/{required_responses} respuestas")
            return ReadResult(
                success=False,
                data=None,
                responses_received=len(responses),
                responses_required=required_responses
            )
            
        # Resolver conflictos: usar la versión más reciente
        best_response = self._resolve_conflicts(responses)
        
        self.logger.info(f"✅ Lectura exitosa: {len(responses)}/{required_responses} respuestas")
        
        return ReadResult(
            success=True,
            data=best_response,
            responses_received=len(responses),
            responses_required=required_responses
        )
        
    def _send_write(self, node, file_name: str, file_content: bytes) -> bool:
        """Envía escritura a un nodo"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.OPERATION_TIMEOUT)
                sock.connect((node.host, node.port))
                
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
                
                # Esperar ACK
                header = sock.recv(8).decode().strip()
                if header:
                    response = json.loads(sock.recv(int(header)).decode())
                    return response.get('status') == 'success'
                    
        except Exception as e:
            self.logger.debug(f"Error escribiendo a {node.node_id}: {e}")
        return False
        
    def _send_read(self, node, file_name: str) -> Optional[Dict]:
        """Envía petición de lectura a un nodo"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.OPERATION_TIMEOUT)
                sock.connect((node.host, node.port))
                
                request = {
                    'action': 'get_file_info',
                    'file_name': file_name
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                header = sock.recv(8).decode().strip()
                if header:
                    response = json.loads(sock.recv(int(header)).decode())
                    if response.get('status') == 'success':
                        return response
                        
        except Exception as e:
            self.logger.debug(f"Error leyendo de {node.node_id}: {e}")
        return None
        
    def _resolve_conflicts(self, responses: List[Dict]) -> Dict:
        """
        Resuelve conflictos entre múltiples respuestas.
        Usa timestamp para determinar la versión más reciente.
        """
        if not responses:
            return None
            
        # Ordenar por timestamp descendente y retornar el más reciente
        sorted_responses = sorted(
            responses, 
            key=lambda x: x.get('timestamp', 0), 
            reverse=True
        )
        
        return sorted_responses[0]