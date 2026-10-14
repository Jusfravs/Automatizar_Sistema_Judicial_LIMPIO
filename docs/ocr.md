# Lectura de adjuntos y OCR: plan pendiente

Este documento recoge el acuerdo de trabajo del 13/10/2026. **No autoriza ni ejecuta descargas, OCR ni cambios en el motor.** El historial y el análisis técnico detallado están en los documentos de coordinación privados `C:\Users\pasante.callcenter\proyectos\coordinacion\discusion-ocr.md` y `C:\Users\pasante.callcenter\proyectos\coordinacion\informe-unlimited-ocr.md`.

## Papel del OCR

El motor lee actuaciones que ya llegan como texto digital y decide la etapa y fase procesal. OCR solo puede aportar texto de adjuntos escaneados que hoy no se leen; **no clasifica causas ni reemplaza al motor o a la inferencia de NVIDIA**. El nombre, extensión y `tipoIngreso` del adjunto son pistas, no pruebas de que una página necesite OCR. En la muestra exploratoria aparecieron `tipoIngreso` **O, ES, CJ y AS**, junto con `nombreArchivo` y `uuid`; deben tratarse como metadatos y no como contenido del documento.

## Requisitos previos

Justin debe confirmar con TI/privacidad de Espoir la finalidad, el acceso permitido, la exclusión de documentos restringidos y la retención. PDF, imágenes y texto extraído no se conservan al terminar cada ejecución. TI/privacidad define por separado el plazo y acceso de las métricas y de la tabla restringida que relaciona ID seudónimo con causa. Conservar documentos para etiquetar casos requeriría otra autorización. Cada etapa requiere la aprobación de Justin.

El navegador debe usar un directorio temporal privado en un volumen cuyo cifrado en reposo confirme TI; también se controlan perfil, caché y destino de descargas. Al terminar se cierra el contexto y se comprueba la limpieza. No se guardan documentos en OneDrive, Git ni el scratchpad sincronizado. `expect_download` de Playwright puede crear archivos temporales: no se promete procesamiento «solo en memoria» ni borrado físico seguro de SSD o respaldos.

## Etapa A: comprobar el mecanismo

Con navegador visible, Justin resuelve el captcha. Se inspeccionan **3–5 documentos** de tipos variados (ES, O y, si existen, CJ/AS) para ver cómo se entregan, tamaño, restricciones y capa de texto. Esta etapa valida el mecanismo; **no estima prevalencia** de escaneos.

## Etapa B: descubrimiento acotado

Solo si la Etapa A funciona y Justin la aprueba: hasta **20 causas** de la cartera estratificadas por incertidumbre procesal, con documentos ES/CJ/AS y controles O. Los topes son **60 archivos, 20 MB y 50 páginas por archivo, 40 captchas o USD 1 de 2Captcha, y 2 horas**. Una sesión secuencial, separada de los trabajadores y fuera del horario de lotes; pausa inicial de 5 segundos con retroceso. Suspender ante un HTTP 429, WAF, captcha anómalo, dos fallos consecutivos de captcha o cualquier error de privacidad.

Los 20 MB y 50 páginas son límites de **aceptación y procesamiento**, no una promesa de evitar toda transferencia mayor: el tamaño puede conocerse antes, durante o después de la descarga, y las páginas se cuentan al abrir el PDF. Ante un exceso, descartar, registrar la razón sin datos sensibles y detener la toma de ese tipo hasta revisar el mecanismo.

Medir por página caracteres útiles, predominio de imagen, legibilidad de fecha/número de causa/verbo procesal y clase preliminar (digital, escaneada, mixta o vacía). Revisión humana de al menos cinco PDF, uno por tipo disponible, y de todos los dudosos. El CSV de métricas usa ID seudónimo y no contiene texto, nombres, URLs ni tokens. La correspondencia ID↔causa queda aparte y restringida. La muestra no permite extrapolar un porcentaje global a toda la cartera.

## Decisión técnica posterior

1. Si la **evidencia decisiva** tiene texto digital legible, extraer ese texto directamente.
2. Si está escaneada, evaluar OCR ligero (Tesseract o PaddleOCR) solo para esa evidencia.
3. Si el OCR ligero falla, recién evaluar Unlimited-OCR localmente, fuera de producción y con una revisión fija del modelo. El análisis del repositorio detectó uso de `eval()` sobre salida del modelo y necesidad de `trust_remote_code`; se exigiría `eval_mode=True`, evitar `save_results=True`, revisar dependencias y no usar código remoto mutable. La GPU de **8 GB** del equipo apenas alcanza el mínimo publicado y puede quedarse sin margen para imágenes y caché. No se adopta la API en nube para documentos judiciales.

Antes de integrar resultados al motor, Operaciones debe etiquetar unas 100 causas estratificadas, con dos revisores para las ambiguas, y medir aciertos y **falsos avances** de etapa/fase. El motor actual no constituye la verdad de referencia.

**Estado:** plan documentado; pendiente autorización de Justin y confirmación de TI. No se ejecutó OCR.
