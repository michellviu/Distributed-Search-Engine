# 🖥️ Cliente con Interfaz Gráfica (GUI)

## Descripción

El cliente GUI proporciona una interfaz gráfica para interactuar con el sistema de búsqueda distribuida. Soporta dos modos:

- **CustomTkinter**: Interfaz moderna y estilizada (requiere instalación)
- **Tkinter estándar**: Interfaz básica incluida en Python

## Instalación

### Con Interfaz Moderna (Recomendado)

```bash
# Instalar CustomTkinter
pip install customtkinter

# O instalar todas las dependencias de GUI
pip install -r requirements-gui.txt
```

### Sin Instalación Adicional

El cliente detecta automáticamente si CustomTkinter está disponible. Si no lo está, usa Tkinter estándar que viene incluido con Python.

## Uso

### Inicio Rápido

```bash
# Desde el directorio raíz del proyecto
./start_client_gui.sh
```

### Inicio Manual

```bash
# Ejecutar como módulo (recomendado)
python -m src.client.client_gui

# Con parámetros personalizados
python -m src.client.client_gui --host localhost --port 5000

# Especificar múltiples coordinadores
python -m src.client.client_gui --coordinators "localhost:5000,192.168.1.100:5000"
```

### Variables de Entorno

```bash
# Configurar coordinadores via variable de entorno
export COORDINATOR_ADDRESSES="localhost:5000,backup:5000"
python -m src.client.client_gui
```

## Interfaz de Usuario

### Panel Principal

```
┌────────────────────────────────────────────────────────────┐
│  🔍 Distributed Search Engine                              │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Búsqueda: [________________________] Tipo: [.txt ▼]       │
│                                                            │
│  [🔍 Buscar]  [📋 Listar Todo]  [🔄 Reconectar]            │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  Resultados:                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 📄 documento.txt - Score: 0.95 - 2.3 KB              │  │
│  │ 📄 readme.md - Score: 0.87 - 1.1 KB                  │  │
│  │ 📄 config.json - Score: 0.72 - 0.5 KB                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  Acciones:                                                 │
│  [📥 Descargar Seleccionado]  [📤 Indexar Archivo]         │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  Log:                                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ [INFO] Conectado a localhost:5000                    │  │
│  │ [OK] Búsqueda completada: 3 resultados               │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Funcionalidades

#### 1. Búsqueda

- **Campo de búsqueda**: Ingresa términos a buscar
- **Filtro de tipo**: Selecciona extensión (.txt, .md, .py, etc.)
- **Búsqueda vacía + tipo**: Lista todos los archivos de ese tipo
- **Presiona Enter** o clic en "Buscar"

#### 2. Listar Todo

- Muestra todos los archivos indexados en el cluster
- No requiere parámetros de búsqueda

#### 3. Descargar

1. Selecciona un archivo de los resultados
2. Clic en "Descargar Seleccionado"
3. Elige el directorio de destino
4. El archivo se descarga desde cualquier réplica disponible

#### 4. Indexar Archivo

1. Clic en "Indexar Archivo"
2. Selecciona el archivo a subir
3. El archivo se distribuye automáticamente a N nodos (factor de replicación)

#### 5. Reconectar

- Intenta reconectar al coordinador si se perdió la conexión
- Útil después de reiniciar el cluster

### Panel de Resultados

Cada resultado muestra:
- 📄 Nombre del archivo
- Ruta completa
- Score de relevancia (0.0 - 1.0)
- Tamaño en KB
- Tipo de archivo

### Panel de Log

Registro de todas las operaciones con código de colores:
- 🟢 Verde: Operación exitosa
- 🔴 Rojo: Error
- ⚪ Blanco: Información

## Configuración

### Archivo de Configuración

El cliente busca configuración en `config/client_config.json`:

```json
{
  "distributed": {
    "coordinators": ["localhost:5000"]
  },
  "host": "localhost",
  "port": 5000,
  "download_path": "./downloads"
}
```

### Prioridad de Configuración

1. Argumentos de línea de comandos (`--host`, `--port`)
2. Variables de entorno (`COORDINATOR_ADDRESSES`)
3. Archivo de configuración
4. Valores por defecto (localhost:5000)

## Múltiples Coordinadores

El cliente soporta failover automático entre coordinadores:

```bash
# Especificar múltiples coordinadores
python -m src.client.client_gui --coordinators "coord1:5000,coord2:5000,coord3:5000"
```

El cliente:
1. Intenta conectar al primer coordinador
2. Si falla, intenta el siguiente
3. Mantiene health checks periódicos
4. Reconecta automáticamente si el coordinador actual cae

## Ejemplos de Uso

### Búsqueda Simple

1. Escribe "python" en el campo de búsqueda
2. Clic en "Buscar"
3. Ver resultados que contienen "python"

### Filtrar por Tipo

1. Deja el campo de búsqueda vacío
2. Selecciona ".md" en el filtro de tipo
3. Clic en "Buscar"
4. Ver todos los archivos Markdown

### Búsqueda Combinada

1. Escribe "readme" en el campo de búsqueda
2. Selecciona ".md" en el filtro de tipo
3. Clic en "Buscar"
4. Ver archivos Markdown que contienen "readme"

### Descargar Archivo

1. Realiza una búsqueda
2. Selecciona un archivo haciendo clic en él
3. Clic en "Descargar Seleccionado"
4. Elige carpeta de destino
5. El archivo se guarda localmente

### Subir Nuevo Archivo

1. Clic en "Indexar Archivo"
2. Selecciona un archivo de tu sistema
3. El archivo se sube y replica automáticamente
4. Aparecerá en futuras búsquedas

## Solución de Problemas

### "No se puede conectar al coordinador"

```bash
# Verificar que el coordinador esté activo
docker service ls | grep coordinator

# Verificar puerto
nc -z localhost 5000
```

### "CustomTkinter no disponible"

```bash
# Instalar CustomTkinter
pip install customtkinter

# O crear entorno virtual
python -m venv venv
source venv/bin/activate
pip install customtkinter
```

### La GUI se congela

- Las operaciones de red se ejecutan en threads separados
- Si hay problemas de red, puede haber un timeout (5 segundos)
- Usar "Reconectar" para restablecer conexión

### Archivo no aparece después de indexar

1. Esperar unos segundos (propagación)
2. Usar "Listar Todo" para refrescar
3. Verificar logs del coordinador
