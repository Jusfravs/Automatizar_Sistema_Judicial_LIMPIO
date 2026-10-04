import asyncio
import os
import sys
from pathlib import Path
from src.logger_config import obtener_logger

logger = obtener_logger("AntigravityAdapter")

ANTIGRAVITY_ROOT = Path(
    os.environ.get("ANTIGRAVITY_CLI_PATH", "C:/Users/HP/OneDrive/Desktop/antigravity_cli")
).resolve()

if not ANTIGRAVITY_ROOT.exists():
    # Intento ruta relativa si ambos proyectos son hermanos en el mismo directorio padre.
    posible_root = Path(__file__).resolve().parents[1].parent / "antigravity_cli"
    if posible_root.exists():
        ANTIGRAVITY_ROOT = posible_root.resolve()

ANTIGRAVITY_AVAILABLE = False
ANTIGRAVITY_IMPORT_ERROR = None

if ANTIGRAVITY_ROOT.exists():
    if str(ANTIGRAVITY_ROOT) not in sys.path:
        sys.path.insert(0, str(ANTIGRAVITY_ROOT))

    try:
        from skills import extraer_via_red, normalizar_columnas
        ANTIGRAVITY_AVAILABLE = True
        logger.info("Repositorio de skills de Antigravity cargado con éxito desde: %s", ANTIGRAVITY_ROOT)
    except Exception as exc:
        ANTIGRAVITY_IMPORT_ERROR = exc
        logger.error(
            "Error al importar 'skills' desde el repositorio '%s': %s",
            ANTIGRAVITY_ROOT,
            exc,
            exc_info=True,
        )
else:
    ANTIGRAVITY_IMPORT_ERROR = ImportError(
        f"No se encontró la carpeta del repositorio de skills en: '{ANTIGRAVITY_ROOT}'. Configure ANTIGRAVITY_CLI_PATH."
    )
    logger.error("Ruta del repositorio de skills no encontrada: %s", ANTIGRAVITY_ROOT)


def _raise_import_error():
    if ANTIGRAVITY_IMPORT_ERROR is not None:
        raise ANTIGRAVITY_IMPORT_ERROR


def extraer_y_normalizar(numero_juicio: str, timeout_ms: int = 15000):
    """
    Extrae los datos de la causa desde E-SATJE usando el motor antigravity y normaliza el DataFrame.
    Si ocurre un error durante la ejecución, se registra en los logs con traceback detallado sin omitirlo.
    """
    if not numero_juicio:
        return None

    if not ANTIGRAVITY_AVAILABLE:
        logger.error("No se puede extraer la causa '%s' porque el repositorio de skills no está disponible.", numero_juicio)
        _raise_import_error()

    try:
        logger.info("Ejecutando extracción vía red para causa '%s' usando skills de Antigravity...", numero_juicio)
        df = asyncio.run(extraer_via_red(numero_juicio, timeout_ms=timeout_ms))
        if df is None or df.empty:
            logger.warning("El motor antigravity devolvió un DataFrame vacío o Nulo para la causa '%s'.", numero_juicio)
            return None

        df_normalizado = normalizar_columnas(df)
        return df_normalizado
    except Exception as exc:
        logger.exception("Excepción durante la extracción de causa '%s' en antigravity_cli: %s", numero_juicio, exc)
        raise exc


def extraer_y_normalizar_dict(numero_juicio: str, timeout_ms: int = 15000):
    """
    Retorna el primer registro extraído como dict, o None si no hay datos.
    Registra cualquier fallo explícitamente en el log de auditoría.
    """
    try:
        df = extraer_y_normalizar(numero_juicio, timeout_ms=timeout_ms)
    except Exception as exc:
        logger.error("Fallo reportado al extraer dict para causa '%s': %s", numero_juicio, exc)
        raise exc

    if df is None or df.empty:
        return None

    records = df.to_dict(orient="records")
    return records[0] if records else None
