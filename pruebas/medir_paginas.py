"""Public CI documentation."""
from __future__ import annotations
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import db, extraccion
DOCUMENTOS = [('RD 244/2016', '%RD244-2016%'), ('Orden ICT/155/2020', '%Orden_ICT155-2020%'), ('Ley 32/2014', '%Ley32-2014%'), ('Directiva 2014/53/UE', '%Directiva_2014-53-UE%'), ('Guía CEM C-01', '%GuiaC01_evaluacion%')]
LARGO = 60

def paginas_reales(paginas: list[str], texto: str) -> list[int]:
    """Public CI documentation."""
    frag = ' '.join(texto.split())[:LARGO].strip()
    if len(frag) < 20:
        return []
    return [i for i, p in enumerate(paginas, 1) if frag in ' '.join(p.split())]

def pagina_decidible(paginas: list[str], texto: str) -> int | None:
    """Public CI documentation."""
    r = paginas_reales(paginas, texto)
    return r[0] if len(r) == 1 else None

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    con = db.conectar(solo_lectura=True)
    print('=== 1. ALCANCE ===')
    tot = con.execute('SELECT count(*) FROM precepto').fetchone()[0]
    conp = con.execute('SELECT count(*) FROM precepto WHERE pagina_inicio IS NOT NULL').fetchone()[0]
    multi = con.execute('SELECT count(*) FROM precepto WHERE pagina_fin > pagina_inicio').fetchone()[0]
    print(f'   preceptos: {tot}, con pagina: {conp} ({conp / tot * 100:.0f} %)')
    print(f'   con pagina_fin > pagina_inicio (intervalo declarado): {multi}')
    por_tipo = defaultdict(lambda: Counter())
    direcciones = Counter()
    abarcan = Counter()
    ejemplos = []
    for nombre, patron in DOCUMENTOS:
        fila = con.execute("SELECT id, ruta_relativa FROM documento WHERE ruta_relativa LIKE ? AND estado_ingesta='ingerido' LIMIT 1", (patron,)).fetchone()
        if not fila:
            print(f'   [FALTA] {nombre}')
            continue
        paginas = extraccion.extraer(fila[1]).paginas
        filas = con.execute('\n            SELECT p.ruta_estructural, p.tipo_unidad, p.pagina_inicio,\n                   p.pagina_fin, p.texto_literal\n            FROM precepto p JOIN version v ON v.id = p.version_id\n            WHERE v.documento_id = ? ORDER BY p.orden', (fila[0],)).fetchall()
        for ruta, tipo, pini, pfin, texto in filas:
            reales = paginas_reales(paginas, texto)
            if not reales:
                por_tipo[tipo]['no_localizable'] += 1
                continue
            real = reales[0]
            if real == pini:
                por_tipo[tipo]['ok'] += 1
            else:
                por_tipo[tipo]['mal'] += 1
                d = real - pini
                direcciones['por debajo (la base adelanta)' if d > 0 else 'por encima (la base atrasa)'] += 1
                if len(ejemplos) < 10:
                    ejemplos.append((nombre, ruta, pini, real))
            fin = ' '.join(texto.split())[-LARGO:]
            pf = [i for i, p in enumerate(paginas, 1) if fin and fin in ' '.join(p.split())]
            if pf and pf[-1] != real:
                abarcan[tipo] += 1
    print('\n=== 2. EXACTITUD POR TIPO DE PRECEPTO ===')
    print(f"   {'tipo':<16}{'ok':>7}{'mal':>7}{'% mal':>8}{'no loc.':>9}")
    for tipo in sorted(por_tipo, key=lambda t: -por_tipo[t]['mal']):
        c = por_tipo[tipo]
        n = c['ok'] + c['mal']
        pct = f"{c['mal'] / n * 100:.0f} %" if n else '-'
        print(f"   {tipo:<16}{c['ok']:>7}{c['mal']:>7}{pct:>8}{c['no_localizable']:>9}")
    print('\n=== 4. DIRECCION DEL ERROR ===')
    for k, v in direcciones.most_common():
        print(f'   {v:5d}  {k}')
    if len(direcciones) > 1:
        print('   -> va en LOS DOS SENTIDOS: no hay correccion aritmetica posible')
    print('\n=== 5. PRECEPTOS QUE ABARCAN MAS DE UNA PAGINA ===')
    if abarcan:
        for k, v in abarcan.most_common():
            print(f'   {v:5d}  {k}')
        print("   -> 'su pagina' es una simplificacion: el campo deberia ser intervalo")
    else:
        print('   ninguno detectado en la muestra')
    print('\n=== ejemplos ===')
    for nombre, ruta, pini, real in ejemplos:
        print(f'   {nombre:<22}{ruta:<26} base p{pini}, esta en p{real}')
if __name__ == '__main__':
    main()
