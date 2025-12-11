"""
Módulo DNS para el sistema distribuido.
Proporciona resolución de nombres basada en CHORD para localizar nodos de procesamiento.

IMPORTANTE: El DNS solo se usa para mapear ID -> IP, NO para decidir
dónde almacenar archivos.
"""
from .chord_dns import ChordDNS, NodeAddress

__all__ = ['ChordDNS', 'NodeAddress']
