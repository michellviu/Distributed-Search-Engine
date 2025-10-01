# Distributed-Search-Engine

📖 **Project Description**

This project focuses on the development of a distributed document search system, created as part of the Distributed Systems course.

## Overview

The Distributed Search Engine is a system for searching and accessing documents across multiple computers. This repository contains the **centralized version** of the system, which implements a client-server architecture where:

- A central server manages document indexing and search queries
- Clients can search for documents and download them
- Files are indexed by name and type for efficient searching
- Duplicate files are detected using hash-based identification

## Features

- 🔍 **Document Search**: Search files by name and type
- 📂 **File Indexing**: Automatic indexing of shared directories
- 🔄 **File Transfer**: Reliable file download with error handling
- 🔐 **Duplicate Detection**: Hash-based duplicate file identification
- ⚙️ **Configurable**: JSON-based configuration system
- 📝 **Logging**: Comprehensive logging for debugging and monitoring

## Project Structure

```
Distributed-Search-Engine/
├── src/                      # Source code
│   ├── server/              # Server implementation
│   ├── client/              # Client implementation
│   ├── indexer/             # Document indexing
│   ├── search/              # Search engine
│   ├── transfer/            # File transfer
│   ├── utils/               # Utilities (config, logging)
│   ├── main_server.py       # Server entry point
│   └── main_client.py       # Client entry point
├── config/                   # Configuration files
├── tests/                    # Unit tests
├── docs/                     # Documentation
├── requirements.txt          # Python dependencies
└── setup.py                 # Installation script
```

For detailed architecture documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requirements

- Python 3.8 or higher
- No external dependencies (uses Python standard library)

## Installation

```bash
# Clone the repository
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine

# Install the package (optional)
pip install -e .
```

## Usage

### Starting the Server

```bash
cd src
python main_server.py --host localhost --port 5000 --index-path ./shared_files
```

Options:
- `--config`: Path to configuration file (default: `../config/server_config.json`)
- `--host`: Server host address (default: `localhost`)
- `--port`: Server port number (default: `5000`)
- `--index-path`: Directory to index files from (default: `./shared_files`)

### Running the Client

Search for files:
```bash
cd src
python main_client.py --host localhost --port 5000 --query "document"
```

Download a file:
```bash
cd src
python main_client.py --host localhost --port 5000 --download FILE_ID --output ./downloads/file.txt
```

Options:
- `--config`: Path to configuration file (default: `../config/client_config.json`)
- `--host`: Server host address (default: `localhost`)
- `--port`: Server port number (default: `5000`)
- `--query`: Search query to execute
- `--download`: File ID to download
- `--output`: Output path for downloaded file

## Configuration

Configuration files are located in the `config/` directory:

- `server_config.json`: Server configuration (host, port, indexing settings)
- `client_config.json`: Client configuration (server connection, logging)

Example server configuration:
```json
{
    "server": {
        "host": "localhost",
        "port": 5000,
        "max_connections": 5
    },
    "indexer": {
        "base_path": "./shared_files",
        "auto_index": true
    },
    "logging": {
        "level": "INFO",
        "file": "logs/server.log"
    }
}
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

## Project Specifications

This project implements a distributed document search system with the following characteristics:

- **Centralized Architecture**: Client-server model with a central indexing server
- **File Search**: Search by file name and type
- **Duplicate Detection**: Identify duplicate files with different names
- **Error Handling**: Robust error handling for network and file transfer issues
- **Efficient Search**: Optimized search algorithms for quick response times

For the complete project specifications, see [buscador.pdf](buscador.pdf).

## Future Enhancements

- Distributed peer-to-peer architecture
- Automatic node discovery
- Index replication across nodes
- Intelligent source selection for file downloads
- Fault tolerance mechanisms

## License

This project is created for educational purposes as part of the Distributed Systems course.

## Contributors

Developed as part of the Distributed Systems course project. 
