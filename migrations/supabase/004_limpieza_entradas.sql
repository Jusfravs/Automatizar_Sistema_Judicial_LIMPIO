-- Permite borrar un Excel de entrada propio que no llegó a tener solicitud
-- (por ejemplo, cuando el insert de la solicitud falla tras la subida).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'storage' AND tablename = 'objects'
           AND policyname = 'lotes_borrado_huerfanos'
    ) THEN
        CREATE POLICY lotes_borrado_huerfanos ON storage.objects FOR DELETE TO authenticated
            USING (
                bucket_id = 'lotes'
                AND (storage.foldername(name))[1] = 'entradas'
                AND owner_id = (SELECT auth.uid())::TEXT
                AND (SELECT privado.rol_actual()) IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM public.solicitudes_lote s
                     WHERE s.archivo_ruta = storage.objects.name
                )
            );
    END IF;
END;
$$;
