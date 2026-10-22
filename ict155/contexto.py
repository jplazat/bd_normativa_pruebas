"""Public CI documentation."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from . import parsers as _parsers, ruta as _ruta
from .consulta import division_que_cierra_enumeracion, ruta_de_cita
RE_NORMA = re.compile('(Real\\s+Decreto\\s+Legislativo\\s+\\d+/\\d{4}|RDL\\s+\\d+/\\d{4}|Ley\\s+\\d+/\\d{4}|Real\\s+Decreto\\s+\\d+/\\d{4}|RD\\s+\\d+/\\d{4}|Orden\\s+[A-Z]{3}/\\d+/\\d{4}|Orden\\s+de\\s+\\d{1,2}\\s+de\\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\\s+de\\s+\\d{4}|Gu[íi]a\\s+(?:del\\s+)?(?:CEM|CML)\\s+C-\\d+|Gu[íi]a\\s+C-\\d+|CGA-ENAC-OCML|\\bEA[-\\s]2/17(?:\\s+(?:M|S[123]))?(?::\\d{4})?|\\bEA[-\\s]4/02(?:\\s+M)?(?::\\d{4})?|\\bWELMEC\\s+(?:Guide\\s+)?\\d+(?:\\.\\d+)+|JCGM\\s+100(?::2008)?(?:/|\\s+)Amd\\.?\\s*1(?::2026)?|JCGM\\s+(?:100|101|106|200)(?::\\d{4})?|\\bGUM\\s+(?:Suplemento|Supplement)\\s+1\\b|\\bGUM\\b(?!\\s+(?:Suplemento|Supplement)\\b)|\\bVIML?\\b|\\bOIML\\s+[DV]\\s?\\d+(?::\\d{4})?|\\bEURAMET\\s+cg-\\d+(?:\\s+v\\.?\\s?\\d+(?:\\.\\d+)?)?|\\bILAC[-\\s][GP]\\s?\\d+(?::(?:\\d{2}/)?\\d{4})?|[Aa]nexo\\s+\\d+\\s+(?:de|del)\\s+EudraLex(?:\\s+Volumen\\s+4)?|Annex\\s+\\d+\\s+(?:of|to)\\s+EudraLex(?:\\s+Volume\\s+4)?|EudraLex\\s+Volumen\\s+4,\\s*Anexo\\s+\\d+|EudraLex\\s+Volume\\s+4,\\s*Annex\\s+\\d+|EudraLex[^,.;]{0,30}Annex\\s+\\d+|Reglamento\\s+Delegado\\s+\\(UE\\)\\s+\\d{4}/\\d+|Reglamento\\s+\\((?:CE|UE)\\)\\s+n?\\.?\\s*[ºo]?\\s*\\d+/\\d{4}|Reglamento\\s+\\(UE\\)\\s+\\d{4}/\\d+|Directiva\\s+\\(?UE\\)?\\s*\\d{4}/\\d+/?U?E?|Directiva\\s+\\d{4}/\\d+/[A-Z]{2}|Decisi[óo]n\\s+de\\s+Ejecuci[óo]n\\s+\\(UE\\)\\s+\\d{4}/\\d+|Decisi[óo]n\\s+n?\\.?\\s*[ºo]?\\s*\\d+/\\d{4}/[A-Z]{2}|Directrices\\s+\\d{4}/C\\s+\\d+/\\d+|Comunicaci[óo]n\\s+C/\\d{4}/\\d+|\\(\\d{4}/C\\s+\\d+/\\d+\\)|EudraLex[^,.;]{0,30}Anexo\\s+\\d+|Directrices\\s+GDP|Directrices\\s+de\\s+distribuci[óo]n\\s+correcta|(?:UNE-)?EN\\s?\\d{4,}(?:-\\d+)?(?::\\d{4})?|ISO/IEC\\s+\\d+(?:-\\d+)?(?::\\d{4})?|ISO\\s+\\d+(?:-\\d+)?(?::\\d{4})?)')
RE_NOMBRE_CON_ANEXO = re.compile('[Aa]nexo\\s+(\\d+)\\s+(?:de|del)\\s+EudraLex(?:\\s+Volumen\\s+4)?')
MOTIVO_NOMBRE_DE_DOCUMENTO = 'es el nombre de un documento (el Anexo de EudraLex), no una referencia a un precepto'

def _sin_el_nombre_de_la_norma(ln: str, ref_txt: str, a: int, b: int, nombres: list[tuple[int, int]]):
    """Public CI documentation."""
    for i0, i1 in nombres:
        if i0 <= a and b <= i1:
            return None
        if a < i0 < b <= i1:
            corte = re.sub('[\\s,;]*(?:de|del)?\\s*$', '', ref_txt[:i0 - a])
            return (corte, a, a + len(corte)) if corte else None
    return (ref_txt, a, b)
_ALTERNATIVAS_REF: list[str] = []
_ALTERNATIVAS_REF.append('\\barts?\\.\\s*\\d[\\w.\\-]*')
_ALTERNATIVAS_REF += [f'art[íi]culos?\\s+\\d+\\s?{_parsers.ORD_LATINO}', f'art[íi]culos?\\s+\\d+\\s+{_parsers.ORD_CASTELLANO}(?=\\s*(?:[,.;:)]|$)|\\s+del?\\b)']
_ALTERNATIVAS_REF.append(f'(?:anexos?|ap[ée]ndices?|t[íi]tulos?)\\s+(?:[IVXLC]+|\\d+|[A-Z]){_parsers.ORD_DIV}')

def _alternativa_de_ordinales() -> str:
    tilde = {'a': '[aá]', 'e': '[eé]', 'i': '[ií]', 'o': '[oó]', 'u': '[uú]'}
    formas = {'preliminar', *_parsers.ORDINALES}
    propias = '|'.join(sorted((''.join((tilde.get(c, c) for c in f)) for f in formas), key=len, reverse=True))
    return f'{propias}|{_parsers.ORD_CASTELLANO}'
_NUMERAL_REF = f'(?-i:\\d|[IVXLC]+\\b|[A-Z]\\b|(?:[ivxlc]+|[a-zñç])(?=\\)))[\\w.\\-]*|(?i:{_alternativa_de_ordinales()})\\b[\\w.\\-]*'
_ALTERNATIVAS_REF.append(f'(?:art[íi]culos?|apartados?|anexos?|anejos?|ap[ée]ndices?|cl[áa]usulas?|tablas?|disposici[óo]n\\s+(?:adicional|transitoria|derogatoria|final)|t[íi]tulos?)\\s+(?:{_NUMERAL_REF})')
RE_REF = re.compile('|'.join(_ALTERNATIVAS_REF), re.I)
_ABREV = re.compile('\\b(?:art|ap|n[ºo]|p|pp|vol|núm|num|cf|etc|Sr|Sra|Ltd|Co)\\.$', re.I)

def frases(texto: str) -> list[tuple[int, int]]:
    """Public CI documentation."""
    cortes = [0]
    for m in re.finditer('\\|', texto):
        cortes.append(m.end())
    for m in re.finditer('[.;:]\\s+(?=[«\\"A-ZÁÉÍÓÚ0-9])', texto):
        if _ABREV.search(texto[max(0, m.start() - 6):m.start() + 1]):
            continue
        cortes.append(m.end())
    cortes.append(len(texto))
    cortes = sorted(set(cortes))
    return [(cortes[i], cortes[i + 1]) for i in range(len(cortes) - 1)]

@dataclass
class CitaResuelta:
    linea: int
    referencia: str
    norma: str | None = None
    ruta: str | None = None
    identificador: str | None = None
    ambigua: bool = False
    motivo: str | None = None
    ambito: str | None = None
    posicion: int = -1
    candidatas: tuple = ()
    contexto: str = ''
    cualificador: str | None = None
    por_entrada: bool = False
RX_LETRA_PEGADA = re.compile('\\.([a-zñç])\\b\\s*$', re.I)
RX_APARTADO_DELANTE = re.compile('^\\s*(apartados?|n[uú]meros?|p[áa]rrafos?)\\s+(\\d+(?:\\.\\d+)*)\\s*(?:,|;)?\\s*(?:de|del)\\s+', re.I)
RX_LETRA_DELANTE = re.compile('(letras?|incisos?)\\s+([a-zñç])\\)\\s*(?:,\\s*)?(?:de|del)\\s+(?:la\\s+|el\\s+|los\\s+|las\\s+)?$', re.I)

def cualificador_perdido(referencia: str, ruta: str | None, antes: str='') -> str | None:
    """Public CI documentation."""
    if not ruta:
        return None
    ultimo = ruta.split('/')[-1]
    cuerpo = ultimo.partition('.')[2]
    m = RX_LETRA_PEGADA.search(referencia.strip())
    if m and (not cuerpo.lower().endswith('.' + m.group(1).lower())):
        return f'letra {m.group(1).lower()}'
    m = RX_APARTADO_DELANTE.match(referencia)
    if m:
        numero = m.group(2)
        if not (cuerpo == numero or cuerpo.endswith('.' + numero) or ultimo.startswith('ap.')):
            return f"{m.group(1).lower().rstrip('s')} {numero}"
    m = RX_LETRA_DELANTE.search(antes or '')
    if m and (not cuerpo.lower().endswith('.' + m.group(2).lower())):
        return f"{m.group(1).lower().rstrip('s')} {m.group(2).lower()})"
    return None

def _encadenar(refs: list[re.Match], texto: str, corta_en_cierre: bool=False) -> list[tuple[str, int, int]]:
    """Public CI documentation."""
    if not refs:
        return []
    grupos: list[list[re.Match]] = [[refs[0]]]
    for m in refs[1:]:
        hueco = texto[grupos[-1][-1].end():m.start()]
        if len(hueco) <= 12 and re.fullmatch('[\\s,;yode/l()\\-]*', hueco, re.I) and (not (corta_en_cierre and (')' in hueco or ';' in hueco))):
            grupos[-1].append(m)
        else:
            grupos.append([m])
    return [(texto[g[0].start():g[-1].end()], g[0].start(), g[-1].end()) for g in grupos]

def _unica(normas: list[str]) -> str | None:
    distintas = list(dict.fromkeys(normas))
    return distintas[0] if len(distintas) == 1 else None

def _tramos(lineas: list[str], solo_titulo: bool) -> dict[int, tuple[int, int]]:
    """Public CI documentation."""
    tramos: dict[int, tuple[int, int]] = {}
    ini = 0
    for i, ln in enumerate(lineas + ['']):
        titulo = ln.lstrip().startswith('#')
        if i == len(lineas) or (titulo if solo_titulo else titulo or not ln.strip()):
            for j in range(ini, i):
                tramos[j] = (ini, i)
            ini = i if titulo and solo_titulo else i + 1
    for j in range(len(lineas)):
        tramos.setdefault(j, (0, len(lineas)))
    return tramos

def normas_heredables(texto: str) -> dict[int, tuple[str | None, str | None]]:
    """Public CI documentation."""
    lineas = texto.split('\n')
    parr, secc = (_tramos(lineas, False), _tramos(lineas, True))
    cache: dict[tuple[int, int], str | None] = {}

    def unica(tramo: tuple[int, int]) -> str | None:
        if tramo not in cache:
            cache[tramo] = _unica([m.group(0) for m in RE_NORMA.finditer('\n'.join(lineas[tramo[0]:tramo[1]]))])
        return cache[tramo]
    return {i + 1: (unica(parr[i]), unica(secc[i])) for i in range(len(lineas))}

def candidatas_de_linea(texto: str) -> dict[int, tuple[str, ...]]:
    """Public CI documentation."""
    lineas = texto.split('\n')
    secc = _tramos(lineas, True)
    cache: dict[tuple[int, int], tuple[str, ...]] = {}

    def todas(tramo: tuple[int, int]) -> tuple[str, ...]:
        if tramo not in cache:
            cache[tramo] = tuple(dict.fromkeys((m.group(0) for m in RE_NORMA.finditer('\n'.join(lineas[tramo[0]:tramo[1]])))))
        return cache[tramo]
    return {i + 1: todas(secc[i]) for i in range(len(lineas))}
MOTIVO_REMITE_AL_INFORME = 'remite a una seccion del propio informe'
RE_ENCABEZADO_MD = re.compile('^\\s*(#{1,6})\\s+(.*)$')
RE_ENCABEZADO_DE_FUENTES = re.compile('fuentes\\s+citadas|relaci[óo]n\\s+de\\s+fuentes|bibliograf[íi]a|referencias\\s+bibliogr[aá]ficas', re.I)
RE_ENTRADA = re.compile('^\\s*(?:[-*•]\\s+|\\d+[.)]\\s+)?\\*\\*(.+?)\\*\\*')
RE_REMITE_AL_INFORME = re.compile('^\\s*(?:v[eé]ase\\s+|ver\\s+)?secci[óo]n(?:es)?\\b|\\b(?:del|de\\s+este|del\\s+presente)\\s+informe\\b', re.I)
RX_PEGADA_NORMA = re.compile('\\s*,?\\s*(?:de\\s+la\\s+norma|(?:del|de)(?:\\s+(?:las|los|la|el))?)\\s*', re.IGNORECASE)
RX_ENUMERACION_ANTES_DE_DE = re.compile('(?:\\s*(?:,|\\by\\b|\\be\\b|\\bo\\b)\\s*\\d+(?:\\.\\d+)*[a-z]?)*\\s*,?\\s*(?:de\\s+la\\s+norma|(?:del|de)(?:\\s+(?:las|los|la|el))?)\\s*', re.IGNORECASE)
RX_CLAUSULA = re.compile('cl[áa]usulas?\\b', re.I)
RX_EMPLEO = re.compile('Empleo\\s*:', re.I)
RX_SOBRE = re.compile(',\\s*sobre\\b', re.I)
RX_SU_INICIAL = re.compile('(?:^|[.:;]\\s+|\\*\\*\\s*)Sus?\\s+$')
RX_Y_DE_HERMANA = re.compile(',\\s*y\\s+$')
MOTIVO_ANEXO_DEL_INFORME = 'puede ser un anexo del propio informe'
RE_ANEXO_PROPIO = re.compile('^\\s*#{1,6}\\s+Anexo\\s+([IVXLCDM]+|\\d+|[A-Z])\\b', re.I)

def anexos_propios(lineas: list[str]) -> frozenset[str]:
    """Public CI documentation."""
    return frozenset((m.group(1).upper() for ln in lineas if (m := RE_ANEXO_PROPIO.match(ln))))

def _elementos_de_empleo(ln: str, en_empleo: bool=False) -> tuple[list[tuple[int, int, int | None, bool]], bool]:
    """Public CI documentation."""
    elementos: list[tuple[int, int, int | None, bool]] = []
    m = RX_EMPLEO.search(ln)
    if m:
        ini = m.end()
    elif en_empleo:
        ini = 0
    else:
        return (elementos, False)
    abre = bool(m)
    n = len(ln)
    while ini < n:
        fin = ln.find(';', ini)
        fin = n if fin < 0 else fin
        s = RX_SOBRE.search(ln, ini, fin)
        elementos.append((ini, fin, s.start() if s else None, abre))
        ini, abre = (fin + 1, True)
    return (elementos, True)

def cabezas_de_elemento(ln: str, en_empleo: bool=False) -> tuple[list[tuple[int, int]], bool]:
    """Public CI documentation."""
    elementos, abierto = _elementos_de_empleo(ln, en_empleo)
    return ([(ini, sobre) for ini, _, sobre, _ in elementos if sobre is not None], abierto)

def apertura_de_elemento(ln: str, ini: int) -> int:
    """Public CI documentation."""
    n = len(ln)
    while ini < n and ln[ini] in ' \t*':
        ini += 1
    return ini

def _tipo_de_referencia(ref_txt: str) -> str | None:
    """Public CI documentation."""
    m = re.match('[^\\W\\d_]+', ref_txt)
    if not m:
        return None
    p = ''.join((c for c in unicodedata.normalize('NFD', m.group(0).lower()) if unicodedata.category(c) != 'Mn'))
    if p.endswith('ones'):
        return p[:-2]
    return p[:-1] if p.endswith('s') else p

def _hermana(ruta: str, vigente: str, vigente_con_apartado: bool) -> str | None:
    """Public CI documentation."""
    if ruta.startswith('ap.') and '.' not in ruta[3:] and vigente_con_apartado and re.fullmatch('art\\.[^/.]+\\.[^/.]+', vigente):
        return f"{vigente.rsplit('.', 1)[0]}.{ruta[3:]}"
    tipo = ruta.split('.')[0]
    if tipo in ('apend', 'tabla') and '/' not in ruta:
        comps = vigente.split('/')
        idx = max((k for k, c in enumerate(comps) if c.startswith(tipo + '.')), default=None)
        if idx:
            return '/'.join(comps[:idx] + [ruta])
    return None

def rangos_de_fuentes(lineas: list[str]) -> list[tuple[int, int]]:
    """Public CI documentation."""
    out: list[tuple[int, int]] = []
    n, i = (len(lineas), 0)
    while i < n:
        h = RE_ENCABEZADO_MD.match(lineas[i])
        if not (h and RE_ENCABEZADO_DE_FUENTES.search(h.group(2))):
            i += 1
            continue
        nivel, fin = (len(h.group(1)), n)
        for j in range(i + 1, n):
            hj = RE_ENCABEZADO_MD.match(lineas[j])
            if hj and len(hj.group(1)) <= nivel:
                fin = j
                break
        out.append((i, fin))
        i = fin
    return out

def entradas_de_fuentes(lineas: list[str]) -> dict[int, tuple[str | None, int]]:
    """Public CI documentation."""
    out: dict[int, tuple[str | None, int]] = {}
    for i, fin in rangos_de_fuentes(lineas):
        j = i + 1
        while j < fin:
            m = RE_ENTRADA.match(lineas[j])
            if not m:
                j += 1
                continue
            normas = list(dict.fromkeys((' '.join(x.group(0).split()) for x in RE_NORMA.finditer(m.group(1)))))
            norma = normas[0] if len(normas) == 1 else None
            out[j] = (norma, m.end())
            k = j + 1
            while k < fin and lineas[k].strip() and (not RE_ENTRADA.match(lineas[k])) and (not RE_ENCABEZADO_MD.match(lineas[k])):
                out[k] = (norma, 0)
                k += 1
            j = k
    return out

def _remite_al_informe(ln: str, a: int, b: int) -> bool:
    """Public CI documentation."""
    ini = ln.rfind('(', 0, a)
    if ini < 0 or ')' in ln[ini:a]:
        return False
    fin = ln.find(')', b)
    return bool(RE_REMITE_AL_INFORME.search(ln[ini + 1:fin if fin >= 0 else len(ln)]))

def localizar_citas(texto: str) -> list[CitaResuelta]:
    texto = unicodedata.normalize('NFC', texto)
    lineas = texto.split('\n')
    out: list[CitaResuelta] = []
    parrafo_de: dict[int, tuple[int, int]] = {}
    ini = 0
    for i, ln in enumerate(lineas + ['']):
        if not ln.strip() or ln.lstrip().startswith('#'):
            for j in range(ini, i):
                parrafo_de[j] = (ini, i)
            ini = i + 1
    seccion_de: dict[int, tuple[int, int]] = {}
    ini = 0
    for i, ln in enumerate(lineas + ['#']):
        if ln.lstrip().startswith('#'):
            for j in range(ini, i):
                seccion_de[j] = (ini, i)
            ini = i
    for j in range(len(lineas)):
        seccion_de.setdefault(j, (0, len(lineas)))
    vigente: str | None = None
    vigente_norma: str | None = None
    vigente_frase: tuple | None = None
    p_actual: tuple[int, int] | None = None
    entradas = entradas_de_fuentes(lineas)
    propios = anexos_propios(lineas)
    cabezas: dict[int, list[tuple[int, int]]] = {}
    elementos: dict[int, list[tuple[int, int, int | None, bool]]] = {}
    tipo_de_cabeza: dict[tuple[int, int], str | None] = {}
    abierto = False
    for k in range(len(lineas)):
        if k in entradas and entradas[k][1] > 0:
            abierto = False
        if k in entradas:
            elementos[k], abierto = _elementos_de_empleo(lineas[k], abierto)
            cabezas[k] = [(ini, sobre) for ini, _, sobre, _ in elementos[k] if sobre is not None]
        else:
            abierto = False
    vigente_apartado = False
    for i, ln in enumerate(lineas):
        if parrafo_de.get(i) != p_actual:
            p_actual, vigente, vigente_norma = (parrafo_de.get(i), None, None)
            vigente_frase = None
        refs = list(RE_REF.finditer(ln))
        if not refs:
            continue
        nombres = [m.span() for m in RE_NOMBRE_CON_ANEXO.finditer(ln)]
        for ref_txt, a, b in _encadenar(refs, ln, corta_en_cierre=i in entradas):
            if nombres:
                ajustada = _sin_el_nombre_de_la_norma(ln, ref_txt, a, b, nombres)
                if ajustada is None:
                    nd = CitaResuelta(linea=i + 1, referencia=ref_txt, ruta=ruta_de_cita(ref_txt), posicion=a, contexto=ln.strip()[:170])
                    nd.ambigua = True
                    nd.motivo = MOTIVO_NOMBRE_DE_DOCUMENTO
                    out.append(nd)
                    continue
                ref_txt, a, b = ajustada
            ruta = ruta_de_cita(ref_txt)
            ent = entradas.get(i)
            cabeza_con_sobre = bool(ent and ent[0] and any((x <= a and b <= y for x, y in cabezas.get(i, ()))))
            elemento = next(((ini, fin, abre) for ini, fin, _, abre in elementos.get(i, ()) if ini <= a < fin), None)
            abre_elemento = bool(ent and ent[0] and elemento and elemento[2] and (a == apertura_de_elemento(ln, elemento[0])))
            es_cabeza = cabeza_con_sobre or abre_elemento
            if ent and ent[0] and elemento and (not es_cabeza) and RX_Y_DE_HERMANA.search(ln[elemento[0]:a]):
                tipo = _tipo_de_referencia(ref_txt)
                es_cabeza = bool(tipo and tipo_de_cabeza.get((i, elemento[0])) == tipo)
            su_inicial = bool(ent and ent[0] and RX_SU_INICIAL.search(ln[:a]))
            anexo_del_informe = False
            if ent and (not cabeza_con_sobre) and (not su_inicial) and ruta:
                el_anexo = ruta.split('/')[0]
                if el_anexo.startswith('anexo.') and el_anexo[6:].upper() in propios:
                    p0 = re.match(RX_ENUMERACION_ANTES_DE_DE, ln[b:])
                    anexo_del_informe = not (p0 and RE_NORMA.match(ln[b + p0.end():]))
            if ent and (a < ent[1] or anexo_del_informe or _remite_al_informe(ln, a, b)):
                nd = CitaResuelta(linea=i + 1, referencia=ref_txt, ruta=ruta, posicion=a, contexto=ln.strip()[:170])
                nd.ambigua = True
                nd.motivo = MOTIVO_NOMBRE_DE_DOCUMENTO if a < ent[1] else MOTIVO_ANEXO_DEL_INFORME if anexo_del_informe else MOTIVO_REMITE_AL_INFORME
                out.append(nd)
                continue
            c = CitaResuelta(linea=i + 1, referencia=ref_txt, ruta=ruta, posicion=a, contexto=ln.strip()[:170])
            if es_cabeza and elemento:
                tipo_de_cabeza.setdefault((i, elemento[0]), _tipo_de_referencia(ref_txt))
            pegada = re.match(RX_ENUMERACION_ANTES_DE_DE if ent else RX_PEGADA_NORMA, ln[b:])
            propia = bool(pegada and RE_NORMA.match(ln[b + pegada.end():]))
            norma = ambito = None
            if propia:
                norma = RE_NORMA.match(ln[b + pegada.end():]).group(0)
                ambito = 'frase'
            elif ent and ent[0] and (es_cabeza or su_inicial):
                norma, ambito, c.por_entrada = (ent[0], 'frase', True)
            primer_nivel = propia or (c.por_entrada and bool(RX_CLAUSULA.match(ref_txt)))
            for ini_f, fin_f in frases(ln) if norma is None else ():
                if ini_f <= a < fin_f:
                    norma = _unica([m.group(0) for m in RE_NORMA.finditer(ln[ini_f:fin_f])])
                    if norma:
                        ambito = 'frase'
                    else:
                        n_frase = [m.group(0) for m in RE_NORMA.finditer(ln[ini_f:fin_f])]
                        if len(set(n_frase)) > 1:
                            c.ambigua = True
                            c.motivo = f'la frase nombra {len(set(n_frase))} normas y ninguna queda determinada'
                    break
            if norma is None and (not c.ambigua):
                p0, p1 = parrafo_de.get(i, (i, i + 1))
                bloque = '\n'.join(lineas[p0:p1])
                cand = [m.group(0) for m in RE_NORMA.finditer(bloque)]
                norma = _unica(cand)
                if norma:
                    ambito = 'parrafo'
                elif len(set(cand)) > 1:
                    c.ambigua = True
                    c.motivo = f'el parrafo nombra {len(set(cand))} normas distintas y la frase de la cita no nombra ninguna'
            if norma is None and (not c.ambigua):
                s0, s1 = seccion_de.get(i, (0, len(lineas)))
                cand = [m.group(0) for m in RE_NORMA.finditer('\n'.join(lineas[s0:s1]))]
                norma = _unica(cand)
                if norma:
                    ambito = 'seccion'
                else:
                    c.ambigua = True
                    c.motivo = 'ni la frase, ni el parrafo, ni la seccion determinan una norma unica' if cand else 'no hay ninguna norma nombrada en la seccion'
            frase_actual = (i, next((f for f in frases(ln) if f[0] <= a < f[1]), None))
            if norma != vigente_norma or ambito != 'frase' or frase_actual != vigente_frase:
                vigente = None
            hermana = _hermana(ruta, vigente, vigente_apartado) if c.por_entrada and es_cabeza and vigente and ruta else None
            if hermana:
                c.ruta = ruta = hermana
            elif ruta and ruta.startswith('ap.') and (not primer_nivel):
                if not vigente:
                    c.ambigua = True
                    c.motivo = 'apartado suelto: el parrafo no dice de que articulo o anexo de esa norma es'
                elif vigente.startswith(('anexo.', 'apend.')):
                    c.ruta = ruta = f'{vigente}/ap.{ruta[3:]}'
                else:
                    c.ruta = ruta = f'{vigente}.{ruta[3:]}'
            elif ruta and ruta.split('/')[0].startswith(('apend.', 'tabla.')) and vigente and vigente.startswith(('anexo.', 'apend.')) and (not primer_nivel):
                c.ruta = ruta = f'{vigente}/{ruta}'
            if ruta and (not ruta_de_cita(ref_txt).startswith('ap.')) and (ruta.split('.')[0] not in _ruta.SOLO_ATRIBUTO):
                vigente, vigente_norma, vigente_frase = (ruta, norma, frase_actual)
                vigente_apartado = bool(re.search('\\bapartados?\\b', ref_txt, re.I))
            s0, s1 = seccion_de.get(i, (0, len(lineas)))
            c.candidatas = tuple(dict.fromkeys((m.group(0) for m in RE_NORMA.finditer('\n'.join(lineas[s0:s1])))))
            c.cualificador = cualificador_perdido(ref_txt, c.ruta, ln[:a])
            c.norma, c.ambito = (norma, ambito)
            if not c.ambigua and division_que_cierra_enumeracion(ref_txt):
                c.ambigua = True
                c.motivo = 'la referencia enumera unidades y la cierra un anexo o un apendice: no se sabe si los contiene o es uno mas de la lista'
            if norma and (not c.ambigua):
                c.identificador = f'{norma}::{c.ruta}' if c.ruta else norma
            out.append(c)
    return out
