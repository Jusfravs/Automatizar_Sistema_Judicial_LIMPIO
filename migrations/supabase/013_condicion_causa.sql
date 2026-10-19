-- Condición de la causa para el portal (revisión conjunta Claude/Codex).
-- Requiere migrations/postgres/005_condicion_causa.sql (columnas en expedientes).
-- 1. "Causas por etapa" cuenta solo las causas VIGENTES; las cerradas se
--    cuentan aparte en v_resumen_condicion. Mismas columnas y permisos que la 010.
-- 2. v_resumen_condicion: total por condición, para el indicador de Inicio.

CREATE OR REPLACE VIEW public.v_resumen_etapas_actuales
WITH (security_invoker = on) AS
SELECT c.eta_id, c.nombre AS etapa, count(e.numero_causa)::INTEGER AS causas
FROM public.catalogo_etapas c
LEFT JOIN public.expedientes e
       ON e.eta_id_etapa_actual = c.eta_id AND e.condicion = 'VIGENTE'
GROUP BY c.eta_id, c.nombre
UNION ALL
SELECT NULL, 'SIN ETAPA', count(*)::INTEGER
FROM public.expedientes e
WHERE e.condicion = 'VIGENTE'
  AND (e.eta_id_etapa_actual IS NULL
       OR NOT EXISTS (SELECT 1 FROM public.catalogo_etapas c WHERE c.eta_id = e.eta_id_etapa_actual));

CREATE OR REPLACE VIEW public.v_resumen_condicion
WITH (security_invoker = on) AS
SELECT k.condicion, count(e.numero_causa)::INTEGER AS causas
FROM (VALUES ('VIGENTE'), ('ARCHIVADA'), ('ABANDONADA'), ('CONCLUIDA')) AS k(condicion)
LEFT JOIN public.expedientes e ON e.condicion = k.condicion
GROUP BY k.condicion;

REVOKE ALL ON public.v_resumen_condicion FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_resumen_condicion TO authenticated;
