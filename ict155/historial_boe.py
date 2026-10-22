"""Public CI documentation."""
from __future__ import annotations
import argparse
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from . import config, consulta, db, parsers, vigencia
from .ruta import sin_libro_primero
from .vigencia import ErrorDeFuente
USER_AGENT = 'ict155-bd-normativa (historial de redacciones)'
TIMEOUT = 120
PAUSA = 1.0
REINTENTOS = 1
ESPERA_REINTENTO = 3.0
URL_BOE_TEXTO = 'https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{}/texto'
URL_BOE_DOC = vigencia.URL_BOE_DOC
AVISO_BOE = 'Fuente: Agencia Estatal Boletín Oficial del Estado; el texto consolidado es informativo'
ESQUEMA = 1
NOMBRE_FICHERO = 'historial_boe.json'
UMBRAL_ROTULO = 3
ESTADO_OK = 'ok'
ESTADO_SIN_TEXTO = 'sin_texto_consolidado'
ESTADO_ERROR = 'error'
SIN_EQUIVALENTE = 'sin_equivalente'
TITULO_NO_RECONOCIDO = 'titulo_no_reconocido'
RUTA_NO_ESTA_EN_LA_BASE = 'ruta_no_esta_en_la_base'
RUTA_AMBIGUA = 'ruta_ambigua'
MOTIVOS = (SIN_EQUIVALENTE, TITULO_NO_RECONOCIDO, RUTA_NO_ESTA_EN_LA_BASE, RUTA_AMBIGUA)
_ultima_peticion = [0.0]

def _descargar(url: str, accept: str) -> tuple[int, bytes]:
    """Public CI documentation."""
    espera = PAUSA - (time.monotonic() - _ultima_peticion[0])
    if espera > 0:
        time.sleep(espera)
    peticion = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
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

def _pedir(url: str, accept: str) -> tuple[int, bytes]:
    """Public CI documentation."""
    for intento in range(REINTENTOS + 1):
        ultimo = intento == REINTENTOS
        try:
            codigo, cuerpo = _descargar(url, accept)
        except ErrorDeFuente:
            if ultimo:
                raise
        else:
            if codigo < 500 or ultimo:
                return (codigo, cuerpo)
        time.sleep(ESPERA_REINTENTO)
    raise ErrorDeFuente('sin respuesta')

def leer_bloques(cuerpo: bytes) -> list[dict]:
    """Public CI documentation."""
    try:
        raiz = ET.fromstring(cuerpo)
    except ET.ParseError as e:
        raise ErrorDeFuente(f'BOE: XML ilegible ({e})') from e
    if raiz.tag != 'response':
        raise ErrorDeFuente(f'BOE: respuesta inesperada (raíz «{raiz.tag}»)')
    codigo = (raiz.findtext('status/code') or '').strip()
    if codigo != '200':
        raise ErrorDeFuente(f"BOE: {codigo or '?'} {(raiz.findtext('status/text') or '').strip()}".strip())
    texto = raiz.find('data/texto')
    if texto is None:
        raise ErrorDeFuente('BOE: la respuesta no trae el texto de la norma')
    bloques = []
    for b in texto.findall('bloque'):
        versiones = [{'id_norma': (v.get('id_norma') or '').strip() or None, 'fecha_publicacion': vigencia._fecha_boe(v.get('fecha_publicacion')), 'fecha_vigencia': vigencia._fecha_boe(v.get('fecha_vigencia'))} for v in b.findall('version')]
        ultima = b.findall('version')[-1:] or [None]
        bloques.append({'id': b.get('id'), 'tipo': (b.get('tipo') or '').strip(), 'titulo': ' '.join((b.get('titulo') or '').split()) or None, 'parrafos': len(ultima[0].findall('p')) if ultima[0] is not None else 0, 'versiones': versiones})
    return bloques
NIVELES = ('libro', 'titulo', 'capitulo', 'seccion')
_ROMANO = '[ivxlcdm]+'
_SUFIJO = 'bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies'
RE_ARTICULO = re.compile(f'^articulo (\\d+)(?: ({_SUFIJO}))?$')
RE_ARTICULO_UNICO = re.compile('^articulo unico$')
RE_DISPOSICION = re.compile('^disposicion (adicional|transitoria|final|derogatoria)(?: (.+))?$')
RE_APARTADO = re.compile('^apartado (\\d+)$')
RE_ANEXO = re.compile(f'^(anexo|anejo)(?: ({_ROMANO}|\\d+))?(?: ({_SUFIJO}))?$')
RE_APENDICE = re.compile(f'^apendice ({_ROMANO}|\\d+)$')
RE_INSTRUCCION = re.compile('^instruccion ([a-z]{1,4}-\\d+)$')
RE_REGLAMENTO = re.compile('^reglamento$')
RE_LIBRO = re.compile(f'^libro ([a-z]+|\\d+)$')
RE_TITULO = re.compile(f'^titulo (preliminar|primero|{_ROMANO}|\\d+)$')
RE_CAPITULO = re.compile(f'^capitulo ({_ROMANO}|\\d+)$')
RE_SECCION = re.compile('^seccion (\\d+)$')

def _sin_tildes(s: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

def _plano(titulo: str | None) -> str:
    return ' '.join(_sin_tildes(titulo or '').lower().split())

def _numeral(n: str) -> str:
    """Public CI documentation."""
    return n.upper() if re.fullmatch(_ROMANO, n) else n

class _Contexto:
    """Public CI documentation."""

    def __init__(self):
        self.reglamento = False
        self.contenedor: str | None = None
        self.apendice: str | None = None
        self.div: dict[str, str | None] = {n: None for n in NIVELES}

    def entra_en(self, contenedor: str | None, reglamento: bool=False) -> None:
        self.contenedor, self.reglamento, self.apendice = (contenedor, reglamento, None)
        self.div = {n: None for n in NIVELES}

def _prefijos(ctx: _Contexto) -> list[str]:
    """Public CI documentation."""
    partes = [p for p in (ctx.contenedor, ctx.apendice) if p]
    if partes:
        prefijos = ['/'.join(partes[:k]) + '/' for k in range(len(partes), 0, -1)]
        return prefijos + ([''] if ctx.contenedor == 'anexo.sn' else [])
    return (['reglamento/'] if ctx.reglamento else []) + ['']

def _candidatas_de_division(ctx: _Contexto, nivel: str, valores: list[str]) -> list[str]:
    """Public CI documentation."""
    previos = [ctx.div[n] for n in NIVELES[:NIVELES.index(nivel)] if ctx.div[n]]
    cadenas = [previos] + ([previos[1:]] if previos and previos[0] == 'libro.1' else [])
    salida = []
    for prefijo in _prefijos(ctx):
        for cadena in cadenas:
            for v in valores:
                salida.append(prefijo + '/'.join([*cadena, v]))
    return list(dict.fromkeys(salida))

def _ordinal(texto: str | None) -> str | None:
    """Public CI documentation."""
    if not texto:
        return '1'
    n = parsers.ordinal_a_numero(texto)
    return n if n.isdigit() else None

def candidatas(bloque: dict, ctx: _Contexto) -> tuple[str | None, list[str], dict]:
    """Public CI documentation."""
    tipo, plano = (bloque.get('tipo'), _plano(bloque.get('titulo')))
    if tipo == 'preambulo':
        return ('preambulo', ['preambulo'], {})
    if tipo in ('nota_inicial', 'firma'):
        return (None, [], {})
    if (m := RE_ARTICULO_UNICO.match(plano)):
        return ('articulo', [p + 'art.unico' for p in _prefijos(ctx)], {})
    if (m := RE_ARTICULO.match(plano)):
        return ('articulo', [p + f'art.{m[1]}' + (f' {m[2]}' if m[2] else '') for p in _prefijos(ctx)], {})
    if (m := RE_DISPOSICION.match(plano)):
        n = _ordinal(m[2])
        return ('disposicion', [p + f'disp.{m[1]}.{n}' for p in _prefijos(ctx)], {}) if n else (None, [], {})
    if (m := RE_APARTADO.match(plano)):
        return ('apartado', [p + f'ap.{m[1]}' for p in _prefijos(ctx)], {})
    if (m := RE_ANEXO.match(plano)):
        numero = _numeral(m[2]) if m[2] else 'sn'
        ruta = f'anexo.{numero}' + (f' {m[3]}' if m[3] else '')
        return ('anexo', [ruta], {'contenedor': ruta})
    if (m := RE_INSTRUCCION.match(plano)):
        ruta = f'itc.{m[1].upper()}'
        return ('instruccion', [ruta], {'contenedor': ruta})
    if RE_REGLAMENTO.match(plano):
        return ('reglamento', ['reglamento'], {'reglamento': True})
    if (m := RE_APENDICE.match(plano)):
        segmento = f'apend.{_numeral(m[1])}'
        return ('apendice', [(ctx.contenedor + '/' if ctx.contenedor else '') + segmento], {'apendice': segmento})
    for nivel, patron in (('libro', RE_LIBRO), ('titulo', RE_TITULO), ('capitulo', RE_CAPITULO), ('seccion', RE_SECCION)):
        m = patron.match(plano)
        if not m:
            continue
        valor = m[1]
        if nivel == 'libro':
            n = parsers.ordinal_a_numero(valor)
            valores = [f'libro.{n}'] if n.isdigit() else []
        elif nivel == 'titulo':
            valores = ['titulo.primero', 'titulo.I'] if valor == 'primero' else [f'titulo.{valor}' if valor == 'preliminar' else f'titulo.{_numeral(valor)}']
        else:
            valores = [f'{nivel}.{_numeral(valor)}']
        if not valores:
            return (None, [], {})
        return (nivel, _candidatas_de_division(ctx, nivel, valores), {'division': (nivel, valores)})
    return (None, [], {})

def correspondencia(bloques: list[dict], rutas_base: set[str]) -> tuple[dict[str, dict], list[dict]]:
    """Public CI documentation."""
    ctx = _Contexto()
    rutas: dict[str, dict] = {}
    sin_ruta: list[dict] = []
    ambiguas: set[str] = set()

    def descartar(b: dict, motivo: str, candidata: str | None=None) -> None:
        d = {'bloque': b['id'], 'tipo': b['tipo'], 'titulo': b['titulo'], 'motivo': motivo}
        if candidata:
            d['candidata'] = candidata
        sin_ruta.append(d)
    for b in bloques:
        clase, posibles, cambios = candidatas(b, ctx)
        elegida = next((c for c in posibles if c in rutas_base), None)
        if 'contenedor' in cambios:
            ctx.entra_en(cambios['contenedor'])
        elif cambios.get('reglamento'):
            ctx.entra_en(None, reglamento=True)
        elif 'apendice' in cambios:
            ctx.apendice = cambios['apendice']
        elif 'division' in cambios:
            nivel, valores = cambios['division']
            ctx.div[nivel] = next((v for v in valores if elegida and elegida.endswith(v)), valores[0])
            for menor in NIVELES[NIVELES.index(nivel) + 1:]:
                ctx.div[menor] = None
        if clase is None:
            descartar(b, SIN_EQUIVALENTE if b['tipo'] in ('nota_inicial', 'firma') else TITULO_NO_RECONOCIDO)
        elif elegida is None:
            descartar(b, RUTA_NO_ESTA_EN_LA_BASE, posibles[0] if posibles else None)
        elif elegida in ambiguas:
            descartar(b, RUTA_AMBIGUA, elegida)
        elif elegida in rutas:
            previo = rutas.pop(elegida)
            ambiguas.add(elegida)
            descartar({'id': previo['bloque'], 'tipo': previo['tipo'], 'titulo': previo['titulo']}, RUTA_AMBIGUA, elegida)
            descartar(b, RUTA_AMBIGUA, elegida)
        else:
            rutas[elegida] = {'bloque': b['id'], 'titulo': b['titulo'], 'tipo': b['tipo'], 'parrafos': b['parrafos'], 'versiones': b['versiones']}
    return (rutas, sin_ruta)

def recuento(n_bloques: int, rutas: dict, sin_ruta: list[dict]) -> dict:
    """Public CI documentation."""
    r = {'bloques': n_bloques, 'con_ruta': len(rutas)}
    for motivo in MOTIVOS:
        r[motivo] = sum((1 for d in sin_ruta if d['motivo'] == motivo))
    return r

def rutas_de_la_obra(con: sqlite3.Connection, obra: str) -> set[str]:
    """Public CI documentation."""
    return {r[0] for r in con.execute('SELECT p.ruta_estructural FROM precepto p JOIN version v ON v.id = p.version_id JOIN obra o ON o.id = v.obra_id WHERE o.identificador_canonico = ?', (obra,))}

def _obra_con_error(oficial: str, titulo: str | None, estado: str, mensaje: str) -> dict:
    return {'identificador_oficial': oficial, 'titulo_base': titulo, 'estado': estado, 'error': mensaje, 'url': URL_BOE_DOC + oficial, 'recuento': None, 'rutas': {}, 'sin_ruta': []}

def consultar_obra(oficial: str, titulo: str | None, rutas_base: set[str]) -> dict:
    """Public CI documentation."""
    if not vigencia.RE_BASE_BOE.match(oficial or ''):
        return _obra_con_error(oficial, titulo, ESTADO_ERROR, 'identificador del BOE no válido')
    try:
        codigo, cuerpo = _pedir(URL_BOE_TEXTO.format(oficial), 'application/xml')
        if codigo == 404:
            return _obra_con_error(oficial, titulo, ESTADO_SIN_TEXTO, 'el BOE no tiene texto consolidado de esta norma (las que solo modifican a otra no se consolidan)')
        if codigo != 200:
            return _obra_con_error(oficial, titulo, ESTADO_ERROR, f'BOE: HTTP {codigo} en /texto de {oficial}')
        bloques = leer_bloques(cuerpo)
    except ErrorDeFuente as e:
        return _obra_con_error(oficial, titulo, ESTADO_ERROR, str(e))
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return _obra_con_error(oficial, titulo, ESTADO_ERROR, f'BOE: respuesta inesperada ({type(e).__name__}: {e})')
    rutas, sin_ruta = correspondencia(bloques, rutas_base)
    return {'identificador_oficial': oficial, 'titulo_base': titulo, 'estado': ESTADO_OK, 'error': None, 'url': URL_BOE_DOC + oficial, 'recuento': recuento(len(bloques), rutas, sin_ruta), 'rutas': rutas, 'sin_ruta': sin_ruta}

def instantanea(ruta_base, progreso=None, solo=None) -> dict:
    """Public CI documentation."""
    con = db.conectar(Path(ruta_base), solo_lectura=True)
    try:
        obras = [o for o in con.execute('SELECT id, identificador_canonico AS ident, titulo FROM obra ORDER BY identificador_canonico') if vigencia.RE_BASE_BOE.match(o['ident']) and (solo is None or o['ident'] in solo)]
        rutas_base = {o['ident']: rutas_de_la_obra(con, o['ident']) for o in obras}
    finally:
        con.close()
    resultado: dict = {'esquema': ESQUEMA, 'consultado': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'fuentes': {'BOE': AVISO_BOE}, 'base': {'ruta': str(ruta_base)}, 'obras': {}}
    for n, o in enumerate(obras, 1):
        if progreso:
            progreso(f"[{n}/{len(obras)}] {o['ident']}")
        resultado['obras'][o['ident']] = consultar_obra(o['ident'], o['titulo'], rutas_base[o['ident']])
    return resultado

def escribir_instantanea(datos: dict, ruta) -> None:
    """Public CI documentation."""
    vigencia.escribir_instantanea(datos, ruta)

def leer_instantanea(ruta) -> dict:
    return vigencia.leer_instantanea(ruta)

def resumen(datos: dict) -> str:
    n = {ESTADO_OK: 0, ESTADO_SIN_TEXTO: 0, ESTADO_ERROR: 0}
    bloques = con_ruta = sin = 0
    for o in datos['obras'].values():
        n[o['estado']] = n.get(o['estado'], 0) + 1
        if o.get('recuento'):
            bloques += o['recuento']['bloques']
            con_ruta += o['recuento']['con_ruta']
            sin += len(o['sin_ruta'])
    return f"{len(datos['obras'])} obras consultadas el {datos['consultado']}: {n[ESTADO_OK]} con historial, {n[ESTADO_SIN_TEXTO]} sin texto consolidado en el BOE, {n[ESTADO_ERROR]} con error; {bloques} bloques, {con_ruta} llevados a una ruta de la base, {sin} sin ruta"

def lineas_de_resumen(datos: dict, obra: str | None=None) -> list[str]:
    """Public CI documentation."""
    salida = []
    for ident, o in sorted(datos['obras'].items()):
        if obra and ident != obra:
            continue
        r = o.get('recuento')
        if o['estado'] != ESTADO_OK or not r:
            salida.append(f"{ident}  [{o['estado']}] {o.get('error') or ''}".rstrip())
            continue
        descartes = ', '.join((f'{r[m]} {m}' for m in MOTIVOS if r[m]))
        salida.append(f"{ident}  [{o['estado']}] {r['bloques']} bloques, {r['con_ruta']} con ruta en la base" + (f'; sin ruta: {descartes}' if descartes else ''))
    return salida
DIAS_DE_VALIDEZ = 30

def ruta_instantanea() -> Path:
    """Public CI documentation."""
    return config.BD.parent / NOMBRE_FICHERO

def instantanea_actual(ruta=None) -> dict | None:
    """Public CI documentation."""
    ruta = Path(ruta) if ruta else ruta_instantanea()
    try:
        return leer_instantanea(ruta)
    except (OSError, ValueError):
        return None

def _es_rotulo(e: dict) -> bool:
    return e.get('tipo') == 'encabezado' and (e.get('parrafos') or 0) <= UMBRAL_ROTULO

def bloque_de(rutas: dict, ruta: str) -> tuple[str, dict] | None:
    """Public CI documentation."""
    actual = ruta
    while actual:
        for r in (actual, sin_libro_primero(actual)):
            if r and r in rutas:
                if actual == ruta or not _es_rotulo(rutas[r]):
                    return (r, rutas[r])
                return None
        actual = consulta.ruta_padre(actual)
    return None

def _fecha_efecto(v: dict) -> str:
    return v.get('fecha_vigencia') or v.get('fecha_publicacion') or ''

def _alias_de_cita(con: sqlite3.Connection, ident: str) -> str:
    """Public CI documentation."""
    alias = [a['alias'] for a in con.execute('SELECT a.alias FROM obra_alias a JOIN obra o ON o.id = a.obra_id WHERE o.identificador_canonico = ?', (ident,)) if a['alias'] != ident]
    alias.sort(key=lambda a: (len(a), a))
    return alias[0] if alias else ident

def _sin_consulta(obra: str, consultado: str | None, aviso: str, estado: str) -> dict:
    return {'estado': estado, 'obra': obra, 'consultado': consultado, 'avisos': [aviso]}

def historial_de(obra: str, ruta: str, datos: dict | None, con: sqlite3.Connection | None=None, hoy: str | None=None) -> dict | None:
    """Public CI documentation."""
    if not vigencia.RE_BASE_BOE.match(obra or '') or not ruta:
        return None
    if datos is None:
        return _sin_consulta(obra, None, 'no hay consulta del historial de redacciones en esta base: no se sabe qué norma dio la redacción de este precepto ni si la base tiene la vigente', 'sin_consulta')
    hoy = hoy or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    consultado = datos.get('consultado') or ''
    try:
        dias = (datetime.fromisoformat(hoy) - datetime.fromisoformat(consultado[:10])).days
    except ValueError:
        dias = None
    o = (datos.get('obras') or {}).get(obra)
    if o is None:
        return _sin_consulta(obra, consultado, 'esta norma no está en la consulta del historial de redacciones: no se sabe qué norma dio la redacción de este precepto', 'obra_no_consultada')
    if o.get('estado') == ESTADO_SIN_TEXTO:
        return _sin_consulta(obra, consultado, f"{o.get('error') or 'el BOE no consolida esta norma'}: no hay historial de redacciones", ESTADO_SIN_TEXTO)
    if o.get('estado') != ESTADO_OK:
        return _sin_consulta(obra, consultado, f"no se pudo consultar el historial de redacciones ({o.get('error') or 'error de la fuente'})", ESTADO_ERROR)
    hallado = bloque_de(o.get('rutas') or {}, ruta)
    if hallado is None:
        return _sin_consulta(obra, consultado, 'el BOE da el historial por bloques (artículo, apartado de anexo, disposición, apéndice) y ninguno casa con esta ruta: no se sabe qué norma dio su redacción', 'sin_bloque')
    ruta_bloque, e = hallado
    h: dict = {'estado': ESTADO_OK, 'obra': obra, 'ruta': ruta, 'ruta_bloque': ruta_bloque, 'ascendiente': ruta_bloque != ruta, 'bloque': {'id': e.get('bloque'), 'titulo': e.get('titulo'), 'tipo': e.get('tipo')}, 'consultado': consultado, 'dias': dias, 'avisos': []}
    oficiales = {}
    if con is not None:
        oficiales = vigencia._oficiales_de_la_base([r[0] for r in con.execute('SELECT identificador_canonico FROM obra')])
    ordenadas = [v for _i, v in sorted(enumerate(e['versiones']), key=lambda t: (_fecha_efecto(t[1]), t[0]))]
    redacciones = []
    for v in ordenadas:
        r = dict(v, original=v['id_norma'] == obra, futura=_fecha_efecto(v) > hoy)
        propia = oficiales.get(v['id_norma'] or '')
        r['obra_en_la_base'] = propia
        r['en_la_base'] = propia is not None
        r['cita_como'] = _alias_de_cita(con, propia) if propia and con is not None else None
        redacciones.append(r)
    vigente = max((i for i, r in enumerate(redacciones) if not r['futura']), default=None)
    h['redacciones'], h['vigente'] = (redacciones, vigente)
    av = h['avisos']
    h['base_tiene_la_vigente'] = None
    if con is not None and vigente is not None:
        f = con.execute('SELECT id FROM obra WHERE identificador_canonico = ?', (obra,)).fetchone()
        fv = vigencia.fecha_de_la_version(con, f['id']) if f else {'fecha_version': None, 'fecha_version_aproximada': False}
        h['fecha_version_base'] = fv['fecha_version'] and (f"edición de {fv['fecha_version'][:4]}" if fv['fecha_version_aproximada'] else fv['fecha_version'])
        ultima = redacciones[vigente]
        publicada = ultima.get('fecha_publicacion') or _fecha_efecto(ultima)
        if not fv['fecha_version']:
            av.append('la base no sabe la fecha de su versión: no se puede saber si tiene la redacción vigente de este precepto')
        elif ultima['original'] and len(redacciones) == 1:
            h['base_tiene_la_vigente'] = True
        elif publicada > fv['fecha_version']:
            h['base_tiene_la_vigente'] = False
            seguro = not (fv['fecha_version_aproximada'] and publicada[:4] == fv['fecha_version'][:4])
            quien = 'la original' if ultima['original'] else _quien(ultima)
            av.append(('la base (versión %s) NO tiene la redacción vigente de este precepto' if seguro else 'puede que la base (versión %s) no tenga la redacción vigente de este precepto') % h['fecha_version_base'] + f': la dio {quien}, publicada el {publicada}. Lo que dice el texto de la base es una redacción anterior: no lo presentes como el texto vigente.')
        else:
            h['base_tiene_la_vigente'] = True
    for r in redacciones:
        if r['futura']:
            av.append(f"redacción aprobada que aún no ha entrado en vigor: la da {r['cita_como'] or r['id_norma']}, vigente desde {r.get('fecha_vigencia') or '?'}")
    if vigente is None:
        av.append('ninguna redacción de este precepto está todavía en vigor')
    if dias is not None and dias > DIAS_DE_VALIDEZ:
        av.append(f'la consulta del historial de redacciones tiene {dias} días: hay que actualizarla')
    return h

def _con_articulo(nombre: str) -> str:
    """Public CI documentation."""
    primera = _sin_tildes(nombre.split()[0]).lower() if nombre.split() else ''
    if primera in ('orden', 'ley', 'resolucion', 'instruccion', 'circular', 'directiva', 'correccion'):
        return 'la ' + nombre
    if primera in ('real', 'decreto', 'reglamento', 'acuerdo', 'convenio'):
        return 'el ' + nombre
    return nombre

def _quien(r: dict) -> str:
    """Public CI documentation."""
    if r['en_la_base'] and r.get('cita_como'):
        return f"{_con_articulo(r['cita_como'])} ({r['id_norma']})"
    if r['en_la_base']:
        return f"la norma {r['id_norma']}"
    return f"la norma {r['id_norma']} (que la base NO tiene)"

def _desde(r: dict, verbo: str='vigente desde') -> str:
    """Public CI documentation."""
    if r.get('fecha_vigencia'):
        return f"{verbo} {r['fecha_vigencia']}"
    return f"publicada el {r['fecha_publicacion']}" if r.get('fecha_publicacion') else ''

def _anterior(r: dict) -> str:
    if r['original']:
        return 'original' + (f' ({_desde(r)})' if _desde(r) else '')
    nombre = f"{r['cita_como']} ({r['id_norma']})" if r.get('cita_como') else f"{r['id_norma']}" + ('' if r['en_la_base'] else ' (la base NO tiene esa norma)')
    return nombre + (f", {_desde(r, 'desde')}" if _desde(r, 'desde') else '')

def texto(h: dict | None) -> str:
    """Public CI documentation."""
    if not h:
        return ''
    lineas = [f"──── REDACCIÓN (BOE, consultada {(h.get('consultado') or 'nunca')[:10]}) ────"]
    if h.get('estado') == ESTADO_OK:
        if h.get('ascendiente'):
            titulo = h['bloque'].get('titulo')
            lineas.append(f"  El BOE no da versiones de {h['ruta']} por separado: este es el historial de su ascendiente {h['ruta_bloque']}" + (f' («{titulo}»)' if titulo else '') + '.')
        reds, vigente = (h['redacciones'], h.get('vigente'))
        if vigente is not None:
            v = reds[vigente]
            desde = _desde(v)
            anteriores = reds[:vigente]
            if v['original'] and (not anteriores):
                lineas.append('  Redacción original, sin modificaciones' + (f' ({desde}).' if desde else '.'))
            elif v['original']:
                lineas.append('  Redacción vigente: la original' + (f', {desde}.' if desde else '.'))
            else:
                base = f"La base tiene esa norma: se cita como «{v['cita_como']}::…»." if v['en_la_base'] and v.get('cita_como') else ''
                lineas.append(f'  Redacción vigente: dada por {_quien(v)}' + (f', {desde}.' if desde else '.') + (f' {base}' if base else ''))
            if anteriores:
                tiene = h.get('base_tiene_la_vigente')
                nota = 'la base solo guarda la vigente' if tiene else 'la base guarda una anterior a la vigente: ver el AVISO' if tiene is False else 'la base guarda una sola de ellas'
                lineas.append(f'  Redacciones anteriores ({nota}): ' + '; '.join((_anterior(r) for r in anteriores)) + '.')
        for r in reds:
            if r['futura']:
                lineas.append(f"  Redacción futura: dada por {_quien(r)}, vigente desde {r.get('fecha_vigencia') or '?'} (aún no en vigor).")
    for a in h.get('avisos') or []:
        lineas.append(f'  AVISO: {a}')
    if h.get('estado') == ESTADO_OK:
        lineas.append(f'  {AVISO_BOE}.')
    return '\n'.join(lineas)

def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(prog='python -m ict155.historial_boe', description='Instantánea del historial de redacciones de las normas del BOE de la base.')
    ap.add_argument('--salida', required=True, help='fichero JSON de la instantánea')
    ap.add_argument('--base', default=None, help='base de datos (por defecto la de producción; solo lectura)')
    args = ap.parse_args(argv)
    ruta_base = Path(args.base) if args.base else config.BD
    datos = instantanea(ruta_base, progreso=lambda s: print(s, file=sys.stderr, flush=True))
    escribir_instantanea(datos, args.salida)
    print(resumen(datos))
    print(f'escrita {args.salida}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
