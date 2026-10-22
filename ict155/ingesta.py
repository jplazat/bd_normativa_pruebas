"""Public CI documentation."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from . import caracter, catalogo, config, db, emisores, extraccion, fundamento, mobiliario, paginas_subprecepto, transcripciones, validador
from .consulta import norm_alias
from .parsers import ANALIZADORES
CARPETAS_REGISTRO = ('01_Conocimiento/Fuentes_primarias/', '01_Conocimiento/Normas_tecnicas/', '01_Conocimiento/05_Reservado/', '01_Conocimiento/Investigacion/', '01_Conocimiento/Mercado_y_competencia/', '01_Conocimiento/Referencia_ciberseguridad_no_vinculante/')
OBSERVADOR_DESCARTE = None

def documentos_biblioteca() -> list[str]:
    raiz = config.BIBLIOTECA
    out = []
    for carpeta in CARPETAS_REGISTRO:
        base = raiz / carpeta
        if not base.exists():
            continue
        for p in base.rglob('*'):
            if p.suffix.lower() == '.pdf' and p.is_file() and (not catalogo.aplazado(config.relativa(p))):
                out.append(config.relativa(p))
    return sorted(set(out))

def _insert_documento(con, texto: extraccion.TextoPdf | None, ruta_rel: str, estado: str, motivo: str | None=None) -> int:
    clase = catalogo.clase_derechos(ruta_rel)
    if texto is None:
        p = config.ruta_biblioteca(ruta_rel)
        st = p.stat()
        cur = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas,\n               hash_texto, motor_extraccion, clase_derechos, estado_ingesta, motivo_estado)\n               VALUES (?,?,?,?,?,?,?,?,?,?)', (ruta_rel, extraccion.sha256_fichero(p), st.st_size, datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds'), None, None, None, clase, estado, motivo))
        return cur.lastrowid
    cur = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas,\n           hash_texto, motor_extraccion, clase_derechos, estado_ingesta, motivo_estado, extraido_en)\n           VALUES (?,?,?,?,?,?,?,?,?,?,?)', (ruta_rel, texto.sha256, texto.bytes, texto.mtime_utc, texto.n_paginas, texto.hash_texto, texto.motor, clase, estado, motivo, datetime.now(timezone.utc).isoformat(timespec='seconds')))
    return cur.lastrowid

def _emisor(ruta_rel: str) -> tuple[str | None, str]:
    """Public CI documentation."""
    e = catalogo.emisor_de(ruta_rel)
    return (e, 'inferido_de_nombre_fichero') if e else (None, 'sin_emisor')

def _identificador_fallback(ruta_rel: str) -> str:
    return 'ICT155-DOC-' + Path(ruta_rel).stem

def _insertar_alias(con, obra_id: int, alias) -> None:
    """Public CI documentation."""
    for a in dict.fromkeys(alias):
        con.execute('INSERT OR IGNORE INTO obra_alias (obra_id, alias, alias_norm) VALUES (?,?,?)', (obra_id, a, norm_alias(a)))

def _registrar_obra_minima(con, ruta_rel: str, doc_id: int) -> None:
    """Public CI documentation."""
    ident = _identificador_fallback(ruta_rel)
    fila = con.execute('SELECT id FROM obra WHERE identificador_canonico=?', (ident,)).fetchone()
    if fila:
        return
    for a in catalogo.alias_de(ruta_rel):
        f = con.execute('SELECT obra_id FROM obra_alias WHERE alias_norm=?', (norm_alias(a),)).fetchone()
        if f:
            con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, es_consolidada,\n                   fecha_consolidacion, fecha_edicion, idioma, completitud,\n                   cabecera_origen) VALUES (?,?,?,?,?,?,?,?,?)', (f['obra_id'], doc_id, f'manifestacion: {catalogo.completitud(ruta_rel)}', 0, None, catalogo.edicion_de(ruta_rel), '?', catalogo.completitud(ruta_rel), None))
            return
    obra_id = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, emisor, emisor_metodo, jurisdiccion) VALUES (?,?,?,?,?,?)', (ident, 'no_troceado', Path(ruta_rel).stem[:400], *_emisor(ruta_rel), 'OTRA')).lastrowid
    _insertar_alias(con, obra_id, [*catalogo.alias_de(ruta_rel), ident])
    con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, es_consolidada,\n           fecha_consolidacion, fecha_edicion, idioma, completitud, cabecera_origen)\n           VALUES (?,?,?,?,?,?,?,?,?)', (obra_id, doc_id, 'no troceada', 0, None, catalogo.edicion_de(ruta_rel), '?', catalogo.completitud(ruta_rel), None))

def ingerir_documento(con: sqlite3.Connection, ruta_rel: str, verbose=False) -> dict:
    if catalogo.aplazado(ruta_rel):
        return {'ruta': ruta_rel, 'estado': 'aplazado_v2a', 'preceptos': 0}
    fam = catalogo.familia(ruta_rel)
    if fam is None or not catalogo.en_nucleo(ruta_rel):
        clase = catalogo.clase_derechos(ruta_rel)
        estado = 'derechos_restringidos' if clase == 'licenciado' else 'registrado_fuera_de_alcance'
        motivo = 'norma tecnica de pago aun sin trocear' if clase == 'licenciado' else 'fuera del alcance de la fase 1'
        doc_id = _insert_documento(con, None, ruta_rel, estado, motivo)
        _registrar_obra_minima(con, ruta_rel, doc_id)
        return {'ruta': ruta_rel, 'estado': estado, 'preceptos': 0}
    limpio = catalogo.TEXTO_LIMPIO_POR_DOCUMENTO.get(ruta_rel)
    if limpio:
        meta0 = catalogo.metadatos(ruta_rel)
        texto = extraccion.extraer_texto_boe(ruta_rel, limpio, meta0['identificador'], meta0['titulo'])
    else:
        texto = extraccion.extraer(ruta_rel)
    metodo = 'capa_texto' if limpio else catalogo.metodo_extraccion(ruta_rel)
    an = ANALIZADORES[fam](texto)
    if not limpio and texto.paginas:
        paginas_subprecepto.afinar(an.preceptos, texto)
    if limpio:
        for p in an.preceptos:
            p.pagina_inicio, p.pagina_fin = (1, texto.n_paginas)
    aviso = f'{texto.caracteres_perdidos} caracteres fuera del BMP sin pareja (CESU-8 roto en origen)' if texto.caracteres_perdidos else None
    doc_id = _insert_documento(con, texto, ruta_rel, 'ingerido', aviso)
    if fam == 'guia' and (not limpio):
        mobiliario.guardar(con, doc_id, texto)
    if fam in ('guia', 'boe', 'eurlex') and (not limpio) and config.ruta_biblioteca(ruta_rel).exists():
        from . import tablas
        doc = tablas.abrir(ruta_rel)
        try:
            tablas.guardar_tablas_pdf(con, doc_id, tablas.tablas_del_documento(doc, texto.paginas))
        finally:
            doc.close()
    meta = catalogo.metadatos(ruta_rel)
    ident = meta.get('identificador') or an.identificador or _identificador_fallback(ruta_rel)
    titulo = (meta.get('titulo') or an.titulo or Path(ruta_rel).stem)[:400]
    if meta:
        an.titulo = titulo
    titulo_obra = titulo if meta.get('titulo') else catalogo.titulo_oficial(ident) or titulo
    juris = 'ES' if '01_Legislacion_ES' in ruta_rel else 'UE' if '02_Legislacion_UE' in ruta_rel else 'OTRA'
    fila = con.execute('SELECT id FROM obra WHERE identificador_canonico=?', (ident,)).fetchone()
    if fila:
        obra_id = fila['id']
    else:
        obra_id = con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, emisor, emisor_metodo, jurisdiccion) VALUES (?,?,?,?,?,?)', (ident, fam, titulo_obra, *_emisor(ruta_rel), juris)).lastrowid
    _insertar_alias(con, obra_id, [*catalogo.alias_de(ruta_rel), ident, *catalogo.alias_de_titulo(an.titulo), *meta.get('alias', [])])
    edicion = catalogo.edicion_de(ruta_rel)
    if an.fecha_consolidacion:
        etiqueta = f'consolidada {an.fecha_consolidacion}'
    elif an.es_consolidada:
        etiqueta = 'consolidada'
    elif edicion:
        etiqueta = f'edicion {edicion[:4]}'
    else:
        etiqueta = 'original'
    ver_id = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, es_consolidada,\n           fecha_consolidacion, fecha_edicion, idioma, completitud, cabecera_origen)\n           VALUES (?,?,?,?,?,?,?,?,?)', (obra_id, doc_id, etiqueta, int(an.es_consolidada), an.fecha_consolidacion, edicion, catalogo.idioma_de(ruta_rel) or an.idioma, catalogo.completitud(ruta_rel), an.cabecera)).lastrowid
    por_ruta: dict[str, int] = {}
    for orden, p in enumerate(an.preceptos):
        padre_id = por_ruta.get(p.padre) if p.padre else None
        try:
            pid = con.execute('INSERT INTO precepto (version_id, padre_id, ruta_estructural, tipo_unidad,\n                   numero, etiqueta_humana, titulo, texto_literal, metodo_extraccion,\n                   marca_consolidacion, pagina_inicio, pagina_fin, orden)\n                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (ver_id, padre_id, p.ruta, p.tipo, p.numero, p.etiqueta, p.titulo, p.texto, metodo, p.marca, p.pagina_inicio, p.pagina_fin, orden)).lastrowid
            por_ruta[p.ruta] = pid
        except sqlite3.IntegrityError as e:
            if OBSERVADOR_DESCARTE is not None:
                OBSERVADOR_DESCARTE({'documento': ruta_rel, 'identificador': ident, 'version_id': ver_id, 'orden': orden, 'precepto': p, 'preceptos': an.preceptos, 'ocupante_id': por_ruta.get(p.ruta), 'error': str(e)})
            continue
    if verbose:
        print(f"  {ruta_rel.split('/')[-1][:60]:62s} {len(an.preceptos):5d} preceptos")
    return {'ruta': ruta_rel, 'estado': 'ingerido', 'preceptos': len(an.preceptos), 'identificador': ident}
ETIQUETA_VERSION = {'transcripcion_verificada': 'transcripcion verificada', 'ocr': 'reconocimiento optico'}

def ingerir_transcripcion(con: sqlite3.Connection, d: dict) -> int:
    """Public CI documentation."""
    paginas = max((p.get('pagina', 1) for p in d['preceptos']))
    fila = con.execute('SELECT id FROM documento WHERE ruta_relativa=?', (d['origen'],)).fetchone()
    if fila:
        doc_id = fila['id']
        con.execute("UPDATE documento SET estado_ingesta='ingerido', motor_extraccion=?, motivo_estado=? WHERE id=?", (d['metodo_extraccion'], d['procedencia'][:400], doc_id))
    else:
        doc_id = con.execute('INSERT INTO documento (ruta_relativa, sha256, bytes, mtime_utc, paginas,\n               hash_texto, motor_extraccion, clase_derechos, estado_ingesta, motivo_estado)\n               VALUES (?,?,?,?,?,?,?,?,?,?)', (d['origen'], '', 0, '', paginas, None, d['metodo_extraccion'], d['clase_derechos'], 'ingerido', d['procedencia'][:400])).lastrowid
    f = con.execute('SELECT id FROM obra WHERE identificador_canonico=?', (d['identificador_canonico'],)).fetchone()
    obra_id = f['id'] if f else con.execute('INSERT INTO obra (identificador_canonico, tipo, titulo, emisor, emisor_metodo, jurisdiccion) VALUES (?,?,?,?,?,?)', (d['identificador_canonico'], d.get('tipo', 'norma_tecnica'), d['titulo'][:400], *_emisor(d.get('origen', '')), 'EU')).lastrowid
    _insertar_alias(con, obra_id, [*d.get('alias', []), d['identificador_canonico'], d['obra']])
    ver_id = con.execute('INSERT INTO version (obra_id, documento_id, etiqueta, es_consolidada,\n           fecha_consolidacion, fecha_edicion, idioma, completitud, cabecera_origen)\n           VALUES (?,?,?,?,?,?,?,?,?)', (obra_id, doc_id, ETIQUETA_VERSION.get(d['metodo_extraccion'], 'derivada'), 0, None, None, d.get('idioma', 'en'), d.get('completitud', 'parcial'), d['procedencia'][:400])).lastrowid
    for orden, p in enumerate(d['preceptos']):
        con.execute('INSERT INTO precepto (version_id, padre_id, ruta_estructural, tipo_unidad,\n               numero, etiqueta_humana, titulo, texto_literal, metodo_extraccion,\n               marca_consolidacion, pagina_inicio, pagina_fin, orden)\n               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (ver_id, None, p['ruta'], p['ruta'].split('.')[0], None, p['etiqueta'], None, p['texto'], d['metodo_extraccion'], None, p.get('pagina', 1), p.get('pagina', 1), orden))
    return len(d['preceptos'])

def ingerir_celdas(con: sqlite3.Connection, verbose: bool=False) -> int:
    """Public CI documentation."""
    from . import tablas
    filas = con.execute("\n        SELECT p.id, p.pagina_inicio, p.texto_literal, d.ruta_relativa\n        FROM precepto p\n        JOIN version v ON v.id = p.version_id\n        JOIN documento d ON d.id = v.documento_id\n        -- No solo los preceptos tipulados 'tabla'. Un anexo puede ser\n        -- integramente una tabla y no llevar la palabra en su encabezado: el\n        -- anexo unico de la Decision 2025/138 son las filas que el acto anade,\n        -- y nada mas. El filtro fino lo pone rejilla_del_precepto(), que exige\n        -- que la tabla de la pagina comparta celdas con el texto del precepto.\n        WHERE p.tipo_unidad IN ('tabla', 'anexo', 'apendice')\n          AND d.ruta_relativa LIKE '%.pdf'\n          AND length(p.texto_literal) < 20000\n        ORDER BY d.ruta_relativa, p.pagina_inicio").fetchall()
    n_celdas = n_tablas = 0
    fallos: list[str] = []
    doc = ruta_abierta = None
    for pid, pagina, texto, ruta in filas:
        if ruta != ruta_abierta:
            if doc is not None:
                doc.close()
            try:
                doc, ruta_abierta = (tablas.abrir(ruta), ruta)
            except Exception as e:
                fallos.append(f'{ruta}: {type(e).__name__}')
                doc, ruta_abierta = (None, ruta)
                continue
        if doc is None:
            continue
        sueltos: list[str] = []
        try:
            rejilla = tablas.rejilla_del_precepto(doc, pagina, texto, sueltos)
        except Exception as e:
            fallos.append(f'{ruta} p.{pagina}: {type(e).__name__}')
            continue
        fallos.extend((f'{ruta} {x}' for x in sueltos))
        if not rejilla:
            continue
        n_tablas += 1
        for i, j, valor, vn in tablas.celdas(rejilla):
            con.execute('INSERT OR IGNORE INTO celda (precepto_id, fila, columna, valor, valor_norm) VALUES (?,?,?,?,?)', (pid, i, j, valor, vn))
            n_celdas += 1
    if doc is not None:
        doc.close()
    if fallos:
        print(f'AVISO: {len(fallos)} fallos al buscar estructura de tabla (al abrir el documento, al analizar la pagina o al extraer una tabla): {fallos[:3]}')
    if verbose:
        print(f'tablas con estructura: {n_tablas} de {len(filas)} preceptos candidatos, {n_celdas} celdas')
    return n_celdas

def consolidar_obras(con: sqlite3.Connection) -> int:
    """Public CI documentation."""
    fundidas = 0
    grupos = con.execute('\n        SELECT alias_norm, group_concat(DISTINCT obra_id) FROM obra_alias\n        GROUP BY alias_norm HAVING count(DISTINCT obra_id) > 1').fetchall()
    for _, ids in grupos:
        obras = [int(x) for x in ids.split(',')]
        con_texto = [o for o in obras if con.execute('SELECT 1 FROM precepto p JOIN version v ON v.id=p.version_id WHERE v.obra_id=? LIMIT 1', (o,)).fetchone()]
        if len(con_texto) != 1:
            fechas = [con.execute('SELECT fecha_edicion FROM version WHERE obra_id=? AND fecha_edicion IS NOT NULL LIMIT 1', (o,)).fetchone() for o in obras]
            vals = [f[0] for f in fechas if f]
            if len(vals) != len(obras) or len(set(vals)) != len(obras):
                continue
            principal = obras[0]
        else:
            principal = con_texto[0]
        for o in obras:
            if o == principal:
                continue
            con.execute('UPDATE version SET obra_id=? WHERE obra_id=?', (principal, o))
            con.execute('UPDATE OR IGNORE obra_alias SET obra_id=? WHERE obra_id=?', (principal, o))
            con.execute('DELETE FROM obra_alias WHERE obra_id=?', (o,))
            con.execute('DELETE FROM obra WHERE id=?', (o,))
            fundidas += 1
    return fundidas

def reconstruir(ruta_bd: Path | None=None, verbose: bool=False) -> dict:
    fundamento.olvidar_cache()
    validador.olvidar_cache()
    con = db.crear(ruta_bd)
    rutas = documentos_biblioteca()
    for g in catalogo.GUIAS_INCLUIDAS:
        if g not in rutas and (config.BIBLIOTECA / g).exists():
            rutas.append(g)
    nucleo = [r for r in rutas if catalogo.en_nucleo(r)]
    resto = [r for r in rutas if not catalogo.en_nucleo(r)]
    if verbose:
        print(f'nucleo: {len(nucleo)} PDF  |  registro sin trocear: {len(resto)} PDF')
    errores = []
    for r in sorted(nucleo):
        try:
            ingerir_documento(con, r, verbose)
        except extraccion.IngestaNoReproducible:
            raise
        except Exception as e:
            errores.append((r, f'{type(e).__name__}: {e}'))
    for r in sorted(resto):
        try:
            ingerir_documento(con, r)
        except extraccion.IngestaNoReproducible:
            raise
        except Exception as e:
            errores.append((r, f'{type(e).__name__}: {e}'))
    fichas = transcripciones.cargar_fichas()
    manuales = transcripciones.cargar()
    ya = {(d['identificador_canonico'], p['ruta']) for d in fichas + manuales for p in d['preceptos']}
    fotos = transcripciones.cargar_fotos({r for i, r in ya if i == 'EN-13486-2023'})
    for d in fichas + manuales + fotos + transcripciones.cargar_ocr():
        try:
            ingerir_transcripcion(con, d)
        except Exception as e:
            errores.append((d.get('origen', '?'), f'{type(e).__name__}: {e}'))
    ingerir_celdas(con, verbose)
    n = consolidar_obras(con)
    if verbose and n:
        print(f'obras fundidas por compartir alias: {n}')
    fundamento.olvidar_cache()
    validador.olvidar_cache()
    resumen_emisores = emisores.sellar(con, verbose)
    resumen_caracter = caracter.sellar(con, verbose)
    con.commit()
    con.execute("INSERT INTO precepto_fts(precepto_fts) VALUES('optimize')")
    con.commit()
    resumen = db.registrar_ingesta(con)
    resumen['errores'] = errores
    resumen['emisores'] = resumen_emisores
    con.close()
    return resumen
