"""
Persistencia del estado del coordinador.

Permite guardar y recuperar el estado del coordinador desde disco,
incluyendo:
- Registro de nodos de procesamiento
- Índice de ubicación de archivos
- Estadísticas

Esto permite que un coordinador se recupere después de un reinicio
sin perder la información del cluster.
"""
import json
import os
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import asdict


class StatePersistence:
    """
    Gestor de persistencia del estado del coordinador.
    
    Características:
    - Guardado periódico automático
    - Guardado en cada cambio importante
    - Recuperación al iniciar
    - Formato JSON legible
    """
    
    SAVE_INTERVAL = 30  # Segundos entre guardados automáticos
    
    def __init__(self, 
                 coordinator_id: str,
                 state_dir: str = "/app/state",
                 auto_save: bool = True):
        """
        Args:
            coordinator_id: ID del coordinador
            state_dir: Directorio donde guardar el estado
            auto_save: Si debe guardar automáticamente
        """
        self.coordinator_id = coordinator_id
        self.state_dir = Path(state_dir)
        self.auto_save = auto_save
        
        self.logger = logging.getLogger(f"StatePersistence-{coordinator_id}")
        
        # Crear directorio si no existe
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Archivos de estado
        self.nodes_file = self.state_dir / f"nodes_{coordinator_id}.json"
        self.files_file = self.state_dir / f"files_{coordinator_id}.json"
        self.meta_file = self.state_dir / f"meta_{coordinator_id}.json"
        
        # Control
        self._active = False
        self._dirty = False  # Indica si hay cambios sin guardar
        self._lock = threading.RLock()
    
    def start(self):
        """Inicia el guardado automático"""
        if self.auto_save:
            self._active = True
            threading.Thread(target=self._auto_save_loop, daemon=True).start()
            self.logger.info(f"💾 Persistencia iniciada en {self.state_dir}")
    
    def stop(self):
        """Detiene el guardado automático y guarda estado final"""
        self._active = False
        self.save_all()
    
    def _auto_save_loop(self):
        """Loop de guardado automático"""
        while self._active:
            time.sleep(self.SAVE_INTERVAL)
            
            if self._dirty:
                self.save_all()
    
    def mark_dirty(self):
        """Marca que hay cambios pendientes de guardar"""
        self._dirty = True
    
    def save_nodes(self, nodes: Dict[str, dict]):
        """
        Guarda el registro de nodos.
        
        Args:
            nodes: Diccionario de nodos {node_id: node_info}
        """
        with self._lock:
            try:
                state = {
                    'timestamp': time.time(),
                    'coordinator_id': self.coordinator_id,
                    'nodes': nodes
                }
                
                # Escribir a archivo temporal primero (atomic write)
                temp_file = self.nodes_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(state, f, indent=2, default=str)
                
                # Renombrar (atómico en la mayoría de sistemas)
                temp_file.rename(self.nodes_file)
                
                self.logger.debug(f"💾 Nodos guardados: {len(nodes)}")
                
            except Exception as e:
                self.logger.error(f"Error guardando nodos: {e}")
    
    def save_files(self, file_locations: Dict[str, List[str]]):
        """
        Guarda el índice de ubicación de archivos.
        
        Args:
            file_locations: Diccionario {file_name: [node_ids]}
        """
        with self._lock:
            try:
                state = {
                    'timestamp': time.time(),
                    'coordinator_id': self.coordinator_id,
                    'file_locations': file_locations
                }
                
                temp_file = self.files_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(state, f, indent=2)
                
                temp_file.rename(self.files_file)
                
                self.logger.debug(f"💾 Archivos guardados: {len(file_locations)}")
                
            except Exception as e:
                self.logger.error(f"Error guardando archivos: {e}")
    
    def save_metadata(self, stats: dict, extra: dict = None):
        """
        Guarda metadatos del coordinador.
        
        Args:
            stats: Estadísticas del coordinador
            extra: Información adicional
        """
        with self._lock:
            try:
                state = {
                    'timestamp': time.time(),
                    'coordinator_id': self.coordinator_id,
                    'stats': stats,
                    'extra': extra or {}
                }
                
                temp_file = self.meta_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(state, f, indent=2)
                
                temp_file.rename(self.meta_file)
                
            except Exception as e:
                self.logger.error(f"Error guardando metadatos: {e}")
    
    def save_all(self, nodes: Dict = None, file_locations: Dict = None, stats: Dict = None):
        """
        Guarda todo el estado.
        
        Los parámetros None no se guardan.
        """
        if nodes is not None:
            self.save_nodes(nodes)
        if file_locations is not None:
            self.save_files(file_locations)
        if stats is not None:
            self.save_metadata(stats)
        
        self._dirty = False
    
    def load_nodes(self) -> Optional[Dict[str, dict]]:
        """
        Carga el registro de nodos desde disco.
        
        Returns:
            Diccionario de nodos o None si no existe
        """
        if not self.nodes_file.exists():
            return None
        
        try:
            with open(self.nodes_file, 'r') as f:
                state = json.load(f)
            
            nodes = state.get('nodes', {})
            self.logger.info(f"📂 Nodos cargados: {len(nodes)}")
            return nodes
            
        except Exception as e:
            self.logger.error(f"Error cargando nodos: {e}")
            return None
    
    def load_files(self) -> Optional[Dict[str, List[str]]]:
        """
        Carga el índice de archivos desde disco.
        
        Returns:
            Diccionario de ubicaciones o None si no existe
        """
        if not self.files_file.exists():
            return None
        
        try:
            with open(self.files_file, 'r') as f:
                state = json.load(f)
            
            file_locations = state.get('file_locations', {})
            self.logger.info(f"📂 Archivos cargados: {len(file_locations)}")
            return file_locations
            
        except Exception as e:
            self.logger.error(f"Error cargando archivos: {e}")
            return None
    
    def load_metadata(self) -> Optional[dict]:
        """
        Carga metadatos desde disco.
        
        Returns:
            Diccionario de metadatos o None si no existe
        """
        if not self.meta_file.exists():
            return None
        
        try:
            with open(self.meta_file, 'r') as f:
                state = json.load(f)
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error cargando metadatos: {e}")
            return None
    
    def load_all(self) -> tuple:
        """
        Carga todo el estado desde disco.
        
        Returns:
            Tupla (nodes, file_locations, metadata)
        """
        nodes = self.load_nodes()
        file_locations = self.load_files()
        metadata = self.load_metadata()
        
        return nodes, file_locations, metadata
    
    def exists(self) -> bool:
        """Verifica si existe estado guardado"""
        return self.nodes_file.exists() or self.files_file.exists()
    
    def clear(self):
        """Elimina todo el estado guardado"""
        for f in [self.nodes_file, self.files_file, self.meta_file]:
            if f.exists():
                f.unlink()
        
        self.logger.info("🗑️ Estado eliminado")
    
    def get_last_save_time(self) -> Optional[float]:
        """Obtiene el timestamp del último guardado"""
        latest = 0
        
        for f in [self.nodes_file, self.files_file, self.meta_file]:
            if f.exists():
                mtime = f.stat().st_mtime
                latest = max(latest, mtime)
        
        return latest if latest > 0 else None
