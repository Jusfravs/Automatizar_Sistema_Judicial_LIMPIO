-- Señal de vida del servicio que procesa los lotes del portal.
-- El servicio actualiza su fila en cada ciclo; el portal solo la lee para avisar
-- cuando el servidor deja de responder.
CREATE TABLE IF NOT EXISTS public.servicio_latido (
    worker_host   TEXT PRIMARY KEY CHECK (char_length(worker_host) BETWEEN 1 AND 120),
    estado        TEXT NOT NULL CHECK (estado IN ('ESPERANDO', 'PROCESANDO')),
    solicitud_id  UUID REFERENCES public.solicitudes_lote (id) ON DELETE SET NULL,
    iniciado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    latido_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.servicio_latido ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.servicio_latido FROM anon, authenticated;
GRANT SELECT ON public.servicio_latido TO authenticated;

DROP POLICY IF EXISTS lectura_usuarios ON public.servicio_latido;
CREATE POLICY lectura_usuarios ON public.servicio_latido FOR SELECT TO authenticated
    USING ((SELECT privado.rol_actual()) IS NOT NULL);
