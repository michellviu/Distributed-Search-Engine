#!/usr/bin/env python3
"""
Cliente interactivo para el servidor de búsqueda distribuida
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from client import SearchClient


def print_header():
    """Print welcome header"""
    print("=" * 60)
    print("   CLIENTE DE BÚSQUEDA DISTRIBUIDA")
    print("=" * 60)
    print()


def print_help():
    """Print available commands"""
    print("\nComandos disponibles:")
    print("  search <query> [tipo]  - Buscar documentos")
    print("  index <ruta>           - Indexar un archivo")
    print("  download <id> <dest>   - Descargar archivo")
    print("  list                   - Listar todos los archivos")
    print("  help                   - Mostrar esta ayuda")
    print("  quit                   - Salir")
    print()


def handle_search(client, args):
    """Handle search command"""
    if len(args) < 1:
        print("❌ Uso: search <query> [tipo]")
        return
    
    query = args[0]
    file_type = args[1] if len(args) > 1 else None
    
    print(f"\n🔍 Buscando: '{query}'" + (f" (tipo: {file_type})" if file_type else ""))
    results = client.search(query, file_type)
    
    if not results:
        print("No se encontraron resultados")
        return
    
    print(f"\n✓ Encontrados {len(results)} resultados:\n")
    for i, result in enumerate(results, 1):
        score = result.get('score', 0)
        size_kb = result.get('size', 0) / 1024
        print(f"{i:2d}. {result['name']}")
        print(f"    📄 Ruta: {result['path']}")
        print(f"    📊 Score: {score:.2f} | Tamaño: {size_kb:.1f} KB")
        print()


def handle_index(client, args):
    """Handle index command"""
    if len(args) < 1:
        print("❌ Uso: index <ruta>")
        return
    
    file_path = args[0]
    
    # Expand path
    path = Path(file_path).expanduser().absolute()
    
    if not path.exists():
        print(f"❌ Error: El archivo no existe: {path}")
        return
    
    print(f"\n📥 Indexando: {path}")
    success = client.index_file(str(path))
    
    if success:
        print("✓ Archivo indexado correctamente\n")
    else:
        print("❌ Error al indexar archivo\n")


def handle_download(client, args):
    """Handle download command"""
    if len(args) < 2:
        print("❌ Uso: download <id> <destino>")
        return
    
    file_id = args[0]
    destination = args[1]
    
    # Expand destination path
    dest_path = Path(destination).expanduser().absolute()
    
    print(f"\n📥 Descargando: {file_id}")
    print(f"   Destino: {dest_path}")
    
    success = client.download_file(file_id, str(dest_path))
    
    if success:
        if dest_path.is_file():
            size_kb = dest_path.stat().st_size / 1024
            print(f"✓ Archivo descargado correctamente")
            print(f"  Tamaño: {size_kb:.1f} KB\n")
        else:
            # Si es directorio, el archivo se guardó con su nombre original
            print(f"✓ Archivo descargado correctamente en {dest_path}\n")
    else:
        print("❌ Error al descargar archivo\n")


def handle_list(client, args):
    """Handle list command"""
    print("\n📋 Listando archivos indexados...")
    files = client.list_files()
    
    if not files:
        print("No hay archivos indexados")
        return
    
    print(f"\n✓ Total: {len(files)} archivos\n")
    
    # Group by file type
    by_type = {}
    for file_info in files:
        file_type = file_info.get('type', 'unknown')
        if file_type not in by_type:
            by_type[file_type] = []
        by_type[file_type].append(file_info)
    
    # Display grouped
    for file_type in sorted(by_type.keys()):
        files_of_type = by_type[file_type]
        print(f"Tipo: {file_type} ({len(files_of_type)} archivos)")
        
        for file_info in files_of_type[:5]:  # Show max 5 per type
            size_kb = file_info.get('size', 0) / 1024
            print(f"  • {file_info['name']:<30s} {size_kb:>8.1f} KB")
        
        if len(files_of_type) > 5:
            print(f"  ... y {len(files_of_type) - 5} archivos más")
        print()


def main():
    """Main interactive loop"""
    print_header()
    
    # Connect to server
    host = 'localhost'
    port = 5000
    
    print(f"Conectando a {host}:{port}...")
    
    try:
        client = SearchClient(host, port)
        print("✓ Conectado al servidor\n")
    except Exception as e:
        print(f"❌ Error al conectar con el servidor: {e}\n")
        print("Asegúrate de que el servidor esté ejecutándose:")
        print("  ./start_server.sh")
        print("  o")
        print("  python src/main_server.py")
        return 1
    
    print_help()
    
    # Interactive loop
    while True:
        try:
            user_input = input("\n> ").strip()
            
            if not user_input:
                continue
            
            parts = user_input.split()
            command = parts[0].lower()
            args = parts[1:]
            
            if command == 'quit' or command == 'exit':
                print("\n¡Hasta luego! 👋\n")
                break
            
            elif command == 'help':
                print_help()
            
            elif command == 'search':
                handle_search(client, args)
            
            elif command == 'index':
                handle_index(client, args)
            
            elif command == 'download':
                handle_download(client, args)
            
            elif command == 'list':
                handle_list(client, args)
            
            else:
                print(f"❌ Comando desconocido: {command}")
                print("Usa 'help' para ver los comandos disponibles")
        
        except KeyboardInterrupt:
            print("\n\n¡Hasta luego! 👋\n")
            break
        
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback
            traceback.print_exc()
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error fatal: {e}\n")
        sys.exit(1)
