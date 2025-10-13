"""
Main server implementation for centralized search engine
"""

import socket
import threading
import logging
import json
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from pathlib import Path


# ==================== Repository Pattern ====================
# Abstracción para el almacenamiento de datos (fácil migración a MongoDB)

class DocumentRepository(ABC):
    """
    Abstract repository for document storage
    Allows easy migration to different storage backends (MongoDB, etc.)
    """
    
    @abstractmethod
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents matching query"""
        pass
    
    @abstractmethod
    def index_file(self, file_path: str) -> bool:
        """Index a single file"""
        pass
    
    @abstractmethod
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific file"""
        pass
    
    @abstractmethod
    def get_all_indexed_files(self) -> List[Dict[str, Any]]:
        """Get all indexed files"""
        pass


class InMemoryDocumentRepository(DocumentRepository):
    """
    In-memory implementation using the current indexer
    This can be replaced with MongoDocumentRepository later
    """
    
    def __init__(self, indexer, search_engine):
        self.indexer = indexer
        self.search_engine = search_engine
        self.logger = logging.getLogger(__name__)
    
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents using the search engine"""
        try:
            return self.search_engine.search(query, file_type)
        except Exception as e:
            self.logger.error(f"Error searching documents: {e}")
            return []
    
    def index_file(self, file_path: str) -> bool:
        """Index a file using the indexer"""
        try:
            self.indexer.index_file(file_path)
            return True
        except Exception as e:
            self.logger.error(f"Error indexing file {file_path}: {e}")
            return False
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file information from index"""
        # Search through the index for the file
        for file_name, file_list in self.indexer.index.items():
            for file_info in file_list:
                if file_info.get('path') == file_id or file_info.get('name') == file_id:
                    return file_info
        return None
    
    def get_all_indexed_files(self) -> List[Dict[str, Any]]:
        """Get all indexed files"""
        all_files = []
        for file_name, file_list in self.indexer.index.items():
            all_files.extend(file_list)
        return all_files


# ==================== Command Pattern ====================
# Encapsula cada operación del servidor como un comando

class Command(ABC):
    """Base class for all server commands"""
    
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """Execute the command and return response"""
        pass


class SearchCommand(Command):
    """Command for searching documents"""
    
    def __init__(self, repository: DocumentRepository, query: str, file_type: Optional[str] = None):
        self.repository = repository
        self.query = query
        self.file_type = file_type
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute search and return results"""
        try:
            self.logger.info(f"Executing search: query='{self.query}', type={self.file_type}")
            results = self.repository.search(self.query, self.file_type)
            return {
                'status': 'success',
                'action': 'search',
                'query': self.query,
                'results': results,
                'count': len(results)
            }
        except Exception as e:
            self.logger.error(f"Search command failed: {e}")
            return {
                'status': 'error',
                'action': 'search',
                'message': str(e)
            }


class IndexCommand(Command):
    """Command for indexing a new document"""
    
    def __init__(self, repository: DocumentRepository, file_path: str = None, 
                 file_name: str = None, file_content: bytes = None):
        self.repository = repository
        self.file_path = file_path  # For backward compatibility
        self.file_name = file_name  # New: file name from client
        self.file_content = file_content  # New: file content from client
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute indexing and return result"""
        try:
            # New behavior: If file content is provided, save it first
            if self.file_content is not None and self.file_name:
                self.logger.info(f"Executing index with uploaded content: file='{self.file_name}'")
                
                # Save file to shared_files directory
                shared_files_dir = Path('shared_files')
                shared_files_dir.mkdir(exist_ok=True)
                
                target_path = shared_files_dir / self.file_name
                with open(target_path, 'wb') as f:
                    f.write(self.file_content)
                
                self.logger.info(f"File saved to: {target_path}")
                
                # Index the saved file
                success = self.repository.index_file(str(target_path))
                
                if success:
                    return {
                        'status': 'success',
                        'action': 'index',
                        'file_path': str(target_path),
                        'message': 'File uploaded and indexed successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'index',
                        'message': 'File uploaded but indexing failed'
                    }
            
            # Old behavior: file_path provided (for backward compatibility)
            elif self.file_path:
                self.logger.info(f"Executing index: file='{self.file_path}'")
                
                # Verify file exists
                if not Path(self.file_path).exists():
                    return {
                        'status': 'error',
                        'action': 'index',
                        'message': f"File not found: {self.file_path}"
                    }
                
                success = self.repository.index_file(self.file_path)
                
                if success:
                    return {
                        'status': 'success',
                        'action': 'index',
                        'file_path': self.file_path,
                        'message': 'File indexed successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'index',
                        'message': 'Failed to index file'
                    }
            else:
                return {
                    'status': 'error',
                    'action': 'index',
                    'message': 'No file path or content provided'
                }
                
        except Exception as e:
            self.logger.error(f"Index command failed: {e}")
            return {
                'status': 'error',
                'action': 'index',
                'message': str(e)
            }


class DownloadCommand(Command):
    """Command for downloading a document"""
    
    def __init__(self, repository: DocumentRepository, file_transfer, file_id: str):
        self.repository = repository
        self.file_transfer = file_transfer
        self.file_id = file_id
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute download preparation and return file info"""
        try:
            self.logger.info(f"Executing download: file_id='{self.file_id}'")
            
            # Get file information from repository
            file_info = self.repository.get_file_info(self.file_id)
            
            if not file_info:
                return {
                    'status': 'error',
                    'action': 'download',
                    'message': f"File not found: {self.file_id}"
                }
            
            file_path = file_info.get('path')
            if not file_path or not Path(file_path).exists():
                return {
                    'status': 'error',
                    'action': 'download',
                    'message': 'File path not available or file does not exist'
                }
            
            return {
                'status': 'success',
                'action': 'download',
                'file_info': file_info,
                'ready': True
            }
        except Exception as e:
            self.logger.error(f"Download command failed: {e}")
            return {
                'status': 'error',
                'action': 'download',
                'message': str(e)
            }


class ListCommand(Command):
    """Command for listing all indexed documents"""
    
    def __init__(self, repository: DocumentRepository):
        self.repository = repository
        self.logger = logging.getLogger(__name__)
    
    def execute(self) -> Dict[str, Any]:
        """Execute list and return all indexed files"""
        try:
            self.logger.info("Executing list all indexed files")
            files = self.repository.get_all_indexed_files()
            return {
                'status': 'success',
                'action': 'list',
                'files': files,
                'count': len(files)
            }
        except Exception as e:
            self.logger.error(f"List command failed: {e}")
            return {
                'status': 'error',
                'action': 'list',
                'message': str(e)
            }


# ==================== Command Factory ====================

class CommandFactory:
    """Factory for creating commands based on requests"""
    
    def __init__(self, repository: DocumentRepository, file_transfer=None):
        self.repository = repository
        self.file_transfer = file_transfer
        self.logger = logging.getLogger(__name__)
    
    def create_command(self, request: Dict[str, Any], file_content: bytes = None) -> Optional[Command]:
        """
        Create a command based on the request
        
        Args:
            request: Dictionary with 'action' and other parameters
            file_content: Optional file content for index operations
            
        Returns:
            Command instance or None if invalid
        """
        action = request.get('action')
        
        if action == 'search':
            query = request.get('query', '')
            file_type = request.get('file_type')
            return SearchCommand(self.repository, query, file_type)
        
        elif action == 'index':
            # New behavior: check if file_name and file_size are provided (upload mode)
            file_name = request.get('file_name')
            file_path = request.get('file_path', '')
            
            if file_name and file_content:
                # Upload mode: file content provided
                return IndexCommand(self.repository, file_path=None, 
                                  file_name=file_name, file_content=file_content)
            else:
                # Old mode: file path provided
                return IndexCommand(self.repository, file_path=file_path)
        
        elif action == 'download':
            file_id = request.get('file_id', '')
            return DownloadCommand(self.repository, self.file_transfer, file_id)
        
        elif action == 'list':
            return ListCommand(self.repository)
        
        else:
            self.logger.warning(f"Unknown action: {action}")
            return None


# ==================== Server Implementation ====================

class SearchServer:
    """
    Centralized server that handles search requests and manages document index
    Uses Command Pattern for extensibility and Repository Pattern for data abstraction
    """
    
    def __init__(self, host: str = 'localhost', port: int = 5000, 
                 repository: DocumentRepository = None, file_transfer=None):
        """
        Initialize the search server
        
        Args:
            host: Server host address
            port: Server port number
            repository: Document repository implementation
            file_transfer: File transfer handler
        """
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.repository = repository
        self.file_transfer = file_transfer
        self.command_factory = CommandFactory(repository, file_transfer)
        self.logger = logging.getLogger(__name__)
        
    def start(self):
        """Start the server and begin listening for connections"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True
        self.logger.info(f"Server started on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = self.socket.accept()
                self.logger.info(f"Connection from {address}")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error accepting connection: {e}")
                
    def handle_client(self, client_socket: socket.socket, address: tuple):
        """
        Handle individual client connections
        
        Args:
            client_socket: Client socket connection
            address: Client address tuple
        """
        try:
            # Receive request from client
            request_data = self._receive_data(client_socket)
            
            if not request_data:
                self.logger.warning(f"No data received from {address}")
                return
            
            # Parse request
            try:
                request = json.loads(request_data)
                self.logger.info(f"Request from {address}: {request.get('action', 'unknown')}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON from {address}: {e}")
                error_response = {
                    'status': 'error',
                    'message': 'Invalid JSON format'
                }
                self._send_response(client_socket, error_response)
                return
            
            # Handle index action with file upload
            file_content = None
            if request.get('action') == 'index' and 'file_size' in request:
                # Receive file content
                file_size = request.get('file_size', 0)
                self.logger.info(f"Receiving file content: {file_size} bytes")
                file_content = self._receive_file_content(client_socket, file_size)
            
            # Create and execute command
            command = self.command_factory.create_command(request, file_content)
            
            if command is None:
                error_response = {
                    'status': 'error',
                    'message': f"Unknown action: {request.get('action', 'none')}"
                }
                self._send_response(client_socket, error_response)
                return
            
            # Execute command
            response = command.execute()
            
            # Handle download special case (needs to send file)
            if request.get('action') == 'download' and response.get('status') == 'success':
                self._send_response(client_socket, response)
                
                # Send the actual file
                file_path = response['file_info']['path']
                self.logger.info(f"Sending file: {file_path}")
                
                if self.file_transfer:
                    success = self.file_transfer.send_file(file_path, client_socket)
                    if success:
                        self.logger.info(f"File sent successfully: {file_path}")
                    else:
                        self.logger.error(f"Failed to send file: {file_path}")
            else:
                # Send response for other actions
                self._send_response(client_socket, response)
            
        except Exception as e:
            self.logger.error(f"Error handling client {address}: {e}", exc_info=True)
            try:
                error_response = {
                    'status': 'error',
                    'message': f"Server error: {str(e)}"
                }
                self._send_response(client_socket, error_response)
            except:
                pass
        finally:
            client_socket.close()
            self.logger.info(f"Connection closed: {address}")
    
    def _receive_data(self, client_socket: socket.socket, buffer_size: int = 4096) -> str:
        """
        Receive data from client socket
        
        Args:
            client_socket: Client socket
            buffer_size: Buffer size for receiving
            
        Returns:
            Decoded string data
        """
        try:
            # First receive the length of the message
            length_data = client_socket.recv(8)
            if not length_data:
                return ''
            
            message_length = int(length_data.decode().strip())
            
            # Receive the actual message
            data = b''
            while len(data) < message_length:
                chunk = client_socket.recv(min(buffer_size, message_length - len(data)))
                if not chunk:
                    break
                data += chunk
            
            return data.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error receiving data: {e}")
            return ''
    
    def _receive_file_content(self, client_socket: socket.socket, file_size: int, 
                             buffer_size: int = 4096) -> bytes:
        """
        Receive file content from client socket
        
        Args:
            client_socket: Client socket
            file_size: Expected file size in bytes
            buffer_size: Buffer size for receiving
            
        Returns:
            File content as bytes
        """
        try:
            self.logger.info(f"Receiving file content: {file_size} bytes")
            data = b''
            while len(data) < file_size:
                chunk = client_socket.recv(min(buffer_size, file_size - len(data)))
                if not chunk:
                    break
                data += chunk
            
            self.logger.info(f"Received {len(data)} bytes")
            return data
        except Exception as e:
            self.logger.error(f"Error receiving file content: {e}")
            return b''
    
    def _send_response(self, client_socket: socket.socket, response: Dict[str, Any]):
        """
        Send response to client
        
        Args:
            client_socket: Client socket
            response: Response dictionary to send
        """
        try:
            response_json = json.dumps(response)
            response_bytes = response_json.encode('utf-8')
            
            # Send length first
            length_str = f"{len(response_bytes):<8}"
            client_socket.sendall(length_str.encode())
            
            # Send actual data
            client_socket.sendall(response_bytes)
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")
            
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.socket:
            self.socket.close()
        self.logger.info("Server stopped")
