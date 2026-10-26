-- Configuración de IA del servicio, para mostrarla en Inicio (pedido de Justin, 25/10/2026).
-- Aditiva: el servicio anterior sigue latiendo sin escribirla. Aplicar ANTES de actualizar
-- el servicio, que ya la escribe. Solo modo, jerarquía, sombra, envío de texto, proveedor y
-- modelo (src/servicio_portal.py: resumen_config_ia); nunca claves.
-- La lectura ya está cubierta por el GRANT SELECT y la política de la 007.
ALTER TABLE public.servicio_latido ADD COLUMN IF NOT EXISTS config_ia JSONB;
