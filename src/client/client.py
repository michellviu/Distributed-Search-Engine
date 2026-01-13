"""
Client implementation for search requests
"""

import socket
import logging
import json
import os
import random
import time
import threading
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

# Add project root to sys.path to find modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from client.coordinator_discovery import CoordinatorDiscovery


def get_server_address():
    """
    Obtiene la dirección del servidor desde variables de entorno.
    Esto permite que el cliente sea transparente al sistema distribuido.
    
    En Docker Swarm, el cliente se conecta al load balancer o al DNS del servicio.
    El sistema distribuido es completamente transparente para el cliente.
    """
    host = os.environ.get('SEARCH_SERVER_HOST', 'localhost')
    port = int(os.environ.get('SEARCH_SERVER_PORT', '5000'))
    return host, port


class SearchClient:
    """
    Client for connecting to search server.
    
    El cliente es agnóstico al sistema distribuido - simplemente se conecta
    a un endpoint (que puede ser un load balancer o un nodo directo).
    """
    
    def __init__(self, server_host: str = None, server_port: int = None):
        """
        Initialize the search client
        
        Args:
            server_host: Server host address (default: from env SEARCH_SERVER_HOST or 'localhost')
            server_port: Server port number (default: from env SEARCH_SERVER_PORT or 5000)
        """
        default_host, default_port = get_server_address()
        self.server_host = server_host or default_host
        self.server_port = server_port or default_port
        self.logger = logging.getLogger(__name__)

        # ========== INICIO: LÓGICA DE FAILOVER Y DESCUBRIMIENTO ==========
        # Cargar configuración desde config/client_config.json
        self.config = self._load_config()
        
        # Lista inicial de coordinadores
        potential_coordinators = []
        if server_host: 
            potential_coordinators.append(f"{server_host}:{server_port}")
            
        # Añadir desde configuración
        config_coords = self.config.get('distributed', {}).get('coordinators', [])
        potential_coordinators.extend(config_coords)
        
        # Inicializar el servicio de discovery
        self.discovery = CoordinatorDiscovery(initial_addresses=potential_coordinators)
        self.current_coordinator: Optional[str] = None
        self._topology_updated = False
        
        # Iniciar thread de actualización periódica
        self._stop_refresh = False
        self._refresh_thread = threading.Thread(target=self._periodic_topology_refresh, daemon=True)
        self._refresh_thread.start()
        
        self._select_coordinator()
        # ========== FIN: LÓGICA DE FAILOVER Y DESCUBRIMIENTO ==========
      
    def _periodic_topology_refresh(self):
        """
        Consulta periódicamente al coordinador actual para descubrir nuevos nodos.
        Esto permite escalar el cluster dinámicamente y que el cliente se entere.
        """
        while not self._stop_refresh:
            time.sleep(10) # Refrescar cada 10 segundos
            
            if self.current_coordinator:
                try:
                    host, port_str = self.current_coordinator.split(':')
                    # self.logger.debug(f"Refrescando topología desde {host}:{port_str}")
                    if self.discovery.refresh_from_mid_stream(host, int(port_str)):
                        # Si encontramos nuevos coordinadores, se agregan automáticamente
                        pass
                except Exception as e:
                    # Si falla el refresh, no pasa nada, ya lo intentará el failover si falla el request principal
                    pass
    
    def shutdown(self):
        """Detiene los threads en segundo plano"""
        self._stop_refresh = True
        
    def _load_config(self) -> dict:
        """Carga la configuración desde json"""
        try:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'client_config.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"No se pudo cargar config: {e}")
        return {}

    def _select_coordinator(self) -> Optional[Tuple[str, int]]:
        """Selecciona un coordinador disponible del pool de conocidos"""
        known = list(self.discovery.get_coordinators())
        
        if not known:
            # Fallback a los defaults si no hay nada conocido
            return self.server_host, self.server_port
            
        if self.current_coordinator and self.current_coordinator in known:
            # Mantener el actual si funciona
            pass
        else:
            # Elegir uno nuevo al azar
            self.current_coordinator = random.choice(known)
            
        try:
            host, port_str = self.current_coordinator.split(':')
            return host, int(port_str)
        except:
            return self.server_host, self.server_port

    def _execute_with_failover(self, operation_name: str, func, *args, **kwargs) -> Any:
        """
        Ejecuta una operación de red con reintentos y cambio automático de coordinador.
        """
        # Intentar con varios nodos si el primero falla
        max_attempts = len(self.discovery.get_coordinators()) + 1
        attempts = 0
        last_error = None
        
        while attempts < max_attempts:
            host, port = self._select_coordinator()
            
            try:
                # self.logger.debug(f"Conectando a {host}:{port} para {operation_name}")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5.0)
                    sock.connect((host, port))
                    
                    # Intentar actualizar topología si es la primera vez que conectamos con éxito
                    if not self._topology_updated:
                        try:
                            # Hacemos esto en un thread para no bloquear la operación actual
                            import threading
                            threading.Thread(
                                target=lambda: self.discovery.refresh_from_mid_stream(host, port),
                                daemon=True
                            ).start()
                            self._topology_updated = True
                        except:
                            pass
                            
                    return func(sock, *args, **kwargs)
            
            except (socket.error, socket.timeout, ConnectionRefusedError) as e:
                self.logger.warning(f"Fallo conexión con {host}:{port} ({operation_name}): {e}")
                
                # Reportar fallo y cambiar coordinador
                self.discovery.report_failure(f"{host}:{port}")
                
                # Forzar cambio de coordinador
                known = list(self.discovery.get_coordinators())
                current = f"{host}:{port}"
                if current in known and len(known) > 1:
                    # Elegir temporalmente otro distinto al que falló
                    options = [c for c in known if c != current]
                    self.current_coordinator = random.choice(options)
                
                last_error = e
                attempts += 1
            
            except Exception as e:
                self.logger.error(f"Error irrecuperable en {operation_name}: {e}")
                raise e # Errores de lógica no activan failover
        
        self.logger.error(f"Operación {operation_name} falló tras {attempts} intentos. Último error: {last_error}")
        return None  # Señal de fallo total

    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict]:
        """
        Send search query to server with FAILOVER support
        """
        def _do_search(sock):
            request = {
                'action': 'search',
                'query': query
            }
            if file_type:
                request['file_type'] = file_type
            
            self._send_request(sock, request)
            response = self._receive_response(sock)
            
            if response.get('status') == 'success':
                self.logger.info(f"Search successful: {response.get('count', 0)} results")
                return response.get('results', [])
            else:
                self.logger.error(f"Search failed: {response.get('message', 'Unknown error')}")
                return []
        
        # Ejecutar con failover
        result = self._execute_with_failover('search', _do_search)
        return result if result is not None else []
    
    def index_file(self, file_path: str) -> bool:
        """
        Request server to index a file with FAILOVER support
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return False
            
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()
        except:
            return False

        def _do_index(sock):
            request = {
                'action': 'index',
                'file_name': file_path_obj.name,
                'file_size': len(file_content)
            }
            self._send_request(sock, request)
            sock.sendall(file_content)
            response = self._receive_response(sock)
            
            return response.get('status') == 'success'

        result = self._execute_with_failover('index', _do_index)
        return result if result is not None else False
    # ... (métodos originales se mantienen abajo si no coinciden) ...
        """
        Download file from server
        
        Args:
            file_id: Identifier of file to download (name or path)
            destination: Local path to save file
            
        Returns:
            True if successful, False otherwise
        """
        def _do_download(sock):
            # Create download request
            request = {
                'action': 'download',
                'file_id': file_id
            }
            
            # Send request
            self._send_request(sock, request)
            
            # Receive response
            response = self._receive_response(sock)
            
            if response.get('status') != 'success':
                self.logger.error(f"Download request failed: {response.get('message', 'Unknown error')}")
                return False
            
            # Receive the file
            file_info = response.get('file_info', {})
            file_name = file_info.get('name', 'downloaded_file')
            
            # Create destination path
            dest_path = Path(destination)
            if dest_path.is_dir():
                dest_path = dest_path / file_name
            
            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Receive file data
            self._receive_file(sock, str(dest_path))
            
            self.logger.info(f"File downloaded successfully: {dest_path}")
            return True

        result = self._execute_with_failover('download', _do_download)
        return result is True
    
    def list_files(self) -> List[Dict]:
        """
        Get list of all indexed files from server
        
        Returns:
            List of file information dictionaries
        """
        def _do_list(sock):
            # Create list request
            request = {
                'action': 'list'
            }
            
            # Send request
            self._send_request(sock, request)
            
            # Receive response
            response = self._receive_response(sock)
            
            if response.get('status') == 'success':
                self.logger.info(f"List successful: {response.get('count', 0)} files")
                return response.get('files', [])
            else:
                self.logger.error(f"List failed: {response.get('message', 'Unknown error')}")
                return []
        
        result = self._execute_with_failover('list', _do_list)
        return result if result is not None else []
    
    def _send_request(self, sock: socket.socket, request: Dict):
        """
        Send request to server
        
        Args:
            sock: Socket connection
            request: Request dictionary
        """
        request_json = json.dumps(request)
        request_bytes = request_json.encode('utf-8')
        
        # Send length first
        length_str = f"{len(request_bytes):<8}"
        sock.sendall(length_str.encode())
        
        # Send actual data
        sock.sendall(request_bytes)
    
    def _receive_response(self, sock: socket.socket) -> Dict:
        """
        Receive response from server
        
        Args:
            sock: Socket connection
            
        Returns:
            Response dictionary
        """
        # Receive length first
        length_data = sock.recv(8)
        if not length_data:
            return {'status': 'error', 'message': 'No response from server'}
        
        message_length = int(length_data.decode().strip())
        
        # Receive actual message
        data = b''
        while len(data) < message_length:
            chunk = sock.recv(min(4096, message_length - len(data)))
            if not chunk:
                break
            data += chunk
        
        return json.loads(data.decode('utf-8'))
    
    def _receive_file(self, sock: socket.socket, dest_path: str, chunk_size: int = 4096):
        """
        Receive file data from server
        
        Args:
            sock: Socket connection
            dest_path: Destination file path
            chunk_size: Size of chunks to receive
        """
        # Receive file size first
        size_data = sock.recv(16)
        if not size_data:
            raise Exception("Failed to receive file size")
        
        file_size = int(size_data.decode().strip())
        
        # Receive file name length and name
        name_len_data = sock.recv(4)
        name_length = int(name_len_data.decode().strip())
        file_name = sock.recv(name_length).decode('utf-8')
        
        # Receive file hash
        file_hash = sock.recv(64).decode('utf-8')
        
        # Receive file data
        received = 0
        with open(dest_path, 'wb') as f:
            while received < file_size:
                chunk = sock.recv(min(chunk_size, file_size - received))
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)
