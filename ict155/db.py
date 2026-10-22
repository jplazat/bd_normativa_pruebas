"""Public CI documentation."""
from __future__ import annotations
import hashlib
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from . import config

def conectar(ruta: Path | None=None, solo_lectura: bool=False) -> sqlite3.Connection:
    ruta = ruta or config.BD
    if solo_lectura:
        if not ruta.exists():
            raise sqlite3.OperationalError(f'no existe la base {ruta}: construyela con `python -m ict155.cli reconstruir`')
        con = sqlite3.connect(f'file:{ruta}?mode=ro', uri=True)
    else:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def crear(ruta: Path | None=None) -> sqlite3.Connection:
    """Public CI documentation."""
    ruta = ruta or config.BD
    ruta.parent.mkdir(parents=True, exist_ok=True)
    for sufijo in ('', '-wal', '-shm'):
        p = Path(str(ruta) + sufijo)
        if p.exists():
            p.unlink()
    con = conectar(ruta)
    con.executescript((Path(__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
    con.commit()
    return con

def git_commit() -> str | None:
    try:
        r = subprocess.run(['git', '-C', str(config.REPO), 'rev-parse', '--short', 'HEAD'], capture_output=True, timeout=10)
        return r.stdout.decode().strip() or None
    except Exception:
        return None

def huella_contenido(con: sqlite3.Connection) -> str:
    """Public CI documentation."""
    h = hashlib.sha256()
    filas = con.execute("\n        SELECT o.identificador_canonico, v.etiqueta, v.idioma, p.ruta_estructural,\n               p.etiqueta_humana, coalesce(p.titulo,''), p.texto_literal,\n               p.pagina_inicio, p.pagina_fin\n        FROM precepto p\n        JOIN version v ON v.id = p.version_id\n        JOIN obra    o ON o.id = v.obra_id\n        ORDER BY o.identificador_canonico, v.etiqueta, v.idioma, p.ruta_estructural\n    ")
    for f in filas:
        h.update(('\x1f'.join((str(x) for x in tuple(f))) + '\x1e').encode('utf-8'))
    celdas = con.execute('\n        SELECT o.identificador_canonico, v.etiqueta, p.ruta_estructural,\n               c.fila, c.columna, c.valor\n        FROM celda c\n        JOIN precepto p ON p.id = c.precepto_id\n        JOIN version  v ON v.id = p.version_id\n        JOIN obra     o ON o.id = v.obra_id\n        ORDER BY o.identificador_canonico, v.etiqueta, p.ruta_estructural,\n                 c.fila, c.columna\n    ')
    for f in celdas:
        h.update(('\x1f'.join((str(x) for x in tuple(f))) + '\x1d').encode('utf-8'))
    try:
        tablas_pdf = con.execute('\n            SELECT d.ruta_relativa, t.orden, t.pagina_inicio, t.pagina_fin,\n                   t.n_filas, t.n_columnas, c.fila, c.columna, c.valor, c.pagina\n            FROM celda_pdf c\n            JOIN tabla_pdf t ON t.id = c.tabla_id\n            JOIN documento d ON d.id = t.documento_id\n            ORDER BY d.ruta_relativa, t.orden, c.fila, c.columna\n        ').fetchall()
    except sqlite3.OperationalError:
        tablas_pdf = []
    for f in tablas_pdf:
        h.update(('\x1f'.join((str(x) for x in tuple(f))) + '\x1c').encode('utf-8'))
    return h.hexdigest()

def registrar_ingesta(con: sqlite3.Connection) -> dict:
    d = {'ejecutada_en': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'git_commit': git_commit(), 'n_documentos': con.execute('SELECT count(*) FROM documento').fetchone()[0], 'n_versiones': con.execute('SELECT count(*) FROM version').fetchone()[0], 'n_preceptos': con.execute('SELECT count(*) FROM precepto').fetchone()[0], 'huella_contenido': huella_contenido(con)}
    con.execute('INSERT INTO ingesta\n        (ejecutada_en, git_commit, n_documentos, n_versiones, n_preceptos, huella_contenido)\n        VALUES (:ejecutada_en,:git_commit,:n_documentos,:n_versiones,:n_preceptos,:huella_contenido)', d)
    con.commit()
    return d
