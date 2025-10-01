"""
Search engine implementation
Processes queries and returns ranked results
"""

import re
import logging
from typing import List, Dict, Set
from pathlib import Path


class SearchEngine:
    """
    Search engine for querying indexed documents
    """
    
    def __init__(self, indexer=None):
        """
        Initialize search engine
        
        Args:
            indexer: DocumentIndexer instance
        """
        self.indexer = indexer
        self.logger = logging.getLogger(__name__)
        
    def search(self, query: str, file_type: str = None) -> List[Dict]:
        """
        Search for documents matching query
        
        Args:
            query: Search query string
            file_type: Optional file type filter (e.g., '.txt', '.pdf')
            
        Returns:
            List of matching documents sorted by relevance
        """
        if not self.indexer:
            self.logger.error("No indexer configured")
            return []
            
        results = []
        query_lower = query.lower()
        
        # Search in indexed files
        for file_name, file_list in self.indexer.index.items():
            if self._matches_query(file_name, query_lower):
                for file_info in file_list:
                    # Filter by file type if specified
                    if file_type and file_info['type'] != file_type:
                        continue
                    
                    # Calculate relevance score
                    score = self._calculate_relevance(file_name, query_lower)
                    
                    result = file_info.copy()
                    result['score'] = score
                    results.append(result)
        
        # Sort by relevance score (higher is better)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
        
    def _matches_query(self, file_name: str, query: str) -> bool:
        """
        Check if file name matches query
        
        Args:
            file_name: Name of file
            query: Search query (lowercase)
            
        Returns:
            True if matches, False otherwise
        """
        file_name_lower = file_name.lower()
        
        # Simple substring match
        if query in file_name_lower:
            return True
            
        # Check if all query terms are in file name
        query_terms = query.split()
        return all(term in file_name_lower for term in query_terms)
        
    def _calculate_relevance(self, file_name: str, query: str) -> float:
        """
        Calculate relevance score for a file
        
        Args:
            file_name: Name of file
            query: Search query (lowercase)
            
        Returns:
            Relevance score (0-1)
        """
        file_name_lower = file_name.lower()
        
        # Exact match gets highest score
        if file_name_lower == query:
            return 1.0
            
        # Starts with query gets high score
        if file_name_lower.startswith(query):
            return 0.9
            
        # Contains query as substring
        if query in file_name_lower:
            return 0.7
            
        # Count matching terms
        query_terms = query.split()
        matches = sum(1 for term in query_terms if term in file_name_lower)
        
        if matches > 0:
            return 0.5 * (matches / len(query_terms))
            
        return 0.0
        
    def search_by_type(self, file_type: str) -> List[Dict]:
        """
        Search for all files of a specific type
        
        Args:
            file_type: File extension (e.g., '.txt', '.pdf')
            
        Returns:
            List of matching documents
        """
        if not self.indexer:
            self.logger.error("No indexer configured")
            return []
            
        results = []
        for file_name, file_list in self.indexer.index.items():
            for file_info in file_list:
                if file_info['type'] == file_type:
                    results.append(file_info)
                    
        return results
