"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import catalogo, mobiliario, parsers
from ict155.extraccion import TextoPdf
GUIA = '01_Conocimiento/Fuentes_primarias/05_Metrologia_e_incertidumbre/NORMA_PAGO_14.pdf'
LEY = '01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_RD244-2016_consolidado.pdf'
CAB_VIM = 'VIM: Guia ficticia de ensayo interno Conceptos supuestos para ensayo'
CAB_JCGM = 'JCGM 106:2012. Primera edición en español. 2015'
CAB_JCGM_PARES = 'JCGM 104:2009 Cabecera ficticia auxiliar para las paginas pares del ensayo XXX'
GUM = 'Expresión de la incertidumbre de medida: 2008 (Esp)'

def _cuerpo(i):
    """Public CI documentation."""
    return [f'Texto propio de la pagina {i}, que no se repite en ninguna otra pagina del documento.', f'Otra frase de la pagina {i}, distinta de todas las demas frases de este documento.']

def _pdf(paginas, ruta=GUIA):
    return TextoPdf(ruta, paginas=['\n'.join(p) for p in paginas])

def _vivas(pdf):
    return [[ln.strip() for ln in pag if ln.strip()] for pag in parsers.paginas_vivas(pdf)]

def _lineas(vivas):
    return [ln for pag in vivas for ln in pag]

def test_las_rutas_del_ensayo_son_de_guia_y_de_ley():
    assert catalogo.familia(GUIA) == 'guia'
    assert catalogo.familia(LEY) == 'boe'

def _vim(partidas=(4, 7, 10, 13), ruta=GUIA, total=16):
    paginas = []
    for i in range(1, total + 1):
        cab = ['VIM: Guia ficticia de ensayo interno', 'Conceptos supuestos para ensayo'] if i in partidas else [CAB_VIM]
        paginas.append(cab + _cuerpo(i))
    return _pdf(paginas, ruta)

def test_la_cabecera_en_dos_renglones_es_la_misma_cabecera_de_un_renglon():
    pdf = _vim()
    assert CAB_VIM in parsers.lineas_repetidas(pdf)
    assert 'Conceptos supuestos para ensayo' not in parsers.lineas_de_maquetacion(pdf)
    vivas = _vivas(pdf)
    todas = _lineas(vivas)
    assert CAB_VIM not in todas
    assert 'VIM: Guia ficticia de ensayo interno' not in todas and 'Conceptos supuestos para ensayo' not in todas
    for i, pag in enumerate(vivas, start=1):
        assert pag == _cuerpo(i)

def test_el_renglon_suelto_de_la_cabecera_en_medio_de_la_pagina_no_se_toca():
    pdf = _vim()
    paginas = list(pdf.paginas)
    cuerpo = _cuerpo(5)
    paginas[4] = '\n'.join([CAB_VIM, cuerpo[0], cuerpo[1], 'Y ahora una frase corta,', 'Conceptos supuestos para ensayo', 'que sigue.', 'Otra mas.', 'Y la ultima.'])
    pdf = TextoPdf(GUIA, paginas=paginas)
    assert 'Conceptos supuestos para ensayo' in _vivas(pdf)[4]

def test_la_primera_pagina_no_se_toca():
    paginas = list(_vim(partidas=(1, 7, 10, 13)).paginas)
    vivas = _vivas(TextoPdf(GUIA, paginas=paginas))
    assert vivas[0][:2] == ['VIM: Guia ficticia de ensayo interno', 'Conceptos supuestos para ensayo']
    assert not any(('oncepto' in ln for pag in vivas[1:] for ln in pag))

def test_la_cabecera_partida_en_una_ley_se_queda_como_estaba():
    vivas = _vivas(_vim(ruta=LEY))
    assert 'Conceptos supuestos para ensayo' in _lineas(vivas)

def _alterna(con_cabecera_impar=14, con_cabecera_par=14, total=30):
    """Public CI documentation."""
    paginas = []
    impares = pares = 0
    for i in range(1, total + 1):
        if i % 2:
            impares += 1
            cab = [CAB_JCGM] if impares <= con_cabecera_impar else []
        else:
            pares += 1
            cab = [CAB_JCGM_PARES] if pares <= con_cabecera_par else []
        paginas.append(cab + _cuerpo(i))
    return _pdf(paginas)

def test_la_cabecera_de_las_impares_no_llega_a_la_mitad_pero_si_a_la_mitad_de_las_impares():
    pdf = _alterna()
    assert CAB_JCGM not in parsers.lineas_repetidas(pdf)
    vivas = _vivas(pdf)
    assert CAB_JCGM not in _lineas(vivas[1:]) and CAB_JCGM_PARES not in _lineas(vivas[1:])
    assert vivas[0][0] == CAB_JCGM
    for i, pag in enumerate(vivas, start=1):
        assert pag[-2:] == _cuerpo(i)

def test_una_cabecera_que_no_llega_a_ocho_paginas_no_se_descubre():
    vivas = _vivas(_alterna(con_cabecera_impar=7, con_cabecera_par=7))
    assert _lineas(vivas).count(CAB_JCGM) == 7 and _lineas(vivas).count(CAB_JCGM_PARES) == 7

def test_la_cabecera_de_las_impares_en_una_ley_se_queda_como_estaba():
    pdf = _alterna()
    pdf = TextoPdf(LEY, paginas=pdf.paginas)
    assert _lineas(_vivas(pdf)).count(CAB_JCGM) == 14

def test_una_linea_en_la_mitad_de_las_paginas_pero_no_en_el_borde_no_se_descubre():
    paginas = []
    for i in range(1, 31):
        cuerpo = _cuerpo(i) + [f'Una tercera frase de la pagina {i}, distinta.', f'Y una cuarta de la pagina {i}, distinta.']
        filas = [f'Fila {i} {k} de la tabla, distinta.' for k in range(5)]
        paginas.append(cuerpo + (['Columna de la tabla que se repite'] if i % 2 else []) + filas)
    pdf = _pdf(paginas)
    assert 'Columna de la tabla que se repite' not in parsers.lineas_repetidas(pdf)
    assert _lineas(_vivas(pdf)).count('Columna de la tabla que se repite') == 15

def test_dos_cabeceras_en_un_renglon_se_quitan_y_una_frase_que_las_cita_no():
    a, b = ('WELMEC Guide 7.2 Software Guide', 'Version 2026')
    frase = f'Para el detalle, vease {a} en su {b}.'
    paginas = []
    for i in range(1, 21):
        cab = [f'{a}        {b}'] if i in (5, 6, 8, 9, 11, 12) else [a, b]
        cuerpo = _cuerpo(i)
        if i == 9:
            cuerpo = cuerpo[:1] + [frase] + cuerpo[1:] + ['Y mas texto.', 'Y mas aun.', 'Y asi.']
        paginas.append(cab + cuerpo)
    pdf = _pdf(paginas)
    assert {a, b} <= parsers.lineas_repetidas(pdf)
    assert f'{a}        {b}' not in parsers.lineas_de_maquetacion(pdf)
    vivas = _vivas(pdf)
    assert not any((ln.startswith(a) for pag in vivas for ln in pag))
    assert not any((ln.strip() == b for pag in vivas for ln in pag))
    assert vivas[8].count(frase) == 1

def _gum():
    """Public CI documentation."""
    paginas = []
    for i in range(1, 21):
        if i <= 8:
            cab = GUM
        elif i <= 16:
            titulo = ['Alcance', 'Definiciones', 'Ejemplos', 'Conceptos básicos'][i % 4]
            cab = f"{(GUM.replace('medida:', 'medida :') if i == 15 else GUM)}          {titulo}"
        elif i <= 19:
            cab = f'{GUM} Ejemplos'
        else:
            cab = f'{GUM} es el título de esta guía'
        paginas.append([cab] + _cuerpo(i))
    return _pdf(paginas)

def test_la_cabecera_pegada_al_titulo_corriente_se_quita_entera():
    vivas = _vivas(_gum())
    assert not any((ln.startswith(GUM[:20]) for pag in vivas[1:19] for ln in pag))
    for i, pag in enumerate(vivas[1:19], start=2):
        assert pag == _cuerpo(i)

def test_el_titulo_corriente_con_un_solo_blanco_solo_vale_si_se_repite():
    vivas = _vivas(_gum())
    assert vivas[19][0] == f'{GUM} es el título de esta guía'
    assert not any((ln == f'{GUM} Ejemplos' for pag in vivas for ln in pag))

def test_la_cabecera_con_un_numero_de_pagina_detras_no_es_un_titulo_corriente():
    cab = 'EURAMET cg-11, Version 2.0 (03/2011)'
    paginas = [[f'{cab}          Page {i}'] + _cuerpo(i) for i in range(1, 21)]
    vivas = _vivas(_pdf(paginas))
    assert all((pag[0] == f'{cab}          Page {i}' or pag[0] == f'{cab} Page {i}' for i, pag in enumerate(vivas, start=1)))

def test_el_numero_de_pagina_n_de_m_es_valido_solo_con_n_entre_1_y_m():
    assert parsers._es_n_de_m('3/5') and parsers._es_n_de_m('1/1') and parsers._es_n_de_m('12/120')
    assert not parsers._es_n_de_m('5/3') and (not parsers._es_n_de_m('0/4'))
    assert not parsers._es_n_de_m('1/4 de') and (not parsers._es_n_de_m('1 / 4 pesetas'))

def test_el_pie_n_de_m_se_quita_si_esta_en_la_mitad_de_las_paginas_y_no_en_medio():
    paginas = []
    for i in range(1, 21):
        cuerpo = _cuerpo(i) + ['Una tercera frase.', 'Una cuarta frase.']
        if i == 7:
            cuerpo += ['1/2']
        paginas.append(cuerpo + ['Una quinta.', 'Una sexta.', 'Una septima.', f'{i % 5 + 1}/5'])
    vivas = _vivas(_pdf(paginas))
    assert not any((ln.endswith('/5') for pag in vivas[1:] for ln in pag))
    assert vivas[6].count('1/2') == 1
    assert vivas[0][-1] == '2/5'

def test_el_n_de_m_en_pocas_paginas_no_se_toca():
    paginas = [_cuerpo(i) + ([f'{i}/20'] if i <= 5 else []) for i in range(1, 21)]
    vivas = _vivas(_pdf(paginas))
    assert sum((1 for pag in vivas for ln in pag if ln.endswith('/20'))) == 5

def test_un_documento_sin_cabeceras_se_queda_igual():
    paginas = [_cuerpo(i) + [f'Tercera frase de la pagina {i}, todavia distinta.'] for i in range(1, 13)]
    pdf = _pdf(paginas)
    assert _vivas(pdf) == [[ln for ln in p if ln.strip()] for p in paginas]

def test_menos_de_cuatro_paginas_no_hay_nada_que_descubrir():
    assert parsers._maquetacion_en_tirada(_pdf([[CAB_JCGM] + _cuerpo(i) for i in range(1, 4)]), set(), set()) == ({}, set())

def _guia_con_cabecera_partida():
    """Public CI documentation."""
    paginas = [['Guía sintética de metrología', 'Edición 2026']]
    for i in range(2, 21):
        cab = ['VIM: Guia ficticia de ensayo interno', 'Conceptos supuestos para ensayo'] if i in (6, 10, 14) else [CAB_VIM]
        pag = list(cab)
        if i % 2 == 0 and i < 20:
            n = i // 2
            pag += [f'{n} Apartado numero {n}', f'Texto del apartado {n}, en la pagina {i}, que no se repite jamas.']
        else:
            pag += [f'Texto del apartado {(i - 1) // 2}, en la pagina {i}, que no se repite jamas.']
        paginas.append(pag)
    return _pdf(paginas)

def test_el_apartado_ya_no_acaba_con_la_cabecera_de_la_pagina_siguiente():
    pdf = _guia_con_cabecera_partida()
    por = {p.ruta: p for p in parsers.analizar_guia(pdf).preceptos}
    assert [r for r in por if r.startswith('ap.')] == [f'ap.{n}' for n in range(1, 10)]
    for n in (2, 4, 6):
        p = por[f'ap.{n}']
        assert 'VIM: Guia ' not in p.texto and 'onceptos supuest' not in p.texto
        assert (p.pagina_inicio, p.pagina_fin) == (2 * n, 2 * n + 1)
    assert por['ap.3'].texto.startswith('3 Apartado numero 3 Texto del apartado 3')

def test_las_rutas_son_las_mismas_con_la_regla_y_sin_ella(monkeypatch):
    pdf = _guia_con_cabecera_partida()
    con = [(p.ruta, p.tipo, p.padre) for p in parsers.analizar_guia(pdf).preceptos]
    monkeypatch.setattr(parsers, '_es_de_guia', lambda _pdf: False)
    sin = [(p.ruta, p.tipo, p.padre) for p in parsers.analizar_guia(pdf).preceptos]
    assert con == sin

def test_lo_que_se_quita_en_tirada_entra_en_el_mobiliario_del_validador():
    pdf = _alterna()
    textos = parsers.textos_de_maquetacion_en_tirada(pdf)
    assert CAB_JCGM in textos and CAB_JCGM_PARES in textos
    patrones = mobiliario.detectar(pdf)
    assert CAB_JCGM in patrones and CAB_JCGM_PARES in patrones

def test_el_n_de_m_entra_como_patron_y_la_cita_con_el_pie_casa():
    from ict155 import validador
    paginas = [_cuerpo(i) + [f'{i % 5 + 1}/5'] for i in range(1, 21)]
    pdf = _pdf(paginas)
    patrones = mobiliario.detectar(pdf)
    assert '#/#' in patrones
    rx = mobiliario.compilar(tuple(patrones) + (CAB_JCGM,), validador._norm)
    cita = validador._norm(f'{CAB_JCGM} {_cuerpo(3)[0]} 3/5 {_cuerpo(3)[1]}')
    guardado = validador._norm(f'{_cuerpo(3)[0]} {_cuerpo(3)[1]}')
    assert mobiliario.quitar(cita, rx) == mobiliario.quitar(guardado, rx)

def test_en_una_ley_no_hay_textos_de_maquetacion_en_tirada():
    pdf = TextoPdf(LEY, paginas=_alterna().paginas)
    assert parsers.textos_de_maquetacion_en_tirada(pdf) == []
