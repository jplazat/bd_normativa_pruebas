"""Public CI documentation."""
from __future__ import annotations
import copy
import itertools
import json
from pathlib import Path
import re
import pytest
from ict155 import brechas, db
FIX = Path(__file__).parent / 'fixtures' / 's10q'
MARCA = 'anotar en evidencia_aportada lo que se recibió, o confirmar que no se recibió nada'
NEUTRO = 'Documento aportado: sin anotar en el registro.'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    c.execute('PRAGMA query_only=ON')
    huella = db.huella_contenido(c)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db, 'huella_contenido', lambda conexion: huella)
        yield c
    c.close()

def _registro(nombre):
    return json.loads((FIX / f'{nombre}.json').read_text(encoding='utf-8'))

def _b(**kw):
    return dict({'id': 'SYN-01', 'estado': 'abierta', 'fecha_estado': '2026-09-01', 'descripcion': 'Comprobación sintética pendiente.', 'citas': [], 'evidencia_aportada': '', 'evidencia_requerida': ''}, **kw)

def _reg(b):
    return {'brechas': [b], 'version': '0.4', 'valoracion_consultor': 'Valoración sintética.'}

def _md(con, registro, tipo='partida', **kw):
    return brechas.informe_fase2_markdown(con, registro, tipo=tipo, corte='2026-10-20', fecha_emision='2026-10-20', **kw)

def _responsable(con, registro):
    return brechas.informe_fase2_para_responsable_markdown(con, registro, corte='2026-10-20', fecha_emision='2026-10-20')
CELDAS = list(itertools.product(('nueva', 'reformulada'), (None, 'no_recibido', 'recibido_en_parte', 'recibido_con_reservas', 'recibido'), ('', 'Documento sintético recibido.'), ('', 'Expediente sintético requerido.')))

@pytest.mark.parametrize('estado,recepcion,aportada,requerida', CELDAS)
@pytest.mark.parametrize('vista', ['partida', 'intermedio', 'final', 'responsable'])
def test_h3_matriz(con, estado, recepcion, aportada, requerida, vista):
    b = _b(estado=estado, evidencia_aportada=aportada, evidencia_requerida=requerida)
    if recepcion is not None:
        b['estado_requerimiento'] = recepcion
    registro = _reg(b)
    sin_detalle = recepcion in ('recibido', 'recibido_en_parte', 'recibido_con_reservas') and (not aportada)
    if vista == 'responsable':
        texto = _responsable(con, registro)
        assert ('comprueba si de verdad se ha recibido algo antes de firmar' in texto) == sin_detalle
        assert (MARCA in texto) == sin_detalle
    elif vista == 'final' and sin_detalle:
        with pytest.raises(brechas.InformeFase2Bloqueado, match='recepción'):
            _md(con, registro, tipo=vista)
    else:
        texto = _md(con, registro, tipo=vista)
        assert ('Respuesta al requerimiento: **pendiente de confirmar**' in texto) == sin_detalle
        assert (NEUTRO in texto) == (not aportada)
        assert MARCA not in texto
        if aportada:
            assert 'Documento aportado: Documento sintético recibido.' in texto

@pytest.mark.parametrize('nombre', ['nueva_recibido_vacio', 'reformulada_recibido_vacio'])
def test_h3_casos_originales_rev22(con, nombre):
    r = _registro(nombre)
    assert 'Respuesta al requerimiento: **pendiente de confirmar**' in _md(con, r)
    assert MARCA in _responsable(con, r)
    with pytest.raises(brechas.InformeFase2Bloqueado):
        _md(con, r, 'final')

@pytest.mark.parametrize('tipo', ['partida', 'intermedio'])
def test_h5_caso_original_documentos_descritos(con, tipo):
    r = _registro('documentos_en_descripcion')
    texto = _md(con, r, tipo)
    assert 'Se aportaron tres documentos sintéticos' in texto
    assert NEUTRO in texto
    assert 'Documento aportado: (ninguno)' not in texto
    assert MARCA in _responsable(con, r)

@pytest.mark.parametrize('descripcion', ['Se recibió un certificado sintético.', 'Declaración sintética pendiente.', 'Acta sintética incompleta.', 'Tres documentos sintéticos aportados.', 'No consta el informe sintético.'])
def test_h5_heuristica_documental_marca_si_hay_duda(con, descripcion):
    r = _reg(_b(descripcion=descripcion))
    assert NEUTRO in _md(con, r)
    assert MARCA in _responsable(con, r)

def test_h5_no_infiere_recepcion_solo_por_lo_requerido(con):
    r = _reg(_b(evidencia_requerida='Documento requerido sin recepción conocida.'))
    assert NEUTRO in _md(con, r)
    assert MARCA not in _responsable(con, r)

def test_h5_no_copia_requerida_a_aportada_en_cerrada(con):
    r = _reg(_b(estado='cerrada', estado_requerimiento='recibido', evidencia_requerida='Expediente que se solicitó; no consta entregado.'))
    assert NEUTRO in _md(con, r)
    assert 'Documento aportado: Expediente que se solicitó' not in _md(con, r)
    assert MARCA in _responsable(con, r)

@pytest.mark.parametrize('vista', ['partida', 'intermedio'])
def test_h6_conclusion_efectiva_en_ficha_y_tabla(con, vista):
    r = _registro('revision_actual_omitida')
    texto = _md(con, r, vista)
    assert '- Antecedente: Faltan todas las hojas sintéticas.' in texto
    assert '- Qué falta: FALTA_SOLO_FIRMA_SINTETICA_REV22' in texto
    assert '- Qué tiene que aportar para cerrarla: FALTA_SOLO_FIRMA_SINTETICA_REV22' in texto
    fila = next((l for l in texto.splitlines() if l.startswith('| SYN-01 |')))
    assert 'FALTA_SOLO_FIRMA_SINTETICA_REV22' in fila
    assert 'Expediente sintético completo' not in fila

def test_h6_revision_sin_conclusion_no_reinventa_peticion(con):
    r = _registro('revision_actual_omitida')
    r['brechas'][0]['revisiones'][0]['que_falta'] = ''
    texto = _md(con, r)
    assert '- Qué falta: sin especificar en la revisión.' in texto
    assert '- Qué tiene que aportar para cerrarla: sin especificar en la revisión.' in texto
    assert '- Antecedente: Faltan todas las hojas sintéticas.' in texto

def test_h6_no_usa_conclusion_posterior(con):
    r = _registro('revision_actual_omitida')
    r['brechas'][0]['revisiones'].append({'numero': 2, 'fecha': '2026-10-21', 'veredicto': 'parcial', 'documento_aportado': 'POSTERIOR_NO_IMPRIMIR', 'que_falta': 'POSTERIOR_NO_IMPRIMIR'})
    texto = _md(con, r)
    assert 'FALTA_SOLO_FIRMA_SINTETICA_REV22' in texto
    assert 'POSTERIOR_NO_IMPRIMIR' not in texto

def test_h7_caso_original_campos_posteriores_no_son_vigentes(con):
    r = _registro('estado_posterior_campos')
    texto = _md(con, r)
    assert 'sin información a la fecha de corte' in texto
    assert 'CARACTERISTICA_POSTERIOR_REV22' not in texto
    assert 'PEDIDO_POSTERIOR_REV22' not in texto
    assert 'estado posterior al corte' in _responsable(con, r)

def test_h7_estado_posterior_con_revision_anterior_conserva_solo_conclusion_efectiva(con):
    r = _registro('estado_posterior_campos')
    r['brechas'][0]['revisiones'] = [{'numero': 1, 'fecha': '2026-10-18', 'veredicto': 'parcial', 'documento_aportado': 'Acta anterior sintética.', 'que_falta': 'Firma anterior sintética.'}]
    texto = _md(con, r)
    assert 'Firma anterior sintética' in texto and 'Acta anterior sintética' in texto
    assert 'CARACTERISTICA_POSTERIOR_REV22' not in texto
    assert 'PEDIDO_POSTERIOR_REV22' not in texto

def test_h7_cierre_efectivo_anterior_no_afirma_que_falta_informacion_actual(con):
    r = _registro('estado_posterior_campos')
    r['brechas'][0]['revisiones'] = [{'numero': 1, 'fecha': '2026-10-18', 'veredicto': 'cumple', 'documento_aportado': 'Acta anterior sintética.', 'que_falta': ''}]
    texto = _md(con, r)
    assert 'Situación de la carencia: **cerrada**' in texto
    assert 'Acta anterior sintética' in texto
    assert '- Qué falta:' not in texto
    assert 'CARACTERISTICA_POSTERIOR_REV22' not in texto
    assert 'PEDIDO_POSTERIOR_REV22' not in texto

def test_h7_sin_fecha_no_inventa_fecha_ni_oculta_plazo_futuro(con):
    r = _reg(_b(descripcion='El plazo sintético de planificación termina el 21/10/2026.', evidencia_requerida='Documento solicitado sin fecha registrada.'))
    del r['brechas'][0]['fecha_estado']
    texto = _md(con, r)
    assert 'El plazo sintético de planificación termina el 21/10/2026' in texto
    assert 'Documento solicitado sin fecha registrada' in texto
    assert 'sin información a la fecha de corte' not in texto

@pytest.mark.parametrize('vista', ['cliente', 'responsable'])
def test_h13_caso_original_cabecera_sin_lineas_inyectadas(con, vista):
    r = _registro('campos_saltos')
    texto = _md(con, r) if vista == 'cliente' else _responsable(con, r)
    assert not re.search('^## (CABECERA|FIRMA|NOTA) SINTÉTICA', texto, re.M)
    assert '\\#\\# CABECERA SINTÉTICA' in texto

@pytest.mark.parametrize('vista', ['cliente', 'responsable'])
def test_h13_escapa_markdown_y_html_sin_alterar_bloqueo_propuesta(con, vista):
    r = _reg(_b())
    r.update(cliente='**Cliente sintético** <b>texto</b>', informe='[Informe](https://sintetico.invalid)', version='0.4\n## propuesta')
    if vista == 'cliente':
        with pytest.raises(brechas.InformeFase2Bloqueado, match='propuesta'):
            _md(con, r)
        r['version'] = '0.4\n## nota'
        texto = _md(con, r)
    else:
        texto = _responsable(con, r)
        assert 'sigue diciendo «propuesta»' in texto
    assert '**Cliente sintético**' not in texto
    assert '<b>' not in texto
    assert '\\[Informe\\]\\(https://sintetico.invalid\\)' in texto
    assert not re.search('^## (propuesta|nota)', texto, re.M)
