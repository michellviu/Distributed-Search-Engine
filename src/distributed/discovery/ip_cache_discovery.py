# src/distributed/discovery/ip_cache_discovery.py
"""
Descubrimiento de nodos usando IP Cache + Escaneo de Subred.
Funciona en Docker Swarm sin necesidad de multicast, DNS, ni seed nodes obligatorios.

Mecanismo:
1. Al iniciar, escanea la subred local buscando otros nodos (puerto 5000)
2. Cuando un nodo contacta a otro (get_peers), envía su info completa
3. El nodo que recibe la petición registra al solicitante (registro bidireccional)
4. Los nodos se propagan entre sí a través de la lista de peers
5. Opcionalmente puede usar seed nodes como respaldo
"""
import socket
import json
import threading
import time
import logging
import ipaddress
from typing import Dict, Callable, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class NodeInfo:
    """Información de un nodo"""
    node_id: str
    host: str
    port: int
    node_type: str  # 'peer' o 'coordinator'
    last_seen: float
    load: int = 0


class IPCacheDiscovery:
    """
    Descubrimiento de nodos usando IP Cache + Escaneo de Subred.
    
    Este método es 100% automático porque:
    - Escanea la subred local buscando otros nodos
    - No depende de multicast (que puede no funcionar en overlay networks)
    - No depende del DNS de Docker
    - No requiere seed nodes (aunque los soporta como respaldo)
    - Usa conexiones TCP directas que siempre funcionan
    - Registro bidireccional: cuando A contacta a B, ambos se registran mutuamente
    """
    
    ANNOUNCE_INTERVAL = 5   # segundos entre anuncios
    NODE_TIMEOUT = 20       # segundos antes de considerar nodo muerto
    SCAN_INTERVAL = 30      # segundos entre escaneos de subred
    DEFAULT_PORT = 5000     # puerto por defecto para escanear
    
    def __init__(self, node_id: str, node_type: str, 
                 host: str, port: int,
                 seed_nodes: List[tuple] = None,
                 enable_subnet_scan: bool = True):
        """
        Args:
            node_id: ID único del nodo
            node_type: 'peer' o 'coordinator'
            host: IP donde este nodo está escuchando
            port: Puerto TCP principal
            seed_nodes: Lista opcional de tuplas (host, port) como respaldo
            enable_subnet_scan: Si True, escanea la subred automáticamente
        """
        self.node_id = node_id
        self.node_type = node_type
        self.host = host
        self.port = port
        self.seed_nodes = seed_nodes or []
        self.enable_subnet_scan = enable_subnet_scan
        
        # Caché de nodos conocidos
        self.nodes: Dict[str, NodeInfo] = {}
        
        # Callbacks cuando hay cambios
        self.on_node_discovered: List[Callable] = []
        self.on_node_lost: List[Callable] = []
        
        self.running = False
        self._lock = threading.Lock()
        self._my_ip = None
        self.logger = logging.getLogger(f"IPCacheDiscovery-{node_id}")
    
    def _get_my_ip(self) -> str:
        """Obtiene la IP de este nodo en la red del cluster"""
        if self._my_ip:
            return self._my_ip
        
        # Método 1: Usar el host configurado si no es 0.0.0.0
        if self.host and self.host != '0.0.0.0':
            self._my_ip = self.host
            return self._my_ip
        
        # Método 2: Obtener todas las IPs y buscar la de la red interna (10.x o 172.x)
        try:
            import subprocess
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2)
            ips = result.stdout.strip().split()
            
            # Priorizar IPs de redes overlay de Docker (10.0.x.x)
            for ip in ips:
                if ip.startswith('10.0.') or ip.startswith('10.1.'):
                    self._my_ip = ip
                    return self._my_ip
            
            # Fallback a cualquier IP privada
            for ip in ips:
                if ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.'):
                    self._my_ip = ip
                    return self._my_ip
                    
            if ips:
                self._my_ip = ips[0]
                return self._my_ip
        except:
            pass
        
        # Método 3: Conectar a socket externo (fallback)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                self._my_ip = s.getsockname()[0]
                return self._my_ip
        except:
            pass
            
        return self.host or "0.0.0.0"
    
    def _get_all_subnets(self) -> List[ipaddress.IPv4Network]:
        """Obtiene todas las subredes en las que está este nodo"""
        subnets = []
        try:
            import subprocess
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2)
            ips = result.stdout.strip().split()
            
            for ip in ips:
                try:
                    # Solo redes privadas
                    if ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.'):
                        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                        if network not in subnets:
                            subnets.append(network)
                except:
                    pass
        except:
            pass
        
        # Fallback: usar _get_my_ip
        if not subnets:
            my_ip = self._get_my_ip()
            try:
                subnets.append(ipaddress.IPv4Network(f"{my_ip}/24", strict=False))
            except:
                pass
                
        return subnets
        
    def start(self):
        """Iniciar descubrimiento"""
        self.running = True
        
        # Obtener nuestra IP
        my_ip = self._get_my_ip()
        self.logger.info(f"✅ IP Cache Discovery iniciado")
        self.logger.info(f"   Mi IP: {my_ip}")
        self.logger.info(f"   Escaneo de subred: {'Habilitado' if self.enable_subnet_scan else 'Deshabilitado'}")
        if self.seed_nodes:
            self.logger.info(f"   Seed nodes: {self.seed_nodes}")
        
        # Thread 1: Escaneo inicial de subred (si está habilitado)
        if self.enable_subnet_scan:
            threading.Thread(target=self._subnet_scan_loop, daemon=True).start()
        
        # Thread 2: Conectar periódicamente a seed nodes y peers conocidos
        threading.Thread(target=self._discovery_loop, daemon=True).start()
        
        # Thread 3: Limpiar nodos muertos
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        
    def stop(self):
        """Detener descubrimiento"""
        self.running = False
        self.logger.info("🛑 IP Cache Discovery detenido")
    
    def _subnet_scan_loop(self):
        """Escanea la subred periódicamente buscando nodos"""
        # Escaneo inicial inmediato
        self._scan_all_subnets()
        
        while self.running:
            time.sleep(self.SCAN_INTERVAL)
            self._scan_all_subnets()
    
    def _scan_all_subnets(self):
        """Escanea todas las subredes disponibles"""
        subnets = self._get_all_subnets()
        for subnet in subnets:
            self._scan_subnet(subnet)
    
    def _scan_subnet(self, subnet: ipaddress.IPv4Network = None):
        """Escanea una subred buscando nodos en el puerto 5000"""
        if not subnet:
            subnets = self._get_all_subnets()
            if subnets:
                subnet = subnets[0]
            else:
                return
            
        my_ip = self._get_my_ip()
        self.logger.info(f"🔍 Escaneando subred {subnet} buscando nodos...")
        
        found_count = 0
        
        # Usar ThreadPoolExecutor para escanear en paralelo
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {}
            
            for ip in subnet.hosts():
                ip_str = str(ip)
                # No escanear nuestra propia IP
                if ip_str == my_ip:
                    continue
                    
                future = executor.submit(self._probe_host, ip_str, self.port)
                futures[future] = ip_str
            
            for future in as_completed(futures, timeout=15):
                ip_str = futures[future]
                try:
                    result = future.result(timeout=3)
                    if result:
                        found_count += 1
                except:
                    pass
        
        if found_count > 0:
            self.logger.info(f"🔍 Escaneo completado: {found_count} nodos encontrados en {subnet}")
    
    def _probe_host(self, host: str, port: int) -> bool:
        """Intenta conectar a un host y obtener peers (descubrimiento)"""
        try:
            self._connect_to_peer(host, port)
            return True
        except:
            return False
        
    def _discovery_loop(self):
        """Loop principal de descubrimiento"""
        # Primera conexión inmediata a seeds
        if self.seed_nodes:
            self._connect_to_all_seeds()
        
        while self.running:
            time.sleep(self.ANNOUNCE_INTERVAL)
            
            # Conectar a seeds (si hay)
            if self.seed_nodes:
                self._connect_to_all_seeds()
            
            # También conectar a peers conocidos para mantener la conexión
            # y propagar información de nuevos nodos
            self._refresh_known_peers()
            
    def _connect_to_all_seeds(self):
        """Conecta a todos los seed nodes"""
        for host, port in self.seed_nodes:
            try:
                self._connect_to_peer(host, port)
            except Exception as e:
                self.logger.debug(f"Error conectando a seed {host}:{port}: {e}")
                
    def _refresh_known_peers(self):
        """Reconecta a peers conocidos para actualizar estado"""
        with self._lock:
            peers_copy = list(self.nodes.values())
            
        for peer in peers_copy:
            try:
                self._connect_to_peer(peer.host, peer.port)
            except Exception as e:
                self.logger.debug(f"Error refrescando peer {peer.node_id}: {e}")
                
    def _connect_to_peer(self, host: str, port: int):
        """
        Conecta a un peer y intercambia información de nodos.
        Envía nuestra info para que el peer nos registre (bidireccional).
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((host, port))
                
                # Enviar get_peers CON nuestra información completa
                # Esto permite registro bidireccional
                request = {
                    'action': 'get_peers',
                    'from_node': self.node_id,
                    'from_host': self.host,
                    'from_port': self.port,
                    'from_type': self.node_type
                }
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
                
                # Registrar el nodo al que nos conectamos
                peer_id = response.get('node_id')
                if peer_id and peer_id != self.node_id:
                    self._register_node(
                        node_id=peer_id,
                        host=host,
                        port=port,
                        node_type='peer'
                    )
                    
                # Registrar todos los peers que el nodo conoce
                for peer in response.get('peers', []):
                    peer_id = peer.get('node_id')
                    peer_host = peer.get('host')
                    peer_port = peer.get('port', 5000)
                    peer_type = peer.get('node_type', 'peer')
                    
                    if peer_id and peer_id != self.node_id:
                        self._register_node(
                            node_id=peer_id,
                            host=peer_host,
                            port=peer_port,
                            node_type=peer_type
                        )
                        
        except socket.timeout:
            self.logger.debug(f"Timeout conectando a {host}:{port}")
        except ConnectionRefusedError:
            self.logger.debug(f"Conexión rechazada: {host}:{port}")
        except Exception as e:
            self.logger.debug(f"Error conectando a {host}:{port}: {e}")
            
    def _register_node(self, node_id: str, host: str, port: int, node_type: str = 'peer'):
        """Registra un nodo en el caché"""
        if not node_id or node_id == self.node_id:
            return
            
        with self._lock:
            is_new = node_id not in self.nodes
            
            node_info = NodeInfo(
                node_id=node_id,
                node_type=node_type,
                host=host,
                port=port,
                last_seen=time.time()
            )
            
            self.nodes[node_id] = node_info
            
        if is_new:
            self.logger.info(f"✓ Nodo descubierto: {node_id} ({host}:{port})")
            for callback in self.on_node_discovered:
                try:
                    callback(node_info)
                except Exception as e:
                    self.logger.error(f"Error en callback on_node_discovered: {e}")
                    
    def register_node_from_connection(self, node_id: str, host: str, port: int, 
                                       node_type: str = 'peer'):
        """
        Registra un nodo que nos contactó (llamado desde el servidor).
        Este es el método para registro bidireccional.
        """
        self._register_node(node_id, host, port, node_type)
        
    def _cleanup_loop(self):
        """Elimina nodos que no responden"""
        while self.running:
            time.sleep(5)
            current_time = time.time()
            
            with self._lock:
                dead_nodes = []
                for node_id, node_info in list(self.nodes.items()):
                    if current_time - node_info.last_seen > self.NODE_TIMEOUT:
                        # Verificar si realmente está muerto
                        if not self._verify_node(node_info.host, node_info.port):
                            dead_nodes.append(node_id)
                        else:
                            # Sigue vivo, actualizar last_seen
                            self.nodes[node_id].last_seen = time.time()
                        
                for node_id in dead_nodes:
                    node_info = self.nodes.pop(node_id)
                    self.logger.warning(f"✗ Nodo perdido: {node_id}")
                    for callback in self.on_node_lost:
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
                
                length_data = sock.recv(8)
                if length_data:
                    return True
        except:
            pass
        return False
        
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
                target=self._connect_to_peer, 
                args=(host, port), 
                daemon=True
            ).start()
            
    def remove_seed_node(self, host: str, port: int = 5000):
        """Elimina un seed node"""
        if (host, port) in self.seed_nodes:
            self.seed_nodes.remove((host, port))
            self.logger.info(f"➖ Seed node eliminado: {host}:{port}")
            
    def update_node_last_seen(self, node_id: str):
        """Actualiza el timestamp de último contacto de un nodo"""
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].last_seen = time.time()
