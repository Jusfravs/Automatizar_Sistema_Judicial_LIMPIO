-- Condición de la causa: tercer eje, aparte de la etapa y la fase.
-- VIGENTE (por defecto), ARCHIVADA, ABANDONADA o CONCLUIDA. Aditiva.
ALTER TABLE expedientes
    ADD COLUMN IF NOT EXISTS condicion VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
    ADD COLUMN IF NOT EXISTS fecha_condicion VARCHAR(50),
    ADD COLUMN IF NOT EXISTS actuacion_condicion TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'expedientes_condicion_check'
    ) THEN
        ALTER TABLE expedientes ADD CONSTRAINT expedientes_condicion_check
            CHECK (condicion IN ('VIGENTE', 'ARCHIVADA', 'ABANDONADA', 'CONCLUIDA'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_expedientes_condicion ON expedientes(condicion);
