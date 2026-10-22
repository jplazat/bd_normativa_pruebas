"""Correcciones R3-B verificadas para seis ejemplares públicos R3.

Ruta y huella del fichero presente forman la frontera de despliegue. Las reglas no
se activan en otras altas o ediciones. No contienen transcripción
normativa ni sustituyen palabras: orientan la lectura de encabezados y páginas.
"""
import re
from functools import lru_cache
from . import alcance_r3
OBRAS = frozenset({'CELEX-32006L0125', 'CELEX-32011R0010', 'BOE-A-2006-22961', 'CELEX-32019R2144', 'CELEX-32007L0045', 'BOE-A-2015-10566'})
PAGINAS_RAW = {'CELEX-32006L0125': (4, 5), 'BOE-A-2006-22961': (23, 24)}
TABLA = re.compile('(?i)\\btablas?\\s+de\\s+correspondencias\\b')
ANEXO_SIN_NUMERAL = re.compile('^ANEXO\\s+(GAMAS\\s+DE\\s+LAS\\s+CANTIDADES\\b.*)$')
SUBSECCION = re.compile('^Subsecci[óo]n\\s+\\d+\\.\\s?[ªa]\\s+[A-ZÁÉÍÓÚÑ]')

def identidad(ruta, huella):
    if not huella or not alcance_r3.activa(ruta, huella):
        return None
    return _por_ejemplar().get((ruta, huella))

@lru_cache(maxsize=1)
def _por_ejemplar():
    import json
    from . import config
    ns = json.loads((config.DATOS_REPO / 'alta_r3.json').read_text(encoding='utf-8'))['normas']
    return {(n['ruta_relativa'], n['sha256_pdf']): n['identificador'] for n in ns if n['identificador'] in OBRAS}

def de_pdf(pdf):
    return identidad(pdf.ruta_relativa, pdf.sha256)

def encabezado_boe(s, ident):
    """Solo para reconocimiento; el renglón literal original se conserva."""
    if ident == 'BOE-A-2006-22961':
        return re.sub('^A\\s+N\\s+E\\s+X\\s+O(?=\\s+(?:VI|VII)\\s*$)', 'ANEXO', s)
    return s

def empieza_subseccion(lineas, k):
    """Sección real seguida de subsección y artículo; una remisión no basta."""
    utiles = [ln.strip() for ln, _ in lineas[k + 1:k + 12] if ln.strip()]
    return bool(utiles and SUBSECCION.match(utiles[0]) and any((re.match('^Artículo\\s+\\d+\\.', s) for s in utiles[1:])))
