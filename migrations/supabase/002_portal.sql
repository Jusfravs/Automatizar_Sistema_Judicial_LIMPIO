-- Capa del portal web. Solo aplica sobre Supabase (usa auth y storage) y
-- requiere las migraciones del motor 001-003 ya aplicadas.

-- Funciones auxiliares fuera de los esquemas expuestos por la Data API
CREATE SCHEMA IF NOT EXISTS privado;
REVOKE ALL ON SCHEMA privado FROM PUBLIC;
GRANT USAGE ON SCHEMA privado TO authenticated;

-- ---------------------------------------------------------------------------
-- Catálogo de etapas y fases (mismos IDs que src/catalogo_procesal.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.catalogo_etapas (
    eta_id INTEGER PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS public.catalogo_fases (
    fas_id INTEGER PRIMARY KEY,
    eta_id INTEGER NOT NULL REFERENCES public.catalogo_etapas(eta_id),
    nombre VARCHAR(80) NOT NULL UNIQUE
);

INSERT INTO public.catalogo_etapas (eta_id, nombre) VALUES
    (10, '1 PRESENTACION Y CALIFICACION'),
    (11, '2 CITACION'),
    (12, '3 CONTESTACION'),
    (13, '4 AUDIENCIA'),
    (14, '5 SENTENCIA'),
    (15, '6 LIQUIDACION Y EMBARGO')
ON CONFLICT (eta_id) DO UPDATE SET nombre = EXCLUDED.nombre;

INSERT INTO public.catalogo_fases (fas_id, eta_id, nombre) VALUES
    (77, 10, '1.1 PRESENTAR DEMANDA'),
    (78, 10, '1.2 ACLARAR Y/O COMPLETAR DEMANDA'),
    (79, 10, '1.3 CALIFICACION'),
    (80, 11, '2.1 CITACION'),
    (81, 11, '2.2 CITACION POR PRENSA'),
    (82, 12, '3.1 CONTESTACION'),
    (83, 13, '4.1 FIJACION FECHA AUDIENCIA'),
    (84, 13, '4.2 AUDIENCIA'),
    (85, 14, '5.1 SENTENCIA EMITIDA POR EL JUEZ'),
    (86, 14, '5.2 APELACION'),
    (87, 14, '5.3 SENTENCIA EJECUTORIADA'),
    (88, 15, '6.1 LIQUIDACION PERITO LIQUIDADOR'),
    (89, 15, '6.2 MANDAMIENTO DE EJECUCION'),
    (90, 15, '6.3 EMBARGO'),
    (91, 15, '6.4 REMATE'),
    (92, 15, '6.5 CONGELAMIENTO DE CUENTAS')
ON CONFLICT (fas_id) DO UPDATE SET eta_id = EXCLUDED.eta_id, nombre = EXCLUDED.nombre;

CREATE OR REPLACE FUNCTION privado.par_etapa_fase_valido(p_eta_id INTEGER, p_fas_id INTEGER)
RETURNS BOOLEAN
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.catalogo_fases f
        WHERE f.fas_id = p_fas_id AND f.eta_id = p_eta_id
    );
$$;

-- ---------------------------------------------------------------------------
-- Perfiles y rol del usuario autenticado
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.perfiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nombre VARCHAR(120) NOT NULL DEFAULT '',
    rol VARCHAR(20) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_perfiles_rol CHECK (rol IN ('admin', 'gestor_lotes', 'gestor_casos'))
);

CREATE OR REPLACE FUNCTION privado.rol_actual()
RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT p.rol FROM public.perfiles p
    WHERE p.id = (SELECT auth.uid()) AND p.activo;
$$;

-- ---------------------------------------------------------------------------
-- Solicitudes de lote creadas desde el portal y atendidas por el servicio
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.solicitudes_lote (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    solicitado_por UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id),
    archivo_ruta TEXT NOT NULL,
    archivo_nombre VARCHAR(255) NOT NULL,
    hoja VARCHAR(120),
    filtros JSONB NOT NULL DEFAULT '{}'::jsonb,
    modo VARCHAR(12) NOT NULL,
    parametro VARCHAR(60),
    trabajadores INTEGER NOT NULL DEFAULT 1,
    continuar BOOLEAN NOT NULL DEFAULT FALSE,
    estado VARCHAR(12) NOT NULL DEFAULT 'SOLICITADA',
    perfil VARCHAR(120),
    ejecucion_id UUID REFERENCES public.ejecuciones(id) ON DELETE SET NULL,
    worker_host VARCHAR(120),
    mensaje TEXT,
    resultado_ruta TEXT,
    cancelar BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    tomado_en TIMESTAMPTZ,
    finalizado_en TIMESTAMPTZ,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_solicitud_modo CHECK (modo IN ('solo', 'lote', 'pendientes')),
    CONSTRAINT ck_solicitud_estado CHECK (estado IN (
        'SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO',
        'COMPLETADA', 'FALLIDA', 'RECHAZADA', 'CANCELADA'
    )),
    CONSTRAINT ck_solicitud_trabajadores CHECK (trabajadores BETWEEN 1 AND 4),
    CONSTRAINT ck_solicitud_parametro CHECK (
        CASE modo
            WHEN 'solo' THEN parametro IS NOT NULL AND length(trim(parametro)) > 0
                             AND trabajadores = 1
            WHEN 'lote' THEN CASE WHEN parametro ~ '^[0-9]{1,3}$'
                                  THEN parametro::INTEGER BETWEEN 2 AND 100
                                  ELSE FALSE END
            ELSE parametro IS NULL
        END
    ),
    CONSTRAINT ck_solicitud_archivo CHECK (archivo_ruta = 'entradas/' || id::TEXT || '.xlsx')
);

CREATE INDEX IF NOT EXISTS idx_solicitudes_estado
    ON public.solicitudes_lote(estado, creado_en);
CREATE INDEX IF NOT EXISTS idx_solicitudes_perfil
    ON public.solicitudes_lote(perfil);
CREATE INDEX IF NOT EXISTS idx_solicitudes_solicitante
    ON public.solicitudes_lote(solicitado_por);
CREATE INDEX IF NOT EXISTS idx_solicitudes_ejecucion
    ON public.solicitudes_lote(ejecucion_id);
CREATE INDEX IF NOT EXISTS idx_catalogo_fases_etapa
    ON public.catalogo_fases(eta_id);

CREATE OR REPLACE FUNCTION public.tocar_actualizado_en()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitudes_actualizado ON public.solicitudes_lote;
CREATE TRIGGER trg_solicitudes_actualizado
    BEFORE UPDATE ON public.solicitudes_lote
    FOR EACH ROW EXECUTE FUNCTION public.tocar_actualizado_en();

CREATE OR REPLACE FUNCTION public.cancelar_solicitud(p_id UUID)
RETURNS VARCHAR
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_estado VARCHAR;
BEGIN
    IF privado.rol_actual() IS NULL OR privado.rol_actual() NOT IN ('admin', 'gestor_lotes') THEN
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

-- ---------------------------------------------------------------------------
-- Revisión humana de auditorías IA desde el portal
-- ---------------------------------------------------------------------------
ALTER TABLE public.revisiones_ia
    ADD COLUMN IF NOT EXISTS revisado_por UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_revisiones_revisor
    ON public.revisiones_ia(revisado_por);

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
    IF privado.rol_actual() IS NULL OR privado.rol_actual() NOT IN ('admin', 'gestor_casos') THEN
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

-- ---------------------------------------------------------------------------
-- Privilegios: anon sin acceso; authenticated solo lectura salvo lo explícito
-- ---------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, PUBLIC;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA privado FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;

GRANT SELECT ON
    public.ejecuciones, public.cola_trabajo, public.resultados_ejecucion,
    public.eventos_auditoria, public.solicitudes_lote,
    public.expedientes, public.actuaciones, public.actuaciones_procesales,
    public.ejecuciones_inferencia, public.auditorias_ia, public.revisiones_ia,
    public.hitos_procesales, public.catalogo_etapas, public.catalogo_fases,
    public.perfiles,
    public.v_estado_ejecuciones, public.v_cola_trabajo, public.v_trabajadores_activos,
    public.v_resumen_fases, public.v_casos_revision_manual, public.v_reporte_ejecutivo
TO authenticated;
GRANT INSERT (id, archivo_ruta, archivo_nombre, hoja, filtros, modo, parametro,
              trabajadores, continuar)
    ON public.solicitudes_lote TO authenticated;

GRANT EXECUTE ON FUNCTION privado.rol_actual() TO authenticated;
GRANT EXECUTE ON FUNCTION public.cancelar_solicitud(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.registrar_revision(BIGINT, VARCHAR, INTEGER, INTEGER, TEXT)
    TO authenticated;

-- ---------------------------------------------------------------------------
-- Seguridad por filas
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_tabla TEXT;
BEGIN
    FOREACH v_tabla IN ARRAY ARRAY[
        'ejecuciones', 'expedientes', 'cola_trabajo', 'resultados_ejecucion',
        'actuaciones', 'eventos_auditoria', 'actuaciones_procesales',
        'ejecuciones_inferencia', 'auditorias_ia', 'revisiones_ia',
        'hitos_procesales', 'catalogo_etapas', 'catalogo_fases', 'perfiles',
        'solicitudes_lote', 'schema_migrations'
    ] LOOP
        IF to_regclass('public.' || v_tabla) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_tabla);
        END IF;
    END LOOP;
END;
$$;

-- Lectura por rol: gestor de lotes
DO $$
DECLARE
    v_tabla TEXT;
BEGIN
    FOREACH v_tabla IN ARRAY ARRAY[
        'ejecuciones', 'cola_trabajo', 'resultados_ejecucion', 'eventos_auditoria',
        'solicitudes_lote'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS lectura_gestor_lotes ON public.%I', v_tabla);
        EXECUTE format(
            'CREATE POLICY lectura_gestor_lotes ON public.%I FOR SELECT TO authenticated '
            'USING ((SELECT privado.rol_actual()) IN (''admin'', ''gestor_lotes''))',
            v_tabla
        );
    END LOOP;
END;
$$;

-- Lectura por rol: gestor de casos
DO $$
DECLARE
    v_tabla TEXT;
BEGIN
    FOREACH v_tabla IN ARRAY ARRAY[
        'expedientes', 'actuaciones', 'actuaciones_procesales',
        'ejecuciones_inferencia', 'auditorias_ia', 'revisiones_ia', 'hitos_procesales'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS lectura_gestor_casos ON public.%I', v_tabla);
        EXECUTE format(
            'CREATE POLICY lectura_gestor_casos ON public.%I FOR SELECT TO authenticated '
            'USING ((SELECT privado.rol_actual()) IN (''admin'', ''gestor_casos''))',
            v_tabla
        );
    END LOOP;
END;
$$;

DROP POLICY IF EXISTS lectura_catalogo ON public.catalogo_etapas;
CREATE POLICY lectura_catalogo ON public.catalogo_etapas FOR SELECT TO authenticated
    USING ((SELECT privado.rol_actual()) IS NOT NULL);
DROP POLICY IF EXISTS lectura_catalogo ON public.catalogo_fases;
CREATE POLICY lectura_catalogo ON public.catalogo_fases FOR SELECT TO authenticated
    USING ((SELECT privado.rol_actual()) IS NOT NULL);

DROP POLICY IF EXISTS lectura_propia ON public.perfiles;
CREATE POLICY lectura_propia ON public.perfiles FOR SELECT TO authenticated
    USING (id = (SELECT auth.uid()) OR (SELECT privado.rol_actual()) = 'admin');

DROP POLICY IF EXISTS alta_gestor_lotes ON public.solicitudes_lote;
CREATE POLICY alta_gestor_lotes ON public.solicitudes_lote FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT privado.rol_actual()) IN ('admin', 'gestor_lotes')
        AND solicitado_por = (SELECT auth.uid())
    );

-- Las vistas respetan el RLS de quien consulta
ALTER VIEW public.v_estado_ejecuciones SET (security_invoker = on);
ALTER VIEW public.v_cola_trabajo SET (security_invoker = on);
ALTER VIEW public.v_trabajadores_activos SET (security_invoker = on);
ALTER VIEW public.v_resumen_fases SET (security_invoker = on);
ALTER VIEW public.v_casos_revision_manual SET (security_invoker = on);
ALTER VIEW public.v_reporte_ejecutivo SET (security_invoker = on);

-- ---------------------------------------------------------------------------
-- Almacenamiento de Excel de entrada y resultados
-- ---------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'lotes', 'lotes', FALSE, 20971520,
    ARRAY['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
)
ON CONFLICT (id) DO UPDATE
    SET public = FALSE,
        file_size_limit = EXCLUDED.file_size_limit,
        allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS lotes_subida_entradas ON storage.objects;
CREATE POLICY lotes_subida_entradas ON storage.objects FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'lotes'
        AND (storage.foldername(name))[1] = 'entradas'
        AND (SELECT privado.rol_actual()) IN ('admin', 'gestor_lotes')
    );

DROP POLICY IF EXISTS lotes_lectura ON storage.objects;
CREATE POLICY lotes_lectura ON storage.objects FOR SELECT TO authenticated
    USING (
        bucket_id = 'lotes'
        AND (SELECT privado.rol_actual()) IN ('admin', 'gestor_lotes')
    );
