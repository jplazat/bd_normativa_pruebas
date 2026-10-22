"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import consulta, db, validador

def _base(ruta: Path, obras: list[dict]) -> Path:
    """Public CI documentation."""
    con = db.crear(ruta)
    for o in obras:
        oid = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, jurisdiccion) VALUES (?,?,?,?)', (o['ident'], o.get('tipo', 'norma'), o['titulo'], 'EU')).lastrowid
        for a in sorted(set(o.get('alias', [])) | {o['ident']}):
            con.execute('INSERT OR IGNORE INTO obra_alias (obra_id, alias, alias_norm) VALUES (?,?,?)', (oid, a, consulta.norm_alias(a)))
        for i, v in enumerate(o['versiones']):
            did = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas, clase_derechos, estado_ingesta) VALUES (?,?,?,?,?,?,?)', (f"sintetico/{o['ident']}_{i}.pdf", '0' * 64, 1, '2026-01-01T00:00:00+00:00', 3, 'publico', 'ingerido')).lastrowid
            vid = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, fecha_edicion, idioma, completitud) VALUES (?,?,?,?,?,?)', (oid, did, v['etiqueta'], v.get('fecha_edicion'), 'es', 'completa')).lastrowid
            for orden, (r, texto) in enumerate(v['preceptos'].items()):
                con.execute('INSERT INTO precepto (version_id, ruta_estructural, tipo_unidad, etiqueta_humana, texto_literal, metodo_extraccion, pagina_inicio, pagina_fin, orden) VALUES (?,?,?,?,?,?,?,?,?)', (vid, r, r.split('.')[0], r, texto, 'capa_texto', 1, 1, orden))
    con.commit()
    con.close()
    return ruta

@pytest.fixture()
def con_en13486(tmp_path):
    """Public CI documentation."""
    ruta = _base(tmp_path / 'b.sqlite', [{'ident': 'EN 13486:2023', 'titulo': 'EN 13486', 'alias': ['EN 13486:2023', 'EN 13486'], 'versiones': [{'etiqueta': '2023', 'fecha_edicion': '2023', 'preceptos': {'ap.6.7.2.10': 'Requisitos de la clausula 6.7.2.10.', 'tabla.4': 'Tabla 4. Valores de la prueba.', 'anexo.A': 'Anexo A. Procedimiento de ensayo.', 'anexo.B': 'Anexo B. Informe.'}}]}])
    con = db.conectar(ruta, solo_lectura=True)
    yield con
    con.close()
FRASE_L735 = '# Informe\n\nLos registros cumplen la Tabla 4, cláusula 6.7.2.10, Anexo A de la EN 13486:2023.\n'
PAREJAS = [('Reglamento (CE) n.º 37/2005', 'Reglamento (CE) 37/2005'), ('EN 13486:2023', 'EN-13486-2023'), ('ILAC-G8:2019', 'ILAC G8:2019'), ('UNE-EN 12830:2019', 'UNE EN 12830:2019')]
GUION_ALIAS = '\nimport json, sys, tempfile\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\nfrom ict155 import catalogo, db, extraccion, ingesta\nfrom ict155.extraccion import TextoPdf\nalias = [a for pareja in json.loads(sys.argv[2]) for a in pareja]\ncon = db.crear(Path(tempfile.mkdtemp()) / "alias.sqlite")\n# 1. Obra minima de un documento sin trocear. Va primero: si sus alias ya\n# fueran de otra obra, se le colgaria una version y no insertaria ninguno.\ncatalogo.ALIAS["sin_trocear_alias.pdf"] = alias\ndoc = con.execute(\n    "INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas,"\n    " clase_derechos, estado_ingesta) VALUES (?,?,?,?,?,?,?)",\n    ("sintetico/sin_trocear_alias.pdf", "0" * 64, 1, "2026-01-01T00:00:00+00:00",\n     1, "licenciado", "derechos_restringidos")).lastrowid\ningesta._registrar_obra_minima(con, "sintetico/sin_trocear_alias.pdf", doc)\n# 2. Documento troceado (BOE sintetico), con los alias declarados en el catalogo.\nboe = "sintetico/BOE_sintetico_alias.pdf"\ncatalogo.ALIAS["BOE_sintetico_alias.pdf"] = alias\ncatalogo.familia = lambda r: "boe"\ncatalogo.en_nucleo = lambda r: True\nextraccion.extraer = lambda r, timeout=None: TextoPdf(r, paginas=[\n    "Referencia: BOE-A-2099-9\\nOrden de prueba de alias\\nTEXTO CONSOLIDADO\\n"\n    "Artículo 1. Objeto.\\nTexto del articulo uno.\\n"])\ningesta.ingerir_documento(con, boe)\n# 3. Transcripcion verificada.\ningesta.ingerir_transcripcion(con, dict(\n    identificador_canonico="TRANSCRIPCION-ALIAS", obra="Transcripcion de alias",\n    titulo="Transcripcion de alias", alias=alias, origen="sintetico/transcripcion.md",\n    metodo_extraccion="transcripcion_verificada", procedencia="prueba",\n    clase_derechos="licenciado", preceptos=[dict(ruta="ap.1", etiqueta="1",\n    texto="Texto.", pagina=1)]))\ncon.commit()\nprint(json.dumps([tuple(f) for f in con.execute(\n    "SELECT o.identificador_canonico, a.alias, a.alias_norm FROM obra_alias a"\n    " JOIN obra o ON o.id = a.obra_id ORDER BY 1, 3, 2")]))\n'

def _tabla_de_alias(semilla: int) -> list:
    import json
    import os
    import subprocess
    raiz = str(Path(__file__).resolve().parent.parent)
    salida = subprocess.run([sys.executable, '-c', GUION_ALIAS, raiz, json.dumps(PAREJAS)], capture_output=True, text=True, check=True, env={**os.environ, 'PYTHONHASHSEED': str(semilla)})
    return json.loads(salida.stdout)
