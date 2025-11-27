"""
Motor de búsqueda distribuida.
Coordina búsquedas entre múltiples nodos y combina resultados.
"""
import socket
import json
import threading
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    node_id: str
    results: List[Dict]
    search_time_ms: float
    error: Optional[str] = None


class DistributedSearchEngine:
    """
    Coordina búsquedas distribuidas entre nodos del cluster.
    Transparente para el cliente: recibe una query, retorna resultados combinados.
    """
    
    SEARCH_TIMEOUT = 10  # segundos
    
    def __init__(self, discovery, node_id: str, local_repository):
        self.discovery = discovery
        self.node_id = node_id
        self.local_repository = local_repository
        self.logger = logging.getLogger(f"DistributedSearch-{node_id}")
        
    def search(self, query: str, file_type: Optional[str] = None, 
               include_local: bool = True) -> Dict[str, Any]:
        """
        Ejecuta búsqueda distribuida en todo el cluster.
        
        Args:
            query: Términos de búsqueda
            file_type: Filtro opcional por tipo de archivo
            include_local: Si incluir resultados locales
            
        Returns:
            Resultados combinados y deduplicados de todos los nodos
        """
        self.logger.info(f"🔍 Búsqueda distribuida: '{query}'")
        
        all_results: List[SearchResult] = []
        threads = []
        lock = threading.Lock()
        
        # 1. Búsqueda local
        if include_local:
            local_results = self._search_local(query, file_type)
            all_results.append(local_results)
            
        # 2. Búsqueda en nodos remotos
        active_nodes = self.discovery.get_active_nodes()
        remote_nodes = [n for n in active_nodes if n.node_id != self.node_id]
        
        self.logger.info(f"Consultando {len(remote_nodes)} nodos remotos...")
        
        def search_remote(node):
            result = self._search_remote(node, query, file_type)
            with lock:
                all_results.append(result)
                
        for node in remote_nodes:
            t = threading.Thread(target=search_remote, args=(node,))
            t.start()
            threads.append(t)
            
        # Esperar resultados con timeout
        for t in threads:
            t.join(timeout=self.SEARCH_TIMEOUT)
            
        # 3. Combinar y deduplicar resultados
        combined = self._merge_results(all_results)
        
        return {
            'status': 'success',
            'query': query,
            'total_results': len(combined),
            'nodes_queried': len(all_results),
            'results': combined
        }
        
    def _search_local(self, query: str, file_type: Optional[str]) -> SearchResult:
        """Ejecuta búsqueda en el repositorio local"""
        import time
        start = time.time()
        
        try:
            results = self.local_repository.search(query, file_type)
            elapsed = (time.time() - start) * 1000
            
            return SearchResult(
                node_id=self.node_id,
                results=results,
                search_time_ms=elapsed
            )
        except Exception as e:
            self.logger.error(f"Error en búsqueda local: {e}")
            return SearchResult(
                node_id=self.node_id,
                results=[],
                search_time_ms=0,
                error=str(e)
            )
            
    def _search_remote(self, node, query: str, file_type: Optional[str]) -> SearchResult:
        """Ejecuta búsqueda en un nodo remoto"""
        import time
        start = time.time()
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.SEARCH_TIMEOUT)
                sock.connect((node.host, node.port))
                
                request = {
                    'action': 'search_local',  # Acción especial para búsqueda sin reenvío
                    'query': query,
                    'file_type': file_type
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                header = sock.recv(8).decode().strip()
                if header:
                    response_data = sock.recv(int(header)).decode()
                    response = json.loads(response_data)
                    
                    elapsed = (time.time() - start) * 1000
                    
                    return SearchResult(
                        node_id=node.node_id,
                        results=response.get('results', []),
                        search_time_ms=elapsed
                    )
                    
        except Exception as e:
            self.logger.debug(f"Error buscando en {node.node_id}: {e}")
            
        return SearchResult(
            node_id=node.node_id,
            results=[],
            search_time_ms=0,
            error=f"Connection failed"
        )
        
    def _merge_results(self, search_results: List[SearchResult]) -> List[Dict]:
        """
        Combina resultados de múltiples nodos.
        Deduplica por file_id/path y ordena por relevancia.
        """
        seen_files = set()
        merged = []
        
        for sr in search_results:
            if sr.error:
                continue
                
            for result in sr.results:
                # Usar path o id como clave única
                file_key = result.get('path') or result.get('file_id') or result.get('name')
                
                if file_key and file_key not in seen_files:
                    seen_files.add(file_key)
                    # Añadir metadata del nodo origen
                    result['source_node'] = sr.node_id
                    merged.append(result)
                    
        # Ordenar por score/relevancia si existe
        merged.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return merged