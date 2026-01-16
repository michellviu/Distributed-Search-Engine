"""
Nodo de Procesamiento del sistema distribuido.

El nodo de procesamiento es responsable de:
1. Almacenar datos (archivos indexados)
2. Ejecutar búsquedas locales
3. Responder a queries del coordinador
4. Registrarse con el coordinador y enviar heartbeats
5. Replicar datos cuando el coordinador lo indique

IMPORTANTE: Los nodos de procesamiento SÍ almacenan datos.
"""
import sys
import os
import logging
import threading
import time
import socket
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.server import SearchServer, InMemoryDocumentRepository
from indexer.indexer import DocumentIndexer
from search.search_engine import SearchEngine
from transfer.file_transfer import FileTransfer
from client.coordinator_discovery import CoordinatorDiscovery


class ProcessingNode:
    """
    Nodo de Procesamiento del sistema distribuido.
    
    Responsabilidades:
    - Almacenar y indexar archivos
    - Ejecutar búsquedas locales
    - Responder a queries del coordinador
    - Mantener heartbeats con el coordinador
    
    SÍ almacena datos localmente.
    """
    
    # Configuración
    HEARTBEAT_INTERVAL = 5  # Segundos entre heartbeats al coordinador
    COORDINATOR_RETRY_INTERVAL = 10  # Segundos entre reintentos de conexión
    
    def __init__(self,
                 node_id: str,
                 host: str,
                 port: int,
                 index_path: str = 'shared_files',
                 data_path: str = None,
                 coordinator_host: str = None,
                 coordinator_port: int = 5000,
                 announce_host: str = None):
        """
        Inicializa el nodo de procesamiento.
        
        Args:
            node_id: ID único del nodo
            host: IP para bind (0.0.0.0 para todas las interfaces)
            port: Puerto TCP
            index_path: Directorio de archivos iniciales (lectura)
            data_path: Directorio para almacenar archivos (escritura, por defecto = index_path)
            coordinator_host: IP del coordinador (Semilla inicial)
            coordinator_port: Puerto del coordinador
            announce_host: IP para anunciarse al coordinador
        """
        self.node_id = node_id
        self.host = host
        self.port = port
        self.announce_host = announce_host or host
        self.index_path = index_path
        # Directorio para almacenar archivos recibidos (puede ser diferente del index_path)
        self.data_path = data_path or index_path
        
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        
        # Inicializar descubrimiento de coordinadores con la semilla proporcionada
        initial_seeds = []
        if coordinator_host:
            initial_seeds.append(f"{coordinator_host}:{coordinator_port}")
        
        self.discovery = CoordinatorDiscovery(initial_seeds)
        
        self.logger = logging.getLogger(f"ProcessingNode-{node_id}")
        
        # Crear directorios si no existen
        Path(index_path).mkdir(parents=True, exist_ok=True)
        Path(self.data_path).mkdir(parents=True, exist_ok=True)
        
        # Componentes de indexación y búsqueda
        self.indexer = DocumentIndexer(index_path)
        self.search_engine = SearchEngine(self.indexer)
        self.file_transfer = FileTransfer()
        self.repository = InMemoryDocumentRepository(self.indexer, self.search_engine)
        
        # Servidor TCP para recibir peticiones
        self.server = SearchServer(
            self.host,
            port,
            self.repository,
            self.file_transfer,
            node_id=node_id
        )
        
        # Estado
        self.active = False
        self.registered_with_coordinator = False
        self.current_load = 0  # Tareas en proceso
        self._lock = threading.RLock()
        
        # Estadísticas
        self.stats = {
            'searches_executed': 0,
            'files_indexed': 0,
            'files_stored': 0,
            'start_time': None
        }
        
        self.logger.info(f"📦 Nodo de procesamiento inicializado: {node_id}")
    
    def start(self):
        """Inicia el nodo de procesamiento"""
        self.active = True
        self.stats['start_time'] = time.time()
        
        self.logger.info("=" * 60)
        self.logger.info("   NODO DE PROCESAMIENTO INICIANDO")
        self.logger.info("=" * 60)
        self.logger.info(f"   ID:          {self.node_id}")
        self.logger.info(f"   Host:        {self.host}:{self.port}")
        self.logger.info(f"   Announce:    {self.announce_host}:{self.port}")
        self.logger.info(f"   Index Path:  {self.index_path}")
        self.logger.info(f"   Data Path:   {self.data_path}")
        if self.coordinator_host:
            self.logger.info(f"   Coordinator: {self.coordinator_host}:{self.coordinator_port}")
        self.logger.info("=" * 60)
        
        # 1. Indexar archivos existentes
        self._index_initial_files()
        
        # 2. Iniciar servidor TCP
        threading.Thread(target=self._start_server, daemon=True).start()
        self.logger.info("✅ Servidor TCP iniciado")
        
        # 3. Registrarse con el coordinador
        if self.coordinator_host:
            threading.Thread(target=self._coordinator_loop, daemon=True).start()
            self.logger.info("✅ Conexión con coordinador iniciada")
        
        self.logger.info("📦 Nodo de procesamiento listo")
        
        # Mantener vivo
        try:
            while self.active:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Detiene el nodo de procesamiento"""
        self.logger.info("🛑 Deteniendo nodo de procesamiento...")
        self.active = False
        self.server.stop()
        self.logger.info("👋 Nodo de procesamiento detenido")
    
    def _index_initial_files(self):
        """
        Indexa los archivos existentes en los directorios.
        
        Indexa desde:
        1. data_path: Archivos previamente almacenados por este nodo
        2. index_path: Archivos iniciales compartidos (si hay coordinador, pide asignación)
        """
        # 1. Indexar archivos del data_path (archivos propios de este nodo)
        if self.data_path != self.index_path:
            data_dir = Path(self.data_path)
            if data_dir.exists():
                data_files = [f for f in data_dir.iterdir() if f.is_file()]
                if data_files:
                    self.logger.info(f"📦 Indexando {len(data_files)} archivos del directorio de datos...")
                    for file_path in data_files:
                        try:
                            self.indexer.index_file(str(file_path))
                            self.stats['files_indexed'] += 1
                        except Exception as e:
                            self.logger.error(f"Error indexando {file_path}: {e}")
        
        # 2. Indexar archivos del index_path (archivos compartidos iniciales)
        shared_dir = Path(self.index_path)
        if not shared_dir.exists():
            self.logger.warning(f"⚠️ Directorio {self.index_path} no existe")
            return
        
        # Obtener lista de archivos disponibles localmente
        local_files = [f.name for f in shared_dir.iterdir() if f.is_file()]
        
        if not local_files:
            self.logger.info("📁 No hay archivos iniciales para indexar")
            return
        
        self.logger.info(f"📋 Archivos iniciales disponibles: {len(local_files)}")
        
        # Si hay coordinador, consultar qué archivos debemos indexar
        files_to_index = local_files
        if self.coordinator_host:
            assigned_files = self._request_file_assignment(local_files)
            if assigned_files is not None:
                files_to_index = assigned_files
                self.logger.info(f"🎯 Coordinador asignó {len(files_to_index)} archivos a este nodo")
            else:
                self.logger.warning("⚠️ No se pudo consultar al coordinador, indexando todos los archivos locales")
        
        # Indexar solo los archivos asignados
        count = 0
        for file_name in files_to_index:
            file_path = shared_dir / file_name
            if file_path.exists() and file_path.is_file():
                try:
                    self.indexer.index_file(str(file_path))
                    count += 1
                    self.logger.debug(f"📄 Indexado: {file_name}")
                except Exception as e:
                    self.logger.error(f"Error indexando {file_path}: {e}")
        
        self.stats['files_indexed'] += count
        self.logger.info(f"📁 Indexados {count} archivos del directorio {self.index_path}")
    
    def _request_file_assignment(self, available_files: List[str]) -> Optional[List[str]]:
        """
        Solicita al coordinador qué archivos de los disponibles debe indexar este nodo.
        
        El coordinador usa balanceo de carga para asignar archivos:
        - Archivos que nadie tiene: asigna a este nodo según replication_factor
        - Archivos que ya tienen otros nodos: no asigna (a menos que falten réplicas)
        
        Args:
            available_files: Lista de archivos disponibles localmente
            
        Returns:
            Lista de archivos que este nodo debe indexar, o None si falla
        """
        if not self.coordinator_host:
            return None
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((self.coordinator_host, self.coordinator_port))
                
                request = {
                    'action': 'request_file_assignment',
                    'node_id': self.node_id,
                    'available_files': available_files,
                    'host': self.announce_host,
                    'port': self.port
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = b''
                    while len(data) < msg_len:
                        chunk = sock.recv(min(4096, msg_len - len(data)))
                        if not chunk:
                            break
                        data += chunk
                    response = json.loads(data.decode())
                    
                    if response.get('status') == 'success':
                        return response.get('assigned_files', [])
                
        except Exception as e:
            self.logger.warning(f"⚠️ Error solicitando asignación de archivos: {e}")
        
        return None
    
    def _start_server(self):
        """Inicia el servidor TCP interno"""
        # Crear socket propio para mayor control
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(50)
        
        self.logger.info(f"🌐 Servidor escuchando en {self.host}:{self.port}")
        
        while self.active:
            try:
                server_socket.settimeout(1.0)
                try:
                    client_socket, address = server_socket.accept()
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
        
        server_socket.close()
    
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
        - search_local: Búsqueda local
        - search: Alias de search_local
        - store: Almacenar archivo
        - replicate: Recibir réplica
        - replicate_to: Replicar archivo a otro nodo
        - health: Health check
        - list: Listar archivos
        - get_peers: Para compatibilidad con discovery
        - status: Estado del nodo
        """
        action = request.get('action', '')
        
        if action in ['search_local', 'search']:
            return self._handle_search(request)
        
        elif action == 'store':
            return self._handle_store(request)
        
        elif action == 'replicate':
            return self._handle_replicate(request)
        
        elif action == 'replicate_to':
            return self._handle_replicate_to(request)
        
        elif action == 'health':
            return {
                'status': 'ok',
                'node_id': self.node_id,
                'node_type': 'processing',
                'load': self.current_load
            }
        
        elif action == 'list':
            return self._handle_list()
        
        elif action == 'get_peers':
            return self._handle_get_peers(request)
        
        elif action == 'status':
            return self._get_node_status()
        
        elif action == 'index':
            return self._handle_index(request)
        
        elif action == 'download':
            return self._handle_download(request)
        
        elif action == 'get_file':
            return self._handle_get_file(request)
        
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}
    
    def _handle_search(self, request: dict) -> dict:
        """Ejecuta una búsqueda local"""
        query = request.get('query', '')
        file_type = request.get('file_type')
        
        if not query:
            return {'status': 'error', 'message': 'Missing query', 'results': []}
        
        with self._lock:
            self.current_load += 1
        
        try:
            import time
            start = time.time()
            
            results = self.repository.search(query, file_type)
            
            elapsed = (time.time() - start) * 1000
            self.stats['searches_executed'] += 1
            
            return {
                'status': 'success',
                'query': query,
                'results': results,
                'count': len(results),
                'search_time_ms': elapsed,
                'node_id': self.node_id
            }
        finally:
            with self._lock:
                self.current_load -= 1
    
    def _handle_store(self, request: dict) -> dict:
        """Almacena un archivo recibido"""
        file_name = request.get('file_name')
        file_content_b64 = request.get('file_content')
        
        if not file_name or not file_content_b64:
            return {'status': 'error', 'message': 'Missing file_name or file_content'}
        
        try:
            import base64
            file_content = base64.b64decode(file_content_b64)
            
            # Guardar archivo en data_path (directorio de almacenamiento)
            file_path = Path(self.data_path) / file_name
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            # Indexar
            self.indexer.index_file(str(file_path))
            
            self.stats['files_stored'] += 1
            self.logger.info(f"📥 Archivo almacenado: {file_name}")
            
            # Notificar al coordinador que el archivo fue almacenado
            self._notify_coordinator_file_stored(file_name)
            
            return {
                'status': 'success',
                'message': f'File {file_name} stored and indexed',
                'node_id': self.node_id
            }
        except Exception as e:
            self.logger.error(f"Error almacenando archivo: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _notify_coordinator_file_stored(self, file_name: str):
        """Notifica al coordinador que un archivo fue almacenado en este nodo"""
        if not self.coordinator_host:
            return
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((self.coordinator_host, self.coordinator_port))
                
                request = {
                    'action': 'file_stored',
                    'file_name': file_name,
                    'node_id': self.node_id
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    self.logger.debug(f"📍 Coordinador notificado: {file_name}")
                    
        except Exception as e:
            self.logger.warning(f"⚠️ No se pudo notificar al coordinador: {e}")
    
    def _handle_replicate(self, request: dict) -> dict:
        """Recibe una réplica de otro nodo"""
        # Mismo comportamiento que store
        return self._handle_store(request)
    
    def _handle_replicate_to(self, request: dict) -> dict:
        """
        Replica un archivo local a otro nodo.
        
        Solicitado por el coordinador cuando necesita aumentar
        el factor de replicación de un archivo.
        """
        file_name = request.get('file_name')
        target_host = request.get('target_host')
        target_port = request.get('target_port', 5001)
        target_node_id = request.get('target_node_id', 'unknown')
        
        if not file_name or not target_host:
            return {'status': 'error', 'message': 'Missing file_name or target_host'}
        
        self.logger.info(f"📨 Recibida solicitud de replicación: '{file_name}' -> {target_node_id} ({target_host}:{target_port})")
        
        # Verificar que tenemos el archivo - buscar en múltiples ubicaciones
        file_path = None
        
        # 1. Buscar en index_path directamente
        candidate = Path(self.index_path) / file_name
        if candidate.exists() and candidate.is_file():
            file_path = candidate
        
        # 2. Buscar en data_path si es diferente
        if not file_path and self.data_path != self.index_path:
            candidate = Path(self.data_path) / file_name
            if candidate.exists() and candidate.is_file():
                file_path = candidate
        
        # 3. Buscar recursivamente en subdirectorios de index_path
        if not file_path:
            for candidate in Path(self.index_path).rglob(file_name):
                if candidate.is_file():
                    file_path = candidate
                    break
        
        # 4. Buscar recursivamente en subdirectorios de data_path
        if not file_path and self.data_path != self.index_path:
            for candidate in Path(self.data_path).rglob(file_name):
                if candidate.is_file():
                    file_path = candidate
                    break
        
        if not file_path:
            self.logger.error(f"❌ Archivo '{file_name}' no encontrado en ninguna ubicación (index_path={self.index_path}, data_path={self.data_path})")
            return {'status': 'error', 'message': f'File not found: {file_name}'}
        
        self.logger.info(f"📁 Archivo encontrado en: {file_path}")
        
        # Leer contenido y enviar al nodo destino
        try:
            import base64
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            file_content_b64 = base64.b64encode(file_content).decode()
            
            # Enviar al nodo destino
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30)
                sock.connect((target_host, target_port))
                
                replicate_request = {
                    'action': 'replicate',
                    'file_name': file_name,
                    'file_content': file_content_b64,
                    'source_node': self.node_id
                }
                
                req_json = json.dumps(replicate_request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                # Leer respuesta
                length_data = sock.recv(8)
                if length_data:
                    msg_len = int(length_data.decode().strip())
                    data = sock.recv(msg_len)
                    response = json.loads(data.decode())
                    
                    if response.get('status') == 'success':
                        self.logger.info(f"✅ Archivo '{file_name}' replicado exitosamente a {target_node_id}")
                        return {
                            'status': 'success',
                            'message': f'File replicated to {target_node_id}'
                        }
                    else:
                        error_msg = response.get('message', 'Unknown error')
                        self.logger.error(f"❌ Fallo al replicar '{file_name}' a {target_node_id}: {error_msg}")
                        return {'status': 'error', 'message': f'Target rejected: {error_msg}'}
            
            self.logger.error(f"❌ Sin respuesta de {target_node_id} al replicar '{file_name}'")
            return {'status': 'error', 'message': 'No response from target node'}
            
        except Exception as e:
            self.logger.error(f"❌ Error replicando '{file_name}' a {target_node_id}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _handle_list(self) -> dict:
        """Lista todos los archivos indexados"""
        try:
            files = self.repository.get_all_indexed_files()
            return {
                'status': 'success',
                'files': files,
                'count': len(files),
                'node_id': self.node_id
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def _handle_get_peers(self, request: dict) -> dict:
        """Para compatibilidad con discovery"""
        return {
            'status': 'success',
            'node_id': self.node_id,
            'node_type': 'processing',
            'peers': []  # Los nodos de procesamiento no conocen otros peers directamente
        }
    
    def _handle_index(self, request: dict) -> dict:
        """Indexa un archivo (para compatibilidad con cliente)"""
        file_name = request.get('file_name')
        file_content_b64 = request.get('file_content')
        
        if file_content_b64:
            return self._handle_store(request)
        
        # Si solo hay file_path, indexar archivo existente
        file_path = request.get('file_path')
        if file_path:
            try:
                self.indexer.index_file(file_path)
                self.stats['files_indexed'] += 1
                return {'status': 'success', 'message': f'File indexed: {file_path}'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
        
        return {'status': 'error', 'message': 'No file_path or file_content provided'}
    
    def _handle_download(self, request: dict) -> dict:
        """Prepara descarga de archivo"""
        file_id = request.get('file_id') or request.get('file_name')
        
        if not file_id:
            return {'status': 'error', 'message': 'Missing file_id'}
        
        file_info = self.repository.get_file_info(file_id)
        
        if not file_info:
            return {'status': 'error', 'message': f'File not found: {file_id}'}
        
        return {
            'status': 'success',
            'file_info': file_info,
            'ready': True,
            'node_id': self.node_id
        }
    
    def _handle_get_file(self, request: dict) -> dict:
        """
        Devuelve el contenido del archivo en base64.
        Usado por el coordinador para servir descargas a clientes.
        """
        import base64
        
        file_name = request.get('file_name') or request.get('file_id')
        
        if not file_name:
            return {'status': 'error', 'message': 'Missing file_name'}
        
        # Buscar archivo en múltiples ubicaciones
        file_path = None
        
        # 1. Buscar en index_path directamente
        candidate = Path(self.index_path) / file_name
        if candidate.exists() and candidate.is_file():
            file_path = candidate
        
        # 2. Buscar en data_path si es diferente
        if not file_path and self.data_path != self.index_path:
            candidate = Path(self.data_path) / file_name
            if candidate.exists() and candidate.is_file():
                file_path = candidate
        
        # 3. Buscar recursivamente en subdirectorios de index_path
        if not file_path:
            for candidate in Path(self.index_path).rglob(file_name):
                if candidate.is_file():
                    file_path = candidate
                    break
        
        # 4. Buscar recursivamente en subdirectorios de data_path
        if not file_path and self.data_path != self.index_path:
            for candidate in Path(self.data_path).rglob(file_name):
                if candidate.is_file():
                    file_path = candidate
                    break
        
        if not file_path:
            self.logger.error(f"❌ Archivo '{file_name}' no encontrado para descarga")
            return {'status': 'error', 'message': f'File not found: {file_name}'}
        
        self.logger.debug(f"📁 Archivo encontrado para descarga en: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            return {
                'status': 'success',
                'file_name': file_name,
                'file_content': content_b64,
                'file_size': len(content),
                'node_id': self.node_id
            }
        except Exception as e:
            self.logger.error(f"Error leyendo archivo {file_name}: {e}")
            return {'status': 'error', 'message': str(e)}

    def _get_node_status(self) -> dict:
        """Obtiene el estado del nodo"""
        uptime = 0
        if self.stats['start_time']:
            uptime = time.time() - self.stats['start_time']
        
        files = self.repository.get_all_indexed_files()
        
        return {
            'status': 'success',
            'node_id': self.node_id,
            'node_type': 'processing',
            'host': self.announce_host,
            'port': self.port,
            'registered_with_coordinator': self.registered_with_coordinator,
            'current_load': self.current_load,
            'files_count': len(files),
            'uptime_seconds': uptime,
            'stats': self.stats
        }
    
    def _coordinator_loop(self):
        """Mantiene conexión con el coordinador (Líder) con soporte de failover"""
        # Esperar a que el servidor esté listo
        time.sleep(2)
        
        while self.active:
            # 1. Descubrir/Refrescar lista de coordinadores
            self.discovery.refresh()
            coordinators = self.discovery.get_coordinators()
            
            if not coordinators:
                self.logger.warning("⚠️ No se han encontrado coordinadores. Reintentando descubrimiento...")
                time.sleep(5)
                continue

            # 2. Intentar encontrar al líder
            leader_found = False
            
            # Priorizar el último coordinador conocido si existe
            if self.coordinator_host:
                current_addr = f"{self.coordinator_host}:{self.coordinator_port}"
                if current_addr in coordinators:
                    # Mover al principio para probar primero
                    coordinators.remove(current_addr)
                    coordinators.insert(0, current_addr)

            for coord_addr in coordinators:
                try:
                    host, port_str = coord_addr.split(':')
                    port = int(port_str)
                    
                    self.logger.info(f"🔄 Intentando conectar con coordinador: {coord_addr}")
                    
                    # Verificar salud y liderazgo
                    is_leader, redirect_host, redirect_port = self._check_coordinator_status(host, port)
                    
                    target_host, target_port = host, port
                    
                    if redirect_host:
                        self.logger.info(f"↩️ Redirigido por coordinador hacia líder: {redirect_host}:{redirect_port}")
                        target_host, target_port = redirect_host, redirect_port
                        # Verificar conectividad con el líder redirigido
                        is_leader, _, _ = self._check_coordinator_status(target_host, target_port)
                    
                    if is_leader:
                        # Actualizar host actual
                        self.coordinator_host = target_host
                        self.coordinator_port = target_port
                        
                        # Intentar registrarse
                        if self._register_with_coordinator():
                            self.registered_with_coordinator = True
                            self.logger.info(f"✅ Conectado y registrado con LÍDER: {target_host}:{target_port}")
                            leader_found = True
                            
                            # SOLICITAR SINCRONIZACIÓN INICIAL:
                            # Pedir al líder que nos envíe los archivos que nos faltan
                            self._request_full_synchronization()
                            
                            # Mantener el loop de heartbeat mientras dure la conexión
                            self._heartbeat_session()
                            
                            # Si salimos de heartbeat_session es porque perdimos conexión
                            self.registered_with_coordinator = False
                            self.logger.warning(f"❌ Conexión perdida con líder {target_host}:{target_port}")
                            break # Salir del for para refrescar lista y buscar nuevo líder
                        else:
                            self.logger.warning(f"⚠️ Falló registro con {target_host}:{target_port}")
                    else:
                        self.logger.info(f"ℹ️ Coordinador {host}:{port} no es líder y no redirigió")

                except Exception as e:
                    self.logger.warning(f"⚠️ Error conectando a {coord_addr}: {e}")
            
            if not leader_found:
                self.logger.warning("⚠️ No se pudo conectar a ningún líder. Reintentando en 5s...")
                time.sleep(5)

    def _check_coordinator_status(self, host: str, port: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Verifica si un coordinador es líder.
        Returns: (is_leader, redirect_host, redirect_port)
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((host, port))
                
                request = json.dumps({'action': 'health'})
                sock.sendall(f"{len(request):<8}".encode() + request.encode())
                
                length_data = sock.recv(8)
                if not length_data: return False, None, None
                
                length = int(length_data.decode().strip())
                data = sock.recv(length)
                response = json.loads(data.decode())
                
                current_leader = response.get('current_leader')
                is_leader = response.get('is_leader', False)
                return is_leader, None, None
        except:
            return False, None, None

    def _heartbeat_session(self):
        """Loop de heartbeats mientras la conexión esté activa"""
        while self.active and self.registered_with_coordinator:
            if not self._send_heartbeat():
                return
            time.sleep(self.HEARTBEAT_INTERVAL)

    def _request_full_synchronization(self):
        """Solicita sincronización completa de archivos al coordinador"""
        if not self.coordinator_host:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30)
                sock.connect((self.coordinator_host, self.coordinator_port))
                
                # Obtener archivos que ya tengo
                my_files = self._get_indexed_file_names()
                
                request = {
                    'action': 'request_sync',
                    'node_id': self.node_id,
                    'current_files': my_files
                }
                
                req_json = json.dumps(request)
                sock.sendall(f"{len(req_json):<8}".encode())
                sock.sendall(req_json.encode())
                
                self.logger.info("📥 Solicitud de sincronización enviada al coordinador")
                
                # La respuesta vendrá asincrónicamente o como comandos de replicación
                # pero podemos leer una confirmación simple
                length_data = sock.recv(8)
                if length_data:
                    self.logger.info("✅ Coordinador inició proceso de sincronización")
                
        except Exception as e:
            self.logger.warning(f"⚠️ Error solicitando sincronización: {e}")

    def _register_with_coordinator(self) -> bool:
        """Se registra con el coordinador"""
        if not self.coordinator_host:
            return False
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((self.coordinator_host, self.coordinator_port))
                
                # Obtener lista de archivos indexados
                indexed_files = self._get_indexed_file_names()
                
                request = {
                    'action': 'register',
                    'node_id': self.node_id,
                    'host': self.announce_host,
                    'port': self.port,
                    'node_type': 'processing',
                    'files': indexed_files  # Incluir archivos al registrarse
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
                    
                    # Manejar redirección explícita del coordinador
                    if response.get('status') == 'redirect':
                        lh = response.get('leader_host')
                        lp = response.get('leader_port')
                        if lh and lp:
                            self.logger.info(f"↩️ Registro redirigido a: {lh}:{lp}")
                            self.coordinator_host = lh
                            self.coordinator_port = lp
                            # Retornamos False para que el loop principal reintente con el nuevo host
                            return False

                    return response.get('status') == 'success'
                
        except Exception as e:
            self.logger.debug(f"Error registrando con coordinador: {e}")
        
        return False
    
    def _get_indexed_file_names(self) -> List[str]:
        """Obtiene la lista de nombres de archivos indexados"""
        try:
            files = self.repository.get_all_indexed_files()
            return [f.get('name', f.get('file_name', str(f))) for f in files]
        except:
            # Fallback: listar archivos de ambos directorios
            file_names = set()
            try:
                for f in Path(self.index_path).iterdir():
                    if f.is_file():
                        file_names.add(f.name)
            except:
                pass
            try:
                if self.data_path != self.index_path:
                    for f in Path(self.data_path).iterdir():
                        if f.is_file():
                            file_names.add(f.name)
            except:
                pass
            return list(file_names)
    
    def _send_heartbeat(self) -> bool:
        """Envía heartbeat al coordinador"""
        if not self.coordinator_host:
            return False
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((self.coordinator_host, self.coordinator_port))
                
                request = {
                    'action': 'heartbeat',
                    'node_id': self.node_id,
                    'load': self.current_load
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
                    return response.get('status') == 'ok'
                
        except Exception as e:
            self.logger.debug(f"Error enviando heartbeat: {e}")
        
        return False
    
    def set_coordinator(self, host: str, port: int = 5000):
        """Configura el coordinador dinámicamente"""
        self.coordinator_host = host
        self.coordinator_port = port
        self.registered_with_coordinator = False
        self.logger.info(f"🔄 Coordinador configurado: {host}:{port}")
    
    def store_file(self, file_name: str, content: bytes) -> bool:
        """
        Almacena un archivo directamente.
        
        Args:
            file_name: Nombre del archivo
            content: Contenido binario
            
        Returns:
            True si el almacenamiento fue exitoso
        """
        try:
            # Guardar archivo en data_path (directorio de almacenamiento)
            file_path = Path(self.data_path) / file_name
            with open(file_path, 'wb') as f:
                f.write(content)
            
            self.indexer.index_file(str(file_path))
            self.stats['files_stored'] += 1
            
            self.logger.info(f"📥 Archivo almacenado: {file_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error almacenando {file_name}: {e}")
            return False
    
    def search_local(self, query: str, file_type: str = None) -> List[dict]:
        """
        Ejecuta una búsqueda local.
        
        Args:
            query: Términos de búsqueda
            file_type: Filtro opcional por tipo
            
        Returns:
            Lista de resultados
        """
        return self.repository.search(query, file_type)
