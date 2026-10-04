"""Contratos estables para ejecuciones secuenciales y concurrentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ESTADOS_TERMINALES = frozenset(
    {
        "PROCESADO",
        "PARCIAL",
        "SIN_RESULTADOS",
        "EXCLUIDO_NO_CORRESPONDE",
        "REVISION",
        "ERROR_FINAL",
        "CANCELADO",
    }
)


@dataclass(frozen=True)
class TrabajoCola:
    """Reserva atomica devuelta a un trabajador."""

    id: Any
    numero_causa: str
    intentos: int
    posicion: int = 0


@dataclass
class ResultadoCaso:
    """Resultado independiente de la base de datos y de los reportes."""

    numero_causa: str
    estado: str
    datos: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    origen: str = "ESATJE_TRANSACCIONAL"
    regreso_confirmado: bool = False
    resultado_original: dict[str, Any] = field(default_factory=dict)

    def como_payload(self) -> dict[str, Any]:
        payload = dict(self.resultado_original)
        payload.update(
            {
                "estado": self.estado,
                "datos": dict(self.datos),
                "regreso_confirmado": self.regreso_confirmado,
            }
        )
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class ConfiguracionConcurrencia:
    """Parametros validados del coordinador multiproceso."""

    habilitada: bool = False
    trabajadores: int = 2
    maximo_trabajadores: int = 4
    navegador_visible: bool = True
    exportar_cada: int = 10
    lease_segundos: int = 120
    heartbeat_segundos: int = 30
    maximo_intentos: int = 3
    captcha_max_concurrentes: int = 2
    inicio_escalonado_segundos: float = 2.0
    casos_por_sesion: int = 10

    @classmethod
    def desde_config(cls, config: Mapping[str, Any] | None) -> "ConfiguracionConcurrencia":
        valores = dict(config or {})
        instancia = cls(
            habilitada=bool(valores.get("habilitada", False)),
            trabajadores=int(valores.get("trabajadores", 2)),
            maximo_trabajadores=int(valores.get("maximo_trabajadores", 4)),
            navegador_visible=bool(valores.get("navegador_visible", True)),
            exportar_cada=int(valores.get("exportar_cada", 10)),
            lease_segundos=int(valores.get("lease_segundos", 120)),
            heartbeat_segundos=int(valores.get("heartbeat_segundos", 30)),
            maximo_intentos=int(valores.get("maximo_intentos", 3)),
            captcha_max_concurrentes=int(
                valores.get("captcha_max_concurrentes", 2)
            ),
            inicio_escalonado_segundos=float(
                valores.get("inicio_escalonado_segundos", 2.0)
            ),
            casos_por_sesion=int(valores.get("casos_por_sesion", 10)),
        )
        instancia.validar()
        return instancia

    def validar(self) -> None:
        if not 1 <= self.trabajadores <= self.maximo_trabajadores:
            raise ValueError("TRABAJADORES_FUERA_DE_RANGO")
        if not 1 <= self.maximo_trabajadores <= 16:
            raise ValueError("MAXIMO_TRABAJADORES_INVALIDO")
        if self.exportar_cada < 1:
            raise ValueError("INTERVALO_EXPORTACION_INVALIDO")
        if self.heartbeat_segundos < 1:
            raise ValueError("HEARTBEAT_INVALIDO")
        if self.lease_segundos <= self.heartbeat_segundos * 2:
            raise ValueError("LEASE_DEBE_SUPERAR_DOS_HEARTBEATS")
        if self.maximo_intentos < 1:
            raise ValueError("MAXIMO_INTENTOS_INVALIDO")
        if not 1 <= self.captcha_max_concurrentes <= self.maximo_trabajadores:
            raise ValueError("CAPTCHA_CONCURRENCIA_INVALIDA")
        if self.inicio_escalonado_segundos < 0:
            raise ValueError("INICIO_ESCALONADO_INVALIDO")
        if self.casos_por_sesion < 1:
            raise ValueError("CASOS_POR_SESION_INVALIDO")

    def validar_motor(self, motor: str, trabajadores: int | None = None) -> int:
        cantidad = self.trabajadores if trabajadores is None else int(trabajadores)
        if not 1 <= cantidad <= self.maximo_trabajadores:
            raise ValueError("TRABAJADORES_FUERA_DE_RANGO")
        if cantidad > 1 and str(motor).lower() != "postgres":
            raise RuntimeError("POSTGRES_REQUERIDO_PARA_CONCURRENCIA")
        return cantidad


def extraer_trabajadores(argumentos, predeterminado=1):
    """Extrae ``--workers N`` sin interferir con los modos historicos."""
    restantes = list(argumentos or [])
    if "--workers" not in restantes:
        return int(predeterminado), restantes
    indice = restantes.index("--workers")
    if indice + 1 >= len(restantes):
        raise ValueError("USO_INVALIDO: --workers <cantidad>")
    if restantes.count("--workers") != 1:
        raise ValueError("USO_INVALIDO: --workers solo puede indicarse una vez")
    try:
        cantidad = int(restantes[indice + 1])
    except (TypeError, ValueError) as exc:
        raise ValueError("USO_INVALIDO: --workers <cantidad>") from exc
    return cantidad, restantes[:indice] + restantes[indice + 2 :]
