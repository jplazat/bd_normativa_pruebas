"""Alcance explícito de los ejemplares R3 por ruta y SHA256 del PDF.

El PDF y el texto extraído se conservan completos. Se recortan exclusivamente
las líneas entregadas al troceador, conservando los ordinales de página.
"""
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path
from threading import Lock
from . import config

@lru_cache(maxsize=None)
def _registro(datos_repo):
    p = datos_repo / 'alta_r3.json'
    if not p.exists():
        return ({}, {})
    ns = json.loads(p.read_text(encoding='utf-8'))['normas']
    return ({r['ruta_relativa']: r['identificador'] for r in ns}, {r['ruta_relativa']: r['sha256_pdf'] for r in ns})

def altas():
    return _registro(config.DATOS_REPO)[0]
_candado_huellas = Lock()

@lru_cache(maxsize=None)
def _huella(ruta, tamano, mtime_ns, ctime_ns):
    h = hashlib.sha256()
    with config.abrir_biblioteca(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    st = ruta.stat()
    if (st.st_size, st.st_mtime_ns, st.st_ctime_ns) != (tamano, mtime_ns, ctime_ns):
        raise OSError('El ejemplar R3 cambió durante el cálculo de su huella')
    return h.hexdigest()

def huella_fichero(ruta):
    """Una lectura por ruta/tamaño/fechas; compartida con la extracción R3."""
    ruta = Path(ruta).resolve()
    with _candado_huellas:
        st = ruta.stat()
        return _huella(ruta, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

@lru_cache(maxsize=1)
def perfiles():
    return json.loads((config.DATOS_REPO / 'alcance_r3.json').read_text(encoding='utf-8'))['perfiles']

def activa(ruta, huella=None):
    registrada = _registro(config.DATOS_REPO)[1].get(ruta)
    if not registrada or (huella and huella != registrada):
        return False
    try:
        return huella_fichero(config.ruta_biblioteca(ruta)) == registrada
    except (OSError, ValueError, config.EscrituraEnBibliotecaError):
        return False

def seleccionar_paginas(paginas, perfil):
    """No recompone texto ni números; elimina bloques fuera del contrato."""
    anexo = None
    encontrados = set()
    salida = []
    en_cuerpo = not perfil.get('ignorar_indice_boe', False)
    cabecera = re.compile('^(?:ANEXO|ANEJO)(?:\\s+([IVXLCDM]+|\\d+|[ÚU]NICO)(?=[ .:]|$)(?:[ .:].*)?)?$')
    for pagina in paginas:
        lineas = []
        for ln in pagina.splitlines():
            limpio = re.sub('^(?:[►▼][A-Z]\\d*\\s*)+', '', ln.strip())
            if limpio.startswith('TEXTO CONSOLIDADO'):
                en_cuerpo = True
            m = cabecera.fullmatch(limpio) if en_cuerpo else None
            if m:
                anexo = m[1] or 'sn'
                encontrados.add(anexo)
            if anexo is None or anexo in perfil['anexos']:
                lineas.append(ln)
        salida.append('\n'.join(lineas))
    faltan = set(perfil['anexos']) - encontrados
    if not encontrados or faltan:
        raise ValueError('No se acredita la frontera de anexos del perfil R3: ' + str(sorted(faltan)))
    return salida

def para_trocear(pdf):
    if not activa(pdf.ruta_relativa, pdf.sha256):
        return pdf
    perfil = perfiles().get(altas()[pdf.ruta_relativa])
    if perfil is None:
        return pdf
    return replace(pdf, paginas=seleccionar_paginas(pdf.paginas, perfil), paginas_del_documento=pdf.n_paginas)

def seleccionar_texto(texto, identificador):
    perfil = perfiles().get(identificador)
    if perfil is None:
        return (texto, None)
    bloques = re.split('^===== PÁGINA (\\d+) =====\\n', texto, flags=re.M)
    if bloques[0].strip() or len(bloques) < 3:
        raise ValueError('El perfil R3 exige el volcado con ordinales del motor')
    numeros = bloques[1::2]
    paginas = bloques[2::2]
    seleccion = seleccionar_paginas(paginas, perfil)
    return ('\n'.join((f'===== PÁGINA {n} =====\n{p}' for n, p in zip(numeros, seleccion))), perfil)
