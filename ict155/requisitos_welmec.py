"""Public CI documentation."""
from __future__ import annotations
import re
import sys
RE_CODIGO = '(?:[PULTSDO]\\d{1,2}|I\\d-\\d{1,2}|\\d-\\d{1,2})'
RE_ENCABEZADO = re.compile(f'^\\s*(?:Risk\\s+Class(?:es)?\\s+[A-E](?:\\s+to\\s+[A-E])?\\s+)?({RE_CODIGO})(?:\\s*:\\s*|\\s+(?=(?-i:[A-Z])))(.*)$')
RE_RIESGO = re.compile('^\\s*(?:Risk\\s+Class(?:es)?\\s+[A-E](?:\\s+to\\s+[A-E])?\\s*)+$')
RE_RUBRICA_DE_INSTRUMENTO = re.compile('^(?:examples of legally relevant|assignment of risk class\\s*$|other aspects\\b)')
RE_ENTRADA_DE_INDICE = re.compile('^(.*?)\\s*\\.{4,}\\s*(\\d+)\\s*$')
PAGINAS_DE_INDICE = (3, 4)
TITULO_PRIMERO = 'specific requirements for type p'
TITULO_DEL_FINAL = 'pattern for test report'
LARGO_MINIMO_DE_TITULO = 15
LARGO_MAXIMO_DE_TITULO_DE_BLOQUE = 80

def _norm(s: str) -> str:
    return ' '.join(s.replace('\xad', '').split()).casefold()

def _serie(codigo: str) -> str:
    """Public CI documentation."""
    return codigo.split('-')[0] if codigo.startswith('I') else codigo[0]

def _numero(codigo: str) -> int:
    return int(codigo.split('-')[1]) if codigo.startswith('I') else int(codigo[1:])

def titulos_del_indice(lp: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Public CI documentation."""
    entradas: list[tuple[str, int]] = []
    acumulado: list[str] = []
    for ln, pag in lp:
        if pag not in PAGINAS_DE_INDICE or not ln.strip():
            continue
        m = RE_ENTRADA_DE_INDICE.match(ln.strip())
        if m:
            entradas.append((_norm(' '.join(acumulado + [m.group(1)])), int(m.group(2))))
            acumulado = []
        else:
            acumulado.append(ln.strip())
    return entradas

def encabezados(lp: list[tuple[str, int]], desde: int, hasta: int) -> list[dict]:
    """Public CI documentation."""
    brutos = []
    for k, (ln, pag) in enumerate(lp):
        if not desde <= pag <= hasta:
            continue
        m = RE_ENCABEZADO.match(ln)
        if m:
            brutos.append({'k': k, 'codigo': m.group(1), 'pagina': pag, 'resto': m.group(2).strip()})
    salida: list[dict] = []
    for b in brutos:
        c = b['codigo']
        if re.fullmatch('\\d-\\d{1,2}', c):
            if not salida or salida[-1]['codigo'] != f"I{c.split('-')[0]}-{int(c.split('-')[1]) - 1}":
                continue
            b['codigo'] = 'I' + c
        salida.append(b)
    for b in salida:
        j = b['k'] - 1
        while j >= 0 and (not lp[j][0].strip() or RE_RIESGO.match(lp[j][0])):
            j -= 1
        b['inicio'] = j + 1 if j + 1 < b['k'] else b['k']
    return salida

def _es_titulo_del_indice(ln: str, pag: int, titulos: list[tuple[str, int]]) -> bool:
    n = _norm(ln)
    return len(n) >= LARGO_MINIMO_DE_TITULO and any((p == pag and (n == t or t.startswith(n)) for t, p in titulos))

def fines(lp: list[tuple[str, int]], bloques: list[dict], titulos: list[tuple[str, int]]) -> None:
    """Public CI documentation."""
    for i, b in enumerate(bloques):
        sigue = bloques[i + 1] if i + 1 < len(bloques) else None
        limite = sigue['inicio'] if sigue else len(lp)
        ultimo_de_serie = sigue is None or _serie(sigue['codigo']) != _serie(b['codigo'])
        b['fin'], b['motivo'] = (limite, 'siguiente' if sigue else 'fin del documento')
        for j in range(b['k'] + 1, limite):
            ln, pag = lp[j]
            if _es_titulo_del_indice(ln, pag, titulos):
                b['fin'], b['motivo'] = (j, 'titulo del indice')
                break
            if ultimo_de_serie and b['codigo'].startswith('I') and RE_RUBRICA_DE_INSTRUMENTO.match(_norm(ln)):
                b['fin'], b['motivo'] = (j, 'rubrica de instrumento')
                break

def comprobar(bloques: list[dict]) -> str | None:
    """Public CI documentation."""
    vistos: dict[str, list[int]] = {}
    for b in bloques:
        vistos.setdefault(_serie(b['codigo']), []).append(_numero(b['codigo']))
    for s, numeros in vistos.items():
        if numeros != list(range(1, len(numeros) + 1)):
            return f'la serie {s} no es continua: {numeros}'
    return None

def titulo_del_bloque(resto: str) -> str | None:
    """Public CI documentation."""
    if resto and len(resto) <= LARGO_MAXIMO_DE_TITULO_DE_BLOQUE and (not resto.endswith('.')):
        return resto
    return None

def partir_en_requisitos(preceptos: list, lp: list[tuple[str, int]], precepto_cls) -> list:
    """Public CI documentation."""
    if sum((len(p.lineas) for p in preceptos)) != len(lp):
        print('aviso: los preceptos de la WELMEC 7.2 no cubren el flujo linea a linea; no se sacan los requisitos', file=sys.stderr)
        return preceptos
    titulos = titulos_del_indice(lp)
    primero = next((p for t, p in titulos if t.startswith(TITULO_PRIMERO)), None)
    final = next((p for t, p in titulos if t.startswith(TITULO_DEL_FINAL)), None)
    if primero is None or final is None:
        print('aviso: la WELMEC 7.2 no trae el indice esperado; no se sacan los requisitos', file=sys.stderr)
        return preceptos
    bloques = encabezados(lp, primero, final)
    motivo = comprobar(bloques) if bloques else 'ningun encabezado'
    if motivo:
        print(f'aviso: bloques de requisito de la WELMEC 7.2 sin sacar ({motivo})', file=sys.stderr)
        return preceptos
    fines(lp, bloques, titulos)
    dueno = [i for i, p in enumerate(preceptos) for _ in p.lineas]
    local = [j for p in preceptos for j in range(len(p.lineas))]
    de_bloque: list[int | None] = [None] * len(lp)
    for n, b in enumerate(bloques):
        for k in range(b['inicio'], b['fin']):
            de_bloque[k] = n
    nuevos: list[tuple[int, object]] = []
    for n, b in enumerate(bloques):
        ks = range(b['inicio'], b['fin'])
        lineas = [preceptos[dueno[k]].lineas[local[k]] for k in ks]
        con_texto = [k for k in ks if lp[k][0].strip()]
        nuevos.append((dueno[b['inicio']], precepto_cls(ruta=f"req.{b['codigo']}", tipo='requisito', numero=b['codigo'], etiqueta=f"Requisito {b['codigo']}", titulo=titulo_del_bloque(b['resto']), lineas=lineas, pagina_inicio=lp[con_texto[0]][1], pagina_fin=lp[con_texto[-1]][1])))
    vivos: list = []
    muertos: dict[str, str | None] = {}
    k0 = 0
    for i, p in enumerate(preceptos):
        ks = range(k0, k0 + len(p.lineas))
        k0 += len(p.lineas)
        quedan = [k for k in ks if de_bloque[k] is None]
        con_texto = [k for k in quedan if lp[k][0].strip()]
        if not con_texto:
            muertos[p.ruta] = p.padre
            continue
        p.lineas = [p.lineas[local[k]] for k in quedan]
        p.pagina_inicio, p.pagina_fin = (lp[con_texto[0]][1], lp[con_texto[-1]][1])
        vivos.append((i, p))
    for _, p in vivos:
        while p.padre in muertos:
            p.padre = muertos[p.padre]
    salida: list = []
    vivos_ids = {id(p) for _, p in vivos}
    for i, p in enumerate(preceptos):
        if id(p) in vivos_ids:
            salida.append(p)
        salida.extend((q for j, q in nuevos if j == i))
    return salida
