"""Public CI documentation."""
from __future__ import annotations
import difflib
import re
from dataclasses import dataclass, field, replace
from .extraccion import MOTOR_TEXTO_BOE, ExtraccionError, TextoPdf, limpiar_lineas
ORDINALES = {'unica': 1, 'unico': 1, 'primera': 1, 'primero': 1, 'segunda': 2, 'segundo': 2, 'tercera': 3, 'tercero': 3, 'cuarta': 4, 'cuarto': 4, 'quinta': 5, 'quinto': 5, 'sexta': 6, 'sexto': 6, 'septima': 7, 'septimo': 7, 'octava': 8, 'octavo': 8, 'novena': 9, 'noveno': 9, 'decima': 10, 'decimo': 10, 'undecima': 11, 'duodecima': 12, 'decimotercera': 13, 'decimocuarta': 14, 'decimoquinta': 15, 'decimosexta': 16, 'decimosexto': 16, 'decimoseptima': 17, 'decimoseptimo': 17, 'decimoctava': 18, 'decimoctavo': 18, 'decimonovena': 19, 'decimonoveno': 19, 'vigesima': 20, 'vigesimo': 20, 'trigesima': 30, 'trigesimo': 30, 'cuadragesima': 40, 'cuadragesimo': 40}
_SIN_TILDE = str.maketrans('áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
ORD_COMPUESTO = '(?:vig|trig|cuadrag)[ée]sim[ao]\\s+(?:primer[ao]|segund[ao]|tercer[ao]|cuart[ao]|quint[ao]|sext[ao]|s[ée]ptim[ao]|octav[ao]|noven[ao])'

def sin_tilde(s: str) -> str:
    return s.translate(_SIN_TILDE)

def ordinal_a_numero(palabra: str) -> str:
    p = sin_tilde(palabra.strip().lower())
    partes = p.split()
    if len(partes) >= 2 and re.fullmatch(ORD_LATINO, partes[-1]):
        return ordinal_a_numero(' '.join(partes[:-1])) + ' ' + partes[-1]
    if len(partes) == 2 and ORDINALES.get(partes[0]) in (20, 30, 40) and (1 <= ORDINALES.get(partes[1], 0) <= 9):
        return str(ORDINALES[partes[0]] + ORDINALES[partes[1]])
    return str(ORDINALES.get(p, palabra.strip().lower()))
RE_CABECERA_BOE_PEGADA = re.compile('^\\s*LEGISLACI[ÓO]N CONSOLIDADA\\s+(?=\\S)', re.I)
RUIDO = (re.compile('^\\s*BOLET[ÍI]N OFICIAL DEL ESTADO\\s*$', re.I), re.compile('^\\s*LEGISLACI[ÓO]N CONSOLIDADA\\s*$', re.I), re.compile('^\\s*P[áa]gina\\s+\\d+\\s*$', re.I), re.compile('^\\s*Este documento es un instrumento de documentaci[óo]n.*$', re.I), re.compile('^\\s*Este texto es exclusivamente un instrumento de documentaci[óo]n.*$', re.I), re.compile('^\\s*Diario Oficial de la Uni[óo]n Europea\\s*$', re.I), re.compile('^\\s*Official Journal of the European Union\\s*$', re.I), re.compile('^\\s*(?:[LC]\\s+\\d{1,4}/\\d{1,4}|\\d{1,2}\\.\\d{1,2}\\.\\d{4})\\s+(?:Diario Oficial de la Uni[óo]n Europea|Official Journal of the European Union)\\s+(?:[LC]\\s+\\d{1,4}/\\d{1,4}|\\d{1,2}\\.\\d{1,2}\\.\\d{4})\\s*$', re.I), re.compile('^\\s*\\d{4,5}[A-Z]\\d{4}\\s+[—-]\\s+[A-Z]{2}\\s+[—-].*$'), re.compile('^\\s*ES\\s+Serie\\s+[LC]\\s*$'), re.compile('^\\s*[-–]\\s*\\d{1,4}\\s*[-–]\\s*$'))
RUIDO_BOE = (re.compile('^\\s*Este texto consolidado no tiene valor jur[íi]dico\\.?\\s*$', re.I), re.compile('^\\s*Este documento es de car[áa]cter informativo y no tiene valor jur[íi]dico\\.?\\s*$', re.I), re.compile('^\\s*https?://www\\.boe\\.es\\s+D\\.\\s*L\\.:.*ISSN.*$', re.I), re.compile('^\\s*Sec\\.\\s+[IVX]+\\.\\s+P[áa]g\\.\\s+\\d+\\s*$', re.I))
RE_PAGINA_PEGADA = re.compile('\\s+P[áa]gina\\s+(\\d+)\\s*$')
RE_PIE_PEGADO_AL_FINAL = re.compile('\\s+(?:Este texto consolidado no tiene valor jur[íi]dico|Este documento es de car[áa]cter informativo y no tiene valor jur[íi]dico)\\.?\\s*$', re.I)
RE_NUMERO_SUELTO = re.compile('^\\s*\\d+\\s*$')
_PUNTOS_Y_PAGINA = '(?:\\.\\s*){4,}\\d{1,4}(?=\\s|$)'
INDICE = re.compile('\\.\\s*\\.\\s*\\.\\s*\\..*?\\d+\\s*$|' + _PUNTOS_Y_PAGINA + '.*?' + _PUNTOS_Y_PAGINA)
_CODIGO_MARCA = '(B|[MC]\\d+)(?![^\\W_])'
MARCA_BLOQUE = re.compile('^\\s*[\\u25bc\\u25ba]\\s*' + _CODIGO_MARCA + '\\s*$')
MARCA_INLINE = re.compile('\\u25ba\\s*' + _CODIGO_MARCA + '|\\u25c4')
MARCA_INICIO = re.compile('^\\s*[\\u25bc\\u25ba]\\s*' + _CODIGO_MARCA + '\\s+(?=\\S)')
MARCA_RESTO = re.compile('[▼]\\s*' + _CODIGO_MARCA)
RX_TABLA_CORRESP = re.compile('(?i)\\btabla\\s+de\\s+correspondencias\\b|\\bcorrelation\\s+table\\b')
RE_ANEXO_TABLA_CORRESP = re.compile('(?i)^\\s*(?:ANEXO|ANNEX)\\s+((?:tabla\\s+de\\s+correspondencias|correlation\\s+table)\\b.*?)\\s*$')
COMILLAS_APERTURA = '«“”‘’"\''
ORD_LATINO = '(?:bis|ter|qu[áa]ter|quinquies|sexies|septies|octies|nonies|decies|undecies|duodecies|terdecies|quaterdecies|quindecies|sexdecies|septdecies|octodecies|novodecies|vicies|unvicies|duovicies|tervicies|quatervicies)\\b'
ORD_DISPOSICION = f'(?:{ORD_COMPUESTO}|[a-zñáéíóú]+)(?:\\s+{ORD_LATINO})?'
ORD_CASTELLANO = '(?:primero|segundo|tercero|cuarto|quinto|sexto|s[ée]ptimo|octavo|noveno|nono|d[ée]cimo|und[ée]cimo|duod[ée]cimo|decimotercero|decimocuarto|decimoquinto|decimosexto|decimos[ée]ptimo|decimoctavo|decimonoveno|vig[ée]simo)\\b'
ORD_ARTICULO = f'(?:{ORD_LATINO}|{ORD_CASTELLANO})'
RX_ORDINAL_PEGADO = re.compile(f'^(\\d+)(?=(?i:{ORD_ARTICULO}))')

def numeral_articulo(s: str) -> str:
    """Public CI documentation."""
    s = RX_ORDINAL_PEGADO.sub('\\1 ', s.strip())
    partes = re.sub('\\s+', ' ', s).split(' ')
    if len(partes) == 1:
        return partes[0]
    return partes[0] + ' ' + ' '.join((sin_tilde(p.lower()) for p in partes[1:]))
ORD_DIV = f'\\s+(?i:{ORD_LATINO})'
NUM_DIV = f'(?:[IVXLC]+|\\d+|[A-Z])(?:{ORD_DIV})?'

def numeral_division(s: str) -> str:
    """Public CI documentation."""
    partes = s.split()
    if not partes:
        return ''
    if len(partes) == 1:
        return partes[0]
    return partes[0] + ' ' + ' '.join((p.lower() for p in partes[1:]))
RUBRICA = '(?:\\s+((?-i:[A-ZÁÉÍÓÚÑ]).*))?'

@dataclass
class Precepto:
    ruta: str
    tipo: str
    numero: str | None
    etiqueta: str
    titulo: str | None
    lineas: list[str] = field(default_factory=list)
    pagina_inicio: int = 1
    pagina_fin: int = 1
    padre: str | None = None
    marca: str | None = None
    metodo: str = 'capa_texto'
    de_indice: bool = False

    @property
    def texto(self) -> str:
        return limpiar_lineas('\n'.join(self.lineas))

    @property
    def sin_texto_aun(self) -> bool:
        """Public CI documentation."""
        return not any((x.strip() for x in self.lineas))

@dataclass
class Analisis:
    preceptos: list[Precepto] = field(default_factory=list)
    identificador: str | None = None
    titulo: str | None = None
    fecha_consolidacion: str | None = None
    es_consolidada: bool = False
    cabecera: str | None = None
    idioma: str = 'es'
LINEAS_DE_BORDE = 3
EN_EL_BORDE = 0.8
RE_SOLO_FECHA = re.compile('^\\s*\\d{1,2}\\.\\d{1,2}\\.\\d{4}\\s*$')
RE_PIE_DE_VERIFICACION = re.compile('\\bcve:|https?://|www\\.', re.I)

def lineas_repetidas(pdf: TextoPdf, umbral: float=0.5) -> set[str]:
    """Public CI documentation."""
    if pdf.n_paginas < 4:
        return set()
    from collections import Counter
    c: Counter = Counter()
    en_borde: Counter = Counter()
    for pag in pdf.paginas:
        lineas = [x.strip() for x in pag.split('\n') if x.strip()]
        borde = set(lineas[:LINEAS_DE_BORDE] + lineas[-LINEAS_DE_BORDE:])
        for ln in {x for x in lineas if len(x) > 3}:
            c[ln] += 1
            if ln in borde:
                en_borde[ln] += 1
    minimo = max(3, int(pdf.n_paginas * umbral))
    identidad = _codigos_del_fichero(pdf.ruta_relativa)
    return {ln for ln, n in c.items() if n >= minimo and len(ln) <= 120 and (en_borde[ln] >= EN_EL_BORDE * n or RE_SOLO_FECHA.match(ln) or RE_PIE_DE_VERIFICACION.search(ln) or _lleva_codigo(ln, identidad))}
RE_NUMERO_EN_EL_BORDE = re.compile('^\\s*(\\d{1,4})\\s+(.*?)\\s*$|^\\s*(.*?)\\s+(\\d{1,4})\\s*$')
LETRAS_MINIMAS_DE_MEZCLA = 12

def _sin_numero_de_pagina(ln: str) -> tuple[str, int | None]:
    """Public CI documentation."""
    m = RE_NUMERO_EN_EL_BORDE.match(ln)
    if not m:
        return (' '.join(ln.split()), None)
    if m.group(1) is not None:
        return (' '.join(m.group(2).split()), int(m.group(1)))
    return (' '.join(m.group(3).split()), int(m.group(4)))

def _letras(ln: str) -> tuple:
    from collections import Counter
    return tuple(sorted(Counter((ch for ch in ln.casefold() if ch.isalpha())).items()))

def _cifras(ln: str):
    from collections import Counter
    return Counter((ch for ch in ln if ch.isdigit()))

def lineas_de_maquetacion(pdf: TextoPdf) -> set[str]:
    """Public CI documentation."""
    repetidas = lineas_repetidas(pdf)
    return repetidas | _variantes_de_maquetacion(pdf, repetidas)

def _variantes_de_maquetacion(pdf: TextoPdf, repetidas: set[str]) -> set[str]:
    """Public CI documentation."""
    from collections import Counter, defaultdict
    if pdf.n_paginas < 4 or not repetidas:
        return set()
    bases = {' '.join(x.split()) for x in repetidas}
    letras_de: dict[tuple, list] = defaultdict(list)
    for x in bases:
        if sum((ch.isalpha() for ch in x)) >= LETRAS_MINIMAS_DE_MEZCLA:
            una, cif = (dict(_letras(x)), _cifras(x))
            letras_de[tuple(sorted(una.items()))].append(cif)
            letras_de[tuple(sorted(((k, 2 * v) for k, v in una.items())))].append(cif + cif)
    candidatos: list[tuple[int, str]] = []
    for i, pag in enumerate(pdf.paginas):
        if i == 0:
            continue
        lineas = [x.strip() for x in pag.split('\n') if x.strip()]
        for ln in set(lineas[:LINEAS_DE_BORDE] + lineas[-LINEAS_DE_BORDE:]):
            if ln not in repetidas:
                candidatos.append((i + 1, ln))
    desfases: dict[str, Counter] = defaultdict(Counter)
    for pag, ln in candidatos:
        clave, n = _sin_numero_de_pagina(ln)
        if n is not None and clave in bases:
            desfases[clave][n - pag] += 1
    variantes = set()
    for pag, ln in candidatos:
        if ' '.join(ln.split()) in bases:
            variantes.add(ln)
            continue
        clave, n = _sin_numero_de_pagina(ln)
        if clave in bases:
            if n is None:
                variantes.add(ln)
            else:
                total = sum(desfases[clave].values())
                d, veces = desfases[clave].most_common(1)[0]
                if n - pag == d and veces >= 3 and (2 * veces >= total):
                    variantes.add(ln)
            continue
        if sum((ch.isalpha() for ch in ln)) < LETRAS_MINIMAS_DE_MEZCLA:
            continue
        cif = _cifras(ln)
        for necesarias in letras_de.get(_letras(ln), ()):
            if not necesarias - cif and sum((cif - necesarias).values()) <= 4:
                variantes.add(ln)
                break
    return variantes

def _codigos_del_fichero(ruta_relativa: str) -> set[str]:
    """Public CI documentation."""
    nombre = re.split('[\\\\/]', ruta_relativa or '')[-1].rsplit('.', 1)[0]
    return {t.casefold() for t in nombre.split('_') if len(t) >= 6 and re.search('[^\\W\\d_]', t)}

def _lleva_codigo(linea: str, codigos: set[str]) -> bool:
    return any((t.casefold() in codigos for t in re.findall('[\\w][\\w\\-.]*', linea)))
TIRADA_MAXIMA = 3
PAGINAS_MINIMAS_EN_TIRADA = 8
LARGO_MINIMO_DE_TIRADA = 8
LARGO_MAXIMO_DE_TIRADA = 360
LARGO_MINIMO_DE_CABECERA = 16
LARGO_MAXIMO_DE_TITULO_CORRIENTE = 80
TITULOS_CORRIENTES = 3
RE_CELDAS = re.compile('\\s{2,}')
RE_N_DE_M = re.compile('^\\d{1,3}/\\d{1,3}$')

def _es_n_de_m(texto: str) -> bool:
    """Public CI documentation."""
    if not RE_N_DE_M.match(texto):
        return False
    n, m = (int(x) for x in texto.split('/'))
    return 1 <= n <= m

def _es_de_guia(pdf: TextoPdf) -> bool:
    from . import catalogo
    return catalogo.familia(pdf.ruta_relativa or '') == 'guia'

def _clave_de_maquetacion(texto: str) -> str:
    return ''.join(texto.split())

def _zona_de_borde(n: int) -> set[int]:
    return set(range(min(LINEAS_DE_BORDE, n))) | set(range(max(0, n - LINEAS_DE_BORDE), n))

def _tiradas_del_borde(n: int, zona: set[int]):
    """Public CI documentation."""
    for s in sorted(zona):
        for largo in range(1, TIRADA_MAXIMA + 1):
            if s + largo > n or s + largo - 1 not in zona:
                break
            yield (s, largo)

def _se_escribe_con(clave: str, bases: list[str]) -> bool:
    """Public CI documentation."""
    if not (any((clave.startswith(b) for b in bases)) and any((clave.endswith(b) for b in bases))):
        return False
    alcanza = [False] * (len(clave) + 1)
    alcanza[0] = True
    for i in range(len(clave)):
        if alcanza[i]:
            for b in bases:
                if clave.startswith(b, i):
                    alcanza[i + len(b)] = True
    return alcanza[-1]

def _resto_tras(texto: str, clave: str) -> tuple[int, str] | None:
    """Public CI documentation."""
    j = 0
    for i, c in enumerate(texto):
        if c.isspace():
            continue
        if c != clave[j]:
            return None
        j += 1
        if j == len(clave):
            resto = texto[i + 1:]
            sin = resto.lstrip()
            return (len(resto) - len(sin), sin) if sin and resto[:1].isspace() else None
    return None

def _titulo_corriente(resto: str, hueco: int) -> bool:
    """Public CI documentation."""
    return hueco >= 2 and any((c.isalpha() for c in resto)) and (len(resto) <= LARGO_MAXIMO_DE_TITULO_CORRIENTE) and (not any((c.isdigit() for c in resto)))

def _maquetacion_en_tirada(pdf: TextoPdf, repetidas: set[str], variantes: set[str]) -> tuple[dict[int, frozenset[int]], set[str]]:
    """Public CI documentation."""
    from collections import defaultdict
    paginas = pdf.paginas
    n = len(paginas)
    if n < 4 or pdf.n_paginas < 4:
        return ({}, set())
    quitadas = repetidas | variantes
    vistas: list[list[tuple[int, str, bool, bool]]] = []
    for i, pag in enumerate(paginas):
        lin = []
        for k, ln in enumerate(pag.split('\n')):
            t = ln.strip()
            if t:
                ya = any((r.match(ln) for r in RUIDO)) or t in (quitadas if i else repetidas) or RE_NUMERO_SUELTO.match(t) is not None
                lin.append((k, t, ya, len(t) <= 3))
        vistas.append(lin)

    def texto_de(tramo) -> str:
        return ' '.join((' '.join(t.split()) for _, t, _, _ in tramo))

    def sin_novedad(tramo) -> bool:
        return all((ya or sin for _, _, ya, sin in tramo))
    minimo = max(PAGINAS_MINIMAS_EN_TIRADA, int(n * 0.5))
    clases = [set(range(0, n, 2)), set(range(1, n, 2))]
    minimo_clase = [max(PAGINAS_MINIMAS_EN_TIRADA, int(len(c) * 0.5)) for c in clases]
    en_borde: dict[str, set[int]] = defaultdict(set)
    texto_de_clave: dict[str, str] = {}
    de_un_renglon: set[str] = set()
    cabezas: dict[str, set[int]] = defaultdict(set)
    n_de_m: set[int] = set()
    for i, lin in enumerate(vistas):
        zona = _zona_de_borde(len(lin))
        for s, largo in _tiradas_del_borde(len(lin), zona):
            tramo = lin[s:s + largo]
            if sin_novedad(tramo):
                continue
            texto = texto_de(tramo)
            if LARGO_MINIMO_DE_TIRADA <= len(texto) <= LARGO_MAXIMO_DE_TIRADA:
                c = _clave_de_maquetacion(texto)
                en_borde[c].add(i)
                texto_de_clave.setdefault(c, texto)
                if largo == 1:
                    de_un_renglon.add(c)
        for s in zona:
            t = lin[s][1]
            if _es_n_de_m(t):
                n_de_m.add(i)
            celdas = [x for x in RE_CELDAS.split(t) if x]
            if len(celdas) >= 2 and len(celdas[0]) >= LARGO_MINIMO_DE_CABECERA and _titulo_corriente(' '.join(celdas[1:]), 2):
                cabezas[_clave_de_maquetacion(celdas[0])].add(i)
    candidatas = {c for c, ps in en_borde.items() if len(ps) >= minimo or any((len(ps & clases[p]) >= minimo_clase[p] for p in (0, 1)))}
    candidatas_cabecera = {c for c, ps in cabezas.items() if len(ps | en_borde.get(c, set())) >= minimo}
    en_cualquier_sitio: dict[str, set[int]] = defaultdict(set)
    if candidatas or candidatas_cabecera:
        for i, lin in enumerate(vistas):
            for s in range(len(lin)):
                for largo in range(1, TIRADA_MAXIMA + 1):
                    if s + largo > len(lin):
                        break
                    c = _clave_de_maquetacion(texto_de(lin[s:s + largo]))
                    if c in candidatas or c in candidatas_cabecera:
                        en_cualquier_sitio[c].add(i)
                celdas = [x for x in RE_CELDAS.split(lin[s][1]) if x]
                if len(celdas) >= 2:
                    c = _clave_de_maquetacion(celdas[0])
                    if c in candidatas_cabecera:
                        en_cualquier_sitio[c].add(i)
    nuevas = {c for c in candidatas if len(en_borde[c]) >= 0.8 * len(en_cualquier_sitio[c])}
    cabeceras_nuevas = {c for c in candidatas_cabecera if len(cabezas[c] | en_borde.get(c, set())) >= 0.8 * len(en_cualquier_sitio[c])}
    pie_n_de_m = len(n_de_m) >= minimo
    conocidas = {_clave_de_maquetacion(q) for q in quitadas if len(q.strip()) > 3}
    claves_conocidas = conocidas | nuevas | cabeceras_nuevas
    bases = sorted((c for c in claves_conocidas if len(c) >= LARGO_MINIMO_DE_TIRADA))
    cabeceras = [c for c in bases if len(c) >= LARGO_MINIMO_DE_CABECERA - 2]
    planas = nuevas & de_un_renglon | cabeceras_nuevas
    titulos: dict[tuple[str, str], set[int]] = defaultdict(set)
    for i, lin in enumerate(vistas):
        if i:
            for s in _zona_de_borde(len(lin)):
                _, t, ya, _ = lin[s]
                if not ya:
                    for c in cabeceras:
                        r = _resto_tras(t, c)
                        if r:
                            titulos[c, _clave_de_maquetacion(r[1])].add(i)
    quitar: dict[int, set[int]] = defaultdict(set)
    textos: set[str] = set()
    for i, lin in enumerate(vistas):
        if i == 0:
            continue
        zona = _zona_de_borde(len(lin))
        for s, largo in _tiradas_del_borde(len(lin), zona):
            tramo = lin[s:s + largo]
            if sin_novedad(tramo):
                continue
            texto = texto_de(tramo)
            c = _clave_de_maquetacion(texto)
            if LARGO_MINIMO_DE_TIRADA <= len(texto) <= LARGO_MAXIMO_DE_TIRADA and (c in claves_conocidas or _se_escribe_con(c, bases)):
                quitar[i].update((k for k, _, _, _ in tramo))
                textos.add(texto)
        for k, t, ya, _ in lin:
            if not ya and _clave_de_maquetacion(t) in planas:
                quitar[i].add(k)
                textos.add(' '.join(t.split()))
        for s in zona:
            k, t, ya, _ = lin[s]
            if ya or k in quitar[i]:
                continue
            if pie_n_de_m and _es_n_de_m(t):
                quitar[i].add(k)
                textos.add('#/#')
                continue
            for c in cabeceras:
                r = _resto_tras(t, c)
                if r and (_titulo_corriente(r[1], r[0]) or len(titulos[c, _clave_de_maquetacion(r[1])]) >= TITULOS_CORRIENTES):
                    quitar[i].add(k)
                    textos.add(' '.join(t.split()))
                    break
    return ({i: frozenset(ks) for i, ks in quitar.items() if ks}, textos)

def textos_de_maquetacion_en_tirada(pdf: TextoPdf) -> list[str]:
    """Public CI documentation."""
    if not _es_de_guia(pdf):
        return []
    repetidas = lineas_repetidas(pdf)
    return sorted(_maquetacion_en_tirada(pdf, repetidas, _variantes_de_maquetacion(pdf, repetidas))[1])
VECINA_CORTA = 25
VECINA_LARGA = 40
TIRADA_MINIMA = 5
RE_ENTRADA_INDICE = re.compile('^\\s*(?:\\d+(?:\\.\\d+){0,3}|[A-Z](?:\\.\\d+){1,3})\\.?\\s+[^\\W\\d]')
RE_PUNTOS_SIN_PAGINA = re.compile('\\.\\s*\\.\\s*\\.\\s*\\.\\s*$')
RE_ROTULO_INDICE = re.compile('^\\s*(?:TABLE\\s+OF\\s+CONTENTS|CONTENTS|[ÍI]NDICE(?:\\s+GENERAL)?|SUMARIO|CONTENIDOS?|TABLE\\s+DES\\s+MATI[ÈE]RES|INHALTSVERZEICHNIS)\\s*$', re.I)
LINEAS_DEL_ROTULO = 3
RE_TITULO_DISPOSICION = re.compile('^\\s*(?:ORDEN|REAL\\s+DECRETO(?:-LEY)?|DECRETO|LEY(?:\\s+ORG[ÁA]NICA)?|RESOLUCI[ÓO]N|CORRECCI[ÓO]N|CIRCULAR|INSTRUCCI[ÓO]N|ACUERDO)\\s+de\\s')
DIGITOS_DISPOSICION = 5
CELDA = 'celda'

def paginas_vivas(pdf: TextoPdf) -> list[list[str]]:
    """Public CI documentation."""
    repetidas = lineas_repetidas(pdf)
    variantes = _variantes_de_maquetacion(pdf, repetidas)
    con_variantes = repetidas | variantes
    en_tirada = _maquetacion_en_tirada(pdf, repetidas, variantes)[0] if _es_de_guia(pdf) else {}
    return [[ln for k, ln in enumerate(pag.split('\n')) if not any((r.match(ln) for r in RUIDO)) and ln.strip() not in (con_variantes if i else repetidas) and (k not in en_tirada.get(i, ()))] for i, pag in enumerate(pdf.paginas)]

def paginas_con_indice(paginas: list[list[str]]) -> set[int]:
    """Public CI documentation."""
    indice: set[int] = set()
    for i, v in enumerate(paginas, start=1):
        ls = [ln.strip() for ln in v if ln.strip()]
        sueltos = [(j, int(t)) for j, t in enumerate(ls) if RE_NUMERO_SUELTO.match(t)]
        if not sueltos:
            continue
        tras_entrada = [n for j, n in sueltos if j > 0 and RE_ENTRADA_INDICE.match(ls[j - 1])]
        if len(tras_entrada) >= 3 and all((a <= b for a, b in zip(tras_entrada, tras_entrada[1:]))):
            indice.add(i)
        if any((RE_ROTULO_INDICE.match(t) for t in ls[:LINEAS_DEL_ROTULO])):
            indice.add(i)
    return indice

def desfases_de_paginacion(paginas: list[list[str]]) -> set[int]:
    """Public CI documentation."""
    from collections import defaultdict
    paginas_de = defaultdict(set)
    for i, v in enumerate(paginas, start=1):
        for ln in v:
            if RE_NUMERO_SUELTO.match(ln):
                paginas_de[int(ln) - i].add(i)
    minimo = max(3, -(-len(paginas) // 4))
    return {d for d, ps in paginas_de.items() if len(ps) >= minimo}
PALABRAS_DE_REFERENCIA_AL_PIE = frozenset({'page', 'pages', 'p', 'pp', 'chapter', 'clause', 'clauses', 'section', 'annex', 'appendix', 'table', 'figure', 'fig', 'no', 'n', 'item', 'step', 'part', 'article', 'art', 'paragraph', 'para', 'point', 'class', 'version', 'level', 'group', 'type', 'pagina', 'paginas', 'pag', 'capitulo', 'apartado', 'tabla', 'figura', 'anexo', 'apendice', 'articulo', 'num', 'numero', 'punto', 'paso', 'parte', 'clase', 'nivel', 'grupo', 'tipo', 'norma', 'iso', 'en', 'une', 'oiml', 'r', 'd', 'c', 'v'})
RE_PIE_CON_NUMERO = re.compile('^(?P<texto>.*?\\S)\\s+(?P<n>\\d{1,4})$')

def sin_numero_de_pagina_pegado(lp: list[tuple[str, int]], desfases: set[int]) -> tuple[list[tuple[str, int]], int]:
    """Public CI documentation."""
    if not desfases:
        return (lp, 0)
    ultima: dict[int, int] = {}
    for k, (ln, pag) in enumerate(lp):
        if ln.strip():
            ultima[pag] = k
    cambios: dict[int, str] = {}
    for pag, k in ultima.items():
        m = RE_PIE_CON_NUMERO.match(lp[k][0].rstrip())
        if not m or int(m.group('n')) - pag not in desfases:
            continue
        palabras = [sin_tilde(x.lower().strip('.,;:()[]')) for x in m.group('texto').split()]
        previa = palabras[-1] if palabras else ''
        if previa in PALABRAS_DE_REFERENCIA_AL_PIE or (previa.isdigit() and len(palabras) > 1 and palabras[-2].isdigit()):
            continue
        cambios[k] = m.group('texto')
    if not cambios:
        return (lp, 0)
    return ([(cambios.get(k, ln), pag) for k, (ln, pag) in enumerate(lp)], len(cambios))

def motivos_de_enteros(paginas: list[list[str]]) -> dict[tuple[int, int], str]:
    """Public CI documentation."""
    from collections import defaultdict
    llenas = [[k for k, ln in enumerate(v) if ln.strip()] for v in paginas]

    def texto(i: int, j: int) -> str:
        return paginas[i - 1][llenas[i - 1][j]].strip()
    sueltos = [(i, j, int(texto(i, j))) for i, ll in enumerate(llenas, start=1) for j in range(len(ll)) if RE_NUMERO_SUELTO.match(texto(i, j))]
    motivos: dict[tuple[int, int], str] = {}
    if not sueltos:
        return motivos

    def interior(i: int, j: int) -> bool:
        return 0 < j < len(llenas[i - 1]) - 1

    def larga(i: int, j: int) -> bool:
        return len(texto(i, j - 1)) >= VECINA_LARGA and len(texto(i, j + 1)) >= VECINA_LARGA

    def tras_puntos(i: int, j: int) -> bool:
        return j > 0 and bool(RE_PUNTOS_SIN_PAGINA.search(texto(i, j - 1)))
    indice = paginas_con_indice(paginas)
    dentro = [(i, j) for i, j, _ in sueltos if interior(i, j) and (not tras_puntos(i, j)) and (i not in indice)]
    en_prosa = sum((1 for i, j in dentro if larga(i, j)))
    numerado = en_prosa >= 3 and 2 * en_prosa >= len(dentro)
    desfases = desfases_de_paginacion(paginas)
    cabecera_tabla = re.compile('^(?:tabla|cuadro|table)\\s+(?:\\d+|[A-Z])(?:[ .:—-]|$)|\\bplan\\s+de\\s+muestreo\\b|\\b(?:mg|µg|μg|g|mmol)\\s*/\\s*(?:kg|l|ml)\\b|^(?:n[úu]mero\\s+de\\s+(?:horas|interrupciones|animales)|tama[ñn]o\\s+m[íi]nimo\\s+de\\s+la\\s+muestra)\\b', re.I)
    fin_tabla = re.compile('^(?:Art[íi]culo\\s|CAP[ÍI]TULO\\s|ANEXO\\s|Disposici[óo]n\\s|\\([*\\d]+\\)\\s|\\d+\\.\\s+[^\\W\\d])')
    fila_numerica = re.compile('^[<>≤≥+−\\-\\d][\\d\\s.,%<>≤≥+−\\-]*$')
    celdas_tabla: set[tuple[int, int]] = set()
    for i, ll in enumerate(llenas, start=1):
        ls = [texto(i, j) for j in range(len(ll))]
        if any((RE_ROTULO_INDICE.match(s) for s in ls[:LINEAS_DEL_ROTULO])):
            continue
        inicio = None

        def cerrar(fin: int) -> None:
            if inicio is None:
                return
            filas = [s for s in ls[inicio:fin] if fila_numerica.fullmatch(s)]
            valores = sum((bool(re.match('^\\d+\\b', s)) for s in ls[inicio:fin]))
            if len(filas) >= 2 and valores >= 3:
                celdas_tabla.update(((i, j) for j in range(inicio, fin)))
        for j, s in enumerate(ls):
            if fin_tabla.match(s) or RE_PUNTOS_SIN_PAGINA.search(s) or RE_PUNTOS_DE_INDICE.search(s) or (len(s) > 160 and (not re.match('^\\d+\\.\\d+\\b', s))):
                cerrar(j)
                inicio = None
            if len(s) <= 120 and cabecera_tabla.search(s):
                if inicio is None:
                    inicio = j
        cerrar(len(ls))
    por_pagina = defaultdict(list)
    for i, j, n in sueltos:
        por_pagina[i].append((j, n))
    tirada: set[tuple[int, int]] = set()
    for i, lista in por_pagina.items():
        serie = lista[:1]
        for (j0, n0), (j1, n1) in zip(lista, lista[1:]):
            if n1 == n0 + 1 and j1 > j0 + 1:
                serie.append((j1, n1))
                continue
            if len(serie) >= TIRADA_MINIMA:
                tirada.update(((i, j) for j, _ in serie))
            serie = [(j1, n1)]
        if len(serie) >= TIRADA_MINIMA:
            tirada.update(((i, j) for j, _ in serie))

    def es_encabezado_de_borde(i: int, j: int, n: int) -> bool:
        if j != 0 or i in indice or len(llenas[i - 1]) < 2:
            return False
        sig = texto(i, 1)
        if not re.match('^[A-ZÁÉÍÓÚÑ]', sig) or RE_PUNTOS_SIN_PAGINA.search(sig) or RE_PUNTOS_DE_INDICE.search(sig) or RE_MES.match(sig) or (sig.split(None, 1)[0].strip(',.;:') in PALABRAS_DE_ENLACE):
            return False
        return any((re.match(f'^\\s*{n}\\.1\\b', texto(i, k)) for k in range(2, len(llenas[i - 1]))))
    for i, j, n in sueltos:
        es_celda_tabla = (i, j) in celdas_tabla and (not numerado) and (n - i not in desfases) and ((i, j) not in tirada) and (not tras_puntos(i, j)) and (not (not interior(i, j) and n == i)) and (not (interior(i, j) and len(texto(i, j)) <= DIGITOS_DISPOSICION and RE_TITULO_DISPOSICION.match(texto(i, j + 1))))
        if es_celda_tabla:
            motivo = CELDA
        elif not interior(i, j):
            motivo = CELDA if es_encabezado_de_borde(i, j, n) else 'borde'
        elif numerado:
            motivo = 'documento'
        elif n - i in desfases:
            motivo = 'pagina'
        elif i in indice or tras_puntos(i, j):
            motivo = 'indice'
        elif len(texto(i, j)) <= DIGITOS_DISPOSICION and RE_TITULO_DISPOSICION.match(texto(i, j + 1)):
            motivo = 'disposicion'
        elif (i, j) in tirada:
            motivo = 'tirada'
        elif len(texto(i, j - 1)) > VECINA_CORTA and len(texto(i, j + 1)) > VECINA_CORTA:
            motivo = 'prosa'
        else:
            motivo = CELDA
        motivos[i, llenas[i - 1][j]] = motivo
    return motivos

def lineas_con_pagina(pdf: TextoPdf, quitar_ajeno: bool=True) -> list[tuple[str, int]]:
    paginas = paginas_vivas(pdf)
    motivos = motivos_de_enteros(paginas)
    lp = [(ln.rstrip(), i) for i, vivas in enumerate(paginas, start=1) for k, ln in enumerate(vivas) if not RE_NUMERO_SUELTO.match(ln) or motivos.get((i, k)) == CELDA]
    lp = sin_numero_de_pagina_pegado(lp, desfases_de_paginacion(paginas))[0]
    if quitar_ajeno and (getattr(pdf, 'texto_ajeno_ue', False) or getattr(pdf, 'maquetacion_del_pdf', None)):
        from . import texto_ajeno_ue
        lp = texto_ajeno_ue.quitar_del_flujo(lp, pdf.notas_del_diario, pdf.n_paginas, getattr(pdf, 'maquetacion_del_pdf', None), getattr(pdf, 'texto_ajeno_ue', False))[0]
    return lp
MESES = {m: i + 1 for i, m in enumerate('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split())}

def fecha_es(texto: str) -> str | None:
    m = re.search('(\\d{1,2})\\s+de\\s+([a-zñáéíóú]+)\\s+de\\s+(\\d{4})', texto, re.I)
    if not m:
        return None
    mes = MESES.get(sin_tilde(m.group(2).lower()))
    return f'{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}' if mes else None
RE_INICIO_DEL_CUERPO_TEXTO_BOE = '^\\s*TEXTO (?:CONSOLIDADO|ORIGINAL)\\s*$'
RE_ARTICULO_SANIDAD = re.compile('^Artículo\\s+([a-záéíóúñ ]+)\\.\\s*(.*)$')
CARDINALES_SANIDAD = {palabra: n for n, palabra in enumerate(('', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciseis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiuno', 'veintidos', 'veintitres', 'veinticuatro', 'veinticinco', 'veintiseis', 'veintisiete', 'veintiocho', 'veintinueve')) if n}
DECENAS_SANIDAD = dict(zip(('treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa'), range(30, 100, 10)))
RE_ITC_BT52 = re.compile('^INSTRUCCI[ÓO]N T[ÉE]CNICA COMPLEMENTARIA \\(ITC\\) (BT-52)(?:\\s+([A-ZÁÉÍÓÚÑ].*))?$')
RE_ITC_REBT = re.compile('^ITC-(BT-\\d{2})\\.?(?:\\s+([A-ZÁÉÍÓÚÑ].*))?$')

def _numero_articulo_sanidad(palabras: str) -> str | None:
    p = sin_tilde(' '.join(palabras.split())).lower()
    bis = p.endswith(' bis')
    if bis:
        p = p[:-4]
    centena = 100 if p.startswith('ciento ') else 0
    if centena:
        p = p[7:]
    if p in ('cien', 'ciento'):
        n = 100
    elif p in CARDINALES_SANIDAD:
        n = centena + CARDINALES_SANIDAD[p]
    elif p in DECENAS_SANIDAD:
        n = centena + DECENAS_SANIDAD[p]
    else:
        decena, sep, unidad = p.partition(' y ')
        if not sep or decena not in DECENAS_SANIDAD or (not 1 <= CARDINALES_SANIDAD.get(unidad, 0) <= 9):
            return None
        n = centena + DECENAS_SANIDAD[decena] + CARDINALES_SANIDAD[unidad]
    return str(n) + ('bis' if bis else '') if 1 <= n <= 116 else None
RE_BOE = {'libro': re.compile(f'^\\s*LIBRO\\s+(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO){RUBRICA}\\s*$'), 'capitulo': re.compile(f'^\\s*CAP[ÍI]TULO\\s+({NUM_DIV}|[ÚU]NICO|PRELIMINAR){RUBRICA}\\s*$'), 'titulo_div': re.compile(f'^\\s*T[ÍI]TULO\\s+({NUM_DIV}|PRELIMINAR|PRIMERO){RUBRICA}\\s*$'), 'seccion': re.compile(f'^\\s*Secci[óo]n\\s+(\\d+)\\.\\s?[ªa]{RUBRICA}\\s*$'), 'articulo': re.compile(f'^\\s*(?-i:A)rt[íi][ct]ulo\\s+(\\d+(?:\\s?{ORD_ARTICULO})?|[úu]nico)\\.\\s*(.*)$', re.I), 'disposicion': re.compile(f'^\\s*Disposici[óo]n\\s+(adicional|transitoria|derogatoria|final)\\s+({ORD_DISPOSICION})\\.?\\s*(.*)$', re.I), 'disposicion_sin_ordinal': re.compile('^\\s*Disposici[óo]n\\s+(adicional|transitoria|derogatoria|final)\\.\\s*(.*)$', re.I), 'anexo': re.compile(f'^\\s*ANE(?:XO|JO)(?:\\s+({NUM_DIV}|[ÚU]NICO){RUBRICA})?\\s*$', re.I), 'apendice': re.compile(f'^\\s*AP[ÉE]NDICE\\s+({NUM_DIV}){RUBRICA}\\s*$', re.I), 'apartado': re.compile('^\\s*Apartado\\s+(\\d+)\\.\\s*(.*)$'), 'tabla': re.compile('^\\s*Tabla\\s+(\\d+)\\.?\\s*(.*)$'), 'instruccion': re.compile('^\\s*INSTRUCCI[ÓO]N\\s+(?:T[ÉE]CNICA\\s+COMPLEMENTARIA\\s+)?((?:ITC-)?[A-Z]{2,4}-\\d{1,3})\\.?(?:\\s+([A-ZÁÉÍÓÚÑ].*))?\\s*$'), 'reglamento': re.compile('^\\s*REGLAMENTO\\s+(?:DE|DEL|PARA|SOBRE|GENERAL|T[ÉE]CNICO)\\s[A-ZÁÉÍÓÚÑ ,.\\-]+$')}
RE_BOLETIN = re.compile('(?:«?BOE»?\\s*)?N[uú]m\\.\\s*\\d+.{0,40}?\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}')
SIN_NUMERAL = 'sn'

def ruta_anexo(ordinal: str | None) -> str:
    """Public CI documentation."""
    return f'anexo.{ordinal}' if ordinal else f'anexo.{SIN_NUMERAL}'
RUTA_INSTRUCCION = 'itc'
RE_AP_DE_INSTRUCCION = re.compile('^\\s*(\\d{1,2}\\.|\\d{1,2}(?:\\.\\d{1,2}){1,4}\\.?)\\s+((?-i:[A-ZÁÉÍÓÚÑ¿«(]).*)$')
RE_INDICE_DE_INSTRUCCION = re.compile('^\\s*(?:0\\.\\s*)?[ÍI]NDICE\\b')
RE_ENTRADA_DE_INSTRUCCION = re.compile('(?:^|(?<=\\s))(\\d{1,2}\\.|\\d{1,2}(?:\\.\\d{1,2}){1,4}\\.?)(?=\\s+[A-ZÁÉÍÓÚÑ¿«(])')
RENGLONES_DE_RUBRICA = 3
RE_APENDICE_DE_INSTRUCCION = re.compile('^\\s*(?:LEGISLACI[ÓO]N CONSOLIDADA\\s+)?AP[ÉE]NDICE\\s+(\\d{1,2})(?:\\s+(.*))?$')

def _siguientes_de(ultimo: str | None) -> set[str]:
    """Public CI documentation."""
    if not ultimo:
        return {'1'}
    u = ultimo.split('.')
    salida = {'.'.join(u + ['1'])}
    for j in range(len(u)):
        salida.add('.'.join(u[:j] + [str(int(u[j]) + 1)]))
    return salida

def _entradas_de_indice(s: str) -> list[tuple[str, str]]:
    """Public CI documentation."""
    ms = list(RE_ENTRADA_DE_INSTRUCCION.finditer(s))
    return [(m.group(1).rstrip('.'), s[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(s)].strip()) for i, m in enumerate(ms)]

def _misma_rubrica(del_indice: str, del_cuerpo: str) -> bool:
    """Public CI documentation."""
    a, b = (_titulo_comparable(del_indice), _titulo_comparable(del_cuerpo))
    n = min(len(a), 40)
    return n >= 3 and difflib.SequenceMatcher(None, a[:n], b[:n]).ratio() >= 0.75

def _trozos_de_instruccion(s: str, ultimo: str | None, rubricas: dict[str, str]) -> list[tuple[str | None, str]]:
    """Public CI documentation."""
    cortes: list[tuple[int, str]] = []
    esperado = ultimo
    for m in RE_ENTRADA_DE_INSTRUCCION.finditer(s):
        num = m.group(1).rstrip('.')
        antes = s[:m.start()].rstrip()
        if num not in _siguientes_de(esperado) or (antes and (not antes.endswith('.'))):
            continue
        resto = s[m.end():].strip()
        rubrica_autonoma = not antes and (resto.isupper() or re.fullmatch('\\((?:Derogad[oa]|Suprimid[oa]|Anulad[oa])\\)\\.?', resto))
        if '.' not in num and rubricas and (not (rubrica_autonoma or (num in rubricas and _misma_rubrica(rubricas[num], s[m.end():])))):
            continue
        cortes.append((m.start(), num))
        esperado = num
    if not cortes:
        return [(None, s)]
    trozos: list[tuple[str | None, str]] = []
    if cortes[0][0] > 0:
        trozos.append((None, s[:cortes[0][0]].rstrip()))
    for i, (pos, num) in enumerate(cortes):
        fin = cortes[i + 1][0] if i + 1 < len(cortes) else len(s)
        trozos.append((num, s[pos:fin].rstrip()))
    return trozos

def _rubrica_de_apartado(resto: str) -> str:
    """Public CI documentation."""
    m = re.match('^(.{3,160}?\\.)\\s+\\S', resto)
    return m.group(1) if m else resto.strip()
RE_ARTICULO_PEGADO = re.compile('(?<=[.:;)])\\s+(?=(?-i:A)rt[íi][ct]ulo\\s+(\\d+)\\.\\s+[«(A-ZÁÉÍÓÚ])')

def partir_articulos_pegados(lp: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Public CI documentation."""
    salida: list[tuple[str, int]] = []
    ultimo: int | None = None
    for ln, pag in lp:
        resto = ln
        while True:
            m = RE_BOE['articulo'].match(resto)
            if m and m.group(1).strip().isdigit():
                ultimo = int(m.group(1))
            corte = None
            if ultimo is not None:
                corte = next((k for k in RE_ARTICULO_PEGADO.finditer(resto) if int(k.group(1)) == ultimo + 1), None)
            if corte is None:
                salida.append((resto, pag))
                break
            salida.append((resto[:corte.start()], pag))
            resto = resto[corte.end():]
    return salida
RE_TITULO_REGLAMENTO = re.compile('^\\s*REGLAMENTO\\s[^a-zñáéíóúü]{6,}$')

def _es_encabezado_de_precepto(s: str, en_anexo: bool) -> bool:
    """Public CI documentation."""
    s_enc = s.lstrip(COMILLAS_APERTURA) if s[0] in COMILLAS_APERTURA else s
    if any((RE_BOE[k].match(s_enc) for k in ('anexo', 'capitulo', 'titulo_div', 'instruccion'))):
        return True
    if any((RE_BOE[k].match(s) for k in ('articulo', 'disposicion', 'disposicion_sin_ordinal'))):
        return True
    if en_anexo:
        return bool(RE_BOE['apendice'].match(s_enc) or RE_BOE['tabla'].match(s) or RE_BOE['apartado'].match(s))
    return False

def _sigue_un_encabezado(lineas: list[tuple[str, int]], k: int, en_anexo: bool) -> bool:
    """Public CI documentation."""
    for ln, _ in lineas[k + 1:k + 12]:
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub('', ln.strip())
        if not s or any((r.match(s) for r in RUIDO_BOE)):
            continue
        return _es_encabezado_de_precepto(s, en_anexo)
    return False

def _sigue_reglamento_articulado(lineas: list[tuple[str, int]], k: int) -> bool:
    """Public CI documentation."""
    siguientes = []
    for ln, _ in lineas[k + 1:k + 12]:
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub('', ln.strip())
        if not s or any((r.match(s) for r in RUIDO_BOE)):
            continue
        siguientes.append(s)
        if len(siguientes) == 2:
            break
    return len(siguientes) == 2 and bool(re.fullmatch('REGLAMENTO\\s+(?:DE|DEL|PARA|SOBRE|GENERAL|T[ÉE]CNICO)\\s+.+', siguientes[0], re.I)) and any((RE_BOE[tipo].match(siguientes[1]) for tipo in ('capitulo', 'titulo_div', 'articulo')))

def analizar_boe(pdf: TextoPdf) -> Analisis:
    from . import estructura_r3b
    correccion_r3b = estructura_r3b.de_pdf(pdf)
    an = Analisis()
    texto_p1 = pdf.paginas[0] if pdf.paginas else ''
    m = re.search('Referencia:\\s*(\\S+)', texto_p1)
    an.identificador = m.group(1).strip() if m else None
    lineas_p1 = [l.strip() for l in texto_p1.split('\n') if l.strip()]
    if len(lineas_p1) > 1:
        an.titulo = lineas_p1[1]
    todo = pdf.texto
    mu = re.search('[ÚU]ltima modificaci[óo]n:\\s*([^\\n]+)', todo)
    if mu:
        crudo = mu.group(1).strip()
        an.cabecera = crudo
        an.es_consolidada = True
        an.fecha_consolidacion = fecha_es(crudo)
    lp = lineas_con_pagina(pdf)
    sin_sueltos = [i for i, (ln, _) in enumerate(lp) if not RE_NUMERO_SUELTO.match(ln)]
    inicio = 0
    for i, (ln, _) in enumerate(lp):
        if re.match(RE_INICIO_DEL_CUERPO_TEXTO_BOE if pdf.motor == MOTOR_TEXTO_BOE else '^\\s*TEXTO CONSOLIDADO', ln):
            inicio = i + 1
            break
    else:
        tope = max(20, len(sin_sueltos) // 5)
        ultimo = max((i for i in sin_sueltos[:tope] if INDICE.search(lp[i][0])), default=-1)
        inicio = ultimo + 1
    preceptos: list[Precepto] = []
    cab_con_pagina = [(ln, pg) for ln, pg in lp[:inicio] if ln.strip() and (not INDICE.search(ln)) and (not RE_NUMERO_SUELTO.match(ln))][:8]
    cab_lineas = [ln for ln, _ in cab_con_pagina]
    cab_paginas = [pg for _, pg in cab_con_pagina]
    if inicio > 0 and lp[inicio - 1][0].strip() not in cab_lineas and re.sub('(?i)texto\\s+(?:consolidado|original)', '', lp[inicio - 1][0]).strip():
        cab_lineas.append(lp[inicio - 1][0].strip())
        cab_paginas.append(lp[inicio - 1][1])
    if not cab_lineas:
        cab_lineas = [l.strip() for l in texto_p1.split('\n') if l.strip()][:8]
        cab_paginas = [1] * len(cab_lineas)
    if cab_lineas:
        preceptos.append(Precepto(ruta='cabecera', tipo='cabecera', numero=None, etiqueta='Cabecera bibliográfica', titulo=None, lineas=cab_lineas, pagina_inicio=min(cab_paginas), pagina_fin=max(cab_paginas)))
    actual: Precepto | None = Precepto(ruta='preambulo', tipo='preambulo', numero=None, etiqueta='Preámbulo', titulo=None, pagina_inicio=1, pagina_fin=1)
    ctx_anexo: str | None = None
    ctx_apendice: str | None = None
    ctx_capitulo: str | None = None
    ctx_titulo: str | None = None
    ctx_libro: str | None = None
    etiqueta_libro: str | None = None
    libro_sin_prefijo: str | None = None
    ctx_itc: str | None = None
    itc_ultimo: str | None = None
    itc_rubrica = 0
    itc_indice = False
    itc_primero: str | None = None
    itc_rubricas: dict[str, str] = {}
    itc_en_apendice = itc_rubrica_apendice = False
    visto_disp_final = False
    ctx_reglamento = False
    ruta_division: str | None = None
    etiqueta_division: str | None = None
    rutas_de_seccion: set[str] = set()
    citas = 0
    reglamento_abierto = False

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None

    def abrir(ruta, tipo, numero, etiqueta, titulo, pagina, padre, encabezado=None):
        nonlocal actual, citas
        cerrar()
        citas = 0
        actual = Precepto(ruta=ruta, tipo=tipo, numero=numero, etiqueta=etiqueta, titulo=titulo or None, pagina_inicio=pagina, pagina_fin=pagina, padre=padre)
        if encabezado:
            actual.lineas.append(encabezado)
    lineas_boe = partir_articulos_pegados(lp[inicio:])
    for k_ln, (ln, pag) in enumerate(lineas_boe):
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub('', ln.strip())
        if s and any((r.match(s) for r in RUIDO_BOE)):
            continue
        mp = RE_PAGINA_PEGADA.search(s) if s else None
        if mp and int(mp.group(1)) == pag:
            s = s[:mp.start()].rstrip()
        mp = RE_PIE_PEGADO_AL_FINAL.search(s) if s and pag == pdf.n_paginas else None
        if mp:
            s = s[:mp.start()].rstrip()
        if not s:
            if actual:
                actual.lineas.append('')
            continue
        en_disp = actual is not None and actual.tipo == 'disposicion'
        citado = en_disp and s[0] in COMILLAS_APERTURA
        dentro_de_cita = en_disp and citas > 0
        s_enc = s.lstrip(COMILLAS_APERTURA) if s[0] in COMILLAS_APERTURA else s
        m = RE_BOE['anexo'].match(estructura_r3b.encabezado_boe(s_enc, correccion_r3b))
        if m and (not citado):
            numero_anexo = numeral_division((m.group(1) or '').upper())
            ctx_anexo = numero_anexo
            if not numero_anexo and visto_disp_final and _sigue_reglamento_articulado(lineas_boe, k_ln):
                ctx_anexo = None
            ctx_apendice = None
            ctx_capitulo = None
            ctx_titulo = None
            ctx_itc = None
            ruta_ax = ruta_anexo(numero_anexo or None)
            ruta_division, etiqueta_division = (ruta_ax, f'Anexo {numero_anexo}'.strip())
            abrir(ruta_ax, 'anexo', numero_anexo or None, f'Anexo {numero_anexo}'.strip(), (m.group(2) or '').strip() or None, pag, None, s)
            continue
        m = RE_BOE['instruccion'].match(s_enc)
        if not m and an.identificador == 'BOE-A-2014-13681':
            m = RE_ITC_BT52.match(s_enc)
        if not m and an.identificador == 'BOE-A-2002-18099':
            m = RE_ITC_REBT.match(s_enc)
        if m:
            ctx_itc = m.group(1)
            ctx_anexo = ctx_apendice = ctx_capitulo = ctx_titulo = None
            ruta_division = etiqueta_division = None
            itc_ultimo, itc_indice, itc_primero, itc_rubricas = (None, False, None, {})
            itc_en_apendice = itc_rubrica_apendice = False
            rubrica = (m.group(2) or '').strip()
            itc_rubrica = 0 if rubrica else RENGLONES_DE_RUBRICA
            abrir(f'{RUTA_INSTRUCCION}.{ctx_itc}', 'instruccion', ctx_itc, f'Instrucción {ctx_itc}', rubrica or None, pag, None, s)
            continue
        if ctx_itc:
            ruta_itc = f'{RUTA_INSTRUCCION}.{ctx_itc}'
            en_la_cabeza = actual is not None and actual.ruta == ruta_itc
            m = RE_APENDICE_DE_INSTRUCCION.match(s)
            if m:
                rubrica = (m.group(2) or '').strip()
                abrir(f'{ruta_itc}/apend.{m.group(1)}', 'apendice', m.group(1), f'Instrucción {ctx_itc}, Apéndice {m.group(1)}', rubrica or None, pag, ruta_itc, s)
                itc_en_apendice, itc_rubrica_apendice = (True, not rubrica)
                continue
            if itc_en_apendice:
                if itc_rubrica_apendice and actual is not None and (len(s) <= 150):
                    actual.titulo = s
                itc_rubrica_apendice = False
                if actual:
                    actual.lineas.append(s)
                    actual.pagina_fin = pag
                continue
            if itc_rubrica and en_la_cabeza:
                if s == s.upper() and re.search('[A-ZÁÉÍÓÚÑ]{3}', s) and (not RE_INDICE_DE_INSTRUCCION.match(s)) and (not (an.identificador == 'BOE-A-2002-18099' and RE_AP_DE_INSTRUCCION.match(s))):
                    actual.titulo = f'{actual.titulo} {s}' if actual.titulo else s
                    actual.lineas.append(s)
                    actual.pagina_fin = pag
                    itc_rubrica -= 1
                    continue
            itc_rubrica = 0
            en_el_cuerpo = itc_ultimo is not None or not en_la_cabeza
            if not en_el_cuerpo:
                m = RE_AP_DE_INSTRUCCION.match(s)
                entradas = _entradas_de_indice(s)
                num = m.group(1).rstrip('.') if m and len(entradas) <= 1 else None
                if RE_INDICE_DE_INSTRUCCION.match(s):
                    itc_indice = True
                if num is None and any((n == '1' for n, _ in entradas)):
                    itc_primero = '1'
                if itc_indice:
                    if num == '1' and itc_primero is None:
                        itc_primero = '1'
                        num = None
                    elif num != '1':
                        num = None
                en_el_cuerpo = num == '1'
                if not en_el_cuerpo:
                    for n, r in entradas:
                        itc_rubricas.setdefault(n, r)
            trozos = _trozos_de_instruccion(s, itc_ultimo, itc_rubricas) if en_el_cuerpo else [(None, s)]
            for num, trozo in trozos:
                if num:
                    padre = f"{ruta_itc}/ap.{num.rsplit('.', 1)[0]}" if '.' in num else ruta_itc
                    resto = trozo[RE_ENTRADA_DE_INSTRUCCION.match(trozo).end():].strip()
                    abrir(f'{ruta_itc}/ap.{num}', 'apartado', num, f'Instrucción {ctx_itc}, apartado {num}', _rubrica_de_apartado(resto), pag, padre, trozo)
                    itc_ultimo = num
                elif actual:
                    if not actual.lineas:
                        actual.pagina_inicio = pag
                    actual.lineas.append(trozo)
                    actual.pagina_fin = pag
            continue
        if visto_disp_final and ctx_anexo is None and (not reglamento_abierto) and RE_TITULO_REGLAMENTO.match(s_enc):
            reglamento_abierto = True
            ctx_reglamento = ctx_reglamento or bool(RE_BOE['reglamento'].match(s_enc))
            ruta_division = etiqueta_division = None
            abrir('reglamento', 'reglamento', None, 'Reglamento', s, pag, None, s)
            continue
        if visto_disp_final and ctx_anexo is None and RE_BOE['reglamento'].match(s_enc):
            ctx_reglamento = True
        m = RE_BOE['seccion'].match(s) if not (citado or dentro_de_cita) else None
        if m and (_sigue_un_encabezado(lineas_boe, k_ln, ctx_anexo is not None) or (correccion_r3b == 'BOE-A-2015-10566' and estructura_r3b.empieza_subseccion(lineas_boe, k_ln))):
            numero_s = m.group(1)
            ruta_s = f'{ruta_division}/seccion.{numero_s}' if ruta_division else f'seccion.{numero_s}'
            if ruta_s not in rutas_de_seccion:
                rutas_de_seccion.add(ruta_s)
                cerrar()
                preceptos.append(Precepto(ruta=ruta_s, tipo='seccion', numero=numero_s, etiqueta=f'{etiqueta_division}, Sección {numero_s}' if etiqueta_division else f'Sección {numero_s}', titulo=(m.group(2) or '').strip() or None, lineas=[s], pagina_inicio=pag, pagina_fin=pag, padre=ruta_division))
                continue
        m = RE_BOE['apendice'].match(s_enc)
        if m and ctx_anexo is not None:
            ctx_apendice = numeral_division(m.group(1).upper())
            r = f'{ruta_anexo(ctx_anexo)}/apend.{ctx_apendice}'
            abrir(r, 'apendice', ctx_apendice, f'Anexo {ctx_anexo}, Apéndice {ctx_apendice}', (m.group(2) or '').strip() or None, pag, ruta_anexo(ctx_anexo), s)
            continue
        m = RE_BOE['tabla'].match(s)
        if m and ctx_anexo:
            base = ruta_anexo(ctx_anexo) + (f'/apend.{ctx_apendice}' if ctx_apendice else '')
            et = f'Anexo {ctx_anexo}' + (f', Apéndice {ctx_apendice}' if ctx_apendice else '') + f', Tabla {m.group(1)}'
            abrir(f'{base}/tabla.{m.group(1)}', 'tabla', m.group(1), et, m.group(2).strip() or None, pag, base, s)
            continue
        m = RE_BOE['apartado'].match(s)
        if m and ctx_anexo is not None:
            base = ruta_anexo(ctx_anexo) + (f'/apend.{ctx_apendice}' if ctx_apendice else '')
            r = f'{base}/ap.{m.group(1)}'
            et = f'Anexo {ctx_anexo}' + (f', Apéndice {ctx_apendice}' if ctx_apendice else '') + f', apartado {m.group(1)}'
            abrir(r, 'apartado', m.group(1), et, m.group(2).strip() or None, pag, base, s)
            continue
        m = RE_BOE['libro'].match(s) if not (citado or dentro_de_cita or ctx_anexo is not None) else None
        if m:
            ctx_libro = ordinal_a_numero(m.group(1))
            if libro_sin_prefijo is None:
                libro_sin_prefijo = ctx_libro
            etiqueta_libro = f'Libro {m.group(1).lower()}'
            ctx_titulo = ctx_capitulo = None
            ruta_division, etiqueta_division = (f'libro.{ctx_libro}', etiqueta_libro)
            abrir(f'libro.{ctx_libro}', 'libro', ctx_libro, etiqueta_libro, (m.group(2) or '').strip() or None, pag, None, s)
            continue
        m = RE_BOE['capitulo'].match(s_enc) or RE_BOE['titulo_div'].match(s_enc)
        if m and (not (citado or dentro_de_cita)):
            ctx_capitulo = numeral_division(m.group(1))
            if sin_tilde(ctx_capitulo) in ('PRELIMINAR', 'PRIMERO', 'UNICO'):
                ctx_capitulo = sin_tilde(ctx_capitulo).lower()
            tipo = 'capitulo' if s_enc.upper().lstrip().startswith('CAP') else 'titulo'
            base = ruta_anexo(ctx_anexo) + '/' if ctx_anexo is not None else ''
            et = (f'Anexo {ctx_anexo}, ' if ctx_anexo is not None else '') + f"{('Capítulo' if tipo == 'capitulo' else 'Título')} {ctx_capitulo}"
            padre = ruta_anexo(ctx_anexo) if ctx_anexo is not None else None
            pre_libro, et_libro = ('', '')
            if ctx_anexo is None and ctx_libro and (ctx_libro != libro_sin_prefijo):
                pre_libro, et_libro = (f'libro.{ctx_libro}/', f'{etiqueta_libro}, ')
                base, padre, et = (pre_libro, f'libro.{ctx_libro}', et_libro + et)
            if ctx_anexo is None and tipo == 'titulo':
                ctx_titulo = ctx_capitulo
            elif ctx_anexo is None and ctx_titulo:
                base, padre = (f'{pre_libro}titulo.{ctx_titulo}/', f'{pre_libro}titulo.{ctx_titulo}')
                et = f'{et_libro}Título {ctx_titulo}, Capítulo {ctx_capitulo}'
            ruta_division, etiqueta_division = (f'{base}{tipo}.{ctx_capitulo}', et)
            abrir(f'{base}{tipo}.{ctx_capitulo}', tipo, ctx_capitulo, et, (m.group(2) or '').strip() or None, pag, padre, s)
            continue
        m = RE_BOE['articulo'].match(s)
        en_letras = RE_ARTICULO_SANIDAD.match(s) if an.identificador == 'BOE-A-1986-10499' and (not m) else None
        num_letras = _numero_articulo_sanidad(en_letras.group(1)) if en_letras else None
        if (m or num_letras) and (not dentro_de_cita):
            num = num_letras or (sin_tilde(re.sub('\\s+', ' ', m.group(1).strip())).lower() if m.group(1).strip().lower().startswith(('ú', 'u')) else numeral_articulo(m.group(1)))
            base = ruta_anexo(ctx_anexo) + '/' if ctx_anexo is not None else ''
            et = f'Anexo {ctx_anexo}, artículo {num}' if ctx_anexo is not None else f'Artículo {num}'
            rubrica = (en_letras if num_letras else m).group(2).strip() or None
            abrir(f'{base}art.{num}', 'articulo', num, et, rubrica, pag, ruta_anexo(ctx_anexo) if ctx_anexo is not None else None, s)
            if re.match('^1\\.\\s', rubrica or ''):
                inicio_cuerpo = (en_letras if num_letras else m).start(2)
                actual.lineas = [s[:inicio_cuerpo].rstrip(), s[inicio_cuerpo:]]
                actual.titulo = None
            continue
        if an.identificador == 'BOE-A-1989-5084' and ctx_anexo is None and (not (citado or dentro_de_cita)) and (s in ('Primero.', 'Segundo.')):
            num = '1' if s == 'Primero.' else '2'
            abrir(f'ap.{num}', 'apartado', num, s.rstrip('.'), None, pag, None, s)
            continue
        pre_r, pre_e = ('reglamento/', 'Reglamento, d') if ctx_reglamento else ('', 'D')
        m = RE_BOE['disposicion_sin_ordinal'].match(s)
        if m:
            clase = m.group(1).lower()
            abrir(f'{pre_r}disp.{sin_tilde(clase)}.1', 'disposicion', '1', f'{pre_e}isposición {clase} única', m.group(2).strip() or None, pag, None, s)
            visto_disp_final = visto_disp_final or clase == 'final'
            continue
        m = RE_BOE['disposicion'].match(s)
        if m:
            clase, ordinal = (m.group(1).lower(), ordinal_a_numero(m.group(2)))
            r = f'{pre_r}disp.{sin_tilde(clase)}.{ordinal}'
            abrir(r, 'disposicion', ordinal, f'{pre_e}isposición {clase} {m.group(2).lower()}', m.group(3).strip() or None, pag, None, s)
            visto_disp_final = visto_disp_final or clase == 'final'
            continue
        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag
            if actual.tipo == 'disposicion':
                citas = max(0, citas + s.count('«') - s.count('»'))
    cerrar()
    an.preceptos = subdividir_anexo_sin_numeral(subdividir(preceptos, listas_interiores=pdf.ruta_relativa in DOCUMENTOS_CON_LISTAS_INTERIORES, boe=True))
    return an
RE_UE = {'articulo': re.compile(f'^\\s*Art[íi]culo\\s*(\\d+(?:\\s?{ORD_ARTICULO})?)(?:\\s+((?:[A-ZÁÉÍÓÚÑ]|\\d{{1,2}}\\.\\s+[A-ZÁÉÍÓÚÑ«\\"]).*))?\\s*$'), 'article_en': re.compile('^\\s*Article\\s+(\\d+[a-z]?)(?:\\s+([A-Z].*))?\\s*$'), 'anexo': re.compile(f'^\\s*(?:ANEXO|ANNEX)(?:\\s+({NUM_DIV}|[ÚU]NICO){RUBRICA})?\\s*$', re.I), 'capitulo': re.compile(f'^\\s*(?:CAP[ÍI]TULO|CHAPTER)\\s+(PRIMERO|{NUM_DIV}):?{RUBRICA}\\s*$', re.I), 'titulo_div': re.compile(f'^\\s*(?:T[ÍI]TULO|TITLE)\\s+({NUM_DIV}):?{RUBRICA}\\s*$', re.I)}
SECCION_UE = re.compile(f'^\\s*(?:SECCI[ÓO]N|SECTION)\\s+({NUM_DIV})\\s*[:.]?{RUBRICA}\\s*$')
CAB_CONSOLIDADA = re.compile('^\\s*0?(\\d{4})([A-Z])(\\d{4})\\s*[—-]\\s*([A-Z]{2})\\s*[—-]\\s*(\\d{2}\\.\\d{2}\\.\\d{4})', re.M)
RE_CABECERA_DOUE_PEGADA = re.compile('^(?:Official Journal of the European Union|Diario Oficial de la Uni[óo]n Europea)\\s+(?=(?:Art[íi]culo|Article)\\s+\\d)')
RE_FOLIO_DOUE = re.compile('^\\s*(?:[LC]\\s+\\d{1,4}/\\d{1,4}|\\d{1,2}\\.\\d{1,2}\\.\\d{4}|[A-Z]{2})\\s*$')
RE_FORMULA_FINAL = re.compile('^\\s*(?:Hecho\\s+en|Done\\s+at)\\s+[^\\d,]{2,40},\\s*(?:el\\s+)?\\d{1,2}(?:\\.?\\s?[ºo°])?\\s+(?:de\\s+)?[A-Za-zÁÉÍÓÚáéíóúñ]+\\s+(?:de\\s+)?\\d{4}\\b')
RE_CAB_UE_CON_FOLIO = re.compile('^\\s*\\d{4,5}[A-Z]\\d{4}\\s*[—-]\\s*[A-Z]{2}\\s*[—-]\\s*\\d{2}\\.\\d{2}\\.\\d{4}\\s*[—-]\\s*\\d{3}\\.\\d{3}\\s*[—-]\\s*\\d+\\b[^\\S\\n]*')

def _conservar_restos_de_cabecera_ue(pdf: TextoPdf) -> TextoPdf:
    """Public CI documentation."""
    paginas = ['\n'.join((RE_CAB_UE_CON_FOLIO.sub('', ln) for ln in p.split('\n'))) for p in pdf.paginas]
    return replace(pdf, paginas=paginas)

def _reubicar_rotulos_sueltos_ue(lp: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Public CI documentation."""

    def limpia(ln):
        return MARCA_INLINE.sub('', MARCA_RESTO.sub('', ln)).strip()

    def rotulos(s):
        return re.findall('([a-zñ])\\)', s) if re.fullmatch('(?:[a-zñ]\\)\\s*)+', s) else []
    salida = list(lp)
    en_articulo = False
    en_anexo = False
    k = 0
    alfabeto = 'abcdefghijklmnñopqrstuvwxyz'
    while k < len(lp):
        s = limpia(lp[k][0])
        if not en_anexo and (RE_UE['articulo'].match(s) or RE_UE['article_en'].match(s)):
            en_articulo = True
        elif RE_UE['anexo'].match(s):
            en_articulo = False
            en_anexo = True
        prefijo = re.fullmatch('(\\d{1,3}\\.\\s*)((?:[a-zñ]\\)\\s*){2,})', s)
        letras = rotulos(prefijo[2] if prefijo else s) if en_articulo else []
        if not letras:
            k += 1
            continue
        indices = [k]
        j = k + 1
        while j < len(lp):
            sig = limpia(lp[j][0])
            nuevas = rotulos(sig)
            if nuevas:
                letras.extend(nuevas)
                indices.append(j)
            elif sig:
                break
            j += 1
        serie = ''.join(letras)
        if len(letras) < 2 or serie not in alfabeto:
            k = j
            continue
        introduccion = None
        if prefijo:
            if j >= len(lp) or not limpia(lp[j][0]).endswith(':') or lp[j][1] != lp[k][1]:
                k = j
                continue
            introduccion = j
            j += 1
        cuerpos = []
        for n in range(j, min(len(lp), j + 2 * len(letras) + 8)):
            t = limpia(lp[n][0])
            if not t:
                continue
            if re.match('^(?:Art[íi]culo|Article|ANEXO|ANNEX|CAP[ÍI]TULO|CHAPTER|\\d+[.)]|[a-zñ]+\\)|[—–])', t) or RE_FORMULA_FINAL.match(t):
                break
            cuerpos.append(n)
            if len(cuerpos) == len(letras):
                break
            if not RE_CIERRA_FRASE.search(t):
                break
        if len(cuerpos) != len(letras):
            k = j
            continue
        for n in indices:
            ln, pag = salida[n]
            salida[n] = (re.sub('[a-zñ]\\)\\s*', '', ln).rstrip(), pag)
        if introduccion is not None:
            ln, pag = salida[k]
            salida[k] = (re.sub('\\d{1,3}\\.\\s*$', '', ln).rstrip(), pag)
            ln, pag = salida[introduccion]
            salida[introduccion] = (prefijo[1].strip() + ' ' + ln, pag)
        for letra, n in zip(letras, cuerpos):
            ln, pag = salida[n]
            salida[n] = (letra + ') ' + ln, pag)
        k = cuerpos[-1] + 1
    return salida

def _anexo_tras_correspondencias(s: str, lp: list[tuple[str, int]], k: int) -> bool:
    """Public CI documentation."""
    if not re.match('^(?:ANEXO|ANNEX)\\b', s):
        return False
    m = RE_UE['anexo'].match(s)
    if not m:
        return False
    rubrica = (m.group(2) or '').strip()
    if not rubrica:
        for ln, _ in lp[k + 1:]:
            t = MARCA_INLINE.sub('', MARCA_RESTO.sub('', ln)).strip()
            if not t or any((rx.match(t) for rx in RUIDO)):
                continue
            rubrica = t
            break
    return bool(re.match('^[A-ZÁÉÍÓÚÑ]', rubrica) and (not re.match('^(?:Anexos?|Annex(?:es)?|Art[íi]culos?|Articles?|Reglamento|Regulation|Directiva|Directive|Presente)\\b', rubrica, re.I)))

def analizar_eurlex(pdf: TextoPdf) -> Analisis:
    from . import estructura_r3b
    correccion_r3b = estructura_r3b.de_pdf(pdf)
    an = Analisis()
    todo = pdf.texto
    m = CAB_CONSOLIDADA.search(todo)
    if m:
        anio, letra, num, idioma, fecha = m.groups()
        an.identificador = f'CELEX-3{anio}{letra}{num}'
        an.es_consolidada = True
        d, mo, y = fecha.split('.')
        an.fecha_consolidacion = f'{y}-{mo}-{d}'
        an.cabecera = m.group(0).strip()
        an.idioma = idioma.lower()
    else:
        m2 = re.search('^\\s*(?:C/)?(\\d{4})/(\\d+)\\s*$', todo[:4000], re.M)
        if m2:
            an.identificador = f'DOUE-{m2.group(1)}-{m2.group(2)}'
        an.cabecera = todo[:120].replace('\n', ' ').strip()
    if re.search('\\bEN L series\\b|Official Journal', todo[:3000]):
        an.idioma = 'en'
    lp = _reubicar_rotulos_sueltos_ue(lineas_con_pagina(_conservar_restos_de_cabecera_ue(pdf)))
    preceptos: list[Precepto] = []
    actual: Precepto | None = Precepto(ruta='preambulo', tipo='preambulo', numero=None, etiqueta='Preámbulo', titulo=None, pagina_inicio=1, pagina_fin=1)
    ctx_anexo: str | None = None
    marca_actual: str | None = None
    n_articulos = 0
    n_formulas = 0

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None

    def abrir(ruta, tipo, numero, etiqueta, titulo, pagina, padre, encabezado=None):
        nonlocal actual
        cerrar()
        actual = Precepto(ruta=ruta, tipo=tipo, numero=numero, etiqueta=etiqueta, titulo=titulo, pagina_inicio=pagina, pagina_fin=pagina, padre=padre, marca=marca_actual)
        if encabezado:
            actual.lineas.append(encabezado)
    esperando_titulo: Precepto | None = None
    en_tabla_corresp = False
    seccion_en_anexo: str | None = None
    capitulo_en_anexo: str | None = None
    nivel_de_arriba: str | None = None
    titulo_en_curso: str | None = None
    for k, (ln, pag) in enumerate(lp):
        s = ln.strip()
        mb = MARCA_BLOQUE.match(s)
        if mb:
            marca_actual = mb.group(1)
            continue
        mi = MARCA_INICIO.match(s)
        if mi:
            marca_actual = mi.group(1)
            s = s[mi.end():].strip()
            if not s:
                continue
        if '►' in s or '◄' in s:
            s = MARCA_INLINE.sub('', s).replace('►', '').strip()
        if MARCA_RESTO.search(s):
            resto = MARCA_RESTO.findall(s)
            if resto:
                marca_actual = resto[-1]
            s = MARCA_RESTO.sub(' ', s).strip()
            s = re.sub('\\s{2,}', ' ', s)
        s = RE_CABECERA_DOUE_PEGADA.sub('', s)
        encabezado_literal = s
        s = re.sub('^_{3,}\\s*(?=Art[íi]culo\\s*\\d)', '', s)
        if not s:
            if actual:
                actual.lineas.append('')
            continue
        if not en_tabla_corresp and actual is not None and (actual.tipo == 'anexo') and (not any((ln.strip() for ln in actual.lineas[1:]))) and (RX_TABLA_CORRESP.search(s) or (correccion_r3b == 'CELEX-32011R0010' and estructura_r3b.TABLA.search(s))):
            en_tabla_corresp = True
        if en_tabla_corresp and _anexo_tras_correspondencias(s, lp, k):
            en_tabla_corresp = False
        if en_tabla_corresp:
            if actual:
                if not actual.lineas:
                    actual.pagina_inicio = pag
                actual.lineas.append(s)
                actual.pagina_fin = pag
            continue
        if actual is not None and actual.tipo != 'preambulo' and RE_FORMULA_FINAL.match(s):
            n_formulas += 1
            abrir('formula_final' if n_formulas == 1 else f'formula_final.{n_formulas}', 'formula_final', None, 'Fórmula final' if n_formulas == 1 else f'Fórmula final ({n_formulas})', None, pag, None, s)
            esperando_titulo = None
            continue
        m = RE_UE['anexo'].match(s)
        if correccion_r3b == 'CELEX-32019R2144' and (not s.startswith('ANEXO ')):
            m = None
        m_tc = None if m else RE_ANEXO_TABLA_CORRESP.match(s)
        if not m and (not m_tc) and (correccion_r3b == 'CELEX-32007L0045'):
            m_tc = estructura_r3b.ANEXO_SIN_NUMERAL.match(s)
        if m or m_tc:
            ctx_anexo = numeral_division((m.group(1) or '').upper()) if m else ''
            seccion_en_anexo = capitulo_en_anexo = nivel_de_arriba = None
            titulo_en_curso = None
            ruta_ax = ruta_anexo(ctx_anexo or None)
            abrir(ruta_ax, 'anexo', ctx_anexo or None, f'Anexo {ctx_anexo}'.strip(), ((m.group(2) or '').strip() if m else m_tc.group(1)) or None, pag, None, s)
            esperando_titulo = None
            if RX_TABLA_CORRESP.search(s):
                en_tabla_corresp = True
            continue
        m = RE_UE['articulo'].match(s) or RE_UE['article_en'].match(s)
        if m:
            num = numeral_articulo(m.group(1))
            n_articulos += 1
            rubrica = (m.group(2) or '').strip() or None
            cuerpo_inline = bool(rubrica and re.match('^\\d{1,2}\\.\\s', rubrica))
            lineas_articulo = [encabezado_literal]
            if cuerpo_inline:
                inicio_cuerpo = len(encabezado_literal) - len(rubrica)
                lineas_articulo = [encabezado_literal[:inicio_cuerpo].rstrip(), rubrica]
                rubrica = None
            if rubrica:
                corte = re.search('\\s(?=\\d{1,2}\\.\\s+[A-ZÁÉÍÓÚa-z])', rubrica)
                if corte:
                    rubrica = rubrica[:corte.start()].strip() or None
            p = Precepto(ruta=f'art.{num}', tipo='articulo', numero=num, etiqueta=f'Artículo {num}', titulo=rubrica, lineas=lineas_articulo, pagina_inicio=pag, pagina_fin=pag, marca=marca_actual)
            cerrar()
            actual = p
            esperando_titulo = None if rubrica or cuerpo_inline else p
            continue
        m = SECCION_UE.match(s) if ctx_anexo is not None else None
        if m:
            num_sec = numeral_division(m.group(1))
            nivel_de_arriba = nivel_de_arriba or 'seccion'
            padre = ruta_anexo(ctx_anexo or None)
            et = f'Anexo {ctx_anexo}'.strip()
            if nivel_de_arriba == 'capitulo' and capitulo_en_anexo:
                padre += f'/capitulo.{capitulo_en_anexo}'
                et += f', Capítulo {capitulo_en_anexo}'
            else:
                seccion_en_anexo, capitulo_en_anexo = (num_sec, None)
            abrir(f'{padre}/seccion.{num_sec}', 'seccion', num_sec, f'{et}, Sección {num_sec}', (m.group(2) or '').strip() or None, pag, padre, s)
            esperando_titulo = None
            continue
        m = RE_UE['capitulo'].match(s) or RE_UE['titulo_div'].match(s)
        if m:
            num_div = numeral_division(m.group(1))
            if sin_tilde(num_div).upper() == 'PRIMERO':
                num_div = 'I'
            tipo = 'capitulo' if sin_tilde(s.upper()).lstrip().startswith(('CAP', 'CHA')) else 'titulo'
            base = ruta_anexo(ctx_anexo) + '/' if ctx_anexo is not None else ''
            et = (f'Anexo {ctx_anexo}, ' if ctx_anexo is not None else '') + f"{('Capítulo' if tipo == 'capitulo' else 'Título')} {num_div}"
            padre = ruta_anexo(ctx_anexo) if ctx_anexo is not None else None
            if ctx_anexo is None and tipo == 'titulo':
                titulo_en_curso = num_div
            elif ctx_anexo is None and titulo_en_curso:
                base, padre = (f'titulo.{titulo_en_curso}/', f'titulo.{titulo_en_curso}')
                et = f'Título {titulo_en_curso}, Capítulo {num_div}'
            if ctx_anexo is not None and tipo == 'capitulo':
                nivel_de_arriba = nivel_de_arriba or 'capitulo'
                if nivel_de_arriba == 'seccion' and seccion_en_anexo:
                    padre = f'{ruta_anexo(ctx_anexo)}/seccion.{seccion_en_anexo}'
                    base = padre + '/'
                    et = f'Anexo {ctx_anexo}, Sección {seccion_en_anexo}, Capítulo {num_div}'
                else:
                    capitulo_en_anexo = num_div
            abrir(f'{base}{tipo}.{num_div}', tipo, num_div, et, (m.group(2) or '').strip() or None, pag, padre, s)
            esperando_titulo = None
            continue
        if esperando_titulo is not None:
            if RE_FOLIO_DOUE.match(s):
                esperando_titulo.lineas.append(s)
                esperando_titulo.pagina_fin = pag
                continue
            if len(s) < 200 and (not re.match('^\\d+\\.', s)):
                esperando_titulo.titulo = s
                esperando_titulo.lineas.append(s)
                esperando_titulo = None
                continue
            esperando_titulo = None
        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag
    cerrar()
    definiciones = {'CELEX-32012R1025': 'art.2', 'CELEX-32017R0745': 'art.2', 'CELEX-32017R0746': 'art.2', 'CELEX-32016R0679': 'art.4', 'CELEX-32018L1972': 'art.2'}
    an.preceptos = subdividir(quedarse_con_el_cuerpo(preceptos), definiciones=frozenset({definiciones[an.identificador]}) if an.identificador in definiciones else frozenset(), letras_con_huecos=frozenset({'art.2'}) if an.identificador == 'CELEX-32002L0058' else frozenset(), numeracion_modificativa=an.identificador == 'CELEX-32017R0625')
    return an
PALABRAS_DE_ENLACE = frozenset({'y', 'e', 'o', 'u', 'ni', 'de', 'del', 'la', 'el', 'los', 'las', 'en', 'a', 'al', 'con', 'por', 'para', 'and', 'or', 'of', 'to', 'in', 'the', 'for', 'with', 'on', 'at', 'by', 'nor'})

def sigue_una_frase(p: Precepto) -> bool:
    """Public CI documentation."""
    palabras = p.texto.split(None, 2)
    return len(palabras) > 1 and palabras[1].strip(',.;:') in PALABRAS_DE_ENLACE

def _sumar(destino: Precepto, p: Precepto, delante: bool=False) -> None:
    """Public CI documentation."""
    destino.lineas = p.lineas + destino.lineas if delante else destino.lineas + p.lineas
    destino.pagina_inicio = min(destino.pagina_inicio, p.pagina_inicio)
    destino.pagina_fin = max(destino.pagina_fin, p.pagina_fin)

def quedarse_con_el_cuerpo(preceptos: list[Precepto], tipos: tuple[str, ...]=('articulo',), paginas_de_indice: frozenset=frozenset(), paginas_de_entradas: frozenset=frozenset()) -> list[Precepto]:
    """Public CI documentation."""
    from collections import defaultdict
    en_anexo, del_articulado = (False, {})
    for p in preceptos:
        if p.tipo in ('anexo', 'apendice'):
            en_anexo = True
        del_articulado[id(p)] = not en_anexo
    por_ruta: dict[str, list] = defaultdict(list)
    for k, p in enumerate(preceptos):
        if p.tipo in tipos:
            por_ruta[p.ruta].append((k, p))

    def preferencia(kp):
        k, p = kp
        if p.tipo == 'articulo':
            return (del_articulado[id(p)], True, True, True, len(p.texto), -k)
        if p.tipo == 'apartado':
            return (True, not p.de_indice and p.pagina_inicio not in paginas_de_indice, del_articulado[id(p)], not sigue_una_frase(p), len(p.texto), -k)
        return (True, True, True, True, len(p.texto), -k)
    ganan = {id(max(l, key=preferencia)[1]) for l in por_ruta.values()}
    salida: list[Precepto] = []
    sin_sitio: list[Precepto] = []
    for p in preceptos:
        if p.tipo in tipos and id(p) not in ganan:
            if salida:
                _sumar(salida[-1], p)
            else:
                sin_sitio.append(p)
            continue
        for q in reversed(sin_sitio):
            _sumar(p, q, delante=True)
        sin_sitio = []
        salida.append(p)
    if paginas_de_indice or paginas_de_entradas:
        _pagina_del_cuerpo(por_ruta, ganan, preferencia, paginas_de_indice | paginas_de_entradas)
    return salida

def _pagina_del_cuerpo(por_ruta: dict[str, list], ganan: set, preferencia, paginas_del_indice) -> None:
    """Public CI documentation."""

    def de_indice(p: Precepto) -> bool:
        return p.de_indice or (p.pagina_inicio in paginas_del_indice and p.pagina_fin in paginas_del_indice)
    for lista in por_ruta.values():
        if len(lista) < 2:
            continue
        gana = [p for _, p in lista if id(p) in ganan]
        if not gana or not de_indice(gana[0]):
            continue
        cuerpo = [kp for kp in lista if id(kp[1]) not in ganan and (not de_indice(kp[1]))]
        if cuerpo:
            b = max(cuerpo, key=preferencia)[1]
            gana[0].pagina_inicio, gana[0].pagina_fin = (b.pagina_inicio, b.pagina_fin)
            if b.titulo and gana[0].titulo and (gana[0].titulo != b.titulo):
                m_pag = re.search('\\s+(\\d{1,3})$', gana[0].titulo)
                if m_pag and gana[0].titulo[:m_pag.start()].strip() == b.titulo.strip():
                    gana[0].titulo = b.titulo
                    gana[0].lineas = [re.sub('\\s+' + m_pag.group(1) + '$', '', ln) for ln in gana[0].lineas]

def sin_rutas_repetidas(preceptos: list[Precepto]) -> list[Precepto]:
    """Public CI documentation."""
    vistas: set[str] = set()
    salida: list[Precepto] = []
    for p in preceptos:
        if p.ruta not in vistas:
            vistas.add(p.ruta)
            salida.append(p)
            continue
        mio = ' '.join(p.texto.split())
        if any((mio in ' '.join(q.texto.split()) for q in salida)):
            continue
        if salida:
            _sumar(salida[-1], p)
    return salida
_RE_GUIA_AP_BASE = re.compile('^\\s*(\\d+(?:\\.\\d+){0,3})\\.?\\s+(\\[?[^\\W\\d].*)$')
RE_GUIA_AP_COMA = re.compile('^\\s*(\\d+(?:\\.\\d+){2,3}),\\s+([A-ZÁÉÍÓÚÑ].*)$')
RE_GUIA_AP_CODIGO = re.compile('^\\s*(\\d+(?:\\.\\d+){1,3})\\.?(\\[[A-Z][A-Za-z0-9\\-]*\\]\\s*[^\\W\\d].*)$')

class _CabeceraDeGuia:
    """Public CI documentation."""

    def __init__(self, *expresiones):
        self._expresiones = expresiones

    def match(self, s, *args):
        for e in self._expresiones:
            m = e.match(s, *args)
            if m:
                return m
        return None
RE_GUIA_AP = _CabeceraDeGuia(_RE_GUIA_AP_BASE, RE_GUIA_AP_COMA, RE_GUIA_AP_CODIGO)
RE_GUIA_AP_ANTIGUO = re.compile('^\\s*(\\d+(?:\\.\\d+){1,3})\\.?\\s*(?:\\(\\d[^()]{0,24}\\)\\s*)+([^\\W\\d].*)$')
RE_GUIA_AP_SOLO = re.compile('^\\s*(\\d+(?:\\.\\d+){1,3})\\.?\\s*(?:\\(\\d[^()]{0,24}\\)\\s*)*$')
RE_NOTA_DEL_TRADUCTOR = re.compile('N\\.\\s*del\\s*T\\.')
LINEAS_DE_PIE = 3
PALABRAS_DE_NOTA = 8
PAGINAS_DE_NOTA = 5
RE_MES = re.compile('(?i:enero|febrero|marzo|abril|mayo|junio|julio|agosto|se?ptiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\\b')
RE_GUIA_TABLA = re.compile('^\\s*(?:Tabla|Table)\\s+(\\d+)\\b\\s*\\.?\\s*(.*)$', re.I)
RE_GUIA_DIV = re.compile('^\\s*(?P<clase>ANNEX|Annex|ANEXO|Anexo|APPENDIX|Appendix|AP[ÉE]NDICE|Ap[ée]ndice|CHAPTER|Chapter|CAP[ÍI]TULO|Cap[íi]tulo)\\s+(?P<num>[IVXLC]+|\\d+|[A-Z]{1,2})\\s*[*∗]?(?:\\s*(?P<sep>[.:—–-])(?:\\s*(?P<rub>[A-ZÁÉÍÓÚÑ].*)|\\s*(?P<minsep>[a-záéíóúñ].*))?|\\s+(?P<rub2>[A-ZÁÉÍÓÚÑ(].*)|\\s+(?P<min>[a-záéíóúñ].*))?\\s*$')
SEPARADORES_DE_RUBRICA = (':', '—', '–', '-')
LINEAS_DE_CABECERA = 3
RE_PUNTOS_DE_INDICE = re.compile('(?:\\.\\s*){4,}\\d*')
LINEAS_DE_INDICE = 3
RE_RUBRICA_CON_PAGINA = re.compile('(?<![:\\-])\\s\\.?\\s*(?:\\d{1,3}|[ivxlc]+)\\s*$', re.I)
TIPO_DIV_GUIA = {'ANNEX': 'anexo', 'ANEXO': 'anexo', 'APPENDIX': 'apendice', 'APENDICE': 'apendice', 'APÉNDICE': 'apendice', 'CHAPTER': 'capitulo', 'CAPITULO': 'capitulo', 'CAPÍTULO': 'capitulo'}
SEGMENTO_DIV_GUIA = {'anexo': 'anexo', 'apendice': 'apend', 'capitulo': 'capitulo'}
ETIQUETA_DIV_GUIA = {'anexo': 'Anexo', 'apendice': 'Apéndice', 'capitulo': 'Capítulo'}

def division_de_guia(s: str, posicion: int, pagina_de_indice: bool):
    """Public CI documentation."""
    if pagina_de_indice:
        return None
    m = RE_GUIA_DIV.match(s)
    if not m:
        return None
    if m.group('minsep') and m.group('sep') not in SEPARADORES_DE_RUBRICA:
        return None
    rubrica = (m.group('rub') or m.group('rub2') or m.group('min') or m.group('minsep') or '').strip()
    if rubrica and RE_RUBRICA_CON_PAGINA.search(rubrica):
        return None
    if rubrica and RE_PUNTOS_SIN_PAGINA.search(rubrica):
        return None
    arriba = posicion < LINEAS_DE_CABECERA
    en_mayusculas = bool(rubrica) and (not any((c.islower() for c in rubrica)))
    a_media = m.group('sep') in (':', '—', '–') and en_mayusculas
    if not (arriba or a_media or encabezado_en_mayusculas(m, rubrica)):
        return None
    tipo = TIPO_DIV_GUIA[m.group('clase').upper()]
    return (tipo, m.group('num'), rubrica or None, bool(arriba and a_media))
RE_NOMBRA_DIVISION = re.compile('\\b(?:ANNEX|ANEXO|APPENDIX|AP[ÉE]NDICE|CHAPTER|CAP[ÍI]TULO)\\s+(?:[IVXLC]+|\\d+|[A-Z])\\b', re.I)

def encabezado_en_mayusculas(m: re.Match, rubrica: str) -> bool:
    """Public CI documentation."""
    return bool(m.group('rub2')) and m.group('sep') is None and m.group('clase').isupper() and (not any((c.islower() for c in rubrica))) and (len(rubrica.split()) >= 2) and (not RE_NOMBRA_DIVISION.search(rubrica))

def sistema_de(num: str) -> str:
    """Public CI documentation."""
    if num.isdigit():
        return 'arabigo'
    if len(num) == 1 and num != 'I':
        return 'letra'
    return 'romano'

def valor_de_numeral(num: str, sistema: str) -> int | None:
    """Public CI documentation."""
    if sistema == 'arabigo':
        return int(num) if num.isdigit() else None
    if sistema == 'letra':
        if len(num) == 1 and num.isalpha():
            return ord(num) - ord('A') + 1
        if len(num) == 2 and num.isalpha():
            return (ord(num[0]) - ord('A') + 1) * 26 + (ord(num[1]) - ord('A') + 1)
        return None
    if not num or any((c not in 'IVXLC' for c in num)):
        return None
    romanos = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total = 0
    for a, b in zip(num, num[1:] + ' '):
        v = romanos[a]
        total += -v if romanos.get(b, 0) > v else v
    return total
SISTEMA_DEL_PRIMERO = {'1': 'arabigo', 'A': 'letra', 'I': 'romano'}

def analizar_guia(pdf: TextoPdf, *, legado: bool=False) -> Analisis:
    """Public CI documentation."""
    an = Analisis()
    lineas_p1 = [l.strip() for l in (pdf.paginas[0] if pdf.paginas else '').split('\n') if l.strip()]
    an.titulo = lineas_p1[0] if lineas_p1 else None
    an.cabecera = ' '.join(lineas_p1[:3])[:200]
    lp, paginas_de_indice = _lineas_de_guia(pdf)
    if legado:
        return _analizar_guia_con(an, lp, paginas_de_indice, pdf, partir=False, rutas_de_hoy=frozenset())
    de_hoy = frozenset((p.ruta for p in _analizar_guia_con(Analisis(), lp, paginas_de_indice, pdf, partir=False, rutas_de_hoy=frozenset()).preceptos))
    an = _analizar_guia_con(an, lp, paginas_de_indice, pdf, partir=True, rutas_de_hoy=de_hoy)
    from . import catalogo, requisitos_welmec
    if (pdf.ruta_relativa or '') in catalogo.GUIAS_CON_BLOQUES_DE_REQUISITO:
        an.preceptos = requisitos_welmec.partir_en_requisitos(an.preceptos, lp, Precepto)
    if catalogo.DOCUMENTOS_CON_ADAPTADOR_SINGULAR.get(pdf.ruta_relativa or '') == 'iso_27001_controles_anexo_a':
        an.preceptos = _partir_controles_iso_27001(pdf, an.preceptos, lp, paginas_de_indice)
    an.preceptos = _quitar_contraportada_bsi(an.preceptos, lp)
    return an
MARCAS_DE_CONTRAPORTADA_BSI = ('NO COPYING WITHOUT BSI PERMISSION', 'British Standards Institution (BSI)')

def _quitar_contraportada_bsi(preceptos: list[Precepto], lp: list[tuple[str, int]]) -> list[Precepto]:
    """Public CI documentation."""
    if not preceptos:
        return preceptos
    ultimo = preceptos[-1]
    idx_bsi = None
    for i, ln in enumerate(ultimo.lineas):
        if any((marca in ln for marca in MARCAS_DE_CONTRAPORTADA_BSI)):
            idx_bsi = i
            break
    if idx_bsi is None:
        return preceptos
    ultimo.lineas = ultimo.lineas[:idx_bsi]
    while ultimo.lineas and (not ultimo.lineas[-1].strip()):
        ultimo.lineas.pop()
    marca_k = next((k for k, (ln, pag) in enumerate(lp) if pag >= ultimo.pagina_inicio and any((marca in ln for marca in MARCAS_DE_CONTRAPORTADA_BSI))), None)
    if marca_k is not None:
        k = marca_k - 1
        while k >= 0 and (not lp[k][0].strip()):
            k -= 1
        if k >= 0:
            ultimo.pagina_fin = max(ultimo.pagina_inicio, lp[k][1])
    return preceptos
CONTROLES_ISO_27001 = tuple([f'5.{i}' for i in range(1, 38)] + [f'6.{i}' for i in range(1, 9)] + [f'7.{i}' for i in range(1, 15)] + [f'8.{i}' for i in range(1, 35)])
RE_CONTROL_ISO_27001 = re.compile('[5-8]\\.\\d{1,2}')
RE_GRUPO_ISO_27001 = re.compile('[5-8]')

def _partir_controles_iso_27001(pdf: TextoPdf, preceptos_cuerpo: list[Precepto], lp: list[tuple[str, int]], paginas_de_indice: set[int]) -> list[Precepto]:
    """Public CI documentation."""
    from . import tablas
    annex_a_idx = next((k for k, (ln, pag) in enumerate(lp) if pag not in paginas_de_indice and (not RE_PUNTOS_DE_INDICE.search(ln)) and ln.strip().startswith('Annex A')))
    bib_idx = next((k for k, (ln, pag) in enumerate(lp) if k > annex_a_idx and pag not in paginas_de_indice and (not RE_PUNTOS_DE_INDICE.search(ln)) and ln.strip().startswith('Bibliography')))
    annex_a_pag = lp[annex_a_idx][1]
    body_precepts = [p for p in preceptos_cuerpo if p.pagina_inicio < annex_a_pag]
    re_ctrl_in = re.compile('(?:^|(?<=\\s))(5\\.(?:[1-9]|[12]\\d|3[0-7])|6\\.[1-8]|7\\.(?:[1-9]|1[0-4])|8\\.(?:[1-9]|[12]\\d|3[0-4]))(?=\\s|$)')
    primero = next(((k, m.start(1)) for k in range(annex_a_idx, bib_idx) for m in re_ctrl_in.finditer(lp[k][0])), None)
    if primero is None:
        raise ExtraccionError('ISO/IEC 27001: no se encuentra el primer control de la Tabla A.1 en el anexo A')
    first_ctrl_k, first_ctrl_pos = primero
    annex_lines = [lp[k][0] for k in range(annex_a_idx, first_ctrl_k)]
    if first_ctrl_pos > 0:
        annex_lines.append(lp[first_ctrl_k][0][:first_ctrl_pos])
    p_annex_A = Precepto(ruta='anexo.A', tipo='anexo', numero='A', etiqueta='Anexo A', titulo='(normative) Information security controls reference', lineas=annex_lines, pagina_inicio=lp[annex_a_idx][1], pagina_fin=lp[first_ctrl_k][1], padre=None)
    controles: list[dict] = []
    grupo: str | None = None
    for pagina, fila in tablas.filas_de_las_tablas(pdf.ruta_relativa, pdf.paginas, annex_a_pag, lp[bib_idx][1]):
        celdas = [c.strip() for c in fila]
        primera = celdas[0] if celdas else ''
        resto = [c for c in celdas[1:] if c]
        if RE_CONTROL_ISO_27001.fullmatch(primera):
            controles.append(dict(numero=primera, titulo=celdas[1] if len(celdas) > 1 else '', texto=' '.join(celdas[2:]).strip(), grupo=grupo, pagina_inicio=pagina, pagina_fin=pagina))
            grupo = None
        elif RE_GRUPO_ISO_27001.fullmatch(primera) and len(resto) == 1:
            if controles:
                grupo = f'{primera} {resto[0]}'
        elif not primera and resto and controles:
            controles[-1]['texto'] = (controles[-1]['texto'] + ' ' + ' '.join(resto)).strip()
            controles[-1]['pagina_fin'] = pagina
        elif any(celdas):
            raise ExtraccionError(f'ISO/IEC 27001: fila de la Tabla A.1 que no se reconoce (p. {pagina}): {celdas[:3]}')
    if tuple((c['numero'] for c in controles)) != CONTROLES_ISO_27001:
        raise ExtraccionError(f'ISO/IEC 27001: la Tabla A.1 da {len(controles)} controles y no los {len(CONTROLES_ISO_27001)} esperados, en orden')
    ctrl_precepts = []
    for c in controles:
        num = c['numero']
        lineas = ([c['grupo']] if c['grupo'] else []) + [f"{num} {c['titulo']}".strip(), c['texto']]
        ctrl_precepts.append(Precepto(ruta=f'anexo.A/ap.{num}', tipo='apartado', numero=num, etiqueta=f'Anexo A, apartado {num}', titulo=c['titulo'] or None, lineas=lineas, pagina_inicio=c['pagina_inicio'], pagina_fin=c['pagina_fin'], padre='anexo.A'))
    return body_precepts + [p_annex_A] + ctrl_precepts

def _analizar_guia_con(an: Analisis, lp, paginas_de_indice, pdf, *, partir: bool, rutas_de_hoy: frozenset) -> Analisis:
    """Public CI documentation."""
    preceptos, repetidas = _trocear_guia(lp, paginas_de_indice, frozenset(), partir=partir, cadena=partir, rutas_de_hoy=rutas_de_hoy)
    if repetidas:
        preceptos, _ = _trocear_guia(lp, paginas_de_indice, frozenset(repetidas), partir=partir, cadena=partir, rutas_de_hoy=rutas_de_hoy)
    sin_rotulo = frozenset({p.pagina_inicio for p in preceptos if p.de_indice} - set(paginas_de_indice))
    if sin_rotulo:
        otra, repetidas = _trocear_guia(lp, paginas_de_indice, frozenset(), sin_rotulo, partir=partir, cadena=partir, rutas_de_hoy=rutas_de_hoy)
        if repetidas:
            otra, _ = _trocear_guia(lp, paginas_de_indice, frozenset(repetidas), sin_rotulo, partir=partir, cadena=partir, rutas_de_hoy=rutas_de_hoy)
        if {p.ruta for p in otra} >= {p.ruta for p in preceptos if p.pagina_inicio not in sin_rotulo}:
            preceptos = otra
    an.preceptos = quedarse_con_el_cuerpo(preceptos, ('apartado', 'tabla', 'anexo', 'apendice', 'capitulo'), frozenset(paginas_de_indice | _paginas_de_indice_alfabetico(lp) | sin_rotulo), frozenset(paginas_con_indice(paginas_vivas(pdf))))
    return an
RE_ROTULO_ALFABETICO = re.compile('^\\s*(?:[ÍI]NDICE\\s+ALFAB[ÉE]TICO|ALPHABETICAL\\s+INDEX|INDEX(?:\\s+ALPHAB[ÉE]TIQUE)?)\\s*$', re.I)
RE_LETRA_DE_INDICE = re.compile('^\\s*[A-ZÁÉÍÓÚÑ]\\s*$')
LETRAS_DE_INDICE = 2

def _paginas_de_indice_alfabetico(lp: list[tuple[str, int]]) -> set[int]:
    primeras: dict[int, list[str]] = {}
    for ln, pag in lp:
        if ln.strip() and len(primeras.setdefault(pag, [])) < LINEAS_DE_CABECERA:
            primeras[pag].append(ln.strip())
    paginas = {pag for pag, ls in primeras.items() if any((RE_ROTULO_ALFABETICO.match(x) for x in ls))}
    letras: dict[int, int] = {}
    for ln, pag in lp:
        if RE_LETRA_DE_INDICE.match(ln):
            letras[pag] = letras.get(pag, 0) + 1
    for pag in sorted(letras):
        if pag - 1 in paginas and letras[pag] >= LETRAS_DE_INDICE:
            paginas.add(pag)
    return paginas

def _lineas_de_guia(pdf: TextoPdf) -> tuple[list[tuple[str, int]], set[int]]:
    """Public CI documentation."""
    lp = lineas_con_pagina(pdf)
    primeras: dict[int, list[str]] = {}
    for ln, pag in lp:
        if ln.strip() and len(primeras.setdefault(pag, [])) < LINEAS_DE_CABECERA:
            primeras[pag].append(ln.strip())
    paginas_de_indice = {pag for pag, ls in primeras.items() if any((RE_ROTULO_INDICE.match(x) for x in ls))}
    con_puntos: dict[int, int] = {}
    for ln, pag in lp:
        if RE_PUNTOS_DE_INDICE.search(ln):
            con_puntos[pag] = con_puntos.get(pag, 0) + 1
    for pag in sorted(paginas_de_indice):
        siguiente = pag + 1
        while con_puntos.get(siguiente, 0) >= LINEAS_DE_INDICE:
            paginas_de_indice.add(siguiente)
            siguiente += 1
    lp = _partir_definiciones_en_linea(lp, paginas_de_indice)
    return (lp, paginas_de_indice)
RE_CAP_TERMINOS = re.compile('^\\s*(?:[1-9]\\d*|[IVXLC]+)?\\.?\\s*(?:terms\\s+and\\s+definitions|t[ée]rminos\\s+y\\s+definiciones|terms,\\s+definitions)\\b', re.I)

def _partir_definiciones_en_linea(lp: list[tuple[str, int]], paginas_de_indice: set[int]) -> list[tuple[str, int]]:
    """Public CI documentation."""
    cap_idx = None
    cap_num = None
    for k, (ln, pag) in enumerate(lp):
        if pag in paginas_de_indice:
            continue
        m = RE_CAP_TERMINOS.match(ln)
        if m:
            cap_idx = k
            m_num = re.match('^\\s*([1-9]\\d*|[IVXLC]+)', ln)
            cap_num = m_num.group(1) if m_num else '3'
            break
    if cap_idx is None:
        return lp
    siguiente_cap = len(lp)
    next_num = str(int(cap_num) + 1) if cap_num.isdigit() else None
    for k in range(cap_idx + 1, len(lp)):
        ln, pag = lp[k]
        if pag in paginas_de_indice:
            continue
        if next_num and re.match(f'^\\s*{next_num}\\b', ln):
            siguiente_cap = k
            break
        elif re.match('^\\s*(?:Annex|Anexo|Bibliography|Bibliograf[íi]a)\\b', ln, re.I):
            siguiente_cap = k
            break
    rx_def = re.compile(f'(?<=\\S)\\s+({re.escape(cap_num)}\\.\\d{{1,3}})\\s+([a-z\\u00e0-\\u00ff])')
    rx_abre = re.compile(f'^\\s*{re.escape(cap_num)}\\.(\\d{{1,3}})(?=\\s|$)')
    ultimo = 0
    lp_nueva = []
    for k, (ln, pag) in enumerate(lp):
        if cap_idx < k < siguiente_cap and pag not in paginas_de_indice:
            curr_ln = ln
            partido = False
            m_abre = rx_abre.match(ln)
            if m_abre:
                ultimo = max(ultimo, int(m_abre.group(1)))
            while True:
                m = next((x for x in rx_def.finditer(curr_ln) if int(x.group(1).rsplit('.', 1)[1]) == ultimo + 1), None)
                if not m:
                    break
                partido = True
                ultimo += 1
                izq = curr_ln[:m.start()].rstrip()
                lp_nueva.append((izq, pag))
                curr_ln = curr_ln[m.start(1):]
            if partido:
                lp_nueva.append((curr_ln, pag))
            else:
                lp_nueva.append((ln, pag))
        else:
            lp_nueva.append((ln, pag))
    return lp_nueva

def divisiones_repetidas(pdf: TextoPdf) -> set[tuple[str, str]]:
    """Public CI documentation."""
    lp, paginas_de_indice = _lineas_de_guia(pdf)
    return _trocear_guia(lp, paginas_de_indice, frozenset())[1]
PAGINAS_DE_ENCABEZADO_REPETIDO = 2

def _no_es_encabezado(m: re.Match, pagina: int, alfabeticas: set[int], de_indice: set[int], siguiente: str) -> bool:
    """Public CI documentation."""
    if pagina in alfabeticas:
        return True
    if pagina in de_indice and (RE_PUNTOS_DE_INDICE.search(m.group(0)) or not siguiente or RE_PUNTOS_DE_INDICE.search(siguiente) or RE_NUMERO_SUELTO.match(siguiente) or RE_GUIA_AP.match(siguiente) or RE_GUIA_AP_ANTIGUO.match(siguiente)):
        return True
    palabras = m.group(2).split(None, 1)
    if palabras and palabras[0].strip(',.;:') in PALABRAS_DE_ENLACE:
        return True
    if RE_NOTA_DEL_TRADUCTOR.match(m.group(2)):
        return True
    if RE_MES.match(m.group(2)):
        return True
    return any((len(x) >= 3 for x in m.group(1).split('.')))

def _mas_uno(parte: str) -> str:
    """Public CI documentation."""
    return f'{int(parte) + 1:0{len(parte)}d}'

def _sigue_la_numeracion(num: str, ultimo: str | None, top: int) -> bool:
    """Public CI documentation."""
    candidatos: set[str] = set()
    if ultimo:
        u = ultimo.split('.')
        for j in range(len(u)):
            siguiente = u[:j] + [_mas_uno(u[j])]
            candidatos.add('.'.join(siguiente))
            candidatos |= {'.'.join(siguiente + [h]) for h in ('1', '01')}
        candidatos |= {'.'.join(u + [h]) for h in ('1', '01')}
    for t in (top, top + 1):
        candidatos |= {f'{t}.1', f'{t}.01'}
    return num in candidatos

def _cuelga_de_lo_abierto(num: str, ultimo: str | None, top: int) -> bool:
    """Public CI documentation."""
    partes = num.split('.')
    u = ultimo.split('.') if ultimo else []
    if len(partes) == 2:
        capitulos = {top, top + 1}
        if u:
            capitulos |= {int(u[0]), int(u[0]) + 1}
        return int(partes[0]) in capitulos
    padre = '.'.join(partes[:-1])
    return padre in {'.'.join(u[:i]) for i in range(1, len(u) + 1)}

def _cita_de_otra_numeracion(m: re.Match, en_anexo: bool, ultimo: str | None, top: int) -> bool:
    if not en_anexo or '.' not in m.group(1) or (not m.group(2).lstrip()[:1].islower()):
        return False
    return not (_sigue_la_numeracion(m.group(1), ultimo, top) and _cuelga_de_lo_abierto(m.group(1), ultimo, top))
RE_HISTORIAL_ANEXO = re.compile('^\\s*(?:\\([a-z]+\\)\\s*[:—–-]?\\s*)?(?:Change|Revision|Document)\\s+history\\b', re.I)

def _es_continuacion_de_frase(m: re.Match, prev: str, rutas_abiertas: set[str], ultimo_con_punto: str | None, ultimo_top: int) -> bool:
    num = m.group(1)
    if '.' not in num or f'ap.{num}' not in rutas_abiertas:
        return False
    if _sigue_la_numeracion(num, ultimo_con_punto, ultimo_top) and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top):
        return False
    p = prev.rstrip()
    if not p:
        return False
    return not RE_FIN_DE_FRASE.search(p) and _ultima_palabra_de(p) in PALABRAS_DE_REFERENCIA
RE_EMPIEZA_NUMERO = re.compile('^(\\d{1,3})\\s+\\S')

def _empieza_bloque_de_notas(resto: list[str], n: int) -> bool:
    """Public CI documentation."""
    esperado = n + 1
    for x in resto:
        m = RE_EMPIEZA_NUMERO.match(x)
        if m:
            if int(m.group(1)) != esperado:
                return False
            esperado += 1
        elif re.match('[\\dA-ZÁÉÍÓÚÑ]', x) and (not RE_NUMERO_SUELTO.match(x)):
            return False
    return True

def _titulo_comparable(titulo: str) -> str:
    """Public CI documentation."""
    return ' '.join(re.sub('[^\\w\\s]', ' ', titulo.lower()).split())

def _titulo_del_renglon_siguiente(s: str, pag: int, k: int, lp: list[tuple[str, int]], siguiente_k: list, alfabeticas: set[int], paginas_de_indice: set[int], ultimo_con_punto: str | None, ultimo_top: int) -> str | None:
    """Public CI documentation."""
    ms = RE_GUIA_AP_SOLO.match(s)
    if not ms or pag in alfabeticas or pag in paginas_de_indice:
        return None
    num = ms.group(1)
    if num == ultimo_con_punto or any((len(x) >= 3 for x in num.split('.'))):
        return None
    if not (_sigue_la_numeracion(num, ultimo_con_punto, ultimo_top) and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top)):
        return None
    j = siguiente_k[k]
    if j is not None and lp[j][1] == pag:
        otro = RE_GUIA_AP_SOLO.match(lp[j][0])
        if otro and otro.group(1) == num:
            j = siguiente_k[j]
    if j is None or lp[j][1] != pag:
        return None
    titulo = lp[j][0].strip()
    if not re.match('[^\\W\\d]', titulo) or RE_PUNTOS_DE_INDICE.search(titulo):
        return None
    palabras = titulo.split(None, 1)
    if palabras[0].strip(',.;:') in PALABRAS_DE_ENLACE or RE_MES.match(titulo):
        return None
    return titulo
RE_NUMERO_SOLO = re.compile('^\\s*(\\d{1,3})\\.?\\s*$')
RE_GUIA_AP_COMILLA = re.compile('^\\s*(\\d+(?:\\.\\d+){1,3})\\.?\\s+([«“\\"„‘].*)$')
RE_PEGADO = re.compile('(?<=\\s)(\\d{1,3}(?:\\.\\d{1,3}){0,3})(\\.?)(?=\\s+\\[?[A-ZÁÉÍÓÚÑ])')
RE_FIN_DE_FRASE = re.compile('[.;:?!][)\\]”»\\"\'’]*$')
RE_CIERRE = re.compile('[)\\]]$')
ETIQUETA_MAXIMA = 5
HUECO_MAXIMO = 2
DENSIDAD_DE_INDICE = 0.5
PALABRAS_DE_REFERENCIA = PALABRAS_DE_ENLACE | frozenset({'see', 'clause', 'clauses', 'section', 'sections', 'paragraph', 'paragraphs', 'para', 'item', 'items', 'point', 'points', 'article', 'articles', 'annex', 'annexes', 'appendix', 'appendices', 'chapter', 'chapters', 'table', 'tables', 'figure', 'figures', 'fig', 'figs', 'eq', 'eqs', 'equation', 'equations', 'note', 'notes', 'step', 'steps', 'subclause', 'subclauses', 'cf', 'per', 'under', 'from', 'than', 'number', 'no', 'nº', 'version', 'edition', 'part', 'parts', 'rule', 'rules', 'requirement', 'requirements', 'class', 'type', 'level', 'range', 'between', 'above', 'below', 'about', 'approx', 'min', 'max', 'also', 'iso', 'iec', 'en', 'etsi', 'oiml', 'welmec', 'ilac', 'ea', 'jcgm', 'ref', 'refs', 'reference', 'references', 'véase', 'ver', 'numeral', 'numerales', 'subapartado', 'subapartados', 'cláusula', 'cláusulas', 'pág', 'págs', 'apdo', 'art', 'arts', 'cap', 'sec', 'sect', 'tabla', 'tablas', 'figura', 'figuras', 'anexo', 'anexos', 'apéndice', 'apéndices', 'capítulo', 'capítulos', 'apartado', 'apartados', 'artículo', 'artículos', 'punto', 'puntos', 'epígrafe', 'epígrafes', 'párrafo', 'párrafos', 'sección', 'secciones', 'ecuación', 'ecuaciones', 'versión', 'edición', 'parte', 'partes', 'e.g', 'i.e', 'etc', 'vs', 'p', 'pp'})

def _ultima_palabra_de(texto: str) -> str:
    palabras = texto.split()
    return palabras[-1].strip('()[],;:.«»"“”\'‘’').casefold() if palabras else ''

def _etiqueta_corta(pre: str) -> bool:
    """Public CI documentation."""
    palabras = pre.split()
    return 0 < len(palabras) <= ETIQUETA_MAXIMA and palabras[0][:1].isupper() and (not any((c.isdigit() for c in pre))) and (not any((c in pre for c in '.;:?!,()'))) and (_ultima_palabra_de(pre) not in PALABRAS_DE_REFERENCIA)

def _numeros_de_candidatas(lp: list[tuple[str, int]], alfabeticas: set[int], paginas_de_indice: set[int], siguiente_linea: list[str], siguiente_k: list) -> list[str | None]:
    """Public CI documentation."""
    salida: list[str | None] = [None] * len(lp)
    for k, (ln, pag) in enumerate(lp):
        s = ln.strip()
        if not s or INDICE.search(s):
            continue
        m = RE_GUIA_AP.match(s) or RE_GUIA_AP_ANTIGUO.match(s) or RE_GUIA_AP_COMILLA.match(s)
        if m and len(m.group(1)) <= 11 and (not _no_es_encabezado(m, pag, alfabeticas, paginas_de_indice, siguiente_linea[k])):
            salida[k] = m.group(1)
            continue
        if pag in alfabeticas or pag in paginas_de_indice:
            continue
        ms = RE_GUIA_AP_SOLO.match(s)
        if ms:
            salida[k] = ms.group(1)
            continue
        ml = RE_NUMERO_SOLO.match(s)
        if ml and _titulo_tras_numero_solo(lp, k, pag, siguiente_k):
            salida[k] = str(int(ml.group(1)))
    return salida

def _titulo_tras_numero_solo(lp: list[tuple[str, int]], k: int, pag: int, siguiente_k: list) -> str | None:
    """Public CI documentation."""
    j = siguiente_k[k]
    if j is None or lp[j][1] != pag:
        return None
    titulo = lp[j][0].strip()
    if not re.match('[A-ZÁÉÍÓÚÑ]', titulo) or RE_PUNTOS_DE_INDICE.search(titulo) or INDICE.search(titulo):
        return None
    if titulo.split(None, 1)[0].strip(',.;:') in PALABRAS_DE_ENLACE or RE_MES.match(titulo):
        return None
    return titulo

def _pegado(t: str, desde: int, es_apartado: bool, ultimo_top: int, ultimo_con_punto: str | None, ya: set, con_evidencia, hijo_detras) -> tuple[int, str, re.Match] | None:
    """Public CI documentation."""
    for m in RE_PEGADO.finditer(t, max(desde, 1)):
        num, punto = (m.group(1), m.group(2))
        if f'ap.{num}' in ya:
            continue
        pre = t[:m.start()].rstrip()
        if not pre or _ultima_palabra_de(pre) in PALABRAS_DE_REFERENCIA:
            continue
        mr = RE_GUIA_AP.match(t[m.start():])
        if not mr or len(num) > 11:
            continue
        antecede = RE_FIN_DE_FRASE.search(pre) or RE_CIERRE.search(pre) or hijo_detras(num)
        if '.' not in num:
            if punto != '.' or int(num) != ultimo_top + 1 or (not con_evidencia(int(num))):
                continue
            if not (antecede or _etiqueta_corta(pre)):
                continue
        else:
            if not (_sigue_la_numeracion(num, ultimo_con_punto, ultimo_top) and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top)):
                continue
            if not (antecede or es_apartado):
                continue
        return (m.start(), num, mr)
    return None

def _trocear_guia(lp: list[tuple[str, int]], paginas_de_indice: set[int], excluir: frozenset, indice_sin_rotulo: frozenset=frozenset(), *, partir: bool=False, cadena: bool=False, rutas_de_hoy: frozenset=frozenset()) -> tuple[list[Precepto], set]:
    """Public CI documentation."""
    preceptos: list[Precepto] = []
    actual: Precepto | None = Precepto(ruta='preambulo', tipo='preambulo', numero=None, etiqueta='Preámbulo', titulo=None, pagina_inicio=1, pagina_fin=1)
    ultimo_top = 0
    pagina_del_ultimo_top = 1
    titulos_de_primer_nivel: dict[int, tuple[str, Precepto]] = {}
    alfabeticas = _paginas_de_indice_alfabetico(lp) | set(indice_sin_rotulo)
    siguiente_linea: list[str] = [''] * len(lp)
    proxima = ''
    for _k in range(len(lp) - 1, -1, -1):
        siguiente_linea[_k] = proxima
        if lp[_k][0].strip():
            proxima = lp[_k][0].strip()
    lineas_por_pagina: dict[int, int] = {}
    lineas_de_pagina: dict[int, list[str]] = {}
    for _ln, _pag in lp:
        if _ln.strip():
            lineas_por_pagina[_pag] = lineas_por_pagina.get(_pag, 0) + 1
            lineas_de_pagina.setdefault(_pag, []).append(_ln.strip())
    siguiente_k: list[int | None] = [None] * len(lp)
    _prox = None
    for _k in range(len(lp) - 1, -1, -1):
        siguiente_k[_k] = _prox
        if lp[_k][0].strip():
            _prox = _k
    ultimo_con_punto: str | None = None
    ruta_seccion: str | None = None
    pagina_en_curso, posicion = (None, -1)
    ultima_div: dict[str, tuple[str, int]] = {}
    ultima_pagina: dict[tuple[str, str], int] = {}
    repetidas: set[tuple[str, str]] = set()

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None
    rutas_abiertas: set[str] = set()
    en_anexo = False
    en_historial = False
    ultimo_renglon_con_texto = ''
    numero_candidata = _numeros_de_candidatas(lp, alfabeticas, paginas_de_indice, siguiente_linea, siguiente_k) if partir or cadena else []
    siguiente_candidata: list[int | None] = [None] * len(lp)
    candidatas_de_primer_nivel: dict[int, list[int]] = {}
    if partir or cadena:
        _prox = None
        for _k in range(len(lp) - 1, -1, -1):
            siguiente_candidata[_k] = _prox
            if numero_candidata[_k] is not None:
                _prox = _k
                if numero_candidata[_k].isdigit():
                    candidatas_de_primer_nivel.setdefault(int(numero_candidata[_k]), []).insert(0, _k)
    candidatas_en_pagina: dict[int, int] = {}
    for _k, _n in enumerate(numero_candidata):
        if _n is not None:
            candidatas_en_pagina[lp[_k][1]] = candidatas_en_pagina.get(lp[_k][1], 0) + 1

    def detras_de(k: int) -> str | None:
        """Public CI documentation."""
        sig = siguiente_candidata[k]
        return numero_candidata[sig] if sig is not None else None

    def con_hijos(k: int, n: int) -> bool:
        """Public CI documentation."""
        sig = siguiente_candidata[k]
        saltos = 0
        while sig is not None and numero_candidata[sig] == str(n) and (saltos < 2):
            sig, saltos = (siguiente_candidata[sig], saltos + 1)
        otro = numero_candidata[sig] if sig is not None else None
        return otro is not None and otro.startswith(f'{n}.')

    def hay_otro_con_hijos(k: int, n: int, pag: int) -> bool:
        """Public CI documentation."""
        return any((k2 > k and k2 != siguiente_candidata[k] and (lp[k2][1] - pag <= PAGINAS_DE_NOTA) and con_hijos(k2, n) for k2 in candidatas_de_primer_nivel.get(n, ())))

    def densidad_de_candidatas(pag: int) -> float:
        """Public CI documentation."""
        return candidatas_en_pagina.get(pag, 0) / max(lineas_por_pagina.get(pag, 1), 1)

    def se_salta_un_capitulo_que_vuelve(k: int, n: int) -> bool:
        """Public CI documentation."""
        return any((k2 > k and con_hijos(k2, m) for m in range(ultimo_top + 1, n) for k2 in candidatas_de_primer_nivel.get(m, ())))

    def titulo_de_numero_solo(s: str, k: int, pag: int) -> str | None:
        """Public CI documentation."""
        ml = RE_NUMERO_SOLO.match(s)
        if not ml or pag in alfabeticas or pag in paginas_de_indice or (int(ml.group(1)) != ultimo_top + 1):
            return None
        titulo = _titulo_tras_numero_solo(lp, k, pag, siguiente_k)
        otro = detras_de(k)
        n = int(ml.group(1))
        if titulo is None or otro is None or densidad_de_candidatas(pag) >= DENSIDAD_DE_INDICE:
            return None
        if otro.startswith(f'{n}.'):
            return titulo
        if otro != str(n + 1):
            return None
        sig = siguiente_candidata[k]
        despues = numero_candidata[siguiente_candidata[sig]] if siguiente_candidata[sig] is not None else None
        return titulo if despues is not None and (despues == str(n + 2) or despues.startswith(f'{n + 1}.')) else None

    def abrir_apartado(num: str, titulo: str, linea: str, pag: int) -> None:
        """Public CI documentation."""
        nonlocal actual, ultimo_top, pagina_del_ultimo_top, ruta_seccion, ultimo_con_punto
        cerrar()
        partes = num.split('.')
        if len(partes) > 1:
            padre = f"ap.{'.'.join(partes[:-1])}"
            ruta_seccion = f'ap.{num}'
            ultimo_con_punto = num
        else:
            padre = None
            ultimo_top = int(partes[0])
            if ultimo_top > 0:
                pagina_del_ultimo_top = pag
            ruta_seccion = f'ap.{num}'
        rutas_abiertas.add(f'ap.{num}')
        actual = Precepto(ruta=f'ap.{num}', tipo='apartado', numero=num, etiqueta=f'Apartado {num}', titulo=titulo, lineas=[linea], pagina_inicio=pag, pagina_fin=pag, padre=padre)
        if len(partes) == 1:
            titulos_de_primer_nivel.setdefault(int(partes[0]), (_titulo_comparable(titulo), actual))

    def procesar(s: str, k_ln: int, pag: int) -> tuple[str, int]:
        """Public CI documentation."""
        nonlocal actual, ultimo_top, pagina_del_ultimo_top, ruta_seccion, ultimo_con_punto, en_anexo, en_historial
        div = division_de_guia(s, posicion, pag in paginas_de_indice)
        if div and (div[0], div[1]) in excluir:
            div = None
        if div:
            previo = ultima_div.get(div[0])
            if previo is None:
                sistema = SISTEMA_DEL_PRIMERO.get(div[1])
                if sistema is None and div[3]:
                    sistema = sistema_de(div[1])
                if sistema is None:
                    div = None
                else:
                    ultima_div[div[0]] = (sistema, valor_de_numeral(div[1], sistema))
            else:
                valor = valor_de_numeral(div[1], previo[0])
                if valor is None or valor < previo[1]:
                    div = None
                else:
                    ultima_div[div[0]] = (previo[0], valor)
        if div:
            clave = (div[0], div[1])
            vista = ultima_pagina.get(clave)
            if vista is not None:
                ultima_pagina[clave] = pag
                if pag - vista > PAGINAS_DE_ENCABEZADO_REPETIDO:
                    repetidas.add(clave)
                div = None
            else:
                ultima_pagina[clave] = pag
        if div:
            tipo, num, rubrica, _ = div
            cerrar()
            if tipo in ('anexo', 'apendice'):
                en_anexo = True
                rub_siguiente = siguiente_linea[k_ln] if k_ln < len(siguiente_linea) else ''
                en_historial = bool(RE_HISTORIAL_ANEXO.search(rubrica or '') or RE_HISTORIAL_ANEXO.search(rub_siguiente))
            else:
                en_historial = False
            actual = Precepto(ruta=f'{SEGMENTO_DIV_GUIA[tipo]}.{num}', tipo=tipo, numero=num, etiqueta=f'{ETIQUETA_DIV_GUIA[tipo]} {num}', titulo=rubrica, lineas=[s], pagina_inicio=pag, pagina_fin=pag, padre=None)
            return ('otro', 0)
        if en_historial:
            if actual:
                if actual.sin_texto_aun:
                    actual.pagina_inicio = pag
                actual.lineas.append(s)
                actual.pagina_fin = pag
            return ('texto', 0)
        mt = RE_GUIA_TABLA.match(s)
        if mt:
            cerrar()
            actual = Precepto(ruta=f'tabla.{mt.group(1)}', tipo='tabla', numero=mt.group(1), etiqueta=f'Tabla {mt.group(1)}', titulo=mt.group(2).strip() or None, lineas=[s], pagina_inicio=pag, pagina_fin=pag, padre=ruta_seccion)
            return ('otro', 0)
        m = RE_GUIA_AP.match(s) or RE_GUIA_AP_ANTIGUO.match(s)
        if m is None and cadena:
            mq = RE_GUIA_AP_COMILLA.match(s)
            if mq and len(mq.group(1)) <= 11 and _sigue_la_numeracion(mq.group(1), ultimo_con_punto, ultimo_top) and _cuelga_de_lo_abierto(mq.group(1), ultimo_con_punto, ultimo_top):
                m = mq
        titulo_aparte = None
        if not m:
            titulo_aparte = _titulo_del_renglon_siguiente(s, pag, k_ln, lp, siguiente_k, alfabeticas, paginas_de_indice, ultimo_con_punto, ultimo_top)
        if titulo_aparte:
            num = RE_GUIA_AP_SOLO.match(s).group(1)
            cerrar()
            partes = num.split('.')
            padre = f"ap.{'.'.join(partes[:-1])}"
            ruta_seccion = f'ap.{num}'
            ultimo_con_punto = num
            rutas_abiertas.add(f'ap.{num}')
            actual = Precepto(ruta=f'ap.{num}', tipo='apartado', numero=num, etiqueta=f'Apartado {num}', titulo=titulo_aparte, lineas=[s], pagina_inicio=pag, pagina_fin=pag, padre=padre)
            return ('otro', 0)
        if m is None and (not titulo_aparte) and cadena and (not en_anexo):
            titulo_sin_punto = titulo_de_numero_solo(s, k_ln, pag)
            if titulo_sin_punto:
                abrir_apartado(str(int(RE_NUMERO_SOLO.match(s).group(1))), titulo_sin_punto, s, pag)
                return ('otro', 0)
        if m and len(m.group(1)) <= 11 and (not _no_es_encabezado(m, pag, alfabeticas, paginas_de_indice, siguiente_linea[k_ln])) and (not _cita_de_otra_numeracion(m, en_anexo, ultimo_con_punto, ultimo_top)) and (not _es_continuacion_de_frase(m, ultimo_renglon_con_texto, rutas_abiertas, ultimo_con_punto, ultimo_top)):
            num = m.group(1)
            partes = num.split('.')
            if len(partes) > 1:
                acepta = True
            else:
                n = int(partes[0])
                nota = (posicion >= lineas_por_pagina.get(pag, 0) - LINEAS_DE_PIE or _empieza_bloque_de_notas(lineas_de_pagina[pag][posicion + 1:], n)) and len(s.split()) >= PALABRAS_DE_NOTA and (pag - pagina_del_ultimo_top >= PAGINAS_DE_NOTA)
                acepta = n == ultimo_top + 1 and (not nota)
                repite_entrada = False
                if n in titulos_de_primer_nivel:
                    mio = _titulo_comparable(m.group(2))
                    antes, previo = titulos_de_primer_nivel[n]
                    solo_titulo = sum((1 for x in previo.lineas if x.strip())) <= 1
                    repite_entrada = solo_titulo and len(mio) >= 4 and antes.startswith(mio)
                acepta = acepta or repite_entrada
                if cadena:
                    if acepta and (not repite_entrada) and (not en_anexo) and (not con_hijos(k_ln, n)) and hay_otro_con_hijos(k_ln, n, pag):
                        acepta = False
                    elif not acepta and n == 0 and (ultimo_top == 0) and (not titulos_de_primer_nivel) and con_hijos(k_ln, 0) and m.group(2)[:1].isupper():
                        acepta = True
                    elif not acepta and (not nota) and (not en_anexo) and (1 < n - ultimo_top <= HUECO_MAXIMO + 1) and con_hijos(k_ln, n) and m.group(2)[:1].isupper() and (densidad_de_candidatas(pag) < DENSIDAD_DE_INDICE) and (not se_salta_un_capitulo_que_vuelve(k_ln, n)):
                        acepta = True
                if acepta and repite_entrada:
                    previo.de_indice = True
            if acepta:
                abrir_apartado(num, m.group(2).strip(), s, pag)
                return ('apartado', m.start(2))
        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag
        return ('texto', 0)

    def partir_pegados(clase: str, inicio: int, k_ln: int, pag: int) -> None:
        """Public CI documentation."""

        def detras() -> str | None:
            sig = siguiente_candidata[k_ln]
            return numero_candidata[sig] if sig is not None else None

        def con_evidencia(n: int) -> bool:
            otro = detras()
            return otro is not None and (otro == str(n + 1) or otro.startswith(f'{n}.'))

        def hijo_detras(num: str) -> bool:
            otro = detras()
            return otro is not None and otro.startswith(f'{num}.')
        es_apartado = clase == 'apartado'
        while actual is not None and actual.lineas:
            t = actual.lineas[-1]
            corte = _pegado(t, inicio, es_apartado, ultimo_top, ultimo_con_punto, rutas_abiertas | rutas_de_hoy, con_evidencia, hijo_detras)
            if corte is None:
                return
            pos, num, mr = corte
            pre, resto = (t[:pos].rstrip(), t[pos:])
            actual.lineas[-1] = pre
            if es_apartado:
                mp = RE_GUIA_AP.match(pre) or RE_GUIA_AP_ANTIGUO.match(pre)
                if mp:
                    actual.titulo = mp.group(2).strip()
                    if '.' not in actual.numero and titulos_de_primer_nivel.get(int(actual.numero), (None, None))[1] is actual:
                        titulos_de_primer_nivel[int(actual.numero)] = (_titulo_comparable(actual.titulo), actual)
            abrir_apartado(num, mr.group(2).strip(), resto, pag)
            es_apartado, inicio = (True, mr.start(2))
    for k_ln, (ln, pag) in enumerate(lp):
        s = ln.strip()
        if s:
            if pag != pagina_en_curso:
                pagina_en_curso, posicion = (pag, -1)
            posicion += 1
        if not s or INDICE.search(s):
            if actual:
                actual.lineas.append('')
            continue
        clase, inicio = procesar(s, k_ln, pag)
        if s:
            ultimo_renglon_con_texto = s
        if partir and clase != 'otro' and (pag not in alfabeticas) and (pag not in paginas_de_indice):
            partir_pegados(clase, inicio, k_ln, pag)
    cerrar()
    return (preceptos, repetidas)
DOCUMENTOS_CON_LISTAS_INTERIORES = frozenset({'01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_RD1021-2022_higiene_alimentos_comercio_minorista_consolidado.pdf', '01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_RD244-2016_consolidado.pdf'})
RE_AP_NUM = re.compile('^\\s*(\\d{1,2})\\.\\s+(?=[«\\"A-ZÁÉÍÓÚa-zñ(])')
RE_LETRA = re.compile('^\\s*([a-zñ])\\)\\s+')
RE_APARTADO_1_PEGADO = re.compile('(?<=\\S)\\s+(?=1\\.\\s+[«\\"A-ZÁÉÍÓÚ(])')
PALABRAS_DE_REMISION = frozenset({'artículo', 'artículos', 'apartado', 'apartados', 'párrafo', 'párrafos', 'número', 'números', 'núm', 'letra', 'letras', 'punto', 'puntos', 'epígrafe', 'epígrafes', 'anexo', 'anexos', 'capítulo', 'capítulos', 'título', 'títulos', 'libro', 'libros', 'sección', 'secciones', 'disposición', 'disposiciones', 'ley', 'leyes', 'real', 'decreto', 'directiva', 'reglamento', 'orden', 'norma', 'tabla', 'figura', 'cláusula', 'y', 'o', 'e', 'u', 'a', 'al', 'de', 'del', 'en', 'con', 'por', 'ni', 'el', 'la', 'los', 'las', 'según', 'conforme'})

def _palabra_anterior(texto: str) -> str:
    palabras = texto.split()
    return palabras[-1].strip('(),;:.«»"“”').casefold() if palabras else ''

def partir_apartados_pegados(lineas: list[str], re_ap: re.Pattern, prefijo: str | None=None, boe: bool=False) -> list[str]:
    """Public CI documentation."""
    numeros = [(lambda m: int(next((g for g in m.groups() if g))) if m else None)(re_ap.match(ln)) for ln in lineas]
    salida: list[str] = []
    ultimo: int | None = None
    for k, ln in enumerate(lineas):
        if numeros[k] is not None:
            ultimo = numeros[k]
        resto = ln
        while ultimo is not None:
            if ultimo + 1 in numeros[k + 1:]:
                break
            detras = '(?<=[.:;])'
            numero = f'{ultimo + 1}\\.'
            if boe:
                detras = '(?:(?<=[.:;])|(?<=\\(Anulado\\))|(?<=\\(Suprimido\\))|(?<=\\(Derogado\\))|(?<=\\(Anulada\\))|(?<=\\(Suprimida\\))|(?<=\\(Derogada\\))|(?<=[a-záéíóúüñ]))'
                if prefijo:
                    numero = f'(?:{ultimo + 1}\\.|{prefijo}\\.{ultimo + 1}\\.?)'
            c = None
            for cc in re.finditer(f'{detras}\\s+(?={numero}\\s+[«\\"A-ZÁÉÍÓÚ(])', resto):
                if boe and resto[cc.start() - 1:cc.start()].islower() and (_palabra_anterior(resto[:cc.start()]) in PALABRAS_DE_REMISION):
                    continue
                c = cc
                break
            if not c:
                break
            salida.append(resto[:c.start()])
            resto = resto[c.end():]
            ultimo += 1
        salida.append(resto)
    return salida
ALFABETO_DE_LETRAS = 'abcdefghijklmnñopqrstuvwxyz'
RE_LETRA_SERIE = re.compile('^\\s*([a-zñ]{1,2})\\)(?:\\s+|$)')
ROMANOS_DE_LETRA = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
SIGUIENTE_ROMANO = {'i': 'ii', 'v': 'vi', 'x': 'xi'}

def _romano_de_sublista(rotulo: str, lineas: list[str], k: int) -> bool:
    """Public CI documentation."""
    siguiente = SIGUIENTE_ROMANO.get(rotulo)
    if siguiente is None:
        return False
    if re.search('[.;:,]\\s+%s\\)(?:\\s|$)' % siguiente, lineas[k]):
        return True
    for ln in lineas[k + 1:]:
        m = RE_LETRA_SERIE.match(ln)
        if m:
            return m.group(1) == siguiente
    return False

def _comillas_netas(ln: str) -> int:
    """Public CI documentation."""
    return ln.count('«') - ln.count('»') + ln.count('“') - ln.count('”')

def _se_cierra_mas_abajo(abiertas: int, netas: list[int], k: int) -> bool:
    """Public CI documentation."""
    acumuladas = abiertas
    for n in netas[k:]:
        acumuladas += n
        if acumuladas <= 0:
            return True
    return False

def _siguientes(letra: str) -> list[str]:
    """Public CI documentation."""
    if letra == 'z':
        return ['aa']
    cabeza, ultima = (letra[:-1], letra[-1])
    if ultima == 'z':
        return [s + 'a' for s in _siguientes(cabeza)]
    i = ALFABETO_DE_LETRAS.index(ultima)
    return [cabeza + ALFABETO_DE_LETRAS[i + 1]] + ([cabeza + 'o'] if ultima == 'n' else [])

def _letras_seguidas(letras: list[str]) -> bool:
    """Public CI documentation."""
    if len(letras) < 2 or letras[0] != 'a':
        return False
    return all((despues in _siguientes(antes) for antes, despues in zip(letras, letras[1:])))

def _siguientes_letras(ultima: str | None) -> list[str]:
    return ['a'] if ultima is None else _siguientes(ultima)
RE_LETRA_CITADA_AL_FINAL = re.compile('(?:^|[\\s(«])[a-zñ]{1,2}(?:\\s+bis)?\\)$')

def _comillas(texto: str, abiertas: int, minimo: int) -> tuple[int, int]:
    """Public CI documentation."""
    for ch in texto:
        if ch == '«':
            abiertas += 1
        elif ch == '»':
            abiertas -= 1
            minimo = min(minimo, abiertas)
    return (abiertas, minimo)

def partir_letras_pegadas(lineas: list[str], boe: bool=False) -> list[str]:
    """Public CI documentation."""
    abren = [(lambda m: m.group(1) if m else None)(RE_LETRA_SERIE.match(ln)) for ln in lineas]
    salida: list[str] = []
    ultima: str | None = None
    abiertas = 0
    en_letra = minimo = 0
    for k, ln in enumerate(lineas):
        if abren[k] is not None and (not (abren[k] in ROMANOS_DE_LETRA and (ultima is None or abren[k] not in _siguientes(ultima)))):
            ultima, en_letra, minimo = (abren[k], abiertas, abiertas)
        resto = ln
        while True:
            debajo = abren[k + 1:]
            if boe and ultima is not None and ('a' in debajo):
                debajo = debajo[:debajo.index('a')]
            cands = [l for l in _siguientes_letras(ultima) if l not in debajo]
            if not cands:
                break
            corte = None
            patron = '(?<=[.:;,])\\s+(?:[yoeu]\\s+)?(?=(%s)\\)(?:\\s|$))' % '|'.join(cands)
            if boe:
                patron = '(?:(?<=[.:;,])\\s+(?:(?:[yoeu]|o en)\\s+)?|(?<=[^\\s.:;,])\\s+(?:[yoeu]|o en)\\s+|(?<=[a-záéíóúüñ0-9])\\s+(?=(?:%s)\\)\\s+[A-ZÁÉÍÓÚÑ]))(?=(%s)\\)(?:\\s|$))' % ('|'.join(cands), '|'.join(cands))
            for c in re.finditer(patron, resto):
                antes = resto[:c.start()]
                if boe and (not c.group(0).strip()) and (antes[-1:] not in '.:;,') and (_palabra_anterior(antes) in PALABRAS_DE_REMISION or RE_LETRA_CITADA_AL_FINAL.search(antes)):
                    continue
                if (antes.endswith(',') or c.group(0).strip()) and RE_LETRA_CITADA_AL_FINAL.search(antes.rstrip(',;').rstrip()):
                    continue
                if _comillas(resto[:c.start()], abiertas, minimo)[1] < en_letra:
                    break
                corte = c
                break
            if corte is None:
                break
            abiertas, minimo = _comillas(resto[:corte.start()], abiertas, minimo)
            salida.append(resto[:corte.end()].rstrip())
            resto = resto[corte.end():]
            ultima, en_letra, minimo = (corte.group(1), abiertas, abiertas)
        salida.append(resto)
        abiertas, minimo = _comillas(resto, abiertas, minimo)
    return salida
RE_ORDINAL_DE_LETRA = re.compile('^\\s*(\\d{1,2})\\.?\\s?[ºª°]')
RE_NUMERO_DE_LETRA = re.compile('^\\s*(\\d{1,3})\\)')
RE_GUION_DE_LETRA = re.compile('^\\s*[–—\\-•·▪]')
RE_CIERRA_FRASE = re.compile('[.;][»\\"”)\\]]*\\s*$')
RE_RUIDO_EN_PARRAFO = re.compile('^\\s*(?:Sec\\.\\s+[IVX]+\\.\\s+P[áa]g\\.\\s+\\d+|P[áa]gina\\s+\\d+(?:\\s*-\\s*\\d+)?|_{3,})\\s*$', re.I)

def _hasta_donde_llega_la_ultima_letra(lb: list[str], boe: bool=False) -> list[str]:
    """Public CI documentation."""
    vivas = [k for k, ln in enumerate(lb) if ln.strip() and (not RE_RUIDO_EN_PARRAFO.match(ln)) and (not any((r.match(ln) for r in RUIDO)))]
    ordinal = numero = 0
    for pos, (antes, k) in enumerate(zip(vivas, vivas[1:])):
        ln = lb[k].lstrip()
        mo, mn = (RE_ORDINAL_DE_LETRA.match(ln), RE_NUMERO_DE_LETRA.match(ln))
        if mo and int(mo.group(1)) in (1, ordinal + 1):
            ordinal = int(mo.group(1))
            continue
        if mn and int(mn.group(1)) in (1, numero + 1):
            numero = int(mn.group(1))
            continue
        if not (mo or mn) and (ln[:1].islower() or RE_GUION_DE_LETRA.match(ln)):
            continue
        if not RE_CIERRA_FRASE.search(lb[antes]):
            continue
        if ordinal and any(((m := RE_ORDINAL_DE_LETRA.match(lb[j])) and int(m.group(1)) == ordinal + 1 for j in vivas[pos + 2:])):
            continue
        return _sin_formula_de_cierre(lb[:antes + 1], boe)
    return _sin_formula_de_cierre(lb[:vivas[-1] + 1] if vivas else lb, boe)
RE_FORMULA_DE_CIERRE = re.compile('\\s+(?=El presente Reglamento será obligatorio en todos sus elementos|Los destinatarios de la presente Directiva serán)')
RE_CIERRE_DEL_ACTO_BOE = re.compile('(?:^|\\s+)(?=Dado en [A-ZÁÉÍÓÚÑ][^,.]{1,40},\\s+(?:a|el)\\s+\\d|Por tanto, Mando a todos los españoles)')

def _sin_formula_de_cierre(lb: list[str], boe: bool=False) -> list[str]:
    for k, ln in enumerate(lb):
        m = RE_FORMULA_DE_CIERRE.search(ln)
        if m:
            return lb[:k] + ([ln[:m.start()]] if ln[:m.start()].strip() else [])
    return _sin_cierre_del_acto_boe(lb) if boe else lb

def _sin_cierre_del_acto_boe(lb: list[str]) -> list[str]:
    for k, ln in enumerate(lb):
        m = RE_CIERRE_DEL_ACTO_BOE.search(ln)
        if m:
            return lb[:k] + ([ln[:m.start()]] if ln[:m.start()].strip() else [])
    return lb

def letras_sin_apartado(p: Precepto, lineas: list[str], boe: bool=False, permitir_huecos: bool=False) -> list[Precepto]:
    """Public CI documentation."""
    letras: list[tuple[str, list[str]]] = []
    cl: str | None = None
    cb: list[str] = []
    comillas = 0
    partidas = partir_letras_pegadas(lineas, boe)
    for k, ln in enumerate(partidas):
        m = RE_LETRA_SERIE.match(ln) if comillas == 0 else None
        if m and (len(m.group(1)) == 2 or m.group(1) in ROMANOS_DE_LETRA) and (cl is None or m.group(1) not in _siguientes(cl)):
            m = None
        if m and _romano_de_sublista(m.group(1), partidas, k):
            m = None
        if m:
            if cl is not None:
                letras.append((cl, cb))
            cl, cb = (m.group(1), [ln])
        elif cl is not None:
            cb.append(ln)
        comillas = max(0, comillas + ln.count('«') - ln.count('»'))
    if cl is not None:
        letras.append((cl, cb))
    serie = [l for l, _ in letras]
    creciente = len(serie) >= 2 and serie[0] == 'a' and all((len(l) == 1 for l in serie)) and all((ALFABETO_DE_LETRAS.index(a) < ALFABETO_DE_LETRAS.index(b) for a, b in zip(serie, serie[1:])))
    if not (_letras_seguidas(serie) or (permitir_huecos and creciente)):
        return []
    ultima, lb = letras[-1]
    sigue = re.compile('(?:^|\\s)[yoeu]\\s+(?:%s)\\)\\s' % '|'.join(_siguientes(ultima)))
    if any((sigue.search(ln) for ln in lb)):
        return []
    letras[-1] = (ultima, _hasta_donde_llega_la_ultima_letra(lb, boe))
    return [Precepto(ruta=f'{p.ruta}.{letra}', tipo='letra', numero=letra, etiqueta=f'{p.etiqueta}, letra {letra})', titulo=None, lineas=lb, pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin, padre=p.ruta, marca=p.marca) for letra, lb in letras]

def _definiciones_numeradas(p: Precepto) -> list[Precepto]:
    """Public CI documentation."""
    bloques = []
    for ln in p.lineas:
        m = re.match('^\\s*(\\d{1,3})\\)(?:\\s|$)', ln)
        if m:
            bloques.append((m.group(1), [ln]))
        elif bloques:
            bloques[-1][1].append(ln)
    numeros = [int(n) for n, _ in bloques]
    if len(numeros) < 2 or numeros[0] != 1 or any((a >= b for a, b in zip(numeros, numeros[1:]))):
        return []
    hijos = []
    for num, lineas in bloques:
        hijo = Precepto(ruta=f'{p.ruta}.{num}', tipo='apartado', numero=num, etiqueta=f'{p.etiqueta}.{num}', titulo=None, lineas=lineas, pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin, padre=p.ruta, marca=p.marca)
        hijos.append(hijo)
        hijos.extend(letras_sin_apartado(hijo, lineas))
    return hijos

def subdividir(preceptos: list[Precepto], listas_interiores: bool=False, boe: bool=False, definiciones: frozenset[str]=frozenset(), letras_con_huecos: frozenset[str]=frozenset(), numeracion_modificativa: bool=False) -> list[Precepto]:
    """Public CI documentation."""
    salida: list[Precepto] = []
    for p in preceptos:
        salida.append(p)
        if p.tipo not in ('articulo', 'apartado', 'disposicion'):
            continue
        if numeracion_modificativa:
            hijos = _subdividir_modificaciones_numeradas(p)
            if hijos is not None:
                salida.extend(hijos)
                continue
        if p.ruta.startswith(RUTA_INSTRUCCION + '.'):
            continue
        if p.ruta in definiciones:
            hijos = _definiciones_numeradas(p)
            if hijos:
                salida.extend(hijos)
                continue
        lineas = [l for l in p.lineas]
        re_ap = RE_AP_NUM
        if p.tipo == 'articulo' and p.numero and p.numero.isdigit():
            re_ap = re.compile('^\\s*(?:%s\\.(\\d{1,2})\\.?|(\\d{1,2})\\.)\\s+(?=[«\\"A-ZÁÉÍÓÚa-zñ(])' % re.escape(p.numero))
        abren = {next((g for g in m.groups() if g)) for m in (re_ap.match(ln) for ln in lineas) if m}
        prefijo = p.numero if boe and p.tipo == 'articulo' and p.numero and p.numero.isdigit() else None
        siguiente_prefijado = prefijo and any((re.search(f'(?<=[.;:)])\\s+{re.escape(prefijo)}\\.2\\.?\\s+[«\\"A-ZÁÉÍÓÚ(]', ln) for ln in lineas))
        if '1' not in abren and (any((int(n) > 1 for n in abren)) or siguiente_prefijado):
            primero = re.compile(f'(?<=\\S)\\s+(?=(?:1\\.|{re.escape(prefijo)}\\.1\\.?)\\s+[«\\"A-ZÁÉÍÓÚ(])') if prefijo else RE_APARTADO_1_PEGADO
            for k in range(min(2, len(lineas))):
                c1 = next((c for c in primero.finditer(lineas[k]) if _palabra_anterior(lineas[k][:c.start()]) not in PALABRAS_DE_REMISION), None)
                if c1:
                    lineas[k:k + 1] = [lineas[k][:c1.start()], lineas[k][c1.end():]]
                    break
        lineas = partir_apartados_pegados(lineas, re_ap, p.numero if p.tipo == 'articulo' and p.numero and p.numero.isdigit() else None, boe)
        bloques: list[tuple[str, list[str]]] = []
        actual_num: str | None = None
        buf: list[str] = []
        numeros = [int(next((g for g in m.groups() if g))) if m else None for m in (re_ap.match(ln) for ln in lineas)]
        anidado: int | None = None
        for k, ln in enumerate(lineas):
            n = numeros[k]
            if listas_interiores and n is not None and (actual_num is not None):
                fuera = int(actual_num) + 1
                if anidado is None and n == 1:
                    anidado, n = (1, None)
                elif anidado is not None:
                    if n == anidado + 1 and (n != fuera or n in numeros[k + 1:]):
                        anidado, n = (n, None)
                    elif n == fuera:
                        anidado = None
                    else:
                        n = None
            if n is not None:
                if actual_num is not None:
                    bloques.append((actual_num, buf))
                actual_num = next((g for g in re_ap.match(ln).groups() if g))
                buf = [ln]
            elif actual_num is not None:
                buf.append(ln)
        if actual_num is not None:
            bloques.append((actual_num, buf))
        if len(bloques) < 2:
            salida.extend(letras_sin_apartado(p, lineas, boe, p.ruta in letras_con_huecos))
            continue
        apartados_con_letras: set[str] = set()
        for num, buf in bloques:
            if boe and p.tipo == 'disposicion':
                buf = _sin_cierre_del_acto_boe(buf)
            hijo = Precepto(ruta=f'{p.ruta}.{num}', tipo='apartado', numero=num, etiqueta=f'{p.etiqueta}.{num}' if p.tipo == 'articulo' else f'{p.etiqueta}, {num}', titulo=None, lineas=buf, pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin, padre=p.ruta, marca=p.marca)
            salida.append(hijo)
            if hijo.ruta in apartados_con_letras:
                continue
            letras: list[tuple[str, list[str]]] = []
            cl: str | None = None
            cb: list[str] = []
            comillas_en_letra = 0
            partidas = partir_letras_pegadas(buf, boe)
            netas = [_comillas_netas(ln) for ln in partidas]
            for k, ln in enumerate(partidas):
                en_cita = comillas_en_letra > 0 and _se_cierra_mas_abajo(comillas_en_letra, netas, k)
                m = None if en_cita else RE_LETRA_SERIE.match(ln)
                if m and (len(m.group(1)) == 2 or m.group(1) in ROMANOS_DE_LETRA) and (cl is None or m.group(1) not in _siguientes(cl)):
                    m = None
                if m and _romano_de_sublista(m.group(1), partidas, k):
                    m = None
                if m:
                    if cl is not None:
                        if m.group(1) == 'a':
                            cb = _hasta_donde_llega_la_ultima_letra(cb, boe)
                        letras.append((cl, cb))
                    cl, cb = (m.group(1), [ln])
                    comillas_en_letra = max(0, netas[k])
                elif cl is not None:
                    cb.append(ln)
                    comillas_en_letra = max(0, comillas_en_letra + netas[k])
            if cl is not None:
                letras.append((cl, cb))
            if letras:
                letras[-1] = (letras[-1][0], _hasta_donde_llega_la_ultima_letra(letras[-1][1], boe))
                apartados_con_letras.add(hijo.ruta)
            for letra, lb in letras:
                salida.append(Precepto(ruta=f'{hijo.ruta}.{letra}', tipo='letra', numero=letra, etiqueta=f'{hijo.etiqueta}, letra {letra})', titulo=None, lineas=lb, pagina_inicio=hijo.pagina_inicio, pagina_fin=hijo.pagina_fin, padre=hijo.ruta, marca=p.marca))
    return salida

def _subdividir_modificaciones_numeradas(p: Precepto) -> list[Precepto] | None:
    """Public CI documentation."""
    if p.tipo != 'articulo':
        return None
    unos = [i for i, ln in enumerate(p.lineas) if re.match('^\\s*1\\.\\s', ln)]
    if len(unos) < 2 or not re.search('\\bse modifica como sigue:\\s*$', p.lineas[unos[0]]):
        return None
    exteriores = subdividir([p], listas_interiores=True)
    salida = []
    interiores = set()
    for q in exteriores[1:]:
        if any((q.ruta.startswith(r + '.') for r in interiores)):
            continue
        salida.append(q)
        if q.tipo != 'apartado' or q.padre != p.ruta or q.numero != '1':
            continue
        inicio = next((i for i, ln in enumerate(q.lineas) if i and re.match('^\\s*1\\.\\s', ln)), None)
        if inicio is not None:
            interior = replace(q, lineas=q.lineas[inicio:])
            salida.extend(subdividir([interior])[1:])
            interiores.add(q.ruta)
    return salida

def subdividir_anexo_sin_numeral(preceptos: list[Precepto]) -> list[Precepto]:
    """Public CI documentation."""
    rx = re.compile('^\\s*(\\d{1,2}(?:\\.\\d{1,2})*)\\.?\\s+(?=[A-ZÁÉÍÓÚÑ«])')
    salida = []
    for p in preceptos:
        salida.append(p)
        if p.tipo != 'capitulo' or p.padre != 'anexo.sn':
            continue
        lineas = list(p.lineas)
        for k in range(min(8, len(lineas))):
            corte = re.search('\\s+(?=1\\.\\s+[A-ZÁÉÍÓÚÑ])', lineas[k])
            if corte:
                lineas[k:k + 1] = [lineas[k][:corte.start()], lineas[k][corte.end():]]
                break
        preparadas = []
        ultimo = None
        for ln in lineas:
            m = rx.match(ln)
            if m and '.' not in m[1]:
                ultimo = int(m[1])
            corte = re.search('\\s+(?=' + str(ultimo + 1) + '\\.\\s+[A-ZÁÉÍÓÚÑ])', ln) if ultimo is not None else None
            if corte:
                preparadas.extend([ln[:corte.start()], ln[corte.end():]])
                ultimo += 1
            else:
                preparadas.append(ln)
        lineas = preparadas
        bloques: dict[str, list[str]] = {}
        activo = None
        for ln in lineas:
            m = rx.match(ln)
            if m:
                num = m.group(1)
                if '.' in num and num.rsplit('.', 1)[0] not in bloques:
                    m = None
                elif num not in bloques or num == activo:
                    activo = num
                    bloques.setdefault(num, [])
                else:
                    m = None
            if activo:
                for num, buf in bloques.items():
                    if activo == num or activo.startswith(num + '.'):
                        buf.append(ln)
        if len(bloques) < 2:
            continue
        for num, buf in bloques.items():
            padre = p.ruta if '.' not in num else p.ruta + '/ap.' + num.rsplit('.', 1)[0]
            salida.append(Precepto(ruta=p.ruta + '/ap.' + num, tipo='apartado', numero=num, etiqueta=f'{p.etiqueta}, apartado {num}', titulo=None, lineas=buf, pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin, padre=padre, marca=p.marca))
    return salida

def _respaldo_documento(pdf: TextoPdf, an: Analisis) -> Analisis:
    """Public CI documentation."""
    if an.preceptos:
        return an
    an.preceptos = [Precepto(ruta='documento', tipo='documento', numero=None, etiqueta=an.titulo or 'documento completo', titulo=None, lineas=[p for p in pdf.paginas], pagina_inicio=1, pagina_fin=max(1, pdf.n_paginas))]
    return an

def vincular_articulado_a_divisiones(preceptos: list[Precepto]) -> list[Precepto]:
    """Public CI documentation."""
    niveles = {'reglamento': 0, 'libro': 1, 'titulo': 2, 'capitulo': 3, 'seccion': 4}
    pila: list[Precepto] = []
    salida = []
    for original in preceptos:
        p = original
        if p.tipo in niveles and (not p.ruta.startswith(('anexo.', 'itc.'))):
            while pila and niveles[pila[-1].tipo] >= niveles[p.tipo]:
                pila.pop()
            if p.padre is None and pila:
                p = replace(p, padre=pila[-1].ruta)
            pila.append(p)
        elif p.tipo == 'articulo' and re.fullmatch('art\\.[^/]+', p.ruta):
            if p.padre is None and pila:
                p = replace(p, padre=pila[-1].ruta)
        elif p.tipo in {'cabecera', 'preambulo', 'disposicion', 'formula_final', 'anexo', 'instruccion'}:
            pila.clear()
        salida.append(p)
    return salida

def _bloques_de_anexo(p: Precepto) -> list[Precepto]:
    """Public CI documentation."""
    if RX_TABLA_CORRESP.search(p.texto):
        return []
    if any((re.match('^\\s*[a-zñ]\\s+(?:bis|ter|quater|quinquies)\\)\\s*', ln) for ln in p.lineas)):
        return []
    divisiones = re.compile('^\\s*(PARTE|Cap[íi]tulo)\\s+([A-Z]|\\d{1,3})\\s*[.—:–-]?\\s+([A-ZÁÉÍÓÚÑ].*)$')
    encontradas = [(k, divisiones.match(ln)) for k, ln in enumerate(p.lineas) if k > 0 and divisiones.match(ln)]
    if encontradas:
        encontradas = [(k, m) for k, m in encontradas if m[1] == encontradas[0][1][1]]
        ultimas = {(m[1], m[2]): (k, m) for k, m in encontradas}
        cortes = sorted(ultimas.values(), key=lambda x: x[0])
        if len(ultimas) != len(encontradas):
            indices = {k for k, _ in encontradas}
            if any((k >= cortes[0][0] and k != ultimas[m[1], m[2]][0] for k, m in encontradas)):
                return []
            if any((ln.strip() and k not in indices for k, ln in enumerate(p.lineas) if encontradas[0][0] <= k < cortes[0][0])):
                return []
        hijos = []
        for n, (inicio, m) in enumerate(cortes):
            fin = cortes[n + 1][0] if n + 1 < len(cortes) else len(p.lineas)
            tipo = 'parte' if m[1] == 'PARTE' else 'capitulo'
            hijo = replace(p, ruta=f'{p.ruta}/{tipo}.{m[2]}', tipo=tipo, numero=m[2], etiqueta=f'{p.etiqueta}, {m[1]} {m[2]}', titulo=m[3], lineas=p.lineas[inicio:fin], padre=p.ruta)
            hijos.append(hijo)
            hijos.extend(_bloques_de_anexo(hijo))
        return hijos
    punto = re.compile('^\\s*(\\d{1,3}(?:\\.\\d{1,3}){1,4}\\.?(?=\\s)|\\d{1,3}[.)])\\s+([A-ZÁÉÍÓÚÑ«¿].*)$')
    cortes = [(k, m[1].rstrip('.)')) for k, ln in enumerate(p.lineas) if (m := punto.match(ln))]
    if len(cortes) < 2:
        return []
    primero = cortes[0][1]
    if '.' in primero:
        prefijo = primero.rsplit('.', 1)[0] + '.'
        cortes = [(k, num) for k, num in cortes if num.startswith(prefijo)]
    inicios = {'1'}
    if p.tipo == 'capitulo' and p.numero and p.numero.isdigit():
        inicios.add(p.numero + '.1')
    if primero not in inicios:
        return []
    ultimo = None
    vistos = set()
    for _, num in cortes:
        if num in vistos or (ultimo is not None and num not in _siguientes_de(ultimo)):
            return []
        vistos.add(num)
        ultimo = num
    hijos = []
    for n, (inicio, num) in enumerate(cortes):
        fin = next((k for k, otro in cortes[n + 1:] if not otro.startswith(num + '.')), len(p.lineas))
        anterior = num.rsplit('.', 1)[0] if '.' in num else None
        padre = f'{p.ruta}/ap.{anterior}' if anterior in vistos else p.ruta
        hijos.append(replace(p, ruta=f'{p.ruta}/ap.{num}', tipo='apartado', numero=num, etiqueta=f'{p.etiqueta}, punto {num}', titulo=None, lineas=p.lineas[inicio:fin], padre=padre))
    return hijos

def subdividir_puntos_de_anexo(preceptos: list[Precepto]) -> list[Precepto]:
    """Public CI documentation."""
    rutas = {p.ruta for p in preceptos}
    salida = []
    for p in preceptos:
        salida.append(p)
        if p.ruta.startswith('anexo.') and p.tipo in {'anexo', 'capitulo', 'seccion', 'apendice'} and (not any((r.startswith(p.ruta + '/') for r in rutas))):
            salida.extend((h for h in _bloques_de_anexo(p) if h.ruta not in rutas))
    return salida

def analizar(familia: str, pdf: TextoPdf) -> Analisis:
    from . import alcance_r3
    pdf = alcance_r3.para_trocear(pdf)
    an = _respaldo_documento(pdf, _ANALIZADORES[familia](pdf))
    an.preceptos = sin_rutas_repetidas(an.preceptos)
    if familia == 'boe':
        altas_boe_r2 = {'BOE-A-1983-19755', 'BOE-A-2000-24019', 'BOE-A-2002-18099', 'BOE-A-2011-11604', 'BOE-A-2011-15623', 'BOE-A-2013-13645', 'BOE-A-2015-710', 'BOE-A-2022-21135'}
        if an.identificador is None or an.identificador in altas_boe_r2 or alcance_r3.activa(pdf.ruta_relativa, pdf.sha256):
            an.preceptos = vincular_articulado_a_divisiones(an.preceptos)
    elif familia == 'eurlex':
        an.preceptos = subdividir_puntos_de_anexo(an.preceptos)
    return an
_ANALIZADORES = {'boe': analizar_boe, 'eurlex': analizar_eurlex, 'guia': analizar_guia}
ANALIZADORES = {k: lambda pdf, f=k: analizar(f, pdf) for k in _ANALIZADORES}
