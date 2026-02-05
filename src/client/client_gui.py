#!/usr/bin/env python3
"""
GUI Client for Distributed Search Engine using CustomTkinter
Conecta directamente al sistema distribuido con soporte de failover
"""

import sys
import socket
import json
import threading
import time
import base64
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# Try to import customtkinter, fallback to regular tkinter
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
    print("CustomTkinter disponible - usando interfaz moderna")
except ImportError:
    CTK_AVAILABLE = False
    print("CustomTkinter no disponible - usando Tkinter estándar")
    print("Instala con: pip install customtkinter")
    
    # Create wrapper classes for tkinter to match customtkinter API
    import tkinter as tk_base
    from tkinter import ttk
    
    class ctk:
        """Wrapper to provide CustomTkinter-like API using standard tkinter"""
        
        @staticmethod
        def set_appearance_mode(mode):
            pass
        
        @staticmethod
        def set_default_color_theme(theme):
            pass
        
        class CTk(tk_base.Tk):
            pass
        
        class CTkFrame(tk_base.Frame):
            def __init__(self, master, **kwargs):
                # Remove customtkinter-specific kwargs
                kwargs.pop('fg_color', None)
                kwargs.pop('corner_radius', None)
                super().__init__(master, **kwargs)
        
        class CTkLabel(tk_base.Label):
            def __init__(self, master, **kwargs):
                # Map customtkinter kwargs to tkinter
                text_color = kwargs.pop('text_color', None)
                if text_color:
                    kwargs['fg'] = text_color
                kwargs.pop('font', None)  # Remove font for now
                super().__init__(master, **kwargs)
        
        class CTkEntry(tk_base.Entry):
            def __init__(self, master, **kwargs):
                kwargs.pop('placeholder_text', None)
                kwargs.pop('corner_radius', None)
                super().__init__(master, **kwargs)
        
        class CTkButton(tk_base.Button):
            def __init__(self, master, **kwargs):
                kwargs.pop('corner_radius', None)
                kwargs.pop('fg_color', None)
                kwargs.pop('hover_color', None)
                super().__init__(master, **kwargs)
        
        class CTkTextbox(scrolledtext.ScrolledText):
            def __init__(self, master, **kwargs):
                kwargs.pop('corner_radius', None)
                kwargs.pop('fg_color', None)
                super().__init__(master, **kwargs)
            
            def tag_config(self, *args, **kwargs):
                """Map to standard text widget tag_config"""
                self.tag_configure(*args, **kwargs)
        
        class CTkFont:
            def __init__(self, **kwargs):
                self.size = kwargs.get('size', 12)
                self.weight = kwargs.get('weight', 'normal')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import Config
from utils.logger import setup_logging
from client.coordinator_discovery import CoordinatorDiscovery


# ============================================================================
# Cliente Distribuido con Failover (integrado en GUI)
# ============================================================================

@dataclass
class CoordinatorInfo:
    """Información de un coordinador conocido"""
    host: str
    port: int
    is_leader: bool = False
    is_alive: bool = True
    last_check: float = 0.0
    failures: int = 0
    
    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class DistributedClient:
    """
    Cliente del sistema distribuido con soporte de failover.
    Compatible con la interfaz esperada por SearchEngineGUI.
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    HEALTH_CHECK_INTERVAL = 10
    LEADER_CHECK_INTERVAL = 5  # Verificar líder cada 5 segundos
    MAX_FAILURES_BEFORE_SKIP = 3
    DISCOVERED_COORDINATORS_FILE = "discovered_coordinators.json"
    
    @classmethod
    def _get_persistence_path(cls) -> Path:
        """Obtiene la ruta del archivo de persistencia"""
        # Usar directorio del usuario para persistencia
        base_dir = Path.home() / ".distributed-search-client"
        base_dir.mkdir(exist_ok=True)
        return base_dir / cls.DISCOVERED_COORDINATORS_FILE
    
    @classmethod
    def load_persisted_coordinators(cls) -> List[str]:
        """Carga coordinadores descubiertos previamente"""
        try:
            path = cls._get_persistence_path()
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)
                    coords = data.get('coordinators', [])
                    if coords:
                        logging.getLogger("DistributedClient").info(
                            f"📂 Cargados {len(coords)} coordinadores persistidos"
                        )
                    return coords
        except Exception as e:
            logging.getLogger("DistributedClient").debug(f"Error cargando coordinadores: {e}")
        return []
    
    def _save_coordinators(self):
        """Guarda los coordinadores conocidos para persistencia"""
        try:
            path = self._get_persistence_path()
            coords = [c.address for c in self.coordinators if c.is_alive or c.failures < 5]
            with open(path, 'w') as f:
                json.dump({
                    'coordinators': coords,
                    'last_updated': time.time()
                }, f, indent=2)
            self.logger.debug(f"💾 Guardados {len(coords)} coordinadores")
        except Exception as e:
            self.logger.debug(f"Error guardando coordinadores: {e}")
    
    def __init__(self, coordinator_addresses: List[str] = None):
        """
        Args:
            coordinator_addresses: Lista de "host:port" de coordinadores (opcional)
                                   Si no se proporciona, usa descubrimiento automático
        """
        self.logger = logging.getLogger("DistributedClient")
        
        # Combinar: coordinadores proporcionados + persistidos
        all_addresses = set()
        
        # 1. Agregar coordinadores proporcionados (semillas)
        if coordinator_addresses:
            all_addresses.update(coordinator_addresses)
        
        # 2. Agregar coordinadores persistidos (descubiertos anteriormente)
        persisted = self.load_persisted_coordinators()
        all_addresses.update(persisted)
        
        # 3. Usar descubrimiento si tenemos direcciones, sino automático
        if all_addresses:
            discovery = CoordinatorDiscovery(initial_addresses=list(all_addresses))
        else:
            discovery = CoordinatorDiscovery()
        
        self.discovery = discovery
        
        # Convertir direcciones descubiertas a CoordinatorInfo
        self.coordinators: List[CoordinatorInfo] = []
        for addr in discovery.get_coordinators():
            parts = addr.split(':')
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 5000
            self.coordinators.append(CoordinatorInfo(host=host, port=port))
        
        if not self.coordinators:
            # raise ValueError("No se encontraron coordinadores")
            self.logger.warning("⚠️ No se encontraron coordinadores iniciales. Esperando configuración manual.")
        
        self.current_coordinator: Optional[CoordinatorInfo] = None
        self._lock = threading.RLock()
        self._active = True
        
        self.logger.info(f"Cliente inicializado con {len(self.coordinators)} coordinadores")
        
        # Conectar ao primer coordinador disponible (si existe)
        if self.coordinators:
            self._find_active_coordinator()
        
        # Health check en background
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        
        # Descubrimiento automático cada 30 segundos
        self.discovery.start_auto_discovery(interval=30)
        
        # Actualizar lista de coordinadores consultando al cluster
        self._discover_coordinators_from_cluster()
    
    def add_manual_coordinator(self, host: str, port: int) -> bool:
        """Agrega un coordinador manualmente e intenta conectar"""
        address = f"{host}:{port}"
        with self._lock:
            # Verificar si ya existe
            for coord in self.coordinators:
                if coord.address == address:
                    return False
            
            new_coord = CoordinatorInfo(host=host, port=port)
            self.coordinators.append(new_coord)
            self.logger.info(f"➕ Coordinador manual agregado: {address}")
            self._save_coordinators()
        
        # Intentar conectar inmediatamente
        if not self.current_coordinator:
            return self._find_active_coordinator()
        return True

    def _find_active_coordinator(self) -> bool:
        """Encuentra un coordinador activo, priorizando siempre al líder"""
        with self._lock:
            # Primero: Intentar descubrir nuevos coordinadores
            self._discover_coordinators_from_cluster()
            
            # Segundo: Buscar el líder conocido
            for coord in self.coordinators:
                if coord.is_leader and coord.failures < self.MAX_FAILURES_BEFORE_SKIP:
                    if self._check_coordinator_health(coord):
                        if coord != self.current_coordinator:
                            self.logger.info(f"✅ Conectado al LÍDER: {coord.address}")
                        self.current_coordinator = coord
                        return True
            
            # Tercero: Buscar cualquier coordinador activo y preguntar por el líder
            for coord in self.coordinators:
                if coord.failures < self.MAX_FAILURES_BEFORE_SKIP:
                    if self._check_coordinator_health(coord):
                        # Preguntar a este coordinador quién es el líder
                        leader = self._ask_for_leader(coord)
                        if leader and leader != coord:
                            if self._check_coordinator_health(leader):
                                self.logger.info(f"✅ Redirigido al LÍDER: {leader.address}")
                                self.current_coordinator = leader
                                return True
                        # Si no hay líder conocido, usar este coordinador
                        self.logger.info(f"⚠️ Conectado a coordinador (no líder): {coord.address}")
                        self.current_coordinator = coord
                        return True
            
            # Cuarto: Resetear y reintentar todos
            for coord in self.coordinators:
                coord.failures = 0
                if self._check_coordinator_health(coord):
                    self.logger.info(f"⚠️ Reconectado a: {coord.address}")
                    self.current_coordinator = coord
                    return True
            
            self.logger.error("❌ No hay coordinadores disponibles")
            return False
    
    def _ask_for_leader(self, coord: CoordinatorInfo) -> Optional[CoordinatorInfo]:
        """Pregunta a un coordinador quién es el líder actual.
        
        Usa el endpoint 'health' para saber si coord es el líder,
        y luego 'get_coordinators' para obtener la dirección real del líder.
        
        Returns:
            CoordinatorInfo del líder actual, o None si no se puede determinar.
        """
        try:
            # Paso 1: Preguntar health para saber si este coord es el líder
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((coord.host, coord.port))
                
                request = {'action': 'health'}
                self._send_request(sock, request)
                response = self._receive_response(sock)
                
                if response and response.get('status') == 'ok':
                    is_leader = response.get('is_leader', False)
                    coord.is_leader = is_leader
                    
                    if is_leader:
                        return coord
                    
                    # Este coord no es líder, preguntar por la lista de coordinadores
                    # para encontrar al líder real
                    leader_id = response.get('current_leader')
                    if leader_id:
                        return self._resolve_leader_from_cluster(coord, leader_id)
        except Exception as e:
            self.logger.debug(f"Error preguntando líder a {coord.address}: {e}")
        return None
    
    def _resolve_leader_from_cluster(self, coord: CoordinatorInfo, leader_id: str) -> Optional[CoordinatorInfo]:
        """Consulta get_coordinators para resolver la dirección del líder por su ID."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((coord.host, coord.port))
                
                request = {'action': 'get_coordinators'}
                self._send_request(sock, request)
                response = self._receive_response(sock)
                
                if response and response.get('status') == 'success':
                    for c_info in response.get('coordinators', []):
                        c_id = c_info.get('coordinator_id', '')
                        c_host = c_info.get('host')
                        c_port = c_info.get('port', 5000)
                        c_is_leader = c_info.get('is_leader', False)
                        
                        if not c_host:
                            continue
                        
                        # Actualizar o agregar coordinador
                        self._merge_coordinators([c_info])
                        
                        # Si es el líder, devolver su info
                        if c_id == leader_id or c_is_leader:
                            # Buscar en nuestra lista actualizada
                            address = f"{c_host}:{c_port}"
                            for existing in self.coordinators:
                                if existing.address == address:
                                    existing.is_leader = True
                                    return existing
                            
                            # Si no existía, crear nuevo
                            new_leader = CoordinatorInfo(
                                host=c_host, port=c_port, is_leader=True
                            )
                            self.coordinators.append(new_leader)
                            self._save_coordinators()
                            return new_leader
        except Exception as e:
            self.logger.debug(f"Error resolviendo líder desde {coord.address}: {e}")
        return None
    
    def _check_coordinator_health(self, coord: CoordinatorInfo) -> bool:
        """Verifica si un coordinador está vivo"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((coord.host, coord.port))
                
                request = {'action': 'health'}
                self._send_request(sock, request)
                response = self._receive_response(sock)
                
                if response and response.get('status') == 'ok':
                    coord.is_alive = True
                    coord.last_check = time.time()
                    coord.failures = 0
                    coord.is_leader = response.get('is_leader', True)
                    return True
        except:
            pass
        
        coord.is_alive = False
        coord.failures += 1
        
        # Si falla, actualizar la lista de coordinadores consultando otros
        self._discover_coordinators_from_cluster()
        
        return False
    
    def _health_check_loop(self):
        """Verifica periódicamente la salud de los coordinadores y descubre nuevos.
        
        Cada LEADER_CHECK_INTERVAL segundos verifica si el líder cambió.
        Cada HEALTH_CHECK_INTERVAL segundos hace health check completo de todos.
        """
        last_full_check = 0
        
        while self._active:
            time.sleep(self.LEADER_CHECK_INTERVAL)
            
            # === Verificación de líder (frecuente) ===
            self._verify_and_switch_leader()
            
            # === Health check completo (menos frecuente) ===
            elapsed = time.time() - last_full_check
            if elapsed >= self.HEALTH_CHECK_INTERVAL:
                last_full_check = time.time()
                
                # Descubrir nuevos coordinadores del cluster
                self._discover_coordinators_from_cluster()
                
                # Verificar salud de todos los coordinadores
                for coord in self.coordinators:
                    if coord != self.current_coordinator:
                        self._check_coordinator_health(coord)
    
    def _verify_and_switch_leader(self):
        """Verifica si el coordinador actual sigue siendo el líder y cambia si es necesario.
        
        Se ejecuta frecuentemente para garantizar que siempre estemos conectados al líder.
        """
        if not self.current_coordinator:
            self._find_active_coordinator()
            return
        
        # 1. Verificar que el coordinador actual esté vivo
        if not self._check_coordinator_health(self.current_coordinator):
            self.logger.warning(f"⚠️ Coordinador actual caído: {self.current_coordinator.address}")
            self.current_coordinator = None
            self._find_active_coordinator()
            return
        
        # 2. Si el coordinador actual ya no es líder, buscar el nuevo líder
        if not self.current_coordinator.is_leader:
            self.logger.info(f"🔄 Coordinador actual {self.current_coordinator.address} ya no es líder, buscando nuevo líder...")
            leader = self._ask_for_leader(self.current_coordinator)
            if leader and leader != self.current_coordinator:
                if self._check_coordinator_health(leader):
                    old_addr = self.current_coordinator.address
                    self.current_coordinator = leader
                    self.logger.info(f"✅ Cambiado de {old_addr} al nuevo LÍDER: {leader.address}")
                    return
            # Si no se encontró líder por ask, buscar en toda la lista
            self._find_active_coordinator()
            return
        
        # 3. Incluso si creemos que es líder, confirmar periódicamente
        #    preguntando a otro coordinador para detectar split-brain
        for coord in self.coordinators:
            if coord != self.current_coordinator and coord.is_alive and coord.failures < self.MAX_FAILURES_BEFORE_SKIP:
                leader = self._ask_for_leader(coord)
                if leader and leader != self.current_coordinator and leader.is_leader:
                    # Otro coordinador reporta un líder diferente
                    if self._check_coordinator_health(leader):
                        old_addr = self.current_coordinator.address
                        self.current_coordinator = leader
                        self.logger.info(f"🔄 Líder cambió: {old_addr} → {leader.address}")
                break  # Solo necesitamos consultar a uno
    
    def _discover_coordinators_from_cluster(self):
        """Pregunta a cualquier coordinador conocido por la lista actualizada de peers"""
        for coord in self.coordinators:
            if coord.failures >= self.MAX_FAILURES_BEFORE_SKIP:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5)
                    sock.connect((coord.host, coord.port))
                    
                    request = {'action': 'get_coordinators'}
                    self._send_request(sock, request)
                    response = self._receive_response(sock)
                    
                    if response and response.get('status') == 'success':
                        new_coords = response.get('coordinators', [])
                        self._merge_coordinators(new_coords)
                        return  # Solo necesitamos preguntar a uno
            except Exception as e:
                self.logger.debug(f"Error descubriendo desde {coord.address}: {e}")
                continue
    
    def _merge_coordinators(self, new_coords: List[dict]):
        """Agrega nuevos coordinadores descubiertos a la lista y los persiste"""
        added_new = False
        with self._lock:
            existing_addresses = {c.address for c in self.coordinators}
            
            for coord_info in new_coords:
                host = coord_info.get('host')
                port = coord_info.get('port', 5000)
                is_leader = coord_info.get('is_leader', False)
                
                if not host:
                    continue
                
                address = f"{host}:{port}"
                
                if address not in existing_addresses:
                    new_coord = CoordinatorInfo(
                        host=host,
                        port=port,
                        is_leader=is_leader
                    )
                    self.coordinators.append(new_coord)
                    self.logger.info(f"🔍 Nuevo coordinador descubierto: {address}")
                    existing_addresses.add(address)
                    added_new = True
                else:
                    # Actualizar info de líder en coordinadores existentes
                    for existing in self.coordinators:
                        if existing.address == address:
                            existing.is_leader = is_leader
                            break
        
        # Persistir si se agregaron nuevos coordinadores
        if added_new:
            self._save_coordinators()
    
    def _send_request(self, sock: socket.socket, request: dict):
        """Envía una request al coordinador"""
        req_json = json.dumps(request)
        sock.sendall(f"{len(req_json):<8}".encode())
        sock.sendall(req_json.encode())
    
    def _receive_response(self, sock: socket.socket) -> Optional[dict]:
        """Recibe una respuesta del coordinador"""
        try:
            length_data = sock.recv(8)
            if not length_data:
                return None
            
            msg_len = int(length_data.decode().strip())
            data = b''
            while len(data) < msg_len:
                chunk = sock.recv(min(4096, msg_len - len(data)))
                if not chunk:
                    break
                data += chunk
            
            return json.loads(data.decode())
        except:
            return None
    
    def _execute_with_failover(self, request: dict) -> Optional[dict]:
        """Ejecuta una request con soporte de failover y redirección al líder.
        
        Si un coordinador responde con 'redirect', el cliente se reconecta
        automáticamente al líder indicado y reintenta la petición.
        """
        for attempt in range(self.MAX_RETRIES):
            if not self.current_coordinator:
                if not self._find_active_coordinator():
                    return {'status': 'error', 'message': 'No hay coordinadores disponibles'}
            
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(10)
                    sock.connect((
                        self.current_coordinator.host,
                        self.current_coordinator.port
                    ))
                    
                    self._send_request(sock, request)
                    response = self._receive_response(sock)
                    
                    if response:
                        # Manejar redirección al líder
                        if response.get('status') == 'redirect':
                            leader_host = response.get('leader_host')
                            leader_port = response.get('leader_port')
                            if leader_host and leader_port:
                                self.logger.info(
                                    f"↪️ Redirigido al líder: {leader_host}:{leader_port}"
                                )
                                # Marcar el actual como no-líder
                                self.current_coordinator.is_leader = False
                                # Buscar o crear el coordinador líder
                                leader = self._get_or_create_coordinator(
                                    leader_host, int(leader_port)
                                )
                                leader.is_leader = True
                                if self._check_coordinator_health(leader):
                                    self.current_coordinator = leader
                                    # Reintentar inmediatamente con el líder
                                    continue
                                else:
                                    self.current_coordinator = None
                                    continue
                            else:
                                # Redirect sin dirección, buscar líder
                                self.current_coordinator.is_leader = False
                                self.current_coordinator = None
                                continue
                        
                        return response
                    
            except Exception:
                if self.current_coordinator:
                    self.current_coordinator.failures += 1
                    self.current_coordinator.is_alive = False
                self.current_coordinator = None
                
                delay = self.RETRY_DELAY * (2 ** attempt)
                time.sleep(delay)
        
        return {'status': 'error', 'message': 'Todos los reintentos fallaron'}
    
    def _get_or_create_coordinator(self, host: str, port: int) -> CoordinatorInfo:
        """Busca un coordinador existente por dirección o crea uno nuevo."""
        address = f"{host}:{port}"
        with self._lock:
            for coord in self.coordinators:
                if coord.address == address:
                    return coord
            
            new_coord = CoordinatorInfo(host=host, port=port)
            self.coordinators.append(new_coord)
            self.logger.info(f"🔍 Nuevo coordinador descubierto por redirect: {address}")
            self._save_coordinators()
            return new_coord
    
    # ========================================================================
    # API compatible con SearchClient (usado por SearchEngineGUI)
    # ========================================================================
    
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict]:
        """
        Busca archivos en el sistema distribuido.
        
        Returns:
            Lista de resultados (compatible con SearchClient)
        """
        request = {
            'action': 'search',
            'query': query,
            'file_type': file_type
        }
        response = self._execute_with_failover(request)
        
        if response and response.get('status') == 'success':
            return response.get('results', [])
        return []
    
    def list_files(self) -> List[Dict]:
        """
        Lista todos los archivos indexados.
        
        Returns:
            Lista de archivos (compatible con SearchClient)
        """
        request = {'action': 'list'}
        response = self._execute_with_failover(request)
        
        if response and response.get('status') == 'success':
            return response.get('files', [])
        return []
    
    def index_file(self, file_path: str) -> bool:
        """
        Indexa un archivo en el sistema distribuido.
        
        Args:
            file_path: Ruta local del archivo
            
        Returns:
            True si fue exitoso
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return False
        
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            file_content_b64 = base64.b64encode(file_content).decode()
            
            # Paso 1: Preguntar al coordinador dónde almacenar
            request = {
                'action': 'store',
                'file_name': file_path_obj.name,
                'file_size': len(file_content),
                'file_content': file_content_b64
            }
            response = self._execute_with_failover(request)
            
            return response and response.get('status') == 'success'
            
        except Exception:
            return False
    
    def download_file(self, file_id: str, destination: str) -> bool:
        """
        Descarga un archivo del sistema distribuido.
        
        Args:
            file_id: Nombre del archivo
            destination: Directorio de destino
            
        Returns:
            True si fue exitoso
        """
        try:
            # Paso 1: Obtener ubicaciones
            request = {
                'action': 'download',
                'file_id': file_id
            }
            response = self._execute_with_failover(request)
            
            if not response or response.get('status') != 'success':
                return False
            
            file_content_b64 = response.get('file_content')
            if not file_content_b64:
                return False
            
            file_content = base64.b64decode(file_content_b64)
            
            # Guardar archivo
            dest_path = Path(destination)
            if dest_path.is_dir():
                dest_path = dest_path / file_id
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(dest_path, 'wb') as f:
                f.write(file_content)
            
            return True
            
        except Exception:
            return False
    
    def get_cluster_status(self) -> dict:
        """Obtiene el estado del cluster"""
        request = {'action': 'cluster_status'}
        return self._execute_with_failover(request) or {}
    
    def get_coordinators_status(self) -> List[dict]:
        """Obtiene el estado de todos los coordinadores conocidos"""
        return [
            {
                'address': coord.address,
                'is_leader': coord.is_leader,
                'is_alive': coord.is_alive,
                'is_current': coord == self.current_coordinator,
                'failures': coord.failures
            }
            for coord in self.coordinators
        ]
    
    def close(self):
        """Cierra el cliente"""
        self._active = False


class SearchEngineGUI:
    """
    Graphical User Interface for the Distributed Search Engine
    Conecta al sistema distribuido con soporte de failover automático
    """
    
    def __init__(self, coordinator_addresses: List[str] = None, host: str = 'localhost', port: int = 5000):
        """
        Initialize the GUI
        
        Args:
            coordinator_addresses: Lista de "host:port" de coordinadores (opcional)
                                   Si no se proporciona, usa descubrimiento automático
            host: Host del coordinador (ignorado si se usa descubrimiento)
            port: Puerto del coordinador (ignorado si se usa descubrimiento)
        """
        # Usar coordinadores configurados o descubrimiento automático
        if coordinator_addresses:
            self.coordinator_addresses = coordinator_addresses
        elif host != 'localhost' or port != 5000:
            # Si se especifican host/port diferentes, usarlos
            self.coordinator_addresses = [f"{host}:{port}"]
        else:
            # Usar descubrimiento automático (None)
            self.coordinator_addresses = None
        
        self.client: Optional[DistributedClient] = None
        self.search_results: List[Dict] = []
        
        # Configure customtkinter appearance
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
        
        # Create main window
        self.root = ctk.CTk() if CTK_AVAILABLE else tk.Tk()
        self.root.title("🔍 Motor de Búsqueda Distribuida")
        self.root.geometry("1100x750")
        
        # Try to connect to coordinators
        self._connect_to_cluster()
        
        # Setup UI
        self._setup_ui()
        
    def _connect_to_cluster(self):
        """Conectar al cluster de coordinadores (usando semillas + persistidos)"""
        try:
            # Combinar coordinadores configurados + persistidos
            all_coords = set()
            if self.coordinator_addresses:
                all_coords.update(self.coordinator_addresses)
            
            # Agregar coordinadores persistidos
            persisted = DistributedClient.load_persisted_coordinators()
            all_coords.update(persisted)
            
            if all_coords:
                self.client = DistributedClient(list(all_coords))
            else:
                # Descubrimiento automático
                self.client = DistributedClient()
            
            if self.client.current_coordinator:
                coord = self.client.current_coordinator
                print(f"✓ Conectado al coordinador {coord.address}" + 
                      (" (líder)" if coord.is_leader else ""))
                print(f"  Total de coordinadores disponibles: {len(self.client.coordinators)}")
            else:
                print("⚠ Cliente creado pero sin coordinador activo")
        except Exception as e:
            print(f"⚠ Error conectando al cluster: {e}")
            self.client = None
    
    def _setup_ui(self):
        """Setup the user interface"""
        # Main container with padding
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="🔍 Motor de Búsqueda Distribuida",
            font=ctk.CTkFont(size=24, weight="bold") if CTK_AVAILABLE else ("Arial", 24, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Connection status frame
        self._setup_status_frame(main_frame)
        
        # Search Frame
        self._setup_search_frame(main_frame)
        
        # Results Frame
        self._setup_results_frame(main_frame)
        
        # Action Buttons Frame
        self._setup_action_frame(main_frame)
        
        # Log Frame
        self._setup_log_frame(main_frame)
    
    def _setup_status_frame(self, parent):
        """Setup cluster status frame"""
        status_frame = ctk.CTkFrame(parent)
        status_frame.pack(fill="x", pady=(0, 10))
        
        # Estado de conexión
        if self.client and self.client.current_coordinator:
            coord = self.client.current_coordinator
            status_text = f"✓ Conectado a {coord.address}"
            if coord.is_leader:
                status_text += " (Líder)"
            status_color = "green"
        else:
            status_text = "✗ Desconectado"
            status_color = "red"
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text=status_text,
            text_color=status_color if CTK_AVAILABLE else None
        )
        self.status_label.pack(side="left", padx=10)
        
        # Botón para ver estado del cluster
        self.cluster_status_btn = ctk.CTkButton(
            status_frame,
            text="📊 Estado Cluster",
            command=self._show_cluster_status,
            width=130
        )
        self.cluster_status_btn.pack(side="right", padx=10)
        
        # Botón reconectar
        self.reconnect_btn = ctk.CTkButton(
            status_frame,
            text="🔄 Reconectar",
            command=self._on_reconnect,
            width=110
        )
        self.reconnect_btn.pack(side="right", padx=5)
    
    def _show_cluster_status(self):
        """Muestra el estado del cluster en una ventana emergente"""
        if not self.client:
            messagebox.showerror("Error", "No hay cliente conectado")
            return
        
        # Crear ventana de estado
        status_window = ctk.CTkToplevel(self.root) if CTK_AVAILABLE else tk.Toplevel(self.root)
        status_window.title("Estado del Cluster")
        status_window.geometry("500x400")
        status_window.transient(self.root)
        
        # Obtener estado de coordinadores
        coord_status = self.client.get_coordinators_status()
        
        # Título
        ctk.CTkLabel(
            status_window,
            text="🖥️ Estado de Coordinadores",
            font=ctk.CTkFont(size=18, weight="bold") if CTK_AVAILABLE else ("Arial", 18, "bold")
        ).pack(pady=10)
        
        # Lista de coordinadores
        for coord in coord_status:
            frame = ctk.CTkFrame(status_window)
            frame.pack(fill="x", padx=10, pady=5)
            
            # Icono de estado
            if coord['is_current']:
                icon = "🟢"
            elif coord['is_alive']:
                icon = "🟡"
            else:
                icon = "🔴"
            
            role = " (Líder)" if coord['is_leader'] else ""
            current = " ← Actual" if coord['is_current'] else ""
            
            text = f"{icon} {coord['address']}{role}{current}"
            ctk.CTkLabel(frame, text=text).pack(side="left", padx=10)
            
            if coord['failures'] > 0:
                ctk.CTkLabel(
                    frame, 
                    text=f"Fallos: {coord['failures']}",
                    text_color="orange" if CTK_AVAILABLE else None
                ).pack(side="right", padx=10)
        
        # Intentar obtener estado del cluster
        try:
            cluster_info = self.client.get_cluster_status()
            if cluster_info and cluster_info.get('status') == 'success':
                ctk.CTkLabel(
                    status_window,
                    text="\n📁 Información del Cluster",
                    font=ctk.CTkFont(size=16, weight="bold") if CTK_AVAILABLE else ("Arial", 16, "bold")
                ).pack(pady=10)
                
                info_frame = ctk.CTkFrame(status_window)
                info_frame.pack(fill="x", padx=10, pady=5)
                
                nodes = cluster_info.get('nodes', [])
                files = cluster_info.get('total_files', 0)
                
                ctk.CTkLabel(info_frame, text=f"Nodos de procesamiento: {len(nodes)}").pack(anchor="w", padx=10)
                ctk.CTkLabel(info_frame, text=f"Archivos totales: {files}").pack(anchor="w", padx=10)
                
                # Mostrar detalles de nodos de procesamiento
                if nodes:
                    ctk.CTkLabel(
                        status_window,
                        text="\n⚙️ Nodos de Procesamiento",
                        font=ctk.CTkFont(size=14, weight="bold") if CTK_AVAILABLE else ("Arial", 14, "bold")
                    ).pack(pady=5)
                    
                    for node in nodes:
                        node_frame = ctk.CTkFrame(status_window)
                        node_frame.pack(fill="x", padx=10, pady=2)
                        node_id = node.get('node_id', 'unknown')
                        host = node.get('host', 'unknown')
                        port = node.get('port', 5000)
                        # files_count viene directamente del NodeInfo.to_dict()
                        files_count = node.get('files_count', 0)
                        current_tasks = node.get('current_tasks', 0)
                        ctk.CTkLabel(node_frame, text=f"   📦 {node_id} ({host}:{port}) - {files_count} archivos, {current_tasks} tareas").pack(anchor="w", padx=10)
        except:
            pass
        
        # Botones de acción
        btn_frame = ctk.CTkFrame(status_window)
        btn_frame.pack(pady=20)

        # Botón Agregar Coordinador Manual
        ctk.CTkButton(
            btn_frame,
            text="➕ Agregar IP",
            command=self._on_add_coordinator_click,
            width=100
        ).pack(side="left", padx=10)
        
        # Botón refrescar
        ctk.CTkButton(
            btn_frame,
            text="🔄 Refrescar",
            command=lambda: [status_window.destroy(), self._show_cluster_status()],
            width=100
        ).pack(side="left", padx=10)
        
        # Botón cerrar
        ctk.CTkButton(
            btn_frame,
            text="Cerrar",
            command=status_window.destroy,
            width=100
        ).pack(side="left", padx=10)

    def _on_add_coordinator_click(self):
        """Muestra diálogo para agregar coordinador manual"""
        dialog = ctk.CTkInputDialog(
            text="Ingrese IP:PUERTO del coordinador:\n(Ej: 192.168.1.50:5000 o coordinator1:5000)",
            title="Agregar Coordinador"
        )
        addr = dialog.get_input()
        if addr:
            try:
                parts = addr.split(':')
                host = parts[0]
                port = int(parts[1]) if len(parts) > 1 else 5000
                
                if self.client:
                    self.client.add_manual_coordinator(host, port)
                    messagebox.showinfo("Éxito", f"Coordinador {host}:{port} agregado.")
                else:
                    # Si no había cliente, crearlo ahora
                    self.coordinator_addresses = [f"{host}:{port}"]
                    self._connect_to_cluster()
                    if self.client:
                        messagebox.showinfo("Éxito", f"Cliente iniciado con {host}:{port}")
            except Exception as e:
                messagebox.showerror("Error", f"Formato inválido: {e}")

    def _setup_search_frame(self, parent):
        """Setup search input frame"""
        search_frame = ctk.CTkFrame(parent)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Search input
        ctk.CTkLabel(search_frame, text="Búsqueda:").pack(side="left", padx=(10, 5))
        
        self.search_entry = ctk.CTkEntry(search_frame, width=400, placeholder_text="Ingresa tu búsqueda...")
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self._on_search())
        
        # File type filter
        ctk.CTkLabel(search_frame, text="Tipo:").pack(side="left", padx=(20, 5))
        
        self.file_type_entry = ctk.CTkEntry(search_frame, width=100, placeholder_text=".txt")
        self.file_type_entry.pack(side="left", padx=5)
        
        # Search button
        self.search_btn = ctk.CTkButton(
            search_frame,
            text="🔍 Buscar",
            command=self._on_search,
            width=100
        )
        self.search_btn.pack(side="left", padx=10)
        
        # List all button
        self.list_btn = ctk.CTkButton(
            search_frame,
            text="📋 Listar Todo",
            command=self._on_list_all,
            width=120
        )
        self.list_btn.pack(side="left", padx=5)
    
    def _setup_results_frame(self, parent):
        """Setup results display frame"""
        results_frame = ctk.CTkFrame(parent)
        results_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        ctk.CTkLabel(
            results_frame,
            text="Resultados:",
            font=ctk.CTkFont(size=14, weight="bold") if CTK_AVAILABLE else ("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Results text area with scrollbar
        if CTK_AVAILABLE:
            self.results_text = ctk.CTkTextbox(results_frame, height=300)
        else:
            self.results_text = scrolledtext.ScrolledText(results_frame, height=15)
        
        self.results_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.results_text.configure(state="disabled")
    
    def _setup_action_frame(self, parent):
        """Setup action buttons frame"""
        action_frame = ctk.CTkFrame(parent)
        action_frame.pack(fill="x", pady=(0, 10))
        
        # Download frame
        download_frame = ctk.CTkFrame(action_frame)
        download_frame.pack(side="left", padx=10, pady=10)
        
        ctk.CTkLabel(download_frame, text="Descargar archivo:").pack(side="left", padx=5)
        
        self.download_entry = ctk.CTkEntry(download_frame, width=300, placeholder_text="Nombre del archivo")
        self.download_entry.pack(side="left", padx=5)
        
        self.download_btn = ctk.CTkButton(
            download_frame,
            text="📥 Descargar",
            command=self._on_download,
            width=120
        )
        self.download_btn.pack(side="left", padx=5)
        
        # Index file button
        self.index_btn = ctk.CTkButton(
            action_frame,
            text="📂 Indexar Archivo",
            command=self._on_index_file,
            width=150
        )
        self.index_btn.pack(side="left", padx=10, pady=10)
        
        # Reconnect button
        self.reconnect_btn = ctk.CTkButton(
            action_frame,
            text="🔄 Reconectar",
            command=self._on_reconnect,
            width=120
        )
        self.reconnect_btn.pack(side="right", padx=10, pady=10)
    
    def _setup_log_frame(self, parent):
        """Setup log display frame"""
        log_frame = ctk.CTkFrame(parent)
        log_frame.pack(fill="x")
        
        ctk.CTkLabel(
            log_frame,
            text="Registro:",
            font=ctk.CTkFont(size=12, weight="bold") if CTK_AVAILABLE else ("Arial", 12, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        if CTK_AVAILABLE:
            self.log_text = ctk.CTkTextbox(log_frame, height=100)
        else:
            self.log_text = scrolledtext.ScrolledText(log_frame, height=5)
        
        self.log_text.pack(fill="x", padx=10, pady=(0, 10))
        self.log_text.configure(state="disabled")
    
    def _log(self, message: str, level: str = "INFO"):
        """
        Add message to log
        
        Args:
            message: Message to log
            level: Log level (INFO, ERROR, SUCCESS)
        """
        self.log_text.configure(state="normal")
        
        # Color coding
        if CTK_AVAILABLE:
            if level == "ERROR":
                tag = "error"
                self.log_text.tag_config("error", foreground="red")
            elif level == "SUCCESS":
                tag = "success"
                self.log_text.tag_config("success", foreground="green")
            else:
                tag = "info"
                self.log_text.tag_config("info", foreground="white")
        else:
            tag = None
        
        timestamp = Path(__file__).stem  # Simple timestamp placeholder
        log_line = f"[{level}] {message}\n"
        
        if tag and CTK_AVAILABLE:
            self.log_text.insert("end", log_line, tag)
        else:
            self.log_text.insert("end", log_line)
        
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()
    
    def _display_results(self, results: List[Dict]):
        """
        Display search results
        
        Args:
            results: List of result dictionaries
        """
        self.search_results = results
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        
        if not results:
            self.results_text.insert("end", "No se encontraron resultados.\n")
        else:
            self.results_text.insert("end", f"✓ Encontrados {len(results)} resultados:\n\n")
            
            for i, result in enumerate(results, 1):
                name = result.get('name', 'Unknown')
                path = result.get('path', 'Unknown')
                score = result.get('score', 0)
                size = result.get('size', 0) / 1024  # KB
                file_type = result.get('type', 'Unknown')
                
                self.results_text.insert("end", f"{i}. {name}\n")
                self.results_text.insert("end", f"   📄 Ruta: {path}\n")
                self.results_text.insert("end", f"   📊 Score: {score:.2f} | Tamaño: {size:.1f} KB | Tipo: {file_type}\n")
                self.results_text.insert("end", "\n")
        
        self.results_text.configure(state="disabled")
    
    def _on_search(self):
        """Handle search button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor.\nUsa 'Reconectar' para intentar de nuevo.")
            return
        
        query = self.search_entry.get().strip()
        file_type = self.file_type_entry.get().strip() or None
        
        # Permitir query vacía si hay file_type
        if not query and not file_type:
            self._log("Error: Ingresa un término de búsqueda o selecciona un tipo de archivo", "ERROR")
            messagebox.showwarning("Advertencia", "Por favor ingresa un término de búsqueda o selecciona un tipo de archivo")
            return
        
        self._log(f"Buscando: '{query or '*'}'" + (f" (tipo: {file_type})" if file_type else ""))
        
        # Run search in thread to avoid blocking UI
        threading.Thread(target=self._search_thread, args=(query, file_type), daemon=True).start()
    
    def _search_thread(self, query: str, file_type: Optional[str]):
        """
        Run search in background thread
        
        Args:
            query: Search query
            file_type: Optional file type filter
        """
        try:
            results = self.client.search(query, file_type)
            self.root.after(0, self._display_results, results)
            self.root.after(0, self._log, f"Búsqueda completada: {len(results)} resultados", "SUCCESS")
        except Exception as e:
            self.root.after(0, self._log, f"Error en búsqueda: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al buscar: {e}")
    
    def _on_list_all(self):
        """Handle list all button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        self._log("Listando todos los archivos...")
        threading.Thread(target=self._list_all_thread, daemon=True).start()
    
    def _list_all_thread(self):
        """Run list all in background thread"""
        try:
            files = self.client.list_files()
            self.root.after(0, self._display_results, files)
            self.root.after(0, self._log, f"Listado completado: {len(files)} archivos", "SUCCESS")
        except Exception as e:
            self.root.after(0, self._log, f"Error al listar: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al listar: {e}")
    
    def _on_download(self):
        """Handle download button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        file_name = self.download_entry.get().strip()
        if not file_name:
            self._log("Error: Debes especificar el nombre del archivo", "ERROR")
            messagebox.showwarning("Advertencia", "Por favor ingresa el nombre del archivo a descargar")
            return
        
        # Ask for destination directory
        dest_dir = filedialog.askdirectory(title="Selecciona el directorio de destino")
        if not dest_dir:
            return
        
        self._log(f"Descargando '{file_name}' a '{dest_dir}'...")
        threading.Thread(target=self._download_thread, args=(file_name, dest_dir), daemon=True).start()
    
    def _download_thread(self, file_name: str, dest_dir: str):
        """
        Run download in background thread
        
        Args:
            file_name: Name of file to download
            dest_dir: Destination directory
        """
        try:
            success = self.client.download_file(file_name, dest_dir)
            if success:
                dest_path = Path(dest_dir) / file_name
                size = dest_path.stat().st_size / 1024 if dest_path.exists() else 0
                self.root.after(0, self._log, f"✓ Descarga exitosa: {file_name} ({size:.1f} KB)", "SUCCESS")
                self.root.after(0, messagebox.showinfo, "Éxito", f"Archivo descargado:\n{dest_path}")
            else:
                self.root.after(0, self._log, f"Error al descargar {file_name}", "ERROR")
                self.root.after(0, messagebox.showerror, "Error", "No se pudo descargar el archivo")
        except Exception as e:
            self.root.after(0, self._log, f"Error en descarga: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al descargar: {e}")
    
    def _on_index_file(self):
        """Handle index file button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        # Ask for file to index
        file_path = filedialog.askopenfilename(title="Selecciona el archivo a indexar")
        if not file_path:
            return
        
        self._log(f"Indexando '{file_path}'...")
        threading.Thread(target=self._index_thread, args=(file_path,), daemon=True).start()
    
    def _index_thread(self, file_path: str):
        """
        Run index in background thread
        
        Args:
            file_path: Path to file to index
        """
        try:
            success = self.client.index_file(file_path)
            if success:
                self.root.after(0, self._log, f"✓ Archivo indexado: {Path(file_path).name}", "SUCCESS")
                self.root.after(0, messagebox.showinfo, "Éxito", f"Archivo indexado correctamente:\n{Path(file_path).name}")
            else:
                self.root.after(0, self._log, f"Error al indexar {file_path}", "ERROR")
                self.root.after(0, messagebox.showerror, "Error", "No se pudo indexar el archivo")
        except Exception as e:
            self.root.after(0, self._log, f"Error al indexar: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al indexar: {e}")
    
    def _on_reconnect(self):
        """Handle reconnect button click - usa coordinadores actuales + persistidos"""
        self._log("Intentando reconectar al cluster...")
        
        # Obtener coordinadores actuales antes de cerrar
        current_coords = []
        if self.client:
            current_coords = [c.address for c in self.client.coordinators]
            self.client.close()
        
        # Combinar: coordinadores actuales + persistidos + semillas originales
        all_coords = set(current_coords)
        all_coords.update(DistributedClient.load_persisted_coordinators())
        if self.coordinator_addresses:
            all_coords.update(self.coordinator_addresses)
        
        # Crear nuevo cliente con todos los coordinadores conocidos
        try:
            if all_coords:
                self.client = DistributedClient(list(all_coords))
            else:
                self.client = DistributedClient()
        except Exception as e:
            self._log(f"Error creando cliente: {e}", "ERROR")
            self.client = None
        
        if self.client and self.client.current_coordinator:
            coord = self.client.current_coordinator
            status_text = f"✓ Conectado a {coord.address}"
            if coord.is_leader:
                status_text += " (Líder)"
            self.status_label.configure(text=status_text, text_color="green" if CTK_AVAILABLE else None)
            self._log(f"✓ Reconexión exitosa ({len(self.client.coordinators)} coordinadores conocidos)", "SUCCESS")
            messagebox.showinfo("Éxito", f"Reconectado al coordinador:\n{coord.address}\n\nCoordinadores conocidos: {len(self.client.coordinators)}")
        else:
            self.status_label.configure(text="✗ Desconectado", text_color="red" if CTK_AVAILABLE else None)
            self._log("Error al reconectar", "ERROR")
            messagebox.showerror("Error", "No se pudo conectar a ningún coordinador\n\nVerifica que el cluster esté en ejecución.")
    
    def run(self):
        """Run the GUI application"""
        self.root.mainloop()
        # Cleanup on exit
        if self.client:
            self.client.close()


def main():
    """Main function"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='GUI Client for Distributed Search Engine')
    parser.add_argument('--config', type=str, default='config/client_config.json', help='Configuration file')
    parser.add_argument('--coordinators', type=str, nargs='+', 
                        help='Lista de coordinadores (host:port). Ej: --coordinators node1:5000 node2:5000')
    parser.add_argument('--host', type=str, help='Host del coordinador principal (fallback)')
    parser.add_argument('--port', type=int, help='Puerto del coordinador principal (fallback)')
    
    args = parser.parse_args()
    
    # Load configuration
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent
    config_path = ROOT_DIR / args.config if not Path(args.config).is_absolute() else args.config
    
    config = Config(str(config_path))
    
    # Setup logging
    log_config = config.get('logging', default={})
    setup_logging(
        level=log_config.get('level', 'INFO'),
        log_file=log_config.get('file'),
        log_format=log_config.get('format')
    )
    
    # Determinar coordinadores
    coordinator_addresses = None
    
    # 1. Desde argumentos --coordinators
    if args.coordinators:
        coordinator_addresses = args.coordinators
    
    # 2. Desde variable de entorno
    elif os.environ.get('COORDINATOR_ADDRESSES'):
        coordinator_addresses = os.environ.get('COORDINATOR_ADDRESSES').split(',')
    
    # 3. Desde configuración (nueva sección 'distributed')
    elif config.get('distributed', default={}):
        dist_config = config.get('distributed', default={})
        coordinator_addresses = dist_config.get('coordinators', [])
    
    # 4. Si aún no hay coordinadores, usar descubrimiento automático
    # (None indica descubrimiento automático en Docker Swarm)
    
    if coordinator_addresses:
        print(f"🔗 Coordinadores configurados: {coordinator_addresses}")
    else:
        print("🔍 Usando descubrimiento automático de coordinadores en Docker Swarm...")
        print("   Buscando servicio 'search_coordinator' en la red")
    
    # Create and run GUI
    app = SearchEngineGUI(coordinator_addresses=coordinator_addresses)
    app.run()


if __name__ == '__main__':
    main()
