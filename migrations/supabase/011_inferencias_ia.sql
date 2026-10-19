-- Comparaciones aditivas entre motor y NVIDIA. No altera expedientes.
-- Aplicación pendiente de aprobación de Justin.
CREATE TABLE IF NOT EXISTS public.inferencias_ia (
    id BIGSERIAL PRIMARY KEY,
    numero_causa VARCHAR(60) NOT NULL REFERENCES public.expedientes(numero_causa),
    ejecucion_id UUID NULL REFERENCES public.ejecuciones(id),
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
CREATE INDEX IF NOT EXISTS idx_inferencias_ia_creado ON public.inferencias_ia(creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_inferencias_ia_causa ON public.inferencias_ia(numero_causa, creado_en DESC);

ALTER TABLE public.inferencias_ia ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.inferencias_ia FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.inferencias_ia_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.inferencias_ia TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.inferencias_ia TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.inferencias_ia_id_seq TO service_role;
CREATE POLICY lectura_usuarios ON public.inferencias_ia FOR SELECT TO authenticated
    USING ((SELECT privado.rol_actual()) IS NOT NULL);
-- Ninguna política INSERT/UPDATE/DELETE para authenticated; service_role
-- escribe con su privilegio BYPASSRLS, sin exponer RPC de escritura.
