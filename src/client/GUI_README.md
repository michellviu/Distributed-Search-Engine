# Cliente GUI - Motor de Búsqueda Distribuida

## 🚀 Inicio Rápido

```bash
# Desde el directorio raíz del proyecto
./start_client_gui.sh
```

## 📖 Características

### Operaciones Disponibles

1. **🔍 Búsqueda**
   - Buscar por nombre de archivo
   - Filtrar por tipo (ej: `.txt`, `.pdf`)
   - Resultados con score de relevancia

2. **📋 Listar**
   - Ver todos los archivos indexados
   - Agrupados por tipo
   - Información de tamaño

3. **📥 Descargar**
   - Selector gráfico de directorio
   - Progreso visual
   - Verificación de integridad

4. **📂 Indexar**
   - Selector gráfico de archivos
   - Feedback inmediato
   - Actualización del índice

5. **🔄 Reconectar**
   - Reconexión automática
   - Manejo de errores
   - Estado visible

### Interfaz Moderna

- 🌙 Tema oscuro elegante
- 🎨 Diseño CustomTkinter
- 📊 Logs con código de colores
- ⚡ Operaciones sin bloquear la UI

## 📚 Documentación

- `docs/GUI_CLIENT.md` - Guía completa
- `docs/SETUP_GUI.md` - Instalación

## 🐛 Problemas Comunes

**GUI no inicia**: Verifica que el servidor esté corriendo

```bash
./start_server.sh
```

**CustomTkinter no detectado**: El script activa automáticamente el entorno virtual

**Error de conexión**: Usa el botón "Reconectar" en la interfaz

## 🎓 Para Extender a P2P

El código está preparado para:

- Múltiples nodos
- Búsqueda distribuida
- Descarga paralela
- Monitoreo de nodos

Ver `docs/GUI_CLIENT.md` para ejemplos.

---
