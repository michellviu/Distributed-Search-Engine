"""
Document indexer implementation
Indexes files by name, type, and content for efficient searching
"""

import os
import hashlib
import logging
from typing import Dict, List, Set
from pathlib import Path


class DocumentIndexer:
    """
    Indexes documents for efficient searching
    """
    
    def __init__(self, base_path: str = None):
        """
        Initialize the document indexer
        
        Args:
            base_path: Base directory to index documents from
        """
        self.base_path = base_path
        self.index: Dict[str, List[Dict]] = {}
        self.file_hashes: Dict[str, Set[str]] = {}  # Maps hash to file paths
        self.logger = logging.getLogger(__name__)
        
    def index_directory(self, directory: str):
        """
        Index all files in a directory
        
        Args:
            directory: Path to directory to index
        """
        path = Path(directory)
        if not path.exists():
            self.logger.error(f"Directory does not exist: {directory}")
            return
            
        for file_path in path.rglob('*'):
            if file_path.is_file():
                self.index_file(str(file_path))
                
    def index_file(self, file_path: str):
        """
        Index a single file
        
        Args:
            file_path: Path to file to index
        """
        try:
            path = Path(file_path)
            file_name = path.name
            file_type = path.suffix
            file_size = path.stat().st_size
            
            # Calculate file hash to detect duplicates
            file_hash = self._calculate_hash(file_path)
            
            # Store file information
            file_info = {
                'path': file_path,
                'name': file_name,
                'type': file_type,
                'size': file_size,
                'hash': file_hash
            }
            
            # Index by file name
            if file_name not in self.index:
                self.index[file_name] = []
            self.index[file_name].append(file_info)
            
            # Track duplicates by hash
            if file_hash not in self.file_hashes:
                self.file_hashes[file_hash] = set()
            self.file_hashes[file_hash].add(file_path)
            
            self.logger.debug(f"Indexed file: {file_path}")
            
        except Exception as e:
            self.logger.error(f"Error indexing file {file_path}: {e}")
            
    def _calculate_hash(self, file_path: str) -> str:
        """
        Calculate SHA256 hash of file
        
        Args:
            file_path: Path to file
            
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""
            
    def get_duplicates(self, file_path: str) -> Set[str]:
        """
        Find duplicate files based on hash
        
        Args:
            file_path: Path to file
            
        Returns:
            Set of paths to duplicate files
        """
        file_hash = self._calculate_hash(file_path)
        if file_hash in self.file_hashes:
            return self.file_hashes[file_hash] - {file_path}
        return set()
        
    def remove_file(self, file_path: str):
        """
        Remove file from index
        
        Args:
            file_path: Path to file to remove
        """
        path = Path(file_path)
        file_name = path.name
        
        if file_name in self.index:
            self.index[file_name] = [
                f for f in self.index[file_name] if f['path'] != file_path
            ]
            if not self.index[file_name]:
                del self.index[file_name]
