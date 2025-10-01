# Project Structure Summary

## Centralized Document Search Engine - File Structure

This document provides a complete overview of the file structure created for the centralized version of the distributed search engine project.

## Directory Tree

```
Distributed-Search-Engine/
├── README.md                         # Main project documentation
├── buscador.pdf                      # Project specifications (original)
├── setup.py                          # Python package installation script
├── requirements.txt                  # Python dependencies
│
├── config/                           # Configuration files
│   ├── server_config.json           # Server configuration
│   └── client_config.json           # Client configuration
│
├── docs/                            # Documentation
│   ├── ARCHITECTURE.md              # Architecture documentation
│   ├── QUICKSTART.md                # Quick start guide
│   └── PROJECT_STRUCTURE.md         # This file
│
├── src/                             # Source code
│   ├── __init__.py                  # Package initialization
│   │
│   ├── server/                      # Server module
│   │   ├── __init__.py
│   │   └── server.py                # Main server implementation
│   │
│   ├── client/                      # Client module
│   │   ├── __init__.py
│   │   └── client.py                # Client implementation
│   │
│   ├── indexer/                     # Indexing module
│   │   ├── __init__.py
│   │   └── indexer.py               # Document indexer
│   │
│   ├── search/                      # Search module
│   │   ├── __init__.py
│   │   └── search_engine.py         # Search engine implementation
│   │
│   ├── transfer/                    # File transfer module
│   │   ├── __init__.py
│   │   └── file_transfer.py         # File transfer handler
│   │
│   ├── utils/                       # Utility modules
│   │   ├── __init__.py
│   │   ├── config.py                # Configuration management
│   │   └── logger.py                # Logging configuration
│   │
│   ├── main_server.py               # Server entry point
│   └── main_client.py               # Client entry point
│
├── tests/                           # Unit tests
│   ├── __init__.py
│   ├── test_indexer.py              # Indexer tests
│   └── test_search.py               # Search engine tests
│
├── shared_files/                    # Shared files directory
│   └── README.md                    # Directory documentation
│
└── logs/                            # Log files (generated at runtime)
```

## File Descriptions

### Root Level Files

- **README.md**: Main project documentation with usage instructions
- **buscador.pdf**: Original project specifications document
- **setup.py**: Python setuptools configuration for package installation
- **requirements.txt**: List of Python dependencies (empty for now - uses stdlib)
- **.gitignore**: Git ignore patterns for Python projects

### Configuration Files (`config/`)

- **server_config.json**: Server configuration
  - Host and port settings
  - Indexer configuration
  - Transfer settings
  - Logging configuration

- **client_config.json**: Client configuration
  - Server connection settings
  - Logging configuration

### Documentation (`docs/`)

- **ARCHITECTURE.md**: Detailed architecture documentation in Spanish
  - Component descriptions
  - Usage examples
  - Feature list
  - Future enhancements

- **QUICKSTART.md**: Quick start guide in Spanish
  - Installation instructions
  - Usage examples
  - Troubleshooting

- **PROJECT_STRUCTURE.md**: This file - complete structure overview

### Source Code (`src/`)

#### Server Module (`src/server/`)
- **server.py**: Main server implementation
  - `SearchServer` class
  - Connection handling
  - Request processing

#### Client Module (`src/client/`)
- **client.py**: Client implementation
  - `SearchClient` class
  - Search requests
  - File downloads

#### Indexer Module (`src/indexer/`)
- **indexer.py**: Document indexer
  - `DocumentIndexer` class
  - File indexing by name and type
  - Hash-based duplicate detection
  - Directory scanning

#### Search Module (`src/search/`)
- **search_engine.py**: Search engine
  - `SearchEngine` class
  - Query processing
  - Relevance scoring
  - Type-based filtering

#### Transfer Module (`src/transfer/`)
- **file_transfer.py**: File transfer handler
  - `FileTransfer` class
  - Chunked file transfer
  - Integrity verification
  - Error handling

#### Utils Module (`src/utils/`)
- **config.py**: Configuration management
  - `Config` class
  - JSON-based configuration
  - Default values

- **logger.py**: Logging configuration
  - `setup_logging()` function
  - Console and file logging
  - Configurable log levels

#### Entry Points
- **main_server.py**: Server startup script
  - Command-line argument parsing
  - Component initialization
  - Server startup

- **main_client.py**: Client startup script
  - Command-line argument parsing
  - Search and download operations

### Tests (`tests/`)

- **test_indexer.py**: Unit tests for indexer
  - File indexing tests
  - Directory indexing tests
  - Duplicate detection tests

- **test_search.py**: Unit tests for search engine
  - Basic search tests
  - Type filtering tests
  - Relevance scoring tests

### Data Directories

- **shared_files/**: Directory for files to be shared and indexed
  - Contains README.md with usage instructions
  - Example files excluded from git

- **logs/**: Runtime log files (created automatically)
  - Excluded from git

## Module Dependencies

```
main_server.py
├── server.server (SearchServer)
├── indexer.indexer (DocumentIndexer)
├── search.search_engine (SearchEngine)
├── utils.config (Config)
└── utils.logger (setup_logging)

main_client.py
├── client.client (SearchClient)
├── utils.config (Config)
└── utils.logger (setup_logging)

SearchServer
└── (uses threading and socket from stdlib)

SearchClient
└── (uses socket from stdlib)

DocumentIndexer
├── pathlib.Path
└── hashlib (for duplicate detection)

SearchEngine
└── DocumentIndexer (dependency)

FileTransfer
└── (uses socket from stdlib)
```

## Key Features Implemented

1. **Modular Architecture**: Separated concerns into distinct modules
2. **Configuration Management**: JSON-based configuration with defaults
3. **Logging System**: Comprehensive logging for debugging
4. **Document Indexing**: Efficient file indexing by name and type
5. **Search Engine**: Query processing with relevance scoring
6. **Duplicate Detection**: Hash-based duplicate file identification
7. **File Transfer**: Chunked transfer with error handling
8. **Testing**: Unit tests for core functionality
9. **Documentation**: Complete documentation in Spanish and English

## Usage Summary

### Start Server
```bash
cd src
python3 main_server.py --host localhost --port 5000 --index-path ./shared_files
```

### Run Client
```bash
cd src
python3 main_client.py --query "documento"
```

### Run Tests
```bash
python3 -m unittest discover tests/ -v
```

## Design Principles

1. **Minimal Dependencies**: Uses only Python standard library
2. **Clear Separation**: Each module has a single responsibility
3. **Extensibility**: Easy to add new features
4. **Configurability**: All settings can be configured
5. **Testability**: Unit tests for core components
6. **Documentation**: Comprehensive documentation in multiple languages

## Next Steps for Development

1. Implement complete server-client communication protocol
2. Add authentication and security features
3. Implement content-based search (not just filename)
4. Add real-time index updates
5. Implement distributed version (peer-to-peer)
6. Add web interface
7. Implement advanced search features (regex, fuzzy matching)
8. Add performance monitoring and metrics

## License and Credits

This project is created for educational purposes as part of the Distributed Systems course.
