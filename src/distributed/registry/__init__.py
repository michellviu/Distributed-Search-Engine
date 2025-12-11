"""
Módulo de registro de nodos para el sistema distribuido.
Proporciona un registro simple de nodos de procesamiento sin usar consistent hashing.
"""
from .node_registry import NodeRegistry, NodeInfo

__all__ = ['NodeRegistry', 'NodeInfo']
