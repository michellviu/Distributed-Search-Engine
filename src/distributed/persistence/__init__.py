"""
Módulo de persistencia para el sistema distribuido.
Proporciona guardado y recuperación del estado del coordinador.
"""
from .state_persistence import StatePersistence

__all__ = ['StatePersistence']
