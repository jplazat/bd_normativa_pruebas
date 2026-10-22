"""Public CI documentation."""
from __future__ import annotations
import os
import re
import subprocess
import unicodedata
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from . import config
TESSERACT = Path(os.environ.get('ICT155_TESSERACT', 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'))
TESSDATA = config.REPO / 'tessdata'
IDIOMAS = 'spa+eng+fra+rus+chi_sim'
PPP_BASE = 300
PPP_VERIFICACION = 600

class OcrNoDisponible(RuntimeError):
    pass

def disponible() -> bool:
    return TESSERACT.exists() and (TESSDATA / 'spa.traineddata').exists()

def _tesseract(imagen: Path, ppp: int | None=None, psm: int=3) -> str:
    if not disponible():
        raise OcrNoDisponible(f'falta tesseract en {TESSERACT} o los modelos en {TESSDATA}')
    cmd = [str(TESSERACT), str(imagen), 'stdout', '-l', IDIOMAS, '--psm', str(psm)]
    if ppp:
        cmd += ['--dpi', str(ppp)]
    p = subprocess.run(cmd, capture_output=True, timeout=600, env={**_env(), 'TESSDATA_PREFIX': str(TESSDATA)})
    if p.returncode != 0:
        raise OcrNoDisponible(p.stderr.decode('utf-8', 'replace')[:300])
    return p.stdout.decode('utf-8', 'replace')

def _env() -> dict:
    import os
    return dict(os.environ)

def _rasterizar(pdf: Path, pagina: int, ppp: int, destino: Path, region=None) -> Path:
    """Public CI documentation."""
    import fitz
    doc = fitz.open(pdf)
    pg = doc[pagina - 1]
    clip = fitz.Rect(*region) if region else None
    pix = pg.get_pixmap(dpi=ppp, clip=clip)
    pix.save(destino)
    doc.close()
    return destino

@dataclass
class Campo:
    nombre: str
    valor: str
    pagina: int
    region: tuple
    verificado: bool = False
    corregido: bool = False
    valor_previo: str | None = None

@dataclass
class ResultadoOcr:
    ruta_rel: str
    paginas: list[str] = field(default_factory=list)
    campos: list[Campo] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return '\n'.join(self.paginas)
PATRONES = {'numero_certificado': re.compile('\\b(\\d{2}[.\\-\\s]?[A-Z][.\\-\\s]?\\d{3,5}(?:[.\\-\\s]?\\d+)?|\\d{4}LT\\d{4}|CEM\\d{8}|E\\s?\\d{3})\\b'), 'entidad_emisora': re.compile('((?:Centro Español de Metrolog[íi]a|EMISOR_DEMO_FR|Laboratoire[^\\n]{0,40}|Ministerio[^\\n]{0,60}|Consejer[íi]a[^\\n]{0,60}|Generalitat[^\\n]{0,40}))'), 'fecha': re.compile('\\b(\\d{1,2}\\s+de\\s+[a-záéíóú]+\\s+de\\s+\\d{4}|\\d{2}[/.\\-]\\d{2}[/.\\-]\\d{4})\\b', re.I), 'alcance': re.compile('((?:registrador|termómetro|thermom|enregistreur|indicador)[^\\n]{10,90})', re.I)}

def _cajas(imagen: Path, ppp: int) -> list[tuple[str, float, float, float, float]]:
    """Public CI documentation."""
    cmd = [str(TESSERACT), str(imagen), 'stdout', '-l', IDIOMAS, '--psm', '3', 'tsv']
    p = subprocess.run(cmd, capture_output=True, timeout=600, env={**_env(), 'TESSDATA_PREFIX': str(TESSDATA)})
    if p.returncode != 0:
        raise OcrNoDisponible(p.stderr.decode('utf-8', 'replace')[:300])
    escala = ppp / 72.0
    out = []
    for ln in p.stdout.decode('utf-8', 'replace').splitlines()[1:]:
        c = ln.split('\t')
        if len(c) < 12 or not c[11].strip():
            continue
        x, y, w, h = (int(c[6]), int(c[7]), int(c[8]), int(c[9]))
        out.append((c[11].strip(), x / escala, y / escala, (x + w) / escala, (y + h) / escala))
    return out

def _region_de(cajas, valor: str, alto: float, ancho: float) -> tuple | None:
    """Public CI documentation."""
    objetivo = re.sub('\\s+', '', valor).lower()
    if len(objetivo) < 3:
        return None
    for i in range(len(cajas)):
        junto = ''
        for j in range(i, min(i + 8, len(cajas))):
            junto += re.sub('\\s+', '', cajas[j][0]).lower()
            if objetivo in junto or (len(junto) > 6 and junto in objetivo):
                y0 = min((c[2] for c in cajas[i:j + 1]))
                y1 = max((c[4] for c in cajas[i:j + 1]))
                margen = max(16.0, (y1 - y0) * 1.6)
                return (0, max(0, y0 - margen), ancho, min(alto, y1 + margen))
            if len(junto) > len(objetivo) + 24:
                break
    return None

def procesar(ruta_rel: str, max_paginas: int=12) -> ResultadoOcr:
    """Public CI documentation."""
    import fitz
    pdf = config.ruta_biblioteca(ruta_rel)
    res = ResultadoOcr(ruta_rel=ruta_rel)
    doc = fitz.open(pdf)
    n = min(doc.page_count, max_paginas)
    doc.close()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cajas_por_pagina = {}
        doc = fitz.open(pdf)
        medidas = {pg: (doc[pg - 1].rect.height, doc[pg - 1].rect.width) for pg in range(1, n + 1)}
        doc.close()
        for pg in range(1, n + 1):
            img = _rasterizar(pdf, pg, PPP_BASE, tmp / f'p{pg}.png')
            res.paginas.append(_tesseract(img, PPP_BASE))
            cajas_por_pagina[pg] = _cajas(img, PPP_BASE)
        for pg, texto in enumerate(res.paginas, start=1):
            alto, ancho = medidas[pg]
            for nombre, pat in PATRONES.items():
                for m in list(pat.finditer(texto))[:2]:
                    valor = m.group(1).strip()
                    reg = _region_de(cajas_por_pagina[pg], valor, alto, ancho)
                    if reg is None:
                        continue
                    c = Campo(nombre=nombre, valor=valor, pagina=pg, region=reg)
                    _verificar(pdf, c, tmp)
                    res.campos.append(c)
    return res

def _norm_cmp(t: str) -> str:
    """Public CI documentation."""
    t = unicodedata.normalize('NFD', t.lower())
    t = ''.join((ch for ch in t if unicodedata.category(ch) != 'Mn'))
    return re.sub('[^a-z0-9]', '', t)
NO_LEGIBLE = 'NO LEGIBLE'

def _parecido(a: str, b: str) -> bool:
    if not a or not b or abs(len(a) - len(b)) > 2:
        return False
    import difflib
    distintos = sum((1 for op in difflib.SequenceMatcher(None, a, b).get_opcodes() if op[0] != 'equal'))
    return distintos <= max(1, min(len(a), len(b)) // 5)

def _verificar(pdf: Path, c: Campo, tmp: Path) -> None:
    """Public CI documentation."""
    img = _rasterizar(pdf, c.pagina, PPP_VERIFICACION, tmp / f'v{c.pagina}_{c.nombre}_{abs(hash(c.valor)) % 9999}.png', region=c.region)
    texto = _tesseract(img, PPP_VERIFICACION, psm=6)
    if _norm_cmp(c.valor) and _norm_cmp(c.valor) in _norm_cmp(texto):
        c.verificado = True
        return
    for m in PATRONES[c.nombre].finditer(texto):
        cand = m.group(1).strip()
        if _norm_cmp(cand) == _norm_cmp(c.valor):
            c.verificado = True
            return
        if _parecido(_norm_cmp(cand), _norm_cmp(c.valor)):
            c.valor_previo, c.valor = (c.valor, cand)
            c.corregido = c.verificado = True
            return
    img2 = _rasterizar(pdf, c.pagina, PPP_VERIFICACION, tmp / f'w{c.pagina}_{c.nombre}.png')
    if _norm_cmp(c.valor) in _norm_cmp(_tesseract(img2, PPP_VERIFICACION)):
        c.verificado = True
        return
    c.valor_previo, c.valor = (c.valor, NO_LEGIBLE)
    c.verificado = False
