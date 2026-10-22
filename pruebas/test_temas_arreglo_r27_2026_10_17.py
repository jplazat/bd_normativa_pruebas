"""Public CI documentation."""
from __future__ import annotations
import pytest
from ict155 import completitud, config
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')

def ids(detectados) -> set[str]:
    return {t.id for t in detectados}

@pytest.fixture(scope='module')
def temas_reales():
    return completitud.cargar()
F02 = 'Ensayo con arreglo a la Directiva 2014/32/UE para un instrumento ficticio.'
P1 = 'Un instrumento ficticio se repara y precinta: se estudia la verificacion despues de reparacion.'

def test_f02_con_arreglo_a_la_directiva_no_dispara_reparacion(temas_reales):
    """Public CI documentation."""
    assert 'reparacion_instrumentos' not in ids(completitud.temas_de(F02, temas_reales))

def test_p1_del_17_oct_sigue_disparando_reparacion(temas_reales):
    """Public CI documentation."""
    assert 'reparacion_instrumentos' in ids(completitud.temas_de(P1, temas_reales))

@pytest.mark.parametrize('pregunta', ['El técnico tiene que arreglar la báscula del mostrador antes de que vuelva a pesar.', 'Se ha hecho un arreglo de la sonda del registrador tras la avería.', 'El fabricante y el titular lo arreglaron entre los dos: el contador volvió a funcionar.'])
def test_arreglo_real_sigue_disparando_reparacion(temas_reales, pregunta):
    assert 'reparacion_instrumentos' in ids(completitud.temas_de(pregunta, temas_reales))

@pytest.mark.parametrize('pregunta', ['El contrato de mantenimiento del registrador se revisa con arreglo a la Directiva de servicios.', 'La verificación del contador se hizo de arreglo a lo dispuesto en la Orden ICT/155/2020.', 'El balanza quedó homologada con arreglo al Reglamento (UE) 2019/1020.'])
def test_formulas_con_arreglo_a_no_disparan_reparacion(temas_reales, pregunta):
    assert 'reparacion_instrumentos' not in ids(completitud.temas_de(pregunta, temas_reales))

@pytest.mark.parametrize('pregunta', ['El técnico hizo un arreglo al contador averiado y ya vuelve a funcionar. ¿Hace falta verificarlo?', 'Le hicimos un arreglo a la báscula de mostrador tras la avería del plato.', 'El fabricante hizo un arreglo al registrador de temperatura para que deje de dar error.'])
def test_arreglo_a_un_instrumento_sigue_disparando_reparacion(temas_reales, pregunta):
    """Public CI documentation."""
    assert 'reparacion_instrumentos' in ids(completitud.temas_de(pregunta, temas_reales))
