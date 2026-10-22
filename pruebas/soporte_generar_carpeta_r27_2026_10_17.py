"""Public CI documentation."""
from __future__ import annotations
import copy
import csv
import hashlib
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
import pytest
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'herramientas' / 'fase2'))
from ict155 import brechas, db
import generar_carpeta as gc
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'fase2'

def _version(con, obra_id, nombre, clase_derechos, preceptos):
    doc = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas, clase_derechos, estado_ingesta) VALUES (?,?,?,?,?,?,?)', (f'{nombre}.pdf', nombre, 1, '2026-01-01', 10, clase_derechos, 'ingerido')).lastrowid
    v = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, idioma, fecha_edicion, fecha_consolidacion) VALUES (?,?,?,?,?,?)', (obra_id, doc, 'v1', 'es', '2026-01-01', '2026-01-01')).lastrowid
    for orden, (ruta, etiqueta_h, texto, pag) in enumerate(preceptos, 1):
        con.execute('INSERT INTO precepto (version_id, ruta_estructural, tipo_unidad, numero, etiqueta_humana, texto_literal, pagina_inicio, pagina_fin, orden) VALUES (?,?,?,?,?,?,?,?,?)', (v, ruta, 'articulo', ruta.rsplit('.', 1)[-1], etiqueta_h, texto, pag, pag, orden))

def _obra(con, ident, titulo, clase_derechos, preceptos):
    cur = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, jurisdiccion) VALUES (?,?,?,?)', (ident, 'norma_tecnica', titulo, 'ES'))
    _version(con, cur.lastrowid, ident, clase_derechos, preceptos)
    return cur.lastrowid
TEXTO_PUBLICO = 'Texto sintético de la norma pública, artículo 1.'
TEXTO_LICENCIADO = 'Texto sintético de la norma con licencia, artículo 1.'

@pytest.fixture(scope='module')
def con(tmp_path_factory):
    c = db.crear(tmp_path_factory.mktemp('fase2') / 'b.sqlite')
    _obra(c, 'NORMA-PUB-001', 'Norma pública sintética', 'publico', [('art.1', 'Artículo 1', TEXTO_PUBLICO, 1)])
    _obra(c, 'NORMA-LIC-001', 'Norma con licencia sintética', 'licenciado', [('art.1', 'Artículo 1', TEXTO_LICENCIADO, 1)])
    c.commit()
    yield c
    c.close()

@pytest.fixture(scope='module')
def registro():
    return brechas.leer_registro(FIXTURES / 'registro_sintetico.json')

def _hash_arbol(raiz: Path) -> dict[str, str]:
    """Public CI documentation."""
    out = {}
    for p in sorted(raiz.rglob('*')):
        if p.is_file():
            out[str(p.relative_to(raiz))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
