import sys, os, json
sys.path.insert(0, os.path.abspath('.'))
from src.agente_extractor import AgenteExtractor

art_dir = os.path.join('data','temp_htmls')
files = sorted([f for f in os.listdir(art_dir) if f.endswith('.html')], key=lambda x: os.path.getmtime(os.path.join(art_dir,x)), reverse=True)
if not files:
    print('No HTML artifacts found')
    sys.exit(0)
html_file = os.path.join(art_dir, files[0])
api_file = html_file.replace('.html','_api.json')
print('Using HTML:', html_file)
print('Using API:', api_file if os.path.exists(api_file) else 'API file not found')

with open(html_file,'r',encoding='utf-8',errors='ignore') as f:
    html = f.read()

ae = AgenteExtractor()
res = ae.procesar_html_string(html)
print('\nEXTRACTOR OUTPUT:')
print(json.dumps(res, ensure_ascii=False, indent=2))

if os.path.exists(api_file):
    with open(api_file,'r',encoding='utf-8') as fa:
        api = json.load(fa)
    print('\nAPI SUMMARY:')
    for p in api:
        print('-', p.get('url'))
        d = p.get('data')
        if isinstance(d, list) and d:
            print('  sample keys:', list(d[0].keys()))
