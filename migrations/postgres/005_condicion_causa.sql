-- Condición de la causa: tercer eje, aparte de la etapa y la fase.
-- VIGENTE (por defecto), ARCHIVADA, ABANDONADA, CONCLUIDA o POR_CONFIRMAR
-- (un auto de cierre cuyo texto resolutivo no se pudo leer). Aditiva.
ALTER TABLE expedientes
    ADD COLUMN IF NOT EXISTS condicion VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
    ADD COLUMN IF NOT EXISTS fecha_condicion VARCHAR(50),
    ADD COLUMN IF NOT EXISTS actuacion_condicion TEXT;

-- Se reemplaza siempre: una versión anterior de esta migración tenía 4 valores.
ALTER TABLE expedientes DROP CONSTRAINT IF EXISTS expedientes_condicion_check;
ALTER TABLE expedientes ADD CONSTRAINT expedientes_condicion_check
    CHECK (condicion IN ('VIGENTE', 'ARCHIVADA', 'ABANDONADA', 'CONCLUIDA', 'POR_CONFIRMAR'));

CREATE INDEX IF NOT EXISTS idx_expedientes_condicion ON expedientes(condicion);
