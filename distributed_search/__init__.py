"""
Distributed Search Engine

A distributed document search system for locating files across multiple computers
based on search patterns and allowing access to identified documents.
"""

__version__ = "0.1.0"
__author__ = "Michelle Liu"

from .core.node import SearchNode
from .core.coordinator import SearchCoordinator
from .search.engine import SearchEngine
from .search.patterns import PatternMatcher

__all__ = [
    "SearchNode",
    "SearchCoordinator", 
    "SearchEngine",
    "PatternMatcher",
]