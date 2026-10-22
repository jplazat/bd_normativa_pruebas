"""Public CI documentation."""
from __future__ import annotations
import pytest
from ict155 import parsers

def _art(lineas, ruta='disp.final.3'):
    return parsers.Precepto(ruta=ruta, tipo='disposicion', numero='3', etiqueta='Disposición final 3', titulo=None, lineas=lineas, pagina_inicio=18, pagina_fin=23)

def _rutas(lineas, ruta='disp.final.3'):
    """Public CI documentation."""
    r = {}
    for q in parsers.subdividir([_art(lineas, ruta=ruta)]):
        r.setdefault(q.ruta, ' '.join(q.lineas))
    return r

def test_letras_dentro_de_cita_entre_comillas_no_abren_letra():
    """Public CI documentation."""
    lineas = ['1. Primer apartado.', '2. Segundo apartado:', 'a) Primera letra legítima;', 'b) Segunda letra con norma citada:', '«Artículo 5. Lista citada.', 'c) letra de la norma citada;', 'd) otra letra de la norma citada.»', 'c) Tercera letra legítima del apartado.', '3. Tercer apartado.']
    r = _rutas(lineas)
    assert 'disp.final.3.2.a' in r
    assert 'disp.final.3.2.b' in r
    assert 'disp.final.3.2.c' in r
    assert 'disp.final.3.2.d' not in r
    assert 'letra de la norma citada' in r['disp.final.3.2.b']
    assert r['disp.final.3.2.c'] == 'c) Tercera letra legítima del apartado.'

def test_segunda_serie_en_apartado_repetido_no_agrega_letras():
    """Public CI documentation."""
    lineas = ['1. Apartado 1.', '2. Fines del Consejo:', 'a) coordinar actuaciones;', 'b) intercambiar información;', 'c) identificar mejoras.', '3. Funciones del Consejo:', 'a) informar proyectos;', 'b) impulsar estudios;', 'c) crear bases de datos;', 'd) comités técnicos.', 'Siete. Se modifica el artículo 31:', '«Artículo 31. Infracciones.', '1. Infracciones muy graves:', 'a) muy grave 1;', 'b) muy grave 2.', '2. Infracciones graves:', 'a) infracción grave a;', 'b) infracción grave b;', 'c) infracción grave c;', 'd) infracción grave d;', 'e) infracción grave e.»']
    r = _rutas(lineas)
    assert 'disp.final.3.2.a' in r
    assert 'disp.final.3.2.b' in r
    assert 'disp.final.3.2.c' in r
    assert 'disp.final.3.2.d' not in r
    assert 'disp.final.3.2.e' not in r
    assert 'coordinar actuaciones' in r['disp.final.3.2.a']

def test_ley32_2014_disp_final_3_letras_oficiales():
    """Public CI documentation."""
    from ict155 import config
    from ict155.extraccion import extraer
    rel = '01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_Ley32-2014_Metrologia_consolidada.pdf'
    if not (config.BIBLIOTECA / rel).exists():
        pytest.skip('PDF no encontrado en entorno local')
    pdf = extraer(rel)
    a = parsers.analizar_boe(pdf)
    letras_3 = [p for p in a.preceptos if p.tipo == 'letra' and p.ruta.startswith('disp.final.3.')]
    rutas_3 = [p.ruta for p in letras_3]
    assert 'disp.final.3.2.a' in rutas_3
    assert 'disp.final.3.2.b' in rutas_3
    assert 'disp.final.3.2.c' in rutas_3
    assert 'disp.final.3.3.a' in rutas_3
    assert 'disp.final.3.3.b' in rutas_3
    assert 'disp.final.3.3.c' in rutas_3
    assert 'disp.final.3.3.d' in rutas_3
    assert 'disp.final.3.1.a' in rutas_3
    assert 'disp.final.3.1.b' in rutas_3
    assert 'disp.final.3.1.c' in rutas_3
    assert 'disp.final.3.1.d' in rutas_3
    for l in 'defghijklmnñopqr':
        assert f'disp.final.3.2.{l}' not in rutas_3
    for l in 'efghi':
        assert f'disp.final.3.3.{l}' not in rutas_3
    assert len(set(rutas_3)) == 11
