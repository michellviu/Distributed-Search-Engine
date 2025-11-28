# src/distributed/discovery/multicast_discovery.py
"""
Descubrimiento de nodos usando UDP Multicast.
Funciona en redes overlay de Docker Swarm (a diferencia de broadcast).
"""
import socket
import struct
import json
import threading
import time
import logging
from typing import Dict, Callable, List, Optional
from dataclasses import dataclass


@dataclass
class NodeInfo:
    """Información de un nodo"""
    node_id: str
    host: str
    port: int
    node_type: str  # 'peer' o 'coordinator'
    last_seen: float
    load: int = 0


class MulticastDiscovery:
    """
    Descubrimiento de nodos usando UDP Multicast.
    
    Multicast funciona en redes overlay de Docker porque usa un grupo
    de IPs especiales (224.0.0.0 - 239.255.255.255) que son ruteadas
    a todos los miembros del grupo.
    """
    
    # Dirección multicast (rango administrativo local)
    MULTICAST_GROUP = '239.255.255.250'
    MULTICAST_PORT = 5007
    
    ANNOUNCE_INTERVAL = 3   # segundos entre anuncios
    NODE_TIMEOUT = 15       # segundos antes de considerar nodo muerto
    
    def __init__(self, node_id: str, node_type: str, 
                 host: str, port: int,
                 seed_nodes: List[tuple] = None):
        """
        Args:
            node_id: ID único del nodo
            node_type: 'peer' o 'coordinator'
            host: IP donde este nodo está escuchando
            port: Puerto TCP principal
            seed_nodes: Lista de tuplas (host, port) para conexión directa
        """
        self.node_id = node_id
        self.node_type = node_type
        self.host = host
        self.port = port
        self.seed_nodes = seed_nodes or []
        
        # Registro de nodos conocidos
        self.nodes: Dict[str, NodeInfo] = {}
        
        # Callbacks cuando hay cambios
        self.on_node_discovered: List[Callable] = []
        self.on_node_lost: List[Callable] = []
        
        self.running = False
        self._lock = threading.Lock()
        self.logger = logging.getLogger(f"MulticastDiscovery-{node_id}")
        
    def start(self):
        """Iniciar descubrimiento"""
        self.running = True
        
        # Thread 1: Enviar anuncios multicast
        threading.Thread(target=self._announce_loop, daemon=True).start()
        
        # Thread 2: Escuchar anuncios multicast
        threading.Thread(target=self._listen_loop, daemon=True).start()
        
        # Thread 3: Conectar a seed nodes via TCP
        if self.seed_nodes:
            threading.Thread(target=self._seed_connect_loop, daemon=True).start()
        
        # Thread 4: Limpiar nodos muertos
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        
        self.logger.info(f"✅ Multicast Discovery iniciado (grupo {self.MULTICAST_GROUP}:{self.MULTICAST_PORT})")
        
    def stop(self):
        self.running = False
        
    def _create_multicast_sender(self) -> socket.socket:
        """Crea socket para enviar mensajes multicast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        # Permitir enviar a localhost también (para pruebas)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        return sock
        
    def _create_multicast_receiver(self) -> socket.socket:
        """Crea socket para recibir mensajes multicast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # En algunos sistemas necesitamos SO_REUSEPORT
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
            
        # Bind al puerto multicast
        sock.bind(('', self.MULTICAST_PORT))
        
        # Unirse al grupo multicast
        mreq = struct.pack('4sL', 
                          socket.inet_aton(self.MULTICAST_GROUP),
                          socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        sock.settimeout(1.0)
        return sock
        
    def _announce_loop(self):
        """Envía anuncios multicast periódicamente"""
        sock = self._create_multicast_sender()
        
        while self.running:
            try:
                message = {
                    'type': 'NODE_ANNOUNCE',
                    'node_id': self.node_id,
                    'node_type': self.node_type,
                    'host': self.host,
                    'port': self.port,
                    'timestamp': time.time(),
                    # Incluir lista de nodos conocidos para propagación
                    'known_nodes': self._get_known_nodes_summary()
                }
                
                data = json.dumps(message).encode()
                sock.sendto(data, (self.MULTICAST_GROUP, self.MULTICAST_PORT))
                self.logger.debug(f"📡 Anuncio multicast enviado")
                
            except Exception as e:
                self.logger.debug(f"Error enviando anuncio multicast: {e}")
                
            time.sleep(self.ANNOUNCE_INTERVAL)
            
        sock.close()
        
    def _listen_loop(self):
        """Escucha anuncios multicast de otros nodos"""
        try:
            sock = self._create_multicast_receiver()
            self.logger.info(f"🔊 Escuchando multicast en {self.MULTICAST_GROUP}:{self.MULTICAST_PORT}")
        except Exception as e:
            self.logger.error(f"No se pudo crear socket multicast: {e}")
            # Fallback: solo usar seed nodes
            return
            
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                message = json.loads(data.decode())
                
                if message.get('type') == 'NODE_ANNOUNCE':
                    self._handle_node_announce(message, addr)
                    
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.running:
                    self.logger.debug(f"Error recibiendo multicast: {e}")
                    
        sock.close()
        
    def _handle_node_announce(self, message: dict, addr: tuple):
        """Procesa anuncio de nodo"""
        node_id = message.get('node_id')
        
        # Ignorarnos a nosotros mismos
        if not node_id or node_id == self.node_id:
            return
            
        # Usar la IP del mensaje o la del paquete
        host = message.get('host') or addr[0]
        
        with self._lock:
            is_new = node_id not in self.nodes
            
            node_info = NodeInfo(
                node_id=node_id,
                node_type=message.get('node_type', 'peer'),
                host=host,
                port=message.get('port', 5000),
                last_seen=time.time()
            )
            
            self.nodes[node_id] = node_info
            
            if is_new:
                self.logger.info(f"✓ Nodo descubierto via multicast: {node_id} ({host}:{node_info.port})")
                for callback in self.on_node_discovered:
                    try:
                        callback(node_info)
                    except Exception as e:
                        self.logger.error(f"Error en callback on_node_discovered: {e}")
                        
        # Procesar nodos conocidos propagados
        known_nodes = message.get('known_nodes', [])
        for known in known_nodes:
            self._register_known_node(known)
            
    def _register_known_node(self, node_data: dict):
        """Registra un nodo conocido propagado por otro nodo"""
        node_id = node_data.get('node_id')
        if not node_id or node_id == self.node_id:
            return
            
        with self._lock:
            if node_id in self.nodes:
                return  # Ya lo conocemos
                
            # Intentar conectar para verificar que está vivo
            host = node_data.get('host')
            port = node_data.get('port', 5000)
            
            if self._verify_node(host, port):
                node_info = NodeInfo(
                    node_id=node_id,
                    node_type=node_data.get('node_type', 'peer'),
                    host=host,
                    port=port,
                    last_seen=time.time()
                )
                
                self.nodes[node_id] = node_info
                self.logger.info(f"✓ Nodo descubierto via propagación: {node_id}")
                
                for callback in self.on_node_discovered:
                    try:
                        callback(node_info)
                    except:
                        pass
                        
    def _verify_node(self, host: str, port: int) -> bool:
        """Verifica que un nodo está vivo con un health check TCP"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                sock.connect((host, port))
                
                request = {'action': 'health'}
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Esperar respuesta
                length_data = sock.recv(8)
                if length_data:
                    return True
                    
        except:
            pass
        return False
        
    def _seed_connect_loop(self):
        """Conecta periódicamente a seed nodes para descubrimiento"""
        while self.running:
            for host, port in self.seed_nodes:
                try:
                    self._connect_to_seed(host, port)
                except Exception as e:
                    self.logger.debug(f"Error conectando a seed {host}:{port}: {e}")
                    
            time.sleep(self.ANNOUNCE_INTERVAL * 2)
            
    def _connect_to_seed(self, host: str, port: int):
        """Conecta a un seed node y obtiene lista de nodos"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((host, port))
                
                # Enviar solicitud de lista de nodos
                request = {'action': 'get_peers', 'from_node': self.node_id}
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Recibir respuesta
                length_data = sock.recv(8)
                if not length_data:
                    return
                    
                msg_len = int(length_data.decode().strip())
                data = b''
                while len(data) < msg_len:
                    chunk = sock.recv(min(4096, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                    
                response = json.loads(data.decode())
                
                # Registrar el seed node
                seed_id = response.get('node_id')
                if seed_id and seed_id != self.node_id:
                    self._register_direct_node(seed_id, host, port)
                    
                # Registrar peers que el seed conoce
                for peer in response.get('peers', []):
                    peer_id = peer.get('node_id')
                    peer_host = peer.get('host')
                    peer_port = peer.get('port', 5000)
                    if peer_id and peer_id != self.node_id:
                        self._register_direct_node(peer_id, peer_host, peer_port)
                        
        except Exception as e:
            self.logger.debug(f"Error en seed connect: {e}")
            
    def _register_direct_node(self, node_id: str, host: str, port: int):
        """Registra un nodo descubierto por conexión directa"""
        with self._lock:
            is_new = node_id not in self.nodes
            
            node_info = NodeInfo(
                node_id=node_id,
                node_type='peer',
                host=host,
                port=port,
                last_seen=time.time()
            )
            
            self.nodes[node_id] = node_info
            
            if is_new:
                self.logger.info(f"✓ Nodo descubierto via seed: {node_id} ({host}:{port})")
                for callback in self.on_node_discovered:
                    try:
                        callback(node_info)
                    except:
                        pass
                        
    def _get_known_nodes_summary(self) -> List[dict]:
        """Retorna resumen de nodos conocidos para propagación"""
        with self._lock:
            return [
                {
                    'node_id': n.node_id,
                    'host': n.host,
                    'port': n.port,
                    'node_type': n.node_type
                }
                for n in list(self.nodes.values())[:10]  # Limitar para no saturar
            ]
            
    def _cleanup_loop(self):
        """Elimina nodos que no responden"""
        while self.running:
            current_time = time.time()
            
            with self._lock:
                dead_nodes = []
                for node_id, node_info in list(self.nodes.items()):
                    if current_time - node_info.last_seen > self.NODE_TIMEOUT:
                        dead_nodes.append(node_id)
                        
                for node_id in dead_nodes:
                    node_info = self.nodes.pop(node_id)
                    self.logger.warning(f"✗ Nodo perdido: {node_id}")
                    for callback in self.on_node_lost:
                        try:
                            callback(node_info)
                        except:
                            pass
                        
            time.sleep(5)
            
    def get_active_nodes(self) -> List[NodeInfo]:
        """Obtener lista de nodos activos"""
        with self._lock:
            return list(self.nodes.values())
            
    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """Obtener información de un nodo específico"""
        with self._lock:
            return self.nodes.get(node_id)
            
    def add_seed_node(self, host: str, port: int = 5000):
        """Añade un seed node dinámicamente"""
        if (host, port) not in self.seed_nodes:
            self.seed_nodes.append((host, port))
            self.logger.info(f"➕ Seed node añadido: {host}:{port}")
            # Conectar inmediatamente
            threading.Thread(
                target=self._connect_to_seed, 
                args=(host, port), 
                daemon=True
            ).start()
            
    def remove_seed_node(self, host: str, port: int = 5000):
        """Elimina un seed node"""
        if (host, port) in self.seed_nodes:
            self.seed_nodes.remove((host, port))
            self.logger.info(f"➖ Seed node eliminado: {host}:{port}")
