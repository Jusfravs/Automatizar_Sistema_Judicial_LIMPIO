"""Atiende las solicitudes de lote creadas desde el portal web."""

from __future__ import annotations

import _thread
import copy
import hashlib
import io
import json
import os
import re
import socket
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.logger_config import obtener_logger


logger = obtener_logger("ServicioPortal")

RAIZ = Path(__file__).resolve().parents[1]
BUCKET = "lotes"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILTROS_PERMITIDOS = ("sucursal", "oficina", "estado_judicial")
ESTADOS_TERMINALES = ("COMPLETADA", "FALLIDA", "RECHAZADA", "CANCELADA")
ESTADOS_DE_EJECUCION = {"COMPLETADA": "COMPLETADA", "CANCELADA": "CANCELADA", "FALLIDA": "FALLIDA"}
LIMITE_MENSAJE = 500
MAXIMO_EXCEL_BYTES = 20 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO_BYTES = 200 * 1024 * 1024
MAXIMO_ARCHIVOS_INTERNOS = 5000
MAXIMA_TASA_COMPRESION = 200
CODIGO_PUBLICO = re.compile(r"^[A-Z][A-Z0-9_]*(:[A-Z0-9_ ,.\-]{1,200})?$")
COLUMNAS_SOLICITUD = (
    "id, archivo_ruta, archivo_nombre, hoja, filtros, modo, parametro, trabajadores, continuar"
)


class ErrorSolicitud(Exception):
    """Rechazo que se informa a quien pidió el lote."""


class CancelacionSolicitada(Exception):
    """El portal pidió detener el lote."""


@dataclass(frozen=True)
class Solicitud:
    id: str
    archivo_ruta: str
    archivo_nombre: str
    hoja: str | None
    filtros: dict
    modo: str
    parametro: str | None
    trabajadores: int
    continuar: bool

    @classmethod
    def desde_fila(cls, fila) -> "Solicitud":
        filtros = fila.get("filtros") or {}
        if isinstance(filtros, str):
            filtros = json.loads(filtros)
        return cls(
            id=str(fila["id"]),
            archivo_ruta=str(fila["archivo_ruta"]),
            archivo_nombre=str(fila["archivo_nombre"]),
            hoja=(str(fila["hoja"]).strip() or None) if fila.get("hoja") else None,
            filtros=filtros if isinstance(filtros, dict) else {},
            modo=str(fila["modo"]),
            parametro=fila.get("parametro"),
            trabajadores=int(fila["trabajadores"]),
            continuar=bool(fila["continuar"]),
        )

    def opciones_ejecucion(self) -> dict:
        """Traduce la solicitud a los argumentos de ``consola.ejecutar_lote``."""
        if self.archivo_ruta != "entradas/%s.xlsx" % self.id:
            raise ErrorSolicitud("RUTA_DE_ARCHIVO_INVALIDA")
        if not 1 <= self.trabajadores <= 4:
            raise ErrorSolicitud("TRABAJADORES_FUERA_DE_RANGO")
        if self.modo == "solo":
            causa = str(self.parametro or "").strip()
            if not causa:
                raise ErrorSolicitud("CAUSA_REQUERIDA")
            if self.trabajadores != 1:
                raise ErrorSolicitud("SOLO_REQUIERE_UN_TRABAJADOR")
            if self.continuar:
                raise ErrorSolicitud("CONTINUAR_NO_ADMITIDO_CON_SOLO")
            return {"solo": causa, "workers": 1, "continuar": False}
        if self.modo == "lote":
            texto = str(self.parametro or "").strip()
            if not texto.isdigit() or not 2 <= int(texto) <= 100:
                raise ErrorSolicitud("TAMANO_DE_LOTE_INVALIDO")
            return {"lote": int(texto), "workers": self.trabajadores, "continuar": self.continuar}
        if self.modo == "pendientes":
            return {"workers": self.trabajadores, "continuar": self.continuar}
        raise ErrorSolicitud("MODO_INVALIDO")


def codigo_publico(texto: object, predeterminado: str = "ERROR_INTERNO") -> str:
    """Reduce un error a un código apto para mostrarse en el portal.

    Los detalles (rutas locales, datos de conexión, trazas) quedan solo en el log.
    """
    valor = str(texto or "").strip()
    if CODIGO_PUBLICO.match(valor):
        return valor
    cabeza = valor.split(":", 1)[0].strip()
    return cabeza if CODIGO_PUBLICO.match(cabeza) else predeterminado


def verificar_excel_seguro(contenido: bytes) -> None:
    """Rechaza archivos que no son xlsx o que se expanden de forma desmedida."""
    if len(contenido) > MAXIMO_EXCEL_BYTES:
        raise ErrorSolicitud("EXCEL_DEMASIADO_GRANDE")
    if not zipfile.is_zipfile(io.BytesIO(contenido)):
        raise ErrorSolicitud("EXCEL_INVALIDO:NO_ES_XLSX")
    with zipfile.ZipFile(io.BytesIO(contenido)) as paquete:
        entradas = paquete.infolist()
        if len(entradas) > MAXIMO_ARCHIVOS_INTERNOS:
            raise ErrorSolicitud("EXCEL_SOSPECHOSO:DEMASIADOS_ARCHIVOS")
        descomprimido = sum(entrada.file_size for entrada in entradas)
        comprimido = sum(entrada.compress_size for entrada in entradas) or 1
        if descomprimido > MAXIMO_DESCOMPRIMIDO_BYTES:
            raise ErrorSolicitud("EXCEL_SOSPECHOSO:TAMANO_DESCOMPRIMIDO")
        if descomprimido / comprimido > MAXIMA_TASA_COMPRESION:
            raise ErrorSolicitud("EXCEL_SOSPECHOSO:TASA_DE_COMPRESION")


def aplicar_filtros(config: dict, filtros: dict) -> dict:
    """Devuelve la configuración con los filtros del portal y su huella recalculada."""
    resultado = copy.deepcopy(config)
    resultado.pop("_config_sha256", None)
    activos = resultado.setdefault("filtros_activos", {})
    for clave in FILTROS_PERMITIDOS:
        valor = filtros.get(clave)
        if valor is None:
            continue
        valor = str(valor).strip()
        if len(valor) > 120:
            raise ErrorSolicitud("FILTRO_DEMASIADO_LARGO:%s" % clave)
        activos[clave] = valor
    canonico = json.dumps(resultado, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    resultado["_config_sha256"] = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return resultado


class ClienteStorage:
    """Cliente mínimo de Supabase Storage para el bucket de lotes."""

    def __init__(self, url: str, clave: str, timeout: int = 120):
        if not url or not clave:
            raise ValueError("SUPABASE_STORAGE_NO_CONFIGURADO")
        self.base = url.rstrip("/") + "/storage/v1/object"
        self.clave = clave
        self.timeout = timeout

    @classmethod
    def desde_entorno(cls) -> "ClienteStorage":
        clave = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        return cls(os.environ.get("SUPABASE_URL", "").strip(), clave.strip())

    def _cabeceras(self, extra: dict | None = None) -> dict:
        cabeceras = {"apikey": self.clave}
        if self.clave.startswith("eyJ"):
            # Las claves heredadas son JWT y Storage también las acepta como portador.
            cabeceras["Authorization"] = "Bearer " + self.clave
        cabeceras.update(extra or {})
        return cabeceras

    def _url(self, ruta: str) -> str:
        return "%s/%s/%s" % (self.base, BUCKET, quote(ruta, safe="/"))

    def descargar(self, ruta: str) -> bytes:
        try:
            with urlopen(Request(self._url(ruta), headers=self._cabeceras()),
                         timeout=self.timeout) as respuesta:
                return respuesta.read()
        except HTTPError as exc:
            raise RuntimeError("STORAGE_DESCARGA_HTTP_%s" % exc.code) from None
        except URLError as exc:
            raise RuntimeError("STORAGE_NO_DISPONIBLE") from exc

    def subir(self, ruta: str, contenido: bytes, tipo: str = TIPO_XLSX) -> None:
        solicitud = Request(
            self._url(ruta), data=contenido, method="POST",
            headers=self._cabeceras({"Content-Type": tipo, "x-upsert": "true"}),
        )
        try:
            with urlopen(solicitud, timeout=self.timeout) as respuesta:
                respuesta.read()
        except HTTPError as exc:
            raise RuntimeError("STORAGE_SUBIDA_HTTP_%s" % exc.code) from None
        except URLError as exc:
            raise RuntimeError("STORAGE_NO_DISPONIBLE") from exc


class RepositorioSolicitudes:
    """Acceso a ``solicitudes_lote`` con la conexión del motor."""

    CAMPOS_ACTUALIZABLES = ("estado", "perfil", "ejecucion_id", "mensaje", "resultado_ruta")

    def __init__(self, repo):
        self.repo = repo

    def _ejecutar(self, sql: str, parametros=(), *, una: bool = False):
        from psycopg2.extras import RealDictCursor

        with self.repo._connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, parametros)
                if cur.description is None:
                    return cur.rowcount
                return cur.fetchone() if una else cur.fetchall()

    def verificar_tabla(self) -> bool:
        fila = self._ejecutar(
            "SELECT to_regclass('public.solicitudes_lote') IS NOT NULL AS existe", una=True
        )
        return bool(fila and fila["existe"])

    def reservar(self, worker_host: str) -> Solicitud | None:
        fila = self._ejecutar(
            """
            UPDATE public.solicitudes_lote
               SET estado = 'TOMADA', worker_host = %s, tomado_en = now()
             WHERE id = (
                   SELECT id FROM public.solicitudes_lote
                    WHERE estado = 'SOLICITADA' AND NOT cancelar
                    ORDER BY creado_en
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1)
            RETURNING """ + COLUMNAS_SOLICITUD,
            (worker_host,), una=True,
        )
        return Solicitud.desde_fila(fila) if fila else None

    def actualizar(self, solicitud_id: str, **campos) -> None:
        desconocidos = set(campos) - set(self.CAMPOS_ACTUALIZABLES)
        if desconocidos:
            raise ValueError("CAMPOS_NO_ACTUALIZABLES:%s" % ",".join(sorted(desconocidos)))
        if not campos:
            return
        if campos.get("mensaje"):
            campos["mensaje"] = str(campos["mensaje"])[:LIMITE_MENSAJE]
        asignaciones = ["%s = %%s" % campo for campo in campos]
        if campos.get("estado") in ESTADOS_TERMINALES:
            asignaciones.append("finalizado_en = now()")
        self._ejecutar(
            "UPDATE public.solicitudes_lote SET %s WHERE id = %%s" % ", ".join(asignaciones),
            (*campos.values(), solicitud_id),
        )

    def cancelacion_pedida(self, solicitud_id: str) -> bool:
        fila = self._ejecutar(
            "SELECT cancelar FROM public.solicitudes_lote WHERE id = %s", (solicitud_id,), una=True
        )
        return bool(fila and fila["cancelar"])

    def cerrar_interrumpidas(self, worker_host: str) -> int:
        """Cierra lo que este equipo dejó a medias si el servicio se detuvo."""
        return self._ejecutar(
            """
            UPDATE public.solicitudes_lote
               SET estado = CASE WHEN cancelar THEN 'CANCELADA' ELSE 'FALLIDA' END,
                   finalizado_en = now(),
                   mensaje = 'El servicio se reinició durante el proceso. Vuelve a solicitar el lote.'
             WHERE worker_host = %s AND estado IN ('TOMADA', 'PREPARANDO', 'EN_CURSO')
            """,
            (worker_host,),
        )


class VigilanteCancelacion:
    """Interrumpe el lote en curso cuando el portal pide cancelarlo.

    La interrupción llega al hilo principal como ``KeyboardInterrupt``, la misma
    señal con la que el coordinador ya detiene a sus trabajadores de forma ordenada.
    """

    def __init__(self, solicitudes, solicitud_id: str, intervalo: float = 5.0,
                 interrumpir=_thread.interrupt_main):
        self.solicitudes = solicitudes
        self.solicitud_id = solicitud_id
        self.intervalo = intervalo
        self.interrumpir = interrumpir
        self.cancelada = False
        self._detener = threading.Event()
        self._hilo = None

    def _vigilar(self):
        while not self._detener.wait(self.intervalo):
            try:
                if self.solicitudes.cancelacion_pedida(self.solicitud_id):
                    self.cancelada = True
                    logger.warning("[PORTAL] Cancelación pedida para %s.", self.solicitud_id)
                    self.interrumpir()
                    return
            except Exception:
                logger.exception("[PORTAL] No se pudo consultar la cancelación de %s.",
                                 self.solicitud_id)

    def __enter__(self):
        self._hilo = threading.Thread(target=self._vigilar, name="vigilante-cancelacion",
                                      daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=self.intervalo + 1)
        return False


def _resumen_estadisticas(estadisticas: dict | None) -> str:
    if not estadisticas:
        return ""
    return ", ".join("%s: %s" % (estado, total) for estado, total in sorted(estadisticas.items()))


class ServicioPortal:
    def __init__(self, solicitudes, storage, *, preparar_lote, ejecutar_lote, directorio: Path,
                 worker_host: str, intervalo: float = 10.0, intervalo_cancelacion: float = 5.0,
                 interrumpir=_thread.interrupt_main):
        self.solicitudes = solicitudes
        self.storage = storage
        self.preparar_lote = preparar_lote
        self.ejecutar_lote = ejecutar_lote
        self.directorio = Path(directorio)
        self.worker_host = worker_host
        self.intervalo = intervalo
        self.intervalo_cancelacion = intervalo_cancelacion
        self.interrumpir = interrumpir

    def atender_una(self) -> bool:
        solicitud = self.solicitudes.reservar(self.worker_host)
        if solicitud is None:
            return False
        self.procesar(solicitud)
        return True

    def procesar(self, solicitud: Solicitud) -> None:
        logger.info("[PORTAL] Solicitud %s tomada (modo %s).", solicitud.id, solicitud.modo)
        try:
            opciones = solicitud.opciones_ejecucion()
            self.solicitudes.actualizar(solicitud.id, estado="PREPARANDO")
            lote, perfil = self._preparar(solicitud)
            if self.solicitudes.cancelacion_pedida(solicitud.id):
                raise CancelacionSolicitada()
            self.solicitudes.actualizar(solicitud.id, estado="EN_CURSO", perfil=perfil)
            with VigilanteCancelacion(self.solicitudes, solicitud.id, self.intervalo_cancelacion,
                                      self.interrumpir) as vigilante:
                try:
                    resultado = self.ejecutar_lote(lote, solicitud, opciones)
                except KeyboardInterrupt:
                    if not vigilante.cancelada:
                        raise
                    raise CancelacionSolicitada() from None
            estado, mensaje, ejecucion_id = self._interpretar(resultado, vigilante.cancelada)
            ruta, error_subida = self._subir_resultado(solicitud, lote)
            if error_subida:
                mensaje = ("%s No se pudo publicar el Excel de resultado (%s)."
                           % (mensaje, error_subida)).strip()
            self.solicitudes.actualizar(solicitud.id, estado=estado, mensaje=mensaje,
                                        ejecucion_id=ejecucion_id, resultado_ruta=ruta)
            logger.info("[PORTAL] Solicitud %s terminó como %s.", solicitud.id, estado)
        except ErrorSolicitud as exc:
            logger.warning("[PORTAL] Solicitud %s rechazada: %s", solicitud.id, exc)
            self.solicitudes.actualizar(solicitud.id, estado="RECHAZADA", mensaje=str(exc))
        except CancelacionSolicitada:
            logger.warning("[PORTAL] Solicitud %s cancelada.", solicitud.id)
            self.solicitudes.actualizar(solicitud.id, estado="CANCELADA",
                                        mensaje="Cancelada desde el portal.")
        except Exception as exc:
            logger.exception("[PORTAL] Solicitud %s falló.", solicitud.id)
            self.solicitudes.actualizar(solicitud.id, estado="FALLIDA",
                                        mensaje=codigo_publico(exc))

    def _preparar(self, solicitud: Solicitud) -> tuple[Path, str]:
        carpeta = self.directorio / "entradas" / solicitud.id
        carpeta.mkdir(parents=True, exist_ok=True)
        excel = carpeta / "entrada.xlsx"
        contenido = self.storage.descargar(solicitud.archivo_ruta)
        verificar_excel_seguro(contenido)
        excel.write_bytes(contenido)
        try:
            preparado = self.preparar_lote(excel, self.directorio / "lotes" / solicitud.id,
                                           solicitud.hoja)
        except ValueError as exc:
            logger.warning("[PORTAL] Excel de %s rechazado: %s", solicitud.id, exc)
            raise ErrorSolicitud(
                "EXCEL_INVALIDO:%s" % codigo_publico(exc, "FORMATO_NO_RECONOCIDO")
            ) from None
        return Path(preparado["directorio"]), str(preparado["perfil"])

    @staticmethod
    def _interpretar(resultado, cancelada: bool) -> tuple[str, str, str | None]:
        if resultado is None:
            return "COMPLETADA", "No había causas pendientes con los filtros elegidos.", None
        estado = ESTADOS_DE_EJECUCION.get(str(resultado.get("estado")), "FALLIDA")
        mensaje = _resumen_estadisticas(resultado.get("estadisticas"))
        if estado == "CANCELADA" and cancelada:
            mensaje = ("Cancelada desde el portal. " + mensaje).strip()
        ejecucion_id = resultado.get("ejecucion_id")
        return estado, mensaje, str(ejecucion_id) if ejecucion_id else None

    def _subir_resultado(self, solicitud: Solicitud, lote: Path) -> tuple[str | None, str | None]:
        excel = lote / "reporte_final.xlsx"
        if not excel.is_file():
            return None, None
        ruta = "resultados/%s.xlsx" % solicitud.id
        try:
            self.storage.subir(ruta, excel.read_bytes())
        except Exception as exc:
            logger.exception("[PORTAL] No se pudo subir el resultado de %s.", solicitud.id)
            return None, codigo_publico(exc, "STORAGE_NO_DISPONIBLE")
        return ruta, None

    def ejecutar(self, *, una_vez: bool = False, detener: threading.Event | None = None) -> None:
        detener = detener or threading.Event()
        cerradas = self.solicitudes.cerrar_interrumpidas(self.worker_host)
        if cerradas:
            logger.warning("[PORTAL] %s solicitud(es) interrumpidas se marcaron como cerradas.",
                           cerradas)
        logger.info("[PORTAL] Servicio activo en %s; consulta cada %ss.",
                    self.worker_host, self.intervalo)
        while not detener.is_set():
            try:
                atendida = self.atender_una()
            except Exception:
                logger.exception("[PORTAL] No se pudieron consultar las solicitudes.")
                atendida = False
            if una_vez:
                return
            if not atendida:
                detener.wait(self.intervalo)


def preparar_con_consola(base: Path):
    def preparar(excel: Path, salida: Path, hoja: str | None) -> dict:
        import consola
        from src.configuracion_lotes import leer_manifiesto

        resultado = consola.preparar(excel, salida, base, hoja)
        resultado["perfil"] = leer_manifiesto(Path(resultado["directorio"]))["perfil_id"]
        return resultado

    return preparar


def ejecutar_con_consola(base: Path):
    def ejecutar(lote: Path, solicitud: Solicitud, opciones: dict):
        import consola

        config = aplicar_filtros(consola._config_perfil(lote, base), solicitud.filtros)
        return consola.ejecutar_lote(lote, base=base, config=config, **opciones)

    return ejecutar


def ejecutar_servicio(ruta_config: Path, *, intervalo: int = 10, una_vez: bool = False) -> int:
    import consola
    from src.configuracion_lotes import cargar_comun
    from src.logger_config import configurar_logging

    configurar_logging(consola=os.environ.get("SISTEMA_JUDICIAL_SERVICE_MODE") != "1")
    ruta_config = Path(ruta_config).expanduser().resolve()
    config = cargar_comun(ruta_config)
    revision = consola.diagnostico(config)
    if not (revision["conexion"] and revision["esquema_completo"] and revision["auditoria_config"]):
        raise ValueError("BASE_DE_DATOS_NO_LISTA:%s" % json.dumps(revision, default=str))
    solicitudes = RepositorioSolicitudes(consola._repositorio(config))
    if not solicitudes.verificar_tabla():
        raise ValueError("TABLA_SOLICITUDES_LOTE_AUSENTE")
    servicio = ServicioPortal(
        solicitudes,
        ClienteStorage.desde_entorno(),
        preparar_lote=preparar_con_consola(ruta_config),
        ejecutar_lote=ejecutar_con_consola(ruta_config),
        directorio=RAIZ / "outputs" / "portal",
        worker_host=socket.gethostname()[:120],
        intervalo=intervalo,
    )
    servicio.ejecutar(una_vez=una_vez)
    return 0
