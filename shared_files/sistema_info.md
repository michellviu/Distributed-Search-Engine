# Sistema Distribuido de Búsqueda - Datos de Prueba

Este archivo contiene información sobre el sistema distribuido.

## Características

1. **Alta Disponibilidad**: El sistema puede tolerar la caída de hasta 2 nodos.
2. **Replicación**: Cada archivo se replica en 3 nodos diferentes.
3. **Búsqueda Rápida**: Índice distribuido para búsquedas eficientes.
4. **Escalabilidad**: Se pueden añadir nodos dinámicamente.

## Arquitectura

- Nodos Coordinadores: Gestionan el cluster
- Nodos de Procesamiento: Almacenan y buscan datos

## Tolerancia a Fallos

El sistema implementa:
- Algoritmo Bully para elección de líder
- Quorum para consistencia de datos
- Re-replicación automática cuando cae un nodo
