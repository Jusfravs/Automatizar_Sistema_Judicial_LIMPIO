import sys, os, json
sys.path.insert(0, os.path.abspath('.'))
from src.gestor_casos import GestorCasos
from src.gestor_cola import GestorCola
from src.motor_busqueda_web import BotJudicial

NUM='23331-2022-04261'
# Load artifacts
api_path = os.path.join('data','temp_htmls', f'{NUM}_api.json')
html_path = os.path.join('data','temp_htmls', f'{NUM}.html')
api = None
if os.path.exists(api_path):
    with open(api_path,'r',encoding='utf-8') as f:
        api = json.load(f)

bot = BotJudicial(url_portal='https://example')
if api:
    bot.paquetes_api_interceptados = api

# Run extraction using saved API/HTML
datos = bot._ejecutar_extraccion_detalles(NUM)
print('EXTRACCION:', datos)

# Update CSV repo
repo = GestorCasos('config.json')
ok = repo.actualizar_caso(NUM, datos)
if ok:
    repo.guardar()
    print('CSV actualizado')
else:
    print('Aviso: no se encontró la fila para actualizar en CSV')

# Update SQLite
cola = GestorCola(ruta_db='estado_casos.db')
try:
    cola.registrar_resultado_transaccional(NUM, datos, origen='ASISTIDO_CSV', ruta_html=html_path if os.path.exists(html_path) else None)
    print('SQLite sincronizado')
except Exception as e:
    print('Error al sincronizar SQLite:', e)

# Encontrar siguiente caso y lanzar main.py con ese caso
casos = repo.obtener_casos_pendientes()
try:
    idx = next(i for i,c in enumerate(casos) if str(c).replace('-','').strip() == NUM.replace('-','').strip())
    siguiente = None
    if idx + 1 < len(casos):
        siguiente = casos[idx+1]
    else:
        print('No hay siguiente caso en la lista')
        sys.exit(0)
    print('Siguiente caso:', siguiente)
    # Lanzar main.py con el siguiente caso
    os.execv(sys.executable, [sys.executable, 'main.py', siguiente])
except StopIteration:
    print('No se encontró el caso en la lista de pendientes; no se lanzó avance')
