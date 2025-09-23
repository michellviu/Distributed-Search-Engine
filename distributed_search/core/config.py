"""
Configuration management for distributed search engine
"""
import os
from typing import List, Optional
from pydantic import BaseModel, Field


class NodeConfig(BaseModel):
    """Configuration for a search node"""
    node_id: str
    host: str = "localhost"
    port: int = Field(ge=1024, le=65535)
    max_connections: int = 100
    search_directories: List[str] = Field(default_factory=list)
    allowed_file_types: List[str] = Field(default_factory=lambda: [".txt", ".pdf", ".doc", ".docx", ".py", ".md"])
    max_file_size_mb: int = 100


class CoordinatorConfig(BaseModel):
    """Configuration for the search coordinator"""
    coordinator_id: str = "coordinator"
    host: str = "localhost"
    port: int = 8000
    known_nodes: List[NodeConfig] = Field(default_factory=list)
    heartbeat_interval: int = 30  # seconds
    search_timeout: int = 60  # seconds


class SearchConfig(BaseModel):
    """Configuration for search operations"""
    max_results: int = 100
    case_sensitive: bool = False
    regex_enabled: bool = True
    fuzzy_search: bool = False
    fuzzy_threshold: float = 0.8


class Config(BaseModel):
    """Main configuration class"""
    node: Optional[NodeConfig] = None
    coordinator: Optional[CoordinatorConfig] = None
    search: SearchConfig = Field(default_factory=SearchConfig)
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables"""
        return cls(
            node=NodeConfig(
                node_id=os.getenv("NODE_ID", "node_1"),
                host=os.getenv("NODE_HOST", "localhost"),
                port=int(os.getenv("NODE_PORT", "8001")),
                search_directories=os.getenv("SEARCH_DIRS", "").split(",") if os.getenv("SEARCH_DIRS") else []
            ) if os.getenv("NODE_MODE") == "node" else None,
            coordinator=CoordinatorConfig(
                host=os.getenv("COORDINATOR_HOST", "localhost"),
                port=int(os.getenv("COORDINATOR_PORT", "8000"))
            ) if os.getenv("NODE_MODE") == "coordinator" else None
        )
    
    @classmethod
    def load_from_file(cls, file_path: str) -> "Config":
        """Load configuration from JSON file"""
        import json
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    def save_to_file(self, file_path: str) -> None:
        """Save configuration to JSON file"""
        import json
        with open(file_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)