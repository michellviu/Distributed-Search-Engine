"""
Registro de Nodos para el sistema distribuido.

Este módulo implementa un registro simple de nodos de procesamiento que permite:
1. Registrar nodos con su ID y dirección IP
2. Buscar la dirección de un nodo dado su ID
3. Mantener un índice de qué archivos están en qué nodos
4. Asignar almacenamiento por balanceo de carga (round-robin o menos cargado)

NO usa consistent hashing ni CHORD. El coordinador mantiene un registro
explícito de la ubicación de cada archivo.
"""
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class NodeInfo:
    """Información de un nodo de procesamiento"""
    node_id: str
    host: str
    port: int
    registered_at: float
    last_seen: float
    load: int = 0  # Número de archivos almacenados
    current_tasks: int = 0  # Tareas en proceso actualmente
    files: Set[str] = field(default_factory=set)  # Archivos en este nodo
    
    def to_dict(self) -> dict:
        return {
            'node_id': self.node_id,
            'host': self.host,
            'port': self.port,
            'registered_at': self.registered_at,
            'last_seen': self.last_seen,
            'load': self.load,
            'current_tasks': self.current_tasks,
            'files_count': len(self.files)
        }


class NodeRegistry:
    """
    Registro de nodos de procesamiento para el coordinador.
    
    Características:
    - Mapeo simple ID -> (IP, Puerto)
    - Registro de archivos por nodo
    - Asignación de almacenamiento por balanceo de carga
    - Thread-safe para uso concurrente
    
    NO usa consistent hashing. El coordinador decide explícitamente
    dónde almacenar cada archivo basándose en la carga de los nodos.
    """
    
    def __init__(self, coordinator_id: str, replication_factor: int = 3):
        self.coordinator_id = coordinator_id
        self.replication_factor = replication_factor
        self.logger = logging.getLogger(f"NodeRegistry-{coordinator_id}")
        
        # Tabla principal: node_id -> NodeInfo
        self.nodes: Dict[str, NodeInfo] = {}
        
        # Índice inverso: file_name -> set de node_ids que lo tienen
        self.file_locations: Dict[str, Set[str]] = {}
        
        # Contador para round-robin
        self._rr_index = 0
        
        self._lock = threading.RLock()
    
    def register_node(self, node_id: str, host: str, port: int) -> bool:
        """
        Registra un nodo de procesamiento.
        
        Args:
            node_id: Identificador único del nodo
            host: Dirección IP del nodo
            port: Puerto TCP del nodo
            
        Returns:
            True si el registro fue exitoso
        """
        with self._lock:
            current_time = time.time()
            
            if node_id in self.nodes:
                # Actualizar nodo existente
                self.nodes[node_id].host = host
                self.nodes[node_id].port = port
                self.nodes[node_id].last_seen = current_time
                self.logger.info(f"📝 Nodo actualizado: {node_id} -> {host}:{port}")
            else:
                # Registrar nuevo nodo
                self.nodes[node_id] = NodeInfo(
                    node_id=node_id,
                    host=host,
                    port=port,
                    registered_at=current_time,
                    last_seen=current_time
                )
                self.logger.info(f"✅ Nodo registrado: {node_id} -> {host}:{port}")
            
            return True
    
    def unregister_node(self, node_id: str) -> bool:
        """
        Elimina un nodo de procesamiento del registro.
        
        Args:
            node_id: Identificador del nodo a eliminar
            
        Returns:
            True si el nodo fue eliminado
        """
        with self._lock:
            if node_id not in self.nodes:
                return False
            
            # Obtener archivos del nodo que se va
            node = self.nodes[node_id]
            orphaned_files = list(node.files)
            
            # Eliminar del registro
            del self.nodes[node_id]
            
            # Actualizar índice de ubicaciones
            for file_name in orphaned_files:
                if file_name in self.file_locations:
                    self.file_locations[file_name].discard(node_id)
                    # Si el archivo no tiene ubicaciones, marcarlo como huérfano
                    if not self.file_locations[file_name]:
                        self.logger.warning(f"⚠️ Archivo huérfano: {file_name}")
            
            self.logger.info(f"🗑️ Nodo eliminado: {node_id}")
            return True
    
    def lookup(self, node_id: str) -> Optional[NodeInfo]:
        """
        Busca la información de un nodo por su ID.
        
        Args:
            node_id: ID del nodo a buscar
            
        Returns:
            NodeInfo si el nodo existe, None si no
        """
        with self._lock:
            return self.nodes.get(node_id)
    
    def resolve(self, node_id: str) -> Optional[Tuple[str, int]]:
        """
        Resuelve un node_id a su dirección (host, port).
        
        Args:
            node_id: ID del nodo a resolver
            
        Returns:
            Tupla (host, port) o None si no existe
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if node:
                return (node.host, node.port)
            return None
    
    def get_nodes_for_storage(self, file_name: str, count: int = None) -> List[str]:
        """
        Determina en qué nodos almacenar un archivo.
        
        Usa balanceo de carga: asigna a los nodos con menor cantidad de archivos.
        
        Args:
            file_name: Nombre del archivo a almacenar
            count: Número de nodos (default: replication_factor)
            
        Returns:
            Lista de node_ids donde almacenar el archivo
        """
        if count is None:
            count = self.replication_factor
        
        with self._lock:
            if not self.nodes:
                return []
            
            # Verificar si el archivo ya tiene ubicaciones
            if file_name in self.file_locations and self.file_locations[file_name]:
                existing = list(self.file_locations[file_name])
                if len(existing) >= count:
                    return existing[:count]
                # Si faltan réplicas, añadir más nodos
                needed = count - len(existing)
                available = [n for n in self.nodes.keys() if n not in existing]
                # Ordenar por carga (menos archivos primero)
                available.sort(key=lambda nid: self.nodes[nid].load)
                return existing + available[:needed]
            
            # Archivo nuevo: asignar a los nodos menos cargados
            sorted_nodes = sorted(
                self.nodes.values(),
                key=lambda n: (n.load, n.current_tasks)
            )
            
            return [n.node_id for n in sorted_nodes[:min(count, len(sorted_nodes))]]
    
    def register_file_location(self, file_name: str, node_id: str):
        """
        Registra que un archivo está almacenado en un nodo específico.
        
        Args:
            file_name: Nombre del archivo
            node_id: ID del nodo donde está almacenado
        """
        with self._lock:
            # Actualizar índice de ubicaciones
            if file_name not in self.file_locations:
                self.file_locations[file_name] = set()
            self.file_locations[file_name].add(node_id)
            
            # Actualizar información del nodo
            if node_id in self.nodes:
                self.nodes[node_id].files.add(file_name)
                self.nodes[node_id].load = len(self.nodes[node_id].files)
            
            self.logger.debug(f"📍 Archivo '{file_name}' registrado en nodo '{node_id}'")
    
    def get_file_locations(self, file_name: str) -> List[str]:
        """
        Obtiene los nodos donde está almacenado un archivo.
        
        Args:
            file_name: Nombre del archivo
            
        Returns:
            Lista de node_ids que tienen el archivo
        """
        with self._lock:
            if file_name in self.file_locations:
                return list(self.file_locations[file_name])
            return []
    
    def get_all_files(self) -> Dict[str, Set[str]]:
        """
        Obtiene todos los archivos y sus ubicaciones.
        
        Returns:
            Diccionario {file_name: set(node_ids)}
        """
        with self._lock:
            return dict(self.file_locations)
    
    def remove_file_location(self, file_name: str, node_id: str):
        """
        Elimina el registro de un archivo en un nodo.
        
        Args:
            file_name: Nombre del archivo
            node_id: ID del nodo
        """
        with self._lock:
            if file_name in self.file_locations:
                self.file_locations[file_name].discard(node_id)
            
            if node_id in self.nodes:
                self.nodes[node_id].files.discard(file_name)
                self.nodes[node_id].load = len(self.nodes[node_id].files)
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """Obtiene lista de todos los nodos registrados"""
        with self._lock:
            return list(self.nodes.values())
    
    def get_active_nodes(self, max_age_seconds: float = 30.0) -> List[NodeInfo]:
        """
        Obtiene nodos activos (vistos recientemente).
        
        Args:
            max_age_seconds: Máxima edad del último contacto
            
        Returns:
            Lista de nodos activos
        """
        with self._lock:
            current_time = time.time()
            return [
                node for node in self.nodes.values()
                if (current_time - node.last_seen) <= max_age_seconds
            ]
    
    def update_last_seen(self, node_id: str) -> bool:
        """Actualiza el timestamp de último contacto de un nodo"""
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].last_seen = time.time()
                return True
            return False
    
    def update_node_tasks(self, node_id: str, tasks: int) -> bool:
        """Actualiza el número de tareas en proceso de un nodo"""
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].current_tasks = tasks
                return True
            return False
    
    def get_least_loaded_node(self) -> Optional[NodeInfo]:
        """
        Obtiene el nodo con menor carga para balanceo.
        
        Returns:
            NodeInfo del nodo con menor carga
        """
        with self._lock:
            if not self.nodes:
                return None
            
            return min(
                self.nodes.values(), 
                key=lambda n: (n.current_tasks, n.load)
            )
    
    def get_next_node_round_robin(self) -> Optional[NodeInfo]:
        """
        Obtiene el siguiente nodo usando round-robin.
        
        Returns:
            NodeInfo del siguiente nodo en rotación
        """
        with self._lock:
            if not self.nodes:
                return None
            
            node_list = list(self.nodes.values())
            self._rr_index = self._rr_index % len(node_list)
            node = node_list[self._rr_index]
            self._rr_index += 1
            
            return node
    
    def get_nodes_sorted_by_load(self) -> List[NodeInfo]:
        """Obtiene nodos ordenados por carga (menor primero)"""
        with self._lock:
            return sorted(
                self.nodes.values(), 
                key=lambda n: (n.current_tasks, n.load)
            )
    
    def get_stats(self) -> dict:
        """Obtiene estadísticas del registro"""
        with self._lock:
            total_files = len(self.file_locations)
            files_with_full_replication = sum(
                1 for locs in self.file_locations.values() 
                if len(locs) >= self.replication_factor
            )
            
            return {
                'total_nodes': len(self.nodes),
                'total_files': total_files,
                'files_fully_replicated': files_with_full_replication,
                'replication_factor': self.replication_factor,
                'nodes': [n.to_dict() for n in self.nodes.values()]
            }
    
    def get_files_needing_replication(self) -> List[Tuple[str, int]]:
        """
        Obtiene archivos que necesitan más réplicas.
        
        Returns:
            Lista de tuplas (file_name, current_replicas)
        """
        with self._lock:
            needs_replication = []
            for file_name, locations in self.file_locations.items():
                if len(locations) < self.replication_factor:
                    needs_replication.append((file_name, len(locations)))
            return needs_replication
    
    def search_files(self, query: str, file_type: str = None) -> List[dict]:
        """
        Busca archivos por nombre/extensión en el registro.
        
        Como el coordinador conoce todos los archivos registrados,
        puede hacer la búsqueda localmente sin consultar nodos.
        
        Args:
            query: Término de búsqueda (substring del nombre)
            file_type: Filtro de extensión (ej: '.txt', '.pdf')
            
        Returns:
            Lista de archivos que coinciden con sus ubicaciones
        """
        with self._lock:
            results = []
            query_lower = query.lower().strip() if query else ''
            query_terms = query_lower.split() if query_lower else []
            
            for file_name, node_ids in self.file_locations.items():
                file_name_lower = file_name.lower()
                
                # Filtrar por extensión si se especificó
                if file_type:
                    if not file_name_lower.endswith(file_type.lower()):
                        continue
                
                # Si no hay query, coincide (solo filtro por extensión o listar todo)
                if not query_lower:
                    matches = True
                else:
                    matches = False
                    
                    # Coincidencia por substring
                    if query_lower in file_name_lower:
                        matches = True
                    # O todos los términos están en el nombre
                    elif query_terms and all(term in file_name_lower for term in query_terms):
                        matches = True
                
                if matches:
                    # Calcular score de relevancia
                    score = self._calculate_file_score(file_name_lower, query_lower)
                    
                    results.append({
                        'name': file_name,
                        'file_name': file_name,
                        'nodes': list(node_ids),
                        'replicas': len(node_ids),
                        'score': score
                    })
            
            # Ordenar por score (mayor primero)
            results.sort(key=lambda x: x['score'], reverse=True)
            return results
    
    def _calculate_file_score(self, file_name: str, query: str) -> float:
        """Calcula score de relevancia para un archivo"""
        # Coincidencia exacta = máximo score
        if file_name == query:
            return 1.0
        
        # El nombre empieza con la query
        if file_name.startswith(query):
            return 0.9
        
        # La query está en el nombre
        if query in file_name:
            # Mayor score si es una palabra completa
            return 0.7
        
        # Coincidencia parcial de términos
        return 0.5
    
    def get_all_file_names(self) -> List[str]:
        """Obtiene lista de todos los nombres de archivos registrados"""
        with self._lock:
            return list(self.file_locations.keys())
    
    def __str__(self) -> str:
        with self._lock:
            return f"NodeRegistry(coordinator={self.coordinator_id}, nodes={len(self.nodes)}, files={len(self.file_locations)})"
    
    def __repr__(self) -> str:
        return self.__str__()
