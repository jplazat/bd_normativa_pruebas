"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
import re
import pytest
from ict155 import interruptores, relacionados, sucesion
GRUPO_BUENO = {'grupos': [{'nombre': 'g', 'disparadores': 'zzz', 'contexto': 'yyy', 'preceptos': [{'identificador': 'Orden ICT/155/2020::art.18', 'nota': 'una nota cualquiera'}]}]}
PAR_BUENO = {'sucesiones': [{'origen': 'BOE-A-1996-750::art.23', 'sucesor': 'BOE-A-2020-2573::art.18', 'equivalencia': 'total', 'nota': 'una nota cualquiera, de largo razonable para la prueba'}]}
MODULOS = [pytest.param(relacionados, GRUPO_BUENO, id='relacionados'), pytest.param(sucesion, PAR_BUENO, id='sucesion')]

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    limpiar_forzados(monkeypatch, raising=False)
    relacionados._CACHE.clear()
    sucesion._CACHE.clear()
    return tmp_path

def _forzar(monkeypatch, modo: str):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'relacionados_cierra': modo})))

def _lineas_sombra() -> list[dict]:
    ruta = interruptores.ruta_sombra()
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_ausente_en_apagado_da_lista_vacia_sin_avisar(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'apagado')
    assert mod.cargar(tmp_path / 'no_existe.json') == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_ausente_en_sombra_da_lista_vacia_y_avisa_en_sombra_log(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'sombra')
    ruta = tmp_path / 'no_existe.json'
    assert mod.cargar(ruta) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1
    assert lineas[0]['control'] == 'relacionados_cierra' and lineas[0]['fichero'] == str(ruta) and lineas[0]['error']

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_ausente_en_bloquea_lanza_errordetabla_con_el_fichero(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'no_existe.json'
    with pytest.raises(mod.ErrorDeTabla) as e:
        mod.cargar(ruta)
    assert str(ruta) in str(e.value)
    assert _lineas_sombra() == []

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_roto_en_apagado_da_lista_vacia_sin_avisar(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'roto.json'
    ruta.write_text('{esto no es json', encoding='utf-8')
    assert mod.cargar(ruta) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_roto_en_sombra_da_lista_vacia_y_avisa(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'sombra')
    ruta = tmp_path / 'roto.json'
    ruta.write_text('{esto no es json', encoding='utf-8')
    assert mod.cargar(ruta) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['fichero'] == str(ruta) and lineas[0]['error']

@pytest.mark.parametrize('mod, _bueno', MODULOS)
def test_roto_en_bloquea_lanza_errordetabla(monkeypatch, tmp_path, mod, _bueno):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'roto.json'
    ruta.write_text('{esto no es json', encoding='utf-8')
    with pytest.raises(mod.ErrorDeTabla) as e:
        mod.cargar(ruta)
    assert str(ruta) in str(e.value)

def test_relacionados_con_expresion_regular_mala_en_bloquea_lanza(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'malo.json'
    ruta.write_text(json.dumps({'grupos': [{'nombre': 'g', 'disparadores': '(sin cerrar', 'contexto': 'x', 'preceptos': []}]}), encoding='utf-8')
    with pytest.raises(relacionados.ErrorDeTabla):
        relacionados.cargar(ruta)

def test_relacionados_con_expresion_regular_mala_en_apagado_da_vacio(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'malo.json'
    ruta.write_text(json.dumps({'grupos': [{'nombre': 'g', 'disparadores': '(sin cerrar', 'contexto': 'x', 'preceptos': []}]}), encoding='utf-8')
    assert relacionados.cargar(ruta) == []

def test_sucesion_con_estructura_mala_en_bloquea_lanza(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'malo.json'
    ruta.write_text('no es json en absoluto {', encoding='utf-8')
    with pytest.raises(sucesion.ErrorDeTabla):
        sucesion.cargar(ruta)

def _forma_rota_relacionados() -> list:
    """Public CI documentation."""
    return [pytest.param({}, id='vacio'), pytest.param({'grupos': None}, id='grupos_null'), pytest.param({'grupo': [{'nombre': 'g', 'disparadores': 'zzz', 'contexto': 'yyy'}]}, id='clave_mal_escrita'), pytest.param({'grupos': [{'nombre': 'g', 'disparadores': 'zzz'}]}, id='falta_contexto'), pytest.param({'grupos': [{'nombre': 'g', 'disparadores': 'zzz', 'contexto': 'yyy'}, {'nombre': 'malo', 'disparadores': 'zzz'}]}, id='mezcla_bueno_y_malo')]

def _forma_rota_sucesion() -> list:
    """Public CI documentation."""
    return [pytest.param({}, id='vacio'), pytest.param({'sucesiones': None}, id='sucesiones_null'), pytest.param({'sucesion': [{'origen': 'A::art.1', 'sucesor': 'B::art.1', 'equivalencia': 'total', 'nota': 'x' * 20}]}, id='clave_mal_escrita'), pytest.param({'sucesiones': 'roto'}, id='sucesiones_texto'), pytest.param({'sucesiones': 1}, id='sucesiones_entero'), pytest.param({'sucesiones': [{'origen': 'A::art.1'}]}, id='par_sin_sucesor'), pytest.param({'sucesiones': [{'origen': 'A::art.1', 'sucesor': 'B::art.1', 'equivalencia': 'total', 'nota': 'x' * 20}, {'origen': 'C::art.1'}]}, id='mezcla_bueno_y_malo')]

def _forma_rota_sucesion_apagado() -> list:
    """Public CI documentation."""
    return [p for p in _forma_rota_sucesion() if p.id not in ('sucesiones_entero', 'mezcla_bueno_y_malo')]

@pytest.mark.parametrize('datos', _forma_rota_relacionados())
def test_relacionados_forma_rota_en_apagado_da_vacio_sin_avisar(monkeypatch, tmp_path, datos):
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    assert relacionados.cargar(ruta) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('datos', _forma_rota_relacionados())
def test_relacionados_forma_rota_en_sombra_avisa_y_da_vacio(monkeypatch, tmp_path, datos):
    _forzar(monkeypatch, 'sombra')
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    assert relacionados.cargar(ruta) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['control'] == 'relacionados_cierra' and (lineas[0]['fichero'] == str(ruta))

@pytest.mark.parametrize('datos', _forma_rota_relacionados())
def test_relacionados_forma_rota_en_bloquea_lanza(monkeypatch, tmp_path, datos):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(relacionados.ErrorDeTabla):
        relacionados.cargar(ruta)
    assert _lineas_sombra() == []

def test_relacionados_raiz_lista_en_apagado_revienta_como_r27_base(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'raiz_lista.json'
    ruta.write_text('[]', encoding='utf-8')
    with pytest.raises(AttributeError):
        relacionados.cargar(ruta)

@pytest.mark.parametrize('modo', ('sombra', 'bloquea'))
def test_relacionados_raiz_lista_fuera_de_apagado_ya_no_revienta(monkeypatch, tmp_path, modo):
    """Public CI documentation."""
    _forzar(monkeypatch, modo)
    ruta = tmp_path / 'raiz_lista.json'
    ruta.write_text('[]', encoding='utf-8')
    if modo == 'bloquea':
        with pytest.raises(relacionados.ErrorDeTabla):
            relacionados.cargar(ruta)
    else:
        assert relacionados.cargar(ruta) == []
        assert len(_lineas_sombra()) == 1

@pytest.mark.parametrize('datos', _forma_rota_sucesion_apagado())
def test_sucesion_forma_rota_en_apagado_da_vacio_sin_avisar(monkeypatch, tmp_path, datos):
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    assert sucesion.cargar(ruta) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('datos', _forma_rota_sucesion())
def test_sucesion_forma_rota_en_sombra_avisa_y_da_lo_de_apagado(monkeypatch, tmp_path, datos):
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    _forzar(monkeypatch, 'apagado')
    try:
        esperado, error = (sucesion.cargar(ruta), None)
    except Exception as e:
        esperado, error = (None, type(e))
    assert _lineas_sombra() == []
    _forzar(monkeypatch, 'sombra')
    if error is None:
        assert sucesion.cargar(ruta) == esperado
    else:
        try:
            assert sucesion.cargar(ruta) == []
        except error:
            pass
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['control'] == 'relacionados_cierra' and (lineas[0]['fichero'] == str(ruta))

@pytest.mark.parametrize('datos', _forma_rota_sucesion())
def test_sucesion_forma_rota_en_bloquea_lanza(monkeypatch, tmp_path, datos):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'forma_rota.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(sucesion.ErrorDeTabla):
        sucesion.cargar(ruta)
    assert _lineas_sombra() == []

def test_sucesion_sucesiones_entero_en_apagado_revienta_como_r27_base(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'sucesiones_entero.json'
    ruta.write_text(json.dumps({'sucesiones': 1}), encoding='utf-8')
    with pytest.raises(TypeError):
        sucesion.cargar(ruta)

def test_sucesion_un_bueno_y_uno_sin_sucesor_en_apagado_da_el_subconjunto_filtrado(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'apagado')
    ruta = tmp_path / 'mixto.json'
    ruta.write_text(json.dumps({'sucesiones': [{'origen': 'A::art.1', 'sucesor': 'B::art.1', 'equivalencia': 'total', 'nota': 'x' * 20}, {'origen': 'C::art.1'}]}), encoding='utf-8')
    pares = sucesion.cargar(ruta)
    assert len(pares) == 1 and pares[0]['origen'] == 'A::art.1'
    assert _lineas_sombra() == []

@pytest.mark.parametrize('mod, bueno', MODULOS)
@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_fichero_bien_formado_se_comporta_igual_en_los_tres_modos(monkeypatch, tmp_path, mod, bueno, modo):
    _forzar(monkeypatch, modo)
    ruta = tmp_path / 'bueno.json'
    ruta.write_text(json.dumps(bueno), encoding='utf-8')
    datos = mod.cargar(ruta)
    assert len(datos) == 1
    assert _lineas_sombra() == []

def test_relacionados_bien_formado_que_grupos_tocan_sigue_funcionando(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'bueno.json'
    ruta.write_text(json.dumps(GRUPO_BUENO), encoding='utf-8')
    grupos = relacionados.cargar(ruta)
    assert relacionados.que_grupos_tocan('algo con zzz y con yyy', grupos) != []
    assert relacionados.que_grupos_tocan('nada que ver', grupos) == []

def test_sucesion_bien_formado_sucesores_de_sigue_funcionando(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    ruta = tmp_path / 'bueno.json'
    ruta.write_text(json.dumps(PAR_BUENO), encoding='utf-8')
    tabla = sucesion.cargar(ruta)
    assert sucesion.sucesores_de('BOE-A-1996-750', 'art.23', tabla) != []
    assert sucesion.sucesores_de('BOE-A-1996-750', 'art.99', tabla) == []

def test_sin_forzar_hoy_relacionados_cierra_esta_apagado_y_un_fichero_roto_no_avisa(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'apagado')
    assert interruptores.modo('relacionados_cierra') == 'apagado'
    ruta = tmp_path / 'no_existe.json'
    assert relacionados.cargar(ruta) == [] and sucesion.cargar(ruta) == []
    assert _lineas_sombra() == []
