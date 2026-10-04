"""Selección de causas y división de lotes para los modos públicos de la CLI."""


TAMANO_BLOQUE_NAVEGADOR = 10
MAXIMO_LOTE = 100


def _causa_comparable(valor):
    return str(valor or "").replace("-", "").strip()


def dividir_en_bloques(casos, tamano_bloque=TAMANO_BLOQUE_NAVEGADOR):
    """Divide un lote largo en sesiones acotadas de navegador."""
    if tamano_bloque < 1:
        raise ValueError("TAMANO_BLOQUE_INVALIDO")
    return [
        list(casos[indice:indice + tamano_bloque])
        for indice in range(0, len(casos), tamano_bloque)
    ]


def seleccionar_casos(casos, argumentos):
    """Aplica modos acotados o el inicio legado sin ampliar silenciosamente el lote."""
    argumentos = list(argumentos or [])
    if not argumentos:
        return list(casos)
    if argumentos[0] == "--solo":
        if len(argumentos) != 2 or not argumentos[1].strip():
            raise ValueError("USO_INVALIDO: --solo <causa>")
        objetivo = _causa_comparable(argumentos[1])
        coincidencia = next(
            (causa for causa in casos if _causa_comparable(causa) == objetivo), None
        )
        if coincidencia is None:
            raise ValueError(f"CAUSA_SOLO_NO_ENCONTRADA:{argumentos[1]}")
        return [coincidencia]
    if argumentos[0] == "--pendientes":
        if len(argumentos) != 1:
            raise ValueError("USO_INVALIDO: --pendientes")
        return list(casos)
    if argumentos[0] == "--reprocesar-filtro":
        if len(argumentos) != 1:
            raise ValueError("USO_INVALIDO: --reprocesar-filtro")
        resultado = []
        vistos = set()
        for causa in casos:
            comparable = _causa_comparable(causa)
            if comparable and comparable not in vistos:
                vistos.add(comparable)
                resultado.append(causa)
        return resultado
    if argumentos[0] == "--lote":
        if len(argumentos) < 2:
            raise ValueError("USO_INVALIDO: --lote <cantidad 2..100>")
        try:
            cantidad = int(argumentos[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("USO_INVALIDO: --lote <cantidad 2..100>") from exc
        if cantidad < 2 or cantidad > MAXIMO_LOTE:
            raise ValueError("LOTE_FUERA_DE_RANGO:2..100")
        if len(argumentos) == 2:
            return list(casos)[:cantidad]
        excluidas = set()
        restantes = argumentos[2:]
        while restantes:
            if len(restantes) < 2 or restantes[0] != "--excluir":
                raise ValueError("USO_INVALIDO: --lote <cantidad> [--excluir <causa> ...]")
            causa = _causa_comparable(restantes[1])
            if not causa:
                raise ValueError("CAUSA_EXCLUIDA_INVALIDA")
            excluidas.add(causa)
            restantes = restantes[2:]
        resultado = []
        vistos = set()
        for causa in casos:
            comparable = _causa_comparable(causa)
            if comparable and comparable not in vistos:
                vistos.add(comparable)
                if comparable not in excluidas:
                    resultado.append(causa)
        if not excluidas.issubset(vistos):
            raise ValueError("CAUSA_EXCLUIDA_NO_ENCONTRADA")
        return resultado[:cantidad]
    if argumentos[0].startswith("--") or len(argumentos) != 1:
        raise ValueError("ARGUMENTOS_INVALIDOS")
    objetivo = _causa_comparable(argumentos[0])
    indice = next(
        (i for i, causa in enumerate(casos) if _causa_comparable(causa) == objetivo),
        None,
    )
    return list(casos) if indice is None else list(casos[indice:])
