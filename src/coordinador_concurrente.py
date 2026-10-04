"""Coordinacion multiproceso para la cola PostgreSQL."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from contextlib import AbstractContextManager

from src.ejecucion import ConfiguracionConcurrencia, ESTADOS_TERMINALES
from src.logger_config import configurar_logging, obtener_logger
from src.procesador_caso import (
    ProcesadorCaso,
    estado_terminal_para_resultado,
    resultado_es_recuperable,
)
from src.repositorio_postgres import RepositorioColaPostgres


logger = obtener_logger("CoordinadorConcurrente")


class RenovadorLease(AbstractContextManager):
    """Renueva un lease mientras Playwright o el CAPTCHA permanecen bloqueados."""

    def __init__(
        self,
        repositorio,
        trabajo_id,
        worker_id,
        lease_segundos,
        heartbeat_segundos,
    ):
        self.repositorio = repositorio
        self.trabajo_id = trabajo_id
        self.worker_id = worker_id
        self.lease_segundos = lease_segundos
        self.heartbeat_segundos = heartbeat_segundos
        self._detener = threading.Event()
        self._hilo = None
        self.lease_perdido = False

    def _ejecutar(self):
        while not self._detener.wait(self.heartbeat_segundos):
            try:
                renovado = self.repositorio.renovar_lease(
                    self.trabajo_id,
                    self.worker_id,
                    self.lease_segundos,
                )
                if not renovado:
                    self.lease_perdido = True
                    logger.error(
                        "[%s] Lease perdido para trabajo %s.",
                        self.worker_id,
                        self.trabajo_id,
                    )
                    return
            except Exception:
                logger.exception(
                    "[%s] No se pudo renovar el lease del trabajo %s.",
                    self.worker_id,
                    self.trabajo_id,
                )

    def __enter__(self):
        self._hilo = threading.Thread(
            target=self._ejecutar,
            name="heartbeat-%s" % self.worker_id,
            daemon=True,
        )
        self._hilo.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=max(1, self.heartbeat_segundos + 1))
        return False


class ExportadorResultadosEjecucion:
    """Unico escritor autorizado de los artefactos tabulares."""

    def __init__(self, repositorio, gestor_casos, ejecucion_id, exportar_cada):
        self.repositorio = repositorio
        self.gestor_casos = gestor_casos
        self.ejecucion_id = ejecucion_id
        self.exportar_cada = int(exportar_cada)
        self.ultimo_id_leido = 0
        self.pendientes = []

    def _leer_nuevos(self):
        filas = self.repositorio.listar_resultados(
            self.ejecucion_id,
            despues_de=self.ultimo_id_leido,
        )
        for fila in filas:
            self.ultimo_id_leido = max(self.ultimo_id_leido, int(fila["id"]))
            if fila["estado"] in ESTADOS_TERMINALES:
                self.pendientes.append(fila)
        return len(filas)

    def sincronizar(self, forzar=False):
        self._leer_nuevos()
        if not self.pendientes:
            return 0
        if not forzar and len(self.pendientes) < self.exportar_cada:
            return 0

        filas = list(self.pendientes)
        actualizados = 0
        for fila in filas:
            payload = fila.get("datos_json") or {}
            if not isinstance(payload, dict):
                continue
            datos = payload.get("datos") or {}
            if fila["estado"] == "REVISION":
                # Una consulta sin verificar no reemplaza las fases anteriores.
                datos = {k: v for k, v in datos.items() if k == "COMENTARIO_ULTIMO"}
            if datos:
                if not self.gestor_casos.actualizar_caso(
                    fila["numero_causa"], datos
                ):
                    raise RuntimeError(
                        "CAUSA_NO_ENCONTRADA_EN_REPORTE:%s"
                        % fila["numero_causa"]
                    )
                actualizados += 1

        if actualizados:
            if not self.gestor_casos.guardar():
                raise RuntimeError("PERSISTENCIA_ERROR:CSV")
            self.gestor_casos.exportar_excel()
        self.pendientes.clear()
        return actualizados


def _esperar_turno_inicio(bloqueo_inicio, ultimo_inicio, intervalo):
    if intervalo <= 0:
        return
    with bloqueo_inicio:
        ahora = time.monotonic()
        espera = max(0.0, float(intervalo) - (ahora - ultimo_inicio.value))
        if espera:
            time.sleep(espera)
        ultimo_inicio.value = time.monotonic()


def ejecutar_trabajador(
    config_db,
    config_navegacion,
    config_captcha,
    config_concurrencia,
    ejecucion_id,
    worker_id,
    ciudad,
    detener,
    captcha_semaforo,
    bloqueo_inicio,
    ultimo_inicio,
):
    """Punto de entrada serializable para ``multiprocessing.spawn``."""
    configurar_logging()
    repo = RepositorioColaPostgres.desde_config(config_db)
    concurrencia = ConfiguracionConcurrencia.desde_config(config_concurrencia)
    procesador = ProcesadorCaso(
        config_navegacion["url_portal"],
        config_navegacion,
        config_captcha,
        navegador_visible=concurrencia.navegador_visible,
        casos_por_sesion=concurrencia.casos_por_sesion,
    )
    logger.info("[%s] Trabajador iniciado.", worker_id)
    try:
        while not detener.is_set():
            trabajo = repo.reservar_siguiente(
                ejecucion_id,
                worker_id,
                concurrencia.lease_segundos,
            )
            if trabajo is None:
                if repo.hay_trabajo_programado(ejecucion_id):
                    time.sleep(2)
                    continue
                break

            try:
                with RenovadorLease(
                    repo,
                    trabajo.id,
                    worker_id,
                    concurrencia.lease_segundos,
                    concurrencia.heartbeat_segundos,
                ) as heartbeat:
                    with captcha_semaforo:
                        _esperar_turno_inicio(
                            bloqueo_inicio,
                            ultimo_inicio,
                            concurrencia.inicio_escalonado_segundos,
                        )
                        resultado = procesador.procesar(trabajo.numero_causa)
                    if heartbeat.lease_perdido:
                        raise RuntimeError("LEASE_PERDIDO_DURANTE_PROCESAMIENTO")

                estado_final = estado_terminal_para_resultado(resultado.estado)
                if estado_final:
                    repo.completar_trabajo(
                        trabajo,
                        worker_id,
                        estado_final,
                        resultado.como_payload(),
                        resultado.origen,
                        ciudad,
                    )
                    logger.info(
                        "[%s] Causa %s completada como %s.",
                        worker_id,
                        trabajo.numero_causa,
                        estado_final,
                    )
                else:
                    estado_error = repo.fallar_trabajo(
                        trabajo,
                        worker_id,
                        resultado.error or resultado.estado,
                        resultado.como_payload(),
                        resultado_es_recuperable(resultado.estado, resultado.error),
                        concurrencia.maximo_intentos,
                    )
                    logger.warning(
                        "[%s] Causa %s termino como %s.",
                        worker_id,
                        trabajo.numero_causa,
                        estado_error,
                    )
            except Exception:
                logger.exception(
                    "[%s] Fallo persistiendo o procesando %s; el lease permitira recuperacion.",
                    worker_id,
                    trabajo.numero_causa,
                )
                procesador.cerrar()
                raise
    finally:
        procesador.cerrar()
        logger.info("[%s] Trabajador cerrado.", worker_id)


class CoordinadorConcurrente:
    """Prepara una ejecucion y supervisa trabajadores locales."""

    def __init__(self, gestor_casos, ruta_config, trabajadores=None):
        self.gestor_casos = gestor_casos
        self.ruta_config = ruta_config
        self.config = gestor_casos.config
        self.config_db = dict(self.config.get("base_de_datos") or {})
        self.concurrencia = ConfiguracionConcurrencia.desde_config(
            self.config.get("concurrencia")
        )
        motor = str(self.config_db.get("motor", "sqlite")).lower()
        self.trabajadores = self.concurrencia.validar_motor(motor, trabajadores)
        if motor != "postgres":
            raise RuntimeError("POSTGRES_REQUERIDO_PARA_MODO_PARALELO")
        self.repositorio = RepositorioColaPostgres.desde_config(self.config_db)

    def _validar_precondiciones(self):
        if not self.repositorio.verificar_conexion():
            raise RuntimeError("POSTGRES_NO_DISPONIBLE")
        if not self.repositorio.verificar_esquema():
            raise RuntimeError("POSTGRES_ESQUEMA_INCOMPLETO")

    def ejecutar(self, casos, ruta_casos_fallidos):
        self._validar_precondiciones()
        causas = list(casos)
        perfil = self.config.get("perfil") or os.path.basename(self.ruta_config)
        opciones_auditoria = ({"config_sha256": self.config["_config_sha256"]}
                              if self.config.get("_config_sha256") else {})
        ejecucion_id = self.repositorio.crear_ejecucion(
            perfil,
            len(causas),
            self.trabajadores,
            **opciones_auditoria,
        )
        insertados = self.repositorio.poblar_trabajos(ejecucion_id, causas)
        if insertados != len(dict.fromkeys(causas)):
            raise RuntimeError("POBLACION_COLA_INCOMPLETA")
        self.repositorio.iniciar_ejecucion(ejecucion_id)

        contexto = multiprocessing.get_context("spawn")
        procesos = []
        cancelada = False
        exportador = ExportadorResultadosEjecucion(
            self.repositorio,
            self.gestor_casos,
            ejecucion_id,
            self.concurrencia.exportar_cada,
        )

        with contexto.Manager() as manager:
            detener = manager.Event()
            captcha_semaforo = manager.BoundedSemaphore(
                self.concurrencia.captcha_max_concurrentes
            )
            bloqueo_inicio = manager.Lock()
            ultimo_inicio = manager.Value("d", 0.0)
            for indice in range(self.trabajadores):
                worker_id = "worker-%02d" % (indice + 1)
                proceso = contexto.Process(
                    target=ejecutar_trabajador,
                    name=worker_id,
                    args=(
                        self.config_db,
                        dict(self.config.get("navegacion") or {}),
                        dict(self.config.get("captcha") or {}),
                        dict(self.config.get("concurrencia") or {}),
                        ejecucion_id,
                        worker_id,
                        self.gestor_casos.filtros.get("sucursal") or "TODAS",
                        detener,
                        captcha_semaforo,
                        bloqueo_inicio,
                        ultimo_inicio,
                    ),
                )
                proceso.start()
                procesos.append(proceso)

            try:
                while any(proceso.is_alive() for proceso in procesos):
                    self.repositorio.recuperar_leases_vencidos(
                        ejecucion_id,
                        self.concurrencia.maximo_intentos,
                    )
                    exportador.sincronizar(forzar=False)
                    for proceso in procesos:
                        proceso.join(timeout=0.2)
                    time.sleep(1)
            except KeyboardInterrupt:
                cancelada = True
                detener.set()
                logger.warning(
                    "Interrupcion solicitada; no se reservaran nuevas causas."
                )
            finally:
                for proceso in procesos:
                    proceso.join(timeout=60)
                for proceso in procesos:
                    if proceso.is_alive():
                        proceso.terminate()
                        proceso.join(timeout=10)

        exportador.sincronizar(forzar=True)
        stats = self.repositorio.obtener_estadisticas(ejecucion_id)
        fallidos = self.repositorio.listar_fallidos(ejecucion_id)
        self._guardar_fallidos(ruta_casos_fallidos, fallidos)
        codigos_salida = [proceso.exitcode for proceso in procesos]
        no_terminales = sum(
            stats.get(estado, 0)
            for estado in ("PENDIENTE", "EN_PROCESO", "ERROR_REINTENTABLE")
        )
        if cancelada:
            estado_ejecucion = "CANCELADA"
        elif no_terminales or any(codigo not in (0, None) for codigo in codigos_salida):
            estado_ejecucion = "FALLIDA"
        else:
            estado_ejecucion = "COMPLETADA"
        self.repositorio.finalizar_ejecucion(ejecucion_id, estado_ejecucion)
        return {
            "ejecucion_id": ejecucion_id,
            "estado": estado_ejecucion,
            "estadisticas": stats,
            "fallidos": fallidos,
        }

    @staticmethod
    def _guardar_fallidos(ruta, causas):
        directorio = os.path.dirname(os.path.abspath(ruta))
        os.makedirs(directorio, exist_ok=True)
        temporal = "%s.tmp.%s" % (ruta, os.getpid())
        try:
            with open(temporal, "w", encoding="utf-8") as archivo:
                for causa in causas:
                    archivo.write("%s\n" % causa)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, ruta)
        finally:
            if os.path.exists(temporal):
                os.unlink(temporal)
