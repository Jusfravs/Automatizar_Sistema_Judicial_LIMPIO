# test_inferencia_casos.py
"""
Pruebas unitarias para validar las reglas de Inferencia Procesal Autónoma
definidas en MODULO_FILTRO_CASOS.md y MOLDE_NUEVOS_CAMBIOS.md (7 reglas de negocio).
"""
import sys
from src.agente_extractor import AgenteExtractor, MotorInferenciaProcesal

def probar_inferencias():
    casos_prueba = [
        {
            "nombre": "1. Presentación de demanda (sin calificación previa -> Carátula de juicio)",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "INGRESO DE CAUSA Y PRESENTACION CON CARATULA DE JUICIO"}
            ],
            "etapa_esperada": "1 PRESENTACION Y CALIFICACION",
            "fase_esperada": "1.1 PRESENTAR DEMANDA"
        },
        {
            "nombre": "2. Completar / Aclarar demanda",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "CARATULA DE JUICIO"},
                {"fecha": "12/01/2024", "detalle": "COMPLETAR Y ACLARAR LA DEMANDA SOLICITADA"}
            ],
            "etapa_esperada": "1 PRESENTACION Y CALIFICACION",
            "fase_esperada": "1.2 COMPLETAR/ACLARAR DEMANDA"
        },
        {
            "nombre": "3. Auto de Calificación de demanda",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "CARATULA DE JUICIO"},
                {"fecha": "15/01/2024", "detalle": "AUTO DE CALIFICACION LA DEMANDA ADMITIDA A TRAMITE"}
            ],
            "etapa_esperada": "1 PRESENTACION Y CALIFICACION",
            "fase_esperada": "1.3 CALIFICACION"
        },
        {
            "nombre": "4. Citación por prensa",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "15/01/2024", "detalle": "AUTO DE CALIFICACION"},
                {"fecha": "20/01/2024", "detalle": "PUBLICACION DE EXTRACTO DE CITACION POR PRENSA EN DIARIO HOY"}
            ],
            "etapa_esperada": "2 CITACION",
            "fase_esperada": "2.2 CITACION POR PRENSA"
        },
        {
            "nombre": "5. Contestación con Calificación -> Inferencia salto a FIJACION FECHA AUDIENCIA",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "15/01/2024", "detalle": "CALIFICACION"},
                {"fecha": "01/02/2024", "detalle": "ESCRITO DE CONTESTACION DE LA DEMANDA Y EXCEPCIONES"},
                {"fecha": "05/02/2024", "detalle": "CALIFICACION DE LA CONTESTACION Y CONVOCATORIA A AUDIENCIA"}
            ],
            "etapa_esperada": "4 AUDIENCIA",
            "fase_esperada": "4.1 FIJACION FECHA AUDIENCIA"
        },
        {
            "nombre": "6. Regla 6 MOLDE: Acuerdo de Mediación antes de Ejecutoria -> 5.3 SENTENCIA EJECUTORIADA",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "20/02/2024", "detalle": "ACTA Y ACUERDO DE MEDIACION ENTRE LAS PARTES"}
            ],
            "etapa_esperada": "5 SENTENCIA",
            "fase_esperada": "5.3 SENTENCIA EJECUTORIADA"
        },
        {
            "nombre": "7. Sentencia Ejecutoriada (Razón)",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/03/2024", "detalle": "SENTENCIA RESOLUCION DEL JUEZ"},
                {"fecha": "15/03/2024", "detalle": "RAZON DE EJECUTORIA Y CAUSA ESTADO"}
            ],
            "etapa_esperada": "5 SENTENCIA",
            "fase_esperada": "5.3 SENTENCIA EJECUTORIADA"
        },
        {
            "nombre": "8. Perito Liquidador (Nombramiento con Informe)",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/04/2024", "detalle": "NOMBRAMIENTO DE PERITO LIQUIDADOR"},
                {"fecha": "10/04/2024", "detalle": "ESCRITO DE INFORME DEL PERITO LIQUIDADOR"}
            ],
            "etapa_esperada": "6 LIQUIDACION Y EMBARGO",
            "fase_esperada": "6.1 LIQUIDACION PERITO LIQUIDADOR"
        },
        {
            "nombre": "9. Regla 1 MOLDE: Remate (Caso Solventado por Remate)",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/05/2024", "detalle": "ACTA DE EMBARGO DE BIENES INMUEBLES"},
                {"fecha": "20/05/2024", "detalle": "FECHA DE PUBLICACION REMATE Y SUBASTA"}
            ],
            "etapa_esperada": "6 LIQUIDACION Y EMBARGO",
            "fase_esperada": "6.4 REMATE"
        },
        {
            "nombre": "10. Regla 1 MOLDE: Congelamiento de cuentas / Oficios de bancos",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/05/2024", "detalle": "EMBARGO"},
                {"fecha": "01/06/2024", "detalle": "AGREGUESE EL OFICIO EMITIDO POR EL BANCO PICHINCHA CON LA RETENCION DE CUENTAS"}
            ],
            "etapa_esperada": "6 LIQUIDACION Y EMBARGO",
            "fase_esperada": "6.5 CONGELAMIENTO DE CUENTAS / CIERRE"
        },
        {
            "nombre": "11. Regla 2 MOLDE: Citación no realizada sin citación exitosa posterior -> Regresa a 1.3 CALIFICACION",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA Y CALIFICACION"},
                {"fecha": "25/01/2024", "detalle": "CITACION NO REALIZADA / RAZON DE ENVIO A CITACIONES"}
            ],
            "etapa_esperada": "1 PRESENTACION Y CALIFICACION",
            "fase_esperada": "1.3 CALIFICACION"
        },
        {
            "nombre": "12. Regla 5 MOLDE: Abandono por falta de impulso con razón de ejecutoria -> Regresa a 1.3 CALIFICACION",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/03/2024", "detalle": "ABANDONO POR FALTA DE IMPULSO PROCESAL"},
                {"fecha": "15/03/2024", "detalle": "RAZON DE EJECUTORIA"}
            ],
            "etapa_esperada": "1 PRESENTACION Y CALIFICACION",
            "fase_esperada": "1.3 CALIFICACION"
        },
        {
            "nombre": "13. Regla 7 MOLDE: Nombramiento de Perito SIN Informe -> 5.3 SENTENCIA EJECUTORIADA",
            "actuaciones": [
                {"fecha": "10/01/2024", "detalle": "DEMANDA"},
                {"fecha": "01/04/2024", "detalle": "NOMBRAMIENTO DE PERITO LIQUIDADOR"}
            ],
            "etapa_esperada": "5 SENTENCIA",
            "fase_esperada": "5.3 SENTENCIA EJECUTORIADA"
        }
    ]

    exitos = 0
    fallos = 0

    print("=" * 70)
    print("EJECUTANDO PRUEBAS DEL MOTOR DE INFERENCIA PROCESAL AUTÓNOMA (MOLDE REGLAS)")
    print("=" * 70)

    for i, test in enumerate(casos_prueba, 1):
        res = MotorInferenciaProcesal.inferir_estado_procesal(test["actuaciones"])
        etapa = res.ultima_etapa
        fase = res.ultima_fase
        fecha = res.fecha_fin_ultima_fase

        cumple_etapa = etapa == test["etapa_esperada"]
        cumple_fase = fase == test["fase_esperada"]

        if cumple_etapa and cumple_fase:
            print(f"[OK] Prueba #{i}: {test['nombre']}")
            print(f"     Etapa: {etapa} | Fase: {fase} | Fecha: {fecha}")
            if res.mensaje_especial:
                print(f"     Mensaje Especial: {res.mensaje_especial}")
            exitos += 1
        else:
            print(f"[FAIL] Prueba #{i}: {test['nombre']}")
            print(f"       Esperado -> Etapa: {test['etapa_esperada']} | Fase: {test['fase_esperada']}")
            print(f"       Obtenido -> Etapa: {etapa} | Fase: {fase}")
            fallos += 1
        print("-" * 70)

    # Validar función calcular_siguiente_fase
    print("\n--- VALIDANDO CÁLCULO DE SIGUIENTE FASE ---")
    sig_etapa, sig_fase = MotorInferenciaProcesal.calcular_siguiente_fase("6.2 MANDAMIENTO DE EJECUCION")
    if sig_fase == "6.3 EMBARGO":
        print(f"[OK] Siguiente de '6.2 MANDAMIENTO DE EJECUCION' -> '{sig_fase}' ({sig_etapa})")
        exitos += 1
    else:
        print(f"[FAIL] Error en siguiente fase: se obtuvo '{sig_fase}'")
        fallos += 1

    print(f"\nRESUMEN: {exitos} exitosas, {fallos} fallidas de {len(casos_prueba) + 1} pruebas.")
    return fallos == 0

if __name__ == "__main__":
    exito = probar_inferencias()
    sys.exit(0 if exito else 1)
