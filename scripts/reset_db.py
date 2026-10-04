"""
Script de reset y recreación limpia de la base de datos estado_casos.db.
Crea un backup antes de recrear la base vacía.

Uso:
    python scripts/reset_db.py
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.gestor_cola import GestorCola


RUTA_DB = "estado_casos.db"
DIRECTORIO_BACKUPS = "backups"


def main():
    print("=" * 60)
    print("  RESET DE BASE DE DATOS SQLite - estado_casos.db")
    print("=" * 60)

    # 1. Backup
    if os.path.exists(RUTA_DB):
        os.makedirs(DIRECTORIO_BACKUPS, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_backup = os.path.join(DIRECTORIO_BACKUPS, f"estado_casos_{timestamp}.db")
        shutil.copy2(RUTA_DB, ruta_backup)
        print(f"[OK] Backup creado en: {ruta_backup}")

        # Estadísticas del backup
        conn = sqlite3.connect(RUTA_DB)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT estado, COUNT(*) FROM juicios GROUP BY estado")
            stats = dict(cursor.fetchall())
            print(f"[INFO] Estadísticas del backup: {stats}")
        except sqlite3.OperationalError:
            print("[INFO] No se pudieron leer estadísticas del backup (tabla inexistente).")
        conn.close()

        # Eliminar la base de datos existente
        os.remove(RUTA_DB)
        print(f"[OK] Base de datos '{RUTA_DB}' eliminada.")
    else:
        print(f"[INFO] No existe '{RUTA_DB}'. Se creará una nueva.")

    # 2. Recrear con esquema limpio
    cola = GestorCola(ruta_db=RUTA_DB)

    # 3. Verificar
    if cola.verificar_esquema():
        print("[OK] Base de datos recreada exitosamente con esquema limpio.")
    else:
        print("[ERROR] Fallo al recrear la base de datos.")
        sys.exit(1)

    # 4. Mostrar tablas
    conn = sqlite3.connect(RUTA_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tablas = [row[0] for row in cursor.fetchall()]
    conn.close()
    print(f"[OK] Tablas creadas: {tablas}")

    print("\n[INFO] Para repoblar la cola, ejecute:")
    print("    python main.py        (flujo asistido)")
    print("    python -m src.orquestador  (flujo headless)")
    print("=" * 60)


if __name__ == "__main__":
    main()
