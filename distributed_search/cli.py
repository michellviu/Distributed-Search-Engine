"""
Command Line Interface for distributed search engine
"""
import asyncio
import logging
import os
import sys
import json
from typing import Optional
import click
from distributed_search.core.config import Config, NodeConfig, CoordinatorConfig
from distributed_search.core.node import SearchNode
from distributed_search.core.coordinator import SearchCoordinator
from distributed_search.search.engine import SearchEngine


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@click.group()
@click.option('--config', '-c', help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, config, verbose):
    """Distributed Search Engine CLI"""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    ctx.ensure_object(dict)
    ctx.obj['config_file'] = config
    

@cli.command()
@click.option('--host', default='localhost', help='Host to bind to')
@click.option('--port', default=8000, type=int, help='Port to bind to')
@click.option('--config-file', help='Save configuration to file')
@click.pass_context
def start_coordinator(ctx, host, port, config_file):
    """Start the search coordinator"""
    config = CoordinatorConfig(
        host=host,
        port=port
    )
    
    if config_file:
        main_config = Config(coordinator=config)
        main_config.save_to_file(config_file)
        click.echo(f"Configuration saved to {config_file}")
    
    coordinator = SearchCoordinator(config)
    
    click.echo(f"Starting search coordinator on {host}:{port}")
    
    try:
        asyncio.run(coordinator.start())
        # Keep running
        asyncio.run(asyncio.Event().wait())
    except KeyboardInterrupt:
        click.echo("\nShutting down coordinator...")
        asyncio.run(coordinator.stop())


@cli.command()
@click.option('--node-id', required=True, help='Unique node identifier')
@click.option('--host', default='localhost', help='Host to bind to')
@click.option('--port', default=8001, type=int, help='Port to bind to')
@click.option('--coordinator', default='http://localhost:8000', help='Coordinator URL')
@click.option('--search-dirs', multiple=True, help='Directories to search (can be specified multiple times)')
@click.option('--config-file', help='Save configuration to file')
@click.pass_context
def start_node(ctx, node_id, host, port, coordinator, search_dirs, config_file):
    """Start a search node"""
    config = NodeConfig(
        node_id=node_id,
        host=host,
        port=port,
        search_directories=list(search_dirs) if search_dirs else [os.getcwd()]
    )
    
    if config_file:
        main_config = Config(node=config)
        main_config.save_to_file(config_file)
        click.echo(f"Configuration saved to {config_file}")
    
    node = SearchNode(config)
    
    click.echo(f"Starting search node '{node_id}' on {host}:{port}")
    click.echo(f"Search directories: {config.search_directories}")
    click.echo(f"Coordinator: {coordinator}")
    
    try:
        asyncio.run(node.start(coordinator))
        # Keep running
        asyncio.run(asyncio.Event().wait())
    except KeyboardInterrupt:
        click.echo(f"\nShutting down node '{node_id}'...")
        asyncio.run(node.stop())


@cli.command()
@click.argument('pattern')
@click.option('--coordinator', default='http://localhost:8000', help='Coordinator URL')
@click.option('--type', 'search_type', default='filename', 
              type=click.Choice(['filename', 'content', 'regex']), 
              help='Search type')
@click.option('--max-results', default=100, type=int, help='Maximum number of results')
@click.option('--output', '-o', help='Output file for results (JSON format)')
@click.option('--download', help='Download directory for files')
@click.pass_context
def search(ctx, pattern, coordinator, search_type, max_results, output, download):
    """Search for files across the distributed network"""
    async def perform_search():
        engine = SearchEngine(coordinator)
        
        try:
            # Check coordinator status
            status = await engine.get_coordinator_status()
            click.echo(f"Connected to coordinator (Active nodes: {status.get('active_nodes', 0)})")
            
            # Perform search
            click.echo(f"Searching for pattern: '{pattern}' (type: {search_type})")
            
            result = await engine.search(pattern, search_type, max_results)
            
            results = result.get('results', [])
            total = result.get('total_results', 0)
            nodes_searched = result.get('nodes_searched', 0)
            
            click.echo(f"\nSearch completed:")
            click.echo(f"  Total results: {total}")
            click.echo(f"  Nodes searched: {nodes_searched}")
            click.echo(f"  Search ID: {result.get('search_id', 'N/A')}")
            
            if results:
                click.echo("\nResults:")
                for i, file_info in enumerate(results, 1):
                    click.echo(f"  {i}. {file_info['file_name']}")
                    click.echo(f"     Path: {file_info['file_path']}")
                    click.echo(f"     Size: {file_info['file_size']} bytes")
                    click.echo(f"     Node: {file_info['node_id']}")
                    click.echo(f"     URL: {file_info['access_url']}")
                    click.echo()
                    
                # Save results to file if requested
                if output:
                    with open(output, 'w') as f:
                        json.dump(result, f, indent=2)
                    click.echo(f"Results saved to {output}")
                    
                # Download files if requested
                if download:
                    os.makedirs(download, exist_ok=True)
                    click.echo(f"\nDownloading files to {download}...")
                    
                    for file_info in results:
                        filename = file_info['file_name']
                        local_path = os.path.join(download, filename)
                        
                        # Handle duplicate filenames
                        counter = 1
                        original_path = local_path
                        while os.path.exists(local_path):
                            base, ext = os.path.splitext(original_path)
                            local_path = f"{base}_{counter}{ext}"
                            counter += 1
                            
                        success = await engine.download_file(file_info, local_path)
                        if success:
                            click.echo(f"  Downloaded: {filename} -> {local_path}")
                        else:
                            click.echo(f"  Failed to download: {filename}")
            else:
                click.echo("\nNo results found.")
                
        except Exception as e:
            click.echo(f"Search error: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(perform_search())


@cli.command()
@click.option('--coordinator', default='http://localhost:8000', help='Coordinator URL')
@click.pass_context
def status(ctx, coordinator):
    """Get status of the distributed search network"""
    async def get_status():
        engine = SearchEngine(coordinator)
        
        try:
            # Get coordinator status
            coord_status = await engine.get_coordinator_status()
            click.echo("Coordinator Status:")
            click.echo(f"  Status: {coord_status.get('status', 'unknown')}")
            click.echo(f"  Total nodes: {coord_status.get('total_nodes', 0)}")
            click.echo(f"  Active nodes: {coord_status.get('active_nodes', 0)}")
            click.echo(f"  Active searches: {coord_status.get('active_searches', 0)}")
            
            # Get nodes status
            nodes_status = await engine.get_nodes_status()
            nodes = nodes_status.get('nodes', [])
            
            click.echo(f"\nNodes ({len(nodes)}):")
            if nodes:
                for node in nodes:
                    status_indicator = "🟢" if node.get('is_active') else "🔴"
                    click.echo(f"  {status_indicator} {node['node_id']} ({node['host']}:{node['port']})")
                    
                    capabilities = node.get('capabilities', {})
                    search_dirs = capabilities.get('search_directories', [])
                    if search_dirs:
                        click.echo(f"    Search directories: {', '.join(search_dirs[:3])}")
                        if len(search_dirs) > 3:
                            click.echo(f"    ... and {len(search_dirs) - 3} more")
                    
                    if not node.get('is_active'):
                        last_seen = node.get('seconds_since_last_seen', 0)
                        click.echo(f"    Last seen: {last_seen:.0f} seconds ago")
            else:
                click.echo("  No nodes registered")
                
        except Exception as e:
            click.echo(f"Status error: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(get_status())


@cli.command()
@click.option('--output', '-o', default='search_config.json', help='Output configuration file')
@click.pass_context
def init_config(ctx, output):
    """Initialize a configuration file with default settings"""
    config = Config(
        coordinator=CoordinatorConfig(),
        node=NodeConfig(
            node_id="node_1",
            port=8001,
            search_directories=[os.getcwd()]
        )
    )
    
    config.save_to_file(output)
    click.echo(f"Configuration file created: {output}")
    click.echo("Edit the file to customize settings, then use:")
    click.echo(f"  search-engine start-coordinator --config-file {output}")
    click.echo(f"  search-engine start-node --config-file {output}")


def main():
    """Main entry point"""
    cli()


if __name__ == '__main__':
    main()