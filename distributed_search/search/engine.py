"""
Search Engine implementation for distributed search
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
import aiohttp
from distributed_search.core.config import SearchConfig


class SearchEngine:
    """
    Main search engine that interfaces with the coordinator
    """
    
    def __init__(self, coordinator_url: str, config: SearchConfig = None):
        self.coordinator_url = coordinator_url
        self.config = config or SearchConfig()
        self.logger = logging.getLogger("SearchEngine")
        
    async def search(
        self, 
        pattern: str, 
        search_type: str = 'filename',
        max_results: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform a distributed search
        
        Args:
            pattern: Search pattern to match
            search_type: Type of search ('filename', 'content', 'regex')
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary containing search results and metadata
        """
        if not pattern.strip():
            raise ValueError("Search pattern cannot be empty")
            
        max_results = max_results or self.config.max_results
        
        search_data = {
            "pattern": pattern,
            "type": search_type,
            "max_results": max_results
        }
        
        self.logger.info(f"Starting search: pattern='{pattern}', type='{search_type}'")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.coordinator_url}/search",
                    json=search_data,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"Search completed: {result.get('total_results', 0)} results found")
                        return result
                    else:
                        error_text = await response.text()
                        raise Exception(f"Search failed with status {response.status}: {error_text}")
                        
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            raise
            
    async def search_filename(self, pattern: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for files by filename pattern"""
        result = await self.search(pattern, 'filename', max_results)
        return result.get('results', [])
        
    async def search_content(self, pattern: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for files by content pattern"""
        result = await self.search(pattern, 'content', max_results)
        return result.get('results', [])
        
    async def search_regex(self, pattern: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for files using regex pattern"""
        result = await self.search(pattern, 'regex', max_results)
        return result.get('results', [])
        
    async def get_coordinator_status(self) -> Dict[str, Any]:
        """Get status of the coordinator"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.coordinator_url}/health",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Coordinator health check failed: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Error getting coordinator status: {e}")
            raise
            
    async def get_nodes_status(self) -> Dict[str, Any]:
        """Get status of all nodes"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.coordinator_url}/nodes",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Failed to get nodes status: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Error getting nodes status: {e}")
            raise
            
    async def download_file(self, file_info: Dict[str, Any], local_path: str) -> bool:
        """
        Download a file from search results
        
        Args:
            file_info: File information from search results
            local_path: Local path to save the file
            
        Returns:
            True if download succeeded, False otherwise
        """
        access_url = file_info.get('access_url')
        if not access_url:
            self.logger.error("No access URL provided for file")
            return False
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(access_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        self.logger.info(f"Downloaded file to {local_path}")
                        return True
                    else:
                        self.logger.error(f"Download failed: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error downloading file: {e}")
            return False