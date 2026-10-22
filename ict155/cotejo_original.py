"""Public CI documentation."""
from __future__ import annotations
import argparse
import functools
import json
import os
import random
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from . import config, consulta, db, historial_boe, mobiliario, vigencia
from .vigencia import ErrorDeFuente
OK = 'OK'
DISTINTO = 'DISTINTO'
SIN_TESTIGO = 'SIN_TESTIGO'
SIN_CONSULTA = 'SIN_CONSULTA'
ESTADOS = (OK, DISTINTO, SIN_TESTIGO, SIN_CONSULTA)
BOE, UE, PDF, OCR = ('boe', 'ue', 'pdf', 'ocr')
FAMILIAS = (BOE, UE, PDF)
ROTULO = {BOE: 'el BOE', UE: 'EUR-Lex', PDF: 'el PDF'}
TEXTO_SIN_TESTIGO = 'este literal no se puede cotejar con un original (texto de reconocimiento óptico o sin texto oficial): cita la cláusula y la página sin entrecomillar'
TEXTO_SIN_CONSULTA = 'sin consulta del texto oficial: rehacerla con `ict155.cli cotejo --actualizar`'
ESTADO_OK = 'ok'
ESTADO_SIN_TEXTO = 'sin_testigo'
ESTADO_ERROR = 'error'
ESQUEMA = 1
NOMBRE_BOE = 'texto_oficial_boe.json'
NOMBRE_UE = 'texto_oficial_ue.json'
ENV_DIR = 'ICT155_COTEJO_DIR'
USER_AGENT = 'ict155-bd-normativa (cotejo con el original)'
TIMEOUT = 120
PAUSA = 1.0
REINTENTOS = 1
ESPERA_REINTENTO = 3.0
URL_CELLAR = 'https://publications.europa.eu/resource/celex/{}'
LENGUAS_CELLAR = {'es': 'spa', 'en': 'eng', 'fr': 'fra', 'de': 'deu', 'it': 'ita', 'pt': 'por'}
AVISO_BOE = 'Fuente: Agencia Estatal Boletín Oficial del Estado; el texto consolidado es informativo'
AVISO_CELLAR = 'Fuente: Oficina de Publicaciones de la UE (CELLAR); solo el Diario Oficial es auténtico'
MARGEN_DE_PAGINAS = 1
MAX_TROZO = 600
DIAS_DE_VALIDEZ = 30

def _tabla() -> dict[int, str | None]:
    """Public CI documentation."""
    t: dict[int, str | None] = {}
    for cp in (8216, 8217, 8218, 8219, 8242, 180, 96, 700):
        t[cp] = "'"
    for cp in (8220, 8221, 8222, 8223, 8243, 171, 187):
        t[cp] = '"'
    for cp in (8208, 8209, 8210, 8211, 8212, 8213, 8722, 8259, 65112, 65123, 65293):
        t[cp] = '-'
    for cp in (8203, 8204, 8205, 8288, 65279):
        t[cp] = None
    for cp in (*range(0, 9), *range(14, 32), *range(127, 160)):
        t[cp] = None
    return t
_TABLA = _tabla()
MARCAS_DE_CONSOLIDACION = ''.join((chr(cp) for cp in (9658, 9668, 9660, 9650)))
RE_MARCAS = re.compile('[' + MARCAS_DE_CONSOLIDACION + ']\\s*(?:M\\d+|C\\d+|A\\d+|X\\d+|E\\d+|B(?!\\w))?')
RE_GUION_BLANDO = re.compile(chr(173) + '[ \\t]*(?:\\r?\\n[ \\t]*)?')
RE_GUION_DE_RENGLON = re.compile('(?<=\\w)-[ \\t]*\\r?\\n[ \\t]*(?=(\\w))')
RE_ESPACIOS = re.compile('\\s+')
RE_ESPACIO_DENTRO = re.compile('(?<=[(\\[])\\s+|\\s+(?=[)\\],;:.])')
RE_N_O = re.compile('\\b([Nn])(?:\\s*\\.\\s*|\\s+)o\\b(?=\\s*\\d)|\\b([Nn])\\s*' + chr(176) + '(?=\\s*\\d)')
RE_SIGNOS = re.compile('\\s*([' + ''.join((chr(cp) for cp in (177, 8805, 8804, 8800, 8776, 215, 247))) + '=<>])\\s*')
RE_CIFRA_PORCIENTO = re.compile('(?<=\\d)\\s+%')
RE_LIGADURA_Y_HUECO = re.compile('([' + ''.join((chr(cp) for cp in range(64257, 64261))) + '])[ \\t]+(?=[^\\W\\d_])')

def _unir_guion(m: re.Match) -> str:
    return '' if m.group(1).islower() else '-'

def _normalizar(texto: str, guion: str, ligadura: bool=False) -> str:
    t = (texto or '').translate(_TABLA)
    if ligadura:
        t = RE_LIGADURA_Y_HUECO.sub('\\1', t)
    t = unicodedata.normalize('NFKC', t).translate(_TABLA)
    t = RE_GUION_BLANDO.sub('', t)
    t = RE_MARCAS.sub(' ', t)
    t = RE_GUION_DE_RENGLON.sub(_unir_guion if guion == 'unir' else '-', t)
    t = RE_ESPACIOS.sub(' ', t)
    t = RE_ESPACIO_DENTRO.sub('', t)
    t = RE_N_O.sub(lambda m: (m.group(1) or m.group(2)) + 'o', t)
    t = RE_SIGNOS.sub('\\1', t)
    t = RE_CIFRA_PORCIENTO.sub('%', t)
    return t.strip()

def normalizar(texto: str) -> str:
    """Public CI documentation."""
    return _normalizar(texto, 'unir')

@functools.lru_cache(maxsize=512)
def normalizar_testigo(texto: str) -> tuple[str, ...]:
    """Public CI documentation."""
    plano = (texto or '').translate(_TABLA)
    lecturas = [('unir', False)]
    if RE_GUION_DE_RENGLON.search(plano):
        lecturas.append(('conservar', False))
    if RE_LIGADURA_Y_HUECO.search(plano):
        lecturas += [(g, True) for g, _ in list(lecturas)]
    return tuple(dict.fromkeys((_normalizar(texto, g, l) for g, l in lecturas)))

def _limite_ok(t: str, i: int, f: str) -> bool:
    """Public CI documentation."""
    fin = i + len(f)
    antes = i == 0 or not (f[0].isalnum() and t[i - 1].isalnum())
    despues = fin == len(t) or not (f[-1].isalnum() and t[fin].isalnum())
    return antes and despues

def _buscar(t: str, f: str, desde: int) -> int:
    """Public CI documentation."""
    for candidato in dict.fromkeys((f, f[:1].swapcase() + f[1:])):
        i = t.find(candidato, desde)
        while i >= 0:
            if _limite_ok(t, i, candidato):
                return i
            i = t.find(candidato, i + 1)
    return -1

def _en_orden(trozos: list[str], t: str) -> int:
    """Public CI documentation."""
    desde = n = 0
    for f in trozos:
        i = _buscar(t, f, desde)
        if i < 0:
            return n
        desde, n = (i + len(f), n + 1)
    return n
RE_ENFASIS = re.compile('(?<![\\w*])(\\*\\*|\\*)(?=[^\\s*])(.+?)(?<=[^\\s*])\\1(?![\\w*])|(?<![\\w_])(__|_)(?=[^\\s_])(.+?)(?<=[^\\s_])\\3(?![\\w_])')
BORDES_DEL_LITERAL = ' "\'.,;:'

def _sin_enfasis(s: str) -> str:
    return RE_ENFASIS.sub(lambda m: m.group(2) or m.group(4), s)

def _trozos(fragmentos: list[str]) -> list[str]:
    """Public CI documentation."""
    return [x for x in (normalizar(_sin_enfasis(f)).strip(BORDES_DEL_LITERAL) for f in fragmentos) if x]

def esta_en(fragmentos: list[str], testigo: str) -> bool:
    """Public CI documentation."""
    trozos = _trozos(fragmentos)
    if not trozos:
        return True
    return any((_en_orden(trozos, t) == len(trozos) for t in normalizar_testigo(testigo)))

def _primer_fragmento_que_falta(trozos: list[str], t: str) -> str | None:
    desde = 0
    for f in trozos:
        i = _buscar(t, f, desde)
        if i < 0:
            return f
        desde = i + len(f)
    return None
VENTANAS_COMO_MUCHO = 80

def _donde(falta: str, t: str) -> tuple[int, int] | None:
    """Public CI documentation."""
    pf = falta.split()
    n = len(pf)
    desplazamiento, acumulado = ([], 0)
    for p in pf:
        desplazamiento.append(acumulado)
        acumulado += len(p) + 1
    ancho = max(30, len(falta) // 2)
    votos: dict[int, int] = {}
    for k in dict.fromkeys((min(x, n) for x in (4, 3, 2, 1))):
        for i in range(min(n - k + 1, VENTANAS_COMO_MUCHO)):
            ventana = ' '.join(pf[i:i + k])
            pos, veces = (t.find(ventana), 0)
            while pos >= 0 and veces < 6:
                cubo = (pos - desplazamiento[i]) // ancho
                votos[cubo] = votos.get(cubo, 0) + k
                pos, veces = (t.find(ventana, pos + 1), veces + 1)
        if votos:
            break
    if not votos:
        return None
    mejor = max(votos, key=lambda c: votos[c] + votos.get(c - 1, 0) + votos.get(c + 1, 0))
    return (mejor * ancho, ancho)

def zona_del_testigo(texto_de_la_base: str, testigo: str, maximo: int=4000) -> str | None:
    """Public CI documentation."""
    t = normalizar_testigo(testigo)[0]
    b = normalizar(texto_de_la_base)
    palabras = b.split()
    sitio = _donde(' '.join(palabras[:VENTANAS_COMO_MUCHO]), t) if b else None
    if sitio is None:
        return None
    inicio, ancho = sitio
    cabeza = t.find(' '.join(palabras[:3]), max(0, inicio - ancho))
    inicio = cabeza if 0 <= cabeza <= inicio + 2 * ancho else inicio
    zona = t[inicio:inicio + len(b) + 300]
    return zona if len(zona) <= maximo else zona[:maximo - 1] + '…'

def trozo_parecido(fragmentos: list[str], testigo: str, maximo: int=MAX_TROZO) -> str | None:
    """Public CI documentation."""
    import difflib
    trozos = _trozos(fragmentos)
    t = normalizar_testigo(testigo)[0]
    falta = _primer_fragmento_que_falta(trozos, t)
    if not falta:
        return None
    pf = falta.split()
    n = len(pf)
    sitio = _donde(falta, t)
    if sitio is None:
        return None
    inicio, ancho = sitio
    ini = t.rfind(' ', 0, max(0, inicio - ancho)) + 1
    pw = t[ini:ini + len(falta) * 2 + 4 * ancho].split()
    bloques = [b for b in difflib.SequenceMatcher(None, pw, pf, autojunk=False).get_matching_blocks() if b.size]
    if not bloques:
        return None
    a0 = max(0, bloques[0].a - bloques[0].b)
    a1 = min(len(pw), bloques[-1].a + (n - bloques[-1].b))
    original = ' '.join(pw[a0:a1])
    return original if len(original) <= maximo else original[:maximo - 1] + '…'
_ultima_peticion = [0.0]

def _descargar_ue(url: str, lengua: str) -> tuple[int, bytes]:
    """Public CI documentation."""
    espera = PAUSA - (time.monotonic() - _ultima_peticion[0])
    if espera > 0:
        time.sleep(espera)
    peticion = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/xhtml+xml', 'Accept-Language': lengua})
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as r:
            return (r.status, r.read())
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read()
        except Exception:
            cuerpo = b''
        return (e.code, cuerpo)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        servidor = urllib.parse.urlsplit(url).netloc
        raise ErrorDeFuente(f"sin respuesta de {servidor}: {getattr(e, 'reason', e)}") from e
    finally:
        _ultima_peticion[0] = time.monotonic()

def _pedir_ue(url: str, lengua: str) -> tuple[int, bytes]:
    for intento in range(REINTENTOS + 1):
        ultimo = intento == REINTENTOS
        try:
            codigo, cuerpo = _descargar_ue(url, lengua)
        except ErrorDeFuente:
            if ultimo:
                raise
        else:
            if codigo < 500 or ultimo:
                return (codigo, cuerpo)
        time.sleep(ESPERA_REINTENTO)
    raise ErrorDeFuente('sin respuesta')

def _plano(e: ET.Element) -> str:
    """Public CI documentation."""
    partes = [e.text or '']
    for h in e:
        partes.append(' ' if h.tag == 'br' else _plano(h))
        partes.append(h.tail or '')
    return ''.join(partes)

def _texto_de_hijo(e: ET.Element) -> list[str]:
    """Public CI documentation."""
    if e.tag == 'table':
        filas = []
        for tr in e.iter('tr'):
            celdas = [' '.join(_plano(c).split()) for c in tr if c.tag in ('td', 'th')]
            filas.append(' '.join((c for c in celdas if c)))
        titulo = [' '.join(_plano(c).split()) for c in e if c.tag == 'caption']
        return [x for x in titulo + filas if x]
    if e.tag in ('p', 'caption', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6') or not len(e):
        t = ' '.join(_plano(e).split())
        return [t] if t else []
    salida: list[str] = []
    for h in e:
        salida.extend(_texto_de_hijo(h))
    return salida

def texto_de_version(version: ET.Element) -> str:
    """Public CI documentation."""
    renglones: list[str] = []
    for h in version:
        renglones.extend(_texto_de_hijo(h))
    return '\n'.join(renglones)

def version_vigente(versiones: list[ET.Element], hoy: str) -> ET.Element | None:
    """Public CI documentation."""
    if not versiones:
        return None

    def efecto(v: ET.Element) -> str:
        return vigencia._fecha_boe(v.get('fecha_vigencia')) or vigencia._fecha_boe(v.get('fecha_publicacion')) or ''
    en_vigor = [(efecto(v), i, v) for i, v in enumerate(versiones) if efecto(v) <= hoy]
    return max(en_vigor, key=lambda t: (t[0], t[1]))[2] if en_vigor else versiones[-1]

def textos_de_bloques(cuerpo: bytes, hoy: str) -> list[str]:
    """Public CI documentation."""
    raiz = ET.fromstring(cuerpo)
    texto = raiz.find('data/texto')
    salida = []
    for b in texto.findall('bloque') if texto is not None else []:
        v = version_vigente(b.findall('version'), hoy)
        salida.append(texto_de_version(v) if v is not None else '')
    return salida

def texto_del_diario(cuerpo: bytes) -> str:
    """Public CI documentation."""
    try:
        raiz = ET.fromstring(cuerpo)
    except ET.ParseError as e:
        raise ErrorDeFuente(f'BOE: XML ilegible ({e})') from e
    texto = raiz.find('texto')
    if raiz.tag != 'documento' or texto is None:
        raise ErrorDeFuente(f'BOE: el Diario no trae el texto (raíz «{raiz.tag}»)')
    renglones: list[str] = []
    for h in texto:
        renglones.extend(_texto_de_hijo(h))
    return '\n'.join(renglones)

def titulo_del_diario(cuerpo: bytes) -> str | None:
    """Public CI documentation."""
    try:
        t = ET.fromstring(cuerpo).findtext('metadatos/titulo')
    except ET.ParseError:
        return None
    return ' '.join((t or '').split()) or None

def _titulo_consolidado(oficial: str) -> str | None:
    """Public CI documentation."""
    try:
        codigo, cuerpo = historial_boe._pedir(vigencia.URL_BOE_API + oficial + '/metadatos', 'application/json')
        return vigencia._meta_json(cuerpo)['titulo'] or None if codigo == 200 else None
    except (ErrorDeFuente, ValueError, KeyError, TypeError, AttributeError):
        return None

def _obra_con_error(oficial: str, estado: str, mensaje: str, url: str) -> dict:
    return {'identificador_oficial': oficial, 'estado': estado, 'error': mensaje, 'url': url, 'fuente': None, 'titulo': None, 'bloques': [], 'rutas': {}, 'sin_ruta': []}

def consultar_obra_boe(oficial: str, rutas_base: set[str], consolidada: bool, hoy: str) -> dict:
    """Public CI documentation."""
    url_doc = vigencia.URL_BOE_DOC + oficial
    if not vigencia.RE_BASE_BOE.match(oficial or ''):
        return _obra_con_error(oficial, ESTADO_ERROR, 'identificador del BOE no válido', url_doc)
    try:
        if consolidada:
            codigo, cuerpo = historial_boe._pedir(historial_boe.URL_BOE_TEXTO.format(oficial), 'application/xml')
            if codigo == 200:
                bloques = historial_boe.leer_bloques(cuerpo)
                textos = textos_de_bloques(cuerpo, hoy)
                if len(textos) != len(bloques):
                    return _obra_con_error(oficial, ESTADO_ERROR, 'BOE: los bloques del texto no cuadran', url_doc)
                rutas, sin_ruta = historial_boe.correspondencia(bloques, rutas_base)
                posicion = {b['id']: i for i, b in enumerate(bloques)}
                return {'identificador_oficial': oficial, 'estado': ESTADO_OK, 'error': None, 'url': url_doc, 'fuente': 'consolidado', 'titulo': _titulo_consolidado(oficial), 'bloques': [{'id': b['id'], 'titulo': b['titulo'], 'tipo': b['tipo'], 'texto': textos[i]} for i, b in enumerate(bloques)], 'rutas': {r: posicion[e['bloque']] for r, e in rutas.items()}, 'sin_ruta': [{k: d.get(k) for k in ('bloque', 'titulo', 'motivo')} for d in sin_ruta]}
            if codigo != 404:
                return _obra_con_error(oficial, ESTADO_ERROR, f'BOE: HTTP {codigo} en /texto de {oficial}', url_doc)
        codigo, cuerpo = historial_boe._pedir(vigencia.URL_BOE_XML + oficial, 'application/xml')
        if codigo == 404:
            return _obra_con_error(oficial, ESTADO_SIN_TEXTO, 'el BOE no tiene ni texto consolidado ni texto del Diario de esta norma', url_doc)
        if codigo != 200:
            return _obra_con_error(oficial, ESTADO_ERROR, f'BOE: HTTP {codigo} en el Diario de {oficial}', url_doc)
        texto = texto_del_diario(cuerpo)
        if not texto.strip():
            return _obra_con_error(oficial, ESTADO_SIN_TEXTO, 'el Diario del BOE no trae texto de esta norma', url_doc)
        return {'identificador_oficial': oficial, 'estado': ESTADO_OK, 'error': None, 'url': url_doc, 'fuente': 'diario', 'titulo': titulo_del_diario(cuerpo), 'bloques': [{'id': 'diario', 'titulo': None, 'tipo': 'documento', 'texto': texto}], 'rutas': {}, 'sin_ruta': []}
    except ErrorDeFuente as e:
        return _obra_con_error(oficial, ESTADO_ERROR, str(e), url_doc)
    except (ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as e:
        return _obra_con_error(oficial, ESTADO_ERROR, f'BOE: respuesta inesperada ({type(e).__name__}: {e})', url_doc)

class _Extractor(HTMLParser):
    """Public CI documentation."""
    SALTAR = {'head', 'script', 'style', 'title'}
    CORTES = {'p', 'div', 'br', 'tr', 'li', 'ul', 'ol', 'table', 'blockquote', 'hr', 'caption', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'body'}
    CELDAS = {'td', 'th'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._saltar = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SALTAR:
            self._saltar += 1
        elif tag in self.CORTES:
            self.partes.append('\n')
        elif tag in self.CELDAS:
            self.partes.append(' ')

    def handle_endtag(self, tag):
        if tag in self.SALTAR:
            self._saltar = max(0, self._saltar - 1)
        elif tag in self.CORTES:
            self.partes.append('\n')
        elif tag in self.CELDAS:
            self.partes.append(' ')

    def handle_startendtag(self, tag, attrs):
        if tag in self.CORTES:
            self.partes.append('\n')

    def handle_data(self, data):
        if not self._saltar:
            self.partes.append(re.sub('\\s+', ' ', data))

def texto_de_xhtml(cuerpo: bytes) -> str:
    """Public CI documentation."""
    e = _Extractor()
    e.feed(cuerpo.decode('utf-8', errors='replace'))
    e.close()
    lineas = [' '.join(l.split()) for l in ''.join(e.partes).split('\n')]
    return '\n'.join((l for l in lineas if l))

def celex_del_documento(oficial: str, consolidada: bool, fecha: str | None) -> str:
    """Public CI documentation."""
    if consolidada and fecha and re.match('^\\d{4}-\\d{2}-\\d{2}$', fecha) and (oficial[:1] == '3'):
        return '0' + oficial[1:] + '-' + fecha.replace('-', '')
    return oficial

def consultar_obra_ue(celex: str, idioma: str) -> dict:
    """Public CI documentation."""
    lengua = LENGUAS_CELLAR.get((idioma or '').lower())
    url = URL_CELLAR.format(urllib.parse.quote(celex, safe=''))
    base = {'celex': celex, 'idioma': idioma, 'url': url, 'texto': None}
    if not lengua:
        return {**base, 'estado': ESTADO_SIN_TEXTO, 'error': f'CELLAR no se consulta en la lengua «{idioma}»'}
    try:
        codigo, cuerpo = _pedir_ue(url, lengua)
        if codigo in (300, 404, 406):
            return {**base, 'estado': ESTADO_SIN_TEXTO, 'error': f'CELLAR no tiene el texto de {celex} en {lengua} (HTTP {codigo})'}
        if codigo != 200:
            return {**base, 'estado': ESTADO_ERROR, 'error': f'CELLAR: HTTP {codigo} en {celex}'}
        texto = texto_de_xhtml(cuerpo)
        if len(texto) < 200:
            return {**base, 'estado': ESTADO_SIN_TEXTO, 'error': f'CELLAR devuelve para {celex} un texto vacío o demasiado corto'}
        return {**base, 'estado': ESTADO_OK, 'error': None, 'texto': texto}
    except ErrorDeFuente as e:
        return {**base, 'estado': ESTADO_ERROR, 'error': str(e)}
    except Exception as e:
        return {**base, 'estado': ESTADO_ERROR, 'error': f'CELLAR: respuesta inesperada ({type(e).__name__}: {e})'}

def clave_de_version(etiqueta: str | None, idioma: str | None) -> str:
    return f"{etiqueta or ''}|{idioma or ''}"

def _versiones_de_la_base(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Public CI documentation."""
    return con.execute('SELECT o.identificador_canonico AS ident, o.titulo, v.id AS vid, v.etiqueta, v.idioma, v.es_consolidada, v.fecha_consolidacion, v.fecha_edicion FROM obra o JOIN version v ON v.obra_id=o.id WHERE EXISTS (SELECT 1 FROM precepto p WHERE p.version_id=v.id) ORDER BY o.identificador_canonico, v.etiqueta, v.idioma').fetchall()

def instantanea_boe(ruta_base, progreso=None, solo=None, hoy: str | None=None) -> dict:
    """Public CI documentation."""
    con = db.conectar(Path(ruta_base), solo_lectura=True)
    try:
        filas = [f for f in _versiones_de_la_base(con) if (vigencia.identificador_oficial(f['ident']) or '').startswith('BOE-A-') and (solo is None or f['ident'] in solo)]
        rutas_base = {f['ident']: historial_boe.rutas_de_la_obra(con, f['ident']) for f in filas}
    finally:
        con.close()
    consultado = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    resultado: dict = {'esquema': ESQUEMA, 'consultado': consultado, 'fuentes': {'BOE': AVISO_BOE}, 'base': {'ruta': str(ruta_base)}, 'obras': {}}
    for n, f in enumerate(filas, 1):
        if f['ident'] in resultado['obras']:
            continue
        oficial = vigencia.identificador_oficial(f['ident'])
        if progreso:
            progreso(f"[{n}/{len(filas)}] {f['ident']} -> {oficial}")
        resultado['obras'][f['ident']] = consultar_obra_boe(oficial, rutas_base[f['ident']], bool(f['es_consolidada']), consultado[:10])
    return resultado

def instantanea_ue(ruta_base, progreso=None, solo=None) -> dict:
    """Public CI documentation."""
    con = db.conectar(Path(ruta_base), solo_lectura=True)
    try:
        filas = [f for f in _versiones_de_la_base(con) if vigencia.RE_CELEX.match(vigencia.identificador_oficial(f['ident']) or '') and (solo is None or f['ident'] in solo)]
    finally:
        con.close()
    consultado = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    resultado: dict = {'esquema': ESQUEMA, 'consultado': consultado, 'fuentes': {'CELLAR': AVISO_CELLAR}, 'base': {'ruta': str(ruta_base)}, 'obras': {}}
    for n, f in enumerate(filas, 1):
        oficial = vigencia.identificador_oficial(f['ident'])
        celex = celex_del_documento(oficial, bool(f['es_consolidada']), f['fecha_consolidacion'])
        if progreso:
            progreso(f"[{n}/{len(filas)}] {f['ident']} ({f['idioma']}) -> {celex}")
        e = consultar_obra_ue(celex, f['idioma'])
        e['identificador_oficial'] = oficial
        resultado['obras'].setdefault(f['ident'], {'versiones': {}})['versiones'][clave_de_version(f['etiqueta'], f['idioma'])] = e
    return resultado

def escribir_instantanea(datos: dict, ruta) -> None:
    """Public CI documentation."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    os.replace(temporal, ruta)
_CACHE_JSON: dict[tuple, dict] = {}

def leer_instantanea(ruta) -> dict:
    """Public CI documentation."""
    ruta = Path(ruta)
    st = ruta.stat()
    clave = (str(ruta), st.st_mtime_ns, st.st_size)
    if clave not in _CACHE_JSON:
        _CACHE_JSON.clear()
        _CACHE_JSON[clave] = json.loads(ruta.read_text(encoding='utf-8'))
    return _CACHE_JSON[clave]

def directorio() -> Path:
    """Public CI documentation."""
    return Path(os.environ[ENV_DIR]) if os.environ.get(ENV_DIR) else config.BD.parent

def ruta_instantanea_boe() -> Path:
    return directorio() / NOMBRE_BOE

def ruta_instantanea_ue() -> Path:
    return directorio() / NOMBRE_UE

def _leer_o_none(ruta) -> dict | None:
    try:
        return leer_instantanea(ruta)
    except (OSError, ValueError):
        return None

def instantanea_boe_actual(ruta=None) -> dict | None:
    return _leer_o_none(Path(ruta) if ruta else ruta_instantanea_boe())

def instantanea_ue_actual(ruta=None) -> dict | None:
    return _leer_o_none(Path(ruta) if ruta else ruta_instantanea_ue())

@dataclass
class Datos:
    """Public CI documentation."""
    boe: dict | None = None
    ue: dict | None = None

def datos_actuales() -> Datos:
    return Datos(instantanea_boe_actual(), instantanea_ue_actual())

def resumen(datos: Datos) -> str:
    partes = []
    for nombre, d in (('BOE', datos.boe), ('UE', datos.ue)):
        if d is None:
            partes.append(f'{nombre}: SIN CONSULTAR (ict155.cli cotejo --actualizar)')
            continue
        n = {ESTADO_OK: 0, ESTADO_SIN_TEXTO: 0, ESTADO_ERROR: 0}
        for o in d['obras'].values():
            for e in o['versiones'].values() if 'versiones' in o else [o]:
                n[e['estado']] = n.get(e['estado'], 0) + 1
        partes.append(f"{nombre}: consultado el {d.get('consultado')}, {len(d['obras'])} obras ({n[ESTADO_OK]} con texto, {n[ESTADO_SIN_TEXTO]} sin testigo, {n[ESTADO_ERROR]} con error)")
    return '; '.join(partes)

def lineas_de_resumen(datos: Datos) -> list[str]:
    salida = []
    if datos.boe:
        for ident, o in sorted(datos.boe['obras'].items()):
            if o['estado'] == ESTADO_OK:
                mapa = f"{len(o['rutas'])} rutas de la base" if o['fuente'] == 'consolidado' else 'la norma entera'
                salida.append(f"BOE  {ident}  [{o['estado']}] {o['fuente']}: {len(o['bloques'])} bloques, {mapa}, {sum((len(b['texto']) for b in o['bloques'])):,} caracteres")
            else:
                salida.append(f"BOE  {ident}  [{o['estado']}] {o.get('error') or ''}".rstrip())
    if datos.ue:
        for ident, o in sorted(datos.ue['obras'].items()):
            for clave, e in sorted(o['versiones'].items()):
                if e['estado'] == ESTADO_OK:
                    salida.append(f"UE   {ident} ({clave})  [{e['estado']}] {e['celex']}: {len(e['texto']):,} caracteres")
                else:
                    salida.append(f"UE   {ident} ({clave})  [{e['estado']}] {e['celex']}: {e.get('error') or ''}".rstrip())
    return salida
_DOCS: 'OrderedDict[str, object]' = OrderedDict()
_PAGINAS: dict[tuple[str, int], tuple[str, bool]] = {}
_MAX_DOCS = 4
_PATRONES: dict[tuple, object] = {}

def limpiar_cache() -> None:
    _DOCS.clear()
    _PAGINAS.clear()
    _PATRONES.clear()
    normalizar_testigo.cache_clear()

def _documento_pdf(ruta_rel: str):
    """Public CI documentation."""
    if ruta_rel in _DOCS:
        _DOCS.move_to_end(ruta_rel)
        return _DOCS[ruta_rel]
    try:
        import fitz
    except Exception as e:
        return f'PyMuPDF no está disponible ({type(e).__name__})'
    try:
        with config.abrir_biblioteca(config.ruta_biblioteca(ruta_rel), 'rb') as f:
            datos = f.read()
        doc = fitz.open(stream=datos, filetype='pdf')
    except Exception as e:
        return f'no se puede abrir el PDF {ruta_rel} ({type(e).__name__}: {e})'
    _DOCS[ruta_rel] = doc
    while len(_DOCS) > _MAX_DOCS:
        _DOCS.popitem(last=False)[1].close()
    return doc
MINIMO_NUMEROS_DE_RENGLON = 8

def _sin_numeros_de_renglon(pg) -> str | None:
    """Public CI documentation."""
    import fitz
    palabras = pg.get_text('words')
    cifras = [w for w in palabras if re.fullmatch('\\d{1,4}', w[4])]
    if len(cifras) < MINIMO_NUMEROS_DE_RENGLON:
        return None
    columnas: dict[int, list] = {}
    for w in cifras:
        columnas.setdefault(round(w[0] / 3), []).append(w)
    col = max(columnas.values(), key=len)
    if len(col) < MINIMO_NUMEROS_DE_RENGLON:
        return None
    col = sorted(col, key=lambda w: w[1])
    valores = [int(w[4]) for w in col]
    if sum((1 for a, b in zip(valores, valores[1:]) if b > a)) < 0.8 * (len(valores) - 1):
        return None
    ids = {id(w) for w in col}
    resto = [w for w in palabras if id(w) not in ids]
    if not resto:
        return None
    izquierda = sorted((w[0] for w in resto))[len(resto) // 20]
    derecha = sorted((w[2] for w in resto))[-1 - len(resto) // 20]
    if max((w[2] for w in col)) < izquierda:
        clip = fitz.Rect(max((w[2] for w in col)) + 0.5, 0, pg.rect.x1, pg.rect.y1)
    elif min((w[0] for w in col)) > derecha:
        clip = fitz.Rect(0, 0, min((w[0] for w in col)) - 0.5, pg.rect.y1)
    else:
        return None
    return pg.get_text('text', clip=clip)

def pagina_pdf(ruta_rel: str, n: int):
    """Public CI documentation."""
    k = (ruta_rel, n)
    if k in _PAGINAS:
        return _PAGINAS[k]
    doc = _documento_pdf(ruta_rel)
    if isinstance(doc, str):
        return doc
    if not 1 <= n <= doc.page_count:
        return ('', False)
    pg = doc[n - 1]
    texto = _sin_numeros_de_renglon(pg) or pg.get_text('text')
    invisible = False
    if texto.strip():
        try:
            vis = inv = 0
            for e in pg.get_texttrace():
                if e.get('type') == 3:
                    inv += len(e.get('chars') or ())
                else:
                    vis += len(e.get('chars') or ())
            invisible = inv > 0 and inv >= vis
        except Exception:
            invisible = False
    _PAGINAS[k] = (texto, invisible)
    return _PAGINAS[k]

def numero_de_paginas_pdf(ruta_rel: str) -> int | None:
    doc = _documento_pdf(ruta_rel)
    return None if isinstance(doc, str) else doc.page_count

def texto_de_paginas_pdf(ruta_rel: str, ini: int, fin: int, propias: tuple[int, int] | None=None) -> tuple[str | None, str | None]:
    """Public CI documentation."""
    partes = []
    for n in range(max(1, ini), fin + 1):
        propia = propias is None or propias[0] <= n <= propias[1]
        p = pagina_pdf(ruta_rel, n)
        if isinstance(p, str):
            if propia:
                return (None, p)
            continue
        texto, invisible = p
        if invisible:
            if propia:
                return (None, f'ocr: la página {n} del PDF es una imagen con una capa de texto de reconocimiento óptico')
            continue
        partes.append(texto)
    return ('\n'.join(partes), None)

def _sin_mobiliario(variantes: tuple[str, ...], patrones: tuple[str, ...]) -> tuple[str, ...]:
    """Public CI documentation."""
    if not patrones:
        return variantes
    rx = _PATRONES.get(patrones)
    if rx is None:
        rx = _PATRONES[patrones] = mobiliario.compilar(patrones, normalizar) or False
    return tuple((mobiliario.quitar(v, rx) for v in variantes)) if rx else variantes

@dataclass
class Cotejo:
    estado: str
    familia: str | None = None
    obra: str | None = None
    motivo: str | None = None
    original: str | None = None
    fuente: str | None = None

    @property
    def rotulo(self) -> str:
        return ROTULO.get(self.familia or '', 'el original')

def _info_version(con: sqlite3.Connection, version_id: int | None) -> sqlite3.Row | None:
    if version_id is None:
        return None
    return con.execute('SELECT o.identificador_canonico AS ident, v.etiqueta, v.idioma, v.es_consolidada, v.fecha_consolidacion, d.ruta_relativa, d.motor_extraccion, d.id AS doc_id FROM version v JOIN obra o ON o.id=v.obra_id JOIN documento d ON d.id=v.documento_id WHERE v.id=?', (version_id,)).fetchone()

def _alcance_del_precepto(con: sqlite3.Connection, version_id: int, ruta: str) -> tuple[int | None, int | None, set[str]]:
    """Public CI documentation."""
    actual = ruta
    while True:
        if actual:
            f = con.execute('SELECT min(pagina_inicio), max(pagina_fin), group_concat(DISTINCT metodo_extraccion) FROM precepto WHERE version_id=? AND (ruta_estructural=? OR ruta_estructural LIKE ? OR ruta_estructural LIKE ?)', (version_id, actual, actual + '.%', actual + '/%')).fetchone()
        else:
            f = con.execute('SELECT min(pagina_inicio), max(pagina_fin), group_concat(DISTINCT metodo_extraccion) FROM precepto WHERE version_id=?', (version_id,)).fetchone()
        if f[0] is not None or not actual:
            return (f[0], f[1], set((f[2] or '').split(',')))
        actual = consulta.ruta_padre(actual) or ''

def _motivo_de_ocr(info: sqlite3.Row, metodos: set[str]) -> str | None:
    motor = (info['motor_extraccion'] or '').casefold()
    etiqueta = (info['etiqueta'] or '').casefold()
    if 'ocr' in motor or etiqueta.startswith('reconocimiento') or 'ocr' in metodos:
        return 'texto de reconocimiento óptico'
    if 'transcripcion_verificada' in metodos or etiqueta.startswith('transcripcion') or motor == 'transcripcion_verificada':
        return 'transcripción de ICT155 (su fuente es una ficha de trabajo, no un original)'
    return None

def familia_de(ident: str) -> str:
    oficial = vigencia.identificador_oficial(ident) or ''
    if oficial.startswith('BOE-A-'):
        return BOE
    if vigencia.RE_CELEX.match(oficial):
        return UE
    return PDF
_RUTAS_DE_LOS_BLOQUES: dict[tuple, dict] = {}

def _bloques_por_ruta(ident: str, o: dict) -> dict[str, dict]:
    """Public CI documentation."""
    k = (ident, id(o))
    if k not in _RUTAS_DE_LOS_BLOQUES:
        if len(_RUTAS_DE_LOS_BLOQUES) > 64:
            _RUTAS_DE_LOS_BLOQUES.clear()
        _RUTAS_DE_LOS_BLOQUES[k] = {r: {'tipo': o['bloques'][i]['tipo'], 'parrafos': len(o['bloques'][i]['texto'].splitlines()), 'posicion': i} for r, i in o['rutas'].items()}
    return _RUTAS_DE_LOS_BLOQUES[k]

def _testigo_boe(datos: Datos, ident: str, ruta: str) -> tuple[str | None, str | None, str | None]:
    """Public CI documentation."""
    if datos.boe is None:
        return (None, None, 'sin_consulta')
    o = datos.boe['obras'].get(ident)
    if o is None:
        return (None, None, 'sin_consulta:esta obra no está en la consulta del texto oficial del BOE')
    if o['estado'] == ESTADO_ERROR:
        return (None, None, f"sin_consulta:no se pudo consultar el BOE ({o.get('error')})")
    if o['estado'] != ESTADO_OK:
        return (None, None, f"sin_testigo:{o.get('error') or 'el BOE no tiene el texto de esta norma'}")
    bloques = o['bloques']
    if ruta == 'cabecera' and o.get('titulo'):
        return (f"{o['titulo']}\nReferencia: {o.get('identificador_oficial') or ident}", 'el título oficial de la norma', None)
    if o['fuente'] == 'consolidado' and ruta:
        hallado = historial_boe.bloque_de(_bloques_por_ruta(ident, o), ruta)
        if hallado:
            r, e = hallado
            b = bloques[e['posicion']]
            return (b['texto'], f"texto consolidado, bloque «{b['titulo'] or b['id']}» ({r})", None)
    texto = '\n'.join((b['texto'] for b in bloques))
    return (texto, 'texto de la norma entera publicada en el Diario Oficial' if o['fuente'] == 'diario' else 'texto consolidado de la norma entera, sin bloque para esta ruta', None)

def _testigo_ue(datos: Datos, ident: str, etiqueta: str, idioma: str) -> tuple[str | None, str | None, str | None]:
    if datos.ue is None:
        return (None, None, 'sin_consulta')
    o = datos.ue['obras'].get(ident)
    e = (o or {}).get('versiones', {}).get(clave_de_version(etiqueta, idioma))
    if e is None:
        return (None, None, 'sin_consulta:esta versión no está en la consulta del texto oficial de la UE')
    if e['estado'] == ESTADO_ERROR:
        return (None, None, f"sin_consulta:no se pudo consultar EUR-Lex ({e.get('error')})")
    if e['estado'] != ESTADO_OK:
        return (None, None, f"sin_testigo:{e.get('error') or 'EUR-Lex no tiene una versión equivalente'}")
    return (e['texto'], f"{e['celex']}, texto de la norma entera", None)

def cotejar(con: sqlite3.Connection, version_id: int | None, ruta: str, fragmentos: list[str], datos: Datos) -> Cotejo:
    """Public CI documentation."""
    info = _info_version(con, version_id)
    if info is None:
        return Cotejo(SIN_TESTIGO, None, None, 'la base no dice de qué documento sale este texto')
    ident = info['ident']
    ini, fin, metodos = _alcance_del_precepto(con, version_id, ruta)
    motivo_ocr = _motivo_de_ocr(info, metodos)
    if motivo_ocr:
        return Cotejo(SIN_TESTIGO, OCR, ident, motivo_ocr)
    familia = familia_de(ident)
    variantes: tuple[str, ...] | None = None
    fuente = None
    if familia in (BOE, UE):
        texto, fuente, problema = _testigo_boe(datos, ident, ruta) if familia == BOE else _testigo_ue(datos, ident, info['etiqueta'], info['idioma'])
        if problema:
            clase, _, porque = problema.partition(':')
            return Cotejo(SIN_TESTIGO if clase == 'sin_testigo' else SIN_CONSULTA, familia, ident, porque or None)
        variantes = normalizar_testigo(texto)
    else:
        if ini is None:
            return Cotejo(SIN_TESTIGO, PDF, ident, 'el precepto no tiene páginas en la base')
        n = numero_de_paginas_pdf(info['ruta_relativa'])
        hasta = fin + MARGEN_DE_PAGINAS if n is None else min(fin + MARGEN_DE_PAGINAS, n)
        texto, motivo = texto_de_paginas_pdf(info['ruta_relativa'], ini - MARGEN_DE_PAGINAS, hasta, propias=(ini, fin))
        if texto is None:
            if (motivo or '').startswith('ocr:'):
                return Cotejo(SIN_TESTIGO, OCR, ident, motivo[4:].strip())
            return Cotejo(SIN_CONSULTA, PDF, ident, motivo)
        variantes = _sin_mobiliario(normalizar_testigo(texto), mobiliario.patrones_de(con, info['ruta_relativa']))
        fuente = f"{info['ruta_relativa']}, páginas {max(1, ini - MARGEN_DE_PAGINAS)} a {hasta}"
    trozos = _trozos(fragmentos)
    if not trozos or any((_en_orden(trozos, v) == len(trozos) for v in variantes)):
        return Cotejo(OK, familia, ident, fuente=fuente)
    mejor = max(variantes, key=lambda v: _en_orden(trozos, v))
    original = trozo_parecido(fragmentos, mejor)
    return Cotejo(DISTINTO, familia, ident, original=original, fuente=fuente)

def detalle_ok(identificador: str, c: Cotejo) -> str:
    """Public CI documentation."""
    return f'está en {identificador}; cotejado con {c.rotulo}'

def detalle_distinto(identificador: str, c: Cotejo) -> str:
    """Public CI documentation."""
    donde = f' ({c.fuente})' if c.fuente else ''
    if c.original:
        parecido = f'el original dice: «{c.original}»'
    else:
        parecido = 'no hay en el original ningún trozo parecido'
    return f'el literal está en {identificador} (texto de la base) pero no coincide con el original, {c.rotulo}{donde}: {parecido}. Usa la redacción del original o quita las comillas y cita cláusula y página'

def detalle_sin_testigo(c: Cotejo) -> str:
    """Public CI documentation."""
    return TEXTO_SIN_TESTIGO + (f' [{c.motivo}]' if c.motivo else '')

def detalle_sin_consulta(c: Cotejo) -> str:
    """Public CI documentation."""
    return TEXTO_SIN_CONSULTA + (f' [{c.motivo}]' if c.motivo and c.motivo != 'sin_consulta' else '')

def texto_del_testigo(con: sqlite3.Connection, version_id: int | None, ruta: str, datos: Datos) -> tuple[str | None, str]:
    """Public CI documentation."""
    info = _info_version(con, version_id)
    if info is None:
        return (None, 'la base no dice de qué documento sale este texto')
    ini, fin, metodos = _alcance_del_precepto(con, version_id, ruta)
    motivo = _motivo_de_ocr(info, metodos)
    if motivo:
        return (None, f'sin testigo: {motivo}')
    familia = familia_de(info['ident'])
    if familia == BOE:
        texto, que, problema = _testigo_boe(datos, info['ident'], ruta)
    elif familia == UE:
        texto, que, problema = _testigo_ue(datos, info['ident'], info['etiqueta'], info['idioma'])
    else:
        if ini is None:
            return (None, 'el precepto no tiene páginas en la base')
        texto, problema = texto_de_paginas_pdf(info['ruta_relativa'], ini - MARGEN_DE_PAGINAS, fin + MARGEN_DE_PAGINAS, propias=(ini, fin))
        que = f"{info['ruta_relativa']}, páginas {max(1, ini - MARGEN_DE_PAGINAS)} a {fin + MARGEN_DE_PAGINAS}"
        if texto is not None:
            problema = None
    if problema or texto is None:
        return (None, f"sin testigo: {problema or 'no hay'}")
    return (texto, que or '')
PALABRAS_DE_FRASE = (8, 18)
MINIMO_DE_CARACTERES = 90

def frases_de_muestra(con: sqlite3.Connection, familia: str, n: int, semilla: int=20261016) -> list[dict]:
    """Public CI documentation."""
    rng = random.Random(semilla)
    candidatos = []
    for f in con.execute("SELECT o.identificador_canonico AS ident, v.id AS vid, p.ruta_estructural AS ruta, p.texto_literal AS t FROM precepto p JOIN version v ON v.id=p.version_id JOIN obra o ON o.id=v.obra_id WHERE p.metodo_extraccion='capa_texto' AND p.ruta_estructural <> 'cabecera' AND length(p.texto_literal) >= ? ORDER BY o.identificador_canonico, v.id, p.orden", (MINIMO_DE_CARACTERES,)):
        if familia_de(f['ident']) == familia and len(f['t'].split()) > PALABRAS_DE_FRASE[1]:
            candidatos.append(f)
    rng.shuffle(candidatos)
    salida = []
    for f in candidatos[:n]:
        pal = f['t'].split()
        largo = rng.randint(*PALABRAS_DE_FRASE)
        ini = rng.randint(0, len(pal) - largo)
        salida.append({'obra': f['ident'], 'version_id': f['vid'], 'ruta': f['ruta'], 'frase': ' '.join(pal[ini:ini + largo])})
    return salida

def medir(con: sqlite3.Connection, datos: Datos, n_por_familia: int=300, semilla: int=20261016, progreso=None) -> dict:
    """Public CI documentation."""
    resultado = {}
    for fam in FAMILIAS:
        muestra = frases_de_muestra(con, fam, n_por_familia, semilla)
        r = {'muestra': len(muestra), OK: 0, DISTINTO: 0, SIN_TESTIGO: 0, SIN_CONSULTA: 0, 'fallos': []}
        for k, m in enumerate(muestra, 1):
            if progreso and k % 100 == 0:
                progreso(f'{fam}: {k}/{len(muestra)}')
            c = cotejar(con, m['version_id'], m['ruta'], [m['frase']], datos)
            r[c.estado] += 1
            if c.estado != OK:
                r['fallos'].append({**m, 'estado': c.estado, 'motivo': c.motivo, 'original': c.original, 'fuente': c.fuente})
        resultado[fam] = r
    return resultado

def texto_de_medicion(r: dict) -> str:
    lineas = []
    for fam in FAMILIAS:
        x = r[fam]
        con_testigo = x[OK] + x[DISTINTO]
        pct = f'{100.0 * x[OK] / con_testigo:.1f} %' if con_testigo else '—'
        lineas.append(f"{ROTULO[fam]:8s} muestra {x['muestra']:4d}: en su testigo {x[OK]:4d}, distinto {x[DISTINTO]:4d}, sin testigo {x[SIN_TESTIGO]:3d}, sin consulta {x[SIN_CONSULTA]:3d}  ->  {pct} de las que tienen testigo")
    return '\n'.join(lineas)

def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(prog='python -m ict155.cotejo_original', description='Instantáneas del texto oficial (BOE y EUR-Lex) con que se cotejan los literales.')
    ap.add_argument('--salida', required=True, help='carpeta donde se escriben las dos instantáneas')
    ap.add_argument('--base', default=None, help='base de datos (por defecto la de producción; solo lectura)')
    args = ap.parse_args(argv)
    ruta_base = Path(args.base) if args.base else config.BD
    salida = Path(args.salida)
    boe = instantanea_boe(ruta_base, progreso=lambda s: print(s, file=sys.stderr, flush=True))
    escribir_instantanea(boe, salida / NOMBRE_BOE)
    ue = instantanea_ue(ruta_base, progreso=lambda s: print(s, file=sys.stderr, flush=True))
    escribir_instantanea(ue, salida / NOMBRE_UE)
    print(resumen(Datos(boe, ue)))
    print(f'escritas {salida / NOMBRE_BOE} y {salida / NOMBRE_UE}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
