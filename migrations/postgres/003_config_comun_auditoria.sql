-- Registra la versión de reglas usada por cada ejecución de la consola.
ALTER TABLE ejecuciones
    ADD COLUMN IF NOT EXISTS config_sha256 CHAR(64);
