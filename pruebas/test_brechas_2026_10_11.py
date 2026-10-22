"""Public CI documentation."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import brechas, cli, db, interruptores, vigencia
from pruebas.almacen_soporte import conservar_almacen_forzado
TEXTO_A1 = 'El titular conservará el registro de verificaciones durante un periodo mínimo de cinco años.'
TEXTO_A2 = 'Los instrumentos se verificarán antes de su puesta en servicio, salvo que estén exentos.'
TEXTO_MID = 'Los fabricantes garantizarán que los instrumentos de medida se han diseñado conforme a los requisitos.'
HOY = '2026-10-11'

def _obra(con, ident, titulo, alias=()):
    cur = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, jurisdiccion) VALUES (?,?,?,?)', (ident, 'ley', titulo, 'ES'))
    for a in alias:
        con.execute('INSERT INTO obra_alias (obra_id, alias, alias_norm) VALUES (?,?,?)', (cur.lastrowid, a, a.lower()))
    return cur.lastrowid

def _version(con, obra_id, nombre, etiqueta, preceptos, fecha_edicion=None):
    doc = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas, clase_derechos, estado_ingesta) VALUES (?,?,?,?,?,?,?)', (f'{nombre}.pdf', nombre, 1, '2026-01-01', 10, 'publico', 'ingerido')).lastrowid
    v = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, idioma, fecha_edicion, fecha_consolidacion) VALUES (?,?,?,?,?,?)', (obra_id, doc, etiqueta, 'es', fecha_edicion, fecha_edicion)).lastrowid
    for orden, (ruta, etiqueta_h, texto, pag) in enumerate(preceptos, 1):
        con.execute('INSERT INTO precepto (version_id, ruta_estructural, tipo_unidad, numero, etiqueta_humana, texto_literal, pagina_inicio, pagina_fin, orden) VALUES (?,?,?,?,?,?,?,?,?)', (v, ruta, 'articulo', ruta.rsplit('.', 1)[-1], etiqueta_h, texto, pag, pag, orden))

@pytest.fixture(scope='module')
def con(tmp_path_factory):
    c = db.crear(tmp_path_factory.mktemp('brechas') / 'b.sqlite')
    a = _obra(c, 'BOE-A-2020-1', 'Orden de prueba sobre registros', alias=('Orden PRB/1/2020',))
    _version(c, a, 'orden', 'v1', [('art.1', 'Artículo 1', TEXTO_A1, 3), ('art.2', 'Artículo 2', TEXTO_A2, 4)])
    m = _obra(c, 'CELEX-32014L0032', 'Directiva de prueba de instrumentos de medida', alias=('MID',))
    _version(c, m, 'mid', 'v1', [('art.1', 'Artículo 1', TEXTO_MID, 5)])
    d = _obra(c, 'BOE-A-2019-2', 'Norma de prueba con dos ediciones')
    _version(c, d, 'dos_a', '2018', [('art.1', 'Artículo 1', 'Texto de la edición de 2018.', 1)], '2018-01-01')
    _version(c, d, 'dos_b', '2022', [('art.1', 'Artículo 1', 'Texto de la edición de 2022.', 1)], '2022-01-01')
    c.commit()
    yield c
    c.close()

def _datos_vigencia():
    mod = {'id': '32026L0706', 'titulo': 'Directiva (UE) 2026/706', 'fecha_comparada': '2026-04-09', 'en_la_base': False}
    return {'consultado': '2026-10-08T10:00:00Z', 'fuentes': {'BOE': vigencia.AVISO_BOE, 'CELLAR': vigencia.AVISO_CELLAR}, 'obras': {'CELEX-32014L0032': {'identificador_oficial': '32014L0032', 'fecha_version': '2015-01-27', 'consulta': {'fuente': 'CELLAR', 'estado': 'vigente'}, 'modificaciones_posteriores': [mod]}, 'BOE-A-2020-1': {'identificador_oficial': 'BOE-A-2020-1', 'fecha_version': '2020-02-01', 'consulta': {'fuente': 'BOE', 'estado': 'vigente'}, 'modificaciones_posteriores': []}}}

@pytest.fixture(autouse=True)
def _vigencia_sintetica(monkeypatch):
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: _datos_vigencia())
    monkeypatch.setattr(vigencia, 'identificador_oficial', lambda obra: {'CELEX-32014L0032': '32014L0032', 'BOE-A-2020-1': 'BOE-A-2020-1'}.get(obra))

@pytest.fixture(autouse=True)
def _cotejo_sintetico(monkeypatch):
    """Public CI documentation."""
    from ict155 import cotejo_original as co
    boe = {'esquema': 1, 'consultado': '2026-10-11T08:00:00Z', 'fuentes': {}, 'base': {'ruta': 'sintetica'}, 'obras': {'BOE-A-2020-1': {'identificador_oficial': 'BOE-A-2020-1', 'estado': 'ok', 'error': None, 'url': 'u', 'fuente': 'consolidado', 'titulo': None, 'sin_ruta': [], 'bloques': [{'id': 'a1', 'titulo': 'Artículo 1', 'tipo': 'precepto', 'texto': TEXTO_A1}, {'id': 'a2', 'titulo': 'Artículo 2', 'tipo': 'precepto', 'texto': TEXTO_A2}], 'rutas': {'art.1': 0, 'art.2': 1}}}}
    ue = {'esquema': 1, 'consultado': '2026-10-11T08:00:00Z', 'fuentes': {}, 'base': {'ruta': 'sintetica'}, 'obras': {'CELEX-32014L0032': {'versiones': {'v1|es': {'celex': '02014L0032-20150127', 'idioma': 'es', 'estado': 'ok', 'error': None, 'url': 'u', 'texto': TEXTO_MID}}}}}
    monkeypatch.setattr(co, 'datos_actuales', lambda: co.Datos(boe, ue))

def _b(bid, citas, estado='abierta', **kw):
    return dict({'id': bid, 'capa': 'metrologia_legal', 'titulo': f'Brecha {bid}', 'estado': estado, 'fecha_estado': '2026-08-05', 'citas': citas}, **kw)

def _reg(*brechas):
    return {'cliente': 'Cliente de prueba', 'informe': 'Informe de prueba', 'brechas': list(brechas)}

def _una(con, cita):
    r, = brechas.comprobar(con, _reg(_b('X-1', [cita])))
    return r.citas[0]

def test_cita_buena_se_verifica(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1'})
    assert c.nivel == brechas.OK and c.estado == 'ENCONTRADO' and (not c.detalle)

def test_cita_por_alias_tambien(con):
    assert _una(con, {'identificador': 'Orden PRB/1/2020::art.2'}).nivel == brechas.OK

def test_precepto_inexistente_es_error_con_su_estado(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.99'})
    assert c.nivel == brechas.ERROR and c.estado == 'PRECEPTO_INEXISTENTE'
    assert c.detalle[0].startswith('PRECEPTO_INEXISTENTE')

def test_obra_que_no_consta_es_error(con):
    c = _una(con, {'identificador': 'BOE-A-1999-9::art.1'})
    assert c.nivel == brechas.ERROR and c.estado == 'NO_CONSTA_EN_BIBLIOTECA'

def test_edicion_ambigua_es_error_y_con_fecha_se_resuelve(con):
    c = _una(con, {'identificador': 'BOE-A-2019-2::art.1'})
    assert c.nivel == brechas.ERROR and c.estado == 'EDICION_AMBIGUA' and ('@' in c.detalle[0])
    assert _una(con, {'identificador': 'BOE-A-2019-2@2022-06-01::art.1'}).nivel == brechas.OK

def test_literal_que_casa(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1', 'literal': 'conservará el registro de verificaciones durante un periodo mínimo de cinco años'})
    assert c.nivel == brechas.OK and any((x.startswith('literal:') for x in c.ok))

def test_literal_que_no_casa_es_error(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1', 'literal': 'conservará el registro de verificaciones durante diez años como mínimo'})
    assert c.nivel == brechas.ERROR and any((x.startswith('literal:') for x in c.detalle))

def test_literal_de_otro_precepto_se_dice_donde_esta(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1', 'literal': 'se verificarán antes de su puesta en servicio, salvo que estén exentos'})
    assert c.nivel == brechas.ERROR and 'art.2' in ' '.join(c.detalle)

def test_literal_con_elision_se_comprueba_por_trozos(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1', 'literal': 'El titular conservará el registro […] un periodo mínimo de cinco años'})
    assert c.nivel == brechas.OK

def test_literal_demasiado_corto_avisa(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.1', 'literal': 'registro'})
    assert c.nivel == brechas.AVISO and 'menos de dos palabras' in c.detalle[0]

def test_literal_sobre_cita_que_no_resuelve_no_se_comprueba(con):
    c = _una(con, {'identificador': 'BOE-A-2020-1::art.99', 'literal': 'lo que sea con varias palabras'})
    assert c.nivel == brechas.ERROR and len(c.detalle) == 1

def test_norma_modificada_avisa_aunque_la_cita_exista(con):
    c = _una(con, {'identificador': 'MID::art.1'})
    assert c.nivel == brechas.AVISO and c.estado == 'ENCONTRADO'
    assert c.detalle[0].startswith('vigencia: MODIFICADA después de la versión de la base')

def test_norma_al_dia_no_avisa(con):
    assert _una(con, {'identificador': 'BOE-A-2020-1::art.2'}).detalle == []

def test_las_brechas_con_citas_sin_verificar_van_primero_error_antes_que_aviso(con):
    reg = _reg(_b('A-1', [{'identificador': 'BOE-A-2020-1::art.1'}]), _b('A-2', [{'identificador': 'MID::art.1'}]), _b('A-3', [{'identificador': 'BOE-A-2020-1::art.99'}]), _b('A-4', [{'identificador': 'BOE-A-2020-1::art.2'}]))
    assert [r.brecha['id'] for r in brechas.comprobar(con, reg)] == ['A-3', 'A-2', 'A-1', 'A-4']

def test_una_brecha_sin_citas_no_esta_verificada(con):
    r, = brechas.comprobar(con, _reg(_b('S-1', [])))
    assert r.nivel == brechas.AVISO
    assert 'no tiene citas normativas' in brechas.informe_markdown(con, _reg(_b('S-1', [])), [r])
REV1 = {'numero': 1, 'fecha': '2026-10-30', 'documento_aportado': 'd1', 'veredicto': 'parcial', 'que_falta': 'el acta'}
REV2 = {'numero': 2, 'fecha': '2026-11-20', 'documento_aportado': 'd2', 'veredicto': 'cumple', 'que_falta': ''}

def test_ultima_revision_es_la_de_numero_mayor_aunque_vaya_antes():
    assert brechas.ultima_revision(_b('R', [], revisiones=[REV2, REV1]))['numero'] == 2
    assert brechas.ultima_revision(_b('R', [])) is None

def test_avisos_de_revision(con):
    cita = [{'identificador': 'BOE-A-2020-1::art.1'}]
    reg = _reg(_b('R-0', cita), _b('R-1', cita, revisiones=[REV1]), _b('R-2', cita, revisiones=[REV1, REV2]), _b('R-3', cita, revisiones=[dict(REV1, veredicto='no_cumple')]), _b('R-4', cita, revisiones=[dict(REV1, veredicto='pendiente')]))
    por_id = {r.brecha['id']: r for r in brechas.comprobar(con, reg)}
    assert por_id['R-0'].avisos_revision == ['sin ninguna revisión']
    assert '«parcial»' in por_id['R-1'].avisos_revision[0]
    assert por_id['R-2'].avisos_revision == []
    assert '«no_cumple»' in por_id['R-3'].avisos_revision[0]
    assert por_id['R-4'].avisos_revision == []

def test_informe_markdown(con, monkeypatch):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'brechas_r27': 'apagado'})))
    reg = _reg(_b('M-08', [{'identificador': 'BOE-A-2020-1::art.99'}, {'identificador': 'BOE-A-2020-1::art.1'}], revisiones=[REV1]), _b('M-09', [{'identificador': 'BOE-A-2020-1::art.2'}], estado='cerrada', capa='otra', revisiones=[REV1, REV2]))
    md = brechas.informe_markdown(con, reg, brechas.comprobar(con, reg))
    assert md.startswith('# Seguimiento de brechas')
    assert 'Brechas: 2. Por estado: abierta: 1, cerrada: 1.' in md
    assert 'Por capa: metrologia_legal: 1, otra: 1.' in md
    assert 'Citas: 3. Verificadas: 2. Con aviso: 0. Con error: 1.' in md
    assert 'Brechas sin ninguna revisión: 0.' in md
    assert 'última revisión es «no_cumple» o «parcial»: 1 (M-08).' in md
    assert md.index('### M-08') < md.index('### M-09')
    assert '| `BOE-A-2020-1::art.99` | ERROR | PRECEPTO_INEXISTENTE' in md
    assert '- Última revisión: nº 1 (2026-10-30): **parcial** · falta: el acta' in md
    assert '- Última revisión: nº 2 (2026-11-20): **cumple**' in md
    assert 'Vigencia consultada: 2026-10-08.' in md

def test_las_barras_de_las_celdas_no_rompen_la_tabla(con):
    reg = _reg(_b('P-1', [{'identificador': 'BOE-A-2020-1::art.1', 'literal': 'conservará | el registro de nunca jamás visto'}]))
    md = brechas.informe_markdown(con, reg, brechas.comprobar(con, reg))
    fila = next((l for l in md.splitlines() if l.startswith('| `BOE-A-2020-1::art.1`')))
    assert fila.replace('\\|', '').count('|') == 4

def test_registro_bien_formado_no_da_errores():
    assert brechas.validar(_reg(_b('V-1', [{'identificador': 'A::b'}], revisiones=[REV1]))) == []

@pytest.mark.parametrize('datos,fragmento', [([], 'objeto JSON'), ({}, 'falta «brechas»'), (_reg(_b('V-1', []), _b('V-1', [])), 'id repetido'), (_reg(_b('', [])), 'falta «id»'), (_reg(_b('V-1', [], estado='abierto')), "«estado» 'abierto' no es válido"), (_reg(_b('V-1', [], fecha_estado='05/08/2026')), '«fecha_estado»'), (_reg(_b('V-1', [], fecha_estado='2026-13-45')), '«fecha_estado»'), (_reg(_b('V-1', [{'identificador': 'sin separador'}])), 'obra::ruta'), (_reg(_b('V-1', [{'identificador': 'A::b`c'}])), 'comillas invertidas'), (_reg(_b('V-1', [{'identificador': 'A::b', 'literal': 3}])), '«literal»'), (_reg(_b('V-1', [], revisiones=[dict(REV1, veredicto='ok')])), '«veredicto»'), (_reg(_b('V-1', [], revisiones=[dict(REV1, fecha='ayer')])), '«fecha»'), (_reg(_b('V-1', [], revisiones=[dict(REV1, numero='1')])), '«numero»'), (_reg(_b('V-1', [], revisiones=[REV1, REV1])), 'repetida'), (_reg(_b('V-1', 'no es lista')), '«citas» tiene que ser una lista')])
def test_registro_mal_formado_da_un_error_claro(datos, fragmento):
    errores = brechas.validar(datos)
    assert errores and any((fragmento in e for e in errores)), errores

def test_se_informa_de_todos_los_errores_a_la_vez():
    errores = brechas.validar(_reg(_b('V-1', [], estado='x'), _b('V-1', [], fecha_estado='no')))
    assert len(errores) == 3

def test_leer_registro_con_fichero_que_no_existe_o_no_es_json(tmp_path):
    with pytest.raises(brechas.RegistroMalo, match='no se puede leer'):
        brechas.leer_registro(tmp_path / 'no_existe.json')
    mal = tmp_path / 'mal.json'
    mal.write_text('{no es json', encoding='utf-8')
    with pytest.raises(brechas.RegistroMalo, match='no es JSON válido'):
        brechas.leer_registro(mal)
    binario = tmp_path / 'bin.json'
    binario.write_bytes(b'\xff\xfe\x00')
    with pytest.raises(brechas.RegistroMalo, match='UTF-8'):
        brechas.leer_registro(binario)

@pytest.fixture
def cli_con_base(con, monkeypatch):
    monkeypatch.setattr(db, 'conectar', lambda ruta=None, solo_lectura=False: con)

def _escribir(tmp_path, datos):
    f = tmp_path / 'registro.json'
    f.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return f

def test_cli_registro_limpio_sale_con_0_y_escribe_el_informe(tmp_path, cli_con_base, capsys, monkeypatch):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'brechas_r27': 'apagado'})))
    f = _escribir(tmp_path, _reg(_b('C-1', [{'identificador': 'BOE-A-2020-1::art.1'}], revisiones=[REV2])))
    salida = tmp_path / 'informe.md'
    assert cli.main(['brechas', str(f), '--salida', str(salida)]) == 0
    assert '### C-1' in salida.read_text(encoding='utf-8')
    assert 'escrito' in capsys.readouterr().out

def test_cli_con_un_error_en_una_cita_sale_con_1_y_pinta_en_pantalla(tmp_path, cli_con_base, capsys):
    f = _escribir(tmp_path, _reg(_b('C-1', [{'identificador': 'BOE-A-2020-1::art.99'}])))
    assert cli.main(['brechas', str(f)]) == 1
    assert 'PRECEPTO_INEXISTENTE' in capsys.readouterr().out

def test_cli_registro_mal_formado_sale_con_2_sin_reventar_y_sin_abrir_la_base(tmp_path, monkeypatch, capsys):

    def no_debe_abrirse(*a, **k):
        raise AssertionError('no se abre la base con un registro mal formado')
    monkeypatch.setattr(db, 'conectar', no_debe_abrirse)
    f = _escribir(tmp_path, _reg(_b('C-1', [], estado='x'), _b('C-1', [])))
    assert cli.main(['brechas', str(f)]) == 2
    err = capsys.readouterr().err
    assert 'registro no válido (2 problemas)' in err and 'id repetido' in err
    assert cli.main(['brechas', str(tmp_path / 'no_existe.json')]) == 2
TEXTO_LIC = 'Cuando el equipo esté en servicio, la temperatura del recinto se registrará cada hora mediante un termómetro calibrado.'
LITERAL_LIC = 'la temperatura del recinto se registrará cada hora mediante un termómetro calibrado'

def _obra_con_derechos(con, ident, clase):
    o = _obra(con, ident, f'Norma de prueba ({clase})')
    _version(con, o, ident, 'v1', [('ap.1', 'Apartado 1', TEXTO_LIC, 2)])
    con.execute('UPDATE documento SET clase_derechos = ? WHERE ruta_relativa = ?', (clase, f'{ident}.pdf'))
    con.commit()

def test_de_una_norma_con_licencia_no_sale_su_texto_y_de_una_publica_si(con):
    _obra_con_derechos(con, 'PUB-LIC-1', 'publico')
    _obra_con_derechos(con, 'UNE-LIC-1', 'licenciado')
    publica = _una(con, {'identificador': 'PUB-LIC-1::ap.1', 'literal': LITERAL_LIC})
    pago = _una(con, {'identificador': 'UNE-LIC-1::ap.1', 'literal': LITERAL_LIC})
    assert publica.nivel == pago.nivel == brechas.AVISO
    assert 'Cuando el equipo esté en servicio' in ' '.join(publica.detalle)
    assert 'omitido: norma con licencia' in ' '.join(pago.detalle)
    reg = _reg(_b('L-1', [{'identificador': 'UNE-LIC-1::ap.1', 'literal': LITERAL_LIC}]))
    md = brechas.informe_markdown(con, reg, brechas.comprobar(con, reg))
    for trozo in ('Cuando el equipo', 'en servicio', 'termómetro', 'temperatura del recinto'):
        assert trozo not in md, trozo
    assert 'UNE-LIC-1::ap.1' in md

def test_los_ambitos_reservados_no_se_abren_con_el_ambito_publico(con):
    _obra_con_derechos(con, 'RES-LIC-1', 'reservado')
    c = _una(con, {'identificador': 'RES-LIC-1::ap.1', 'literal': LITERAL_LIC})
    assert c.estado == 'DERECHOS_RESTRINGIDOS' and c.nivel == brechas.AVISO
    assert 'Cuando el equipo' not in ' '.join(c.detalle + c.ok) and 'temperatura' not in ' '.join(c.detalle + c.ok)
