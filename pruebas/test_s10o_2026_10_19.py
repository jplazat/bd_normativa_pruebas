"""Public CI documentation."""
from __future__ import annotations
import pytest
from ict155 import brechas, db
pytestmark = pytest.mark.skipif(not __import__('ict155.config', fromlist=['BD']).BD.exists(), reason='hace falta una base')
CITA_PUBLICA = 'Orden ICT/155/2020::anexo.XI/ap.5'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

def _b(bid, citas=(), estado='abierta', **kw):
    return dict({'id': bid, 'estado': estado, 'fecha_estado': '2026-08-05', 'citas': list(citas)}, **kw)

def _reg(*brechas_, **kw):
    return dict({'brechas': list(brechas_)}, **kw)

def _md(con, reg, **kw):
    kw.setdefault('tipo', 'intermedio')
    kw.setdefault('corte', '2026-10-20')
    kw.setdefault('fecha_emision', '2026-10-18')
    return brechas.informe_fase2_markdown(con, reg, **kw)

def _reg_a():
    """Public CI documentation."""
    return _reg(_b('C-S10o-A', [{'identificador': CITA_PUBLICA}], estado='cerrada', descripcion='Comprobación sintética completada.', evidencia_requerida='Certificado sintético.', estado_requerimiento='no_recibido', evidencia_aportada='Acta sintética recibida.'))

@pytest.mark.parametrize('tipo', ['partida', 'intermedio'])
def test_a_respuesta_al_requerimiento_pendiente_de_confirmar(con, tipo):
    texto = _md(con, _reg_a(), tipo=tipo)
    assert 'Documento aportado: Acta sintética recibida.' in texto
    assert 'Respuesta al requerimiento: **pendiente de confirmar**' in texto
    assert 'pendiente: no recibido' not in texto

@pytest.mark.parametrize('tipo', ['partida', 'intermedio'])
def test_a_situacion_sigue_cerrada_en_la_fase_1(con, tipo):
    """Public CI documentation."""
    texto = _md(con, _reg_a(), tipo=tipo)
    assert 'Situación de la carencia: **cerrada en la fase 1**' in texto

def test_a_el_final_se_niega(con):
    with pytest.raises(brechas.InformeFase2Bloqueado, match='recepción'):
        _md(con, _reg_a(), tipo='final')

def test_a_para_responsable_marca_la_contradiccion(con):
    responsable = brechas.informe_fase2_para_responsable_markdown(con, _reg_a(), corte='2026-10-20', fecha_emision='2026-10-18')
    assert 'C-S10o-A' in responsable
    assert 'no_recibido' in responsable
    assert 'evidencia_aportada' in responsable

def test_a_una_abierta_no_recibido_con_evidencia_sigue_igual(con):
    """Public CI documentation."""
    reg = _reg(_b('C-S10o-A-abierta', [{'identificador': CITA_PUBLICA}], estado_requerimiento='no_recibido', evidencia_aportada='Acta sintética recibida.'))
    texto = _md(con, reg, tipo='intermedio')
    assert 'Respuesta al requerimiento: **pendiente de confirmar**' in texto

def _reg_b():
    """Public CI documentation."""
    return _reg(_b('C-S10o-B', [{'identificador': CITA_PUBLICA}], estado='cerrada', descripcion='Comprobación sintética completada.', evidencia_requerida='Hoja sintética completa.', estado_requerimiento='recibido_en_parte', evidencia_aportada='Hoja sintética 1 de 3.'))

@pytest.mark.parametrize('tipo', ['partida', 'intermedio'])
def test_b_al_cliente_sin_cambios(con, tipo):
    """Public CI documentation."""
    texto = _md(con, _reg_b(), tipo=tipo)
    assert 'Documento aportado: Hoja sintética 1 de 3.' in texto
    assert 'Respuesta al requerimiento: **recibido en parte**' in texto

def test_b_no_bloquea_la_partida(con):
    _md(con, _reg_b(), tipo='partida')

def test_b_bloquea_el_final(con):
    with pytest.raises(brechas.InformeFase2Bloqueado, match='recepción parcial'):
        _md(con, _reg_b(), tipo='final')

def test_b_para_responsable_marca_la_recepcion_parcial(con):
    responsable = brechas.informe_fase2_para_responsable_markdown(con, _reg_b(), corte='2026-10-20', fecha_emision='2026-10-18')
    assert 'C-S10o-B' in responsable
    assert 'cerrada con recepción parcial' in responsable
    assert 'confirmar que el cierre no depende de lo que falta' in responsable

def test_b_una_abierta_recibido_en_parte_no_lleva_esta_marca_nueva(con):
    """Public CI documentation."""
    reg = _reg(_b('C-S10o-B-abierta', [{'identificador': CITA_PUBLICA}], estado_requerimiento='recibido_en_parte', evidencia_aportada='Hoja sintética 1 de 3.'))
    responsable = brechas.informe_fase2_para_responsable_markdown(con, reg, corte='2026-10-20', fecha_emision='2026-10-18')
    assert 'cerrada con recepción parcial' not in responsable
