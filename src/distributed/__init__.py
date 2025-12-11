# Distributed Search Engine Components

from .node import CoordinatorNode, ProcessingNode
from .registry import NodeRegistry, NodeInfo
from .dns import ChordDNS, NodeAddress
from .consistency import QuorumManager, QuorumLevel, WriteResult, ReadResult
from .coordination import CoordinatorCluster, CoordinatorRole
from .persistence import StatePersistence

__all__ = [
    # Nodos
    'CoordinatorNode',
    'ProcessingNode',
    # Registry
    'NodeRegistry',
    'NodeInfo',
    # DNS basado en CHORD
    'ChordDNS',
    'NodeAddress',
    # Consistencia (Quorum)
    'QuorumManager',
    'QuorumLevel',
    'WriteResult',
    'ReadResult',
    # Coordinación de cluster
    'CoordinatorCluster',
    'CoordinatorRole',
    # Persistencia
    'StatePersistence'
]
