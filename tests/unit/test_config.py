"""
Test configuration and search functionality
"""
import pytest
import tempfile
import os
from distributed_search.core.config import Config, NodeConfig, CoordinatorConfig, SearchConfig


class TestConfig:
    """Test configuration management"""
    
    def test_node_config_creation(self):
        """Test creating a node configuration"""
        config = NodeConfig(
            node_id="test_node",
            host="localhost",
            port=8001,
            search_directories=["/tmp/test"]
        )
        
        assert config.node_id == "test_node"
        assert config.host == "localhost"
        assert config.port == 8001
        assert "/tmp/test" in config.search_directories
        
    def test_coordinator_config_creation(self):
        """Test creating a coordinator configuration"""
        config = CoordinatorConfig(
            coordinator_id="test_coordinator",
            host="localhost",
            port=8000
        )
        
        assert config.coordinator_id == "test_coordinator"
        assert config.host == "localhost"
        assert config.port == 8000
        
    def test_search_config_creation(self):
        """Test creating a search configuration"""
        config = SearchConfig(
            max_results=50,
            case_sensitive=True,
            regex_enabled=False
        )
        
        assert config.max_results == 50
        assert config.case_sensitive is True
        assert config.regex_enabled is False
        
    def test_config_serialization(self):
        """Test configuration serialization to/from file"""
        config = Config(
            node=NodeConfig(
                node_id="test_node",
                port=8001
            ),
            search=SearchConfig(
                max_results=25
            )
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config.save_to_file(f.name)
            
            # Load config back
            loaded_config = Config.load_from_file(f.name)
            
            assert loaded_config.node.node_id == "test_node"
            assert loaded_config.node.port == 8001
            assert loaded_config.search.max_results == 25
            
            # Clean up
            os.unlink(f.name)


if __name__ == '__main__':
    pytest.main([__file__])