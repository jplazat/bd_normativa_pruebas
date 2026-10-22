"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import parsers
from ict155.extraccion import TextoPdf
PROSA = 'La verificacion periodica se realiza conforme a lo dispuesto en esta orden y en sus anexos'

def _lineas(*paginas: str) -> list[str]:
    pdf = TextoPdf('sintetico.pdf', paginas=list(paginas))
    return [ln for ln, _ in parsers.lineas_con_pagina(pdf)]

def _motivos(*paginas: str) -> dict[str, list[str]]:
    """Public CI documentation."""
    pdf = TextoPdf('sintetico.pdf', paginas=list(paginas))
    vivas = parsers.paginas_vivas(pdf)
    out: dict[str, list[str]] = {}
    for (i, k), motivo in sorted(parsers.motivos_de_enteros(vivas).items()):
        out.setdefault(vivas[i - 1][k].strip(), []).append(motivo)
    return out

def test_los_periodos_de_verificacion_se_conservan():
    """Public CI documentation."""
    lineas = _lineas('Contadores de gas\nPeriodo de verificacion (anos)\nMembrana deformable.\n10\nDesplazamiento rotativo.\n6\nTurbina.\n4\nConversor.\n4\n' + PROSA + '.\nFin del anexo.')
    texto = ' '.join(lineas)
    assert 'Membrana deformable. 10 Desplazamiento rotativo. 6 Turbina. 4 Conversor. 4' in texto

def test_la_tabla_de_muestreo_se_conserva():
    """Public CI documentation."""
    texto = ' '.join(_lineas('Plan de muestreo\nAceptación del lote\nRechazo del lote\n1\n2\n3\n4\n5\n6\n10\n11\n' + PROSA + '.\nFin del anexo.'))
    assert 'Aceptación del lote Rechazo del lote 1 2 3 4 5 6 10 11' in texto

def test_las_clases_y_sus_errores_se_conservan():
    """Public CI documentation."""
    texto = ' '.join(_lineas('Clase de exactitud\nError maximo\n0.5\n± 0,5 %\n1\n±1%\n2\n±2%\n' + PROSA + '.'))
    assert '0.5 ± 0,5 % 1 ±1% 2 ±2%' in texto

def test_la_tabla_de_la_prueba_de_p8_se_conserva():
    lineas = _lineas('ANEXO II\nTabla 1. Escalones de verificación\nEscalón\nCarga\n1\n100\n2\n500\nFin de la tabla.')
    assert '100' in lineas and '500' in lineas

def _pagina_numerada(desde: int, n: int) -> str:
    """Public CI documentation."""
    out = [f'Draft annex for consultation, page {desde}']
    for k in range(desde, desde + n):
        out += [f'{PROSA}, line {k} of the draft text', str(k)]
    out.append('End of page')
    return '\n'.join(out)

def test_la_numeracion_de_lineas_no_entra():
    """Public CI documentation."""
    paginas = [_pagina_numerada(1 + 10 * p, 10) for p in range(4)]
    assert not any((ln.strip().isdigit() for ln in _lineas(*paginas)))

def test_en_un_documento_numerado_no_entra_ni_lo_que_parece_celda():
    """Public CI documentation."""
    paginas = [_pagina_numerada(1 + 10 * p, 10) for p in range(3)]
    paginas.append('Annex table\nClass\nValue\nA\n7\nB\n9\nEnd of table')
    m = _motivos(*paginas)
    assert set(m['7']) == {'documento'} and set(m['9']) == {'documento'}

def _pagina_con_nota(p: int) -> str:
    """Public CI documentation."""
    return f'Guidance page {p}\n{PROSA}, paragraph {p}, in this guidance.\n{10 + 3 * p}\n{PROSA}, as described in paragraph {p}.\nEnd of page {p}'

def test_la_llamada_de_nota_entre_dos_frases_no_entra():
    """Public CI documentation."""
    paginas = [_pagina_con_nota(p) for p in range(4)]
    assert not any((ln.strip().isdigit() for ln in _lineas(*paginas)))

def test_la_llamada_de_nota_entre_lineas_cortas_tampoco_en_un_documento_con_notas():
    """Public CI documentation."""
    paginas = [_pagina_con_nota(p) for p in range(4)]
    paginas.append('Guidance page 4\nfinal remark.\n23\n4.3 Validation\nEnd of page 4')
    m = _motivos(*paginas)
    assert m['23'] == ['documento']

def test_el_numero_de_pagina_que_no_va_en_el_borde_no_entra():
    """Public CI documentation."""
    paginas = []
    for p in range(1, 9):
        paginas.append(f'Vocabulario, entrada {p}\nmagnitud {p}\nNota {p}\n{p + 4}\nJJCCGGMM {p}{p}')
    m = _motivos(*paginas)
    assert all((set(m[str(p + 4)]) == {'pagina'} for p in range(1, 9)))
    assert not any((ln.strip().isdigit() for ln in _lineas(*paginas)))

def test_los_numeros_de_pagina_del_indice_no_entran():
    """Public CI documentation."""
    indice = 'Índice\n1 Alcance\n1\n2 Referencias normativas\n2\n3 Términos y definiciones\n2\n5 Principios básicos\n10\n5.1 Generalidades\n10\nBibliografía'
    m = _motivos(indice, '1 Alcance\n' + PROSA + '.')
    assert set(m['10']) == {'indice'} and set(m['2']) == {'indice'}

def test_el_numero_de_pagina_que_abre_o_cierra_la_pagina_sigue_siendo_ruido():
    lineas = _lineas('12\nTexto de la pagina doce.\n13', 'Otra pagina.\n14')
    assert not any((ln.strip().isdigit() for ln in lineas))

def test_un_entero_entre_dos_parrafos_no_es_celda():
    """Public CI documentation."""
    m = _motivos(f'Titulo\n{PROSA} primero.\n3\n{PROSA} segundo.\nFin.')
    assert m['3'] == ['prosa']

def test_sin_enteros_sueltos_la_salida_es_la_de_antes_de_p8():
    """Public CI documentation."""
    pdf = TextoPdf('s.pdf', paginas=[f'{PROSA}.\n7\n{PROSA}.', 'Pagina 2\n8'])
    antes = [(ln.rstrip(), i) for i, pag in enumerate(pdf.paginas, start=1) for ln in pag.split('\n') if not any((r.match(ln) for r in parsers.RUIDO + (parsers.RE_NUMERO_SUELTO,)))]
    assert parsers.lineas_con_pagina(pdf) == antes

def test_la_cabecera_de_un_consolidado_no_pierde_lineas():
    """Public CI documentation."""
    pag1 = 'Referencia: BOE-A-2099-1\nOrden de prueba por la que se regula algo\nMinisterio de Pruebas\n«BOE» núm. 1, de 1 de enero de 2099\nDepartamento: Ministerio de Pruebas\nÍNDICE\nArtículo 1. Objeto y ambito de aplicacion de la orden de prueba\nTipo\nDato\n3\nArtículo 2. Definiciones . . . . . . . . 4\nTEXTO CONSOLIDADO\nÚltima modificación: 2 de febrero de 2099\nArtículo 1. Objeto.\nTexto del articulo uno.'
    pdf = TextoPdf('boe.pdf', paginas=[pag1])
    cab = next((p for p in parsers.analizar_boe(pdf).preceptos if p.ruta == 'cabecera'))
    assert '3' not in [ln.strip() for ln in cab.lineas]
    assert len(cab.lineas) == 8

def test_el_indice_del_boe_no_cierra_la_puerta_de_una_orden_con_tablas():
    """Public CI documentation."""
    indice = '\n'.join((f'Artículo {k}. Disposicion de prueba numero {k} . . . . . . . . . . . .\n{k + 2}' for k in range(1, 30)))
    pag1 = 'ÍNDICE\n' + indice + '\nTEXTO CONSOLIDADO'
    tabla = 'ANEXO III\nMembrana deformable.\n10\nDesplazamiento rotativo.\n6\nTurbina.\n4\nConversor.\n4\n' + PROSA + '.'
    pdf = TextoPdf('sintetico.pdf', paginas=[pag1, tabla])
    vivas = parsers.paginas_vivas(pdf)
    por_pagina: dict[int, set[str]] = {}
    for (i, _), motivo in parsers.motivos_de_enteros(vivas).items():
        por_pagina.setdefault(i, set()).add(motivo)
    assert por_pagina == {1: {'indice'}, 2: {'celda'}}
