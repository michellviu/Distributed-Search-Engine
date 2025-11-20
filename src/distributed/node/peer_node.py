import sys
from pathlib import Path

from src.distributed.replication.replication_manager import ReplicationManager
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.server import SearchServer, InMemoryDocumentRepository
from indexer.indexer import DocumentIndexer
from search.search_engine import SearchEngine
from transfer.file_transfer import FileTransfer
from distributed.discovery.node_discovery import NodeDiscovery, NodeInfo
from distributed.discovery.heartbeat import HeartbeatMonitor
import threading
import logging
import asyncio

class PeerNode:
    """
    Nodo P2P del sistema distribuido
    """
    
    def __init__(self, node_id: str, host: str, port: int,
                 index_path: str = 'shared_files',
                 is_coordinator: bool = False):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.is_coordinator = is_coordinator
        self.logger = logging.getLogger(f"PeerNode-{node_id}")
        
        indexer = DocumentIndexer(index_path)
        search_engine = SearchEngine(indexer)
        file_transfer = FileTransfer()
        repository = InMemoryDocumentRepository(indexer, search_engine)
        
        self.discovery = NodeDiscovery(node_id, 'peer', host, port)
        self.replication_manager = ReplicationManager(self.discovery, node_id)

        self.server = SearchServer(
            host, 
            port, 
            repository, 
            file_transfer, 
            node_id=node_id,
            discovery=self.discovery,
            replication_manager=self.replication_manager
        )
        
        self.heartbeat = HeartbeatMonitor()
        
        self.discovery.on_node_discovered.append(self._on_node_discovered)
        self.discovery.on_node_lost.append(self._on_node_lost)
        self.heartbeat.on_node_failed.append(self._on_node_failed)
        self.heartbeat.on_node_recovered.append(self._on_node_recovered)
        
        self.active = True
        
    def _on_node_discovered(self, node_info: NodeInfo):
        """Callback: Se descubrió un nuevo nodo"""
        self.logger.info(f"Nuevo nodo: {node_info.node_id}")
        self.heartbeat.register_node(
            node_info.node_id,
            node_info.host,
            node_info.port
        )
        
        
    def _on_node_lost(self, node_info: NodeInfo):
        """Callback: Se perdió contacto con un nodo"""
        self.logger.warning(f"Nodo perdido: {node_info.node_id}")
        self.heartbeat.unregister_node(node_info.node_id)
        
    def _on_node_failed(self, node_id: str, node_info: dict):
        """Callback: Un nodo falló health check"""
        self.logger.error(f"Nodo falló: {node_id}")
        # TODO: Verificar si necesitamos re-replicar documentos
        
    def _on_node_recovered(self, node_id: str, node_info: dict):
        """Callback: Un nodo se recuperó"""
        self.logger.info(f"Nodo recuperado: {node_id}")
        threading.Thread(target=self.replication_manager.check_redundancy()).start()
        
        
    def start(self):
        """Iniciar nodo distribuido"""
        self.logger.info(f"🚀 Iniciando nodo {self.node_id} en {self.host}:{self.port}")
        
        indexer = self.server.repository.indexer
        indexer.index_directory(indexer.base_path)
        self.logger.info(f"📚 {len(indexer.index)} documentos indexados")
        
        # Iniciar componentes distribuidos
        self.discovery.start()
        self.heartbeat.start()
        
        # Iniciar servidor
        server_thread = threading.Thread(target=self.server.start)
        server_thread.daemon = True
        server_thread.start()
        
        self.logger.info("✅ Nodo activo")
        
        # 🆕 Esperar 5 segundos para descubrir nodos
        self.logger.info("🔍 Descubriendo nodos en la red...")
        threading.Event().wait(5)

        self.logger.info("🔄 Sincronizando datos con el cluster...")
        threading.Thread(target=self.replication_manager.check_redundancy).start()
        
        try:
            while self.active:
                threading.Event().wait(1)
        except KeyboardInterrupt:
            self.stop()
            
            
    def stop(self):
        """Detener nodo"""
        self.logger.info("🛑 Deteniendo nodo...")
        self.active = False
        self.discovery.stop()
        self.heartbeat.stop()
        self.server.stop()
        
    def get_cluster_status(self) -> dict:
        """Obtener estado del cluster"""
        active_nodes = self.discovery.get_active_nodes()
        healthy_nodes = self.heartbeat.get_healthy_nodes()
        indexer = self.server.repository.indexer
        
        return {
            'node_id': self.node_id,
            'is_coordinator': self.is_coordinator,
            'total_nodes': len(active_nodes) + 1,
            'healthy_nodes': len(healthy_nodes) + 1,
            'local_documents': len(indexer.index),
            'peers': [
                {
                    'node_id': n.node_id,
                    'host': n.host,
                    'port': n.port,
                    'status': 'healthy' if n.node_id in healthy_nodes else 'unknown',
                }
                for n in active_nodes
            ]
        }