# Significado de las tres lecturas del caso

| Campo | Qué representa | Cómo se obtiene |
|---|---|---|
| `ULTIMA ETAPA` / `ULTIMA FASE` | El estado más avanzado acreditado en la rama activa del árbol procesal. Puede seguir en curso. | El motor clasifica las actuaciones; en inferencia dual, NVIDIA propone este mismo hito para compararlo. |
| `ETAPA ACTUAL` / `FASE ACTUAL` | La fase operativa que sigue al último estado reconocido según el árbol. En los extremos de remate y congelamiento puede permanecer en la misma fase. | Se calcula con `MotorInferenciaProcesal.calcular_siguiente_fase`; la IA no elige este par por separado. |
| `ESTADO ULTIMA GESTION JUDICIAL` | El título de la gestión judicial más reciente por fecha, pertenezca o no al árbol. | `src/ultima_gestion.py` lo extrae de las actuaciones; no interviene en la inferencia de etapas. |

El JSON de NVIDIA llama `ultimo_hito` al par que alimenta `ULTIMA ETAPA` y `ULTIMA FASE`. Tras validarlo contra el catálogo y sus referencias de evidencia, el sistema calcula `estado_actual` mediante la transición del árbol. Si la transición no tiene un ID de catálogo válido, la IA no puede sustituir al motor.

La comparación en sombra registra los dos pares de cada fuente. Las etiquetas humanas de evaluación deben distinguir el último estado acreditado de la fase siguiente; ninguna de esas columnas se debe rellenar copiando la última gestión judicial. Una discrepancia motor–IA indica una revisión pendiente, no que alguna fuente haya acertado.

La jerarquía predeterminada sigue siendo `motor`. El envío de texto de actuaciones y la comparación dentro del lote están apagados por defecto.
