"""
Nodo P2P del sistema distribuido - Versión completa
"""
import sys
import os
import logging
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.server import SearchServer, InMemoryDocumentRepository
from indexer.indexer import DocumentIndexer
from search.search_engine import SearchEngine
from transfer.file_transfer import FileTransfer
from distributed.discovery.ip_cache_discovery import IPCacheDiscovery, NodeInfo
from distributed.discovery.heartbeat import HeartbeatMonitor
from distributed.replication.replication_manager import ReplicationManager
from distributed.coordination.coordinator import LeaderElection, LoadBalancer
from distributed.contistency.quorum import QuorumManager
from distributed.search.distributed_search_engine import DistributedSearchEngine


class PeerNode:
    """
    Nodo P2P del sistema distribuido.
    
    Cada nodo puede ser:
    - Coordinador (si gana la elección): Balancea carga y coordina
    - Seguidor: Procesa peticiones locales y responde al coordinador
    """
    
    def __init__(self, node_id: str, host: str, port: int,
                 index_path: str = 'shared_files',
                 seed_nodes: list = None,
                 announce_host: str = None):
        self.node_id = node_id
        self.host = host  # Para bind (normalmente 0.0.0.0)
        self.announce_host = announce_host or host  # Para anunciarse
        self.port = port
        self.logger = logging.getLogger(f"PeerNode-{node_id}")
        
        # Crear directorio de archivos si no existe
        Path(index_path).mkdir(parents=True, exist_ok=True)
        
        # Componentes de indexación y búsqueda
        self.index_path = index_path
        self.indexer = DocumentIndexer(index_path)
        search_engine = SearchEngine(self.indexer)
        file_transfer = FileTransfer()
        self.repository = InMemoryDocumentRepository(self.indexer, search_engine)
        
        # === Componentes Distribuidos ===
        
        # 1. Descubrimiento de nodos (usando IP Cache + seed nodes)
        # Usamos announce_host para que otros nodos sepan dónde conectarse
        self.discovery = IPCacheDiscovery(
            node_id=node_id, 
            node_type='peer', 
            host=self.announce_host,  # IP para anunciarse
            port=port,
            seed_nodes=seed_nodes or []
        )
        
        # 2. Monitoreo de salud
        self.heartbeat = HeartbeatMonitor(election_callback=self._check_leader_health)
        
        # 3. Replicación
        self.replication_manager = ReplicationManager(
            self.discovery, 
            node_id, 
            self.repository
        )
        
        # Indexar solo los archivos que nos corresponden según el hash ring
        # (después de inicializar replication_manager para tener acceso al hash ring)
        self._index_initial_files()
        
        # 4. Elección de líder y balanceo de carga
        self.election = LeaderElection(node_id, self.discovery)
        self.load_balancer = LoadBalancer(self.discovery, self.heartbeat)
        
        # 5. Consistencia (Quorum)
        self.quorum_manager = QuorumManager(self.discovery, node_id)
        
        # 6. Búsqueda distribuida
        self.distributed_search = DistributedSearchEngine(
            self.discovery,
            node_id,
            self.repository
        )
        
        # Servidor TCP (recibe conexiones de clientes y otros nodos)
        # Usamos self.host (0.0.0.0) para bind y aceptar conexiones de cualquier interfaz
        self.server = SearchServer(
            self.host,  # 0.0.0.0 para aceptar conexiones de cualquier IP
            port, 
            self.repository, 
            file_transfer, 
            node_id=node_id,
            discovery=self.discovery,
            replication_manager=self.replication_manager,
            quorum_manager=self.quorum_manager
        )
        
        # Configurar componentes distribuidos en el servidor
        self.server.set_distributed_components(
            election=self.election,
            distributed_search=self.distributed_search
        )
        
        # Conectar callbacks
        self._setup_callbacks()
        
        self.active = True
        
    def _index_initial_files(self):
        """
        Indexar solo los archivos que le corresponden a este nodo según el hash ring.
        Los archivos que no nos corresponden se ignoran (otro nodo los tiene).
        """
        from pathlib import Path
        shared_dir = Path(self.index_path)
        if shared_dir.exists():
            indexed_count = 0
            skipped_count = 0
            
            for file_path in shared_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_name = file_path.name
                        
                        # Verificar si este archivo nos corresponde según el hash ring
                        if self._should_store_file(file_name):
                            self.indexer.index_file(str(file_path))
                            indexed_count += 1
                            self.logger.info(f"📄 Indexado (nos corresponde): {file_name}")
                        else:
                            skipped_count += 1
                            self.logger.debug(f"⏭️ Saltado (no nos corresponde): {file_name}")
                    except Exception as e:
                        self.logger.error(f"Error indexando {file_path}: {e}")
            
            self.logger.info(f"📁 Indexados {indexed_count} archivos, saltados {skipped_count}")
        else:
            self.logger.warning(f"⚠️ Directorio {self.index_path} no existe")
    
    def _should_store_file(self, file_name: str) -> bool:
        """
        Determina si este nodo debe almacenar el archivo según el hash ring.
        Un nodo debe almacenar un archivo si está entre los REPLICATION_FACTOR nodos
        responsables de ese archivo.
        """
        # Actualizar el anillo con los nodos conocidos
        self.replication_manager._update_ring()
        
        # Obtener los nodos responsables de este archivo
        target_nodes = self.replication_manager.hash_ring.get_nodes_for_replication(
            file_name, 
            self.replication_manager.REPLICATION_FACTOR
        )
        
        # Verificar si nuestro node_id está en la lista
        # El node_id en el hash ring puede tener prefijo "node_"
        our_ids = [self.node_id, f"node_{self.node_id}"]
        
        for target in target_nodes:
            if target in our_ids or self.node_id in target:
                return True
        
        return False
    
    def _check_leader_health(self):
        """
        Callback llamado periódicamente por HeartbeatMonitor.
        Verifica si el líder actual sigue vivo.
        """
        if not self.election.current_leader:
            return
            
        leader_id = self.election.current_leader.node_id
        
        # Si somos el líder, no hay nada que verificar
        if leader_id == self.node_id:
            return
            
        # Verificar si el líder está en nodos saludables
        healthy_nodes = self.heartbeat.get_healthy_nodes()
        if leader_id not in healthy_nodes:
            self.logger.warning(f"⚠️ El coordinador {leader_id} no responde. Iniciando elección...")
            threading.Thread(target=self.election.start_election, daemon=True).start()
        
    def _setup_callbacks(self):
        """Configura todos los callbacks entre componentes"""
        # Discovery callbacks
        self.discovery.on_node_discovered.append(self._on_node_discovered)
        self.discovery.on_node_lost.append(self._on_node_lost)
        
        # Heartbeat callbacks
        self.heartbeat.on_node_failed.append(self._on_node_failed)
        self.heartbeat.on_node_recovered.append(self._on_node_recovered)
        
        # Election callbacks
        self.election.on_became_leader.append(self._on_became_leader)
        self.election.on_leader_changed.append(self._on_leader_changed)
        
    def _on_node_discovered(self, node_info: NodeInfo):
        """Callback: Se descubrió un nuevo nodo"""
        self.logger.info(f"🆕 Nuevo nodo: {node_info.node_id} ({node_info.host}:{node_info.port})")
        self.heartbeat.register_node(
            node_info.node_id,
            node_info.host,
            node_info.port
        )
        
        # Verificar si ahora podemos cumplir con el factor de replicación mínimo (3 nodos)
        # y redistribuir datos si es necesario
        total_nodes = len(self.discovery.get_active_nodes()) + 1  # +1 por nosotros
        if total_nodes >= self.replication_manager.REPLICATION_FACTOR:
            self.logger.info(f"📊 Ahora hay {total_nodes} nodos - verificando redistribución de réplicas...")
            threading.Thread(
                target=self.replication_manager.check_redundancy,
                daemon=True
            ).start()
        
    def _on_node_lost(self, node_info: NodeInfo):
        """Callback: Se perdió contacto con un nodo"""
        self.logger.warning(f"👋 Nodo perdido: {node_info.node_id}")
        self.heartbeat.unregister_node(node_info.node_id)
        
    def _on_node_failed(self, node_id: str, node_info: dict):
        """Callback: Un nodo falló health check"""
        self.logger.error(f"💀 Nodo falló: {node_id}")
        
        # Eliminar del discovery para que no aparezca en get_active_nodes()
        with self.discovery._lock:
            if node_id in self.discovery.nodes:
                del self.discovery.nodes[node_id]
                self.logger.info(f"🗑️ Nodo {node_id} eliminado del discovery")
        
        # Si el líder cayó, iniciar elección
        if self.election.current_leader and self.election.current_leader.node_id == node_id:
            self.logger.warning("⚠️ El coordinador cayó! Iniciando elección...")
            threading.Thread(target=self.election.start_election, daemon=True).start()
            
        # Redistribuir datos si somos el coordinador
        if self.election.is_leader():
            self.logger.info("🔄 Iniciando redistribución de datos...")
            threading.Thread(
                target=self.replication_manager.check_redundancy,
                daemon=True
            ).start()

    def _on_node_recovered(self, node_id: str, node_info: dict):
        """Callback: Un nodo se recuperó"""
        self.logger.info(f"✅ Nodo recuperado: {node_id}")
        
        # Verificar redundancia para sincronizar datos
        threading.Thread(
            target=self.replication_manager.check_redundancy,
            daemon=True
        ).start()
        
    def _on_became_leader(self):
        """Callback: Este nodo se convirtió en coordinador"""
        self.logger.info("👑 ¡Somos el COORDINADOR del cluster!")
        
    def _on_leader_changed(self, new_leader):
        """Callback: Hay un nuevo coordinador"""
        self.logger.info(f"👑 Nuevo coordinador: {new_leader.node_id}")
        
    def start(self):
        """Inicia el nodo y todos sus componentes"""
        self.logger.info(f"🚀 Iniciando nodo {self.node_id} en {self.host}:{self.port}")
        
        # 1. Iniciar descubrimiento
        self.discovery.start()
        self.logger.info("✅ Discovery iniciado")
        
        # 2. Iniciar heartbeat
        self.heartbeat.start()
        self.logger.info("✅ Heartbeat iniciado")
        
        # 3. Iniciar servidor TCP en thread separado
        server_thread = threading.Thread(target=self.server.start, daemon=True)
        server_thread.start()
        self.logger.info("✅ Servidor TCP iniciado")
        
        # 4. Esperar para descubrir otros nodos
        self.logger.info("🔍 Descubriendo nodos en la red...")
        time.sleep(5)
        
        # 5. Iniciar elección de líder
        active_nodes = self.discovery.get_active_nodes()
        self.logger.info(f"📊 Nodos encontrados: {len(active_nodes)}")
        
        self.logger.info("🗳️ Iniciando elección de líder...")
        self.election.start_election()
        
        # 6. Sincronizar datos con el cluster
        time.sleep(2)
        self.logger.info("🔄 Sincronizando datos con el cluster...")
        
        # Verificar si tenemos suficientes nodos para tolerancia a fallos (mínimo 3)
        total_nodes = len(active_nodes) + 1  # +1 por nosotros
        if total_nodes < self.replication_manager.REPLICATION_FACTOR:
            self.logger.warning(
                f"⚠️ ADVERTENCIA: Solo hay {total_nodes} nodos activos. "
                f"Se requieren al menos {self.replication_manager.REPLICATION_FACTOR} nodos "
                f"para tolerar la caída de 2 nodos (cada documento en 3 nodos mínimo)."
            )
        else:
            self.logger.info(f"✅ Cluster con {total_nodes} nodos - tolerancia a fallos OK")
        
        threading.Thread(
            target=self.replication_manager.check_redundancy,
            daemon=True
        ).start()
        
        self.logger.info("="*50)
        self.logger.info(f"✅ Nodo {self.node_id} completamente activo")
        self.logger.info(f"   Rol: {'COORDINADOR' if self.election.is_leader() else 'SEGUIDOR'}")
        self.logger.info("="*50)
        
        # Loop principal
        try:
            while self.active:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        """Detener nodo"""
        self.logger.info("🛑 Deteniendo nodo...")
        self.active = False
        self.discovery.stop()
        self.heartbeat.stop()
        self.server.stop()
        self.logger.info("👋 Nodo detenido")
        
    def get_cluster_status(self) -> dict:
        """Obtener estado del cluster"""
        active_nodes = self.discovery.get_active_nodes()
        healthy_nodes = self.heartbeat.get_healthy_nodes()
        
        return {
            'node_id': self.node_id,
            'role': 'coordinator' if self.election.is_leader() else 'follower',
            'coordinator': self.election.current_leader.node_id if self.election.current_leader else None,
            'total_nodes': len(active_nodes) + 1,  # +1 por nosotros
            'healthy_nodes': len(healthy_nodes),
            'peers': [
                {
                    'node_id': n.node_id,
                    'host': n.host,
                    'port': n.port,
                    'status': 'healthy' if n.node_id in healthy_nodes else 'unhealthy',
                }
                for n in active_nodes
            ]
        }
        
    def get_local_files(self) -> list:
        """Obtener lista de archivos indexados localmente"""
        return self.repository.get_all_indexed_files()