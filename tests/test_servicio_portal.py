import io
import json
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.almacen_b2 import ClienteB2
from src.servicio_portal import (
    ClienteStorage,
    ClienteStorageHibrido,
    ErrorSolicitud,
    RepositorioSolicitudes,
    ServicioPortal,
    Solicitud,
    VigilanteCancelacion,
    aplicar_filtros,
    codigo_publico,
    verificar_excel_seguro,
)


def paquete_zip(archivos):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as paquete:
        for nombre, contenido in archivos.items():
            paquete.writestr(nombre, contenido)
    return memoria.getvalue()


EXCEL_PRUEBA = paquete_zip({
    "[Content_Types].xml": "<Types/>",
    "xl/workbook.xml": "<workbook/>",
})


ID = "6f1c2b9e-1111-4222-8333-444455556666"


class TestAlmacenB2(unittest.TestCase):
    def test_rutas_nuevas_b2_y_antiguas_supabase(self):
        supabase = MagicMock()
        b2 = MagicMock()
        almacen = ClienteStorageHibrido(supabase, b2)
        almacen.descargar("entradas/antiguo.xlsx")
        almacen.descargar("b2:entradas/nuevo.xlsx")
        almacen.subir("b2:resultados/nuevo.xlsx", b"excel")
        supabase.descargar.assert_called_once_with("entradas/antiguo.xlsx")
        b2.descargar.assert_called_once_with("b2:entradas/nuevo.xlsx")
        b2.subir.assert_called_once_with(
            "b2:resultados/nuevo.xlsx", b"excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_b2_rechaza_rutas_invalidas_y_usa_bucket_privado(self):
        cliente_s3 = MagicMock()
        cliente_s3.head_object.return_value = {"ContentLength": 5}
        cliente_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"datos")}
        b2 = ClienteB2("https://s3.us-east-005.backblazeb2.com", "judicial-privado", "id", "clave", cliente=cliente_s3)
        self.assertEqual(b2.descargar("b2:entradas/archivo.xlsx"), b"datos")
        cliente_s3.get_object.assert_called_once_with(Bucket="judicial-privado", Key="entradas/archivo.xlsx")
        cliente_s3.head_object.return_value = {"ContentLength": 21 * 1024 * 1024}
        with self.assertRaises(ValueError):
            b2.descargar("b2:entradas/demasiado-grande.xlsx")
        with self.assertRaises(ValueError):
            b2.descargar("b2:../otro-archivo.xlsx")


def solicitud(**cambios):
    datos = {
        "id": ID,
        "archivo_ruta": "entradas/%s.xlsx" % ID,
        "archivo_nombre": "reporte.xlsx",
        "hoja": None,
        "filtros": {"sucursal": "QUITO"},
        "modo": "lote",
        "parametro": "10",
        "trabajadores": 2,
        "continuar": False,
    }
    datos.update(cambios)
    return Solicitud(**datos)


class SolicitudesFalsas:
    def __init__(self, pendientes=(), cancelar_tras=None):
        self.pendientes = list(pendientes)
        self.cambios = []
        self.consultas_cancelacion = 0
        self.cancelar_tras = cancelar_tras
        self.cerradas_para = None

    def reservar(self, worker_host):
        return self.pendientes.pop(0) if self.pendientes else None

    def actualizar(self, solicitud_id, **campos):
        self.cambios.append(campos)

    def cancelacion_pedida(self, solicitud_id):
        self.consultas_cancelacion += 1
        return self.cancelar_tras is not None and self.consultas_cancelacion > self.cancelar_tras

    def cerrar_interrumpidas(self, worker_host):
        self.cerradas_para = worker_host
        return 0

    @property
    def final(self):
        return self.cambios[-1]


class StorageFalso:
    def __init__(self):
        self.subidas = {}

    def descargar(self, ruta):
        return EXCEL_PRUEBA

    def subir(self, ruta, contenido, tipo=None):
        self.subidas[ruta] = contenido


class TestSolicitud(unittest.TestCase):
    def test_lote_valido(self):
        self.assertEqual(solicitud().opciones_ejecucion(),
                         {"lote": 10, "workers": 2, "continuar": False})

    def test_solo_exige_un_trabajador_y_sin_continuar(self):
        self.assertEqual(
            solicitud(modo="solo", parametro=" 17230-2023-00001 ", trabajadores=1)
            .opciones_ejecucion(),
            {"solo": "17230-2023-00001", "workers": 1, "continuar": False},
        )
        for cambios in ({"trabajadores": 2}, {"continuar": True}, {"parametro": " "}):
            datos = {"modo": "solo", "parametro": "X", "trabajadores": 1, **cambios}
            with self.subTest(cambios=cambios), self.assertRaises(ErrorSolicitud):
                solicitud(**datos).opciones_ejecucion()

    def test_lote_fuera_de_rango_y_modo_desconocido(self):
        for cambios in ({"parametro": "1"}, {"parametro": "101"}, {"parametro": "diez"},
                        {"modo": "todo"}, {"trabajadores": 5}):
            with self.subTest(cambios=cambios), self.assertRaises(ErrorSolicitud):
                solicitud(**cambios).opciones_ejecucion()

    def test_ruta_de_archivo_debe_corresponder_a_la_solicitud(self):
        with self.assertRaises(ErrorSolicitud):
            solicitud(archivo_ruta="entradas/otro.xlsx").opciones_ejecucion()

    def test_desde_fila_acepta_filtros_en_texto(self):
        fila = {"id": ID, "archivo_ruta": "a", "archivo_nombre": "b", "hoja": "  ",
                "filtros": json.dumps({"oficina": "X"}), "modo": "pendientes",
                "parametro": None, "trabajadores": 1, "continuar": True}
        resultado = Solicitud.desde_fila(fila)
        self.assertEqual(resultado.filtros, {"oficina": "X"})
        self.assertIsNone(resultado.hoja)


class TestAplicarFiltros(unittest.TestCase):
    def test_reemplaza_solo_filtros_permitidos_y_recalcula_huella(self):
        base = {"filtros_activos": {"sucursal": "TODAS", "columna_estado_judicial": "ESTADO"},
                "_config_sha256": "viejo"}
        resultado = aplicar_filtros(base, {"sucursal": " QUITO ", "columna_estado_judicial": "X",
                                           "inicio_desde_juicio": "Y"})
        self.assertEqual(resultado["filtros_activos"],
                         {"sucursal": "QUITO", "columna_estado_judicial": "ESTADO"})
        self.assertNotEqual(resultado["_config_sha256"], "viejo")
        self.assertEqual(base["filtros_activos"]["sucursal"], "TODAS")

    def test_filtro_demasiado_largo(self):
        with self.assertRaises(ErrorSolicitud):
            aplicar_filtros({}, {"oficina": "x" * 121})


class TestClienteStorage(unittest.TestCase):
    def _cabeceras_enviadas(self, clave):
        cliente = ClienteStorage("https://proyecto.supabase.co/", clave)
        respuesta = MagicMock()
        respuesta.__enter__.return_value.read.return_value = b"ok"
        with patch("src.servicio_portal.urlopen", return_value=respuesta) as abrir:
            cliente.descargar("entradas/a b.xlsx")
        peticion = abrir.call_args.args[0]
        return peticion, {k.lower(): v for k, v in peticion.header_items()}

    def test_clave_secreta_solo_en_apikey(self):
        peticion, cabeceras = self._cabeceras_enviadas("sb_secret_abc")
        self.assertEqual(cabeceras["apikey"], "sb_secret_abc")
        self.assertNotIn("authorization", cabeceras)
        self.assertEqual(
            peticion.full_url,
            "https://proyecto.supabase.co/storage/v1/object/lotes/entradas/a%20b.xlsx",
        )

    def test_clave_heredada_tambien_como_portador(self):
        _, cabeceras = self._cabeceras_enviadas("eyJhbGciOi.jwt")
        self.assertEqual(cabeceras["authorization"], "Bearer eyJhbGciOi.jwt")

    def test_sin_configuracion(self):
        with self.assertRaises(ValueError):
            ClienteStorage("", "clave")


class TestRepositorioSolicitudes(unittest.TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.cursor.description = None
        self.cursor.rowcount = 1
        conexion = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = self.cursor
        repo = MagicMock()

        @contextmanager
        def _connection():
            yield conexion

        repo._connection = _connection
        self.repositorio = RepositorioSolicitudes(repo)

    def test_actualizar_estado_terminal_fija_fecha_de_fin(self):
        self.repositorio.actualizar(ID, estado="COMPLETADA", mensaje="x" * 900)
        sql, parametros = self.cursor.execute.call_args.args
        self.assertIn("finalizado_en = now()", sql)
        self.assertEqual(len(parametros[1]), 500)
        self.assertEqual(parametros[-1], ID)

    def test_actualizar_rechaza_campos_no_permitidos(self):
        with self.assertRaises(ValueError):
            self.repositorio.actualizar(ID, solicitado_por="otro")

    def test_reservar_usa_skip_locked(self):
        self.cursor.description = ("id",)
        self.cursor.fetchone.return_value = None
        self.assertIsNone(self.repositorio.reservar("servidor"))
        sql = self.cursor.execute.call_args.args[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertIn("NOT cancelar", sql)


class TestServicioPortal(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.directorio = Path(self.temporal.name)
        self.lote = self.directorio / "lote"
        self.lote.mkdir()

    def servicio(self, solicitudes, ejecutar=None, preparar=None, storage=None, **opciones):
        def preparar_por_defecto(excel, salida, hoja):
            self.assertEqual(excel.read_bytes(), EXCEL_PRUEBA)
            return {"directorio": str(self.lote), "perfil": "lote-abc"}

        return ServicioPortal(
            solicitudes, storage or StorageFalso(),
            preparar_lote=preparar or preparar_por_defecto,
            ejecutar_lote=ejecutar or (lambda lote, sol, op: {
                "ejecucion_id": "e-1", "estado": "COMPLETADA",
                "estadisticas": {"PROCESADO": 9, "ERROR_FINAL": 1}}),
            directorio=self.directorio, worker_host="servidor",
            intervalo_cancelacion=0.01, **opciones,
        )

    def test_flujo_completo_publica_resultado(self):
        (self.lote / "reporte_final.xlsx").write_bytes(b"final")
        solicitudes = SolicitudesFalsas([solicitud()])
        storage = StorageFalso()
        recibido = {}

        def ejecutar(lote, sol, opciones):
            recibido.update(opciones)
            return {"ejecucion_id": "e-1", "estado": "COMPLETADA",
                    "estadisticas": {"PROCESADO": 9, "ERROR_FINAL": 1}}

        self.assertTrue(self.servicio(solicitudes, ejecutar, storage=storage).atender_una())
        self.assertEqual(recibido, {"lote": 10, "workers": 2, "continuar": False})
        self.assertEqual([c.get("estado") for c in solicitudes.cambios],
                         ["PREPARANDO", "EN_CURSO", "COMPLETADA"])
        self.assertEqual(solicitudes.cambios[1]["perfil"], "lote-abc")
        self.assertEqual(solicitudes.final["ejecucion_id"], "e-1")
        self.assertEqual(solicitudes.final["resultado_ruta"], "resultados/%s.xlsx" % ID)
        self.assertEqual(solicitudes.final["mensaje"], "ERROR_FINAL: 1, PROCESADO: 9")
        self.assertEqual(storage.subidas["resultados/%s.xlsx" % ID], b"final")

    def test_lote_b2_publica_resultado_en_b2(self):
        (self.lote / "reporte_final.xlsx").write_bytes(b"final")
        solicitudes = SolicitudesFalsas([solicitud(archivo_ruta=f"b2:entradas/{ID}/{ID}.xlsx")])
        storage = StorageFalso()
        self.assertTrue(self.servicio(solicitudes, storage=storage).atender_una())
        ruta = f"b2:resultados/{ID}.xlsx"
        self.assertEqual(solicitudes.final["resultado_ruta"], ruta)
        self.assertEqual(storage.subidas[ruta], b"final")

    def test_sin_causas_pendientes_completa_con_mensaje(self):
        solicitudes = SolicitudesFalsas([solicitud()])
        self.servicio(solicitudes, lambda *a: None).atender_una()
        self.assertEqual(solicitudes.final["estado"], "COMPLETADA")
        self.assertIn("No había causas", solicitudes.final["mensaje"])
        self.assertIsNone(solicitudes.final["resultado_ruta"])

    def test_excel_invalido_rechaza(self):
        def preparar(excel, salida, hoja):
            raise ValueError("COLUMNAS_FALTANTES:SUCURSAL")

        solicitudes = SolicitudesFalsas([solicitud()])
        self.servicio(solicitudes, preparar=preparar).atender_una()
        self.assertEqual(solicitudes.final["estado"], "RECHAZADA")
        self.assertIn("COLUMNAS_FALTANTES", solicitudes.final["mensaje"])

    def test_solicitud_invalida_rechaza_sin_descargar(self):
        solicitudes = SolicitudesFalsas([solicitud(parametro="500")])
        storage = MagicMock()
        self.servicio(solicitudes, storage=storage).atender_una()
        storage.descargar.assert_not_called()
        self.assertEqual(solicitudes.final["estado"], "RECHAZADA")

    def test_cancelada_antes_de_ejecutar(self):
        ejecutar = MagicMock()
        solicitudes = SolicitudesFalsas([solicitud()], cancelar_tras=0)
        self.servicio(solicitudes, ejecutar).atender_una()
        ejecutar.assert_not_called()
        self.assertEqual(solicitudes.final["estado"], "CANCELADA")

    def test_cancelacion_durante_la_ejecucion_detiene_el_lote(self):
        interrumpido = threading.Event()

        def ejecutar(lote, sol, opciones):
            self.assertTrue(interrumpido.wait(2))
            raise KeyboardInterrupt

        solicitudes = SolicitudesFalsas([solicitud()], cancelar_tras=1)
        self.servicio(solicitudes, ejecutar, interrumpir=interrumpido.set).atender_una()
        self.assertEqual(solicitudes.final["estado"], "CANCELADA")

    def test_interrupcion_del_operador_no_se_trata_como_cancelacion(self):
        def ejecutar(lote, sol, opciones):
            raise KeyboardInterrupt

        solicitudes = SolicitudesFalsas([solicitud()])
        with self.assertRaises(KeyboardInterrupt):
            self.servicio(solicitudes, ejecutar).atender_una()

    def test_error_inesperado_marca_fallida(self):
        def ejecutar(lote, sol, opciones):
            raise RuntimeError("POSTGRES_NO_DISPONIBLE")

        solicitudes = SolicitudesFalsas([solicitud()])
        self.servicio(solicitudes, ejecutar).atender_una()
        self.assertEqual(solicitudes.final["estado"], "FALLIDA")
        self.assertIn("POSTGRES_NO_DISPONIBLE", solicitudes.final["mensaje"])

    def test_falla_de_subida_no_pierde_el_resultado_del_lote(self):
        (self.lote / "reporte_final.xlsx").write_bytes(b"final")
        storage = StorageFalso()
        storage.subir = MagicMock(side_effect=RuntimeError("STORAGE_SUBIDA_HTTP_500"))
        solicitudes = SolicitudesFalsas([solicitud()])
        self.servicio(solicitudes, storage=storage).atender_una()
        self.assertEqual(solicitudes.final["estado"], "COMPLETADA")
        self.assertIsNone(solicitudes.final["resultado_ruta"])
        self.assertIn("STORAGE_SUBIDA_HTTP_500", solicitudes.final["mensaje"])

    def test_ejecutar_una_vez_cierra_interrumpidas_y_atiende(self):
        solicitudes = SolicitudesFalsas([])
        self.servicio(solicitudes).ejecutar(una_vez=True)
        self.assertEqual(solicitudes.cerradas_para, "servidor")


class TestVerificarExcelSeguro(unittest.TestCase):
    def test_acepta_un_xlsx_normal(self):
        verificar_excel_seguro(EXCEL_PRUEBA)

    def test_rechaza_lo_que_no_es_xlsx(self):
        with self.assertRaisesRegex(ErrorSolicitud, "NO_ES_XLSX"):
            verificar_excel_seguro(b"esto no es un excel")

    def test_rechaza_una_bomba_de_compresion(self):
        bomba = paquete_zip({"xl/sharedStrings.xml": "0" * (5 * 1024 * 1024)})
        with self.assertRaisesRegex(ErrorSolicitud, "EXCEL_SOSPECHOSO"):
            verificar_excel_seguro(bomba)

    def test_rechaza_archivos_demasiado_grandes(self):
        with patch("src.servicio_portal.MAXIMO_EXCEL_BYTES", 10):
            with self.assertRaisesRegex(ErrorSolicitud, "EXCEL_DEMASIADO_GRANDE"):
                verificar_excel_seguro(EXCEL_PRUEBA)


class TestCodigoPublico(unittest.TestCase):
    def test_conserva_codigos_estables(self):
        self.assertEqual(codigo_publico("POSTGRES_NO_DISPONIBLE"), "POSTGRES_NO_DISPONIBLE")
        self.assertEqual(codigo_publico(ValueError("COLUMNAS_FALTANTES:SUCURSAL, ESTADO")),
                         "COLUMNAS_FALTANTES:SUCURSAL, ESTADO")

    def test_oculta_rutas_y_detalles_internos(self):
        self.assertEqual(codigo_publico(r"DESTINO_YA_EXISTE:C:\Users\HP\outputs\lote"),
                         "DESTINO_YA_EXISTE")
        self.assertEqual(
            codigo_publico('connection to server at "db.x.supabase.co" (1.2.3.4), port 5432 failed'),
            "ERROR_INTERNO",
        )
        self.assertEqual(codigo_publico("", "STORAGE_NO_DISPONIBLE"), "STORAGE_NO_DISPONIBLE")


class TestServicioRechazaExcelInseguro(unittest.TestCase):
    def test_no_prepara_un_archivo_que_no_es_xlsx(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        storage = MagicMock()
        storage.descargar.return_value = b"no es zip"
        preparar = MagicMock()
        solicitudes = SolicitudesFalsas([solicitud()])
        ServicioPortal(
            solicitudes, storage, preparar_lote=preparar, ejecutar_lote=MagicMock(),
            directorio=Path(temporal.name), worker_host="servidor",
        ).atender_una()
        preparar.assert_not_called()
        self.assertEqual(solicitudes.final["estado"], "RECHAZADA")
        self.assertEqual(solicitudes.final["mensaje"], "EXCEL_INVALIDO:NO_ES_XLSX")


class TestVigilanteCancelacion(unittest.TestCase):
    def test_no_interrumpe_si_no_hay_cancelacion(self):
        interrupcion = MagicMock()
        with VigilanteCancelacion(SolicitudesFalsas(), ID, 0.01, interrupcion):
            time.sleep(0.05)
        interrupcion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
