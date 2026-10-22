"""Public CI documentation."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from ict155 import config, extraccion, parsers
from ict155.extraccion import TextoPdf
RAIZ = Path(__file__).resolve().parent.parent

def test_la_directiva_esta_declarada_y_solo_ella():
    assert len(extraccion.DOCUMENTOS_EN_ORDEN_INTERNO) == 1
    assert 'Directiva_2014-31-UE' in next(iter(extraccion.DOCUMENTOS_EN_ORDEN_INTERNO))

def test_la_cabecera_unida_del_diario_oficial_es_ruido_en_los_dos_ordenes():
    for ln in ('L 96/112 Diario Oficial de la Unión Europea 29.3.2014', '29.3.2014 Diario Oficial de la Unión Europea L 96/113', 'L 153/75 Official Journal of the European Union 22.5.2014'):
        assert any((r.match(ln) for r in parsers.RUIDO)), ln
    frase = 'publicada en el Diario Oficial de la Unión Europea el 29.3.2014'
    assert not any((r.match(frase) for r in parsers.RUIDO))

def test_el_codigo_de_lengua_se_quita_solo_delante_de_la_cabecera():
    pagina = 'texto del articulo\nES\n\nL 96/112 Diario Oficial de la Unión Europea 29.3.2014\n'
    assert extraccion._sin_idioma_de_cabecera(pagina).split('\n')[1] == ''
    tabla = 'Estado\nES\nFR\n'
    assert extraccion._sin_idioma_de_cabecera(tabla) == tabla

def test_la_directiva_se_extrae_con_raw_y_el_motor_lo_dice(tmp_path, monkeypatch):
    fitz = pytest.importorskip('fitz')
    if not shutil.which(config.PDFTOTEXT):
        pytest.skip('sin pdftotext')
    rel = next(iter(extraccion.DOCUMENTOS_EN_ORDEN_INTERNO))
    destino = tmp_path / 'd.pdf'
    destino.parent.mkdir(parents=True, exist_ok=True)
    d = fitz.open()
    d.new_page().insert_text((72, 72), 'Articulo 1 Objeto.')
    d.save(destino)
    llamadas = []
    original = subprocess.run

    def espia(args, **kw):
        llamadas.append(list(args))
        return original(args, **kw)
    monkeypatch.setattr(config, 'ruta_biblioteca', lambda ruta: destino if ruta == rel else tmp_path / ruta)
    monkeypatch.setattr(config, 'relativa', lambda ruta: rel if ruta == destino else str(ruta))
    monkeypatch.setattr(extraccion.subprocess, 'run', espia)
    t = extraccion.extraer(rel)
    assert t.motor == config.MOTOR_XPDF + ' -raw'
    assert '-raw' in llamadas[0]
    assert t.ruta_relativa == rel

def test_tabla_de_correspondencias_con_la_rubrica_en_el_renglon_siguiente():
    """Public CI documentation."""
    lineas = ['Artículo 1', 'Objeto', 'La presente Directiva se aplica.', 'ANEXO VI', 'TABLA DE CORRESPONDENCIAS', 'Directiva 2009/23/CE Presente Directiva', 'Anexo VII Anexo V', 'Anexo VIII —']
    an = parsers.analizar('eurlex', TextoPdf('doue_prueba.pdf', paginas=['\n'.join(lineas)]))
    rutas = {p.ruta for p in an.preceptos}
    assert 'anexo.VI' in rutas and 'anexo.VII' not in rutas and ('anexo.VIII' not in rutas)
    assert 'Anexo VII Anexo V' in next((p for p in an.preceptos if p.ruta == 'anexo.VI')).texto

def _cita(identificador):
    r = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'ict155.cli', 'cita', identificador, '--json'], cwd=RAIZ, capture_output=True, timeout=120)
    return json.loads(r.stdout.decode('utf-8'))

@pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')
def test_en_la_base_el_articulo_6_tiene_sus_nueve_apartados_y_el_3_tres():
    """Public CI documentation."""
    if _cita('Directiva 2014/31/UE::art.6.4')['estado'] == 'PRECEPTO_INEXISTENTE':
        pytest.skip('la base aun no esta reconstruida con esta ronda')
    texto = ' '.join(_cita('Directiva 2014/31/UE::art.6.4')['texto_literal'].split())
    assert texto.startswith('4. Los fabricantes se asegurarán de que existan procedimientos')
    assert _cita('Directiva 2014/31/UE::art.6.9')['estado'] == 'ENCONTRADO'
    assert _cita('Directiva 2014/31/UE::art.3.4')['estado'] == 'PRECEPTO_INEXISTENTE'
    assert _cita('Directiva 2014/31/UE::art.1.2.g')['estado'] == 'ENCONTRADO'
