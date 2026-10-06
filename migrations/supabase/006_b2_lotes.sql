-- Permite entradas nuevas en B2, vinculadas al usuario y al ID del lote.
-- Las rutas antiguas de Supabase siguen siendo válidas.
ALTER TABLE public.solicitudes_lote
    DROP CONSTRAINT IF EXISTS ck_solicitud_archivo;

ALTER TABLE public.solicitudes_lote
    ADD CONSTRAINT ck_solicitud_archivo CHECK (
        archivo_ruta = 'entradas/' || id::text || '.xlsx'
        OR archivo_ruta = 'b2:entradas/' || solicitado_por::text || '/' || id::text || '.xlsx'
    );
