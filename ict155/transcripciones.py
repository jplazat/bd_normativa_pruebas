"""Public CI documentation."""
from __future__ import annotations
import io
import json
import re
from pathlib import Path
from . import config
FICHA = '01_Conocimiento/Normas_tecnicas/NORMA_PAGO_49.md'

def _bloques_de_la_ficha() -> dict[str, tuple[str, str]]:
    """Public CI documentation."""
    ruta = config.BIBLIOTECA / FICHA
    if not ruta.exists():
        return {}
    lineas = config.abrir_biblioteca(ruta).read().split('\n')
    out: dict[str, tuple[str, str]] = {}
    clave = titulo = None
    cuerpo: list[str] = []
    for ln in lineas:
        m = re.match('^### (10 (?:ter|quater))\\.(\\S+)\\s+(.*)$', ln)
        if m:
            if clave:
                out[clave] = (titulo, '\n'.join(cuerpo).strip())
            clave = f'{m.group(1)}.{m.group(2)}'
            titulo, cuerpo = (m.group(3).strip(), [])
        elif ln.startswith('## ') and clave:
            out[clave] = (titulo, '\n'.join(cuerpo).strip())
            clave = None
        elif clave is not None:
            cuerpo.append(ln)
    if clave:
        out[clave] = (titulo, '\n'.join(cuerpo).strip())
    return out

def cargar() -> list[dict]:
    """Public CI documentation."""
    dir_t = config.DATOS_REPO / 'transcripciones'
    if not dir_t.exists():
        return []
    bloques = _bloques_de_la_ficha()
    out = []
    for f in sorted(dir_t.glob('*.json')):
        if f.name.startswith('_'):
            continue
        d = json.loads(io.open(f, encoding='utf-8').read())
        vivos = []
        for p in d['preceptos']:
            trozos = []
            for clave in [x.strip() for x in re.split('\\s+y\\s+|,', p['fuente'])]:
                if clave in bloques:
                    tit, cuerpo = bloques[clave]
                    trozos.append(f'[{clave}] {tit}\n{cuerpo}')
            if trozos:
                p['texto'] = '\n\n'.join(trozos)
                vivos.append(p)
        d['preceptos'] = vivos
        d['origen'] = 'repo:' + f.relative_to(config.REPO).as_posix()
        out.append(d)
    return out

def cargar_ocr() -> list[dict]:
    """Public CI documentation."""
    dir_o = config.DATOS_REPO / 'ocr'
    if not dir_o.exists():
        return []
    out = []
    for f in sorted(dir_o.glob('*.json')):
        d = json.loads(io.open(f, encoding='utf-8').read())
        campos = [c for c in d['campos'] if c['verificado']]
        out.append(dict(obra=Path(d['ruta_rel']).stem, identificador_canonico='ICT155-OCR-' + Path(d['ruta_rel']).stem, titulo=Path(d['ruta_rel']).stem.replace('_', ' ')[:400], clase_derechos=d['regimen'], metodo_extraccion='ocr', idioma='fr' if 'EMISOR_DEMO_FR' in d['ruta_rel'] else 'es', completitud='completa', procedencia=f'OCR con Tesseract 5.4 a {300} ppp, idiomas spa+eng+fra+rus+chi_sim. {len(campos)} campos de alto valor verificados sobre recorte a 600 ppp', alias=[v for c in campos if c['nombre'] == 'numero_certificado' for v in [c['valor']]], origen=d['ruta_rel'], preceptos=[dict(ruta=f'pag.{i}', etiqueta=f'Pagina {i}', pagina=i, texto=t.strip()) for i, t in enumerate(d['paginas'], 1) if t.strip()]))
    return out
FOTOS = [dict(carpeta='01_Conocimiento/Normas_tecnicas/NORMA_PAGO_30/Photos-1-001', obra='EN 13486:2023', identificador_canonico='EN-13486-2023')]

def cargar_fotos(rutas_ya_puestas: set[str] | None=None) -> list[dict]:
    """Public CI documentation."""
    from . import ocr_fotos
    ya = rutas_ya_puestas or set()
    out = []
    for f in FOTOS:
        if not (config.BIBLIOTECA / f['carpeta']).exists():
            continue
        preceptos, resumen = ocr_fotos.preceptos_de(f['carpeta'])
        preceptos = [p for p in preceptos if p['ruta'] not in ya]
        if not preceptos:
            continue
        out.append(dict(obra=f['obra'], identificador_canonico=f['identificador_canonico'], titulo=f['obra'], clase_derechos='licenciado', metodo_extraccion='ocr', idioma='en', completitud='parcial', procedencia=f"OCR de {resumen['fotos']} fotografias de pagina impresa. Receta medida: gris + desenfoque gaussiano 1,0, tesseract -l eng --psm 6. {resumen['descartadas']} lineas descartadas por ser moire. Tablas NO reconocidas ({', '.join(resumen['tablas_sin_ocr'])}): van a transcripcion manual", alias=[], origen=f['carpeta'], preceptos=preceptos, resumen=resumen))
    return out
FICHAS = [dict(ruta='01_Conocimiento/Normas_tecnicas/NORMA_PAGO_31.md', obra='EN 13486:2023', identificador_canonico='EN-13486-2023', titulo='EN 13486:2023, Temperature recorders and thermometers for the transport, storage and distribution of temperature sensitive goods. Periodic verification', idioma='en', completitud='parcial', procedencia='Ficha completa de transcripcion verificada. Cubre la norma entera salvo la clausula 1, con las ocho tablas transcritas a mano (1, 2, 3 con celdas combinadas desplegadas, 4, C.1, C.2, C.3 y D.1)', alias=['EN 13486:2023', 'EN 13486', 'EN-13486:2023', 'EN 13486:2023 (2023)'])]
SUPERADOS = {'01_Conocimiento/Normas_tecnicas/NORMA_PAGO_33.md': 'subconjunto de tablas, contenido en la ficha completa', 'datos/transcripciones/NORMA_PAGO_01_PARCIAL.json': 'mapa de los apartados 10 ter y 10 quater de la ficha de trabajo, seis clausulas. La ficha completa cubre esas seis y veintiocho mas, por la misma via y con la misma autoridad'}

def cargar_fichas() -> list[dict]:
    """Public CI documentation."""
    from . import ficha_norma
    out = []
    for f in FICHAS:
        if not (config.BIBLIOTECA / f['ruta']).exists():
            continue
        preceptos = ficha_norma.analizar(f['ruta'])
        if not preceptos:
            continue
        out.append(dict(obra=f['obra'], identificador_canonico=f['identificador_canonico'], titulo=f['titulo'], clase_derechos='licenciado', metodo_extraccion='transcripcion_verificada', idioma=f['idioma'], completitud=f['completitud'], procedencia=f['procedencia'], alias=f['alias'], origen=f['ruta'], preceptos=preceptos))
    return out
