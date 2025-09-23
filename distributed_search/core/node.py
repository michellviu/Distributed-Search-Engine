"""
Search Node implementation for distributed search engine
"""
import asyncio
import os
import logging
from typing import List, Dict, Any, Optional
import aiohttp
from aiohttp import web
import psutil
from .config import NodeConfig, Config


class SearchNode:
    """
    A search node that can search local files and communicate with the coordinator
    """
    
    def __init__(self, config: NodeConfig):
        self.config = config
        self.logger = logging.getLogger(f"SearchNode-{config.node_id}")
        self.app = web.Application()
        self.setup_routes()
        self.coordinator_url: Optional[str] = None
        self.is_running = False
        
    def setup_routes(self):
        """Setup HTTP routes for the node"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_post('/search', self.handle_search_request)
        self.app.router.add_get('/status', self.get_status)
        self.app.router.add_get('/files/{file_path:.*}', self.serve_file)
        
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "node_id": self.config.node_id,
            "uptime": "TODO",  # Implement uptime tracking
            "memory_usage": psutil.virtual_memory().percent,
            "cpu_usage": psutil.cpu_percent()
        })
        
    async def handle_search_request(self, request):
        """Handle search request from coordinator"""
        try:
            data = await request.json()
            pattern = data.get('pattern', '')
            search_type = data.get('type', 'filename')
            
            self.logger.info(f"Received search request: pattern='{pattern}', type='{search_type}'")
            
            results = await self.search_local_files(pattern, search_type)
            
            return web.json_response({
                "node_id": self.config.node_id,
                "results": results,
                "status": "success"
            })
            
        except Exception as e:
            self.logger.error(f"Error handling search request: {e}")
            return web.json_response({
                "node_id": self.config.node_id,
                "error": str(e),
                "status": "error"
            }, status=500)
            
    async def search_local_files(self, pattern: str, search_type: str = 'filename') -> List[Dict[str, Any]]:
        """Search for files matching the pattern in local directories"""
        results = []
        
        for directory in self.config.search_directories:
            if not os.path.exists(directory):
                self.logger.warning(f"Directory does not exist: {directory}")
                continue
                
            try:
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        file_path = os.path.join(root, file)
                        
                        # Check file type filter
                        _, ext = os.path.splitext(file)
                        if ext.lower() not in self.config.allowed_file_types:
                            continue
                            
                        # Check file size
                        try:
                            file_size = os.path.getsize(file_path)
                            if file_size > self.config.max_file_size_mb * 1024 * 1024:
                                continue
                        except OSError:
                            continue
                            
                        # Perform pattern matching
                        if await self.matches_pattern(file_path, pattern, search_type):
                            stat = os.stat(file_path)
                            results.append({
                                "file_path": file_path,
                                "file_name": file,
                                "file_size": file_size,
                                "modified_time": stat.st_mtime,
                                "node_id": self.config.node_id,
                                "access_url": f"http://{self.config.host}:{self.config.port}/files/{file_path}"
                            })
                            
            except Exception as e:
                self.logger.error(f"Error searching directory {directory}: {e}")
                
        return results
        
    async def matches_pattern(self, file_path: str, pattern: str, search_type: str) -> bool:
        """Check if file matches the search pattern"""
        import re
        
        if search_type == 'filename':
            file_name = os.path.basename(file_path)
            return pattern.lower() in file_name.lower()
            
        elif search_type == 'content':
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    return pattern.lower() in content.lower()
            except:
                return False
                
        elif search_type == 'regex':
            try:
                file_name = os.path.basename(file_path)
                return bool(re.search(pattern, file_name, re.IGNORECASE))
            except re.error:
                return False
                
        return False
        
    async def get_status(self, request):
        """Get node status information"""
        return web.json_response({
            "node_id": self.config.node_id,
            "host": self.config.host,
            "port": self.config.port,
            "search_directories": self.config.search_directories,
            "allowed_file_types": self.config.allowed_file_types,
            "is_running": self.is_running,
            "system_info": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": {path: psutil.disk_usage(path).percent 
                              for path in self.config.search_directories 
                              if os.path.exists(path)}
            }
        })
        
    async def serve_file(self, request):
        """Serve file for download"""
        file_path = request.match_info['file_path']
        
        if not os.path.exists(file_path):
            return web.Response(status=404, text="File not found")
            
        # Security check - ensure file is in allowed directories
        allowed = False
        for allowed_dir in self.config.search_directories:
            if file_path.startswith(os.path.abspath(allowed_dir)):
                allowed = True
                break
                
        if not allowed:
            return web.Response(status=403, text="Access denied")
            
        return web.FileResponse(file_path)
        
    async def register_with_coordinator(self, coordinator_url: str):
        """Register this node with the coordinator"""
        self.coordinator_url = coordinator_url
        
        registration_data = {
            "node_id": self.config.node_id,
            "host": self.config.host,
            "port": self.config.port,
            "capabilities": {
                "search_directories": self.config.search_directories,
                "allowed_file_types": self.config.allowed_file_types,
                "max_file_size_mb": self.config.max_file_size_mb
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{coordinator_url}/register",
                    json=registration_data
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Successfully registered with coordinator at {coordinator_url}")
                        return True
                    else:
                        self.logger.error(f"Failed to register with coordinator: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error registering with coordinator: {e}")
            return False
            
    async def start(self, coordinator_url: Optional[str] = None):
        """Start the search node"""
        self.logger.info(f"Starting search node {self.config.node_id} on {self.config.host}:{self.config.port}")
        
        if coordinator_url:
            await self.register_with_coordinator(coordinator_url)
            
        self.is_running = True
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        self.logger.info(f"Search node {self.config.node_id} started successfully")
        
    async def stop(self):
        """Stop the search node"""
        self.logger.info(f"Stopping search node {self.config.node_id}")
        self.is_running = False