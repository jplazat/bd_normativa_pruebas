"""Public CI documentation."""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import config, extraccion
UN_PDF = '01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_Ley32-2014_Metrologia_consolidada.pdf'

@pytest.fixture(autouse=True)
def sin_biblioteca():
    if not (config.BIBLIOTECA / UN_PDF).exists():
        pytest.skip('biblioteca no disponible')

def test_el_agotamiento_de_tiempo_es_ruidoso():
    """Public CI documentation."""
    with pytest.raises(extraccion.IngestaNoReproducible) as e:
        extraccion.extraer(UN_PDF, timeout=0.001)
    assert 'reproducib' in str(e.value).lower() or 'carga' in str(e.value).lower()

def test_el_error_de_tiempo_no_se_confunde_con_un_pdf_ilegible():
    """Public CI documentation."""
    assert not issubclass(extraccion.IngestaNoReproducible, extraccion.ExtraccionError)

def test_el_limite_es_configurable_sin_tocar_codigo():
    """Public CI documentation."""
    previo = os.environ.get('ICT155_TIMEOUT')
    os.environ['ICT155_TIMEOUT'] = '0.001'
    try:
        with pytest.raises(extraccion.IngestaNoReproducible):
            extraccion.extraer(UN_PDF)
    finally:
        if previo is None:
            os.environ.pop('ICT155_TIMEOUT', None)
        else:
            os.environ['ICT155_TIMEOUT'] = previo

def test_la_huella_incluye_las_celdas():
    """Public CI documentation."""
    import shutil
    import sqlite3
    import tempfile
    from ict155 import db
    if not config.BD.exists():
        pytest.skip('no hay base construida')
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / 'c.sqlite'
        shutil.copy(config.BD, copia)
        con = sqlite3.connect(copia)
        con.row_factory = sqlite3.Row
        try:
            if con.execute('SELECT count(*) FROM celda').fetchone()[0] == 0:
                pytest.skip('no hay celdas todavia')
            antes = db.huella_contenido(con)
            con.execute("UPDATE celda SET valor = valor || 'X' WHERE rowid = (SELECT min(rowid) FROM celda)")
            assert db.huella_contenido(con) != antes, 'cambiar una celda no mueve la huella: las tablas quedan fuera '
        finally:
            con.close()
