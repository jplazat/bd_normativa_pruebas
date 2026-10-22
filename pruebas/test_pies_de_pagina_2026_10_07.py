"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import parsers
from ict155.extraccion import TextoPdf
PIE = 'JCGM © 2008 - Reservados todos los derechos'

def _ruido(ln):
    return any((r.match(ln) for r in parsers.RUIDO))

def test_el_pie_de_eurlex_con_cuatro_cifras_y_el_numero_entre_rayas_son_ruido():
    assert _ruido('2014L0032 — ES — 27.01.2015 — 001.003 — 12')
    assert _ruido('02014L0030 — ES — 30.05.2026 — 002.001 — 3')
    assert _ruido('- 55 -') and _ruido('– 7 –')
    assert not _ruido('2014/32/UE — ES — texto') and (not _ruido('- 55 - y sigue'))

def _paginas(cuerpo_de):
    """Public CI documentation."""
    return [f'Cabecera de la guia\nLinea uno de la pagina {i}.\n' + cuerpo_de(i) + '\n' + pie for i, pie in enumerate([PIE, PIE, PIE, PIE, f'{PIE}      15', f'{PIE}   16', f'{PIE}  17', f'{PIE}      18'], start=1)]

def test_el_pie_con_el_numero_de_pagina_es_maquetacion():
    pdf = TextoPdf('guia_sintetica.pdf', paginas=_paginas(lambda i: f'Texto de la pagina {i}.'))
    m = parsers.lineas_de_maquetacion(pdf)
    assert {f'{PIE}      15', f'{PIE}   16', f'{PIE}  17', f'{PIE}      18'} <= m
    vivas = parsers.paginas_vivas(pdf)
    assert not any(('Reservados' in ln for pag in vivas for ln in pag))

def test_un_encabezado_con_numero_no_se_confunde_con_la_cabecera():
    paginas = _paginas(lambda i: 'Texto.')
    paginas[5] = '4 Cabecera de la guia\nEl apartado cuatro empieza aqui.\nTexto.\n' + PIE
    pdf = TextoPdf('guia_sintetica.pdf', paginas=paginas)
    assert '4 Cabecera de la guia' not in parsers.lineas_de_maquetacion(pdf)

def test_el_pie_revuelto_con_las_mismas_letras_es_maquetacion_y_el_que_cambia_una_cifra_no():
    pie = 'JCGM © 2012 – Reservados todos los derechos'
    paginas = [f'Texto de la pagina {i}.\nOtra linea {i}.\n{pie}' for i in range(1, 8)]
    paginas[3] = 'Texto de la pagina 4.\nOtra linea 4.\nJCGM © 2012 – Reservados todos los de-r5ec1ho- s'
    paginas[5] = 'Texto de la pagina 6.\nOtra linea 6.\nJCGM © 2013 – Reservados todos los derechos'
    m = parsers.lineas_de_maquetacion(TextoPdf('vim_sintetico.pdf', paginas=paginas))
    assert 'JCGM © 2012 – Reservados todos los de-r5ec1ho- s' in m
    assert 'JCGM © 2013 – Reservados todos los derechos' not in m

def test_la_cabecera_duplicada_por_la_negrita_es_maquetacion():
    cab = 'El papel de la incertidumbre de medida'
    paginas = [f'{cab}\nTexto de la pagina {i}.\nOtra linea {i}.' for i in range(1, 8)]
    paginas[4] = 'EEll ppaappeell ddee llaa iinncceerrttiidduummbbrree ddee mmeeddiiddaa\nTexto.\nOtra.'
    m = parsers.lineas_de_maquetacion(TextoPdf('jcgm_sintetico.pdf', paginas=paginas))
    assert 'EEll ppaappeell ddee llaa iinncceerrttiidduummbbrree ddee mmeeddiiddaa' in m

def test_una_nota_con_las_letras_de_dos_cabeceras_no_es_maquetacion():
    paginas = [f'OJ L, 20.11.2024\nTexto de la pagina {i}.\nELI: http://data.europa.eu/eli/reg/2024/2847/oj' for i in range(1, 8)]
    nota = '(1) OJ L, 2024/2847, 20.11.2024, ELI: http://data.europa.eu/eli/reg/2024/2847/oj.'
    paginas[5] = f'OJ L, 20.11.2024\nTexto.\n{nota}\nELI: http://data.europa.eu/eli/reg/2024/2847/oj'
    m = parsers.lineas_de_maquetacion(TextoPdf('cra_sintetico.pdf', paginas=paginas))
    assert nota not in m

def test_la_primera_pagina_no_pierde_su_variante():
    paginas = _paginas(lambda i: 'Texto.')
    paginas[0] = f'{PIE}  15\nTitulo de la guia\nTexto.\n{PIE}'
    pdf = TextoPdf('guia_sintetica.pdf', paginas=paginas)
    vivas = parsers.paginas_vivas(pdf)
    assert f'{PIE}  15' in vivas[0] and f'{PIE}  17' not in vivas[6]
