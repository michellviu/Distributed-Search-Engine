"""
Tests for document indexer
"""

import unittest
import tempfile
import os
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.indexer.indexer import DocumentIndexer


class TestDocumentIndexer(unittest.TestCase):
    """Test cases for DocumentIndexer class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.indexer = DocumentIndexer(self.temp_dir)
        
    def test_index_file(self):
        """Test indexing a single file"""
        # Create a test file
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("Test content")
        
        # Index the file
        self.indexer.index_file(str(test_file))
        
        # Verify it was indexed
        self.assertIn("test.txt", self.indexer.index)
        self.assertEqual(len(self.indexer.index["test.txt"]), 1)
        
    def test_index_directory(self):
        """Test indexing a directory"""
        # Create test files
        (Path(self.temp_dir) / "file1.txt").write_text("Content 1")
        (Path(self.temp_dir) / "file2.pdf").write_text("Content 2")
        
        # Index the directory
        self.indexer.index_directory(self.temp_dir)
        
        # Verify files were indexed
        self.assertIn("file1.txt", self.indexer.index)
        self.assertIn("file2.pdf", self.indexer.index)
        
    def test_duplicate_detection(self):
        """Test duplicate file detection"""
        # Create two files with same content
        file1 = Path(self.temp_dir) / "original.txt"
        file2 = Path(self.temp_dir) / "duplicate.txt"
        
        content = "Same content"
        file1.write_text(content)
        file2.write_text(content)
        
        # Index both files
        self.indexer.index_file(str(file1))
        self.indexer.index_file(str(file2))
        
        # Check for duplicates
        duplicates = self.indexer.get_duplicates(str(file1))
        self.assertIn(str(file2), duplicates)
        
    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()
