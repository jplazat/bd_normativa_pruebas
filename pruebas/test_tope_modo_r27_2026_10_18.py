"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
from pathlib import Path
import pytest
from ict155 import completitud, config, db, interruptores
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base (LOCALAPPDATA/ict155/bd)')

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    limpiar_forzados(monkeypatch, raising=False)
    return tmp_path

def _forzar(monkeypatch, modo: str):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': modo})))

def _lineas_sombra() -> list[dict]:
    ruta = interruptores.ruta_sombra()
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]

def _escribe(tmp_path, datos) -> Path:
    ruta = tmp_path / 'temas.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta

def _temas_solo_con(tmp_path, **cambios_obligatorio) -> list[completitud.Tema]:
    o = {'acepta': ['Ley 32/2014::art.1'], 'por_que': 'un precepto que solo exige cubre_estricto', 'solo_con': 'cubre_estricto'}
    o.update(cambios_obligatorio)
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [o]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

def test_tope_modo_ausente_es_none(tmp_path):
    assert _temas_solo_con(tmp_path)[0].obligatorios[0].tope_modo is None

def test_tope_modo_sombra_con_solo_con_carga(tmp_path):
    assert _temas_solo_con(tmp_path, tope_modo='sombra')[0].obligatorios[0].tope_modo == 'sombra'

def test_tope_modo_apagado_con_acepta_hoja_carga(tmp_path):
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': ['Ley 32/2014::art.12'], 'por_que': 'x', 'acepta_hoja': ['Ley 32/2014::art.12.1'], 'tope_modo': 'apagado'}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    assert temas[0].obligatorios[0].tope_modo == 'apagado'

def test_tope_modo_bloquea_falla(tmp_path):
    with pytest.raises(completitud.TemasMal, match='«tope_modo» solo puede ser'):
        _temas_solo_con(tmp_path, tope_modo='bloquea')

@pytest.mark.parametrize('valor', ['apagada', 'sombras', '', 3, True])
def test_tope_modo_con_valor_invalido_falla(tmp_path, valor):
    with pytest.raises(completitud.TemasMal, match='«tope_modo» solo puede ser'):
        _temas_solo_con(tmp_path, tope_modo=valor)

def test_tope_modo_sin_acepta_hoja_ni_solo_con_falla(tmp_path):
    with pytest.raises(completitud.TemasMal, match='«tope_modo» no tiene sentido sin'):
        datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': ['Ley 32/2014::art.1'], 'por_que': 'x', 'tope_modo': 'sombra'}]}]}
        completitud.cargar(_escribe(tmp_path, datos))

@pytest.mark.parametrize('modo_global', ['apagado', 'sombra', 'bloquea'])
def test_modo_para_sin_tope_devuelve_el_global(tmp_path, modo_global):
    o = _temas_solo_con(tmp_path)[0].obligatorios[0]
    assert completitud._modo_para(o, modo_global) == modo_global

@pytest.mark.parametrize('modo_global, tope, esperado', [('bloquea', 'sombra', 'sombra'), ('bloquea', 'apagado', 'apagado'), ('sombra', 'apagado', 'apagado'), ('sombra', 'sombra', 'sombra'), ('apagado', 'sombra', 'apagado'), ('apagado', 'apagado', 'apagado')])
def test_modo_para_con_tope_es_el_menor(tmp_path, modo_global, tope, esperado):
    o = _temas_solo_con(tmp_path, tope_modo=tope)[0].obligatorios[0]
    assert completitud._modo_para(o, modo_global) == esperado
HOJA_1, HOJA_2, HOJA_3 = ('Ley 32/2014::art.12.1', 'Ley 32/2014::art.12.2', 'Ley 32/2014::art.12.3')
HOJA_RD_1, HOJA_RD_2 = ('RD 244/2016::art.20.1', 'RD 244/2016::art.20.2')

def _temas_computo_y_reparacion(tmp_path, tope_computo) -> list[completitud.Tema]:
    """Public CI documentation."""
    o_solo_con = {'acepta': ['Ley 32/2014::art.1'], 'por_que': 'un precepto que solo exige cubre_estricto', 'solo_con': 'cubre_estricto'}
    o_hoja = {'acepta': ['Ley 32/2014::art.12'], 'por_que': 'el plazo tras una reparación', 'acepta_hoja': [HOJA_1, HOJA_2, HOJA_3], 'regla_hoja': 'todos', 'estado_hoja': 'validado (prueba sintética)', 'por_que_hoja': {HOJA_1: 'por qué 1', HOJA_2: 'por qué 2', HOJA_3: 'por qué 3'}}
    if tope_computo is not None:
        o_solo_con['tope_modo'] = tope_computo
        o_hoja['tope_modo'] = tope_computo
    o_reparacion = {'acepta': ['RD 244/2016::art.20'], 'por_que': 'quién puede reparar', 'acepta_hoja': [HOJA_RD_1, HOJA_RD_2], 'regla_hoja': 'todos', 'estado_hoja': 'validado (prueba sintética)', 'por_que_hoja': {HOJA_RD_1: 'motivo 20.1', HOJA_RD_2: 'motivo 20.2'}}
    datos = {'temas': [{'id': 'computo', 'nombre': 'Cómputo del plazo', 'cuando': [['zzz']], 'obligatorios': [o_solo_con, o_hoja]}, {'id': 'reparacion', 'nombre': 'Reparación', 'cuando': [['zzz']], 'obligatorios': [o_reparacion]}]}
    return completitud.cargar(_escribe(tmp_path, datos))
RESPUESTA = f'Ver `{HOJA_1}` y `{HOJA_RD_1}`.'

def test_computo_sin_tope_tambien_bloquearia(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo=None)
    f = completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    ids = {x.identificador for x in f}
    assert ids == {'Ley 32/2014::art.1', HOJA_2, HOJA_3, HOJA_RD_2}
    assert _lineas_sombra() == []

def test_tope_sombra_en_computo_no_deja_ninguna_falta_de_computo(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    f = completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    assert {x.tema for x in f} == {'reparacion'}
    assert {x.identificador for x in f} == {HOJA_RD_2}

def test_tope_sombra_en_computo_anota_las_tres_faltas_en_sombra_log_con_tope(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    lineas = _lineas_sombra()
    assert len(lineas) == 3
    assert all((l['control'] == 'cubre_estricto' and l['tema'] == 'computo' and (l['tope'] == 'sombra') for l in lineas))
    assert {l['obligatorio'] for l in lineas} == {'Ley 32/2014::art.1', HOJA_2, HOJA_3}

def test_tope_sombra_no_anota_nada_de_reparacion(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    assert not any((l.get('tema') == 'reparacion' for l in _lineas_sombra()))

def test_tope_apagado_no_deja_ni_falta_ni_sombra(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='apagado')
    f = completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    assert {x.tema for x in f} == {'reparacion'}
    assert not any((l.get('tema') == 'computo' for l in _lineas_sombra()))

@pytest.mark.parametrize('modo_global', ['apagado', 'sombra', 'bloquea'])
def test_tope_apagado_es_mudo_en_los_tres_modos_globales(monkeypatch, con, tmp_path, modo_global):
    _forzar(monkeypatch, modo_global)
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='apagado')
    f = completitud.faltan(con, RESPUESTA, 'zzz', ('publico',), temas)
    assert not any((x.tema == 'computo' for x in f))
    assert not any((l.get('tema') == 'computo' for l in _lineas_sombra()))

def test_a_dict_no_exporta_hoja_bloquea_con_tope_sombra(tmp_path, monkeypatch):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    d = completitud.a_dict(temas)
    o_hoja = d['temas'][0]['obligatorios'][0]
    assert 'hoja_bloquea' not in o_hoja and 'hoja_bloquea_regla' not in o_hoja

def test_a_dict_oculta_el_solo_con_topado_a_sombra(tmp_path, monkeypatch):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    d = completitud.a_dict(temas)
    assert d['temas'][0]['obligatorios'] == [{'identificador': 'Ley 32/2014::art.12', 'acepta': ['Ley 32/2014::art.12'], 'por_que': 'el plazo tras una reparación'}]

def test_a_dict_no_toca_reparacion_que_sigue_exigiendo_todos(tmp_path, monkeypatch):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    d = completitud.a_dict(temas)
    o = d['temas'][1]['obligatorios'][0]
    assert o['hoja_bloquea'] == [HOJA_RD_1, HOJA_RD_2] and o['hoja_bloquea_regla'] == 'todos'

def test_texto_no_dice_hay_que_citar_todos_con_tope_sombra(tmp_path, monkeypatch):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    t = completitud.texto(temas)
    assert 'hay que citar TODOS' not in t.split('TEMA «Reparación»')[0]
    assert 'hay que citar TODOS' in t.split('TEMA «Reparación»')[1]

def test_texto_omite_la_anotacion_de_bloquea_para_el_obligatorio_topado(tmp_path, monkeypatch):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_computo_y_reparacion(tmp_path, tope_computo='sombra')
    t = completitud.texto(temas)
    assert '[en «bloquea»' not in t.split('TEMA «Reparación»')[0]
    assert '[en «bloquea»' in t.split('TEMA «Reparación»')[1]
