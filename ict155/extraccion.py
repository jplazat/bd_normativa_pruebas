"""Extraccion de texto de PDF, con UTF-8 obligatorio.

El pdftotext de este equipo es Xpdf 4.00 y su codificacion de salida por defecto
es Latin-1: borra en silencio, sin error ni aviso, todo caracter que no quepa en
Latin-1. Una pasada asi concluyo que la biblioteca no tenia documentos en chino.
Por eso -enc UTF-8 va en cada invocacion y hay una prueba de regresion que lo
vigila.
"""
from __future__ import annotations
import collections
import hashlib
import re
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from . import config, superindices, texto_ajeno_ue
SALTO_PAGINA = '\x0c'
RANGOS = {'han': re.compile('[一-鿿㐀-䶿]'), 'cirilico': re.compile('[Ѐ-ӿ]'), 'griego': re.compile('[Ͱ-Ͽ]')}

class IngestaNoReproducible(RuntimeError):
    """La ingesta no ha podido completarse igual que otra vez.

    Se lanza cuando la extraccion se agota por tiempo. Un agotamiento depende de
    lo ocupada que este la maquina, asi que tratarlo como error blando produce
    bases distintas segun la carga, y una base que sale distinta segun la carga
    no es reconstruible. Reconstruible es la propiedad de la que cuelga todo lo
    demas, asi que esto detiene la ingesta en vez de degradarla.
    """

class ExtraccionError(RuntimeError):
    pass

@dataclass
class TextoPdf:
    ruta_relativa: str
    paginas: list[str] = field(default_factory=list)
    sha256: str = ''
    bytes: int = 0
    mtime_utc: str = ''
    hash_texto: str = ''
    caracteres_perdidos: int = 0
    motor: str = config.MOTOR_XPDF
    registros_exponentes: list = field(default_factory=list)
    texto_ajeno_ue: bool = False
    notas_del_diario: list | None = None
    maquetacion_del_pdf: list | None = None
    paginas_del_documento: int = 0

    @property
    def n_paginas(self) -> int:
        return self.paginas_del_documento or len(self.paginas)

    @property
    def texto(self) -> str:
        return '\n'.join(self.paginas)

    def pagina_de(self, indice_global: int) -> int:
        """Numero de pagina (1-based) que contiene un offset del texto unido."""
        acc = 0
        for i, p in enumerate(self.paginas):
            acc += len(p) + 1
            if indice_global < acc:
                return i + 1
        return self.n_paginas

def sha256_fichero(ruta: Path) -> str:
    from . import alcance_r3
    try:
        relativa = config.relativa(ruta)
    except ValueError:
        relativa = None
    if relativa in alcance_r3.altas():
        return alcance_r3.huella_fichero(ruta)
    h = hashlib.sha256()
    with config.abrir_biblioteca(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()
RE_MARCA_DE_AGUA = re.compile("[-`,']{6,}")

def quitar_marca_de_agua(texto: str) -> str:
    """`texto` sin los tramos de marca de agua editorial (ver `RE_MARCA_DE_AGUA`)."""
    return RE_MARCA_DE_AGUA.sub(lambda m: '' if len(set(m.group(0))) >= 2 else m.group(0), texto)

def normalizar(texto: str) -> str:
    """Normalizacion minima y conservadora: no toca el contenido, solo la forma.

    NFC porque el mismo caracter acentuado puede venir compuesto o descompuesto,
    y eso rompe comparaciones literales sin que se vea.
    """
    t = texto.replace('\r\n', '\n').replace('\r', '\n')
    t = unicodedata.normalize('NFC', t)
    t = re.sub('\xad\\s*', '', t)
    t = t.replace('\xa0', ' ')
    for c in ('\u200b', '\u200c', '\u200d', '\ufeff'):
        t = t.replace(c, '')
    return quitar_marca_de_agua(t)

def decodificar(crudo: bytes, ruta_rel: str='') -> tuple[str, int]:
    """Decodifica la salida de pdftotext, reparando CESU-8 si hace falta.

    Hallazgo del 1/8/2026: Xpdf 4.00, incluso con -enc UTF-8, emite **CESU-8**
    para los caracteres fuera del plano basico. Es decir, codifica cada mitad del
    par suplente por separado, lo que no es UTF-8 valido. Afecta a las letras
    matematicas en cursiva que los textos legales usan como variables de formula:
    los bytes ed a0 b5 ed b1 92 son U+D835 U+DC52, que juntos son U+1D452, la 'e'
    matematica.

    Se recompone el par en lugar de tirar el caracter: perder una variable de
    una formula es el fallo silencioso que este proyecto persigue. Devuelve el
    numero de suplentes que no se pudieron emparejar, que se registra por
    documento en lugar de silenciarse.
    """
    try:
        return (crudo.decode('utf-8'), 0)
    except UnicodeDecodeError:
        pass
    try:
        suelto = crudo.decode('utf-8', 'surrogatepass')
    except UnicodeError as e:
        raise ExtraccionError(f'salida no decodificable en {ruta_rel}: {e}. Revisar que se paso -enc UTF-8.') from e
    out: list[str] = []
    huerfanos = 0
    i, n = (0, len(suelto))
    while i < n:
        c = suelto[i]
        if '\ud800' <= c <= '\udbff' and i + 1 < n and ('\udc00' <= suelto[i + 1] <= '\udfff'):
            out.append(chr(65536 + (ord(c) - 55296 << 10) + (ord(suelto[i + 1]) - 56320)))
            i += 2
            continue
        if '\ud800' <= c <= '\udfff':
            out.append('�')
            huerfanos += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return (''.join(out), huerfanos)

def _paginas_pymupdf(ruta) -> list[str] | None:
    """Extraccion con PyMuPDF. Conserva guiones lexicos partidos en el salto de
    linea, que Xpdf pierde: "Norma UNE-
EN 12830" sale de Xpdf como "UNEEN",
    y ese guion es parte del nombre de la norma, no una particion silabica."""
    try:
        import fitz
    except ImportError:
        return None
    try:
        d = fitz.open(ruta)
        return [pag.get_text() for pag in d]
    except Exception:
        return None
RE_FIRMA_DOBLADA = re.compile('([^\\W\\d_])\\1([^\\W\\d_])\\2([^\\W\\d_])\\3')

def firmas_dobladas(texto: str) -> list[str]:
    """Los tramos de tres pares de letras iguales seguidos (al menos dos letras distintas) de `texto`."""
    return [m.group(0) for m in RE_FIRMA_DOBLADA.finditer(texto) if len({m.group(1), m.group(2), m.group(3)}) > 1]

def _solo_letras(texto: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFKC', texto).casefold() if c.isalpha()))

def paginas_con_capa_duplicada(paginas: list[str], paginas_pymupdf: list[str]) -> list[int]:
    """Indices (desde 0) de las paginas de Xpdf con alguna firma que PyMuPDF no tiene en esa pagina."""
    malas = []
    for i, (x, m) in enumerate(zip(paginas, paginas_pymupdf)):
        firmas = firmas_dobladas(x)
        if not firmas:
            continue
        flujo = _solo_letras(m)
        if any((_solo_letras(f) not in flujo for f in firmas)):
            malas.append(i)
    return malas
LETRAS_DE_PALABRA_LARGA = 6
LETRAS_DE_TRAMO = 4
SALTOS_ENTRE_TRAMOS = 4
CANDIDATAS_POR_PAGINA = 40
LETRAS_MAXIMAS_DE_CANDIDATA = 70
LETRAS_MAXIMAS_DE_FLUJO = 30000
ESTADOS_MAXIMOS = 20000
FRACCION_DE_MOBILIARIO = 0.2
FRACCION_DE_MOBILIARIO_PARA_QUITAR = 1 / 3
LETRAS_DE_RENGLON_DE_MOBILIARIO = 8
FRACCION_DE_MOBILIARIO_CORTO = 0.5
LETRAS_DE_RENGLON_DE_MOBILIARIO_CORTO = 3
VECES_DE_MOBILIARIO_POR_PAGINA = 2
TOLERANCIA_DE_COBERTURA = 0
NODOS_MAXIMOS_DE_COBERTURA = 30000
SOLUCIONES_MAXIMAS = 4
RENGLONES_MAXIMOS_CANDIDATOS = 400
CARACTERES_MINIMOS_DE_RENGLON = 3
RENGLONES_MINUSCULOS_MAXIMOS = 3
CARACTERES_DE_TRAMO_DE_ORDEN = 5
FRACCION_DE_VOTOS_DE_ORDEN = 0.4
RE_NUMERACION = re.compile('[-−]?\\(?\\d+(?:[.,]\\d+)*[.)]?')

def _bigramas(flujo: str) -> dict[str, list[int]]:
    """Las posiciones de cada par de letras seguidas de `flujo`."""
    d: dict[str, list[int]] = {}
    for i in range(len(flujo) - 1):
        d.setdefault(flujo[i:i + 2], []).append(i)
    return d

def _es_intercalacion(palabra: str, flujo: str, bigramas: dict[str, list[int]]) -> bool:
    """Si `palabra` (solo letras) se puede repartir letra a letra entre dos tramos seguidos de `flujo`, de
    LETRAS_DE_TRAMO o mas cada uno, saltando de uno a otro SALTOS_ENTRE_TRAMOS veces o mas.

    Busqueda por estados (posicion siguiente en cada tramo, letras ya puestas en cada uno, tramo de la ultima letra y saltos),
    sin enumerar las posiciones de salida: un tramo «pendiente» (una sola letra puesta) se ancla cuando llega la segunda, por
    el indice de pares de letras. Por simetria la primera letra va siempre al tramo A."""
    n, lf = (len(palabra), len(flujo))
    if n < 2 * LETRAS_DE_TRAMO or lf < 2 * LETRAS_DE_TRAMO:
        return False
    tope = SALTOS_ENTRE_TRAMOS
    estados = {(palabra[0], None, 1, 0, 0, 0)}
    for c in palabra[1:]:
        nuevos = set()
        for sa, sb, la, lb, ultimo, saltos in estados:
            if isinstance(sa, str):
                for o in bigramas.get(sa + c, ()):
                    nuevos.add((o + 2, sb, la + 1, lb, 0, min(saltos + (ultimo != 0), tope)))
            elif sa < lf and flujo[sa] == c:
                nuevos.add((sa + 1, sb, min(la + 1, LETRAS_DE_TRAMO), lb, 0, min(saltos + (ultimo != 0), tope)))
            if sb is None:
                nuevos.add((sa, c, la, 1, 1, min(saltos + (ultimo != 1), tope)))
            elif isinstance(sb, str):
                for o in bigramas.get(sb + c, ()):
                    nuevos.add((sa, o + 2, la, lb + 1, 1, min(saltos + (ultimo != 1), tope)))
            elif sb < lf and flujo[sb] == c:
                nuevos.add((sa, sb + 1, la, min(lb + 1, LETRAS_DE_TRAMO), 1, min(saltos + (ultimo != 1), tope)))
        if not nuevos or len(nuevos) > ESTADOS_MAXIMOS:
            return False
        estados = nuevos
    return any((la >= LETRAS_DE_TRAMO and lb >= LETRAS_DE_TRAMO and (saltos >= tope) and (not isinstance(sa, str)) and (not isinstance(sb, str)) for sa, sb, la, lb, _, saltos in estados))

def _palabras_largas(pagina: str) -> list[str]:
    """Las palabras de `pagina` de LETRAS_DE_PALABRA_LARGA letras o mas, solo con sus letras y en minuscula."""
    out = []
    for t in pagina.split():
        letras = _solo_letras(t)
        if len(letras) >= LETRAS_DE_PALABRA_LARGA:
            out.append(letras)
    return out

def _mobiliario(paginas_pymupdf: list[str]) -> str:
    """Las letras de los renglones que se repiten en el 20 % de las paginas (3 como minimo): cabeceras, pies y marcas de agua."""
    veces: dict[str, int] = {}
    for p in paginas_pymupdf:
        for ln in {_solo_letras(r) for r in p.split('\n')}:
            if len(ln) >= LETRAS_DE_RENGLON_DE_MOBILIARIO:
                veces[ln] = veces.get(ln, 0) + 1
    minimo = max(3, FRACCION_DE_MOBILIARIO * len(paginas_pymupdf))
    return ''.join(sorted((ln for ln, n in veces.items() if n >= minimo)))[:LETRAS_MAXIMAS_DE_FLUJO]

def palabras_revueltas(pagina_xpdf: str, flujo_pymupdf: str, verificadas, mobiliario: str='', bigramas_mobiliario: dict | None=None) -> list[str]:
    """Las palabras revueltas de la pagina de Xpdf (ver arriba): las de 6 letras o mas que no estan en el texto de PyMuPDF
    de la pagina ni entre las `verificadas` del documento y que son la intercalacion de dos tramos de ese texto sin serlo
    de dos del `mobiliario`."""
    if len(flujo_pymupdf) > LETRAS_MAXIMAS_DE_FLUJO:
        return []
    candidatas, vistas = ([], set())
    for t in _palabras_largas(pagina_xpdf):
        if t not in flujo_pymupdf and t not in verificadas and (t not in vistas):
            vistas.add(t)
            candidatas.append(t[:LETRAS_MAXIMAS_DE_CANDIDATA])
    if not candidatas:
        return []
    bigramas = _bigramas(flujo_pymupdf)
    if mobiliario and bigramas_mobiliario is None:
        bigramas_mobiliario = _bigramas(mobiliario)
    return [t for t in candidatas[:CANDIDATAS_POR_PAGINA] if _es_intercalacion(t, flujo_pymupdf, bigramas) and (not (mobiliario and _es_intercalacion(t, mobiliario, bigramas_mobiliario)))]

def paginas_con_texto_revuelto(paginas: list[str], paginas_pymupdf: list[str]) -> list[int]:
    """Indices (desde 0) de las paginas de Xpdf con alguna palabra revuelta (ver arriba)."""
    flujos_x = [_solo_letras(x) for x in paginas]
    flujos_m = [_solo_letras(m) for m in paginas_pymupdf]
    verificadas = _palabras_verificadas(paginas, paginas_pymupdf, flujos_x, flujos_m)
    mobiliario = _mobiliario(paginas_pymupdf)
    bigramas_mobiliario = _bigramas(mobiliario) if mobiliario else None
    return [i for i, x in enumerate(paginas) if palabras_revueltas(x, flujos_m[i], verificadas, mobiliario, bigramas_mobiliario)]

def _palabras_verificadas(paginas, paginas_pymupdf, flujos_x, flujos_m) -> set[str]:
    """Las palabras largas que Xpdf y PyMuPDF leen igual en alguna pagina del documento."""
    verificadas: set[str] = set()
    for i, ms in enumerate(paginas_pymupdf):
        verificadas.update((t for t in _palabras_largas(paginas[i]) if t in flujos_m[i]))
        verificadas.update((t for t in _palabras_largas(ms) if t in flujos_x[i]))
    return verificadas

def _solo_alnum(texto: str) -> str:
    """Las letras y las cifras de `texto`, en minuscula y sin espacios ni signos."""
    return ''.join((c for c in unicodedata.normalize('NFKC', texto).casefold() if c.isalnum()))

def _renglones_de_mobiliario(paginas_pymupdf: list[str]) -> tuple[set[str], set[str]]:
    """(largos, cortos): los renglones de PyMuPDF que son mobiliario (cabeceras, pies, marcas de agua) y que se quitan si
    estaban mezclados con un renglon de cuerpo. Un renglon es mobiliario si esta en muchas paginas y en cada una sale una
    o dos veces (una cabecera, un pie); «(all parts)», una referencia o una nota que se repite en el cuerpo (ocho veces en
    una pagina, 4 de 15 paginas) no lo es. `largos`: las letras y cifras de los de 8 letras o mas que estan en la tercera
    parte de las paginas o mas (3 como minimo). Con las cifras, no solo las letras como `_mobiliario`: «[SOURCE: ISO/IEC
    27035-1:2016, 3.5]» y «[SOURCE: ISO/IEC 27000:2018, 3.35]» son dos renglones, no el mismo repetido. `cortos`: los
    renglones en crudo, sin espacios, de 3 letras o mas que estan en la mitad de las paginas o mas (3 como minimo):
    «ISO 23412:2020», «SIST EN 18031-1:2024»; una «NOTA» suelta no llega a tanto."""
    por_pagina: dict[tuple[str, str], list[int]] = {}
    for p in paginas_pymupdf:
        en_pagina: dict[tuple[str, str], int] = {}
        for r in p.split('\n'):
            letras = len(_solo_letras(r))
            if letras >= LETRAS_DE_RENGLON_DE_MOBILIARIO:
                clave = ('L', _solo_alnum(r))
                en_pagina[clave] = en_pagina.get(clave, 0) + 1
            if letras >= LETRAS_DE_RENGLON_DE_MOBILIARIO_CORTO:
                clave = ('C', ''.join(r.split()))
                en_pagina[clave] = en_pagina.get(clave, 0) + 1
        for clave, veces in en_pagina.items():
            por_pagina.setdefault(clave, []).append(veces)
    minimo = max(3, FRACCION_DE_MOBILIARIO_PARA_QUITAR * len(paginas_pymupdf))
    minimo_corto = max(3, FRACCION_DE_MOBILIARIO_CORTO * len(paginas_pymupdf))
    out: dict[str, set[str]] = {'L': set(), 'C': set()}
    for (tipo, r), veces in por_pagina.items():
        if len(veces) >= (minimo if tipo == 'L' else minimo_corto) and sorted(veces)[len(veces) // 2] <= VECES_DE_MOBILIARIO_POR_PAGINA:
            out[tipo].add(r)
    return (out['L'], out['C'])

def _cubrir_renglones(necesita: dict[str, int], candidatos: list, tolerancia: int) -> tuple[list[tuple], bool]:
    """Los conjuntos de `candidatos` ([(indice, {caracter: veces}, es_minusculo)]) cuya suma de caracteres es la de
    `necesita` con a lo sumo `tolerancia` caracteres de menos y otros tantos de mas. Devuelve (hasta SOLUCIONES_MAXIMAS
    conjuntos como tuplas de indices, si la busqueda se agoto). Busqueda por ramificacion y poda: se ramifica por el
    caracter mas escaso de los que faltan (el renglon que mas veces lo trae, incluido o no) y se corta cuando alguno de los
    que faltan ya no los pueden aportar los renglones sin decidir; no depende del reloj, asi que sale lo mismo siempre."""
    utiles = []
    for idx, c, minusculo in candidatos:
        if sum((max(0, v - necesita.get(ch, 0)) for ch, v in c.items())) <= tolerancia and (not any((ch.isdigit() and v > necesita.get(ch, 0) for ch, v in c.items()))):
            utiles.append((idx, c, minusculo))
    if not utiles:
        return ([], False)
    if len(utiles) > RENGLONES_MAXIMOS_CANDIDATOS:
        return ([], True)
    letras = list(necesita)
    cifras = [ch for ch in letras if ch.isdigit()]
    disponibles = dict.fromkeys(letras, 0)
    for _, c, _ in utiles:
        for ch, v in c.items():
            if ch in disponibles:
                disponibles[ch] += v
    soluciones: list[tuple] = []
    estado = {'nodos': 0, 'agotado': False}

    def buscar(sin_decidir, quedan, disp, elegidos, sobrante, minusculos):
        if len(soluciones) >= SOLUCIONES_MAXIMAS or estado['agotado']:
            return
        estado['nodos'] += 1
        if estado['nodos'] > NODOS_MAXIMOS_DE_COBERTURA:
            estado['agotado'] = True
            return
        if sum((max(0, quedan[ch] - disp[ch]) for ch in letras)) > tolerancia or any((quedan[ch] > disp[ch] for ch in cifras)):
            return
        if sum(quedan.values()) <= tolerancia and (not any((quedan[ch] for ch in cifras))):
            soluciones.append(tuple(elegidos))
            return
        if not sin_decidir:
            return
        escasa = min((ch for ch in letras if quedan[ch] > 0), key=lambda ch: (disp[ch], ch))
        k = max((k for k in sin_decidir if utiles[k][1].get(escasa, 0) > 0), key=lambda k: (utiles[k][1][escasa], -k), default=None)
        if k is None:
            return
        resto = [x for x in sin_decidir if x != k]
        idx, c, minusculo = utiles[k]
        disp2 = dict(disp)
        for ch, v in c.items():
            if ch in disp2:
                disp2[ch] -= v
        sobra = sobrante + sum((max(0, v - quedan.get(ch, 0)) for ch, v in c.items()))
        if sobra <= tolerancia and (not any((ch.isdigit() and v > quedan.get(ch, 0) for ch, v in c.items()))) and (minusculos + minusculo <= RENGLONES_MINUSCULOS_MAXIMOS):
            quedan2 = dict(quedan)
            for ch, v in c.items():
                if ch in quedan2:
                    quedan2[ch] = max(0, quedan2[ch] - v)
            buscar(resto, quedan2, disp2, elegidos + [idx], sobra, minusculos + minusculo)
        buscar(resto, quedan, disp2, elegidos, sobrante, minusculos)
    buscar(list(range(len(utiles))), dict(necesita), disponibles, [], 0, 0)
    return (soluciones, estado['agotado'])

def _ordenar_renglones(linea: str, cuerpo: list[tuple[int, str]]) -> list[int] | None:
    """Los indices de `cuerpo` ([(indice en PyMuPDF, sus caracteres)], en el orden de PyMuPDF) en el orden en que sus
    caracteres estan en `linea` (la de Xpdf), o None si no se puede asegurar. Cada renglon vota por la posicion de la linea
    donde caen sus tramos de CARACTERES_DE_TRAMO_DE_ORDEN caracteres; si la posicion mas votada no reune el
    FRACCION_DE_VOTOS_DE_ORDEN de los tramos del renglon, no se fia (un renglon corto o el que esta revuelto no se sitúa).
    Si los renglones situados ya vienen en ese orden en PyMuPDF, se queda el de PyMuPDF; si no, solo se reordena cuando
    estan todos situados; si falta alguno por situar y el orden de PyMuPDF no coincide, None."""
    n = CARACTERES_DE_TRAMO_DE_ORDEN
    indice: dict[str, list[int]] = {}
    for i in range(len(linea) - n + 1):
        indice.setdefault(linea[i:i + n], []).append(i)
    posicion: dict[int, int] = {}
    for j, letras in cuerpo:
        tramos = len(letras) - n + 1
        if tramos < 3:
            continue
        votos: dict[int, int] = {}
        for o in range(tramos):
            for p in indice.get(letras[o:o + n], ()):
                votos[p - o] = votos.get(p - o, 0) + 1
        if not votos:
            continue
        fuerza = {d: sum((v for k, v in votos.items() if abs(k - d) <= 2)) for d in votos}
        mejor = max(votos, key=lambda d: (fuerza[d], -d))
        if fuerza[mejor] >= max(3, FRACCION_DE_VOTOS_DE_ORDEN * tramos):
            posicion[j] = mejor
    indices = [j for j, _ in cuerpo]
    en_pymupdf = [j for j in indices if j in posicion]
    en_la_linea = sorted(en_pymupdf, key=lambda j: (posicion[j], j))
    if en_la_linea == en_pymupdf:
        return indices
    return en_la_linea if len(en_pymupdf) == len(indices) else None

def reparar_texto_revuelto(paginas: list[str], paginas_pymupdf: list[str], excluir=frozenset()) -> dict[int, tuple[str, int]]:
    """{indice de pagina (desde 0): (su texto con los renglones revueltos cambiados, cuantos renglones)} de las paginas de
    Xpdf con palabras revueltas cuyos renglones se pueden alinear con seguridad con renglones enteros de PyMuPDF (ver
    arriba). Los renglones sin palabras revueltas, y los que no se pueden alinear, quedan exactamente como estaban. No se
    toca la pagina 1 ni las de `excluir`. Con otro numero de paginas no se compara nada."""
    if len(paginas) != len(paginas_pymupdf):
        return {}
    flujos_x = [_solo_letras(x) for x in paginas]
    flujos_m = [_solo_letras(m) for m in paginas_pymupdf]
    verificadas = _palabras_verificadas(paginas, paginas_pymupdf, flujos_x, flujos_m)
    mobiliario = _mobiliario(paginas_pymupdf)
    bigramas_mobiliario = _bigramas(mobiliario) if mobiliario else None
    mob_largos = mob_cortos = None
    out: dict[int, tuple[str, int]] = {}
    for i, x in enumerate(paginas):
        if i == 0 or i in excluir:
            continue
        revueltas = set(palabras_revueltas(x, flujos_m[i], verificadas, mobiliario, bigramas_mobiliario))
        if not revueltas:
            continue
        if mob_largos is None:
            mob_largos, mob_cortos = _renglones_de_mobiliario(paginas_pymupdf)
        renglones = [normalizar(r).strip() for r in paginas_pymupdf[i].split('\n')]
        info: dict[int, tuple[str, bool]] = {}
        candidatos = []
        for j, r in enumerate(renglones):
            a = _solo_alnum(r)
            numeracion = bool(a) and RE_NUMERACION.fullmatch(r) is not None
            if len(a) < CARACTERES_MINIMOS_DE_RENGLON and (not numeracion):
                continue
            info[j] = (a, len(_solo_letras(r)) >= LETRAS_DE_RENGLON_DE_MOBILIARIO and a in mob_largos or ''.join(r.split()) in mob_cortos)
            c: dict[str, int] = {}
            for ch in a:
                c[ch] = c.get(ch, 0) + 1
            candidatos.append((j, c, len(a) < CARACTERES_MINIMOS_DE_RENGLON))
        usados: set[int] = set()
        lineas = x.split('\n')
        cambios = 0
        for k, ln in enumerate(lineas):
            if not any((_solo_letras(t)[:LETRAS_MAXIMAS_DE_CANDIDATA] in revueltas for t in ln.split())):
                continue
            a_linea = _solo_alnum(ln)
            necesita: dict[str, int] = {}
            for ch in a_linea:
                necesita[ch] = necesita.get(ch, 0) + 1
            libres = [cand for cand in candidatos if cand[0] not in usados]
            soluciones: list[tuple] = []
            for tolerancia in range(TOLERANCIA_DE_COBERTURA + 1):
                soluciones, _ = _cubrir_renglones(necesita, libres, tolerancia)
                if soluciones:
                    break
            if not soluciones:
                continue
            cuerpos = {tuple(sorted((renglones[j] for j in s if not info[j][1]))) for s in soluciones}
            if len(cuerpos) != 1:
                continue
            solucion = soluciones[0]
            cuerpo = [(j, info[j][0]) for j in sorted(solucion) if not info[j][1]]
            if not cuerpo:
                continue
            orden = _ordenar_renglones(a_linea, cuerpo)
            if orden is None:
                continue
            nuevo = '\n'.join((renglones[j] for j in orden))
            if nuevo == ln:
                continue
            lineas[k] = nuevo
            usados.update(solucion)
            cambios += 1
        if cambios:
            out[i] = ('\n'.join(lineas), cambios)
    return out

def _capa_duplicada(ruta: Path, ruta_rel: str, paginas: list[str], pymupdf_ya_fallo: bool=False) -> tuple[dict[int, str], str, list[str] | None]:
    """({indice de pagina: su texto de PyMuPDF}, nota para `documento.motor_extraccion`, paginas de PyMuPDF o None si no se
    pueden comparar) de las paginas con la capa de texto duplicada (tres pares de letras iguales seguidos: la pagina entera
    viene de PyMuPDF). PyMuPDF se lee SIEMPRE, una sola vez: el texto revuelto sin pares solo se ve comparandolo con el suyo
    (`_texto_revuelto`, que usa las paginas que devuelve esta funcion). `pymupdf_ya_fallo`: con ICT155_MOTOR=pymupdf
    `extraer` ya aviso de que PyMuPDF no funciona (S3) y el documento se graba como Xpdf; sin firmas no se avisa dos veces."""
    firmas = any((firmas_dobladas(p) for p in paginas))
    pgs = _paginas_pymupdf(ruta)
    if pgs is None:
        if firmas:
            print(f'aviso: {ruta_rel} tiene tramos de letras dobladas y PyMuPDF no esta disponible: el texto se queda como lo da Xpdf', file=sys.stderr)
            return ({}, '; capa duplicada sin comprobar: PyMuPDF no disponible', None)
        if pymupdf_ya_fallo:
            return ({}, '', None)
        print(f'aviso: PyMuPDF no esta disponible: no se ha comprobado si {ruta_rel} tiene texto revuelto; el texto se queda como lo da Xpdf', file=sys.stderr)
        return ({}, '; texto revuelto sin comprobar: PyMuPDF no disponible', None)
    if len(pgs) != len(paginas):
        if firmas:
            print(f'aviso: {ruta_rel} tiene tramos de letras dobladas pero Xpdf da {len(paginas)} paginas y PyMuPDF {len(pgs)}: el texto se queda como lo da Xpdf', file=sys.stderr)
            return ({}, f'; capa duplicada sin comprobar: {len(paginas)} paginas con Xpdf y {len(pgs)} con PyMuPDF', None)
        print(f'aviso: {ruta_rel}: Xpdf da {len(paginas)} paginas y PyMuPDF {len(pgs)}: no se ha comprobado si tiene texto revuelto; el texto se queda como lo da Xpdf', file=sys.stderr)
        return ({}, f'; texto revuelto sin comprobar: {len(paginas)} paginas con Xpdf y {len(pgs)} con PyMuPDF', None)
    dobladas = paginas_con_capa_duplicada(paginas, pgs) if firmas else []
    if not dobladas:
        return ({}, '', pgs)
    return ({i: normalizar(pgs[i]) for i in dobladas}, f"; capa duplicada: {len(dobladas)} pgs de PyMuPDF: {','.join((str(i + 1) for i in dobladas))}", pgs)

def _texto_revuelto(paginas: list[str], paginas_pymupdf: list[str], excluir=frozenset()) -> tuple[list[str], str]:
    """(las paginas con los renglones revueltos cambiados por los de PyMuPDF, nota para `documento.motor_extraccion`).
    Se llama con las paginas FINALES (despues de la capa duplicada y del -layout): el -layout se decide, pagina a pagina,
    sobre el texto de siempre de Xpdf, y repararlo antes lo habria cambiado donde el -layout rinde mas (medido el 11-oct-2026:
    JCGM 101 pags. 21 y 70, EN 18031-1 pag. 5). `excluir`: las paginas que ya vienen enteras de PyMuPDF.
    La portada (pagina 1) no se cambia nunca por texto revuelto: de ella sale el titulo de la obra, y PyMuPDF la ordena de
    otra manera (medido el 11-oct-2026: ILAC G8 pasaba a titularse «About ILAC» y las EN 18031-2/-3 perdian su identificador)."""
    reparadas = reparar_texto_revuelto(paginas, paginas_pymupdf, excluir=excluir)
    if not reparadas:
        return (paginas, '')
    nuevas = list(paginas)
    for i, (texto, _) in reparadas.items():
        nuevas[i] = texto
    return (nuevas, f"; texto revuelto: {sum((n for _, n in reparadas.values()))} renglones en {len(reparadas)} pgs de PyMuPDF: {','.join((str(i + 1) for i in sorted(reparadas)))}")
DOCUMENTOS_CON_CAPA_OCR = frozenset({'01_Conocimiento/Normas_tecnicas/NORMA_PAGO_34.pdf'})
RE_UNION_DE_RENGLON = re.compile('(\\S)-[ \\t]*\\n[ \\t]*(\\S)')
RE_PUNTOS_DE_RELLENO = re.compile('\\.{5,}|…{2,}')
RE_PALABRA_CON_SIGNOS = re.compile('([(\\[“\\"\'‘]*)([^\\W\\d_]+)([.,;:)\\]”\\"\'’]*)')
RE_CAPITULAR = re.compile('(?<!\\S)([A-Z]) ([a-z]{3,})(?![\\w])')
LETRAS_MINIMAS_DE_INTERCALADA = 6
FICHAS_POR_VENTANA = (2, 3, 4)

def _fichas_de_pymupdf(pagina_pymupdf: str) -> tuple[list[str], list[str]]:
    """(fichas con el guion de final de renglon conservado, fichas con ese guion quitado): la pagina de PyMuPDF como la escribe el PDF y como la deja Xpdf."""
    t = unicodedata.normalize('NFKC', pagina_pymupdf)
    return (RE_UNION_DE_RENGLON.sub('\\1-\\2', t).split(), RE_UNION_DE_RENGLON.sub('\\1\\2', t).split())

def _son_palabras(partes) -> bool:
    """Si cada ficha es una palabra de letras, con un signo de apertura solo delante de la primera y uno de cierre solo detras de la ultima."""
    for k, p in enumerate(partes):
        m = RE_PALABRA_CON_SIGNOS.fullmatch(p)
        if not m or (m.group(1) and k != 0) or (m.group(3) and k != len(partes) - 1):
            return False
    return True

def _es_mezcla_de_dos(ficha: str, partes) -> bool:
    """Si `ficha` es una mezcla letra a letra de dos tramos seguidos de `partes` (cada tramo, la union de una o mas fichas, en su orden)."""
    for j in range(1, len(partes)):
        a, b = (''.join(partes[:j]), ''.join(partes[j:]))
        if len(a) + len(b) != len(ficha):
            continue
        alcanzable = [[False] * (len(b) + 1) for _ in range(len(a) + 1)]
        alcanzable[0][0] = True
        for i in range(len(a) + 1):
            for k in range(len(b) + 1):
                if not alcanzable[i][k] or i + k >= len(ficha):
                    continue
                c = ficha[i + k]
                if i < len(a) and a[i] == c:
                    alcanzable[i + 1][k] = True
                if k < len(b) and b[k] == c:
                    alcanzable[i][k + 1] = True
        if alcanzable[len(a)][len(b)]:
            return True
    return False

def palabras_con_testigo(pagina: str, pagina_pymupdf: str, *, capa_ocr: bool) -> tuple[str, list[tuple[str, str, str, int]]]:
    """(la pagina de Xpdf con las palabras pegadas, intercaladas y capitulares reparadas, [(clase, antes, despues, veces)]). Ver arriba. `pagina_pymupdf` ya normalizada."""
    cambios: dict[tuple[str, str, str], int] = {}
    salida = pagina
    con, sin = _fichas_de_pymupdf(pagina_pymupdf)
    conjunto = set(con) | set(sin)
    if capa_ocr:
        ventanas: dict[str, set[tuple]] = {}
        vecindades: dict[str, set[tuple]] = {}
        firmas: dict[str, list[tuple]] = {}
        pegadas_en_pymupdf: dict[str, set[tuple]] = {}
        for seq in (con, sin):
            for i, f in enumerate(seq):
                pegadas_en_pymupdf.setdefault(f, set()).add((seq[i - 1] if i else None, seq[i + 1] if i + 1 < len(seq) else None))
                for k in FICHAS_POR_VENTANA:
                    if i + k > len(seq):
                        break
                    partes = tuple(seq[i:i + k])
                    union = ''.join(partes)
                    siguiente = seq[i + k] if i + k < len(seq) else None
                    ventanas.setdefault(union, set()).add(partes)
                    vecindades.setdefault(union, set()).add((seq[i - 1] if i else None, siguiente))
                    firmas.setdefault(''.join(sorted(union)), []).append((partes, siguiente))
        con_puntos: set[str] = set()
        for ln in pagina.split('\n'):
            if RE_PUNTOS_DE_RELLENO.search(ln):
                con_puntos.update(ln.split())
        fichas = [(m.start(), m.end(), m.group()) for m in re.finditer('\\S+', pagina)]
        cuenta_x = collections.Counter((f[2] for f in fichas))
        cuenta_m = collections.Counter(con)
        reemplazos: list[tuple[int, int, str, str]] = []
        for idx, (ini, fin, t) in enumerate(fichas):
            if t in con_puntos or len(t) < 3:
                continue
            anterior = fichas[idx - 1][2] if idx else None
            siguiente = fichas[idx + 1][2] if idx + 1 < len(fichas) else None
            if t in conjunto:
                if cuenta_x[t] > cuenta_m[t] and RE_PALABRA_CON_SIGNOS.fullmatch(t) and (t in ventanas) and (len(ventanas[t]) == 1) and _son_palabras(next(iter(ventanas[t]))) and ((anterior, siguiente) in vecindades[t]) and ((anterior, siguiente) not in pegadas_en_pymupdf[t]):
                    reemplazos.append((ini, fin, ' '.join(next(iter(ventanas[t]))), 'pegadas'))
                continue
            if RE_PALABRA_CON_SIGNOS.fullmatch(t) and t in ventanas:
                if len(ventanas[t]) == 1 and _son_palabras(next(iter(ventanas[t]))):
                    reemplazos.append((ini, fin, ' '.join(next(iter(ventanas[t]))), 'pegadas'))
                continue
            if len(t) >= LETRAS_MINIMAS_DE_INTERCALADA:
                buenas = {partes for partes, sig in firmas.get(''.join(sorted(t)), []) if sig is not None and sig == siguiente and (''.join(partes) != t) and _es_mezcla_de_dos(t, partes)}
                if len(buenas) == 1:
                    reemplazos.append((ini, fin, ' '.join(next(iter(buenas))), 'intercaladas'))
        for ini, fin, nuevo, clase in sorted(reemplazos, reverse=True):
            antes = salida[ini:fin]
            salida = salida[:ini] + nuevo + salida[fin:]
            cambios[clase, antes, nuevo] = cambios.get((clase, antes, nuevo), 0) + 1
    pares = set(zip(con, con[1:])) | set(zip(sin, sin[1:]))
    for a, b in sorted(set(RE_CAPITULAR.findall(salida))):
        if (a, b) not in pares and a + b in conjunto:
            salida, n = re.subn('(?<![^\\s])' + a + ' ' + b + '(?!\\w)', a + b, salida)
            if n:
                cambios['capitular', f'{a} {b}', a + b] = n
    return (salida, [(c, a, d, n) for (c, a, d), n in cambios.items()])

def _palabras_con_testigo(paginas: list[str], paginas_pymupdf: list[str], capa_ocr: bool) -> tuple[list[str], str]:
    """(las paginas con las palabras reparadas, nota para `documento.motor_extraccion`). Con otro numero de paginas no se compara nada."""
    if len(paginas) != len(paginas_pymupdf):
        return (paginas, '')
    nuevas = list(paginas)
    cambiadas: list[int] = []
    total = 0
    for i, (x, m) in enumerate(zip(paginas, paginas_pymupdf)):
        if not capa_ocr and (not RE_CAPITULAR.search(x)):
            continue
        nueva, cambios = palabras_con_testigo(x, normalizar(m), capa_ocr=capa_ocr)
        if cambios:
            nuevas[i] = nueva
            cambiadas.append(i + 1)
            total += sum((c[3] for c in cambios))
    if not cambiadas:
        return (paginas, '')
    return (nuevas, f"; palabras con testigo: {total} en {len(cambiadas)} pgs de PyMuPDF: {','.join(map(str, cambiadas))}")
RE_ROTULO_DE_FILA = re.compile('^[A-Z]{1,3}\\d{1,3}(?:[./]\\d{1,3})*(?:/[A-Z]{1,3}\\d{1,3}(?:\\.\\d{1,3})?)?$')

def _rotulos_de_fila(texto: str) -> list[str]:
    """Los rotulos de fila de un texto, en el orden en que aparecen."""
    return [t for t in texto.split() if RE_ROTULO_DE_FILA.match(t)]

def _tiene_rotulos_sueltos(pagina: str) -> bool:
    """Si algun renglon de la pagina son dos o mas rotulos de fila y nada mas."""
    for ln in pagina.split('\n'):
        toks = ln.split()
        if len(toks) >= 2 and all((RE_ROTULO_DE_FILA.match(t) for t in toks)):
            return True
    return False

def _palabras_sin_guion_de_renglon(texto: str):
    """El multiconjunto de palabras de una pagina de PyMuPDF con las partidas por guion de renglon unidas (`opera-\\ntion` -> `operation`), como las deja Xpdf."""
    return _palabras_de_pagina(re.sub('(\\w)-[ \\t]*\\n[ \\t]*(\\w)', '\\1\\2', texto))

def paginas_con_rotulos_separados(paginas: list[str], paginas_pymupdf: list[str], excluir=frozenset()) -> list[int]:
    """Los indices de las paginas de Xpdf que se leen con PyMuPDF porque separan los rotulos de fila de su texto (ver arriba). Con otro numero de paginas no se compara nada."""
    if len(paginas) != len(paginas_pymupdf):
        return []
    return [i for i, (x, w) in enumerate(zip(paginas, paginas_pymupdf)) if i and i not in excluir and _tiene_rotulos_sueltos(x) and (_palabras_de_pagina(x) == _palabras_sin_guion_de_renglon(w)) and (_rotulos_de_fila(x) != _rotulos_de_fila(w))]

def _pagina_de_pymupdf(texto: str) -> str:
    """El texto de una pagina de PyMuPDF como el de una de Xpdf: normalizado y con las palabras partidas por guion de renglon unidas."""
    return re.sub('(\\w)-[ \\t]*\\n[ \\t]*(\\w)', '\\1\\2', normalizar(texto))
DOCUMENTOS_EN_ORDEN_INTERNO = frozenset({'01_Conocimiento/Fuentes_primarias/02_Legislacion_UE/DOUE_Directiva_2014-31-UE_IPFNA_texto_original_2014_VIGENTE_sin_modificar_es.pdf'})
DOCUMENTOS_EN_ORDEN_INTERNO_CON_TESTIGO = {'01_Conocimiento/Fuentes_primarias/05_Metrologia_e_incertidumbre/NORMA_PAGO_61.pdf': frozenset({40, 41, 42})}

def _palabras_de_pagina(texto: str):
    """El multiconjunto de palabras (`\\w+`) de una pagina, sin ligaduras ni guiones de particion: lo que comparan `-raw` y PyMuPDF."""
    import collections
    t = unicodedata.normalize('NFKC', texto).replace('\xad', '')
    return collections.Counter(re.findall('\\w+', t))

def _separar_uniones(texto: str, de_raw, del_testigo) -> tuple[str, int]:
    """Separa en `texto` las palabras que `-raw` pego y el testigo tiene como dos (`characteristicsover` frente a `characteristics`
    `over`). Solo toca una palabra que el testigo no tiene y que es exactamente la union de dos que el testigo tiene de mas."""
    solo_raw, solo_testigo = (de_raw - del_testigo, dict(del_testigo - de_raw))
    hechas = 0
    for union, veces in list(solo_raw.items()):
        for _ in range(veces):
            for x in list(solo_testigo):
                if solo_testigo[x] <= 0 or len(x) >= len(union) or (not union.startswith(x)):
                    continue
                y = union[len(x):]
                if solo_testigo.get(y, 0) < (2 if y == x else 1):
                    continue
                nuevo, n = re.subn('(?<!\\w)' + re.escape(union) + '(?!\\w)', x + ' ' + y, texto, count=1)
                if n:
                    texto, hechas = (nuevo, hechas + 1)
                    solo_testigo[x] -= 1
                    solo_testigo[y] -= 1
                    break
    return (texto, hechas)

def _paginas_de_xpdf(ruta, ruta_rel: str, timeout, *, raw: bool) -> tuple[list[str], str]:
    """(paginas, texto crudo) de Xpdf, con o sin `-raw`: las mismas normalizaciones que el camino de siempre."""
    proc = subprocess.run(config.ARGS_PDFTOTEXT + (['-raw'] if raw else []) + [str(ruta), '-'], capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise ExtraccionError(f"pdftotext rc={proc.returncode} en {ruta_rel}: {proc.stderr.decode('utf-8', 'replace')[:200]}")
    crudo, _ = decodificar(proc.stdout, ruta_rel)
    crudo = normalizar(crudo)
    paginas = crudo.split(SALTO_PAGINA)
    if paginas and (not paginas[-1].strip()):
        paginas.pop()
    paginas, _nota = guiones_con_testigo(ruta, ruta_rel, paginas, crudo)
    return (paginas, crudo)

def _orden_paginas_r3b(ruta, ruta_rel, paginas, timeout):
    """F1/F4: orden interno solo en páginas y huellas revisadas de R3.

    Se aplica al final de las reparaciones automáticas: ninguna heurística
    posterior debe devolver la mezcla de columnas. No se cambia el resto
    del documento y se conserva el número de páginas o se detiene la ingesta.
    """
    from . import estructura_r3b
    if estructura_r3b.alcance_r3.altas().get(ruta_rel) not in estructura_r3b.PAGINAS_RAW:
        return (paginas, '')
    if not estructura_r3b.alcance_r3.activa(ruta_rel):
        return (paginas, '')
    ident = estructura_r3b.identidad(ruta_rel, sha256_fichero(ruta))
    elegidas = estructura_r3b.PAGINAS_RAW.get(ident)
    if not elegidas:
        return (paginas, '')
    raw, _ = _paginas_de_xpdf(ruta, ruta_rel, timeout, raw=True)
    if len(raw) != len(paginas) or max(elegidas) > len(raw):
        raise IngestaNoReproducible('R3-B: páginas de orden interno desalineadas: ' + ruta_rel)
    nuevas = list(paginas)
    for n in elegidas:
        if not raw[n - 1].strip():
            raise IngestaNoReproducible('R3-B: página de orden interno vacía: ' + str(n))
        pagina = raw[n - 1]
        if ident == 'BOE-A-2006-22961':
            pagina = re.sub('(?m)^(?:46678 Sábado 30 diciembre 2006 BOE núm\\. 312|BOE núm\\. 312 Sábado 30 diciembre 2006 46679)\\s*\\n', '', pagina)
        nuevas[n - 1] = pagina
    return (nuevas, '; R3-B orden interno -raw en páginas ' + ','.join(map(str, elegidas)))

def _orden_interno_con_testigo(ruta, ruta_rel: str, paginas_raw: list[str], timeout) -> tuple[list[str], str, bool]:
    """(paginas, nota para `motor_extraccion`, si se usa `-raw`). Ver `DOCUMENTOS_EN_ORDEN_INTERNO_CON_TESTIGO`."""
    sin_cambio = DOCUMENTOS_EN_ORDEN_INTERNO_CON_TESTIGO[ruta_rel]
    planas, _ = _paginas_de_xpdf(ruta, ruta_rel, timeout, raw=False)
    testigo = _paginas_pymupdf(ruta)
    if testigo is None or not len(testigo) == len(planas) == len(paginas_raw):
        motivo = 'PyMuPDF no disponible' if testigo is None else f'{len(paginas_raw)} paginas con -raw, {len(planas)} sin el y {len(testigo)} con PyMuPDF'
        print(f'aviso: {ruta_rel} se lee sin el orden interno ({motivo})', file=sys.stderr)
        return (planas, f'; orden interno sin testigo: {motivo}', False)
    salida: list[str] = []
    reparadas: list[int] = []
    como_xpdf: list[int] = []
    uniones = 0
    for i, (raw, plana, pg) in enumerate(zip(paginas_raw, planas, testigo)):
        if i + 1 in sin_cambio:
            salida.append(plana)
            como_xpdf.append(i + 1)
            continue
        quiero = _palabras_de_pagina(pg)
        tengo = _palabras_de_pagina(raw)
        texto, n = (raw, 0)
        if tengo != quiero:
            texto, n = _separar_uniones(raw, tengo, quiero)
        if _palabras_de_pagina(texto) == quiero:
            salida.append(texto)
            if n:
                reparadas.append(i + 1)
                uniones += n
        else:
            salida.append(plana)
            como_xpdf.append(i + 1)
    nota = f'; orden interno con testigo de PyMuPDF: {len(salida) - len(como_xpdf)} pgs de -raw'
    if reparadas:
        nota += f" ({uniones} palabras separadas en pgs {','.join(map(str, reparadas))})"
    if como_xpdf:
        nota += f", {len(como_xpdf)} como Xpdf: {','.join(map(str, como_xpdf))}"
    return (salida, nota, len(como_xpdf) < len(salida))
RE_DIARIO_OFICIAL = re.compile('Diario Oficial de la Uni[óo]n Europea|Official Journal of the European Union')

def _sin_idioma_de_cabecera(pagina: str) -> str:
    """En el orden interno la cabecera del Diario Oficial va al final de la pagina: el codigo de
    lengua ("ES") en un renglon y en el siguiente "L 96/112 Diario Oficial... 29.3.2014" (que quita
    `parsers.RUIDO`). Se deja en blanco el renglon del codigo; los demas no se tocan."""
    lineas = pagina.split('\n')
    vivas = [i for i, ln in enumerate(lineas) if ln.strip()]
    for a, b in zip(vivas, vivas[1:]):
        if re.fullmatch('\\s*[A-Z]{2}\\s*', lineas[a]) and RE_DIARIO_OFICIAL.search(lineas[b]):
            lineas[a] = ''
    return '\n'.join(lineas)
GUIONES_DE_RENGLON = '-' + chr(8208) + chr(8209)
RE_RENGLON_CON_GUION = re.compile('([^\\W_]+)[' + GUIONES_DE_RENGLON + '][ \\t]*\\n[ \\t]*([^\\W_]+)')
RE_PALABRA_CON_GUIONES = re.compile('[^\\W_]+(?:-[^\\W_]+)*')

def _es_del_boe(ruta_rel: str) -> bool:
    """Si el documento es de la familia `boe` y su capa de texto es nativa. Un BOE escaneado (la Orden de 1996, cuyo OCR si parte
    las palabras por silabas: "reglamen-
tariamente") se queda como estaba: sus preceptos salen de su texto limpio."""
    from . import catalogo
    return catalogo.familia(ruta_rel) == 'boe' and catalogo.metodo_extraccion(ruta_rel) == 'capa_texto' and (ruta_rel not in catalogo.TEXTO_LIMPIO_POR_DOCUMENTO)

def _es_guia_de_la_ue(ruta_rel: str) -> bool:
    """Si el documento es de la familia `guia` y esta en la carpeta de la legislacion de la UE (R15): las Directrices del Diario Oficial (GDP, C/2025/214), los anexos de EudraLex
    con el membrete de la AEMPS, PIC/S… Ellos llevan folios, cabeceras y pies del Diario o de la Comision; el resto de las guias (WELMEC, EA, ILAC…), no, y no entran."""
    from . import catalogo
    return catalogo.familia(ruta_rel) == 'guia' and ruta_rel.startswith(catalogo.FP + '02_Legislacion_UE/')

def _testigos_de_la_ue(ruta, ruta_rel: str, n_paginas: int) -> tuple[bool, list | None, list | None, str]:
    """(marca `texto_ajeno_ue`, notas del Diario de cada pagina, maquetacion de cada pagina, nota para `motor_extraccion`). La familia `eurlex` lleva los folios y las notas
    (R11); las guias de la carpeta de la UE, ademas, la maquetacion que PyMuPDF confirma (R15); las guias revisadas a mano que no son del Diario (R15b), SOLO la maquetacion
    (sin marca, sin notas). Cualquier otro documento: (False, None, None, "")."""
    from . import maquetacion_pymupdf
    de_la_ue, guia_de_la_ue = (_es_de_la_ue(ruta_rel), _es_guia_de_la_ue(ruta_rel))
    if _es_guia_revisada(ruta_rel):
        maquetacion = maquetacion_pymupdf.piezas_de_maquetacion(ruta, n_paginas)
        if maquetacion is None:
            print(f'aviso: {ruta_rel} es una guia con la maquetacion revisada y PyMuPDF no esta o cuenta otras paginas que Xpdf: no se quita la maquetacion de la pagina', file=sys.stderr)
            return (False, None, None, '; maquetacion sin testigo: PyMuPDF no disponible o con otro numero de paginas')
        return (False, None, maquetacion, '')
    if not (de_la_ue or guia_de_la_ue):
        return (False, None, None, '')
    notas, nota = texto_ajeno_ue.notas_con_testigo(ruta, ruta_rel, n_paginas)
    maquetacion = None
    if guia_de_la_ue:
        maquetacion = maquetacion_pymupdf.piezas_de_maquetacion(ruta, n_paginas)
        if maquetacion is None:
            print(f'aviso: {ruta_rel} es una guia de la UE y PyMuPDF no esta o cuenta otras paginas que Xpdf: no se quita la maquetacion de la pagina', file=sys.stderr)
            nota += '; maquetacion sin testigo: PyMuPDF no disponible o con otro numero de paginas'
    return (True, notas, maquetacion, nota)

def _es_guia_revisada(ruta_rel: str) -> bool:
    """Si el documento es una guia que NO es de la carpeta de la UE y cuyas formas de maquetacion se han revisado a mano (R15b): `catalogo.GUIAS_CON_MAQUETACION_REVISADA`."""
    from . import catalogo
    return ruta_rel in catalogo.GUIAS_CON_MAQUETACION_REVISADA and catalogo.familia(ruta_rel) == 'guia' and (not _es_guia_de_la_ue(ruta_rel))

def _es_de_la_ue(ruta_rel: str) -> bool:
    """Si el documento es de la familia `eurlex` (las normas del Diario Oficial de la UE). Las guias —aunque sean del Diario, como las Directrices GDP— no entran aqui."""
    from . import catalogo
    return catalogo.familia(ruta_rel) == 'eurlex'

def _vocabulario_sin_partir(paginas_pymupdf: list[str]) -> tuple[set[str], set[str]]:
    """(palabras, compuestos con guion) que PyMuPDF ve ENTERAS en un renglon, en minuscula. No cuenta la mitad de arriba ni la de
    abajo de una palabra partida."""
    palabras: set[str] = set()
    compuestos: set[str] = set()
    for pag in paginas_pymupdf:
        lineas = pag.split('\n')
        for k, ln in enumerate(lineas):
            toks = [m.group(0).casefold() for m in RE_PALABRA_CON_GUIONES.finditer(ln)]
            if ln.rstrip().endswith('-') and toks:
                toks = toks[:-1]
            if k and lineas[k - 1].rstrip().endswith('-') and toks:
                toks = toks[1:]
            for t in toks:
                (compuestos if '-' in t else palabras).add(t)
    return (palabras, compuestos)

def guion_silabico(a: str, b: str, palabras: set[str], compuestos: set[str]) -> bool:
    """Si el guion entre `a` y `b` (final de un renglon y principio del siguiente) es de particion silabica: la palabra unida
    existe en el documento sin partir y la forma con guion no. Solo entre letras: una cifra o una formula quimica («CF3-\\nCH3»)
    no se parte por silabas."""
    return a.isalpha() and b.isalpha() and ((a + b).casefold() in palabras) and (f'{a}-{b}'.casefold() not in compuestos)

def guiones_del_boe(ruta, ruta_rel: str, paginas: list[str]) -> tuple[list[str], str]:
    """(paginas con los guiones de verdad del BOE repuestos, nota para `motor_extraccion`; vacia si todo fue normal)."""
    pgs = _paginas_pymupdf(ruta)
    if pgs is not None and len(pgs) == len(paginas):
        pgs = [normalizar(x) for x in pgs]
        palabras, compuestos = _vocabulario_sin_partir(pgs)
        salida = []
        for x, m in zip(paginas, pgs):
            desde = 0
            for r in RE_RENGLON_CON_GUION.finditer(m):
                a, b = (r.group(1), r.group(2))
                if guion_silabico(a, b, palabras, compuestos):
                    continue
                unida = re.compile('(?<![^\\W_])' + re.escape(a + b) + '(?![^\\W_])')
                h = unida.search(x, desde)
                if h:
                    x = x[:h.start()] + a + '-' + b + x[h.end():]
                    desde = h.start() + len(a) + 1 + len(b)

            def unir(r, palabras=palabras, compuestos=compuestos):
                if guion_silabico(r.group(1), r.group(2), palabras, compuestos):
                    return r.group(0)
                return r.group(1) + '-' + r.group(2)
            x = RE_RENGLON_CON_GUION.sub(unir, x)
            salida.append(x)
        return (salida, '')
    motivo = 'PyMuPDF no disponible' if pgs is None else f'{len(paginas)} paginas con Xpdf y {len(pgs)} con PyMuPDF'
    print(f'aviso: {ruta_rel} es del BOE y no se pueden comprobar los guiones contra el PDF ({motivo}): no se reponen guiones', file=sys.stderr)
    return (paginas, f'; guiones sin testigo: {motivo}')
RE_DESIGNACION_LARGA = re.compile('\\b[A-ZÁÉÍÓÚ0-9]{1,8}(?:-[A-ZÁÉÍÓÚ0-9]{1,10}){2,}\\b')

def _pares_de_guiones(texto: str) -> dict[str, str]:
    """{forma unida: forma con guion} de las designaciones del texto cuya forma con guion es al menos tan frecuente como la unida (los candidatos
    de `restaurar_guiones`). Con un guion (`RE_DESIGNACION`) la forma unida no lleva ninguno; con dos o mas (`RE_DESIGNACION_LARGA`), una por cada guion
    que Xpdf pudo comerse (las demas se conservan)."""
    pares = {}
    for m in RE_DESIGNACION.finditer(texto):
        con_guion = m.group(0)
        sin_guion = m.group(1) + m.group(2)
        if sin_guion != con_guion:
            pares[sin_guion] = con_guion
    largas: dict[str, set[str]] = {}
    for m in RE_DESIGNACION_LARGA.finditer(texto):
        con_guion = m.group(0)
        partes = con_guion.split('-')
        for j in range(1, len(partes)):
            sin_guion = '-'.join(partes[:j - 1] + [partes[j - 1] + partes[j]] + partes[j + 1:])
            largas.setdefault(sin_guion, set()).add(con_guion)
    for sin_guion, cons in largas.items():
        if len(cons) == 1 and sin_guion not in pares:
            pares[sin_guion] = next(iter(cons))
    return {sin: con for sin, con in pares.items() if texto.count(con) >= texto.count(sin)}

def _nucleo(trozo: str) -> str:
    return re.sub('[\\W_]+', '', trozo).casefold()

def _vecinos(texto: str, inicio: int, fin: int) -> tuple[str, str]:
    """(nucleo del token anterior, nucleo del siguiente) al token que contiene texto[inicio:fin]."""
    i, j = (inicio, fin)
    while i > 0 and (not texto[i - 1].isspace()):
        i -= 1
    while j < len(texto) and (not texto[j].isspace()):
        j += 1
    antes = texto[max(0, i - 200):i].split()[-1:]
    despues = texto[j:j + 200].split()[:1]
    return (_nucleo(antes[0]) if antes else '', _nucleo(despues[0]) if despues else '')

def _mu_con_guiones_unidos(m: str) -> str:
    """Una pagina de PyMuPDF con el guion del final de renglon unido a lo que sigue («MI-» y debajo «006» -> «MI-006»)."""
    return RE_RENGLON_CON_GUION.sub(lambda r: r.group(1) + '-' + r.group(2), m)

def restaurar_guiones_con_testigo(paginas: list[str], paginas_mu: list[str], pares: dict[str, str]) -> tuple[list[str], int]:
    """(paginas con los guiones perdidos repuestos donde el PDF los tiene, cuantos). `paginas` y `paginas_mu` tienen el mismo numero."""
    mu_norm = [normalizar(m) for m in paginas_mu]
    mus = [_mu_con_guiones_unidos(m) for m in mu_norm]
    palabras, compuestos = _vocabulario_sin_partir(mu_norm)
    salida: list[str] = []
    total = 0
    for x, m in zip(paginas, mus):
        for sin, con in pares.items():
            if all((p.isalpha() for p in con.split('-'))) and sin.casefold() in palabras and (con.casefold() not in compuestos):
                continue
            rx_con = re.compile('\\b' + re.escape(con) + '\\b')
            perdidos = len(rx_con.findall(m)) - len(rx_con.findall(x))
            if perdidos <= 0:
                continue
            partes = con.split('-')
            rotos = [re.compile('\\b' + re.escape('-'.join(partes[:j + 1])) + '-[ \\t]*\\n[ \\t]*' + re.escape('-'.join(partes[j + 1:])) + '\\b') for j in range(len(partes) - 1)]
            ocurrencias = sorted(list(re.finditer('\\b' + re.escape(sin) + '\\b', x)) + [o for rx in rotos for o in rx.finditer(x)], key=lambda o: o.start())
            if not ocurrencias:
                continue
            if len(ocurrencias) <= perdidos:
                elegidas = ocurrencias
            else:
                en_pdf = {_vecinos(m, r.start(), r.end()) for r in rx_con.finditer(m)}
                puntos = []
                for o in ocurrencias:
                    ant, sig = _vecinos(x, o.start(), o.end())
                    puntos.append(max((int(ant != '' and ant == a) + int(sig != '' and sig == b) for a, b in en_pdf)))
                orden = sorted(range(len(ocurrencias)), key=lambda k: (-puntos[k], k))
                con_punto = [k for k in orden if puntos[k] >= 1]
                tope = con_punto[:perdidos]
                if len(con_punto) > perdidos and puntos[con_punto[perdidos - 1]] == puntos[con_punto[perdidos]]:
                    tope = [k for k in tope if puntos[k] > puntos[con_punto[perdidos]]]
                elegidas = [ocurrencias[k] for k in sorted(tope)]
            for o in reversed(elegidas):
                x = x[:o.start()] + con + x[o.end():]
                total += 1
        salida.append(x)
    return (salida, total)

def _pares_con_los_del_testigo(pares: dict[str, str], paginas_mu: list[str] | None) -> dict[str, str]:
    """`pares` mas los que salen del texto de PyMuPDF (con el guion de final de renglon unido): en un PDF con capa OCR hay designaciones («SP800-90C», «CWE-790») que solo
    aparecen partidas al final de renglon, y como Xpdf no las tiene enteras en ningun sitio la forma con guion no existe en su crudo y no se forma el par. Los pares
    del crudo mandan. Solo para `DOCUMENTOS_CON_CAPA_OCR`: aplicado a toda la biblioteca cambia ademas cinco documentos, y en uno de ellos (la pagina 135 del Manual ATP) a peor."""
    if paginas_mu is None:
        return pares
    texto_mu = '\n'.join((_mu_con_guiones_unidos(normalizar(p)) for p in paginas_mu))
    return {**_pares_de_guiones(texto_mu), **pares}

def guiones_con_testigo(ruta, ruta_rel: str, paginas: list[str], texto_pares: str) -> tuple[list[str], str]:
    """(paginas, nota para `motor_extraccion`) de un documento que NO es del BOE: la heuristica de `restaurar_guiones` con el testigo del PDF.
    `texto_pares` es el texto del documento del que salen los candidatos (el crudo de Xpdf)."""
    pares = _pares_de_guiones(texto_pares)
    pgs = None
    if ruta_rel in DOCUMENTOS_CON_CAPA_OCR:
        pgs = _paginas_pymupdf(ruta)
        pares = _pares_con_los_del_testigo(pares, pgs)
    if not pares:
        return (paginas, '')
    if pgs is None:
        pgs = _paginas_pymupdf(ruta)
    if pgs is not None and len(pgs) == len(paginas):
        return (restaurar_guiones_con_testigo(paginas, pgs, pares)[0], '')
    motivo = 'PyMuPDF no disponible' if pgs is None else f'{len(paginas)} paginas con Xpdf y {len(pgs)} con PyMuPDF'
    print(f'aviso: {ruta_rel} tiene designaciones con guion que Xpdf pudo partir y no se pueden comprobar contra el PDF ({motivo}): no se reponen guiones', file=sys.stderr)
    return (paginas, f'; guiones sin testigo: {motivo}')

def extraer(ruta_rel: str, timeout: int | None=None) -> TextoPdf:
    """Extrae un PDF de la biblioteca a paginas, en UTF-8 explicito."""
    timeout = timeout or float(os.environ.get('ICT155_TIMEOUT', '300'))
    ruta = config.ruta_biblioteca(ruta_rel)
    if not ruta.exists():
        raise ExtraccionError(f'no existe: {ruta_rel}')
    if config.MOTOR == 'pymupdf':
        pgs = _paginas_pymupdf(ruta)
        if pgs is not None:
            pgs = [normalizar(x) for x in pgs]
            es_de_la_ue, notas_del_diario, maquetacion_del_pdf, nota_ajeno = _testigos_de_la_ue(ruta, ruta_rel, len(pgs))
            pgs, nota_exp, registros_exp = superindices.exponentes_con_testigo(ruta, ruta_rel, pgs)
            st = ruta.stat()
            t = TextoPdf(motor=(config.MOTOR_PYMUPDF + nota_ajeno + nota_exp)[:500], registros_exponentes=registros_exp, texto_ajeno_ue=es_de_la_ue, notas_del_diario=notas_del_diario, maquetacion_del_pdf=maquetacion_del_pdf, caracteres_perdidos=0, ruta_relativa=config.relativa(ruta), paginas=pgs, sha256=sha256_fichero(ruta), bytes=st.st_size, mtime_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds'))
            t.hash_texto = hashlib.sha256(t.texto.encode('utf-8')).hexdigest()
            return t
        print(f'aviso: PyMuPDF no disponible o fallido en {ruta_rel}; se extrae con Xpdf y asi se graba', file=sys.stderr)
    orden_interno = ruta_rel in DOCUMENTOS_EN_ORDEN_INTERNO
    con_testigo = ruta_rel in DOCUMENTOS_EN_ORDEN_INTERNO_CON_TESTIGO
    try:
        proc = subprocess.run(config.ARGS_PDFTOTEXT + (['-raw'] if orden_interno or con_testigo else []) + [str(ruta), '-'], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise IngestaNoReproducible(f"pdftotext se paso de {timeout} s en {ruta_rel}. No se degrada a 'documento registrado': eso daria una base distinta segun la carga de la maquina. Sube ICT155_TIMEOUT o mira por que ese PDF tarda") from e
    if proc.returncode != 0:
        raise ExtraccionError(f"pdftotext rc={proc.returncode} en {ruta_rel}: {proc.stderr.decode('utf-8', 'replace')[:200]}")
    crudo, perdidos = decodificar(proc.stdout, ruta_rel)
    crudo = normalizar(crudo)
    del_boe = _es_del_boe(ruta_rel)
    paginas = crudo.split(SALTO_PAGINA)
    if paginas and (not paginas[-1].strip()):
        paginas.pop()
    nota_guiones = ''
    if not del_boe:
        paginas, nota_guiones = guiones_con_testigo(ruta, ruta_rel, paginas, crudo)
    motor = config.MOTOR_XPDF
    nota_orden, usa_raw = ('', False)
    if con_testigo:
        paginas, nota_orden, usa_raw = _orden_interno_con_testigo(ruta, ruta_rel, paginas, timeout)
    de_pymupdf, nota_capa, pgs_pymupdf = _capa_duplicada(ruta, ruta_rel, paginas, pymupdf_ya_fallo=config.MOTOR == 'pymupdf')
    for i, texto in de_pymupdf.items():
        paginas[i] = texto
    de_rotulos: list[int] = []
    if pgs_pymupdf is not None and (not (orden_interno or con_testigo)):
        from . import catalogo
        if catalogo.familia(ruta_rel) == 'guia':
            de_rotulos = paginas_con_rotulos_separados(paginas, pgs_pymupdf, excluir=frozenset(de_pymupdf))
            for i in de_rotulos:
                paginas[i] = _pagina_de_pymupdf(pgs_pymupdf[i])
            if de_rotulos:
                nota_capa += f"; rotulos de fila separados de su texto: {len(de_rotulos)} pgs de PyMuPDF: {','.join((str(i + 1) for i in de_rotulos))}"
    protegidas = frozenset(de_pymupdf) | frozenset(de_rotulos)
    if del_boe:
        paginas, nota_guiones = guiones_del_boe(ruta, ruta_rel, paginas)
    nota_capa += nota_guiones
    nota_capa += nota_orden
    if config.LAYOUT_GUIAS in ('paginas', 'todo') and (not usa_raw):
        paginas, motor = _layout_en_guias(ruta, ruta_rel, paginas, timeout, protegidas=protegidas)
    if pgs_pymupdf is not None:
        paginas, nota_revuelto = _texto_revuelto(paginas, pgs_pymupdf, excluir=protegidas)
        nota_capa += nota_revuelto
        paginas, nota_palabras = _palabras_con_testigo(paginas, pgs_pymupdf, ruta_rel in DOCUMENTOS_CON_CAPA_OCR)
        nota_capa += nota_palabras
    if usa_raw:
        motor = config.MOTOR_XPDF + ' -raw'
    if orden_interno:
        paginas = [_sin_idioma_de_cabecera(p) for p in paginas]
        motor = config.MOTOR_XPDF + ' -raw'
    paginas, nota_r3b = _orden_paginas_r3b(ruta, ruta_rel, paginas, timeout)
    nota_capa += nota_r3b
    es_de_la_ue, notas_del_diario, maquetacion_del_pdf, nota_ajeno = _testigos_de_la_ue(ruta, ruta_rel, len(paginas))
    nota_capa += nota_ajeno
    paginas, nota_exp, registros_exp = superindices.exponentes_con_testigo(ruta, ruta_rel, paginas)
    nota_capa += nota_exp
    motor = (motor + nota_capa)[:500]
    st = ruta.stat()
    t = TextoPdf(motor=motor, caracteres_perdidos=perdidos, ruta_relativa=config.relativa(ruta), paginas=paginas, registros_exponentes=registros_exp, texto_ajeno_ue=es_de_la_ue, notas_del_diario=notas_del_diario, maquetacion_del_pdf=maquetacion_del_pdf, sha256=sha256_fichero(ruta), bytes=st.st_size, mtime_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds'))
    t.hash_texto = hashlib.sha256(t.texto.encode('utf-8')).hexdigest()
    return t
MOTOR_TEXTO_BOE = 'texto-boe'

def n_paginas_del_pdf(ruta_pdf_rel: str) -> int:
    """Las paginas del PDF, que el texto limpio de un BOE no trae."""
    return len(extraer(ruta_pdf_rel).paginas)

def extraer_texto_boe(ruta_pdf_rel: str, ruta_txt_rel: str, identificador: str, titulo: str) -> TextoPdf:
    """El texto limpio de un BOE, con la forma que `analizar_boe` espera de un PDF.

    Tanda del 4 de octubre de 2026, T4. La Orden de 2 de septiembre de 1996 es un BOE
    de papel con una capa de texto de OCR antigua que el analizador no puede
    leer. El propio BOE publica su texto (`https://www.boe.es/diario_boe/txt.php?id=...`);
    la biblioteca lo guarda junto al PDF, un parrafo por linea y sin cambiar una
    palabra. Aqui se le da la forma de un texto de boletin: una cabecera que sale
    de los metadatos YA DECLARADOS (`Referencia`, titulo) y la linea `TEXTO
    ORIGINAL`, que es la que rotula el propio BOE, seguida del texto.

    El documento sigue siendo el PDF: su sha256, su tamano y su fecha. Lo que
    cambia es de donde salen los preceptos. El texto no trae paginas, asi que todo
    va en una sola pagina; `documento.paginas` es la del PDF y cada precepto lleva
    las paginas 1 a N (cierto: esta en algun sitio del documento). Ver ingesta.
    """
    pdf = config.ruta_biblioteca(ruta_pdf_rel)
    txt = config.ruta_biblioteca(ruta_txt_rel)
    if not txt.exists():
        raise ExtraccionError(f'el texto limpio declarado para {ruta_pdf_rel} no esta: {ruta_txt_rel}. No se cae al OCR del PDF en silencio: sin el, la obra daria PRECEPTO_INEXISTENTE sobre articulos que estan impresos')
    with config.abrir_biblioteca(txt, 'r') as f:
        crudo = normalizar(f.read())
    lineas = [x.strip() for x in crudo.split('\n') if x.strip()]
    cabecera = [f'Referencia: {identificador}', titulo, 'TEXTO ORIGINAL']
    st = pdf.stat()
    t = TextoPdf(paginas_del_documento=n_paginas_del_pdf(ruta_pdf_rel), motor=MOTOR_TEXTO_BOE, caracteres_perdidos=0, ruta_relativa=config.relativa(pdf), paginas=['\n'.join(cabecera + lineas)], sha256=sha256_fichero(pdf), bytes=st.st_size, mtime_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds'))
    t.hash_texto = hashlib.sha256(t.texto.encode('utf-8')).hexdigest()
    return t
LINEA_COLAPSADA = 300
PROPORCION_COLAPSADA = 0.5

def pagina_colapsada(pagina: str) -> bool:
    lineas = [ln for ln in pagina.split('\n') if ln.strip()]
    total = sum((len(ln) for ln in lineas))
    if not total:
        return False
    largas = sum((len(ln) for ln in lineas if len(ln) > LINEA_COLAPSADA))
    return largas >= PROPORCION_COLAPSADA * total

def _paginas_con_layout(ruta: Path, ruta_rel: str, timeout) -> list[str]:
    proc = subprocess.run(config.ARGS_PDFTOTEXT + ['-layout', str(ruta), '-'], capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise ExtraccionError(f"pdftotext -layout rc={proc.returncode} en {ruta_rel}: {proc.stderr.decode('utf-8', 'replace')[:200]}")
    crudo, _ = decodificar(proc.stdout, ruta_rel)
    crudo = normalizar(crudo)
    paginas = crudo.split(SALTO_PAGINA)
    if paginas and (not paginas[-1].strip()):
        paginas.pop()
    pares = _pares_de_guiones(crudo)
    pgs = None
    if ruta_rel in DOCUMENTOS_CON_CAPA_OCR:
        pgs = _paginas_pymupdf(ruta)
        pares = _pares_con_los_del_testigo(pares, pgs)
    if pares:
        if pgs is None:
            pgs = _paginas_pymupdf(ruta)
        if pgs is not None and len(pgs) == len(paginas):
            paginas = restaurar_guiones_con_testigo(paginas, pgs, pares)[0]
    return paginas

def _rutas_de_guia(ruta_rel: str, paginas: list[str]) -> set[str]:
    """Las rutas que el analizador de guias saca de estas paginas.

    Con `legado=True` (R13, 11-oct-2026): la sonda de `-layout` mide con el analizador de antes de partir los encabezados
    pegados a mitad de renglon (`parsers._pegado`). Asi la decision de que paginas llevan `-layout` no cambia y el texto
    extraido de cada guia es el mismo: partir apartados no debe cambiar ni una palabra del documento."""
    from . import parsers
    t = TextoPdf(ruta_relativa=ruta_rel, paginas=paginas)
    return {p.ruta for p in parsers.analizar_guia(t, legado=True).preceptos}

def _layout_en_guias(ruta: Path, ruta_rel: str, paginas: list[str], timeout, protegidas: frozenset=frozenset()) -> tuple[list[str], str]:
    """Las paginas con -layout donde toca, y el motor que lo dice.

    Solo para la familia `guia`: el BOE y EUR-Lex no se tocan nunca. Si el
    numero de paginas de las dos extracciones no coincide, no se sustituye nada
    y se dice: mezclar paginas desalineadas fabricaria texto. El documento sale
    ENTERO como sin la bandera: la misma lista `paginas` y el mismo motor.

    Ultima tanda de la campana cero errores, punto 5. La medicion del 3 de
    octubre atribuyo a ese descuadre las rutas perdidas de las Directrices GDP
    en ingles, pero el aviso de "13 paginas frente a 14" es de las GDP en
    espanol, que salen intactas. Las GDP en ingles cuadran y pierden
    `capitulo.6` y `capitulo.7` por otra cosa: sus paginas 8 y 9 van a dos
    columnas, y -layout pone en la misma linea la columna izquierda y la
    derecha, con lo que el encabezado deja de serlo. Lo mismo pasa con las
    tablas de WELMEC 8.6. Por eso, desde esta tanda:

    - una pagina solo se sustituye si el analizador de guias sigue sacando del
      documento TODAS las rutas que sacaba sin -layout (se prueba pagina a
      pagina, en orden, y se queda con las que no quitan nada);
    - la primera pagina no se sustituye nunca: de ella salen el titulo y el
      emisor, y en la medicion cuatro obras cambiaron de titulo a peor;
    - en modo `todo`, si el documento entero con -layout pierde alguna ruta, se
      queda entero sin -layout;
    - las `protegidas` (indices de paginas que ya vienen de PyMuPDF por tener la capa
      de texto duplicada, ver `_capa_duplicada`) no se sustituyen nunca.
    """
    from . import catalogo
    if catalogo.familia(ruta_rel) != 'guia':
        return (paginas, config.MOTOR_XPDF)
    con_layout = _paginas_con_layout(ruta, ruta_rel, timeout)
    if len(con_layout) != len(paginas):
        print(f'aviso: -layout da {len(con_layout)} paginas y sin -layout {len(paginas)} en {ruta_rel}; el documento entero se queda sin -layout', file=sys.stderr)
        return (paginas, config.MOTOR_XPDF)
    antes = _rutas_de_guia(ruta_rel, paginas)
    if config.LAYOUT_GUIAS == 'todo':
        if not _rutas_de_guia(ruta_rel, con_layout) >= antes:
            print(f'aviso: con -layout se pierden rutas en {ruta_rel}; el documento entero se queda sin -layout', file=sys.stderr)
            return (paginas, config.MOTOR_XPDF)
        if protegidas:
            con_layout = [paginas[i] if i in protegidas else p for i, p in enumerate(con_layout)]
        return (con_layout, config.MOTOR_XPDF + ' -layout')
    nuevas = list(paginas)
    cambiadas = []
    for i, p in enumerate(paginas):
        if i == 0 or i in protegidas or (not pagina_colapsada(p)):
            continue
        prueba = list(nuevas)
        prueba[i] = con_layout[i]
        if _rutas_de_guia(ruta_rel, prueba) >= antes:
            nuevas, cambiadas = (prueba, cambiadas + [i])
    if not cambiadas:
        return (paginas, config.MOTOR_XPDF)
    lista = ','.join((str(i + 1) for i in cambiadas))
    return (nuevas, f'{config.MOTOR_XPDF}; -layout en {len(cambiadas)} de {len(paginas)} paginas: {lista}'[:500])
RE_DESIGNACION = re.compile('\\b([A-ZÁÉÍÓÚ0-9]{1,8})-([A-ZÁÉÍÓÚ0-9][A-ZÁÉÍÓÚ0-9]{0,9})\\b')

def restaurar_guiones(texto: str) -> tuple[str, int]:
    """Repone el guion que Xpdf pierde al unir una palabra partida en el salto.

    Xpdf une las dos mitades de una palabra partida al final de linea y se come
    el guion. Cuando el guion es silabico da igual, pero cuando forma parte del
    termino no: "Norma UNE-
EN 12830" sale "UNEEN 12830", y ese guion es parte
    del nombre de la norma. La Orden ICT/155/2020 y la Guia CEM C-01 tienen las
    dos el mismo caso.

    Regla: si en el propio documento la designacion aparece tambien con guion,
    la forma sin guion es una union perdida y se repone. Se limita a
    designaciones (mayuscula o digito a los dos lados) para no tocar la prosa.
    """
    pares = {}
    for m in RE_DESIGNACION.finditer(texto):
        con_guion = m.group(0)
        sin_guion = m.group(1) + m.group(2)
        if sin_guion != con_guion:
            pares[sin_guion] = con_guion
    if not pares:
        return (texto, 0)
    n = 0
    for sin_guion, con_guion in pares.items():
        if texto.count(con_guion) >= texto.count(sin_guion):
            nuevo_texto, k = re.subn('\\b' + re.escape(sin_guion) + '\\b', con_guion, texto)
            if k:
                texto, n = (nuevo_texto, n + k)
    return (texto, n)

def contar_rangos(texto: str) -> dict[str, int]:
    return {k: len(p.findall(texto)) for k, p in RANGOS.items()}

def limpiar_lineas(texto: str) -> str:
    """Reune palabras partidas por salto de linea y colapsa espacios.

    Los PDF del BOE y de EUR-Lex parten palabras con guion al final de linea y,
    en la maquetacion a dos columnas, tambien con guion suave. Sin rehacerlas,
    una comparacion literal falla por un guion.
    """
    t = re.sub('(\\w)-\\n(\\w)', '\\1\\2', texto)
    t = re.sub('[ \\t]*\\n[ \\t]*', ' ', t)
    t = re.sub('[ \\t]{2,}', ' ', t)
    return t.strip()
