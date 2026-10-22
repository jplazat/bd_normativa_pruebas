"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import importlib.util
import json
from pathlib import Path
import pytest
from ict155 import completitud, db, interruptores

@pytest.fixture(scope='module')
def temas():
    return completitud.cargar()

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(autouse=True)
def aislado(monkeypatch, tmp_path):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': 'bloquea', 'relacionados_cierra': 'bloquea', 'cifras': 'sombra', 'negacion_base': 'sombra', 'brechas_r27': 'sombra', 'ambito': 'sombra', 'temas_r27': 'sombra'})))

def _anclas(temas, tema):
    return [o for t in temas if t.id == tema for o in t.obligatorios if o.regla_hoja == 'todos']
TRAMITES = ['¿Cuánto tiempo tengo para recurrir una multa por no verificar?', 'Me han impuesto una multa por no verificar. ¿Hasta cuándo puedo recurrir?', 'Me han impuesto una multa por no verificar. ¿Qué plazo tengo para recurrir?', 'Me han impuesto una multa por no verificar. ¿Cuánto plazo tengo para alegar?', 'Me han impuesto una multa por no verificar. ¿Cómo presento alegaciones?', 'Me han impuesto una multa por no verificar. ¿Qué recurso puedo presentar?', 'Me han impuesto una multa por no verificar. ¿Cuándo prescribe?', 'Me han impuesto una multa por no verificar. ¿Cuál es el plazo de prescripción?', 'Me han impuesto una multa por no verificar. ¿Cómo puedo pagar?', 'Me han impuesto una multa por no verificar. ¿Qué plazo tengo para el pago?', 'Me han impuesto una multa por no verificar. ¿Cómo solicito el pronto pago?', 'Me han impuesto una multa por no verificar. ¿Puedo solicitar una reducción?']
MIXTAS = ['¿Cuáles son las multas por no verificar un registrador y qué recurso puedo presentar?', '¿Me pueden multar por no verificar y qué recurso puedo presentar?', '¿Qué multa corresponde por no verificar y qué plazo tengo para recurrir?', '¿Cuánto es la multa por no verificar y hasta cuándo puedo recurrir?', '¿Qué sanción me pueden poner por no verificar y cuándo prescribe?', '¿Qué consecuencias tiene no verificar y cómo puedo alegar?', '¿Qué multas hay por no verificar y qué recurso puedo presentar?', '¿Cuáles son las infracciones por no verificar y cómo se pagan las multas?', '¿Me podrían sancionar por no verificar y qué recurso podría presentar?', '¿Qué multa corresponde por no verificar y puedo solicitar una reducción?']
NEGADAS = ['El termómetro no se ha reparado ni modificado. ¿Desde cuándo cuenta su verificación periódica?', 'El termómetro está sin reparar. ¿Desde cuándo cuenta su verificación periódica?', 'El termómetro no ha sido reparado. ¿Desde cuándo cuenta su verificación periódica?', 'El termómetro nunca se ha reparado. ¿Desde cuándo cuenta su verificación periódica?']
REPARACIONES = ['El termómetro no se ha reparado ni modificado. ¿Quién puede repararlo si se avería?', 'El termómetro está sin reparar; ¿quién puede repararlo?', 'El termómetro no ha sido reparado, pero ¿qué requisitos tiene su reparación?', 'El termómetro nunca se ha reparado y quiero saber quién puede repararlo.', 'No se ha reparado el termómetro; ¿quién puede reparar otro registrador?', 'No se ha reparado el termómetro y ¿quién puede reparar otro registrador?', 'No se ha verificado el termómetro. ¿Quién puede repararlo?', '¿Quién puede reparar el termómetro?']

@pytest.mark.parametrize('pregunta', TRAMITES)
def test_h1_tramite_no_exige_tramos(temas, pregunta):
    assert all((not o.hoja_gatillada(completitud.normalizar(pregunta)) for o in _anclas(temas, 'consecuencias_verificacion')))

@pytest.mark.parametrize('pregunta', MIXTAS)
def test_h2_mixta_conserva_tramos(temas, pregunta):
    assert all((o.hoja_gatillada(completitud.normalizar(pregunta)) for o in _anclas(temas, 'consecuencias_verificacion')))

@pytest.mark.parametrize('pregunta', NEGADAS)
def test_h4_reparacion_negada_no_exige_hojas(temas, pregunta):
    assert all((not o.hoja_gatillada(completitud.normalizar(pregunta)) for o in _anclas(temas, 'reparacion_instrumentos')))

@pytest.mark.parametrize('pregunta', REPARACIONES)
def test_h4_pregunta_por_otra_reparacion_conserva_hojas(temas, pregunta):
    assert all((o.hoja_gatillada(completitud.normalizar(pregunta)) for o in _anclas(temas, 'reparacion_instrumentos')))

@pytest.mark.parametrize('modo', ['apagado', 'sombra', 'bloquea'])
@pytest.mark.parametrize('grupo,activo,tema', [(TRAMITES, False, 'consecuencias_verificacion'), (MIXTAS, True, 'consecuencias_verificacion'), (NEGADAS, False, 'reparacion_instrumentos'), (REPARACIONES, True, 'reparacion_instrumentos')])
def test_preguntas_en_faltan_y_obligatorios(monkeypatch, con, temas, modo, grupo, activo, tema):
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': modo})))
    for pregunta in grupo:
        detectados = completitud.temas_de(pregunta, temas)
        assert tema in {t.id for t in detectados}
        anclas = _anclas(temas, tema)
        respuesta = ' '.join((f'`{o.hoja_activa[0]}`' for o in anclas))
        pendientes = {h for o in anclas for h in o.hoja_activa[1:]}
        faltas = {f.identificador for f in completitud.faltan(con, respuesta, pregunta, ('publico',), temas)}
        assert pendientes <= faltas if activo and modo == 'bloquea' else pendientes.isdisjoint(faltas)
        datos = completitud.a_dict(detectados, pregunta)
        actuales = [o for t in datos['temas'] if t['id'] == tema for o in t['obligatorios']]
        assert all((('hoja_bloquea' in o) == (activo and modo == 'bloquea') for o in actuales if o['identificador'] in {a.acepta[0] for a in anclas}))
        assert {a.acepta[0] for a in anclas} <= {o['identificador'] for o in actuales}
        ruta = interruptores.ruta_sombra()
        if ruta.exists() and (not activo):
            lineas = [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]
            assert pendientes.isdisjoint({l.get('obligatorio') for l in lineas})

@pytest.fixture(scope='module')
def srv():
    ruta = Path(__file__).resolve().parents[1] / 'cowork' / 'servidor_mcp.py'
    spec = importlib.util.spec_from_file_location('servidor_s7i', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

@pytest.mark.parametrize('formato', ['cli', 'mcp'])
def test_h5_nombra_los_dos_articulos_y_limita_su_cobertura(temas, srv, formato):
    pregunta = '¿Quién puede reparar el termómetro?'
    detectados = completitud.temas_de(pregunta, temas)
    salida = completitud.texto(detectados, pregunta) if formato == 'cli' else srv._formatear_obligatorios(completitud.a_dict(detectados, pregunta))[0]
    linea = next((l for l in salida.splitlines() if 'hay que citar TODOS: RD 244/2016::art.20.1' in l))
    assert 'RD 244/2016::art.20 y Ley 32/2014::art.11' in linea
    assert 'cada artículo entero cubre solo las hojas de su propia obra' in linea
    assert '(o el artículo entero)' not in linea
    assert salida == completitud.texto(detectados, pregunta)

def test_h5_articulo_entero_del_rd_no_cubre_la_ley(con, temas):
    pregunta = '¿Quién puede reparar el termómetro?'
    respuesta = '`RD 244/2016::art.20` `Ley 32/2014::art.12`'
    faltas = {f.identificador for f in completitud.faltan(con, respuesta, pregunta, ('publico',), temas)}
    assert 'Ley 32/2014::art.11.1' in faltas
    assert not {'RD 244/2016::art.20.1', 'RD 244/2016::art.20.2'} & faltas
    faltas_con_ambos = {f.identificador for f in completitud.faltan(con, respuesta + ' `Ley 32/2014::art.11`', pregunta, ('publico',), temas)}
    assert 'Ley 32/2014::art.11.1' not in faltas_con_ambos
