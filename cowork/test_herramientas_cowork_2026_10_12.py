"""Public CI documentation."""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import pytest
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from ict155 import brechas, cli, consulta, db, revision, vigencia
_spec = importlib.util.spec_from_file_location('servidor_mcp_herramientas', AQUI / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
HOY = '2026-10-12'
TEXTO_889 = 'a) Real Decreto 889/2006, de 21 de julio, por el que se regula el control metrológico del Estado.'
FRASE_13486 = 'El dispositivo ficticio de ensayo debe conservar un registro auxiliar durante su comprobacion.'
TEXTO_13486 = f'**Quién fija la periodicidad.** «{FRASE_13486}», teniendo en cuenta los requisitos del fabricante.'
TEXTO_A1 = 'El titular conservará el registro de verificaciones durante un periodo mínimo de cinco años.'

def _obra(con, ident, titulo, alias=(), tipo='ley'):
    cur = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, jurisdiccion) VALUES (?,?,?,?)', (ident, tipo, titulo, 'ES'))
    for a in (ident, *alias):
        con.execute('INSERT OR IGNORE INTO obra_alias (obra_id, alias, alias_norm) VALUES (?,?,?)', (cur.lastrowid, a, consulta.norm_alias(a)))
    return cur.lastrowid

def _version(con, obra_id, nombre, etiqueta, preceptos, completitud='completa', regimen='publico', metodo='capa_texto', idioma='es', fecha=None):
    doc = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas, clase_derechos, estado_ingesta) VALUES (?,?,?,?,?,?,?)', (f'{nombre}.pdf', nombre, 1, '2026-01-01', 20, regimen, 'ingerido')).lastrowid
    v = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, idioma, fecha_edicion, fecha_consolidacion, completitud) VALUES (?,?,?,?,?,?,?)', (obra_id, doc, etiqueta, idioma, fecha, fecha, completitud)).lastrowid
    for orden, (ruta, etiqueta_h, texto, pag) in enumerate(preceptos, 1):
        con.execute('INSERT INTO precepto (version_id, ruta_estructural, tipo_unidad, numero, etiqueta_humana, texto_literal, metodo_extraccion, pagina_inicio, pagina_fin, orden) VALUES (?,?,?,?,?,?,?,?,?,?)', (v, ruta, 'articulo', ruta.rsplit('.', 1)[-1], etiqueta_h, texto, metodo, pag, pag, orden))

def _rutas(*rutas):
    return [(r, r, f'Texto del precepto {r}.', i) for i, r in enumerate(rutas, 1)]

@pytest.fixture(scope='module')
def con(tmp_path_factory):
    c = db.crear(tmp_path_factory.mktemp('herramientas') / 'h.sqlite')
    r30 = _obra(c, 'CELEX-32022R0030', 'Reglamento Delegado (UE) 2022/30 de la Comisión', ['Reglamento Delegado (UE) 2022/30'])
    _version(c, r30, 'r30', 'consolidada 2023-10-27', _rutas('art.1'), fecha='2023-10-27')
    for sufijo in ('en_COMPLETO', 'es_TRUNCADO'):
        o = _obra(c, f'ICT155-DOC-DOUE_Reglamento_Delegado_2022-30_ciberseguridad_RED_{sufijo}', f'Copia {sufijo}')
        _version(c, o, f'r30_{sufijo}', 'original', _rutas('art.1'), fecha='2022-01-01')
    d339 = _obra(c, 'DOUE-2026-339', 'Reglamento Delegado (UE) 2026/339 por el que se deroga el 2022/30')
    _version(c, d339, 'd339', 'original', _rutas('art.1'))
    rd244 = _obra(c, 'BOE-A-2016-5530', 'Real Decreto 244/2016', ['RD 244/2016'])
    _version(c, rd244, 'rd244', 'consolidada 2025-04-12', [('disp.derogatoria.1.a', 'Disposición derogatoria única, letra a)', TEXTO_889, 46), ('art.1', 'Artículo 1', TEXTO_A1, 3)], fecha='2025-04-12')
    orden = _obra(c, 'BOE-A-2020-2573', 'Orden ICT/155/2020', ['Orden ICT/155/2020'])
    _version(c, orden, 'orden', 'consolidada 2025-10-03', _rutas('anexo.I', 'anexo.I/ap.1', 'anexo.I/ap.2', 'anexo.I/ap.3', 'anexo.I/apend.I', 'anexo.XI', 'anexo.XI/ap.1', 'anexo.XI/ap.2', 'anexo.XI/ap.3', 'anexo.XI/ap.3.a', 'anexo.XI/ap.4', 'anexo.XI/ap.5', 'anexo.XI/ap.6', 'anexo.XI/apend.I', 'anexo.XI/apend.II', 'anexo.XII', 'anexo.XII/ap.1'), fecha='2025-10-03')
    larga = _obra(c, 'BOE-A-2019-7', 'Ley larga de prueba')
    _version(c, larga, 'larga', 'v1', _rutas(*[f'art.{n}' for n in range(1, 21)], 'anexo.I'))
    en = _obra(c, 'ICT155-DOC-NORMA_PAGO_26', 'EUROPEAN STANDARD', ['EN 12830', 'EN 12830:2018'], tipo='guia')
    _version(c, en, 'en12830', 'edicion 2018', _rutas('ap.7', 'ap.8', 'ap.9'), regimen='licenciado', idioma='en')
    par = _obra(c, 'ICT155-DOC-NORMA_PAGO_27_PARCIAL', 'NORMA_PAGO_27', tipo='guia')
    _version(c, par, 'en12830p', 'edicion 2018', [('ap.3.7', 'Apartado 3.7', '3.7 indication of a measuring instrument [EN 12830:2018] (E) 7', 9)], completitud='parcial', regimen='licenciado', idioma='en')
    en13486 = _obra(c, 'EN-13486-2023', 'EN 13486:2023 Temperature recorders', ['EN 13486:2023'], tipo='norma_tecnica')
    _version(c, en13486, 'en13486', 'transcripcion verificada', [('ap.4', 'Frecuencia y tipo de verificación (cláusula 4)', TEXTO_13486, 5)], completitud='parcial', regimen='licenciado', metodo='transcripcion_verificada', idioma='en')
    ocr = _obra(c, 'EN-999001', 'EN 99999 por reconocimiento optico', ['EN 99999:2020'], tipo='norma_tecnica')
    _version(c, ocr, 'en99999', 'reconocimiento optico', [('pag.4', 'Página 4', 'El sistema se verificará cada año por un laboratorio acreditado.', 4)], metodo='ocr', regimen='licenciado')
    normal = _obra(c, 'BOE-A-2020-1', 'Orden de prueba sobre registros', ['Orden PRB/1/2020'])
    _version(c, normal, 'normal', 'v1', [('art.1', 'Artículo 1', TEXTO_A1, 3)])
    c.commit()
    yield c
    c.close()

@pytest.fixture
def cli_con_base(con, monkeypatch):
    monkeypatch.setattr(db, 'conectar', lambda ruta=None, solo_lectura=False: con)

@pytest.fixture(autouse=True)
def _registro_de_pruebas(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, 'AUDIT_DIR', str(tmp_path / 'audit'))
    monkeypatch.setattr(srv, 'AUDIT_LOG', str(tmp_path / 'audit' / 'audit.log'))

def _mod_deroga():
    return {'id': '32026R0339', 'fecha_documento': '2026-02-16', 'fecha_vigor': '2026-05-19', 'titulo': 'Reglamento Delegado (UE) 2026/339 de la Comisión, de 16 de febrero de 2026, por el que se deroga el Reglamento Delegado (UE) 2022/30', 'relacion': 'DEROGA (parcial o con efecto futuro)', 'fecha_comparada': '2026-05-19', 'obra_en_la_base': 'DOUE-2026-339', 'en_la_base': True}

def _datos_vigencia(*mods, obra='CELEX-32022R0030', oficial='32022R0030', version='2023-10-27'):
    return {'consultado': '2026-10-12T08:00:00Z', 'fuentes': {'BOE': vigencia.AVISO_BOE, 'CELLAR': vigencia.AVISO_CELLAR}, 'obras': {obra: {'identificador_oficial': oficial, 'fecha_version': version, 'consulta': {'fuente': 'CELLAR', 'estado': 'vigente'}, 'modificaciones_posteriores': list(mods)}}}

def _salida_json(capsys, argv):
    assert cli.main(argv) == 0
    return json.loads(capsys.readouterr().out)

def test_1_vigencia_prefiere_la_obra_legislativa_y_las_otras_copias_van_aparte(con, cli_con_base, monkeypatch, capsys):
    """Public CI documentation."""
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: _datos_vigencia(_mod_deroga()))
    for texto in ('2022/30', 'Reglamento Delegado 2022/30', 'Reglamento Delegado (UE) 2022/30'):
        obras, otras, no_leg = vigencia.obras_de_la_norma(con, texto)
        assert obras == ['CELEX-32022R0030'] and no_leg == [], texto
        assert len(otras['CELEX-32022R0030']) == 2 and all((c.startswith('ICT155-DOC-DOUE_') for c in otras['CELEX-32022R0030']))
    d = _salida_json(capsys, ['vigencia', '2022/30', '--json'])
    assert list(d['obras']) == ['CELEX-32022R0030'] and d['obras']['CELEX-32022R0030'] is not None
    assert len(d['otras_copias']['CELEX-32022R0030']) == 2 and 'no_esta_en_la_base' not in d
    ok, texto, estado = srv.formatear('normativa_vigencia', ['vigencia', '--json', '--', '2022/30'], json.dumps(d), {'obra': '2022/30'})
    assert ok and 'no es legislación' not in texto and ('CELEX-32022R0030' in texto)
    assert 'otras copias de esta misma norma' in texto and estado == 'OBRAS=1;CON_AVISO=1'

def test_1_quien_pide_una_copia_por_su_identificador_exacto_recibe_esa_copia(con):
    copia = 'ICT155-DOC-DOUE_Reglamento_Delegado_2022-30_ciberseguridad_RED_en_COMPLETO'
    assert vigencia.obras_de_la_norma(con, copia) == ([copia], {}, [])
    assert vigencia.obras_de_la_norma(con, 'ict155-doc-doue_reglamento_delegado_2022-30_ciberseguridad_red_en_completo')[0] == [copia]
    assert vigencia.obras_de_la_norma(con, 'EN-13486-2023') == ([], {}, ['EN-13486-2023'])

def test_1_vigencia_de_una_norma_que_no_esta_dice_que_la_base_no_la_tiene(con, cli_con_base, monkeypatch, capsys):
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: _datos_vigencia())
    d = _salida_json(capsys, ['vigencia', 'RD 889/2006', '--json'])
    assert d['obras'] == {} and list(d['no_esta_en_la_base']) == ['RD 889/2006']
    assert d['no_esta_en_la_base']['RD 889/2006']['menciones'] == ['BOE-A-2016-5530::disp.derogatoria.1.a']
    ok, texto, estado = srv.formatear('normativa_vigencia', ['vigencia', '--json', '--', 'RD 889/2006'], json.dumps(d), {'obra': 'RD 889/2006'})
    assert ok and 'no es legislación' not in texto
    assert 'la base NO tiene esa norma' in texto and 'normativa_buscar' in texto
    assert 'BOE-A-2016-5530::disp.derogatoria.1.a' in texto and estado == 'OBRAS=0;CON_AVISO=0;NO_ESTA=1'

def test_1_una_obra_que_no_es_legislacion_sigue_diciendo_que_no_lo_es(con, cli_con_base, monkeypatch, capsys):
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: _datos_vigencia())
    d = _salida_json(capsys, ['vigencia', 'EN 12830:2018', '--json'])
    assert d['obras'] == {'ICT155-DOC-NORMA_PAGO_26': None} and 'no_esta_en_la_base' not in d

def test_2_precepto_inexistente_propone_el_padre_y_los_hermanos_que_existen(con):
    r = consulta.resolver(con, 'Orden ICT/155/2020::anexo.XI/ap.9')
    assert r.estado == consulta.PRECEPTO_INEXISTENTE
    assert r.candidatos == ['anexo.XI', 'anexo.XI/ap.1', 'anexo.XI/ap.2', 'anexo.XI/ap.3', 'anexo.XI/ap.4', 'anexo.XI/ap.5', 'anexo.XI/ap.6', 'anexo.XI/apend.I', 'anexo.XI/apend.II']
    assert not any((c.startswith('anexo.I/') or c == 'anexo.I' for c in r.candidatos))

def test_2_los_hermanos_de_la_misma_clase_van_antes_que_los_apendices_y_un_apartado_con_hijos_propone_a_sus_hijos(con):
    r = consulta.resolver(con, 'Orden ICT/155/2020::anexo.XI/ap.3.d')
    assert r.estado == consulta.PRECEPTO_INEXISTENTE and r.candidatos == ['anexo.XI/ap.3', 'anexo.XI/ap.3.a']

def test_2_sin_padre_que_exista_salen_los_de_primer_nivel_mas_parecidos(con):
    r = consulta.resolver(con, 'BOE-A-2019-7::art.30')
    assert r.estado == consulta.PRECEPTO_INEXISTENTE
    assert len(r.candidatos) == consulta.MAXIMO_CERCANOS and 'art.20' in r.candidatos and ('art.1' not in r.candidatos)
    assert r.candidatos == sorted(r.candidatos, key=lambda c: (c.startswith('anexo'), int(c.split('.')[1]) if c.startswith('art') else 0))

def test_3_buscar_el_nombre_de_una_norma_empieza_por_la_obra_que_la_tiene_completa(con, cli_con_base, capsys):
    """Public CI documentation."""
    d = _salida_json(capsys, ['buscar', 'EN 12830:2018', '--json', '--con-obras'])
    assert [o['identificador'] for o in d['obras']] == ['ICT155-DOC-NORMA_PAGO_26']
    v, = d['obras'][0]['versiones']
    assert v['completitud'] == 'completa' and v['regimen'] == 'licenciado' and (v['preceptos'] == 3)
    assert d['obras'][0]['alias'][0] == 'EN 12830:2018'
    assert any((f['obra'].endswith('_PARCIAL') for f in d['resultados']))
    ok, texto, estado = srv.formatear('normativa_buscar', ['buscar', 'EN 12830:2018', '--json', '--con-obras'], json.dumps(d), {'texto': 'EN 12830:2018'})
    assert ok and texto.startswith('OBRAS DE LA BASE que se llaman «EN 12830:2018»')
    cabecera = texto.split('resultado(s)')[0]
    assert 'ICT155-DOC-NORMA_PAGO_26' in cabecera and 'COMPLETA' in cabecera and ('licenciado' in cabecera)
    assert '«EN 12830:2018::ruta»' in cabecera

def test_3_la_copia_parcial_se_dice_parcial_y_sin_la_opcion_sale_la_lista_de_siempre(con, cli_con_base, capsys):
    o = consulta.obras_para_buscar(con, 'ICT155-DOC-NORMA_PAGO_27_PARCIAL')
    assert 'PARCIAL' in '\n'.join(o[0]['lineas']) and 'no prueba que la norma no lo tenga' in '\n'.join(o[0]['lineas'])
    d = _salida_json(capsys, ['buscar', 'EN 12830:2018', '--json'])
    assert isinstance(d, list) and all(('obra' in f for f in d))
    assert cli.main(['buscar', 'palabrainexistente', '--json', '--con-obras']) == 1

def test_3_un_texto_que_no_es_el_nombre_de_ninguna_obra_no_cambia_la_salida(con, cli_con_base, capsys):
    assert consulta.obras_para_buscar(con, 'periodo mínimo de cinco años') == []
    assert consulta.obras_para_buscar(con, '   ') == [] and consulta.obras_para_buscar(con, '¿?') == []
    d = _salida_json(capsys, ['buscar', 'periodo mínimo de cinco años', '--json', '--con-obras'])
    assert d['obras'] == [] and d['resultados']
    ok, texto, _ = srv.formatear('normativa_buscar', ['buscar', 'x', '--json', '--con-obras'], json.dumps(d), {'texto': 'x'})
    assert ok and (not texto.startswith('OBRAS')) and ('resultado(s)' in texto)

def _cita(ident, obra='BOE-A-2020-1', titulo='Orden de prueba sobre registros', **extra):
    d = {'estado': 'ENCONTRADO', 'identificador': ident, 'etiqueta_humana': 'Artículo', 'titulo': 't', 'texto_literal': 'texto del precepto', 'obra': obra, 'obra_titulo': titulo, 'version': 'v1', 'fichero': 'f.pdf', 'pagina_inicio': 5, 'pagina_fin': 5, 'regimen': 'publico', 'caracter_juridico': 'vinculante', 'emisor': 'BOE'}
    d.update(extra)
    return d

@pytest.fixture
def limites(tmp_path, monkeypatch):

    def poner(*entradas):
        ruta = tmp_path / 'limites.json'
        ruta.write_text(json.dumps({'preceptos': list(entradas), 'generales': []}), encoding='utf-8')
        monkeypatch.setattr(srv, 'LIMITES_JSON', str(ruta))
    return poner

def test_4_cita_pasa_a_los_limites_tambien_el_alias_escrito(limites):
    """Public CI documentation."""
    limites({'obra': 'orden prb/1/2020', 'ruta': '^art\\.1$', 'aviso': 'AVISO-DEL-ALIAS'})
    ident = 'Orden PRB/1/2020::art.1'
    ok, texto, _ = srv.formatear('normativa_cita', ['cita', ident, '--json'], json.dumps(_cita(ident)), {'identificador': ident})
    assert ok and '──── LÍMITE CONOCIDO DE ESTE PRECEPTO ────' in texto and ('AVISO: AVISO-DEL-ALIAS' in texto)
    ident2 = 'BOE-A-2020-1::art.1'
    _, texto2, _ = srv.formatear('normativa_cita', ['cita', ident2, '--json'], json.dumps(_cita(ident2)), {'identificador': ident2})
    assert 'AVISO-DEL-ALIAS' not in texto2

def test_4_la_fecha_del_alias_escrito_no_estorba(limites):
    limites({'obra': 'orden prb/1/2020', 'ruta': '^art\\.1$', 'aviso': 'AVISO-DEL-ALIAS'})
    ident = 'Orden PRB/1/2020@2026-01-01::art.1'
    _, texto, _ = srv.formatear('normativa_cita', ['cita', ident, '--json'], json.dumps(_cita(ident)), {'identificador': ident})
    assert 'AVISO-DEL-ALIAS' in texto

def _registro(*citas):
    return {'cliente': 'c', 'informe': 'i', 'brechas': [{'id': 'B-1', 'estado': 'abierta', 'fecha_estado': '2026-10-12', 'citas': list(citas)}]}

@pytest.fixture
def vigencia_al_dia(monkeypatch):
    datos = _datos_vigencia(obra='BOE-A-2020-1', oficial='BOE-A-2020-1', version='2020-02-01')
    datos['obras']['BOE-A-2020-1']['consulta']['fuente'] = 'BOE'
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: datos)
    return datos

def test_5_brechas_ensena_los_limites_de_cada_cita_con_el_canonico_y_el_alias_escrito(con, limites, vigencia_al_dia):
    limites({'obra': 'BOE-A-2020-1', 'ruta': '^art\\.1$', 'aviso': 'AVISO-DEL-CANONICO'}, {'obra': 'orden prb/1/2020', 'ruta': '^art\\.1$', 'aviso': 'AVISO-DEL-ALIAS'}, {'obra': 'BOE-A-2020-1', 'ruta': '^art\\.2$', 'aviso': 'OTRO-PRECEPTO'})
    reg = _registro({'identificador': 'Orden PRB/1/2020::art.1'}, {'identificador': 'BOE-A-2020-1::art.1'})
    r = brechas.comprobar(con, reg, avisos_de_limites=srv._avisos_de_limites)[0]
    alias, canonica = r.citas
    assert alias.nivel == brechas.AVISO and 'límite conocido: AVISO-DEL-CANONICO' in alias.detalle
    assert 'límite conocido: AVISO-DEL-ALIAS' in alias.detalle and 'OTRO-PRECEPTO' not in ' '.join(alias.detalle)
    assert 'límite conocido: AVISO-DEL-CANONICO' in canonica.detalle and 'AVISO-DEL-ALIAS' not in ' '.join(canonica.detalle)
    md = brechas.informe_markdown(con, reg, [r])
    assert 'límite conocido: AVISO-DEL-ALIAS' in md and 'Con aviso: 2' in md

def test_5_una_cita_que_no_casa_con_ningun_limite_sale_limpia_y_un_error_no_los_busca(con, limites, vigencia_al_dia):
    limites({'obra': 'BOE-A-2020-1', 'ruta': '^art\\.1$', 'aviso': 'AVISO-X'})
    reg = _registro({'identificador': 'BOE-A-2020-1::art.99'}, {'identificador': 'BOE-A-2016-5530::art.1'})
    r = brechas.comprobar(con, reg, avisos_de_limites=srv._avisos_de_limites)[0]
    assert all(('AVISO-X' not in ' '.join(c.detalle) for c in r.citas))
    assert r.citas[0].nivel == brechas.ERROR

def test_5_brechas_carga_por_defecto_la_misma_funcion_que_cita(con, vigencia_al_dia, cli_con_base, tmp_path, capsys, monkeypatch):
    fn = brechas.avisos_de_limites_de_cowork()
    assert callable(fn) and fn.__name__ == '_avisos_de_limites' and (fn.__code__.co_code == srv._avisos_de_limites.__code__.co_code)
    monkeypatch.setattr(brechas, '_LIMITES_DE_COWORK', [lambda obras, ruta: ['AVISO-DE-LA-CLI'] if 'BOE-A-2020-1' in obras else []])
    f = tmp_path / 'registro.json'
    f.write_text(json.dumps(_registro({'identificador': 'Orden PRB/1/2020::art.1'})), encoding='utf-8')
    assert cli.main(['brechas', str(f)]) == 0
    assert 'límite conocido: AVISO-DE-LA-CLI' in capsys.readouterr().out

def test_6_un_acto_que_deroga_sale_como_derogacion_posterior_y_no_como_modificada():
    v = vigencia.vigencia_de('CELEX-32022R0030', _datos_vigencia(_mod_deroga()), hoy=HOY)
    aviso, = v['avisos']
    assert aviso.startswith('DEROGACIÓN posterior a la versión de la base (2023-10-27): 32026R0339')
    assert 'MODIFICADA' not in aviso and 'efecto diferido' in aviso and ('hay que leer el acto' in aviso)
    assert 'su texto está en la base como DOUE-2026-339' in aviso and 'normativa_cita «DOUE-2026-339»' in aviso

def test_6_si_el_acto_no_esta_en_la_base_se_dice_y_una_modificacion_normal_sigue_siendo_modificada():
    sin_base = dict(_mod_deroga(), obra_en_la_base=None, en_la_base=False)
    aviso, = vigencia.vigencia_de('CELEX-32022R0030', _datos_vigencia(sin_base), hoy=HOY)['avisos']
    assert aviso.startswith('DEROGACIÓN posterior') and 'que la base NO tiene' in aviso and ('fuente oficial' in aviso)
    modifica = {'id': '32023R2444', 'titulo': 'Reglamento Delegado (UE) 2023/2444 por el que se modifica el 2022/30', 'relacion': 'MODIFICA', 'fecha_comparada': '2023-10-27', 'en_la_base': False}
    aviso, = vigencia.vigencia_de('CELEX-32022R0030', _datos_vigencia(modifica, version='2022-01-01'), hoy=HOY)['avisos']
    assert aviso.startswith('MODIFICADA después de la versión de la base') and 'DEROGACIÓN' not in aviso

def test_6_derogacion_futura_o_dudosa_tambien_dicen_derogacion():
    futura = dict(_mod_deroga(), futura=True)
    dudosa = dict(_mod_deroga(), dudosa=True)
    assert vigencia.vigencia_de('CELEX-32022R0030', _datos_vigencia(futura), hoy=HOY)['avisos'][0].startswith('DEROGACIÓN posterior aprobada que aún no ha entrado en vigor')
    assert vigencia.vigencia_de('CELEX-32022R0030', _datos_vigencia(dudosa), hoy=HOY)['avisos'][0].startswith('posible DEROGACIÓN posterior a la versión de la base')

def test_6_la_derogacion_llega_igual_a_cita_a_brechas_y_a_vigencia(con, monkeypatch):
    datos = _datos_vigencia(_mod_deroga())
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: datos)
    c = brechas.comprobar(con, _registro({'identificador': 'Reglamento Delegado (UE) 2022/30::art.1'}), avisos_de_limites=None)[0].citas[0]
    assert c.nivel == brechas.AVISO and c.detalle[0].startswith('vigencia: DEROGACIÓN posterior')
    v = vigencia.vigencia_de('CELEX-32022R0030', datos, hoy=HOY)
    d = _cita('Reglamento Delegado (UE) 2022/30::art.1', obra='CELEX-32022R0030', vigencia=v)
    _, texto, _ = srv.formatear('normativa_cita', ['cita', 'x', '--json'], json.dumps(d), {'identificador': d['identificador']})
    assert 'AVISO: DEROGACIÓN posterior a la versión de la base' in texto and 'MODIFICADA' not in texto
    _, texto, _ = srv.formatear('normativa_vigencia', ['vigencia', '--json'], json.dumps({'consultado': '2026-10-12', 'obras': {'CELEX-32022R0030': v}}), {})
    assert 'AVISO: DEROGACIÓN posterior a la versión de la base' in texto
T_2026_1738 = 'Reglamento (UE) 2026/1738 del Parlamento Europeo y del Consejo, de 8 de julio de 2026, relativo a los requisitos de circularidad aplicables al diseño de los vehículos y a la gestión de los vehículos al final de su vida útil, por el que se modifican los Reglamentos (UE) n.° 168/2013, (UE) 2018/858, (UE) 2019/1020 y (UE) 2023/1542, y se derogan las Directivas 2000/53/CE y 2005/64/CE (Texto pertinente a efectos del EEE)'
T_2023_1542 = 'Reglamento (UE) 2023/1542 del Parlamento Europeo y del Consejo, de 12 de julio de 2023, relativo a las pilas y baterías y sus residuos y por el que se modifican la Directiva 2008/98/CE y el Reglamento (UE) 2019/1020 y se deroga la Directiva 2006/66/CE (Texto pertinente a efectos del EEE)'
T_2018_1139 = 'Reglamento (UE) 2018/1139 del Parlamento Europeo y del Consejo de 4 de julio de 2018 sobre normas comunes en el ámbito de la aviación civil y por el que se crea una Agencia de la Unión Europea para la Seguridad Aérea y por el que se modifican los Reglamentos (CE) n.o 2111/2005, (CE) n.o 1008/2008, (UE) n.o 996/2010 y (UE) n.o 376/2014 y las Directivas 2014/30/UE y 2014/53/UE del Parlamento Europeo y del Consejo y se derogan los Reglamentos (CE) n.o 552/2004 y (CE) n.o 216/2008 del Parlamento Europeo y del Consejo y el Reglamento (CEE) n.o 3922/91 del Consejo(Texto pertinente a efectos del EEE.)'

def _aviso(obra, oficial, titulo, version='2020-01-01', relacion='MODIFICA', **extra):
    mod = {'id': '32026R9999', 'titulo': titulo, 'relacion': relacion, 'fecha_comparada': '2026-05-19', 'en_la_base': False}
    mod.update(extra)
    a, = vigencia.vigencia_de(obra, _datos_vigencia(mod, obra=obra, oficial=oficial, version=version), hoy=HOY)['avisos']
    return a

def test_6_solo_deroga_esta_norma_si_el_titulo_nombra_su_numero_en_lo_que_deroga():
    """Public CI documentation."""
    assert _aviso('CELEX-32022R0030', '32022R0030', _mod_deroga()['titulo']).startswith('DEROGACIÓN posterior')
    for obra, oficial, titulo in (('CELEX-32023R1542', '32023R1542', T_2026_1738), ('CELEX-32019R1020', '32019R1020', T_2026_1738), ('CELEX-32019R1020', '32019R1020', T_2023_1542), ('CELEX-32014L0053', '32014L0053', T_2018_1139), ('CELEX-32001L0083', '32001L0083', 'Reglamento (UE) 2017/745 ... por el que se modifican la Directiva 2001/83/CE y por el que se derogan las Directivas 90/385/CEE y 93/42/CEE del Consejo')):
        aviso = _aviso(obra, oficial, titulo)
        assert aviso.startswith('MODIFICADA después de la versión de la base') and 'DEROGACIÓN' not in aviso, (obra, titulo[:50])

def test_6_un_titulo_recortado_sin_el_numero_no_es_derogacion_ni_cuenta_la_relacion_de_la_fuente():
    recortado = 'Reglamento Delegado (UE) 2026/339 de la Comisión, de 16 de febrero de 2026, por el que se deroga el Reglamento Delegado (UE)'
    for titulo in (recortado, recortado + ' 2022', 'Reglamento Delegado (UE) 2026/339, por el que se deroga', 'Reglamento Delegado (UE) 2026/339'):
        aviso = _aviso('CELEX-32022R0030', '32022R0030', titulo, relacion='DEROGA (parcial o con efecto futuro)')
        assert aviso.startswith('MODIFICADA') and 'DEROGACIÓN' not in aviso, titulo

def test_6_el_numero_ha_de_estar_en_lo_que_se_deroga_y_entero():
    c = lambda titulo: _aviso('CELEX-32022R0030', '32022R0030', titulo).startswith('DEROGACIÓN')
    assert c('Reglamento (UE) 2026/1 por el que se deroga el Reglamento Delegado (UE) 2022/30')
    assert c('Reglamento (UE) 2026/1 por el que se deroga el Reglamento Delegado (UE) 2021/5 y el Reglamento Delegado (UE) 2022/30')
    assert not c('Reglamento (UE) 2026/1 por el que se deroga el Reglamento Delegado (UE) 2022/301')
    assert not c('Reglamento (UE) 2026/1 por el que se deroga el Reglamento (UE) 2021/5 y se modifica el Reglamento Delegado (UE) 2022/30')
    assert not c('Reglamento (UE) 2026/1 por el que se deroga la Directiva 2006/66/CE, que modifica el Reglamento Delegado (UE) 2022/30')
    assert c('Reglamento (UE) 2026/1 por el que se deroga el Reglamento Delegado (UE) 2022/30 y se modifica la Directiva 2006/66/CE')
    assert not c('Reglamento (UE) 2026/1 por el que se modifica el Reglamento Delegado (UE) 2022/30 y se deroga la Directiva 2006/66/CE')

def test_6_los_reglamentos_antiguos_se_nombran_n_barra_ano_y_los_boe_por_el_numero_de_su_titulo():
    assert vigencia.numeros_de_la_norma('32022R0030') == ['2022/30', '30/2022']
    assert '37/2005' in vigencia.numeros_de_la_norma('32005R0037') and '98/34' in vigencia.numeros_de_la_norma('31998L0034')
    assert vigencia.numeros_de_la_norma('BOE-A-2016-5530', 'Real Decreto 244/2016, de 3 de junio, por el que se desarrolla la Ley 32/2014') == ['244/2016']
    assert vigencia.numeros_de_la_norma('BOE-A-2017-13543', 'Resolución de 2 de noviembre, por la que se publica') == []
    assert _aviso('CELEX-32008R0216', '32008R0216', T_2018_1139).startswith('DEROGACIÓN posterior')
    boe = {'id': 'BOE-A-2027-1', 'texto': 'Real Decreto 1/2027, de 5 de enero, por el que se deroga el Real Decreto 244/2016, de 3 de junio', 'fecha_comparada': '2027-01-06', 'en_la_base': False}
    datos = {'consultado': '2027-02-01T00:00:00Z', 'fuentes': {}, 'obras': {'BOE-A-2016-5530': {'identificador_oficial': 'BOE-A-2016-5530', 'fecha_version': '2025-04-12', 'consulta': {'fuente': 'BOE', 'estado': 'vigente', 'titulo': 'Real Decreto 244/2016, de 3 de junio, por el que se desarrolla la Ley 32/2014'}, 'modificaciones_posteriores': [boe, dict(boe, id='BOE-A-2027-2', texto='Real Decreto 2/2027 por el que se deroga el Real Decreto 889/2006')]}}}
    a1, a2 = vigencia.vigencia_de('BOE-A-2016-5530', datos, hoy='2027-02-01')['avisos']
    assert a1.startswith('DEROGACIÓN posterior') and a2.startswith('MODIFICADA')

@pytest.mark.parametrize('escrita,canonica', [('anexo.XI/apendice.III', 'anexo.XI/apend.III'), ('anexo.XI/apéndice.III', 'anexo.XI/apend.III'), ('Anexo.XI/Apendice.III', 'anexo.XI/apend.III'), ('apendice.iii', 'apend.iii'), ('anexo.XI/apartado.2', 'anexo.XI/ap.2'), ('articulo.8.1', 'art.8.1'), ('artículo.13.4', 'art.13.4'), ('disposicion.final.2', 'disp.final.2'), ('disposición.transitoria.1.1', 'disp.transitoria.1.1'), ('libro.2/título.I/capítulo.II/sección.1', 'libro.2/titulo.I/capitulo.II/seccion.1'), ('preámbulo', 'preambulo'), ('anexo.A/clausula.4.3', 'anexo.A/ap.4.3'), ('requisito.U1', 'req.U1'), ('anexo.XI/apend.III', 'anexo.XI/apend.III'), ('itc.IF-01/ap.1', 'itc.IF-01/ap.1'), ('art.13.4', 'art.13.4'), ('disp.final.2', 'disp.final.2'), ('req.U1', 'req.U1'), ('formula_final', 'formula_final'), ('pag.4', 'pag.4'), ('anexo.sn', 'anexo.sn'), ('foo.1/bar', 'foo.1/bar'), ('', '')])
def test_8_las_formas_largas_de_las_clases_se_llevan_a_la_forma_de_la_base(escrita, canonica):
    assert consulta.ruta_canonica(escrita) == canonica
    assert consulta.ruta_canonica(canonica) == canonica

def test_8_partir_identificador_da_la_ruta_canonica_y_resolver_encuentra_el_apendice(con):
    assert consulta.partir_identificador('Orden ICT/155/2020@2025-10-03::anexo.XI/apendice.II') == ('Orden ICT/155/2020@2025-10-03', 'anexo.XI/apend.II')
    for escrita, esperado in (('anexo.XI/apendice.II', 'anexo.XI/apend.II'), ('anexo.XI/apéndice.II', 'anexo.XI/apend.II'), ('anexo.XI/apartado.2', 'anexo.XI/ap.2'), ('Anexo.XI/Apartado.2', 'anexo.XI/ap.2')):
        r = consulta.resolver(con, f'Orden ICT/155/2020::{escrita}')
        assert r.estado == consulta.ENCONTRADO and r.identificador == f'Orden ICT/155/2020::{escrita}', escrita
        assert r.texto_literal == f'Texto del precepto {esperado}.', escrita
    for escrita in ('articulo.1', 'artículo.1'):
        assert consulta.resolver(con, f'Orden PRB/1/2020::{escrita}').estado == consulta.ENCONTRADO

def test_8_el_resto_del_sistema_tambien_lee_la_ruta_canonica(con, cli_con_base, capsys):
    """Public CI documentation."""
    assert cli.main(['cotejar', 'Orden PRB/1/2020::articulo.1', 'El titular conservará el registro de verificaciones', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['estado'] == 'COINCIDE'
    inf = revision.revisar(con, 'Dice `Orden PRB/1/2020::articulo.1`:\n\n> El titular conservará el registro de verificaciones durante un periodo mínimo\n')
    assert [(c.tipo, c.nivel) for c in inf.comprobaciones if c.tipo in ('identificador', 'literal')] == [('identificador', revision.OK), ('literal', revision.OK)]
    _, texto = consulta.texto_de_ambito(con, 'Orden PRB/1/2020::articulo.1')
    assert texto == TEXTO_A1

def test_8_si_la_clase_pedida_no_existe_pero_otra_con_el_mismo_numeral_si_se_propone(con):
    r = consulta.resolver(con, 'Orden ICT/155/2020::anexo.XI/appendix.II')
    assert r.estado == consulta.FUERA_DE_ALCANCE and r.candidatos == ['anexo.XI/apend.II']
    assert '¿quieres decir `anexo.XI/apend.II`?' in r.detalle and 'no es que no este troceada' in r.detalle
    assert 'NINGUNA' not in r.detalle
    r2 = consulta.resolver(con, 'Orden ICT/155/2020::anexo.XI/appendix.IX')
    assert r2.estado == consulta.FUERA_DE_ALCANCE and 'NINGUNA unidad de clase `appendix.`' in r2.detalle and (r2.candidatos is None)
    r3 = consulta.resolver(con, 'Orden ICT/155/2020::anexo.XI/apendice.IX')
    assert r3.estado == consulta.PRECEPTO_INEXISTENTE and 'anexo.XI/apend.II' in r3.candidatos

def test_8_la_propuesta_llega_a_cowork(con):
    ident = 'Orden ICT/155/2020::anexo.XI/appendix.II'
    r = consulta.resolver(con, ident)
    ok, texto, estado = srv.formatear('normativa_cita', ['cita', ident, '--json'], json.dumps(r.dict()), {'identificador': ident})
    assert ok and estado == 'FUERA_DE_ALCANCE' and ('¿quieres decir `anexo.XI/apend.II`?' in texto)

def test_7_la_naturaleza_del_texto():
    assert consulta.naturaleza_del_texto('v1', 'completa') is None
    assert consulta.naturaleza_del_texto('consolidada 2025-10-03', 'completa', 'capa_texto') is None
    assert consulta.naturaleza_del_texto('transcripcion verificada', 'completa') == 'transcripción de ICT155, NO es el literal de la norma: solo lo entrecomillado es literal'
    assert consulta.naturaleza_del_texto('reconocimiento optico', 'completa') == 'reconocimiento óptico: puede tener errores de lectura'
    assert consulta.naturaleza_del_texto('edicion 2018', 'parcial') == 'ejemplar PARCIAL: no es la norma entera'
    assert consulta.naturaleza_del_texto('edicion 2019', 'extracto').startswith('ejemplar EXTRACTO')
    assert consulta.naturaleza_del_texto('v1', 'completa', 'ocr') == 'reconocimiento óptico: puede tener errores de lectura'
    both = consulta.naturaleza_del_texto('transcripcion verificada', 'parcial')
    assert both.startswith('transcripción de ICT155') and both.endswith('ejemplar PARCIAL: no es la norma entera')

def test_7_cita_de_una_transcripcion_no_dice_texto_literal(con):
    r = consulta.resolver(con, 'EN 13486:2023::ap.4')
    assert r.estado == consulta.ENCONTRADO and r.version == 'transcripcion verificada'
    assert r.naturaleza_del_texto and 'transcripción de ICT155' in r.naturaleza_del_texto
    ident = 'EN 13486:2023::ap.4'
    ok, texto, _ = srv.formatear('normativa_cita', ['cita', ident, '--json'], json.dumps(r.dict()), {'identificador': ident})
    assert ok and 'TEXTO LITERAL' not in texto
    assert 'TEXTO (transcripción de ICT155, NO es el literal de la norma: solo lo entrecomillado es literal; ejemplar PARCIAL: no es la norma entera):' in texto
    r2 = consulta.resolver(con, 'EN 99999:2020::pag.4')
    assert r2.estado == consulta.ENCONTRADO
    _, texto2, _ = srv.formatear('normativa_cita', ['cita', 'x', '--json'], json.dumps(r2.dict()), {'identificador': 'EN 99999:2020::pag.4'})
    assert 'TEXTO (reconocimiento óptico: puede tener errores de lectura):' in texto2 and 'TEXTO LITERAL' not in texto2

def test_7_un_texto_de_un_ejemplar_completo_sigue_siendo_texto_literal(con):
    r = consulta.resolver(con, 'Orden PRB/1/2020::art.1')
    assert r.estado == consulta.ENCONTRADO and r.naturaleza_del_texto is None and ('naturaleza_del_texto' not in r.dict())
    _, texto, _ = srv.formatear('normativa_cita', ['cita', 'x', '--json'], json.dumps(r.dict()), {'identificador': 'x'})
    assert 'TEXTO LITERAL:' in texto

def test_7_revisar_avisa_y_no_da_por_bueno_un_literal_de_una_transcripcion(con):
    borrador = f'Lo dice la norma, `EN 13486:2023::ap.4`, p. 5:\n\n> {FRASE_13486}\n'
    inf = revision.revisar(con, borrador)
    assert not [c for c in inf.comprobaciones if c.tipo == 'literal']
    lit, = [c for c in inf.comprobaciones if c.tipo == 'cotejo']
    assert lit.nivel == revision.ERROR and 'no se puede cotejar con un original' in lit.detalle
    assert 'transcripción de ICT155' in lit.detalle and 'cita la cláusula y la página sin entrecomillar' in lit.detalle
    ok = revision.revisar(con, f'Dice `Orden PRB/1/2020::art.1`:\n\n> El titular conservará el registro de verificaciones durante un periodo mínimo de cinco años\n')
    assert [c.nivel for c in ok.comprobaciones if c.tipo == 'literal'] == [revision.OK]

def test_7_brechas_avisa_cuando_el_literal_esta_en_una_transcripcion(con, monkeypatch):
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: None)
    c = brechas.comprobar(con, _registro({'identificador': 'EN 13486:2023::ap.4', 'literal': FRASE_13486}), avisos_de_limites=None)[0].citas[0]
    assert c.nivel == brechas.ERROR
    assert any((d.startswith('literal:') and 'no se puede cotejar con un original' in d for d in c.detalle))
    assert not any((o.startswith('literal:') for o in c.ok))
