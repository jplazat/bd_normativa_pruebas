"""Public CI documentation."""
from __future__ import annotations
import collections
import sys
from pathlib import Path
import pytest
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'pruebas'))
from ict155 import catalogo, consulta, db
from ict155.consulta import norm_alias
PREFIJO = 'ICT155-DOC-'
COMPARTIDOS = {'welmec guide 7 2', 'welmec 7 2'}
REPETIDOS_ANTIGUOS = {'DOUE_Reglamento_CE_37-2005_temperaturas_ultracongelados_CONSOLIDADO_es.pdf', 'DOUE_Decision_768-2008-CE_marco_comun_comercializacion_modulos_es.pdf', 'DOUE_2013-C343-01_Directrices_GDP_distribucion_medicamentos_es.pdf', 'NORMA_PAGO_15.pdf', 'NORMA_PAGO_52.pdf', 'NORMA_PAGO_65_EXTRACTO.pdf'}

def _ident(fichero: str) -> str:
    return PREFIJO + fichero.rsplit('.', 1)[0]

@pytest.fixture(scope='module')
def con_catalogo(tmp_path_factory):
    from soporte_revision_2026_10_01_tanda3 import _base
    obras = [dict(ident=_ident(f), titulo=f, alias=list(a), versiones=[dict(etiqueta='v', fecha_edicion=None, preceptos={'art.1': 'x'})]) for f, a in catalogo.ALIAS.items()]
    ruta = _base(tmp_path_factory.mktemp('catalogo') / 'c.sqlite', obras)
    return db.conectar(ruta, solo_lectura=True)

def _resuelve(con, nombre):
    return sorted((o['identificador_canonico'][len(PREFIJO):] for o in consulta._obra_por_alias(con, nombre)))

def test_ningun_alias_normalizado_designa_dos_obras_del_catalogo():
    por = collections.defaultdict(set)
    for f, alias in catalogo.ALIAS.items():
        for a in [*alias, _ident(f)]:
            por[norm_alias(a)].add(f)
    choques = {k: sorted(v) for k, v in por.items() if len(v) > 1 and k not in COMPARTIDOS}
    assert not choques, choques

def test_cada_alias_del_catalogo_lleva_solo_a_su_obra(con_catalogo):
    fallos = []
    for f, alias in catalogo.ALIAS.items():
        propias = {f.rsplit('.', 1)[0]}
        for a in alias:
            hallado = set(_resuelve(con_catalogo, a))
            if f.startswith('NORMA_PAGO_') and norm_alias(a) in COMPARTIDOS:
                continue
            if hallado != propias:
                fallos.append(f'{a!r} -> {sorted(hallado)} (esperado {sorted(propias)})')
    assert not fallos, '\n'.join(fallos)

def test_los_alias_de_una_obra_no_se_repiten_al_normalizar():
    malos = []
    for f, alias in catalogo.ALIAS.items():
        if f in REPETIDOS_ANTIGUOS:
            continue
        c = collections.Counter((norm_alias(a) for a in alias))
        malos += [f'{f}: {k!r}' for k, v in c.items() if v > 1]
    assert not malos, malos

@pytest.mark.parametrize('nombre,obra', [('GUM', 'NORMA_PAGO_10'), ('VIM', 'NORMA_PAGO_14'), ('VIML', 'NORMA_PAGO_62'), ('Anexo 11 de EudraLex Volumen 4', 'NORMA_PAGO_23'), ('Anexo 11', 'NORMA_PAGO_23'), ('Annex 11', 'NORMA_PAGO_25')])
def test_gum_vim_y_anexo_11_solo_casan_con_su_obra(con_catalogo, nombre, obra):
    assert _resuelve(con_catalogo, nombre) == [obra]

@pytest.mark.parametrize('nombre,obra', [('EA-2/17', 'NORMA_PAGO_15'), ('EA-2/17 M', 'NORMA_PAGO_15'), ('EA-2/17 S1', 'NORMA_PAGO_16'), ('EA-2/17 S1:2026', 'NORMA_PAGO_16'), ('EA-2/17 S2', 'NORMA_PAGO_17'), ('EA-2/17 S3', 'NORMA_PAGO_18'), ('WELMEC Guide 8.1', 'NORMA_PAGO_73'), ('WELMEC 8.10', 'NORMA_PAGO_72'), ('WELMEC Guide 8.2', 'NORMA_PAGO_75'), ('WELMEC 8.21', 'NORMA_PAGO_74'), ('OIML D 1', 'NORMA_PAGO_60'), ('OIML V1:2022', 'NORMA_PAGO_62'), ('EURAMET cg-8 v3.1', 'NORMA_PAGO_48'), ('ILAC-P14:09/2020', 'NORMA_PAGO_53'), ('ILAC-G24:2022', 'NORMA_PAGO_50'), ('EA-4/02 M:2022', 'NORMA_PAGO_19'), ('JCGM 100:2008', 'NORMA_PAGO_10'), ('JCGM 101:2008', 'NORMA_PAGO_11'), ('JCGM 200:2012', 'NORMA_PAGO_14'), ('JCGM 100:2008/Amd 1:2026', 'NORMA_PAGO_59'), ('Guía CEM C-04', 'NORMA_PAGO_08'), ('Guía del CEM C-05', 'NORMA_PAGO_09')])
def test_cada_nombre_citado_lleva_a_su_obra_y_a_ninguna_otra(con_catalogo, nombre, obra):
    assert _resuelve(con_catalogo, nombre) == [obra]

@pytest.mark.parametrize('nombre', ['WELMEC 8', 'WELMEC Guide 8', 'OIML D 11', 'OIML V 11', 'EURAMET cg-1', 'EURAMET cg-2', 'JCGM 10', 'JCGM 1000', 'EA-4/0', 'ILAC G2', 'ILAC P1', 'Guía CEM C-0'])
def test_un_numero_recortado_no_alcanza_ninguna_obra(con_catalogo, nombre):
    assert _resuelve(con_catalogo, nombre) == [], nombre

def test_la_enmienda_del_gum_no_la_alcanza_la_cita_del_gum_a_secas(con_catalogo):
    assert 'NORMA_PAGO_59' not in _resuelve(con_catalogo, 'JCGM 100:2008')
    assert 'NORMA_PAGO_59' not in _resuelve(con_catalogo, 'GUM')
NO_CITABLES = ['BOE_RD188-2016_equipos_radioelectricos_texto_original_2016_NO_CONSOLIDADO.pdf', 'DOUE_Directiva_2014-53-UE_RED_texto_original_2014_en.pdf', 'DOUE_Reglamento_CE_765-2008_texto_original_2008_NO_CITAR_arts15-29_SUPRIMIDOS_es.pdf', 'NORMA_PAGO_27_PARCIAL.pdf', 'DOUE_Reglamento_CE_37-2005_temperaturas_ultracongelados_es.pdf', 'DOUE_Reglamento_CE_37-2005_temperaturas_ultracongelados_en.pdf', 'NORMA_PAGO_05.pdf', 'NORMA_PAGO_13.pdf', 'NORMA_PAGO_03.pdf']

@pytest.mark.parametrize('fichero', NO_CITABLES)
def test_las_no_citables_no_llevan_alias(fichero):
    assert not catalogo.ALIAS.get(fichero), fichero

def test_la_c01_de_2020_no_le_quita_el_nombre_a_la_rev_1(con_catalogo):
    assert _resuelve(con_catalogo, 'Guía CEM C-01') == ['NORMA_PAGO_06']
CITABLES_CON_ALIAS = ['NORMA_PAGO_11.pdf', 'NORMA_PAGO_10.pdf', 'NORMA_PAGO_14.pdf', 'NORMA_PAGO_12.pdf', 'NORMA_PAGO_68.pdf', 'NORMA_PAGO_71.pdf', 'NORMA_PAGO_73.pdf', 'NORMA_PAGO_75.pdf', 'NORMA_PAGO_76.pdf', 'NORMA_PAGO_77.pdf', 'NORMA_PAGO_78.pdf', 'NORMA_PAGO_79.pdf', 'NORMA_PAGO_80.pdf', 'NORMA_PAGO_72.pdf', 'NORMA_PAGO_74.pdf', 'NORMA_PAGO_60.pdf', 'NORMA_PAGO_62.pdf', 'NORMA_PAGO_48.pdf', 'NORMA_PAGO_45.pdf', 'NORMA_PAGO_46.pdf', 'NORMA_PAGO_47.pdf', 'NORMA_PAGO_50.pdf', 'NORMA_PAGO_51.pdf', 'NORMA_PAGO_53.pdf', 'NORMA_PAGO_19.pdf', 'NORMA_PAGO_16.pdf', 'NORMA_PAGO_17.pdf', 'NORMA_PAGO_18.pdf', 'NORMA_PAGO_08.pdf', 'NORMA_PAGO_09.pdf', 'NORMA_PAGO_04.pdf', 'NORMA_PAGO_25.pdf', 'DOUE_2013-C343-01_Directrices_GDP_distribucion_medicamentos_en.pdf', 'NORMA_PAGO_59.pdf']

def test_son_34_las_citables_con_alias_nuevo():
    assert len(CITABLES_CON_ALIAS) == len(set(CITABLES_CON_ALIAS)) == 34
    for f in CITABLES_CON_ALIAS:
        assert catalogo.ALIAS.get(f), f
