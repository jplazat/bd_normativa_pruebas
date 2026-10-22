"""Public CI documentation."""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import config, consulta, db, extraccion
from pruebas.medir_paginas import DOCUMENTOS, LARGO, pagina_decidible
CONOCIDOS = {'RD 244/2016 anexo.I/art.2.4'}
MAXIMO_FALLOS = 0

@pytest.fixture(scope='module')
def con():
    if not config.BD.exists():
        pytest.skip('base no disponible')
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

def test_la_pagina_declarada_contiene_el_texto(con):
    """Public CI documentation."""
    fallos, decidibles, indecidibles = ([], 0, 0)
    for nombre, patron in DOCUMENTOS:
        f = con.execute("SELECT id, ruta_relativa FROM documento WHERE ruta_relativa LIKE ? AND estado_ingesta='ingerido' LIMIT 1", (patron,)).fetchone()
        if not f:
            continue
        paginas = extraccion.extraer(f[1]).paginas
        filas = con.execute('\n                SELECT p.ruta_estructural, p.pagina_inicio, p.pagina_fin,\n                       p.texto_literal\n                FROM precepto p JOIN version v ON v.id = p.version_id\n                WHERE v.documento_id = ?', (f[0],)).fetchall()
        arranques = Counter((' '.join(t.split())[:LARGO].strip() for _, _, _, t in filas))
        for ruta, pini, pfin, texto in filas:
            real = pagina_decidible(paginas, texto) if arranques[' '.join(texto.split())[:LARGO].strip()] == 1 else None
            if real is None:
                indecidibles += 1
                continue
            decidibles += 1
            if not pini <= real <= pfin and f'{nombre} {ruta}' not in CONOCIDOS:
                fallos.append(f'  {nombre} {ruta}: declara [{pini}-{pfin}], esta en {real}')
    assert decidibles > 1000, f'solo {decidibles} decidibles: la puerta no mide'
    assert len(fallos) <= MAXIMO_FALLOS, f'{len(fallos)} de {decidibles} preceptos declaran una pagina que no contiene su texto ({indecidibles} indecidibles):\n' + '\n'.join(fallos[:12])

def test_la_ruta_empieza_donde_dice_su_ultimo_nivel(con):
    """Public CI documentation."""
    fallos = 0
    ejemplos = []
    filas = con.execute("\n        SELECT p.ruta_estructural, substr(p.texto_literal, 1, 12)\n        FROM precepto p\n        WHERE p.tipo_unidad = 'letra' LIMIT 400").fetchall()
    for ruta, arranque in filas:
        letra = ruta.rsplit('.', 1)[-1]
        if not arranque.strip().lower().startswith((f'{letra})', f'{letra} )', f'({letra})')):
            fallos += 1
            if len(ejemplos) < 6:
                ejemplos.append(f'  {ruta}: empieza por {arranque.strip()[:14]!r}')
    if filas:
        assert fallos == 0, f'{fallos} de {len(filas)} rutas de letra no empiezan por su letra:\n' + '\n'.join(ejemplos)

def test_el_fundamento_del_caracter_juridico_se_puede_leer(con):
    """Public CI documentation."""
    filas = con.execute("SELECT identificador_canonico, caracter_juridico_fundamento FROM obra WHERE caracter_juridico <> 'indeterminado'").fetchall()
    fallos = []
    for ident, fundamento in filas:
        r = consulta.resolver(con, fundamento, modo=consulta.MODO_LOCALIZAR)
        if r.estado not in (consulta.ENCONTRADO, consulta.LOCALIZADO_SIN_TEXTO):
            fallos.append(f'  {ident}: {fundamento!r} -> {r.estado}')
    assert not fallos, 'hay fundamentos que no se pueden recorrer:\n' + '\n'.join(fallos)

def test_el_fundamento_del_emisor_dice_donde(con):
    """Public CI documentation."""
    filas = con.execute("SELECT identificador_canonico, emisor, emisor_fundamento FROM obra WHERE emisor_metodo = 'declarado_en_documento'").fetchall()
    for ident, emisor, fundamento in filas:
        assert fundamento and fundamento.strip(), ident
        assert any((c.isdigit() for c in fundamento)), f'{ident}: {fundamento!r} no dice ninguna pagina'

def test_los_indecidibles_se_declaran_y_no_se_dan_por_buenos(con):
    """Public CI documentation."""
    f = con.execute("SELECT id, ruta_relativa FROM documento WHERE ruta_relativa LIKE ? AND estado_ingesta='ingerido' LIMIT 1", ('%RD244-2016%',)).fetchone()
    if not f:
        pytest.skip('RD 244/2016 no cargado')
    paginas = extraccion.extraer(f[1]).paginas
    textos = [r[0] for r in con.execute("SELECT p.texto_literal FROM precepto p JOIN version v ON v.id=p.version_id WHERE v.documento_id=? AND p.tipo_unidad='apendice'", (f[0],))]
    indecidibles = sum((1 for t in textos if pagina_decidible(paginas, t) is None))
    assert indecidibles > 0, 'los apendices empiezan todos igual: si ninguno sale indecidible, el metodo esta contando como acierto lo que no puede decidir'
