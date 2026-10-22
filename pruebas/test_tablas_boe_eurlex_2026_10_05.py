"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import tablas

class _Fila:

    def __init__(self, cells):
        self.cells = cells
        self.bbox = (min((c[0] for c in cells if c)), min((c[1] for c in cells if c)), max((c[2] for c in cells if c)), max((c[3] for c in cells if c)))

class _Tabla:

    def __init__(self, cajas, textos):
        self.rows = [_Fila(f) for f in cajas]
        self._t = textos

    def extract(self):
        return self._t

def _linea(texto, x0, y, ancho=5.0):
    """Public CI documentation."""
    chars = [(c, (x0 + k * ancho, y, x0 + (k + 1) * ancho, y + 8)) for k, c in enumerate(texto)]
    return ((x0, y, x0 + len(texto) * ancho, y + 8), chars)
CAJAS = [[(0, 0, 200, 20), (200, 0, 400, 20)]]
EXTRACT = [['Membrana deformable.', 'Q - Q - Q\nmin t max']]
LINEAS = [_linea('Membrana deformable.', 2, 5), _linea('Qmin - Qt - Qmax', 202, 5)]
PAGINA = tablas.norm(tablas.limpiar_celda('Tipo del contador Membrana deformable. Qmin - Qt - Qmax'))

def test_el_subindice_en_su_sitio_si_la_pagina_lo_dice_asi():
    t = _Tabla(CAJAS, EXTRACT)
    assert tablas.leer_celdas(t, LINEAS, PAGINA) == [['Membrana deformable.', 'Qmin - Qt - Qmax']]

def test_si_la_pagina_no_lo_dice_en_ese_orden_se_queda_find_tables():
    t = _Tabla(CAJAS, EXTRACT)
    otra = tablas.norm('Tipo del contador Membrana deformable. Qmax - Qt - Qmin')
    assert tablas.leer_celdas(t, LINEAS, otra)[0][1] == 'Q - Q - Q min t max'

def test_con_un_caracter_distinto_se_queda_find_tables():
    t = _Tabla(CAJAS, [['Membrana deformable.', 'Mean temperature']])
    lineas = [_linea('Membrana deformable.', 2, 5), _linea('temperature Mea', 202, 5)]
    pagina = tablas.norm('Membrana deformable. temperature Mea Mean temperature')
    assert tablas.leer_celdas(t, lineas, pagina)[0][1] == 'Mean temperature'

def test_sin_lineas_es_la_lectura_de_siempre():
    t = _Tabla(CAJAS, EXTRACT)
    assert tablas.leer_celdas(t) == [['Membrana deformable.', 'Q - Q - Q min t max']]

def test_la_tabla_de_subindices_ya_no_se_descarta():
    filas_antes = tablas.leer_celdas(_Tabla(CAJAS + [[(0, 20, 200, 40), (200, 20, 400, 40)]], EXTRACT + [['Turbina.', 'Q - Q\nmin max']]))
    pagina_texto = 'Tipo del contador Membrana deformable. Qmin - Qt - Qmax Turbina. Qmin - Qmax'
    assert not tablas.es_tabla_valida(filas_antes, pagina_texto)
    t = _Tabla(CAJAS + [[(0, 20, 200, 40), (200, 20, 400, 40)]], EXTRACT + [['Turbina.', 'Q - Q\nmin max']])
    lineas = LINEAS + [_linea('Turbina.', 2, 25), _linea('Qmin - Qmax', 202, 25)]
    filas = tablas.leer_celdas(t, lineas, tablas.norm(tablas.limpiar_celda(pagina_texto)))
    assert filas[1] == ['Turbina.', 'Qmin - Qmax']
    assert tablas.es_tabla_valida(filas, pagina_texto)

def test_una_tabla_de_una_fila_al_pie_de_pagina_vale():
    fila = [['Normativa aplicable', 'Norma UNE-EN 61000-4-11:2021. Compatibilidad electromagnetica']]
    pagina = 'Normativa aplicable Norma UNE-EN 61000-4-11:2021. Compatibilidad electromagnetica (CEM)'
    assert tablas.es_tabla_valida(fila, pagina)

def test_la_fila_es_del_precepto_aunque_los_espacios_sean_otros():
    t = dict(filas=[['Reglamento (CE) n. o 765/2008', 'Presente Reglamento'], ['Mensajes', '3XYA 79YA 99YA', '5 y 6']])
    texto = 'Tabla de correspondencias Reglamento (CE) n.o 765/2008 Presente Reglamento Mensajes 3XYA 79YA 99YA 5y6'
    assert tablas.filas_del_precepto(t, texto) == t['filas']

def test_una_fila_de_otro_precepto_sigue_sin_ser_suya():
    t = dict(filas=[['Qmin ≤ Q < Qt', '± 6 %', '± 4 %'], ['Qt ≤ Q < Qmax', '± 3 %', '± 2 %']])
    texto = 'Tabla 4. Clase 1,5 1,0 Qt ≤ Q < Qmax ± 3 % ± 2 %'
    assert tablas.filas_del_precepto(t, texto) == [t['filas'][1]]

def test_la_fila_de_la_tabla_de_al_lado_no_es_suya():
    t4 = dict(filas=[['Clase', '1,5', '1,0'], ['Qmin ≤ Q < Qt', '± 3 %', '± 2 %'], ['Qt ≤ Q < Qmax', '± 1,5 %', '± 1 %']])
    texto3 = 'Tabla 3. Clase 1,5 1,0 Qmin ≤ Q < Qt ± 6 % ± 4 % Qt ≤ Q < Qmax ± 3 % ± 2 %'
    texto4 = 'Tabla 4. Clase 1,5 1,0 Qmin ≤ Q < Qt ± 3 % ± 2 % Qt ≤ Q < Qmax ± 1,5 % ± 1 %'
    assert tablas.filas_suyas(t4, texto3, [texto4]) == [t4['filas'][0]]
    assert tablas.filas_suyas(t4, texto4, [texto3]) == t4['filas']
    assert not tablas.es_duena(t4, texto3, [texto4]) and tablas.es_duena(t4, texto4, [texto3])

def test_una_tabla_que_reparten_dos_preceptos_da_a_cada_uno_sus_filas():
    t = dict(filas=[['Term', 'Where'], ['accuracy class', 'Annex I'], ['module H1', 'Annex II']])
    ap1 = 'Term Where accuracy class Annex I module H1 see Annex II'
    ap2 = 'Term Where module H1 Annex II'
    assert tablas._puntos_de_fila(['moduleh1', 'annexii'], tablas.norm(ap1).replace(' ', '')) == 1
    assert tablas.filas_suyas(t, ap1, [ap2]) == t['filas'][:2]
    assert tablas.filas_suyas(t, ap2, [ap1]) == [t['filas'][0], t['filas'][2]]

def test_una_fila_suelta_en_dos_preceptos_solo_la_usa_el_dueno_de_la_tabla():
    t = dict(filas=[['Magnitud', 'Valor'], ['Longitud', '1 m'], ['Masa', '1 kg']])
    duena = 'Magnitud y Valor. Longitud y 1 m. Masa y 1 kg.'
    otro = 'Masa y 1 kg.'
    assert tablas._puntos(t, duena) == (0, 3) and tablas._puntos(t, otro) == (0, 1)
    assert tablas.filas_suyas(t, duena, [otro]) == t['filas']
    assert tablas.filas_suyas(t, otro, [duena]) == []

class _TablaSimple:

    def __init__(self, filas):
        self._f = filas

    def extract(self):
        return self._f

class _Pag:

    def __init__(self, tablas_):
        self._t = tablas_

    def find_tables(self):
        return type('R', (), {'tables': [_TablaSimple(f) for f in self._t]})()

class _Documento:

    def __init__(self, paginas):
        self._p = [_Pag(t) for t in paginas]
        self.page_count = len(paginas)

    def __getitem__(self, i):
        return self._p[i]

def test_un_pie_de_pagina_dibujado_como_tabla_no_se_guarda():
    pies = [[['ATP Handbook 2025', 'iii']], [['iv', 'ATP Handbook 2025']], [['ATP Handbook 2025', 'v']], [['vi', 'ATP Handbook 2025']], [['ATP Handbook 2025', 'vii']], [['viii', 'ATP Handbook 2025']]]
    datos = [['Class', 'Temperature'], ['FRC', '-20 °C']]
    paginas = [[p, datos] if k == 2 else [p] for k, p in enumerate(pies)]
    textos = ['ATP Handbook 2025 iii iv v vi vii viii Class Temperature FRC -20 °C'] * 6
    descartadas = []
    t = tablas.tablas_del_documento(_Documento(paginas), textos, descartadas)
    assert len(descartadas) == 6
    assert [x['filas'][0][0][0] for x in t] == ['Class']

def test_una_tabla_de_una_fila_que_no_se_repite_se_guarda():
    filas = [[['Normativa aplicable', 'Norma UNE-EN 61000-4-11:2021']], [['Normativa aplicable', 'Norma UNE-EN 61000-4-6:2014']], [['Normativa aplicable', 'Norma UNE-EN 61000-4-4:2013']]]
    textos = ['Normativa aplicable Norma UNE-EN 61000-4-11:2021 61000-4-6:2014 61000-4-4:2013'] * 3
    t = tablas.tablas_del_documento(_Documento([[f] for f in filas]), textos)
    assert len(t) == 3

class _TablaConCaja(_TablaSimple):

    def __init__(self, filas, caja):
        super().__init__(filas)
        self.bbox = caja

class _PagConBloques:
    """Public CI documentation."""

    def __init__(self, tablas_cajas, bloques):
        self._t = tablas_cajas
        self._b = bloques

    def find_tables(self):
        return type('R', (), {'tables': [_TablaConCaja(f, c) for f, c in self._t]})()

    def get_text(self, modo='text', **kw):
        if modo == 'blocks':
            return self._b
        if modo == 'rawdict':
            return {'blocks': []}
        return ' '.join((b[4] for b in self._b))

class _DocConBloques:

    def __init__(self, paginas):
        self._p = paginas
        self.page_count = len(paginas)

    def __getitem__(self, i):
        return self._p[i]
CAB_CMM = ['Cantidad minima medida (CMM)', 'Error maximo permitido']

def test_dos_tablas_con_la_misma_cabecera_en_paginas_seguidas_no_se_juntan_si_hay_un_titulo():
    t1 = [CAB_CMM, ['De 1 L a 2 L', '± 1 %']]
    t2 = [CAB_CMM, ['De 1 L a 2 L', '± 2 %']]
    p59 = _PagConBloques([(t1, (50, 600, 550, 780))], [(50, 560, 550, 590, 'Tabla 1. Error maximo permitido para cantidades minimas', 0, 0)])
    p60 = _PagConBloques([(t2, (50, 120, 550, 300))], [(50, 80, 550, 110, 'Tabla 2. Error maximo permitido para cantidades minimas', 0, 0)])
    texto = 'Cantidad minima medida (CMM) Error maximo permitido De 1 L a 2 L Tabla'
    t = tablas.tablas_del_documento(_DocConBloques([p59, p60]), [texto, texto])
    assert [x['filas'][1][1][0] for x in t] == ['± 1 %', '± 2 %']

def test_una_tabla_que_sigue_arriba_de_la_pagina_siguiente_si_se_junta():
    t1 = [CAB_CMM, ['De 1 L a 2 L', '± 1 %']]
    t2 = [CAB_CMM, ['De 0,4 L a 1 L', '± 1 % de CMM']]
    p59 = _PagConBloques([(t1, (50, 600, 550, 780))], [(50, 800, 550, 815, 'Pagina 59', 0, 0)])
    p60 = _PagConBloques([(t2, (50, 120, 550, 300))], [(50, 40, 550, 60, 'BOLETIN OFICIAL DEL ESTADO', 0, 0)])
    texto = 'Cantidad minima medida (CMM) Error maximo permitido De 1 L a 2 L 0,4 de CMM Pagina'
    t = tablas.tablas_del_documento(_DocConBloques([p59, p60]), [texto, texto])
    assert len(t) == 1 and (t[0]['pagina_inicio'], t[0]['pagina_fin']) == (1, 2)
    assert len(t[0]['filas']) == 3
