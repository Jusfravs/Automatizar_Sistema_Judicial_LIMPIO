-- Historial y auditoría append-only para el modo concurrente.
-- La tabla expedientes conserva la fotografía vigente.

CREATE TABLE IF NOT EXISTS actuaciones_procesales (
    actuacion_id VARCHAR(28) PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    carpeta TEXT NOT NULL,
    fecha TEXT NOT NULL,
    titulo TEXT NOT NULL,
    detalle TEXT NOT NULL,
    contenido_sha256 CHAR(64) NOT NULL,
    datos_json JSONB NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_actuaciones_procesales_causa
    ON actuaciones_procesales(numero_causa, fecha);

CREATE TABLE IF NOT EXISTS ejecuciones_inferencia (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    huella_contexto CHAR(64) NOT NULL,
    version_reglas VARCHAR(80) NOT NULL,
    estado_json JSONB NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(numero_causa, huella_contexto, version_reglas)
);

CREATE TABLE IF NOT EXISTS auditorias_ia (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    huella_contexto VARCHAR(160) NOT NULL,
    modelo VARCHAR(160) NOT NULL,
    modo VARCHAR(32) NOT NULL,
    estado VARCHAR(32) NOT NULL,
    decision_json JSONB,
    consumo_json JSONB,
    error_codigo VARCHAR(80),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(numero_causa, huella_contexto, modelo, modo)
);
CREATE INDEX IF NOT EXISTS idx_auditorias_ia_causa
    ON auditorias_ia(numero_causa, creado_en);

CREATE TABLE IF NOT EXISTS revisiones_ia (
    id BIGSERIAL PRIMARY KEY,
    auditoria_id BIGINT NOT NULL UNIQUE REFERENCES auditorias_ia(id),
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    estado VARCHAR(32) NOT NULL DEFAULT 'PENDIENTE',
    decision_humana VARCHAR(32),
    eta_id_manual INTEGER,
    fas_id_manual INTEGER,
    observacion TEXT,
    revisado_en TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS hitos_procesales (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES expedientes(numero_causa),
    actuacion_id VARCHAR(28) NOT NULL REFERENCES actuaciones_procesales(actuacion_id),
    eta_id INTEGER,
    fas_id INTEGER,
    fuente VARCHAR(40) NOT NULL,
    condicion VARCHAR(40) NOT NULL,
    version VARCHAR(80) NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(numero_causa, actuacion_id, fuente, version)
);
