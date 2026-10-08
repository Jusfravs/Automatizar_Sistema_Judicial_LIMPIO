-- Solo quien creó el lote, o un administrador, puede cancelarlo.
-- Hallazgo Alto de la revisión de seguridad (Codex, 8/10/2026): la versión de 005 comprobaba que
-- el llamante tuviera perfil activo, pero no que el lote fuera suyo; como la función es
-- SECURITY DEFINER, ni RLS ni la ausencia de UPDATE directo lo impedían.
-- PENDIENTE DE APROBACIÓN DE JUSTIN: no aplicar sin su visto bueno.

CREATE OR REPLACE FUNCTION public.cancelar_solicitud(p_id UUID)
RETURNS VARCHAR
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_estado VARCHAR;
    v_ejecucion UUID;
    v_solicitante UUID;
    v_usuario UUID := (SELECT auth.uid());
    v_rol TEXT := privado.rol_actual();
    v_resultado VARCHAR;
BEGIN
    IF v_rol IS NULL THEN
        RAISE EXCEPTION 'ROL_NO_AUTORIZADO' USING ERRCODE = '42501';
    END IF;
    SELECT estado, ejecucion_id, solicitado_por INTO v_estado, v_ejecucion, v_solicitante
      FROM public.solicitudes_lote WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SOLICITUD_NO_EXISTE';
    END IF;
    IF v_solicitante IS DISTINCT FROM v_usuario AND v_rol <> 'admin' THEN
        RAISE EXCEPTION 'SOLICITUD_DE_OTRO_USUARIO' USING ERRCODE = '42501';
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
-- CREATE OR REPLACE conserva propietario y permisos (EXECUTE solo para authenticated, desde 002).
