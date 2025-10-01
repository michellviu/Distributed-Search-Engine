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
            path = Path(file_path)
            if not path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False
                
            file_size = path.stat().st_size
            
            # Send file metadata
            metadata = f"{path.name}|{file_size}".encode()
            socket_conn.sendall(metadata)
            
            # Wait for acknowledgment
            ack = socket_conn.recv(1024)
            if ack != b"READY":
                self.logger.error("Failed to receive ready acknowledgment")
                return False
            
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
            # Receive file metadata
            metadata = socket_conn.recv(1024).decode()
            file_name, file_size_str = metadata.split('|')
            file_size = int(file_size_str)
            
            # Send ready acknowledgment
            socket_conn.sendall(b"READY")
            
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
