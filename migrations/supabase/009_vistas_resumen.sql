-- Vistas de resumen para los gráficos de Inicio ("Panorama de la cartera").
-- Solo lectura y aditiva: no toca tablas ni datos. Con security_invoker, cada vista respeta
-- el RLS de quien consulta (un usuario sin perfil activo no ve filas).

-- Causas por etapa procesal actual, en el orden del catálogo (1 → 6). Las causas sin etapa
-- (revisión manual, excluidas o sin datos) van en una fila aparte con eta_id NULL.
CREATE OR REPLACE VIEW public.v_resumen_etapas_actuales
WITH (security_invoker = on) AS
SELECT c.eta_id, c.nombre AS etapa, count(e.numero_causa)::INTEGER AS causas
FROM public.catalogo_etapas c
LEFT JOIN public.expedientes e ON e.eta_id_etapa_actual = c.eta_id
GROUP BY c.eta_id, c.nombre
UNION ALL
SELECT NULL, 'SIN ETAPA', count(*)::INTEGER
FROM public.expedientes
WHERE eta_id_etapa_actual IS NULL;

-- Causas consultadas por día en los últimos 30 días (hora de Ecuador), con los días sin
-- actividad en cero: el gráfico muestra las pausas en vez de unir días lejanos.
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
    GROUP BY 1
)
SELECT d.dia, coalesce(c.causas, 0) AS causas
FROM dias d
LEFT JOIN conteos c USING (dia);

REVOKE ALL ON public.v_resumen_etapas_actuales, public.v_actividad_diaria FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_resumen_etapas_actuales, public.v_actividad_diaria TO authenticated;
