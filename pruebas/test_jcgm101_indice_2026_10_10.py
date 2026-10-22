"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import parsers
from ict155.extraccion import TextoPdf

def _pdf(*paginas):
    return TextoPdf('sintetico/guia_con_indice_pag.pdf', paginas=['\n'.join(p) for p in paginas])

def test_apartado_con_numero_de_pagina_del_indice_se_limpia_al_ganar_cuerpo():
    pdf = _pdf(['', ''], ['Contenido', '1 Alcance', '3', '2 Ejemplos', '3', '2.1 Modelo aditivo', '4'], ['2.2 Modelo lineal 53', '', '2.3 Otro modelo', '6', '2.4 Mas', '7', '2.5 Fin', '8'], ['1 Alcance', 'Texto alcance', '2 Ejemplos', ''], ['2.1 Modelo aditivo', 'Texto 2.1', '2.2 Modelo lineal', '', '2.2.1 Formulacion', 'Texto formulacion 2.2'])
    res = parsers.analizar_guia(pdf).preceptos
    por = {p.ruta: p for p in res}
    assert 'ap.2.2' in por
    assert por['ap.2.2'].titulo == 'Modelo lineal'
    assert por['ap.2.2'].lineas == ['2.2 Modelo lineal', '']
    assert por['ap.2.2'].pagina_inicio == 5
