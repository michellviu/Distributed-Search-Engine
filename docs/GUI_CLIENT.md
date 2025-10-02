# 🖥️ Cliente con Interfaz Gráfica (GUI)

## Descripción

## Instalación

### Opción 1: Con Interfaz Moderna (Recomendado)

```bash
# Instalar CustomTkinter para una interfaz más bonita
pip install customtkinter
```

### Opción 2: Usar Tkinter Estándar (Ya incluido en Python)

```bash
# No necesitas instalar nada, Tkinter viene con Python
# La GUI detectará automáticamente que no tienes CustomTkinter
```

## Uso

### Script de Inicio Rápido

```bash
# Desde el directorio raíz del proyecto
./start_client_gui.sh
```

### Inicio Manual

```bash
# Con configuración por defecto
python3 src/client/client_gui.py

# Con configuración personalizada
python3 src/client/client_gui.py --config mi_config.json --host 192.168.1.100 --port 5000
```

### Si instalaste el paquete

```bash
# Puedes agregar el GUI como entry point en setup.py
search-client-gui
```

## Interfaz de Usuario

La GUI incluye las siguientes secciones:

### 1. **Barra de Búsqueda**

- Campo de búsqueda con filtro por tipo de archivo
- Botón "Buscar" (o presiona Enter)
- Botón "Listar Todo" para ver todos los archivos

### 2. **Panel de Resultados**

- Muestra resultados con:
- Nombre del archivo
- Ruta completa
- Score de relevancia
- Tamaño en KB
- Tipo de archivo

### 3. **Acciones**

- **Descargar**: Ingresa nombre y elige directorio
- **Indexar Archivo**: Abre diálogo para seleccionar archivo
- **Reconectar**: Intenta reconectar si se perdió la conexión

### 4. **Registro (Log)**

- Muestra todas las operaciones realizadas
- Código de colores: Verde (éxito), Rojo (error), Blanco (info)

## Ejemplo de Uso

1. **Iniciar el servidor** (en otra terminal):

   ```bash
   ./start_server.sh
   ```

2. **Iniciar el cliente GUI**:

   ```bash
   ./start_client_gui.sh
   ```

3. **Usar la interfaz**:
   - Escribe "python" en el campo de búsqueda
   - (Opcional) Especifica ".txt" en el filtro de tipo
   - Haz clic en "Buscar" o presiona Enter
   - Selecciona un archivo de los resultados
   - Copia el nombre y pégalo en "Descargar archivo"
   - Haz clic en "Descargar" y elige el directorio

### ✅ Mismo Cliente para Múltiples Nodos

```python
# Fácil de adaptar para conectar a múltiples servidores
servers = [
    ('node1.example.com', 5000),
    ('node2.example.com', 5000),
    ('node3.example.com', 5000)
]

# El GUI puede mostrar un selector de nodos
```

### ✅ Monitoreo Visual

- Ver estado de conexión con cada nodo
- Progreso de descarga desde múltiples fuentes
- Estadísticas de red en tiempo real

## Personalización

### Temas

```python
# En client_gui.py, línea ~49
ctk.set_appearance_mode("dark")  # "System", "Dark", "Light"
ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"
```

### Colores

```python
# Personalizar colores de CustomTkinter
ctk.set_default_color_theme("custom_theme.json")
```

### Tamaño de Ventana

```python
# En client_gui.py, línea ~57
self.root.geometry("1000x700")  # Cambiar dimensiones
```

## Troubleshooting

### La GUI no inicia

**Problema**: `No module named 'tkinter'`

**Solución (Ubuntu/Debian)**:

```bash
sudo apt-get install python3-tk
```

**Solución (Fedora/RHEL)**:

```bash
sudo dnf install python3-tkinter
```

### CustomTkinter no funciona

**Opción 1**: Actualizar

```bash
pip install --upgrade customtkinter
```

**Opción 2**: Usar Tkinter estándar

- El código detecta automáticamente y usa Tkinter si CustomTkinter no está disponible

### La GUI se congela

- **Causa**: Operación de red bloqueando el thread principal
- **Solución**: Ya implementado - todas las operaciones de red corren en threads separados

### No se conecta al servidor

1. Verifica que el servidor esté corriendo:

   ```bash
   tail -f logs/server.log
   ```

2. Usa el botón "Reconectar" en la GUI

3. Verifica host y puerto en `config/client_config.json`

## Próximos Pasos para Versión Distribuida

1. **Selector de Nodos**:

   ```python
   # Agregar dropdown para elegir servidor
   self.server_selector = ctk.CTkComboBox(
       frame,
       values=["node1:5000", "node2:5000", "node3:5000"]
   )
   ```

2. **Búsqueda en Múltiples Nodos**:

   ```python
   # Lanzar búsquedas paralelas
   results = []
   threads = []
   for server in servers:
       t = threading.Thread(target=search_node, args=(server,))
       threads.append(t)
       t.start()
   ```

3. **Progress Bars**:

   ```python
   # Mostrar progreso de descarga
   self.progress_bar = ctk.CTkProgressBar(frame)
   self.progress_bar.pack()
   ```

4. **Gráficas de Red**:

   ```python
   # Instalar matplotlib para gráficas
   pip install matplotlib
   # Mostrar estadísticas visuales
   ```
