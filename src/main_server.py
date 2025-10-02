"""
Main entry point for running the centralized search server
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from server.server import SearchServer, InMemoryDocumentRepository
from indexer.indexer import DocumentIndexer
from search.search_engine import SearchEngine
from transfer.file_transfer import FileTransfer
from utils.config import Config
from utils.logger import setup_logging

ROOT_DIR = Path(__file__).resolve().parent.parent


def main():
    """Main function to start the server"""
    default_config_path = ROOT_DIR / 'config' / 'server_config.json'
    parser = argparse.ArgumentParser(
        description='Centralized Document Search Engine Server'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=str(default_config_path),
        help='Path to configuration file'
    )
    parser.add_argument(
        '--host',
        type=str,
        help='Server host address (overrides config)'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='Server port number (overrides config)'
    )
    parser.add_argument(
        '--index-path',
        type=str,
        help='Path to index documents from (overrides config)'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Setup logging
    log_config = config.get('logging')
    setup_logging(
        level=log_config.get('level', 'INFO'),
        log_file=log_config.get('file'),
        log_format=log_config.get('format')
    )
    
    # Get server configuration
    server_config = config.get('server')
    host = args.host or server_config.get('host', 'localhost')
    port = args.port or server_config.get('port', 5000)
    
    # Get indexer configuration
    indexer_config = config.get('indexer')
    index_path = args.index_path or indexer_config.get('base_path', 'shared_files')
    
    # Initialize components with dependency injection
    indexer = DocumentIndexer(index_path)
    search_engine = SearchEngine(indexer)
    file_transfer = FileTransfer()
    
    # Create repository (abstraction layer for easy migration to MongoDB)
    repository = InMemoryDocumentRepository(indexer, search_engine)
    
    # Create server with injected dependencies
    server = SearchServer(host, port, repository, file_transfer)
    
    # Index initial files if path exists
    if Path(index_path).exists():
        print(f"Indexing files from {index_path}...")
        indexer.index_directory(index_path)
        print(f"Indexed {len(indexer.index)} unique file names")
    else:
        print(f"Warning: Index path {index_path} does not exist")
    
    # Start server
    print(f"Starting server on {host}:{port}")
    print("Available actions: search, index, download, list")
    print("Press Ctrl+C to stop the server")
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
        print("Server stopped")


if __name__ == '__main__':
    main()
