CREATE TABLE IF NOT EXISTS ejecuciones (
    id UUID PRIMARY KEY,
    perfil VARCHAR(120) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PREPARADA',
    trabajadores_configurados INTEGER NOT NULL DEFAULT 1,
    total_esperado INTEGER NOT NULL DEFAULT 0,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    iniciado_en TIMESTAMPTZ,
    finalizado_en TIMESTAMPTZ,
    CONSTRAINT ck_ejecuciones_estado CHECK (
        estado IN ('PREPARADA', 'ACTIVA', 'DETENIENDO', 'COMPLETADA', 'FALLIDA', 'CANCELADA')
    )
);

CREATE TABLE IF NOT EXISTS expedientes (
    numero_causa VARCHAR(60) PRIMARY KEY,
    ciudad VARCHAR(100) DEFAULT 'QUITO',
    estado VARCHAR(50) DEFAULT 'PENDIENTE',
    eta_id_ultima_etapa INTEGER,
    ultima_etapa VARCHAR(150),
    fas_id_ultima_fase INTEGER,
    ultima_fase VARCHAR(150),
    fecha_fin_ultima_fase VARCHAR(50),
    eta_id_etapa_actual INTEGER,
    etapa_actual VARCHAR(150),
    fas_id_fase_actual INTEGER,
    fase_actual VARCHAR(150),
    fecha_inicio_fase_actual VARCHAR(50),
    mensaje_especial VARCHAR(255),
    actor TEXT,
    demandado TEXT,
    tipo_accion TEXT,
    fecha_inicio_juicio VARCHAR(50),
    total_actuaciones INTEGER DEFAULT 0,
    origen VARCHAR(100) DEFAULT 'ESATJE_TRANSACCIONAL',
    ruta_html TEXT,
    reintentos INTEGER DEFAULT 0,
    datos_json JSONB,
    fuente_migracion VARCHAR(120),
    fuente_prioridad INTEGER NOT NULL DEFAULT 0,
    version_fuente_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE expedientes
    ADD COLUMN IF NOT EXISTS eta_id_ultima_etapa INTEGER,
    ADD COLUMN IF NOT EXISTS fas_id_ultima_fase INTEGER,
    ADD COLUMN IF NOT EXISTS eta_id_etapa_actual INTEGER,
    ADD COLUMN IF NOT EXISTS fas_id_fase_actual INTEGER,
    ADD COLUMN IF NOT EXISTS fuente_migracion VARCHAR(120),
    ADD COLUMN IF NOT EXISTS fuente_prioridad INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS version_fuente_en TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS cola_trabajo (
    id BIGSERIAL PRIMARY KEY,
    ejecucion_id UUID NOT NULL REFERENCES ejecuciones(id) ON DELETE CASCADE,
    numero_causa VARCHAR(60) NOT NULL,
    posicion INTEGER NOT NULL,
    prioridad INTEGER NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    intentos INTEGER NOT NULL DEFAULT 0,
    disponible_desde TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    worker_id VARCHAR(120),
    reservado_en TIMESTAMPTZ,
    heartbeat_en TIMESTAMPTZ,
    lease_hasta TIMESTAMPTZ,
    ultimo_error TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ejecucion_id, numero_causa),
    CONSTRAINT ck_cola_estado CHECK (
        estado IN (
            'PENDIENTE', 'EN_PROCESO', 'PROCESADO', 'PARCIAL',
            'SIN_RESULTADOS', 'EXCLUIDO_NO_CORRESPONDE', 'REVISION',
            'ERROR_REINTENTABLE', 'ERROR_FINAL', 'CANCELADO'
        )
    )
);

CREATE TABLE IF NOT EXISTS resultados_ejecucion (
    id BIGSERIAL PRIMARY KEY,
    ejecucion_id UUID REFERENCES ejecuciones(id) ON DELETE SET NULL,
    trabajo_id BIGINT REFERENCES cola_trabajo(id) ON DELETE SET NULL,
    numero_causa VARCHAR(60) NOT NULL,
    intento INTEGER NOT NULL DEFAULT 1,
    estado VARCHAR(50) NOT NULL,
    origen VARCHAR(100) NOT NULL,
    worker_id VARCHAR(120),
    ciudad VARCHAR(100),
    datos_json JSONB NOT NULL,
    fuente_migracion VARCHAR(120),
    fuente_actualizado_en TIMESTAMPTZ,
    hash_fuente CHAR(64),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS actuaciones (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) REFERENCES expedientes(numero_causa) ON DELETE CASCADE,
    fecha VARCHAR(50),
    tipo_actuacion TEXT,
    detalle TEXT,
    instancia VARCHAR(100),
    orden INTEGER,
    creado_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eventos_auditoria (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60),
    ejecucion_id UUID REFERENCES ejecuciones(id) ON DELETE SET NULL,
    worker_id VARCHAR(120),
    tipo_evento VARCHAR(100) NOT NULL,
    origen VARCHAR(100),
    detalle TEXT,
    hash_fuente CHAR(64),
    creado_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE eventos_auditoria
    ADD COLUMN IF NOT EXISTS ejecucion_id UUID REFERENCES ejecuciones(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS worker_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS hash_fuente CHAR(64);

CREATE INDEX IF NOT EXISTS idx_cola_reserva
    ON cola_trabajo(ejecucion_id, estado, disponible_desde, prioridad DESC, posicion);
CREATE INDEX IF NOT EXISTS idx_cola_lease ON cola_trabajo(ejecucion_id, lease_hasta)
    WHERE estado = 'EN_PROCESO';
CREATE INDEX IF NOT EXISTS idx_resultados_ejecucion ON resultados_ejecucion(ejecucion_id, id);
CREATE INDEX IF NOT EXISTS idx_resultados_causa ON resultados_ejecucion(numero_causa, creado_en DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_resultados_hash_fuente
    ON resultados_ejecucion(hash_fuente) WHERE hash_fuente IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_eventos_hash_fuente
    ON eventos_auditoria(hash_fuente) WHERE hash_fuente IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_expedientes_estado ON expedientes(estado);
CREATE INDEX IF NOT EXISTS idx_expedientes_ultima_fase ON expedientes(ultima_fase);
CREATE INDEX IF NOT EXISTS idx_expedientes_ciudad ON expedientes(ciudad);
CREATE INDEX IF NOT EXISTS idx_expedientes_datos_gin ON expedientes USING GIN(datos_json);
CREATE INDEX IF NOT EXISTS idx_actuaciones_causa ON actuaciones(numero_causa, orden);
CREATE INDEX IF NOT EXISTS idx_eventos_causa ON eventos_auditoria(numero_causa, creado_en);

CREATE OR REPLACE VIEW v_estado_ejecuciones AS
SELECT
    e.id,
    e.perfil,
    e.estado,
    e.trabajadores_configurados,
    e.total_esperado,
    COUNT(c.id) FILTER (WHERE c.estado = 'PENDIENTE') AS pendientes,
    COUNT(c.id) FILTER (WHERE c.estado = 'EN_PROCESO') AS en_proceso,
    COUNT(c.id) FILTER (
        WHERE c.estado IN ('PROCESADO', 'PARCIAL', 'SIN_RESULTADOS',
                           'EXCLUIDO_NO_CORRESPONDE', 'REVISION')
    ) AS atendidos,
    COUNT(c.id) FILTER (WHERE c.estado = 'ERROR_FINAL') AS errores_finales,
    e.creado_en,
    e.iniciado_en,
    e.finalizado_en
FROM ejecuciones e
LEFT JOIN cola_trabajo c ON c.ejecucion_id = e.id
GROUP BY e.id;

CREATE OR REPLACE VIEW v_cola_trabajo AS
SELECT ejecucion_id, numero_causa, posicion, estado, intentos, worker_id,
       reservado_en, heartbeat_en, lease_hasta, ultimo_error, actualizado_en
FROM cola_trabajo
ORDER BY ejecucion_id, posicion;

CREATE OR REPLACE VIEW v_trabajadores_activos AS
SELECT ejecucion_id, worker_id, COUNT(*) AS trabajos_activos,
       MIN(reservado_en) AS activo_desde,
       MAX(heartbeat_en) AS ultimo_heartbeat,
       MAX(lease_hasta) AS lease_hasta
FROM cola_trabajo
WHERE estado = 'EN_PROCESO'
GROUP BY ejecucion_id, worker_id;

CREATE OR REPLACE VIEW v_resumen_fases AS
SELECT COALESCE(ultima_etapa, 'SIN PROCESAR') AS etapa,
       COALESCE(ultima_fase, 'SIN PROCESAR') AS fase,
       COUNT(*) AS total_casos,
       ROUND(
           COUNT(*) * 100.0 /
           NULLIF((SELECT COUNT(*) FROM expedientes WHERE estado = 'PROCESADO'), 0),
           2
       ) AS porcentaje
FROM expedientes
WHERE estado = 'PROCESADO'
GROUP BY ultima_etapa, ultima_fase
ORDER BY total_casos DESC;

CREATE OR REPLACE VIEW v_casos_revision_manual AS
SELECT numero_causa, ciudad, ultima_fase, fecha_fin_ultima_fase,
       mensaje_especial, actor, demandado, total_actuaciones, actualizado_en
FROM expedientes
WHERE mensaje_especial ILIKE '%REVISION MANUAL%'
   OR fase_actual = 'REVISION MANUAL'
   OR ultima_fase = '4.3 ACUERDO DE MEDIACION'
ORDER BY actualizado_en DESC;

CREATE OR REPLACE VIEW v_reporte_ejecutivo AS
SELECT numero_causa, ciudad, actor, demandado, tipo_accion,
       fecha_inicio_juicio, ultima_etapa, ultima_fase,
       fecha_fin_ultima_fase, etapa_actual, fase_actual,
       fecha_inicio_fase_actual, mensaje_especial, total_actuaciones,
       estado, actualizado_en, eta_id_ultima_etapa, fas_id_ultima_fase,
       eta_id_etapa_actual, fas_id_fase_actual
FROM expedientes
ORDER BY numero_causa;
