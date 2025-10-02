#!/usr/bin/env python3
"""
GUI Client for Distributed Search Engine using CustomTkinter
No JavaScript required - Pure Python solution
"""

import sys
import threading
from pathlib import Path
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# Try to import customtkinter, fallback to regular tkinter
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
    print("CustomTkinter disponible - usando interfaz moderna")
except ImportError:
    CTK_AVAILABLE = False
    print("CustomTkinter no disponible - usando Tkinter estándar")
    print("Instala con: pip install customtkinter")
    
    # Create wrapper classes for tkinter to match customtkinter API
    import tkinter as tk_base
    from tkinter import ttk
    
    class ctk:
        """Wrapper to provide CustomTkinter-like API using standard tkinter"""
        
        @staticmethod
        def set_appearance_mode(mode):
            pass
        
        @staticmethod
        def set_default_color_theme(theme):
            pass
        
        class CTk(tk_base.Tk):
            pass
        
        class CTkFrame(tk_base.Frame):
            def __init__(self, master, **kwargs):
                # Remove customtkinter-specific kwargs
                kwargs.pop('fg_color', None)
                kwargs.pop('corner_radius', None)
                super().__init__(master, **kwargs)
        
        class CTkLabel(tk_base.Label):
            def __init__(self, master, **kwargs):
                # Map customtkinter kwargs to tkinter
                text_color = kwargs.pop('text_color', None)
                if text_color:
                    kwargs['fg'] = text_color
                kwargs.pop('font', None)  # Remove font for now
                super().__init__(master, **kwargs)
        
        class CTkEntry(tk_base.Entry):
            def __init__(self, master, **kwargs):
                kwargs.pop('placeholder_text', None)
                kwargs.pop('corner_radius', None)
                super().__init__(master, **kwargs)
        
        class CTkButton(tk_base.Button):
            def __init__(self, master, **kwargs):
                kwargs.pop('corner_radius', None)
                kwargs.pop('fg_color', None)
                kwargs.pop('hover_color', None)
                super().__init__(master, **kwargs)
        
        class CTkTextbox(scrolledtext.ScrolledText):
            def __init__(self, master, **kwargs):
                kwargs.pop('corner_radius', None)
                kwargs.pop('fg_color', None)
                super().__init__(master, **kwargs)
            
            def tag_config(self, *args, **kwargs):
                """Map to standard text widget tag_config"""
                self.tag_configure(*args, **kwargs)
        
        class CTkFont:
            def __init__(self, **kwargs):
                self.size = kwargs.get('size', 12)
                self.weight = kwargs.get('weight', 'normal')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from client.client import SearchClient
from utils.config import Config
from utils.logger import setup_logging


class SearchEngineGUI:
    """
    Graphical User Interface for the Search Engine Client
    """
    
    def __init__(self, host: str = 'localhost', port: int = 5000):
        """
        Initialize the GUI
        
        Args:
            host: Server host
            port: Server port
        """
        self.host = host
        self.port = port
        self.client = None
        self.search_results: List[Dict] = []
        
        # Configure customtkinter appearance
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("dark")  # Modes: "System", "Dark", "Light"
            ctk.set_default_color_theme("blue")  # Themes: "blue", "green", "dark-blue"
        
        # Create main window
        self.root = ctk.CTk() if CTK_AVAILABLE else tk.Tk()
        self.root.title("Motor de Búsqueda Distribuida")
        self.root.geometry("1000x700")
        
        # Try to connect to server
        self._connect_to_server()
        
        # Setup UI
        self._setup_ui()
        
    def _connect_to_server(self):
        """Connect to the search server"""
        try:
            self.client = SearchClient(self.host, self.port)
            print(f"✓ Conectado al servidor {self.host}:{self.port}")
        except Exception as e:
            print(f"⚠ Advertencia: No se pudo conectar al servidor: {e}")
            self.client = None
    
    def _setup_ui(self):
        """Setup the user interface"""
        # Main container with padding
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="🔍 Motor de Búsqueda Distribuida",
            font=ctk.CTkFont(size=24, weight="bold") if CTK_AVAILABLE else ("Arial", 24, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Connection status
        status_color = "green" if self.client else "red"
        status_text = f"Conectado a {self.host}:{self.port}" if self.client else "Desconectado"
        self.status_label = ctk.CTkLabel(
            main_frame,
            text=f"Estado: {status_text}",
            text_color=status_color if CTK_AVAILABLE else None
        )
        self.status_label.pack(pady=(0, 10))
        
        # Search Frame
        self._setup_search_frame(main_frame)
        
        # Results Frame
        self._setup_results_frame(main_frame)
        
        # Action Buttons Frame
        self._setup_action_frame(main_frame)
        
        # Log Frame
        self._setup_log_frame(main_frame)
    
    def _setup_search_frame(self, parent):
        """Setup search input frame"""
        search_frame = ctk.CTkFrame(parent)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Search input
        ctk.CTkLabel(search_frame, text="Búsqueda:").pack(side="left", padx=(10, 5))
        
        self.search_entry = ctk.CTkEntry(search_frame, width=400, placeholder_text="Ingresa tu búsqueda...")
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self._on_search())
        
        # File type filter
        ctk.CTkLabel(search_frame, text="Tipo:").pack(side="left", padx=(20, 5))
        
        self.file_type_entry = ctk.CTkEntry(search_frame, width=100, placeholder_text=".txt")
        self.file_type_entry.pack(side="left", padx=5)
        
        # Search button
        self.search_btn = ctk.CTkButton(
            search_frame,
            text="🔍 Buscar",
            command=self._on_search,
            width=100
        )
        self.search_btn.pack(side="left", padx=10)
        
        # List all button
        self.list_btn = ctk.CTkButton(
            search_frame,
            text="📋 Listar Todo",
            command=self._on_list_all,
            width=120
        )
        self.list_btn.pack(side="left", padx=5)
    
    def _setup_results_frame(self, parent):
        """Setup results display frame"""
        results_frame = ctk.CTkFrame(parent)
        results_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        ctk.CTkLabel(
            results_frame,
            text="Resultados:",
            font=ctk.CTkFont(size=14, weight="bold") if CTK_AVAILABLE else ("Arial", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Results text area with scrollbar
        if CTK_AVAILABLE:
            self.results_text = ctk.CTkTextbox(results_frame, height=300)
        else:
            self.results_text = scrolledtext.ScrolledText(results_frame, height=15)
        
        self.results_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.results_text.configure(state="disabled")
    
    def _setup_action_frame(self, parent):
        """Setup action buttons frame"""
        action_frame = ctk.CTkFrame(parent)
        action_frame.pack(fill="x", pady=(0, 10))
        
        # Download frame
        download_frame = ctk.CTkFrame(action_frame)
        download_frame.pack(side="left", padx=10, pady=10)
        
        ctk.CTkLabel(download_frame, text="Descargar archivo:").pack(side="left", padx=5)
        
        self.download_entry = ctk.CTkEntry(download_frame, width=300, placeholder_text="Nombre del archivo")
        self.download_entry.pack(side="left", padx=5)
        
        self.download_btn = ctk.CTkButton(
            download_frame,
            text="📥 Descargar",
            command=self._on_download,
            width=120
        )
        self.download_btn.pack(side="left", padx=5)
        
        # Index file button
        self.index_btn = ctk.CTkButton(
            action_frame,
            text="📂 Indexar Archivo",
            command=self._on_index_file,
            width=150
        )
        self.index_btn.pack(side="left", padx=10, pady=10)
        
        # Reconnect button
        self.reconnect_btn = ctk.CTkButton(
            action_frame,
            text="🔄 Reconectar",
            command=self._on_reconnect,
            width=120
        )
        self.reconnect_btn.pack(side="right", padx=10, pady=10)
    
    def _setup_log_frame(self, parent):
        """Setup log display frame"""
        log_frame = ctk.CTkFrame(parent)
        log_frame.pack(fill="x")
        
        ctk.CTkLabel(
            log_frame,
            text="Registro:",
            font=ctk.CTkFont(size=12, weight="bold") if CTK_AVAILABLE else ("Arial", 12, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        if CTK_AVAILABLE:
            self.log_text = ctk.CTkTextbox(log_frame, height=100)
        else:
            self.log_text = scrolledtext.ScrolledText(log_frame, height=5)
        
        self.log_text.pack(fill="x", padx=10, pady=(0, 10))
        self.log_text.configure(state="disabled")
    
    def _log(self, message: str, level: str = "INFO"):
        """
        Add message to log
        
        Args:
            message: Message to log
            level: Log level (INFO, ERROR, SUCCESS)
        """
        self.log_text.configure(state="normal")
        
        # Color coding
        if CTK_AVAILABLE:
            if level == "ERROR":
                tag = "error"
                self.log_text.tag_config("error", foreground="red")
            elif level == "SUCCESS":
                tag = "success"
                self.log_text.tag_config("success", foreground="green")
            else:
                tag = "info"
                self.log_text.tag_config("info", foreground="white")
        else:
            tag = None
        
        timestamp = Path(__file__).stem  # Simple timestamp placeholder
        log_line = f"[{level}] {message}\n"
        
        if tag and CTK_AVAILABLE:
            self.log_text.insert("end", log_line, tag)
        else:
            self.log_text.insert("end", log_line)
        
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()
    
    def _display_results(self, results: List[Dict]):
        """
        Display search results
        
        Args:
            results: List of result dictionaries
        """
        self.search_results = results
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        
        if not results:
            self.results_text.insert("end", "No se encontraron resultados.\n")
        else:
            self.results_text.insert("end", f"✓ Encontrados {len(results)} resultados:\n\n")
            
            for i, result in enumerate(results, 1):
                name = result.get('name', 'Unknown')
                path = result.get('path', 'Unknown')
                score = result.get('score', 0)
                size = result.get('size', 0) / 1024  # KB
                file_type = result.get('type', 'Unknown')
                
                self.results_text.insert("end", f"{i}. {name}\n")
                self.results_text.insert("end", f"   📄 Ruta: {path}\n")
                self.results_text.insert("end", f"   📊 Score: {score:.2f} | Tamaño: {size:.1f} KB | Tipo: {file_type}\n")
                self.results_text.insert("end", "\n")
        
        self.results_text.configure(state="disabled")
    
    def _on_search(self):
        """Handle search button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor.\nUsa 'Reconectar' para intentar de nuevo.")
            return
        
        query = self.search_entry.get().strip()
        if not query:
            self._log("Error: La búsqueda no puede estar vacía", "ERROR")
            messagebox.showwarning("Advertencia", "Por favor ingresa un término de búsqueda")
            return
        
        file_type = self.file_type_entry.get().strip() or None
        
        self._log(f"Buscando: '{query}'" + (f" (tipo: {file_type})" if file_type else ""))
        
        # Run search in thread to avoid blocking UI
        threading.Thread(target=self._search_thread, args=(query, file_type), daemon=True).start()
    
    def _search_thread(self, query: str, file_type: Optional[str]):
        """
        Run search in background thread
        
        Args:
            query: Search query
            file_type: Optional file type filter
        """
        try:
            results = self.client.search(query, file_type)
            self.root.after(0, self._display_results, results)
            self.root.after(0, self._log, f"Búsqueda completada: {len(results)} resultados", "SUCCESS")
        except Exception as e:
            self.root.after(0, self._log, f"Error en búsqueda: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al buscar: {e}")
    
    def _on_list_all(self):
        """Handle list all button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        self._log("Listando todos los archivos...")
        threading.Thread(target=self._list_all_thread, daemon=True).start()
    
    def _list_all_thread(self):
        """Run list all in background thread"""
        try:
            files = self.client.list_files()
            self.root.after(0, self._display_results, files)
            self.root.after(0, self._log, f"Listado completado: {len(files)} archivos", "SUCCESS")
        except Exception as e:
            self.root.after(0, self._log, f"Error al listar: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al listar: {e}")
    
    def _on_download(self):
        """Handle download button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        file_name = self.download_entry.get().strip()
        if not file_name:
            self._log("Error: Debes especificar el nombre del archivo", "ERROR")
            messagebox.showwarning("Advertencia", "Por favor ingresa el nombre del archivo a descargar")
            return
        
        # Ask for destination directory
        dest_dir = filedialog.askdirectory(title="Selecciona el directorio de destino")
        if not dest_dir:
            return
        
        self._log(f"Descargando '{file_name}' a '{dest_dir}'...")
        threading.Thread(target=self._download_thread, args=(file_name, dest_dir), daemon=True).start()
    
    def _download_thread(self, file_name: str, dest_dir: str):
        """
        Run download in background thread
        
        Args:
            file_name: Name of file to download
            dest_dir: Destination directory
        """
        try:
            success = self.client.download_file(file_name, dest_dir)
            if success:
                dest_path = Path(dest_dir) / file_name
                size = dest_path.stat().st_size / 1024 if dest_path.exists() else 0
                self.root.after(0, self._log, f"✓ Descarga exitosa: {file_name} ({size:.1f} KB)", "SUCCESS")
                self.root.after(0, messagebox.showinfo, "Éxito", f"Archivo descargado:\n{dest_path}")
            else:
                self.root.after(0, self._log, f"Error al descargar {file_name}", "ERROR")
                self.root.after(0, messagebox.showerror, "Error", "No se pudo descargar el archivo")
        except Exception as e:
            self.root.after(0, self._log, f"Error en descarga: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al descargar: {e}")
    
    def _on_index_file(self):
        """Handle index file button click"""
        if not self.client:
            self._log("Error: No hay conexión con el servidor", "ERROR")
            messagebox.showerror("Error", "No hay conexión con el servidor")
            return
        
        # Ask for file to index
        file_path = filedialog.askopenfilename(title="Selecciona el archivo a indexar")
        if not file_path:
            return
        
        self._log(f"Indexando '{file_path}'...")
        threading.Thread(target=self._index_thread, args=(file_path,), daemon=True).start()
    
    def _index_thread(self, file_path: str):
        """
        Run index in background thread
        
        Args:
            file_path: Path to file to index
        """
        try:
            success = self.client.index_file(file_path)
            if success:
                self.root.after(0, self._log, f"✓ Archivo indexado: {Path(file_path).name}", "SUCCESS")
                self.root.after(0, messagebox.showinfo, "Éxito", f"Archivo indexado correctamente:\n{Path(file_path).name}")
            else:
                self.root.after(0, self._log, f"Error al indexar {file_path}", "ERROR")
                self.root.after(0, messagebox.showerror, "Error", "No se pudo indexar el archivo")
        except Exception as e:
            self.root.after(0, self._log, f"Error al indexar: {e}", "ERROR")
            self.root.after(0, messagebox.showerror, "Error", f"Error al indexar: {e}")
    
    def _on_reconnect(self):
        """Handle reconnect button click"""
        self._log("Intentando reconectar...")
        self._connect_to_server()
        
        if self.client:
            status_text = f"Conectado a {self.host}:{self.port}"
            self.status_label.configure(text=f"Estado: {status_text}", text_color="green" if CTK_AVAILABLE else None)
            self._log("✓ Reconexión exitosa", "SUCCESS")
            messagebox.showinfo("Éxito", "Reconectado al servidor")
        else:
            status_text = "Desconectado"
            self.status_label.configure(text=f"Estado: {status_text}", text_color="red" if CTK_AVAILABLE else None)
            self._log("Error al reconectar", "ERROR")
            messagebox.showerror("Error", f"No se pudo conectar a {self.host}:{self.port}\n\nAsegúrate de que el servidor esté ejecutándose.")
    
    def run(self):
        """Run the GUI application"""
        self.root.mainloop()


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='GUI Client for Distributed Search Engine')
    parser.add_argument('--config', type=str, default='config/client_config.json', help='Configuration file')
    parser.add_argument('--host', type=str, help='Server host')
    parser.add_argument('--port', type=int, help='Server port')
    
    args = parser.parse_args()
    
    # Load configuration
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent
    config_path = ROOT_DIR / args.config if not Path(args.config).is_absolute() else args.config
    
    config = Config(str(config_path))
    
    # Setup logging
    log_config = config.get('logging', default={})
    setup_logging(
        level=log_config.get('level', 'INFO'),
        log_file=log_config.get('file'),
        log_format=log_config.get('format')
    )
    
    # Get server configuration
    server_config = config.get('server', default={})
    host = args.host or server_config.get('host', 'localhost')
    port = args.port or server_config.get('port', 5000)
    
    # Create and run GUI
    app = SearchEngineGUI(host, port)
    app.run()


if __name__ == '__main__':
    main()
