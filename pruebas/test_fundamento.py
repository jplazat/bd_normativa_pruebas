"""Public CI documentation."""
from __future__ import annotations
import random
import re
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import config, db, fundamento
SEMILLA = 20260805
N_MUESTRAS = 60
PALABRAS_POR_MUESTRA = 12

@pytest.fixture(scope='module')
def con():
    if not config.BD.exists():
        pytest.skip('base no disponible')
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(scope='module')
def muestras(con):
    """Public CI documentation."""
    filas = con.execute('\n        SELECT p.id, p.ruta_estructural AS ruta, p.texto_literal AS texto,\n               o.identificador_canonico AS ident\n        FROM precepto p\n        JOIN version v ON v.id = p.version_id\n        JOIN obra o    ON o.id = v.obra_id\n        WHERE length(p.texto_literal) > 400\n          AND NOT EXISTS (SELECT 1 FROM precepto h WHERE h.padre_id = p.id)\n    ').fetchall()
    rnd = random.Random(SEMILLA)
    elegidas = rnd.sample(filas, min(N_MUESTRAS, len(filas)))
    out = []
    for f in elegidas:
        pal = fundamento.normalizar(f['texto']).split()
        if len(pal) < PALABRAS_POR_MUESTRA * 2:
            continue
        i = rnd.randrange(0, len(pal) - PALABRAS_POR_MUESTRA)
        out.append((f['ident'], f['ruta'], ' '.join(pal[i:i + PALABRAS_POR_MUESTRA])))
    return out

def test_hay_muestras_suficientes(muestras):
    """Public CI documentation."""
    assert len(muestras) >= 30, f'solo {len(muestras)} muestras'

def test_una_frase_del_interior_localiza_su_propio_precepto(con, muestras):
    """Public CI documentation."""
    fallos = []
    for ident, ruta, frase in muestras:
        r = fundamento.localizar(con, frase, ident)
        if r.estado == fundamento.LOCALIZADO:
            if r.candidatos[0].ruta != ruta:
                fallos.append((ruta, r.candidatos[0].ruta, frase[:60]))
        elif r.estado == fundamento.AMBIGUO:
            if ruta not in {c.ruta for c in r.candidatos}:
                fallos.append((ruta, 'AMBIGUO sin incluirlo', frase[:60]))
        else:
            fallos.append((ruta, 'NO_LOCALIZADO', frase[:60]))
    assert not fallos, f'{len(fallos)} de {len(muestras)}: {fallos[:5]}'

def test_nunca_devuelve_una_ruta_de_otra_obra(con, muestras):
    """Public CI documentation."""
    fallos = []
    for ident, ruta, frase in muestras:
        r = fundamento.localizar(con, frase)
        if r.estado == fundamento.LOCALIZADO and r.candidatos[0].identificador != ident:
            fallos.append((ident, r.candidatos[0].identificador, frase[:60]))
    assert not fallos, f'{fallos[:5]}'

def test_el_fundamento_devuelto_es_una_ruta_resoluble(con, muestras):
    """Public CI documentation."""
    comprobados = 0
    for ident, ruta, frase in muestras:
        r = fundamento.localizar(con, frase, ident)
        if r.estado != fundamento.LOCALIZADO:
            continue
        obra, _, r_ruta = r.fundamento.partition('::')
        n = con.execute('\n            SELECT count(*) FROM precepto p\n            JOIN version v ON v.id = p.version_id\n            JOIN obra o    ON o.id = v.obra_id\n            WHERE o.identificador_canonico = ? AND p.ruta_estructural = ?', (obra, r_ruta)).fetchone()[0]
        assert n >= 1, f'{r.fundamento} no resuelve a ningun precepto'
        comprobados += 1
    assert comprobados >= 20, f'solo {comprobados} resolubles comprobados'

def test_una_obra_con_varias_versiones_deja_el_fundamento_incompleto(con):
    """Public CI documentation."""
    filas = con.execute('\n        SELECT o.identificador_canonico AS ident, count(v.id) AS n\n        FROM obra o JOIN version v ON v.obra_id = o.id\n        GROUP BY o.id HAVING count(v.id) > 1').fetchall()
    multi = {f['ident'] for f in filas}
    assert len(multi) <= 12, f'{len(multi)} obras con varias versiones: el fundamento obra::ruta empieza a ser insuficiente. {sorted(multi)[:10]}'

def test_una_frase_que_no_esta_no_se_inventa(con):
    r = fundamento.localizar(con, 'el titular remitira el informe en color verde antes del jueves')
    assert r.estado == fundamento.NO_LOCALIZADO
    assert r.fundamento is None

def test_una_frase_demasiado_corta_se_rechaza_antes_de_buscar(con):
    """Public CI documentation."""
    r = fundamento.localizar(con, 'el instrumento')
    assert r.estado == fundamento.NO_LOCALIZADO
    assert 'palabras utiles' in (r.motivo or '')

def test_una_frase_en_dos_obras_distintas_es_AMBIGUO(con):
    """Public CI documentation."""
    candidata = None
    for f in con.execute('\n        SELECT p.texto_literal AS texto FROM precepto p\n        WHERE length(p.texto_literal) BETWEEN 200 AND 2000 LIMIT 250'):
        pal = fundamento.normalizar(f['texto']).split()
        if len(pal) < 14:
            continue
        frase = ' '.join(pal[:10])
        r = fundamento.localizar(con, frase)
        if r.estado == fundamento.AMBIGUO and len({c.identificador for c in r.candidatos}) > 1:
            candidata = (frase, r)
            break
    if candidata is None:
        pytest.skip('no consta ninguna frase de 10 palabras repetida entre obras')
    frase, r = candidata
    assert r.fundamento is None, 'AMBIGUO no puede devolver fundamento'
    assert len(r.candidatos) > 1

def test_el_padre_y_el_hijo_no_son_dos_sitios(con):
    """Public CI documentation."""
    f = con.execute('\n        SELECT h.texto_literal AS texto, h.ruta_estructural AS hijo,\n               o.identificador_canonico AS ident\n        FROM precepto h\n        JOIN precepto p ON p.id = h.padre_id\n        JOIN version v ON v.id = h.version_id\n        JOIN obra o    ON o.id = v.obra_id\n        WHERE length(h.texto_literal) > 500 LIMIT 1').fetchone()
    if not f:
        pytest.skip('no consta un par padre-hijo con texto suficiente')
    pal = fundamento.normalizar(f['texto']).split()
    frase = ' '.join(pal[3:15])
    r = fundamento.localizar(con, frase, f['ident'])
    assert r.estado == fundamento.LOCALIZADO
    assert r.candidatos[0].ruta == f['hijo']

def test_un_ascendiente_se_mide_por_segmentos_y_no_por_prefijo(con):
    """Public CI documentation."""
    assert fundamento._es_ascendiente('art.5', 'art.5.1')
    assert fundamento._es_ascendiente('anexo.XI', 'anexo.XI/ap.1')
    assert not fundamento._es_ascendiente('art.5', 'art.51')
    assert not fundamento._es_ascendiente('anexo.I', 'anexo.II')

def test_el_guion_de_particion_no_rompe_la_busqueda(con, muestras):
    """Public CI documentation."""
    if not muestras:
        pytest.skip('sin muestras')
    for ident, ruta, frase in muestras:
        pal = frase.split()
        i = next((k for k, p in enumerate(pal) if len(p) >= 4), None)
        if i is None:
            continue
        mitad = len(pal[i]) // 2
        rota = ' '.join(pal[:i] + [pal[i][:mitad] + '-\n' + pal[i][mitad:]] + pal[i + 1:])
        r = fundamento.localizar(con, rota, ident)
        assert r.estado in (fundamento.LOCALIZADO, fundamento.AMBIGUO), f'la particion rompe la busqueda: {rota[:80]!r}'
        return
    pytest.skip('ninguna muestra tiene una palabra de 4 letras que partir')
