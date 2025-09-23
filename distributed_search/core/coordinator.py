"""
Search Coordinator implementation for distributed search engine
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
import aiohttp
from aiohttp import web
from .config import CoordinatorConfig


class SearchCoordinator:
    """
    Central coordinator that manages search nodes and distributes search requests
    """
    
    def __init__(self, config: CoordinatorConfig):
        self.config = config
        self.logger = logging.getLogger(f"SearchCoordinator-{config.coordinator_id}")
        self.app = web.Application()
        self.setup_routes()
        
        # Registry of active nodes
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.node_last_seen: Dict[str, float] = {}
        
        # Search request tracking
        self.active_searches: Dict[str, Dict[str, Any]] = {}
        
    def setup_routes(self):
        """Setup HTTP routes for the coordinator"""
        self.app.router.add_post('/register', self.register_node)
        self.app.router.add_post('/search', self.handle_search_request)
        self.app.router.add_get('/nodes', self.list_nodes)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_delete('/nodes/{node_id}', self.unregister_node)
        
    async def health_check(self, request):
        """Health check endpoint"""
        active_nodes = len([n for n, last_seen in self.node_last_seen.items() 
                           if time.time() - last_seen < 2 * self.config.heartbeat_interval])
        
        return web.json_response({
            "status": "healthy",
            "coordinator_id": self.config.coordinator_id,
            "total_nodes": len(self.nodes),
            "active_nodes": active_nodes,
            "active_searches": len(self.active_searches)
        })
        
    async def register_node(self, request):
        """Register a new search node"""
        try:
            data = await request.json()
            node_id = data.get('node_id')
            
            if not node_id:
                return web.json_response(
                    {"error": "node_id is required"}, 
                    status=400
                )
                
            # Store node information
            self.nodes[node_id] = {
                "node_id": node_id,
                "host": data.get('host', 'localhost'),
                "port": data.get('port', 8001),
                "capabilities": data.get('capabilities', {}),
                "registered_at": time.time()
            }
            
            self.node_last_seen[node_id] = time.time()
            
            self.logger.info(f"Registered node: {node_id}")
            
            return web.json_response({
                "status": "registered",
                "node_id": node_id,
                "message": f"Node {node_id} registered successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Error registering node: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
            
    async def unregister_node(self, request):
        """Unregister a search node"""
        node_id = request.match_info['node_id']
        
        if node_id in self.nodes:
            del self.nodes[node_id]
            if node_id in self.node_last_seen:
                del self.node_last_seen[node_id]
                
            self.logger.info(f"Unregistered node: {node_id}")
            return web.json_response({
                "status": "unregistered",
                "node_id": node_id
            })
        else:
            return web.json_response(
                {"error": "Node not found"}, 
                status=404
            )
            
    async def list_nodes(self, request):
        """List all registered nodes"""
        current_time = time.time()
        node_list = []
        
        for node_id, node_info in self.nodes.items():
            last_seen = self.node_last_seen.get(node_id, 0)
            is_active = (current_time - last_seen) < 2 * self.config.heartbeat_interval
            
            node_list.append({
                **node_info,
                "last_seen": last_seen,
                "is_active": is_active,
                "seconds_since_last_seen": current_time - last_seen
            })
            
        return web.json_response({
            "nodes": node_list,
            "total_count": len(node_list),
            "active_count": len([n for n in node_list if n["is_active"]])
        })
        
    async def handle_search_request(self, request):
        """Handle distributed search request"""
        try:
            data = await request.json()
            pattern = data.get('pattern', '')
            search_type = data.get('type', 'filename')
            max_results = data.get('max_results', 100)
            
            if not pattern:
                return web.json_response(
                    {"error": "search pattern is required"}, 
                    status=400
                )
                
            self.logger.info(f"Received search request: pattern='{pattern}', type='{search_type}'")
            
            # Generate search ID
            search_id = f"search_{int(time.time())}_{len(self.active_searches)}"
            
            # Track search
            self.active_searches[search_id] = {
                "pattern": pattern,
                "search_type": search_type,
                "max_results": max_results,
                "started_at": time.time(),
                "status": "in_progress"
            }
            
            try:
                # Distribute search to all active nodes
                results = await self.distribute_search(pattern, search_type, max_results)
                
                self.active_searches[search_id]["status"] = "completed"
                self.active_searches[search_id]["results_count"] = len(results)
                
                return web.json_response({
                    "search_id": search_id,
                    "pattern": pattern,
                    "search_type": search_type,
                    "results": results,
                    "total_results": len(results),
                    "nodes_searched": len(self.get_active_nodes()),
                    "status": "success"
                })
                
            except Exception as e:
                self.active_searches[search_id]["status"] = "failed"
                self.active_searches[search_id]["error"] = str(e)
                raise
                
        except Exception as e:
            self.logger.error(f"Error handling search request: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
        finally:
            # Clean up old searches
            await self.cleanup_old_searches()
            
    def get_active_nodes(self) -> List[Dict[str, Any]]:
        """Get list of currently active nodes"""
        current_time = time.time()
        active_nodes = []
        
        for node_id, node_info in self.nodes.items():
            last_seen = self.node_last_seen.get(node_id, 0)
            if (current_time - last_seen) < 2 * self.config.heartbeat_interval:
                active_nodes.append(node_info)
                
        return active_nodes
        
    async def distribute_search(self, pattern: str, search_type: str, max_results: int) -> List[Dict[str, Any]]:
        """Distribute search request to all active nodes"""
        active_nodes = self.get_active_nodes()
        
        if not active_nodes:
            self.logger.warning("No active nodes available for search")
            return []
            
        self.logger.info(f"Distributing search to {len(active_nodes)} nodes")
        
        # Create search tasks for each node
        search_tasks = []
        for node in active_nodes:
            task = self.search_node(node, pattern, search_type)
            search_tasks.append(task)
            
        # Wait for all searches to complete or timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*search_tasks, return_exceptions=True),
                timeout=self.config.search_timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"Search timed out after {self.config.search_timeout} seconds")
            results = []
            
        # Combine results from all nodes
        combined_results = []
        for result in results:
            if isinstance(result, list):
                combined_results.extend(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Node search error: {result}")
                
        # Sort and limit results
        combined_results.sort(key=lambda x: x.get('modified_time', 0), reverse=True)
        return combined_results[:max_results]
        
    async def search_node(self, node: Dict[str, Any], pattern: str, search_type: str) -> List[Dict[str, Any]]:
        """Search a specific node"""
        node_url = f"http://{node['host']}:{node['port']}"
        
        search_data = {
            "pattern": pattern,
            "type": search_type
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{node_url}/search",
                    json=search_data,
                    timeout=aiohttp.ClientTimeout(total=self.config.search_timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('results', [])
                    else:
                        self.logger.error(f"Node {node['node_id']} returned status {response.status}")
                        return []
                        
        except Exception as e:
            self.logger.error(f"Error searching node {node['node_id']}: {e}")
            return []
            
    async def cleanup_old_searches(self):
        """Clean up old search records"""
        current_time = time.time()
        cutoff_time = current_time - 3600  # Keep searches for 1 hour
        
        old_searches = [
            search_id for search_id, search_info in self.active_searches.items()
            if search_info.get('started_at', 0) < cutoff_time
        ]
        
        for search_id in old_searches:
            del self.active_searches[search_id]
            
    async def start_heartbeat_monitor(self):
        """Start monitoring node heartbeats"""
        while True:
            try:
                await self.check_node_health()
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(self.config.heartbeat_interval)
                
    async def check_node_health(self):
        """Check health of all registered nodes"""
        current_time = time.time()
        
        for node_id, node_info in list(self.nodes.items()):
            try:
                node_url = f"http://{node_info['host']}:{node_info['port']}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{node_url}/health",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            self.node_last_seen[node_id] = current_time
                        else:
                            self.logger.warning(f"Node {node_id} health check failed: {response.status}")
                            
            except Exception as e:
                self.logger.warning(f"Node {node_id} unreachable: {e}")
                
        # Remove nodes that haven't been seen for too long
        offline_nodes = [
            node_id for node_id, last_seen in self.node_last_seen.items()
            if current_time - last_seen > 3 * self.config.heartbeat_interval
        ]
        
        for node_id in offline_nodes:
            self.logger.info(f"Removing offline node: {node_id}")
            if node_id in self.nodes:
                del self.nodes[node_id]
            if node_id in self.node_last_seen:
                del self.node_last_seen[node_id]
                
    async def start(self):
        """Start the search coordinator"""
        self.logger.info(f"Starting search coordinator on {self.config.host}:{self.config.port}")
        
        # Start heartbeat monitoring
        asyncio.create_task(self.start_heartbeat_monitor())
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        self.logger.info(f"Search coordinator started successfully")
        
    async def stop(self):
        """Stop the search coordinator"""
        self.logger.info("Stopping search coordinator")