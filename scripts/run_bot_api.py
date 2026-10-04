import sys, os, json
sys.path.insert(0, os.path.abspath('.'))
from src.motor_busqueda_web import BotJudicial

with open('data/temp_htmls/23331-2022-04261_api.json','r',encoding='utf-8') as f:
    api=json.load(f)

bot=BotJudicial(url_portal='https://example')
# API file format is a list of {url,data}
bot.paquetes_api_interceptados=api
res=bot._ejecutar_extraccion_detalles('23331-2022-04261')
print(json.dumps(res, ensure_ascii=False, indent=2))
