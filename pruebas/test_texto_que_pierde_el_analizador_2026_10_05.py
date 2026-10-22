"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import consulta, parsers
from ict155.extraccion import TextoPdf

def _p(ruta, tipo, texto, pag, numero=None):
    return parsers.Precepto(ruta=ruta, tipo=tipo, numero=numero, etiqueta=ruta, titulo=None, lineas=texto.split('\n'), pagina_inicio=pag, pagina_fin=pag)

def _plano(p):
    return ' '.join(p.texto.split())

def test_la_aparicion_que_pierde_no_se_tira_va_con_el_precepto_anterior():
    pre = [_p('preambulo', 'preambulo', 'Guia de ejemplo', 1), _p('ap.1.1', 'apartado', '1.1 Alcance', 1, '1.1'), _p('ap.1.1', 'apartado', '1.1 Alcance\nEsta guia se aplica a los registradores.', 3, '1.1')]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',))
    assert [p.ruta for p in out] == ['preambulo', 'ap.1.1']
    assert _plano(out[0]) == 'Guia de ejemplo 1.1 Alcance'
    assert _plano(out[1]) == '1.1 Alcance Esta guia se aplica a los registradores.'

def test_si_la_que_pierde_es_la_primera_va_con_la_siguiente():
    pre = [_p('ap.1', 'apartado', '1 Alcance', 1, '1'), _p('ap.1', 'apartado', '1 Alcance\nTexto del alcance.', 2, '1')]
    out = parsers.quedarse_con_el_cuerpo(pre, ('apartado',))
    assert len(out) == 1 and _plano(out[0]) == '1 Alcance 1 Alcance Texto del alcance.'
    assert (out[0].pagina_inicio, out[0].pagina_fin) == (1, 2)

def test_en_eurlex_gana_el_articulo_del_articulado_a_la_fila_de_la_tabla_de_correspondencias():
    cuerpo = _p('art.15', 'articulo', 'Artículo 15 Marcado de conformidad\nLa conformidad de un instrumento.', 10)
    anexo = _p('anexo.V', 'anexo', 'ANEXO V', 40)
    fila = _p('art.15', 'articulo', 'Artículo 15 Artículo 16 Artículo 17, apartados 1 a 5 ' * 4, 40)
    out = parsers.quedarse_con_el_cuerpo([cuerpo, anexo, fila])
    assert out == [cuerpo, anexo]
    assert 'Artículo 16 Artículo 17, apartados 1 a 5' in anexo.texto

def test_en_una_guia_pierde_la_aparicion_de_un_indice_aunque_sea_mas_larga():
    cuerpo = _p('ap.2.47', 'apartado', '2.47 compatibilidad metrológica de resultados de medida\npropiedad de un conjunto de resultados de medida', 40, '2.47')
    siguiente = _p('ap.3.1', 'apartado', '3.1 instrumento de medida', 50, '3.1')
    indice = _p('ap.2.47', 'apartado', '2.47 measurement condición de funcionamiento\n' + 'término 1.1 ' * 300, 79, '2.47')
    out = parsers.quedarse_con_el_cuerpo([cuerpo, siguiente, indice], ('apartado',), frozenset({79}))
    assert out == [cuerpo, siguiente]
    assert 'measurement condición de funcionamiento' in siguiente.texto and siguiente.pagina_fin == 79

def test_en_una_guia_pierde_la_aparicion_que_sigue_una_frase():
    bueno = _p('ap.5.1.2', 'apartado', '5.1.2 La incertidumbre típica combinada uc(y)', 32, '5.1.2')
    remision = _p('ap.5.1.2', 'apartado', '5.1.2 y E.3.1); la incertidumbre de uc(y)\n' + 'x ' * 500, 91, '5.1.2')
    out = parsers.quedarse_con_el_cuerpo([bueno, remision], ('apartado',))
    assert out == [bueno] and '5.1.2 y E.3.1);' in bueno.texto
    assert parsers.sigue_una_frase(_p('ap.3.2', 'apartado', '3.2 of the Directive 2014/53/EU', 10))
    assert parsers.sigue_una_frase(_p('ap.4.4', 'apartado', '4.4 y sgtes. incertidumbre', 135))
    assert not parsers.sigue_una_frase(_p('ap.5.1', 'apartado', '5.1 The Accreditation Body shall', 7))
    assert not parsers.sigue_una_frase(_p('ap.9.1.1', 'apartado', '9.1.1 Los ejemplos dados', 52))

def test_las_paginas_del_indice_alfabetico_se_reconocen_por_su_rotulo():
    lp = [('Índice alfabético', 79), ('A', 79), ('2.47 measurement', 79), ('2.46 comparabilidad', 40)]
    assert parsers._paginas_de_indice_alfabetico(lp) == {79}

def test_si_empatan_gana_la_primera_como_hasta_ahora():
    a = _p('ap.2.1', 'apartado', '2.1 Generalidades', 5, '2.1')
    b = _p('ap.2.1', 'apartado', '2.1 Generalidades', 19, '2.1')
    assert parsers.quedarse_con_el_cuerpo([a, b], ('apartado',)) == [a]
BOE = 'TEXTO CONSOLIDADO Última modificación: 27 de diciembre de 2025\nTÍTULO I\nDisposiciones generales\nCAPÍTULO I\nObjeto\nArtículo 1. Objeto.\nEsta ley regula las telecomunicaciones.\nArtículo 5. Programas.\nEn el marco de lo previsto en el\nartículo 5.3, h), de la presente Ley, el Ministerio promoverá la creación de programas.\nTÍTULO II\nOperadores\nCAPÍTULO I\nDerechos de los operadores\nSección 1.ª Ocupación del dominio público\nArtículo 6. Derechos.\nTexto del artículo seis.\nDisposición adicional vigésima. Prestación de servicios.\nTexto de la vigésima.\nDisposición adicional vigésima primera. Comunicación al Registro.\nTexto de la vigésima primera.\nDisposición adicional vigésima segunda. Comunicación al Ministerio.\nTexto de la vigésima segunda.'

def _boe():
    return parsers.analizar('boe', TextoPdf('BOE_ley_sintetica.pdf', paginas=[BOE]))

def test_las_disposiciones_con_ordinal_compuesto_tienen_cada_una_su_ruta():
    assert parsers.ordinal_a_numero('vigésima primera') == '21'
    assert parsers.ordinal_a_numero('decimosexta') == '16'
    assert parsers.ordinal_a_numero('vigésima') == '20'
    rutas = {p.ruta: _plano(p) for p in _boe().preceptos}
    assert rutas['disp.adicional.20'] == 'Disposición adicional vigésima. Prestación de servicios. Texto de la vigésima.'
    assert rutas['disp.adicional.21'].endswith('Texto de la vigésima primera.')
    assert rutas['disp.adicional.22'].endswith('Texto de la vigésima segunda.')
    assert consulta.ruta_de_cita('disposición adicional vigésima primera') == 'disp.adicional.21'

def test_un_capitulo_cuelga_de_su_titulo_y_no_choca_con_el_del_titulo_anterior():
    an = _boe()
    rutas = [p.ruta for p in an.preceptos]
    assert len(rutas) == len(set(rutas))
    assert 'titulo.I/capitulo.I' in rutas and 'titulo.II/capitulo.I' in rutas
    cap = next((p for p in an.preceptos if p.ruta == 'titulo.II/capitulo.I'))
    assert cap.padre == 'titulo.II'
    sec = next((p for p in an.preceptos if p.ruta == 'titulo.II/capitulo.I/seccion.1'))
    assert sec.padre == 'titulo.II/capitulo.I' and sec.texto == 'Sección 1.ª Ocupación del dominio público'
    assert 'Sección' not in cap.texto

def test_un_renglon_que_empieza_por_articulo_en_minuscula_es_texto():
    art5 = [p for p in _boe().preceptos if p.ruta == 'art.5']
    assert len(art5) == 1 and 'artículo 5.3, h), de la presente Ley' in art5[0].texto

def test_la_linea_de_la_consolidacion_entra_en_la_cabecera():
    cab = next((p for p in _boe().preceptos if p.ruta == 'cabecera'))
    assert 'Última modificación: 27 de diciembre de 2025' in cab.texto

def test_dos_preceptos_con_la_misma_ruta_no_llegan_a_la_ingesta():
    padre = _p('disp.final.3', 'disposicion', 'Disposición final tercera.\n1. Uno.\n«1. Uno de la otra ley.»', 5)
    hijo1 = _p('disp.final.3.1', 'apartado', '1. Uno.', 5)
    hijo2 = _p('disp.final.3.1', 'apartado', '1. Uno de la otra ley.', 5)
    assert parsers.sin_rutas_repetidas([padre, hijo1, hijo2]) == [padre, hijo1]
    a = _p('capitulo.I', 'capitulo', 'CAPÍTULO I Disposiciones generales', 1)
    b = _p('art.1', 'articulo', 'Artículo 1. Objeto.', 1)
    c = _p('capitulo.I', 'capitulo', 'CAPÍTULO I Derechos de los operadores', 4)
    assert parsers.sin_rutas_repetidas([a, b, c]) == [a, b]
    assert 'Derechos de los operadores' in b.texto and b.pagina_fin == 4
