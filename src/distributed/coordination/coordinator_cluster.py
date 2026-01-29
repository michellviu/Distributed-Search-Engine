"""
Cluster de Coordinadores con replicación de estado.

Permite tener múltiples coordinadores donde:
- Uno es el líder activo que procesa requests
- Los demás son réplicas que mantienen el estado sincronizado
- Si el líder cae, una réplica toma el control usando el algoritmo BULLY

Algoritmo Bully para elección de líder:
1. Cuando un nodo P detecta que el líder cayó, inicia una elección
2. P envía mensaje ELECTION a todos los nodos con ID mayor que P
3. Si P recibe respuesta OK de algún nodo con mayor ID, espera
4. Si P no recibe respuesta OK, P se declara líder
5. El nuevo líder envía COORDINATOR a todos los nodos

El estado replicado incluye:
- Registro de nodos de procesamiento
- Índice de ubicación de archivos
"""
import json
import socket
import threading
import time
import logging
import random
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CoordinatorRole(Enum):
    """Rol del coordinador en el cluster"""
    LEADER = "LEADER"       # Procesa requests activamente
    FOLLOWER = "FOLLOWER"   # Replica estado del líder
    CANDIDATE = "CANDIDATE" # En proceso de elección


class BullyMessage(Enum):
    """Tipos de mensaje del algoritmo Bully"""
    ELECTION = "ELECTION"       # Iniciar elección
    OK = "OK"                   # Respuesta a ELECTION (hay alguien con mayor ID)
    COORDINATOR = "COORDINATOR" # Anuncio de nuevo líder


@dataclass
class CoordinatorPeer:
    """Información de un coordinador peer"""
    coordinator_id: str
    host: str
    port: int
    role: CoordinatorRole = CoordinatorRole.FOLLOWER
    last_seen: float = 0.0
    is_alive: bool = True
    
    def to_dict(self) -> dict:
        return {
            'coordinator_id': self.coordinator_id,
            'host': self.host,
            'port': self.port,
            'role': self.role.value,
            'last_seen': self.last_seen,
            'is_alive': self.is_alive
        }


@dataclass
class StateSnapshot:
    """Snapshot del estado del coordinador para replicación"""
    version: int
    timestamp: float
    nodes: Dict[str, dict]  # node_id -> node_info
    file_locations: Dict[str, List[str]]  # file_name -> list of node_ids
    
    def to_dict(self) -> dict:
        return {
            'version': self.version,
            'timestamp': self.timestamp,
            'nodes': self.nodes,
            'file_locations': self.file_locations
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StateSnapshot':
        return cls(
            version=data['version'],
            timestamp=data['timestamp'],
            nodes=data['nodes'],
            file_locations=data['file_locations']
        )


class CoordinatorCluster:
    """
    Gestor de cluster de coordinadores con algoritmo BULLY.
    
    Algoritmo Bully:
    - El nodo con MAYOR ID es el líder
    - Cuando se detecta caída del líder, se inicia elección
    - Mensajes: ELECTION, OK, COORDINATOR
    
    Características:
    - Elección de líder usando algoritmo Bully
    - Replicación síncrona del estado al escribir
    - Heartbeats entre coordinadores
    - Failover automático cuando cae el líder
    """
    
    HEARTBEAT_INTERVAL = 3  # Segundos entre heartbeats
    LEADER_TIMEOUT = 10  # Segundos sin contacto para considerar líder muerto
    ELECTION_TIMEOUT = 5  # Segundos esperando respuestas OK
    COORDINATOR_TIMEOUT = 8  # Segundos esperando mensaje COORDINATOR
    STATE_SYNC_INTERVAL = 5  # Segundos entre sincronizaciones de estado
    
    def __init__(self, 
                 coordinator_id: str, 
                 host: str, 
                 port: int,
                 peer_addresses: List[str] = None,
                 state_file: str = None):
        """
        Args:
            coordinator_id: ID único de este coordinador
            host: IP de este coordinador
            port: Puerto de este coordinador
            peer_addresses: Lista de "host:port" de otros coordinadores
            state_file: Archivo para persistir estado (opcional)
        """
        self.coordinator_id = coordinator_id
        self.host = host
        self.port = port
        self.state_file = state_file
        
        self.logger = logging.getLogger(f"CoordCluster-{coordinator_id}")
        
        # Estado del cluster
        self.role = CoordinatorRole.FOLLOWER
        self.current_leader: Optional[str] = None
        self.peers: Dict[str, CoordinatorPeer] = {}
        
        # Estado replicado
        self.state_version = 0
        self._state_lock = threading.RLock()
        
        # Control
        self.active = False
        self._election_in_progress = False
        
        # Callback para reconciliación cuando se acepta nuevo líder
        self._on_new_leader_callback = None
        
        # Parsear peers iniciales
        if peer_addresses:
            for addr in peer_addresses:
                self._add_peer_from_address(addr)
    
    def set_on_new_leader_callback(self, callback):
        """Configura callback a llamar cuando se acepta un nuevo líder"""
        self._on_new_leader_callback = callback
    
    def add_peer(self, coordinator_id: str, host: str, port: int):
        """
        Añade un nuevo peer al cluster dinámicamente.
        
        Args:
            coordinator_id: ID del nuevo coordinador
            host: Hostname o IP
            port: Puerto
        """
        if coordinator_id == self.coordinator_id:
            return

        if coordinator_id not in self.peers:
            self.logger.info(f"🆕 Nuevo peer descubierto: {coordinator_id} ({host}:{port})")
            self.peers[coordinator_id] = CoordinatorPeer(
                coordinator_id=coordinator_id,
                host=host,
                port=port,
                is_alive=True,
                last_seen=time.time()
            )
            # Disparar una nueva elección cuando se añade un nuevo coordinador
            # para asegurarnos de que el cluster reevalúe quién debe ser líder.
            if self.active and not self._election_in_progress:
                self.logger.info(f"🔔 Nuevo peer {coordinator_id} añadido — lanzando elección para reevaluar líder")
                threading.Thread(target=self._start_election, daemon=True).start()
        else:
            # Actualizar info si ya existe
            peer = self.peers[coordinator_id]
            if peer.host != host or peer.port != port:
                self.logger.info(f"🔄 Actualizando info peer {coordinator_id}: {peer.host}:{peer.port} -> {host}:{port}")
                peer.host = host
                peer.port = port
                peer.is_alive = True
                peer.last_seen = time.time()
                # Si cambia la información de un peer conocido, reevalúa liderazgo
                if self.active and not self._election_in_progress:
                    threading.Thread(target=self._start_election, daemon=True).start()

    def _add_peer_from_address(self, address: str):
        """Añade un peer desde una dirección 'host:port'"""
        try:
            parts = address.split(':')
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 5000
            peer_id = f"coord-{host}-{port}"
            
            if peer_id != self.coordinator_id:
                self.peers[peer_id] = CoordinatorPeer(
                    coordinator_id=peer_id,
                    host=host,
                    port=port
                )
        except Exception as e:
            self.logger.warning(f"Error parseando peer address {address}: {e}")
    
    def start(self):
        """Inicia el cluster manager"""
        self.active = True
        self.logger.info(f"🎯 Iniciando cluster manager para {self.coordinator_id}")
        
        # Cargar estado persistido si existe
        self._load_state()
        
        # Descubrir IDs reales de los peers antes de iniciar elección
        self._discover_peer_ids()
        
        # Obtener lista completa de coordinadores de un peer conocido
        self._initial_peer_discovery()
        
        # Iniciar heartbeat a otros coordinadores
        threading.Thread(target=self._peer_heartbeat_loop, daemon=True).start()
        
        # Iniciar verificación de líder
        threading.Thread(target=self._leader_check_loop, daemon=True).start()
        
        # Iniciar descubrimiento de peers
        threading.Thread(target=self._discover_peers_loop, daemon=True).start()
        
        # Intentar elección inicial después de un delay para que los peers estén listos
        threading.Timer(3.0, self._start_election).start()
    
    def _discover_peer_ids(self):
        """Descubre los IDs reales de los peers haciendo un heartbeat inicial"""
        self.logger.info(f"🔍 Descubriendo IDs reales de {len(self.peers)} peers...")
        
        for peer_id, peer in list(self.peers.items()):
            try:
                self._check_peer_health(peer)
            except:
                pass
        
        self.logger.info(f"🔍 Peers actuales: {list(self.peers.keys())}")
    
    def _initial_peer_discovery(self):
        """Descubre la lista completa de coordinadores consultando a un peer conocido"""
        if not self.peers:
            return
        
        # Tomar el primer peer conocido
        peer = next(iter(self.peers.values()))
        try:
            response = self._send_request_to_peer(peer, {'action': 'get_coordinators'})
            if response and response.get('status') == 'success':
                coords = response.get('coordinators', [])
                for c in coords:
                    c_id = c.get('coordinator_id')
                    c_host = c.get('host')
                    c_port = c.get('port')
                    if c_id != self.coordinator_id and c_id not in self.peers:
                        self.add_peer(c_id, c_host, c_port)
                        self.logger.info(f"🆕 Descubierto peer inicial: {c_id} ({c_host}:{c_port})")
        except Exception as e:
            self.logger.debug(f"Error en descubrimiento inicial de peers: {e}")
    
    def stop(self):
        """Detiene el cluster manager"""
        self.active = False
        self._save_state()
        self.logger.info("👋 Cluster manager detenido")
    
    def is_leader(self) -> bool:
        """Retorna True si este coordinador es el líder"""
        return self.role == CoordinatorRole.LEADER
    
    def get_leader_address(self) -> Optional[tuple]:
        """Retorna (host, port) del líder actual"""
        if self.role == CoordinatorRole.LEADER:
            return (self.host, self.port)
        
        if self.current_leader and self.current_leader in self.peers:
            peer = self.peers[self.current_leader]
            return (peer.host, peer.port)
        
        return None
    
    def replicate_state(self, nodes: dict, file_locations: dict):
        """
        Replica el estado a todos los followers.
        
        Args:
            nodes: Diccionario de nodos registrados
            file_locations: Diccionario de ubicaciones de archivos
        """
        if not self.is_leader():
            return
        
        with self._state_lock:
            self.state_version += 1
            snapshot = StateSnapshot(
                version=self.state_version,
                timestamp=time.time(),
                nodes=nodes,
                file_locations=file_locations
            )
        
        # Enviar a todos los peers en paralelo
        threads = []
        for peer_id, peer in self.peers.items():
            if peer.is_alive:
                t = threading.Thread(
                    target=self._send_state_to_peer,
                    args=(peer, snapshot)
                )
                t.start()
                threads.append(t)
        
        # Esperar confirmación (con timeout corto)
        for t in threads:
            t.join(timeout=2.0)
        
        # Persistir estado
        self._save_state()
    
    def _send_request_to_peer(self, peer: CoordinatorPeer, request: dict) -> Optional[dict]:
        """Envía una request a un peer y retorna la response"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((peer.host, peer.port))
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = sock.recv(msg_len)
                    response = json.loads(data.decode())
                    return response
                
        except Exception as e:
            self.logger.debug(f"Error sending request to {peer.coordinator_id}: {e}")
        
        return None
    
    def handle_state_replication(self, from_coordinator: str, state_data: dict) -> bool:
        """
        Recibe estado replicado del líder.
        
        Returns:
            True si se aplicó el estado
        """
        if self.is_leader():
            return False  # Líder no recibe replicación
        
        with self._state_lock:
            snapshot = StateSnapshot.from_dict(state_data)
            
            if snapshot.version > self.state_version:
                self.state_version = snapshot.version
                self.logger.debug(
                    f"📥 Estado recibido de {from_coordinator} (v{snapshot.version})"
                )
                return True
        
        return False
    
    def _peer_heartbeat_loop(self):
        """Envía heartbeats a otros coordinadores"""
        while self.active:
            time.sleep(self.HEARTBEAT_INTERVAL)
            
            for peer_id, peer in list(self.peers.items()):
                alive = self._check_peer_health(peer)
                peer.is_alive = alive
                if alive:
                    peer.last_seen = time.time()
    
    def _check_peer_health(self, peer: CoordinatorPeer) -> bool:
        """Verifica si un peer está vivo y actualiza su información"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((peer.host, peer.port))
                
                request = {
                    'action': 'coordinator_heartbeat',
                    'from_coordinator': self.coordinator_id,
                    'from_host': self.host,
                    'from_port': self.port,
                    'role': self.role.value
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = sock.recv(msg_len)
                    response = json.loads(data.decode())
                    
                    # Actualizar rol del peer
                    peer_role = response.get('role', 'FOLLOWER')
                    peer.role = CoordinatorRole(peer_role)
                    
                    # Actualizar el ID real del peer si es diferente
                    real_id = response.get('coordinator_id')
                    if real_id and real_id != peer.coordinator_id:
                        self.logger.info(f"🔄 Actualizando ID del peer: {peer.coordinator_id} -> {real_id}")
                        old_id = peer.coordinator_id
                        peer.coordinator_id = real_id
                        # Actualizar la referencia en el diccionario de peers
                        if old_id in self.peers:
                            del self.peers[old_id]
                            self.peers[real_id] = peer
                    
                    return True
        except:
            pass
        return False
    
    def _leader_check_loop(self):
        """Verifica periódicamente si el líder está vivo"""
        while self.active:
            time.sleep(self.HEARTBEAT_INTERVAL)
            
            if self.role == CoordinatorRole.LEADER:
                continue  # Somos el líder
            
            # Verificar si el líder está vivo
            if self.current_leader:
                if self.current_leader in self.peers:
                    peer = self.peers[self.current_leader]
                    if not peer.is_alive or (time.time() - peer.last_seen) > self.LEADER_TIMEOUT:
                        self.logger.warning(f"⚠️ Líder {self.current_leader} no responde")
                        self._start_election()
    
    def _start_election(self):
        """
        Inicia proceso de elección de líder usando algoritmo BULLY modificado.
        
        Para asegurar que todos los coordinadores participen, enviamos ELECTION a todos los peers conocidos.
        El nodo con el ID más alto será el líder.
        
        Algoritmo:
        1. Enviar ELECTION a todos los peers conocidos
        2. Si recibe OK de alguno (hay alguien con mayor ID), esperar COORDINATOR
        3. Si no recibe OK (timeout), declararse líder y enviar COORDINATOR
        """
        if self._election_in_progress:
            return
        
        self._election_in_progress = True
        self.role = CoordinatorRole.CANDIDATE
        self.logger.info("🗳️ [BULLY] Iniciando elección de líder entre todos los peers conocidos...")
        
        try:
            # Paso 1: Enviar ELECTION a TODOS los peers conocidos (no solo higher)
            known_peers = [
                peer for peer in self.peers.values()
                if peer.is_alive
            ]
            
            if not known_peers:
                # No hay peers conocidos, somos el líder por defecto
                self._become_leader()
                return
            
            # Enviar ELECTION a todos los peers conocidos
            self.logger.info(f"🗳️ [BULLY] Enviando ELECTION a {len(known_peers)} peers conocidos")
            received_ok = False
            ok_lock = threading.Lock()
            
            def send_election(peer: CoordinatorPeer):
                nonlocal received_ok
                try:
                    response = self._send_bully_message(
                        peer, 
                        BullyMessage.ELECTION,
                        timeout=self.ELECTION_TIMEOUT
                    )
                    if response and response.get('message_type') == BullyMessage.OK.value:
                        with ok_lock:
                            received_ok = True
                        self.logger.debug(f"🗳️ [BULLY] Recibido OK de {peer.coordinator_id}")
                except Exception as e:
                    self.logger.debug(f"🗳️ [BULLY] No response from {peer.coordinator_id}: {e}")
            
            # Enviar en paralelo
            threads = []
            for peer in known_peers:
                t = threading.Thread(target=send_election, args=(peer,))
                t.start()
                threads.append(t)
            
            # Esperar respuestas (con timeout)
            for t in threads:
                t.join(timeout=self.ELECTION_TIMEOUT)
            
            # Paso 2: Evaluar resultados
            if received_ok:
                # Alguien con mayor ID respondió, esperar COORDINATOR
                self.logger.info("🗳️ [BULLY] Recibido OK, esperando COORDINATOR...")
                self._wait_for_coordinator()
            else:
                # Nadie respondió, somos el líder
                self.logger.info("🗳️ [BULLY] Sin respuestas OK, soy el líder")
                self._become_leader()
                
        finally:
            self._election_in_progress = False
    
    def _become_leader(self):
        """Se declara líder y anuncia a todos los peers"""
        self.role = CoordinatorRole.LEADER
        self.current_leader = self.coordinator_id
        self.logger.info(f"👑 [BULLY] Este nodo es ahora el LÍDER: {self.coordinator_id}")
        
        # Enviar COORDINATOR a TODOS los peers
        self._announce_leadership()
    
    def _wait_for_coordinator(self):
        """
        Espera mensaje COORDINATOR de un nodo con mayor ID.
        Si no llega en el timeout, reinicia elección.
        """
        start_time = time.time()
        
        while (time.time() - start_time) < self.COORDINATOR_TIMEOUT:
            if self.role == CoordinatorRole.FOLLOWER and self.current_leader:
                # Ya recibimos COORDINATOR
                return
            time.sleep(0.5)
        
        # Timeout: el nodo con mayor ID no se convirtió en líder
        # Reiniciar elección
        self.logger.warning("🗳️ [BULLY] Timeout esperando COORDINATOR, reiniciando elección")
        self._election_in_progress = False  # Permitir nueva elección
        self._start_election()
    
    def _send_bully_message(
        self, 
        peer: CoordinatorPeer, 
        message_type: BullyMessage,
        timeout: float = 3.0
    ) -> Optional[dict]:
        """Envía un mensaje del algoritmo Bully a un peer"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((peer.host, peer.port))
                
                request = {
                    'action': 'bully_message',
                    'message_type': message_type.value,
                    'from_coordinator': self.coordinator_id,
                    'from_host': self.host,
                    'from_port': self.port
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = sock.recv(msg_len)
                    return json.loads(data.decode())
        except:
            pass
        return None
    
    def handle_bully_message(self, message_type: str, from_id: str, from_host: str, from_port: int) -> dict:
        """
        Procesa un mensaje del algoritmo Bully.
        """
        # Auto-registro del peer si no lo conocemos (Gossip)
        if from_id and from_host and from_port:
            self.add_peer(from_id, from_host, from_port)

        msg_type = BullyMessage(message_type)
        
        if msg_type == BullyMessage.ELECTION:
            # Alguien está iniciando elección
            # Si el que envía tiene menor ID, responder OK y empezar nuestra propia elección
            # Solo respondemos OK si nosotros tenemos mayor ID que el que inició
            # la elección. En ese caso iniciamos nuestra propia elección para
            # también competir y anunciarnos si corresponde.
            try:
                if self.coordinator_id > from_id:
                    self.logger.info(f"🗳️ [BULLY] Recibido ELECTION de {from_id} (ID menor), respondiendo OK e iniciando elección propia")
                    threading.Thread(target=self._start_election, daemon=True).start()
                    return {
                        'status': 'ok',
                        'message_type': BullyMessage.OK.value,
                        'from_coordinator': self.coordinator_id
                    }
                else:
                    # Si nosotros NO tenemos mayor ID, no respondemos OK; el
                    # iniciador seguirá esperando COORDINATOR de alguien con
                    # mayor ID.
                    self.logger.info(f"🗳️ [BULLY] Recibido ELECTION de {from_id} (ID mayor o igual), no respondo OK")
                    return {'status': 'ok'}
            except Exception:
                return {'status': 'ok'}
        
        elif msg_type == BullyMessage.COORDINATOR:
            # Nuevo líder anunciado
            self.logger.info(f"👑 [BULLY] Recibido COORDINATOR de {from_id}")
            self._accept_new_leader(from_id, from_host, from_port)
            
            return {
                'status': 'ok',
                'message_type': 'ACK',
                'from_coordinator': self.coordinator_id
            }
        
        return {'status': 'ok'}
    
    def _accept_new_leader(self, leader_id: str, leader_host: str, leader_port: int):
        """Acepta un nuevo líder anunciado vía COORDINATOR"""
        was_candidate_or_leader = self.role in (CoordinatorRole.CANDIDATE, CoordinatorRole.LEADER)
        
        self.current_leader = leader_id
        self.role = CoordinatorRole.FOLLOWER
        self._election_in_progress = False
        
        # Asegurar que el líder está en nuestra lista de peers
        if leader_id not in self.peers:
            self.peers[leader_id] = CoordinatorPeer(
                coordinator_id=leader_id,
                host=leader_host,
                port=leader_port,
                role=CoordinatorRole.LEADER,
                is_alive=True,
                last_seen=time.time()
            )
        else:
            self.peers[leader_id].role = CoordinatorRole.LEADER
            self.peers[leader_id].is_alive = True
            self.peers[leader_id].last_seen = time.time()
        
        self.logger.info(f"👑 [BULLY] Nuevo líder aceptado: {leader_id}")
        
        # Llamar callback de reconciliación si estábamos desconectados
        if was_candidate_or_leader and self._on_new_leader_callback:
            self.logger.info(f"🔄 [BULLY] Solicitando reconciliación con nuevo líder...")
            threading.Thread(
                target=self._on_new_leader_callback,
                args=(leader_id, leader_host, leader_port),
                daemon=True
            ).start()
    
    def _announce_leadership(self):
        """
        Anuncia a TODOS los peers que somos el líder.
        Envía mensaje COORDINATOR del algoritmo Bully.
        """
        self.logger.info(f"📢 [BULLY] Anunciando liderazgo a {len(self.peers)} peers")
        
        def send_coordinator(peer: CoordinatorPeer):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(3)
                    sock.connect((peer.host, peer.port))
                    
                    request = {
                        'action': 'bully_message',
                        'message_type': BullyMessage.COORDINATOR.value,
                        'from_coordinator': self.coordinator_id,
                        'from_host': self.host,
                        'from_port': self.port
                    }
                    
                    req_json = json.dumps(request)
                    sock.sendall(f"{len(req_json):<8}".encode())
                    sock.sendall(req_json.encode())
                    
                    self.logger.debug(f"📢 [BULLY] COORDINATOR enviado a {peer.coordinator_id}")
            except Exception as e:
                self.logger.debug(f"📢 [BULLY] Error enviando COORDINATOR a {peer.coordinator_id}: {e}")
        
        # Enviar a todos en paralelo
        threads = []
        for peer_id, peer in self.peers.items():
            t = threading.Thread(target=send_coordinator, args=(peer,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join(timeout=3)
    
    def handle_leader_announcement(self, leader_id: str, leader_host: str, leader_port: int):
        """
        Recibe anuncio de nuevo líder (compatibilidad con mensajes legacy).
        Redirige a _accept_new_leader.
        """
        self._accept_new_leader(leader_id, leader_host, leader_port)
    
    def _save_state(self):
        """Persiste el estado a disco"""
        if not self.state_file:
            return
        
        try:
            state = {
                'coordinator_id': self.coordinator_id,
                'state_version': self.state_version,
                'peers': {pid: p.to_dict() for pid, p in self.peers.items()}
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error guardando estado: {e}")
    
    def _load_state(self):
        """Carga el estado desde disco"""
        if not self.state_file or not Path(self.state_file).exists():
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            self.state_version = state.get('state_version', 0)
            self.logger.info(f"📂 Estado cargado desde disco (v{self.state_version})")
            
        except Exception as e:
            self.logger.error(f"Error cargando estado: {e}")
    
    def _discover_peers_loop(self):
        """Descubre nuevos peers consultando a los conocidos (gossip protocol)"""
        while self.active:
            time.sleep(10)  # Cada 10 segundos
            
            if self.peers:
                # Elegir un peer aleatorio para consultar
                peer = random.choice(list(self.peers.values()))
                if peer.is_alive:
                    try:
                        # Consultar lista de coordinadores
                        response = self._send_request_to_peer(peer, {'action': 'get_coordinators'})
                        if response and response.get('status') == 'success':
                            coords = response.get('coordinators', [])
                            for c in coords:
                                c_id = c.get('coordinator_id')
                                c_host = c.get('host')
                                c_port = c.get('port')
                                if c_id != self.coordinator_id and c_id not in self.peers:
                                    self.add_peer(c_id, c_host, c_port)
                                    self.logger.debug(f"🆕 Descubierto peer via gossip: {c_id} ({c_host}:{c_port})")
                    except Exception as e:
                        self.logger.debug(f"Error discovering peers from {peer.coordinator_id}: {e}")
    
    def get_cluster_status(self) -> dict:
        """Obtiene estado del cluster de coordinadores"""
        return {
            'coordinator_id': self.coordinator_id,
            'role': self.role.value,
            'current_leader': self.current_leader,
            'state_version': self.state_version,
            'peers': {pid: p.to_dict() for pid, p in self.peers.items()},
            'alive_peers': sum(1 for p in self.peers.values() if p.is_alive)
        }
