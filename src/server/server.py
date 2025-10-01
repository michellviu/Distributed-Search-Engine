"""
Main server implementation for centralized search engine
"""

import socket
import threading
import logging
from typing import Dict, List


class SearchServer:
    """
    Centralized server that handles search requests and manages document index
    """
    
    def __init__(self, host: str = 'localhost', port: int = 5000):
        """
        Initialize the search server
        
        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.logger = logging.getLogger(__name__)
        
    def start(self):
        """Start the server and begin listening for connections"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
                    args=(client_socket,)
                )
                client_thread.start()
            except Exception as e:
                self.logger.error(f"Error accepting connection: {e}")
                
    def handle_client(self, client_socket: socket.socket):
        """
        Handle individual client connections
        
        Args:
            client_socket: Client socket connection
        """
        try:
            # Handle client requests here
            pass
        finally:
            client_socket.close()
            
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.socket:
            self.socket.close()
        self.logger.info("Server stopped")
