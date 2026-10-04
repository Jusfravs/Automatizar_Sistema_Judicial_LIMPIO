import unittest
from src.agente_extractor import AgenteExtractor, MotorInferenciaProcesal
from src.motor_busqueda_web import BotJudicial


class TestClasificacionArbol(unittest.TestCase):
    """
    Suite de pruebas unitarias para la Regla del Árbol Procesal.
    Verifica que la ubicación procesal se base strictly en la jerarquía
    y rama activa del árbol de actuaciones, previniendo falsos positivos por
    palabras clave aisladas.
    """

    def setUp(self):
        self.extractor = AgenteExtractor()

    def test_segmentacion_por_instancia(self):
        """Verifica que las actuaciones se agrupen correctamente por rama de instancia."""
        actuaciones = [
            {"fecha": "01/01/2023", "detalle": "PRESENTACION DE DEMANDA Y ANEXOS"},
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION Y CITESE AL DEMANDADO"},
            {"fecha": "05/06/2023", "detalle": "SEGUNDA INSTANCIA: CORTE PROVINCIAL RECIBE APELACION"},
            {"fecha": "20/06/2023", "detalle": "CORTE PROVINCIAL RESUELVE RECURSO DE APELACION"}
        ]
        
        instancias = MotorInferenciaProcesal._segmentar_por_instancia(actuaciones)
        self.assertIn("PRIMERA INSTANCIA", instancias)
        self.assertIn("SEGUNDA INSTANCIA", instancias)
        self.assertEqual(len(instancias["PRIMERA INSTANCIA"]), 2)
        self.assertEqual(len(instancias["SEGUNDA INSTANCIA"]), 2)

    def test_seleccion_rama_activa(self):
        """Verifica que la rama activa sea la de mayor jerarquía procesal."""
        instancias = {
            "PRIMERA INSTANCIA": [{"fecha": "01/01/2023", "detalle": "CITACION"}],
            "SEGUNDA INSTANCIA": [{"fecha": "10/05/2023", "detalle": "RECURSO DE APELACION EN CORTE PROVINCIAL"}]
        }
        
        nombre_rama, actuaciones_rama = MotorInferenciaProcesal._seleccionar_rama_activa(instancias)
        self.assertEqual(nombre_rama, "SEGUNDA INSTANCIA")
        self.assertEqual(len(actuaciones_rama), 1)

    def test_ejecutivo_en_citacion_no_es_mandamiento(self):
        """
        Un caso de procedimiento EJECUTIVO cuyas actuaciones están en etapa de CITACION
        NO debe clasificarse como MANDAMIENTO DE EJECUCION.
        """
        actuaciones = [
            {"fecha": "01/02/2023", "detalle": "INGRESO DE DEMANDA Y SORTEO"},
            {"fecha": "05/02/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {"fecha": "20/02/2023", "detalle": "BOLETA DE CITACION AL DEMANDADO NOTIFICADA EN SU DOMICILIO"}
        ]
        
        etapa, fase, fecha = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(etapa, "2 CITACION")
        self.assertEqual(fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertNotEqual(etapa, "6 LIQUIDACION Y EMBARGO")
        self.assertNotEqual(fase, "6.2 MANDAMIENTO DE EJECUCION")

    def test_ejecutivo_con_mandamiento_real(self):
        """
        Un caso que contenga explícitamente el auto de 'Mandamiento de ejecución' en sus actuaciones
        SÍ debe clasificarse como MANDAMIENTO DE EJECUCION.
        """
        actuaciones = [
            {"fecha": "01/02/2023", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "20/02/2023", "detalle": "CITACION AL DEMANDADO"},
            {"fecha": "10/05/2023", "detalle": "SENTENCIA EMITIDA POR EL JUEZ DECLARA CON LUGAR"},
            {"fecha": "15/06/2023", "detalle": "AUTO DICTA MANDAMIENTO DE EJECUCION Y ORDEN DE PAGO EN 3 DIAS"}
        ]
        
        etapa, fase, fecha = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(etapa, "6 LIQUIDACION Y EMBARGO")
        self.assertEqual(fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(fecha, "15/06/2023")

    def test_sin_embargo_no_activa_embargo_y_prevalece_perito(self):
        actuaciones = [
            {
                "fecha": "29/11/2024",
                "detalle": (
                    "La condena depende de la conducta procesal. Sin embargo, "
                    "tratandose de pagares corresponde aplicar otra norma."
                ),
            },
            {
                "fecha": "12/08/2025",
                "detalle": "NOMBRAMIENTO DE PERITO LIQUIDADOR",
            },
            {
                "fecha": "27/08/2025",
                "detalle": "SE NOTIFICA EL CONTENIDO DEL INFORME PERICIAL",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(
            resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR"
        )
        self.assertEqual(resultado.fecha_fin_ultima_fase, "12/08/2025")

    def test_sin_embargo_con_html_tampoco_activa_embargo(self):
        actuaciones = [{
            "fecha": "29/11/2024",
            "detalle": "SIN&nbsp;<strong>EMBARGO</strong>, SE ACLARA LA NORMA",
        }]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertNotEqual(resultado.ultima_fase, "6.3 EMBARGO")

    def test_orden_de_embargo_no_equivale_a_medida_ejecutada(self):
        actuaciones = [
            {
                "fecha": "09/05/2025",
                "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)",
            },
            {
                "fecha": "10/05/2025",
                "detalle": "SE ORDENA EL EMBARGO DE LOS BIENES DEL EJECUTADO",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "09/05/2025")

    def test_campos_operativos_envian_la_fase_actual_no_el_hito_previo(self):
        actuaciones = [{
            "fecha": "10/05/2025",
            "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)",
        }]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fase_actual, "6.3 EMBARGO")
        self.assertEqual(resultado.get("FASE_PROCESAL"), "6.3 EMBARGO")
        self.assertEqual(
            resultado.get("ETAPA_PROCESAL"), "6 LIQUIDACION Y EMBARGO"
        )

    def test_medida_negada_en_calificacion_no_activa_embargo(self):
        actuaciones = [{
            "fecha": "22/05/2026",
            "detalle": (
                "SE CALIFICA Y ADMITE LA DEMANDA. NO RESULTA PROCEDENTE "
                "DISPONER MEDIDA DE SECUESTRO O APREHENSION DEL VEHICULO. "
                "CITESE A LA DEMANDADA."
            ),
        }]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")

    def test_medida_de_cuaderno_deprecatorio_no_desplaza_citacion_principal(self):
        actuaciones = [
            {
                "fecha": "27/09/2023",
                "ORIGEN_CARPETA": "principal",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
            },
            {
                "fecha": "10/03/2026",
                "ORIGEN_CARPETA": "principal",
                "detalle": "CITACION: REALIZADA - EN PERSONA",
            },
            {
                "fecha": "10/02/2026",
                "ORIGEN_CARPETA": "deprecatorio_pasaje",
                "detalle": "CARATULA SORTEO DE DEPRECATORIOS",
            },
            {
                "fecha": "19/02/2026",
                "ORIGEN_CARPETA": "deprecatorio_pasaje",
                "detalle": (
                    "PRESENTE DEPRECATORIO. CUMPLASE CON LA DILIGENCIA "
                    "ORDENADA. PARA LA PRACTICA DE LA EJECUCION DEL EMBARGO "
                    "SE DESIGNA ALGUACIL Y DEPOSITARIO."
                ),
            },
            {
                "fecha": "20/02/2026",
                "ORIGEN_CARPETA": "deprecatorio_pasaje",
                "detalle": "ACTA DE EMBARGO E INSCRIPCION DE EMBARGO",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/03/2026")
        self.assertEqual(resultado.fase_actual, "CONTESTACION")

    def test_descripcion_inicial_con_liquidacion_no_activa_fase_6_1(self):
        actuaciones = [
            {
                "fecha": "10/02/2026",
                "detalle": (
                    "RECIBIDO EL PROCESO CIVIL, PROCEDIMIENTO EJECUTIVO, "
                    "ASUNTO: COBRO Y LIQUIDACION DE OBLIGACIONES. "
                    "SEGUIDO POR LA PARTE ACTORA CONTRA LA DEMANDADA."
                ) * 3,
            },
            {
                "fecha": "04/03/2026",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "04/03/2026")

    def test_perito_liquidador_real_sigue_activando_fase_6_1(self):
        actuaciones = [
            {
                "fecha": "24/07/2026",
                "detalle": "NOMBRAMIENTO DE PERITO LIQUIDADOR (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "25/07/2026",
                "detalle": "SE NOTIFICA EL CONTENIDO DEL INFORME PERICIAL",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "24/07/2026")

    def test_factura_en_doc_general_posterior_precisa_fecha_perito(self):
        actuaciones = [
            {
                "fecha": "15/05/2026 10:00",
                "detalle": "NOMBRAMIENTO DE PERITO (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "19/05/2026 14:00",
                "detalle": "ANEXOS, DOC. GENERAL, FEPRESENTACION",
                "TIENE_ADJUNTO": True,
                "NOMBRES_ADJUNTOS": [
                    "CEDULA.pdf", "FACTURA 0904218468001.pdf",
                    "CALIFICACION DE PERITO.pdf",
                ],
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "19/05/2026 14:00")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "fecha_pago_perito")

    def test_escrito_con_factura_posterior_precisa_fecha_perito(self):
        actuaciones = [
            {"fecha": "15/05/2026", "detalle": "ACTA SORTEO PERITO"},
            {
                "fecha": "23/05/2026",
                "detalle": "ESCRITO, FEPRESENTACION",
                "TIENE_ADJUNTO": True,
                "NOMBRES_ADJUNTOS": ["FACTURA PERITO 001-001-000123.pdf"],
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "23/05/2026")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "fecha_pago_perito")

    def test_escrito_generico_sin_factura_no_reemplaza_fecha_nombramiento(self):
        actuaciones = [
            {"fecha": "15/05/2026", "detalle": "NOMBRAMIENTO DE PERITO"},
            {
                "fecha": "23/05/2026",
                "detalle": "ESCRITO, FEPRESENTACION",
                "TIENE_ADJUNTO": True,
                "NOMBRES_ADJUNTOS": ["CEDULA.pdf", "CALIFICACION.pdf"],
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/05/2026")
        self.assertNotEqual(resultado.get("REGLA_APLICADA"), "fecha_pago_perito")

    def test_comprobante_pago_honorarios_perito_precisa_fecha(self):
        actuaciones = [
            {"fecha": "15/05/2026", "detalle": "NOMBRAMIENTO DE PERITO"},
            {
                "fecha": "24/05/2026",
                "detalle": "DOC. GENERAL, FEPRESENTACION",
                "NOMBRES_ADJUNTOS": [
                    "CEDULA.pdf", "PAGO DE SERVICIOS PROFESIONALES.pdf",
                ],
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "24/05/2026")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "fecha_pago_perito")

    def test_pago_generico_no_reemplaza_fecha_nombramiento_perito(self):
        actuaciones = [
            {"fecha": "15/05/2026", "detalle": "NOMBRAMIENTO DE PERITO"},
            {
                "fecha": "24/05/2026",
                "detalle": "DOC. GENERAL, FEPRESENTACION",
                "NOMBRES_ADJUNTOS": ["COMPROBANTE DE PAGO ARANCEL.pdf"],
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/05/2026")
        self.assertNotEqual(resultado.get("REGLA_APLICADA"), "fecha_pago_perito")

    def test_embargo_real_no_retrocede_por_citacion_fallida_antigua(self):
        actuaciones = [
            {"fecha": "26/08/2024", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "10/09/2024", "detalle": "CITACION: NO REALIZADA - DIRECCION INCORRECTA"},
            {"fecha": "10/11/2025", "detalle": "ACTA DE EMBARGO"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.3 EMBARGO")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/11/2025")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "hallazgo_taxonomia")

    def test_ejecutoriado_que_sea_el_auto_no_es_sentencia_ejecutoriada(self):
        actuaciones = [
            {
                "fecha": "04/08/2025",
                "detalle": (
                    "LA DEMANDA SE CALIFICA Y ADMITE A TRAMITE. SE ORDENA LA CITACION. "
                    "EJECUTORIADO QUE SEA EL PRESENTE AUTO, LA PARTE ACTORA DARA "
                    "FACILIDADES PARA OBTENER COPIAS PARA LA CITACION."
                ),
            },
            {
                "fecha": "04/08/2025",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")

    def test_acuerdo_de_mediacion_clasifica_como_sentencia_ejecutoriada(self):
        actuaciones = [{
            "fecha": "05/03/2025",
            "detalle": (
                "EL ACTA DE MEDIACION CON ACUERDO TOTAL TIENE EL EFECTO DE "
                "SENTENCIA EJECUTORIADA Y COSA JUZGADA. SE ARCHIVA LA CAUSA."
            ),
        }]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        # Acuerdo de mediación con efecto de ejecutoria → regla_6 → 5.3
        self.assertEqual(resultado.ultima_etapa, "5 SENTENCIA")
        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "05/03/2025")

    def test_incumplimiento_posterior_no_mueve_fecha_del_mandamiento(self):
        actuaciones = [
            {
                "fecha": "06/04/2023",
                "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)",
            },
            {
                "fecha": "25/05/2023",
                "detalle": (
                    "RAZON: LA PARTE EJECUTADA NO HA PAGADO DENTRO DEL TERMINO "
                    "CONCEDIDO EN EL MANDAMIENTO DE EJECUCION."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "06/04/2023")

    def test_solicitud_de_razon_de_cumplimiento_no_mueve_fecha_mandamiento(self):
        actuaciones = [
            {"fecha": "09/03/2026", "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)"},
            {
                "fecha": "02/04/2026",
                "detalle": (
                    "SE DISPONE QUE EL SECRETARIO SIENTE RAZON SI LA PARTE "
                    "DEMANDADA DIO CUMPLIMIENTO O NO CON EL MANDAMIENTO DE "
                    "EJECUCION ORDENADO EN AUTOS."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "09/03/2026")

    def test_embargo_informado_de_otro_expediente_no_avanza_a_6_3(self):
        actuaciones = [
            {"fecha": "22/05/2023", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "16/05/2024",
                "detalle": (
                    "SE INCORPORA OFICIO Y SE PONE EN CONOCIMIENTO QUE DENTRO DE LA "
                    "CAUSA NRO. 23331-2023-00123 SE HA ORDENADO EL EMBARGO DEL BIEN "
                    "INMUEBLE PARA QUE LOS ACREEDORES HAGAN VALER SUS DERECHOS."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "22/05/2023")

    def test_causa_externa_sin_guiones_no_aporta_embargo(self):
        actuaciones = [
            {"fecha": "22/05/2023", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "16/05/2024",
                "detalle": "DENTRO DE LA CAUSA 23331202300123 SE ORDENO EL EMBARGO.",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa="23331-2020-00001"
        )
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "22/05/2023")

    def test_metadato_de_otra_causa_no_aporta_embargo(self):
        actuaciones = [
            {"fecha": "22/05/2023", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "16/05/2024",
                "CAUSA": "23331-2023-00123",
                "detalle": "SE ORDENA EL EMBARGO DEL BIEN DEL EJECUTADO.",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa="23331-2020-00001"
        )
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "22/05/2023")

    def test_evidencia_externa_que_adelanta_fase_se_ignora_sin_revision_manual(self):
        actuaciones = [
            {"fecha": "22/05/2023", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "16/05/2024",
                "detalle": "DENTRO DE LA CAUSA 23331-2023-00123 SE ORDENO EL EMBARGO.",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa="23331-2020-00001"
        )
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.etapa_actual, "6 LIQUIDACION Y EMBARGO")
        self.assertEqual(resultado.fase_actual, "6.3 EMBARGO")

    def test_ruc_de_trece_digitos_no_se_confunde_con_causa_externa(self):
        actuaciones = [
            {"fecha": "22/05/2023", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "16/05/2024",
                "detalle": "ACTA DE EMBARGO. RUC 1791789806001.",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa="23331-2020-00001"
        )
        self.assertEqual(resultado.ultima_fase, "6.3 EMBARGO")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "16/05/2024")

    def test_nulidad_por_falta_de_citacion_retrocede_a_calificacion(self):
        actuaciones = [
            {"fecha": "15/12/2022", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "30/08/2023", "detalle": "NULIDAD POR FALTA DE CITACION (AUTO INTERLOCUTORIO)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/12/2022")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_segunda_instancia_activa_clasificacion(self):
        """
        Si un caso tiene Primera Instancia en Citación pero la rama de Segunda Instancia registra Apelación,
        la clasificación debe basarse en la rama de Segunda Instancia.
        """
        actuaciones = [
            {"fecha": "01/01/2023", "detalle": "BOLETA DE CITACION"},
            {"fecha": "10/04/2023", "detalle": "SEGUNDA INSTANCIA CORTE PROVINCIAL RECURSO DE APELACION ADMITIDO"}
        ]
        
        etapa, fase, fecha = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(etapa, "5 SENTENCIA")
        self.assertEqual(fase, "5.2 APELACION")

    def test_keyword_en_html_no_sobreescribe_fase_real(self):
        """
        HTML con 'mandamiento de ejecución' en encabezados o menús no debe alterar la clasificación
        si la tabla de actuaciones indica una etapa previa (ej. Audiencia).
        """
        html_con_menu = """
        <html>
        <body>
            <div class="menu-lateral">Procesos de Mandamiento de Ejecución y Cobranzas</div>
            <table>
                <tr><td>10/03/2023</td><td>AUTO SEÑALA FECHA Y HORA PARA AUDIENCIA PRELIMINAR</td></tr>
            </table>
        </body>
        </html>
        """
        resultado = self.extractor.procesar_html_string(html_con_menu)
        self.assertEqual(resultado["ETAPA_PROCESAL"], "4 AUDIENCIA")
        self.assertIn("AUDIENCIA", resultado["FASE_PROCESAL"])
        self.assertNotIn("MANDAMIENTO", resultado["FASE_PROCESAL"])



    def test_regla_2_usa_fecha_de_calificacion_sin_dependencia_del_orden(self):
        actuaciones_base = [
            {"fecha": "16/12/2022", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (RAZON DE NOTIFICACION)"},
            {"fecha": "04/07/2023", "detalle": "CITACION: NO REALIZADA - CAMBIO DE DIRECCION"},
            {"fecha": "01/12/2022", "detalle": "PRESENTACION DE DEMANDA"},
        ]
        ordenes = (
            actuaciones_base,
            list(reversed(actuaciones_base)),
            [actuaciones_base[1], actuaciones_base[2], actuaciones_base[0]],
        )
        for actuaciones in ordenes:
            resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
            self.assertEqual(resultado.ultima_etapa, "1 PRESENTACION Y CALIFICACION")
            self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
            self.assertEqual(resultado.fecha_fin_ultima_fase, "16/12/2022")
            self.assertIn("CALIFICACION DE SOLICITUD", resultado.get("ACTUACION_RESPALDO"))
            self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_regla_2_elige_la_calificacion_mas_reciente(self):
        actuaciones = [
            {"fecha": "16/12/2022", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "10/01/2023", "detalle": "CALIFICACION DE DEMANDA"},
            {"fecha": "04/07/2023", "detalle": "CITACION NO REALIZADA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_etapa, "1 PRESENTACION Y CALIFICACION")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/01/2023")

    def test_regla_2_ignora_mencion_generica_posterior_de_califica(self):
        actuaciones = [
            {"fecha": "19/01/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)"},
            {"fecha": "02/03/2023", "detalle": "CITACION: NO REALIZADA - DESCONOCIDO"},
            {"fecha": "10/03/2026", "detalle": "En un auto posterior el juzgador califica la conducta procesal de las partes."},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "19/01/2023")
        self.assertIn("CALIFICACION DE SOLICITUD", resultado.get("ACTUACION_RESPALDO"))

    def test_abandono_con_ejecutoria_aplica_regla_5(self):
        actuaciones = [
            {"fecha": "19/01/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (RAZON DE NOTIFICACION)"},
            {
                "fecha": "10/03/2026",
                "detalle": (
                    "AUTO QUE DECLARA ABANDONO POR FALTA DE IMPULSO PROCESAL. "
                    "En sus consideraciones califica la conducta de las partes. "
                    "RAZON DE EJECUTORIA."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        # Abandono + RAZON DE EJECUTORIA → Regla 5 → 1.3 CALIFICACION
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_5_abandono_ejecutoria")
        self.assertEqual(resultado.ultima_etapa, "1 PRESENTACION Y CALIFICACION")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")

    def test_citacion_realizada_con_dos_puntos_anula_fallo_anterior(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "04/02/2023", "detalle": "CITACION: NO REALIZADA - CAMBIO DE DIRECCION"},
            {"fecha": "10/02/2023", "detalle": "CITACIÓN: REALIZADA - EN PERSONA"},
            {"fecha": "20/03/2023", "detalle": "SENTENCIA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.1 SENTENCIA EMITIDA POR EL JUEZ")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "20/03/2023")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "hallazgo_taxonomia")

    def test_regla_2_recupera_fecha_calificacion_fuera_de_rama_activa(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "01/02/2023", "detalle": "CORTE NACIONAL - DESPACHO DEPRECATORIO"},
            {"fecha": "04/02/2023", "detalle": "CITACION: NO REALIZADA - CAMBIO DE DIRECCION"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/01/2023")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_regla_2_sin_calificacion_no_hereda_fecha_de_citacion(self):
        actuaciones = [{"fecha": "04/07/2023", "detalle": "CITACION NO REALIZADA"}]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_etapa, "1 PRESENTACION Y CALIFICACION")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertIsNone(resultado.fecha_fin_ultima_fase)
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_boletas_de_notificacion_no_convierten_aclaracion_en_citacion(self):
        actuaciones = [
            {"fecha": "16/01/2023", "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "17/01/2023",
                "detalle": "MEDIANTE BOLETAS JUDICIALES NOTIFIQUE EL AUTO QUE ANTECEDE AL ABOGADO",
            },
            {"fecha": "27/01/2023", "detalle": "ARCHIVO POR NO COMPLETAR DEMANDA (AUTO INTERLOCUTORIO). NOTIFIQUESE."},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        # Archivo por no completar → se reclasifica como 1.2 COMPLETAR/ACLARAR DEMANDA
        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "16/01/2023")

    def test_archivo_por_no_completar_no_desplaza_la_fecha_de_la_orden(self):
        actuaciones = [
            {
                "fecha": "14/01/2026",
                "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "02/02/2026",
                "detalle": "ARCHIVO POR NO COMPLETAR DEMANDA (AUTO INTERLOCUTORIO)",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "14/01/2026")

    def test_archivo_redactado_en_providencia_no_desplaza_fecha_de_completar(self):
        actuaciones = [
            {
                "fecha": "25/02/2026",
                "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "09/04/2026",
                "detalle": (
                    "REVISADA LA DEMANDA SE VERIFICA QUE NO SE HA CUMPLIDO "
                    "CON ACLARAR O COMPLETAR. EN CONSECUENCIA, SE DISPONE EL "
                    "ARCHIVO DE LA CAUSA POR NO COMPLETAR LA DEMANDA."
                ),
            },
            {
                "fecha": "10/04/2026",
                "detalle": "ARCHIVO POR NO COMPLETAR DEMANDA (RAZON DE NOTIFICACION)",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "25/02/2026")

    def test_archivo_por_no_dar_cumplimiento_no_desplaza_auto_inicial(self):
        actuaciones = [
            {
                "fecha": "25/10/2024",
                "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "16/04/2025",
                "detalle": (
                    "SIN QUE LA PARTE ACTORA HAYA DADO CUMPLIMIENTO A LO DISPUESTO, "
                    "SE DISPONE EL ARCHIVO DE LA PRESENTE DEMANDA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "25/10/2024")

    def test_verificacion_secretarial_no_desplaza_orden_de_completar(self):
        actuaciones = [
            {
                "fecha": "31/10/2022",
                "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "16/11/2022",
                "detalle": (
                    "SE DISPONE QUE EL ACTUARIO SIENTE RAZON INDICANDO SI EL "
                    "MEMORIAL PARA COMPLETAR LA DEMANDA FUE PRESENTADO DENTRO "
                    "DEL TERMINO CONCEDIDO."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "31/10/2022")

    def test_advertencia_de_sentencia_en_auto_inicial_no_es_sentencia(self):
        actuaciones = [
            {
                "fecha": "14/07/2026",
                "detalle": (
                    "LA DEMANDA SE CALIFICA DE CLARA Y COMPLETA Y SE ADMITE A TRAMITE. "
                    "EL DEMANDADO SERA CITADO Y PODRA PROPONER EXCEPCIONES; BAJO "
                    "PREVENCION QUE DE NO HACERLO SE PRONUNCIARA INMEDIATAMENTE SENTENCIA."
                ),
            },
            {"fecha": "14/07/2026", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "14/07/2026")

    def test_sentencia_real_sigue_reconocida(self):
        actuaciones = [
            {"fecha": "10/01/2026", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "20/06/2026", "detalle": "SENTENCIA (RESOLUCION)"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.1 SENTENCIA EMITIDA POR EL JUEZ")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "20/06/2026")

    def test_resolucion_generica_en_calificacion_no_es_sentencia(self):
        actuaciones = [{
            "fecha": "14/01/2026",
            "detalle": (
                "VISTOS: LA DEMANDA SE CALIFICA DE CLARA Y COMPLETA Y SE "
                "ADMITE A TRAMITE. RESOLUCION: SE RESUELVE CITAR A LA PARTE "
                "DEMANDADA PARA QUE CONTESTE."
            ),
        }]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")

    def test_cita_legal_sobre_inadmision_dentro_de_sentencia_no_es_terminal(self):
        actuaciones = [
            {"fecha": "10/01/2024", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "30/06/2026",
                "detalle": (
                    "SENTENCIA (RESOLUCION). EN LOS ANTECEDENTES SE TRANSCRIBE "
                    "EL ARTICULO 347: LA OMISION PRODUCIRA LA INADMISION DE LA "
                    "DEMANDA. ADMINISTRANDO JUSTICIA, SE ACEPTA LA DEMANDA."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.1 SENTENCIA EMITIDA POR EL JUEZ")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "30/06/2026")

    def test_orden_de_elaborar_boletas_no_significa_citacion_realizada(self):
        actuaciones = [
            {"fecha": "14/01/2026", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "14/01/2026",
                "detalle": (
                    "SE DISPONE ELABORAR LAS BOLETAS DE CITACION Y, UNA VEZ "
                    "REMITIDAS LAS COPIAS, SE PROCEDERA CON LA CITACION ORDENADA."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")

    def test_razon_posterior_que_menciona_auto_inicial_no_mueve_fecha_calificacion(self):
        actuaciones = [
            {"fecha": "14/01/2026", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "29/01/2026",
                "detalle": (
                    "RAZON: PONGO EN CONOCIMIENTO EL EXTRACTO DE LA DEMANDA "
                    "Y AUTO INICIAL."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "14/01/2026")

    def test_estado_de_abandono_con_ejecutoriado_aplica_regla_5(self):
        actuaciones = [
            {"fecha": "20/01/2015", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "09/02/2017",
                "detalle": (
                    "LA PRESENTE CAUSA SE ENCUENTRA EN ESTADO DE ABANDONO; "
                    "EJECUTORIADO EL PRESENTE AUTO, ORDENO EL ARCHIVO "
                    "DEFINITIVO DEL PROCESO."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        # Abandono + EJECUTORIADO → Regla 5 → 1.3 CALIFICACION
        self.assertEqual(resultado.ultima_etapa, "1 PRESENTACION Y CALIFICACION")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")

    def test_citacion_real_prevalece_sobre_advertencia_de_sentencia(self):
        actuaciones = [
            {
                "fecha": "18/12/2025",
                "detalle": (
                    "LA DEMANDA SE CALIFICA Y SE ADMITE A TRAMITE. EL DEMANDADO PODRA "
                    "PROPONER EXCEPCIONES; DE NO HACERLO SE PRONUNCIARA SENTENCIA."
                ),
            },
            {"fecha": "18/12/2025", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "13/05/2026", "detalle": "CITACION: REALIZADA - BOLETA FIJADA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "13/05/2026")
        self.assertEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertEqual(resultado.fase_actual, "CONTESTACION")

    def test_actas_de_citacion_completas_prevalecen_sobre_mencion_posterior(self):
        actuaciones = [
            {"fecha": "11/12/2017", "detalle": "CALIFICACION DE DEMANDA"},
            {
                "fecha": "03/09/2021 10:26",
                "detalle": "CITACI\u00d3N: Realizada - BOLETA FIJADA",
            },
            {
                "fecha": "03/09/2021 10:27",
                "detalle": "CITACI\u00d3N: Realizada - BOLETA FIJADA",
            },
            {
                "fecha": "19/10/2022",
                "detalle": (
                    "POR CUANTO CONSTAN LAS ACTAS DE CITACI\u00d3N REALIZADA A "
                    "LOS DOS DEMANDADOS EL 03 DE SEPTIEMBRE DE 2021."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "03/09/2021 10:27")

    def test_citaciones_posteriores_de_cada_demandado_resuelven_fallos_anteriores(self):
        actuaciones = [
            {"fecha": "11/12/2017", "detalle": "CALIFICACION DE DEMANDA"},
            {
                "fecha": "18/11/2020",
                "detalle": "NO CITACION A LA PARTE DEMANDADA SALGUERO PALACIOS DIEGO ADOLFO.",
            },
            {
                "fecha": "18/11/2020",
                "detalle": "NO CITACION A LA PARTE DEMANDADA RECALDE CAMACHO LUCIA CLORINDA.",
            },
            {
                "fecha": "23/08/2021",
                "detalle": "RAZON ENVIO A CITACIONES (SALGUERO PALACIOS DIEGO ADOLFO): TERCERA GESTION REALIZADA POR EL CITADOR: BOLETA 3",
            },
            {
                "fecha": "23/08/2021",
                "detalle": "RAZON ENVIO A CITACIONES (RECALDE CAMACHO LUCIA CLORINDA): TERCERA GESTION REALIZADA POR EL CITADOR: BOLETA 3",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "23/08/2021")

    def test_solo_ordenar_citacion_no_marca_contestacion_actual(self):
        actuaciones = [
            {
                "fecha": "18/12/2025",
                "detalle": (
                    "LA DEMANDA SE CALIFICA Y ADMITE A TRAMITE. "
                    "SE ORDENA LA CITACION DE LA PERSONA DEMANDADA."
                ),
            },
            {"fecha": "18/12/2025", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertNotEqual(resultado.fase_actual, "CONTESTACION")

    def test_citacion_fallida_no_marca_contestacion_actual(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION"},
            {"fecha": "04/02/2023", "detalle": "CITACION: NO REALIZADA - DIRECCION INCORRECTA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertNotEqual(resultado.fase_actual, "CONTESTACION")

    def test_otro_numero_de_juicio_y_citacion_incompleta_no_avanzan_fase(self):
        actuaciones = [
            {
                "fecha": "12/05/2014",
                "detalle": "CAUSA NO. 17306-2014-0325: CALIFICACION DE DEMANDA",
            },
            {
                "fecha": "22/07/2016",
                "detalle": (
                    "CAUSA NO. 17306-2014-0323: OFICIO PARA CITACION POR PRENSA "
                    "Y PUBLICACION EN DIARIO."
                ),
            },
            {
                "fecha": "09/06/2017",
                "detalle": (
                    "CITACION REALIZADA EN PERSONA A LA PARTE DEMANDADA "
                    "OVIEDO TAMBACO CARLOS PATRICIO."
                ),
            },
            {
                "fecha": "09/06/2017",
                "detalle": (
                    "CITACION NO REALIZADA A LA PARTE DEMANDADA FLORES "
                    "MONTUFAR DARWIN PAUL."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa="17306-2014-0325"
        )

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "12/05/2014")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_boleta_notificada_marca_contestacion_actual(self):
        actuaciones = [
            {"fecha": "05/02/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {
                "fecha": "20/02/2023",
                "detalle": "BOLETA DE CITACION AL DEMANDADO NOTIFICADA EN SU DOMICILIO",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertEqual(resultado.fase_actual, "CONTESTACION")

    def test_acta_ambigua_no_anula_una_citacion_fallida(self):
        actuaciones = [
            {"fecha": "14/03/2025", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "14/03/2025",
                "detalle": "SE REMITIRAN BOLETAS A LA OFICINA DE CITACIONES Y, DE NO CONTESTAR, SE PRONUNCIARA SENTENCIA",
            },
            {"fecha": "02/09/2025", "detalle": "ACTA DE CITACION"},
            {"fecha": "02/09/2025", "detalle": "CITACION: NO REALIZADA - OTROS"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "14/03/2025")

    def test_acta_generica_sin_resultado_no_marca_citacion(self):
        actuaciones = [
            {"fecha": "18/09/2024", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "25/08/2025", "detalle": "ACTA DE CITACION"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "18/09/2024")

    def test_no_se_ha_procedido_a_citar_conserva_calificacion(self):
        actuaciones = [
            {"fecha": "18/09/2024", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "25/08/2025", "detalle": "ACTA DE CITACION"},
            {
                "fecha": "06/07/2026",
                "detalle": "NO SE HA PROCEDIDO A CITAR A LA PARTE DEMANDADA POR DIRECCION INSUFICIENTE. CITESE EN NUEVA DIRECCION.",
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "18/09/2024")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_archivo_sin_litis_trabada_deja_citacion_como_siguiente_paso(self):
        actuaciones = [
            {"fecha": "16/09/2015", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "05/06/2017",
                "detalle": (
                    "EL ACTOR NO HA PROPORCIONADO LAS COPIAS PERTINENTES PARA "
                    "REALIZAR LA CITACION. NO SE HA TRABADO LA LITIS. "
                    "SE ORDENA EL ARCHIVO DE LA PRESENTE CAUSA. NOTIFIQUESE Y ARCHIVESE."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "05/06/2017")
        self.assertEqual(resultado.etapa_actual, "2 CITACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_archivo_sin_citacion")

    def test_acta_posterior_confirma_citacion_y_no_retrocede_fase_avanzada(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "02/02/2023", "detalle": "RAZON ENVIO A CITACIONES: PROCESO ASIGNADO A UN CITADOR"},
            {"fecha": "10/02/2023", "detalle": "ACTA DE CITACION"},
            {"fecha": "20/04/2023", "detalle": "SENTENCIA (RESOLUCION)"},
            {"fecha": "01/06/2023", "detalle": "NOMBRAMIENTO DE PERITO LIQUIDADOR"},
            {"fecha": "20/06/2023", "detalle": "INFORME DEL PERITO"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "20/06/2023")

    def test_fallo_posterior_al_acta_retrocede_a_calificacion(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "02/02/2023", "detalle": "ACTA DE CITACION"},
            {"fecha": "03/02/2023", "detalle": "CITACION: NO REALIZADA - DIRECCION INCORRECTA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/01/2023")

    def test_acta_posterior_no_anula_dos_citaciones_fallidas(self):
        actuaciones = [
            {"fecha": "15/08/2025", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "01/08/2026", "detalle": "RAZON ENVIO A CITACIONES (PERSONA UNO): GESTION REALIZADA CON RAZON DE NO CITACION"},
            {"fecha": "01/08/2026", "detalle": "RAZON ENVIO A CITACIONES (PERSONA DOS): GESTION REALIZADA CON RAZON DE NO CITACION"},
            {"fecha": "02/08/2026", "detalle": "ACTA DE CITACION"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/08/2025")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_edicto_no_coincide_dentro_del_nombre_edictor(self):
        actuaciones = [
            {
                "fecha": "06/07/2026",
                "detalle": (
                    "AB. EDICTOR RODRIGO MANZANO AVOCÓ CONOCIMIENTO. "
                    "LA DEMANDA SE CALIFICA Y ADMITE A TRAMITE. "
                    "SE ORDENA LA CITACION EN EL DOMICILIO SENALADO."
                ),
            },
            {"fecha": "06/07/2026", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "06/07/2026")

    def test_dos_demandados_exigen_citacion_completa_de_ambos(self):
        actuaciones = [
            {"fecha": "27/09/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "29/02/2024",
                "detalle": (
                    "RAZON ENVIO A CITACIONES (PERSONA UNO): "
                    "GESTION REALIZADA CON RAZON DE NO CITACION"
                ),
            },
            {
                "fecha": "15/03/2024",
                "detalle": (
                    "RAZON ENVIO A CITACIONES (PERSONA DOS): TERCERA GESTION "
                    "REALIZADA POR EL CITADOR: BOLETA 3"
                ),
            },
            {"fecha": "17/04/2024", "detalle": "CITACION: REALIZADA - BOLETA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "27/09/2023")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_2_citacion_fallida")

    def test_dos_demandados_citados_marcan_contestacion_actual(self):
        actuaciones = [
            {"fecha": "27/09/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "15/03/2024",
                "detalle": (
                    "RAZON ENVIO A CITACIONES (PERSONA UNO): TERCERA GESTION "
                    "REALIZADA POR EL CITADOR: BOLETA 3"
                ),
            },
            {
                "fecha": "17/04/2024",
                "detalle": (
                    "RAZON ENVIO A CITACIONES (PERSONA DOS): TERCERA GESTION "
                    "REALIZADA POR EL CITADOR: BOLETA 3"
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertEqual(resultado.fase_actual, "CONTESTACION")

    def test_citacion_de_un_solo_demandado_no_habilita_contestacion(self):
        actuaciones = [
            {"fecha": "27/09/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "15/03/2024",
                "detalle": "CITACION REALIZADA EN PERSONA A LA DEMANDADA PERSONA UNO",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones,
            demandados=["PERSONA UNO", "PERSONA DOS"],
        )

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.etapa_actual, "2 CITACION")
        self.assertEqual(
            resultado.get("REGLA_APLICADA"),
            "regla_citacion_incompleta_demandados",
        )

    def test_citacion_de_todos_los_demandados_habilita_contestacion(self):
        actuaciones = [
            {"fecha": "27/09/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {
                "fecha": "15/03/2024",
                "detalle": "CITACION REALIZADA EN PERSONA A LA DEMANDADA PERSONA UNO",
            },
            {
                "fecha": "17/04/2024",
                "detalle": "CITACION REALIZADA EN PERSONA A LA DEMANDADA PERSONA DOS",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones,
            demandados=["PERSONA UNO", "PERSONA DOS"],
        )

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.etapa_actual, "CONTESTACION")

    def test_constancia_generica_no_cubre_varios_demandados(self):
        actuaciones = [
            {"fecha": "27/09/2023", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
            {"fecha": "15/03/2024", "detalle": "CITACION: REALIZADA - BOLETA"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones,
            demandados=["PERSONA UNO", "PERSONA DOS"],
        )

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.etapa_actual, "2 CITACION")

    def test_orden_futura_legalmente_citada_no_es_citacion_cumplida(self):
        actuaciones = [
            {"fecha": "01/03/2024", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "09/03/2026",
                "detalle": (
                    "SE PONE EN CONOCIMIENTO EL ACTA DE NO CITACI&OACUTE;N, "
                    "DE LA CUAL SE SENALA QUE NO SE CIT&OACUTE; A MARIA DEMANDADA. "
                    "SE DISPONE CITARLA EN SU LUGAR DE TRABAJO A FIN DE QUE SEA "
                    "LEGALMENTE CITADA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")

    def test_no_se_encuentra_citado_no_es_citacion_exitosa(self):
        actuaciones = [
            {"fecha": "30/11/2016", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "08/11/2021",
                "detalle": (
                    "RAZON: CONSTA QUE CRUZ CARRILLO CESAR AUGUSTO "
                    "NO SE ENCUENTRA CITADO."
                ),
            },
            {"fecha": "08/11/2021", "detalle": "CITACION: REALIZADA - RAZON"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")

    def test_no_he_podido_citar_prevalece_sobre_rotulo_generico(self):
        actuaciones = [
            {"fecha": "19/12/2013", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "22/01/2014",
                "detalle": (
                    "SENOR JUEZ: SIENTO POR TAL QUE NO HE PODIDO CITAR A "
                    "QUINCHUELA CHUQUITARCO MONICA PILAR, POR CUANTO NO EXISTE "
                    "LA DIRECCION INDICADA."
                ),
            },
            {"fecha": "22/01/2014", "detalle": "CITACION: REALIZADA - RAZON"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")

    def test_exito_de_otros_no_compensa_demandado_sin_citar(self):
        actuaciones = [
            {"fecha": "26/06/2017", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "21/11/2018",
                "detalle": (
                    "EL SENOR TISALEMA QUINAUCHO LUIS ORLANDO NO HA SIDO "
                    "CITADO POR DIRECCION INCORRECTA."
                ),
            },
            {
                "fecha": "29/11/2018",
                "detalle": (
                    "LOS SENORES QUISHPE TIPAN CARMEN AMELIA Y CHANGOLUISA "
                    "TASIGUANO SEGUNDO ANTONIO HAN SIDO CITADOS EN PERSONA."
                ),
            },
            {"fecha": "29/11/2018", "detalle": "CITACION REALIZADA (RAZON)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")

    def test_archivo_de_causa_clasifica_en_ultima_fase_conocida(self):
        actuaciones = [
            {"fecha": "01/11/2017", "detalle": "ARCHIVO DE LA CAUSA (AUTO RESOLUTIVO)"},
            {"fecha": "06/11/2017", "detalle": "ARCHIVO DE LA CAUSA (RAZON DE NOTIFICACION)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        # Sin etapas previas reconocibles → cae en 1.1 PRESENTAR DEMANDA
        self.assertIn(resultado.ultima_etapa, ["1 PRESENTACION Y CALIFICACION", "2 CITACION", "3 CONTESTACION", "4 AUDIENCIA", "5 SENTENCIA", "6 LIQUIDACION Y EMBARGO"])
        self.assertNotIn("7", resultado.ultima_fase)

    def test_reapertura_explicita_deja_sin_efecto_archivo_anterior(self):
        actuaciones = [
            {"fecha": "01/11/2017", "detalle": "ARCHIVO DE LA CAUSA (AUTO RESOLUTIVO)"},
            {
                "fecha": "10/01/2018",
                "detalle": (
                    "AUTO DE CALIFICACION: SE DEJA SIN EFECTO EL AUTO DE ARCHIVO "
                    "DE LA CAUSA. LA DEMANDA SE CALIFICA Y ADMITE A TRAMITE."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/01/2018")

    def test_falta_de_constancia_fotografica_mantiene_citacion_pendiente(self):
        actuaciones = [
            {"fecha": "25/10/2022", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)"},
            {
                "fecha": "19/05/2026",
                "detalle": (
                    "CONSTAN ACTAS DE CITACIONES REALIZADAS; SIN EMBARGO EL "
                    "CITADOR NO HA ADJUNTADO LA CONSTANCIA FOTOGRAFICA. SE "
                    "DISPONE QUE EL CITADOR AMPLIE SU CITACION."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "25/10/2022")
        self.assertNotEqual(resultado.etapa_actual, "CONTESTACION")

    def test_instrucciones_para_contestar_no_son_contestacion_presentada(self):
        actuaciones = [
            {"fecha": "17/11/2025", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)"},
            {
                "fecha": "17/11/2025",
                "detalle": (
                    "CONTESTACION A LA DEMANDA: SE CONCEDE EL TERMINO DE QUINCE "
                    "DIAS PARA QUE, UNA VEZ CITADA, LA DEMANDADA CONTESTE LA "
                    "DEMANDA Y PUEDA PROPONER EXCEPCIONES."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")

    def test_falta_de_contestacion_no_es_contestacion_presentada(self):
        actuaciones = [
            {"fecha": "31/01/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {"fecha": "05/03/2024", "detalle": "CITACION: REALIZADA - BOLETA FIJADA"},
            {
                "fecha": "22/11/2024",
                "detalle": "FALTA DE CONTESTACI\uFFFDN DE LA DEMANDA ART. 352 (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "22/11/2024",
                "detalle": (
                    "HA PRECLUIDO EL TERMINO LEGAL PARA CONTESTAR LA DEMANDA Y "
                    "LA PARTE DEMANDADA NO HA PRESENTADO NINGUN ESCRITO."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "05/03/2024")
        self.assertNotEqual(resultado.ultima_etapa, "3 CONTESTACION")

    def test_escrito_expresso_de_contestacion_si_marca_fase_tres(self):
        actuaciones = [
            {"fecha": "31/01/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {"fecha": "05/03/2024", "detalle": "CITACION: REALIZADA - BOLETA FIJADA"},
            {
                "fecha": "18/03/2024",
                "detalle": "PRESENTA CONTESTACION A LA DEMANDA Y OPONE EXCEPCIONES.",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "3.1 CONTESTACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "18/03/2024")

    def test_retiro_sin_calificar_conserva_aclaracion(self):
        actuaciones = [
            {
                "fecha": "06/07/2026",
                "detalle": "COMPLETAR Y/O ACLARAR LA SOLICITUD Y/O DEMANDA",
            },
            {
                "fecha": "30/07/2026",
                "detalle": (
                    "PREVIO A SER CALIFICADA LA DEMANDA, LA PARTE ACTORA SOLICITA "
                    "SU RETIRO. LA DEMANDA SERA DEVUELTA SIN ESTAR CALIFICADA. "
                    "SE DISPONE EL ARCHIVO DEFINITIVO DE LA CAUSA."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        # Retiro antes de calificar → 1.2 COMPLETAR/ACLARAR DEMANDA (la última fase válida detectada)
        self.assertEqual(resultado.ultima_fase, "1.2 COMPLETAR/ACLARAR DEMANDA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "06/07/2026")

    def test_referencia_doctrinal_a_corte_nacional_no_crea_casacion(self):
        actuaciones = [
            {
                "fecha": "23/06/2022",
                "detalle": "RAZON DE EJECUTORIA: LA SENTENCIA SE ENCUENTRA EJECUTORIADA",
                "CLAVE_CARPETA": "causa_1",
            },
            {
                "fecha": "02/03/2022",
                "detalle": (
                    "DEPRECATORIO PARA PRACTICAR CITACION. ES UN ASUNTO LOGISTICO, "
                    "TAL COMO LO SENALA LA CORTE NACIONAL DE JUSTICIA EN OFICIO "
                    "CIRCULAR; SE DISPONE DEVOLVER EL DEPRECATORIO."
                ) * 4,
                "CLAVE_CARPETA": "causa_2",
            },
        ]
        segmentos = MotorInferenciaProcesal._segmentar_por_instancia(actuaciones)
        self.assertNotIn("CASACION", segmentos)
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "23/06/2022")

    def test_perito_sin_informe_conserva_fecha_real_de_ejecutoria(self):
        actuaciones = [
            {"fecha": "27/06/2025", "detalle": "SENTENCIA (RESOLUCION)"},
            {"fecha": "19/08/2025", "detalle": "RAZON DE EJECUTORIA (RAZON)"},
            {"fecha": "20/07/2026", "detalle": "NOMBRAMIENTO DE PERITO (AUTO DE SUSTANCIACION)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "19/08/2025")
        self.assertEqual(resultado.fase_actual, "6.1 LIQUIDACION PERITO LIQUIDADOR")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "regla_7_perito_sin_informe")

    def test_perito_sin_ejecutoria_visible_conserva_respaldo_historico(self):
        actuaciones = [
            {"fecha": "06/07/2026", "detalle": "NOMBRAMIENTO DE PERITO (AUTO DE SUSTANCIACION)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "06/07/2026")
        self.assertEqual(resultado.fase_actual, "6.1 LIQUIDACION PERITO LIQUIDADOR")

    def test_publicacion_del_aviso_no_cierra_la_fase_de_remate(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO"},
            {"fecha": "15/11/2024", "detalle": "SE FIJA FECHA PARA QUE TENGA LUGAR EL REMATE DEL BIEN"},
            {
                "fecha": "19/11/2024",
                "detalle": "PROCEDO A PUBLICAR EL AVISO DE REMATE CORRESPONDIENTE A LA CAUSA",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.3 EMBARGO")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/04/2023")
        self.assertEqual(resultado.fase_actual, "6.4 REMATE")

    def test_auto_publicacion_y_fecha_remate_actualiza_fecha_operativa(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO DEL INMUEBLE"},
            {
                "fecha": "09/07/2026",
                "detalle": (
                    "PUBLICACION Y FECHA PARA REMATE (AUTO INTERLOCUTORIO). "
                    "SEGUNDO SENALAMIENTO DE REMATE JUDICIAL EN LINEA. "
                    "SE SENALA PARA EL DIA 28 DE SEPTIEMBRE DE 2026 LA "
                    "REALIZACION DEL REMATE JUDICIAL EN LINEA."
                ),
            },
            {
                "fecha": "10/07/2026",
                "detalle": (
                    "PUBLICACION Y FECHA PARA REMATE (RAZON DE NOTIFICACION): "
                    "SE NOTIFICA EL AUTO QUE ANTECEDE."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        # El embargo se conserva como hito verificable; el auto posterior
        # abre la fase operativa de remate y aporta su propia fecha.
        self.assertEqual(resultado.ultima_fase, "6.3 EMBARGO")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/04/2023")
        self.assertEqual(resultado.fase_actual, "6.4 REMATE")
        self.assertEqual(resultado.get("FECHA_INICIO_FASE_ACTUAL"), "09/07/2026")
        self.assertEqual(resultado.get("REGLA_APLICADA"), "programacion_formal_remate")

    def test_razon_publicacion_remate_es_respaldo_si_no_existe_auto(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO DEL INMUEBLE"},
            {
                "fecha": "10/07/2026",
                "detalle": (
                    "PUBLICACION Y FECHA PARA REMATE (RAZON DE NOTIFICACION): "
                    "SE PROCEDIO A PUBLICAR EL REMATE JUDICIAL PARA EFECTUARSE "
                    "EL 28 DE SEPTIEMBRE DE 2026."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.fase_actual, "6.4 REMATE")
        self.assertEqual(resultado.get("FECHA_INICIO_FASE_ACTUAL"), "10/07/2026")

    def test_publicacion_remate_negada_no_actualiza_fecha_operativa(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO DEL INMUEBLE"},
            {
                "fecha": "09/07/2026",
                "detalle": (
                    "PUBLICACION Y FECHA PARA REMATE (AUTO INTERLOCUTORIO): "
                    "SE NIEGA LA PUBLICACION SOLICITADA Y NO SE SENALA REMATE."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.fase_actual, "6.4 REMATE")
        self.assertEqual(resultado.get("FECHA_INICIO_FASE_ACTUAL"), "10/04/2023")
        self.assertNotEqual(resultado.get("REGLA_APLICADA"), "programacion_formal_remate")

    def test_cita_doctrinal_de_embargo_no_supera_ejecutoria(self):
        actuaciones = [
            {
                "fecha": "10/07/2019",
                "detalle": (
                    "SENTENCIA. LA DOCTRINA DICE QUE EL JUICIO EJECUTIVO ES UN "
                    "PROCEDIMIENTO PARA LLEVAR A EFECTO MEDIANTE EMBARGO Y VENTA "
                    "DE BIENES EL COBRO DE CREDITOS. SIN EMBARGO, SE ACEPTA LA DEMANDA."
                ),
            },
            {"fecha": "26/07/2019", "detalle": "RAZON DE EJECUTORIA (RAZON)"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "26/07/2019")

    def test_orden_deprecada_de_embargo_no_supera_citacion_cumplida(self):
        actuaciones = [
            {
                "fecha": "30/11/2023",
                "detalle": (
                    "DESPACHO DEPRECATORIO: EL JUEZ DEPRECA LA PRACTICA DE "
                    "DILIGENCIA DE EMBARGO Y CITACION PARA QUE SE REALICEN LAS "
                    "DILIGENCIAS PERTINENTES."
                ),
            },
            {
                "fecha": "10/03/2026",
                "detalle": "CITACION: REALIZADA - EN PERSONA A ORTEGA LOAYZA EDWIN EFRAIN",
            },
            {
                "fecha": "10/03/2026",
                "detalle": "CITACION: REALIZADA - EN PERSONA A MOROCHO JIMA ANGELA JEANNETH",
            },
            {
                "fecha": "19/06/2026",
                "detalle": "DEVOLUCION DEPRECATORIO POR CUMPLIMIENTO DE DILIGENCIA",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/03/2026")
        self.assertEqual(resultado.etapa_actual, "CONTESTACION")
        self.assertEqual(resultado.fase_actual, "CONTESTACION")

    def test_citacion_resumen_exitosa_resuelve_fallos_individuales_previos(self):
        actuaciones = [
            {"fecha": "01/02/2026", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "12/02/2026",
                "detalle": "CITACION: NO REALIZADA - DESCONOCIDO (DEMANDADO PEREZ JUAN)",
            },
            {
                "fecha": "10/03/2026",
                "detalle": "CITACION: REALIZADA - EN PERSONA",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/03/2026")
    def test_peticion_de_embargo_no_supera_mandamiento(self):
        actuaciones = [
            {"fecha": "22/12/2025", "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)"},
            {
                "fecha": "23/02/2026",
                "detalle": (
                    "VISTOS: AGREGUESE EL ESCRITO Y SE DISPONE: EN RELACION A LA "
                    "PETICION DE EMBARGO DEL AUTOMOTOR, SE EVIDENCIA UNA PRENDA "
                    "VIGENTE, RAZON POR LA CUAL ESTE JUZGADOR NO PUEDE EJECUTAR "
                    "LA PETICION; POR TANTO, SE LO NIEGA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "22/12/2025")

    def test_cita_legal_de_remate_y_adjudicacion_no_supera_mandamiento(self):
        actuaciones = [
            {
                "fecha": "30/08/2017",
                "detalle": (
                    "SENTENCIA: EL ARTICULO 413 DEL CODIGO DE PROCEDIMIENTO CIVIL "
                    "MENCIONA LAS ACTAS JUDICIALES DE REMATE O LAS COPIAS DE LOS "
                    "AUTOS DE ADJUDICACION COMO TITULOS EJECUTIVOS."
                ),
            },
            {
                "fecha": "28/11/2017",
                "detalle": "MANDAMIENTO DE EJECUCION (AUTO)",
            },
            {
                "fecha": "12/12/2017",
                "detalle": (
                    "SE PRETENDE EMBARGAR UN VEHICULO CON RESERVA DE DOMINIO; "
                    "NO SE ATIENDE LO PETICIONADO POR IMPROCEDENTE."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "28/11/2017")
    def test_mencion_normativa_de_embargo_no_supera_calificacion(self):
        actuaciones = [
            {"fecha": "26/08/2024", "detalle": "AUTO DE CALIFICACION"},
            {
                "fecha": "10/11/2025",
                "detalle": (
                    "EL ACTOR HACE MENCION A LA PROVIDENCIA PREVENTIVA DE SECUESTRO "
                    "Y A LA NORMATIVA PREVISTA PARA EMBARGO, QUE SOLO CABE EN "
                    "EJECUCION. PREVIO A PROVEER, ACLARE SU REQUERIMIENTO."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "26/08/2024")

    def test_embargo_no_ordenado_y_remate_negado_no_superan_mandamiento(self):
        actuaciones = [
            {"fecha": "21/05/2026", "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)"},
            {
                "fecha": "23/07/2026",
                "detalle": (
                    "SE SOLICITA PUBLICACION PARA QUE TERCEROS INTERVENGAN EN EL "
                    "REMATE DEL BIEN. EN LA PRESENTE CAUSA NO SE HA ORDENADO EMBARGO "
                    "DE BIEN ALGUNO, POR LO QUE SE NIEGA LA PUBLICACION SOLICITADA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "21/05/2026")

    def test_orden_explicita_de_embargo_no_supera_mandamiento(self):
        actuaciones = [
            {"fecha": "21/05/2026", "detalle": "MANDAMIENTO DE EJECUCION"},
            {"fecha": "23/07/2026", "detalle": "SE ORDENA EL EMBARGO DEL VEHICULO DEL EJECUTADO"},
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "21/05/2026")

    def test_secuestro_ejecutado_no_equivale_a_embargo(self):
        ordenado = [
            {"fecha": "21/05/2026", "detalle": "MANDAMIENTO DE EJECUCION"},
            {"fecha": "23/07/2026", "detalle": "SE DISPONE EL SECUESTRO DEL VEHICULO"},
        ]
        ejecutado = ordenado + [
            {"fecha": "28/07/2026", "detalle": "ACTA DE SECUESTRO DEL VEHICULO"},
        ]

        resultado_ordenado = MotorInferenciaProcesal.inferir_estado_procesal(ordenado)
        resultado_ejecutado = MotorInferenciaProcesal.inferir_estado_procesal(ejecutado)

        self.assertEqual(resultado_ordenado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado_ejecutado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado_ejecutado.fecha_fin_ultima_fase, "21/05/2026")

    def test_acta_de_secuestro_preventivo_conserva_calificacion_y_citacion(self):
        """Regresión del caso 07333-2025-03301: cautelar no es embargo."""
        actuaciones = [
            {
                "fecha": "19/01/2026",
                "detalle": (
                    "CALIFICACION DE SOLICITUD Y/O DEMANDA. SE CALIFICA Y ADMITE "
                    "A TRAMITE. SE ORDENA LA CITACION DE LA DEMANDADA. "
                    "PROVIDENCIA PREVENTIVA: SE ORDENA EL SECUESTRO DEL VEHICULO."
                ),
            },
            {
                "fecha": "02/02/2026",
                "detalle": "ACTA DE SECUESTRO DEL VEHICULO",
            },
            {
                "fecha": "10/03/2026",
                "detalle": "INCORPORESE A LOS AUTOS EL ACTA DE SECUESTRO PRESENTADA.",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "19/01/2026")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertNotEqual(resultado.ultima_fase, "6.3 EMBARGO")

    def test_consulta_a_superintendencia_no_es_congelamiento(self):
        actuaciones = [
            {"fecha": "09/03/2026", "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)"},
            {
                "fecha": "21/05/2026",
                "detalle": (
                    "OFICIESE A LA SUPERINTENDENCIA DE BANCOS PARA QUE CERTIFIQUE "
                    "SI LOS EJECUTADOS MANTIENEN CUENTAS CORRIENTES O DE AHORROS."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "09/03/2026")

    def test_cuentas_congeladas_con_montos_si_son_fase_6_5(self):
        actuaciones = [
            {"fecha": "09/03/2026", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "21/05/2026",
                "detalle": (
                    "EL BANCO INFORMA QUE TRES CUENTAS FUERON CONGELADAS POR LOS "
                    "MONTOS DE USD 120, USD 80 Y USD 45."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.5 CONGELAMIENTO DE CUENTAS / CIERRE")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "21/05/2026")

    def test_transferencia_de_valores_retenidos_si_es_fase_6_5(self):
        actuaciones = [
            {"fecha": "09/03/2026", "detalle": "MANDAMIENTO DE EJECUCION"},
            {
                "fecha": "25/05/2026",
                "detalle": (
                    "SE DISPONE QUE EL BANCO TRANSFIERA LOS VALORES RETENIDOS A "
                    "LA CUENTA JUDICIAL DE ESTA CAUSA."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.5 CONGELAMIENTO DE CUENTAS / CIERRE")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "25/05/2026")

    def test_publicacion_y_fecha_de_remate_no_equivalen_a_remate_ejecutado(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO"},
            {"fecha": "15/11/2024", "detalle": "SE FIJA FECHA PARA EL REMATE DEL BIEN"},
            {"fecha": "19/11/2024", "detalle": "SE PUBLICA EL AVISO DE REMATE"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.3 EMBARGO")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/04/2023")
        self.assertEqual(resultado.fase_actual, "6.4 REMATE")

    def test_adjudicacion_acredita_remate_ejecutado(self):
        actuaciones = [
            {"fecha": "10/04/2023", "detalle": "ACTA DE EMBARGO"},
            {"fecha": "19/11/2024", "detalle": "SE PUBLICA EL AVISO DE REMATE"},
            {"fecha": "22/01/2025", "detalle": "AUTO DE ADJUDICACION: SE ADJUDICA EL BIEN AL POSTOR GANADOR"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.4 REMATE")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "22/01/2025")

    def test_articulo_372_y_orden_de_pagar_identifican_mandamiento(self):
        actuaciones = [
            {"fecha": "09/06/2025", "detalle": "RAZON DE EJECUTORIA"},
            {
                "fecha": "13/05/2026",
                "detalle": (
                    "DE CONFORMIDAD AL ARTICULO 372 DEL COGEP, SE ORDENA QUE LA "
                    "PARTE EJECUTADA PAGUE USD 3.717,72 EN EL TERMINO DE CINCO DIAS."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "13/05/2026")

    def test_orden_de_pago_mercantil_dentro_de_sentencia_no_es_mandamiento(self):
        actuaciones = [
            {
                "fecha": "31/07/2023",
                "detalle": (
                    "SENTENCIA. SE DETERMINA QUE EL TITULO VALOR CONTIENE UNA "
                    "ORDEN DE PAGO POR SU NATURALEZA MERCANTIL."
                ),
            },
            {"fecha": "04/08/2023", "detalle": "RAZON DE EJECUTORIA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "04/08/2023")

    def test_formula_sentencia_que_antecede_debidamente_ejecutoriada(self):
        actuaciones = [
            {"fecha": "29/10/2018", "detalle": "SENTENCIA (RESOLUCION)"},
            {
                "fecha": "08/11/2018",
                "detalle": (
                    "RAZON: LA SENTENCIA QUE ANTECEDE SE ENCUENTRA "
                    "DEBIDAMENTE EJECUTORIADA POR EL MINISTERIO DE LA LEY."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "5.3 SENTENCIA EJECUTORIADA")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "08/11/2018")

    def test_publicacion_posterior_no_reemplaza_fecha_del_mandamiento(self):
        actuaciones = [
            {"fecha": "08/05/2026", "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)"},
            {
                "fecha": "22/06/2026",
                "detalle": (
                    "SE DISPONE LA PUBLICACION DEL MANDAMIENTO DE EJECUCION PARA "
                    "CONOCIMIENTO DE TERCEROS POR INCUMPLIMIENTO."
                ),
            },
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "6.2 MANDAMIENTO DE EJECUCION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "08/05/2026")

    def test_acta_de_sorteo_no_desplaza_una_calificacion_real(self):
        actuaciones = [
            {"fecha": "07/07/2026", "detalle": "ACTA DE SORTEO"},
            {"fecha": "14/07/2026", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA"},
        ]
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)
        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "14/07/2026")

    def test_control_diario_no_es_citacion_por_prensa_y_fallo_personal_pendiente(self):
        """Un control administrativo diario no puede suplir una citación real."""
        actuaciones = [
            {"fecha": "12/05/2017", "detalle": "CALIFICACION DE DEMANDA"},
            {
                "fecha": "20/01/2023",
                "detalle": (
                    "SE HA EFECTUADO LA CITACION A MOLINA CHANGO OLMEDO; "
                    "EL CITADO NO ACEPTO FIRMAR LA HOJA DE CONTROL DIARIO."
                ),
            },
            {
                "fecha": "25/05/2023",
                "detalle": (
                    "RAZON ENVIO A CITACIONES (CARTUCHE GUERRA NORMA DEL PILAR): "
                    "GESTION REALIZADA CON RAZON DE NO CITACION, DIRECCION PRINCIPAL."
                ),
            },
            {
                "fecha": "25/05/2023",
                "detalle": "CITACION: NO REALIZADA - DIRECCION INSUFICIENTE",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertNotEqual(resultado.ultima_fase, "2.2 CITACION POR PRENSA")

    def test_publicacion_en_diario_de_circulacion_si_es_citacion_por_prensa(self):
        actuaciones = [
            {"fecha": "01/01/2026", "detalle": "CALIFICACION DE DEMANDA"},
            {
                "fecha": "02/01/2026",
                "detalle": (
                    "SE DISPONE LA PUBLICACION EN DIARIO DE MAYOR CIRCULACION "
                    "PARA LA CITACION DE LA DEMANDADA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.2 CITACION POR PRENSA")

    def test_referencia_normativa_de_prensa_no_sustituye_citacion_fallida(self):
        actuaciones = [
            {
                "fecha": "10/02/2025",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "29/05/2025",
                "detalle": "CITACION: NO REALIZADA - CAMBIO DE DIRECCION",
            },
            {
                "fecha": "16/07/2026",
                "detalle": (
                    "VISTOS: EL ART. 56 REGULA LA CITACION A TRAVES DE LOS "
                    "MEDIOS DE COMUNICACION. LA JURISPRUDENCIA SOBRE CITACION "
                    "POR LA PRENSA EXIGE AGOTAR GESTIONES. PREVIO A PROVEER, "
                    "EL ACTOR DEBE ACUDIR A LOS REGISTROS PUBLICOS. CUMPLASE."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "10/02/2025")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")

    def test_orden_de_cumplir_estandares_sobre_prensa_no_es_citacion(self):
        actuaciones = [
            {
                "fecha": "16/05/2024",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "01/07/2024",
                "detalle": "CITACION: NO REALIZADA - DIRECCION INSUFICIENTE",
            },
            {
                "fecha": "17/07/2026",
                "detalle": (
                    "EL JUEZ ORDENA AL ACTOR QUE CUMPLA CON LOS ESTANDARES "
                    "PREVISTOS EN LA SENTENCIA 2791-17-EP/23 SOBRE CITACION "
                    "POR LA PRENSA Y DEBIDO PROCESO, Y REALICE GESTIONES PARA "
                    "DETERMINAR EL DOMICILIO DE LA PARTE DEMANDADA."
                ),
            },
        ]

        texto = actuaciones[-1]["detalle"]
        self.assertFalse(
            MotorInferenciaProcesal._es_citacion_prensa_acreditada(texto)
        )

    def test_contestacion_usa_fecha_del_escrito_confirmado_posteriormente(self):
        actuaciones = [
            {
                "fecha": "15/11/2023 16:43",
                "detalle": "ESCRITO, FEPRESENTACION",
            },
            {
                "fecha": "12/06/2024 11:54",
                "detalle": (
                    "INCORPORESE AL EXPEDIENTE LOS ESCRITOS DE CONTESTACION "
                    "A LA DEMANDA PRESENTADOS POR LA PARTE DEMANDADA; "
                    "TENGASE EN CUENTA SU COMPARECENCIA A JUICIO."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "3.1 CONTESTACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/11/2023 16:43")
        self.assertEqual(resultado.regla_aplicada, "fecha_presentacion_contestacion")

    def test_una_sola_contestacion_acreditada_basta_y_usa_escrito_inmediato(self):
        """No se exige que todos los demandados contesten la demanda."""
        actuaciones = [
            {
                "fecha": "26/04/2023",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "28/08/2023",
                "detalle": "CITACION: REALIZADA - EN PERSONA A MORA VALLES JHONATHAN EFREN",
            },
            {
                "fecha": "28/08/2023",
                "detalle": "CITACION: NO REALIZADA A COBOS CORREA JENNY EDITA - CAMBIO DE DIRECCION",
            },
            {
                "fecha": "07/09/2023 14:05",
                "detalle": "ESCRITO",
            },
            {
                "fecha": "25/09/2023 16:26",
                "detalle": (
                    "AGREGUESE AL PROCESO EL ESCRITO QUE ANTECEDE. TENGASE EN "
                    "CUENTA LA COMPARECENCIA DEL DEMANDADO MORA VALLES. "
                    "OPORTUNAMENTE ME PRONUNCIARE RESPECTO AL CONTENIDO DE SU "
                    "CONTESTACION A LA DEMANDA."
                ),
            },
            {
                "fecha": "14/01/2025 13:58",
                "detalle": (
                    "LA PARTE DEMANDADA MORA VALLES HA COMPARECIDO EN LA "
                    "PRESENTE CAUSA MEDIANTE MEMORIAL DE FECHA 07 DE SEPTIEMBRE "
                    "DEL 2024, CONTESTANDO LA PRESENTE DEMANDA Y PROPONIENDO "
                    "EXCEPCIONES PREVIAS."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_etapa, "3 CONTESTACION")
        self.assertEqual(resultado.ultima_fase, "3.1 CONTESTACION")
        # La razón posterior contiene un año inconsistente; el escrito y la
        # providencia inmediata de septiembre determinan la fecha procesal.
        self.assertEqual(resultado.fecha_fin_ultima_fase, "07/09/2023 14:05")
        self.assertEqual(resultado.etapa_actual, "4 AUDIENCIA")
        self.assertEqual(resultado.fase_actual, "4.1 FIJACION FECHA AUDIENCIA")
        self.assertEqual(resultado.regla_aplicada, "fecha_presentacion_contestacion")

    def test_orden_de_certificar_si_hubo_contestacion_no_la_acredita(self):
        """La verificación condicional no debe confundirse con una respuesta."""
        actuaciones = [
            {
                "fecha": "25/10/2022",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "05/03/2024",
                "detalle": "CITACION: REALIZADA - BOLETA FIJADA",
            },
            {
                "fecha": "13/04/2026",
                "detalle": (
                    "SE DISPONE AL ACTUARIO QUE SIENTE RAZON CERTIFICANDO SI "
                    "LA PARTE DEMANDADA HA COMPARECIDO A JUICIO CONTESTANDO "
                    "A LA DEMANDA Y DEDUCIENDO EXCEPCIONES."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "05/03/2024")

    def test_plazo_para_contestar_no_es_contestacion_presentada(self):
        actuaciones = [
            {
                "fecha": "09/04/2025",
                "detalle": (
                    "SE CALIFICA LA DEMANDA. SE CONCEDE A LOS DEMANDADOS EL "
                    "TERMINO DE QUINCE DIAS PARA CONTESTAR LA DEMANDA U "
                    "OPONER EXCEPCIONES."
                ),
            },
            {
                "fecha": "10/07/2025",
                "detalle": (
                    "EN CUMPLIMIENTO DEL AUTO DE CALIFICACION DE FECHA "
                    "09/04/2025, SE REQUIERE COMPLETAR EL DEPRECATORIO PARA "
                    "CITACION. LAS FORMAS EXTRAORDINARIAS INCLUYEN EL "
                    "ALLANAMIENTO, SIN QUE EXISTA UNO PRESENTADO EN LA CAUSA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "09/04/2025")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")

    def test_respuesta_a_requerimiento_de_citacion_no_es_contestacion(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {
                "fecha": "05/02/2023",
                "detalle": (
                    "OFICIO DEL TENIENTE POLITICO DA CONTESTACION AL "
                    "REQUERIMIENTO DE CITACION: LA DEMANDADA NO RESIDE EN "
                    "LA DIRECCION INFORMADA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertNotEqual(resultado.ultima_etapa, "3 CONTESTACION")

    def test_citacion_mixta_no_acredita_a_los_dos_demandados(self):
        actuaciones = [
            {"fecha": "08/10/2024", "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)"},
            {
                "fecha": "11/12/2024",
                "detalle": (
                    "ACTA DE CITACION REALIZADA AL DEMANDADO SENOR SANDRO NOVOA GOMEZ. "
                    "ACTA DE CITACION <STRONG>NO</STRONG> REALIZADA A LA DEMANDADA "
                    "SENORA MARIANA YAGUANA CORREA."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones,
            demandados="SANDRO NOVOA GOMEZ, MARIANA YAGUANA CORREA",
        )

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "08/10/2024")

    def test_no_han_comparecido_ni_contestado_no_es_fase_tres(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {"fecha": "05/02/2023", "detalle": "CITACION: REALIZADA - BOLETA"},
            {
                "fecha": "01/03/2023",
                "detalle": (
                    "LOS DEMANDADOS NO HAN COMPARECIDO A JUICIO NI HAN "
                    "CONTESTADO LA DEMANDA, PROPUESTO EXCEPCIONES O "
                    "CANCELADO LO ADEUDADO."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertNotEqual(resultado.ultima_etapa, "3 CONTESTACION")

    def test_orden_condicional_despues_de_citar_no_es_contestacion(self):
        actuaciones = [
            {"fecha": "10/01/2023", "detalle": "AUTO DE CALIFICACION DE LA DEMANDA"},
            {"fecha": "05/02/2023", "detalle": "CITACION: REALIZADA - BOLETA"},
            {
                "fecha": "01/03/2023",
                "detalle": (
                    "POR SECRETARIA SIENTE RAZON INDICANDO SI LA PARTE HA "
                    "SIDO CITADA Y SI DENTRO DEL TERMINO HA COMPARECIDO "
                    "CONTESTANDO LA DEMANDA O PROPONIENDO EXCEPCIONES."
                ),
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertNotEqual(resultado.ultima_etapa, "3 CONTESTACION")

    def test_escrito_generico_con_adjunto_posterior_marca_revision_documental(self):
        """No se inventa contestación, pero tampoco se oculta el escrito posterior."""
        actuaciones = [
            {
                "fecha": "15/08/2022",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "16/12/2022 16:08",
                "detalle": "ESCRITO, FEPRESENTACION",
                "TIENE_ADJUNTO": True,
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fecha_fin_ultima_fase, "15/08/2022")
        self.assertEqual(resultado.etapa_actual, "REVISION MANUAL")
        self.assertEqual(resultado.fase_actual, "REVISION MANUAL")
        self.assertIn("ESCRITO POSTERIOR SIN TIPO CONFIRMADO", resultado.mensaje_especial)
        self.assertEqual(resultado.regla_aplicada, "revision_documental_escrito_generico")
        self.assertEqual(
            resultado.get("ACTUACION_PENDIENTE_REVISION")["fecha"],
            "16/12/2022 16:08",
        )

    def test_escrito_generico_sin_adjunto_no_marca_revision_documental(self):
        actuaciones = [
            {
                "fecha": "15/08/2022",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "16/12/2022",
                "detalle": "ESCRITO, FEPRESENTACION",
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "1.3 CALIFICACION")
        self.assertEqual(resultado.fase_actual, "2.1 CITACION (PERSONA/BOLETA)")
        self.assertIsNone(resultado.mensaje_especial)

    def test_escrito_generico_con_adjunto_no_abre_revision_tras_fase_confirmada_posterior(self):
        actuaciones = [
            {
                "fecha": "15/08/2022",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)",
            },
            {
                "fecha": "20/09/2022",
                "detalle": "BOLETA DE CITACION AL DEMANDADO NOTIFICADA",
            },
            {
                "fecha": "10/10/2022",
                "detalle": "CONTESTA LA DEMANDA Y OPONE EXCEPCIONES",
            },
            {
                "fecha": "16/12/2022",
                "detalle": "ESCRITO, FEPRESENTACION",
                "TIENE_ADJUNTO": True,
            },
        ]

        resultado = MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)

        self.assertEqual(resultado.ultima_fase, "3.1 CONTESTACION")
        self.assertEqual(resultado.fase_actual, "4.1 FIJACION FECHA AUDIENCIA")
        self.assertIsNone(resultado.mensaje_especial)

    def test_html_con_icono_de_archivo_conserva_metadato_de_adjunto(self):
        html = """
        <div role="row">
          <span>15/08/2022 15:36</span>
          <span>CALIFICACION DE SOLICITUD Y/O DEMANDA (AUTO DE SUSTANCIACION)</span>
        </div>
        <div role="row">
          <span>16/12/2022 16:08</span>
          <span>ESCRITO</span><span>FePresentacion</span>
          <a role="link" mattooltip="Ver archivos"></a>
        </div>
        """

        resultado = self.extractor.procesar_html_string(html)
        escrito = next(
            actuacion for actuacion in resultado["HISTORIAL_ACTUACIONES"]
            if "FEPRESENTACION" in actuacion["detalle"]
        )

        self.assertTrue(escrito["TIENE_ADJUNTO"])
        self.assertEqual(resultado["ULTIMA FASE"], "1.3 CALIFICACION")
        self.assertEqual(resultado["FASE ACTUAL"], "REVISION MANUAL")

if __name__ == "__main__":
    unittest.main()
