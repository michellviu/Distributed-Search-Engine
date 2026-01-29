"""
Descubrimiento dinámico de coordinadores en Docker Swarm.

Este módulo permite al cliente descubrir automáticamente coordinadores
disponibles en el cluster de Docker Swarm sin necesidad de configuración
previa de direcciones.

Estrategias de descubrimiento:
1. DNS de Docker Swarm: search_coordinator (resuelve a todas las réplicas)
2. Verificación de conectividad a puertos conocidos
3. Fallback a direcciones configuradas

NOTA: El descubrimiento DNS solo funciona si el cliente está DENTRO de Docker.
Si el cliente corre en el host, debe usar localhost:5000 (puerto expuesto).
"""

import socket
import logging
import threading
import time
import json
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass


@dataclass
class DiscoveredCoordinator:
    """Coordinador descubierto dinámicamente"""
    host: str
    port: int = 5000
    discovered_at: float = 0.0
    is_alive: bool = True
    is_leader: bool = False
    
    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class CoordinatorDiscovery:
    """
    Descubrimiento automático de coordinadores en Docker Networks.
    
    Usa el DNS interno de Docker para resolver el alias de red común
    'coordinator' a todas las IPs de contenedores coordinadores.
    
    En Docker Network (cliente dentro de Docker):
    - 'coordinator' → Resuelve a todas las IPs de contenedores con ese alias
    
    Fuera de Docker (cliente en el host):
    - Solo puede conectar a localhost:puerto_expuesto
    - Docker balancea internamente entre coordinadores
    
    Estrategia de descubrimiento:
    1. Si está dentro de Docker: resolver 'coordinator' (alias común)
    2. Si falla: usar direcciones hardcodeadas/persistidas
    3. Si sigue fallando: usar localhost:5000
    """
    
    # Alias de red común para todos los coordinadores
    DOCKER_NETWORK_ALIAS = "coordinator"
    
    # # Fallback para cliente fuera de Docker
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 5000
    
    def __init__(self, initial_addresses: Optional[List[str]] = None):
        """
        Inicializa el descubridor de coordinadores.
        
        Args:
            initial_addresses: Lista de direcciones iniciales (opcional)
        """
        self.logger = logging.getLogger("CoordinatorDiscovery")
        
        # Coordinadores conocidos
        self.coordinators: Set[str] = set()
        self._is_inside_docker = True#self._check_if_inside_docker()
        self.logger.info(f"Cliente dentro de Docker: {self._is_inside_docker}")
        self._lock = threading.RLock()
        self._auto_discovery_enabled = False
        
        # Agregar direcciones iniciales
        # if initial_addresses:
        #     for addr in initial_addresses:
        #         # Limpiar y validar
        #         if ":" in addr:
        #             self.coordinators.add(addr)
        #         else:
        #             self.coordinators.add(f"{addr}:{self.DEFAULT_PORT}")
        
        # Intentar descubrir automáticamente
        if self._is_inside_docker:
            self._discover_from_docker_dns()
        
        # Si no se encontró nada, usar localhost
        if not self.coordinators:
            self.coordinators.add(f"{self.DEFAULT_HOST}:{self.DEFAULT_PORT}")
            if self._is_inside_docker:
                self.logger.warning("No se encontraron coordinadores via DNS")
        
        self.logger.info(f"Coordinadores descubiertos: {self.coordinators}")
    
    # def _check_if_inside_docker(self) -> bool:
    #     """Detecta si el cliente está corriendo dentro de Docker"""
    #     try:
    #         with open('/proc/1/cgroup', 'r') as f:
    #             return 'docker' in f.read()
    #     except:
    #         pass
        
    #     try:
    #         # Verificar si existe /.dockerenv
    #         import os
    #         return os.path.exists('/.dockerenv')
    #     except:
    #         pass
        
    #     return False
    
    def _discover_from_docker_dns(self) -> bool:
        """
        Descubre coordinadores intentando resolver nombres de host conocidos.
        
        Intenta resolver 'coordinator1', 'coordinator2', etc. hasta encontrar algunos.
        Esto funciona dentro de Docker network donde los hostnames están disponibles.
        """
        discovered = False
        
        # Intentar resolver nombres de coordinadores conocidos
        for i in range(1, 20):  # coordinator1 to coordinator19
            hostname = f"coordinator{i}"
            try:
                ips = self._resolve_dns(hostname)
                if ips:
                    # Usar la primera IP, asumir puerto estándar
                    ip = ips[0]
                    self.coordinators.add(f"{ip}:{self.DEFAULT_PORT}")
                    discovered = True
                    self.logger.debug(f"✓ Descubierto {hostname} → {ip}")
            except:
                # No se pudo resolver este hostname, continuar
                pass
        
        if discovered:
            self.logger.info(f"✅ Descubiertos coordinadores via hostname resolution: {self.get_coordinators()}")
            return True
        
        # Fallback: intentar el alias común
        try:
            ips = self._resolve_dns(self.DOCKER_NETWORK_ALIAS)
            if ips:
                for ip in ips:
                    if ip != '127.0.0.1' and ip != 'localhost':  # Evitar localhost
                        self.coordinators.add(f"{ip}:{self.DEFAULT_PORT}")
                        discovered = True
        except:
            pass
        
        return discovered
    
    def _resolve_dns(self, hostname: str) -> List[str]:
        """
        Resuelve un hostname a lista de IPs usando Docker Network DNS.
        
        En Docker networks, cuando múltiples contenedores tienen el mismo
        network alias, el DNS resuelve a múltiples IPs (round-robin).
        
        Ejemplo con 3 coordinadores:
            'coordinator' → ['10.0.1.5', '10.0.2.6', '10.0.3.7']
        """
        try:
            # getaddrinfo puede retornar múltiples resultados para el mismo hostname
            results = socket.getaddrinfo(
                hostname, 
                self.DEFAULT_PORT, 
                socket.AF_INET, 
                socket.SOCK_STREAM
            )
            
            # Extraer IPs únicas (Docker puede retornar duplicados)
            ips = list(set(result[4][0] for result in results))
            
            self.logger.info(f"DEBUG: Resolved '{hostname}' to IPs: {ips}")
            
            if ips:
                self.logger.debug(f"✓ Resolvió '{hostname}' → {ips}")
            return ips
        except socket.gaierror as e:
            self.logger.debug(f"✗ No se pudo resolver '{hostname}': {e}")
            raise
    
    def get_coordinators(self) -> List[str]:
        """Obtiene lista de coordinadores descubiertos"""
        with self._lock:
            return sorted(list(self.coordinators))
    
    def add_coordinator(self, address: str) -> None:
        """Agregar un coordinador a la lista conocida"""
        with self._lock:
            self.coordinators.add(address)
            self.logger.info(f"Coordinador agregado: {address}")
    
    def refresh(self) -> None:
        """Refresca la lista de coordinadores descubiertos"""
        if not self._is_inside_docker:
            # Fuera de Docker, no tiene sentido refrescar DNS
            # Solo verificar que localhost:5000 sigue respondiendo
            self.logger.debug("Cliente fuera de Docker, usando localhost:5000")
            return
        
        with self._lock:
            old_coordinators = self.coordinators.copy()
            self.coordinators.clear()
        
        self._discover_from_docker_dns()
        
        if not self.coordinators:
            # Restaurar los anteriores si no encontramos nuevos
            self.coordinators = old_coordinators
        else:
            self.logger.info(f"Coordinadores refrescados: {self.coordinators}")
    
    def start_auto_discovery(self, interval: int = 30) -> Optional[threading.Thread]:
        """
        Inicia thread de descubrimiento automático periódico.
        
        Args:
            interval: Segundos entre intentos de descubrimiento
            
        Returns:
            Thread de descubrimiento o None si está fuera de Docker
        """
        if not self._is_inside_docker:
            self.logger.debug("Auto-descubrimiento deshabilitado fuera de Docker")
            return None
        
        if self._auto_discovery_enabled:
            return None
        
        self._auto_discovery_enabled = True
        
        def discovery_loop():
            while self._auto_discovery_enabled:
                time.sleep(interval)
                self.refresh()
        
        thread = threading.Thread(target=discovery_loop, daemon=True)
        thread.start()
        self.logger.info(f"Descubrimiento automático iniciado (cada {interval}s)")
        return thread
    
    def get_real_coordinator_count(self) -> int:
        """
        Obtiene el número real de coordinadores del cluster.
        
        Consulta al coordinador conectado para obtener la información real
        del cluster, no solo los coordinadores localmente conocidos.
        """
        try:
            for addr in self.coordinators:
                host, port = addr.split(':')
                # Aprovechar para actualizar la lista completa
                if self.refresh_from_mid_stream(host, int(port)):
                    return len(self.coordinators)
        except:
            pass
        
        return len(self.coordinators)

    def refresh_from_mid_stream(self, host: str, port: int) -> bool:
        """
        Consulta a un coordinador activo por la lista completa de pares.
        Esto permite descubrir nuevos nodos añadidos dinámicamente.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((host, port))
                
                request = json.dumps({'action': 'get_coordinators'})
                sock.sendall(f"{len(request):<8}".encode() + request.encode())
                
                length_data = sock.recv(8)
                if not length_data: return False
                
                length = int(length_data.decode().strip())
                data = b''
                while len(data) < length:
                    chunk = sock.recv(4096)
                    if not chunk: break
                    data += chunk
                
                response = json.loads(data.decode())
                if response.get('status') == 'success':
                    coords = response.get('coordinators', [])
                    for c in coords:
                        c_host = c.get('host')
                        c_port = c.get('port')
                        if c_host and c_port:
                            self.add_coordinator(f"{c_host}:{c_port}")
                    return True
        except Exception as e:
            self.logger.debug(f"Error refreshing from {host}:{port}: {e}")
        return False
