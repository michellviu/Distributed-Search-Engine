"""
File transfer implementation
Handles file download and upload with error recovery
"""

import os
import logging
import socket
from typing import Optional
from pathlib import Path


class FileTransfer:
    """
    Manages file transfer operations
    """
    
    CHUNK_SIZE = 4096
    
    def __init__(self):
        """Initialize file transfer handler"""
        self.logger = logging.getLogger(__name__)
        
    def send_file(self, file_path: str, socket_conn: socket.socket) -> bool:
        """
        Send file through socket connection
        
        Args:
            file_path: Path to file to send
            socket_conn: Socket connection to send through
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import hashlib
            
            path = Path(file_path)
            if not path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False
                
            file_size = path.stat().st_size
            file_name = path.name
            
            # Calculate file hash
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            file_hash = sha256_hash.hexdigest()
            
            # Send file size (16 bytes, right-aligned)
            size_str = f"{file_size:>16}"
            socket_conn.sendall(size_str.encode())
            
            # Send file name length (4 bytes, right-aligned)
            name_len_str = f"{len(file_name):>4}"
            socket_conn.sendall(name_len_str.encode())
            
            # Send file name
            socket_conn.sendall(file_name.encode('utf-8'))
            
            # Send file hash (64 bytes)
            socket_conn.sendall(file_hash.encode('utf-8'))
            
            # Send file content
            with open(file_path, 'rb') as f:
                bytes_sent = 0
                while bytes_sent < file_size:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    socket_conn.sendall(chunk)
                    bytes_sent += len(chunk)
                    
            self.logger.info(f"Sent file {file_path} ({bytes_sent} bytes)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending file {file_path}: {e}")
            return False
            
    def receive_file(self, socket_conn: socket.socket, destination_dir: str) -> Optional[str]:
        """
        Receive file through socket connection
        
        Args:
            socket_conn: Socket connection to receive from
            destination_dir: Directory to save received file
            
        Returns:
            Path to saved file if successful, None otherwise
        """
        try:
            # Receive file size (16 bytes)
            size_data = socket_conn.recv(16)
            if not size_data:
                self.logger.error("Failed to receive file size")
                return None
            file_size = int(size_data.decode().strip())
            
            # Receive file name length (4 bytes)
            name_len_data = socket_conn.recv(4)
            if not name_len_data:
                self.logger.error("Failed to receive file name length")
                return None
            name_length = int(name_len_data.decode().strip())
            
            # Receive file name
            file_name = socket_conn.recv(name_length).decode('utf-8')
            
            # Receive file hash (64 bytes)
            file_hash = socket_conn.recv(64).decode('utf-8')
            
            # Prepare destination
            dest_path = Path(destination_dir) / file_name
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Receive file content
            with open(dest_path, 'wb') as f:
                bytes_received = 0
                while bytes_received < file_size:
                    chunk = socket_conn.recv(
                        min(self.CHUNK_SIZE, file_size - bytes_received)
                    )
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_received += len(chunk)
                    
            if bytes_received == file_size:
                self.logger.info(f"Received file {file_name} ({bytes_received} bytes)")
                
                # Verify file integrity
                if self.verify_file(str(dest_path), file_hash):
                    self.logger.info(f"File integrity verified: {file_name}")
                else:
                    self.logger.warning(f"File integrity check failed: {file_name}")
                
                return str(dest_path)
            else:
                self.logger.error(
                    f"Incomplete file transfer: {bytes_received}/{file_size} bytes"
                )
                return None
                
        except Exception as e:
            self.logger.error(f"Error receiving file: {e}")
            return None
            
    def verify_file(self, file_path: str, expected_hash: str) -> bool:
        """
        Verify file integrity using hash
        
        Args:
            file_path: Path to file to verify
            expected_hash: Expected file hash
            
        Returns:
            True if hash matches, False otherwise
        """
        import hashlib
        
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            actual_hash = sha256_hash.hexdigest()
            return actual_hash == expected_hash
            
        except Exception as e:
            self.logger.error(f"Error verifying file {file_path}: {e}")
            return False
