#!/usr/bin/env python3
"""
Punto de entrada principal para el sistema distribuido.

Soporta dos roles:
- coordinator: Nodo coordinador (no almacena datos)
- processing: Nodo de procesamiento (almacena datos)

Uso:
    # Iniciar coordinador
    python -m src.main_distributed --role coordinator --id coord-1 --port 5000
    
    # Iniciar nodo de procesamiento
    python -m src.main_distributed --role processing --id proc-1 --port 6001 \
        --coordinator-host localhost --coordinator-port 5000
"""
import sys
import argparse
import logging
import os
from pathlib import Path

# Añadir src al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.distributed.node.coordinator_node import CoordinatorNode
from src.distributed.node.processing_node import ProcessingNode
from src.utils.logger import setup_logging


def main():
    parser = argparse.ArgumentParser(
        description='Sistema Distribuido de Búsqueda',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Iniciar coordinador
  python -m src.main_distributed --role coordinator --id coord-1 --port 5000
  
  # Iniciar nodo de procesamiento
  python -m src.main_distributed --role processing --id proc-1 --port 6001 \\
      --coordinator-host localhost --coordinator-port 5000
        """
    )
    
    # Argumentos comunes
    parser.add_argument('--role', type=str, required=True,
                        choices=['coordinator', 'processing'],
                        help='Rol del nodo: coordinator o processing')
    parser.add_argument('--id', type=str, 
                        default=os.environ.get('NODE_ID', 'node-1'),
                        help='ID único del nodo')
    parser.add_argument('--host', type=str,
                        default=os.environ.get('NODE_HOST', '0.0.0.0'),
                        help='Host para bind (default: 0.0.0.0)')
    parser.add_argument('--port', type=int,
                        default=int(os.environ.get('NODE_PORT', '5000')),
                        help='Puerto TCP (default: 5000)')
    parser.add_argument('--announce-host', type=str,
                        default=os.environ.get('ANNOUNCE_HOST'),
                        help='Host para anunciarse a otros nodos')
    parser.add_argument('--log-level', type=str,
                        default=os.environ.get('LOG_LEVEL', 'INFO'),
                        help='Nivel de logging')
    
    # Argumentos para nodo de procesamiento
    parser.add_argument('--coordinator-host', type=str,
                        default=os.environ.get('COORDINATOR_HOST', 'localhost'),
                        help='Host del coordinador')
    parser.add_argument('--coordinator-port', type=int,
                        default=int(os.environ.get('COORDINATOR_PORT', '5000')),
                        help='Puerto del coordinador')
    parser.add_argument('--index-path', type=str,
                        default=os.environ.get('INDEX_PATH', 'shared_files'),
                        help='Directorio de archivos a indexar')
    
    args = parser.parse_args()
    
    # Configurar logging
    setup_logging(level=args.log_level)
    logger = logging.getLogger('main_distributed')
    
    logger.info("=" * 60)
    logger.info("   SISTEMA DISTRIBUIDO DE BÚSQUEDA")
    logger.info("=" * 60)
    logger.info(f"   Rol:  {args.role.upper()}")
    logger.info(f"   ID:   {args.id}")
    logger.info(f"   Host: {args.host}:{args.port}")
    logger.info("=" * 60)
    
    try:
        if args.role == 'coordinator':
            # Iniciar nodo coordinador
            node = CoordinatorNode(
                coordinator_id=args.id,
                host=args.host,
                port=args.port,
                announce_host=args.announce_host
            )
            node.start()
            
        elif args.role == 'processing':
            # Iniciar nodo de procesamiento
            node = ProcessingNode(
                node_id=args.id,
                host=args.host,
                port=args.port,
                index_path=args.index_path,
                coordinator_host=args.coordinator_host,
                coordinator_port=args.coordinator_port,
                announce_host=args.announce_host
            )
            node.start()
            
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupción de teclado recibida")
        if 'node' in locals():
            node.stop()
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
