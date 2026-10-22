"""Tablas con estructura: filas y celdas, no una linea de texto.

El problema, y lleva tres casos del arnes en rojo desde el principio: una tabla
de dos dimensiones **no tiene linealizacion canonica**. Quien la cita la lee por
filas e inserta signos que representan su estructura («Clase: 0,2 / 0,5 / 1 /
2»); la extraccion lineal devuelve las celdas por columnas («Clase 0,2 0,5
Errores maximos permitidos. ± 0,2 °C»). Ninguna de las dos es incorrecta y
compararlas como cadena no esta bien definido.

Se intento antes acertar con la linealizacion, leyendo por filas. Resolvia el
contenido en aislado (N53 3/3, N40 3/7) pero al integrarlo no movia la puerta 1,
empeoraba la 2 y triplicaba el tiempo de pruebas. La medicion sigue en
`pruebas/medir_tablas.py`.

Aqui el planteamiento es otro: **no hace falta linealizar**. La tabla se guarda
con su estructura y una cita se verifica comprobando que cada valor esta y en
que fila y columna, que es ademas lo que un revisor necesita saber.

Coste: `find_tables()` solo se ejecuta sobre la pagina en que empieza un
precepto de tipo tabla, anexo o apendice (`ingesta.ingerir_celdas`; un anexo
puede ser entero una tabla). Cuando eran solo los de tipo tabla se midieron 86
paginas de varios miles y 23 s en la ingesta. Cero en cada pasada de pruebas.
"""
from __future__ import annotations

import collections
import re
import unicodedata

from . import config, superindices
from .extraccion import quitar_marca_de_agua


def norm(s: str) -> str:
    """Para comparar celdas: sin acentos, sin puntuacion, en minusculas.

    El grado centigrado y el signo mas-menos SI se conservan: en una tabla de
    metrologia son el dato, no puntuacion. Quitarlos haria que "± 0,5 °C" y
    "0,5" fueran la misma celda.
    """
    s = unicodedata.normalize("NFD", superindices.plegar(s or "").lower())   # R14: «10⁻⁶» y «10-6» son la misma celda
    s = "".join(c for c in s if unicodedata.category(c) != "Mn" or c in "̧")
    s = s.replace(",", ".")
    return re.sub(r"[^a-z0-9.±°<>≤≥/+-]+", " ", s).strip()


def rejillas_de_pagina(doc, pagina: int,
                      fallos: list[str] | None = None) -> list[list[list[str]]]:
    """Las tablas de una pagina, cada una como lista de filas de celdas.

    Si PyMuPDF no puede analizar la pagina, la excepcion SUBE: antes se
    devolvia [] y la tabla se quedaba sin celdas sin que nada lo registrara.
    `ingesta.ingerir_celdas` la cuenta junto a los fallos de abrir el documento.
    Si falla UNA tabla de la pagina, se salta esa y se conservan las demas,
    como hasta ahora, pero se anota en `fallos` cuando quien llama lo pasa.
    """
    tablas = doc[pagina - 1].find_tables().tables
    out = []
    for i, t in enumerate(tablas):
        try:
            filas = t.extract()
        except Exception as e:                               # noqa: BLE001
            if fallos is not None:
                fallos.append(f"p.{pagina} tabla {i + 1}: {type(e).__name__}")
            continue
        limpia = [[(c or "").strip() for c in fila] for fila in filas]
        if any(any(c for c in fila) for fila in limpia):
            out.append(limpia)
    return out


def _puntuacion(rejilla: list[list[str]], texto_precepto: str) -> int:
    """Cuantas celdas de la rejilla aparecen en el texto lineal del precepto.

    Una pagina puede tener varias tablas y el precepto es una de ellas. La que
    mas comparte con el texto ya almacenado es la suya: se usa el propio texto
    lineal, que es imperfecto para citar pero perfectamente bueno para decidir
    de cual de las tablas de la pagina estamos hablando.
    """
    t = norm(texto_precepto)
    n = 0
    for fila in rejilla:
        for c in fila:
            v = norm(c)
            if len(v) >= 2 and v in t:
                n += 1
    return n


def rejilla_del_precepto(doc, pagina: int, texto_precepto: str,
                         fallos: list[str] | None = None):
    """La tabla de la pagina que corresponde a este precepto, o None."""
    rejillas = rejillas_de_pagina(doc, pagina, fallos)
    if not rejillas:
        return None
    mejor = max(rejillas, key=lambda r: _puntuacion(r, texto_precepto))
    return mejor if _puntuacion(mejor, texto_precepto) >= 2 else None


def celdas(rejilla: list[list[str]]):
    """Las celdas no vacias, con su fila y su columna."""
    for i, fila in enumerate(rejilla):
        for j, valor in enumerate(fila):
            v = (valor or "").strip()
            # Una celda cuya forma normalizada queda vacia (un guion largo, una
            # barra, un signo de "sin dato") no se puede situar nunca, asi que
            # guardarla solo anade ruido a la tabla.
            if v and norm(v):
                yield i, j, v, norm(v)


def ubicar(con, precepto_id: int, valor: str) -> list[tuple[int, int, str]]:
    """Donde esta un valor dentro de una tabla ya almacenada.

    Devuelve las posiciones (fila, columna, valor) que lo contienen. Es lo que
    convierte "el valor esta" en una verificacion util: un revisor necesita
    saber en que fila y columna mirar, no solo que el numero aparece en algun
    sitio de la pagina.
    """
    v = norm(valor)
    if not v:
        return []
    exactas = con.execute(
        "SELECT fila, columna, valor FROM celda WHERE precepto_id=? AND valor_norm=?",
        (precepto_id, v)).fetchall()
    if exactas:
        return [tuple(r) for r in exactas]
    return [tuple(r) for r in con.execute(
        "SELECT fila, columna, valor FROM celda WHERE precepto_id=? "
        "AND (valor_norm LIKE ? OR ? LIKE '%'||valor_norm||'%') AND length(valor_norm)>1",
        (precepto_id, f"%{v}%", v)).fetchall()]


def abrir(ruta_rel: str):
    import fitz
    return fitz.open(config.ruta_biblioteca(ruta_rel))


# ============================================================================
# LAS TABLAS DE TODAS LAS PAGINAS DE UNA GUIA (4-oct-2026, hecho en local).
# Peticion de la persona responsable: "que cada celda conserve su columna". Lo de arriba solo mira
# los preceptos de tipo tabla, anexo o apendice, y solo la pagina en que empiezan:
# las guias que son tablas de principio a fin (WELMEC 8.6, 8.1, 8.7, EA-2/17 S2)
# no tenian ninguna celda, y de las tablas de varias paginas solo se guardaba la
# primera. Ver docs/PREDICCION_tablas_con_columnas_2026-10-04.md.
#
# Se guardan en `tabla_pdf` y `celda_pdf`, aparte de `celda`, que no se toca.
# ============================================================================

MINIMA_PARTE_EN_LA_PAGINA = 0.8


# La marca de agua de la ISO/IEC 27001 (R17d, 13-oct-2026): `extraccion.normalizar` la quita del texto, y los valores de las celdas del PDF tambien pasan por
# aqui. Una celda es una unidad cerrada por la geometria de la tabla, y la marca, que cruza sus fronteras, deja trozos cortos ("--``" junto al "5.18" de una fila): ademas de los tramos
# de 6 o mas que quita `quitar_marca_de_agua`, aqui se quita la ficha entera formada solo por esos caracteres con tres o mas de largo y dos o mas distintos. Medido sobre Z63 y Z64: fuera
# de la ISO no hay una sola ficha asi en ninguna celda, de modo que ninguna otra celda cambia.
RE_FRAGMENTO_DE_MARCA = re.compile(r"(?<!\S)[-`,']{3,}(?!\S)")


def _sin_marca_de_agua(valor: str) -> str:
    """`valor` sin la marca de agua editorial. Si la marca ocupaba un renglon entero de la celda ("unau-\\n,`,,`---\\nthorized") el renglon desaparece, para que el
    guion de final de renglon de arriba se una con lo de abajo."""
    s = quitar_marca_de_agua(valor)
    s = RE_FRAGMENTO_DE_MARCA.sub(lambda m: "" if len(set(m.group(0))) >= 2 else m.group(0), s)
    if s != valor:
        s = re.sub(r"[ \t]*\n(?:[ \t]*\n)+", "\n", s)
    return s


def limpiar_celda(valor: str) -> str:
    """El texto de una celda en una linea: guion blando y guion de final de linea
    unidos ("nin\\xad\\ngun" -> "ningun"), saltos de linea como espacios, sin marca de agua."""
    s = re.sub("­\\s*", "", _sin_marca_de_agua(valor or ""))
    s = re.sub(r"(?<=[^\W\d_])-\n(?=[^\W\d_])", "", s)
    return " ".join(s.split())


def canon(s: str) -> str:
    """Para ver si una celda esta en el texto de un precepto: `norm`, sin espacios
    (Xpdf y la tabla los ponen distinto: "n.o" / "n. o") y sin el guion de corte
    entre dos letras ("inter- face" es "interface"). Entre cifras el guion se queda:
    "-20 °C" no es "20 °C"."""
    return re.sub(r"(?<=[a-z])-(?=[a-z])", "", norm(s).replace(" ", ""))


def _palabras(texto: str) -> set[str]:
    s = unicodedata.normalize("NFD", limpiar_celda(texto).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return set(re.findall(r"[a-z]{3,}", s))


def es_tabla_valida(filas: list[list[str]], texto_pagina: str) -> bool:
    """Dos columnas con contenido y el 80 % de las celdas con todas sus palabras en
    el texto de la pagina. Lo que no cumple es un recuadro del logotipo ("EA l |
    /17 tion for s vities") o un trozo de formula, no una tabla. Vale una sola fila:
    una tabla que empieza al pie de una pagina ("Normativa aplicable | Norma UNE-EN
    61000-4-11:2021...", Orden ICT/155/2020, anexo XVII) se perdia (5-oct-2026)."""
    if not filas:
        return False
    columnas = {j for f in filas for j, c in enumerate(f) if c}
    if len(columnas) < 2:
        return False
    llenas = [c for f in filas for c in f if c]
    pagina = _palabras(texto_pagina)
    buenas = sum(1 for c in llenas if _palabras(c) <= pagina)
    return buenas >= MINIMA_PARTE_EN_LA_PAGINA * len(llenas)


TOLERANCIA_PUNTOS = 1.0


def _quien(celdas_con_texto, n_f: int, n_c: int) -> list[list[int | None]]:
    """Para cada hueco de la rejilla, que celda con texto lo ocupa (o None)."""
    quien: list[list[int | None]] = [[None] * n_c for _ in range(n_f)]
    for k, (i, j, uf, uc) in enumerate(celdas_con_texto):
        for m in range(i, uf + 1):
            for c in range(j, uc + 1):
                quien[m][c] = k
    return quien


def _columnas_que_sobran(quien, n_c: int) -> set[int]:
    """Fronteras entre columnas que no separan dos celdas con texto en ninguna fila.

    Una frontera que solo tiene texto a un lado (una columna finisima vacia junto a
    un titulo) o que una celda con texto atraviesa no separa nada. Pero si entre dos
    textos distintos de una fila solo hay columnas vacias ("Risk Class D", dos
    columnas finisimas, "Risk Class E") y ninguna de esas fronteras separa nada en
    otra fila, se queda una: la que menos celdas con texto atraviesan."""
    separan = {b for b in range(n_c - 1)
               if any(f[b] is not None and f[b + 1] is not None and f[b] != f[b + 1]
                      for f in quien)}
    cruces = [sum(1 for f in quien if f[b] is not None and f[b] == f[b + 1])
              for b in range(n_c - 1)]
    for f in quien:
        con_texto = [c for c in range(n_c) if f[c] is not None]
        for a, z in zip(con_texto, con_texto[1:]):
            if f[a] != f[z] and not any(b in separan for b in range(a, z)):
                separan.add(min(range(a, z), key=lambda b: (cruces[b], b)))
    return set(range(n_c - 1)) - separan


def _filas_que_sobran(quien, n_f: int) -> set[int]:
    """Fronteras entre filas que cruzan mas columnas con texto que las que cortan.

    Un titulo de tres lineas con una raya entre cada una corta una columna; las
    celdas de la cabecera de al lado la cruzan. Contar por filas, como las
    columnas, no vale: aqui las lineas del titulo SI son celdas distintas."""
    sobran = set()
    for b in range(n_f - 1):
        par = list(zip(quien[b], quien[b + 1]))
        cruzan = sum(1 for a, z in par if a is not None and a == z)
        cortan = sum(1 for a, z in par if a != z)
        if cruzan > cortan:
            sobran.add(b)
    return sobran


def _grupos(n: int, sobran: set[int]) -> list[list[int]]:
    grupos = [[0]] if n else []
    for k in range(1, n):
        if k - 1 in sobran:
            grupos[-1].append(k)
        else:
            grupos.append([k])
    return grupos


def lineas_de_la_pagina(page) -> list:
    """Las lineas de la capa de texto de la pagina, cada una con sus caracteres y su caja.

    Es la agrupacion en lineas que usa la propia capa de texto: un subindice va en
    la misma linea que su letra ("Qmin"), no en otra como en `find_tables`."""
    import fitz
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_LIGATURES
                        | fitz.TEXT_PRESERVE_WHITESPACE)
    return [(l["bbox"], [(ch["c"], ch["bbox"]) for s in l["spans"] for ch in s["chars"]])
            for b in raw["blocks"] for l in b.get("lines", [])]


def _texto_por_caracteres(lineas, caja) -> str:
    """Los caracteres con el centro dentro de la caja, linea a linea, de arriba abajo."""
    x0, y0, x1, y1 = caja
    partes = []
    for _, chars in sorted(lineas, key=lambda x: (round(x[0][1]), x[0][0])):
        sel = "".join(c for c, bb in chars
                      if x0 <= (bb[0] + bb[2]) / 2 <= x1 and y0 <= (bb[1] + bb[3]) / 2 <= y1)
        if sel.strip():
            partes.append(sel.strip())
    return "\n".join(partes)


def _sin_espacios(s: str) -> list[str]:
    return sorted(c for c in (s or "") if not c.isspace())


def leer_celdas(t, lineas=None, referencia: str = "") -> list[list[str]]:
    """El texto de cada celda de la rejilla de `find_tables`, en una linea.

    `extract()` pone los subindices en otra linea ("Q - Q - Q / min t max", Orden
    ICT/155/2020, anexo IV, apendice II, tabla 2). Con las lineas de la capa de
    texto sale "Qmin - Qt - Qmax". Se usa esa lectura solo si tiene EXACTAMENTE los
    mismos caracteres (sin contar espacios) y aparece tal cual en el texto de la
    pagina (`referencia`, ya normalizada): asi solo cambia el orden, y solo cuando
    el propio documento lo dice en ese orden. Un texto girado en vertical, que
    `find_tables` si sabe leer, se queda como lo lee `find_tables`.
    """
    crudas = t.extract()
    filas = [[limpiar_celda(c) for c in f] for f in crudas]
    geo = getattr(t, "rows", None)
    if lineas is None or not referencia or not geo or len(geo) != len(filas):
        return filas
    for i, r in enumerate(geo):
        for j, caja in enumerate(r.cells):
            if not caja or j >= len(filas[i]) or not filas[i][j]:
                continue
            otra = _texto_por_caracteres(lineas, caja)
            limpia = limpiar_celda(otra)
            if (limpia != filas[i][j] and _sin_espacios(otra) == _sin_espacios(crudas[i][j])
                    and norm(limpia) and norm(limpia) in referencia):
                filas[i][j] = limpia
    return filas


def rejilla_real(t, filas: list[list[str]] | None = None) -> list[list[str]]:
    """Las filas de una tabla de PyMuPDF con las columnas y filas que se leen.

    `extract()` da la rejilla de lineas del PDF: una cabecera dibujada con columnas
    finisimas a los lados, o un titulo de tres lineas con una raya entre cada una,
    deja el titulo en una columna y sus datos en la de al lado (una celda combinada
    lleva su texto en su PRIMERA columna). Con la posicion de cada celda: una
    frontera entre columnas que en ninguna fila separa dos celdas con texto, y una
    entre filas que cruzan mas columnas con texto que las que corta, no separan
    nada y se quitan; las columnas (o filas) juntas unen sus textos
    en orden, y lo que queda sin texto se quita. Solo une: no pierde ni anade palabra.
    Sin geometria (una tabla simulada) devuelve `extract()` tal cual. `filas`: el
    texto de cada celda ya leido (`leer_celdas`); si no se da, el de `extract()`.
    """
    if filas is None:
        filas = [[limpiar_celda(c) for c in f] for f in t.extract()]
    filas = [list(f) for f in filas]
    geo = getattr(t, "rows", None)
    if not filas or not geo or len(geo) != len(filas):
        return filas
    n_f, n_c = len(filas), max(len(f) for f in filas)
    xs: list[float] = []
    for j in range(n_c):
        x = [r.cells[j][0] for r in geo if j < len(r.cells) and r.cells[j]]
        xs.append(min(x) if x else (xs[-1] if xs else 0.0))
    ys = [r.bbox[1] for r in geo]
    # Una celda metida dentro de otra con el mismo texto es un duplicado que
    # inventa `find_tables` ("8.2.1 | 8.2.1" en la WELMEC 8.7): el PDF lo dice una vez.
    cajas = {(i, j): caja for i, r in enumerate(geo) for j, caja in enumerate(r.cells)
             if caja and j < len(filas[i]) and filas[i][j]}
    for (i, j), a in cajas.items():
        for (m, c), b in cajas.items():
            if ((m, c) != (i, j) and filas[m][c] and norm(filas[m][c]) == norm(filas[i][j])
                    and b[0] - TOLERANCIA_PUNTOS <= a[0] and a[2] <= b[2] + TOLERANCIA_PUNTOS
                    and b[1] - TOLERANCIA_PUNTOS <= a[1] and a[3] <= b[3] + TOLERANCIA_PUNTOS
                    and (b[2] - b[0]) * (b[3] - b[1]) > (a[2] - a[0]) * (a[3] - a[1])):
                filas[i][j] = ""
                break
    celdas_con_texto = []                 # (fila, col, ultima fila, ultima col)
    for i, r in enumerate(geo):
        for j, caja in enumerate(r.cells):
            if caja and j < len(filas[i]) and filas[i][j]:
                uc = max([j] + [k for k in range(j + 1, n_c) if xs[k] < caja[2] - TOLERANCIA_PUNTOS])
                uf = max([i] + [m for m in range(i + 1, n_f) if ys[m] < caja[3] - TOLERANCIA_PUNTOS])
                celdas_con_texto.append((i, j, uf, uc))
    quien = _quien(celdas_con_texto, n_f, n_c)
    cols = _grupos(n_c, _columnas_que_sobran(quien, n_c))
    lins = _grupos(n_f, _filas_que_sobran(quien, n_f))
    out = [[" ".join(filas[i][j] for i in li for j in co if j < len(filas[i]) and filas[i][j])
            for co in cols] for li in lins]
    llenas = [k for k in range(len(cols)) if any(f[k] for f in out)]
    return [[f[k] for k in llenas] for f in out if any(f)]


def _cabecera(fila: list[str]) -> tuple[str, ...]:
    return tuple(norm(c) for c in fila)


PAGINAS_PARA_SER_MOBILIARIO = 3
_RE_NUMERO_DE_PAGINA = re.compile(r"^(?:\d+|[ivxlcdm]+)$", re.IGNORECASE)


def _firma_de_mobiliario(fila: list[str]) -> tuple[str, ...]:
    """La fila con la celda que es solo un numero de pagina ("iii", "12") borrada. Un
    numero dentro de un texto no se borra: "Norma UNE-EN 61000-4-11" y "61000-4-6"
    son dos tablas, no un pie que se repite."""
    return tuple("#" if _RE_NUMERO_DE_PAGINA.match(c.strip()) else norm(c) for c in fila)


def tablas_del_documento(doc, textos_de_pagina: list[str],
                         descartadas: list | None = None) -> list[dict]:
    """Todas las tablas validas del documento, en orden, con las de varias paginas
    juntas: una tabla que empieza una pagina con las mismas columnas y la MISMA fila
    de cabecera que la ultima de la pagina anterior es la misma tabla (no se repite
    la cabecera). Sin cabecera repetida no se junta: no se adivina.

    Tampoco se junta si entre los dos trozos hay contenido: texto debajo del primero
    en su pagina, o texto o un titulo ("Tabla 2.") encima del segundo en la suya.
    Una continuacion de verdad acaba al pie de una pagina y sigue arriba de la
    siguiente. En la Orden ICT/155/2020 (anexo VI, apendice II) la tabla 2 empieza
    la pagina 60 con la misma cabecera que la tabla 1 de la 59, y se juntaban: la
    tabla 1 confirmaba valores de la 2 (5-oct-2026).

    Una tabla de UNA fila que se repite en tres paginas o mas, cambiando solo los
    numeros, es un pie o una cabecera dibujados como tabla ("ATP Handbook 2025 |
    iii", UNECE): no se guarda; si se pasa `descartadas`, se anota alli.

    Cada tabla: dict(pagina_inicio, pagina_fin, n_columnas, filas=[[(valor, pagina)]])
    """
    por_pagina = [_tablas_de_la_pagina(doc, i, textos_de_pagina) for i in range(doc.page_count)]
    paginas_de: dict = {}
    for i, todas in enumerate(por_pagina):
        for filas, _, _ in todas:
            if len(filas) == 1:
                paginas_de.setdefault(_firma_de_mobiliario(filas[0]), set()).add(i)
    out: list[dict] = []
    ultima_pagina_con_tabla = None
    for i, todas in enumerate(por_pagina):
        validas = []
        for filas, arriba, abajo in todas:
            if (len(filas) == 1 and len(paginas_de.get(_firma_de_mobiliario(filas[0]), ()))
                    >= PAGINAS_PARA_SER_MOBILIARIO):
                if descartadas is not None:
                    descartadas.append((i + 1, filas))
                continue
            validas.append((filas, arriba, abajo))
        for k, (filas, arriba, abajo) in enumerate(validas):
            n_col = max(len(f) for f in filas)
            previa = out[-1] if out else None
            sigue = (k == 0 and previa is not None
                     and ultima_pagina_con_tabla == i
                     and not previa["_contenido_debajo"] and not arriba
                     and previa["n_columnas"] == n_col
                     and _cabecera(previa["cabecera"]) == _cabecera(filas[0])
                     and any(previa["cabecera"]))
            if sigue:
                previa["filas"] += [[(c, i + 1) for c in f] for f in filas[1:]]
                previa["pagina_fin"] = i + 1
                previa["_contenido_debajo"] = abajo
            else:
                out.append(dict(pagina_inicio=i + 1, pagina_fin=i + 1, n_columnas=n_col,
                                cabecera=filas[0], _contenido_debajo=abajo,
                                filas=[[(c, i + 1) for c in f] for f in filas]))
        if validas:
            ultima_pagina_con_tabla = i + 1
    return out


PALABRAS_DE_CONTENIDO = 20
_RE_TITULO_DE_TABLA = re.compile(r"^\s*(?:tabla|table|cuadro|tableau)\s+[0-9ivxlc]+\b",
                                 re.IGNORECASE | re.MULTILINE)


def _hay_contenido(bloques) -> bool:
    """Un titulo de tabla, o texto de verdad (no solo la cabecera o el pie de la pagina)."""
    texto = "\n".join(str(b[4]) for b in bloques)
    return bool(_RE_TITULO_DE_TABLA.search(texto)) or len(re.findall(r"\w+", texto)) >= PALABRAS_DE_CONTENIDO


def _tablas_de_la_pagina(doc, i: int, textos_de_pagina: list[str]) -> list:
    """Las tablas validas de la pagina i (desde 0): (filas de celdas, hay contenido
    encima en la pagina, hay contenido debajo)."""
    # La validez se mide contra el texto de Xpdf Y la capa de texto de la propia
    # pagina: en las paginas que Xpdf saca maquetadas, una palabra partida con
    # guion dentro de una celda queda cortada por la columna de al lado
    # ("consid- 27005:2022 attack vector ered", WELMEC 7.2 de 2026), y la tabla,
    # que la tiene entera, se descartaba como si fuera un logotipo.
    texto = textos_de_pagina[i] if i < len(textos_de_pagina) else ""
    capa = getattr(doc[i], "get_text", None)
    if capa is not None:
        texto = texto + "\n" + capa()
    validas = []
    encontradas = doc[i].find_tables().tables
    lineas, referencia, bloques = None, "", []
    if encontradas and capa is not None:
        try:
            lineas = lineas_de_la_pagina(doc[i])
            referencia = norm(limpiar_celda(texto))
            bloques = [b for b in capa("blocks") if len(b) > 4 and str(b[4]).strip()]
        except Exception:                                        # noqa: BLE001
            lineas = None          # sin lineas, cada celda como la lee find_tables
    for t in encontradas:
        try:
            filas = leer_celdas(t, lineas, referencia)
            if es_tabla_valida(filas, texto) and (real := rejilla_real(t, filas)):
                caja = getattr(t, "bbox", None)
                arriba = abajo = False
                if bloques and caja:
                    arriba = _hay_contenido([b for b in bloques if b[3] <= caja[1] + 1])
                    abajo = _hay_contenido([b for b in bloques if b[1] >= caja[3] - 1])
                validas.append((real, arriba, abajo))
        except Exception:                                        # noqa: BLE001
            continue
    return validas


def filas_de_las_tablas(ruta_rel: str, textos_de_pagina: list[str], pagina_desde: int, pagina_hasta: int) -> list[tuple[int, list[str]]]:
    """[(pagina, fila)] de las tablas validas de las paginas `pagina_desde` a `pagina_hasta` (desde 1) del PDF, en orden: las mismas filas, con las mismas celdas, que
    `tablas_del_documento` guarda en `celda_pdf`. Para los adaptadores singulares que construyen preceptos de las filas de una tabla (la A.1 de la ISO/IEC 27001, R17d)."""
    doc = abrir(ruta_rel)
    try:
        salida: list[tuple[int, list[str]]] = []
        for pagina in range(pagina_desde, min(pagina_hasta, doc.page_count) + 1):
            for filas, _arriba, _abajo in _tablas_de_la_pagina(doc, pagina - 1, textos_de_pagina):
                salida.extend((pagina, list(fila)) for fila in filas)
        return salida
    finally:
        doc.close()


def guardar_tablas_pdf(con, documento_id: int, tablas: list[dict]) -> tuple[int, int]:
    """Escribe las tablas de un documento; devuelve (tablas, celdas).

    Se guarda toda celda con texto, aunque sea un simbolo que `norm` deja en nada:
    en la WELMEC 5.2 las marcas "√" dicen que modulos valen para cada instrumento."""
    n_celdas = 0
    for orden, t in enumerate(tablas, 1):
        tid = con.execute(
            "INSERT INTO tabla_pdf (documento_id, orden, pagina_inicio, pagina_fin, "
            "n_filas, n_columnas) VALUES (?,?,?,?,?,?)",
            (documento_id, orden, t["pagina_inicio"], t["pagina_fin"], len(t["filas"]),
             t["n_columnas"])).lastrowid
        for fi, fila in enumerate(t["filas"]):
            for co, (valor, pagina) in enumerate(fila):
                if valor and valor.strip():
                    con.execute("INSERT INTO celda_pdf (tabla_id, fila, columna, valor, "
                                "valor_norm, pagina) VALUES (?,?,?,?,?,?)",
                                (tid, fi, co, valor, norm(valor), pagina))
                    n_celdas += 1
    return len(tablas), n_celdas


def tablas_de_paginas(con, ruta_relativa: str | None, pagina_inicio, pagina_fin) -> list[dict]:
    """Las tablas guardadas que tocan esas paginas del documento, con sus filas.

    Cada tabla: dict(orden, pagina_inicio, pagina_fin, n_columnas, filas=[[valor]],
    paginas_de_fila=[pagina]), con las celdas vacias como "". [] si la base no tiene
    la tabla `tabla_pdf`.
    """
    if not ruta_relativa or pagina_inicio is None:
        return []
    fin = pagina_fin or pagina_inicio
    try:
        tablas = con.execute(
            "SELECT t.id, t.orden, t.pagina_inicio, t.pagina_fin, t.n_filas, t.n_columnas "
            "FROM tabla_pdf t JOIN documento d ON d.id=t.documento_id "
            "WHERE d.ruta_relativa=? AND t.pagina_inicio<=? AND t.pagina_fin>=? "
            "ORDER BY t.orden", (ruta_relativa, fin, pagina_inicio)).fetchall()
    except Exception:                                            # noqa: BLE001
        return []
    out = []
    for tid, orden, pi, pf, nf, nc in tablas:
        filas = [[""] * nc for _ in range(nf)]
        paginas = [pi] * nf
        for fi, co, valor, pag in con.execute(
                "SELECT fila, columna, valor, pagina FROM celda_pdf WHERE tabla_id=?", (tid,)):
            if fi < nf and co < nc:
                filas[fi][co] = valor
                if pag is not None:
                    paginas[fi] = pag
        out.append(dict(orden=orden, pagina_inicio=pi, pagina_fin=pf, n_columnas=nc,
                        filas=filas, paginas_de_fila=paginas))
    return out


def filas_del_precepto(tabla: dict, texto_precepto: str) -> list[list[str]]:
    """Las filas de la tabla cuyas celdas estan TODAS en el texto del precepto.

    Una pagina puede llevar el final de un precepto y una tabla del siguiente: solo
    las filas que el propio precepto contiene son suyas. La primera fila (la
    cabecera) se queda si tambien esta en el texto. Se compara sin espacios: Xpdf y
    la tabla los ponen distinto ("n.o" / "n. o", "5y6" / "5 y 6", 5-oct-2026).
    """
    t = canon(texto_precepto)
    out = []
    for fila in tabla["filas"]:
        llenas = [canon(c) for c in fila if c and norm(c)]
        if llenas and all(c in t for c in llenas):
            out.append(fila)
    return out


def _puntos(tabla: dict, texto_precepto: str) -> tuple[int, int]:
    """(filas seguidas en el texto, filas con cada celda en el texto), sin espacios."""
    t = canon(texto_precepto)
    seguidas = celda_a_celda = 0
    for fila in tabla["filas"]:
        cs = [canon(c) for c in fila if c and norm(c)]
        if cs and all(c in t for c in cs):
            celda_a_celda += 1
            seguidas += "".join(cs) in t
    return seguidas, celda_a_celda


def es_duena(tabla: dict, texto_precepto: str, otros_textos) -> bool:
    """¿Es este precepto dueno de la tabla? Lo es si ningun otro precepto de esas
    paginas le gana en (filas seguidas en su texto, filas con cada celda en su
    texto). Empatar tambien es ser dueno: un anexo y la tabla que lleva dentro.

    Mirar cada celda por separado no basta: en la Orden ICT/155/2020 (anexo IV,
    apendice II) las tablas 3 y 4 estan en la misma pagina y la fila «Qmin ≤ Q <
    Qt | ± 3 % | ± 2 %» de la 4 tiene cada celda en el texto de la 3, pero no
    seguidas; con eso una cita de la tabla 4 se confirmaba como literal de la 3
    (5-oct-2026). Seguidas solo estan en la 4: la duena es la 4.
    """
    mio = _puntos(tabla, texto_precepto)
    if mio[1] == 0:
        return False
    return all(_puntos(tabla, o) <= mio for o in otros_textos)


def textos_de_otros_preceptos(con, ruta_relativa: str | None, pagina_inicio, pagina_fin,
                              texto_propio: str | None) -> list[str]:
    """Los textos de los demas preceptos del documento que tocan esas paginas."""
    if not ruta_relativa or pagina_inicio is None:
        return []
    fin = pagina_fin or pagina_inicio
    filas = con.execute(
        "SELECT p.texto_literal FROM precepto p JOIN version v ON v.id=p.version_id "
        "JOIN documento d ON d.id=v.documento_id WHERE d.ruta_relativa=? "
        "AND p.pagina_inicio<=? AND p.pagina_fin>=?", (ruta_relativa, fin, pagina_inicio))
    return [t for (t,) in filas if t and t != texto_propio]


def _puntos_de_fila(celdas: list[str], texto_sin_espacios: str) -> int:
    """2 si la fila esta seguida en el texto, 1 si solo celda a celda, 0 si no."""
    if not celdas or not all(c in texto_sin_espacios for c in celdas):
        return 0
    return 2 if "".join(celdas) in texto_sin_espacios else 1


def filas_suyas(tabla: dict, texto_precepto: str, otros_textos) -> list[list[str]]:
    """Las filas de la tabla que son de este precepto, fila a fila.

    Una fila es suya si ningun otro precepto de esas paginas la tiene mejor: seguida
    en su texto gana a suelta (cada celda por separado). Si aqui solo esta suelta y
    en otro precepto tambien, es ambigua: solo la usa el dueno de la tabla
    (`es_duena`). Una tabla que reparten dos preceptos (la de terminos de la WELMEC
    8.1, paginas 5-18) da a cada uno sus filas; con el dueno de la tabla entera, el
    apartado 1 se quedaba filas del siguiente (5-oct-2026).
    """
    mio_t = canon(texto_precepto or "")
    otros_t = [canon(o) for o in otros_textos]
    duena = None
    out = []
    for fila in tabla["filas"]:
        cs = [canon(c) for c in fila if c and norm(c)]
        mio = _puntos_de_fila(cs, mio_t)
        if mio == 0:
            continue
        ajenos = [_puntos_de_fila(cs, o) for o in otros_t]
        if any(a > mio for a in ajenos):
            continue
        if mio == 1 and any(a == 1 for a in ajenos):
            if duena is None:
                duena = es_duena(tabla, texto_precepto or "", otros_textos)
            if not duena:
                continue
        out.append(fila)
    return out


def filas_para_validar(con, ruta_relativa, pagina_inicio, pagina_fin,
                       texto_precepto: str | None) -> list[list[list[str]]]:
    """Por cada tabla de las paginas del precepto, las filas suyas (`filas_suyas`):
    con lo que el validador puede leer por filas."""
    out = []
    for t in tablas_de_paginas(con, ruta_relativa, pagina_inicio, pagina_fin):
        otros = textos_de_otros_preceptos(con, ruta_relativa, t["pagina_inicio"],
                                          t["pagina_fin"], texto_precepto)
        filas = filas_suyas(t, texto_precepto or "", otros)
        if filas:
            out.append(filas)
    return out


def otros_preceptos(con, ruta_relativa: str | None, pagina_inicio, pagina_fin,
                    texto_propio: str | None) -> list[tuple[int, int, str]]:
    """(pagina_inicio, pagina_fin, texto) de los demas preceptos del documento que
    tocan esas paginas."""
    if not ruta_relativa or pagina_inicio is None:
        return []
    fin = pagina_fin or pagina_inicio
    filas = con.execute(
        "SELECT p.pagina_inicio, p.pagina_fin, p.texto_literal FROM precepto p "
        "JOIN version v ON v.id=p.version_id JOIN documento d ON d.id=v.documento_id "
        "WHERE d.ruta_relativa=? AND p.pagina_inicio<=? AND p.pagina_fin>=?",
        (ruta_relativa, fin, pagina_inicio))
    return [(a, b, t) for a, b, t in filas if t and t != texto_propio]


PARTE_PARA_HUERFANA = 0.6
CELDA_LITERAL_MINIMA = 4      # caracteres de `canon`: "1", "X", "Yes", "3.2" no cuentan


def _palabras_de(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", norm(texto))


def filas_huerfanas(tabla: dict, texto_precepto: str, pagina_inicio, pagina_fin,
                    otros) -> list[list[str]]:
    """Las filas que ningun precepto tiene (ni seguidas ni celda a celda: Xpdf leyo la
    tabla cruzando columnas, "...de gotas de Las gotas que caen... dano. agua") y que
    este precepto se queda PARA ENSENAR. De los preceptos que cubren la pagina de la
    fila, tiene que ser el unico que trae tal cual alguna celda propia de la fila (de
    4 caracteres o mas) y tener mas parte de sus palabras que cualquier otro (al
    menos el 60 %); si no, la fila no se ensena con ninguno. Celdas propias: las que
    no se repiten en otra fila de la tabla. Una fila sin celdas propias no se ensena.
    El validador nunca confirma con ellas. `otros`: (pagina_inicio, pagina_fin, texto).

    Cada condicion sale de un error leido a mano (5-oct-2026): con el empate en
    palabras salian filas del anexo III de la MID tambien en el IV; solo con las
    palabras, la fila "9.3 Management review | Title only" de la WELMEC 8.6 iba con
    el 9.3.2, que tiene esas palabras sueltas, y no con el 9.3, que tiene la celda;
    en esa guia tres columnas repiten el texto del modulo D en muchas filas y ese
    texto daba la fila del 8.3.2 al 8.3.1; y el 8.2.4 es solo su titulo, mientras el
    cuerpo de su fila acabo en el texto del 8.3.1.
    """
    if pagina_inicio is None:
        return []
    fin = pagina_fin or pagina_inicio
    mio_c = canon(texto_precepto or "")
    mias = set(_palabras_de(texto_precepto or ""))
    otros_c = [(a, b, canon(t), set(_palabras_de(t))) for a, b, t in otros]
    veces = collections.Counter(c for fila in tabla["filas"]
                                for c in {canon(x) for x in fila if x and norm(x)})
    out = []
    for k, fila in enumerate(tabla["filas"]):
        cs = [canon(c) for c in fila if c and norm(c)]
        pal = _palabras_de(" ".join(fila))
        if not cs or not pal:
            continue
        if _puntos_de_fila(cs, mio_c) or any(_puntos_de_fila(cs, oc) for _, _, oc, _ in otros_c):
            continue                           # alguien la tiene: no es huerfana
        pag = tabla.get("paginas_de_fila", [None] * len(tabla["filas"]))[k] or tabla["pagina_inicio"]
        if not (pagina_inicio <= pag <= fin):
            continue
        propias = [x for x in fila if x and norm(x) and veces[canon(x)] == 1]
        largas = [canon(x) for x in propias if len(canon(x)) >= CELDA_LITERAL_MINIMA]
        pal = _palabras_de(" ".join(propias))
        if not largas or not pal:
            continue                           # nada que sea solo de esta fila
        parte = sum(1 for w in pal if w in mias) / len(pal)
        literal = sum(len(c) for c in largas if c in mio_c)
        rivales = [(sum(1 for w in pal if w in op) / len(pal),
                    sum(len(c) for c in largas if c in oc))
                   for a, b, oc, op in otros_c if a is not None and b is not None and a <= pag <= b]
        if parte >= PARTE_PARA_HUERFANA and literal > 0 and all(
                parte > r and l == 0 for r, l in rivales):
            out.append(fila)
    return out


def _tabla_con_indices_omitidos(tabla, texto_precepto, otros_textos):
    """Tabla con cabecera multinivel cuya columna 1..n omitió Xpdf.

    Solo presentación: toda la tabla restante debe aparecer seguida, en orden,
    en el texto. No basta con números sueltos o con una cabecera coincidente.
    Un rival independiente que contenga la misma secuencia impide asignarla.
    Las filas recuperadas se marcan sin validar.
    """
    filas = tabla['filas']
    inicio = next((k for k,f in enumerate(filas) if f and f[0].strip() == '1'), None)
    if inicio is None or inicio < 2 or len(filas)-inicio < 2:
        return False
    datos = filas[inicio:]
    if [f[0].strip() for f in datos] != [str(n) for n in range(1,len(datos)+1)]:
        return False
    if any(not any(norm(c) for c in f[1:]) for f in datos):
        return False
    firma = canon(lectura_por_filas(filas[:inicio] + [f[1:] for f in datos]))
    propio = canon(texto_precepto or '')
    if not firma or firma not in propio:
        return False
    return all(firma not in (otro := canon(o)) or propio in otro for o in otros_textos)


def tablas_para_ensenar(con, ruta_relativa, pagina_inicio, pagina_fin,
                        texto_precepto: str | None
                        ) -> list[tuple[dict, list[list[str]], list[list[str]]]]:
    """Las tablas que la consulta ensena con el precepto: (tabla, filas, sin_validar).

    Sus filas (`filas_suyas`) y las huerfanas que le tocan (`filas_huerfanas`), en el
    orden de la tabla; la tabla entera si el precepto es su dueno, la tabla cabe en
    sus paginas y la mayoria de las filas son suyas: en una tabla de texto largo a
    dos columnas Xpdf lee las columnas entrelazadas y el texto de una celda no sale
    seguido en el precepto (definiciones de la MID, exenciones de RoHS).
    `sin_validar` son las filas de `filas` que no son suyas (las huerfanas y, si la
    tabla va entera, las de otros preceptos o que el texto no trae): el validador no
    las usa (`filas_para_validar`) y la consulta tiene que decirlo.
    """
    out = []
    for t in tablas_de_paginas(con, ruta_relativa, pagina_inicio, pagina_fin):
        otros_p = otros_preceptos(con, ruta_relativa, t["pagina_inicio"], t["pagina_fin"],
                                  texto_precepto)
        otros = [x for _, _, x in otros_p]
        suyas = filas_suyas(t, texto_precepto or "", otros)
        con_texto = [f for f in t["filas"] if any(norm(c) for c in f)]
        dentro = (pagina_inicio is not None and pagina_inicio <= t["pagina_inicio"]
                  and t["pagina_fin"] <= (pagina_fin or pagina_inicio))
        if dentro and _tabla_con_indices_omitidos(t, texto_precepto, otros):
            out.append((t, con_texto, [f for f in con_texto if f not in suyas]))
            continue
        if suyas and dentro and 2 * len(suyas) >= len(con_texto) and es_duena(
                t, texto_precepto or "", otros):
            out.append((t, con_texto, [f for f in con_texto if f not in suyas]))
            continue
        huerfanas = filas_huerfanas(t, texto_precepto, pagina_inicio, pagina_fin, otros_p)
        if suyas or huerfanas:
            elegidas = [f for f in t["filas"] if f in suyas or f in huerfanas]
            out.append((t, elegidas, [f for f in elegidas if f not in suyas]))
    return out


def lectura_por_filas(filas: list[list[str]]) -> str:
    """La tabla leida por filas, de izquierda a derecha: como la lee una persona."""
    return " ".join(" ".join(c for c in fila if c) for fila in filas)


def markdown(filas: list[list[str]]) -> str:
    """La tabla en Markdown, con la primera fila como cabecera."""
    if not filas:
        return ""
    def esc(c):
        return (c or "").replace("|", "/")
    lineas = ["| " + " | ".join(esc(c) for c in filas[0]) + " |",
              "|" + "---|" * len(filas[0])]
    lineas += ["| " + " | ".join(esc(c) for c in f) + " |" for f in filas[1:]]
    return "\n".join(lineas)
