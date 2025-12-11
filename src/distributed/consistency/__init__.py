"""
Módulo de consistencia para el sistema distribuido.
Proporciona mecanismos de quorum para mantener la consistencia de datos replicados.
"""
from .quorum import QuorumManager, QuorumLevel, WriteResult, ReadResult, FileVersion

__all__ = ['QuorumManager', 'QuorumLevel', 'WriteResult', 'ReadResult', 'FileVersion']
