"""Public CI documentation."""
from __future__ import annotations
import re
import subprocess
import tempfile
from pathlib import Path
from . import config
from .ocr import TESSDATA, TESSERACT, OcrNoDisponible, _env
RADIO_DESENFOQUE = 1.0
IDIOMA = 'eng'
PSM = '6'
UMBRAL_ALFABETICO = 0.55
MINIMO_CARACTERES = 12
UMBRAL_FRAGMENTOS = 0.6
SENAL_DE_CONTENIDO = (re.compile('\\d+(?:[.,]\\d+)?\\s*°\\s*[CF]'), re.compile('[±<>≤≥]\\s*\\d'), re.compile('^\\s*\\d+(?:\\.\\d+){1,3}\\s*$'), re.compile('\\b(?:Table|Tabla|Figure|Figura|Annex|Anexo)\\b', re.I), re.compile('\\bEN\\s?\\d{4,5}\\b|\\bISO\\s?\\d+\\b'), re.compile('\\bk\\s*=\\s*\\d'))

def _preparar(origen: Path, destino: Path) -> Path:
    from PIL import Image, ImageFilter, ImageOps
    im = Image.open(origen)
    im = ImageOps.exif_transpose(im)
    im = im.convert('L')
    im = im.filter(ImageFilter.GaussianBlur(RADIO_DESENFOQUE))
    im.save(destino)
    return destino
RE_PALABRA_LARGA = re.compile('[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{5,}')

def _es_texto(linea: str) -> bool:
    """Public CI documentation."""
    s = linea.strip()
    if not s:
        return False
    if any((p.search(s) for p in SENAL_DE_CONTENIDO)):
        return True
    tokens = s.split()
    fragmentos = sum((1 for t in tokens if len(t) <= 2))
    if tokens and fragmentos / len(tokens) > UMBRAL_FRAGMENTOS:
        return False
    if RE_PALABRA_LARGA.search(s):
        return True
    if len(s) < MINIMO_CARACTERES:
        return False
    letras = sum((1 for c in s if c.isalpha()))
    return letras / len(s) >= UMBRAL_ALFABETICO

def limpiar(texto: str) -> tuple[str, int]:
    """Public CI documentation."""
    vivas, muertas = ([], 0)
    for ln in texto.splitlines():
        if not ln.strip():
            continue
        if _es_texto(ln):
            vivas.append(ln.rstrip())
        else:
            muertas += 1
    return ('\n'.join(vivas), muertas)

def reconocer(origen: Path) -> tuple[str, int, int]:
    """Public CI documentation."""
    with tempfile.TemporaryDirectory() as tmp:
        img = _preparar(origen, Path(tmp) / 'p.png')
        p = subprocess.run([str(TESSERACT), str(img), 'stdout', '-l', IDIOMA, '--psm', PSM], capture_output=True, timeout=600, env={**_env(), 'TESSDATA_PREFIX': str(TESSDATA)})
    if p.returncode != 0:
        raise OcrNoDisponible(f'tesseract rc={p.returncode} en {origen.name}: ' + p.stderr.decode('utf-8', 'replace')[:300])
    crudo = p.stdout.decode('utf-8', 'replace')
    limpio, muertas = limpiar(crudo)
    return (limpio, len(limpio.splitlines()), muertas)
RE_CLAUSULA = re.compile('^\\s*(\\d+(?:\\.\\d+)*)\\s+([A-Z][^\\n]{2,80})$')
RE_ANEXO = re.compile('^\\s*Annex\\s+([A-Z])\\b(.*)$', re.I)
RE_TABLA = re.compile('^\\s*(Table|Figure)\\s+([A-Z]?\\.?\\d+)', re.I)

def _podar(etiqueta: str) -> str:
    palabras = etiqueta.rstrip().split()
    while len(palabras) > 2:
        u = palabras[-1]
        if len(u) <= 3 and (not u.isalpha()):
            palabras.pop()
        elif len(u) <= 2 and u.lower() not in ('of', 'in', 'to', 'de'):
            palabras.pop()
        else:
            break
    return ' '.join(palabras)

def trocear(texto: str, pagina: int) -> list[dict]:
    """Public CI documentation."""
    out: list[dict] = []
    actual = {'ruta': f'pag.{pagina}', 'etiqueta': f'Pagina {pagina}', 'lineas': [], 'pagina': pagina}
    for ln in texto.splitlines():
        mt = RE_TABLA.match(ln)
        ma = RE_ANEXO.match(ln)
        mc = RE_CLAUSULA.match(ln)
        if mt:
            out.append(actual)
            out.append({'ruta': f"tabla.{mt.group(2).strip('.')}", 'etiqueta': f'{mt.group(1).title()} {mt.group(2)}', 'lineas': [], 'pagina': pagina, 'sin_ocr': True})
            actual = {'ruta': f'pag.{pagina}.cont', 'etiqueta': f'Pagina {pagina}', 'lineas': [], 'pagina': pagina}
        elif ma:
            out.append(actual)
            actual = {'ruta': f'anexo.{ma.group(1).upper()}', 'etiqueta': _podar(f'Annex {ma.group(1).upper()}{ma.group(2)}')[:120], 'lineas': [], 'pagina': pagina}
        elif mc:
            out.append(actual)
            actual = {'ruta': f'ap.{mc.group(1)}', 'etiqueta': _podar(f'{mc.group(1)} {mc.group(2)}')[:120], 'lineas': [], 'pagina': pagina}
        else:
            actual['lineas'].append(ln)
    out.append(actual)
    return [b for b in out if b['lineas'] or b.get('sin_ocr')]

def _unificar(paginas: list[dict]) -> list[dict]:
    """Public CI documentation."""
    orden: list[str] = []
    juntos: dict[str, dict] = {}
    for pag in paginas:
        for b in pag['bloques']:
            ruta = b['ruta']
            if ruta.startswith('pag.'):
                ruta = f"pag.{b['pagina']}"
                b = {**b, 'ruta': ruta}
            if ruta not in juntos:
                juntos[ruta] = {**b, 'lineas': list(b['lineas'])}
                orden.append(ruta)
            else:
                juntos[ruta]['lineas'] += b['lineas']
    return [juntos[r] for r in orden]

def procesar_carpeta(rel_carpeta: str) -> list[dict]:
    """Public CI documentation."""
    base = config.BIBLIOTECA / rel_carpeta
    fotos = sorted((p for p in base.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png')))
    salida = []
    for i, f in enumerate(fotos, 1):
        texto, vivas, muertas = reconocer(f)
        salida.append({'foto': f.name, 'pagina': i, 'texto': texto, 'lineas': vivas, 'descartadas': muertas, 'bloques': trocear(texto, i)})
    return salida

def preceptos_de(rel_carpeta: str) -> tuple[list[dict], dict]:
    """Public CI documentation."""
    paginas = procesar_carpeta(rel_carpeta)
    bloques = _unificar(paginas)
    preceptos, sin_ocr = ([], [])
    for b in bloques:
        if b.get('sin_ocr'):
            sin_ocr.append(b['ruta'])
            continue
        texto = '\n'.join(b['lineas']).strip()
        if len(texto) < 40:
            continue
        preceptos.append(dict(ruta=b['ruta'], etiqueta=b['etiqueta'], pagina=b['pagina'], texto=texto))
    resumen = dict(fotos=len(paginas), lineas=sum((p['lineas'] for p in paginas)), descartadas=sum((p['descartadas'] for p in paginas)), preceptos=len(preceptos), tablas_sin_ocr=sorted(set(sin_ocr)))
    return (preceptos, resumen)
