"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import parsers
from ict155.extraccion import TextoPdf
from ict155.parsers import Precepto

def _pdf(*paginas):
    return TextoPdf('sintetico/documento.pdf', paginas=['\n'.join(p) for p in paginas])

def _rango(p):
    return (p.pagina_inicio, p.pagina_fin)

def _por_ruta(preceptos):
    return {p.ruta: p for p in preceptos}
BOE_TRES_PAGINAS = _pdf(['BOLETÍN OFICIAL DEL ESTADO', 'Real Decreto 1/2099, de 1 de enero, por el que se aprueba algo.', 'Referencia: BOE-A-2099-1'], ['Artículo 1. Objeto. ........................ 1', 'Artículo 2. Ámbito. ........................ 1'], ['TEXTO CONSOLIDADO Última modificación: 1 de enero de 2099', '', 'Preámbulo de la norma con una frase suficientemente larga.', 'Artículo 1. Objeto.', 'Esta norma tiene por objeto algo.'])

def test_la_cabecera_acaba_en_la_pagina_de_su_ultima_linea():
    cab = _por_ruta(parsers.analizar_boe(BOE_TRES_PAGINAS).preceptos)['cabecera']
    assert _rango(cab) == (1, 3)
    assert cab.texto.startswith('Real Decreto 1/2099')
    assert cab.texto.endswith('TEXTO CONSOLIDADO Última modificación: 1 de enero de 2099')

def test_la_cabecera_de_un_documento_con_todo_en_la_primera_pagina_sigue_en_la_1():
    boe = _pdf(['BOLETÍN OFICIAL DEL ESTADO', 'Real Decreto 1/2099, de 1 de enero.', 'Referencia: BOE-A-2099-1', 'TEXTO CONSOLIDADO Última modificación: 1 de enero de 2099', 'Artículo 1. Objeto.', 'Esta norma.'], ['Artículo 2. Otro.', 'Texto.'])
    por = _por_ruta(parsers.analizar_boe(boe).preceptos)
    assert _rango(por['cabecera']) == (1, 1)
    assert _rango(por['art.1']) == (1, 1) and _rango(por['art.2']) == (2, 2)

def test_la_cabecera_no_cambia_de_texto_ni_los_demas_preceptos_de_pagina():
    por = _por_ruta(parsers.analizar_boe(BOE_TRES_PAGINAS).preceptos)
    assert ' '.join(por['cabecera'].texto.split()) == 'Real Decreto 1/2099, de 1 de enero, por el que se aprueba algo. Referencia: BOE-A-2099-1 TEXTO CONSOLIDADO Última modificación: 1 de enero de 2099'
    assert _rango(por['art.1']) == (3, 3)

def test_el_preambulo_de_un_boe_empieza_donde_empieza_su_primera_linea_con_texto():
    por = _por_ruta(parsers.analizar_boe(BOE_TRES_PAGINAS).preceptos)
    assert _rango(por['preambulo']) == (3, 3)

def test_el_preambulo_que_pasa_a_otra_pagina_acaba_en_ella():
    boe = _pdf(['BOLETÍN OFICIAL DEL ESTADO', 'Real Decreto 1/2099, de 1 de enero.', 'Referencia: BOE-A-2099-1', 'TEXTO CONSOLIDADO Última modificación: 1 de enero de 2099', '', 'Primer parrafo del preambulo de la norma.'], ['Segundo parrafo del preambulo de la norma.', 'Artículo 1. Objeto.', 'Esta norma.'])
    por = _por_ruta(parsers.analizar_boe(boe).preceptos)
    assert _rango(por['preambulo']) == (1, 2)
    assert _rango(por['cabecera']) == (1, 1)
GUIA_PAGINA_1_VACIA = _pdf(['', ''], ['C-02', 'GUIA DE LA COMISION DE METROLOGIA LEGAL', '', 'La presente edicion de esta guia se publica en la web.', '1 Alcance', 'Esta guia se aplica a los registradores de temperatura de ejemplo.'])

def test_el_preambulo_de_una_guia_con_la_primera_pagina_vacia_empieza_en_la_2():
    por = _por_ruta(parsers.analizar_guia(GUIA_PAGINA_1_VACIA).preceptos)
    assert _rango(por['preambulo']) == (2, 2)
    assert por['preambulo'].texto.startswith('C-02')

def test_el_preambulo_de_una_directiva_con_la_primera_pagina_vacia_empieza_en_la_2():
    ue = _pdf(['', ''], ['EL PARLAMENTO EUROPEO Y EL CONSEJO DE LA UNIÓN EUROPEA,', 'Considerando lo siguiente:', '(1) Conviene armonizar las normas de los Estados miembros.', ''], ['HAN ADOPTADO LA PRESENTE DIRECTIVA:', 'Artículo 1', 'Objeto', 'La presente Directiva establece normas comunes.'])
    por = _por_ruta(parsers.analizar_eurlex(ue).preceptos)
    assert _rango(por['preambulo']) == (2, 3)
    assert _rango(por['art.1']) == (3, 3)

def test_un_precepto_que_abre_con_su_encabezado_no_cambia_de_pagina_de_comienzo():
    p = Precepto(ruta='ap.1', tipo='apartado', numero='1', etiqueta='1', titulo=None, lineas=['1 Alcance'], pagina_inicio=4, pagina_fin=4)
    assert not p.sin_texto_aun
    assert Precepto(ruta='preambulo', tipo='preambulo', numero=None, etiqueta='P', titulo=None, lineas=['', '  ']).sin_texto_aun

def _ap(ruta, texto, pagina, fin=None, de_indice=False):
    return Precepto(ruta=ruta, tipo='apartado', numero=ruta.rsplit('.', 1)[-1], etiqueta=ruta, titulo=None, lineas=texto.split('\n'), pagina_inicio=pagina, pagina_fin=fin or pagina, de_indice=de_indice)

def _jcgm101():
    """Public CI documentation."""
    return [_ap('ap.9.1', '9.1 Ilustraciones de aspectos de este Suplemento', 6), _ap('ap.9.2', '9.2 Modelo aditivo', 6), _ap('ap.9.2.1', '9.2.1 Formulación', 6), _ap('ap.9', '9 Ejemplos', 52), _ap('ap.9.1', '9.1 Ilustraciones de aspectos de este Suplemento', 52), _ap('ap.9.1.1', 'Texto ficticio del ensayo para comparar paginas y conservar longitude', 52), _ap('ap.9.2', '9.2 Modelo aditivo', 53), _ap('ap.9.2.1', '9.2.1 Formulación\nEste ejemplo considera el modelo aditivo.', 53, 54)]

def _texto_y_ruta(preceptos):
    return [(p.ruta, ' '.join(p.texto.split())) for p in preceptos]

def test_el_apartado_que_en_el_cuerpo_es_solo_su_titulo_se_queda_con_la_pagina_del_cuerpo():
    antes = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}))
    despues = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}), frozenset({5, 6}))
    assert _rango(_por_ruta(antes)['ap.9.2']) == (6, 6)
    assert _rango(_por_ruta(antes)['ap.9.1']) == (6, 6)
    assert _rango(_por_ruta(despues)['ap.9.2']) == (53, 53)
    assert _rango(_por_ruta(despues)['ap.9.1']) == (52, 52)

def test_no_cambia_ningun_texto_ni_ninguna_ruta_ni_el_orden():
    antes = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}))
    despues = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}), frozenset({5, 6}))
    assert _texto_y_ruta(antes) == _texto_y_ruta(despues)
    assert _texto_y_ruta(despues)[1] == ('ap.9.2', '9.2 Modelo aditivo 9.2.1 Formulación')

def test_solo_cambian_las_paginas_de_los_que_ganaba_el_indice():
    antes = {p.ruta: _rango(p) for p in parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}))}
    despues = {p.ruta: _rango(p) for p in parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}), frozenset({5, 6}))}
    cambian = {r for r in antes if antes[r] != despues[r]}
    assert cambian == {'ap.9.1', 'ap.9.2'}
    assert despues['ap.9.2.1'] == antes['ap.9.2.1'] == (53, 54)

def test_sin_las_paginas_de_entradas_todo_queda_como_antes():
    a = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}))
    b = parsers.quedarse_con_el_cuerpo(_jcgm101(), ('apartado',), frozenset({5}), frozenset())
    assert [(p.ruta, _rango(p)) for p in a] == [(p.ruta, _rango(p)) for p in b]

def test_la_entrada_del_indice_que_no_tiene_otra_aparicion_se_queda_como_esta():
    pre = [_ap('ap.9.2', '9.2 Modelo aditivo', 6), _ap('ap.9.3', '9.3 Calibración', 40)]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',), frozenset(), frozenset({6}))
    assert _rango(_por_ruta(out)['ap.9.2']) == (6, 6)

def test_la_que_gana_con_texto_mas_alla_del_indice_no_se_mueve():
    pre = [_ap('ap.9.5.4', '9.5.4 Resultados\n' + 'Prologo e introduccion. ' * 400, 6, 10), _ap('ap.9.5.3', '9.5.3 Propagacion y resumen\nTexto del apartado.', 76), _ap('ap.9.5.4', '9.5.4 Resultados', 76)]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',), frozenset({5}), frozenset({5, 6}))
    assert _rango(_por_ruta(out)['ap.9.5.4']) == (6, 10)

def test_la_que_gana_en_el_cuerpo_no_se_mueve_aunque_haya_una_aparicion_anterior():
    pre = [_ap('ap.4.2.5', '4.2.5 Otro requisito\nEl equipo cumplira lo dispuesto.', 10), _ap('ap.4.2.6', '4.2.6 Requisito de ejemplo', 11), _ap('ap.4.2.6', '4.2.6 Requisito de ejemplo\nEl equipo cumplira lo dispuesto en la norma.', 13)]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',), frozenset({3}), frozenset({3, 4}))
    assert _rango(_por_ruta(out)['ap.4.2.6']) == (13, 13)

def test_si_todas_las_apariciones_son_de_indice_no_hay_cuerpo_al_que_ir():
    pre = [_ap('ap.1', '1 Alcance\nTexto previo.', 2), _ap('ap.2', '2 Ejemplos largos de la primera entrada', 3), _ap('ap.3', '3 Otro apartado\nCon su texto.', 3), _ap('ap.2', '2 Ejemplos', 4)]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',), frozenset({3, 4}), frozenset({3, 4}))
    assert _rango(_por_ruta(out)['ap.2']) == (3, 3)

def test_una_pagina_con_tres_numeros_de_pagina_tras_entradas_es_de_indice():
    paginas = [['Introducción', 'Texto de una pagina normal.'], ['2.1 Modelo aditivo', '44', '2.1.1 Formulación', '44', '2.2 Modelo lineal', '45']]
    assert parsers.paginas_con_indice(paginas) == {2}

def test_los_numeros_que_decrecen_o_la_falta_de_entradas_no_hacen_un_indice():
    assert parsers.paginas_con_indice([['2.1 Modelo aditivo', '44', '2.1.1 Formulación', '12', '2.2 Modelo lineal', '9']]) == set()
    assert parsers.paginas_con_indice([['Texto', '44', 'Otro texto', '45', 'Mas texto', '46']]) == set()
    assert parsers.paginas_con_indice([['2.1 Modelo aditivo', '44', '2.2 Otro', '45']]) == set()

def test_el_rotulo_de_un_indice_tambien_la_marca_si_hay_enteros():
    assert parsers.paginas_con_indice([['Contenido', 'Prólogo', '5']]) == {1}

def test_la_regla_de_indice_de_los_enteros_sueltos_sigue_igual():
    paginas = [['Cabecera del documento', '2.1 Modelo aditivo', '44', '2.1.1 Formulación', '44', '2.2 Modelo lineal', '45', 'Pie del documento']]
    motivos = parsers.motivos_de_enteros(paginas)
    assert {m for m in motivos.values()} == {'indice'}
GUIA_CON_INDICE_SIN_PUNTOS = _pdf(['', ''], ['Contenido', '1 Alcance', '3', '2 Ejemplos', '3', '2.1 Modelo aditivo', '4', '2.1.1 Formulación', '4'], ['2.2 Modelo lineal', '5', '2.2.1 Formulación', '5', '2.2.2 Resultados', '5'], ['1 Alcance', 'Esta guía de ejemplo trata del cálculo de la incertidumbre de medida en un caso sencillo.', '2 Ejemplos', '2.1 Modelo aditivo', ''], ['2.1.1 Formulación', 'Este ejemplo considera el modelo aditivo con cuatro magnitudes de entrada independientes.', '2.2 Modelo lineal', '', '2.2.1 Formulación', 'Este ejemplo considera el modelo lineal con dos magnitudes.', '2.2.2 Resultados', 'Los resultados se resumen en la tabla siguiente para las dos magnitudes.'])

def _analizar_guia(monkeypatch, con_entradas: bool):
    if not con_entradas:
        original = parsers.quedarse_con_el_cuerpo
        monkeypatch.setattr(parsers, 'quedarse_con_el_cuerpo', lambda pre, tipos=('articulo',), indice=frozenset(), entradas=frozenset(): original(pre, tipos, indice))
    return parsers.analizar_guia(GUIA_CON_INDICE_SIN_PUNTOS).preceptos

def test_en_una_guia_el_titulo_que_empata_con_su_entrada_del_indice_lleva_la_pagina_del_cuerpo(monkeypatch):
    por = _por_ruta(_analizar_guia(monkeypatch, True))
    assert _rango(por['ap.2.2']) == (5, 5)
    assert _rango(por['ap.2.1']) == (4, 4)

def test_en_una_guia_no_cambia_ningun_texto_ni_ruta_ni_orden(monkeypatch):
    con = _analizar_guia(monkeypatch, True)
    sin = _analizar_guia(monkeypatch, False)
    assert [(p.ruta, p.tipo, p.padre, p.texto) for p in sin] == [(p.ruta, p.tipo, p.padre, p.texto) for p in con]
    assert _rango(_por_ruta(sin)['ap.2.2']) == (3, 3)
    assert {p.ruta for p, q in zip(sin, con) if _rango(p) != _rango(q)} == {'ap.2.2'}
