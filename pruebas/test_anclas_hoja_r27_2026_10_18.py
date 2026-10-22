"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import importlib.util
import json
from pathlib import Path
import pytest
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
from ict155 import completitud, config, db, interruptores
_spec = importlib.util.spec_from_file_location('servidor_mcp_r27_s7b', RAIZ / 'cowork' / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base (LOCALAPPDATA/ict155/bd)')
ACEPTA = 'Ley 32/2014::art.12'
HOJA = 'Ley 32/2014::art.12.2'
CITA_QUE_NO_CUBRE = 'Ley 32/2014::art.12.4'
RESPUESTA_SOLO_SUBAPARTADO = f'Se puede reparar sin repetir la verificación en los casos del `{CITA_QUE_NO_CUBRE}`.'
RESPUESTA_LA_HOJA = f'Se aplica el `{HOJA}`.'
RESPUESTA_SIN_NADA = 'Esto no cita nada de ese artículo.'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    limpiar_forzados(monkeypatch, raising=False)

def _forzar(monkeypatch, modo: str):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': modo})))

def _lineas_sombra() -> list[dict]:
    ruta = interruptores.ruta_sombra()
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]

def _escribe(tmp_path, datos, nombre='temas.json') -> Path:
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta

def _tema(acepta=(ACEPTA,), acepta_hoja=None, estado_hoja=None) -> dict:
    obligatorio = {'acepta': list(acepta), 'por_que': 'el plazo tras una reparación'}
    if acepta_hoja is not None:
        obligatorio['acepta_hoja'] = list(acepta_hoja)
    if estado_hoja is not None:
        obligatorio['estado_hoja'] = estado_hoja
    return {'id': 't', 'nombre': 'Reparación de instrumentos', 'cuando': [['zzz']], 'obligatorios': [obligatorio]}

def _temas(tmp_path, **kw) -> list[completitud.Tema]:
    return completitud.cargar(_escribe(tmp_path, {'temas': [_tema(**kw)]}))

def test_hoja_activa_vacia_sin_estado_hoja(tmp_path):
    o = _temas(tmp_path, acepta_hoja=[HOJA])[0].obligatorios[0]
    assert o.acepta_hoja == (HOJA,) and o.estado_hoja == '' and (o.hoja_activa == ())

@pytest.mark.parametrize('estado', ['propuesta del 17-oct, pendiente de Responsable', 'PENDIENTE', 'rechazada por Responsable el 20-oct', 'validando', '  '])
def test_hoja_activa_vacia_con_estado_no_validado(tmp_path, estado):
    o = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=estado)[0].obligatorios[0]
    assert o.hoja_activa == ()

@pytest.mark.parametrize('estado', ['validado 18-oct', 'VALIDADO el 18-oct por Responsable', '  Validado  '])
def test_hoja_activa_con_estado_validado_sin_distinguir_mayusculas(tmp_path, estado):
    o = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=estado)[0].obligatorios[0]
    assert o.hoja_activa == (HOJA,)

def test_estado_hoja_tiene_que_ser_texto(tmp_path):
    with pytest.raises(completitud.TemasMal, match='«estado_hoja» tiene que ser un texto'):
        _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=3)

@pytest.mark.parametrize('estado', [None, 'propuesta del 17-oct, pendiente de Responsable'])
@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_sin_validar_cubre_como_antes_en_los_tres_modos(monkeypatch, con, tmp_path, modo, estado):
    """Public CI documentation."""
    _forzar(monkeypatch, modo)
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=estado)
    assert completitud.faltan(con, RESPUESTA_SOLO_SUBAPARTADO, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

def test_una_vez_validada_bloquea_si_caza_el_subapartado_equivocado(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    f = completitud.faltan(con, RESPUESTA_SOLO_SUBAPARTADO, 'zzz', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == HOJA
    assert f[0].cita_que_no_cubre and 'art.12.4' in f[0].cita_que_no_cubre

def test_una_vez_validada_sombra_avisa_sin_cambiar_el_veredicto(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'sombra')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    assert completitud.faltan(con, RESPUESTA_SOLO_SUBAPARTADO, 'zzz', ('publico',), temas) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['control'] == 'cubre_estricto' and (lineas[0]['obligatorio'] == HOJA)

def test_una_vez_validada_apagado_no_cambia(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'apagado')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    assert completitud.faltan(con, RESPUESTA_SOLO_SUBAPARTADO, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('estado', [None, 'pendiente', 'validado 18-oct'])
@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_citar_la_hoja_cubre_este_o_no_validada(monkeypatch, con, tmp_path, modo, estado):
    _forzar(monkeypatch, modo)
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=estado)
    assert completitud.faltan(con, RESPUESTA_LA_HOJA, 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('estado', [None, 'pendiente', 'validado 18-oct'])
@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_sin_citar_nada_falta_el_acepta_entero_este_o_no_validada(monkeypatch, con, tmp_path, modo, estado):
    _forzar(monkeypatch, modo)
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja=estado)
    f = completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == ACEPTA and (f[0].cita_que_no_cubre is None)

def test_validar_contra_la_base_sigue_validando_la_hoja_este_o_no_validada(con, tmp_path):
    """Public CI documentation."""
    malos = completitud.validar_contra_la_base(con, _temas(tmp_path, acepta_hoja=['Ley 32/2014::art.12.999'], estado_hoja='pendiente'))
    assert len(malos) == 1 and malos[0].startswith('Ley 32/2014::art.12.999 [t]: ')
    malos = completitud.validar_contra_la_base(con, _temas(tmp_path, acepta_hoja=['Ley 32/2014::art.12.999'], estado_hoja='validado 18-oct'))
    assert len(malos) == 1 and malos[0].startswith('Ley 32/2014::art.12.999 [t]: ')

def test_bloquea_con_hoja_validada_ensena_el_identificador_de_la_hoja(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    assert f'[en «bloquea» solo cubre citar {HOJA}' in completitud.texto(temas)
    d = completitud.a_dict(temas)
    assert d['temas'][0]['obligatorios'][0]['hoja_bloquea'] == [HOJA]

@pytest.mark.parametrize('modo', ['apagado', 'sombra'])
def test_fuera_de_bloquea_no_ensena_la_hoja(monkeypatch, tmp_path, modo):
    _forzar(monkeypatch, modo)
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    assert 'hoja_bloquea' not in completitud.a_dict(temas)['temas'][0]['obligatorios'][0]
    assert 'en «bloquea»' not in completitud.texto(temas)

def test_bloquea_sin_validar_no_ensena_nada_nuevo(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='pendiente de Responsable')
    assert 'hoja_bloquea' not in completitud.a_dict(temas)['temas'][0]['obligatorios'][0]
    assert 'en «bloquea»' not in completitud.texto(temas)

def test_cli_y_extension_dicen_lo_mismo_con_hoja_validada_en_bloquea(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    d = json.loads(json.dumps(completitud.a_dict(temas), ensure_ascii=False))
    assert srv._formatear_obligatorios(d)[0] == completitud.texto(temas)

def test_motivo_incompleta_del_servidor_dice_lo_mismo_que_la_cli(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    f = completitud.faltan(con, RESPUESTA_SOLO_SUBAPARTADO, 'zzz', ('publico',), temas)[0]
    assert f.cita_que_no_cubre
    assert srv._motivo_incompleta(f.dict()) == f.motivo
    assert f.motivo.endswith('no lo cubre') and 'art.12.4' in f.motivo

def test_controles_json_roto_no_rompe_a_dict_ni_texto(tmp_path, monkeypatch):
    """Public CI documentation."""
    monkeypatch.setattr(interruptores, 'RUTA_CONTROLES', tmp_path / 'no_existe.json')
    temas = _temas(tmp_path, acepta_hoja=[HOJA], estado_hoja='validado 18-oct')
    assert 'hoja_bloquea' not in completitud.a_dict(temas)['temas'][0]['obligatorios'][0]
    assert 'en «bloquea»' not in completitud.texto(temas)

def test_acepta_hoja_con_el_codigo_boe_de_la_misma_obra_carga(tmp_path):
    """Public CI documentation."""
    temas = _temas(tmp_path, acepta_hoja=['BOE-A-2014-13359::art.12.2'])
    assert temas[0].obligatorios[0].acepta_hoja == ('BOE-A-2014-13359::art.12.2',)

def test_acepta_con_el_codigo_boe_y_la_hoja_con_el_alias_tambien_carga(tmp_path):
    temas = _temas(tmp_path, acepta=['BOE-A-2014-13359::art.12'], acepta_hoja=[HOJA])
    assert temas[0].obligatorios[0].acepta_hoja == (HOJA,)

def test_una_hoja_de_otra_obra_de_verdad_sigue_fallando(tmp_path):
    with pytest.raises(completitud.TemasMal, match='tiene que ser igual o estar por debajo de alguno de «acepta»'):
        _temas(tmp_path, acepta_hoja=['Otra ley::art.12.2'])

def test_una_hoja_con_la_ruta_que_no_corresponde_sigue_fallando(tmp_path):
    with pytest.raises(completitud.TemasMal, match='tiene que ser igual o estar por debajo de alguno de «acepta»'):
        _temas(tmp_path, acepta_hoja=['Ley 32/2014::art.99'])

def test_una_hoja_con_el_codigo_boe_no_para_la_verificacion_en_ningun_modo(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    for modo in interruptores.MODOS:
        _forzar(monkeypatch, modo)
        temas = _temas(tmp_path, acepta_hoja=['BOE-A-2014-13359::art.12.2'])
        f = completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz', ('publico',), temas)
        assert len(f) == 1 and f[0].identificador == ACEPTA
