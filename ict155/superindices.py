"""Los exponentes en Unicode (R14, 11-oct-2026; docs/PREDICCION_exponentes_2026-10-11.md).

Xpdf aplana los superindices: `kg/m³` sale «kg/m3», `10¹²` sale «1012» y `10⁻⁶` sale «10-6». Esta pieza hace dos cosas:

 1. EXTRACCION. Con el testigo del PDF (PyMuPDF: `spans` con `flags & 1`, o mas pequenos y elevados) devuelve los exponentes a su forma de superindice Unicode
    (`⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺`), solo los que son exponentes. Las llamadas a nota al pie (un superindice detras de una palabra) no se convierten y se listan aparte con su criterio.
    Ningun otro caracter cambia.
 2. BUSQUEDA Y COTEJO. `plegar` lleva un texto a la forma que comparan las busquedas, y se aplica en los DOS lados: superindice -> su cifra o signo corrientes y el `^`
    delante de un exponente se quita. Asi «10^12», «10¹²» y «1012» son lo mismo, y «m3», «m^3» y «m³» tambien.
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass, field
SUPERINDICES = '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺'
PLANOS = '0123456789-+'
A_SUPERINDICE = str.maketrans(PLANOS, SUPERINDICES)
A_PLANO = str.maketrans(SUPERINDICES, PLANOS)
SIGNOS = '-−–‐‑‒﹣－+'
_A_CLAVE = str.maketrans({c: '-' for c in '−–‐‑‒﹣－'} | {'\xa0': ' '})
RX_CIRCUNFLEJO = re.compile('\\^(?=[-+−–]?\\d)')
RX_SUPERINDICE = re.compile('[' + SUPERINDICES + ']')
_MENOS = '-−–‐‑‒﹣－'

def a_superindice(s: str) -> str:
    """Las cifras y los signos de `s` en superindice («-6» -> «⁻⁶»; cualquier clase de menos pasa a «⁻»). El resto, igual."""
    out = []
    for c in s:
        if c in '0123456789':
            out.append(c.translate(A_SUPERINDICE))
        elif c in _MENOS:
            out.append('⁻')
        elif c == '+':
            out.append('⁺')
        else:
            out.append(c)
    return ''.join(out)

def plegar(s: str) -> str:
    """El texto para COMPARAR, igual en los dos lados: superindice -> cifra o signo corriente, y se quita el `^` delante de un exponente.
    «10^-6», «10⁻⁶» y «10-6» salen iguales; «m3», «m^3» y «m³» tambien. No toca nada mas (ni mayusculas ni acentos)."""
    if not s:
        return s
    if RX_SUPERINDICE.search(s):
        s = s.translate(A_PLANO)
    if '^' in s:
        s = RX_CIRCUNFLEJO.sub('', s)
    return s

def clave(s: str) -> str:
    """Para emparejar el texto de PyMuPDF con el de Xpdf: los signos menos de cualquier clase y el espacio duro, caracter por caracter (la longitud no cambia)."""
    return s.translate(_A_CLAVE)
UNIDADES = frozenset('m cm mm dm km µm μm nm g kg mg µg μg s ms µs μs ns h min A mA µA μA K mol cd Hz kHz MHz GHz N kN Pa kPa MPa hPa bar mbar J kJ\nW kW mW V kV mV µV μV Ω kΩ MΩ µΩ μΩ µF μF nF pF °C ºC l ml mL dl t lm lx dB ppm rad sr Bq Gy Sv Wh kWh Å'.split())
_UNA_LETRA = re.compile('^[a-zα-ωΑ-Ωµ]$|^[KVAWNJΩ]$')
_RE_POT10 = (re.compile('(?:^|[^0-9A-Za-z.,])10$'), re.compile('[0-9.,]+[×x*·⋅]10$'), re.compile('[×x*·⋅(/]10$'))
_PALABRAS_CORTAS = frozenset('de la el en un se su al es lo le of to in on at by or is it an as be if no up we do'.split())
EXPONENTE, NOTA, SIN_BASE, AMBIGUO, OTRO = ('exponente', 'nota', 'sin_base', 'ambiguo', 'otro')
_CIERRES = ')]}'
_APERTURAS = '([{'

def _grupo_final(base: str) -> tuple[str, bool]:
    """(contenido, abierto) del grupo entre parentesis o corchetes con que acaba `base`; `abierto` es si su apertura esta en el mismo token."""
    pila = 0
    for i in range(len(base) - 1, -1, -1):
        c = base[i]
        if c in _CIERRES:
            pila += 1
        elif c in _APERTURAS:
            pila -= 1
            if pila == 0:
                return (base[i + 1:-1], True)
    return (base[:-1], False)

def clasificar(base: str, texto: str, previa_exp: bool=False) -> tuple[str, str]:
    """(clase, motivo) de un superindice `texto` (cifras y signo) que va detras de `base` (el trozo del token que lo precede, sin espacios).

    EXPONENTE: potencia de diez; cualquier superindice con signo (una llamada a nota nunca lleva signo); una sola cifra 2 a 9 detras de un simbolo de
    unidad, de una variable de una letra minuscula o griega o de `2`; detras de un grupo entre parentesis con operaciones o de una variable
    (`[u(RS)/RS]²`, `(δx)²`, `(2¹⁰)⁸`). NOTA: detras de una palabra o sigla, de puntuacion, de un numero de varias cifras, de un numero o una sigla entre
    parentesis, o una cifra suelta 1 tras una unidad o letra. SIN_BASE: empieza el token. AMBIGUO: una letra mayuscula que no es unidad, o un grupo
    entre parentesis que no se sabe si es una expresion o una sigla. OTRO: el superindice no es solo cifras y signo.
    `previa_exp`: ya hay un exponente antes en el mismo token (`(2¹⁰)⁸`)."""
    m = re.fullmatch('([-−–‐‑‒+]?)(\\d{1,3})', texto.strip())
    if not m:
        return (OTRO, 'el superindice no es solo cifras y signo')
    signo, dig = m.groups()
    uno_a_nueve = len(dig) == 1 and dig != '1'
    if base == '':
        return (SIN_BASE, 'el superindice empieza el token (sin base)')
    if re.fullmatch('[(\\[]', base):
        return (NOTA, 'llamada a nota entre parentesis: (¹)')
    if any((rx.search(base) for rx in _RE_POT10)):
        return (EXPONENTE, 'potencia de diez')
    if re.search('[𝐀-𝟿]', base) and (not signo):
        return (AMBIGUO, 'formula con letras matematicas (el texto de la capa viene doblado y no se puede emparejar)')
    if signo:
        return (EXPONENTE, 'exponente con signo (una llamada a nota nunca lleva signo)')
    core = base
    if base[-1] in _CIERRES:
        if previa_exp and uno_a_nueve:
            return (EXPONENTE, 'detras de un grupo que ya lleva un exponente')
        contenido, abierto = _grupo_final(base)
        if abierto:
            if re.fullmatch('\\d{1,3}', contenido):
                return (NOTA, 'la base es un numero entre parentesis')
            if re.fullmatch('\\d{4}', contenido):
                return (NOTA, 'la base es un ano entre parentesis')
            if re.fullmatch('[A-ZÁÉÍÓÚÑ]{2,}[A-Z0-9/-]*', contenido) or re.fullmatch('[^\\W\\d_]{4,}', contenido):
                return (NOTA, 'detras de una sigla o una palabra entre parentesis')
            if re.search('[^\\W\\d_]{4,}|[A-ZÁÉÍÓÚÑ]{3,}|\\d{4}', contenido):
                return (NOTA, 'detras de un grupo entre parentesis con una palabra, una sigla o un ano')
            if not uno_a_nueve:
                return (NOTA, 'cifra suelta 1, o de varias cifras, tras un grupo entre parentesis')
            if re.search('[+\\-−/×·*=<>]|\\d[.,]\\d', contenido):
                return (EXPONENTE, 'detras de un grupo con operaciones o decimales')
            if re.fullmatch("[a-zα-ωµ][a-z0-9α-ωµ’'‘]{0,3}", contenido):
                return (EXPONENTE, 'detras de un grupo corto (una variable)')
            return (AMBIGUO, 'un grupo entre parentesis que no se sabe si es una expresion o una sigla')
        core = contenido
        mu = re.fullmatch('(.*?)([°º]?[A-Za-zµμΩ]{1,3})[-−](\\d)', core)
        if mu and mu.group(2) in UNIDADES:
            return (EXPONENTE, 'detras de una unidad con exponente negativo')
        if len(dig) == 1 and dig != '1' and (core not in _PALABRAS_CORTAS) and re.fullmatch("[a-zα-ωµ][a-z0-9α-ωµ’'‘]{1,2}", core):
            return (EXPONENTE, 'detras de un grupo corto (una variable) sin su apertura en el token')
    cerrado = core != base
    if re.search('[.,;:!?»”\\"’\']$', core):
        return (NOTA, 'detras de puntuacion')
    mt = re.search('([°º]?[^\\W\\d_]+)$', core)
    tail = mt.group(1) if mt else ''
    if mt:
        pre = core[:mt.start()]
        if re.fullmatch('[A-Za-z]+\\d+', pre) and len(tail) == 1:
            return (NOTA, 'codigo alfanumerico (letras, cifras y una letra)')
        if tail in UNIDADES:
            return (EXPONENTE, 'detras de simbolo de unidad') if uno_a_nueve else (NOTA, 'cifra suelta que no es 2..9 tras una unidad')
        if len(tail) == 1 and _UNA_LETRA.match(tail):
            return (EXPONENTE, 'detras de variable de una letra') if uno_a_nueve else (NOTA, 'cifra suelta que no es 2..9 tras una letra')
        if len(tail) == 2 and tail.islower() and (re.fullmatch('[a-z]{2}', tail) and tail[0] in 'uvsxyztn' and (tail[1] in 'ijklmnpqrc') or (re.fullmatch('[a-zα-ωµ]{2}', tail) and re.search('[α-ωµ]', tail))):
            return (EXPONENTE, 'detras de variable con subindice') if uno_a_nueve else (NOTA, 'cifra suelta tras dos letras')
        if len(tail) == 1:
            return (AMBIGUO, 'una letra mayuscula que no es unidad (variable o llamada)')
        return (NOTA, f'detras de una palabra o sigla ({len(tail)} letras)')
    if re.fullmatch('\\(?2', core) and (not cerrado):
        return (EXPONENTE, 'detras de una base de una cifra (2)')
    if cerrado and re.fullmatch('\\d{1,3}', core):
        return (AMBIGUO, 'un numero corto cerrado con parentesis sin su apertura')
    if re.search('\\d$', core):
        return (NOTA, 'detras de un numero')
    return (SIN_BASE, 'base sin letras ni cifras: ' + core[-3:])
TAM_MAXIMO = 0.7
ELEVACION_MINIMA = 0.3

@dataclass
class Corrida:
    """Un tramo de superindice dentro de un token."""
    ini: int
    fin: int
    texto: str
    clase: str
    motivo: str
    via: str
    tam: float
    base: str

@dataclass
class TokenPdf:
    texto: str
    corridas: list[Corrida] = field(default_factory=list)
    anterior: str = ''
    siguiente: str = ''
    inicio_linea: bool = False
    ant_txt: str = ''
    sig_txt: str = ''
    resto: int = 0

    @property
    def exponentes(self) -> list[Corrida]:
        return [c for c in self.corridas if c.clase == EXPONENTE]
_UNIDADES_DE_LONGITUD = frozenset('m cm mm dm km nm µm μm'.split())
_GRIEGAS = re.compile('[σμµαβγδεθλνρτφχψωΩ]')

def _admite_hueco(anterior: str, corrida: str) -> bool:
    """Si un superindice que empieza su token, separado por un blanco del token anterior, es el exponente de ese token. EUR-Lex, el GUM y el ATP emiten un
    espacio entre la base y el superindice —«10 –4», «μg/cm 2», «σ 2»—, y ahi una llamada a nota («0 °C 6», «0 Pa 2») se parece mucho a un exponente: solo se
    admite la base «10», un exponente CON signo tras una unidad o una letra griega, una longitud (m, cm, mm, dm...) con 2 o 3, una letra griega con 2 a 4 y
    V, A, W o K con 2."""
    if anterior == '10':
        return True
    if re.search('[.,;:!?)\\]}]$', anterior):
        return False
    m = re.search('([°º]?[^\\W\\d_]+)$', anterior)
    if not m:
        return False
    tail = m.group(1)
    mm = re.fullmatch('([-−–‐‑‒+]?)(\\d{1,3})', corrida.strip())
    if not mm:
        return False
    signo, dig = mm.groups()
    if signo:
        return tail in UNIDADES or bool(_GRIEGAS.fullmatch(tail))
    if tail in _UNIDADES_DE_LONGITUD:
        return dig in ('2', '3')
    if _GRIEGAS.fullmatch(tail):
        return dig in ('2', '3', '4')
    return tail in ('V', 'A', 'W', 'K') and dig == '2'

def _nucleo(trozo: str) -> str:
    return re.sub('[\\W_]+', '', trozo).casefold()

def _es_superindice(span: dict, previo: dict | None) -> tuple[bool, str, float]:
    t = span['text'].strip()
    if not t:
        return (False, '', 0.0)
    tam = span['size'] / previo['size'] if previo and previo['size'] else 1.0
    if span['flags'] & 1:
        return (True, 'flags', tam)
    if previo and re.fullmatch('[-−–+]?\\d{1,3}', t) and (tam <= TAM_MAXIMO) and (previo['origin'][1] - span['origin'][1] >= ELEVACION_MINIMA * previo['size']):
        return (True, 'geometria', tam)
    return (False, '', tam)

def tokens_de_pagina(pagina) -> list[TokenPdf]:
    """Los tokens de una pagina de PyMuPDF que llevan un superindice (con su clase), mas TODOS los demas tokens como texto plano para contar las apariciones
    sin superindice. Devuelve la lista completa en el orden de lectura de PyMuPDF."""
    out: list[TokenPdf] = []
    import fitz
    d = pagina.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    for b in d.get('blocks', []):
        for ln in b.get('lines', []):
            spans = [s for s in ln['spans']]
            texto = ''
            sup: list[tuple[bool, str, float]] = []
            previo = None
            for s in spans:
                es, via, tam = _es_superindice(s, previo)
                texto += s['text']
                sup.extend([(es, via, tam)] * len(s['text']))
                if s['text'].strip() and (not es):
                    previo = s
            toks = [(m.start(), m.end()) for m in re.finditer('\\S+', texto)]
            linea: list[TokenPdf] = []
            for ini, fin in toks:
                t = texto[ini:fin]
                tp = TokenPdf(texto=t)
                k = 0
                while k < len(t):
                    if sup[ini + k][0] and (not t[k].isspace()):
                        j = k
                        while j < len(t) and sup[ini + j][0]:
                            j += 1
                        via, tam = (sup[ini + k][1], sup[ini + k][2])
                        k0 = k
                        base = t[:k]
                        corrida = t[k:j]
                        if k > 0 and re.fullmatch('\\d{1,3}', corrida) and (t[k - 1] in SIGNOS) and any((rx.search(t[:k - 1]) for rx in _RE_POT10)):
                            k0 = k - 1
                            corrida = t[k0:j]
                            base = t[:k0]
                        cl, mot = clasificar(base, corrida, previa_exp=any((c.clase == EXPONENTE for c in tp.corridas)))
                        tp.corridas.append(Corrida(k0, j, corrida, cl, mot, via, round(tam, 2), base))
                        k = j
                    else:
                        k += 1
                linea.append(tp)
            fusion: list[TokenPdf] = []
            for tp in linea:
                if fusion and tp.corridas and (tp.corridas[0].ini == 0) and (not fusion[-1].corridas) and _admite_hueco(fusion[-1].texto, tp.corridas[0].texto):
                    previo_tp = fusion.pop()
                    resto = len(previo_tp.texto) + 1
                    nuevo = TokenPdf(texto=previo_tp.texto + ' ' + tp.texto, resto=resto)
                    for c in tp.corridas:
                        cl, mot = clasificar(previo_tp.texto, c.texto) if c.ini == 0 else (c.clase, c.motivo)
                        nuevo.corridas.append(Corrida(c.ini + resto, c.fin + resto, c.texto, cl, mot, c.via, c.tam, previo_tp.texto if c.ini == 0 else c.base))
                    fusion.append(nuevo)
                else:
                    fusion.append(tp)
            if fusion:
                fusion[0].inicio_linea = True
            out.extend(fusion)
    for i, tp in enumerate(out):
        tp.anterior = _nucleo(out[i - 1].texto) if i else ''
        tp.siguiente = _nucleo(out[i + 1].texto) if i + 1 < len(out) else ''
        tp.ant_txt = out[i - 1].texto if i else ''
        tp.sig_txt = out[i + 1].texto if i + 1 < len(out) else ''
        for c in tp.corridas:
            if c.clase != SIN_BASE:
                continue
            if tp.ant_txt.endswith('(') and tp.sig_txt.startswith(')'):
                c.clase, c.motivo = (NOTA, 'llamada a nota entre parentesis sueltos: ( ¹ )')
            elif tp.inicio_linea and c.ini == 0 and (c.fin == len(tp.texto)):
                c.clase, c.motivo = (NOTA, 'numero de la nota al pie, solo al principio del renglon')
    return out

def _abrir(ruta):
    try:
        import fitz
    except Exception:
        return None
    try:
        return fitz.open(str(ruta))
    except Exception:
        return None

def tokens_del_pdf(ruta) -> list[list[TokenPdf]] | None:
    """Los tokens de cada pagina del PDF, o None si PyMuPDF no esta o no abre el fichero."""
    doc = _abrir(ruta)
    if doc is None:
        return None
    try:
        return [tokens_de_pagina(p) for p in doc]
    except Exception:
        return None
    finally:
        doc.close()

@dataclass
class Registro:
    """Un exponente que cambia, o uno que no se pudo convertir, con su porque."""
    pagina: int
    antes: str
    despues: str
    clase: str
    motivo: str
    como: str
    contexto: str = ''

def _vecinos(texto: str, ini: int, fin: int) -> tuple[str, str]:
    i, j = (ini, fin)
    while i > 0 and (not texto[i - 1].isspace()):
        i -= 1
    while j < len(texto) and (not texto[j].isspace()):
        j += 1
    antes = texto[max(0, i - 200):i].split()[-1:]
    despues = texto[j:j + 200].split()[:1]
    return (_nucleo(antes[0]) if antes else '', _nucleo(despues[0]) if despues else '')

def _como(tp: TokenPdf, c: Corrida) -> str:
    return f"PyMuPDF: superindice «{c.texto}» ({('marca flags=1' if c.via == 'flags' else 'sin marca pero a ' + format(c.tam, '.2f') + ' del cuerpo y elevado')}, tamano {c.tam:.2f} del cuerpo) detras de «{c.base}»: {c.motivo}"

def convertir_pagina(x: str, tokens: list[TokenPdf], numero: int) -> tuple[str, list[Registro]]:
    """La pagina `x` (texto de Xpdf o de la capa) con los exponentes de `tokens` (los de PyMuPDF de la misma pagina) en superindice, y que paso con cada uno."""
    registros: list[Registro] = []
    for tp in tokens:
        for c in tp.corridas:
            if c.clase != EXPONENTE:
                registros.append(Registro(numero, tp.texto, tp.texto, c.clase, c.motivo, f'PyMuPDF: superindice «{c.texto}» detras de «{c.base}»; no se convierte', f'{tp.anterior} {tp.siguiente}'.strip()))
    marcados = [tp for tp in tokens if tp.exponentes]
    if not marcados:
        return (x, registros)
    kx = clave(x)
    por_clave: dict[str, list[tuple[tuple[int, ...], TokenPdf]]] = {}
    for tp in tokens:
        mascara = tuple(sorted((i for c in tp.exponentes for i in range(c.ini, c.fin))))
        por_clave.setdefault(clave(tp.texto), []).append((mascara, tp))
    cambios: list[tuple[int, int, str, str, TokenPdf]] = []
    vistos: set[str] = set()
    for tp in marcados:
        k = clave(tp.texto)
        if k in vistos:
            continue
        vistos.add(k)
        ocurrencias_m = por_clave[k]
        mascaras = {m for m, _ in ocurrencias_m}
        if ' ' in k:
            primera, segunda = k.split(' ', 1)
            rx = re.compile('(?<!\\S)' + re.escape(primera) + '(\\s*)' + re.escape(segunda) + '(?!\\S)')
        else:
            rx = re.compile('(?<!\\S)' + re.escape(k) + '(?!\\S)')
        encontradas = list(rx.finditer(kx))
        if ' ' in k and len(encontradas) != len(ocurrencias_m):
            for m, t in ocurrencias_m:
                for c in t.exponentes:
                    registros.append(Registro(numero, t.texto, t.texto, 'ambiguo_en_texto' if encontradas else 'no_localizado', 'la base y el superindice van separados en el PDF y el texto de la pagina no tiene tantas coincidencias como exponentes', _como(t, c), f'{t.anterior} {t.siguiente}'.strip()))
            continue
        if not encontradas:
            for m, t in ocurrencias_m:
                if m:
                    for c in t.exponentes:
                        registros.append(Registro(numero, t.texto, t.texto, 'no_localizado', 'el token no esta en el texto de la pagina', _como(t, c) + '; Xpdf no tiene ese token', f'{t.anterior} {t.siguiente}'.strip()))
            continue
        for h in encontradas:
            if len(mascaras) == 1:
                mascara = next(iter(mascaras))
                tp_m = ocurrencias_m[0][1]
                metodo = 'Xpdf: ese token solo existe en la pagina del PDF con superindice'
            else:
                ant, sig = _vecinos(x, h.start(), h.end())
                puntos = []
                for m, t in ocurrencias_m:
                    puntos.append((int(ant != '' and ant == t.anterior) + int(sig != '' and sig == t.siguiente), m, t))
                mejor = max((p for p, _, _ in puntos))
                finalistas = [(m, t) for p, m, t in puntos if p == mejor]
                if mejor == 0 or len({m for m, _ in finalistas}) != 1:
                    for m, t in ocurrencias_m:
                        if m:
                            for c in t.exponentes:
                                registros.append(Registro(numero, x[h.start():h.end()], x[h.start():h.end()], 'ambiguo_en_texto', 'el mismo token aparece con y sin superindice en la pagina y los vecinos no deciden', _como(t, c), f'{t.anterior} {t.siguiente}'.strip()))
                    continue
                mascara, tp_m = finalistas[0]
                metodo = f'Xpdf: el token existe con y sin superindice; elegido por los vecinos «{ant}» y «{sig}»'
            if not mascara:
                continue
            if ' ' in k:

                def posicion(i, h=h, primera=primera):
                    return h.end(1) + (i - (len(primera) + 1))
            else:

                def posicion(i, h=h):
                    return h.start() + i
            antes = x[h.start():h.end()]
            nuevo = list(antes)
            valido = True
            for i in mascara:
                pos = posicion(i) - h.start()
                c = antes[pos] if 0 <= pos < len(antes) else ''
                if c == '' or c not in '0123456789' + SIGNOS:
                    valido = False
                    break
                nuevo[pos] = a_superindice(c)
            if valido:
                despues = ''.join(nuevo)
                cambios.append((h.start(), h.end(), antes, despues, tp_m))
                motivo = '; '.join(dict.fromkeys((c.motivo for c in tp_m.exponentes)))
                como = ' | '.join((_como(tp_m, c) for c in tp_m.exponentes)) + '; ' + metodo
                registros.append(Registro(numero, antes, despues, EXPONENTE, motivo, como, f'{tp_m.anterior} {tp_m.siguiente}'.strip()))
            else:
                registros.append(Registro(numero, antes, antes, 'no_localizado', 'los caracteres del texto no son los del exponente', _como(tp_m, tp_m.exponentes[0]), ''))
    for ini, fin, antes, despues, _ in sorted(cambios, key=lambda c: c[0], reverse=True):
        x = x[:ini] + despues + x[fin:]
    return (x, registros)

def exponentes_con_testigo(ruta, ruta_rel: str, paginas: list[str]) -> tuple[list[str], str, list[Registro]]:
    """(paginas con los exponentes en superindice, nota para `motor_extraccion` («» si todo fue normal), registros de lo que cambia y de lo que no).
    Sin PyMuPDF, o con otro numero de paginas que Xpdf, no se convierte nada y se dice (solo si el PDF tiene algun exponente)."""
    pdf = tokens_del_pdf(ruta)
    if pdf is None:
        print(f'aviso: {ruta_rel}: PyMuPDF no esta disponible o no abre el PDF: los exponentes no se pueden comprobar y no se convierten', file=sys.stderr)
        return (paginas, '; exponentes sin testigo: PyMuPDF no disponible', [])
    if len(pdf) != len(paginas):
        if any((tp.exponentes for pg in pdf for tp in pg)):
            motivo = f'{len(paginas)} paginas con Xpdf y {len(pdf)} con PyMuPDF'
            print(f'aviso: {ruta_rel} tiene exponentes y no se pueden comprobar contra el PDF ({motivo}): no se convierten', file=sys.stderr)
            return (paginas, f'; exponentes sin testigo: {motivo}', [])
        return (paginas, '', [])
    salida: list[str] = []
    registros: list[Registro] = []
    for i, (x, toks) in enumerate(zip(paginas, pdf)):
        nueva, regs = convertir_pagina(x, toks, i + 1)
        salida.append(nueva)
        registros.extend(regs)
    return (salida, '', registros)
