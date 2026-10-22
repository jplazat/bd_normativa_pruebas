"""Public CI documentation."""
from __future__ import annotations
import math
import re
import sqlite3
from collections import Counter
DDL = 'CREATE TABLE IF NOT EXISTS mobiliario (documento_id INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE, patron TEXT NOT NULL, PRIMARY KEY (documento_id, patron))'
MINIMO_PAGINAS = 4
POSICIONES = 3
UMBRAL_PAGINAS = 0.3
UMBRAL_NUMERO_DE_PAGINA = 0.8
LARGO_MAX = 160
VECINOS = 4
RX_PALABRA = re.compile('[^\\W\\d_]{2,}')
RX_NUMERO_SUELTO = '\\d{1,4}'

def _linea(s: str) -> str:
    return ' '.join(s.split())

def detectar(pdf) -> list[str]:
    """Public CI documentation."""
    from .parsers import lineas_repetidas, textos_de_maquetacion_en_tirada
    if pdf.n_paginas < MINIMO_PAGINAS:
        return []
    out = _repetidas_en_el_borde(pdf.paginas, lineas_repetidas(pdf))
    out |= set(_con_numero_de_pagina(pdf.paginas))
    out |= {_linea(t) for t in textos_de_maquetacion_en_tirada(pdf)}
    return sorted((p for p in out if p and len(p) <= LARGO_MAX))

def _repetidas_en_el_borde(paginas: list[str], repetidas: set[str]) -> set[str]:
    """Public CI documentation."""
    en_borde: Counter = Counter()
    en_total: Counter = Counter()
    for pag in paginas:
        lineas = [t for t in (_linea(x) for x in pag.splitlines()) if t]
        borde = set(lineas[:POSICIONES] + lineas[-POSICIONES:])
        for t in set(lineas):
            en_total[t] += 1
            if t in borde:
                en_borde[t] += 1
    out = set()
    for r in repetidas:
        t = _linea(r)
        if en_total[t] and en_borde[t] >= UMBRAL_NUMERO_DE_PAGINA * en_total[t]:
            out.add(t)
    return out

def _con_numero_de_pagina(paginas: list[str]) -> list[str]:
    n = len(paginas)
    grupos: dict[str, list[tuple[int, str]]] = {}
    for i, pag in enumerate(paginas):
        lineas = [t for t in (_linea(x) for x in pag.split('\n')) if t]
        vistas = set()
        for t in lineas[:POSICIONES] + lineas[-POSICIONES:]:
            if not re.search('\\d', t) or '#' in t or len(t) > LARGO_MAX:
                continue
            clave = re.sub('\\d+', '#', t).casefold()
            if clave in vistas:
                continue
            vistas.add(clave)
            grupos.setdefault(clave, []).append((i, t))
    minimo = max(MINIMO_PAGINAS, math.ceil(n * UMBRAL_PAGINAS))
    out = []
    for apariciones in grupos.values():
        if len(apariciones) < minimo:
            continue
        patron = _patron([t for _, t in apariciones])
        if '#' in patron and _lleva_numero_de_pagina(apariciones):
            out.append(patron)
    return out

def _lleva_numero_de_pagina(apariciones: list[tuple[int, str]]) -> bool:
    """Public CI documentation."""
    partes = [(i, re.split('(\\d+)', t)) for i, t in apariciones]
    base = partes[0][1]
    if any((len(p) != len(base) for _, p in partes)):
        return False
    for j in range(1, len(base), 2):
        if all((p[j] == base[j] for _, p in partes)):
            continue
        desfases = Counter((int(p[j]) - i for i, p in partes))
        if desfases.most_common(1)[0][1] >= UMBRAL_NUMERO_DE_PAGINA * len(partes):
            return True
    return False

def _patron(lineas: list[str]) -> str:
    """Public CI documentation."""
    partes = [re.split('(\\d+)', t) for t in lineas]
    base = partes[0]
    res = []
    for j, trozo in enumerate(base):
        if j % 2 == 0:
            res.append(trozo)
        else:
            res.append(trozo if all((len(p) == len(base) and p[j] == trozo for p in partes)) else '#')
    return ''.join(res)

def guardar(con: sqlite3.Connection, documento_id: int, pdf) -> int:
    """Public CI documentation."""
    con.execute(DDL)
    con.execute('DELETE FROM mobiliario WHERE documento_id=?', (documento_id,))
    patrones = detectar(pdf)
    con.executemany('INSERT INTO mobiliario (documento_id, patron) VALUES (?,?)', [(documento_id, p) for p in patrones])
    return len(patrones)

def _es_largo(patron: str) -> bool:
    return len(RX_PALABRA.findall(patron)) >= 2 and len(patron) >= 8

def compilar(patrones, normalizar) -> re.Pattern | None:
    """Public CI documentation."""
    largos, cortos = ([], [])
    for p in patrones:
        n = ' '.join(normalizar(p).split())
        if not n or n == '#':
            continue
        rx = ' '.join((re.escape(tok).replace('\\#', RX_NUMERO_SUELTO) for tok in n.split(' ')))
        (largos if _es_largo(p) else cortos).append(rx)
    if not largos:
        return None
    largos.sort(key=len, reverse=True)
    cortos.sort(key=len, reverse=True)
    largo = '(?:' + '|'.join(largos) + ')'
    elemento = '(?:' + '|'.join(largos + cortos + [RX_NUMERO_SUELTO]) + ')'
    tirada = f'(?<!\\S)(?:{elemento} ){{0,{VECINOS}}}{largo}(?: {elemento}){{0,{VECINOS}}}(?!\\S)'
    return re.compile(tirada)

def quitar(texto: str, rx: re.Pattern | None) -> str:
    """Public CI documentation."""
    if rx is None:
        return texto
    return ' '.join(rx.sub(' ', texto).split())

def patrones_de(con: sqlite3.Connection, ruta_relativa: str | None) -> tuple[str, ...]:
    """Public CI documentation."""
    if not ruta_relativa:
        return ()
    try:
        filas = con.execute('SELECT m.patron FROM mobiliario m JOIN documento d ON d.id=m.documento_id WHERE d.ruta_relativa=? ORDER BY m.patron', (ruta_relativa,)).fetchall()
    except sqlite3.OperationalError:
        return ()
    return tuple((f[0] for f in filas))
