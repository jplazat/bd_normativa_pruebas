"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
from pathlib import Path
import pytest
from ict155 import ambito, brechas, config, consulta, db, entrega, interruptores, revision, vigencia
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')
FIX = Path(__file__).resolve().parent / 'fixtures'
HOY = '2026-10-13'
AMBITO_TXT = 'El transporte de este helado aplica el régimen de ultracongelados: `CELEX-32005R0037::art.2.3`.\n'
LIMPIO_SIN_AMBITO = 'La reparación de los registradores de temperatura la hacía una entidad inscrita: `BOE-A-1996-21021::art.16`.\n'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(scope='module')
def datos():
    return vigencia.leer_instantanea(FIX / 'vigencia_r18_2026-10-13.json')

def sello_de(con, datos, texto) -> str:
    return revision.revisar(con, texto, datos_vigencia=datos, hoy=HOY).linea()

def sellado(con, datos, texto) -> str:
    return texto.rstrip('\n') + '\n\n' + sello_de(con, datos, texto) + '\n'

@pytest.fixture
def forzar(monkeypatch, tmp_path):
    """Public CI documentation."""

    def _forzar(modo: str, **otros: str) -> Path:
        monkeypatch.setenv('ICT155_CONTROLES_FORZADOS', conservar_almacen_forzado(json.dumps({'ambito': modo, **otros})))
        monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path))
        return tmp_path
    return _forzar

def _reg(*brechas_, **kw):
    return dict({'brechas': list(brechas_)}, **kw)

def _b(bid, revisiones, citas=None):
    return {'id': bid, 'estado': 'abierta', 'fecha_estado': '2026-08-05', 'citas': citas or [], 'revisiones': revisiones}

def _rev(que_falta='', documento_aportado=''):
    return [{'numero': 1, 'fecha': '2026-10-17', 'veredicto': 'parcial', 'documento_aportado': documento_aportado, 'que_falta': que_falta, 'citas': [], 'no_aplica': []}]

def test_motivos_entrega_vacio_sin_hallazgo(con):
    assert ambito.motivos_entrega(con, LIMPIO_SIN_AMBITO, None) == []
    assert ambito.motivos_entrega(con, LIMPIO_SIN_AMBITO, '') == []

def test_motivos_entrega_lleva_el_prefijo_y_la_correccion_literal(con):
    motivos = ambito.motivos_entrega(con, AMBITO_TXT, None)
    assert len(motivos) == 1
    m = motivos[0]
    assert m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO + ':')
    assert 'CELEX-32005R0037' in m or 'Reglamento (CE) 37/2005' in m
    assert 'RD 1109/1991::art.1.2' in m
    assert 'helados' in m.lower()

def test_motivos_entrega_sin_pregunta_sigue_mirando_la_respuesta(con):
    assert len(ambito.motivos_entrega(con, AMBITO_TXT, None)) == 1
    assert len(ambito.motivos_entrega(con, AMBITO_TXT, '')) == 1
    assert len(ambito.motivos_entrega(con, AMBITO_TXT, 'una pregunta cualquiera, sin la palabra helado')) == 1

def test_hallazgos_veredicto_es_comprobar_sobre_el_propio_texto(con):
    assert [h.dict() for h in ambito.hallazgos_veredicto(con, AMBITO_TXT)] == [h.dict() for h in ambito.comprobar(con, AMBITO_TXT, '')]
    assert len(ambito.hallazgos_veredicto(con, AMBITO_TXT)) == 1
    assert ambito.hallazgos_veredicto(con, LIMPIO_SIN_AMBITO) == []
    assert ambito.hallazgos_veredicto(con, '') == []

def test_entrega_apagado_no_cambia_nada(con, datos, forzar):
    forzar('apagado')
    respuesta = sellado(con, datos, AMBITO_TXT)
    v_apagado = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    forzar('apagado')
    v = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    assert not any((m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO) for m in v.motivos))
    assert v.primera_linea == v_apagado.primera_linea and v.motivos == v_apagado.motivos

def test_entrega_sombra_anota_y_no_toca_el_veredicto(con, datos, forzar):
    forzar('apagado')
    respuesta = sellado(con, datos, AMBITO_TXT)
    v_apagado = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    tmp = forzar('sombra')
    v = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    assert v.veredicto == v_apagado.veredicto and v.motivos == v_apagado.motivos
    assert not any((m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO) for m in v.motivos))
    assert (tmp / 'sombra.log').exists() or any(tmp.rglob('sombra.log'))
    linea = next((l for l in (tmp / 'sombra.log').read_text(encoding='utf-8').splitlines() if l.strip()))
    entrada = json.loads(linea)
    assert entrada['control'] == 'ambito'
    assert ambito.PREFIJO_FUERA_DE_AMBITO in entrada['motivo']

def test_entrega_bloquea_anade_el_motivo_y_es_no_valida(con, datos, forzar):
    forzar('bloquea')
    respuesta = sellado(con, datos, AMBITO_TXT)
    v = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    assert v.veredicto == entrega.NO_VALIDA and (not v.valida)
    assert sum((m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO) for m in v.motivos)) == 1
    assert 'RD 1109/1991::art.1.2' in v.primera_linea

def test_entrega_bloquea_no_toca_una_respuesta_sin_disparo(con, datos, forzar):
    forzar('bloquea')
    respuesta = sellado(con, datos, LIMPIO_SIN_AMBITO)
    v = entrega.verificar(con, respuesta, datos_vigencia=datos, hoy=HOY)
    assert not any((m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO) for m in v.motivos))

def test_brechas_apagado_no_calcula_ni_cambia_citas(con, forzar):
    forzar('apagado')
    reg = _reg(_b('B-1', _rev(que_falta=AMBITO_TXT)))
    resultados = brechas.comprobar(con, reg)
    assert not any((h.tipo == 'fuera_de_ambito' for h in resultados.hallazgos))
    assert all((not c.identificador.startswith('(ambito)') for r in resultados for c in r.citas))
    texto = brechas.informe_markdown(con, reg, resultados)
    assert 'FUERA DE ÁMBITO' not in texto

def test_brechas_sombra_anota_para_mirar_sin_tocar_citas(con, forzar):
    tmp = forzar('sombra', brechas_r27='sombra')
    reg = _reg(_b('B-1', _rev(que_falta=AMBITO_TXT)))
    resultados = brechas.comprobar(con, reg)
    hallazgos_ambito = [h for h in resultados.hallazgos if h.tipo == 'fuera_de_ambito']
    assert len(hallazgos_ambito) == 1 and hallazgos_ambito[0].brecha_id == 'B-1'
    assert ambito.PREFIJO_FUERA_DE_AMBITO in hallazgos_ambito[0].mensaje
    assert all((not c.identificador.startswith('(ambito)') for r in resultados for c in r.citas))
    assert [r.nivel for r in resultados] == [brechas.AVISO]
    texto = brechas.informe_markdown(con, reg, resultados)
    assert '## PARA MIRAR (control en sombra)' in texto
    seccion = texto.split('## PARA MIRAR (control en sombra)', 1)[1]
    assert 'B-1' in seccion and ambito.PREFIJO_FUERA_DE_AMBITO in seccion
    assert (tmp / 'sombra.log').exists() or any(tmp.rglob('sombra.log'))

def test_brechas_bloquea_anade_una_cita_que_bloquea(con, forzar):
    forzar('bloquea')
    reg = _reg(_b('B-1', _rev(que_falta=AMBITO_TXT)))
    resultados = brechas.comprobar(con, reg)
    r = next((r for r in resultados if r.brecha['id'] == 'B-1'))
    nuevas = [c for c in r.citas if c.identificador.startswith('(ambito)')]
    assert len(nuevas) == 1 and nuevas[0].nivel == brechas.ERROR
    assert 'RD 1109/1991::art.1.2' in '; '.join(nuevas[0].detalle)
    assert r.nivel == brechas.ERROR

def test_brechas_sin_texto_en_la_revision_no_dispara(con, forzar):
    for modo in ('sombra', 'bloquea'):
        forzar(modo)
        reg = _reg(_b('B-1', _rev(que_falta='', documento_aportado='')))
        resultados = brechas.comprobar(con, reg)
        assert not any((h.tipo == 'fuera_de_ambito' for h in resultados.hallazgos))
        assert all((not c.identificador.startswith('(ambito)') for r in resultados for c in r.citas))

def test_brechas_sin_ninguna_revision_no_dispara(con, forzar):
    forzar('bloquea')
    reg = _reg(_b('B-1', []))
    resultados = brechas.comprobar(con, reg)
    assert not any((h.tipo == 'fuera_de_ambito' for h in resultados.hallazgos))
