"""Monitorea las interacciones manuales en e-SATJE sin automatizar los clics."""
import argparse
import json
import os
import sys
from time import monotonic

RAIZ_PROYECTO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_PROYECTO not in sys.path:
    sys.path.insert(0, RAIZ_PROYECTO)

from src.logger_config import configurar_logging
from src.motor_busqueda_web import BotJudicial


def cargar_configuracion(ruta_config):
    ruta = os.path.abspath(ruta_config)
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def estado_visible(page):
    return page.evaluate("""() => {
        const campo = document.querySelector("input[formcontrolname='numeroCausa']");
        const boton = [...document.querySelectorAll("button")].find(
            e => e.textContent.trim().toUpperCase() === "BUSCAR"
        );
        return {
            url: location.href,
            causa: campo?.value ?? null,
            captcha: Boolean(document.querySelector(
                "ngx-recaptcha2, textarea[name='g-recaptcha-response'], iframe[title*='recaptcha' i]"
            )),
            buscar: boton ? {
                disabled: boton.disabled,
                aria: boton.getAttribute("aria-label"),
                clase: boton.className,
            } : null,
        };
    }""")


def instalar_monitor(page):
    page.evaluate("""() => {
        window.__monitorEsatjeEventos = [];
        document.addEventListener("click", evento => {
            const objetivo = evento.target;
            const accionable = objetivo.closest(
                "button, a, [role='link'], [role='button'], [mattooltip]"
            );
            const fila = objetivo.closest("tr, mat-row, [role='row'], .fila");
            const describir = nodo => nodo ? {
                etiqueta: nodo.tagName,
                texto: (nodo.innerText || nodo.textContent || "").trim().slice(0, 1000),
                rol: nodo.getAttribute("role"),
                aria: nodo.getAttribute("aria-label"),
                titulo: nodo.getAttribute("title"),
                tooltip: nodo.getAttribute("mattooltip"),
                clase: typeof nodo.className === "string" ? nodo.className : "",
            } : null;
            window.__monitorEsatjeEventos.push({
                instante: new Date().toISOString(),
                objetivo: describir(objetivo),
                accionable: describir(accionable),
                fila: describir(fila),
            });
        }, true);
    }""")


def instalar_monitor_red(page, eventos_red):
    """Registra metadatos de red para descubrir la API de adjuntos sin leer PDFs."""
    def registrar(response):
        try:
            tipo = response.headers.get("content-type", "")
            if response.status < 200 or response.status >= 400:
                return
            url = response.url
            if any(marca in (url + " " + tipo).lower() for marca in (
                "archivo", "document", "adjunto", "download", "pdf", "file"
            )):
                eventos_red.append({
                    "instante": monotonic(),
                    "url": url,
                    "estado": response.status,
                    "content_type": tipo,
                    "metodo": getattr(response.request, "method", None),
                })
        except Exception:
            pass

    page.on("response", registrar)


def extraer_eventos(page):
    return page.evaluate("""() => {
        const eventos = window.__monitorEsatjeEventos || [];
        window.__monitorEsatjeEventos = [];
        return eventos;
    }""")


def guardar_evidencia(page, directorio, causa, indice, evento, estado, red):
    base = os.path.join(directorio, f"monitoreo_{causa}_{indice:03d}")
    with open(f"{base}.json", "w", encoding="utf-8") as archivo:
        json.dump(
            {"evento": evento, "estado": estado, "red": list(red)},
            archivo, ensure_ascii=False, indent=2,
        )
    with open(f"{base}.html", "w", encoding="utf-8") as archivo:
        archivo.write(page.content())
    page.screenshot(path=f"{base}.png", full_page=True)


def main():
    parser = argparse.ArgumentParser(
        description="Monitorea manualmente un expediente e-SATJE."
    )
    parser.add_argument("causa")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    causa_original = args.causa.strip()
    configuracion = cargar_configuracion(args.config)
    navegacion = configuracion["navegacion"]
    configurar_logging(
        os.path.join(RAIZ_PROYECTO, "diagnostico_esatje.log"),
        reemplazar=True,
    )
    # Monitor deliberadamente manual: no usa credenciales ni intenta resolver
    # CAPTCHA. Sirve para que la persona confirme los adjuntos y para registrar
    # la API que los entrega.
    bot = BotJudicial(
        navegacion["url_portal"], navegacion,
        captcha={"modo": "manual", "fallback_manual": True},
    )
    directorio = os.path.join(RAIZ_PROYECTO, "data", "temp_htmls")
    os.makedirs(directorio, exist_ok=True)
    causa = BotJudicial._causa_canonica(causa_original)
    indice = 0
    ultimo_estado = None

    try:
        bot.iniciar_navegador(modo_visible=True)
        bot._preparar_busqueda(causa_original)
        bot.page.bring_to_front()
        instalar_monitor(bot.page)
        eventos_red = []
        instalar_monitor_red(bot.page, eventos_red)
        print("MONITOREO_LISTO: complete CAPTCHA y abra manualmente el archivo PDF relevante.")
        limite = monotonic() + 300
        while monotonic() < limite:
            estado = estado_visible(bot.page)
            if estado != ultimo_estado:
                print("ESTADO", json.dumps(estado, ensure_ascii=False))
                ultimo_estado = estado
            for evento in extraer_eventos(bot.page):
                indice += 1
                guardar_evidencia(
                    bot.page, directorio, causa, indice, evento, estado, eventos_red
                )
                print("EVENTO", indice, json.dumps(evento, ensure_ascii=False))
            bot.page.wait_for_timeout(250)
        return 0
    finally:
        bot.cerrar_navegador()


if __name__ == "__main__":
    raise SystemExit(main())

