"""Public CI documentation."""
from __future__ import annotations
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from . import afirmaciones, revision

def _sin_tildes(s: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))
_UNIDADES_PALABRA = ('cero', 'un', 'una', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve')
_TEEN_VEINTI_PALABRA = ('diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiún', 'veintiuno', 'veintiuna', 'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho', 'veintinueve')
_DECENA_PALABRA = ('treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa')
_CENTENA_PALABRA = ('cien', 'ciento', 'doscientos', 'doscientas', 'trescientos', 'trescientas', 'cuatrocientos', 'cuatrocientas', 'quinientos', 'quinientas', 'seiscientos', 'seiscientas', 'setecientos', 'setecientas', 'ochocientos', 'ochocientas', 'novecientos', 'novecientas')
_VALOR_UNIDAD = {'cero': 0, 'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9}
_VALOR_TEEN_VEINTI = {'diez': 10, 'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15, 'dieciseis': 16, 'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19, 'veinte': 20, 'veintiun': 21, 'veintiuno': 21, 'veintiuna': 21, 'veintidos': 22, 'veintitres': 23, 'veinticuatro': 24, 'veinticinco': 25, 'veintiseis': 26, 'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29}
_VALOR_DECENA = {'treinta': 30, 'cuarenta': 40, 'cincuenta': 50, 'sesenta': 60, 'setenta': 70, 'ochenta': 80, 'noventa': 90}
_VALOR_CENTENA = {'cien': 100, 'ciento': 100, 'doscientos': 200, 'doscientas': 200, 'trescientos': 300, 'trescientas': 300, 'cuatrocientos': 400, 'cuatrocientas': 400, 'quinientos': 500, 'quinientas': 500, 'seiscientos': 600, 'seiscientas': 600, 'setecientos': 700, 'setecientas': 700, 'ochocientos': 800, 'ochocientas': 800, 'novecientos': 900, 'novecientas': 900}
_VALOR_SIMPLE = {**_VALOR_UNIDAD, **_VALOR_TEEN_VEINTI, **_VALOR_DECENA}

def _alt(*palabras: str) -> str:
    return '|'.join(sorted(palabras, key=len, reverse=True))
_NUM_PALABRA_PAT = '(?:(?:' + _alt(*_CENTENA_PALABRA) + ')(?:\\s+(?:(?:' + _alt(*_DECENA_PALABRA) + ')(?:\\s+y\\s+(?:' + _alt(*_UNIDADES_PALABRA) + '))?|(?:' + _alt(*_TEEN_VEINTI_PALABRA) + ')|(?:' + _alt(*_UNIDADES_PALABRA) + ')))?|(?:' + _alt(*_DECENA_PALABRA) + ')(?:\\s+y\\s+(?:' + _alt(*_UNIDADES_PALABRA) + '))?|(?:' + _alt(*_TEEN_VEINTI_PALABRA) + ')|(?:' + _alt(*_UNIDADES_PALABRA) + '))'
RE_NUM_PALABRA = re.compile('(?i)\\b' + _NUM_PALABRA_PAT + '\\b')

def _palabra_a_numero(cadena: str) -> int | None:
    """Public CI documentation."""
    tokens = [t for t in re.split('[\\s-]+', _sin_tildes(cadena.lower())) if t and t != 'y']
    if not tokens:
        return None
    valor, i = (0, 0)
    if tokens[i] in _VALOR_CENTENA:
        valor += _VALOR_CENTENA[tokens[i]]
        i += 1
    resto = tokens[i:]
    if not resto:
        return valor or None
    if len(resto) == 1 and resto[0] in _VALOR_SIMPLE:
        return valor + _VALOR_SIMPLE[resto[0]]
    if len(resto) == 2 and resto[0] in _VALOR_DECENA and (resto[1] in _VALOR_UNIDAD):
        return valor + _VALOR_DECENA[resto[0]] + _VALOR_UNIDAD[resto[1]]
    return None
TIEMPO_CORTO = 'tiempo_corto'
TIEMPO_LARGO = 'tiempo_largo'
_FACTOR_A_MINUTOS = {'minutos': 1.0, 'horas': 60.0, 'dias': 60.0 * 24, 'semanas': 60.0 * 24 * 7}
_FACTOR_A_MESES = {'meses': 1.0, 'anios': 12.0}
UNIDADES_SOLO_SOMBRA = frozenset({'euros', 'porcentaje', 'fecha'})

def clase(unidad: str) -> str:
    """Public CI documentation."""
    if unidad in _FACTOR_A_MINUTOS:
        return TIEMPO_CORTO
    if unidad in _FACTOR_A_MESES:
        return TIEMPO_LARGO
    return unidad

@dataclass(frozen=True)
class Cifra:
    unidad: str
    valor: float | tuple[float, float] | str
    texto: str
    inicio: int
    fin: int
    valor_confirmado: float | None = None

def _rango(v) -> tuple[float, float]:
    return v if isinstance(v, tuple) else (float(v), float(v))

def equivalentes(a: Cifra, b: Cifra) -> bool:
    """Public CI documentation."""
    if a.unidad == 'fecha' or b.unidad == 'fecha':
        return a.unidad == 'fecha' and b.unidad == 'fecha' and (a.valor == b.valor)
    if a.unidad == 'celsius' or b.unidad == 'celsius':
        if not (a.unidad == 'celsius' and b.unidad == 'celsius'):
            return False
        ra, rb = (_rango(a.valor), _rango(b.valor))
        return abs(ra[0] - rb[0]) < 1e-06 and abs(ra[1] - rb[1]) < 1e-06
    ca, cb = (clase(a.unidad), clase(b.unidad))
    if ca == cb == TIEMPO_CORTO:
        fa, fb = (_FACTOR_A_MINUTOS[a.unidad], _FACTOR_A_MINUTOS[b.unidad])
    elif ca == cb == TIEMPO_LARGO:
        fa, fb = (_FACTOR_A_MESES[a.unidad], _FACTOR_A_MESES[b.unidad])
    elif a.unidad == b.unidad:
        fa, fb = (1.0, 1.0)
    else:
        return False
    ra = tuple((v * fa for v in _rango(a.valor)))
    rb = tuple((v * fb for v in _rango(b.valor)))
    return abs(ra[0] - rb[0]) < 1e-06 and abs(ra[1] - rb[1]) < 1e-06
_UNIDAD_TIEMPO_RE = '(?:a[ñn]os?|mes(?:es)?|semanas?|d[ií]as?|horas?|minutos?)'
_NUM_DECIMAL_RE = '\\d{1,4}(?:[.,]\\d{1,2})?'
_NUM_O_PALABRA = '(?:' + _NUM_DECIMAL_RE + '|' + _NUM_PALABRA_PAT + ')'
RE_CANTIDAD = re.compile('(?i)\\b(?P<num>' + _NUM_O_PALABRA + ')\\b(?:\\s*\\(\\s*(?P<confirma>\\d{1,4})\\s*\\))?\\s+(?P<unidad>' + _UNIDAD_TIEMPO_RE + ')\\b')
_UNIDAD_TIEMPO_NORMAL = {'ano': 'anios', 'anos': 'anios', 'mes': 'meses', 'meses': 'meses', 'semana': 'semanas', 'semanas': 'semanas', 'dia': 'dias', 'dias': 'dias', 'hora': 'horas', 'horas': 'horas', 'minuto': 'minutos', 'minutos': 'minutos'}
RE_CANTIDAD_COMPUESTA = re.compile('(?i)\\b(?P<num1>' + _NUM_O_PALABRA + ')\\b\\s+(?P<unidad1>' + _UNIDAD_TIEMPO_RE + ')\\s+y\\s+(?P<num2>' + _NUM_O_PALABRA + ')\\b\\s+(?P<unidad2>' + _UNIDAD_TIEMPO_RE + ')\\b')
RE_RANGO_TIEMPO = re.compile('(?i)\\bentre\\s+(?P<lo>' + _NUM_O_PALABRA + ')\\b\\s+(?:a|y)\\s+(?P<hi>' + _NUM_O_PALABRA + ')\\b\\s+(?P<unidad>' + _UNIDAD_TIEMPO_RE + ')\\b|\\b(?P<lo2>' + _NUM_DECIMAL_RE + ')\\s*[-–—]\\s*(?P<hi2>' + _NUM_DECIMAL_RE + ')\\s+(?P<unidad2>' + _UNIDAD_TIEMPO_RE + ')\\b')
RE_PERIODICIDAD = re.compile('(?i)\\b(anual|bienal|semestral|trimestral|mensual)\\b')
_PERIODICIDAD = {'anual': ('anios', 1.0), 'bienal': ('anios', 2.0), 'semestral': ('meses', 6.0), 'trimestral': ('meses', 3.0), 'mensual': ('meses', 1.0)}
RE_UNA_VEZ = re.compile('(?i)\\buna\\s+vez\\s+al\\s+(añ?o|mes|semana|d[ií]a)\\b')
_UNA_VEZ_UNIDAD = {'ano': 'anios', 'ao': 'anios', 'mes': 'meses', 'semana': 'semanas', 'dia': 'dias'}
_SIGNO = '+\\-–−'
_NUM_SIMPLE = '[' + _SIGNO + ']?\\s*\\d+(?:[.,]\\d+)?'
_UNIDAD_CELSIUS_RE = '[°º]\\s*c\\b'
RE_TEMP_RANGO_PALABRA = re.compile('(?i)(?<![\\w.,])(?P<lo>' + _NUM_SIMPLE + ')\\s*(?P<u1>' + _UNIDAD_CELSIUS_RE + ')?\\s*(?:a|y)\\s*(?P<hi>' + _NUM_SIMPLE + ')\\s*(?(u1)(?:' + _UNIDAD_CELSIUS_RE + ')?|' + _UNIDAD_CELSIUS_RE + ')')
RE_TEMP_RANGO_GUION = re.compile('(?i)(?<![\\w.,])(?P<lo>' + _NUM_SIMPLE + ')\\s*(?P<u1>' + _UNIDAD_CELSIUS_RE + ')?\\s*[-–—]\\s*(?P<hi>' + _NUM_SIMPLE + ')\\s*(?(u1)(?:' + _UNIDAD_CELSIUS_RE + ')?|' + _UNIDAD_CELSIUS_RE + ')')
RE_TEMP_UNO = re.compile('(?i)(?<![\\w.,])(' + _NUM_SIMPLE + ')\\s*[°º]\\s*c\\b')
RE_TEMP_PALABRA = re.compile('(?i)\\bmenos\\s+(' + _NUM_PALABRA_PAT + ')\\s+grados\\b')
_MESES_PALABRA = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
_MESES_ABREV = {'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12}
RE_FECHA_LARGA = re.compile('(?i)\\b(\\d{1,2})\\s+de\\s+([a-zñ]+)\\s+de\\s+(\\d{4})\\b')
RE_FECHA_ABR = re.compile('(?i)\\b(\\d{1,2})-([a-zñ]{3,4})-(\\d{4})\\b')
RE_FECHA_NUM = re.compile('\\b(\\d{1,2})/(\\d{1,2})/(\\d{4})\\b')
RE_PORCENTAJE = re.compile('(?i)(?<![\\w.,])(?:(?P<pnum_d>\\d{1,3}(?:[.,]\\d+)?)\\s*%|(?P<pnum_t>' + _NUM_DECIMAL_RE + '|' + _NUM_PALABRA_PAT + ')\\s*por\\s+ciento\\b)')
RE_EUROS = re.compile('(?i)(?<![\\w.,])(?:(?P<enum_d>\\d{1,3}(?:\\.\\d{3})*(?:,\\d{1,2})?|\\d+(?:,\\d{1,2})?)\\s*(?:€|euros?\\b)|(?P<enum_t>' + _NUM_PALABRA_PAT + ')\\s*euros?\\b)')

def _valor_cantidad(num: str) -> float | None:
    """Public CI documentation."""
    num = num.strip()
    if re.fullmatch(_NUM_DECIMAL_RE, num):
        return float(num.replace(',', '.'))
    return _palabra_a_numero(num)

def _solapa(a: int, b: int, ocupado: list[tuple[int, int]]) -> bool:
    return any((a < y and x < b for x, y in ocupado))

def _es_enumeracion(texto: str, inicio: int, fin: int) -> bool:
    """Public CI documentation."""
    antes = re.split('[.;!?\\n]', texto[:inicio])[-1]
    despues = re.split('[.;!?\\n]', texto[fin:])[0]
    if re.search('(?i)\\brespectivamente\\b', antes + ' ' + despues):
        return True
    if re.search('(?i)\\b(?:total|suman?)\\b', antes):
        return False
    return bool(re.search('(?i)\\b(?:plazos|duraciones|per[ií]odos|periodicidades)\\b', antes))

def extraer(texto: str) -> list[Cifra]:
    """Public CI documentation."""
    cifras: list[Cifra] = []
    ocupado: list[tuple[int, int]] = []

    def _anota(a: int, b: int, unidad: str, valor, valor_confirmado: float | None=None) -> None:
        ocupado.append((a, b))
        cifras.append(Cifra(unidad, valor, texto[a:b], a, b, valor_confirmado))
    for m in RE_FECHA_LARGA.finditer(texto):
        mes = _MESES_PALABRA.get(_sin_tildes(m.group(2).lower()))
        if mes is None:
            continue
        dia, anio = (int(m.group(1)), int(m.group(3)))
        if not 1 <= dia <= 31:
            continue
        _anota(m.start(), m.end(), 'fecha', f'{anio:04d}-{mes:02d}-{dia:02d}')
    for m in RE_FECHA_ABR.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        mes = _MESES_ABREV.get(_sin_tildes(m.group(2).lower()))
        if mes is None:
            continue
        dia, anio = (int(m.group(1)), int(m.group(3)))
        if not 1 <= dia <= 31:
            continue
        _anota(m.start(), m.end(), 'fecha', f'{anio:04d}-{mes:02d}-{dia:02d}')
    for m in RE_FECHA_NUM.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        dia, mes, anio = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if not (1 <= dia <= 31 and 1 <= mes <= 12):
            continue
        _anota(m.start(), m.end(), 'fecha', f'{anio:04d}-{mes:02d}-{dia:02d}')
    for m in RE_TEMP_RANGO_PALABRA.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        _anota(m.start(), m.end(), 'celsius', (_num_con_signo(m.group('lo')), _num_con_signo(m.group('hi'))))
    for m in RE_TEMP_RANGO_GUION.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        _anota(m.start(), m.end(), 'celsius', (_num_con_signo(m.group('lo')), _num_con_signo(m.group('hi'))))
    for m in RE_TEMP_UNO.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        v = _num_con_signo(m.group(1))
        _anota(m.start(), m.end(), 'celsius', (v, v))
    for m in RE_TEMP_PALABRA.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        n = _palabra_a_numero(m.group(1))
        if n is None:
            continue
        _anota(m.start(), m.end(), 'celsius', (-float(n), -float(n)))
    for m in RE_RANGO_TIEMPO.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        g_lo, g_hi, g_unidad = ('lo', 'hi', 'unidad') if m.group('lo') is not None else ('lo2', 'hi2', 'unidad2')
        lo, hi = (_valor_cantidad(m.group(g_lo)), _valor_cantidad(m.group(g_hi)))
        if lo is None or hi is None:
            continue
        unidad = _UNIDAD_TIEMPO_NORMAL.get(_sin_tildes(m.group(g_unidad).lower()))
        if unidad is None:
            continue
        _anota(m.start(), m.end(), unidad, (lo, hi))
    for m in RE_CANTIDAD_COMPUESTA.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        v1, v2 = (_valor_cantidad(m.group('num1')), _valor_cantidad(m.group('num2')))
        if v1 is None or v2 is None:
            continue
        u1 = _UNIDAD_TIEMPO_NORMAL.get(_sin_tildes(m.group('unidad1').lower()))
        u2 = _UNIDAD_TIEMPO_NORMAL.get(_sin_tildes(m.group('unidad2').lower()))
        if u1 is None or u2 is None or u1 == u2 or (clase(u1) != clase(u2)):
            continue
        if _es_enumeracion(texto, m.start(), m.end()):
            continue
        factor = _FACTOR_A_MESES if clase(u1) == TIEMPO_LARGO else _FACTOR_A_MINUTOS
        _anota(m.start(), m.end(), u1, v1 + v2 * factor[u2] / factor[u1])
    for m in RE_CANTIDAD.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        valor = _valor_cantidad(m.group('num'))
        if valor is None:
            continue
        confirma = m.group('confirma')
        valor_confirmado = float(confirma) if confirma is not None else None
        unidad = _UNIDAD_TIEMPO_NORMAL.get(_sin_tildes(m.group('unidad').lower()))
        if unidad is None:
            continue
        _anota(m.start(), m.end(), unidad, valor, valor_confirmado)
    for m in RE_PERIODICIDAD.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        entrada = _PERIODICIDAD.get(_sin_tildes(m.group(1).lower()))
        if entrada is None:
            continue
        unidad, valor = entrada
        _anota(m.start(), m.end(), unidad, valor)
    for m in RE_UNA_VEZ.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        unidad = _UNA_VEZ_UNIDAD.get(_sin_tildes(m.group(1).lower()))
        if unidad is None:
            continue
        _anota(m.start(), m.end(), unidad, 1.0)
    for m in RE_PORCENTAJE.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        if m.group('pnum_d') is not None:
            valor = float(m.group('pnum_d').replace(',', '.'))
        else:
            valor = _valor_cantidad(m.group('pnum_t'))
        if valor is None:
            continue
        _anota(m.start(), m.end(), 'porcentaje', valor)
    for m in RE_EUROS.finditer(texto):
        if _solapa(m.start(), m.end(), ocupado):
            continue
        if m.group('enum_d') is not None:
            valor = _num_euro(m.group('enum_d'))
        else:
            v = _palabra_a_numero(m.group('enum_t'))
            if v is None:
                continue
            valor = float(v)
        _anota(m.start(), m.end(), 'euros', valor)
    cifras.sort(key=lambda c: c.inicio)
    return cifras

def _num_con_signo(s: str) -> float:
    s = s.strip()
    neg = bool(s) and s[0] in '-–−'
    s = s.lstrip('+-–−').strip().replace(',', '.')
    v = float(s)
    return -v if neg else v

def _num_euro(s: str) -> float:
    s = s.strip()
    if ',' in s:
        entero, _, dec = s.rpartition(',')
        return float(f"{entero.replace('.', '')}.{dec}")
    return float(s.replace('.', ''))

@dataclass(frozen=True)
class Hallazgo:
    tipo: str
    cifra_frase: Cifra
    cifras_precepto: tuple[Cifra, ...]
    identificador: str | None
    frase: str
    motivo: str

def _incoherencias(frase: str, identificador: str | None, cifras_frase: list[Cifra]) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    for cf in cifras_frase:
        if cf.valor_confirmado is not None and abs(cf.valor_confirmado - float(cf.valor)) >= 1e-06:
            salida.append(Hallazgo('incoherencia', cf, (), identificador, frase, f'la respuesta escribe "{cf.texto}": el número en letra/dígito ({cf.valor:g}) y el del paréntesis ({cf.valor_confirmado:g}) no coinciden; no se elige ninguno en silencio'))
    return salida
_RE_ETIQUETA_EXPLICITA = re.compile('\\b(?i:obligaci[oó]n)\\s+([A-Z0-9][A-Za-z0-9]{0,2})\\b')
_RE_ETIQUETA_ELIPTICA = re.compile('\\b(?:la|el)\\s+([A-ZÁÉÍÓÚÑ])\\b')

def _etiqueta(texto: str) -> str | None:
    m = _RE_ETIQUETA_EXPLICITA.search(texto)
    if m:
        return _sin_tildes(m.group(1)).lower()
    m = _RE_ETIQUETA_ELIPTICA.search(texto)
    if m:
        return _sin_tildes(m.group(1)).lower()
    return None

def _hay_desacuerdo(cifs: tuple[Cifra, ...]) -> bool:
    return any((not equivalentes(a, b) for i, a in enumerate(cifs) for b in cifs[i + 1:]))

def _segmentos_con_rango(texto: str) -> list[tuple[int, int, str]]:
    """Public CI documentation."""
    salida: list[tuple[int, int, str]] = []
    inicio = 0
    for m in re.finditer(';|\\n\\s*\\n', texto):
        salida.append((inicio, m.start(), texto[inicio:m.start()]))
        inicio = m.end()
    salida.append((inicio, len(texto), texto[inicio:]))
    return salida

def _etiqueta_precepto(texto_precepto: str, cp: Cifra) -> str | None:
    for ini, fin, seg in _segmentos_con_rango(texto_precepto):
        if ini <= cp.inicio <= fin:
            return _etiqueta(seg)
    return None
_RE_MARCA_PREVIA = re.compile('(?i)\\b(?:desde\\s+hace|han\\s+pasado|han\\s+sido|hace|lleva(?:n)?)\\s*$')
_RE_MARCA_POSTERIOR = re.compile('(?i)^\\s{0,3}de\\s+retraso\\b')

def _marca_hecho_del_caso(frase: str, cf: Cifra) -> bool:
    antes, despues = (frase[:cf.inicio], frase[cf.fin:])
    return bool(_RE_MARCA_PREVIA.search(antes[-24:]) or _RE_MARCA_POSTERIOR.match(despues))

def _marca_mencion_no_atribuida(frase: str, cf: Cifra, identificador: str | None=None) -> bool:
    """Public CI documentation."""
    if identificador:
        for m in re.finditer('\\([^()]*\\)', frase):
            if not (m.start() < cf.inicio and cf.fin < m.end()):
                continue
            guia = re.search('(?i)\\bseg[uú]n\\s+la\\s+gu[ií]a\\s+([a-z]+\\s*[-–]?\\s*\\d+)\\b', frase[cf.fin:m.end()])
            if guia:
                codigo = re.sub('[^a-z0-9]', '', _sin_tildes(guia.group(1)).lower())
                fundamento = re.sub('[^a-z0-9]', '', _sin_tildes(identificador).lower())
                if 'guia' + codigo not in fundamento:
                    return True
    antes = re.split('[;.!?\\n]', frase[:cf.inicio])[-1]
    despues = re.split('[;.!?\\n]', frase[cf.fin:])[0]
    clausula = re.split('(?i)\\bpero\\b|\\bsin embargo\\b|:', antes)[-1]
    if re.search('(?i)\\bno\\s+(?:ten[ií]a|conten[ií]a|inclu[ií]a|recog[ií]a|tiene|contiene|incluye|recoge|fija|fijaba)\\b[^;.!?\\n:]{0,120}$', clausula):
        return True
    if clase(cf.unidad) in (TIEMPO_LARGO, TIEMPO_CORTO) and re.search('(?i)\\bantes\\s+de\\s+que\\s+(?:transcurra|venza|finalice|termine)\\s+el\\s+plazo\\s+de\\s*$', antes[-100:]):
        return True
    segmento = antes + frase[cf.inicio:cf.fin] + despues
    for m in re.finditer('«[^»]*»|“[^”]*”|"[^"\\n]*"', segmento):
        if not (m.start() <= len(antes) and len(antes) + cf.fin - cf.inicio <= m.end()):
            continue
        if re.search('(?i)\\b(?:he|hemos)\\s+buscado\\b', segmento[max(0, m.start() - 240):m.start()]) and re.search('(?i)\\bno\\s+(?:aparece|consta|figura)\\b', segmento[m.end():m.end() + 150]):
            return True
    return False
_RE_MARCA_LIMITE = re.compile('(?i)\\b(dentro\\s+del?|fuera\\s+del?|no\\s+super\\w*|no\\s+exced\\w*|como\\s+m[aá]ximo|como\\s+m[ií]nimo|inferior\\s+a|superior\\s+a|por\\s+debajo\\s+del?|por\\s+encima\\s+del?|igual\\s+o\\s+inferior|igual\\s+o\\s+superior|m[aá]s\\s+\\w+\\s+que\\s+(?:es[ae]|el|la|dich[oa])\\s+(?:l[ií]mite|m[aá]ximo|m[ií]nimo|umbral|valor|cifra|tolerancia))\\b')

def _marca_limite(frase: str, cf: Cifra) -> bool:
    ventana = frase[max(0, cf.inicio - 40):cf.fin + 50]
    return bool(_RE_MARCA_LIMITE.search(ventana))
_RE_CUENTA = re.compile('(?i)(?<![\\w.,])[+\\-−]?\\s*\\d+(?:[.,]\\d+)?\\s*(?:°\\s*º?\\s*c)?\\s*(?:[+\\-−]|m[aá]s|menos)\\s*[+\\-−]?\\s*\\d+(?:[.,]\\d+)?\\s*(?:°\\s*º?\\s*c)?\\s*(?:=|es)\\s*$')

def _es_resultado_de_cuenta(frase: str, cf: Cifra) -> bool:
    ventana = frase[max(0, cf.inicio - 40):cf.inicio]
    return bool(_RE_CUENTA.search(ventana))

def contradicciones(frase: str, texto_precepto: str, pregunta: str | None=None, identificador: str | None=None) -> list[Hallazgo]:
    """Public CI documentation."""
    cifras_frase = extraer(frase)
    cifras_precepto = extraer(texto_precepto)
    cifras_pregunta = extraer(pregunta) if pregunta else []
    hallazgos: list[Hallazgo] = list(_incoherencias(frase, identificador, cifras_frase))
    cifras_incoherentes = {h.cifra_frase for h in hallazgos}
    for cf in cifras_frase:
        if cf in cifras_incoherentes:
            continue
        if any((equivalentes(cf, cp) for cp in cifras_pregunta)):
            continue
        misma_clase = tuple((cp for cp in cifras_precepto if clase(cp.unidad) == clase(cf.unidad)))
        if not misma_clase:
            hallazgos.append(Hallazgo('sin_respaldo', cf, (), identificador, frase, f'''la respuesta dice "{cf.texto}" y {identificador or 'el precepto'} no tiene ninguna cifra de esa unidad'''))
            continue
        etiqueta_frase = _etiqueta(frase)
        if etiqueta_frase and len(misma_clase) > 1:
            asociadas = tuple((cp for cp in misma_clase if _etiqueta_precepto(texto_precepto, cp) == etiqueta_frase))
            if _hay_desacuerdo(asociadas):
                hallazgos.append(Hallazgo('sin_respaldo', cf, asociadas, identificador, frase, f'''la respuesta dice "{cf.texto}": la etiqueta de obligación corresponde a varias cifras distintas de {identificador or 'el precepto'}; atribución ambigua, no contradicción'''))
                continue
        if any((equivalentes(cf, cp) for cp in misma_clase)):
            if len(misma_clase) > 1 and _hay_desacuerdo(misma_clase):
                etiquetas = {cp: _etiqueta_precepto(texto_precepto, cp) for cp in misma_clase}
                etiquetadas = [cp for cp in misma_clase if etiquetas[cp]]
                if len(etiquetadas) >= 2:
                    asociadas = tuple((cp for cp in etiquetadas if etiquetas[cp] == etiqueta_frase)) if etiqueta_frase else ()
                    cp_asociada = asociadas[0] if asociadas and (not _hay_desacuerdo(asociadas)) else None
                    if cp_asociada is not None:
                        if equivalentes(cf, cp_asociada):
                            continue
                        hallazgos.append(Hallazgo('contradiccion', cf, (cp_asociada,), identificador, frase, f'''la respuesta dice "{cf.texto}" y {identificador or 'el precepto'} dice "{cp_asociada.texto}" para esa misma obligación'''))
                        continue
                    hallazgos.append(Hallazgo('sin_respaldo', cf, misma_clase, identificador, frase, f'''la respuesta dice "{cf.texto}": coincide con alguna cifra de {identificador or 'el precepto'}, pero este tiene varias cifras de esa unidad para obligaciones distintas y la frase no dice con seguridad a cuál se refiere'''))
                    continue
            continue
        if _marca_mencion_no_atribuida(frase, cf, identificador):
            hallazgos.append(Hallazgo('sin_respaldo', cf, misma_clase, identificador, frase, f'''la respuesta menciona "{cf.texto}" como referencia, término ausente o inciso atribuido a otra guía; no lo atribuye a {identificador or 'el precepto'}: sin respaldo, no contradicción'''))
            continue
        if _marca_hecho_del_caso(frase, cf):
            hallazgos.append(Hallazgo('sin_respaldo', cf, misma_clase, identificador, frase, f'''la respuesta dice "{cf.texto}" junto a una marca de hecho del caso (no una afirmación sobre lo que dice {identificador or 'el precepto'}): como mucho sin respaldo, no contradicción'''))
            continue
        if _marca_limite(frase, cf):
            hallazgos.append(Hallazgo('sin_respaldo', cf, misma_clase, identificador, frase, f'''la respuesta dice "{cf.texto}" junto a una comparación con un intervalo o un límite (no una igualdad con lo que dice {identificador or 'el precepto'}): como mucho sin respaldo, no contradicción'''))
            continue
        if _es_resultado_de_cuenta(frase, cf):
            hallazgos.append(Hallazgo('sin_respaldo', cf, misma_clase, identificador, frase, f'''la respuesta dice "{cf.texto}" como resultado de una cuenta con cifras de la propia frase (no una afirmación de que {identificador or 'el precepto'} dice ese número): como mucho sin respaldo, no contradicción'''))
            continue
        hallazgos.append(Hallazgo('contradiccion', cf, misma_clase, identificador, frase, f'''la respuesta dice "{cf.texto}" y {identificador or 'el precepto'} dice "{' / '.join((cp.texto for cp in misma_clase))}"'''))
    return hallazgos
_RE_IDENT_A_BORRAR = (revision.RE_IDENT_TICK, revision.RE_IDENT_SUELTO, revision.RE_OBRA_SOLA)

def _sin_identificadores(texto: str) -> str:
    salida = texto
    for r in _RE_IDENT_A_BORRAR:
        salida = r.sub(lambda m: ' ' * len(m.group(0)), salida)
    return salida
_RE_FIN_DE_FRASE = re.compile('(?<=[.!?])\\s+(?=[A-ZÁÉÍÓÚÑ¿¡])')
_RE_INICIO_VINETA = re.compile('\\n(?=[ \\t]*(?:[-*•]|\\d{1,2}[.)]|[a-zA-Z][.)])\\s)')

def _frases(texto: str) -> list[tuple[int, int, str]]:
    salida: list[tuple[int, int, str]] = []
    for ini_p, fin_p in revision._bloques(texto):
        parrafo = texto[ini_p:fin_p]
        if not parrafo.strip():
            continue
        puntos_corte = {m.end() for m in _RE_FIN_DE_FRASE.finditer(parrafo)}
        puntos_corte.update((m.end() for m in _RE_INICIO_VINETA.finditer(parrafo)))
        cortes = [0] + sorted(puntos_corte) + [len(parrafo)]
        for a, b in zip(cortes, cortes[1:]):
            trozo = parrafo[a:b]
            recortada = trozo.strip()
            if not recortada:
                continue
            ini = ini_p + a + (len(trozo) - len(trozo.lstrip()))
            salida.append((ini, ini + len(recortada), recortada))
    return salida

def _racimo_entre_parentesis(frase: str, r_ini: int) -> bool:
    return frase[:r_ini].rstrip().endswith('(')

def _nombra_otra_norma(tramo: str, idents_r: list[str]) -> re.Match | None:
    for m in afirmaciones.RE_NORMA_NUMERADA.finditer(tramo):
        numero = m.group(2)
        if not any((numero in ident for ident in idents_r)):
            return m
    return None
_UMBRAL_RACIMO = 18

def _agrupa_citas(idents_frase: list[tuple[int, int, str]]) -> list[tuple[int, int, list[str]]]:
    """Public CI documentation."""
    racimos: list[list] = []
    for a, b, ident in sorted(idents_frase):
        if racimos and a - racimos[-1][1] <= _UMBRAL_RACIMO:
            racimos[-1][1] = max(racimos[-1][1], b)
            if ident not in racimos[-1][2]:
                racimos[-1][2].append(ident)
        else:
            racimos.append([a, b, [ident]])
    return [(a, b, idents_g) for a, b, idents_g in racimos]

def comprobar_respuesta(con: sqlite3.Connection, respuesta: str, pregunta: str | None=None) -> list[Hallazgo]:
    """Public CI documentation."""
    borrador = revision.sin_lineas_de_sello(respuesta)
    idents = revision.identificadores_del_borrador(borrador)
    bloques = revision._bloques(borrador)
    sin_ident = _sin_identificadores(borrador)
    hallazgos: list[Hallazgo] = []
    textos: dict[str, str] = {}
    confirmadas: dict[tuple[str, tuple[str, ...]], list[Cifra]] = {}

    def _texto_de(ident: str) -> str:
        if ident not in textos:
            try:
                _, texto_precepto = revision._texto_de(con, ident)
            except Exception:
                texto_precepto = ''
            textos[ident] = texto_precepto
        return textos[ident]

    def _coteja(trozo: str, idents_g: list[str]) -> None:
        texto_combinado = '\n'.join((t for i in idents_g if (t := _texto_de(i))))
        if not texto_combinado:
            return
        contexto = (re.sub('\\s+', ' ', trozo).strip(), tuple(sorted(set(idents_g))))
        previas = confirmadas.get(contexto, [])
        cifras_precepto = extraer(texto_combinado)
        hallazgos_trozo = contradicciones(trozo, texto_combinado, pregunta, identificador=', '.join(idents_g))
        for h in hallazgos_trozo:
            if h.tipo == 'contradiccion' and any((equivalentes(h.cifra_frase, c) for c in previas)):
                continue
            hallazgos.append(h)
        for cf in extraer(trozo):
            if any((equivalentes(cf, cp) for cp in cifras_precepto)) and (not any((h.cifra_frase == cf for h in hallazgos_trozo))):
                confirmadas.setdefault(contexto, []).append(cf)
    for ini, fin, frase_con_ident in _frases(borrador):
        frase = sin_ident[ini:ini + len(frase_con_ident)]
        if not frase.strip():
            continue
        idents_frase = [(a - ini, b - ini, i) for a, b, i in idents if ini <= a and b <= fin]
        if not idents_frase:
            candidatos = revision._identificadores_que_gobiernan(borrador, ini, idents, bloques)
            if candidatos:
                _coteja(frase, candidatos)
            continue
        desde = 0
        racimos = _agrupa_citas(idents_frase)
        for idx, (r_ini, r_fin, idents_r) in enumerate(racimos):
            fin_trozo = r_fin
            if not extraer(frase[desde:r_ini]) and (not _racimo_entre_parentesis(frase, r_ini)):
                limite = racimos[idx + 1][0] if idx + 1 < len(racimos) else len(frase)
                m_fin_clausula = re.search(';', frase[r_fin:limite])
                if m_fin_clausula is not None:
                    fin_trozo = r_fin + m_fin_clausula.start()
                elif idx + 1 == len(racimos):
                    fin_trozo = limite
                if fin_trozo != r_fin:
                    m_otra_norma = _nombra_otra_norma(frase[r_fin:fin_trozo], idents_r)
                    if m_otra_norma:
                        fin_trozo = r_fin + m_otra_norma.start()
            trozo = frase[desde:fin_trozo]
            if trozo.strip():
                _coteja(trozo, idents_r)
            desde = fin_trozo
    return hallazgos
