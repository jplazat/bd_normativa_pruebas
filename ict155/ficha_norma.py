"""Public CI documentation."""
from __future__ import annotations
import re
from . import config
RE_SECCION = re.compile('^##\\s+\\d+(?:\\s+(?:bis|ter|quater))?\\.\\s+(.*)$', re.I)
RE_TABLA = re.compile('^###\\s+Tabla\\s+([A-Z]?\\.?\\d+)\\s*(?:[—\\-–]\\s*(.*))?$', re.I)
RE_SUBCLAUSULA = re.compile('^###\\s+(\\d+(?:\\.\\d+)*)\\s+(.*)$')
RE_CLAUSULA_EN_TITULO = re.compile('cl[áa]usula\\s+(\\d+(?:\\.\\d+)*)', re.I)
RE_ANEXO_EN_TITULO = re.compile('anexo\\s+([A-Z])\\b', re.I)
RE_PAGINA = re.compile('p[áa]gina[s]?\\s+(\\d+)', re.I)
RE_TABLA_INLINE = re.compile('^\\*\\*Tabla\\s+([A-Z]?\\.?\\d+)\\s*(?:[—\\-–]\\s*([^*]*?))?\\.?\\*\\*\\s*$', re.I)
RE_SUBCLAUSULA_INLINE = re.compile('^\\*\\*(\\d+(?:\\.\\d+)+)\\s+([^*]{2,70}?)\\.?\\*\\*\\s*(.*)$')
SECCIONES_META = ('Identificación', 'Estructura', 'Qué cambió', 'Bibliografía', 'Lo que esta ficha NO cubre', 'Notas de uso', 'Documentos relacionados', 'Régimen de uso', 'Procedencia')

def _ruta_de_titulo(titulo: str) -> tuple[str | None, int]:
    pagina = int(RE_PAGINA.search(titulo).group(1)) if RE_PAGINA.search(titulo) else 1
    ma = RE_ANEXO_EN_TITULO.search(titulo)
    if ma:
        return (f'anexo.{ma.group(1).upper()}', pagina)
    mc = RE_CLAUSULA_EN_TITULO.search(titulo)
    if mc:
        return (f'ap.{mc.group(1)}', pagina)
    return (None, pagina)

def analizar(ruta_rel: str) -> list[dict]:
    """Public CI documentation."""
    texto = config.abrir_biblioteca(config.BIBLIOTECA / ruta_rel).read()
    preceptos: list[dict] = []
    ruta = None
    pagina = 1
    buf: list[str] = []
    etiqueta = ''

    def cerrar():
        cuerpo = '\n'.join(buf).strip()
        if ruta and len(cuerpo) >= 30:
            preceptos.append(dict(ruta=ruta, etiqueta=etiqueta[:120], pagina=pagina, texto=cuerpo))
    for ln in texto.split('\n'):
        ms = RE_SECCION.match(ln)
        mt = RE_TABLA.match(ln)
        msc = RE_SUBCLAUSULA.match(ln)
        mi = RE_SUBCLAUSULA_INLINE.match(ln)
        mti = RE_TABLA_INLINE.match(ln)
        if ms:
            cerrar()
            buf = []
            titulo = ms.group(1).strip()
            if any((k.lower() in titulo.lower() for k in SECCIONES_META)):
                ruta, etiqueta = (None, '')
                continue
            ruta, pagina = _ruta_de_titulo(titulo)
            etiqueta = titulo
        elif mt:
            cerrar()
            buf = []
            ruta = f"tabla.{mt.group(1).strip('.')}"
            etiqueta = f'Tabla {mt.group(1)}' + (f' — {mt.group(2)}' if mt.group(2) else '')
            if RE_PAGINA.search(ln):
                pagina = int(RE_PAGINA.search(ln).group(1))
        elif mti:
            cerrar()
            buf = []
            ruta = f"tabla.{mti.group(1).strip('.')}"
            etiqueta = f'Tabla {mti.group(1)}' + (f' — {mti.group(2).strip()}' if mti.group(2) else '')
            if RE_PAGINA.search(ln):
                pagina = int(RE_PAGINA.search(ln).group(1))
        elif msc:
            cerrar()
            buf = []
            ruta = f'ap.{msc.group(1)}'
            etiqueta = f'{msc.group(1)} {msc.group(2)}'[:120]
            if RE_PAGINA.search(ln):
                pagina = int(RE_PAGINA.search(ln).group(1))
        elif mi:
            cerrar()
            buf = [mi.group(3)]
            ruta = f'ap.{mi.group(1)}'
            etiqueta = f'{mi.group(1)} {mi.group(2)}'[:120]
        else:
            buf.append(ln)
    cerrar()
    juntos: dict[str, dict] = {}
    for p in preceptos:
        if p['ruta'] in juntos:
            juntos[p['ruta']]['texto'] += '\n\n' + p['texto']
        else:
            juntos[p['ruta']] = p
    return list(juntos.values())
