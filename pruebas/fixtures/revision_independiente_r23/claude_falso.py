"""Public CI documentation."""
import json
import os
import sys
import time
carpeta = os.environ['ICT155_CLAUDE_FALSO']
entrada = sys.stdin.buffer.read().decode('utf-8')
n = 1
while os.path.exists(os.path.join(carpeta, f'llamada_{n}.json')):
    n += 1
with open(os.path.join(carpeta, f'llamada_{n}.json'), 'w', encoding='utf-8') as f:
    json.dump({'argv': sys.argv[1:], 'entrada': entrada}, f, ensure_ascii=False)
with open(os.path.join(carpeta, 'guion.json'), encoding='utf-8') as f:
    guion = json.load(f)
paso = guion[min(n - 1, len(guion) - 1)]
if paso.get('dormir'):
    time.sleep(float(paso['dormir']))
if 'salir' in paso:
    sys.exit(int(paso['salir']))

def escribir(texto):
    """Public CI documentation."""
    sys.stdout.buffer.write(texto.encode('utf-8'))
    sys.stdout.buffer.flush()
if 'crudo' in paso:
    escribir(paso['crudo'])
elif 'error' in paso:
    escribir(json.dumps({'type': 'result', 'subtype': 'error_during_execution', 'is_error': True, 'result': paso['error']}, ensure_ascii=False))
else:
    escribir(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': paso.get('result', ''), 'duration_ms': 12, 'duration_api_ms': 10, 'total_cost_usd': 0.01, 'num_turns': 1, 'usage': {'input_tokens': 100, 'output_tokens': 20, 'output_tokens_details': {'thinking_tokens': 7}}}, ensure_ascii=False))
