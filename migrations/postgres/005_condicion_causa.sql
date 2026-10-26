-- Condición de la causa: tercer eje, aparte de la etapa y la fase.
-- VIGENTE, ARCHIVADA, ABANDONADA, CONCLUIDA o POR_CONFIRMAR (no se pudo
-- decidir: auto de cierre sin texto resolutivo o causa sin historial). Aditiva.
-- El histórico entra como POR_CONFIRMAR, no VIGENTE: hasta que
-- scripts/recalcular_condicion.py lo lea, su condición no está comprobada.
-- El motor siempre escribe la condición al procesar una causa.
ALTER TABLE expedientes
    ADD COLUMN IF NOT EXISTS condicion VARCHAR(20) NOT NULL DEFAULT 'POR_CONFIRMAR',
    ADD COLUMN IF NOT EXISTS fecha_condicion VARCHAR(50),
    ADD COLUMN IF NOT EXISTS actuacion_condicion TEXT;

-- ADD COLUMN IF NOT EXISTS no cambia el default si una versión anterior de
-- esta migración ya creó la columna con DEFAULT 'VIGENTE'.
ALTER TABLE expedientes ALTER COLUMN condicion SET DEFAULT 'POR_CONFIRMAR';

-- Se reemplaza siempre: una versión anterior de esta migración tenía 4 valores.
ALTER TABLE expedientes DROP CONSTRAINT IF EXISTS expedientes_condicion_check;
ALTER TABLE expedientes ADD CONSTRAINT expedientes_condicion_check
    CHECK (condicion IN ('VIGENTE', 'ARCHIVADA', 'ABANDONADA', 'CONCLUIDA', 'POR_CONFIRMAR'));

CREATE INDEX IF NOT EXISTS idx_expedientes_condicion ON expedientes(condicion);
