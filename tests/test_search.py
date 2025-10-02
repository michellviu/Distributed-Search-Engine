"""
Tests for search engine
"""

import unittest
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.indexer.indexer import DocumentIndexer
from src.search.search_engine import SearchEngine


class TestSearchEngine(unittest.TestCase):
    """Test cases for SearchEngine class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.indexer = DocumentIndexer(self.temp_dir)
        self.search_engine = SearchEngine(self.indexer)
        
        # Create and index test files
        files = [
            ("document1.txt", "Test content 1"),
            ("document2.pdf", "Test content 2"),
            ("report.txt", "Test content 3"),
            ("data.csv", "Test content 4")
        ]
        
        for filename, content in files:
            file_path = Path(self.temp_dir) / filename
            file_path.write_text(content)
            self.indexer.index_file(str(file_path))
        
    def test_search_basic(self):
        """Test basic search functionality"""
        results = self.search_engine.search("document")
        
        # Should find document1.txt and document2.pdf
        self.assertEqual(len(results), 2)
        names = [r['name'] for r in results]
        self.assertIn("document1.txt", names)
        self.assertIn("document2.pdf", names)
        
    def test_search_with_type_filter(self):
        """Test search with file type filter"""
        results = self.search_engine.search("document", file_type=".txt")
        
        # Should only find document1.txt
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], "document1.txt")
        
    def test_search_by_type(self):
        """Test searching by file type only"""
        results = self.search_engine.search_by_type(".txt")
        
        # Should find document1.txt and report.txt
        self.assertEqual(len(results), 2)
        
    def test_search_no_results(self):
        """Test search with no results"""
        results = self.search_engine.search("nonexistent")
        
        self.assertEqual(len(results), 0)
        
    def test_relevance_scoring(self):
        """Test that results are sorted by relevance"""
        results = self.search_engine.search("document")
        
        # Results should be sorted by score (descending)
        if len(results) > 1:
            for i in range(len(results) - 1):
                self.assertGreaterEqual(results[i]['score'], results[i + 1]['score'])
        
    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()
