-- Acceso unificado: todo usuario activo del portal opera lotes y casos.
-- El rol admin se conserva para la gestión de usuarios.

ALTER TABLE public.perfiles DROP CONSTRAINT IF EXISTS ck_perfiles_rol;
UPDATE public.perfiles SET rol = 'usuario' WHERE rol IN ('gestor_lotes', 'gestor_casos');
ALTER TABLE public.perfiles
    ADD CONSTRAINT ck_perfiles_rol CHECK (rol IN ('admin', 'usuario'));
ALTER TABLE public.perfiles ALTER COLUMN rol SET DEFAULT 'usuario';

DO $$
DECLARE
    v_tabla TEXT;
BEGIN
    FOREACH v_tabla IN ARRAY ARRAY[
        'ejecuciones', 'cola_trabajo', 'resultados_ejecucion', 'eventos_auditoria',
        'solicitudes_lote', 'expedientes', 'actuaciones', 'actuaciones_procesales',
        'ejecuciones_inferencia', 'auditorias_ia', 'revisiones_ia', 'hitos_procesales'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS lectura_gestor_lotes ON public.%I', v_tabla);
        EXECUTE format('DROP POLICY IF EXISTS lectura_gestor_casos ON public.%I', v_tabla);
        EXECUTE format('DROP POLICY IF EXISTS lectura_usuarios ON public.%I', v_tabla);
        EXECUTE format(
            'CREATE POLICY lectura_usuarios ON public.%I FOR SELECT TO authenticated '
            'USING ((SELECT privado.rol_actual()) IS NOT NULL)',
            v_tabla
        );
    END LOOP;
END;
$$;

DROP POLICY IF EXISTS alta_gestor_lotes ON public.solicitudes_lote;
DROP POLICY IF EXISTS alta_usuarios ON public.solicitudes_lote;
CREATE POLICY alta_usuarios ON public.solicitudes_lote FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT privado.rol_actual()) IS NOT NULL
        AND solicitado_por = (SELECT auth.uid())
    );

DROP POLICY IF EXISTS lotes_subida_entradas ON storage.objects;
CREATE POLICY lotes_subida_entradas ON storage.objects FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'lotes'
        AND (storage.foldername(name))[1] = 'entradas'
        AND (SELECT privado.rol_actual()) IS NOT NULL
    );

DROP POLICY IF EXISTS lotes_lectura ON storage.objects;
CREATE POLICY lotes_lectura ON storage.objects FOR SELECT TO authenticated
    USING (
        bucket_id = 'lotes'
        AND (SELECT privado.rol_actual()) IS NOT NULL
    );

CREATE OR REPLACE FUNCTION public.cancelar_solicitud(p_id UUID)
RETURNS VARCHAR
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_estado VARCHAR;
BEGIN
    IF privado.rol_actual() IS NULL THEN
        RAISE EXCEPTION 'ROL_NO_AUTORIZADO' USING ERRCODE = '42501';
    END IF;
    SELECT estado INTO v_estado FROM public.solicitudes_lote WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SOLICITUD_NO_EXISTE';
    END IF;
    IF v_estado = 'SOLICITADA' THEN
        UPDATE public.solicitudes_lote
           SET estado = 'CANCELADA', cancelar = TRUE, finalizado_en = now(),
               mensaje = 'Cancelada antes de iniciar.'
         WHERE id = p_id;
        RETURN 'CANCELADA';
    ELSIF v_estado IN ('TOMADA', 'PREPARANDO', 'EN_CURSO') THEN
        UPDATE public.solicitudes_lote SET cancelar = TRUE WHERE id = p_id;
        RETURN 'CANCELACION_SOLICITADA';
    END IF;
    RAISE EXCEPTION 'SOLICITUD_FINALIZADA';
END;
$$;

-- Replica las reglas de scripts/importar_revision_ia.py. La versión vigente
-- debe coincidir con VERSION_PROMPT de src/proveedor_nvidia.py.
CREATE OR REPLACE FUNCTION public.registrar_revision(
    p_auditoria_id BIGINT,
    p_decision VARCHAR,
    p_eta_id INTEGER DEFAULT NULL,
    p_fas_id INTEGER DEFAULT NULL,
    p_observacion TEXT DEFAULT NULL
)
RETURNS VARCHAR
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    c_version_vigente CONSTANT VARCHAR := 'auditoria-nvidia-3';
    v_decision VARCHAR := upper(trim(coalesce(p_decision, '')));
    v_observacion TEXT := trim(coalesce(p_observacion, ''));
    v_causa VARCHAR;
    v_estado_auditoria VARCHAR;
    v_propuesta JSONB;
    v_estado_revision VARCHAR;
    v_ultimo BIGINT;
    v_version TEXT;
    v_actual JSONB;
    v_ref TEXT;
BEGIN
    IF privado.rol_actual() IS NULL THEN
        RAISE EXCEPTION 'ROL_NO_AUTORIZADO' USING ERRCODE = '42501';
    END IF;
    IF v_decision NOT IN ('ACEPTAR_SISTEMA', 'ACEPTAR_IA', 'CORREGIR_MANUALMENTE', 'POSPONER') THEN
        RAISE EXCEPTION 'DECISION_INVALIDA';
    END IF;

    SELECT a.numero_causa, a.estado, a.decision_json, r.estado
      INTO v_causa, v_estado_auditoria, v_propuesta, v_estado_revision
      FROM public.auditorias_ia a
      JOIN public.revisiones_ia r ON r.auditoria_id = a.id
     WHERE a.id = p_auditoria_id
       FOR UPDATE OF r;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'REVISION_OBSOLETA';
    END IF;
    SELECT max(id) INTO v_ultimo FROM public.auditorias_ia WHERE numero_causa = v_causa;
    IF v_ultimo <> p_auditoria_id
       OR v_estado_auditoria NOT IN ('REVISION', 'INSUFICIENTE')
       OR v_estado_revision <> 'PENDIENTE' THEN
        RAISE EXCEPTION 'REVISION_OBSOLETA';
    END IF;
    v_propuesta := coalesce(v_propuesta, '{}'::jsonb);
    v_version := coalesce(v_propuesta ->> 'version_prompt', '');
    IF v_version LIKE 'auditoria-nvidia-%' AND v_version <> c_version_vigente THEN
        RAISE EXCEPTION 'REVISION_OBSOLETA';
    END IF;

    IF v_decision = 'ACEPTAR_IA' THEN
        v_actual := coalesce(v_propuesta -> 'estado_actual', '{}'::jsonb);
        IF v_propuesta ->> 'decision' IS DISTINCT FROM 'CORREGIR'
           OR jsonb_typeof(v_actual -> 'eta_id') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_actual -> 'fas_id') IS DISTINCT FROM 'number'
           OR NOT privado.par_etapa_fase_valido(
                  (v_actual ->> 'eta_id')::INTEGER, (v_actual ->> 'fas_id')::INTEGER) THEN
            RAISE EXCEPTION 'PROPUESTA_IA_INVALIDA';
        END IF;
        IF jsonb_typeof(v_propuesta -> 'evidencias') IS DISTINCT FROM 'array'
           OR jsonb_array_length(v_propuesta -> 'evidencias') = 0 THEN
            RAISE EXCEPTION 'EVIDENCIA_INVALIDA';
        END IF;
        FOR v_ref IN SELECT jsonb_array_elements_text(v_propuesta -> 'evidencias') LOOP
            IF NOT EXISTS (
                SELECT 1 FROM public.actuaciones_procesales
                 WHERE actuacion_id = v_ref AND numero_causa = v_causa
            ) THEN
                RAISE EXCEPTION 'EVIDENCIA_INVALIDA';
            END IF;
        END LOOP;
    END IF;

    IF v_decision = 'CORREGIR_MANUALMENTE' THEN
        IF NOT coalesce(privado.par_etapa_fase_valido(p_eta_id, p_fas_id), FALSE)
           OR v_observacion = '' THEN
            RAISE EXCEPTION 'CORRECCION_MANUAL_INVALIDA';
        END IF;
    ELSIF p_eta_id IS NOT NULL OR p_fas_id IS NOT NULL THEN
        RAISE EXCEPTION 'IDS_MANUALES_INESPERADOS';
    END IF;

    UPDATE public.revisiones_ia
       SET estado = CASE WHEN v_decision = 'POSPONER' THEN 'PENDIENTE' ELSE 'RESUELTA' END,
           decision_humana = v_decision,
           eta_id_manual = p_eta_id,
           fas_id_manual = p_fas_id,
           observacion = nullif(v_observacion, ''),
           revisado_en = CASE WHEN v_decision = 'POSPONER' THEN NULL ELSE now() END,
           revisado_por = (SELECT auth.uid())
     WHERE auditoria_id = p_auditoria_id AND estado = 'PENDIENTE';

    RETURN CASE WHEN v_decision = 'POSPONER' THEN 'PENDIENTE' ELSE 'RESUELTA' END;
END;
$$;
