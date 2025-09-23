#!/bin/bash

# Distributed Search Engine Demo Script
# This script demonstrates how to set up and use the distributed search engine

echo "🔍 Distributed Search Engine Demo"
echo "=================================="

# Create demo directories and files
echo "📁 Setting up demo environment..."
mkdir -p demo_files/documents
mkdir -p demo_files/code
mkdir -p demo_files/logs

# Create sample files
cat > demo_files/documents/readme.txt << 'EOF'
This is a sample document for testing the distributed search engine.
It contains various keywords that can be searched for.
Keywords: documentation, testing, search, distributed, system
EOF

cat > demo_files/documents/report.md << 'EOF'
# Project Report

This report contains information about the distributed search system.

## Features
- Multiple node support
- Real-time search
- Pattern matching
- File download capabilities

## Keywords
- distributed search
- file indexing
- network architecture
EOF

cat > demo_files/code/example.py << 'EOF'
"""
Example Python script for demonstration
"""
import os
import sys

def search_function():
    """Example search function"""
    print("Searching for files...")
    return "search complete"

if __name__ == "__main__":
    search_function()
EOF

cat > demo_files/logs/application.log << 'EOF'
2024-01-01 10:00:00 INFO Starting application
2024-01-01 10:00:01 INFO Loading configuration
2024-01-01 10:00:02 INFO Search engine initialized
2024-01-01 10:00:03 INFO Server started on port 8000
2024-01-01 10:00:04 INFO Ready to accept connections
EOF

echo "✅ Demo files created in ./demo_files/"

# Create configuration files
echo "⚙️  Creating configuration files..."

cat > demo_coordinator.json << 'EOF'
{
  "coordinator": {
    "coordinator_id": "demo_coordinator",
    "host": "localhost",
    "port": 8000,
    "known_nodes": [],
    "heartbeat_interval": 30,
    "search_timeout": 60
  },
  "search": {
    "max_results": 50,
    "case_sensitive": false,
    "regex_enabled": true,
    "fuzzy_search": false,
    "fuzzy_threshold": 0.8
  }
}
EOF

cat > demo_node.json << 'EOF'
{
  "node": {
    "node_id": "demo_node",
    "host": "localhost",
    "port": 8001,
    "max_connections": 50,
    "search_directories": [
      "./demo_files"
    ],
    "allowed_file_types": [
      ".txt",
      ".md",
      ".py",
      ".log",
      ".json"
    ],
    "max_file_size_mb": 10
  },
  "search": {
    "max_results": 50,
    "case_sensitive": false,
    "regex_enabled": true,
    "fuzzy_search": true,
    "fuzzy_threshold": 0.8
  }
}
EOF

echo "✅ Configuration files created"

echo ""
echo "🚀 To start the distributed search engine:"
echo ""
echo "1. Start the coordinator:"
echo "   search-engine start-coordinator --config-file demo_coordinator.json"
echo ""
echo "2. In another terminal, start a search node:"
echo "   search-engine start-node --config-file demo_node.json --coordinator http://localhost:8000"
echo ""
echo "3. Check system status:"
echo "   search-engine status --coordinator http://localhost:8000"
echo ""
echo "4. Perform searches:"
echo "   search-engine search \"readme\" --type filename --coordinator http://localhost:8000"
echo "   search-engine search \"distributed\" --type content --coordinator http://localhost:8000"
echo "   search-engine search \"\.py$\" --type regex --coordinator http://localhost:8000"
echo ""
echo "5. Download found files:"
echo "   search-engine search \"report\" --download ./downloads/ --coordinator http://localhost:8000"
echo ""
echo "📝 Note: Make sure you have installed the package first:"
echo "   pip install -e ."
echo ""
echo "🧹 To clean up demo files:"
echo "   rm -rf demo_files/ demo_coordinator.json demo_node.json downloads/"