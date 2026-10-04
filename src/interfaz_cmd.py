"""Menú navegable para usar el sistema judicial desde una terminal Windows."""

from __future__ import annotations

import getpass
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


class InterfazCMD:
    AZUL = "38;2;48;96;145"
    TURQUESA = "38;2;79;211;206"
    DORADO = "38;2;242;190;98"
    VERDE = "38;2;111;216;158"
    ROJO = "38;2;248;119;128"
    SUAVE = "38;2;159;177;197"
    BLANCO = "38;2;242;247;251"

    def __init__(self, api):
        self.api = api
        self.perfil: Path | None = None
        self.interactiva = sys.stdin.isatty() and sys.stdout.isatty()
        self.ansi = self._activar_ansi() if self.interactiva else False
        try:
            "╭─╮│▸↑↓".encode(sys.stdout.encoding or "utf-8")
            self.unicode = True
        except UnicodeEncodeError:
            self.unicode = False

    @staticmethod
    def _activar_ansi() -> bool:
        if os.name != "nt":
            return True
        try:
            import ctypes

            kernel = ctypes.windll.kernel32
            salida = kernel.GetStdHandle(-11)
            modo = ctypes.c_ulong()
            if kernel.GetConsoleMode(salida, ctypes.byref(modo)):
                return bool(kernel.SetConsoleMode(salida, modo.value | 0x0004))
        except (AttributeError, OSError):
            pass
        return False

    def _tono(self, texto: str, codigo: str) -> str:
        return f"\x1b[{codigo}m{texto}\x1b[0m" if self.ansi else texto

    @property
    def _ancho(self) -> int:
        return max(52, min(98, shutil.get_terminal_size((88, 30)).columns - 2))

    def _recortar(self, texto: str, limite: int) -> str:
        texto = str(texto)
        return texto if len(texto) <= limite else texto[:limite - 1] + "…"

    def _fila(self, texto: str = "", *, tono: str | None = None, foco: bool = False) -> None:
        interior = self._ancho - 2
        contenido = (" " + self._recortar(texto, interior - 2)).ljust(interior)
        if foco and self.ansi:
            contenido = self._tono(contenido, "48;2;36;123;145;38;2;255;255;255;1")
        elif tono:
            contenido = self._tono(contenido, tono)
        lado = "│" if self.unicode else "|"
        print(self._tono(lado, self.AZUL) + contenido + self._tono(lado, self.AZUL))

    def _borde(self, izquierda: str, centro: str, derecha: str) -> None:
        if not self.unicode:
            izquierda, centro, derecha = "+", "-", "+"
        print(self._tono(izquierda + centro * (self._ancho - 2) + derecha, self.AZUL))

    def _pantalla(self, titulo: str, detalle: str = "") -> None:
        if self.ansi:
            print("\x1b[2J\x1b[H", end="")
        else:
            print("\n")
        self._borde("╭", "─", "╮")
        self._fila("  S I S T E M A   J U D I C I A L", tono=self.TURQUESA)
        self._fila("  Centro de control  /  e-SATJE", tono=self.SUAVE)
        self._borde("├", "─", "┤")
        self._fila("  " + titulo.upper(), tono=self.DORADO)
        if detalle:
            self._fila("  " + detalle, tono=self.SUAVE)
        self._fila()

    def _dato(self, etiqueta: str, valor: object, *, alerta: bool = False) -> None:
        color = self.ROJO if alerta else self.VERDE
        print("  " + self._tono(f"{etiqueta:<22}", self.SUAVE) + self._tono(str(valor), color))

    def _progreso(self, completos: int, total: int) -> str:
        proporcion = min(1.0, max(0.0, completos / total)) if total else 0.0
        llenos = round(proporcion * 24)
        marca = "█" if self.unicode else "#"
        vacio = "░" if self.unicode else "."
        barra = self._tono(marca * llenos, self.VERDE) + self._tono(vacio * (24 - llenos), self.SUAVE)
        return f"  {barra}  {proporcion:.0%}"

    def _pausa(self) -> None:
        try:
            input("\nPulsa Enter para volver al menú...")
        except EOFError:
            pass

    def _seleccionar(self, titulo: str, opciones: list[str], detalle: str = "",
                    descripciones: list[str] | None = None) -> int | None:
        if not opciones:
            return None
        actual = 0
        while True:
            self._pantalla(titulo, detalle)
            alto = shutil.get_terminal_size((88, 30)).lines
            visibles = max(5, min(12, (alto - 11) // (2 if descripciones else 1)))
            inicio = max(0, min(actual - visibles // 2, len(opciones) - visibles))
            fin = min(len(opciones), inicio + visibles)
            if inicio:
                self._fila(f"    {'↑' if self.unicode else '^'} {inicio} opciones anteriores", tono=self.SUAVE)
            for indice in range(inicio, fin):
                foco = indice == actual
                marca = ("▸" if self.unicode else ">") if foco else " "
                self._fila(f"  {marca} {indice + 1:02}   {opciones[indice]}",
                           tono=self.BLANCO if foco else self.SUAVE, foco=foco)
                if descripciones and indice < len(descripciones):
                    self._fila("          " + descripciones[indice],
                               tono=self.TURQUESA if foco else self.SUAVE, foco=foco)
            if fin < len(opciones):
                self._fila(f"    {'↓' if self.unicode else 'v'} {len(opciones) - fin} opciones más", tono=self.SUAVE)
            self._fila()
            self._borde("╰", "─", "╯")
            flechas = "↑ ↓" if self.unicode else "^ v"
            print(self._tono(f"  {flechas} mover    Enter abrir    0 / Esc volver", self.TURQUESA))
            if not self.interactiva or os.name != "nt":
                try:
                    respuesta = input("  Opción: ").strip()
                except EOFError:
                    return None
                if respuesta in {"0", ""}:
                    return None
                if respuesta.isdigit() and 1 <= int(respuesta) <= len(opciones):
                    return int(respuesta) - 1
                continue
            import msvcrt

            tecla = msvcrt.getwch()
            if tecla in ("\x00", "\xe0"):
                direccion = msvcrt.getwch()
                if direccion == "H":
                    actual = (actual - 1) % len(opciones)
                elif direccion == "P":
                    actual = (actual + 1) % len(opciones)
                elif direccion == "G":
                    actual = 0
                elif direccion == "O":
                    actual = len(opciones) - 1
            elif tecla in ("\r", "\n"):
                return actual
            elif tecla in ("\x1b", "0"):
                return None
            elif tecla.isdigit() and 1 <= int(tecla) <= min(len(opciones), 9):
                return int(tecla) - 1

    @staticmethod
    def _ruta_pegada(texto: str) -> Path:
        return Path(texto.strip().strip('"').strip("'")).expanduser().resolve()

    def _elegir_excel(self) -> Path | None:
        carpeta = Path.home() / "Downloads"
        if not carpeta.is_dir():
            carpeta = Path.cwd()
        while True:
            try:
                carpetas = sorted((p for p in carpeta.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
                excels = sorted((p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == ".xlsx"
                                 and not p.name.startswith("~$")), key=lambda p: p.name.lower())
            except OSError as exc:
                self._pantalla("No se pudo abrir la carpeta")
                print(exc)
                self._pausa()
                return None
            entradas = [("Pegar ruta de un Excel", None), (".. Carpeta anterior", carpeta.parent)]
            entradas += [(f"[Carpeta] {p.name}", p) for p in carpetas]
            entradas += [(f"[Excel] {p.name}", p) for p in excels]
            indice = self._seleccionar("Selecciona el Excel", [e[0] for e in entradas], str(carpeta))
            if indice is None:
                return None
            if indice == 0:
                ruta = self._ruta_pegada(input("Pega la ruta del Excel y pulsa Enter: "))
                if ruta.is_file() and ruta.suffix.lower() == ".xlsx":
                    return ruta
                print("No se encontró un archivo .xlsx en esa ruta.")
                self._pausa()
                continue
            elegido = entradas[indice][1]
            if elegido.is_dir():
                carpeta = elegido
            else:
                return elegido

    def _perfiles(self) -> list[Path]:
        raiz = self.api.RAIZ / "outputs" / "lotes"
        if not raiz.is_dir():
            return []
        return sorted((p for p in raiz.iterdir() if p.is_dir() and (p / "manifiesto.json").is_file()),
                      key=lambda p: p.stat().st_mtime, reverse=True)

    def _elegir_perfil(self) -> Path | None:
        perfiles = self._perfiles()
        entradas = [(f"{p.name}  ({datetime.fromtimestamp(p.stat().st_mtime):%d/%m/%Y %H:%M})", p)
                    for p in perfiles]
        entradas.append(("Pegar ruta de otra carpeta de lote", None))
        indice = self._seleccionar("Selecciona un lote preparado", [e[0] for e in entradas])
        if indice is None:
            return None
        perfil = entradas[indice][1]
        if perfil is None:
            perfil = self._ruta_pegada(input("Pega la carpeta del lote: "))
        if not (perfil / "manifiesto.json").is_file():
            print("Esa carpeta no contiene un manifiesto de lote.")
            self._pausa()
            return None
        self.api._config_perfil(perfil)
        self.api.actualizar_casos(perfil, self.api.CONFIG_COMUN)
        self.perfil = perfil
        return perfil

    def _asegurar_perfil(self) -> Path | None:
        return self.perfil if self.perfil and (self.perfil / "manifiesto.json").is_file() else self._elegir_perfil()

    def _validar(self) -> None:
        excel = self._elegir_excel()
        if excel is None:
            return
        self._pantalla("Validando Excel", excel.name)
        try:
            _, resumen = self.api.leer_y_validar(excel)
            self._dato("Hoja detectada", resumen["hoja"])
            self._dato("Encabezado", f"fila {resumen['fila_encabezado']}")
            self._dato("Filas", resumen["filas"])
            self._dato("Causas únicas", resumen["causas_unicas"])
            self._dato("Filas activas", resumen["activas"])
            print("\n  " + self._tono("[OK] Estructura lista para preparar un lote.", self.VERDE))
        except (OSError, ValueError, KeyError) as exc:
            print("  " + self._tono(f"[ERROR] No se pudo validar: {exc}", self.ROJO))
        self._pausa()

    def _preparar(self) -> None:
        excel = self._elegir_excel()
        if excel is None:
            return
        self._pantalla("Preparando lote", excel.name)
        try:
            _, resumen = self.api.leer_y_validar(excel)
            nombre = re.sub(r"[^a-zA-Z0-9]+", "_", excel.stem).strip("_").lower()[:34] or "lote"
            base = self.api.RAIZ / "outputs" / "lotes"
            salida = base / f"{nombre}_{resumen['sha256'][:12]}"
            self._dato("Filas", resumen["filas"])
            self._dato("Causas únicas", resumen["causas_unicas"])
            self._dato("Filas activas", resumen["activas"])
            print("\n  " + self._tono("DESTINO", self.DORADO))
            print(f"  {salida}")
            if self._seleccionar("Crear lote", ["Crear lote y seleccionarlo", "Volver"], excel.name) != 0:
                return
            resultado = self.api.preparar(excel, salida, self.api.CONFIG_COMUN)
            self.perfil = Path(resultado["directorio"])
            self._pantalla("Lote preparado")
            self._dato("Filas guardadas", resultado["filas"])
            self._dato("Causas únicas", resultado["causas_unicas"])
            self._dato("Lote activo", self.perfil.name)
            mensaje = ("[OK] Excel conocido: se reabrió el lote sin borrar avances."
                       if resultado["reutilizado"] else "[OK] Revisa la conexión y luego ejecuta un piloto.")
            print("\n  " + self._tono(mensaje, self.VERDE))
        except (OSError, ValueError, KeyError) as exc:
            print(f"No se pudo preparar: {exc}")
        self._pausa()

    def _configurar_conexion(self) -> None:
        tipo = self._seleccionar("Conexión PostgreSQL", ["Servidor en este equipo", "Servidor remoto", "Solo cargar contraseña"])
        if tipo is None:
            return
        config = self.api.cargar_comun(self.api.CONFIG_COMUN)
        db = dict(config["base_de_datos"])
        if tipo in (0, 1):
            actual = db.get("host", "localhost")
            host = "localhost" if tipo == 0 else input(f"Servidor [{actual}]: ").strip() or actual
            db["host"] = host
            for campo, etiqueta, defecto in (
                ("puerto", "Puerto", "5432"),
                ("nombre_db", "Base de datos", "casos_judiciales"),
                ("usuario", "Usuario", "judicial_app"),
            ):
                actual = str(db.get(campo, defecto))
                valor = input(f"{etiqueta} [{actual}]: ").strip() or actual
                db[campo] = int(valor) if campo == "puerto" else valor
            if tipo == 1:
                db["sslmode"] = "verify-full"
                certificado = input("Ruta del certificado CA (Enter si ya está configurado): ").strip().strip('"')
                if certificado:
                    db["sslrootcert"] = certificado
            else:
                db["sslmode"] = "prefer"
                db["sslrootcert"] = ""
            config["base_de_datos"] = db
            self.api.guardar_json_atomico(self.api.CONFIG_COMUN, config)
        secreto = getpass.getpass("Contraseña PostgreSQL (no se mostrará): ")
        if secreto:
            os.environ["POSTGRES_PASSWORD"] = secreto
        self._pantalla("Conexión configurada para esta sesión")
        self._dato("Servidor", db.get("host", "localhost"))
        self._dato("Base", db.get("nombre_db", "casos_judiciales"))
        self._dato("TLS", db.get("sslmode", "predeterminado local"))
        print("\n  La contraseña queda solo en esta sesión.")
        self._pausa()

    def _asegurar_clave(self, variable: str, etiqueta: str) -> bool:
        if os.getenv(variable):
            return True
        secreto = getpass.getpass(f"{etiqueta} (no se mostrará): ")
        if not secreto:
            print(f"Falta {etiqueta}; operación cancelada.")
            self._pausa()
            return False
        os.environ[variable] = secreto
        return True

    def _diagnostico(self) -> None:
        perfil = self._asegurar_perfil()
        if not perfil:
            return
        if not self._asegurar_clave("POSTGRES_PASSWORD", "Contraseña PostgreSQL"):
            return
        self._pantalla("Diagnóstico PostgreSQL", perfil.name)
        try:
            datos = self.api.diagnostico(self.api._config_perfil(perfil))
            self._dato("Servidor", datos["servidor"])
            self._dato("Base", datos["base"])
            self._dato("TLS", datos["tls"])
            self._dato("Conexión", "correcta" if datos["conexion"] else "fallida",
                       alerta=not datos["conexion"])
            self._dato("Esquema", "completo" if datos["esquema_completo"] else "incompleto",
                       alerta=not datos["esquema_completo"])
            self._dato("Auditoría config", "lista" if datos["auditoria_config"] else "migración 003 pendiente",
                       alerta=not datos["auditoria_config"])
        except Exception as exc:
            print(f"No se pudo conectar: {exc}")
        self._pausa()

    def _actualizar_esquema(self) -> None:
        perfil = self._asegurar_perfil()
        if not perfil or not self._asegurar_clave("POSTGRES_PASSWORD", "Contraseña PostgreSQL"):
            return
        config = self.api._config_perfil(perfil)
        db = config["base_de_datos"]
        servidor = db.get("host", "localhost")
        base = db.get("nombre_db", "casos_judiciales")
        self._pantalla("Actualizar esquema PostgreSQL", f"{servidor} / {base}")
        print("  Se aplicará únicamente la migración 003 si está pendiente.")
        print("  Usa una cuenta que sea propietaria de las tablas de esta base.")
        if self._seleccionar("Aplicar migraciones", ["Aplicar ahora", "Volver sin cambios"]) != 0:
            return
        usuario = input("Usuario administrador [postgres]: ").strip() or "postgres"
        secreto = getpass.getpass("Contraseña administrativa (no se guardará): ")
        try:
            self.api.aplicar_migraciones(config, usuario, secreto)
            print("\n  " + self._tono("[OK] Migraciones aplicadas.", self.VERDE))
        finally:
            del secreto
        self._pausa()

    def _consultar(self, errores: bool) -> None:
        perfil = self._asegurar_perfil()
        if not perfil:
            return
        if not self._asegurar_clave("POSTGRES_PASSWORD", "Contraseña PostgreSQL"):
            return
        self._pantalla("Errores y revisiones" if errores else "Estado de ejecuciones", perfil.name)
        try:
            filas = self.api.ejecuciones(self.api._config_perfil(perfil), 20, errores)
            if not filas:
                print("No hay registros para este lote.")
            for fila in filas:
                if errores:
                    print("  " + self._tono(f"{fila['numero_causa']}  {fila['estado']}", self.DORADO)
                          + f"  intentos={fila['intentos']}")
                    if fila.get("ultimo_error"):
                        print("  " + str(fila["ultimo_error"])[:180])
                else:
                    print("  " + self._tono(str(fila["estado"]), self.VERDE) + f"  {fila['id']}")
                    total = fila["total_esperado"]
                    completos = fila["atendidos"] + fila["errores_finales"]
                    print(self._progreso(completos, total))
                    print(f"  Pendientes: {fila['pendientes']}  En proceso: {fila['en_proceso']}")
                    print(f"  Atendidos: {fila['atendidos']}  Errores finales: {fila['errores_finales']}")
        except Exception as exc:
            print(f"No se pudo consultar: {exc}")
        self._pausa()

    def _ejecutar(self) -> None:
        perfil = self._asegurar_perfil()
        if not perfil:
            return
        modo = self._seleccionar("Procesar causas", [
            "Piloto: una causa", "Lote pequeño: 10 causas", "Lote: 50 causas",
            "Todas las causas activas", "Continuar pendientes de este lote",
        ], perfil.name)
        if modo is None:
            return
        argumentos = ["ejecutar", str(perfil)]
        if modo == 0:
            from src.gestor_casos import GestorCasos

            try:
                gestor = GestorCasos(str(self.api.CONFIG_COMUN),
                                    config_efectiva=self.api._config_perfil(perfil))
                causas = list(dict.fromkeys(gestor.obtener_casos_pendientes()))
            except (OSError, ValueError, KeyError) as exc:
                print(f"No se pudo leer el lote: {exc}")
                self._pausa()
                return
            opciones = [f"{causa}" for causa in causas[:30]]
            opciones.append("Escribir otro número de causa")
            indice = self._seleccionar("Elige la causa piloto", opciones, perfil.name)
            if indice is None:
                return
            causa = causas[indice] if indice < len(opciones) - 1 else input("Número de causa: ").strip()
            argumentos += ["--solo", causa, "--workers", "1"]
            descripcion = f"Una causa: {causa}"
        else:
            if modo in (1, 2):
                argumentos += ["--lote", "10" if modo == 1 else "50"]
            else:
                argumentos.append("--pendientes")
            if modo == 4:
                argumentos.append("--continuar")
            workers = self._seleccionar("Trabajadores", ["1 trabajador", "2 trabajadores", "3 trabajadores", "4 trabajadores"])
            if workers is None:
                return
            argumentos += ["--workers", str(workers + 1)]
            descripcion = ["", "10 causas", "50 causas", "Todas las causas", "Pendientes de este lote"][modo]
        if not self._asegurar_clave("POSTGRES_PASSWORD", "Contraseña PostgreSQL"):
            return
        if not self._asegurar_clave("AUTOCAPTCHA_API_KEY", "Clave de 2Captcha"):
            return
        self._pantalla("Revisar ejecución", perfil.name)
        self._dato("Modo", descripcion)
        self._dato("Trabajadores", argumentos[-1])
        self._dato("Servidor", self.api.cargar_comun(self.api.CONFIG_COMUN)["base_de_datos"].get("host", "localhost"))
        print("\n  El navegador consultará e-SATJE y actualizará la base y los reportes.")
        if self._seleccionar("Iniciar procesamiento", ["Iniciar ahora", "Volver sin ejecutar"]) != 0:
            return
        self._pantalla("Procesamiento en curso", "Ctrl+C detiene la ejecución de forma controlada")
        try:
            codigo = self.api.main(argumentos)
            print("\nEjecución terminada." if codigo == 0 else f"\nLa ejecución terminó con código {codigo}.")
        except KeyboardInterrupt:
            print("\nEjecución interrumpida; revisa Estado y Errores antes de reanudar.")
        self._pausa()

    def iniciar(self) -> int:
        acciones = [
            ("Seleccionar lote preparado", self._elegir_perfil),
            ("Elegir Excel y preparar lote", self._preparar),
            ("Validar Excel", self._validar),
            ("Configurar conexión PostgreSQL", self._configurar_conexion),
            ("Comprobar conexión y esquema", self._diagnostico),
            ("Aplicar migraciones pendientes", self._actualizar_esquema),
            ("Procesar causas", self._ejecutar),
            ("Ver estado de ejecuciones", lambda: self._consultar(False)),
            ("Revisar errores y causas pendientes", lambda: self._consultar(True)),
        ]
        descripciones = [
            "Recupera un lote anterior y consulta su progreso.",
            "Detecta columnas y crea el espacio de trabajo automáticamente.",
            "Comprueba un archivo sin cambiarlo.",
            "Host, base, TLS y contraseña para esta sesión.",
            "Verifica el servidor y las tablas necesarias.",
            "Actualiza la base con una credencial administrativa temporal.",
            "Elige causa piloto, lote pequeño o pendientes.",
            "Muestra avances y resultados de cada corrida.",
            "Inspecciona causas que requieren atención.",
            "Cierra el centro de control.",
        ]
        while True:
            lote = self.perfil.name if self.perfil else "ninguno seleccionado"
            servidor = self.api.cargar_comun(self.api.CONFIG_COMUN)["base_de_datos"].get("host", "localhost")
            indice = self._seleccionar("Menú principal", [a[0] for a in acciones] + ["Salir"],
                                       f"Lote: {lote}  |  PostgreSQL: {servidor}", descripciones)
            if indice is None or indice == len(acciones):
                return 0
            try:
                acciones[indice][1]()
            except (EOFError, KeyboardInterrupt):
                print("\nOperación cancelada.")
                if not self.interactiva:
                    return 0
            except (OSError, ValueError, KeyError) as exc:
                print("\n" + self._tono(f"[ERROR] {exc}", self.ROJO))
                self._pausa()
