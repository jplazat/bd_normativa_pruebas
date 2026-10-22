"""Public CI documentation."""
from __future__ import annotations
import re
from bisect import bisect_right
from .parsers import Precepto, lineas_con_pagina
TROZOS = (80, 50, 30)
RE_GUION_SUAVE = re.compile('\xad\\s*')
RE_MARCAS_EURLEX = re.compile('[►◄▼]\\s*(?:[A-Z]{1,2}\\d{1,3}\\b|[A-Z]\\b)?')
RE_PALABRA_PARTIDA = re.compile('\\w-$')
RE_EMPIEZA_PALABRA = re.compile('\\w')

def _linea(ln: str) -> str:
    return ' '.join(RE_MARCAS_EURLEX.sub('', RE_GUION_SUAVE.sub('', ln)).split())

class _Texto:
    """Public CI documentation."""

    def __init__(self):
        self.partes: list[str] = []
        self.largo = 0
        self.ultima = ''
        self.suave = False

    def anadir(self, ln: str):
        """Public CI documentation."""
        suave = ln.rstrip().endswith('\xad')
        ln = _linea(ln)
        if not ln:
            return None
        previa = self.largo
        if self.partes:
            if self.suave and RE_EMPIEZA_PALABRA.match(ln):
                pass
            elif RE_PALABRA_PARTIDA.search(self.ultima) and RE_EMPIEZA_PALABRA.match(ln):
                self.ultima = self.ultima[:-1]
                self.partes[-1] = self.ultima
                self.largo -= 1
                previa = self.largo
            else:
                self.partes.append(' ')
                self.largo += 1
        inicio = self.largo
        self.partes.append(ln)
        self.ultima = ln
        self.suave = suave
        self.largo += len(ln)
        return (inicio, previa)

    def texto(self) -> str:
        return ''.join(self.partes)

def _texto_de(lineas: list[str]) -> str:
    """Public CI documentation."""
    t = _Texto()
    for ln in lineas:
        t.anadir(ln)
    s = t.texto()
    return s[:-1] if RE_PALABRA_PARTIDA.search(s) else s

class _Documento:
    """Public CI documentation."""

    def __init__(self, pdf):
        armado = _Texto()
        n = max(pdf.n_paginas, len(pdf.paginas))
        inicio: dict[int, int] = {}
        fin: dict[int, int] = {}
        anterior = None
        for ln, pag in lineas_con_pagina(pdf):
            puesta = armado.anadir(ln)
            if puesta is None:
                continue
            if pag != anterior:
                if anterior is not None:
                    fin[anterior] = puesta[1]
                inicio[pag] = puesta[0]
                anterior = pag
            n = max(n, pag)
        self.texto = armado.texto()
        if anterior is not None:
            fin[anterior] = len(self.texto)
        self.n = n
        self.inicios = [0] * n
        self.fines = [0] * n
        siguiente = len(self.texto) + 1
        for pag in range(n, 0, -1):
            siguiente = inicio.get(pag, siguiente)
            self.inicios[pag - 1] = siguiente
        previo = 0
        for pag in range(1, n + 1):
            previo = fin.get(pag, previo)
            self.fines[pag - 1] = previo

    def desde(self, pagina: int) -> int:
        """Public CI documentation."""
        return self.inicios[min(max(pagina, 1), self.n) - 1]

    def hasta(self, pagina: int) -> int:
        """Public CI documentation."""
        return self.fines[min(max(pagina, 1), self.n) - 1]

    def pagina_de(self, posicion: int) -> int:
        """Public CI documentation."""
        return max(1, bisect_right(self.inicios, posicion))

    def apariciones(self, trozo: str, desde: int, hasta: int):
        i = self.texto.find(trozo, desde, hasta)
        while i >= 0:
            yield i
            i = self.texto.find(trozo, i + 1, hasta)

    def unica(self, trozo: str, desde: int, hasta: int) -> int:
        """Public CI documentation."""
        i = self.texto.find(trozo, desde, hasta)
        return -1 if i >= 0 and self.texto.find(trozo, i + 1, hasta) >= 0 else i

    def comienzo(self, t: str, desde: int, hasta: int) -> int:
        """Public CI documentation."""
        if not t:
            return -1
        for k in TROZOS:
            if k != TROZOS[0]:
                i = self.unica(t[:k], desde, hasta)
            else:
                i = -1
                for a in self.apariciones(t[:k], desde, hasta):
                    if self.texto.startswith(t, a):
                        i = a
                        break
                    if i < 0:
                        i = a
            if i >= 0:
                return i
        return -1

    def final(self, t: str, desde: int, hasta: int) -> int:
        """Public CI documentation."""
        if not t:
            return -1
        esperado = desde + len(t)
        if esperado <= hasta and self.texto.startswith(t, desde):
            return esperado
        for k in TROZOS:
            trozo = t[-k:]
            if k != TROZOS[0]:
                i = self.unica(trozo, desde, hasta)
            else:
                i = min(self.apariciones(trozo, desde, hasta), key=lambda a: abs(a + len(trozo) - esperado), default=-1)
            if i >= 0:
                return i + len(trozo)
        return -1

def _padre_primero(preceptos: list[Precepto], por_ruta: dict[str, Precepto]) -> list[Precepto]:
    """Public CI documentation."""
    puesto: dict[str, int] = {}
    for k, p in enumerate(preceptos):
        puesto.setdefault(p.ruta, k)
    if all((p.padre not in puesto or puesto[p.padre] < k for k, p in enumerate(preceptos))):
        return preceptos

    def profundidad(p: Precepto) -> int:
        vistos, n, q = ({p.ruta}, 0, p)
        while q.padre in por_ruta and q.padre not in vistos:
            vistos.add(q.padre)
            q = por_ruta[q.padre]
            n += 1
        return n
    return sorted(preceptos, key=profundidad)

def afinar(preceptos: list[Precepto], pdf) -> dict:
    """Public CI documentation."""
    cuentas = {'afinados': 0, 'estrechados': 0, 'sin_cambio_ya_una_pagina': 0, 'se_queda_el_del_padre': 0}
    if not preceptos or not pdf.paginas:
        return cuentas
    por_ruta: dict[str, Precepto] = {}
    for p in preceptos:
        por_ruta.setdefault(p.ruta, p)
    original = {r: (p.pagina_inicio, p.pagina_fin) for r, p in por_ruta.items()}
    if not any((p.padre in por_ruta and p.padre != p.ruta and ((p.pagina_inicio, p.pagina_fin) == original[p.padre]) for p in preceptos)):
        return cuentas
    con_hijos = {p.padre for p in preceptos if p.padre}
    doc = _Documento(pdf)
    comienzo: dict[str, int] = {}
    cursor: dict[str, int] = {}
    for p in _padre_primero(preceptos, por_ruta):
        padre = por_ruta.get(p.padre) if p.padre else None
        if padre is p:
            padre = None
        if padre is None or (p.pagina_inicio, p.pagina_fin) != original[padre.ruta]:
            if p.ruta in con_hijos and p.ruta not in comienzo:
                desde, hasta = (doc.desde(p.pagina_inicio), doc.hasta(p.pagina_fin))
                i = doc.comienzo(_texto_de(p.lineas), desde, hasta)
                comienzo[p.ruta] = i if i >= 0 else desde
            continue
        antes = (p.pagina_inicio, p.pagina_fin)
        if p.pagina_inicio == p.pagina_fin:
            cuentas['sin_cambio_ya_una_pagina'] += 1
            continue
        ini_pag, fin_pag = (max(padre.pagina_inicio, p.pagina_inicio), min(padre.pagina_fin, p.pagina_fin))
        desde = max(doc.desde(ini_pag), comienzo.get(padre.ruta, 0), cursor.get(padre.ruta, 0))
        hasta = doc.hasta(fin_pag)
        t = _texto_de(p.lineas)
        i = doc.comienzo(t, desde, hasta)
        f = doc.final(t, i, hasta) if i >= 0 else -1
        if i >= 0 and f > i:
            inicio, fin = (doc.pagina_de(i), doc.pagina_de(f - 1))
            if max(padre.pagina_inicio, p.pagina_inicio) <= inicio <= fin <= min(padre.pagina_fin, p.pagina_fin):
                p.pagina_inicio, p.pagina_fin = (inicio, fin)
                comienzo[p.ruta] = i
                cursor[padre.ruta] = i + 1
                cuentas['afinados'] += 1
                cuentas['estrechados'] += (inicio, fin) != antes
                continue
        comienzo[p.ruta] = desde
        cuentas['se_queda_el_del_padre'] += 1
    return cuentas
