"""El texto ajeno de las normas de la UE (R11, 11-oct-2026; docs/PREDICCION_texto_ajeno_ue_2026-10-11.md).

El PDF de una norma del Diario Oficial lleva, ademas de la norma, la maquetacion del Diario: el folio de cada pagina («C 343/4 ES», «31/81 ES», «L 153/72 EN»),
la cabecera («L 10/18 ES 13.1.2005») y las notas al pie («(1) DO L 324 de 10.12.2007, p. 121.»). La extraccion las dejaba pegadas en medio del articulo y un cotejo con
el texto oficial veia texto que la norma no tiene. Aqui se quitan, con reglas y no con una lista, y SOLO en la familia `eurlex`.

DONDE. En el flujo de lineas del analizador (`parsers.lineas_con_pagina`), que ya no lleva la maquetacion repetida (la cabecera y el pie que salen en cada pagina) y sabe
la pagina de cada linea. NO en el texto de las paginas de `extraer`: quitar alli un folio o una fecha cambia lo que el detector de lineas repetidas ve en el resto de las
paginas y deja sueltas las que antes quitaba (medido: «13.8.2008» en la Decision 768/2008). La extraccion solo guarda el testigo de las notas (`notas_con_testigo`).

R15 (11-oct-2026): lo mismo se aplica a las guias de la carpeta de la UE (las Directrices GDP, las C/2025/214, los anexos de EudraLex con el membrete de la AEMPS, PIC/S: ver
`extraccion._es_guia_de_la_ue`), que ademas llevan las piezas de maquetacion que PyMuPDF confirma por su franja y su repeticion (`maquetacion_pymupdf`); el flujo se limpia en el orden
notas, piezas, folios.

QUE.
 - **folio y cabecera**: una linea que es solo un folio con letra de serie (`L 153/72`, `C 343/4`); o un folio sin letra (`31/81`) en el borde de su pagina, si es el de SU
   pagina («31/81» en la 31 de un PDF de 81) o si tiene un codigo de idioma al lado; y, junto a un folio y en el borde de su pagina, el codigo de idioma, la fecha de
   cabecera, la rotulacion de serie y el ELI del pie. Un «ES» o un «3/4» sueltos, lejos de un folio, no se tocan: pueden ser una celda.
 - **nota al pie** (PyMuPDF es el testigo): un parrafo que EMPIEZA por su llamada («(1)», «( 1 )»), esta compuesto en un cuerpo MENOR que el del texto del documento
   (8,4 frente a 9,5 en las consolidadas; 8,5 frente a 9,6 en la serie L nueva) y es de las del Diario: una referencia («DO L 324 de 10.12.2007, p. 121», «Reglamento
   (UE) 2016/679 del Parlamento Europeo y del Consejo…», «Posicion del Parlamento Europeo de…», «Vease la pagina 83 del presente Diario Oficial»). Con eso un considerando
   que empieza por el nombre de un acto («(7) El Reglamento Delegado (UE) 2022/30 debe modificarse»: cuerpo normal) no es una nota, y la nota de una tabla de anexo
   («( 1 ) Para los contadores electromecanicos de la clase B se aplicara…»: cuerpo menor, pero es texto de la norma) tampoco. La llamada «(1)» DENTRO del texto se queda.
   Una nota que no es una referencia pero va pegada, con el numero seguido, a una que si lo es («(2) De conformidad con el Acuerdo sobre la retirada del Reino Unido…» tras
   «(1) DO L 299…») es del Diario tambien: el bloque de notas de una pagina es del Diario entero. Las notas de una tabla o de un anexo, que estan solas, no.
   La nota se quita solo si coincide con un tramo de lineas de su pagina, letra a letra salvo espacios y signos (lo que no coincide no se toca y se lista).
 - **formula final** («Hecho en Bruselas, el 20 de julio de 2023. Por la Comision…»): no es una nota ni un folio, es la firma del acto. No se quita: va a un precepto
   propio (`formula_final`) y deja de pegarse al ultimo articulo (ver `parsers.analizar_eurlex`).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

# ------------------------------------------------------------------------------------------------------------------ folio y cabecera
RE_FOLIO_CON_SERIE = re.compile(r"^\s*[LC]\s+\d{1,4}/\d{1,4}\s*$")
RE_FOLIO_NUMERICO = re.compile(r"^\s*(\d{1,3})/(\d{1,3})\s*$")
RE_SOLO_IDIOMA = re.compile(r"^\s*(?:ES|EN)\s*$")
RE_SERIE = re.compile(r"^\s*(?:II|III|IV|V)\s*$|^\s*\((?:Comunicaciones|Communications)\)\s*$")
RE_FECHA_DE_CABECERA = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{4}\s*$")
RE_ELI_DEL_PIE = re.compile(r"^\s*ELI:\s*https?://data\.europa\.eu/eli/\S+/oj\s*$")
# A cuantas lineas de un folio puede estar el codigo de idioma o la fecha que lo acompanan
VENTANA_DEL_FOLIO = 6
# Cuantas lineas (no vacias) desde el borde de su pagina cuenta como «en el borde»
BORDE_DE_LA_PAGINA = 4


def lineas_de_folio(textos: list[str], paginas: list[int], n_paginas: int = 0) -> set[int]:
    """Los indices de las lineas del flujo (`textos[i]` en la pagina `paginas[i]`) que son maquetacion del Diario: el folio, el codigo de idioma, la fecha de cabecera, la
    rotulacion de serie y el ELI del pie que lo acompanan. `n_paginas` es el numero de paginas del PDF (0 = no se sabe)."""
    n = len(textos)
    por_pagina: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        if textos[i].strip():
            por_pagina[paginas[i]].append(i)
    desde_el_borde = [10 ** 6] * n
    for idx in por_pagina.values():
        for k, i in enumerate(idx):
            desde_el_borde[i] = min(k, len(idx) - 1 - k)
    en_el_borde = lambda i: desde_el_borde[i] < BORDE_DE_LA_PAGINA  # noqa: E731
    idiomas = [i for i in range(n) if RE_SOLO_IDIOMA.match(textos[i])]
    folios = [i for i in range(n) if RE_FOLIO_CON_SERIE.match(textos[i])]
    for i in range(n):
        m = RE_FOLIO_NUMERICO.match(textos[i])
        if not m or not en_el_borde(i):
            continue
        # «31/81» es el folio si el total es el del PDF («81») y dice la pagina en que esta («31» en la 31) o tiene un codigo de idioma al lado. Si no se sabe el total del
        # PDF, basta el codigo de idioma. Una fraccion («3/4») junto a un «ES» de una celda no es un folio.
        total_del_pdf = not n_paginas or int(m.group(2)) == n_paginas
        es_el_de_su_pagina = bool(n_paginas) and int(m.group(1)) == paginas[i]
        con_idioma = any(abs(i - j) <= VENTANA_DEL_FOLIO and en_el_borde(j) for j in idiomas)
        if total_del_pdf and (es_el_de_su_pagina or con_idioma):
            folios.append(i)
    folios = sorted(set(folios))
    quitar = set(folios)
    if not folios:
        return quitar
    for i in range(n):
        if i in quitar or not en_el_borde(i):
            continue
        if RE_SOLO_IDIOMA.match(textos[i]) or RE_FECHA_DE_CABECERA.match(textos[i]) or RE_SERIE.match(textos[i]) or RE_ELI_DEL_PIE.match(textos[i]):
            if any(abs(i - f) <= VENTANA_DEL_FOLIO for f in folios):
                quitar.add(i)
    return quitar


# ------------------------------------------------------------------------------------------------------------------ notas al pie (PyMuPDF)
RE_LLAMADA = re.compile(r"^\s*\(\s*(\d{1,3})\s*\)")
# una nota es de un cuerpo menor que el del documento; los cuerpos de los dos formatos del Diario miden 0,88-0,89 del texto
PROPORCION_DE_NOTA = 0.93
# Lo que hace de una nota «una nota del Diario»: una referencia a otro acto o a una publicacion. Se mira detras de la llamada.
RE_REFERENCIA_AL_INICIO = re.compile(
    r"^\s*(?:(?:DO|OJ)\s+[LC]\b|ELI:|V[ée]ase\b|See\b|Posici[óo]n\s+del|Position\s+of|Dictamen\b|Opinion\b|"
    r"(?:(?:Commission|Council|Comisi[óo]n|Consejo)\s+)?(?:(?:Delegated|Implementing|Delegado|de\s+Ejecuci[óo]n)\s+)?"
    r"(?:Directiva|Directive|Reglamento|Regulation|Decisi[óo]n|Decision|Recomendaci[óo]n|Recommendation|Comunicaci[óo]n|Communication|Resoluci[óo]n|Resolution|"
    r"Conclusiones|Conclusions|Constituci[óo]n|Constitution|Convenio|Convention|Acuerdo|Agreement|Tratado|Treaty|Protocolo|Protocol|Libro\s+Verde|Green\s+Paper|"
    r"Informe|Report|Carta|Charter|Estatuto|Statute|Sentencia|Judgment|Norma|Standard)\b|"
    r"Art[íi]culos?\s+\d|Articles?\s+\d|Anexo\s+[IVX\d]|Annex\s+[IVX\d]|Punto\s+\d|Point\s+\d)", re.I)
# La marca de consolidacion que EUR-Lex pone delante del texto de una nota («( 1 ) ►C1 Reglamento (UE) 2018/1139…»)
RE_MARCA_DE_CONSOLIDACION = re.compile(r"^\s*(?:[►◄▼]\s*(?:[A-Z]{1,2}\d{1,3}\b|[A-Z]\b)?\s*)+")


def es_nota_del_diario(texto: str) -> bool:
    """El texto de una nota (con su llamada) es de las del Diario: EMPIEZA por una referencia (a un acto, a una publicacion, a una pagina), no es una nota de tabla ni un
    considerando. Que lleve una referencia dentro («… del Reglamento (CE) n.o 2073/2005 de la Comision (DO L 338…)») no basta: la nota de una tabla del 853/2004 la lleva."""
    # la llamada y el numero repetido que a veces la sigue («(2)2) Posicion del Parlamento Europeo de…»), y la marca de consolidacion
    resto = re.sub(r"^\s*\(\s*\d{1,3}\s*\)\s*(?:\d{1,3}\)\s*)?", "", texto, count=1)
    resto = RE_MARCA_DE_CONSOLIDACION.sub("", resto)
    return bool(RE_REFERENCIA_AL_INICIO.match(resto))


@dataclass
class LineaPdf:
    texto: str
    tam: float          # tamano de la parte con texto (no el de la llamada)
    y0: float
    y1: float
    x0: float
    negrita: bool
    bloque: int
    llamada: bool = False       # empieza por «(N)»


def lineas_visuales(pagina) -> list[LineaPdf]:
    """Las lineas de una pagina de PyMuPDF, con la llamada «(N)» unida a su texto cuando el PDF las pone en dos lineas del mismo bloque a la misma altura (serie L
    nueva: «(5)» y el texto de la nota, o «(4)» y el texto del considerando)."""
    import fitz
    d = pagina.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    out: list[LineaPdf] = []
    for bi, b in enumerate(d.get("blocks", [])):
        previa: LineaPdf | None = None
        for ln in b.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            texto = "".join(s["text"] for s in ln["spans"])
            principal = max(spans, key=lambda s: len(s["text"].strip()))
            actual = LineaPdf(texto=texto, tam=principal["size"], y0=ln["bbox"][1], y1=ln["bbox"][3], x0=ln["bbox"][0],
                              negrita=bool(principal["flags"] & 16), bloque=bi)
            # la llamada sola («(4)») y, a su derecha y a la misma altura, el texto: una sola linea visual
            if (previa is not None and previa.llamada and len(previa.texto.strip()) <= 7 and RE_LLAMADA.match(previa.texto)
                    and abs(actual.y0 - previa.y0) < 4 and actual.x0 > previa.x0):
                previa.texto = previa.texto.rstrip() + " " + actual.texto
                previa.tam = actual.tam
                previa.negrita = actual.negrita
                previa.y1 = max(previa.y1, actual.y1)
                continue
            actual.llamada = bool(RE_LLAMADA.match(texto))
            out.append(actual)
            previa = actual
    return out


def tamano_del_cuerpo(lineas: list[LineaPdf]) -> float:
    """El tamano de letra con que se compone la mayor parte del texto de las lineas (una pagina, o todo el documento)."""
    from collections import Counter
    c: Counter = Counter()
    for ln in lineas:
        c[round(ln.tam, 1)] += len(ln.texto.strip())
    return c.most_common(1)[0][0] if c else 0.0


# El cuerpo del articulado de un documento: el mayor de los tamanos que reunen al menos esta parte de su texto. Una pagina de notas tiene mas notas que cuerpo, y un
# documento con anexos de tablas enormes (el Reglamento 853/2004) tiene mas letra pequena que normal; el articulado sigue siendo el tamano mayor que pesa.
PESO_MINIMO_DEL_CUERPO = 0.10


def tamano_del_cuerpo_del_documento(lineas_por_pagina: list[list[LineaPdf]]) -> float:
    from collections import Counter
    c: Counter = Counter()
    for lineas in lineas_por_pagina:
        for ln in lineas:
            c[round(ln.tam, 1)] += len(ln.texto.strip())
    total = sum(c.values())
    candidatos = [t for t, n in c.items() if total and n >= PESO_MINIMO_DEL_CUERPO * total]
    return max(candidatos) if candidatos else (c.most_common(1)[0][0] if c else 0.0)


RE_LLAMADA_REPETIDA = re.compile(r"^(\(\s*(\d{1,3})\s*\))\s*\2\)\s*")


def notas_de_pagina(lineas: list[LineaPdf], cuerpo: float) -> list[str]:
    """Los parrafos de nota al pie del Diario de una pagina, tal como los lee PyMuPDF (espacios juntos).

    Una nota es del Diario si es una referencia (`es_nota_del_diario`). Una nota que no lo es («(2) De conformidad con el Acuerdo sobre la retirada del Reino Unido…», «(2) Cybersecurity of
    5G networks – EU Toolbox…») lo es tambien cuando esta pegada, en el mismo bloque de notas y con el numero seguido, a una que si: el bloque de notas de una pagina es del Diario entero.
    Las notas de una tabla o de un anexo, que estan solas, no lo son."""
    notas: list[list[LineaPdf]] = []
    posiciones: list[tuple[int, int]] = []      # (primera, ultima) linea de cada nota dentro de `lineas`
    abierta = False
    for k, ln in enumerate(lineas):
        pequena = ln.tam <= cuerpo * PROPORCION_DE_NOTA and not ln.negrita and ln.texto.strip() != ""
        if ln.llamada and pequena and len(ln.texto.strip()) > 6:
            notas.append([ln])
            posiciones.append((k, k))
            abierta = True
        elif abierta and pequena and not ln.llamada and (ln.bloque == notas[-1][-1].bloque
                                                         or (ln.bloque == notas[-1][-1].bloque + 1 and ln.y0 - notas[-1][-1].y1 < 6 and ln.x0 >= notas[-1][0].x0 - 1)):
            notas[-1].append(ln)
            posiciones[-1] = (posiciones[-1][0], k)
        else:
            abierta = False
    # «(1)1) DO C…»: la llamada repetida de la serie L nueva es una sola
    textos = [RE_LLAMADA_REPETIDA.sub(r"\1 ", " ".join(" ".join(x.texto.split()) for x in nota)) for nota in notas]
    numeros = [int(RE_LLAMADA.match(t).group(1)) for t in textos]
    aceptada = [es_nota_del_diario(t) for t in textos]
    cambia = True
    while cambia:
        cambia = False
        for k in range(len(notas)):
            if aceptada[k]:
                continue
            for v in (k - 1, k + 1):
                if 0 <= v < len(notas) and aceptada[v] and numeros[k] == numeros[v] + (k - v) and (
                        posiciones[v][1] + 1 == posiciones[k][0] if v < k else posiciones[k][1] + 1 == posiciones[v][0]):
                    aceptada[k] = True
                    cambia = True
                    break
    return [t for t, a in zip(textos, aceptada) if a]


def notas_del_pdf(ruta) -> list[list[str]] | None:
    """Las notas del Diario de cada pagina del PDF, o None si PyMuPDF no esta o no abre el fichero."""
    try:
        import fitz
        doc = fitz.open(str(ruta))
    except Exception:  # noqa: BLE001
        return None
    try:
        paginas = [lineas_visuales(p) for p in doc]
    except Exception:  # noqa: BLE001
        return None
    finally:
        doc.close()
    cuerpo_del_documento = tamano_del_cuerpo_del_documento(paginas)
    if not cuerpo_del_documento:
        return [[] for _ in paginas]
    # el cuerpo de cada pagina: el de la pagina o, si es menor (una pagina de notas), el del documento
    return [notas_de_pagina(lineas, max(tamano_del_cuerpo(lineas), cuerpo_del_documento)) for lineas in paginas]


# ------------------------------------------------------------------------------------------------------------------ quitar del flujo de lineas
def _esqueleto(s: str) -> str:
    """Las letras y cifras de un texto, en minuscula y sin signos ni espacios. NFKC primero: el `m²` de la capa de exponentes (R14) y el `m2` de PyMuPDF son lo mismo."""
    return re.sub(r"[^0-9a-záéíóúñüçàèìòùâêîôûäëïöü]", "", unicodedata.normalize("NFKC", s).casefold())


def tramos_de_notas(lineas: list[str], notas: list[str]) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    """Los tramos de lineas consecutivas de una pagina que dicen, letra a letra salvo espacios y signos, una nota o varias notas seguidas (Xpdf junta a veces dos notas en un
    renglon: «(1) DO L 204 de 21.7.1988, p. 37. (2) DO L 189 de 20.7.1990, p. 17.», o parte una en varios). Devuelve ([(i, j, a, b)], [las notas sin localizar]): las lineas
    i..j son las notas a..b (indices de `notas`, en el orden de PyMuPDF), y los blancos entre medias van con el tramo. El tramo tiene que ser EXACTO: lo que no lo es, no se toca."""
    esq = [_esqueleto(ln) for ln in lineas]
    es = [_esqueleto(x) for x in notas]
    n = len(lineas)
    usadas_l: set[int] = set()
    usadas_n: set[int] = set()
    tramos: list[tuple[int, int, int, int]] = []
    for a in range(len(notas)):
        if a in usadas_n or not es[a]:
            continue
        for i in range(n):
            if i in usadas_l or not esq[i] or not (es[a].startswith(esq[i]) or esq[i].startswith(es[a])):
                continue
            acum_l, acum_n, j, b = esq[i], es[a], i, a
            hallado = False
            while True:
                if acum_l == acum_n:
                    hallado = True
                    break
                if acum_n.startswith(acum_l):             # faltan lineas
                    j += 1
                    if j >= n or j in usadas_l:
                        break
                    acum_l += esq[j]
                elif acum_l.startswith(acum_n):           # la linea lleva mas notas
                    b += 1
                    if b >= len(es) or b in usadas_n:
                        break
                    acum_n += es[b]
                else:
                    break
            if hallado:
                tramos.append((i, j, a, b))
                usadas_l.update(range(i, j + 1))
                usadas_n.update(range(a, b + 1))
                break
    return tramos, [a for a in range(len(notas)) if a not in usadas_n]


def corte_de_nota_al_final(linea: str, nota: str) -> tuple[int, bool] | None:
    """(longitud del renglon sin la nota, si la nota iba pegada a una palabra sin espacio de por medio) si el renglon ACABA con `nota` (letra a letra salvo espacios y
    signos) y lleva texto delante; si no, None.

    12-oct-2026 (c138; defecto D1 de la revision c137). Xpdf, al leer una palabra partida por guion al pie de una columna, se come el guion y SIGUE por el bloque de
    notas que hay debajo: «...debe aplicarse a los procedi(1) DO L 281 de 23.11.1995, p. 31.» en una sola linea, y el resto de la palabra («mientos.») sale arriba de la
    columna siguiente. La nota no es un tramo de lineas (va pegada al final de una linea de cuerpo) y se quedaba dentro de la palabra. Se pide un esqueleto de 12
    caracteres como minimo: una nota muy corta («(1) Id.») podria acabar una linea de cuerpo por casualidad."""
    en = _esqueleto(nota)
    if len(en) < 12:
        return None
    esq: list[str] = []
    donde: list[int] = []
    for i, c in enumerate(linea):
        for e in _esqueleto(c):
            esq.append(e)
            donde.append(i)
    if len(esq) <= len(en) or "".join(esq[len(esq) - len(en):]) != en:
        return None
    # la llamada «(1)» / «( 1 )» empieza en el «(» que hay antes de la primera cifra de la nota; lo que va delante es el cuerpo
    llamada = donde[len(esq) - len(en)]
    while llamada > 0 and linea[llamada - 1] in "( \t":
        llamada -= 1
        if linea[llamada] == "(":
            break
    prefijo = linea[:llamada].rstrip()
    if not prefijo:
        return None
    return len(prefijo), llamada > 0 and not linea[llamada - 1].isspace()


def _palabras_del_flujo(textos: list[str]):
    from collections import Counter
    return Counter(re.findall(r"[^\W\d_]+", " ".join(textos).casefold()))


def _unir_palabra_partida(salida: list[tuple[str, int]], posiciones: list[int], pendientes: set[int]) -> list[Registro]:
    """Devuelve a su sitio el final de la palabra que Xpdf partio al pie de una columna (ver `corte_de_nota_al_final`): al renglon `i` (que acaba sin espacio en el
    principio de la palabra) se le pega el primer trozo del siguiente renglon con texto del flujo («mientos.»), SOLO si la palabra completa («procedimientos») esta en el
    propio documento sin partir. Si no, se deja como esta (el renglon cortado y el siguiente) y se dice."""
    registros: list[Registro] = []
    vocabulario = _palabras_del_flujo([t for t, _ in salida])
    por_posicion = {i: k for k, i in enumerate(posiciones)}
    for i in sorted(pendientes):
        k = por_posicion.get(i)
        if k is None:
            continue
        previa, pag = salida[k]
        sig = next((j for j in range(k + 1, len(salida)) if salida[j][0].strip()), None)
        ini = re.search(r"([^\W\d_]+)$", previa)
        fin = re.match(r"\s*([^\W\d_]+)", salida[sig][0]) if sig is not None else None
        if not ini or not fin or not fin.group(1)[0].islower() or not vocabulario.get((ini.group(1) + fin.group(1)).casefold(), 0):
            registros.append(Registro(pag, "PALABRA_PARTIDA_SIN_UNIR", previa[-30:], "el renglon acababa sin espacio en un trozo de palabra y no se encuentra la palabra entera en el documento"))
            continue
        resto = salida[sig][0][fin.end():]
        salida[k] = (previa + fin.group(1), pag)
        # lo que sigue al trozo (puntuacion pegada: «mientos.») se queda con la palabra; el renglon siguiente conserva el resto
        m_punt = re.match(r"[^\s\w]*", resto)
        if m_punt and m_punt.group(0):
            salida[k] = (salida[k][0] + m_punt.group(0), pag)
            resto = resto[m_punt.end():]
        salida[sig] = (resto.lstrip(), salida[sig][1])
        registros.append(Registro(pag, "PALABRA_UNIDA", ini.group(1) + fin.group(1), "el final de la palabra partida al pie de la columna, devuelto a su sitio"))
    return registros


@dataclass
class Registro:
    pagina: int
    clase: str            # FOLIO | NOTA | NOTA_SIN_LOCALIZAR | NOTA_PEGADA | PALABRA_UNIDA | PALABRA_PARTIDA_SIN_UNIR | MAQUETACION | MAQUETACION_SIN_LOCALIZAR
    texto: str
    como: str


def _sin_el_pie_pegado(nota: str, piezas: list[str]) -> str:
    """La nota sin el pie de pagina que PyMuPDF le pego detras (la ultima nota de la pagina 14 del GDP acaba en el «ES» del pie): solo si ese final es una pieza de maquetacion de la
    pagina. Sin piezas (la familia `eurlex`) no se llama."""
    nota = nota.rstrip()
    cambia = True
    while cambia:
        cambia = False
        for pieza in sorted(piezas, key=len, reverse=True):
            if pieza and len(nota) > len(pieza) and nota.endswith(pieza) and nota[-len(pieza) - 1].isspace():
                nota = nota[:-len(pieza)].rstrip()
                cambia = True
    return nota


def quitar_del_flujo(lp: list[tuple[str, int]], notas_por_pagina: list[list[str]] | None, n_paginas: int = 0,
                     piezas_por_pagina: list[list[str]] | None = None, folios_del_diario: bool = True) -> tuple[list[tuple[str, int]], list[Registro]]:
    """El flujo (linea, pagina) de `parsers.lineas_con_pagina` sin los folios y las notas del Diario (y, en los documentos que lo piden, sin la maquetacion que PyMuPDF confirma:
    `piezas_por_pagina`, ver `maquetacion_pymupdf`), y que se quito. Las lineas quitadas se borran enteras; el resto no cambia. `folios_del_diario=False` (las guias que no son del
    Diario, R15b) deja fuera las reglas de folio por texto: «L 12/3» o un «3/4» pueden ser contenido de una guia."""
    textos = [ln for ln, _ in lp]
    paginas = [p for _, p in lp]
    registros: list[Registro] = []
    quitar: set[int] = set()
    pendientes: set[int] = set()        # renglones a los que se corto una nota pegada a una palabra partida: hay que devolverles el final de la palabra
    # PRIMERO las notas, con todas las lineas de la pagina: la ultima linea de una nota puede ser un «ELI: http://…/oj.» que, suelto, parece el pie del Diario.
    if notas_por_pagina:
        indices: dict[int, list[int]] = defaultdict(list)
        for i, p in enumerate(paginas):
            indices[p].append(i)
        for n, notas in enumerate(notas_por_pagina, start=1):
            idx = indices.get(n, [])
            lineas = [textos[i] for i in idx]
            if piezas_por_pagina and n <= len(piezas_por_pagina):
                notas = [_sin_el_pie_pegado(nota, piezas_por_pagina[n - 1]) for nota in notas]
            tramos, sin_localizar = tramos_de_notas(lineas, notas)
            for i, j, a, b in tramos:
                quitar.update(idx[k] for k in range(i, j + 1))
                for k in range(a, b + 1):
                    registros.append(Registro(n, "NOTA", notas[k], "PyMuPDF: parrafo con llamada, en cuerpo menor y de referencia; coincide con las lineas %d-%d de la pagina" % (i + 1, j + 1)))
            for k in sin_localizar:
                # La nota pegada al final de un renglon de cuerpo (Xpdf, al partir una palabra al pie de una columna): se corta del renglon (c138, ver `corte_de_nota_al_final`)
                cortada = next(((i, c) for i in idx if i not in quitar for c in [corte_de_nota_al_final(textos[i], notas[k])] if c), None)
                if cortada is None:
                    registros.append(Registro(n, "NOTA_SIN_LOCALIZAR", notas[k], "PyMuPDF: nota del Diario en cuerpo menor; el flujo no la tiene como tramo exacto de lineas"))
                    continue
                i, (largo, pegada) = cortada
                textos[i] = textos[i][:largo]
                if pegada:
                    pendientes.add(i)
                registros.append(Registro(n, "NOTA_PEGADA", notas[k], "PyMuPDF: nota del Diario en cuerpo menor, pegada al final de un renglon de cuerpo; se corta del renglon"
                                          + (" (iba pegada a una palabra partida)" if pegada else "")))
    # Luego la maquetacion que PyMuPDF confirma (R15): cabecera, pie y folio con el numero de pagina, cubiertos EXACTAMENTE con lineas de la pagina
    if piezas_por_pagina:
        from . import maquetacion_pymupdf as M
        restantes: dict[int, list[int]] = defaultdict(list)
        for i, p in enumerate(paginas):
            if i not in quitar:
                restantes[p].append(i)
        for n, piezas in enumerate(piezas_por_pagina, start=1):
            idx = restantes.get(n, [])
            if not piezas or not idx:
                continue
            tramos, sin_usar = M.tramos_de_piezas([textos[i] for i in idx], piezas)
            for i, j, usadas in tramos:
                quitar.update(idx[k] for k in range(i, j + 1))
                for k in usadas:
                    registros.append(Registro(n, "MAQUETACION", piezas[k], "PyMuPDF: linea de la franja de la pagina que se repite en la plantilla; coincide con las lineas %d-%d de la pagina" % (i + 1, j + 1)))
            # Una pieza sin usar ya no esta en el flujo (la quito el detector de lineas repetidas) o va pegada a texto de cuerpo: esto ultimo se dice
            en_el_flujo = [M.esqueleto(textos[i]) for i in idx if i not in quitar]
            for k in sin_usar:
                e = M.esqueleto(piezas[k])
                if len(e) >= 6 and any(x.startswith(e) or x.endswith(e) for x in en_el_flujo):
                    registros.append(Registro(n, "MAQUETACION_SIN_LOCALIZAR", piezas[k], "PyMuPDF: linea de la franja de la pagina; en el flujo va pegada a otro texto y no se toca"))
    # Despues el folio y lo que lo acompana, sobre lo que queda
    resto = [i for i in range(len(lp)) if i not in quitar]
    for k in sorted(lineas_de_folio([textos[i] for i in resto], [paginas[i] for i in resto], n_paginas) if folios_del_diario else ()):
        i = resto[k]
        quitar.add(i)
        registros.append(Registro(paginas[i], "FOLIO", textos[i].strip(), "linea que es solo un folio, el idioma, la fecha de cabecera o el ELI del pie, junto a un folio"))
    posiciones = [i for i in range(len(lp)) if i not in quitar]
    salida = [(textos[i], paginas[i]) for i in posiciones]
    if pendientes:
        registros.extend(_unir_palabra_partida(salida, posiciones, pendientes))
    return salida, registros


def notas_con_testigo(ruta, ruta_rel: str, n_paginas: int) -> tuple[list[list[str]] | None, str]:
    """(notas del Diario de cada pagina, nota para `motor_extraccion`). Las notas necesitan PyMuPDF y el mismo numero de paginas que Xpdf: si faltan, None, se avisa y se anota
    («; notas del Diario sin testigo: …»). Los folios no necesitan el PDF."""
    notas = notas_del_pdf(ruta)
    if notas is None:
        print(f"aviso: {ruta_rel} es de la UE y PyMuPDF no esta disponible: se quitan los folios y no las notas al pie", file=sys.stderr)
        return None, "; notas del Diario sin testigo: PyMuPDF no disponible"
    if len(notas) != n_paginas:
        if any(notas):
            print(f"aviso: {ruta_rel} es de la UE, Xpdf da {n_paginas} paginas y PyMuPDF {len(notas)}: se quitan los folios y no las notas al pie", file=sys.stderr)
            return None, f"; notas del Diario sin testigo: {n_paginas} paginas con Xpdf y {len(notas)} con PyMuPDF"
        return None, ""
    return notas, ""


def registros_de(pdf) -> list[Registro]:
    """Lo que se quita (y lo que no se pudo quitar) del texto de un `TextoPdf` de la UE: para medir y para auditar. No cambia nada."""
    from . import parsers
    if not (getattr(pdf, "texto_ajeno_ue", False) or getattr(pdf, "maquetacion_del_pdf", None)):
        return []
    return quitar_del_flujo(parsers.lineas_con_pagina(pdf, quitar_ajeno=False), pdf.notas_del_diario, pdf.n_paginas, getattr(pdf, "maquetacion_del_pdf", None),
                            getattr(pdf, "texto_ajeno_ue", False))[1]
