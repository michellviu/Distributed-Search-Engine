"""
Logging configuration
"""

import logging
import sys
import socket
import threading
from pathlib import Path


def setup_logging(level: str = 'INFO', log_file: str = None, log_format: str = None):
    """
    Setup logging configuration
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        log_format: Log message format (optional)
    """
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[]
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    logging.getLogger().addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logging.getLogger().addHandler(file_handler)
        
    logging.info("Logging configured successfully")


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def setup_distributed_logging(level: str = 'INFO', log_file: str = None, log_format: str = None, broadcast_port: int = 5000):
    """
    Setup distributed logging configuration

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        log_format: Log message format (optional)
        broadcast_port: Port to broadcast log messages to other nodes
    """
    setup_logging(level, log_file, log_format)

    # Broadcast logs to other nodes
    def broadcast_logs():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        logger = get_logger("distributed_logger")
        
        class BroadcastHandler(logging.Handler):
            def emit(self, record):
                try:
                    message = self.format(record)
                    sock.sendto(message.encode('utf-8'), ('<broadcast>', broadcast_port))
                except Exception as e:
                    logger.error(f"Failed to broadcast log: {e}")

        broadcast_handler = BroadcastHandler()
        broadcast_handler.setLevel(getattr(logging, level.upper()))
        broadcast_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(broadcast_handler)

    threading.Thread(target=broadcast_logs, daemon=True).start()
    logging.info("Distributed logging configured successfully")
