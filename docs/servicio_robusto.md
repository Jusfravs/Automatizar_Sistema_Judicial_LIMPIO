# Resistencia del servicio ante interrupciones de PostgreSQL

Las conexiones del servicio y del guardado de resultados tienen un plazo de
conexión de 10 segundos, `statement_timeout` de 120 segundos y keepalives TCP.
El repositorio de cola admite `base_de_datos.statement_timeout_ms` para ajustar
el plazo cuando una operación legítima tarde más. Una consulta lenta del portal
se registra desde los 2 segundos con su tipo y duración, sin parámetros ni SQL
completo. Si falla la conexión, se conserva la excepción original aunque fallen
el `rollback` o el cierre.

El servicio abre una conexión nueva en cada sondeo. Si la base no responde al
arrancar, espera y vuelve a intentar la recuperación de solicitudes interrumpidas
antes de reservar otra. Si se interrumpe mientras consulta la cola en reposo,
espera al siguiente sondeo para reconectar. No repite automáticamente un lote ya
tomado: su ejecución puede haber producido efectos antes del error y requiere
verificar el estado de la solicitud.

## Supervisor propuesto, pendiente de implementación

Un supervisor externo podría vigilar el latido y reiniciar el proceso solamente
si confirma que no existe una solicitud activa (`TOMADA`, `PREPARANDO` o
`EN_CURSO`) para el host. Si PostgreSQL está inaccesible, no puede confirmar esa
condición y no debe reiniciar. El supervisor necesita un umbral sostenido, un
periodo de enfriamiento y un límite de reinicios, con registro del motivo. Antes
de habilitarlo se deben probar suspensión/reanudación de Windows y recuperación
de una solicitud tomada. Ningún reinicio automático se incluye en este PR.
