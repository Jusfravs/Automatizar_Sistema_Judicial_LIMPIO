-- Endurecimiento tras la auditoría del portal.

-- La subida solo admite el nombre exacto que exige el contrato.
ALTER POLICY lotes_subida_entradas ON storage.objects
    WITH CHECK (
        bucket_id = 'lotes'
        AND name ~ '^entradas/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.xlsx$'
        AND (SELECT privado.rol_actual()) IS NOT NULL
    );

-- Las tablas, secuencias y funciones futuras no otorgan permisos implícitos a
-- usuarios autenticados: cada migración debe concederlos de forma explícita.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM authenticated;

-- Trazabilidad de cancelaciones.
ALTER TABLE public.solicitudes_lote
    ADD COLUMN IF NOT EXISTS cancelado_por UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_solicitudes_cancelado_por
    ON public.solicitudes_lote(cancelado_por);

CREATE OR REPLACE FUNCTION public.cancelar_solicitud(p_id UUID)
RETURNS VARCHAR
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_estado VARCHAR;
    v_ejecucion UUID;
    v_usuario UUID := (SELECT auth.uid());
    v_resultado VARCHAR;
BEGIN
    IF privado.rol_actual() IS NULL THEN
        RAISE EXCEPTION 'ROL_NO_AUTORIZADO' USING ERRCODE = '42501';
    END IF;
    SELECT estado, ejecucion_id INTO v_estado, v_ejecucion
      FROM public.solicitudes_lote WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SOLICITUD_NO_EXISTE';
    END IF;
    IF v_estado = 'SOLICITADA' THEN
        UPDATE public.solicitudes_lote
           SET estado = 'CANCELADA', cancelar = TRUE, cancelado_por = v_usuario,
               finalizado_en = now(), mensaje = 'Cancelada antes de iniciar.'
         WHERE id = p_id;
        v_resultado := 'CANCELADA';
    ELSIF v_estado IN ('TOMADA', 'PREPARANDO', 'EN_CURSO') THEN
        UPDATE public.solicitudes_lote
           SET cancelar = TRUE, cancelado_por = v_usuario
         WHERE id = p_id;
        v_resultado := 'CANCELACION_SOLICITADA';
    ELSE
        RAISE EXCEPTION 'SOLICITUD_FINALIZADA';
    END IF;
    INSERT INTO public.eventos_auditoria (ejecucion_id, tipo_evento, origen, detalle)
    VALUES (v_ejecucion, 'SOLICITUD_CANCELADA', 'portal',
            format('solicitud=%s usuario=%s resultado=%s', p_id, v_usuario, v_resultado));
    RETURN v_resultado;
END;
$$;
