"""Ejecuta una sola causa en e-SATJE para diagnosticar la navegaci?n visible."""
import json
import os
import sys

RAIZ_PROYECTO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_PROYECTO not in sys.path:
    sys.path.insert(0, RAIZ_PROYECTO)

from src.logger_config import configurar_logging
from src.motor_busqueda_web import BotJudicial


def cargar_navegacion():
    ruta_config = os.path.join(os.path.dirname(__file__), "..", "config.json")
    with open(ruta_config, "r", encoding="utf-8") as archivo:
        return json.load(archivo)["navegacion"]


def main():
    if len(sys.argv) != 2:
        print("Uso: python scripts/diagnosticar_esatje.py 23331-2022-02089")
        return 2

    numero_causa = sys.argv[1].strip()
    navegacion = cargar_navegacion()
    configurar_logging(
        os.path.join(RAIZ_PROYECTO, "diagnostico_esatje.log"),
        reemplazar=True,
    )
    bot = BotJudicial(navegacion["url_portal"], navegacion)

    try:
        bot.iniciar_navegador(modo_visible=True)
        resultado = bot.procesar_flujo_judicatura(numero_causa)
        print(
            "RESULTADO_DIAGNOSTICO "
            + json.dumps(resultado, ensure_ascii=False, default=str)
        )
        estados_confirmados = {
            "COMPLETADO", "PARCIAL", "SIN_RESULTADOS", "EXCLUIDO_NO_CORRESPONDE"
        }
        return 0 if (
            resultado.get("estado") in estados_confirmados
            and resultado.get("regreso_confirmado")
        ) else 1
    finally:
        bot.cerrar_navegador()


if __name__ == "__main__":
    raise SystemExit(main())

