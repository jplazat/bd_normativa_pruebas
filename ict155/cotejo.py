"""Public CI documentation."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from . import superindices
COINCIDE = 'COINCIDE'
NO_COINCIDE = 'NO_COINCIDE'
SIN_PRECEPTO = 'SIN_PRECEPTO'
SIN_AFIRMACION = 'SIN_AFIRMACION'
UMBRAL = 0.85
VACIAS = frozenset('\na al ante bajo con contra de del desde durante en entre hacia hasta mediante\npara por segun sin so sobre tras y e ni o u que qui, quien cuyo cual cuales\nel la los las un una unos unas lo\nse su sus le les me te nos os\nser es son sea sean fue fueron era eran estar esta estan este esta estos estas\nhaber ha han habia hay hubiera\ncomo cuando donde mientras si no\nmas menos muy tambien tanto todo toda todos todas cada\n'.split())

def normalizar(s: str) -> list[str]:
    s = unicodedata.normalize('NFKD', superindices.plegar(s or ''))
    s = ''.join((c for c in s if not unicodedata.combining(c)))
    return [w for w in re.split('[^\\w]+', s.lower()) if w]

def con_contenido(palabras: list[str]) -> list[str]:
    """Public CI documentation."""
    return [w for w in palabras if w not in VACIAS and len(w) > 2]

@dataclass
class Cotejo:
    estado: str
    proporcion: float = 0.0
    faltan: list[str] = field(default_factory=list)
    n_afirmacion: int = 0
    detalle: str | None = None

def cotejar(texto_precepto: str | None, afirmacion: str, umbral: float=UMBRAL) -> Cotejo:
    """Public CI documentation."""
    if not texto_precepto:
        return Cotejo(SIN_PRECEPTO, detalle='el precepto no tiene texto en la base: no se puede cotejar, y eso NO significa que la afirmacion sea falsa')
    en_precepto = set(con_contenido(normalizar(texto_precepto)))
    pedidas = con_contenido(normalizar(afirmacion))
    if not pedidas:
        return Cotejo(SIN_AFIRMACION, detalle='la afirmacion no tiene palabras con contenido que cotejar')
    faltan = [w for w in dict.fromkeys(pedidas) if w not in en_precepto]
    prop = 1 - len(faltan) / len(set(pedidas))
    estado = COINCIDE if prop >= umbral else NO_COINCIDE
    return Cotejo(estado, round(prop, 3), faltan, len(set(pedidas)))
