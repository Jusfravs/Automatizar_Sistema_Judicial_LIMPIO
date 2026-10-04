import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
import json
from pathlib import Path
from src.agente_extractor import MotorInferenciaProcesal
from src.catalogo_procesal import enriquecer_datos_procesales
from src.gestor_casos import GestorCasos

def actualizar_todo_quito():
    db_path = Path("data/quito/estado_casos_quito.db")
    if not db_path.exists():
        print("No se encontró la base de datos de Quito.")
        return

    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT r.numero_causa, r.datos_json
        FROM resultados_expediente AS r
        INNER JOIN juicios AS j ON j.numero_causa = r.numero_causa
        WHERE j.estado <> 'EXCLUIDO_NO_CORRESPONDE'
    """).fetchall()
    print(f"Total expedientes en DB Quito: {len(rows)}")

    gestor = GestorCasos(ruta_config="config_quito.json")
    
    actualizados = 0
    for causa_val, datos_json in rows:
        data = json.loads(datos_json)
        actuaciones = (data.get("datos") or {}).get("HISTORIAL_ACTUACIONES") or []
        if not actuaciones:
            continue
        
        inf = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa=causa_val
        )
        
        datos_extraidos = data.get("datos", {})
        datos_extraidos["ETAPA_PROCESAL"] = inf.etapa_actual
        datos_extraidos["FASE_PROCESAL"] = inf.fase_actual
        datos_extraidos["FECHA INICIAL FASE ACTUAL"] = inf.fecha_inicio_fase_actual
        datos_extraidos["ULTIMA ETAPA"] = inf.ultima_etapa
        datos_extraidos["ULTIMA FASE"] = inf.ultima_fase
        datos_extraidos["FECHA FIN ULTIMA FASE"] = inf.fecha_fin_ultima_fase
        datos_extraidos["ETAPA ACTUAL"] = inf.etapa_actual
        datos_extraidos["FASE ACTUAL"] = inf.fase_actual
        datos_extraidos["FECHA INICIO FASE ACTUAL"] = inf.fecha_inicio_fase_actual
        enriquecer_datos_procesales(
            datos_extraidos, normalizar_etiquetas=True
        )
        if inf.mensaje_especial:
            datos_extraidos["COMENTARIO_ULTIMO"] = inf.mensaje_especial
        datos_extraidos["ACTUACION_RESPALDO"] = inf.actuacion_respaldo
        
        data["datos"] = datos_extraidos
        nuevo_json = json.dumps(data, ensure_ascii=False)
        conn.execute("UPDATE resultados_expediente SET datos_json = ? WHERE numero_causa = ?", (nuevo_json, causa_val))
        
        # Actualizar en DataFrame del gestor
        gestor.actualizar_caso(str(causa_val), datos_extraidos)
        actualizados += 1

    conn.commit()
    conn.close()
    
    # Guardar en CSV
    gestor.guardar()
    print(f"✅ Guardado CSV con {actualizados} expedientes actualizados.")

    # Intentar exportar a Excel
    try:
        gestor.exportar_excel()
        print(f"✅ Guardado Excel con {actualizados} expedientes actualizados.")
    except PermissionError:
        print("⚠️ El archivo Excel de Quito está abierto por otro programa. Cierre Excel para permitir la exportación.")
    except Exception as e:
        print(f"⚠️ Error al exportar Excel: {e}")

if __name__ == "__main__":
    actualizar_todo_quito()
