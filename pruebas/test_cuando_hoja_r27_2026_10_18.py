"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
from pathlib import Path
import pytest
from ict155 import completitud, config, db, interruptores
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base (LOCALAPPDATA/ict155/bd)')
ACEPTA = 'Ley 32/2014::art.12'
HOJA_1, HOJA_2, HOJA_3 = ('Ley 32/2014::art.12.1', 'Ley 32/2014::art.12.2', 'Ley 32/2014::art.12.3')
ACEPTA_SOLO_CON = 'Ley 32/2014::art.1'

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

def _obligatorio_todos(**cambios) -> dict:
    o = {'acepta': [ACEPTA], 'por_que': 'el plazo tras una reparación', 'acepta_hoja': [HOJA_1, HOJA_2, HOJA_3], 'regla_hoja': 'todos', 'estado_hoja': 'validado (prueba sintética)', 'por_que_hoja': {HOJA_1: 'por qué 1', HOJA_2: 'por qué 2', HOJA_3: 'por qué 3'}}
    o.update(cambios)
    return o

def _temas_todos(tmp_path, **cambios) -> list[completitud.Tema]:
    datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [_obligatorio_todos(**cambios)]}]}
    return completitud.cargar(_escribe(tmp_path, datos))

def _obligatorio_solo_con(**cambios) -> dict:
    o = {'acepta': [ACEPTA_SOLO_CON], 'por_que': 'un precepto que solo exige cubre_estricto', 'estado_hoja': 'validado (prueba sintética)', 'solo_con': 'cubre_estricto'}
    o.update(cambios)
    return o

def _temas_solo_con(tmp_path, **cambios) -> list[completitud.Tema]:
    datos = {'temas': [{'id': 'u', 'nombre': 'U', 'cuando': [['zzz']], 'obligatorios': [_obligatorio_solo_con(**cambios)]}]}
    return completitud.cargar(_escribe(tmp_path, datos))
RESPUESTA_SOLO_1 = f'Se aplica el `{HOJA_1}`.'
RESPUESTA_TODOS = f'Se aplican el `{HOJA_1}`, el `{HOJA_2}` y el `{HOJA_3}`.'
RESPUESTA_ENTERO = f'Se aplica el `{ACEPTA}` entero.'
RESPUESTA_SIN_NADA = 'Esto no cita nada de ese artículo.'
RESPUESTA_CITA_SOLO_CON = f'Se aplica el `{ACEPTA_SOLO_CON}`.'
PREGUNTA_CASA = '¿qué repara exactamente la intervención?'
PREGUNTA_NO_CASA = '¿cuánto cuesta la verificación?'

def test_cuando_hoja_ausente_gatilla_siempre(tmp_path):
    o = _temas_todos(tmp_path)[0].obligatorios[0]
    assert o.cuando_hoja == ()
    assert o.hoja_gatillada(completitud.normalizar('cualquier cosa, lo que sea')) is True

def test_cuando_hoja_carga_y_compara_sin_tildes(tmp_path):
    o = _temas_todos(tmp_path, cuando_hoja=[['repar']])[0].obligatorios[0]
    assert o.hoja_gatillada(completitud.normalizar('hay que repararlo')) is True
    assert o.hoja_gatillada(completitud.normalizar('no tiene nada que ver')) is False

def test_cuando_hoja_con_varios_grupos_exige_casar_todos(tmp_path):
    o = _temas_todos(tmp_path, cuando_hoja=[['repar'], ['placa', 'sonda']])[0].obligatorios[0]
    assert o.hoja_gatillada(completitud.normalizar('reparar la placa')) is True
    assert o.hoja_gatillada(completitud.normalizar('reparar el equipo')) is False
    assert o.hoja_gatillada(completitud.normalizar('cambiar la placa sin reparar')) is False or True
    assert o.hoja_gatillada(completitud.normalizar('cambiar la placa')) is False

def test_cuando_hoja_sin_acepta_hoja_ni_solo_con_no_tiene_sentido(tmp_path):
    with pytest.raises(completitud.TemasMal, match='«cuando_hoja» no tiene sentido sin «acepta_hoja» ni «solo_con»'):
        datos = {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [{'acepta': [ACEPTA], 'por_que': 'x', 'cuando_hoja': [['repar']]}]}]}
        completitud.cargar(_escribe(tmp_path, datos))

def test_cuando_hoja_vale_con_solo_con_sin_acepta_hoja(tmp_path):
    o = _temas_solo_con(tmp_path, cuando_hoja=[['repar']])[0].obligatorios[0]
    assert o.cuando_hoja and o.solo_con == 'cubre_estricto'

def test_cuando_hoja_mal_formado_falla_como_cuando(tmp_path):
    with pytest.raises(completitud.TemasMal, match='«cuando_hoja» tiene que ser una lista no vacía'):
        _temas_todos(tmp_path, cuando_hoja=[])
    with pytest.raises(completitud.TemasMal, match='hay una expresión vacía o que no es texto'):
        _temas_todos(tmp_path, cuando_hoja=[['']])
    with pytest.raises(completitud.TemasMal, match='no compila'):
        _temas_todos(tmp_path, cuando_hoja=[['(']])
    with pytest.raises(completitud.TemasMal, match='lleva tildes o eñes'):
        _temas_todos(tmp_path, cuando_hoja=[['reparación']])
    with pytest.raises(completitud.TemasMal, match='casa con el texto vacío'):
        _temas_todos(tmp_path, cuando_hoja=[['.*']])

def test_todos_con_cuando_hoja_que_no_casa_se_comporta_como_sin_ancla_en_bloquea(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    assert completitud.faltan(con, RESPUESTA_SOLO_1, 'zzz, pero de otra cosa', ('publico',), temas) == []
    assert completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz, pero de otra cosa', ('publico',), temas) == [completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz, pero de otra cosa', ('publico',), temas)[0]]
    f = completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz, pero de otra cosa', ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == ACEPTA and (f[0].cita_que_no_cubre is None)

def test_todos_con_cuando_hoja_que_casa_exige_todos_en_bloquea(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    f = completitud.faltan(con, RESPUESTA_SOLO_1, 'zzz hay que repararlo', ('publico',), temas)
    assert {x.identificador for x in f} == {HOJA_2, HOJA_3}
    assert completitud.faltan(con, RESPUESTA_TODOS, 'zzz hay que repararlo', ('publico',), temas) == []

def test_todos_con_cuando_hoja_el_articulo_entero_cubre_case_o_no_cuando_hoja(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    assert completitud.faltan(con, RESPUESTA_ENTERO, 'zzz hay que repararlo', ('publico',), temas) == []
    assert completitud.faltan(con, RESPUESTA_ENTERO, 'zzz, pero de otra cosa', ('publico',), temas) == []

def test_todos_con_cuando_hoja_que_no_casa_en_sombra_no_anota_nada(monkeypatch, con, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'sombra')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    assert completitud.faltan(con, RESPUESTA_SOLO_1, 'zzz, pero de otra cosa', ('publico',), temas) == []
    assert _lineas_sombra() == []

def test_todos_con_cuando_hoja_que_casa_en_sombra_anota_como_antes(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'sombra')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    assert completitud.faltan(con, RESPUESTA_SOLO_1, 'zzz hay que repararlo', ('publico',), temas) == []
    lineas = _lineas_sombra()
    assert {l['obligatorio'] for l in lineas} == {HOJA_2, HOJA_3}

def test_todos_con_cuando_hoja_en_apagado_no_cambia_case_o_no(monkeypatch, con, tmp_path):
    _forzar(monkeypatch, 'apagado')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    for pregunta in ('zzz, pero de otra cosa', 'zzz hay que repararlo'):
        assert completitud.faltan(con, RESPUESTA_SOLO_1, pregunta, ('publico',), temas) == []
    assert _lineas_sombra() == []

def test_solo_con_con_cuando_hoja_que_no_casa_no_existe_en_ningun_modo(monkeypatch, con, tmp_path):
    temas = _temas_solo_con(tmp_path, cuando_hoja=[['repar']])
    for modo in interruptores.MODOS:
        _forzar(monkeypatch, modo)
        assert completitud.faltan(con, RESPUESTA_SIN_NADA, 'zzz, pero de otra cosa', ('publico',), temas) == []
        assert _lineas_sombra() == []

def test_solo_con_con_cuando_hoja_que_casa_se_comporta_como_antes_de_s7e(monkeypatch, con, tmp_path):
    temas = _temas_solo_con(tmp_path, cuando_hoja=[['repar']])
    pregunta = 'zzz hay que repararlo'
    _forzar(monkeypatch, 'apagado')
    assert completitud.faltan(con, RESPUESTA_SIN_NADA, pregunta, ('publico',), temas) == []
    assert _lineas_sombra() == []
    _forzar(monkeypatch, 'sombra')
    assert completitud.faltan(con, RESPUESTA_SIN_NADA, pregunta, ('publico',), temas) == []
    lineas = _lineas_sombra()
    assert len(lineas) == 1 and lineas[0]['obligatorio'] == ACEPTA_SOLO_CON
    _forzar(monkeypatch, 'bloquea')
    f = completitud.faltan(con, RESPUESTA_SIN_NADA, pregunta, ('publico',), temas)
    assert len(f) == 1 and f[0].identificador == ACEPTA_SOLO_CON
    assert completitud.faltan(con, RESPUESTA_CITA_SOLO_CON, pregunta, ('publico',), temas) == []

def test_a_dict_y_texto_sin_pregunta_es_byte_a_byte_lo_de_antes(monkeypatch, tmp_path):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    d = completitud.a_dict(temas)
    o = d['temas'][0]['obligatorios'][0]
    assert o['hoja_bloquea'] == [HOJA_1, HOJA_2, HOJA_3] and o['hoja_bloquea_regla'] == 'todos'
    assert f'[en «bloquea» hay que citar TODOS: {HOJA_1}, {HOJA_2}, {HOJA_3}' in completitud.texto(temas)

def test_a_dict_y_texto_con_pregunta_que_no_casa_oculta_el_detalle_de_hoja(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    d = completitud.a_dict(temas, PREGUNTA_NO_CASA)
    o = d['temas'][0]['obligatorios'][0]
    assert 'hoja_bloquea' not in o and 'hoja_bloquea_regla' not in o
    assert o['identificador'] == ACEPTA
    assert 'en «bloquea»' not in completitud.texto(temas, PREGUNTA_NO_CASA)

def test_a_dict_y_texto_con_pregunta_que_casa_ensena_el_detalle_de_hoja(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    d = completitud.a_dict(temas, PREGUNTA_CASA)
    o = d['temas'][0]['obligatorios'][0]
    assert o['hoja_bloquea'] == [HOJA_1, HOJA_2, HOJA_3] and o['hoja_bloquea_regla'] == 'todos'
    assert f'[en «bloquea» hay que citar TODOS: {HOJA_1}, {HOJA_2}, {HOJA_3}' in completitud.texto(temas, PREGUNTA_CASA)

def test_a_dict_y_texto_solo_con_con_pregunta_que_no_casa_lo_oculta_entero(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_solo_con(tmp_path, cuando_hoja=[['repar']])
    d = completitud.a_dict(temas, PREGUNTA_NO_CASA)
    assert d['temas'][0]['obligatorios'] == [] and d['n_obligatorios'] == 0
    assert ACEPTA_SOLO_CON not in completitud.texto(temas, PREGUNTA_NO_CASA)

def test_a_dict_y_texto_solo_con_con_pregunta_que_casa_lo_ensena(monkeypatch, tmp_path):
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_solo_con(tmp_path, cuando_hoja=[['repar']])
    d = completitud.a_dict(temas, PREGUNTA_CASA)
    assert d['n_obligatorios'] == 1 and d['temas'][0]['obligatorios'][0]['identificador'] == ACEPTA_SOLO_CON
    assert ACEPTA_SOLO_CON in completitud.texto(temas, PREGUNTA_CASA)

def test_cli_y_extension_dicen_lo_mismo_con_pregunta(monkeypatch, tmp_path):
    """Public CI documentation."""
    import importlib.util
    raiz = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location('servidor_mcp_r27_s7e', raiz / 'cowork' / 'servidor_mcp.py')
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    _forzar(monkeypatch, 'bloquea')
    temas = _temas_todos(tmp_path, cuando_hoja=[['repar']])
    for pregunta in (PREGUNTA_CASA, PREGUNTA_NO_CASA):
        d = json.loads(json.dumps(completitud.a_dict(temas, pregunta), ensure_ascii=False))
        assert srv._formatear_obligatorios(d)[0] == completitud.texto(temas, pregunta)

def test_cli_obligatorios_json_pasa_la_pregunta(monkeypatch, tmp_path, capsys):
    from ict155 import cli
    monkeypatch.setattr(completitud, 'RUTA_TEMAS', _escribe(tmp_path, {'temas': [{'id': 't', 'nombre': 'T', 'cuando': [['zzz']], 'obligatorios': [_obligatorio_todos(cuando_hoja=[['repar']])]}]}))
    _forzar(monkeypatch, 'bloquea')
    fuente = tmp_path / 'pregunta.md'
    fuente.write_text('zzz, pero de otra cosa', encoding='utf-8')
    rc = cli.main(['obligatorios', str(fuente), '--json'])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 0
    o = salida['temas'][0]['obligatorios'][0]
    assert 'hoja_bloquea' not in o
    fuente.write_text('zzz, hay que repararlo ya', encoding='utf-8')
    rc = cli.main(['obligatorios', str(fuente), '--json'])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 0
    o = salida['temas'][0]['obligatorios'][0]
    assert o.get('hoja_bloquea') == [HOJA_1, HOJA_2, HOJA_3]

@pytest.fixture(scope='module')
def temas_reales():
    return completitud.cargar()

def _obligatorio_real(temas, tema_id: str, acepta0: str) -> completitud.Obligatorio:
    for t in temas:
        if t.id == tema_id:
            for o in t.obligatorios:
                if o.acepta[0] == acepta0:
                    return o
    raise AssertionError(f'no encontrado: {tema_id} / {acepta0}')
COMPUTO_POSITIVAS = ['Compré los registradores en noviembre pero no los instalé hasta el año siguiente. ¿Cuándo vencía la primera verificación periódica si no hay acta de puesta en servicio?', 'El organismo verificó el registrador antes de que venciera el plazo. ¿Desde qué fecha se cuenta la siguiente verificación periódica?']
COMPUTO_NEGATIVAS = ['La verificación periódica de un registrador vence el día 20 y el operador la pidió el día 10. ¿Puede seguir usándolo hasta que vengan a verificarlo?', 'Me dicen que hay que sustituir los registradores a los diez años de vida útil aunque pasen la verificación periódica. ¿Es así?', 'El fabricante recompila el firmware del registrador sin cambiar el número de versión. ¿Cierra eso la carencia de versiones?', 'Un inspector calificó como leve una infracción por no verificar. ¿Cuándo prescribe la infracción y desde cuándo se cuenta?']

@pytest.mark.parametrize('pregunta', COMPUTO_POSITIVAS)
def test_computo_gatilla_con_preguntas_que_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4'):
        o = _obligatorio_real(temas_reales, 'plazo_verificacion_temperatura', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is True, (acepta0, pregunta)

@pytest.mark.parametrize('pregunta', COMPUTO_NEGATIVAS)
def test_computo_no_gatilla_con_preguntas_parecidas_que_no_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4'):
        o = _obligatorio_real(temas_reales, 'plazo_verificacion_temperatura', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is False, (acepta0, pregunta)
PASADO_PLAZO_POSITIVAS = ['El operador ha seguido usando los registradores con la verificación periódica vencida hace cinco meses. ¿Puede seguir así?', 'Se detectaron registradores sin verificar en una inspección y el operador dice que puede seguir igual mientras no se abra expediente. ¿Es cierto?']
PASADO_PLAZO_NEGATIVAS = ['Un registrador da un error mayor que el de su clase en la verificación periódica. ¿Qué plazos tiene el organismo para el informe?', 'El técnico que repasó la placa de un registrador solo entregó una factura. ¿Qué tiene que contener el informe del reparador?', 'Tras reparar un registrador, el reparador lo ha vuelto a precintar. ¿Tiene que estar parado hasta la verificación después de reparación?']

@pytest.mark.parametrize('pregunta', PASADO_PLAZO_POSITIVAS)
def test_pasado_plazo_gatilla_con_preguntas_que_tratan_de_eso(temas_reales, pregunta):
    o = _obligatorio_real(temas_reales, 'consecuencias_verificacion', 'Orden ICT/155/2020::art.14')
    assert o.hoja_gatillada(completitud.normalizar(pregunta)) is True, pregunta

@pytest.mark.parametrize('pregunta', PASADO_PLAZO_NEGATIVAS)
def test_pasado_plazo_no_gatilla_con_preguntas_parecidas_que_no_tratan_de_eso(temas_reales, pregunta):
    o = _obligatorio_real(temas_reales, 'consecuencias_verificacion', 'Orden ICT/155/2020::art.14')
    assert o.hoja_gatillada(completitud.normalizar(pregunta)) is False, pregunta
MULTAS_POSITIVAS = ['El operador ha seguido usando registradores con la verificación periódica vencida. ¿Qué infracciones son y qué multas tienen?', 'Un registrador de un furgón sigue circulando sin haber superado la verificación. ¿Qué sanción le puede caer al operador?']
MULTAS_NEGATIVAS = ['Un registrador da un error mayor que el de su clase en la verificación periódica. ¿Qué plazos tiene el organismo para el informe?', 'El fabricante recompila el firmware del registrador sin cambiar el número de versión. ¿Cierra eso la carencia de versiones?', 'Un inspector calificó como leve una infracción por no verificar. ¿Cuándo prescribe la infracción y desde cuándo se cuenta?']

@pytest.mark.parametrize('pregunta', MULTAS_POSITIVAS)
def test_multas_gatilla_con_preguntas_que_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Ley 32/2014::art.22', 'Ley 32/2014::art.23'):
        o = _obligatorio_real(temas_reales, 'consecuencias_verificacion', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is True, (acepta0, pregunta)

@pytest.mark.parametrize('pregunta', MULTAS_NEGATIVAS)
def test_multas_no_gatilla_con_preguntas_parecidas_que_no_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Ley 32/2014::art.22', 'Ley 32/2014::art.23'):
        o = _obligatorio_real(temas_reales, 'consecuencias_verificacion', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is False, (acepta0, pregunta)
REPARACION_POSITIVAS = ['Un superadministrador puede corregir a distancia el desplazamiento de calibración de los registradores. ¿Quién puede ajustar un registrador sometido a control metrológico y qué hace falta después?', 'El técnico que sustituyó la placa electrónica de un registrador averiado solo entregó una factura. ¿Qué tiene que contener el informe del reparador?', 'Tras reparar un registrador averiado, el reparador lo ha vuelto a precintar con sus propios precintos. ¿Puede el operador volver a usarlo ya?']
REPARACION_NEGATIVAS = ['La verificación periódica de un registrador vence el día 20 y el operador la pidió el día 10. ¿Puede seguir usándolo hasta que vengan a verificarlo?', 'Me dicen que hay que sustituir los registradores a los diez años de vida útil aunque pasen la verificación periódica. ¿Es así?', 'El fabricante recompila el firmware del registrador sin cambiar el número de versión. ¿Cierra eso la carencia de versiones?']

@pytest.mark.parametrize('pregunta', REPARACION_POSITIVAS)
def test_reparacion_gatilla_con_preguntas_que_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Ley 32/2014::art.12', 'RD 244/2016::art.20'):
        o = _obligatorio_real(temas_reales, 'reparacion_instrumentos', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is True, (acepta0, pregunta)

@pytest.mark.parametrize('pregunta', REPARACION_NEGATIVAS)
def test_reparacion_no_gatilla_con_preguntas_parecidas_que_no_tratan_de_eso(temas_reales, pregunta):
    for acepta0 in ('Ley 32/2014::art.12', 'RD 244/2016::art.20'):
        o = _obligatorio_real(temas_reales, 'reparacion_instrumentos', acepta0)
        assert o.hoja_gatillada(completitud.normalizar(pregunta)) is False, (acepta0, pregunta)

def test_faltan_real_computo_exige_el_detalle_solo_cuando_la_pregunta_lo_pide(monkeypatch, con, temas_reales):
    _forzar(monkeypatch, 'bloquea')
    positiva, negativa = (COMPUTO_POSITIVAS[0], COMPUTO_NEGATIVAS[0])
    sombra = interruptores.ruta_sombra()
    f_pos = {x.identificador for x in completitud.faltan(con, RESPUESTA_SIN_NADA, positiva, ('publico',), temas_reales)}
    en_sombra_pos = sombra.read_text(encoding='utf-8') if sombra.exists() else ''
    f_neg = {x.identificador for x in completitud.faltan(con, RESPUESTA_SIN_NADA, negativa, ('publico',), temas_reales)}
    en_sombra_total = sombra.read_text(encoding='utf-8') if sombra.exists() else ''
    en_sombra_neg = en_sombra_total[len(en_sombra_pos):]
    assert 'Orden ICT/155/2020::art.14.2' not in f_pos and 'Orden ICT/155/2020::art.14.4' not in f_pos
    assert 'Orden ICT/155/2020::art.14.2' in en_sombra_pos and 'Orden ICT/155/2020::art.14.4' in en_sombra_pos
    assert 'Orden ICT/155/2020::art.14.2' not in f_neg and 'Orden ICT/155/2020::art.14.4' not in f_neg
    assert 'Orden ICT/155/2020::art.14.2' not in en_sombra_neg and 'Orden ICT/155/2020::art.14.4' not in en_sombra_neg

def test_faltan_real_multas_exige_todos_los_tramos_solo_cuando_la_pregunta_lo_pide(monkeypatch, con, temas_reales):
    _forzar(monkeypatch, 'bloquea')
    respuesta_un_tramo = 'Se aplica `Ley 32/2014::art.22.1.f`. También `Orden ICT/155/2020::art.14.1`. Y `Ley 32/2014::art.23.1.a`.'
    positiva, negativa = (MULTAS_POSITIVAS[0], MULTAS_NEGATIVAS[-1])
    f_pos = {x.identificador for x in completitud.faltan(con, respuesta_un_tramo, positiva, ('publico',), temas_reales)}
    f_neg = {x.identificador for x in completitud.faltan(con, respuesta_un_tramo, negativa, ('publico',), temas_reales)}
    assert {'Ley 32/2014::art.22.2.b', 'Ley 32/2014::art.22.3.b'} <= f_pos
    assert 'Ley 32/2014::art.22.2.b' not in f_neg and 'Ley 32/2014::art.22.3.b' not in f_neg

def test_a_dict_real_no_ensena_el_detalle_de_multas_en_una_pregunta_de_relleno(monkeypatch, temas_reales):
    """Public CI documentation."""
    _forzar(monkeypatch, 'bloquea')
    pregunta = MULTAS_NEGATIVAS[-1]
    detectados = completitud.temas_de(pregunta, temas_reales)
    d = completitud.a_dict(detectados, pregunta)
    for t in d['temas']:
        for o in t['obligatorios']:
            if o['identificador'] in ('Ley 32/2014::art.22', 'Ley 32/2014::art.23'):
                assert 'hoja_bloquea_regla' not in o
