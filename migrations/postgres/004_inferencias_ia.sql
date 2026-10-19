-- Equivalente local de la migración Supabase 011; no se aplica automáticamente.
CREATE TABLE IF NOT EXISTS inferencias_ia (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    ejecucion_id UUID NULL REFERENCES ejecuciones(id),
    huella_contexto CHAR(64) NOT NULL,
    modelo VARCHAR(160) NOT NULL,
    version_prompt VARCHAR(80) NOT NULL,
    motor_eta_actual INTEGER,
    motor_fas_actual INTEGER,
    motor_eta_ultimo INTEGER,
    motor_fas_ultimo INTEGER,
    ia_eta_actual INTEGER,
    ia_fas_actual INTEGER,
    ia_eta_ultimo INTEGER,
    ia_fas_ultimo INTEGER,
    confianza NUMERIC(4,3) CHECK (confianza BETWEEN 0 AND 1),
    evidencias JSONB NOT NULL DEFAULT '[]'::jsonb,
    motivo TEXT,
    coincide_actual BOOLEAN,
    coincide_ultimo BOOLEAN,
    latencia_ms INTEGER CHECK (latencia_ms >= 0),
    tokens INTEGER CHECK (tokens >= 0),
    error VARCHAR(80),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (numero_causa, huella_contexto, modelo, version_prompt)
);
CREATE INDEX IF NOT EXISTS idx_inferencias_ia_creado ON inferencias_ia(creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_inferencias_ia_causa ON inferencias_ia(numero_causa, creado_en DESC);
