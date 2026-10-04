# src/limpieza.py
import os
import stat
import shutil
from src.logger_config import obtener_logger

logger = obtener_logger("Limpieza")

DIR_TEMP_HTMLS = "temp_htmls"
DB_HISTORICA = "estado_casos.db"

def _remove_readonly(func, path, excinfo):
    """Manejador para forzar eliminación de archivos con atributo de solo lectura en Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def ejecutar_limpieza(dir_temp=DIR_TEMP_HTMLS, db_historica=DB_HISTORICA):
    """
    Elimina de forma recursiva y segura el directorio temp_htmls/ conservando estado_casos.db.
    """
    print("=" * 60)
    print("[LIMPIEZA] - PURGA SEGURA DE ARTEFACTOS TEMPORALES")
    print("=" * 60)

    # 1. Purgar carpeta temp_htmls/
    if os.path.exists(dir_temp):
        try:
            archivos_count = len(os.listdir(dir_temp))
            shutil.rmtree(dir_temp, onerror=_remove_readonly)
            mensaje = f"[OK] Directorio '{dir_temp}/' eliminado correctamente ({archivos_count} archivos eliminados)."
            print(mensaje)
            logger.info(mensaje)
        except Exception as e:
            mensaje_err = f"[ERROR] No se pudo eliminar el directorio '{dir_temp}': {e}"
            print(mensaje_err)
            logger.error(mensaje_err)

    else:
        print(f"[*] El directorio '{dir_temp}/' no existe o ya fue purgado.")

    # 2. Confirmación de conservación de base de datos de estado
    if os.path.exists(db_historica):
        tamanio_mb = round(os.path.getsize(db_historica) / (1024 * 1024), 2)
        print(f"[PRESERVADO] Base de datos histórica '{db_historica}' conservada intacta ({tamanio_mb} MB).")
        logger.info(f"DB histórica preservada: {db_historica} ({tamanio_mb} MB)")
    else:
        print(f"[*] Base de datos histórica '{db_historica}' no encontrada.")

    print("=" * 60)
    print("[OK] Proceso de limpieza finalizado.")
    print("=" * 60)

if __name__ == "__main__":
    ejecutar_limpieza()
