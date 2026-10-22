"""Public CI documentation."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import pytest
from ict155 import almacen
AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('servidor_mcp_limites', AQUI / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
JSON_REAL = AQUI / 'limites_conocidos.json'
CAB_LIMITE = '──── LÍMITE CONOCIDO DE ESTE PRECEPTO ────'
CAB_GENERALES = '──── LÍMITES GENERALES ────'

def _cita(ident, obra='BOE-A-2016-5530', titulo='Real Decreto 244/2016', ini=5, fin=6, **extra):
    d = {'estado': 'ENCONTRADO', 'identificador': ident, 'etiqueta_humana': 'Artículo', 'titulo': 't', 'texto_literal': 'texto del precepto', 'obra': obra, 'obra_titulo': titulo, 'version': 'v1', 'fichero': 'f.pdf', 'pagina_inicio': ini, 'pagina_fin': fin, 'regimen': 'publico', 'caracter_juridico': 'vinculante', 'emisor': 'BOE'}
    d.update(extra)
    return d

def _formatear(d, ident=None, nombre='normativa_cita'):
    ident = ident or d['identificador']
    ok, texto, estado = srv.formatear(nombre, ['cita', ident, '--json'], json.dumps(d), {'identificador': ident})
    assert ok
    return texto

@pytest.fixture
def json_propio(tmp_path, monkeypatch):

    def poner(preceptos=(), generales=()):
        ruta = tmp_path / 'limites.json'
        ruta.write_text(json.dumps({'preceptos': list(preceptos), 'generales': list(generales)}), encoding='utf-8')
        monkeypatch.setattr(srv, 'LIMITES_JSON', str(ruta))
    return poner

@pytest.fixture
def errores(monkeypatch):
    registro = []
    monkeypatch.setattr(srv, 'log_err', registro.append)
    return registro
ENTRADA = {'obra': 'BOE-A-2016-5530', 'ruta': '^anexo\\.I/art\\.17\\.4\\.e$', 'aviso': 'AVISO-UNO'}

def test_el_json_del_repositorio_es_valido_y_sus_expresiones_compilan(errores):
    datos = json.loads(almacen.leer(JSON_REAL, encoding='utf-8'))
    preceptos, generales = srv._cargar_limites()
    assert len(preceptos) == len(datos['preceptos']) >= 1
    assert generales == datos['generales'] and len(generales) >= 1
    assert errores == []

def test_una_entrada_que_casa_añade_el_bloque_detras_de_la_vigencia_y_antes_del_contexto(json_propio):
    json_propio([ENTRADA])
    d = _cita('BOE-A-2016-5530::anexo.I/art.17.4.e', vigencia={'fuente': 'BOE', 'consultado': '2026-10-08', 'estado': 'vigente', 'avisos': []}, contexto={'ambito': [], 'padre': {'identificador': 'x::y', 'etiqueta': 'Apartado', 'texto': 'p'}})
    texto = _formatear(d)
    assert CAB_LIMITE in texto and 'AVISO: AVISO-UNO' in texto
    assert texto.index('──── VIGENCIA') < texto.index(CAB_LIMITE) < texto.index('──── CONTEXTO OBLIGATORIO')

def test_la_obra_tambien_casa_por_el_titulo_sin_distinguir_mayusculas(json_propio):
    json_propio([{'obra': 'jcgm 106', 'ruta': '^ap\\.9\\.4\\.7$', 'aviso': 'AVISO-JCGM'}])
    d = _cita('ICT155-DOC-X::ap.9.4.7', obra='ICT155-DOC-X', titulo='JCGM 106:2012 Evaluación', ini=43, fin=45)
    assert 'AVISO: AVISO-JCGM' in _formatear(d)

def test_una_entrada_que_no_casa_no_añade_nada(json_propio):
    json_propio([ENTRADA])
    assert CAB_LIMITE not in _formatear(_cita('BOE-A-2016-5530::anexo.I/art.17.4.d'))
    assert CAB_LIMITE not in _formatear(_cita('BOE-A-2000-1::anexo.I/art.17.4.e', obra='BOE-A-2000-1'))

def test_la_ruta_esta_anclada(json_propio):
    json_propio([ENTRADA])
    assert CAB_LIMITE not in _formatear(_cita('BOE-A-2016-5530::anexo.I/art.17.4.e.1'))

def test_varias_entradas_que_casan_salen_todas(json_propio):
    json_propio([ENTRADA, {'obra': '5530', 'ruta': '^anexo\\.I/', 'aviso': 'AVISO-DOS'}, {'obra': 'otra', 'ruta': '.*', 'aviso': 'AVISO-NO'}])
    texto = _formatear(_cita('BOE-A-2016-5530::anexo.I/art.17.4.e'))
    assert texto.count(CAB_LIMITE) == 1
    assert 'AVISO-UNO' in texto and 'AVISO-DOS' in texto and ('AVISO-NO' not in texto)

def test_documento_entero_con_mas_de_tres_paginas(json_propio):
    json_propio([])
    texto = _formatear(_cita('X::art.1', ini=1, fin=10, paginas_documento=10))
    assert CAB_LIMITE in texto and srv.AVISO_SIN_PAGINA in texto

@pytest.mark.parametrize('ini,fin,total', [(1, 3, 3), (2, 10, 10), (1, 9, 10), (1, 10, 11)])
def test_documento_entero_no_se_aplica_si_no_lo_es_o_el_documento_es_corto(json_propio, ini, fin, total):
    json_propio([])
    assert CAB_LIMITE not in _formatear(_cita('X::art.1', ini=ini, fin=fin, paginas_documento=total))

def test_sin_el_numero_de_paginas_del_documento_la_regla_se_omite(json_propio):
    json_propio([])
    assert CAB_LIMITE not in _formatear(_cita('X::art.1', ini=1, fin=10))

def test_estado_añade_los_limites_generales_al_final(json_propio):
    json_propio(generales=['Primero.', 'Segundo.'])
    ok, texto, _ = srv.formatear('normativa_estado', ['info'], 'Base: 3 documentos\nHuella: abc\n', {})
    assert ok and texto.startswith('Base: 3 documentos\nHuella: abc')
    cola = texto.split(CAB_GENERALES)[1]
    assert '- Primero.' in cola and '- Segundo.' in cola
    assert texto.rstrip().endswith('Lista completa y fechada: D:\\Proyectos\\bd_normativa\\LIMITES_DE_USO.md')

def test_obras_no_lleva_el_bloque_de_estado(json_propio):
    json_propio(generales=['Primero.'])
    ok, texto, _ = srv.formatear('normativa_obras', ['obras'], 'A\nB\n', {})
    assert CAB_GENERALES not in texto

def test_pagina_en_singular_cuando_es_una_sola(json_propio):
    json_propio([])
    texto = _formatear(_cita('X::art.1', ini=58, fin=58))
    assert 'página 58' in texto and 'páginas 58-58' not in texto and ('58-58' not in texto)
    assert 'páginas 5-6' in _formatear(_cita('X::art.1', ini=5, fin=6))

def test_fundamento_y_cotejar_con_un_precepto_que_casa(json_propio):
    json_propio([ENTRADA])
    f = {'estado': 'LOCALIZADO', 'frase': 'x', 'fundamento': 'y', 'motivo': None, 'candidatos': [{'ruta': 'anexo.I/art.17.4.e', 'etiqueta': 'e', 'obra': 'BOE-A-2016-5530', 'identificador': 'BOE-A-2016-5530::anexo.I/art.17.4.e', 'pagina_inicio': 3, 'pagina_fin': 3}]}
    ok, texto, estado = srv.formatear('normativa_fundamento', ['fundamento', 'x', '--json'], json.dumps(f), {})
    assert estado == 'LOCALIZADO' and CAB_LIMITE in texto and ('AVISO: AVISO-UNO' in texto)
    c = {'estado': 'COINCIDE', 'proporcion': 1.0}
    ident = 'BOE-A-2016-5530::anexo.I/art.17.4.e'
    _, texto, _ = srv.formatear('normativa_cotejar', ['cotejar', ident, 'a', '--json'], json.dumps(c), {'identificador': ident, 'afirmacion': 'a'})
    assert CAB_LIMITE in texto and 'AVISO-UNO' in texto
    ident = 'BOE-A-2016-5530::anexo.I/art.17.4.d'
    _, texto, _ = srv.formatear('normativa_cotejar', ['cotejar', ident, 'a', '--json'], json.dumps(c), {'identificador': ident, 'afirmacion': 'a'})
    assert CAB_LIMITE not in texto

def _sin_limites(monkeypatch, tmp_path, contenido):
    ruta = tmp_path / 'roto.json'
    if contenido is not None:
        ruta.write_text(contenido, encoding='utf-8')
    monkeypatch.setattr(srv, 'LIMITES_JSON', str(ruta))

@pytest.mark.parametrize('contenido', [None, '{no es json', '[]', ''])
def test_sin_json_o_con_json_roto_responde_igual_que_antes_y_registra_el_error(monkeypatch, tmp_path, errores, contenido):
    d = _cita('BOE-A-2016-5530::anexo.I/art.17.4.e', ini=5, fin=5)
    con = _formatear(d)
    _sin_limites(monkeypatch, tmp_path, contenido)
    sin = _formatear(d)
    assert CAB_LIMITE in con and CAB_LIMITE not in sin
    assert sin == con.split(CAB_LIMITE)[0].rstrip('\n')
    _, estado_txt, _ = srv.formatear('normativa_estado', ['info'], 'Base\n', {})
    assert estado_txt == 'Base'
    assert errores and 'limites_conocidos.json' in errores[0]

def test_una_entrada_mala_se_ignora_y_las_buenas_siguen(json_propio, errores):
    json_propio([{'obra': 'x', 'ruta': '(', 'aviso': 'a'}, {'obra': 'x'}, 'no soy un objeto', ENTRADA])
    assert [a for _, _, a in srv._cargar_limites()[0]] == ['AVISO-UNO']
    assert len(errores) == 3
    assert 'AVISO-UNO' in _formatear(_cita('BOE-A-2016-5530::anexo.I/art.17.4.e'))

def test_la_version_del_servidor_y_la_del_manifiesto_coinciden():
    assert tuple((int(x) for x in srv.VERSION.split('.'))) >= (1, 3, 0)
    assert json.loads((AQUI / 'mcpb' / 'manifest.json').read_text(encoding='utf-8'))['version'] == srv.VERSION
