# Significado de las tres lecturas del caso

| Campo | Qué representa | Cómo se obtiene |
|---|---|---|
| `ULTIMA ETAPA` / `ULTIMA FASE` | El estado más avanzado acreditado en la rama activa del árbol procesal. Puede seguir en curso. | El motor clasifica las actuaciones; en inferencia dual, NVIDIA propone este mismo hito para compararlo. |
| `ETAPA ACTUAL` / `FASE ACTUAL` | La fase operativa que sigue al último estado reconocido según el árbol. En los extremos de remate y congelamiento puede permanecer en la misma fase. | Se calcula con `MotorInferenciaProcesal.calcular_siguiente_fase`; la IA no elige este par por separado. |
| `ESTADO ULTIMA GESTION JUDICIAL` | El título de la gestión judicial más reciente por fecha, pertenezca o no al árbol. | `src/ultima_gestion.py` lo extrae de las actuaciones; no interviene en la inferencia de etapas. |

El JSON de NVIDIA llama `ultimo_hito` al par que alimenta `ULTIMA ETAPA` y `ULTIMA FASE`. Tras validarlo contra el catálogo y sus referencias de evidencia, el sistema calcula `estado_actual` mediante la transición del árbol. Si la transición no tiene un ID de catálogo válido, la IA no puede sustituir al motor.

La comparación en sombra registra los dos pares de cada fuente. Las etiquetas humanas de evaluación deben distinguir el último estado acreditado de la fase siguiente; ninguna de esas columnas se debe rellenar copiando la última gestión judicial. Una discrepancia motor–IA indica una revisión pendiente, no que alguna fuente haya acertado.

La jerarquía predeterminada sigue siendo `motor`. El envío de texto de actuaciones y la comparación dentro del lote están apagados por defecto.

Cuando `ia_primero` acepta una etapa o fase distinta, conserva las fechas que
calculó el motor y marca `FUENTE_FECHAS=MOTOR` y
`MOTIVO_FUENTE=IA_CON_FECHAS_MOTOR`. NVIDIA no entrega una fecha de hito
verificada; estas fechas pueden corresponder a la clasificación previa del
motor y deben contrastarse antes de usar la cronología como definitiva.

## Evidencia estructurada y cierres (inferencia NVIDIA v4)

La muestra de hasta 100 actuaciones conserva rótulos procesales intermedios para
que un mandamiento anterior no desaparezca detrás de oficios recientes. El
contexto de NVIDIA sigue sin enviar texto libre: agrega el resultado de las
citaciones (`REALIZADA`, `NO_REALIZADA` o `SIN_CONSTANCIA`), referencias
seudónimas `P1`, `P2` para relacionar intentos de una misma persona, y señales
explícitas de abandono o archivo.

Una propuesta 6.2 sin evidencia de mandamiento, 5.1 sin evidencia de sentencia,
2.1 sin constancia de citación o con una citación fallida pendiente, y un hito
seguido de cierre en la misma carpeta se rechazan con un código auditable. El
rechazo deja la clasificación oficial en el motor y requiere revisión humana.
El archivo sigue siendo una condición distinta de la fase del árbol: una causa
archivada no debe interpretarse como tarea activa solo porque el motor calcule
una fase siguiente.
