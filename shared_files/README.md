# Shared Files Directory

This directory contains files that will be indexed and made searchable by the centralized search engine.

## Purpose

- Files placed in this directory are automatically indexed when the server starts
- The indexer scans all files and subdirectories recursively
- Files can be searched by name and type

## Example Files

The following example files are provided for testing:
- `ejemplo1.txt` - Example text document about distributed systems
- `ejemplo2.pdf` - Another example document about file searching
- `reporte_final.txt` - Final project report

## Usage

1. Add your files to this directory
2. Start the server: `cd ../src && python3 main_server.py`
3. The server will automatically index all files
4. Use the client to search: `python3 main_client.py --query "ejemplo"`

## Notes

- Supported file types: all files can be indexed
- Search is performed on file names and extensions
- Duplicate files (same content, different names) are detected using SHA256 hashing
