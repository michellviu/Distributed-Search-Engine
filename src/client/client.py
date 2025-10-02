"""
Client implementation for search requests
"""

import socket
import logging
import json
from typing import List, Dict, Optional
from pathlib import Path


class SearchClient:
    """
    Client for connecting to centralized search server
    """
    
    def __init__(self, server_host: str = 'localhost', server_port: int = 5000):
        """
        Initialize the search client
        
        Args:
            server_host: Server host address
            server_port: Server port number
        """
        self.server_host = server_host
        self.server_port = server_port
        self.logger = logging.getLogger(__name__)
        
    def search(self, query: str, file_type: Optional[str] = None) -> List[Dict]:
        """
        Send search query to server
        
        Args:
            query: Search query string
            file_type: Optional file type filter (e.g., '.txt', '.pdf')
            
        Returns:
            List of matching documents
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.server_host, self.server_port))
                
                # Create search request
                request = {
                    'action': 'search',
                    'query': query
                }
                if file_type:
                    request['file_type'] = file_type
                
                # Send request
                self._send_request(sock, request)
                
                # Receive response
                response = self._receive_response(sock)
                
                if response.get('status') == 'success':
                    self.logger.info(f"Search successful: {response.get('count', 0)} results")
                    return response.get('results', [])
                else:
                    self.logger.error(f"Search failed: {response.get('message', 'Unknown error')}")
                    return []
                    
        except Exception as e:
            self.logger.error(f"Error sending search request: {e}")
            return []
    
    def index_file(self, file_path: str) -> bool:
        """
        Request server to index a file
        
        Args:
            file_path: Path to file to index
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.server_host, self.server_port))
                
                # Create index request
                request = {
                    'action': 'index',
                    'file_path': file_path
                }
                
                # Send request
                self._send_request(sock, request)
                
                # Receive response
                response = self._receive_response(sock)
                
                if response.get('status') == 'success':
                    self.logger.info(f"File indexed successfully: {file_path}")
                    return True
                else:
                    self.logger.error(f"Failed to index file: {response.get('message', 'Unknown error')}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error indexing file: {e}")
            return False
            
    def download_file(self, file_id: str, destination: str) -> bool:
        """
        Download file from server
        
        Args:
            file_id: Identifier of file to download (name or path)
            destination: Local path to save file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.server_host, self.server_port))
                
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
                
        except Exception as e:
            self.logger.error(f"Error downloading file: {e}")
            return False
    
    def list_files(self) -> List[Dict]:
        """
        Get list of all indexed files from server
        
        Returns:
            List of file information dictionaries
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.server_host, self.server_port))
                
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
                    
        except Exception as e:
            self.logger.error(f"Error listing files: {e}")
            return []
    
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
