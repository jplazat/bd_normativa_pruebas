"""Public CI documentation."""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
WT = Path(__file__).resolve().parents[1]
if str(WT) not in sys.path:
    sys.path.insert(0, str(WT))
from ict155 import consulta, parsers, cli
from ict155.extraccion import TextoPdf
from pruebas.soporte_alta_top30_r28_2026_10_19 import CITAS, NORMAS, ruta
from pruebas import estructura_completa_top30 as ec
ROOT = WT.parents[1]
BASE = ROOT / 'lad_top30/ict155/bd/conocimiento.sqlite'
TEXTOS = ROOT / 'tmp/top30_texto_motor'
ORDINALES = (('CELEX-32017R0745', 'art.123.3.e', 'e bis'), ('CELEX-32017R0745', 'art.123.3.e', 'e ter'), ('CELEX-32017R0745', 'art.123.3.e', 'e quater'), ('CELEX-32017R0745', 'anexo.I/capitulo.III', 'a bis'), ('CELEX-32017R0745', 'anexo.I/capitulo.III', 'a ter'), ('CELEX-32017R0746', 'art.113.3.f', 'f bis'), ('CELEX-32017R0746', 'art.113.3.f', 'f ter'), ('CELEX-32017R0746', 'art.113.3.f', 'f quater'), ('CELEX-32017R0746', 'art.113.3.f', 'f quinquies'), ('CELEX-32017R0746', 'anexo.I/capitulo.III', 'a bis'), ('CELEX-32017R0746', 'anexo.I/capitulo.III', 'a ter'), ('CELEX-32017R0746', 'anexo.I/capitulo.III', 'a quater'), ('CELEX-32017R0746', 'anexo.I/capitulo.III', 'a quinquies'), ('CELEX-32017R0746', 'anexo.XIII', 'a bis'), ('CELEX-32017R0746', 'anexo.XIII', 'a ter'))
H1 = {'a': 'los artículos 35 a 50', 'b': 'los artículos 101 y 103', 'c': 'el artículo 102', 'd': 'sin perjuicio de las obligaciones de la Comisión'}

def consulta_ordinal(obra, contenedor, rotulo):
    puntos = {('CELEX-32017R0745', 'anexo.I/capitulo.III'): ('anexo.I', '23.4'), ('CELEX-32017R0746', 'anexo.I/capitulo.III'): ('anexo.I', '20.4.1'), ('CELEX-32017R0746', 'anexo.XIII'): ('anexo.XIII', '2.3.2')}
    if (obra, contenedor) in puntos:
        anexo, punto = puntos[obra, contenedor]
        return obra + '::' + anexo + '/ap.' + punto + '.' + rotulo
    padre = contenedor.rsplit('.', 1)[0] if re.search('\\.[a-zñ]$', contenedor) else contenedor
    return obra + '::' + padre + '.' + rotulo

def h1_correspondencia(con):
    """Public CI documentation."""
    errores = []
    for letra, comienzo in H1.items():
        ident = 'CELEX-32017R0745::art.123.3.' + letra
        r = consulta.resolver(con, ident)
        text = r.texto_literal or ''
        if r.estado != consulta.ENCONTRADO or not text.startswith(letra + ') ' + comienzo):
            errores.append(ident + ': falta su cuerpo propio')
        if 'No obstante lo dispuesto en el apartado 2:' in text or any((s in text for l, s in H1.items() if l != letra)):
            errores.append(ident + ': contiene introducción o cuerpo ajeno')
    return errores

def simular(con, textos):
    memoria = sqlite3.connect(':memory:')
    memoria.row_factory = sqlite3.Row
    con.backup(memoria)
    resultados = []
    grupos = []
    for obra, nombre, _ in NORMAS:
        fp = textos / (nombre.removesuffix('.pdf') + '.motor.txt')
        raw = fp.read_text(encoding='utf-8')
        partes = re.split('^===== PÁGINA \\d+ =====[^\\S\\n]*\\n', raw, flags=re.M)
        if partes[0].strip():
            raise ValueError('dump sin delimitadores: ' + str(fp))
        pdf = TextoPdf(ruta_relativa=ruta(nombre), paginas=partes[1:])
        familia = 'boe' if obra.startswith('BOE') else 'eurlex'
        ps = parsers.analizar(familia, pdf).preceptos
        ver = memoria.execute('SELECT v.id FROM version v JOIN obra o ON o.id=v.obra_id WHERE o.identificador_canonico=?', (obra,)).fetchall()
        assert len(ver) == 1, obra
        vid = ver[0][0]
        memoria.execute('DELETE FROM precepto WHERE version_id=?', (vid,))
        ids = {}
        for n, p in enumerate(ps):
            ids[p.ruta] = memoria.execute('INSERT INTO precepto (version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,titulo,texto_literal,pagina_inicio,pagina_fin,orden,marca_consolidacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (vid, ids.get(p.padre), p.ruta, p.tipo, p.numero, p.etiqueta, p.titulo, p.texto, p.pagina_inicio, p.pagina_fin, n, p.marca)).lastrowid
        filas = [dict(ruta=p.ruta, padre=p.padre, tipo=p.tipo, texto=p.texto) for p in ps]
        r = ec.comprobar_norma(raw, filas, familia, criterio='calibrado', identificador=obra)
        resultados.append(dict(obra=obra, preceptos=len(ps), correcta=r['correcta'], faltantes=[h['ruta'] for h in r['faltantes']]))
        for pag, text in enumerate(pdf.paginas, 1):
            for ln in text.splitlines():
                s = re.sub('[►▼◄]\\s*[A-Z]\\d*\\b', '', ln).replace('◄', '').strip()
                if re.fullmatch('\\d{1,3}\\.\\s*(?:[a-zñ]\\)\\s*){2,}', s):
                    grupos.append(dict(obra=obra, pagina=pag, rotulos=s))
    memoria.commit()
    return (memoria, resultados, grupos)

def comprobar(con):
    consultas = []
    errores = []
    for obra, path, ancla in CITAS:
        ident = obra + '::' + path
        r = consulta.resolver(con, ident)
        ok = r.estado == consulta.ENCONTRADO and ancla.casefold() in (r.texto_literal or '').casefold()
        avisos = r.dict().get('calidad_textual', [])
        esperado = 'ENCONTRADO; contiene ' + repr(ancla)
        if (obra, path) in {('CELEX-31976L0211', 'art.1'), ('CELEX-31976L0211', 'anexo.I'), ('BOE-A-1989-5084', 'anexo.sn')}:
            ok = ok and bool(avisos)
            esperado += '; AVISO DE CALIDAD TEXTUAL con página/testigo'
        consultas.append(dict(consulta=ident, esperado=esperado, correcta=ok, estado=r.estado, calidad_textual=avisos))
        if not ok:
            errores.append(ident)
    errores.extend(h1_correspondencia(con))
    for letra, ancla in H1.items():
        ident = 'CELEX-32017R0745::art.123.3.' + letra
        r = consulta.resolver(con, ident)
        consultas.append(dict(consulta=ident, esperado='ENCONTRADO; empieza ' + repr(letra + ') ' + ancla) + '; sin introducción ni otros cuerpos', correcta=not any((e.startswith(ident + ':') for e in errores)), estado=r.estado))
    ident = 'CELEX-32017R0745::art.123.3'
    r = consulta.resolver(con, ident)
    intro = r.estado == consulta.ENCONTRADO and (r.texto_literal or '').startswith('3. No obstante lo dispuesto en el apartado 2:')
    consultas.append(dict(consulta=ident, esperado='ENCONTRADO; empieza por la introducción «3. No obstante lo dispuesto en el apartado 2:»', correcta=intro, estado=r.estado))
    if not intro:
        errores.append(ident)
    for obra, contenedor, rotulo in ORDINALES:
        ident = consulta_ordinal(obra, contenedor, rotulo)
        r = consulta.resolver(con, ident)
        ok = r.estado == consulta.CONTENIDO_EN_ANCESTRO and r.ambito_localizado == contenedor and (r.texto_literal is None) and ('LOCALIZADO EN SU CONTENEDOR ' + contenedor in (r.detalle or ''))
        consultas.append(dict(consulta=ident, esperado='CONTENIDO_EN_ANCESTRO; LOCALIZADO EN SU CONTENEDOR ' + contenedor + '; sin texto propio', correcta=ok, estado=r.estado, contenedor=r.ambito_localizado))
        if not ok:
            errores.append(ident)
    ident = 'BOE-A-2007-16478::art.9.10'
    r = consulta.resolver(con, ident)
    ts = cli._tablas_del_resultado(con, r)
    completa = any(([f[0] for f in t['filas'][3:]] == ['1', '2', '3', '4', '5'] and t['filas_sin_validar'] == 5 for t in ts))
    aviso = any((a['no_certificado'] == 'filas_de_tabla' and 16 in a['paginas_pdf'] for a in r.dict().get('calidad_textual', [])))
    consultas.append(dict(consulta=ident, esperado='8 filas, 5 sin validar; o aviso de tabla incompleta, página 16 si la comparación de verdad impide el arreglo', correcta=completa or aviso, tabla_completa=completa, aviso=aviso))
    if not (completa or aviso):
        errores.append(ident)
    return dict(correcta=not errores, errores=errores, consultas=consultas)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=BASE)
    p.add_argument('--textos', type=Path, default=TEXTOS)
    p.add_argument('--simular-parser', action='store_true')
    p.add_argument('--salida', type=Path)
    a = p.parse_args()
    if not a.base.is_file():
        print('PENDIENTE: falta la base de pruebas', a.base)
        return 2
    con = sqlite3.connect(a.base.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    assert con.execute('PRAGMA query_only').fetchone()[0] == 1
    corpus = []
    grupos = []
    trabajo = con
    try:
        if a.simular_parser:
            trabajo, corpus, grupos = simular(con, a.textos)
        r = comprobar(trabajo)
        r.update(simulacion_en_memoria=a.simular_parser, corpus=corpus, grupos_tras_numero=grupos)
        if corpus and (not all((x['correcta'] for x in corpus))):
            r['correcta'] = False
        if a.salida:
            a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('ING4:', 'CORRECTO' if r['correcta'] else 'NO CORRECTO', sum((x['correcta'] for x in r['consultas'])), '/', len(r['consultas']), 'consultas; corpus', sum((x['correcta'] for x in corpus)), '/', len(corpus))
        for e in r['errores']:
            print('PENDIENTE:', e)
        return 0 if r['correcta'] else 1
    finally:
        if trabajo is not con:
            trabajo.close()
        con.close()
if __name__ == '__main__':
    raise SystemExit(main())
