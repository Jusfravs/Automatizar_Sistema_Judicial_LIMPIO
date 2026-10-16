-- Alinea la revision de IA con ULTIMA = ultimo estado acreditado del arbol
-- y ACTUAL = fase operativa siguiente. No aplicar sin autorizacion.
-- Conserva permisos y search_path de la funcion ya desplegada.

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
    c_version_vigente CONSTANT VARCHAR := 'auditoria-nvidia-4';
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
