"""`normativa_brechas` en la extension de Cowork (11-oct-2026, v1.4.0).

Con dobles de `ejecutar`: no hace falta base ni corpus. Que `brechas` no reproduce texto de una norma con licencia lo
prueba pruebas/test_brechas_2026_10_11.py, con la base sintetica y el codigo real.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest
AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('servidor_mcp_brechas', AQUI / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
INFORME = '# Seguimiento de brechas\n\n## Resumen\n\n- Brechas: 2. Por estado: abierta: 2.\n- Citas: 5. Verificadas: 3. Con aviso: 1. Con error: 1.\n\n## Brechas\n\n### M-08 · Algo\n'

@pytest.fixture(autouse=True)
def _registro_de_pruebas(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, 'AUDIT_DIR', str(tmp_path / 'audit'))
    monkeypatch.setattr(srv, 'AUDIT_LOG', str(tmp_path / 'audit' / 'audit.log'))

@pytest.fixture
def registro(tmp_path):
    f = tmp_path / 'registro.json'
    f.write_text('{}', encoding='utf-8')
    return str(f)

def _ejecutar_falso(monkeypatch, rc, out='', err=''):
    llamadas = []

    def falso(args, entrada=None):
        llamadas.append((args, entrada))
        return (rc, out, err)
    monkeypatch.setattr(srv, 'ejecutar', falso)
    return llamadas

def test_la_herramienta_esta_publicada_y_es_de_consulta():
    t = srv.TOOL_BY_NAME['normativa_brechas']
    assert t['orden'] == 'brechas' and 'brechas' in srv.ORDENES and ('reconstruir' not in srv.ORDENES)
    assert t['inputSchema']['required'] == ['registro']
    pub = srv.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
    assert 'normativa_brechas' in {x['name'] for x in pub}
    assert next((x for x in pub if x['name'] == 'normativa_brechas'))['annotations']['readOnlyHint'] is True
    assert 'tras cada lote de verificación' in t['description']

def test_las_instrucciones_del_servidor_traen_el_punto_nuevo():
    assert 'normativa_brechas(registro): comprueba contra la base todas las citas de un registro de brechas y su última revisión; úsalo tras cada lote de verificación.' in srv.SERVER_INSTRUCTIONS

def test_argumentos_de_la_orden(registro):
    args = srv.argumentos_de_la_orden('normativa_brechas', {'registro': registro})
    assert args == ['brechas', '--ambito', 'publico', '--', registro]
    assert '--salida' not in args and srv.entrada_de_la_orden('normativa_brechas', {'registro': registro}) is None

def test_la_extension_json_no_distingue_mayusculas(tmp_path):
    f = tmp_path / 'REGISTRO.JSON'
    f.write_text('{}', encoding='utf-8')
    assert srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(f)})[-1] == str(f)

def test_ruta_que_no_es_json(tmp_path):
    f = tmp_path / 'registro.txt'
    f.write_text('{}', encoding='utf-8')
    with pytest.raises(srv.ArgumentoMalo, match='\\.json'):
        srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(f)})

def test_ruta_que_no_existe(tmp_path):
    with pytest.raises(srv.ArgumentoMalo, match='no existe'):
        srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(tmp_path / 'nada.json')})

def test_ruta_que_es_un_directorio(tmp_path):
    d = tmp_path / 'carpeta.json'
    d.mkdir()
    with pytest.raises(srv.ArgumentoMalo, match='no es un fichero'):
        srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(d)})

def test_fichero_demasiado_grande_y_justo_por_debajo(tmp_path):
    f = tmp_path / 'grande.json'
    f.write_bytes(b' ' * srv.LARGO_MAXIMO_REGISTRO)
    with pytest.raises(srv.ArgumentoMalo, match='demasiado grande'):
        srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(f)})
    f.write_bytes(b' ' * (srv.LARGO_MAXIMO_REGISTRO - 1))
    assert srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(f)})[-1] == str(f)

@pytest.mark.parametrize('ruta', ['--salida=x.json', '--ambito=reservado.json', 'registro.json', './registro.json'])
def test_una_ruta_que_empieza_por_guiones_o_no_es_absoluta_no_llega_a_la_orden(ruta, monkeypatch):
    llamadas = _ejecutar_falso(monkeypatch, 0, INFORME)
    with pytest.raises(srv.ArgumentoMalo, match='absoluta'):
        srv.argumentos_de_la_orden('normativa_brechas', {'registro': ruta})
    r = srv.call_tool('normativa_brechas', {'registro': ruta})
    assert r['isError'] and 'Error en los argumentos' in r['content'][0]['text'] and (llamadas == [])

def test_una_ruta_absoluta_con_guiones_en_el_nombre_va_detras_del_separador(tmp_path):
    f = tmp_path / '--salida=otro.json'
    f.write_text('{}', encoding='utf-8')
    args = srv.argumentos_de_la_orden('normativa_brechas', {'registro': str(f)})
    assert args[-2:] == ['--', str(f)]

@pytest.mark.parametrize('malo', [{}, {'registro': ''}, {'registro': '   '}, {'registro': 3}, {'registro': ['a.json']}, {'registro': 'a\x00.json'}])
def test_registro_vacio_o_de_otro_tipo(malo):
    with pytest.raises(srv.ArgumentoMalo):
        srv.argumentos_de_la_orden('normativa_brechas', malo)

def test_rc_1_con_informe_es_un_resultado_bueno(registro, monkeypatch):
    llamadas = _ejecutar_falso(monkeypatch, 1, INFORME)
    r = srv.call_tool('normativa_brechas', {'registro': registro})
    assert r['isError'] is False
    assert r['content'][0]['text'] == INFORME.strip()
    assert llamadas == [(['brechas', '--ambito', 'publico', '--', registro], None)]

def test_rc_0_tambien(registro, monkeypatch):
    _ejecutar_falso(monkeypatch, 0, INFORME)
    assert srv.call_tool('normativa_brechas', {'registro': registro})['isError'] is False

def test_el_resumen_de_citas_va_al_registro_de_auditoria(registro, monkeypatch, tmp_path):
    _ejecutar_falso(monkeypatch, 1, INFORME)
    srv.call_tool('normativa_brechas', {'registro': registro})
    linea = (tmp_path / 'audit' / 'audit.log').read_text(encoding='utf-8').strip()
    assert 'normativa_brechas' in linea and 'estado=VERIFICADAS=3;AVISO=1;ERROR=1' in linea
    assert registro not in linea

def test_registro_no_valido_devuelve_todos_los_problemas(registro, monkeypatch):
    problemas = [f"  - brecha B-{i}: «fecha_estado» '' no es una fecha AAAA-MM-DD" for i in range(1, 81)]
    err = 'registro no válido (80 problemas):\n' + '\n'.join(problemas) + '\n'
    _ejecutar_falso(monkeypatch, 2, '', err)
    r = srv.call_tool('normativa_brechas', {'registro': registro})
    texto = r['content'][0]['text']
    assert r['isError'] is True
    assert 'registro no válido (80 problemas)' in texto
    assert 'B-1:' in texto and 'B-80:' in texto and (len(texto) > 800)
    assert all((p.strip() in texto for p in problemas))

def test_otro_error_de_la_orden_tambien_sale_completo(registro, monkeypatch):
    _ejecutar_falso(monkeypatch, 1, '', 'no existe la base X: construyela\nlinea de pymupdf ignorada\n')
    r = srv.call_tool('normativa_brechas', {'registro': registro})
    assert r['isError'] and 'no existe la base X' in r['content'][0]['text'] and ('pymupdf' not in r['content'][0]['text'])

def test_tiempo_agotado(registro, monkeypatch):

    def agotado(args, entrada=None):
        raise srv.subprocess.TimeoutExpired(args, 1)
    monkeypatch.setattr(srv, 'ejecutar', agotado)
    r = srv.call_tool('normativa_brechas', {'registro': registro})
    assert r['isError'] and 'tardó más de 600 s' in r['content'][0]['text']

def test_brechas_tiene_su_propio_plazo_y_las_demas_el_de_siempre(monkeypatch):
    """El registro real (84 citas) tardó 84 s con el PC cargado: con el plazo general (90 s) se cortaría."""
    plazos = []

    def run(cmd, **kw):
        plazos.append((cmd[5], kw['timeout']))
        return srv.subprocess.CompletedProcess(cmd, 0, b'', b'')
    monkeypatch.setattr(srv.subprocess, 'run', run)
    srv.ejecutar(['brechas', '--ambito', 'publico', '--', 'D:\\r.json'])
    srv.ejecutar(['buscar', 'x', '--limite', '1', '--json'])
    assert plazos == [('brechas', 600), ('buscar', srv.TIEMPO_MAXIMO)]

def test_el_informe_pasa_tal_cual_sin_reproducir_nada_mas(registro, monkeypatch):
    """El servidor no añade texto de la base al informe: lo que sale es lo que imprimió `brechas`."""
    informe = INFORME + '| `UNE-EN 12830::ap.5.3.4` | AVISO | literal: deja fuera la condición de su frase [texto de la norma omitido: norma con licencia] |\n'
    _ejecutar_falso(monkeypatch, 1, informe)
    texto = srv.call_tool('normativa_brechas', {'registro': registro})['content'][0]['text']
    assert texto == informe.strip() and '«' not in texto
