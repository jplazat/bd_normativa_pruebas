"""Public CI documentation."""
from __future__ import annotations
import re
import unicodedata
from collections import Counter, defaultdict
FRANJA_DE_LA_PAGINA = 0.11
UMBRAL_DE_PAGINAS = 0.3
MINIMO_DE_PAGINAS = 3
TOLERANCIA_EN_Y = 2.0
ALTURAS_COMUNES = 2
PARTE_EN_LA_MISMA_ALTURA = 0.7
RE_FRACCION = re.compile('[a-z]{0,3}\\s*#\\s*/\\s*#')
MAXIMO_DE_LINEAS_POR_TRAMO = 8
MUESTRA_DE_PAGINAS = 10
UMBRAL_DE_TABLA = 0.2
UMBRAL_DE_COLUMNAS = 0.5
FILAS_DE_UNA_TABLA = 2
AREA_DENTRO_DE_LA_TABLA = 0.5
SEPARACION_DE_FILAS = 2.2
TOLERANCIA_EN_X = 3.0

def normalizar(s: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', s).replace('\xad', '').split())

def forma(s: str) -> str:
    """Public CI documentation."""
    return re.sub('\\d+', '#', normalizar(s).casefold())

def esqueleto(s: str) -> str:
    """Public CI documentation."""
    return re.sub('[\\W_]+', '', unicodedata.normalize('NFKC', s).casefold())

def lineas_de_franja(pagina) -> list[tuple[str, str, float, float, float, float]]:
    """Public CI documentation."""
    import fitz
    altura = pagina.rect.height
    d = pagina.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    out = []
    for b in d.get('blocks', []):
        for ln in b.get('lines', []):
            if not any((s['text'].strip() for s in ln['spans'])):
                continue
            texto = normalizar(''.join((s['text'] for s in ln['spans'])))
            if not texto:
                continue
            x0, y0, x1, y1 = ln['bbox']
            if y1 <= FRANJA_DE_LA_PAGINA * altura:
                out.append((texto, 'arriba', round(y0, 1), x0, x1, y1))
            elif y0 >= (1 - FRANJA_DE_LA_PAGINA) * altura:
                out.append((texto, 'abajo', round(y0, 1), x0, x1, y1))
    return out

def formas_confirmadas(lineas_por_pagina: list[list[tuple]]) -> set[tuple[str, str]]:
    """Public CI documentation."""
    n = len(lineas_por_pagina)
    if n < 4:
        return set()
    umbral = max(MINIMO_DE_PAGINAS, int(UMBRAL_DE_PAGINAS * n))
    apariciones: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for pn, lns in enumerate(lineas_por_pagina, start=1):
        for texto, lado, y0, *_ in lns:
            apariciones[forma(texto), lado].append((pn, y0))
    confirmadas = set()
    for clave, apar in apariciones.items():
        f = clave[0]
        if len({p for p, _ in apar}) < umbral or not (sum((ch.isalpha() for ch in f)) >= 2 or RE_FRACCION.fullmatch(f)):
            continue
        alturas = [y for y, _ in Counter((round(y) for _, y in apar)).most_common(ALTURAS_COMUNES)]
        if sum((1 for _, y in apar if any((abs(y - a) <= TOLERANCIA_EN_Y for a in alturas)))) >= PARTE_EN_LA_MISMA_ALTURA * len(apar):
            confirmadas.add(clave)
    return confirmadas

def _muestra(paginas: list[int], n: int) -> list[int]:
    """Public CI documentation."""
    if len(paginas) <= n:
        return list(paginas)
    return [paginas[round(i * (len(paginas) - 1) / (n - 1))] for i in range(n)]

def _tablas_de_la_pagina(pagina) -> list[tuple] | None:
    """Public CI documentation."""
    try:
        return [tuple(t.bbox) for t in pagina.find_tables().tables if t.row_count >= FILAS_DE_UNA_TABLA]
    except Exception:
        return None

def _cajas_de_la_pagina(pagina) -> list[tuple]:
    import fitz
    d = pagina.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    return [tuple(ln['bbox']) for b in d.get('blocks', []) for ln in b.get('lines', []) if any((s['text'].strip() for s in ln['spans']))]

def _dentro_de_una_tabla(caja: tuple, tablas: list[tuple]) -> bool:
    x0, y0, x1, y1 = caja
    area = max((x1 - x0) * (y1 - y0), 1e-06)
    for tx0, ty0, tx1, ty1 in tablas:
        ancho, alto = (min(x1, tx1) - max(x0, tx0), min(y1, ty1) - max(y0, ty0))
        if ancho > 0 and alto > 0 and (ancho * alto / area >= AREA_DENTRO_DE_LA_TABLA):
            return True
    return False

def _en_columnas_alineadas(caja: tuple, lado: str, cajas: list[tuple]) -> bool:
    """Public CI documentation."""
    x0, y0, x1, y1 = caja
    alto = max(y1 - y0, 6.0)
    centro = (y0 + y1) / 2
    fila = [c for c in cajas if abs((c[1] + c[3]) / 2 - centro) <= alto / 2]
    columnas = sorted({round(c[0]) for c in fila})
    if len(columnas) < 2:
        return False
    contigua = [c for c in cajas if (0.5 * alto < (c[1] + c[3]) / 2 - centro <= SEPARACION_DE_FILAS * alto if lado == 'arriba' else 0.5 * alto < centro - (c[1] + c[3]) / 2 <= SEPARACION_DE_FILAS * alto)]
    if not contigua:
        return False
    x_contiguas = {round(c[0]) for c in contigua}
    return sum((1 for x in columnas if any((abs(x - z) <= TOLERANCIA_EN_X for z in x_contiguas)))) >= 2

def estadisticas_de_tabla(doc, lineas_por_pagina: list[list[tuple]], confirmadas: set[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """Public CI documentation."""
    apariciones: dict[tuple[str, str], list[tuple[int, tuple]]] = defaultdict(list)
    for pn, lns in enumerate(lineas_por_pagina, start=1):
        for texto, lado, _y0, x0, x1, y1 in lns:
            clave = (forma(texto), lado)
            if clave in confirmadas:
                apariciones[clave].append((pn, (x0, _y0, x1, y1)))
    tablas: dict[int, list[tuple] | None] = {}
    cajas: dict[int, list[tuple]] = {}
    estadisticas = {}
    for clave, apar in apariciones.items():
        muestra = set(_muestra(sorted({p for p, _ in apar}), MUESTRA_DE_PAGINAS))
        elegidas = [(p, c) for p, c in apar if p in muestra]
        en_tabla = alineadas = 0
        for p, caja in elegidas:
            if p not in tablas:
                tablas[p] = _tablas_de_la_pagina(doc[p - 1])
                cajas[p] = _cajas_de_la_pagina(doc[p - 1])
            if tablas[p] is None or _dentro_de_una_tabla(caja, tablas[p]):
                en_tabla += 1
            if _en_columnas_alineadas(caja, clave[1], cajas[p]):
                alineadas += 1
        estadisticas[clave] = dict(muestras=len(elegidas), en_tabla=en_tabla, alineadas=alineadas)
    return estadisticas

def es_de_tabla(estadistica: dict) -> bool:
    n = max(estadistica['muestras'], 1)
    return estadistica['en_tabla'] / n >= UMBRAL_DE_TABLA or estadistica['alineadas'] / n >= UMBRAL_DE_COLUMNAS

def _leer_formas(ruta, n_paginas: int):
    """Public CI documentation."""
    try:
        import fitz
        doc = fitz.open(str(ruta))
    except Exception:
        return None
    try:
        lineas = [lineas_de_franja(p) for p in doc]
        if len(lineas) != n_paginas:
            return None
        confirmadas = formas_confirmadas(lineas)
        return (lineas, confirmadas, estadisticas_de_tabla(doc, lineas, confirmadas))
    except Exception:
        return None
    finally:
        doc.close()

def piezas_de_maquetacion(ruta, n_paginas: int) -> list[list[str]] | None:
    """Public CI documentation."""
    leido = _leer_formas(ruta, n_paginas)
    if leido is None:
        return None
    lineas, confirmadas, estadisticas = leido
    validas = {clave for clave in confirmadas if not es_de_tabla(estadisticas[clave])}
    return [[l[0] for l in lns if (forma(l[0]), l[1]) in validas] for lns in lineas]

def formas_del_documento(ruta, n_paginas: int) -> list[dict] | None:
    """Public CI documentation."""
    leido = _leer_formas(ruta, n_paginas)
    if leido is None:
        return None
    lineas, confirmadas, estadisticas = leido
    datos: dict[tuple[str, str], dict] = {}
    for pn, lns in enumerate(lineas, start=1):
        for texto, lado, y0, *_ in lns:
            clave = (forma(texto), lado)
            if clave in confirmadas:
                d = datos.setdefault(clave, dict(forma=clave[0], lado=lado, paginas=set(), ejemplo=texto, alturas=Counter()))
                d['paginas'].add(pn)
                d['alturas'][round(y0)] += 1
    salida = []
    for clave, d in datos.items():
        e = estadisticas[clave]
        salida.append(dict(forma=d['forma'], lado=d['lado'], paginas=len(d['paginas']), cobertura=len(d['paginas']) / n_paginas, ejemplo=d['ejemplo'], alturas=dict(d['alturas'].most_common(3)), muestras=e['muestras'], en_tabla=e['en_tabla'], alineadas=e['alineadas'], vetada=es_de_tabla(e)))
    return sorted(salida, key=lambda x: (x['lado'], -x['paginas']))

def _cubrir(resto: str, esq: list[str], libres: frozenset[int]) -> list[int] | None:
    """Public CI documentation."""
    if not resto:
        return []
    for k in sorted(libres):
        if esq[k] and resto.startswith(esq[k]):
            r = _cubrir(resto[len(esq[k]):], esq, libres - {k})
            if r is not None:
                return [k] + r
    return None

def _es_principio(resto: str, esq: list[str], libres: frozenset[int]) -> bool:
    """Public CI documentation."""
    if not resto:
        return True
    for k in libres:
        if not esq[k]:
            continue
        if esq[k].startswith(resto):
            return True
        if resto.startswith(esq[k]) and _es_principio(resto[len(esq[k]):], esq, libres - {k}):
            return True
    return False

def tramos_de_piezas(lineas: list[str], piezas: list[str]) -> tuple[list[tuple[int, int, list[int]]], list[int]]:
    """Public CI documentation."""
    esq_l = [esqueleto(x) for x in lineas]
    esq_p = [esqueleto(x) for x in piezas]
    libres = frozenset((k for k in range(len(piezas)) if esq_p[k]))
    tramos: list[tuple[int, int, list[int]]] = []
    i, n = (0, len(lineas))
    while i < n and libres:
        if not esq_l[i]:
            i += 1
            continue
        acum, hallado = ('', False)
        for j in range(i, min(n, i + MAXIMO_DE_LINEAS_POR_TRAMO)):
            acum += esq_l[j]
            if not acum:
                continue
            usadas = _cubrir(acum, esq_p, libres)
            if usadas is not None:
                tramos.append((i, j, usadas))
                libres = libres - set(usadas)
                i, hallado = (j + 1, True)
                break
            if not _es_principio(acum, esq_p, libres):
                break
        if not hallado:
            i += 1
    sin_usar = sorted(set(range(len(piezas))) - {k for _, _, u in tramos for k in u})
    return (tramos, sin_usar)
