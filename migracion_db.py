# migracion_db.py
"""
Script de migración y verificación para la base de datos SQLite estado_casos.db.
Garantiza el esquema completo (tablas e índices) y recupera registros huérfanos.

Uso: python migracion_db.py
"""
import os
import shutil
import sqlite3
from datetime import datetime
from src.gestor_cola import GestorCola


RUTA_DB = "estado_casos.db"


def backup_db(ruta_db):
    """Crea un respaldo de la base de datos antes de migrar."""
    if not os.path.exists(ruta_db):
        print(f"[!] No existe la base de datos en '{ruta_db}'. Se creará una nueva.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_backup = f"{ruta_db}.backup_{timestamp}"
    shutil.copy2(ruta_db, ruta_backup)
    print(f"[OK] Backup creado: {ruta_backup}")
    return ruta_backup


def migrar(ruta_db=RUTA_DB):
    """Ejecuta la migración completa delegando en GestorCola."""
    print("=" * 60)
    print("  MIGRACIÓN DE BASE DE DATOS SQLite - estado_casos.db")
    print("=" * 60)

    # 1. Backup
    backup_db(ruta_db)

    # 2. Inicializar esquema mediante GestorCola (crea tablas e índices automáticamente)
    print("\n--- Verificando y actualizando esquema ---")
    cola = GestorCola(ruta_db=ruta_db)
    if cola.verificar_esquema():
        print("[OK] Tablas e índices verificados correctamente.")
    else:
        print("[ERROR] Fallo al verificar el esquema de la base de datos.")

    # 3. Recuperar registros huérfanos (EN_PROCESO → PENDIENTE)
    print("\n--- Recuperando registros huérfanos ---")
    huerfanos_recuperados = cola.recuperar_huerfanos()
    if huerfanos_recuperados > 0:
        print(f"[OK] {huerfanos_recuperados} registro(s) huérfano(s) recuperado(s) a 'PENDIENTE'.")
    else:
        print("[OK] No hay registros huérfanos en 'EN_PROCESO'.")

    # 4. Estadísticas finales
    print("\n--- Estadísticas post-migración ---")
    stats = cola.obtener_estadisticas()
    for estado, cantidad in stats.items():
        print(f"  {estado}: {cantidad}")

    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM resultados_expediente")
    total_resultados = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM eventos_extraccion")
    total_eventos = cursor.fetchone()[0]
    conn.close()

    print(f"  Resultados guardados: {total_resultados}")
    print(f"  Eventos registrados: {total_eventos}")
    print("\n[OK] ¡Migración completada exitosamente!")


if __name__ == "__main__":
    migrar()
