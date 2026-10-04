"""Limpia un conjunto explícito de causas para volver a consultarlas en e-SATJE.

Conserva los datos base del reporte, respalda SQLite/CSV/Excel, elimina la
evidencia extraída anterior y devuelve las causas a PENDIENTE.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.gestor_casos import GestorCasos
from src.catalogo_procesal import CAMPOS_ID


CAUSAS_QUITO_AUDITADAS = (
    "17230-2016-17734", "17233-2017-00375", "17230-2015-17343",
    "17233-2024-01557", "17230-2016-03164", "17230-2016-05679",
    "17230-2016-04908", "17233-2024-05000", "17233-2020-01411",
    "17307-2014-0329", "17315-2024-00284", "17233-2025-11175",
    "17230-2016-11413", "17233-2022-05783", "17230-2015-15007",
    "17233-2018-03830", "17233-2017-02258", "17233-2022-06854",
    "17233-2024-07607", "17233-2019-00127", "17233-2025-09411",
    "17233-2025-09167", "17230-2015-13845", "17233-2025-06383",
    "17233-2017-00211", "17230-2015-13843", "17233-2025-11170",
    "17233-2025-11354", "17231-2025-00028",
)

CAMPOS_LIMPIAR = (
    # Salida vigente del reporte. No incluye columnas de cartera ni el
    # comentario base que entrega el Excel de origen.
    "HISTORIAL_ACTUACIONES", "FECHA INICIO JUICIO",
    "FECHA FIN ULTIMA FASE", "ULTIMA ETAPA", "ULTIMA FASE",
    "FECHA INICIO FASE ACTUAL", "ETAPA ACTUAL", "FASE ACTUAL",
    "DIAS TRANSCURRIDOS",
    "FECHA ULTIMA GESTION JUDICIAL", "ESTADO ULTIMA GESTION JUDICIAL",
    *CAMPOS_ID,
    # Salida legada que puede subsistir en el CSV de trabajo.
    "ETAPA_PROCESAL", "FASE_PROCESAL", "FECHA INICIAL FASE ACTUAL",
)


def limpiar_comentario_automatico(valor):
    """Elimina la marca creada por el bot, sin borrar una nota humana.

    ``main.py`` usa el prefijo ``REVISION MANUAL:`` para errores t\u00e9cnicos.
    Al devolver una causa a PENDIENTE esa marca deja de ser vigente; en
    cambio, cualquier comentario con otro origen se conserva.
    """
    texto = str(valor or "")
    return "" if texto.strip().upper().startswith("REVISION MANUAL:") else texto


def normalizar_causa(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())


def ruta_configurada(config_path, valor):
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else (config_path.parent / ruta).resolve()


def respaldar(ruta, directorio, marca):
    if not ruta.exists():
        raise FileNotFoundError(ruta)
    destino = directorio / f"{ruta.stem}_antes_reproceso_{marca}{ruta.suffix}"
    shutil.copy2(ruta, destino)
    return destino


def respaldar_si_existe(ruta, directorio, marca):
    """Respalda un artefacto opcional sin tratar su ausencia como un error."""
    return respaldar(ruta, directorio, marca) if ruta.exists() else None


def verificar_archivos_libres(rutas):
    """Falla antes de tocar SQLite si Excel mantiene un bloqueo exclusivo."""
    for ruta in rutas:
        try:
            with ruta.open("r+b"):
                pass
        except PermissionError as exc:
            raise PermissionError(
                f"ARCHIVO_BLOQUEADO_CIERRE_EXCEL_O_EDITOR:{ruta}"
            ) from exc


def _restaurar_comentario_base(repo, indices, causas):
    """Restaura el comentario original, nunca un ERROR escrito por el RPA."""
    if "COMENTARIO_ULTIMO" not in repo.df.columns:
        return

    base = repo._cargar_excel_robusto()
    if "NUMERO_JUICIO" not in base.columns:
        raise LookupError("COLUMNA_NUMERO_JUICIO_AUSENTE_ORIGEN")
    if "COMENTARIO_ULTIMO" not in base.columns:
        base["COMENTARIO_ULTIMO"] = ""

    causas_exactas = {str(causa).strip() for causa in causas}
    comentarios_base = {}
    for _, fila in base.iterrows():
        causa = str(fila.get("NUMERO_JUICIO") or "").strip()
        if causa in causas_exactas:
            comentarios_base.setdefault(causa, []).append(
                fila.get("COMENTARIO_ULTIMO", "")
            )

    faltantes = sorted(causas_exactas - set(comentarios_base))
    if faltantes:
        raise LookupError(f"CAUSAS_AUSENTES_ORIGEN:{faltantes}")

    ocurrencias = {}
    for indice in indices:
        causa = str(repo.df.at[indice, "NUMERO_JUICIO"]).strip()
        posicion = ocurrencias.get(causa, 0)
        comentarios = comentarios_base[causa]
        repo.df.at[indice, "COMENTARIO_ULTIMO"] = comentarios[
            min(posicion, len(comentarios) - 1)
        ]
        ocurrencias[causa] = posicion + 1


def _conectar_postgres(config):
    """Abre PostgreSQL solo cuando la configuración lo declara obligatorio."""
    config_db = config.get("base_de_datos", {})
    if config_db.get("motor") != "postgres":
        return None
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("POSTGRES_DRIVER_AUSENTE") from exc
    return psycopg2.connect(
        host=config_db.get("host", "localhost"),
        port=config_db.get("puerto", 5432),
        user=config_db.get("usuario", "postgres"),
        password=os.getenv(config_db.get("password_env", "POSTGRES_PASSWORD"), ""),
        dbname=config_db.get("nombre_db"),
        connect_timeout=10,
    )


def _respaldar_postgres(conexion, causas, destino):
    """Bloquea trabajos de las causas y respalda su fotografía y auditoría."""
    if conexion is None:
        return None
    respaldo = {}
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT numero_causa, estado FROM cola_trabajo "
            "WHERE numero_causa = ANY(%s) FOR UPDATE",
            (list(causas),),
        )
        en_proceso = [causa for causa, estado in cursor.fetchall()
                      if estado == "EN_PROCESO"]
        if en_proceso:
            raise RuntimeError(f"CAUSAS_EN_PROCESO_POSTGRES:{en_proceso}")
        for tabla in ("expedientes", "actuaciones", "eventos_auditoria"):
            cursor.execute(
                f"SELECT * FROM {tabla} WHERE numero_causa = ANY(%s)", (list(causas),)
            )
            columnas = [columna[0] for columna in cursor.description]
            respaldo[tabla] = [
                dict(zip(columnas, fila)) for fila in cursor.fetchall()
            ]
    destino.write_text(
        json.dumps(respaldo, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )
    return destino


def _limpiar_postgres(conexion, causas):
    """Reinicia la fotografía vigente sin borrar el expediente ni su auditoría."""
    if conexion is None:
        return {"habilitado": False, "expedientes": 0, "actuaciones": 0, "eventos": 0}
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT numero_causa FROM expedientes "
                "WHERE numero_causa = ANY(%s) FOR UPDATE",
                (list(causas),),
            )
            expedientes_presentes = len(cursor.fetchall())
            cursor.execute(
                "DELETE FROM actuaciones WHERE numero_causa = ANY(%s)", (list(causas),)
            )
            actuaciones = cursor.rowcount
            cursor.execute(
                "UPDATE expedientes SET estado='PENDIENTE', reintentos=0, "
            "ruta_html=NULL, actor=NULL, demandado=NULL, tipo_accion=NULL, "
            "fecha_inicio_juicio=NULL, eta_id_ultima_etapa=NULL, ultima_etapa=NULL, "
                "fas_id_ultima_fase=NULL, ultima_fase=NULL, "
                "fecha_fin_ultima_fase=NULL, eta_id_etapa_actual=NULL, "
                "etapa_actual=NULL, fas_id_fase_actual=NULL, fase_actual=NULL, "
                "fecha_inicio_fase_actual=NULL, mensaje_especial=NULL, "
                "total_actuaciones=0, datos_json=NULL, actualizado_en=CURRENT_TIMESTAMP "
                "WHERE expedientes.numero_causa = ANY(%s) "
                "AND expedientes.estado IS DISTINCT FROM 'EN_PROCESO' "
                "AND NOT EXISTS ("
                "SELECT 1 FROM cola_trabajo AS cola "
                "WHERE cola.numero_causa = expedientes.numero_causa "
                "AND cola.estado = 'EN_PROCESO')",
                (list(causas),),
            )
            expedientes = cursor.rowcount
            if expedientes != expedientes_presentes:
                raise RuntimeError("CAUSAS_EN_PROCESO_POSTGRES")
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    return {
        "habilitado": True,
        "expedientes": expedientes,
        "actuaciones": actuaciones,
        "eventos": 0,
    }


def _eliminar_evidencias(repo, causas_norm):
    """Elimina exclusivamente carpetas temporales de las causas reiniciadas."""
    raiz = Path(repo.ruta_csv).resolve().parent / "temp_htmls"
    eliminadas = []
    bloqueadas = []
    for causa_norm in causas_norm:
        destino = raiz / causa_norm
        if destino.is_dir():
            try:
                shutil.rmtree(destino)
                eliminadas.append(str(destino.resolve()))
            except PermissionError:
                # El reinicio de datos no debe quedar a medias por una ACL de
                # Windows sobre archivos temporales. Se informa la ruta para
                # que el propietario pueda retirarla sin ampliar el alcance.
                bloqueadas.append(str(destino.resolve()))
    return eliminadas, bloqueadas


def _limpiar_lista_fallidos(ruta, causas_norm):
    if not ruta.exists():
        return 0
    existentes = ruta.read_text(encoding="utf-8").splitlines()
    conservadas = [
        causa for causa in existentes if normalizar_causa(causa) not in causas_norm
    ]
    ruta.write_text(
        "".join(f"{causa}\n" for causa in conservadas), encoding="utf-8"
    )
    return len(existentes) - len(conservadas)


def limpiar(config_path, causas):
    config_path = Path(config_path).resolve()
    repo = GestorCasos(str(config_path))
    rutas = repo.config.get("rutas", {})
    ruta_db = ruta_configurada(config_path, rutas.get("archivo_db", "estado_casos.db"))
    ruta_csv = Path(repo.ruta_csv).resolve()
    ruta_excel = Path(repo.ruta_final).resolve()
    ruta_fallidos = ruta_configurada(
        config_path,
        rutas.get("archivo_casos_fallidos", str(RAIZ / "data" / "casos_fallidos.txt")),
    )
    causas = tuple(dict.fromkeys(str(c).strip() for c in causas if str(c).strip()))
    causas_norm = {normalizar_causa(c): c for c in causas}

    if len(causas_norm) != len(causas):
        raise ValueError("CAUSAS_DUPLICADAS_O_INVALIDAS")
    directorio = ruta_db.parent / "backups"
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    directorio.mkdir(parents=True, exist_ok=True)
    verificar_archivos_libres((ruta_csv, ruta_excel, ruta_fallidos))

    conexion = sqlite3.connect(ruta_db, timeout=30.0)
    conexion_pg = None
    sqlite_confirmado = False
    postgres_confirmado = False
    try:
        conexion_pg = _conectar_postgres(repo.config)
        placeholders = ",".join("?" for _ in causas)
        filas = conexion.execute(
            f"SELECT numero_causa, estado FROM juicios WHERE numero_causa IN ({placeholders})",
            causas,
        ).fetchall()
        encontradas = {normalizar_causa(c): (c, estado) for c, estado in filas}
        faltantes = sorted(set(causas_norm) - set(encontradas))
        if faltantes:
            raise LookupError(f"CAUSAS_AUSENTES_SQLITE:{faltantes}")
        en_proceso = [c for c, estado in encontradas.values() if estado == "EN_PROCESO"]
        if en_proceso:
            raise RuntimeError(f"CAUSAS_EN_PROCESO:{en_proceso}")

        respaldos = [respaldar(ruta_csv, directorio, marca), respaldar(ruta_excel, directorio, marca)]
        respaldo_fallidos = respaldar_si_existe(ruta_fallidos, directorio, marca)
        if respaldo_fallidos:
            respaldos.append(respaldo_fallidos)
        respaldo_db = directorio / f"{ruta_db.stem}_antes_reproceso_{marca}.db"
        copia = sqlite3.connect(respaldo_db)
        try:
            conexion.backup(copia)
        finally:
            copia.close()
        respaldos.append(respaldo_db)
        respaldo_pg = _respaldar_postgres(
            conexion_pg,
            causas,
            directorio / f"postgres_antes_reproceso_{marca}.json",
        )
        if respaldo_pg:
            respaldos.append(respaldo_pg)

        mascara = repo.df["NUMERO_JUICIO"].map(normalizar_causa)
        indices = repo.df.index[mascara.isin(causas_norm)]
        causas_en_csv = set(mascara.loc[indices])
        faltantes_csv = sorted(set(causas_norm) - causas_en_csv)
        if faltantes_csv:
            raise LookupError(f"CAUSAS_AUSENTES_CSV:{faltantes_csv}")
        for indice in indices:
            for campo in CAMPOS_LIMPIAR:
                if campo in repo.df.columns:
                    valor_vacio = "" if repo.df[campo].dtype == object else None
                    repo.df.at[indice, campo] = valor_vacio
            if "COMENTARIO_ULTIMO" in repo.df.columns:
                repo.df.at[indice, "COMENTARIO_ULTIMO"] = (
                    limpiar_comentario_automatico(
                        repo.df.at[indice, "COMENTARIO_ULTIMO"]
                    )
                )

        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute(
            f"DELETE FROM resultados_expediente WHERE numero_causa IN ({placeholders})",
            causas,
        )
        conexion.execute(
            f"DELETE FROM eventos_extraccion WHERE numero_causa IN ({placeholders})",
            causas,
        )
        conexion.execute(
            f"UPDATE juicios SET estado='PENDIENTE', reintentos=0, ruta_html=NULL "
            f"WHERE numero_causa IN ({placeholders})",
            causas,
        )

        if not repo.guardar():
            raise RuntimeError("PERSISTENCIA_ERROR:CSV")
        repo.exportar_excel()
        conexion.commit()
        sqlite_confirmado = True
        postgres = _limpiar_postgres(conexion_pg, causas)
        postgres_confirmado = True
        evidencias_eliminadas, evidencias_bloqueadas = _eliminar_evidencias(
            repo, causas_norm
        )
        fallidos_retirados = _limpiar_lista_fallidos(ruta_fallidos, causas_norm)
    except Exception:
        conexion.rollback()
        if not postgres_confirmado:
            if sqlite_confirmado:
                respaldo_origen = sqlite3.connect(respaldo_db)
                try:
                    respaldo_origen.backup(conexion)
                finally:
                    respaldo_origen.close()
            # Restaurar los formatos solo si PostgreSQL no confirmó el cambio.
            for respaldo in locals().get("respaldos", []):
                if respaldo.suffix.lower() in {".csv", ".xlsx"}:
                    destino = ruta_csv if respaldo.suffix.lower() == ".csv" else ruta_excel
                    shutil.copy2(respaldo, destino)
        raise
    finally:
        conexion.close()
        if conexion_pg is not None:
            conexion_pg.close()

    return {
        "causas_limpiadas": len(causas),
        "estado_nuevo": "PENDIENTE",
        "resultados_sqlite_eliminados": len(causas),
        "postgres": postgres,
        "evidencias_eliminadas": len(evidencias_eliminadas),
        "evidencias_bloqueadas": evidencias_bloqueadas,
        "fallidos_retirados": fallidos_retirados,
        "respaldos": [str(r.resolve()) for r in respaldos],
        "sqlite": str(ruta_db),
        "csv": str(ruta_csv),
        "excel": str(ruta_excel),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--causa", action="append", dest="causas")
    parser.add_argument("--auditoria-quito", action="store_true")
    args = parser.parse_args()
    causas = CAUSAS_QUITO_AUDITADAS if args.auditoria_quito else (args.causas or [])
    if not causas:
        parser.error("indique --auditoria-quito o al menos un --causa")
    print(json.dumps(limpiar(args.config, causas), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
