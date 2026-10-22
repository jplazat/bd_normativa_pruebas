"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
from pathlib import Path
import pytest
from ict155 import completitud, config, db, interruptores
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')
ACEPTA_P1 = 'Ley 32/2014::art.12'
ACEPTA_HOJA_P1 = 'Ley 32/2014::art.12.2'
CITA_QUE_NO_CUBRE_P1 = 'Ley 32/2014::art.12.4'

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
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta

def _tema_p1(**cambios_obligatorio) -> dict:
    obligatorio = {'acepta': [ACEPTA_P1], 'por_que': 'el plazo tras una reparación', 'acepta_hoja': [ACEPTA_HOJA_P1], 'estado_hoja': 'validado (prueba sintética)'}
    obligatorio.update(cambios_obligatorio)
    return {'id': 't', 'nombre': 'Reparación de instrumentos', 'cuando': [['zzz']], 'obligatorios': [obligatorio]}

def _temas_p1(tmp_path, **cambios_obligatorio) -> list[completitud.Tema]:
    return completitud.cargar(_escribe(tmp_path, {'temas': [_tema_p1(**cambios_obligatorio)]}))

def test_acepta_hoja_ausente_da_una_tupla_vacia(tmp_path):
    datos = {'temas': [{'id': 'u', 'nombre': 'U', 'cuando': [['zzz']], 'obligatorios': [{'acepta': [ACEPTA_P1], 'por_que': 'x'}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    assert temas[0].obligatorios[0].acepta_hoja == ()

def test_acepta_hoja_bien_formado_carga(tmp_path):
    temas = _temas_p1(tmp_path)
    assert temas[0].obligatorios[0].acepta_hoja == (ACEPTA_HOJA_P1,)
    assert temas[0].obligatorios[0].acepta == (ACEPTA_P1,)

def test_acepta_hoja_con_varios_valores_carga_en_orden(tmp_path):
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': ['Ley 32/2014::art.12'], 'por_que': 'x', 'acepta_hoja': ['Ley 32/2014::art.12.2', 'Ley 32/2014::art.12.4']}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    assert temas[0].obligatorios[0].acepta_hoja == ('Ley 32/2014::art.12.2', 'Ley 32/2014::art.12.4')

@pytest.mark.parametrize('acepta_hoja, problema', [([], '«acepta_hoja» tiene que ser una lista no vacía si se da'), (['sin separador'], 'no es un identificador «obra::ruta»'), ([3], 'no es un identificador «obra::ruta»'), (['Ley 32/2014::art.99'], 'tiene que ser igual o estar por debajo de alguno de «acepta»'), (['Otra ley::art.12.2'], 'tiene que ser igual o estar por debajo de alguno de «acepta»')])
def test_acepta_hoja_mal_formado_falla_con_un_error_claro(tmp_path, acepta_hoja, problema):
    with pytest.raises(completitud.TemasMal) as e:
        _temas_p1(tmp_path, acepta_hoja=acepta_hoja)
    assert problema in str(e.value)

def test_acepta_hoja_igual_al_acepta_entero_vale(tmp_path):
    """Public CI documentation."""
    temas = _temas_p1(tmp_path, acepta_hoja=[ACEPTA_P1])
    assert temas[0].obligatorios[0].acepta_hoja == (ACEPTA_P1,)

def test_acepta_hoja_se_valida_contra_la_base(con, tmp_path):
    malos = completitud.validar_contra_la_base(con, _temas_p1(tmp_path))
    assert malos == []
    malos = completitud.validar_contra_la_base(con, _temas_p1(tmp_path, acepta_hoja=['Ley 32/2014::art.12.999']))
    assert len(malos) == 1 and malos[0].startswith('Ley 32/2014::art.12.999 [t]: ')
RESPUESTA_SOLO_12_4 = 'Se puede reparar sin repetir la verificación en los casos del `Ley 32/2014::art.12.4`.'
RESPUESTA_ENTERO = 'Se aplica el `Ley 32/2014::art.12` entero.'
RESPUESTA_LA_HOJA = 'Se aplica el `Ley 32/2014::art.12.2`.'
RESPUESTA_SIN_NADA = 'Esto no cita nada de ese artículo.'

def test_apagado_citar_solo_el_subapartado_que_no_importa_cubre(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'apagado')
    temas = _temas_p1(tmp_path)
    assert completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

def test_sombra_citar_solo_el_subapartado_que_no_importa_cubre_y_avisa(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'sombra')
    temas = _temas_p1(tmp_path)
    assert completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1
    assert lineas[0]['control'] == 'cubre_estricto' and lineas[0]['tema'] == 't' and (lineas[0]['obligatorio'] == ACEPTA_HOJA_P1)
    assert 'art.12.4' in lineas[0]['citado']

def test_bloquea_citar_solo_el_subapartado_que_no_importa_falta_con_la_correccion(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_p1(tmp_path)
    f = completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas)
    assert len(f) == 1
    assert f[0].identificador == ACEPTA_HOJA_P1 and f[0].tema == 't'
    assert f[0].cita_que_no_cubre and 'art.12.4' in f[0].cita_que_no_cubre
    assert f'falta citar {ACEPTA_HOJA_P1} (' in f[0].motivo
    assert f[0].motivo.endswith('no lo cubre') and 'art.12.4' in f[0].motivo
    assert _lineas_sombra() == []

@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_citando_el_articulo_entero_cubre_en_los_tres_modos(monkeypatch, con, tmp_path, modo):
    _forzar(monkeypatch, modo)
    temas = _temas_p1(tmp_path)
    assert completitud.faltan(con, RESPUESTA_ENTERO, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_citando_la_hoja_pedida_cubre_en_los_tres_modos(monkeypatch, con, tmp_path, modo):
    _forzar(monkeypatch, modo)
    temas = _temas_p1(tmp_path)
    assert completitud.faltan(con, RESPUESTA_LA_HOJA, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_sin_citar_nada_falta_en_los_tres_modos_sin_correccion(monkeypatch, con, tmp_path, modo):
    _forzar(monkeypatch, modo)
    temas = _temas_p1(tmp_path)
    f = completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == ACEPTA_P1 and (f[0].cita_que_no_cubre is None)
    assert f[0].motivo == f'INCOMPLETA: falta citar {ACEPTA_P1} (el plazo tras una reparación) [tema «Reparación de instrumentos»]'

def test_un_obligatorio_sin_acepta_hoja_no_cambia_con_el_modo(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': [ACEPTA_P1], 'por_que': 'x'}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    for modo in interruptores.MODOS:
        _forzar(monkeypatch, modo)
        assert completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas) == []
        assert _lineas_sombra() == []

def test_falta_dict_lleva_cita_que_no_cubre_solo_cuando_hay(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_p1(tmp_path)
    f = completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas)[0]
    assert 'cita_que_no_cubre' in f.dict() and f.dict()['cita_que_no_cubre'] == f.cita_que_no_cubre
    json.dumps(f.dict(), ensure_ascii=False)
    sin = completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz', ('publico',), temas)[0]
    assert 'cita_que_no_cubre' not in sin.dict()

def test_sin_forzar_hoy_cubre_estricto_esta_apagado(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'apagado')
    assert interruptores.modo('cubre_estricto') == 'apagado'
    temas = _temas_p1(tmp_path)
    assert completitud.faltan(con, RESPUESTA_SOLO_12_4, 'zzz', ('publico',), temas) == []
ACEPTA_PADRE_INEXISTENTE = 'BOE-A-2022-10757::disp.adicional'
ACEPTA_HOJA_SI_RESUELVE = 'BOE-A-2022-10757::disp.adicional.1'
RESPUESTA_SOLO_LA_HOJA_QUE_RESUELVE = f'Se aplica el `{ACEPTA_HOJA_SI_RESUELVE}`.'

def _temas_padre_inexistente(tmp_path) -> list[completitud.Tema]:
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': [ACEPTA_PADRE_INEXISTENTE], 'por_que': 'x', 'acepta_hoja': [ACEPTA_HOJA_SI_RESUELVE]}]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_padre_que_no_resuelve_con_solo_la_hoja_citada_falta_en_los_tres_modos(monkeypatch, con, tmp_path, modo):
    """Public CI documentation."""
    _forzar(monkeypatch, modo)
    temas = _temas_padre_inexistente(tmp_path)
    f = completitud.faltan(con, RESPUESTA_SOLO_LA_HOJA_QUE_RESUELVE, 'zzz', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == ACEPTA_PADRE_INEXISTENTE and (f[0].cita_que_no_cubre is None)
    assert _lineas_sombra() == []
