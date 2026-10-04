import sys
import os
import json
# Asegurar que la ruta del paquete src esté en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.agente_extractor import AgenteExtractor

with open('data/temp_htmls/23331-2022-04261_api.json','r',encoding='utf-8') as f:
    api=json.load(f)

ae=AgenteExtractor()
for p in api:
    d=p.get('data')
    if isinstance(d,list):
        for reg in d:
            campos=['nombreTipoAccion','nombreProvidencia','nombreTipoResolucion','nombreDelito','nombreMateria','nombreEstadoJuicio']
            texto=' '.join([str(reg.get(c)) for c in campos if reg.get(c)])
            if texto:
                etapa,fase,score=ae.evaluar_similitud_semantica(texto)
                print('COMPOSED TEXT:',texto)
                print('=>',etapa,fase,score)
    else:
        print('Non-list data type:', type(d))
