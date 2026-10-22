"""Public CI documentation."""
from __future__ import annotations
import json
import re
from . import config, fundamento
INVENTARIO = '03_Proyecto_BD_Normativa/01_Inventario/EMISOR_declarado_ZCODE.md'
MAPA = 'emisor_declarado.json'
DECLARADO = 'declarado_en_documento'
INFERIDO = 'inferido_de_nombre_fichero'
RX_ENTRADA = re.compile('^###\\s+(E10-\\d+)\\s+(.+?)\\s*$', re.M)
RX_BLOQUE = re.compile('^(?!>)(.{0,140}?)\\(([^()]*)\\)\\s*:\\s*$', re.M)
RX_ES_EMISOR = re.compile('emisor', re.I)
SITIOS_QUE_NOMBRAN = frozenset(('membrete', 'cabecera', 'pie', 'pie de copyright', 'colofon', 'firma'))

def sitio_nombra(sitio: str | None) -> bool:
    return (sitio or '').split(',')[0].strip().lower() in SITIOS_QUE_NOMBRAN
_ACENTOS = set('áéíóúÁÉÍÓÚñÑüÜ¿¡')

def reparar_codificacion(s: str) -> str:
    """Public CI documentation."""
    try:
        r = s.encode('cp850').decode('latin-1')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    n = sum((1 for c in s if c in _ACENTOS))
    return r if sum((1 for c in r if c in _ACENTOS)) > n else s

def parsear_inventario(texto: str) -> list[dict]:
    """Public CI documentation."""
    entradas = []
    trozos = list(RX_ENTRADA.finditer(texto))
    for i, m in enumerate(trozos):
        fin = trozos[i + 1].start() if i + 1 < len(trozos) else len(texto)
        cuerpo = texto[m.end():fin]
        bloques: list[dict] = []
        estado = {'rotulo': None, 'sitio': None, 'lineas': []}

        def cerrar():
            if estado['lineas'] and estado['rotulo'] is not None:
                bloques.append({'rotulo': estado['rotulo'].strip(), 'sitio': estado['sitio'], 'frase': ' '.join(estado['lineas'])})
            estado['lineas'] = []
        for linea in cuerpo.splitlines():
            mb = RX_BLOQUE.match(linea)
            if mb:
                cerrar()
                estado['rotulo'], estado['sitio'] = (mb.group(1), mb.group(2))
                continue
            if linea.startswith('> '):
                estado['lineas'].append(reparar_codificacion(linea[2:].strip()))
            elif estado['lineas']:
                cerrar()
        cerrar()
        entradas.append({'id': m.group(1), 'fichero': m.group(2).strip(), 'bloques': bloques})
    return entradas

def generar(con) -> list[dict]:
    """Public CI documentation."""
    with config.abrir_biblioteca(config.ruta_biblioteca(INVENTARIO)) as fh:
        entradas = parsear_inventario(fh.read())
    docs = {}
    for f in con.execute('\n            SELECT d.ruta_relativa, d.estado_ingesta AS estado,\n                   o.identificador_canonico AS ident\n            FROM documento d\n            LEFT JOIN version v ON v.documento_id = d.id\n            LEFT JOIN obra o    ON o.id = v.obra_id'):
        docs[f['ruta_relativa'].rsplit('/', 1)[-1]] = (f['estado'], f['ident'])
    mapa = []
    for e in entradas:
        info = docs.get(e['fichero'])
        if not info or info[0] != 'ingerido' or (not info[1]):
            continue
        ident = info[1]
        for b in e['bloques']:
            if not RX_ES_EMISOR.search(b['rotulo']):
                continue
            r = fundamento.localizar(con, b['frase'], ident)
            if r.estado != fundamento.LOCALIZADO:
                continue
            mapa.append({'entrada': e['id'], 'fichero': e['fichero'], 'identificador': ident, 'sitio': (b['sitio'] or '').strip(), 'rotulo': b['rotulo'], 'frase': b['frase'], 'fundamento': r.fundamento})
            break
    mapa.sort(key=lambda x: x['entrada'])
    return mapa

def cargar_mapa() -> list[dict]:
    """Public CI documentation."""
    ruta = config.DATOS_REPO / MAPA
    if not ruta.exists():
        return []
    return json.loads(ruta.read_text(encoding='utf-8'))

def sellar(con, verbose: bool=False) -> dict:
    """Public CI documentation."""
    sellados = muertos = sin_obra = narran = 0
    obras = set()
    for e in cargar_mapa():
        ident, ruta = e['fundamento'].split('::', 1)
        fila = con.execute('SELECT id FROM obra WHERE identificador_canonico = ?', (ident,)).fetchone()
        if fila is None:
            sin_obra += 1
            continue
        existe = con.execute('\n            SELECT 1 FROM precepto p\n            JOIN version v ON v.id = p.version_id\n            WHERE v.obra_id = ? AND p.ruta_estructural = ?', (fila['id'], ruta)).fetchone()
        if existe is None:
            muertos += 1
            continue
        if sitio_nombra(e['sitio']):
            con.execute('UPDATE obra SET emisor = ?, emisor_metodo = ?, emisor_fundamento = ?, emisor_frase = ? WHERE id = ?', (e['frase'], DECLARADO, e['fundamento'], e['frase'], fila['id']))
            sellados += 1
            obras.add(fila['id'])
        else:
            con.execute('UPDATE obra SET emisor_fundamento = ?, emisor_frase = ? WHERE id = ?', (e['fundamento'], e['frase'], fila['id']))
            narran += 1
    if verbose:
        print(f'emisor declarado en documento: {len(obras)} obras ({sellados} entradas del inventario)  |  frase y ruta sin nombre destilado: {narran}' + (f'  |  fundamento que ya no resuelve: {muertos}' if muertos else '') + (f'  |  sin obra: {sin_obra}' if sin_obra else ''))
    return {'sellados': sellados, 'obras': len(obras), 'narran': narran, 'muertos': muertos, 'sin_obra': sin_obra}
