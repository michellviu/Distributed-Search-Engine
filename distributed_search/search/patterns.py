"""
Pattern matching utilities for distributed search
"""
import re
import os
import difflib
from typing import List, Optional
from distributed_search.core.config import SearchConfig


class PatternMatcher:
    """
    Advanced pattern matching for search operations
    """
    
    def __init__(self, config: SearchConfig = None):
        self.config = config or SearchConfig()
        
    def match_filename(self, filename: str, pattern: str) -> bool:
        """
        Match pattern against filename
        
        Args:
            filename: The filename to match against
            pattern: The search pattern
            
        Returns:
            True if pattern matches, False otherwise
        """
        if not self.config.case_sensitive:
            filename = filename.lower()
            pattern = pattern.lower()
            
        if self.config.regex_enabled and self._is_regex_pattern(pattern):
            return self._match_regex(filename, pattern)
        else:
            return pattern in filename
            
    def match_content(self, content: str, pattern: str) -> bool:
        """
        Match pattern against file content
        
        Args:
            content: The file content to search in
            pattern: The search pattern
            
        Returns:
            True if pattern matches, False otherwise
        """
        if not self.config.case_sensitive:
            content = content.lower()
            pattern = pattern.lower()
            
        if self.config.regex_enabled and self._is_regex_pattern(pattern):
            return self._match_regex(content, pattern)
        else:
            return pattern in content
            
    def fuzzy_match(self, text: str, pattern: str) -> bool:
        """
        Perform fuzzy matching using difflib
        
        Args:
            text: Text to match against
            pattern: Pattern to search for
            
        Returns:
            True if fuzzy match succeeds, False otherwise
        """
        if not self.config.fuzzy_search:
            return False
            
        if not self.config.case_sensitive:
            text = text.lower()
            pattern = pattern.lower()
            
        # Use sequence matcher for fuzzy matching
        matcher = difflib.SequenceMatcher(None, text, pattern)
        similarity = matcher.ratio()
        
        return similarity >= self.config.fuzzy_threshold
        
    def extract_matches(self, content: str, pattern: str) -> List[str]:
        """
        Extract all matches from content
        
        Args:
            content: Content to search in
            pattern: Pattern to search for
            
        Returns:
            List of matched strings
        """
        matches = []
        
        if self.config.regex_enabled and self._is_regex_pattern(pattern):
            try:
                flags = 0 if self.config.case_sensitive else re.IGNORECASE
                matches = re.findall(pattern, content, flags)
            except re.error:
                # Fallback to simple string search
                pass
                
        if not matches:
            # Simple string search
            search_text = content if self.config.case_sensitive else content.lower()
            search_pattern = pattern if self.config.case_sensitive else pattern.lower()
            
            start = 0
            while True:
                pos = search_text.find(search_pattern, start)
                if pos == -1:
                    break
                matches.append(content[pos:pos + len(pattern)])
                start = pos + 1
                
        return matches
        
    def get_context(self, content: str, pattern: str, context_lines: int = 2) -> List[str]:
        """
        Get context around matches in content
        
        Args:
            content: Content to search in
            pattern: Pattern to search for
            context_lines: Number of lines of context around matches
            
        Returns:
            List of context snippets
        """
        lines = content.split('\n')
        contexts = []
        
        for i, line in enumerate(lines):
            if self.match_content(line, pattern):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                
                context = '\n'.join(lines[start:end])
                contexts.append({
                    'line_number': i + 1,
                    'context': context,
                    'match_line': line
                })
                
        return contexts
        
    def _is_regex_pattern(self, pattern: str) -> bool:
        """
        Check if pattern contains regex special characters
        
        Args:
            pattern: Pattern to check
            
        Returns:
            True if pattern appears to be regex, False otherwise
        """
        regex_chars = set('[](){}^$*+?|\\.')
        return any(char in pattern for char in regex_chars)
        
    def _match_regex(self, text: str, pattern: str) -> bool:
        """
        Perform regex matching
        
        Args:
            text: Text to match against
            pattern: Regex pattern
            
        Returns:
            True if regex matches, False otherwise
        """
        try:
            flags = 0 if self.config.case_sensitive else re.IGNORECASE
            return bool(re.search(pattern, text, flags))
        except re.error:
            # If regex is invalid, fall back to string search
            return pattern in text
            
    def highlight_matches(self, text: str, pattern: str, highlight_format: str = "**{}**") -> str:
        """
        Highlight matches in text
        
        Args:
            text: Text to highlight matches in
            pattern: Pattern to search for
            highlight_format: Format string for highlighting (default: markdown bold)
            
        Returns:
            Text with highlighted matches
        """
        if self.config.regex_enabled and self._is_regex_pattern(pattern):
            try:
                flags = 0 if self.config.case_sensitive else re.IGNORECASE
                
                def replace_func(match):
                    return highlight_format.format(match.group(0))
                    
                return re.sub(pattern, replace_func, text, flags=flags)
            except re.error:
                pass
                
        # Fallback to simple string replacement
        search_text = text if self.config.case_sensitive else text.lower()
        search_pattern = pattern if self.config.case_sensitive else pattern.lower()
        
        if search_pattern in search_text:
            # Find all occurrences and replace them
            result = text
            start = 0
            offset = 0
            
            while True:
                pos = search_text.find(search_pattern, start)
                if pos == -1:
                    break
                    
                # Replace in the result string
                actual_pos = pos + offset
                original_match = text[pos:pos + len(pattern)]
                highlighted = highlight_format.format(original_match)
                
                result = result[:actual_pos] + highlighted + result[actual_pos + len(pattern):]
                
                # Update offset for next iteration
                offset += len(highlighted) - len(pattern)
                start = pos + 1
                
            return result
            
        return text
        
    def validate_pattern(self, pattern: str, search_type: str = 'filename') -> bool:
        """
        Validate search pattern
        
        Args:
            pattern: Pattern to validate
            search_type: Type of search ('filename', 'content', 'regex')
            
        Returns:
            True if pattern is valid, False otherwise
        """
        if not pattern or not pattern.strip():
            return False
            
        if search_type == 'regex' or (self.config.regex_enabled and self._is_regex_pattern(pattern)):
            try:
                re.compile(pattern)
                return True
            except re.error:
                return False
                
        return True
        
    def get_suggestions(self, text: str, pattern: str, max_suggestions: int = 5) -> List[str]:
        """
        Get suggestions for similar matches
        
        Args:
            text: Text to find suggestions in
            pattern: Original pattern
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested matches
        """
        if not self.config.fuzzy_search:
            return []
            
        words = text.split()
        suggestions = []
        
        for word in words:
            similarity = difflib.SequenceMatcher(None, pattern.lower(), word.lower()).ratio()
            if similarity >= 0.6:  # Threshold for suggestions
                suggestions.append((word, similarity))
                
        # Sort by similarity and return top suggestions
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return [word for word, _ in suggestions[:max_suggestions]]