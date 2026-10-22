"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
import pytest
from ict155 import completitud, config, db, interruptores
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta la base')

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path))
    limpiar_forzados(monkeypatch, raising=False)

def _exigidos(monkeypatch, pregunta: str, modo: str='bloquea') -> set[str]:
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': modo})))
    texto = completitud.texto(completitud.temas_de(pregunta, completitud.cargar()), pregunta)
    return {i for i in ('Ley 32/2014::art.23.1.a', 'Ley 32/2014::art.22.3.b', 'Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4', 'Ley 32/2014::art.12.1') if i in texto}

def test_consecuencias_de_no_verificar_exige_los_tramos_de_multa(monkeypatch):
    e = _exigidos(monkeypatch, '¿Qué consecuencias tiene no verificar un registrador de temperatura?')
    assert {'Ley 32/2014::art.23.1.a', 'Ley 32/2014::art.22.3.b'} <= e

def test_cada_cuanto_exige_el_computo(monkeypatch, con):
    pregunta = '¿Cada cuánto hay que verificar un registrador de temperatura?'
    e = _exigidos(monkeypatch, pregunta)
    assert not {'Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4'} & e
    computo = [o for t in completitud.cargar() for o in t.obligatorios if o.acepta[0] in ('Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4')]
    assert len(computo) == 2 and all((o.tope_modo == 'sombra' for o in computo))
    assert all((o.hoja_gatillada(completitud.normalizar(pregunta)) for o in computo))
    assert 'plazo_verificacion_temperatura' in {t.id for t in completitud.temas_de(pregunta, completitud.cargar())}
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps({'cubre_estricto': 'bloquea'})))
    completitud.faltan(con, 'Esto no cita nada de ese artículo.', pregunta)
    lineas = [json.loads(l) for l in interruptores.ruta_sombra().read_text(encoding='utf-8').splitlines()]
    anotados = {l['obligatorio']: l.get('tope') for l in lineas if l.get('obligatorio') in ('Orden ICT/155/2020::art.14.2', 'Orden ICT/155/2020::art.14.4')}
    assert anotados == {'Orden ICT/155/2020::art.14.2': 'sombra', 'Orden ICT/155/2020::art.14.4': 'sombra'}

@pytest.mark.parametrize('pregunta', ['La furgoneta de reparto lleva un registrador de temperatura verificado. ¿Cumple?', 'El repartidor lleva el registrador en la cabina. ¿Qué instrumento hay que verificar?', 'Vamos a repartir los registradores entre los almacenes. ¿Cada uno necesita su verificación?'])
def test_reparto_no_dispara_el_tema_reparacion(pregunta):
    ids = {t.id for t in completitud.temas_de(pregunta, completitud.cargar())}
    assert 'reparacion_instrumentos' not in ids

def test_reparar_sigue_disparando_el_tema_reparacion():
    ids = {t.id for t in completitud.temas_de('Hay que reparar el registrador averiado: ¿qué pasa con su verificación?', completitud.cargar())}
    assert 'reparacion_instrumentos' in ids
