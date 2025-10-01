"""
Configuration management
"""

import json
import os
from typing import Dict, Any
from pathlib import Path


class Config:
    """
    Configuration manager for the search engine
    """
    
    DEFAULT_CONFIG = {
        'server': {
            'host': 'localhost',
            'port': 5000,
            'max_connections': 5
        },
        'indexer': {
            'base_path': './shared_files',
            'auto_index': True,
            'watch_changes': True
        },
        'transfer': {
            'chunk_size': 4096,
            'max_retries': 3,
            'timeout': 30
        },
        'logging': {
            'level': 'INFO',
            'file': 'search_engine.log',
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    }
    
    def __init__(self, config_file: str = None):
        """
        Initialize configuration
        
        Args:
            config_file: Path to configuration file (JSON)
        """
        self.config = self.DEFAULT_CONFIG.copy()
        if config_file and Path(config_file).exists():
            self.load_from_file(config_file)
            
    def load_from_file(self, config_file: str):
        """
        Load configuration from JSON file
        
        Args:
            config_file: Path to configuration file
        """
        try:
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                self._merge_config(user_config)
        except Exception as e:
            print(f"Error loading config file: {e}")
            
    def _merge_config(self, user_config: Dict[str, Any]):
        """
        Merge user configuration with default configuration
        
        Args:
            user_config: User-provided configuration
        """
        for key, value in user_config.items():
            if key in self.config and isinstance(value, dict):
                self.config[key].update(value)
            else:
                self.config[key] = value
                
    def get(self, section: str, key: str = None, default=None):
        """
        Get configuration value
        
        Args:
            section: Configuration section
            key: Configuration key within section
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        if key is None:
            return self.config.get(section, default)
        return self.config.get(section, {}).get(key, default)
        
    def save_to_file(self, config_file: str):
        """
        Save configuration to JSON file
        
        Args:
            config_file: Path to save configuration
        """
        try:
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config file: {e}")
