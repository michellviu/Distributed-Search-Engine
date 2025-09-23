# Example Usage Guide

This directory contains example configurations and scripts for the Distributed Search Engine.

## Files

- `coordinator_config.json` - Example configuration for the search coordinator
- `node_config.json` - Example configuration for a search node
- `demo.sh` - Interactive demo script that sets up a complete example environment

## Quick Demo

Run the demo script to see the distributed search engine in action:

```bash
./examples/demo.sh
```

This will:
1. Create sample files to search
2. Generate configuration files
3. Provide step-by-step instructions to start the system

## Manual Setup

### 1. Start the Coordinator

```bash
search-engine start-coordinator --config-file examples/coordinator_config.json
```

### 2. Start Search Nodes

```bash
# Node 1
search-engine start-node --config-file examples/node_config.json --coordinator http://localhost:8000
```

### 3. Perform Searches

```bash
# Search by filename
search-engine search "document" --type filename --coordinator http://localhost:8000

# Search by content
search-engine search "distributed system" --type content --coordinator http://localhost:8000

# Search with regex
search-engine search "\.py$" --type regex --coordinator http://localhost:8000
```

### 4. Check System Status

```bash
search-engine status --coordinator http://localhost:8000
```

## Production Deployment

For production deployment, consider:

1. **Security**: Use HTTPS and implement authentication
2. **Configuration**: Store configurations in secure locations
3. **Monitoring**: Set up health checks and logging
4. **Scaling**: Deploy multiple nodes across different machines
5. **Backup**: Regular backup of file indices

## Network Setup

For multi-machine deployment:

1. Update `host` to `0.0.0.0` in configurations
2. Configure firewall rules for the ports (default 8000-8003)
3. Update coordinator URL in node configurations
4. Ensure network connectivity between all machines

Example network configuration:

```
Machine 1 (Coordinator): 192.168.1.10:8000
Machine 2 (Node 1):     192.168.1.11:8001
Machine 3 (Node 2):     192.168.1.12:8001
```

Update node configurations to point to coordinator:
```bash
search-engine start-node --node-id node1 --host 0.0.0.0 --port 8001 --coordinator http://192.168.1.10:8000
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check if coordinator is running and ports are open
2. **No Results**: Verify search directories exist and are readable
3. **Permission Denied**: Check file and directory permissions

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
search-engine --verbose start-coordinator
search-engine --verbose start-node --node-id debug_node --port 8001
```