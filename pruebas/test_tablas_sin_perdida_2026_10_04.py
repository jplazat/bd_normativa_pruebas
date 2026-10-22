"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import parsers
from ict155.extraccion import TextoPdf

def _paginas(n=8):
    """Public CI documentation."""
    out = []
    for i in range(n):
        out.append('\n'.join(['WELMEC 9.9, issue 1', f'Texto corriente de la pagina {i}, distinto en cada una', f'Segunda linea propia de la pagina {i}', 'DIRECTIVE 2014/31/EU (NAWID)', f'Provision {i} of the quality system', 'ISO/IEC 17065', '13.8.2008' if i % 2 else f'Linea extra {i}', 'cve: BOE-A-2017-13543 Verificable en http://www.boe.es' if i % 2 == 0 else f'Otra {i}', f'Tercera linea propia {i}', f'Cuarta linea propia {i}', f'Quinta linea propia {i}', 'Page footer of the guide']))
    return out

def test_se_quitan_la_cabecera_el_pie_la_fecha_y_el_pie_de_verificacion():
    rep = parsers.lineas_repetidas(TextoPdf(ruta_relativa='g.pdf', paginas=_paginas()))
    assert 'WELMEC 9.9, issue 1' in rep
    assert 'Page footer of the guide' in rep
    assert '13.8.2008' in rep
    assert 'cve: BOE-A-2017-13543 Verificable en http://www.boe.es' in rep

def test_la_cabecera_de_columna_y_la_celda_de_en_medio_se_quedan():
    rep = parsers.lineas_repetidas(TextoPdf(ruta_relativa='g.pdf', paginas=_paginas()))
    assert 'DIRECTIVE 2014/31/EU (NAWID)' not in rep
    assert 'ISO/IEC 17065' not in rep

def test_el_analizador_conserva_el_contenido_de_la_tabla():
    paginas = _paginas()
    paginas[0] = '1 Scope\n' + paginas[0]
    t = TextoPdf(ruta_relativa='g.pdf', paginas=paginas)
    texto = ' '.join((p.texto for p in parsers.analizar_guia(t).preceptos))
    assert texto.count('DIRECTIVE 2014/31/EU (NAWID)') == 8
    assert texto.count('ISO/IEC 17065') == 8
    assert 'WELMEC 9.9, issue 1' not in texto
    assert '13.8.2008' not in texto

def test_menos_de_cuatro_paginas_no_quita_nada():
    assert parsers.lineas_repetidas(TextoPdf(ruta_relativa='g.pdf', paginas=_paginas(3))) == set()

def test_la_cabecera_con_el_codigo_del_documento_se_quita_aunque_salga_en_medio():
    """Public CI documentation."""
    paginas = []
    for i in range(6):
        paginas.append('\n'.join([f'Primera linea propia {i}', f'Segunda linea propia {i}', f'Tercera {i}', 'CGA-ENAC-OCML Rev.4, Mayo 2021 Series 1, 4, 5, 7 y 13', f'Cuarta linea propia {i}', f'Quinta {i}', f'Sexta {i}', f'Septima {i}']))
    t = TextoPdf(ruta_relativa='x/NORMA_PAGO_39_CGA-ENAC-OCML.pdf', paginas=paginas)
    assert 'CGA-ENAC-OCML Rev.4, Mayo 2021 Series 1, 4, 5, 7 y 13' in parsers.lineas_repetidas(t)
    t2 = TextoPdf(ruta_relativa='x/OTRA_GUIA_2021.pdf', paginas=paginas)
    assert 'CGA-ENAC-OCML Rev.4, Mayo 2021 Series 1, 4, 5, 7 y 13' not in parsers.lineas_repetidas(t2)
