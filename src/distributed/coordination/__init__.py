"""
Módulo de coordinación para el sistema distribuido.
Proporciona replicación de coordinadores y elección de líder usando algoritmo Bully.
"""
from .coordinator_cluster import CoordinatorCluster, CoordinatorRole, CoordinatorPeer, StateSnapshot, BullyMessage

__all__ = ['CoordinatorCluster', 'CoordinatorRole', 'CoordinatorPeer', 'StateSnapshot', 'BullyMessage']
