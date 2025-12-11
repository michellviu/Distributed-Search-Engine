"""
Sistema de Quorum para consistencia de datos.

Implementa un protocolo de quorum configurable para asegurar
la consistencia de archivos replicados en múltiples nodos de procesamiento.
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum


class QuorumLevel(Enum):
    """Niveles de consistencia para operaciones"""
    ONE = "ONE"           # Al menos 1 nodo confirma
    QUORUM = "QUORUM"     # Mayoría de réplicas (N/2 + 1)
    ALL = "ALL"           # Todas las réplicas confirman


@dataclass
class WriteResult:
    """Resultado de una operación de escritura con quorum"""
    success: bool
    confirmed_nodes: List[str]
    failed_nodes: List[str]
    quorum_achieved: bool
    required_confirmations: int
    actual_confirmations: int
    duration_ms: float
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'confirmed_nodes': self.confirmed_nodes,
            'failed_nodes': self.failed_nodes,
            'quorum_achieved': self.quorum_achieved,
            'required_confirmations': self.required_confirmations,
            'actual_confirmations': self.actual_confirmations,
            'duration_ms': self.duration_ms
        }


@dataclass
class ReadResult:
    """Resultado de una operación de lectura con quorum"""
    success: bool
    data: Optional[Any]
    version: int
    responding_nodes: List[str]
    failed_nodes: List[str]
    duration_ms: float
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'data': self.data,
            'version': self.version,
            'responding_nodes': self.responding_nodes,
            'failed_nodes': self.failed_nodes,
            'duration_ms': self.duration_ms
        }


@dataclass
class FileVersion:
    """Control de versión para un archivo"""
    file_id: str
    version: int
    timestamp: float
    checksum: str
    nodes: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> dict:
        return {
            'file_id': self.file_id,
            'version': self.version,
            'timestamp': self.timestamp,
            'checksum': self.checksum,
            'nodes': list(self.nodes)
        }


class QuorumManager:
    """
    Gestor de Quorum para operaciones de escritura/lectura distribuidas.
    
    Características:
    - Soporta diferentes niveles de consistencia (ONE, QUORUM, ALL)
    - Control de versiones para detectar conflictos
    - Manejo de timeouts y fallos parciales
    - Reparación de réplicas (read repair)
    """
    
    def __init__(
        self,
        node_id: str,
        default_level: QuorumLevel = QuorumLevel.QUORUM,
        write_timeout: float = 5.0,
        read_timeout: float = 3.0
    ):
        self.node_id = node_id
        self.default_level = default_level
        self.write_timeout = write_timeout
        self.read_timeout = read_timeout
        self.logger = logging.getLogger(f"Quorum-{node_id}")
        
        # Control de versiones
        self.file_versions: Dict[str, FileVersion] = {}
        self._version_lock = asyncio.Lock()
        
    def calculate_quorum(self, total_replicas: int, level: QuorumLevel) -> int:
        """
        Calcula el número de confirmaciones requeridas para el quorum.
        
        Args:
            total_replicas: Número total de réplicas
            level: Nivel de consistencia requerido
            
        Returns:
            Número de confirmaciones necesarias
        """
        if level == QuorumLevel.ONE:
            return 1
        elif level == QuorumLevel.ALL:
            return total_replicas
        else:  # QUORUM
            return (total_replicas // 2) + 1
    
    async def quorum_write(
        self,
        file_id: str,
        data: bytes,
        target_nodes: List[str],
        send_func,  # async func(node_id, file_id, data, version) -> bool
        level: Optional[QuorumLevel] = None
    ) -> WriteResult:
        """
        Ejecuta una escritura con quorum.
        
        Args:
            file_id: Identificador del archivo
            data: Datos a escribir
            target_nodes: Lista de nodos destino
            send_func: Función async para enviar datos a un nodo
            level: Nivel de quorum (usa default si no se especifica)
            
        Returns:
            WriteResult con el resultado de la operación
        """
        start_time = time.time()
        level = level or self.default_level
        required = self.calculate_quorum(len(target_nodes), level)
        
        self.logger.debug(
            f"📝 Iniciando quorum write para {file_id} -> "
            f"{len(target_nodes)} nodos, requiere {required} confirmaciones"
        )
        
        # Incrementar versión
        async with self._version_lock:
            version = await self._get_next_version(file_id)
        
        # Enviar a todos los nodos en paralelo
        tasks = []
        for node_id in target_nodes:
            task = asyncio.create_task(
                self._send_with_timeout(send_func, node_id, file_id, data, version)
            )
            tasks.append((node_id, task))
        
        confirmed = []
        failed = []
        
        # Esperar resultados
        for node_id, task in tasks:
            try:
                result = await task
                if result:
                    confirmed.append(node_id)
                else:
                    failed.append(node_id)
            except Exception as e:
                self.logger.error(f"❌ Error en write a {node_id}: {e}")
                failed.append(node_id)
        
        # Actualizar control de versiones
        if len(confirmed) >= required:
            async with self._version_lock:
                if file_id not in self.file_versions:
                    import hashlib
                    checksum = hashlib.md5(data).hexdigest()
                    self.file_versions[file_id] = FileVersion(
                        file_id=file_id,
                        version=version,
                        timestamp=time.time(),
                        checksum=checksum
                    )
                self.file_versions[file_id].nodes = set(confirmed)
                self.file_versions[file_id].version = version
        
        duration = (time.time() - start_time) * 1000
        quorum_achieved = len(confirmed) >= required
        
        result = WriteResult(
            success=quorum_achieved,
            confirmed_nodes=confirmed,
            failed_nodes=failed,
            quorum_achieved=quorum_achieved,
            required_confirmations=required,
            actual_confirmations=len(confirmed),
            duration_ms=duration
        )
        
        if quorum_achieved:
            self.logger.info(
                f"✅ Quorum write exitoso para {file_id}: "
                f"{len(confirmed)}/{len(target_nodes)} confirmaciones"
            )
        else:
            self.logger.warning(
                f"⚠️ Quorum write fallido para {file_id}: "
                f"solo {len(confirmed)}/{required} confirmaciones"
            )
        
        return result
    
    async def quorum_read(
        self,
        file_id: str,
        source_nodes: List[str],
        read_func,  # async func(node_id, file_id) -> (data, version) or None
        level: Optional[QuorumLevel] = None
    ) -> ReadResult:
        """
        Ejecuta una lectura con quorum.
        
        Lee de múltiples nodos y retorna la versión más reciente.
        Opcionalmente puede hacer read repair si encuentra inconsistencias.
        
        Args:
            file_id: Identificador del archivo
            source_nodes: Lista de nodos fuente
            read_func: Función async para leer de un nodo
            level: Nivel de quorum
            
        Returns:
            ReadResult con el resultado
        """
        start_time = time.time()
        level = level or self.default_level
        required = self.calculate_quorum(len(source_nodes), level)
        
        self.logger.debug(
            f"📖 Iniciando quorum read para {file_id} desde "
            f"{len(source_nodes)} nodos, requiere {required} respuestas"
        )
        
        # Leer de todos los nodos en paralelo
        tasks = []
        for node_id in source_nodes:
            task = asyncio.create_task(
                self._read_with_timeout(read_func, node_id, file_id)
            )
            tasks.append((node_id, task))
        
        responses = []  # (node_id, data, version)
        failed = []
        
        for node_id, task in tasks:
            try:
                result = await task
                if result is not None:
                    data, version = result
                    responses.append((node_id, data, version))
                else:
                    failed.append(node_id)
            except Exception as e:
                self.logger.error(f"❌ Error en read de {node_id}: {e}")
                failed.append(node_id)
        
        duration = (time.time() - start_time) * 1000
        
        if len(responses) < required:
            return ReadResult(
                success=False,
                data=None,
                version=-1,
                responding_nodes=[r[0] for r in responses],
                failed_nodes=failed,
                duration_ms=duration
            )
        
        # Encontrar la versión más reciente
        responses.sort(key=lambda x: x[2], reverse=True)
        latest_node, latest_data, latest_version = responses[0]
        
        self.logger.info(
            f"✅ Quorum read exitoso para {file_id}: "
            f"versión {latest_version} de {latest_node}"
        )
        
        return ReadResult(
            success=True,
            data=latest_data,
            version=latest_version,
            responding_nodes=[r[0] for r in responses],
            failed_nodes=failed,
            duration_ms=duration
        )
    
    async def _send_with_timeout(
        self, 
        send_func, 
        node_id: str, 
        file_id: str, 
        data: bytes, 
        version: int
    ) -> bool:
        """Envía con timeout"""
        try:
            return await asyncio.wait_for(
                send_func(node_id, file_id, data, version),
                timeout=self.write_timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"⏱️ Timeout en write a {node_id}")
            return False
    
    async def _read_with_timeout(
        self, 
        read_func, 
        node_id: str, 
        file_id: str
    ) -> Optional[Tuple[Any, int]]:
        """Lee con timeout"""
        try:
            return await asyncio.wait_for(
                read_func(node_id, file_id),
                timeout=self.read_timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"⏱️ Timeout en read de {node_id}")
            return None
    
    async def _get_next_version(self, file_id: str) -> int:
        """Obtiene el siguiente número de versión para un archivo"""
        if file_id in self.file_versions:
            return self.file_versions[file_id].version + 1
        return 1
    
    def get_file_version(self, file_id: str) -> Optional[FileVersion]:
        """Obtiene información de versión de un archivo"""
        return self.file_versions.get(file_id)
    
    def get_files_on_node(self, node_id: str) -> List[str]:
        """Obtiene lista de archivos en un nodo específico"""
        return [
            fv.file_id 
            for fv in self.file_versions.values() 
            if node_id in fv.nodes
        ]
    
    def get_stats(self) -> dict:
        """Obtiene estadísticas del gestor de quorum"""
        return {
            'node_id': self.node_id,
            'default_level': self.default_level.value,
            'tracked_files': len(self.file_versions),
            'write_timeout': self.write_timeout,
            'read_timeout': self.read_timeout
        }
