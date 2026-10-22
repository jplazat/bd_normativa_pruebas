"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import importlib.util
import json
from pathlib import Path
import pytest
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
from ict155 import completitud, config, consulta, db, interruptores
_spec = importlib.util.spec_from_file_location('servidor_mcp_r27_s7f', RAIZ / 'cowork' / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base (LOCALAPPDATA/ict155/bd)')

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(scope='module')
def temas_reales():
    return completitud.cargar()

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    limpiar_forzados(monkeypatch, raising=False)
    return tmp_path

def _forzar(monkeypatch, **controles):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps(controles)))

def _lineas_sombra() -> list[dict]:
    ruta = interruptores.ruta_sombra()
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]

def _escribe(tmp_path, datos) -> Path:
    ruta = tmp_path / 'temas.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta
PREGUNTA_CONSECUENCIAS = '¿qué consecuencias tiene no verificar un instrumento?'
PREGUNTA_PLAZO = '¿cada cuánto hay que verificar un registrador de temperatura?'
PREGUNTA_REPARACION = '¿qué hay que hacer para reparar un instrumento de medida sometido a control metrológico?'

def test_citar_el_apartado_entero_cubre_las_tres_letras_del_articulo_23(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'El importe de las multas está en el `Ley 32/2014::art.23.1`.'
    f = completitud.faltan(con, respuesta, PREGUNTA_CONSECUENCIAS, ('publico',), temas_reales)
    assert not any((x.identificador.startswith('Ley 32/2014::art.23') for x in f))

def test_citar_el_articulo_14_entero_cubre_los_dos_tramos_solo_con(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'El plazo se cuenta según el `Orden ICT/155/2020::art.14`.'
    f = completitud.faltan(con, respuesta, PREGUNTA_PLAZO, ('publico',), temas_reales)
    assert not any((x.identificador in ('Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4') for x in f))

def test_ojo_con_p1_citar_solo_una_hoja_no_cubre_su_hermana(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'El fabricante puede repararlo sin verificación después de reparación (`Ley 32/2014::art.12.4`).'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    assert 'Ley 32/2014::art.12.2' in {x.identificador for x in f}

def test_citar_solo_el_articulo_20_entero_no_cubre_la_hoja_de_la_ley(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'Quién puede reparar: ver el `RD 244/2016::art.20` completo.'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    assert 'Ley 32/2014::art.11.1' in {x.identificador for x in f}

def test_citar_solo_el_articulo_11_entero_no_cubre_las_hojas_del_rd(monkeypatch, con, temas_reales):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'La declaración responsable: ver el `Ley 32/2014::art.11` completo.'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    faltan_rd = {x.identificador for x in f if x.identificador.startswith('RD 244/2016::art.20')}
    assert faltan_rd == {'RD 244/2016::art.20.1', 'RD 244/2016::art.20.2'}

def test_cita_que_no_cubre_no_acusa_a_citas_de_otra_obra(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'Hay que presentar antes la declaración responsable (`RD 244/2016::art.20.1`) y, tras comprobar el funcionamiento, volver a colocar los precintos (`RD 244/2016::art.20.2`).'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    falta_11_1 = next((x for x in f if x.identificador == 'Ley 32/2014::art.11.1'))
    assert falta_11_1.cita_que_no_cubre is None
    assert 'no lo cubre' not in falta_11_1.motivo

def test_cita_que_no_cubre_sigue_acusando_a_citas_de_la_misma_obra(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'El fabricante puede repararlo sin verificación después de reparación (`Ley 32/2014::art.12.4`).'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    falta_12_2 = next((x for x in f if x.identificador == 'Ley 32/2014::art.12.2'))
    assert falta_12_2.cita_que_no_cubre and 'art.12.4' in falta_12_2.cita_que_no_cubre

@pytest.mark.parametrize('con_parentesis, sin_parentesis', [('art.22.1.f)', 'art.22.1.f'), ('art.23.1.a)', 'art.23.1.a')])
def test_ruta_canonica_quita_el_parentesis_final_de_una_letra(con_parentesis, sin_parentesis):
    assert consulta.ruta_canonica(con_parentesis) == sin_parentesis

def test_ruta_canonica_no_toca_un_parentesis_que_no_sigue_a_una_letra_de_un_tramo():
    """Public CI documentation."""
    assert consulta.ruta_canonica('anexo.XI/apend.III') == 'anexo.XI/apend.III'

def test_citar_la_letra_con_parentesis_cubre_igual_que_sin_el(monkeypatch, con, temas_reales):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'Es infracción leve (`Ley 32/2014::art.22.1.f)`).'
    f = completitud.faltan(con, respuesta, PREGUNTA_CONSECUENCIAS, ('publico',), temas_reales)
    assert 'Ley 32/2014::art.22.1.f' not in {x.identificador for x in f}

def _temas_nuevo_con_solo_con(tmp_path, **cambios_obligatorio) -> list[completitud.Tema]:
    o = {'acepta': ['Ley 32/2014::art.1'], 'por_que': 'un precepto que solo exige cubre_estricto', 'estado_hoja': 'validado (prueba sintética)', 'solo_con': 'cubre_estricto'}
    o.update(cambios_obligatorio)
    datos = {'temas': [{'id': 'nuevo_r27', 'nombre': 'Nuevo de la Fase 2', 'control': 'temas_r27', 'cuando': [['zzz']], 'obligatorios': [o]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

def test_solo_con_apagado_no_anota_sombra_aunque_el_tema_sea_de_temas_r27(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='apagado', temas_r27='sombra')
    temas = _temas_nuevo_con_solo_con(tmp_path)
    assert completitud.faltan(con, 'Esto no cita nada.', 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

def test_solo_con_en_sombra_de_verdad_si_anota_desde_para_sombra(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='sombra', temas_r27='sombra')
    temas = _temas_nuevo_con_solo_con(tmp_path)
    assert completitud.faltan(con, 'Esto no cita nada.', 'zzz', ('publico',), temas) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['obligatorio'] == 'Ley 32/2014::art.1'
ACEPTA_DOS_NORMAS = ['RD 244/2016::art.20', 'Ley 32/2014::art.11']
HOJA_RD_1, HOJA_RD_2, HOJA_LEY = ('RD 244/2016::art.20.1', 'RD 244/2016::art.20.2', 'Ley 32/2014::art.11.1')
POR_QUE_HOJA_DOS_NORMAS = {HOJA_RD_1: 'motivo del 20.1', HOJA_RD_2: 'motivo del 20.2', HOJA_LEY: 'motivo del 11.1'}

def _temas_dos_normas(tmp_path, **cambios) -> list[completitud.Tema]:
    o = {'acepta': ACEPTA_DOS_NORMAS, 'por_que': 'motivo general del grupo', 'acepta_hoja': [HOJA_RD_1, HOJA_RD_2, HOJA_LEY], 'regla_hoja': 'todos', 'estado_hoja': 'validado (prueba sintética)', 'por_que_hoja': POR_QUE_HOJA_DOS_NORMAS}
    o.update(cambios)
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [o]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

def test_a_dict_exporta_el_por_que_de_cada_hoja_con_regla_todos(monkeypatch, tmp_path):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_dos_normas(tmp_path)
    o = completitud.a_dict(temas)['temas'][0]['obligatorios'][0]
    assert o['hoja_bloquea_por_que'] == POR_QUE_HOJA_DOS_NORMAS

def test_texto_desglosa_cada_hoja_con_su_motivo_propio(monkeypatch, tmp_path):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_dos_normas(tmp_path)
    t = completitud.texto(temas)
    for h, motivo in POR_QUE_HOJA_DOS_NORMAS.items():
        assert f'· {h} — {motivo}' in t

def test_texto_omite_tambien_vale_cuando_la_regla_todos_esta_activa(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_dos_normas(tmp_path)
    assert 'también vale' not in completitud.texto(temas)

@pytest.mark.parametrize('modo', ['apagado', 'sombra'])
def test_texto_fuera_de_bloquea_sigue_diciendo_tambien_vale(monkeypatch, tmp_path, modo):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto=modo)
    temas = _temas_dos_normas(tmp_path)
    assert f'también vale: {ACEPTA_DOS_NORMAS[1]}' in completitud.texto(temas)

def test_cli_y_extension_dicen_lo_mismo_con_regla_todos_y_dos_normas(monkeypatch, tmp_path):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_dos_normas(tmp_path)
    d = json.loads(json.dumps(completitud.a_dict(temas), ensure_ascii=False))
    assert srv._formatear_obligatorios(d)[0] == completitud.texto(temas)

def test_motivo_incompleta_del_servidor_sigue_sin_cita_que_no_cubre_entre_obras(monkeypatch, con, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    respuesta = 'Hay que presentar antes la declaración responsable (`RD 244/2016::art.20.1`) y, tras comprobar el funcionamiento, volver a colocar los precintos (`RD 244/2016::art.20.2`).'
    f = completitud.faltan(con, respuesta, PREGUNTA_REPARACION, ('publico',), temas_reales)
    falta_11_1 = next((x for x in f if x.identificador == 'Ley 32/2014::art.11.1'))
    assert srv._motivo_incompleta(falta_11_1.dict()) == falta_11_1.motivo
    assert 'no lo cubre' not in srv._motivo_incompleta(falta_11_1.dict())

def test_por_que_hoja_con_espacios_de_mas_se_normaliza_igual_que_acepta_hoja(tmp_path):
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': ['Ley 32/2014::art.12'], 'por_que': 'p', 'acepta_hoja': [' Ley 32/2014::art.12.1 ', 'Ley 32/2014 :: art.12.2'], 'regla_hoja': 'todos', 'estado_hoja': 'validado (prueba)', 'por_que_hoja': {' Ley 32/2014::art.12.1 ': 'motivo a', 'Ley 32/2014 :: art.12.2': 'motivo b'}}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    o = temas[0].obligatorios[0]
    assert o.acepta_hoja == ('Ley 32/2014::art.12.1', 'Ley 32/2014::art.12.2')
    assert o.por_que_hoja == {'Ley 32/2014::art.12.1': 'motivo a', 'Ley 32/2014::art.12.2': 'motivo b'}

def test_estado_hoja_en_femenino_activa_la_hoja_igual_que_en_masculino(tmp_path):
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': ['Ley 32/2014::art.12'], 'por_que': 'p', 'acepta_hoja': ['Ley 32/2014::art.12.1'], 'estado_hoja': 'validada por Responsable el 18-oct-2026 (chat)'}]}]}
    temas = completitud.cargar(_escribe(tmp_path, datos))
    assert temas[0].obligatorios[0].hoja_activa == ('Ley 32/2014::art.12.1',)

def _temas_solo_con_estado(tmp_path, estado_hoja) -> list[completitud.Tema]:
    o = {'acepta': ['Ley 32/2014::art.1'], 'por_que': 'un precepto que solo exige cubre_estricto', 'solo_con': 'cubre_estricto'}
    if estado_hoja is not None:
        o['estado_hoja'] = estado_hoja
    datos = {'temas': [{'id': 'u', 'nombre': 'U', 'cuando': [['zzz']], 'obligatorios': [o]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

def test_solo_con_pendiente_no_se_exige_en_bloquea(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_solo_con_estado(tmp_path, 'pendiente de Responsable')
    assert completitud.faltan(con, 'Esto no cita nada.', 'zzz', ('publico',), temas) == []

def test_solo_con_pendiente_tampoco_anota_en_sombra(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, cubre_estricto='sombra')
    temas = _temas_solo_con_estado(tmp_path, 'pendiente de Responsable')
    assert completitud.faltan(con, 'Esto no cita nada.', 'zzz', ('publico',), temas) == []
    assert _lineas_sombra() == []

@pytest.mark.parametrize('estado_hoja', ['validado por Responsable', 'validada por Responsable', None])
def test_solo_con_validado_o_sin_estado_sigue_exigiendose_en_bloquea(monkeypatch, con, tmp_path, estado_hoja):
    _forzar(monkeypatch, cubre_estricto='bloquea')
    temas = _temas_solo_con_estado(tmp_path, estado_hoja)
    f = completitud.faltan(con, 'Esto no cita nada.', 'zzz', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == 'Ley 32/2014::art.1'
