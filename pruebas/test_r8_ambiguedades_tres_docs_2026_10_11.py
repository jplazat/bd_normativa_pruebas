"""Public CI documentation."""
import pytest
from ict155 import caracter, catalogo, contexto

def test_rx_pegada_norma_variantes():
    texto_gdp = 'de las Directrices GDP 2013/C 343/01'
    m = contexto.RX_PEGADA_NORMA.match(texto_gdp)
    assert m is not None
    assert texto_gdp[m.end():] == 'Directrices GDP 2013/C 343/01'
    texto_en = 'de la norma EN 12830:2018'
    m2 = contexto.RX_PEGADA_NORMA.match(texto_en)
    assert m2 is not None
    assert texto_en[m2.end():] == 'EN 12830:2018'
    texto_reg = 'del Reglamento (UE) 2016/425'
    m3 = contexto.RX_PEGADA_NORMA.match(texto_reg)
    assert m3 is not None
    assert texto_reg[m3.end():] == 'Reglamento (UE) 2016/425'
    assert contexto.RE_NORMA.match(texto_reg[m3.end():]) is not None

def test_re_norma_rdl_y_rd():
    assert contexto.RE_NORMA.search('según el Real Decreto Legislativo 1/2007 de 16 de noviembre')
    assert contexto.RE_NORMA.search('conforme al RDL 1/2007')
    assert contexto.RE_NORMA.search('según el Real Decreto 1468/1988 de 2 de diciembre')
    assert contexto.RE_NORMA.search('conforme al RD 1468/1988')

def test_catalogo_alias_tres_docs_nuevos():
    f_rdl = 'BOE_RDL1-2007_Consumidores_y_Usuarios_consolidado.pdf'
    assert f_rdl in catalogo.ALIAS
    assert 'RDL 1/2007' in catalogo.ALIAS[f_rdl]
    assert 'Real Decreto Legislativo 1/2007' in catalogo.ALIAS[f_rdl]
    assert 'TRLGDCU' in catalogo.ALIAS[f_rdl]
    f_rd = 'BOE_RD1468-1988_etiquetado_productos_industriales_consolidado.pdf'
    assert f_rd in catalogo.ALIAS
    assert 'RD 1468/1988' in catalogo.ALIAS[f_rd]
    assert 'Real Decreto 1468/1988' in catalogo.ALIAS[f_rd]
    f_oiml = 'NORMA_PAGO_61.pdf'
    assert f_oiml in catalogo.ALIAS
    assert 'OIML D 31:2019' in catalogo.ALIAS[f_oiml]
    assert 'OIML D 31' in catalogo.ALIAS[f_oiml]
    assert 'OIML D31' in catalogo.ALIAS[f_oiml]

def test_caracter_tres_docs_nuevos():
    tipo_rdl, ruta_rdl, nombre_rdl = caracter.TABLA['BOE-A-2007-20555']
    assert tipo_rdl == 'vinculante'
    assert ruta_rdl == 'BOE-A-2007-20555::cabecera'
    assert '1/2007' in nombre_rdl
    tipo_rd, ruta_rd, nombre_rd = caracter.TABLA['BOE-A-1988-28089']
    assert tipo_rd == 'vinculante'
    assert ruta_rd == 'BOE-A-1988-28089::cabecera'
    assert '1468/1988' in nombre_rd
