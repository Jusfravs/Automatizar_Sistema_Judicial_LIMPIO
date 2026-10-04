import unittest

from src.servicio_captcha import (
    CaptchaCredencialError,
    CaptchaDesafio,
    CaptchaProveedorError,
    CaptchaResolucionTimeout,
    CaptchaSolucion,
    Proveedor2Captcha,
    sanear_datos_captcha,
)


class TransporteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def __call__(self, url, contenido, timeout_s):
        self.llamadas.append((url, contenido, timeout_s))
        if not self.respuestas:
            raise AssertionError("TRANSPORTE_SIN_RESPUESTA_PROGRAMADA")
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class TransporteProcesando:
    def __init__(self):
        self.creada = False

    def __call__(self, url, contenido, timeout_s):
        if url.endswith("/createTask"):
            self.creada = True
            return {"errorId": 0, "taskId": 99}
        return {"errorId": 0, "status": "processing"}


class RelojFalso:
    def __init__(self, valores):
        self.valores = iter(valores)

    def __call__(self):
        return next(self.valores)


class ServicioCaptchaTests(unittest.TestCase):
    def desafio(self):
        return CaptchaDesafio(
            tipo="recaptcha_v2",
            website_url="https://portal.example/busqueda",
            sitekey="sitekey-publica",
            widget_id="0",
        )

    def proveedor(self, transporte, **configuracion):
        config = {
            "http_timeout_ms": 1000,
            "resolucion_timeout_ms": 5000,
            "sondeo_ms": 1000,
            **configuracion,
        }
        return Proveedor2Captcha(
            "clave-secreta-de-prueba",
            config,
            transporte=transporte,
            dormir=lambda segundos: None,
        )

    def test_create_processing_ready_devuelve_token_sin_exponerlo(self):
        transporte = TransporteFalso([
            {"errorId": 0, "taskId": 123},
            {"errorId": 0, "status": "processing"},
            {
                "errorId": 0,
                "status": "ready",
                "solution": {"gRecaptchaResponse": "token-super-secreto"},
                "cost": "0.00299",
            },
        ])
        proveedor = self.proveedor(transporte)

        solucion = proveedor.resolver(self.desafio())

        self.assertEqual(solucion.token, "token-super-secreto")
        self.assertEqual(solucion.task_id, 123)
        self.assertEqual(solucion.costo_usd, 0.00299)
        self.assertNotIn("token-super-secreto", repr(solucion))
        self.assertTrue(transporte.llamadas[0][0].endswith("/createTask"))
        self.assertEqual(
            transporte.llamadas[0][1]["task"]["type"],
            "RecaptchaV2TaskProxyless",
        )

    def test_error_de_credencial_se_clasifica_sin_incluir_clave(self):
        transporte = TransporteFalso([{
            "errorId": 1,
            "errorCode": "ERROR_KEY_DOES_NOT_EXIST",
            "errorDescription": "invalid",
        }])
        proveedor = self.proveedor(transporte)

        with self.assertRaises(CaptchaCredencialError) as contexto:
            proveedor.comprobar_disponibilidad()

        self.assertEqual(str(contexto.exception), "ERROR_KEY_DOES_NOT_EXIST")
        self.assertNotIn("clave-secreta-de-prueba", str(contexto.exception))

    def test_saneamiento_redacta_clave_token_y_cookies(self):
        datos = {
            "clientKey": "clave",
            "solution": {"gRecaptchaResponse": "token", "cost": "0.1"},
            "cookies": "sesion=secreta",
        }

        saneado = sanear_datos_captcha(datos)

        self.assertEqual(saneado["clientKey"], "<redactado>")
        self.assertEqual(saneado["solution"]["gRecaptchaResponse"], "<redactado>")
        self.assertEqual(saneado["cookies"], "<redactado>")
        self.assertEqual(saneado["solution"]["cost"], "0.1")

    def test_get_balance_reintenta_error_transitorio_de_red(self):
        error_red = CaptchaProveedorError("CAPTCHA_RED_ERROR", recuperable=True)
        transporte = TransporteFalso([
            error_red,
            CaptchaProveedorError("CAPTCHA_RED_ERROR", recuperable=True),
            {"errorId": 0, "balance": "1.25"},
        ])
        esperas = []
        proveedor = Proveedor2Captcha(
            "clave-secreta-de-prueba",
            {
                "http_timeout_ms": 1000,
                "max_intentos_red": 3,
                "reintento_red_ms": 100,
            },
            transporte=transporte,
            dormir=esperas.append,
        )

        disponibilidad = proveedor.comprobar_disponibilidad()

        self.assertTrue(disponibilidad["disponible"])
        self.assertEqual(disponibilidad["saldo_usd"], 1.25)
        self.assertEqual(len(transporte.llamadas), 3)
        self.assertEqual(esperas, [0.1, 0.2])

    def test_create_task_no_se_reintenta_si_la_respuesta_es_ambigua(self):
        transporte = TransporteFalso([
            CaptchaProveedorError("CAPTCHA_RED_ERROR", recuperable=True),
        ])
        proveedor = self.proveedor(transporte, max_intentos_red=3)

        with self.assertRaisesRegex(CaptchaProveedorError, "CAPTCHA_RED_ERROR"):
            proveedor.resolver(self.desafio())

        self.assertEqual(len(transporte.llamadas), 1)

    def test_timeout_total_no_crea_una_segunda_tarea(self):
        transporte = TransporteProcesando()
        reloj = RelojFalso([0.0, 0.0, 2.0])
        proveedor = Proveedor2Captcha(
            "clave-secreta-de-prueba",
            {
                "http_timeout_ms": 1000,
                "resolucion_timeout_ms": 1000,
                "sondeo_ms": 1000,
            },
            transporte=transporte,
            dormir=lambda segundos: None,
            reloj=reloj,
        )

        with self.assertLogs("src.servicio_captcha", level="INFO") as logs:
            with self.assertRaises(CaptchaResolucionTimeout):
                proveedor.resolver(self.desafio())

        self.assertTrue(transporte.creada)
        salida = "\n".join(logs.output)
        self.assertIn("Tarea 99 creada", salida)
        self.assertIn("sigue processing", salida)
        self.assertNotIn("clave-secreta-de-prueba", salida)

    def test_reporte_es_idempotente(self):
        transporte = TransporteFalso([{"errorId": 0, "status": "success"}])
        proveedor = self.proveedor(transporte)

        self.assertTrue(proveedor.reportar_correcta(123))
        self.assertFalse(proveedor.reportar_correcta(123))
        self.assertEqual(len(transporte.llamadas), 1)

    def test_modelo_solucion_no_muestra_token_en_repr(self):
        solucion = CaptchaSolucion("token", 1, "2captcha", 5000, 0.1)
        self.assertNotIn("token'", repr(solucion))
        self.assertIn("<redactado>", repr(solucion))


if __name__ == "__main__":
    unittest.main()
