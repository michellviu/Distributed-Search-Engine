"""
Nodo Coordinador del sistema distribuido.

El nodo coordinador es responsable de:
1. Mantener registro de nodos de procesamiento
2. Monitorear la salud de los nodos de procesamiento (heartbeats)
3. Asignar tareas de búsqueda a nodos de procesamiento
4. Determinar en qué nodos almacenar datos (por balanceo de carga)
5. Coordinar la replicación de datos entre nodos
6. Mantener un índice de qué archivos están en qué nodos

IMPORTANTE: Los nodos coordinadores NO almacenan datos.

El coordinador:
- USA CHORD DNS para resolver nodo_id -> IP (localización de nodos)
- NO usa consistent hashing para decidir DÓNDE almacenar (usa balanceo de carga)
- USA Quorum para mantener consistencia de archivos replicados
- OPTIMIZA búsquedas usando el índice de ubicaciones de archivos
"""
import sys
import os
import logging
import threading
import asyncio
import time
import socket
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import base64
import hashlib
import hmac
import secrets

# Intentar usar cryptography. Si no está, usar fallback XOR simple (débil).
try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:
    Fernet = None
    InvalidToken = Exception
    _HAS_CRYPTO = False

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from distributed.registry.node_registry import NodeRegistry, NodeInfo
from distributed.dns.chord_dns import ChordDNS
from distributed.consistency.quorum import QuorumManager, QuorumLevel, WriteResult
from distributed.coordination.coordinator_cluster import CoordinatorCluster, CoordinatorRole


class CoordinatorNode:
    """
    Nodo Coordinador del sistema distribuido.
    
    Responsabilidades:
    - Registro y descubrimiento de nodos de procesamiento
    - Monitoreo de salud (heartbeats)
    - Balanceo de carga para asignación de tareas y almacenamiento
    - Mantener índice de ubicación de archivos
    - Coordinar búsquedas distribuidas (optimizadas por índice)
    - Gestión de consistencia mediante quorum
    
    Componentes:
    - CHORD DNS: Para resolver ID -> IP de nodos
    - QuorumManager: Para escrituras/lecturas consistentes
    - NodeRegistry: Para gestión de nodos y archivos
    
    NO almacena datos localmente.
    NO usa consistent hashing para asignar almacenamiento.
    """
    
    # Configuración
    HEARTBEAT_INTERVAL = 5  # Segundos entre heartbeats
    NODE_TIMEOUT = 15  # Segundos sin respuesta para considerar nodo muerto
    REPLICATION_FACTOR = 3  # Número de réplicas por archivo
    QUORUM_LEVEL = QuorumLevel.QUORUM  # Nivel de consistencia por defecto
    
    def __init__(self, 
                 coordinator_id: str,
                 host: str,
                 port: int,
                 announce_host: str = None,
                 peer_coordinators: List[str] = None):
        """
        Inicializa el nodo coordinador.
        
        Args:
            coordinator_id: ID único del coordinador
            host: IP para bind (0.0.0.0 para todas las interfaces)
            port: Puerto TCP
            announce_host: IP para anunciarse a otros nodos
            peer_coordinators: Lista de otros coordinadores ["host:port", ...]
        """
        self.coordinator_id = coordinator_id
        self.host = host
        self.port = port
        self.announce_host = announce_host or host
        self.peer_coordinators = peer_coordinators or []
        
        self.logger = logging.getLogger(f"Coordinator-{coordinator_id}")
        
        # Registro de nodos de procesamiento (sin consistent hashing)
        self.registry = NodeRegistry(coordinator_id, self.REPLICATION_FACTOR)
        
        # CHORD DNS para resolución de nodos (solo para lookup, NO para storage)
        self.dns = ChordDNS(coordinator_id)
        
        # Quorum Manager para consistencia
        self.quorum = QuorumManager(
            coordinator_id, 
            default_level=self.QUORUM_LEVEL
        )
        
        # Cluster de coordinadores con algoritmo BULLY
        self.cluster = CoordinatorCluster(
            coordinator_id=coordinator_id,
            host=announce_host or host,
            port=port,
            peer_addresses=peer_coordinators
        )
        
        # Configurar callback para reconciliación cuando cambia el líder
        self.cluster.set_on_new_leader_callback(self._on_new_leader_elected)
        
        # Event loop para operaciones async
        self._loop = None
        self._loop_thread = None
        
        # Estado del coordinador
        self.active = False
        self.server_socket = None
        self._lock = threading.RLock()
        
        # Seguimiento de replicaciones en progreso
        self._replication_in_progress = {}  # {file_name: set(target_node_ids)}
        self._replication_lock = threading.Lock()
        
        # Estadísticas
        self.stats = {
            'queries_processed': 0,
            'files_stored': 0,
            'optimized_searches': 0,
            'start_time': None,
            'replications_requested': 0,
            'replications_succeeded': 0,
            'replications_failed': 0
        }
        
        self.logger.info(f"🎯 Coordinador inicializado: {coordinator_id}")
        # Inicializar criptografía (clave maestra)
        self._init_crypto()
        
    def start(self):
        """Inicia el nodo coordinador"""
        self.active = True
        self.stats['start_time'] = time.time()
        
        self.logger.info("=" * 60)
        self.logger.info("   NODO COORDINADOR INICIANDO")
        self.logger.info("=" * 60)
        self.logger.info(f"   ID:          {self.coordinator_id}")
        self.logger.info(f"   Host:        {self.host}:{self.port}")
        self.logger.info(f"   Announce:    {self.announce_host}:{self.port}")
        self.logger.info(f"   Quorum:      {self.QUORUM_LEVEL.value}")
        self.logger.info(f"   Peers:       {len(self.peer_coordinators)} coordinadores")
        self.logger.info("=" * 60)
        
        # 0. Iniciar event loop para async
        self._start_async_loop()
        self.logger.info("✅ Event loop async iniciado")
        
        # 1. Iniciar servidor TCP
        threading.Thread(target=self._start_server, daemon=True).start()
        self.logger.info("✅ Servidor TCP iniciado")
        
        # 2. Iniciar heartbeat monitor
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        self.logger.info("✅ Monitor de heartbeats iniciado")
        
        # 3. Iniciar verificación de replicación
        threading.Thread(target=self._replication_check_loop, daemon=True).start()
        self.logger.info("✅ Verificador de replicación iniciado")
        
        # 4. Iniciar cluster de coordinadores (algoritmo Bully)
        if self.peer_coordinators:
            self.cluster.start()
            self.logger.info("✅ Cluster de coordinadores iniciado (Bully)")
            
            # 5. Iniciar sincronización continua de estado entre coordinadores
            threading.Thread(target=self._state_sync_loop, daemon=True).start()
            self.logger.info("✅ Sincronización de estado entre coordinadores iniciada")
        else:
            # Si no hay peers, somos el líder por defecto
            self.cluster.role = CoordinatorRole.LEADER
            self.cluster.current_leader = self.coordinator_id
            self.logger.info("✅ Único coordinador - asumiendo liderazgo")
        
        self.logger.info("🎯 Coordinador listo para recibir conexiones")
        
        # Mantener vivo
        try:
            while self.active:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def _start_async_loop(self):
        """Inicia un event loop en un thread separado para operaciones async"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        # Esperar a que el loop esté listo
        time.sleep(0.1)
    
    def stop(self):
        """Detiene el nodo coordinador"""
        self.logger.info("🛑 Deteniendo coordinador...")
        self.active = False
        
        # Detener cluster de coordinadores
        if self.cluster.active:
            self.cluster.stop()
        
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self.logger.info("👋 Coordinador detenido")
    
    def _send_to_socket(self, sock: socket.socket, data: dict):
        """Envía datos JSON a un socket con prefijo de longitud"""
        json_data = json.dumps(data)
        message = f"{len(json_data):<8}{json_data}"
        sock.sendall(message.encode())
    
    def _receive_from_socket(self, sock: socket.socket) -> dict:
        """Recibe datos JSON de un socket con prefijo de longitud"""
        try:
            length_str = sock.recv(8).decode()
            if not length_str:
                return None
            length = int(length_str.strip())
            
            data = b''
            while len(data) < length:
                chunk = sock.recv(min(4096, length - len(data)))
                if not chunk:
                    break
                data += chunk
            
            return json.loads(data.decode())
        except Exception as e:
            self.logger.debug(f"Error recibiendo de socket: {e}")
            return None
    
    def _start_server(self):
        """Inicia el servidor TCP para recibir conexiones"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(50)
        
        while self.active:
            try:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, address = self.server_socket.accept()
                    threading.Thread(
                        target=self._handle_connection,
                        args=(client_socket, address),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self.active:
                    self.logger.error(f"Error en servidor: {e}")
    
    def _handle_connection(self, client_socket: socket.socket, address: tuple):
        """Maneja una conexión entrante"""
        try:
            client_socket.settimeout(30)
            
            # Leer header con longitud
            length_data = client_socket.recv(8)
            if not length_data:
                return
            
            msg_len = int(length_data.decode().strip())
            
            # Leer mensaje
            data = b''
            while len(data) < msg_len:
                chunk = client_socket.recv(min(4096, msg_len - len(data)))
                if not chunk:
                    break
                data += chunk
            
            request = json.loads(data.decode())
            response = self._handle_request(request, address)
            
            # Enviar respuesta
            response_json = json.dumps(response)
            response_bytes = response_json.encode()
            client_socket.sendall(f"{len(response_bytes):<8}".encode())
            client_socket.sendall(response_bytes)
            
        except Exception as e:
            self.logger.debug(f"Error manejando conexión de {address}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _handle_request(self, request: dict, address: tuple) -> dict:
        """
        Procesa una petición entrante.
        
        Acciones soportadas:
        - register: Registrar nodo de procesamiento
        - heartbeat: Actualizar estado de nodo
        - search: Coordinar búsqueda distribuida
        - store: Determinar nodos para almacenar archivo
        - file_stored: Confirmar que un archivo fue almacenado en un nodo
        - get_nodes: Obtener lista de nodos activos
        - get_file_locations: Obtener nodos donde está un archivo
        - get_peers: Para compatibilidad con discovery
        - health: Health check
        - cluster_status: Estado del cluster
        """
        action = request.get('action', '')
        
        if action == 'request_sync':
            return self._handle_request_sync(request)
            
        elif action == 'register':
            return self._handle_register(request)
        
        elif action == 'heartbeat':
            return self._handle_heartbeat(request)
        
        elif action == 'search':
            return self._handle_search(request)
        
        elif action == 'store':
            return self._handle_store(request)
        
        elif action == 'file_stored':
            return self._handle_file_stored(request)
        
        elif action == 'get_nodes':
            return self._handle_get_nodes(request)
            
        elif action == 'get_coordinators':
            return self._handle_get_coordinators(request)
        
        elif action == 'get_file_locations':
            return self._handle_get_file_locations(request)
        
        elif action == 'get_peers':
            return self._handle_get_peers(request, address)
        
        elif action == 'health':
            return {
                'status': 'ok', 
                'node_type': 'coordinator',
                'is_leader': self.cluster.is_leader(),
                'role': self.cluster.role.value,
                'current_leader': self.cluster.current_leader,
                'coordinator_id': self.coordinator_id
            }
        
        elif action == 'cluster_status':
            return self._get_cluster_status()
        
        elif action == 'list':
            return self._handle_list(request)
        
        elif action == 'download':
            return self._handle_download(request)
        
        elif action == 'request_file_assignment':
            return self._handle_request_file_assignment(request)
        
        # === Mensajes del algoritmo BULLY ===
        elif action == 'bully_message':
            return self._handle_bully_message(request)
        
        elif action == 'coordinator_heartbeat':
            return self._handle_coordinator_heartbeat(request)
        
        elif action == 'replicate_state':
            return self._handle_replicate_state(request)
        
        elif action == 'request_reconciliation':
            return self._handle_reconciliation_request(request)
        
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}
    
    def _handle_request_sync(self, request: dict) -> dict:
        """
        Maneja solicitud de sincronización de un nodo nuevo/reconectado.
        Verifica qué archivos le faltan y ordena replicación.
        """
        node_id = request.get('node_id')
        current_files = set(request.get('current_files', []))
        
        if not node_id:
            return {'status': 'error', 'message': 'Missing node_id'}
        
        self.logger.info(f"🔄 Iniciando sincronización para nodo {node_id}")
        
        # Obtener todos los archivos conocidos en el sistema
        all_known_files = self.registry.get_all_file_names()
        files_to_sync = []
        
        for file_name in all_known_files:
            if file_name not in current_files:
                # El nodo no tiene este archivo, verificar si necesita réplica
                # (o si forzamos full replication como pidió el usuario)
                files_to_sync.append(file_name)
        
        if files_to_sync:
            self.logger.info(f"📦 Nodo {node_id} necesita {len(files_to_sync)} archivos")
            # Iniciar replicación en background para no bloquear
            threading.Thread(
                target=self._push_files_to_node,
                args=(node_id, files_to_sync),
                daemon=True
            ).start()
            
        return {'status': 'success', 'scheduled': len(files_to_sync)}

    def _push_files_to_node(self, target_node_id: str, files: List[str]):
        """Envía archivos faltantes a un nodo específico"""
        target_node = self.registry.lookup(target_node_id)
        if not target_node:
            return

        for file_name in files:
            # Buscar quién tiene el archivo (source)
            locations = self.registry.get_file_locations(file_name)
            if not locations:
                continue
                
            # Elegir un source activo
            source_id = locations[0]
            source_node = self.registry.lookup(source_id)
            
            if source_node:
                if self._check_node_health(source_node):
                    self.logger.info(f"🔄 Replicando '{file_name}' de {source_id} a {target_node_id}")
                    self._trigger_replication(file_name, source_node, target_node)
                    time.sleep(0.5)  # Evitar saturación
                else:
                    self.logger.warning(f"⚠️ No se puede replicar '{file_name}': Fuente {source_id} no responde health check")
            else:
                self.logger.warning(f"⚠️ No se puede replicar '{file_name}': Fuente {source_id} no encontrada en registro")

    def _handle_register(self, request: dict) -> dict:
        """Registra un nodo de procesamiento"""
        # Validar si somos el líder. Si no, redirigir.
        if not self.cluster.is_leader():
            leader_id = self.cluster.current_leader
            leader_addr = self.cluster.get_leader_address() # Retorna tupla (host, port) o None
            
            if leader_id and leader_addr:
                return {
                    'status': 'redirect',
                    'leader_host': leader_addr[0],
                    'leader_port': leader_addr[1],
                    'message': f'Redirect to leader {leader_id}'
                }

        node_id = request.get('node_id')
        host = request.get('host')
        port = request.get('port', 5001)
        files = request.get('files', [])  # Lista de archivos que tiene el nodo
        
        if not node_id or not host:
            return {'status': 'error', 'message': 'Missing node_id or host'}
        
        # Registrar en el registry (para gestión y balanceo)
        self.registry.register_node(node_id, host, port)
        
        # Registrar en el CHORD DNS (para resolución rápida de ID -> IP)
        self.dns.register_node(node_id, host, port)
        
        # Registrar los archivos que el nodo tiene
        for file_name in files:
            # Intentar mapear nombre encriptado a original si aplica
            mapped = self._map_encrypted_to_original(file_name) if file_name else None
            if mapped:
                self.registry.register_file_location(mapped, node_id)
            else:
                self.registry.register_file_location(file_name, node_id)
        
        # Normalizar y limpiar entradas encriptadas (evita duplicados en el índice)
        try:
            self._cleanup_encrypted_entries()
        except Exception:
            pass

        self.logger.info(f"📝 Nodo de procesamiento registrado: {node_id} ({host}:{port}) - {len(files)} archivos")
        
        return {
            'status': 'success',
            'message': f'Node {node_id} registered with {len(files)} files',
            'coordinator_id': self.coordinator_id
        }
    
    def _handle_heartbeat(self, request: dict) -> dict:
        """Actualiza el heartbeat de un nodo"""
        node_id = request.get('node_id')
        current_tasks = request.get('load', 0)
        files_count = request.get('files_count', 0)
        
        if not node_id:
            return {'status': 'error', 'message': 'Missing node_id'}
        
        updated = self.registry.update_last_seen(node_id)
        if updated:
            self.registry.update_node_tasks(node_id, current_tasks)
            # También actualizar en DNS
            self.dns.update_last_seen(node_id)
        
        return {
            'status': 'ok' if updated else 'error',
            'message': 'Heartbeat received' if updated else 'Node not registered'
        }
    
    def _handle_request_file_assignment(self, request: dict) -> dict:
        """
        Asigna archivos a un nodo de procesamiento para indexación inicial.
        
        Implementa balanceo de carga para la indexación inicial:
        - Archivos nuevos: asigna usando hash consistente del nombre
        - Archivos existentes: solo asigna si faltan réplicas Y este nodo 
          es el mejor candidato (menor carga)
        
        Esto evita que todos los nodos indexen todos los archivos cuando
        comparten el mismo volumen de almacenamiento.
        """
        node_id = request.get('node_id')
        available_files = request.get('available_files', [])
        host = request.get('host')
        port = request.get('port', 5000)
        
        if not node_id or not host:
            return {'status': 'error', 'message': 'Missing node_id or host'}
        
        # Registrar el nodo primero si no está registrado
        self.registry.register_node(node_id, host, port)
        self.dns.register_node(node_id, host, port)
        
        # Determinar qué archivos asignar a este nodo
        assigned_files = []
        
        with self._lock:
            # Obtener número de nodos activos (incluyendo este)
            active_nodes = list(self.registry.get_active_nodes())
            num_nodes = len(active_nodes)
            
            if num_nodes == 0:
                num_nodes = 1
            
            # Encontrar el índice de este nodo en la lista ordenada
            node_ids_sorted = sorted([n.node_id for n in active_nodes])
            if node_id not in node_ids_sorted:
                node_ids_sorted.append(node_id)
                node_ids_sorted.sort()
            
            node_index = node_ids_sorted.index(node_id)
            num_total_nodes = len(node_ids_sorted)
            
            for file_name in available_files:
                # Verificar si el archivo ya está registrado
                existing_locations = self.registry.get_file_locations(file_name)
                current_replicas = len(existing_locations)
                
                # Calcular cuántas réplicas se necesitan (máximo replication_factor o num_nodes)
                target_replicas = min(self.REPLICATION_FACTOR, num_total_nodes)
                
                if current_replicas >= target_replicas:
                    # Ya hay suficientes réplicas, no asignar
                    continue
                
                if not existing_locations:
                    # Archivo nuevo: usar hash consistente para decidir
                    file_hash = hash(file_name) % num_total_nodes
                    
                    # Este nodo debe tener el archivo si está en las primeras 'target_replicas' posiciones
                    target_indices = [(file_hash + i) % num_total_nodes for i in range(target_replicas)]
                    
                    if node_index in target_indices:
                        assigned_files.append(file_name)
                else:
                    # Archivo existente pero faltan réplicas
                    if node_id not in existing_locations:
                        # Solo asignar si este nodo es el mejor candidato
                        # (primero en el orden de hash que no tiene el archivo)
                        file_hash = hash(file_name) % num_total_nodes
                        
                        # Buscar el siguiente nodo que debería tener el archivo
                        for i in range(num_total_nodes):
                            candidate_idx = (file_hash + i) % num_total_nodes
                            candidate_id = node_ids_sorted[candidate_idx]
                            
                            if candidate_id not in existing_locations:
                                # Este es el siguiente nodo que debería tener el archivo
                                if candidate_id == node_id:
                                    assigned_files.append(file_name)
                                break  # Solo asignar a un nodo por iteración
        
        self.logger.info(
            f"📋 Asignación de archivos para {node_id}: "
            f"{len(assigned_files)}/{len(available_files)} archivos"
        )
        
        return {
            'status': 'success',
            'node_id': node_id,
            'assigned_files': assigned_files,
            'total_available': len(available_files),
            'total_assigned': len(assigned_files)
        }
    
    # =========================================================================
    # HANDLERS PARA ALGORITMO BULLY Y COORDINACIÓN DE CLUSTER
    # =========================================================================
    
    def _handle_bully_message(self, request: dict) -> dict:
        """
        Procesa mensajes del algoritmo Bully para elección de líder.
        
        Tipos de mensaje:
        - ELECTION: Un nodo inicia elección (responder OK si tenemos mayor ID)
        - COORDINATOR: Un nodo anuncia que es el nuevo líder
        """
        message_type = request.get('message_type')
        from_id = request.get('from_coordinator')
        from_host = request.get('from_host')
        from_port = request.get('from_port', 5000)
        
        self.logger.info(f"🗳️ Mensaje Bully recibido: {message_type} de {from_id}")
        
        return self.cluster.handle_bully_message(
            message_type=message_type,
            from_id=from_id,
            from_host=from_host,
            from_port=from_port
        )
    
    def _handle_coordinator_heartbeat(self, request: dict) -> dict:
        """
        Procesa heartbeat de otro coordinador.
        Usado para detectar si el líder sigue vivo.
        """
        from_id = request.get('from_coordinator')
        from_host = request.get('from_host')
        from_port = request.get('from_port')
        role = request.get('role', 'FOLLOWER')
        
        self.logger.debug(f"💓 Heartbeat de coordinador: {from_id} ({role})")
        
        # Gossip: Si el coordinador que nos contacta no lo conocemos, lo agregamos
        if from_id and from_host and from_port:
            self.cluster.add_peer(from_id, from_host, from_port)
        
        return {
            'status': 'ok',
            'coordinator_id': self.coordinator_id,
            'role': self.cluster.role.value,
            'is_leader': self.cluster.is_leader()
        }
    
    def _handle_replicate_state(self, request: dict) -> dict:
        """
        Recibe estado replicado del líder.
        Solo los followers reciben este mensaje.
        """
        from_id = request.get('from_coordinator')
        state_data = request.get('state')
        
        if not state_data:
            return {'status': 'error', 'message': 'No state data'}
        
        # Aplicar el estado recibido (solo si somos follower)
        applied = self.cluster.handle_state_replication(from_id, state_data)
        
        if applied:
            # IMPORTANTE: Aplicar el estado al registry LOCAL
            nodes_data = state_data.get('nodes', {})
            file_locations = state_data.get('file_locations', {})
            
            # Actualizar nodos
            for node_id, node_info in nodes_data.items():
                if node_id not in self.registry.nodes:
                    self.registry.register_node(
                        node_id,
                        node_info.get('host', 'unknown'),
                        node_info.get('port', 5001)
                    )
                # Actualizar last_seen
                self.registry.update_last_seen(node_id)
            
            # Actualizar ubicaciones de archivos
            for file_name, locations in file_locations.items():
                for node_id in locations:
                    self.registry.register_file_location(file_name, node_id)
            
            self.logger.debug(
                f"📥 Estado sincronizado del líder: "
                f"{len(nodes_data)} nodos, {len(file_locations)} archivos"
            )
        
        return {
            'status': 'ok' if applied else 'ignored',
            'coordinator_id': self.coordinator_id
        }
    
    def _handle_reconciliation_request(self, request: dict) -> dict:
        """
        Procesa una solicitud de reconciliación de otro coordinador.
        
        Usado cuando un coordinador se reconecta después de una partición de red.
        El coordinador que se reconecta envía su estado y recibe el estado actual.
        """
        from_id = request.get('from_coordinator')
        their_state = request.get('state', {})
        
        self.logger.info(f"🔄 Solicitud de reconciliación de {from_id}")
        
        # Obtener nuestro estado actual
        our_state = {
            'nodes': {nid: node.to_dict() for nid, node in self.registry.nodes.items()},
            'file_locations': dict(self.registry.file_locations)
        }
        
        # Realizar la reconciliación
        reconciled = self._reconcile_states(their_state, our_state)
        
        return {
            'status': 'ok',
            'coordinator_id': self.coordinator_id,
            'reconciled_state': reconciled,
            'is_leader': self.cluster.is_leader()
        }
    
    def _reconcile_states(self, their_state: dict, our_state: dict) -> dict:
        """
        Reconcilia dos estados de coordinadores después de una partición de red.
        
        Estrategia de reconciliación:
        - Unir todos los nodos conocidos
        - Unir todas las ubicaciones de archivos
        - Resolver conflictos tomando la unión (más réplicas = más disponibilidad)
        """
        reconciled = {
            'nodes': {},
            'file_locations': {}
        }
        
        # 1. Unir nodos de ambos estados
        all_nodes = set()
        if 'nodes' in their_state:
            all_nodes.update(their_state['nodes'].keys())
        if 'nodes' in our_state:
            all_nodes.update(our_state['nodes'].keys())
        
        # Preferir nuestro estado si es más reciente
        for node_id in all_nodes:
            their_node = their_state.get('nodes', {}).get(node_id)
            our_node = our_state.get('nodes', {}).get(node_id)
            
            if our_node and their_node:
                # Tomar el más reciente
                our_seen = our_node.get('last_seen', 0)
                their_seen = their_node.get('last_seen', 0)
                reconciled['nodes'][node_id] = our_node if our_seen >= their_seen else their_node
            else:
                reconciled['nodes'][node_id] = our_node or their_node
        
        # 2. Unir ubicaciones de archivos (tomar la UNIÓN)
        all_files = set()
        if 'file_locations' in their_state:
            all_files.update(their_state['file_locations'].keys())
        if 'file_locations' in our_state:
            all_files.update(our_state['file_locations'].keys())
        
        for file_name in all_files:
            their_locs = set(their_state.get('file_locations', {}).get(file_name, []))
            our_locs = set(our_state.get('file_locations', {}).get(file_name, []))
            
            # Unión de ubicaciones (más réplicas = más disponibilidad)
            reconciled['file_locations'][file_name] = list(their_locs | our_locs)
        
        self.logger.info(
            f"🔄 Reconciliación: {len(reconciled['nodes'])} nodos, "
            f"{len(reconciled['file_locations'])} archivos"
        )
        
        # 3. Aplicar el estado reconciliado a nuestro registro
        self._apply_reconciled_state(reconciled)
        
        return reconciled
    
    def _apply_reconciled_state(self, reconciled: dict):
        """Aplica el estado reconciliado a nuestro registro local"""
        # Aplicar nodos
        for node_id, node_data in reconciled.get('nodes', {}).items():
            if node_id not in self.registry.nodes:
                self.registry.register_node(
                    node_id,
                    node_data.get('host', 'unknown'),
                    node_data.get('port', 5001)
                )
        
        # Aplicar ubicaciones de archivos
        for file_name, locations in reconciled.get('file_locations', {}).items():
            for node_id in locations:
                self.registry.register_file_location(file_name, node_id)
    
    def _state_sync_loop(self):
        """
        Loop de sincronización continua de estado entre coordinadores.
        
        - Si somos LÍDER: Enviamos nuestro estado a todos los followers cada 5 segundos.
        - Si somos FOLLOWER: Enviamos nuestro estado al líder (Anti-Entropy) para asegurar consistencia.
        
        Esto garantiza recuperación bidireccional tras particiones de red.
        """
        STATE_SYNC_INTERVAL = 5  # Segundos entre sincronizaciones
        
        while self.active:
            time.sleep(STATE_SYNC_INTERVAL)
            
            try:
                if self.cluster.is_leader():
                    # Somos el líder: replicar estado a todos los followers
                    nodes = {nid: node.to_dict() for nid, node in self.registry.nodes.items()}
                    # IMPORTANTE: Convertir sets a lists para JSON serialization
                    file_locations = {k: list(v) for k, v in self.registry.file_locations.items()}
                    
                    if nodes or file_locations:
                        self.cluster.replicate_state(nodes, file_locations)
                        self.logger.debug(
                            f"📤 Estado replicado a followers: "
                            f"{len(nodes)} nodos, {len(file_locations)} archivos"
                        )
                else:
                    # Somos follower: asegurar que el líder tenga nuestros datos (Anti-Entropy)
                    # Esto cubre el caso "Split Brain" donde recibimos datos aislados
                    self.request_reconciliation_from_leader()
                    
            except Exception as e:
                self.logger.debug(f"Error en sync loop: {e}")
    
    def _replicate_state_to_followers(self):
        """
        Replica el estado actual a todos los followers.
        Solo el líder debe llamar este método.
        """
        if not self.cluster.is_leader():
            return
        
        nodes = {nid: node.to_dict() for nid, node in self.registry.nodes.items()}
        # IMPORTANTE: Convertir sets a lists para JSON serialization
        file_locations = {k: list(v) for k, v in self.registry.file_locations.items()}
        
        self.cluster.replicate_state(nodes, file_locations)
    
    def request_reconciliation_from_leader(self):
        """
        Solicita reconciliación al líder después de reconectarse.
        Usado cuando un follower se reconecta tras una partición de red.
        """
        leader_addr = self.cluster.get_leader_address()
        if not leader_addr or self.cluster.is_leader():
            return None
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect(leader_addr)
                
                # Enviar nuestro estado para reconciliación
                our_state = {
                    'nodes': {nid: node.to_dict() for nid, node in self.registry.nodes.items()},
                    # IMPORTANTE: Convertir sets a lists para JSON serialization
                    'file_locations': {k: list(v) for k, v in self.registry.file_locations.items()}
                }
                
                request = {
                    'action': 'request_reconciliation',
                    'from_coordinator': self.coordinator_id,
                    'state': our_state
                }
                
                self._send_to_socket(sock, request)
                response = self._receive_from_socket(sock)
                
                if response and response.get('reconciled_state'):
                    self._apply_reconciled_state(response['reconciled_state'])
                    self.logger.info("✅ Reconciliación con líder completada")
                    return response
                    
        except Exception as e:
            self.logger.error(f"❌ Error en reconciliación: {e}")
        
        return None
    
    def _on_new_leader_elected(self, leader_id: str, leader_host: str, leader_port: int):
        """
        Callback llamado cuando se acepta un nuevo líder.
        Usado para sincronización automática después de partición de red.
        """
        self.logger.info(f"🔄 Nuevo líder detectado: {leader_id} en {leader_host}:{leader_port}")
        
        # Esperar un momento para que el líder esté listo
        time.sleep(1)
        
        # Solicitar reconciliación al nuevo líder
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((leader_host, leader_port))
                
                # Enviar nuestro estado para reconciliación
                our_state = {
                    'nodes': {nid: node.to_dict() for nid, node in self.registry.nodes.items()},
                    # IMPORTANTE: Convertir sets a lists para JSON serialization
                    'file_locations': {k: list(v) for k, v in self.registry.file_locations.items()}
                }
                
                request = {
                    'action': 'request_reconciliation',
                    'from_coordinator': self.coordinator_id,
                    'state': our_state
                }
                
                self._send_to_socket(sock, request)
                response = self._receive_from_socket(sock)
                
                if response and response.get('status') == 'ok':
                    reconciled = response.get('reconciled_state', {})
                    self._apply_reconciled_state(reconciled)
                    
                    nodes_count = len(reconciled.get('nodes', {}))
                    files_count = len(reconciled.get('file_locations', {}))
                    self.logger.info(
                        f"✅ Reconciliación automática completada: "
                        f"{nodes_count} nodos, {files_count} archivos"
                    )
                else:
                    self.logger.warning(f"⚠️ Reconciliación falló: {response}")
                    
        except Exception as e:
            self.logger.error(f"❌ Error en reconciliación automática: {e}")

    def _handle_search(self, request: dict) -> dict:
        """
        Coordina una búsqueda distribuida OPTIMIZADA.
        
        OPTIMIZACIÓN: Como la búsqueda es por nombre/extensión de archivo,
        el coordinador puede hacerla LOCALMENTE en su registro sin
        consultar los nodos de procesamiento.
        
        El coordinador conoce todos los archivos y sus ubicaciones,
        así que puede responder directamente.
        
        Si el cliente necesita descargar el archivo, usará las ubicaciones
        devueltas para contactar a los nodos de procesamiento.
        """
        query = request.get('query', '')
        file_type = request.get('file_type')
        
        # Permitir búsqueda vacía si hay file_type (listar por extensión)
        if not query and not file_type:
            # Si no hay query ni file_type, retornar todos los archivos
            query = ''  # Buscar todo
        
        self.logger.info(f"🔍 Búsqueda: '{query}' (tipo: {file_type or 'any'})")
        
        # Asegurar que no tengamos entradas duplicadas antes de buscar
        try:
            self._cleanup_encrypted_entries()
        except Exception:
            pass

        # Búsqueda LOCAL en el registro del coordinador
        # No necesitamos consultar nodos porque solo buscamos por nombre
        results = self.registry.search_files(query, file_type)
        
        self.stats['queries_processed'] += 1
        self.stats['optimized_searches'] += 1
        
        # Añadir información de nodos activos para cada resultado
        for result in results:
            active_nodes = []
            for node_id in result.get('nodes', []):
                node = self.registry.lookup(node_id)
                if node:
                    active_nodes.append({
                        'node_id': node_id,
                        'host': node.host,
                        'port': node.port
                    })
            result['active_nodes'] = active_nodes
        
        return {
            'status': 'success',
            'query': query,
            'file_type': file_type,
            'total_results': len(results),
            'search_type': 'local_registry',  # Búsqueda optimizada local
            'results': results
        }
    
    def _query_processing_node(self, node: NodeInfo, query: str, file_type: str = None) -> List[dict]:
        """Envía una query de búsqueda a un nodo de procesamiento"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((node.host, node.port))
                
                request = {
                    'action': 'search_local',
                    'query': query,
                    'file_type': file_type
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if not length_data:
                    return []
                
                msg_len = int(length_data.decode().strip())
                data = b''
                while len(data) < msg_len:
                    chunk = sock.recv(min(4096, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                response = json.loads(data.decode())
                results = response.get('results', [])
                
                # Añadir nodo origen
                for r in results:
                    r['source_node'] = node.node_id
                
                return results
                
        except Exception as e:
            self.logger.debug(f"Error querying {node.node_id}: {e}")
            return []
    
    def _merge_search_results(self, results: List[dict]) -> List[dict]:
        """Deduplica y ordena resultados de búsqueda"""
        seen = set()
        merged = []
        
        for result in results:
            key = result.get('path') or result.get('file_id') or result.get('name')
            if key and key not in seen:
                seen.add(key)
                merged.append(result)
        
        # Ordenar por score si existe
        merged.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return merged
    
    def _handle_store(self, request: dict) -> dict:
        """
        Almacena un archivo en el sistema distribuido.
        
        Usa BALANCEO DE CARGA: asigna a los nodos con menos archivos.
        NO usa consistent hashing.
        
        Si se proporciona file_content, el coordinador distribuye el archivo
        a los nodos de procesamiento seleccionados.
        """
        file_name = request.get('file_name')
        file_size = request.get('file_size', 0)
        file_content = request.get('file_content')  # Base64 encoded
        
        if not file_name:
            return {'status': 'error', 'message': 'Missing file_name'}
        
        # Verificar si el archivo ya existe
        existing_locations = self.registry.get_file_locations(file_name)
        if existing_locations:
            # El archivo ya existe, devolver ubicaciones actuales
            target_nodes = []
            for node_id in existing_locations:
                addr = self.registry.resolve(node_id)
                if addr:
                    target_nodes.append({
                        'node_id': node_id,
                        'host': addr[0],
                        'port': addr[1]
                    })
            
            return {
                'status': 'success',
                'file_name': file_name,
                'target_nodes': target_nodes,
                'replication_factor': len(target_nodes),
                'already_exists': True
            }
        
        # Archivo nuevo: asignar a TODOS los nodos activos si queremos full replication
        # o usar REPLICATION_FACTOR.
        # Aquí asignamos a TODOS para garantizar disponibilidad inmediata
        all_active_nodes = self.registry.get_active_nodes(max_age_seconds=self.NODE_TIMEOUT)
        target_node_ids = [n.node_id for n in all_active_nodes]
        
        # Si no hay suficientes nodos activos, al menos intentar con el factor mínimo
        if not target_node_ids:
            return {
                'status': 'error',
                'message': 'No processing nodes available for storage'
            }

        # Resolver IDs a direcciones
        target_nodes = []
        for node_id in target_node_ids:
            addr = self.registry.resolve(node_id)
            if addr:
                target_nodes.append({
                    'node_id': node_id,
                    'host': addr[0],
                    'port': addr[1]
                })
        
        self.logger.info(f"📦 Archivo '{file_name}' asignado a nodos: {target_node_ids} (por balanceo de carga)")
        
        # Si se proporciona contenido, distribuir a los nodos
        stored_nodes = []
        if file_content:
            for target in target_nodes:
                success = self._send_file_to_node(
                    file_name, 
                    file_content, 
                    target['host'], 
                    target['port'],
                    target['node_id']
                )
                if success:
                    stored_nodes.append(target['node_id'])
                    # Registrar ubicación inmediatamente para evitar inconsistencias si falla el callback
                    self.registry.register_file_location(file_name, target['node_id'])
            
            if stored_nodes:
                self.logger.info(f"✅ Archivo '{file_name}' distribuido a {len(stored_nodes)} nodos: {stored_nodes}")
            else:
                return {
                    'status': 'error',
                    'message': 'Failed to store file on any node'
                }
        
        return {
            'status': 'success',
            'file_name': file_name,
            'target_nodes': target_nodes,
            'stored_on': stored_nodes if file_content else [],
            'replication_factor': len(target_nodes),
            'already_exists': False
        }
    
    def _send_file_to_node(self, file_name: str, file_content: str, host: str, port: int, node_id: str) -> bool:
        """Envía un archivo a un nodo de procesamiento (coordina cifrado del contenido)"""
        self.logger.info(f"📤 Intentando enviar '{file_name}' a {node_id} ({host}:{port})")
        try:
            # file_content expected base64 from client -> decode
            try:
                raw_bytes = base64.b64decode(file_content.encode())
            except Exception:
                raw_bytes = file_content.encode()  # fallback, treat as raw bytes string

            # Cifrar el contenido con la clave maestra (mismo ciphertext para todas las réplicas)
            encrypted_content = self._encrypt_bytes(raw_bytes)  # devuelve base64/text

            # Nombre determinístico (para que el nodo lo use como key para almacenamiento)
            encrypted_name = self._encrypt_filename(file_name)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30)
                sock.connect((host, port))
                
                request = {
                    'action': 'store',
                    'file_name': encrypted_name,
                    'file_content': encrypted_content,
                    # incluir nombre original por compatibilidad si el nodo lo quiere notificar luego
                    'original_file_name': file_name,
                    'encrypted_by_coord': True
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    response_data = b''
                    while len(response_data) < msg_len:
                        chunk = sock.recv(min(4096, msg_len - len(response_data)))
                        if not chunk:
                            break
                        response_data += chunk
                    
                    response = json.loads(response_data.decode())
                    if response.get('status') == 'success':
                        self.logger.info(f"✅ Archivo '{file_name}' enviado exitosamente a {node_id}")
                        return True
                    else:
                        self.logger.warning(f"⚠️ Nodo {node_id} respondió con error: {response}")
                
                return False
                
        except Exception as e:
            self.logger.warning(f"⚠️ Error enviando archivo a {node_id}: {e}")
            return False
    
    def _handle_file_stored(self, request: dict) -> dict:
        """
        Confirma que un archivo fue almacenado en un nodo.
        
        Después de que un nodo de procesamiento almacena un archivo,
        notifica al coordinador para actualizar el índice de ubicaciones.
        """
        file_name = request.get('file_name')
        node_id = request.get('node_id')
        original_provided = request.get('original_file_name')  # si el nodo nos da el nombre original

        if not file_name or not node_id:
            return {'status': 'error', 'message': 'Missing file_name or node_id'}

        # Preferir nombre original si fue enviado por el nodo
        if original_provided:
            original_name = original_provided
        else:
            # Intentar mapear nombre cifrado a nombre original conocido
            mapped = self._map_encrypted_to_original(file_name)
            original_name = mapped if mapped else file_name

        # Registrar usando el NOMBRE ORIGINAL (el índice del coordinador debe permanecer sin cifrar)
        self.registry.register_file_location(original_name, node_id)
        self.stats['files_stored'] += 1

        # Remover de replicaciones en progreso usando el nombre original (si existe)
        with self._replication_lock:
            if original_name in self._replication_in_progress:
                self._replication_in_progress[original_name].discard(node_id)
                if not self._replication_in_progress[original_name]:
                    del self._replication_in_progress[original_name]
            # Además, si el caller pasó el encrypted key as in-progress, limpiarlo también
            if file_name in self._replication_in_progress and file_name != original_name:
                self._replication_in_progress[file_name].discard(node_id)
                if not self._replication_in_progress[file_name]:
                    del self._replication_in_progress[file_name]

        self.logger.info(f"📍 Confirmado: '{original_name}' almacenado en {node_id}")
        
        # Intentar limpiar entradas encriptadas que puedan duplicar este registro
        try:
            self._cleanup_encrypted_entries()
        except Exception:
            pass

        return {
            'status': 'success',
            'message': f'File location registered: {original_name} -> {node_id}'
        }
    
    def _handle_get_nodes(self, request: dict) -> dict:
        """Devuelve lista de nodos de procesamiento activos"""
        nodes = self.registry.get_active_nodes(max_age_seconds=self.NODE_TIMEOUT)
        
        return {
            'status': 'success',
            'nodes': [n.to_dict() for n in nodes],
            'count': len(nodes)
        }

    def _handle_get_coordinators(self, request: dict) -> dict:
        """
        Devuelve lista de coordinadores conocidos en el cluster.
        Usado para descubrimiento dinámico por parte de clientes.
        """
        peers = []
        
        # Agregar este mismo coordinador
        peers.append({
            'coordinator_id': self.coordinator_id,
            'host': self.announce_host,
            'port': self.port,
            'is_leader': self.cluster.is_leader(),
            'role': self.cluster.role.value if hasattr(self.cluster, 'role') else 'UNKNOWN'
        })
        
        # Agregar peers conocidos
        if hasattr(self.cluster, 'peers'):
            for peer_id, peer in self.cluster.peers.items():
                peers.append({
                    'coordinator_id': peer.coordinator_id,
                    'host': peer.host,
                    'port': peer.port,
                    'is_leader': False, # Solo estimación
                    'role': peer.role.value if hasattr(peer, 'role') else 'UNKNOWN'
                })
        
        return {
            'status': 'success',
            'coordinators': peers,
            'count': len(peers)
        }
    
    def _handle_get_file_locations(self, request: dict) -> dict:
        """Devuelve los nodos donde está almacenado un archivo"""
        file_name = request.get('file_name')
        
        if not file_name:
            return {'status': 'error', 'message': 'Missing file_name'}
        
        # Intentar obtener ubicaciones directas
        node_ids = self.registry.get_file_locations(file_name)
        
        # Si no hay resultados, quizás el cliente envió el nombre encriptado: mapearlo
        if not node_ids:
            mapped = self._map_encrypted_to_original(file_name)
            if mapped:
                node_ids = self.registry.get_file_locations(mapped) or []
                file_name = mapped  # devolver el nombre original en la respuesta
        
        nodes = []
        for node_id in node_ids:
            addr = self.registry.resolve(node_id)
            if addr:
                nodes.append({
                    'node_id': node_id,
                    'host': addr[0],
                    'port': addr[1]
                })
        
        return {
            'status': 'success',
            'file_name': file_name,
            'nodes': nodes,
            'count': len(nodes)
        }
    
    def _handle_list(self, request: dict) -> dict:
        """
        Lista todos los archivos indexados en el sistema.
        Compatible con la interfaz del cliente GUI.
        """
        try:
            # Limpiar posibles entradas encriptadas antes de listar para evitar duplicados
            try:
                self._cleanup_encrypted_entries()
            except Exception:
                pass

            # Obtener todos los archivos del registro (normalizados)
            all_files = self.registry.get_all_files()
            
            files = []
            for file_name, node_ids in all_files.items():
                files.append({
                    'name': file_name,
                    'replicas': len(node_ids),
                    'nodes': list(node_ids)
                })
            
            return {
                'status': 'success',
                'files': files,
                'count': len(files)
            }
        except Exception as e:
            self.logger.error(f"Error en list: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _handle_download(self, request: dict) -> dict:
        """
        Descarga un archivo del sistema distribuido.

        Coordina petición usando nombres cifrados y descifra contenido recibido.
        """
        import base64
        
        file_id = request.get('file_id') or request.get('file_name')
        
        if not file_id:
            return {'status': 'error', 'message': 'Missing file_id'}
        
        # Obtener nodos que tienen el archivo (registro usa el nombre original)
        node_ids = self.registry.get_file_locations(file_id)
        
        if not node_ids:
            return {'status': 'error', 'message': f'File not found: {file_id}'}
        
        # Nombre cifrado determinístico que el nodo debe tener
        encrypted_name = self._encrypt_filename(file_id)
        
        # Intentar descargar de cada nodo hasta tener éxito
        for node_id in node_ids:
            addr = self.registry.resolve(node_id)
            if not addr:
                continue
            
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(10)
                    sock.connect((addr[0], addr[1]))
                    
                    # Pedir al nodo de procesamiento el archivo usando el nombre cifrado
                    download_request = {
                        'action': 'get_file',
                        'file_name': encrypted_name,
                        'encrypted_by_coord': True
                    }
                    
                    self._send_to_socket(sock, download_request)
                    response = self._receive_from_socket(sock)
                    
                    if response and response.get('status') == 'success':
                        enc_content = response.get('file_content')
                        if not enc_content:
                            continue
                        # Descifrar usando la clave maestra (mismo esquema usado al almacenar)
                        decrypted = self._decrypt_bytes(enc_content)
                        if decrypted is None:
                            # si no pudo descifrar, seguir intentando con otros nodos
                            continue
                        b64content = base64.b64encode(decrypted).decode()
                        return {
                            'status': 'success',
                            'file_name': file_id,
                            'file_content': b64content,
                            'file_size': len(decrypted)
                        }
                        
            except Exception as e:
                self.logger.debug(f"Error descargando de {node_id}: {e}")
                continue
        
        return {'status': 'error', 'message': f'Could not download file from any node: {file_id}'}

    def _handle_get_peers(self, request: dict, address: tuple) -> dict:
        """Para compatibilidad con el sistema de discovery"""
        # Registrar el nodo que pregunta si es un processing node
        from_node = request.get('from_node')
        from_host = request.get('from_host')
        from_port = request.get('from_port', 5001)
        from_type = request.get('from_type', 'processing')
        
        if from_node and from_host and from_type == 'processing':
            self.registry.register_node(from_node, from_host, from_port)
        
        # Devolver lista de nodos conocidos
        nodes = self.registry.get_all_nodes()
        
        return {
            'status': 'success',
            'node_id': self.coordinator_id,
            'node_type': 'coordinator',
            'peers': [n.to_dict() for n in nodes]
        }
    
    def _heartbeat_loop(self):
        """Verifica periódicamente la salud de los nodos de procesamiento"""
        while self.active:
            time.sleep(self.HEARTBEAT_INTERVAL)
            
            # Solo el líder gestiona la salud activa de los nodos
            if not self.cluster.is_leader():
                continue

            nodes = self.registry.get_all_nodes()
            current_time = time.time()
            dead_nodes = []
            
            for node in nodes:
                # Verificar si el nodo ha expirado
                if (current_time - node.last_seen) > self.NODE_TIMEOUT:
                    # Verificar con un health check directo
                    if not self._check_node_health(node):
                        dead_nodes.append(node)
            
            # Procesar nodos caídos
            for node in dead_nodes:
                self._handle_node_failure(node)
    
    def _handle_node_failure(self, node: NodeInfo):
        """
        Maneja la caída de un nodo de procesamiento.
        
        1. Elimina el nodo del registro
        2. Identifica archivos que quedaron bajo el factor de replicación
        3. Dispara re-replicación URGENTE de esos archivos
        """
        node_id = node.node_id
        self.logger.warning(f"💀 Nodo de procesamiento perdido: {node_id}")
        
        # Obtener archivos que estaban en este nodo ANTES de eliminarlo
        affected_files = list(node.files) if node.files else []
        
        # Eliminar nodo del registro
        self.registry.unregister_node(node_id)
        self.dns.unregister_node(node_id)
        
        # Verificar qué archivos necesitan re-replicación urgente
        urgent_files = []
        for file_name in affected_files:
            current_locations = self.registry.get_file_locations(file_name)
            if len(current_locations) < self.REPLICATION_FACTOR:
                urgent_files.append((file_name, len(current_locations)))
        
        if urgent_files:
            self.logger.warning(
                f"⚠️ {len(urgent_files)} archivos necesitan re-replicación URGENTE"
            )
            # Disparar re-replicación en paralelo
            self._urgent_replication(urgent_files)
    
    def _urgent_replication(self, files_to_replicate: List[tuple]):
        """
        Re-replica archivos de forma urgente después de la caída de un nodo.
        
        Args:
            files_to_replicate: Lista de (file_name, current_replica_count)
        """
        threads = []
        
        for file_name, current_count in files_to_replicate:
            t = threading.Thread(
                target=self._request_replication,
                args=(file_name, current_count),
                daemon=True
            )
            t.start()
            threads.append(t)
        
        # Esperar que termine la re-replicación (con timeout)
        for t in threads:
            t.join(timeout=30)
        
        self.logger.info(f"✅ Re-replicación urgente completada para {len(files_to_replicate)} archivos")
    
    def _replication_check_loop(self):
        """Verifica periódicamente que los archivos tengan suficientes réplicas"""
        while self.active:
            time.sleep(5)  # Cada 5 segundos (más rápido para pruebas)
            
            # Solo el líder gestiona la replicación
            if not self.cluster.is_leader():
                continue

            files_needing_replication = self.registry.get_files_needing_replication()
            
            if files_needing_replication:
                self.logger.info(f"🔄 {len(files_needing_replication)} archivos necesitan más réplicas")
                
                for file_name, current_replicas in files_needing_replication:
                    self._request_replication(file_name, current_replicas)
    
    def _request_replication(self, file_name: str, current_replicas: int):
        """Solicita replicación adicional de un archivo"""
        # Obtener nodos donde ya está el archivo
        current_nodes = self.registry.get_file_locations(file_name)
        if not current_nodes:
            return
        
        # Obtener nodos candidatos para replicar
        needed = self.REPLICATION_FACTOR - current_replicas
        all_nodes = self.registry.get_active_nodes(max_age_seconds=self.NODE_TIMEOUT)
        
        candidates = [n for n in all_nodes if n.node_id not in current_nodes]
        candidates.sort(key=lambda n: n.load)  # Menos cargados primero
        
        if not candidates:
            return
        
        # Seleccionar nodo fuente y destinos
        source_node_id = current_nodes[0]
        source = self.registry.lookup(source_node_id)
        
        if not source:
            return
        
        for target in candidates[:needed]:
            self._trigger_replication(file_name, source, target)
    
    def _trigger_replication(self, file_name: str, source: NodeInfo, target: NodeInfo):
        """Solicita a un nodo que replique un archivo a otro nodo"""
        # Verificar si ya está en progreso
        with self._replication_lock:
            if file_name not in self._replication_in_progress:
                self._replication_in_progress[file_name] = set()
            
            if target.node_id in self._replication_in_progress[file_name]:
                self.logger.debug(f"⏳ Replicación de '{file_name}' a {target.node_id} ya en progreso")
                return
            
            # Marcar como en progreso
            self._replication_in_progress[file_name].add(target.node_id)
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30)  # Aumentar timeout para archivos grandes
                sock.connect((source.host, source.port))
                
                # Usar nombre cifrado determinístico para que el nodo fuente encuentre el fichero
                encrypted_name = self._encrypt_filename(file_name)
                
                request = {
                    'action': 'replicate_to',
                    'file_name': encrypted_name,
                    'target_host': target.host,
                    'target_port': target.port,
                    'target_node_id': target.node_id,
                    # opcional: indicar original para trazabilidad
                    'original_file_name': file_name,
                    'encrypted_by_coord': True
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                self.logger.info(f"📤 Solicitada replicación de '{file_name}': {source.node_id} -> {target.node_id}")
                self.stats['replications_requested'] += 1
                
                # Esperar respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = sock.recv(msg_len)
                    response = json.loads(data.decode())
                    
                    if response.get('status') == 'success':
                        self.logger.info(f"✅ Replicación exitosa de '{file_name}' a {target.node_id}")
                        self.stats['replications_succeeded'] += 1
                        # La confirmación final vendrá cuando el target notifique con file_stored
                    else:
                        error_msg = response.get('message', 'Unknown error')
                        self.logger.error(f"❌ Replicación fallida de '{file_name}' a {target.node_id}: {error_msg}")
                        self.stats['replications_failed'] += 1
                        # Remover de en progreso para permitir reintento
                        with self._replication_lock:
                            self._replication_in_progress[file_name].discard(target.node_id)
                else:
                    self.logger.warning(f"⚠️ Sin respuesta de {source.node_id} para replicación de '{file_name}'")
                    self.stats['replications_failed'] += 1
                    with self._replication_lock:
                        self._replication_in_progress[file_name].discard(target.node_id)
                
        except Exception as e:
            self.logger.error(f"❌ Error solicitando replicación de '{file_name}' ({source.node_id} -> {target.node_id}): {e}")
            self.stats['replications_failed'] += 1
            # Remover de en progreso para permitir reintento
            with self._replication_lock:
                if file_name in self._replication_in_progress:
                    self._replication_in_progress[file_name].discard(target.node_id)
    
    def _check_node_health(self, node: NodeInfo) -> bool:
        """Verifica si un nodo está vivo con un health check TCP"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((node.host, node.port))
                
                request = {'action': 'health'}
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                length_data = sock.recv(8)
                if length_data:
                    self.registry.update_last_seen(node.node_id)
                    return True
        except:
            pass
        return False
    
    def _get_cluster_status(self) -> dict:
        """Obtiene el estado completo del cluster"""
        nodes = self.registry.get_all_nodes()
        active_nodes = self.registry.get_active_nodes(max_age_seconds=self.NODE_TIMEOUT)
        
        uptime = 0
        if self.stats['start_time']:
            uptime = time.time() - self.stats['start_time']
        
        # Obtener estado del cluster de coordinadores (Bully)
        cluster_status = self.cluster.get_cluster_status()
        
        return {
            'status': 'success',
            'coordinator_id': self.coordinator_id,
            'coordinator_host': self.announce_host,
            'coordinator_port': self.port,
            # === Estado del cluster de coordinadores (Bully) ===
            'role': cluster_status.get('role', 'UNKNOWN'),
            'is_leader': self.cluster.is_leader(),
            'current_leader': cluster_status.get('current_leader'),
            'coordinator_peers': cluster_status.get('alive_peers', 0),
            'state_version': cluster_status.get('state_version', 0),
            # === Estado de nodos de procesamiento ===
            'total_processing_nodes': len(nodes),
            'active_processing_nodes': len(active_nodes),
            'replication_factor': self.REPLICATION_FACTOR,
            'quorum_level': self.QUORUM_LEVEL.value,
            'uptime_seconds': uptime,
            'stats': self.stats,
            'total_files': len(self.registry.get_all_file_names()),
            'nodes': [n.to_dict() for n in nodes],
            'registry_stats': self.registry.get_stats(),
            'dns_stats': self.dns.get_stats(),
            'quorum_stats': self.quorum.get_stats()
        }
    
    def assign_task(self, task_type: str, **kwargs) -> Optional[NodeInfo]:
        """
        Asigna una tarea al nodo de procesamiento menos cargado.
        
        Args:
            task_type: Tipo de tarea (search, index, etc.)
            **kwargs: Parámetros adicionales de la tarea
            
        Returns:
            NodeInfo del nodo asignado o None
        """
        node = self.registry.get_least_loaded_node()
        
        if node:
            # Incrementar tareas del nodo
            self.registry.update_node_tasks(node.node_id, node.current_tasks + 1)
            self.logger.debug(f"📋 Tarea '{task_type}' asignada a {node.node_id}")
        
        return node
    
    def release_task(self, node_id: str):
        """Libera una tarea completada de un nodo"""
        node = self.registry.lookup(node_id)
        if node and node.current_tasks > 0:
            self.registry.update_node_tasks(node_id, node.current_tasks - 1)

    # -----------------------
    # CRYPTO HELPERS
    # -----------------------
    def _init_crypto(self):
        """
        Inicializa claves para cifrado. Usa una clave maestra (env COORD_MASTER_KEY)
        o genera una si no está presente. Soporta Fernet si está instalado,
        sino usa un fallback XOR simple.
        """
        env_key = os.environ.get('COORD_MASTER_KEY')
        if env_key:
            try:
                # Esperar base64 urlsafe encoded para Fernet, si viene así
                self._master_key = env_key.encode()
            except Exception:
                self._master_key = env_key.encode()
        else:
            # Generar clave aleatoria de 32 bytes
            self._master_key = secrets.token_bytes(32)

        self._use_fernet = _HAS_CRYPTO
        if self._use_fernet:
            # Nada más: derivaremos claves por nodo cuando haga falta
            self.logger.debug("🔐 Fernet disponible: usando cifrado fuerte")
        else:
            self.logger.warning("⚠️ cryptography no disponible: usando fallback XOR (no seguro)")

    def _derive_key(self, node_id: Optional[str]) -> bytes:
        """
        Deriva una clave simétrica basada en la master_key y el node_id.
        Devuelve una clave urlsafe base64 de 32 bytes apta para Fernet.
        """
        node_bytes = (node_id or "").encode()
        digest = hashlib.sha256(self._master_key + node_bytes).digest()
        return base64.urlsafe_b64encode(digest)

    def _encrypt_payload(self, data: dict, node_id: Optional[str] = None) -> str:
        """Encripta un diccionario y devuelve base64/text para transporte."""
        json_data = json.dumps(data).encode()
        if self._use_fernet:
            key = self._derive_key(node_id)
            f = Fernet(key)
            token = f.encrypt(json_data)
            return token.decode()
        else:
            # Fallback XOR (débil): usar SHA256 como stream key
            key_stream = hashlib.sha256(self._master_key + (node_id or "").encode()).digest()
            xored = bytes([b ^ key_stream[i % len(key_stream)] for i, b in enumerate(json_data)])
            return base64.b64encode(xored).decode()

    def _decrypt_payload(self, token: str, node_id: Optional[str] = None) -> Optional[dict]:
        """Desencripta una cadena y devuelve el dict, o None si falla."""
        try:
            if self._use_fernet:
                key = self._derive_key(node_id)
                f = Fernet(key)
                plain = f.decrypt(token.encode())
            else:
                xored = base64.b64decode(token.encode())
                key_stream = hashlib.sha256(self._master_key + (node_id or "").encode()).digest()
                plain = bytes([b ^ key_stream[i % len(key_stream)] for i, b in enumerate(xored)])
            return json.loads(plain.decode())
        except (InvalidToken, Exception) as e:
            self.logger.debug(f"🔓 Error desencriptando payload (maybe not encrypted): {e}")
            return None

    # -----------------------
    # NUEVOS HELPERS DE CRYPTO (BYTES Y NOMBRE DETERMINÍSTICO)
    # -----------------------
    def _encrypt_bytes(self, data: bytes) -> str:
        """
        Cifra bytes con la clave maestra (misma salida para todos los nodos si se usa Fernet con key derivada sin node_id).
        Devuelve una cadena segura (base64/urlsafe) que puede almacenarse/transmitirse.
        """
        try:
            if self._use_fernet:
                # derivar con node_id=None => clave global
                key = self._derive_key(None)
                f = Fernet(key)
                token = f.encrypt(data)  # bytes
                return token.decode()
            else:
                key_stream = hashlib.sha256(self._master_key).digest()
                xored = bytes([b ^ key_stream[i % len(key_stream)] for i, b in enumerate(data)])
                return base64.b64encode(xored).decode()
        except Exception as e:
            self.logger.debug(f"Error encrypting bytes: {e}")
            return None

    def _decrypt_bytes(self, token: str) -> Optional[bytes]:
        """Descifra la cadena generada por _encrypt_bytes y devuelve bytes o None."""
        try:
            if self._use_fernet:
                key = self._derive_key(None)
                f = Fernet(key)
                plain = f.decrypt(token.encode())
                return plain
            else:
                xored = base64.b64decode(token.encode())
                key_stream = hashlib.sha256(self._master_key).digest()
                plain = bytes([b ^ key_stream[i % len(key_stream)] for i, b in enumerate(xored)])
                return plain
        except Exception as e:
            self.logger.debug(f"Error decrypting bytes: {e}")
            return None

    def _encrypt_filename(self, file_name: str) -> str:
        """
        Convierte un nombre de archivo en una representación cifrada/determinística
        (HMAC-SHA256 + urlsafe base64). No es necesario revertirla en el nodo,
        el coordinador volverá a calcularla para búsquedas/descargas.
        """
        try:
            hm = hmac.new(self._master_key, file_name.encode(), hashlib.sha256).digest()
            return base64.urlsafe_b64encode(hm).decode().rstrip('=')
        except Exception as e:
            self.logger.debug(f"Error encrypting filename: {e}")
            # Fallback simple
            return base64.urlsafe_b64encode(file_name.encode()).decode().rstrip('=')
    
    def _map_encrypted_to_original(self, encrypted_name: str) -> Optional[str]:
        """
        Dado un nombre cifrado (determinístico) intenta encontrar el nombre
        original en nuestro registro comparando _encrypt_filename(original) == encrypted_name.
        Retorna el nombre original o None si no se encuentra.
        """
        try:
            all_files = self.registry.get_all_file_names()
            for orig in all_files:
                try:
                    if self._encrypt_filename(orig) == encrypted_name:
                        return orig
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _cleanup_encrypted_entries(self):
        """
        Fusiona en el registry las keys que son nombres "encriptados" y que
        correspondan a un nombre original conocido. Mueve las ubicaciones de
        nodos desde la key encriptada al nombre original y elimina la entrada
        encriptada para evitar duplicados visibles al usuario.
        """
        try:
            # Construir conjunto de nombres actuales (posibles originales)
            originals = set(self.registry.get_all_file_names())
            # Mapear encrypted_name -> original
            enc_to_orig = {}
            for orig in originals:
                try:
                    enc = self._encrypt_filename(orig)
                    enc_to_orig[enc] = orig
                except Exception:
                    continue

            # Revisar las keys actuales en file_locations
            keys = list(self.registry.file_locations.keys())
            for key in keys:
                # Si la key es una representación encriptada que corresponde a un original
                if key in enc_to_orig:
                    orig = enc_to_orig[key]
                    # Mover nodos de 'key' a 'orig'
                    node_set = set(self.registry.file_locations.get(key, []))
                    if node_set:
                        for node_id in node_set:
                            # Registrar ubicación bajo el nombre original (idempotente)
                            self.registry.register_file_location(orig, node_id)
                            # Además eliminar el nombre encriptado de la lista de archivos del nodo si existe
                            node_obj = self.registry.lookup(node_id)
                            if node_obj and key in getattr(node_obj, 'files', set()):
                                try:
                                    node_obj.files.discard(key)
                                except Exception:
                                    pass
                    # Finalmente eliminar la entrada encriptada del registry interno
                    try:
                        del self.registry.file_locations[key]
                    except Exception:
                        pass
        except Exception as e:
            self.logger.debug(f"Error cleaning encrypted entries: {e}")
