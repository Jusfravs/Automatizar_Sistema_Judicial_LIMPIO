-- Ajustes a las vistas de resumen de la 009 (revisión de Codex). Mismas columnas y permisos.
-- 1. Causas con una etapa que no está en el catálogo cuentan en "SIN ETAPA" (no se pierden del total).
-- 2. "Causas consultadas" cuenta solo consultas con resultado: los intentos con error
--    (ERROR, ERROR_REINTENTABLE, ERROR_FINAL) no son una consulta hecha.

CREATE OR REPLACE VIEW public.v_resumen_etapas_actuales
WITH (security_invoker = on) AS
SELECT c.eta_id, c.nombre AS etapa, count(e.numero_causa)::INTEGER AS causas
FROM public.catalogo_etapas c
LEFT JOIN public.expedientes e ON e.eta_id_etapa_actual = c.eta_id
GROUP BY c.eta_id, c.nombre
UNION ALL
SELECT NULL, 'SIN ETAPA', count(*)::INTEGER
FROM public.expedientes e
WHERE e.eta_id_etapa_actual IS NULL
   OR NOT EXISTS (SELECT 1 FROM public.catalogo_etapas c WHERE c.eta_id = e.eta_id_etapa_actual);

CREATE OR REPLACE VIEW public.v_actividad_diaria
WITH (security_invoker = on) AS
WITH hoy AS (
    SELECT (now() AT TIME ZONE 'America/Guayaquil')::DATE AS dia
),
dias AS (
    SELECT generate_series(hoy.dia - 29, hoy.dia, INTERVAL '1 day')::DATE AS dia FROM hoy
),
conteos AS (
    SELECT (r.creado_en AT TIME ZONE 'America/Guayaquil')::DATE AS dia,
           count(DISTINCT r.numero_causa)::INTEGER AS causas
    FROM public.resultados_ejecucion r
    WHERE r.creado_en >= now() - INTERVAL '31 days'
      AND r.estado NOT LIKE 'ERROR%'
    GROUP BY 1
)
SELECT d.dia, coalesce(c.causas, 0) AS causas
FROM dias d
LEFT JOIN conteos c USING (dia);

REVOKE ALL ON public.v_resumen_etapas_actuales, public.v_actividad_diaria FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_resumen_etapas_actuales, public.v_actividad_diaria TO authenticated;
