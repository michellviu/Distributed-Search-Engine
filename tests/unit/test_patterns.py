"""
Test pattern matching functionality
"""
import pytest
from distributed_search.search.patterns import PatternMatcher
from distributed_search.core.config import SearchConfig


class TestPatternMatcher:
    """Test pattern matching functionality"""
    
    def setup_method(self):
        """Setup test environment"""
        self.config = SearchConfig(
            case_sensitive=False,
            regex_enabled=True,
            fuzzy_search=True,
            fuzzy_threshold=0.8
        )
        self.matcher = PatternMatcher(self.config)
        
    def test_filename_matching(self):
        """Test filename pattern matching"""
        # Simple substring matching
        assert self.matcher.match_filename("test_file.txt", "test")
        assert self.matcher.match_filename("document.pdf", "doc")
        assert not self.matcher.match_filename("image.jpg", "text")
        
        # Case insensitive matching
        assert self.matcher.match_filename("TestFile.TXT", "testfile")
        
    def test_content_matching(self):
        """Test content pattern matching"""
        content = "This is a test document with some sample text."
        
        assert self.matcher.match_content(content, "test")
        assert self.matcher.match_content(content, "sample")
        assert not self.matcher.match_content(content, "missing")
        
    def test_regex_matching(self):
        """Test regex pattern matching"""
        # Test regex detection
        assert self.matcher._is_regex_pattern(r"\d+")
        assert self.matcher._is_regex_pattern(r"test.*\.txt")
        assert not self.matcher._is_regex_pattern("simple")
        
        # Test regex matching
        assert self.matcher.match_filename("file123.txt", r"\d+")
        assert self.matcher.match_filename("test_document.txt", r"test.*\.txt")
        
    def test_fuzzy_matching(self):
        """Test fuzzy pattern matching"""
        # Similar strings should match
        assert self.matcher.fuzzy_match("hello", "helo")
        assert self.matcher.fuzzy_match("document", "documnet")
        
        # Very different strings should not match
        assert not self.matcher.fuzzy_match("hello", "world")
        
    def test_extract_matches(self):
        """Test match extraction"""
        content = "Find test1 and test2 in this text"
        matches = self.matcher.extract_matches(content, r"test\d+")
        
        assert len(matches) == 2
        assert "test1" in matches
        assert "test2" in matches
        
    def test_pattern_validation(self):
        """Test pattern validation"""
        # Valid patterns
        assert self.matcher.validate_pattern("simple")
        assert self.matcher.validate_pattern(r"\d+")
        
        # Invalid patterns
        assert not self.matcher.validate_pattern("")
        assert not self.matcher.validate_pattern("   ")
        
    def test_highlight_matches(self):
        """Test match highlighting"""
        text = "This is a test document"
        highlighted = self.matcher.highlight_matches(text, "test")
        
        assert "**test**" in highlighted
        assert "This is a **test** document" == highlighted


if __name__ == '__main__':
    pytest.main([__file__])