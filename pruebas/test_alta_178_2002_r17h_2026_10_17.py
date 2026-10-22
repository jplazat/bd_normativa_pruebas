"""Public CI documentation."""
from __future__ import annotations
import pytest
from ict155 import caracter, catalogo, config, consulta, db
OBRA = 'CELEX-32002R0178'
RUTA = '01_Conocimiento/Fuentes_primarias/02_Legislacion_UE/DOUE_Reglamento_CE_178-2002_legislacion_alimentaria_consolidado_es.pdf'
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    if c.execute('SELECT 1 FROM obra WHERE identificador_canonico=?', (OBRA,)).fetchone() is None:
        c.close()
        pytest.skip('la base es anterior al alta del Reglamento (CE) 178/2002 (R17h)')
    yield c
    c.close()

def test_el_catalogo_lo_registra_con_sus_nombres_su_titulo_y_su_caracter():
    assert catalogo.alias_de(RUTA) == ['Reglamento (CE) 178/2002', 'Reglamento 178/2002']
    assert catalogo.titulo_oficial(OBRA).startswith('REGLAMENTO (CE) No 178/2002 DEL PARLAMENTO EUROPEO Y DEL CONSEJO de 28 de enero de 2002')
    assert caracter.TABLA[OBRA][:2] == ('vinculante', f'{OBRA}::preambulo')

def test_entra_entero_con_su_titulo_oficial_y_es_vinculante(con):
    obra = con.execute('SELECT titulo, caracter_juridico FROM obra WHERE identificador_canonico=?', (OBRA,)).fetchone()
    assert obra[0] == catalogo.titulo_oficial(OBRA) and obra[1] == 'vinculante'
    n = con.execute('SELECT count(*) FROM precepto p JOIN version v ON v.id=p.version_id JOIN documento d ON d.id=v.documento_id WHERE d.ruta_relativa=?', (RUTA,)).fetchone()[0]
    assert n >= 400, n

@pytest.mark.parametrize('nombre', ['Reglamento (CE) 178/2002', 'Reglamento 178/2002', OBRA])
def test_responde_a_sus_nombres_y_el_art_3_define_explotador_de_empresa_alimentaria(con, nombre):
    r = consulta.resolver(con, f'{nombre}::art.3')
    assert r.estado == 'ENCONTRADO' and r.obra == OBRA, (nombre, r.estado, r.obra)
    assert '3) «Explotador de empresa alimentaria» (también denominado «operador de empresa alimentaria»), las personas físicas o jurídicas responsables de asegurar el cumplimiento de los requisitos de la legislación alimentaria en la empresa alimentaria bajo su control. 4) «Pienso»' in ' '.join(r.texto_literal.split())

def test_trae_las_responsabilidades_y_la_trazabilidad(con):
    assert 'Los explotadores de empresas alimentarias y de empresas de piensos se asegurarán' in ' '.join(consulta.resolver(con, f'{OBRA}::art.17').texto_literal.split())
    assert 'deberá asegurarse la trazabilidad de los alimentos' in ' '.join(consulta.resolver(con, f'{OBRA}::art.18').texto_literal.split())
