"""Adaptador compatible de la cola SQLite secuencial."""

from __future__ import annotations

import json
import os

from src.ejecucion import TrabajoCola
from src.gestor_cola import GestorCola


class RepositorioColaSQLite:
    """Expone el contrato comun sin habilitar concurrencia sobre SQLite."""

    def __init__(self, ruta_db):
        self.gestor = GestorCola(ruta_db=ruta_db)
        self.ruta_db = ruta_db
        self.ejecucion_id = "sqlite:%s" % os.path.abspath(ruta_db)

    def verificar_conexion(self):
        with self.gestor._connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def verificar_esquema(self):
        return self.gestor.verificar_esquema()

    def crear_ejecucion(self, perfil, total_esperado, trabajadores):
        if int(trabajadores) != 1:
            raise RuntimeError("SQLITE_SOLO_ADMITE_UN_TRABAJADOR")
        return self.ejecucion_id

    def poblar_trabajos(self, ejecucion_id, causas):
        self._validar_ejecucion(ejecucion_id)
        unicas = list(dict.fromkeys(str(c).strip() for c in causas if str(c).strip()))
        self.gestor.poblar_cola(unicas)
        return len(unicas)

    def iniciar_ejecucion(self, ejecucion_id):
        self._validar_ejecucion(ejecucion_id)

    def reservar_siguiente(self, ejecucion_id, worker_id, lease_segundos):
        self._validar_ejecucion(ejecucion_id)
        causa = self.gestor.obtener_siguiente()
        if causa is None:
            return None
        with self.gestor._connection() as conn:
            fila = conn.execute(
                "SELECT reintentos FROM juicios WHERE numero_causa = ?",
                (causa,),
            ).fetchone()
        return TrabajoCola(causa, causa, int(fila[0] or 0) + 1)

    def renovar_lease(self, trabajo_id, worker_id, lease_segundos):
        with self.gestor._connection() as conn:
            fila = conn.execute(
                "SELECT estado FROM juicios WHERE numero_causa = ?",
                (str(trabajo_id),),
            ).fetchone()
        return bool(fila and fila[0] == "EN_PROCESO")

    def completar_trabajo(
        self, trabajo, worker_id, estado_final, resultado, origen, ciudad
    ):
        estado_sqlite = {
            "REVISION": "ERROR",
            "ERROR_FINAL": "ERROR",
        }.get(estado_final, estado_final)
        self.gestor.registrar_resultado_transaccional(
            trabajo.numero_causa,
            dict(resultado),
            origen,
            estado_final=estado_sqlite,
        )

    def fallar_trabajo(
        self,
        trabajo,
        worker_id,
        detalle,
        resultado,
        recuperable,
        maximo_intentos,
    ):
        payload = dict(resultado or {})
        payload.setdefault("estado", "ERROR")
        payload.setdefault("error", str(detalle))
        self.gestor.registrar_resultado_transaccional(
            trabajo.numero_causa,
            payload,
            "ESATJE_TRANSACCIONAL",
            estado_final="ERROR",
        )
        return "ERROR_FINAL"

    def recuperar_leases_vencidos(self, ejecucion_id, maximo_intentos):
        self._validar_ejecucion(ejecucion_id)
        return self.gestor.recuperar_huerfanos()

    def obtener_estadisticas(self, ejecucion_id):
        self._validar_ejecucion(ejecucion_id)
        return self.gestor.obtener_estadisticas()

    def listar_resultados(self, ejecucion_id, despues_de=0):
        self._validar_ejecucion(ejecucion_id)
        with self.gestor._connection() as conn:
            filas = conn.execute(
                """
                SELECT rowid, numero_causa, datos_json, actualizado_en
                FROM resultados_expediente
                WHERE rowid > ?
                ORDER BY rowid
                """,
                (int(despues_de),),
            ).fetchall()
        resultados = []
        for rowid, causa, contenido, creado_en in filas:
            try:
                payload = json.loads(contenido)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            estado = payload.get("estado", "PROCESADO")
            estado = {
                "COMPLETADO": "PROCESADO",
                "ERROR": "ERROR_FINAL",
                "ERROR_VERIFICACION_MANUAL": "REVISION",
            }.get(estado, estado)
            resultados.append(
                {
                    "id": rowid,
                    "numero_causa": causa,
                    "estado": estado,
                    "datos_json": payload,
                    "creado_en": creado_en,
                }
            )
        return resultados

    def finalizar_ejecucion(self, ejecucion_id, estado):
        self._validar_ejecucion(ejecucion_id)

    def _validar_ejecucion(self, ejecucion_id):
        if ejecucion_id != self.ejecucion_id:
            raise LookupError("EJECUCION_SQLITE_DESCONOCIDA")
