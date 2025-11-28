"""
Main server implementation for centralized search engine
"""

import socket
import threading
import logging
import json
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from pathlib import Path


# ==================== Repository Pattern ====================
# Abstracción para el almacenamiento de datos (fácil migración a MongoDB)

class DocumentRepository(ABC):
    """
    Abstract repository for document storage
    Allows easy migration to different storage backends (MongoDB, etc.)
    """
    
    @abstractmethod
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents matching query"""
        pass
    
    @abstractmethod
    def index_file(self, file_path: str) -> bool:
        """Index a single file"""
        pass
    
    @abstractmethod
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific file"""
        pass
    
    @abstractmethod
    def get_all_indexed_files(self) -> List[Dict[str, Any]]:
        """Get all indexed files"""
        pass


class InMemoryDocumentRepository(DocumentRepository):
    """
    In-memory implementation using the current indexer
    This can be replaced with MongoDocumentRepository later
    """
    
    def __init__(self, indexer, search_engine):
        self.indexer = indexer
        self.search_engine = search_engine
        self.logger = logging.getLogger(__name__)
    
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents using the search engine"""
        try:
            return self.search_engine.search(query, file_type)
        except Exception as e:
            self.logger.error(f"Error searching documents: {e}")
            return []
    
    def index_file(self, file_path: str) -> bool:
        """Index a file using the indexer"""
        try:
            self.indexer.index_file(file_path)
            return True
        except Exception as e:
            self.logger.error(f"Error indexing file {file_path}: {e}")
            return False
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file information from index"""
        # Search through the index for the file
        for file_name, file_list in self.indexer.index.items():
            for file_info in file_list:
                if file_info.get('path') == file_id or file_info.get('name') == file_id:
                    return file_info
        return None
    
    def get_all_indexed_files(self) -> List[Dict[str, Any]]:
        """Get all indexed files"""
        all_files = []
        for file_name, file_list in self.indexer.index.items():
            all_files.extend(file_list)
        return all_files


# ==================== Command Pattern ====================
# Encapsula cada operación del servidor como un comando

class Command(ABC):
    """Base class for all server commands"""
    
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """Execute the command and return response"""
        pass


class SearchCommand(Command):
    """Command for searching documents"""
    
    def __init__(self, repository: DocumentRepository, query: str, file_type: Optional[str] = None):
        self.repository = repository
        self.query = query
        self.file_type = file_type
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute search and return results"""
        try:
            self.logger.info(f"Executing search: query='{self.query}', type={self.file_type}")
            results = self.repository.search(self.query, self.file_type)
            return {
                'status': 'success',
                'action': 'search',
                'query': self.query,
                'results': results,
                'count': len(results)
            }
        except Exception as e:
            self.logger.error(f"Search command failed: {e}")
            return {
                'status': 'error',
                'action': 'search',
                'message': str(e)
            }


class IndexCommand(Command):
    """
    Command for indexing a new document.
    
    Cuando se sube un archivo:
    1. Lo guarda temporalmente
    2. Usa Quorum para replicar con garantía de consistencia
    3. Solo lo mantiene localmente si este nodo es responsable
    """
    
    def __init__(self, repository: DocumentRepository, file_path: str = None, 
                 file_name: str = None, file_content: bytes = None,
                 replication_manager=None, node_id: str = None,
                 quorum_manager=None, consistency: str = 'QUORUM'):
        self.repository = repository
        self.file_path = file_path
        self.file_name = file_name
        self.file_content = file_content
        self.replication_manager = replication_manager
        self.node_id = node_id
        self.quorum_manager = quorum_manager
        self.consistency = consistency
        self.logger = logging.getLogger(__name__)
    
    def _is_responsible_for_file(self, file_name: str) -> bool:
        """Verifica si este nodo debe almacenar el archivo según hash ring."""
        if not self.replication_manager or not self.node_id:
            return True  # Sin replication manager, asumir que sí
        
        self.replication_manager._update_ring()
        target_nodes = self.replication_manager.hash_ring.get_nodes_for_replication(
            file_name, self.replication_manager.REPLICATION_FACTOR
        )
        
        # Normalizar node_id para comparación
        my_normalized = self.replication_manager._normalize_node_id(self.node_id)
        
        for target in target_nodes:
            target_normalized = self.replication_manager._normalize_node_id(target)
            if my_normalized == target_normalized:
                return True
        
        return False
    
    def _get_consistency_level(self):
        """Obtiene el nivel de consistencia del QuorumManager"""
        if self.quorum_manager:
            # Import relativo para compatibilidad con Docker
            try:
                from src.distributed.contistency.quorum import ConsistencyLevel
            except ImportError:
                from distributed.contistency.quorum import ConsistencyLevel
            levels = {
                'ONE': ConsistencyLevel.ONE,
                'QUORUM': ConsistencyLevel.QUORUM,
                'ALL': ConsistencyLevel.ALL
            }
            return levels.get(self.consistency.upper(), ConsistencyLevel.QUORUM)
        return None
    
    def execute(self) -> Dict[str, Any]:
        """Execute indexing and return result"""
        try:
            # New behavior: If file content is provided, save it first
            if self.file_content is not None and self.file_name:
                self.logger.info(f"📤 Recibiendo archivo: '{self.file_name}'")
                
                shared_files_dir = Path('shared_files')
                shared_files_dir.mkdir(exist_ok=True)
                target_path = shared_files_dir / self.file_name
                
                # Verificar si este nodo es responsable de este archivo
                is_responsible = self._is_responsible_for_file(self.file_name)
                
                if is_responsible:
                    # Guardar y indexar localmente
                    with open(target_path, 'wb') as f:
                        f.write(self.file_content)
                    self.repository.index_file(str(target_path))
                    self.logger.info(f"✅ Archivo guardado (nos corresponde): {self.file_name}")
                else:
                    self.logger.info(f"⏭️ Archivo no nos corresponde, solo replicando: {self.file_name}")
                
                # Usar Quorum si está disponible, sino replicación directa
                if self.quorum_manager and self.replication_manager:
                    consistency_level = self._get_consistency_level()
                    self.logger.info(f"🔐 Usando QUORUM para replicación (consistencia: {self.consistency})")
                    
                    # Obtener nodos objetivo del hash ring
                    self.replication_manager._update_ring()
                    target_nodes = self.replication_manager.hash_ring.get_nodes_for_replication(
                        self.file_name, self.replication_manager.REPLICATION_FACTOR
                    )
                    
                    # Mapear node_ids a NodeInfo
                    nodes_to_replicate = []
                    for node in self.replication_manager.discovery.get_active_nodes():
                        node_normalized = self.replication_manager._normalize_node_id(node.node_id)
                        for target in target_nodes:
                            target_normalized = self.replication_manager._normalize_node_id(target)
                            if node_normalized == target_normalized:
                                nodes_to_replicate.append(node)
                                break
                    
                    def quorum_replicate():
                        result = self.quorum_manager.write_with_quorum(
                            self.file_name,
                            self.file_content,
                            consistency_level,
                            nodes_to_replicate
                        )
                        if result.success:
                            self.logger.info(f"✅ Quorum write exitoso: {result.nodes_succeeded}/{result.total_nodes} nodos")
                        else:
                            self.logger.warning(f"⚠️ Quorum write parcial: {result.nodes_succeeded}/{result.total_nodes} nodos")
                    
                    threading.Thread(target=quorum_replicate).start()
                    
                elif self.replication_manager:
                    self.logger.info("🔄 Iniciando replicación distribuida (sin Quorum)...")
                    threading.Thread(
                        target=self.replication_manager.replicate_file,
                        args=(self.file_name, self.file_content)
                    ).start()

                return {
                    'status': 'success',
                    'action': 'index',
                    'file_path': str(target_path) if is_responsible else None,
                    'stored_locally': is_responsible,
                    'quorum_enabled': self.quorum_manager is not None,
                    'consistency': self.consistency,
                    'message': 'File uploaded and being replicated with quorum consistency' if self.quorum_manager else 'File uploaded and being replicated'
                }
            
            # Old behavior: file_path provided (for backward compatibility)
            elif self.file_path:
                self.logger.info(f"Executing index: file='{self.file_path}'")
                
                # Verify file exists
                if not Path(self.file_path).exists():
                    return {
                        'status': 'error',
                        'action': 'index',
                        'message': f"File not found: {self.file_path}"
                    }
                
                success = self.repository.index_file(self.file_path)
                
                if success:
                    return {
                        'status': 'success',
                        'action': 'index',
                        'file_path': self.file_path,
                        'message': 'File indexed successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'index',
                        'message': 'Failed to index file'
                    }
            else:
                return {
                    'status': 'error',
                    'action': 'index',
                    'message': 'No file path or content provided'
                }
                
        except Exception as e:
            self.logger.error(f"Index command failed: {e}")
            return {
                'status': 'error',
                'action': 'index',
                'message': str(e)
            }


class DownloadCommand(Command):
    """Command for downloading a document"""
    
    def __init__(self, repository: DocumentRepository, file_transfer, file_id: str):
        self.repository = repository
        self.file_transfer = file_transfer
        self.file_id = file_id
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute download preparation and return file info"""
        try:
            self.logger.info(f"Executing download: file_id='{self.file_id}'")
            
            # Get file information from repository
            file_info = self.repository.get_file_info(self.file_id)
            
            if not file_info:
                return {
                    'status': 'error',
                    'action': 'download',
                    'message': f"File not found: {self.file_id}"
                }
            
            file_path = file_info.get('path')
            if not file_path or not Path(file_path).exists():
                return {
                    'status': 'error',
                    'action': 'download',
                    'message': 'File path not available or file does not exist'
                }
            
            return {
                'status': 'success',
                'action': 'download',
                'file_info': file_info,
                'ready': True
            }
        except Exception as e:
            self.logger.error(f"Download command failed: {e}")
            return {
                'status': 'error',
                'action': 'download',
                'message': str(e)
            }


class ListCommand(Command):
    """Command for listing all indexed documents"""
    
    def __init__(self, repository: DocumentRepository):
        self.repository = repository
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute list and return all indexed files"""
        try:
            self.logger.info("Executing list all indexed files")
            files = self.repository.get_all_indexed_files()
            return {
                'status': 'success',
                'action': 'list',
                'files': files,
                'count': len(files)
            }
        except Exception as e:
            self.logger.error(f"List command failed: {e}")
            return {
                'status': 'error',
                'action': 'list',
                'message': str(e)
            }


class HealthCommand(Command):
    """Command for checking server health"""
    
    def __init__(self):
        pass
    
    def execute(self) -> Dict[str, Any]:
        """Return health status"""
        return {
            'status': 'ok',
            'action': 'health',
            'message': 'Server is running'
        }
    

class ReplicateCommand(Command):
    """
    Comando para recibir una réplica desde otro nodo.
    
    Verifica que este nodo sea responsable del archivo según el hash ring
    antes de almacenarlo. Esto garantiza que cada archivo solo esté en
    los nodos que le corresponden (REPLICATION_FACTOR nodos).
    
    Si is_quorum_write=True, se salta la verificación de hash ring porque
    el QuorumManager ya determinó que este nodo debe recibir el archivo.
    """
    
    def __init__(self, repository: DocumentRepository, file_name: str, 
                 file_content: bytes, replication_manager=None, node_id: str = None,
                 is_quorum_write: bool = False):
        self.repository = repository
        self.file_name = file_name
        self.file_content = file_content
        self.replication_manager = replication_manager
        self.node_id = node_id
        self.is_quorum_write = is_quorum_write
        self.logger = logging.getLogger(__name__)
        
    def execute(self) -> Dict[str, Any]:
        try:
            # Si es una escritura Quorum, confiar en que el QuorumManager ya validó
            if self.is_quorum_write:
                self.logger.info(f"📥 Recibiendo réplica QUORUM: {self.file_name}")
            elif self.replication_manager and self.node_id:
                # Verificar si este nodo debe almacenar el archivo según el hash ring
                if not self._should_store_file():
                    self.logger.info(f"⏭️ Rechazando réplica {self.file_name} - no nos corresponde")
                    return {
                        'status': 'rejected',
                        'action': 'replicate',
                        'message': 'Node not responsible for this file',
                        'reason': 'hash_ring_mismatch'
                    }
            
            self.logger.info(f"📥 Recibiendo réplica: {self.file_name}")
            
            # Guardar archivo
            shared_files_dir = Path('shared_files')
            shared_files_dir.mkdir(exist_ok=True)
            target_path = shared_files_dir / self.file_name
            
            with open(target_path, 'wb') as f:
                f.write(self.file_content)
                
            # Indexar localmente
            success = self.repository.index_file(str(target_path))
            
            return {
                'status': 'success' if success else 'error',
                'action': 'replicate',
                'quorum_write': self.is_quorum_write,
                'message': 'Replica stored via Quorum' if self.is_quorum_write else 'Replica stored',
                'timestamp': __import__('time').time()
            }
        except Exception as e:
            self.logger.error(f"Error guardando réplica: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _should_store_file(self) -> bool:
        """
        Verifica si este nodo debe almacenar el archivo según el hash ring.
        """
        self.replication_manager._update_ring()
        
        target_nodes = self.replication_manager.hash_ring.get_nodes_for_replication(
            self.file_name, 
            self.replication_manager.REPLICATION_FACTOR
        )
        
        # Verificar si nuestro node_id está en la lista de nodos responsables
        our_ids = [self.node_id, f"node_{self.node_id}"]
        
        for target in target_nodes:
            if target in our_ids or self.node_id in target:
                return True
        
        return False


# ==================== Distributed Commands ====================

class ElectionCommand(Command):
    """Comando para manejar mensajes de elección de líder"""
    
    def __init__(self, election, from_node: str):
        self.election = election
        self.from_node = from_node
        
    def execute(self) -> Dict[str, Any]:
        return self.election.handle_election_message(self.from_node)


class CoordinatorCommand(Command):
    """Comando para manejar anuncio de nuevo coordinador"""
    
    def __init__(self, election, coordinator_id: str, host: str, port: int):
        self.election = election
        self.coordinator_id = coordinator_id
        self.host = host
        self.port = port
        
    def execute(self) -> Dict[str, Any]:
        self.election.handle_coordinator_message(
            self.coordinator_id, 
            self.host, 
            self.port
        )
        return {'status': 'ok', 'action': 'coordinator'}


class GetFileInfoCommand(Command):
    """Comando para obtener info de un archivo específico"""
    
    def __init__(self, repository: DocumentRepository, file_name: str):
        self.repository = repository
        self.file_name = file_name
        self.logger = logging.getLogger(__name__)
        
    def execute(self) -> Dict[str, Any]:
        try:
            file_info = self.repository.get_file_info(self.file_name)
            if file_info:
                return {
                    'status': 'success',
                    'action': 'get_file_info',
                    'file_info': file_info,
                    'timestamp': __import__('time').time()
                }
            return {
                'status': 'error',
                'action': 'get_file_info',
                'message': 'File not found'
            }
        except Exception as e:
            self.logger.error(f"Error getting file info: {e}")
            return {'status': 'error', 'message': str(e)}


class ClusterStatusCommand(Command):
    """Comando para obtener estado del cluster"""
    
    def __init__(self, election, repository: DocumentRepository, node_id: str = None, discovery=None):
        self.election = election
        self.repository = repository
        self.node_id = node_id
        self.discovery = discovery
        
    def execute(self) -> Dict[str, Any]:
        files = self.repository.get_all_indexed_files()
        status = {
            'status': 'success',
            'action': 'cluster_status',
            'node_id': self.node_id,
            'indexed_files': len(files),
            'files': [{'name': f.get('name'), 'size': f.get('size')} for f in files]
        }
        if self.election:
            status['is_leader'] = self.election.is_leader()
            if self.election.current_leader:
                status['leader'] = self.election.current_leader.node_id
        # Añadir info de peers conocidos
        if self.discovery:
            peers = self.discovery.get_active_nodes()
            status['peers_count'] = len(peers)
            status['peers'] = [{'node_id': p.node_id, 'host': p.host, 'port': p.port} for p in peers]
        return status


class GetPeersCommand(Command):
    """Comando para obtener lista de peers conocidos (para discovery)"""
    
    def __init__(self, discovery, node_id: str, from_node: str = None,
                 from_host: str = None, from_port: int = None, from_type: str = 'peer'):
        self.discovery = discovery
        self.node_id = node_id
        self.from_node = from_node
        self.from_host = from_host
        self.from_port = from_port
        self.from_type = from_type
        self.logger = logging.getLogger(__name__)
        
    def execute(self) -> Dict[str, Any]:
        # REGISTRO BIDIRECCIONAL: Registrar al nodo que nos contactó
        if self.discovery and self.from_node and self.from_host and self.from_port:
            self.logger.info(f"📥 Registrando nodo via IP Cache: {self.from_node} ({self.from_host}:{self.from_port})")
            # Usar el método específico para registro desde conexión
            if hasattr(self.discovery, 'register_node_from_connection'):
                self.discovery.register_node_from_connection(
                    node_id=self.from_node,
                    host=self.from_host,
                    port=self.from_port,
                    node_type=self.from_type
                )
        
        peers = []
        if self.discovery:
            for node in self.discovery.get_active_nodes():
                peers.append({
                    'node_id': node.node_id,
                    'host': node.host,
                    'port': node.port,
                    'node_type': node.node_type
                })
        return {
            'status': 'success',
            'action': 'get_peers',
            'node_id': self.node_id,
            'peers': peers
        }


class DistributedSearchCommand(Command):
    """Comando para búsqueda distribuida en todo el cluster"""
    
    def __init__(self, distributed_search, query: str, file_type: str = None):
        self.distributed_search = distributed_search
        self.query = query
        self.file_type = file_type
        self.logger = logging.getLogger(__name__)
        
    def execute(self) -> Dict[str, Any]:
        if not self.distributed_search:
            return {
                'status': 'error',
                'action': 'distributed_search',
                'message': 'Distributed search not available'
            }
        try:
            return self.distributed_search.search(self.query, self.file_type)
        except Exception as e:
            self.logger.error(f"Distributed search failed: {e}")
            return {
                'status': 'error',
                'action': 'distributed_search',
                'message': str(e)
            }


# ==================== Command Factory ====================

class CommandFactory:
    """Factory for creating commands based on requests"""
    
    def __init__(self, repository: DocumentRepository, file_transfer=None, 
                 replication_manager=None, distributed_search=None, election=None,
                 node_id: str = None, discovery=None, quorum_manager=None):
        self.repository = repository
        self.file_transfer = file_transfer
        self.replication_manager = replication_manager
        self.distributed_search = distributed_search
        self.election = election
        self.node_id = node_id
        self.discovery = discovery
        self.quorum_manager = quorum_manager
        self.logger = logging.getLogger(__name__)
    
    def create_command(self, request: Dict[str, Any], file_content: bytes = None) -> Optional[Command]:
        """
        Create a command based on the request
        
        Args:
            request: Dictionary with 'action' and other parameters
            file_content: Optional file content for index operations
            
        Returns:
            Command instance or None if invalid
        """
        action = request.get('action')
        
        if action == 'search':
            query = request.get('query', '')
            file_type = request.get('file_type')
            # Si hay búsqueda distribuida disponible, usarla por defecto
            if self.distributed_search:
                return DistributedSearchCommand(self.distributed_search, query, file_type)
            return SearchCommand(self.repository, query, file_type)
        
        elif action == 'index':
            # New behavior: check if file_name and file_size are provided (upload mode)
            file_name = request.get('file_name')
            file_path = request.get('file_path', '')
            consistency = request.get('consistency', 'QUORUM')  # Nivel de consistencia
            
            if file_name and file_content:
                # Upload mode: file content provided
                return IndexCommand(self.repository, file_path=None, 
                                  file_name=file_name, file_content=file_content,
                                  replication_manager=self.replication_manager,
                                  node_id=self.node_id,
                                  quorum_manager=self.quorum_manager,
                                  consistency=consistency)
            else:
                # Old mode: file path provided
                return IndexCommand(self.repository, file_path=file_path,
                                  replication_manager=self.replication_manager,
                                  node_id=self.node_id,
                                  quorum_manager=self.quorum_manager,
                                  consistency=consistency)
        
        elif action == 'download':
            file_id = request.get('file_id', '')
            return DownloadCommand(self.repository, self.file_transfer, file_id)
        
        elif action == 'list':
            return ListCommand(self.repository)
            
        elif action == 'health':
            return HealthCommand()
        
        elif action == 'replicate':
            file_name = request.get('file_name')
            is_quorum_write = request.get('is_quorum_write', False)  # Si viene de Quorum
            if file_name and file_content:
                return ReplicateCommand(
                    self.repository, 
                    file_name, 
                    file_content,
                    replication_manager=self.replication_manager,
                    node_id=self.node_id,
                    is_quorum_write=is_quorum_write
                )
            return None
        
        # === Comandos Distribuidos ===
        elif action == 'search_local':
            # Búsqueda solo local (sin reenvío a otros nodos)
            query = request.get('query', '')
            file_type = request.get('file_type')
            return SearchCommand(self.repository, query, file_type)
        
        elif action == 'election':
            # Mensaje de elección de líder
            from_node = request.get('from_node')
            if self.election:
                return ElectionCommand(self.election, from_node)
            return None
        
        elif action == 'coordinator':
            # Anuncio de nuevo coordinador
            if self.election:
                return CoordinatorCommand(
                    self.election,
                    request.get('coordinator_id'),
                    request.get('coordinator_host'),
                    request.get('coordinator_port')
                )
            return None
        
        elif action == 'get_file_info':
            # Obtener info de archivo específico
            file_name = request.get('file_name')
            return GetFileInfoCommand(self.repository, file_name)
        
        elif action == 'cluster_status':
            # Estado del cluster (para debugging)
            return ClusterStatusCommand(self.election, self.repository, self.node_id, self.discovery)
        
        elif action == 'get_peers':
            # Obtener lista de peers conocidos (para discovery)
            # Incluye registro bidireccional via IP Cache
            return GetPeersCommand(
                self.discovery, 
                self.node_id,
                from_node=request.get('from_node'),
                from_host=request.get('from_host'),
                from_port=request.get('from_port'),
                from_type=request.get('from_type', 'peer')
            )
        
        elif action == 'distributed_search':
            # Búsqueda distribuida en todo el cluster
            query = request.get('query', '')
            file_type = request.get('file_type')
            return DistributedSearchCommand(self.distributed_search, query, file_type)
        
        else:
            self.logger.warning(f"Unknown action: {action}")
            return None


# ==================== Server Implementation ====================

class SearchServer:
    """
    Centralized server that handles search requests and manages document index
    Uses Command Pattern for extensibility and Repository Pattern for data abstraction
    """
    
    def __init__(self, host: str = 'localhost', port: int = 5000, 
                 repository: DocumentRepository = None, file_transfer=None,
                 node_id: str = None, discovery=None, replication_manager=None,
                 quorum_manager=None):
        """
        Initialize the search server
        
        Args:
            host: Server host address
            port: Server port number
            repository: Document repository implementation
            file_transfer: File transfer handler
            node_id: ID of the node (for distributed mode)
            discovery: Node discovery service (for distributed mode)
            replication_manager: Manager for file replication
            quorum_manager: Manager for quorum consistency
        """
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.repository = repository
        self.file_transfer = file_transfer
        self.node_id = node_id
        self.discovery = discovery
        self.replication_manager = replication_manager
        self.quorum_manager = quorum_manager
        self.election = None  # Set later if distributed
        self.distributed_search = None  # Set later if distributed
        self.command_factory = None  # Initialize after all components are set
        self.logger = logging.getLogger(__name__)
        self._init_command_factory()
    
    def _init_command_factory(self):
        """Initialize command factory with all components"""
        self.command_factory = CommandFactory(
            self.repository, 
            self.file_transfer, 
            self.replication_manager,
            self.distributed_search,
            self.election,
            self.node_id,
            self.discovery,
            self.quorum_manager
        )
    
    def set_distributed_components(self, election=None, distributed_search=None):
        """Set distributed components after initialization"""
        self.election = election
        self.distributed_search = distributed_search
        self._init_command_factory()
        
    def start(self):
        """Start the server and begin listening for connections"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True
        self.logger.info(f"Server started on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = self.socket.accept()
                self.logger.info(f"Connection from {address}")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error accepting connection: {e}")
                
    def handle_client(self, client_socket: socket.socket, address: tuple):
        """
        Handle individual client connections
        
        Args:
            client_socket: Client socket connection
            address: Client address tuple
        """
        try:
            # Receive request from client
            request_data = self._receive_data(client_socket)
            
            if not request_data:
                self.logger.warning(f"No data received from {address}")
                return
            
            # Parse request
            try:
                request = json.loads(request_data)
                self.logger.info(f"Request from {address}: {request.get('action', 'unknown')}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON from {address}: {e}")
                error_response = {
                    'status': 'error',
                    'message': 'Invalid JSON format'
                }
                self._send_response(client_socket, error_response)
                return
            
            # Handle index action with file upload
            file_content = None
            if request.get('action') in ['index', 'replicate'] and 'file_size' in request:
                # Receive file content
                file_size = request.get('file_size', 0)
                self.logger.info(f"Receiving file content: {file_size} bytes")
                file_content = self._receive_file_content(client_socket, file_size)
            
            # Create and execute command
            command = self.command_factory.create_command(request, file_content)
            
            if command is None:
                error_response = {
                    'status': 'error',
                    'message': f"Unknown action: {request.get('action', 'none')}"
                }
                self._send_response(client_socket, error_response)
                return
            
            # Execute command
            response = command.execute()
            
            # Handle download special case (needs to send file)
            if request.get('action') == 'download' and response.get('status') == 'success':
                self._send_response(client_socket, response)
                
                # Send the actual file
                file_path = response['file_info']['path']
                self.logger.info(f"Sending file: {file_path}")
                
                if self.file_transfer:
                    success = self.file_transfer.send_file(file_path, client_socket)
                    if success:
                        self.logger.info(f"File sent successfully: {file_path}")
                    else:
                        self.logger.error(f"Failed to send file: {file_path}")
            else:
                # Send response for other actions
                self._send_response(client_socket, response)
            
        except Exception as e:
            self.logger.error(f"Error handling client {address}: {e}", exc_info=True)
            try:
                error_response = {
                    'status': 'error',
                    'message': f"Server error: {str(e)}"
                }
                self._send_response(client_socket, error_response)
            except:
                pass
        finally:
            client_socket.close()
            self.logger.info(f"Connection closed: {address}")
    
    def _receive_data(self, client_socket: socket.socket, buffer_size: int = 4096) -> str:
        """
        Receive data from client socket
        
        Args:
            client_socket: Client socket
            buffer_size: Buffer size for receiving
            
        Returns:
            Decoded string data
        """
        try:
            # First receive the length of the message
            length_data = client_socket.recv(8)
            if not length_data:
                return ''
            
            message_length = int(length_data.decode().strip())
            
            # Receive the actual message
            data = b''
            while len(data) < message_length:
                chunk = client_socket.recv(min(buffer_size, message_length - len(data)))
                if not chunk:
                    break
                data += chunk
            
            return data.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error receiving data: {e}")
            return ''
    
    def _receive_file_content(self, client_socket: socket.socket, file_size: int, 
                             buffer_size: int = 4096) -> bytes:
        """
        Receive file content from client socket
        
        Args:
            client_socket: Client socket
            file_size: Expected file size in bytes
            buffer_size: Buffer size for receiving
            
        Returns:
            File content as bytes
        """
        try:
            self.logger.info(f"Receiving file content: {file_size} bytes")
            data = b''
            while len(data) < file_size:
                chunk = client_socket.recv(min(buffer_size, file_size - len(data)))
                if not chunk:
                    break
                data += chunk
            
            self.logger.info(f"Received {len(data)} bytes")
            return data
        except Exception as e:
            self.logger.error(f"Error receiving file content: {e}")
            return b''
    
    def _send_response(self, client_socket: socket.socket, response: Dict[str, Any]):
        """
        Send response to client
        
        Args:
            client_socket: Client socket
            response: Response dictionary to send
        """
        try:
            response_json = json.dumps(response)
            response_bytes = response_json.encode('utf-8')
            
            # Send length first
            length_str = f"{len(response_bytes):<8}"
            client_socket.sendall(length_str.encode())
            
            # Send actual data
            client_socket.sendall(response_bytes)
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")
            
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.socket:
            self.socket.close()
        self.logger.info("Server stopped")
