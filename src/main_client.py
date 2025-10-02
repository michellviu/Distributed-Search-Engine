"""
Main entry point for running the search client
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from client.client import SearchClient
from utils.config import Config
from utils.logger import setup_logging

ROOT_DIR = Path(__file__).resolve().parent.parent


def main():
    """Main function to run the client"""
    default_config_path = ROOT_DIR / 'config' / 'client_config.json'
    parser = argparse.ArgumentParser(
        description='Centralized Document Search Engine Client'
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
        '--query',
        type=str,
        help='Search query to execute'
    )
    parser.add_argument(
        '--download',
        type=str,
        help='File ID to download'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output path for downloaded file'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Setup logging
    log_config = config.get('logging', default={})
    setup_logging(
        level=log_config.get('level', 'INFO'),
        log_file=log_config.get('file'),
        log_format=log_config.get('format')
    )
    
    # Get server configuration
    server_config = config.get('server', default={})
    host = args.host or server_config.get('host', 'localhost')
    port = args.port or server_config.get('port', 5000)
    
    # Initialize client
    client = SearchClient(host, port)
    
    # Execute requested operation
    if args.query:
        print(f"Searching for: {args.query}")
        results = client.search(args.query)
        
        if results:
            print(f"\nFound {len(results)} results:")
            for i, result in enumerate(results, 1):
                print(f"{i}. {result}")
        else:
            print("No results found")
            
    elif args.download and args.output:
        print(f"Downloading file {args.download} to {args.output}")
        success = client.download_file(args.download, args.output)
        
        if success:
            print("Download completed successfully")
        else:
            print("Download failed")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
