# src/logger_config.py
import logging
import multiprocessing
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_log_base = Path(os.environ.get("SISTEMA_JUDICIAL_LOG_FILE", "ejecucion_produccion.log"))
if os.environ.get("SISTEMA_JUDICIAL_SERVICE_MODE") == "1" and multiprocessing.current_process().name != "MainProcess":
    LOG_FILE = str(_log_base.with_name(f"{_log_base.stem}.worker-{os.getpid()}{_log_base.suffix}"))
else:
    LOG_FILE = str(_log_base)
_HANDLER_TAG = "_casos_judiciales_handler"
_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"


def configurar_logging(ruta_archivo=LOG_FILE, consola=True, nivel=logging.INFO, reemplazar=False):
    """Configura logging de proceso de forma explícita y sin efectos al importar."""
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    propios = [handler for handler in raiz.handlers if getattr(handler, _HANDLER_TAG, False)]
    if reemplazar:
        for handler in propios:
            raiz.removeHandler(handler)
            handler.close()
        propios = []
    if propios:
        return raiz

    formatter = logging.Formatter(fmt=_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    if ruta_archivo:
        Path(ruta_archivo).parent.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            ruta_archivo, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        archivo.setLevel(nivel)
        archivo.setFormatter(formatter)
        setattr(archivo, _HANDLER_TAG, True)
        raiz.addHandler(archivo)
    if consola:
        salida = logging.StreamHandler(sys.stdout)
        salida.setLevel(nivel)
        salida.setFormatter(formatter)
        setattr(salida, _HANDLER_TAG, True)
        raiz.addHandler(salida)
    return raiz


def obtener_logger(nombre_modulo):
    """Devuelve un logger nominal; la aplicación decide sus destinos."""
    return logging.getLogger(nombre_modulo)
