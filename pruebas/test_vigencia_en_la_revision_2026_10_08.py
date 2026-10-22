"""Public CI documentation."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest
from ict155 import config, db, revision, vigencia
RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location('servidor_mcp_vig', RAIZ / 'cowork' / 'servidor_mcp.py')
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)
HOY = '2026-10-08'

def _datos(**obras):
    return {'consultado': '2026-10-08T10:00:00Z', 'fuentes': {'BOE': vigencia.AVISO_BOE, 'CELLAR': vigencia.AVISO_CELLAR}, 'obras': obras}

def _obra(oficial, estado='vigente', fuente='CELLAR', version='2015-01-27', mods=(), **consulta):
    return {'identificador_oficial': oficial, 'fecha_version': version, 'consulta': {'fuente': fuente, 'estado': estado, **consulta}, 'modificaciones_posteriores': list(mods)}
MID_MODIFICADA = _obra('32014L0032', mods=[{'id': '32026L0706', 'titulo': 'Directiva (UE) 2026/706', 'fecha_comparada': '2026-04-09', 'en_la_base': False}])

def test_una_guia_no_tiene_vigencia():
    assert vigencia.vigencia_de('ICT155-DOC-NORMA_PAGO_14', _datos()) is None

def test_sin_consulta_guardada_se_dice_que_no_se_sabe():
    v = vigencia.vigencia_de('CELEX-32014L0032', None, hoy=HOY)
    assert v['estado'] is None and 'no hay consulta de vigencia' in v['avisos'][0]

def test_modificada_despues_de_la_version_de_la_base_y_que_la_base_no_tiene():
    v = vigencia.vigencia_de('CELEX-32014L0032', _datos(**{'CELEX-32014L0032': MID_MODIFICADA}), hoy=HOY)
    assert len(v['avisos']) == 1
    assert v['avisos'][0].startswith('MODIFICADA después de la versión de la base (2015-01-27): 32026L0706')
    assert v['avisos'][0].endswith('que la base NO tiene')

def test_si_el_acto_modificativo_esta_en_la_base_se_dice_donde():
    """Public CI documentation."""
    mid = _obra('32014L0032', mods=[dict(MID_MODIFICADA['modificaciones_posteriores'][0], en_la_base=True, obra_en_la_base='DOUE-2026-706')])
    v = vigencia.vigencia_de('CELEX-32014L0032', _datos(**{'CELEX-32014L0032': mid}), hoy=HOY)
    assert len(v['avisos']) == 1 and v['avisos'][0].startswith('MODIFICADA después de la versión de la base')
    assert v['avisos'][0].endswith('su texto está en la base como DOUE-2026-706')
    assert 'NO tiene' not in v['avisos'][0]

def test_derogada_futura_dudosa_y_consulta_vieja():
    o = _obra('BOE-A-1996-21021', estado='derogada', fuente='BOE', version='1996-09-02', fecha_derogacion='2006-12-07', derogada_por=[{'id': 'BOE-A-2006-21277', 'texto': 'por Orden ITC/3701/2006'}], mods=[{'id': 'X1', 'fecha_comparada': '2027-08-13', 'futura': True, 'en_la_base': False}, {'id': 'X2', 'fecha_comparada': None, 'fecha_desconocida': True, 'en_la_base': True}])
    v = vigencia.vigencia_de('BOE-A-1996-21021', _datos(**{'BOE-A-1996-21021': o}), hoy='2026-12-01')
    texto = ' | '.join(v['avisos'])
    assert 'DEROGADA el 2006-12-07 por BOE-A-2006-21277' in texto
    assert 'aún no ha entrado en vigor: X1' in texto
    assert 'posible modificación posterior' in texto and 'X2' in texto
    assert 'la consulta de vigencia tiene 54 días' in texto

def test_una_version_de_la_que_solo_se_sabe_el_anio_no_se_da_como_fecha_exacta():
    o = _obra('BOE-A-2016-4444', fuente='BOE', version='2016-01-01', mods=[{'id': 'BOE-A-2021-9722', 'texto': 'por Real Decreto', 'fecha_comparada': '2021-06-11', 'en_la_base': False}])
    o['fecha_version_aproximada'] = True
    v = vigencia.vigencia_de('BOE-A-2016-4444', _datos(**{'BOE-A-2016-4444': o}), hoy=HOY)
    assert v['fecha_version_base'] == 'edición de 2016'
    assert 'versión de la base (edición de 2016)' in v['avisos'][0]

def test_al_dia_no_lleva_avisos_y_el_texto_lo_dice():
    v = vigencia.vigencia_de('BOE-A-2016-5530', _datos(**{'BOE-A-2016-5530': _obra('BOE-A-2016-5530', fuente='BOE', version='2025-04-12')}), hoy=HOY)
    assert v['avisos'] == []
    assert 'Sin modificaciones posteriores a la versión de la base' in vigencia.texto(v)

def test_el_servidor_pinta_la_vigencia_igual_que_la_base():
    for v in (vigencia.vigencia_de('CELEX-32014L0032', _datos(**{'CELEX-32014L0032': MID_MODIFICADA}), hoy=HOY), vigencia.vigencia_de('CELEX-32014L0032', None, hoy=HOY), None):
        assert srv._texto_vigencia(v) == vigencia.texto(v)

def test_la_herramienta_de_vigencia_nunca_actualiza():
    assert srv.argumentos_de_la_orden('normativa_vigencia', {}) == ['vigencia', '--json']
    assert srv.argumentos_de_la_orden('normativa_vigencia', {'obra': 'MID'}) == ['vigencia', '--json', '--', 'MID']
    args = srv.argumentos_de_la_orden('normativa_vigencia', {'obra': '--actualizar'})
    assert args == ['vigencia', '--json', '--', '--actualizar']
    from ict155 import cli
    leidos = {}
    real = cli.cmd_vigencia
    try:
        cli.cmd_vigencia = lambda a: leidos.update(actualizar=a.actualizar, obra=a.obra) or 0
        cli.main(args)
    finally:
        cli.cmd_vigencia = real
    assert leidos == {'actualizar': False, 'obra': '--actualizar'}

def test_la_cita_lleva_el_bloque_de_vigencia_antes_del_contexto():
    import json
    d = {'estado': 'ENCONTRADO', 'identificador': 'MID::art.4', 'texto_literal': 'texto', 'obra': 'CELEX-32014L0032', 'vigencia': vigencia.vigencia_de('CELEX-32014L0032', _datos(**{'CELEX-32014L0032': MID_MODIFICADA}), hoy=HOY), 'contexto': {'precepto': 'MID::art.4', 'ambito': [{'identificador': 'MID::art.2', 'etiqueta': 'Artículo 2', 'paginas': '3', 'texto': 'ámbito'}]}}
    ok, texto, estado = srv.formatear('normativa_cita', ['cita', 'MID::art.4', '--json'], json.dumps(d), {})
    assert ok and estado == 'ENCONTRADO'
    assert texto.index('──── VIGENCIA') < texto.index('──── CONTEXTO OBLIGATORIO')
    assert '32026L0706' in texto

@pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')
def test_la_revision_avisa_de_la_vigencia_de_cada_norma_citada(monkeypatch):
    monkeypatch.setattr(vigencia, 'instantanea_actual', lambda ruta=None: _datos(**{'CELEX-32014L0032': MID_MODIFICADA}))
    con = db.conectar(solo_lectura=True)
    inf = revision.revisar(con, 'Según la MID, «los Estados miembros» (`MID::art.4`).\n')
    vig = [c for c in inf.comprobaciones if c.tipo == 'vigencia']
    assert len(vig) == 1 and vig[0].nivel == revision.AVISO and (vig[0].linea == 1)
    assert '32026L0706' in vig[0].detalle and 'Dilo en la respuesta' in vig[0].detalle
