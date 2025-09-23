# Distributed Search Engine

📖 **Project Description**

This project implements a distributed document search system that enables searching for files across multiple computers. The system locates documents based on search patterns and provides access to identified documents through a distributed network architecture.

## ✨ Features

- **Distributed Architecture**: Search across multiple nodes in a network
- **Multiple Search Types**: Filename, content, and regex pattern matching
- **REST API**: HTTP-based communication between components
- **Real-time Monitoring**: Health checks and status monitoring for all nodes
- **File Access**: Direct download of found files through the network
- **Configurable**: Flexible configuration for different deployment scenarios
- **Command Line Interface**: Easy-to-use CLI for all operations

## 🏗️ Architecture

The system consists of three main components:

1. **Search Coordinator**: Central node that manages search requests and coordinates with search nodes
2. **Search Nodes**: Distributed nodes that index and search local files
3. **Search Engine Client**: Interface for submitting search requests and retrieving results

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Search Node   │    │   Search Node   │    │   Search Node   │
│   (Port 8001)   │    │   (Port 8002)   │    │   (Port 8003)   │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Coordinator   │
                    │   (Port 8000)   │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │     Client      │
                    │  (Search API)   │
                    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/michellviu/Distributed-Search-Engine.git
cd Distributed-Search-Engine
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package:
```bash
pip install -e .
```

### Basic Usage

1. **Start the Coordinator**:
```bash
search-engine start-coordinator --host localhost --port 8000
```

2. **Start Search Nodes** (in separate terminals):
```bash
# Node 1
search-engine start-node --node-id node1 --host localhost --port 8001 --search-dirs /path/to/search --coordinator http://localhost:8000

# Node 2
search-engine start-node --node-id node2 --host localhost --port 8002 --search-dirs /another/path --coordinator http://localhost:8000
```

3. **Search for Files**:
```bash
# Search by filename
search-engine search "document" --type filename --coordinator http://localhost:8000

# Search by content
search-engine search "python" --type content --coordinator http://localhost:8000

# Search with regex
search-engine search "\.py$" --type regex --coordinator http://localhost:8000
```

4. **Check System Status**:
```bash
search-engine status --coordinator http://localhost:8000
```

## 📖 Detailed Usage

### Configuration

Generate a configuration file:
```bash
search-engine init-config --output config.json
```

Use configuration file:
```bash
search-engine start-coordinator --config-file config.json
search-engine start-node --config-file config.json
```

### Search Types

- **filename**: Search in file names (default)
- **content**: Search within file contents (for text files)
- **regex**: Use regular expressions for pattern matching

### Advanced Search Options

```bash
# Limit results
search-engine search "test" --max-results 50

# Save results to file
search-engine search "document" --output results.json

# Download found files
search-engine search "report" --download ./downloads/
```

## 🔧 API Reference

### Coordinator Endpoints

- `POST /search` - Submit search request
- `GET /nodes` - List registered nodes
- `GET /health` - Get coordinator health status
- `POST /register` - Register a new node
- `DELETE /nodes/{node_id}` - Unregister a node

### Node Endpoints

- `POST /search` - Search local files
- `GET /health` - Get node health status
- `GET /status` - Get detailed node status
- `GET /files/{file_path}` - Download file

### Search Request Format

```json
{
  "pattern": "search_pattern",
  "type": "filename|content|regex",
  "max_results": 100
}
```

### Search Response Format

```json
{
  "search_id": "search_123",
  "pattern": "search_pattern",
  "search_type": "filename",
  "results": [
    {
      "file_path": "/path/to/file.txt",
      "file_name": "file.txt",
      "file_size": 1024,
      "modified_time": 1634567890,
      "node_id": "node1",
      "access_url": "http://localhost:8001/files/path/to/file.txt"
    }
  ],
  "total_results": 1,
  "nodes_searched": 2,
  "status": "success"
}
```

## 🧪 Testing

Run the test suite:
```bash
pytest tests/
```

Run with coverage:
```bash
pytest --cov=distributed_search tests/
```

## 📁 Project Structure

```
distributed_search/
├── core/                 # Core system components
│   ├── config.py        # Configuration management
│   ├── coordinator.py   # Search coordinator
│   └── node.py          # Search node
├── search/              # Search functionality
│   ├── engine.py        # Search engine client
│   └── patterns.py      # Pattern matching utilities
├── storage/             # Storage and indexing
│   └── indexer.py       # File indexing system
├── utils/               # Utility functions
│   └── helpers.py       # Helper functions
├── network/             # Network components (future)
└── cli.py               # Command line interface
```

## 🔒 Security Considerations

- File access is restricted to configured search directories
- HTTP endpoints should be secured in production environments
- Consider implementing authentication for production deployments
- Validate all file paths to prevent directory traversal attacks

## 🐛 Troubleshooting

### Common Issues

1. **Node registration fails**:
   - Check if coordinator is running
   - Verify network connectivity
   - Check firewall settings

2. **No search results**:
   - Verify search directories exist and are readable
   - Check file permissions
   - Ensure nodes are properly registered

3. **File download fails**:
   - Verify file still exists on the node
   - Check network connectivity
   - Ensure proper file permissions

### Logging

Enable verbose logging:
```bash
search-engine --verbose start-coordinator
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For questions or support, please open an issue in the GitHub repository.
