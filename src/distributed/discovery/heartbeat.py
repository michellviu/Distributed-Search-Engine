import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
import threading
from typing import Dict, Callable, List
from client.client import SearchClient

class HeartbeatMonitor:
    """
    Monitor de salud de nodos usando TCP health checks
    
    - Hace ping periódico a cada nodo (comando 'health' vía TCP)
    - Si un nodo no responde 3 veces consecutivas → marcado como muerto
    - Notifica cuando un nodo se recupera
    - Callback periódico para verificar salud del líder
    """
    
    CHECK_INTERVAL = 5   # segundos (reducido para detectar fallos más rápido)
    MAX_FAILURES = 2     # intentos antes de declarar muerto
    LEADER_CHECK_INTERVAL = 10  # segundos entre verificaciones del líder
    
    def __init__(self, election_callback: Callable = None):
        """
        Args:
            election_callback: Callback opcional para verificar si el líder sigue vivo
        """
        self.nodes: Dict[str, dict] = {}
        self.running = False
        self.on_node_failed: List[Callable] = []
        self.on_node_recovered: List[Callable] = []
        self.election_callback = election_callback
        self._lock = threading.Lock()
        self._last_leader_check = 0
        
    def register_node(self, node_id: str, host: str, port: int):
        """Registrar nodo para monitorear"""
        with self._lock:
            self.nodes[node_id] = {
                'host': host,
                'port': port,
                'status': 'unknown',
                'failures': 0,
                'last_check': 0
            }
            
    def unregister_node(self, node_id: str):
        """Dejar de monitorear nodo"""
        with self._lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
                
    def start(self):
        """Iniciar monitoreo"""
        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        
    def stop(self):
        self.running = False
        
    def _monitor_loop(self):
        """Loop principal de monitoreo"""
        while self.running:
            with self._lock:
                nodes_copy = dict(self.nodes)
                
            for node_id, node_info in nodes_copy.items():
                self._check_node(node_id, node_info)
            
            # Verificar salud del líder periódicamente
            current_time = time.time()
            if self.election_callback and (current_time - self._last_leader_check) > self.LEADER_CHECK_INTERVAL:
                self._last_leader_check = current_time
                try:
                    self.election_callback()
                except Exception as e:
                    pass  # Ignorar errores del callback
                
            time.sleep(self.CHECK_INTERVAL)
            
    def _check_node(self, node_id: str, node_info: dict):
        """Verificar salud de un nodo usando protocolo TCP"""
        try:
            # Usar socket directo para health check
            import socket
            import json
            
            is_healthy = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2) # Timeout corto para health check
                    sock.connect((node_info['host'], node_info['port']))
                    
                    request = {'action': 'health'}
                    request_json = json.dumps(request)
                    request_bytes = request_json.encode('utf-8')
                    
                    length_str = f"{len(request_bytes):<8}"
                    sock.sendall(length_str.encode())
                    sock.sendall(request_bytes)
                    
                    # Leer respuesta
                    length_data = sock.recv(8)
                    if length_data:
                        msg_len = int(length_data.decode().strip())
                        data = b''
                        while len(data) < msg_len:
                            chunk = sock.recv(min(4096, msg_len - len(data)))
                            if not chunk: break
                            data += chunk
                        
                        response = json.loads(data.decode())
                        is_healthy = response.get('status') == 'ok'
            except Exception:
                is_healthy = False
            
            if is_healthy:
                with self._lock:
                    old_status = node_info['status']
                    self.nodes[node_id]['status'] = 'healthy'
                    self.nodes[node_id]['failures'] = 0
                    self.nodes[node_id]['last_check'] = time.time()
                    
                    # Nodo se recuperó
                    if old_status == 'failed':
                        print(f"✓ Nodo recuperado: {node_id}")
                        for callback in self.on_node_recovered:
                            callback(node_id, node_info)
            else:
                self._handle_failure(node_id, node_info)
                
        except Exception as e:
            self._handle_failure(node_id, node_info)
            
    def _handle_failure(self, node_id: str, node_info: dict):
        """Manejar fallo de health check"""
        with self._lock:
            self.nodes[node_id]['failures'] += 1
            failures = self.nodes[node_id]['failures']
            
            if failures >= self.MAX_FAILURES:
                old_status = node_info['status']
                self.nodes[node_id]['status'] = 'failed'
                
                if old_status != 'failed':
                    print(f"✗ Nodo falló: {node_id} ({failures} intentos)")
                    for callback in self.on_node_failed:
                        callback(node_id, node_info)
                        
    def get_healthy_nodes(self) -> List[str]:
        """Obtener IDs de nodos saludables"""
        with self._lock:
            return [nid for nid, info in self.nodes.items() 
                    if info['status'] == 'healthy']