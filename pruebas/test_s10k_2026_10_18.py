"""Public CI documentation."""
from __future__ import annotations
import re
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import brechas, db
CITA_PUBLICA = 'Orden ICT/155/2020::anexo.XI/ap.5'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

def _registro():
    return {'fecha_corte': '2026-11-20', 'brechas': [{'id': 'K-01', 'estado': 'abierta', 'fecha_estado': '2026-09-01', 'citas': [{'identificador': CITA_PUBLICA, 'literal': 'será de dos años.'}], 'estado_requerimiento': 'recibido_en_parte', 'evidencia_aportada': '', 'descripcion': 'Falta la hoja de calibración del equipo de pesaje nº 3.', 'evidencia_requerida': 'Hoja de calibración vigente del equipo nº 3.', 'revisiones': []}]}

def test_resumen_sin_marca_interna_y_coherente_con_el_cuerpo(con):
    texto = brechas.informe_fase2_markdown(con, _registro(), tipo='intermedio')
    assert 'en el registro' not in texto.replace('Documento aportado: sin anotar en el registro.', '')
    resumen = texto.split('## Carencias', 1)[0]
    cuerpo = texto.split('## Carencias', 1)[1]
    assert 'pendiente de confirmar: 1' in resumen
    n_situacion = len(re.findall('- Situación de la carencia: \\*\\*', cuerpo))
    n_respuesta = len(re.findall('- Respuesta al requerimiento: \\*\\*', cuerpo))
    assert n_situacion == 1 and n_respuesta == 1
    m_situacion = re.search('Situación: (.+?)\\.', resumen)
    m_respuesta = re.search('Respuesta al requerimiento: (.+?)\\.', resumen)
    assert m_situacion is not None and m_respuesta is not None
    total_situacion = sum((int(v) for v in re.findall(': (\\d+)', m_situacion.group(1))))
    total_respuesta = sum((int(v) for v in re.findall(': (\\d+)', m_respuesta.group(1))))
    assert total_situacion == n_situacion
    assert total_respuesta == n_respuesta

def test_para_responsable_sigue_con_la_marca_completa(con):
    texto = brechas.informe_fase2_para_responsable_markdown(con, _registro())
    assert 'estado_requerimiento «recibido_en_parte» sin «evidencia_aportada» en el registro' in texto
