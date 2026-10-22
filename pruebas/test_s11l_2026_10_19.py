"""Public CI documentation."""
from __future__ import annotations
import copy
import itertools
import json
import re
import shutil
import sys
from pathlib import Path
import pytest
RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'herramientas' / 'fase2')]
from ict155 import brechas, db
import generar_carpeta as gc
REV23 = Path('D:\\Proyectos\\r27\\tmp\\rev23')
CORTE = '2026-10-20'

@pytest.fixture(scope='module')
def con(tmp_path_factory):
    c = db.crear(tmp_path_factory.mktemp('base_s11l') / 'sintetica.sqlite')
    c.execute('PRAGMA query_only=ON')
    yield c
    c.close()

@pytest.fixture
def registros(tmp_path):
    resultado = {}
    for nombre in ('revision_actual_omitida', 'estado_posterior_campos', 'corte_registro'):
        copia = tmp_path / f'{nombre}.json'
        shutil.copy2(REV23 / copia.name, copia)
        registro = brechas.leer_registro(copia)
        for b in registro['brechas']:
            b['citas'] = []
        resultado[nombre] = registro
    return resultado

def _campo_informe(ficha, etiqueta):
    coincidencia = re.search(f'^- {re.escape(etiqueta)}: (.*)$', ficha, re.M)
    return coincidencia.group(1) if coincidencia else None

def _apartado_leeme(leeme, titulo):
    coincidencia = re.search(f'^## {re.escape(titulo)}\\n\\n(.*?)(?=^## |\\Z)', leeme, re.M | re.S)
    return coincidencia.group(1).strip() if coincidencia else None

def _descripcion_leeme(leeme):
    """Public CI documentation."""
    parrafos = leeme.split('## Qué hay que aportar', 1)[0].strip().split('\n\n')[2:]
    return '\n\n'.join((p for p in parrafos if not p.startswith('Antecedente:'))).strip()

def _concordancia(con, registro, destino, *, corte=CORTE, fecha=CORTE):
    informe = brechas.informe_fase2_markdown(con, registro, tipo='partida', corte=corte, fecha_emision=fecha, datos_vigencia=None, avisos_de_limites=[])
    res = gc.generar(con, registro, destino, corte=corte, fecha=fecha)
    for b in registro['brechas']:
        ficha = re.search(f"^### {re.escape(b['id'])}(?: ·[^\\n]*)?\\n(.*?)(?=^### |^## |\\Z)", informe, re.M | re.S).group(1)
        situacion = re.search('Situación de la carencia: \\*\\*(.*?)\\*\\*', ficha).group(1)
        if situacion in ('cerrada', 'cerrada en la fase 1'):
            assert b['id'] in res.cerradas
            continue
        nombre = next((n for n in res.subcarpetas if n == b['id'] or n.startswith(b['id'] + ' -')))
        leeme = (destino / nombre / 'LEEME.md').read_text(encoding='utf-8')
        assert f'Estado: **{situacion}**' in leeme
        que_falta = _apartado_leeme(leeme, 'Qué falta') or _descripcion_leeme(leeme)
        assert que_falta == _campo_informe(ficha, 'Qué falta')
        assert _apartado_leeme(leeme, 'Qué hay que aportar') == _campo_informe(ficha, 'Qué tiene que aportar para cerrarla')
        antecedente = _campo_informe(ficha, 'Antecedente')
        if antecedente:
            assert f'Antecedente: {antecedente}' in leeme
        else:
            assert 'Antecedente:' not in leeme
    return (res, informe)

@pytest.mark.parametrize('nombre', ['revision_actual_omitida', 'estado_posterior_campos'])
def test_casos_rev23_concordancia_leeme_igual_informe(con, registros, tmp_path, nombre):
    _concordancia(con, registros[nombre], tmp_path / 'cliente')
CELDAS = list(itertools.product(('abierta', 'cerrada', 'reformulada', 'nueva'), ('no_cumple', 'parcial', 'pendiente', 'cumple'), ('anterior', 'solo_posterior', 'antes_y_despues')))

@pytest.mark.parametrize('estado,veredicto,historia', CELDAS)
def test_matriz_concordancia_por_cada_carencia(con, registros, tmp_path, estado, veredicto, historia):
    registro = copy.deepcopy(registros['revision_actual_omitida'])
    b = registro['brechas'][0]
    b['estado'] = estado
    b['revisiones'][0]['veredicto'] = veredicto
    if historia == 'solo_posterior':
        b['fecha_estado'] = '2026-10-21'
        b['revisiones'][0]['fecha'] = '2026-10-21'
    elif historia == 'antes_y_despues':
        b['revisiones'].append(dict(numero=2, fecha='2026-10-21', veredicto='cumple', documento_aportado='Documento posterior sintético.', que_falta=''))
    _concordancia(con, registro, tmp_path / 'cliente')

@pytest.mark.parametrize('con_revision', [False, True])
def test_n2_no_filtra_datos_posteriores_por_nombre_indice_ni_plantillas(con, registros, tmp_path, con_revision):
    registro = registros['estado_posterior_campos']
    b = registro['brechas'][0]
    b['titulo'] = 'TITULO_POSTERIOR_S11L'
    if con_revision:
        b['revisiones'] = [dict(numero=1, fecha='2026-10-18', veredicto='parcial', documento_aportado='Hojas sintéticas anteriores.', que_falta='FIRMA_ANTERIOR_S11L')]
    destino = tmp_path / 'cliente'
    _concordancia(con, registro, destino)
    for ruta in destino.rglob('*'):
        assert 'TITULO_POSTERIOR_S11L' not in ruta.name
        if not ruta.is_file():
            continue
        if ruta.suffix == '.xlsx':
            from openpyxl import load_workbook
            wb = load_workbook(ruta)
            texto = '\n'.join((str(c.value) for ws in wb for fila in ws for c in fila if c.value is not None))
            wb.close()
        else:
            texto = ruta.read_text(encoding='utf-8-sig')
        for marca in ('TITULO_POSTERIOR_S11L', 'CARACTERISTICA_POSTERIOR_REV22', 'PEDIDO_POSTERIOR_REV22'):
            assert marca not in texto

@pytest.mark.parametrize('conclusion', ['', '   ', 'Firma sintética.\nSolo falta validarla.'])
def test_revision_efectiva_sin_resucitar_peticion_superada(con, registros, tmp_path, conclusion):
    registro = registros['revision_actual_omitida']
    registro['brechas'][0]['revisiones'][0]['que_falta'] = conclusion
    _concordancia(con, registro, tmp_path / 'cliente')

def test_corte_omitido_usa_fecha_corte_del_registro(con, registros, tmp_path):
    res, _ = _concordancia(con, registros['corte_registro'], tmp_path / 'cliente', corte=None)
    assert not res.cerradas and len(res.subcarpetas) == 1

def test_corte_explicito_prevalece_sobre_registro(con, registros, tmp_path):
    res, _ = _concordancia(con, registros['corte_registro'], tmp_path / 'cliente')
    assert res.cerradas and (not res.subcarpetas)

@pytest.mark.parametrize('descripcion', ['', 'Descripción sintética vigente.'])
@pytest.mark.parametrize('requerida', ['', 'Documento sintético vigente.'])
def test_sin_revision_concordancia_y_redaccion_neutra(con, registros, tmp_path, descripcion, requerida):
    registro = registros['revision_actual_omitida']
    b = registro['brechas'][0]
    b.update(revisiones=[], descripcion=descripcion, evidencia_requerida=requerida)
    _concordancia(con, registro, tmp_path / 'cliente')

def test_concordancia_de_varias_fichas_no_mezcla_sus_instrucciones(con, registros, tmp_path):
    registro = copy.deepcopy(registros['revision_actual_omitida'])
    posterior = copy.deepcopy(registros['estado_posterior_campos']['brechas'][0])
    posterior['id'] = 'POST-02'
    inicial = copy.deepcopy(registro['brechas'][0])
    inicial.update(id='INI-03', revisiones=[], descripcion='Descripción inicial sintética vigente.', evidencia_requerida='Petición inicial sintética vigente.')
    cerrada = copy.deepcopy(inicial)
    cerrada.update(id='CER-04', estado='cerrada')
    registro['brechas'].extend([posterior, inicial, cerrada])
    res, _ = _concordancia(con, registro, tmp_path / 'cliente')
    assert len(res.subcarpetas) == 3 and res.cerradas == ['CER-04']
