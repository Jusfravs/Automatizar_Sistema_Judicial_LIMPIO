"""Contratos del reproceso; todas las causas y bases de prueba son sintéticas."""

import copy
import json
import os
import re
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts import preparar_reproceso_causas as reproceso
from src.catalogo_procesal import CAMPOS_ID


CAUSA = "99999-2099-00001"


class _CursorPostgres:
    """Aplica solo el SQL necesario para comprobar conservación de filas."""

    def __init__(self, conexion):
        self.conexion = conexion
        self.rowcount = 0
        self.description = None
        self.filas = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, parametros=()):
        texto = " ".join(sql.lower().split())
        tabla = re.search(r"\b(?:from|update)\s+(\w+)", texto)
        if texto.startswith("select "):
            nombre = tabla.group(1)
            filas = [fila for fila in self.conexion.trabajo[nombre]
                     if fila["numero_causa"] in parametros[0]]
            columnas = list(filas[0]) if filas else ["numero_causa"]
            self.description = [(columna,) for columna in columnas]
            self.filas = [tuple(fila.get(columna) for columna in columnas)
                          for fila in filas]
            return
        if texto.startswith("delete "):
            nombre = tabla.group(1)
            if nombre != "actuaciones":
                raise AssertionError(f"REPROCESO_BORRA_HISTORIAL:{nombre}")
            anteriores = self.conexion.trabajo[nombre]
            self.conexion.trabajo[nombre] = [
                fila for fila in anteriores if fila["numero_causa"] not in parametros[0]
            ]
            self.rowcount = len(anteriores) - len(self.conexion.trabajo[nombre])
            return
        if texto.startswith("update expedientes "):
            valores = texto + " " + " ".join(map(str, parametros)).lower()
            if "estado" not in texto or "pendiente" not in valores:
                raise AssertionError("FOTOGRAFIA_SIN_ESTADO_PENDIENTE")
            if "reintentos" not in texto or "ruta_html" not in texto:
                raise AssertionError("FOTOGRAFIA_SIN_REINICIO_OPERATIVO")
            if any(campo not in texto for campo in (
                "ultima_fase", "datos_json", "actor", "demandado",
                "tipo_accion", "fecha_inicio_juicio",
            )):
                raise AssertionError("FOTOGRAFIA_PROCESAL_NO_LIMPIADA")
            for fila in self.conexion.trabajo["expedientes"]:
                if fila["numero_causa"] == CAUSA:
                    fila.update(estado="PENDIENTE", reintentos=0,
                                ruta_html=None, ultima_fase=None, datos_json=None,
                                actor=None, demandado=None, tipo_accion=None,
                                fecha_inicio_juicio=None)
                    self.rowcount = 1
            return
        raise AssertionError(f"SQL_INESPERADO_EN_REPROCESO:{texto}")

    def fetchall(self):
        return self.filas


class _PostgresSintetico:
    def __init__(self):
        self.estado = {
            "expedientes": [dict(numero_causa=CAUSA, estado="PROCESADO",
                                 reintentos=2, ruta_html="antiguo.html",
                                 ultima_fase="3.1", datos_json={"fase": "3.1"},
                                 actor="ACTOR SINTETICO", demandado="DEMANDADO SINTETICO",
                                 tipo_accion="ACCION SINTETICA",
                                 fecha_inicio_juicio="01/01/2099")],
            "actuaciones": [dict(numero_causa=CAUSA, tipo_actuacion="LEGADA")],
            "eventos_auditoria": [dict(numero_causa=CAUSA, tipo_evento="EXTRACCION")],
            "actuaciones_procesales": [dict(numero_causa=CAUSA, id=1)],
            "ejecuciones_inferencia": [dict(numero_causa=CAUSA, id=2)],
            "auditorias_ia": [dict(numero_causa=CAUSA, id=3)],
            "revisiones_ia": [dict(numero_causa=CAUSA, id=4)],
            "hitos_procesales": [dict(numero_causa=CAUSA, id=5)],
        }
        self.trabajo = copy.deepcopy(self.estado)

    def cursor(self):
        return _CursorPostgres(self)

    def commit(self):
        self.estado = copy.deepcopy(self.trabajo)

    def rollback(self):
        self.trabajo = copy.deepcopy(self.estado)


class _GestorSintetico:
    def __init__(self, raiz):
        self.ruta_csv = str(raiz / "reporte.csv")
        self.ruta_final = str(raiz / "reporte.xlsx")
        self.config = {"rutas": {
            "archivo_db": str(raiz / "estado.db"),
            "archivo_casos_fallidos": str(raiz / "fallidos.txt"),
        }}
        self.df = pd.read_csv(self.ruta_csv, dtype=str).fillna("")

    def guardar(self):
        self.df.to_csv(self.ruta_csv, index=False)
        return True

    def exportar_excel(self):
        self.df.to_excel(self.ruta_final, index=False)

    def _cargar_excel_robusto(self):
        return pd.DataFrame({"NUMERO_JUICIO": [CAUSA],
                             "COMENTARIO_ULTIMO": ["nota humana"]})


class ReprocesoPostgresTests(unittest.TestCase):
    def test_reproceso_vacia_ultima_gestion_y_ids_en_csv_y_excel(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            config = raiz / "config.json"
            config.write_text("{}", encoding="utf-8")
            csv = raiz / "reporte.csv"
            excel = raiz / "reporte.xlsx"
            sqlite = raiz / "estado.db"
            (raiz / "fallidos.txt").write_text("", encoding="utf-8")
            originales = {
                "NUMERO_JUICIO": [CAUSA],
                "HISTORIAL_ACTUACIONES": ["actuación anterior"],
                "FECHA ULTIMA GESTION JUDICIAL": ["24/09/2099"],
                "ESTADO ULTIMA GESTION JUDICIAL": ["AUTO DE SUSTANCIACIÓN"],
                "COMENTARIO_ULTIMO": ["nota humana"],
            }
            for posicion, campo in enumerate(CAMPOS_ID, start=1):
                originales[campo] = [posicion]
            pd.DataFrame(originales).to_csv(csv, index=False)
            pd.DataFrame(originales).to_excel(excel, index=False)
            with closing(sqlite3.connect(sqlite)) as conexion, conexion:
                conexion.execute("CREATE TABLE juicios (numero_causa TEXT PRIMARY KEY, estado TEXT, reintentos INTEGER, ruta_html TEXT)")
                conexion.execute("CREATE TABLE resultados_expediente (numero_causa TEXT, datos_json TEXT)")
                conexion.execute("CREATE TABLE eventos_extraccion (numero_causa TEXT, detalle TEXT)")
                conexion.execute("INSERT INTO juicios VALUES (?, 'PROCESADO', 1, 'antiguo.html')", (CAUSA,))
            gestor = _GestorSintetico(raiz)

            with patch.object(reproceso, "GestorCasos", return_value=gestor), \
                 patch.object(reproceso, "_conectar_postgres", return_value=None):
                reproceso.limpiar(config, [CAUSA])

            campos_obsoletos = (
                "FECHA ULTIMA GESTION JUDICIAL",
                "ESTADO ULTIMA GESTION JUDICIAL",
                *CAMPOS_ID,
            )
            for ruta, lector in ((csv, pd.read_csv), (excel, pd.read_excel)):
                reporte = lector(ruta)
                with self.subTest(formato=ruta.suffix):
                    self.assertEqual(len(reporte), 1)
                    self.assertEqual(reporte.loc[0, "NUMERO_JUICIO"], CAUSA)
                    self.assertEqual(reporte.loc[0, "COMENTARIO_ULTIMO"], "nota humana")
                    for campo in campos_obsoletos:
                        valor = reporte.loc[0, campo]
                        self.assertTrue(pd.isna(valor) or str(valor).strip() == "",
                                        f"{campo} conserva un valor obsoleto: {valor!r}")

    def test_con_historial_ia_conserva_expediente_y_auditoria(self):
        postgres = _PostgresSintetico()
        historial_antes = {
            nombre: copy.deepcopy(postgres.estado[nombre])
            for nombre in ("eventos_auditoria", "actuaciones_procesales",
                           "ejecuciones_inferencia", "auditorias_ia",
                           "revisiones_ia", "hitos_procesales")
        }

        resultado = reproceso._limpiar_postgres(postgres, [CAUSA])

        self.assertTrue(resultado["habilitado"])
        self.assertEqual(postgres.estado["actuaciones"], [])
        self.assertEqual(len(postgres.estado["expedientes"]), 1)
        fotografia = postgres.estado["expedientes"][0]
        self.assertEqual(fotografia["estado"], "PENDIENTE")
        self.assertEqual(fotografia["reintentos"], 0)
        self.assertIsNone(fotografia["ruta_html"])
        self.assertIsNone(fotografia["ultima_fase"])
        self.assertIsNone(fotografia["datos_json"])
        for campo in ("actor", "demandado", "tipo_accion", "fecha_inicio_juicio"):
            self.assertIsNone(fotografia[campo], campo)
        for nombre, filas in historial_antes.items():
            with self.subTest(tabla=nombre):
                self.assertEqual(postgres.estado[nombre], filas)

    def test_fallo_postgres_tras_commit_sqlite_compensa_los_tres_formatos(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            config = raiz / "config.json"
            config.write_text(json.dumps({}), encoding="utf-8")
            csv = raiz / "reporte.csv"
            excel = raiz / "reporte.xlsx"
            sqlite = raiz / "estado.db"
            fallidos = raiz / "fallidos.txt"
            pd.DataFrame({
                "NUMERO_JUICIO": [CAUSA],
                "HISTORIAL_ACTUACIONES": ["evidencia anterior"],
                "ULTIMA FASE": ["3.1"],
                "COMENTARIO_ULTIMO": ["nota humana"],
            }).to_csv(csv, index=False)
            excel.write_bytes(b"EXCEL_ANTERIOR")
            fallidos.write_text(CAUSA + "\n", encoding="utf-8")
            with closing(sqlite3.connect(sqlite)) as conexion, conexion:
                conexion.execute("CREATE TABLE juicios (numero_causa TEXT PRIMARY KEY, estado TEXT, reintentos INTEGER, ruta_html TEXT)")
                conexion.execute("CREATE TABLE resultados_expediente (numero_causa TEXT, datos_json TEXT)")
                conexion.execute("CREATE TABLE eventos_extraccion (numero_causa TEXT, detalle TEXT)")
                conexion.execute("INSERT INTO juicios VALUES (?, 'PROCESADO', 2, 'antiguo.html')", (CAUSA,))
                conexion.execute("INSERT INTO resultados_expediente VALUES (?, '{}')", (CAUSA,))
                conexion.execute("INSERT INTO eventos_extraccion VALUES (?, 'evidencia')", (CAUSA,))
            csv_antes = csv.read_bytes()
            excel_antes = excel.read_bytes()
            gestor = _GestorSintetico(raiz)

            class ConexionFallida:
                def close(self):
                    pass

            def fallar_despues_de_sqlite(_conexion, _causas):
                with closing(sqlite3.connect(sqlite)) as conexion:
                    estado = conexion.execute("SELECT estado FROM juicios WHERE numero_causa=?", (CAUSA,)).fetchone()[0]
                self.assertEqual(estado, "PENDIENTE", "El fallo debe ocurrir tras confirmar SQLite")
                raise RuntimeError("POSTGRES_SIMULADO")

            with patch.object(reproceso, "GestorCasos", return_value=gestor), \
                 patch.object(reproceso, "_conectar_postgres", return_value=ConexionFallida()), \
                 patch.object(reproceso, "_respaldar_postgres", return_value=None), \
                 patch.object(reproceso, "_limpiar_postgres", side_effect=fallar_despues_de_sqlite):
                with self.assertRaisesRegex(RuntimeError, "POSTGRES_SIMULADO"):
                    reproceso.limpiar(config, [CAUSA])

            with closing(sqlite3.connect(sqlite)) as conexion:
                self.assertEqual(conexion.execute("SELECT estado, reintentos, ruta_html FROM juicios").fetchone(),
                                 ("PROCESADO", 2, "antiguo.html"))
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM resultados_expediente").fetchone()[0], 1)
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM eventos_extraccion").fetchone()[0], 1)
            self.assertEqual(csv.read_bytes(), csv_antes)
            self.assertEqual(excel.read_bytes(), excel_antes)
            self.assertEqual(fallidos.read_text(encoding="utf-8"), CAUSA + "\n")

    def test_integracion_postgres_efimero(self):
        dsn = os.getenv("TEST_POSTGRES_DSN")
        nombre_db = os.getenv("TEST_POSTGRES_DB")
        if not dsn or not nombre_db:
            self.skipTest("Configure TEST_POSTGRES_DSN y TEST_POSTGRES_DB para una base local aislada")
        if not (
            nombre_db.startswith(("test_", "qa_"))
            or nombre_db == "casos_judiciales_test"
        ):
            self.fail("TEST_POSTGRES_DB debe ser una base de pruebas aislada")
        try:
            import psycopg2
            from psycopg2 import sql
            from psycopg2.extensions import parse_dsn
        except ImportError:
            self.skipTest("psycopg2 no está instalado para la integración efímera")
        parametros = parse_dsn(dsn)
        if parametros.get("host") not in ("localhost", "127.0.0.1", "::1"):
            self.fail("TEST_POSTGRES_DSN debe apuntar a PostgreSQL local")
        if parametros.get("dbname") != nombre_db:
            self.fail("TEST_POSTGRES_DB no coincide con dbname de TEST_POSTGRES_DSN")

        conexion = psycopg2.connect(dsn, connect_timeout=5)
        esquema = "qa_reproceso_" + uuid.uuid4().hex
        creado = False
        try:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                self.assertEqual(cursor.fetchone()[0], nombre_db)
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(esquema)))
                creado = True
                cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
                migraciones = Path(__file__).resolve().parents[1] / "migrations" / "postgres"
                for nombre in ("001_concurrencia_base.sql", "002_historial_inferencia_ia.sql"):
                    cursor.execute((migraciones / nombre).read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO expedientes "
                    "(numero_causa, estado, ultima_fase, reintentos, ruta_html, datos_json, "
                    "actor, demandado, tipo_accion, fecha_inicio_juicio) "
                    "VALUES (%s, 'PROCESADO', '3.1', 2, 'antiguo.html', "
                    "'{\"fase\":\"3.1\"}'::jsonb, 'ACTOR SINTETICO', "
                    "'DEMANDADO SINTETICO', 'ACCION SINTETICA', '01/01/2099')",
                    (CAUSA,),
                )
                cursor.execute(
                    "INSERT INTO actuaciones (numero_causa, tipo_actuacion) VALUES (%s, 'LEGADA')",
                    (CAUSA,),
                )
                cursor.execute(
                    "INSERT INTO eventos_auditoria (numero_causa, tipo_evento) VALUES (%s, 'EXTRACCION')",
                    (CAUSA,),
                )
                cursor.execute(
                    "INSERT INTO actuaciones_procesales "
                    "(actuacion_id, numero_causa, carpeta, fecha, titulo, detalle, contenido_sha256, datos_json) "
                    "VALUES ('act-sintetica', %s, 'carpeta-1', '01/01/2099', 'TITULO', 'DETALLE', %s, '{}'::jsonb)",
                    (CAUSA, "a" * 64),
                )
                cursor.execute(
                    "INSERT INTO ejecuciones_inferencia "
                    "(numero_causa, huella_contexto, version_reglas, estado_json) "
                    "VALUES (%s, %s, 'test', '{}'::jsonb)",
                    (CAUSA, "b" * 64),
                )
                cursor.execute(
                    "INSERT INTO auditorias_ia (numero_causa, huella_contexto, modelo, modo, estado) "
                    "VALUES (%s, 'contexto-test', 'modelo-test', 'prueba', 'COMPLETADA') RETURNING id",
                    (CAUSA,),
                )
                auditoria_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO revisiones_ia (auditoria_id, numero_causa) VALUES (%s, %s)",
                    (auditoria_id, CAUSA),
                )
                cursor.execute(
                    "INSERT INTO hitos_procesales "
                    "(numero_causa, actuacion_id, fuente, condicion, version) "
                    "VALUES (%s, 'act-sintetica', 'TEST', 'CUMPLIDA', 'test')",
                    (CAUSA,),
                )
            conexion.commit()

            # Reaplicar ambas migraciones sobre datos existentes no debe
            # borrar ni duplicar la trazabilidad ya registrada.
            with conexion.cursor() as cursor:
                for nombre in (
                    "001_concurrencia_base.sql",
                    "002_historial_inferencia_ia.sql",
                ):
                    cursor.execute((migraciones / nombre).read_text(encoding="utf-8"))
                for tabla in (
                    "actuaciones_procesales", "ejecuciones_inferencia",
                    "auditorias_ia", "revisiones_ia", "hitos_procesales",
                ):
                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) FROM {} WHERE numero_causa=%s").format(
                            sql.Identifier(tabla)
                        ),
                        (CAUSA,),
                    )
                    self.assertEqual(cursor.fetchone()[0], 1, tabla)
            conexion.commit()

            reproceso._limpiar_postgres(conexion, [CAUSA])

            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT estado, reintentos, ruta_html, ultima_fase, datos_json, "
                    "actor, demandado, tipo_accion, fecha_inicio_juicio "
                    "FROM expedientes WHERE numero_causa=%s", (CAUSA,)
                )
                self.assertEqual(cursor.fetchone(),
                                 ("PENDIENTE", 0, None, None, None, None, None, None, None))
                for tabla, esperado in (
                    ("actuaciones", 0),
                    ("eventos_auditoria", 1),
                    ("actuaciones_procesales", 1),
                    ("ejecuciones_inferencia", 1),
                    ("auditorias_ia", 1),
                    ("revisiones_ia", 1),
                    ("hitos_procesales", 1),
                ):
                    with self.subTest(tabla=tabla):
                        cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(tabla)))
                        self.assertEqual(cursor.fetchone()[0], esperado)
        finally:
            conexion.rollback()
            if creado:
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (esquema,))
                    if cursor.fetchone():
                        cursor.execute("SET search_path TO public")
                        cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(esquema)))
                conexion.commit()
            conexion.close()


if __name__ == "__main__":
    unittest.main()
