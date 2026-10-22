"""Public CI documentation."""
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import copy
import sqlite3
import pytest
from ict155 import brechas, db
TEXTO_SINTETICO = 'alfa bravo charlie delta eco foxtrot golf hotel india julieta kilo lima mike noviembre oscar papa quebec romeo'
CLIENTE_MARKDOWN = '[x](y)\n# titulo <b>texto</b> **negrita**'
CLIENTE_ESCAPADO = '\\[x\\]\\(y\\) \\# titulo \\<b\\>texto\\</b\\> \\*\\*negrita\\*\\*'

@pytest.fixture
def con(monkeypatch, tmp_path):
    monkeypatch.setattr(brechas, '_textos_no_publicos', lambda *a: [TEXTO_SINTETICO])
    monkeypatch.setattr(brechas, '_textos_publicos_citados', lambda *a: [])
    monkeypatch.setattr(db, 'huella_contenido', lambda c: 'huella-sintetica-s11n')
    monkeypatch.setenv('ICT155_CONTROLES_FORZADOS', conservar_almacen_forzado('{"*":"apagado"}'))
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'audit'))
    with sqlite3.connect(':memory:') as c:
        c.execute('PRAGMA query_only=ON')
        yield c

def informe(con, registro, tipo):
    opciones = dict(corte='2026-10-19', fecha_emision='2026-10-19', datos_vigencia=None, avisos_de_limites=None)
    if tipo == 'responsable':
        return brechas.informe_fase2_para_responsable_markdown(con, registro, **opciones)
    return brechas.informe_fase2_markdown(con, registro, tipo=tipo, **opciones)

@pytest.mark.parametrize('tipo', ['borrador', 'partida', 'intermedio', 'final'])
@pytest.mark.parametrize('campo', ['cliente', 'version', 'informe'])
def test_marca_generada_sin_barras_y_otros_campos_inertes(con, campo, tipo):
    registro = dict(brechas=[], cliente=CLIENTE_MARKDOWN, informe=CLIENTE_MARKDOWN, version=CLIENTE_MARKDOWN, valoracion_consultor='Valoración sintética.')
    registro[campo] = TEXTO_SINTETICO
    anterior = copy.deepcopy(registro)
    md = informe(con, registro, tipo)
    assert TEXTO_SINTETICO not in md
    assert brechas.NOTA_TEXTO_LICENCIA in md
    assert '\\[texto de norma con licencia: ver la cita\\]' not in md
    assert md.count(CLIENTE_ESCAPADO) == 2
    assert '[x](y)' not in md
    assert '\n# titulo' not in md
    assert registro == anterior

@pytest.mark.parametrize('campo', ['cliente', 'informe'])
def test_marca_generada_tambien_en_cabecera_para_responsable(con, campo):
    registro = dict(brechas=[], cliente=CLIENTE_MARKDOWN, informe=CLIENTE_MARKDOWN)
    registro[campo] = TEXTO_SINTETICO
    md = informe(con, registro, 'responsable')
    assert TEXTO_SINTETICO not in md
    assert brechas.NOTA_TEXTO_LICENCIA in md
    assert '\\[texto de norma con licencia: ver la cita\\]' not in md
    assert CLIENTE_ESCAPADO in md

@pytest.mark.parametrize('texto', [CLIENTE_MARKDOWN, brechas.NOTA_TEXTO_LICENCIA + '[x](y)\n# titulo', '[x](y)\n# titulo' + brechas.NOTA_TEXTO_LICENCIA, brechas.NOTA_TEXTO_LICENCIA + '(y)', brechas.NOTA_TEXTO_LICENCIA.upper(), '\\[texto de norma con licencia: ver la cita\\]', '\\`*_{}[]()<>#+!|~'])
def test_texto_cliente_sigue_escapado_incluso_junto_a_marca(texto):
    especiales = set('\\`*_{}[]()<>#+!|~')
    esperado = ''.join((('\\' if c in especiales else '') + c for c in ' '.join(texto.split())))
    assert brechas._cabecera_fase2(texto) == esperado

def test_marca_exacta_del_sistema_se_conserva():
    assert brechas._cabecera_fase2(brechas.NOTA_TEXTO_LICENCIA) == brechas.NOTA_TEXTO_LICENCIA
