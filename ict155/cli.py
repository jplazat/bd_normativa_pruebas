"""Public CI documentation."""
from __future__ import annotations
import argparse
import json
import re
import sys
from . import almacen, ambito, brechas, calidad_textual, completitud, config, consulta, contexto_norma, cotejo, cotejo_original, db, entrega, fundamento, historial_boe, ingesta, interruptores, relacionados, revision, sucesion, vigencia

def _salida_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

def _fecha_mal_escrita(identificador: str) -> str | None:
    """Public CI documentation."""
    cab, _ = consulta.partir_identificador(identificador)
    _, arroba, fecha = cab.partition('@')
    if not arroba or consulta.fecha_bien_escrita(fecha) or consulta.es_anio(fecha):
        return None
    return fecha

def _rechazar_fecha(identificador: str) -> bool:
    mala = _fecha_mal_escrita(identificador)
    if mala is None:
        return False
    print(f'fecha {mala!r} mal escrita: va como AAAA-MM-DD, por ejemplo "Ley 32/2014@2026-08-05::art.8.1"', file=sys.stderr)
    return True

def _entero_positivo(s: str) -> int:
    try:
        n = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{s!r} no es un numero entero') from None
    if n < 1:
        raise argparse.ArgumentTypeError(f'tiene que ser 1 o mas, no {n}')
    return n

def cmd_reconstruir(a):
    r = ingesta.reconstruir(verbose=not a.silencioso)
    print(f"\ndocumentos {r['n_documentos']}  versiones {r['n_versiones']}  preceptos {r['n_preceptos']}")
    print(f"huella {r['huella_contenido'][:16]}  base {config.BD}")
    if r['errores']:
        print(f"\n{len(r['errores'])} errores:")
        for ruta, e in r['errores']:
            print(f'  {ruta}: {e}')
        return 1
    return 0

def _tablas_del_resultado(con, r) -> list[dict]:
    """Public CI documentation."""
    from . import tablas
    out = []
    for t, filas, sin_validar in tablas.tablas_para_ensenar(con, r.fichero, r.pagina_inicio, r.pagina_fin, r.texto_literal):
        cabecera = t['filas'][0]
        cuerpo = [f for f in filas if f != cabecera]
        if not cuerpo and len(t['filas']) > 1:
            continue
        out.append(dict(orden=t['orden'], paginas=[t['pagina_inicio'], t['pagina_fin']], filas=[cabecera] + cuerpo, filas_sin_validar=sum((1 for f in cuerpo if f in sin_validar))))
    return out

def _mensaje_tabla_sucesion_rota(e: sucesion.ErrorDeTabla | interruptores.ErrorDeControles) -> str:
    if isinstance(e, almacen.ErrorDeAlmacen):
        return str(e)
    return f'{e}. Restaura `cowork/sucesores_revisados.json` desde git o baja el control `relacionados_cierra` con `D:\\Proyectos\\r27\\TODO_A_SOMBRA.cmd`.'
_ERRORES_DE_TABLA = (sucesion.ErrorDeTabla, relacionados.ErrorDeTabla, interruptores.ErrorDeControles, ambito.ReglasMal, brechas.ErrorDeCalculo)

def _mensaje_tabla_rota(e: Exception) -> str:
    if isinstance(e, calidad_textual.ErrorDeCalidad):
        return f'No se ha podido comprobar la calidad textual: {e}. Revisa o restaura `datos/calidad_textual.json`; no se omiten sus avisos.'
    if isinstance(e, almacen.ErrorDeAlmacen):
        return str(e)
    if isinstance(e, interruptores.ErrorDeControles):
        return f'No se ha podido comprobar: {e}. Restaura `cowork/controles.json` desde git: la palanca no sirve en este caso.'
    return f'No se ha podido comprobar: {e}. Restaura la tabla desde git o baja el control con `D:\\Proyectos\\r27\\TODO_A_SOMBRA.cmd`.'

def cmd_cita(a):
    if _rechazar_fecha(a.identificador):
        return 2
    con = db.conectar(solo_lectura=True)
    modo = consulta.MODO_LOCALIZAR if getattr(a, 'localizar', False) else consulta.MODO_TEXTO
    r = consulta.resolver(con, a.identificador, tuple(a.ambito), modo=modo)
    tablas_r = _tablas_del_resultado(con, r) if r.texto_literal else []
    ctx = None
    if getattr(a, 'contexto', False) and r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO):
        ctx = contexto_norma.contexto(con, a.identificador, tuple(a.ambito))
    vig = None
    if r.obra and r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO):
        vig = vigencia.vigencia_de(r.obra, vigencia.instantanea_actual())
        if vig and vig.get('estado') == 'derogada':
            try:
                vig['sucesion'] = sucesion.sucesores_de(r.obra, consulta.partir_identificador(r.identificador or a.identificador)[1])
            except (sucesion.ErrorDeTabla, interruptores.ErrorDeControles) as e:
                print(_mensaje_tabla_sucesion_rota(e), file=sys.stderr)
                return 2
    hist = None
    if r.obra and r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO):
        hist = historial_boe.historial_de(r.obra, consulta.partir_identificador(r.identificador or a.identificador)[1], historial_boe.instantanea_actual(), con=con)
    if a.json:
        d = r.dict()
        d['tablas'] = tablas_r
        if ctx is not None:
            d['contexto'] = ctx
        if vig is not None:
            d['vigencia'] = vig
        if hist is not None:
            d['historial'] = hist
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0 if r.estado == consulta.ENCONTRADO else 1
    print(f'[{r.estado}]  {a.identificador}')
    if r.detalle:
        print(f'  {r.detalle}')
    if r.candidatos:
        print(f"  cercanos: {', '.join(map(str, r.candidatos))}")
    if r.estado in (consulta.ENCONTRADO, consulta.LOCALIZADO_SIN_TEXTO):
        print(f'\n  {r.etiqueta_humana}' + (f'. {r.titulo}' if r.titulo else ''))
        if r.texto_literal:
            print(f'\n{r.texto_literal}\n')
        from . import tablas
        for t in tablas_r:
            print(f"  tabla {t['orden']} del documento (paginas {t['paginas'][0]}-{t['paginas'][1]}), filas de este precepto:\n")
            print(tablas.markdown(t['filas']) + '\n')
            if t['filas_sin_validar']:
                n = t['filas_sin_validar']
                print(f"  ({n} fila{('s' if n > 1 else '')} de esta tabla no sale{('n' if n > 1 else '')} seguida{('s' if n > 1 else '')} en el texto del precepto: se ensena{('n' if n > 1 else '')}, pero el comprobador de citas no la{('s' if n > 1 else '')} lee por filas.)\n")
        print(f"  obra    : {r.obra}  {r.obra_titulo or ''}"[:110])
        print(f'  version : {r.version}' + (f'  (consolidacion {r.fecha_consolidacion})' if r.fecha_consolidacion else ''))
        print(f'  fichero : {r.fichero}')
        print(f'  paginas : {r.pagina_inicio}' + (f'-{r.pagina_fin}' if r.pagina_fin != r.pagina_inicio else ''))
        if r.marca_consolidacion:
            print(f'  marca   : {r.marca_consolidacion}')
        if r.regimen and r.regimen != 'publico':
            print(f'  regimen : {r.regimen}')
        if r.naturaleza_del_texto:
            print(f'  AVISO: el texto de arriba no es el literal del documento ({r.naturaleza_del_texto})')
        if not r.reproducible:
            print('  AVISO: contenido no reproducible fuera de la casa')
        elif r.regimen and r.regimen != 'publico':
            print('  AVISO: texto de pago. En un entregable se cita clausula y pagina, no el literal (regla 8.4)')
    if vig:
        print('\n' + vigencia.texto(vig))
    if hist:
        print('\n' + historial_boe.texto(hist))
    if ctx:
        texto_ctx = contexto_norma.texto(ctx)
        if texto_ctx:
            print(texto_ctx)
    return 0 if r.estado == consulta.ENCONTRADO else 1

def cmd_vigencia(a):
    """Public CI documentation."""
    if a.actualizar:
        datos = vigencia.instantanea(config.BD, progreso=lambda s: print(s, file=sys.stderr, flush=True))
        vigencia.escribir_instantanea(datos, vigencia.ruta_instantanea())
        print(vigencia.resumen(datos))
        print(f'escrita {vigencia.ruta_instantanea()}')
        return 0
    datos = vigencia.instantanea_actual()
    otras_copias: dict[str, list[str]] = {}
    no_esta: dict[str, dict] = {}
    if a.obra:
        con = db.conectar(solo_lectura=True)
        obras, otras_copias, no_legislativas = vigencia.obras_de_la_norma(con, a.obra)
        if not obras and no_legislativas:
            obras = no_legislativas[:5]
        elif not obras:
            no_esta[a.obra] = {'menciones': _menciones_de(con, a.obra)}
    else:
        obras = sorted((datos or {}).get('obras', {}))
    salida = {o: vigencia.vigencia_de(o, datos) for o in obras}
    if a.json:
        d = {'consultado': (datos or {}).get('consultado'), 'obras': salida}
        copias = {o: c for o, c in otras_copias.items() if c}
        if copias:
            d['otras_copias'] = copias
        if no_esta:
            d['no_esta_en_la_base'] = no_esta
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    if datos is None:
        print('No hay consulta de vigencia en esta base: ict155.cli vigencia --actualizar')
    for o, v in salida.items():
        if v is None:
            print(f'{o}: no es legislacion (no hay vigencia que consultar)')
            continue
        print(f"{o}  [{v.get('estado') or 'sin estado'}]" + ('' if v['avisos'] else '  al dia'))
        for av in v['avisos']:
            print(f'    AVISO: {av}')
        if otras_copias.get(o):
            print(f"    otras copias de la misma norma en la base: {', '.join(otras_copias[o])}")
    for nombre, info in no_esta.items():
        print(f'{nombre}: la base NO tiene esa norma (no se sabe su vigencia). Buscala con `buscar`: ' + (f"se la menciona en {', '.join(info['menciones'])}" if info['menciones'] else 'ninguna norma la menciona'))
    return 0

def cmd_historial_boe(a):
    """Public CI documentation."""
    from pathlib import Path
    destino = Path(a.salida) if a.salida else historial_boe.ruta_instantanea()
    if a.actualizar:
        datos = historial_boe.instantanea(config.BD, progreso=lambda s: print(s, file=sys.stderr, flush=True))
        historial_boe.escribir_instantanea(datos, destino)
        print(historial_boe.resumen(datos))
        print(f'escrita {destino}')
        return 0
    if a.ruta and (not a.obra):
        print('--ruta necesita --obra: la obra de la que se quiere el historial del precepto', file=sys.stderr)
        return 2
    datos = historial_boe.instantanea_actual(destino)
    if datos is None:
        print(f'No hay consulta del historial de redacciones ({destino}): ict155.cli historial-boe --actualizar')
        return 1
    if not a.obra:
        if a.json:
            print(json.dumps({'consultado': datos.get('consultado'), 'obras': {i: o.get('recuento') or {'estado': o['estado'], 'error': o.get('error')} for i, o in datos['obras'].items()}}, ensure_ascii=False, indent=2))
            return 0
        print(historial_boe.resumen(datos))
        print('\n'.join(historial_boe.lineas_de_resumen(datos)))
        return 0
    con = db.conectar(solo_lectura=True)
    obras, _otras, no_legislativas = vigencia.obras_de_la_norma(con, a.obra)
    obra = next((o for o in obras if o in datos['obras']), None) or (obras[0] if obras else None)
    if obra is None or not vigencia.RE_BASE_BOE.match(obra):
        print(f'{a.obra}: no es una norma del BOE de la base (identificador BOE-A-...): no hay historial de redacciones que consultar' + (f" ({', '.join(no_legislativas[:3])} no es legislacion)" if no_legislativas else ''))
        return 2
    if a.ruta:
        h = historial_boe.historial_de(obra, consulta.ruta_canonica(a.ruta), datos, con=con)
        if a.json:
            print(json.dumps(h, ensure_ascii=False, indent=2))
        else:
            print(f'{obra}::{consulta.ruta_canonica(a.ruta)}\n' + historial_boe.texto(h))
        return 0 if h and h['estado'] == historial_boe.ESTADO_OK else 1
    o = datos['obras'].get(obra)
    if o is None:
        print(f'{obra}: no esta en la consulta del historial de redacciones')
        return 1
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=2))
        return 0
    print('\n'.join(historial_boe.lineas_de_resumen(datos, obra)))
    for d in o.get('sin_ruta') or []:
        print(f"    sin ruta: {d['bloque']} ({d['tipo']}, «{d['titulo'] or ''}»): {d['motivo']}" + (f" [{d['candidata']}]" if d.get('candidata') else ''))
    return 0

def cmd_cotejo(a):
    """Public CI documentation."""
    from pathlib import Path
    if a.actualizar:
        destino = Path(a.salida) if a.salida else cotejo_original.directorio()
        boe = cotejo_original.instantanea_boe(config.BD, progreso=lambda s: print(s, file=sys.stderr, flush=True))
        cotejo_original.escribir_instantanea(boe, destino / cotejo_original.NOMBRE_BOE)
        ue = cotejo_original.instantanea_ue(config.BD, progreso=lambda s: print(s, file=sys.stderr, flush=True))
        cotejo_original.escribir_instantanea(ue, destino / cotejo_original.NOMBRE_UE)
        print(cotejo_original.resumen(cotejo_original.Datos(boe, ue)))
        print(f'escritas {destino / cotejo_original.NOMBRE_BOE} y {destino / cotejo_original.NOMBRE_UE}')
        return 0
    if a.salida:
        datos = cotejo_original.Datos(cotejo_original.instantanea_boe_actual(Path(a.salida) / cotejo_original.NOMBRE_BOE), cotejo_original.instantanea_ue_actual(Path(a.salida) / cotejo_original.NOMBRE_UE))
    else:
        datos = cotejo_original.datos_actuales()
    if a.ruta and (not a.obra):
        print('--ruta necesita --obra: la obra del precepto del que se quiere el testigo', file=sys.stderr)
        return 2
    if a.medir:
        con = db.conectar(solo_lectura=True)
        r = cotejo_original.medir(con, datos, a.muestra, progreso=lambda s: print(s, file=sys.stderr, flush=True))
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(cotejo_original.texto_de_medicion(r))
            print('\n' + cotejo_original.resumen(datos))
        return 0
    if not a.obra:
        if datos.boe is None and datos.ue is None:
            print(f'No hay consulta del texto oficial ({cotejo_original.directorio()}): ict155.cli cotejo --actualizar')
            return 1
        if a.json:
            print(json.dumps({'boe': datos.boe and {i: {'estado': o['estado'], 'fuente': o.get('fuente'), 'error': o.get('error')} for i, o in datos.boe['obras'].items()}, 'ue': datos.ue and {i: {k: {'estado': e['estado'], 'celex': e['celex'], 'error': e.get('error')} for k, e in o['versiones'].items()} for i, o in datos.ue['obras'].items()}}, ensure_ascii=False, indent=2))
            return 0
        print(cotejo_original.resumen(datos))
        print('\n'.join(cotejo_original.lineas_de_resumen(datos)))
        return 0
    con = db.conectar(solo_lectura=True)
    r = consulta.resolver(con, f'{a.obra}::{a.ruta}' if a.ruta else a.obra)
    if r.estado not in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO) or not r.version_id:
        print(f"{a.obra}{('::' + a.ruta if a.ruta else '')}: {r.estado} {r.detalle or ''}".rstrip())
        return 2
    ruta = consulta.ruta_efectiva(con, r.version_id, consulta.ruta_canonica(a.ruta)) if a.ruta else ''
    texto, que = cotejo_original.texto_del_testigo(con, r.version_id, ruta, datos)
    print(f'{r.obra}::{ruta}  [{cotejo_original.familia_de(r.obra)}]')
    if texto is None:
        print(f'  {que}')
        return 1
    print(f'  testigo: {que} ({len(texto):,} caracteres)')
    _r, base = revision._texto_de(con, f'{r.obra}::{ruta}') if ruta else (None, '')
    if base:
        base_ok = cotejo_original.cotejar(con, r.version_id, ruta, [base], datos)
        print(f'  el texto de la base ({len(base):,} caracteres) ' + ('esta entero en el testigo' if base_ok.estado == cotejo_original.OK else f'NO esta entero en el testigo ({base_ok.estado})'))
        if base_ok.estado == cotejo_original.DISTINTO and base_ok.original:
            print(f'  el original dice: «{base_ok.original}»')
    if a.json:
        print(json.dumps({'obra': r.obra, 'ruta': ruta, 'testigo': que, 'texto': texto}, ensure_ascii=False, indent=2))
        return 0
    if base and len(texto) > 2 * len(base) + 2000:
        zona = cotejo_original.zona_del_testigo(base, texto)
        if zona:
            print(f'\n(la parte del original que corresponde al precepto, normalizada; {len(texto):,} caracteres tiene la norma entera)\n{zona}')
            return 0
    if len(texto) <= 4000:
        print('\n' + texto)
    else:
        print('\n' + texto[:4000] + f'\n… ({len(texto) - 4000:,} caracteres mas; --json los da enteros)')
    return 0

def _menciones_de(con, nombre: str, maximo: int=5) -> list[str]:
    """Public CI documentation."""
    numeros = re.findall('\\d+(?:/\\d+)+', nombre)
    vistos: dict[str, None] = {}
    for f in consulta.buscar(con, numeros[0] if numeros else nombre, maximo * 2):
        vistos.setdefault(f"{f['obra']}::{f['ruta_estructural']}", None)
    return list(vistos)[:maximo]

def _leer_borrador(fuente: str) -> str:
    """Public CI documentation."""
    if fuente == '-':
        return sys.stdin.buffer.read().decode('utf-8-sig')
    with open(fuente, 'rb') as f:
        return f.read().decode('utf-8-sig')

def cmd_revisar(a):
    """Public CI documentation."""
    try:
        borrador = _leer_borrador(a.fuente)
    except OSError as e:
        print(f'no se puede leer {a.fuente!r}: {e.strerror or e}', file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print('el borrador no esta en UTF-8', file=sys.stderr)
        return 2
    con = db.conectar(solo_lectura=True)
    try:
        informe = revision.revisar(con, borrador, tuple(a.ambito))
    except _ERRORES_DE_TABLA as e:
        print(_mensaje_tabla_rota(e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(informe.dict(), ensure_ascii=False, indent=2))
    else:
        print(informe.texto())
    return 0 if informe.resumen()['errores'] == 0 else 1

class _EntradaMala(Exception):
    """Public CI documentation."""

def _leer_json_utf8(ruta: str, que: str):
    """Public CI documentation."""
    try:
        return json.loads(_leer_borrador(ruta))
    except OSError as e:
        raise _EntradaMala(f'no se puede leer {ruta!r}: {e.strerror or e}') from None
    except UnicodeDecodeError:
        raise _EntradaMala(f'{que} no esta en UTF-8') from None
    except ValueError as e:
        raise _EntradaMala(f'{que} no es un JSON valido ({e})') from None

def _respuesta_y_pregunta(a) -> tuple[str, str | None]:
    """Public CI documentation."""
    if a.entrada_json and a.pregunta_fichero:
        raise _EntradaMala('--entrada-json y --pregunta-fichero no van juntos: con --entrada-json la pregunta viene en el JSON')
    if a.pregunta_fichero == '-' and a.fuente == '-':
        raise _EntradaMala('--pregunta-fichero no puede ser - si la respuesta tambien viene de la entrada estandar')
    if a.entrada_json:
        d = _leer_json_utf8(a.fuente, 'la entrada')
        if not isinstance(d, dict) or not isinstance(d.get('respuesta'), str):
            raise _EntradaMala('--entrada-json: la entrada tiene que ser un objeto {"respuesta": "...", "pregunta": "..."} con la respuesta como texto')
        if d.get('pregunta') is not None and (not isinstance(d['pregunta'], str)):
            raise _EntradaMala('--entrada-json: "pregunta" tiene que ser un texto')
        return (d['respuesta'], d.get('pregunta'))
    try:
        respuesta = _leer_borrador(a.fuente)
    except OSError as e:
        raise _EntradaMala(f'no se puede leer {a.fuente!r}: {e.strerror or e}') from None
    except UnicodeDecodeError:
        raise _EntradaMala('la respuesta no esta en UTF-8') from None
    pregunta = None
    if a.pregunta_fichero:
        try:
            pregunta = _leer_borrador(a.pregunta_fichero)
        except OSError as e:
            raise _EntradaMala(f'no se puede leer {a.pregunta_fichero!r}: {e.strerror or e}') from None
        except UnicodeDecodeError:
            raise _EntradaMala('la pregunta no esta en UTF-8') from None
    return (respuesta, pregunta)

def _pasadas_pedidas(a, por_defecto: int) -> int:
    """Public CI documentation."""
    if a.pasadas is not None and (not a.revision_independiente):
        raise _EntradaMala('--pasadas solo vale con --revision-independiente')
    return por_defecto if a.pasadas is None else a.pasadas

def cmd_verificar_entrega(a):
    """Public CI documentation."""
    try:
        revisiones = _pasadas_pedidas(a, 1)
        respuesta, pregunta = _respuesta_y_pregunta(a)
        con = db.conectar(solo_lectura=True)
        v = entrega.verificar(con, respuesta, tuple(a.ambito), pregunta=pregunta, revision_independiente=a.revision_independiente, cache_revision=not a.sin_cache_revision, revisiones=revisiones)
    except _EntradaMala as e:
        print(e, file=sys.stderr)
        return 2
    except completitud.TemasMal as e:
        print(e, file=sys.stderr)
        return 2
    except _ERRORES_DE_TABLA as e:
        print(_mensaje_tabla_rota(e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(v.dict(), ensure_ascii=False, indent=2))
    else:
        print(v.texto())
    return 0 if v.valida else 1

def cmd_obligatorios(a):
    """Public CI documentation."""
    try:
        pregunta = _leer_borrador(a.fuente)
    except OSError as e:
        print(f'no se puede leer {a.fuente!r}: {e.strerror or e}', file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print('la pregunta no esta en UTF-8', file=sys.stderr)
        return 2
    try:
        temas = completitud.temas_de(pregunta)
    except (completitud.TemasMal, interruptores.ErrorDeControles) as e:
        print(e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(completitud.a_dict(temas, pregunta), ensure_ascii=False, indent=2))
    else:
        print(completitud.texto(temas, pregunta))
    return 0

def cmd_verificar_entregas(a):
    """Public CI documentation."""
    from pathlib import Path
    try:
        revisiones = _pasadas_pedidas(a, 1)
    except _EntradaMala as e:
        print(e, file=sys.stderr)
        return 2
    carpeta = Path(a.carpeta)
    if not carpeta.is_dir():
        print(f'{a.carpeta!r} no es una carpeta', file=sys.stderr)
        return 2
    preguntas = temas = None
    if a.preguntas:
        try:
            preguntas = _leer_preguntas(a.preguntas)
            temas = completitud.cargar()
        except _EntradaMala as e:
            print(e, file=sys.stderr)
            return 2
        except completitud.TemasMal as e:
            print(e, file=sys.stderr)
            return 2
    ficheros = sorted((f for f in carpeta.iterdir() if f.is_file() and f.suffix.lower() == '.md' and (not f.name.lower().endswith('_no_abrir.md'))), key=lambda f: f.name.lower())
    con = db.conectar(solo_lectura=True)
    huella = db.huella_contenido(con)
    datos = vigencia.instantanea_actual()
    try:
        tabla = sucesion.cargar()
        relacionados.cargar()
        if interruptores.modo('ambito') == 'bloquea':
            ambito.cargar()
    except _ERRORES_DE_TABLA as e:
        print(_mensaje_tabla_rota(e), file=sys.stderr)
        return 2
    filas, ilegibles = ([], 0)
    for f in ficheros:
        try:
            texto = _leer_borrador(str(f))
        except (OSError, UnicodeDecodeError) as e:
            ilegibles += 1
            fila = {'fichero': f.name, 'veredicto': 'NO SE PUEDE LEER', 'motivos': [str(getattr(e, 'strerror', None) or e)], 'sello': None, 'sello_en_el_texto': None}
            if preguntas is not None:
                fila.update(completa='-', temas=[], faltan=[])
            filas.append(fila)
            continue
        pregunta = None
        if preguntas is not None:
            pregunta = preguntas.get(f.name)
            if pregunta is None:
                pregunta = next((p for k, p in preguntas.items() if k.casefold() == f.name.casefold()), None)
        v = entrega.verificar(con, texto, tuple(a.ambito), huella, datos_vigencia=datos, tabla_sucesion=tabla, pregunta=pregunta, temas=temas, revision_independiente=a.revision_independiente, cache_revision=not a.sin_cache_revision, revisiones=revisiones)
        avisos = [c for c in v.avisos if c.nivel == revision.AVISO]
        motivos = v.motivos or ([f"{len(avisos)} {('aviso' if len(avisos) == 1 else 'avisos')} que atender"] if avisos else [])
        fila = {'fichero': f.name, 'veredicto': v.veredicto, 'motivos': motivos, 'sello': v.codigo, 'sello_en_el_texto': v.codigo_presente}
        if preguntas is not None:
            fila.update(completa=_completa(v), temas=v.temas, faltan=[x.dict() for x in v.faltan])
        if a.revision_independiente and v.independiente is not None:
            ind = v.independiente
            fila['revision_independiente'] = {'hecha': ind.hecha, 'fallo': ind.fallo, 'omitida': ind.omitida, 'modelo': ind.modelo, 'segundos': round(ind.segundos, 1), 'en_cache': ind.en_cache, 'pasadas': ind.pasadas, 'objeciones': [o.dict() for o in ind.objeciones], 'n_descartadas': ind.n_descartadas, 'descartes_por_motivo': ind.descartes_por_motivo()}
        filas.append(fila)
    cuenta = {x: sum((1 for r in filas if r['veredicto'] == x)) for x in entrega.VEREDICTOS}
    sin_pregunta = [r['fichero'] for r in filas if r.get('completa') == 'sin pregunta']
    nombres = {f.name.casefold() for f in ficheros}
    sin_fichero = sorted((k for k in preguntas if k.casefold() not in nombres), key=str.casefold) if preguntas is not None else []
    incompletas = sum((1 for r in filas if r.get('faltan')))
    if a.json:
        salida = {'carpeta': str(carpeta), 'huella_base': huella, 'filas': filas, 'recuento': cuenta, 'ilegibles': ilegibles}
        if preguntas is not None:
            salida.update(preguntas=str(a.preguntas), incompletas=incompletas, sin_pregunta=sin_pregunta, preguntas_sin_fichero=sin_fichero)
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        print(f'VERIFICACIÓN DE ENTREGAS de {carpeta} (huella de la base {huella[:8]})\n')
        if preguntas is None:
            print('| Fichero | Veredicto | Motivo |\n|---|---|---|')
            for r in filas:
                print(f"| {r['fichero']} | {r['veredicto']} | {'; '.join(_motivos_de_la_tabla(r['motivos'])) or '-'} |")
        else:
            print('| Fichero | Veredicto | Motivo | Completa |\n|---|---|---|---|')
            for r in filas:
                motivos = [m for m in r['motivos'] if not m.startswith('INCOMPLETA: ')]
                if r['faltan']:
                    n = len(r['faltan'])
                    motivos.append(f"INCOMPLETA: {n} obligatorio{('s' if n != 1 else '')} sin citar")
                print(f"| {r['fichero']} | {r['veredicto']} | {'; '.join(_motivos_de_la_tabla(motivos)) or '-'} | {r['completa']} |")
        if a.revision_independiente:
            _imprimir_revision_independiente(filas)
        print(f'\n{len(filas)} ficheros: {cuenta[entrega.VALIDA]} válidas, {cuenta[entrega.VALIDA_CON_AVISOS]} válidas con avisos, {cuenta[entrega.NO_VALIDA]} no válidas' + (f', {ilegibles} que no se han podido leer' if ilegibles else '') + '.')
        if preguntas is not None:
            print(f'{incompletas} incompletas (les falta citar lo obligatorio del tema de su pregunta).')
            if sin_pregunta:
                print(f"Sin pregunta en {a.preguntas} (verificadas sin comprobar que estén completas): {', '.join(sin_pregunta)}.")
            if sin_fichero:
                print(f"Preguntas sin fichero en la carpeta: {', '.join(sin_fichero)}.")
            print('«Completa: sí» solo dice que no falta ningún obligatorio de los temas detectados en la pregunta: la lista no es exhaustiva y, sin tema detectado, no hay nada que exigir.')
    if ilegibles:
        return 2
    return 1 if cuenta[entrega.NO_VALIDA] else 0
PREFIJO_OBJECION = 'OBJECIÓN de la revisión independiente: '

def _motivos_de_la_tabla(motivos: list[str]) -> list[str]:
    """Public CI documentation."""
    objeciones = [m for m in motivos if m.startswith(PREFIJO_OBJECION)]
    resto = [m for m in motivos if not m.startswith(PREFIJO_OBJECION)]
    return resto + ([f"{len(objeciones)} {('OBJECIÓN' if len(objeciones) == 1 else 'OBJECIONES')} de la revisión independiente (debajo)"] if objeciones else [])

def _imprimir_revision_independiente(filas: list[dict]) -> None:
    """Public CI documentation."""
    hechas = [r for r in filas if r.get('revision_independiente')]
    con_objeciones = [r for r in hechas if r['revision_independiente']['objeciones']]
    no_hechas = [r for r in hechas if not r['revision_independiente']['hecha']]
    descartadas = sum((r['revision_independiente']['n_descartadas'] for r in hechas if r['revision_independiente']['hecha']))
    if con_objeciones:
        print('\nOBJECIONES de la revisión independiente (cada una se resuelve cambiando el texto o marcándolo como opinión si es una lectura):')
        for r in con_objeciones:
            for o in r['revision_independiente']['objeciones']:
                print(f"- {r['fichero']}: {o['motivo']}")
    print(f"\nRevisión independiente: {sum((len(r['revision_independiente']['objeciones']) for r in hechas))} objeciones en {len(con_objeciones)} de {len(hechas)} ficheros; {len(no_hechas)} sin poder hacerse (NO VÁLIDAS); {descartadas} descartadas por el código por no traer pruebas verificables.")

def _completa(v) -> str:
    """Public CI documentation."""
    if not v.pregunta_dada:
        return 'sin pregunta'
    return 'NO: falta ' + ', '.join((f.identificador for f in v.faltan)) if v.faltan else 'sí'

def _leer_preguntas(ruta: str) -> dict[str, str]:
    """Public CI documentation."""
    d = _leer_json_utf8(ruta, 'el fichero de preguntas')
    if not isinstance(d, dict) or any((not isinstance(k, str) or not isinstance(v, str) for k, v in d.items())):
        raise _EntradaMala('el fichero de preguntas tiene que ser un objeto {"Q1.md": "la pregunta", ...} con textos')
    return d

def cmd_brechas(a):
    """Public CI documentation."""
    from . import brechas
    try:
        registro = brechas.leer_registro(a.registro)
    except brechas.RegistroMalo as e:
        print(f"registro no válido ({len(e.errores)} problema{('s' if len(e.errores) != 1 else '')}):", file=sys.stderr)
        for m in e.errores:
            print(f'  - {m}', file=sys.stderr)
        return 2
    if a.para_responsable and (not a.informe_fase2):
        print('--para-responsable solo vale con --informe-fase2', file=sys.stderr)
        return 2
    con = db.conectar(solo_lectura=True)
    if a.informe_fase2:
        if a.corte is not None and (not brechas._fecha_ok(a.corte)):
            print(f'--corte {a.corte!r} no es una fecha AAAA-MM-DD válida', file=sys.stderr)
            return 2
        if a.fecha_emision is not None and (not brechas._fecha_ok(a.fecha_emision)):
            print(f'--fecha-emision {a.fecha_emision!r} no es una fecha AAAA-MM-DD válida', file=sys.stderr)
            return 2
        fecha_emision_fase2 = a.fecha_emision or brechas.datetime.date.today().isoformat()
        ambitos_fase2 = tuple(a.ambito) or ('publico',)
        corte_final_fase2 = a.corte if a.corte is not None else registro.get('fecha_corte')
        corte_efectivo_fase2 = min(corte_final_fase2, fecha_emision_fase2) if isinstance(corte_final_fase2, str) and brechas._fecha_ok(corte_final_fase2) else None
        try:
            resultados = brechas.comprobar(con, registro, ambitos_fase2, corte=corte_efectivo_fase2)
        except _ERRORES_DE_TABLA as e:
            print(_mensaje_tabla_rota(e), file=sys.stderr)
            return 2
        errores_previos = [(r.brecha.get('id'), c) for r in resultados for c in r.citas if c.nivel == brechas.ERROR]
        if errores_previos:
            print('el informe de la Fase 2 no se compone: la comprobación de siempre tiene errores sin resolver:', file=sys.stderr)
            for bid, c in errores_previos:
                print(f"  - {bid}: {c.identificador}: {'; '.join(c.detalle)}", file=sys.stderr)
            return 1
        try:
            if a.para_responsable:
                texto = brechas.informe_fase2_para_responsable_markdown(con, registro, ambitos=ambitos_fase2, resultados=resultados, corte=a.corte, fecha_emision=fecha_emision_fase2)
            else:
                texto = brechas.informe_fase2_markdown(con, registro, tipo=a.tipo, corte=a.corte, ambitos=ambitos_fase2, fecha_emision=fecha_emision_fase2)
        except brechas.InformeFase2Bloqueado as e:
            print(f'informe no generado: {e}', file=sys.stderr)
            return 2
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        except _ERRORES_DE_TABLA as e:
            print(_mensaje_tabla_rota(e), file=sys.stderr)
            return 2
        codigo = 0
    else:
        try:
            resultados = brechas.comprobar(con, registro, tuple(a.ambito))
        except _ERRORES_DE_TABLA as e:
            print(_mensaje_tabla_rota(e), file=sys.stderr)
            return 2
        texto = brechas.informe_markdown(con, registro, resultados)
        codigo = 1 if any((c.nivel == brechas.ERROR for r in resultados for c in r.citas)) else 0
    if a.salida:
        try:
            from datetime import datetime
            from pathlib import Path
            ruta = Path(a.salida)
            contenido = texto.encode('utf-8')
            if ruta.is_symlink():
                raise OSError('la salida es un enlace; no se escribe a través de él')
            if ruta.exists():
                if ruta.read_bytes() == contenido:
                    print(f'sin cambios {a.salida}')
                    return codigo
                sello = datetime.now().strftime('%Y%m%d-%H%M%S')
                anterior = ruta.with_name(f'{ruta.stem}_anterior_{sello}{ruta.suffix}')
                n = 2
                while anterior.exists() or anterior.is_symlink():
                    anterior = ruta.with_name(f'{ruta.stem}_anterior_{sello}_{n}{ruta.suffix}')
                    n += 1
                ruta.rename(anterior)
                print(f'informe anterior conservado en {anterior}')
            with ruta.open('xb') as f:
                f.write(contenido)
        except UnicodeError:
            print('no se puede codificar el informe en UTF-8; revisa el texto del registro', file=sys.stderr)
            return 2
        except OSError as e:
            print(f'no se puede escribir {a.salida!r}: {e.strerror or e}', file=sys.stderr)
            return 2
        print(f'escrito {a.salida}')
    else:
        try:
            print(texto, end='')
        except UnicodeError:
            print('no se puede codificar el informe para la consola; usa --salida con un fichero UTF-8', file=sys.stderr)
            return 2
    return codigo

def cmd_comprobar_carpeta(a):
    """Public CI documentation."""
    from pathlib import Path
    from . import comprobar_carpeta
    try:
        revisiones = _pasadas_pedidas(a, 2)
    except _EntradaMala as e:
        print(e, file=sys.stderr)
        return 2
    carpeta = Path(a.carpeta)
    if not carpeta.is_dir():
        print(f'{a.carpeta!r} no es una carpeta', file=sys.stderr)
        return 2
    con = db.conectar(solo_lectura=True)
    try:
        if interruptores.modo('ambito') == 'bloquea':
            ambito.cargar()
        r = comprobar_carpeta.comprobar(con, carpeta, a.archivada_en, momento=a.momento, revision_independiente=a.revision_independiente, revisiones=revisiones)
    except comprobar_carpeta.CarpetaIlegible as e:
        print(e, file=sys.stderr)
        return 2
    except completitud.TemasMal as e:
        print(e, file=sys.stderr)
        return 2
    except _ERRORES_DE_TABLA as e:
        print(_mensaje_tabla_rota(e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r.dict(), ensure_ascii=False, indent=2))
    else:
        print(r.texto(), end='')
    if r.error_tabla:
        return 2
    return 0 if r.listo else 1

def cmd_cotejar(a):
    """Public CI documentation."""
    _, ruta = consulta.partir_identificador(a.identificador)
    if not ruta:
        print('cotejar necesita la ruta del precepto: obra::ruta, por ejemplo "EN 12830:2018::ap.5.3.4"', file=sys.stderr)
        return 2
    if _rechazar_fecha(a.identificador):
        return 2
    con = db.conectar(solo_lectura=True)
    r = consulta.resolver(con, a.identificador, tuple(a.ambito), modo=consulta.MODO_LOCALIZAR)
    if r.estado not in (consulta.ENCONTRADO, consulta.LOCALIZADO_SIN_TEXTO):
        print(f'[{r.estado}]  {a.identificador}')
        if r.detalle:
            print(f'  {r.detalle}')
        return 1
    fila = con.execute('SELECT texto_literal t FROM precepto WHERE version_id = ? AND ruta_estructural = ?', (r.version_id, consulta.ruta_efectiva(con, r.version_id, ruta))).fetchone()
    c = cotejo.cotejar(fila['t'] if fila else None, a.afirmacion)
    if a.json:
        print(json.dumps(c.__dict__, ensure_ascii=False, indent=2))
        return 0 if c.estado == cotejo.COINCIDE else 1
    print(f'[{c.estado}]  {a.identificador}')
    if c.detalle:
        print(f'  {c.detalle}')
        return 1
    print(f'  {c.proporcion:.0%} de las {c.n_afirmacion} palabras con contenido de la afirmacion estan en el precepto')
    if c.faltan:
        print(f"  faltan: {', '.join(c.faltan[:20])}")
    print(f'  fichero : {r.fichero}   paginas: {r.pagina_inicio}')
    if not r.reproducible:
        print('  AVISO: precepto de regimen restringido. Su texto NO se ha')
        print('  impreso y no debe reproducirse en un entregable.')
    print()
    print('  Coincidir no prueba que la afirmacion sea correcta: las palabras')
    print('  pueden estar y el sentido ser el contrario. Esto acota el trabajo')
    print('  de quien valida, no lo sustituye.')
    return 0 if c.estado == cotejo.COINCIDE else 1

def cmd_buscar(a):
    con = db.conectar(solo_lectura=True)
    filas = consulta.buscar(con, a.consulta, a.limite, tuple(a.ambito))
    obras = consulta.obras_para_buscar(con, a.consulta, tuple(a.ambito)) if a.con_obras or not a.json else []
    if a.json:
        if a.con_obras:
            print(json.dumps({'obras': obras, 'resultados': filas}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(filas, ensure_ascii=False, indent=2))
        return 0 if filas or obras else 1
    if obras:
        print(f'Obras de la base que se llaman «{a.consulta}»:')
        for o in obras:
            print('\n'.join(o['lineas']))
        print()
    if not filas:
        if not obras:
            print('sin resultados', file=sys.stderr)
            return 1
        return 0
    for f in filas:
        regimen = f"   [{f['clase_derechos']}]" if f['clase_derechos'] != 'publico' else ''
        print(f"{f['obra']}/{f['ruta_estructural']}   p.{f['pagina_inicio']}{regimen}")
        print(f"   {f['etiqueta_humana']}" + (f". {f['titulo']}" if f['titulo'] else ''))
        print(f"   {f['fragmento']}".replace('\n', ' ')[:220])
        print()
    return 0

def cmd_info(a):
    con = db.conectar(solo_lectura=True)
    i = con.execute('SELECT * FROM ingesta ORDER BY id DESC LIMIT 1').fetchone()
    if not i:
        print('base sin ingesta', file=sys.stderr)
        return 1
    print(f'base     : {config.BD}')
    print(f"ingesta  : {i['ejecutada_en']}  commit {i['git_commit']}")
    print(f"contenido: {i['n_documentos']} documentos, {i['n_versiones']} versiones, {i['n_preceptos']} preceptos")
    print(f"huella   : {i['huella_contenido']}")
    datos = vigencia.instantanea_actual()
    print(f'vigencia : ' + ((f"consultada {datos['consultado']}" if datos.get('consultado') else 'complemento sin fecha de consulta') + f" (BOE y CELLAR), {len(datos.get('obras', {}))} normas" if datos else 'SIN CONSULTAR (ict155.cli vigencia --actualizar)'))
    hist = historial_boe.instantanea_actual()
    print(f'historial: ' + (f"consultado {hist.get('consultado')} (BOE), {len(hist.get('obras', {}))} normas" if hist else 'SIN CONSULTAR (ict155.cli historial-boe --actualizar)'))
    print('cotejo   : ' + cotejo_original.resumen(cotejo_original.datos_actuales()))
    for f in con.execute('SELECT estado_ingesta, count(*) n FROM documento GROUP BY 1 ORDER BY n DESC'):
        print(f"  {f['estado_ingesta']:32s} {f['n']}")
    return 0

def cmd_obras(a):
    con = db.conectar(solo_lectura=True)
    for f in con.execute('\n        SELECT o.identificador_canonico i, o.titulo t, v.etiqueta e,\n               (SELECT count(*) FROM precepto p WHERE p.version_id=v.id) n\n        FROM obra o JOIN version v ON v.obra_id=o.id ORDER BY o.jurisdiccion, o.identificador_canonico'):
        print(f"{f['i']:26s} {f['n']:5d}  {f['e']:26s} {f['t'][:60]}")
    return 0

def cmd_fundamento(a):
    con = db.conectar(solo_lectura=True)
    r = fundamento.localizar(con, a.frase, a.obra)
    codigo = 0 if r.estado == fundamento.LOCALIZADO else 2
    if a.json:
        print(json.dumps({'estado': r.estado, 'frase': r.frase, 'fundamento': r.fundamento, 'motivo': r.motivo, 'candidatos': [c.__dict__ for c in r.candidatos]}, ensure_ascii=False, indent=2))
        return codigo
    print(f'[{r.estado}]')
    if r.estado == fundamento.LOCALIZADO:
        c = r.candidatos[0]
        print(f'  fundamento : {r.fundamento}')
        print(f'  precepto   : {c.etiqueta}')
        print(f'  obra       : {c.obra}')
        print(f'  paginas    : {c.pagina_inicio}-{c.pagina_fin}')
        return 0
    if r.motivo:
        print(f'  {r.motivo}')
    for c in r.candidatos:
        print(f'  {c.identificador}::{c.ruta}   p.{c.pagina_inicio}   {c.etiqueta}')
    return codigo

def cmd_hechos(a):
    from . import hechos
    try:
        pregunta, explicitos, respuestas = (a.pregunta, a.hecho, a.respuesta)
        if getattr(a, 'entrada_json', False):
            if a.pregunta != '-' or a.hecho or a.respuesta:
                raise hechos.ErrorDeHechos('--entrada-json requiere pregunta - y no admite --hecho ni --respuesta')
            try:
                entrada = json.loads(sys.stdin.read())
            except ValueError as e:
                raise hechos.ErrorDeHechos(f'entrada JSON no válida: {e}') from e
            if not isinstance(entrada, dict) or set(entrada) - {'pregunta', 'hechos', 'respuestas'}:
                raise hechos.ErrorDeHechos('la entrada debe ser un objeto con pregunta, hechos y respuestas')
            pregunta = entrada.get('pregunta')
            explicitos, respuestas = (entrada.get('hechos', {}), entrada.get('respuestas', {}))
            for campo, valor in (('hechos', explicitos), ('respuestas', respuestas)):
                if not isinstance(valor, dict):
                    raise hechos.ErrorDeHechos(f'{campo} debe ser un objeto de valores JSON')
        exp = hechos.expediente(pregunta, explicitos, respuestas=respuestas, ruta=a.diccionario, ensayo=a.ensayo)
        print(hechos.volcar(exp))
        return 0
    except (hechos.ErrorDeHechos, interruptores.ErrorDeControles) as e:
        print(json.dumps({'estado': 'no_comprobado', 'motivo': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

def main(argv=None):
    _salida_utf8()
    try:
        return _main(argv)
    except (interruptores.ErrorDeControles, calidad_textual.ErrorDeCalidad) as e:
        print(_mensaje_tabla_rota(e), file=sys.stderr)
        return 2

def _main(argv=None):
    p = argparse.ArgumentParser('ict155', description='Base de conocimiento normativo ICT155')
    sub = p.add_subparsers(dest='cmd', required=True)
    argumentos = list(sys.argv[1:] if argv is None else argv)
    if argumentos and argumentos[0] == 'hechos' or interruptores.modo('entrada_hechos') != 'apagado':
        q = sub.add_parser('hechos', help='SUGERENCIA SIN COMPROBAR; confirmar antes de evaluar B2/B3')
        q.add_argument('pregunta')
        q.add_argument('--entrada-json', action='store_true', help=argparse.SUPPRESS)
        q.add_argument('--hecho', action='append', default=[], metavar='ID=VALOR')
        q.add_argument('--respuesta', action='append', default=[], metavar='UNIDAD.ID=VALOR', help='respuesta explícita; admite corregir la sugerencia; conserve las anteriores')
        q.add_argument('--diccionario', default=None, metavar='RUTA', help='diccionario DH v3 y tablas compañeras')
        q.add_argument('--ensayo', action='store_true', help='ensayo explícito aunque entrada_hechos esté apagado; no cambia controles')
        q.set_defaults(func=cmd_hechos)
    q = sub.add_parser('reconstruir', help='reconstruye la base desde la biblioteca')
    q.add_argument('--silencioso', action='store_true')
    q.set_defaults(func=cmd_reconstruir)
    q = sub.add_parser('cita', help='devuelve un precepto y su procedencia')
    q.add_argument('identificador', help='p.ej. BOE-A-2020-2573::anexo.XI/ap.1')
    q.add_argument('--ambito', action='append', default=[], help='ambitos de confidencialidad')
    q.add_argument('--localizar', action='store_true', help='para obras de regimen restringido: dice DONDE esta la clausula (fichero y pagina) sin reproducir su texto')
    q.add_argument('--contexto', action='store_true', help='detras del texto, el contexto obligatorio: ambito de la norma, definiciones de los terminos que usa el precepto, su padre y sus remisiones')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_cita)
    q = sub.add_parser('revisar', help='revisa un borrador contra la base: identificadores, literales (enteros, con su condicion), paginas, rutas poco fiables y normas que la base no tiene. Sale con 1 si hay algun ERROR')
    q.add_argument('fuente', help='fichero con el borrador (UTF-8), o - para leerlo de la entrada estandar')
    q.add_argument('--ambito', action='append', default=[], help='ambitos de confidencialidad')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_revisar)
    q = sub.add_parser('verificar-entrega', help='verifica la respuesta que se va a entregar: su linea de sello tiene que ser la que da `revisar` para ese texto (con su codigo), sin errores ni afirmaciones sin comprobar. Sale con 1 si no es valida')
    q.add_argument('fuente', help='fichero con la respuesta (UTF-8), o - para leerla de la entrada estandar')
    q.add_argument('--pregunta-fichero', default=None, metavar='RUTA', help='fichero con la pregunta de Responsable, tal cual (UTF-8): ademas comprueba que la respuesta cita lo obligatorio del tema de la pregunta (INCOMPLETA si falta). Sin ella no se comprueba y se dice')
    q.add_argument('--entrada-json', action='store_true', help='la entrada (fichero o -) es un objeto {"respuesta": "...", "pregunta": "..."} en vez del texto suelto (lo usa la extension de Cowork)')
    q.add_argument('--revision-independiente', action='store_true', help='ademas, una segunda lectura de la interpretacion con `claude -p`, sin el contexto de la conversacion: cada objecion con pruebas verificables hace la entrega NO VALIDA, y si la revision no se puede hacer tambien (falla cerrado). Tarda decenas de segundos')
    q.add_argument('--pasadas', type=_entero_positivo, default=None, metavar='N', help='con --revision-independiente: cuantas revisiones independientes, a la vez y cada una una llamada distinta al modelo (por defecto 1); vale la union de sus objeciones y, si una pasada falla, la revision falla cerrado')
    q.add_argument('--sin-cache-revision', action='store_true', help='con --revision-independiente: ni lee ni escribe la cache de la revision')
    q.add_argument('--ambito', action='append', default=[], help='ambitos de confidencialidad')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_verificar_entrega)
    q = sub.add_parser('obligatorios', help='lo que no puede faltar en la respuesta a una pregunta: los temas de cowork/temas_obligatorios.json que casan con ella y los preceptos que hay que citar de cada uno (y por que). Solo lee; no abre la base')
    q.add_argument('fuente', help='fichero con la pregunta de Responsable, tal cual (UTF-8), o - para leerla de la entrada estandar')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_obligatorios)
    q = sub.add_parser('verificar-entregas', help='verifica como entrega cada .md de una carpeta: una fila por fichero (fichero, veredicto, motivo) y un recuento. Solo lee. Sale con 1 si alguna es NO VALIDA')
    q.add_argument('carpeta', help='carpeta con las respuestas (.md, UTF-8)')
    q.add_argument('--preguntas', default=None, metavar='FICHERO.json', help='JSON {"Q1.md": "la pregunta", ...}: cada respuesta se verifica con su pregunta (INCOMPLETA si falta lo obligatorio de su tema) y la salida lleva la columna Completa; un fichero que no este en el JSON se verifica sin pregunta y se dice')
    q.add_argument('--revision-independiente', action='store_true', help='ademas, la segunda lectura de la interpretacion de cada respuesta (`claude -p`; decenas de segundos por fichero, una a una): las objeciones con pruebas verificables y las revisiones que no se pudieron hacer hacen NO VALIDA la entrega')
    q.add_argument('--pasadas', type=_entero_positivo, default=None, metavar='N', help='con --revision-independiente: cuantas revisiones independientes de cada respuesta, a la vez y cada una una llamada distinta al modelo (por defecto 1)')
    q.add_argument('--sin-cache-revision', action='store_true', help='con --revision-independiente: ni lee ni escribe la cache de la revision')
    q.add_argument('--ambito', action='append', default=[], help='ambitos de confidencialidad')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_verificar_entregas)
    q = sub.add_parser('brechas', help='sigue las brechas de una auditoria: verifica sus citas (y literales y vigencia) contra la base y muestra la ultima revision de cada una. Sale con 1 si alguna cita tiene ERROR y con 2 si el registro esta mal formado')
    q.add_argument('registro', help='registro de brechas (JSON UTF-8; vive fuera del repositorio)')
    q.add_argument('--salida', default=None, help='escribe el informe Markdown en este fichero en vez de en pantalla')
    q.add_argument('--ambito', action='append', default=[], help='ambitos de confidencialidad')
    q.add_argument('--informe-fase2', action='store_true', help='compone el informe de seguimiento de la Fase 2 (R27-S10) en vez del informe de siempre: solo con datos del registro y literales de la base, nada de LLM')
    q.add_argument('--tipo', choices=('borrador', 'intermedio', 'final', 'partida'), default='intermedio', help='con --informe-fase2: tipo de informe (por defecto intermedio; «partida» es el informe de arranque de la Fase 2, sin revisiones todavía)')
    q.add_argument('--corte', default=None, metavar='AAAA-MM-DD', help='con --informe-fase2: fecha de corte que sale en la cabecera (obligatoria para intermedio/final, del propio argumento o de «fecha_corte» del registro)')
    q.add_argument('--fecha-emision', dest='fecha_emision', default=None, metavar='AAAA-MM-DD', help='con --informe-fase2: fecha de emisión (por defecto, hoy); se le pasa igual a --para-responsable para que la marca de G-7 (emisión anterior al corte) salga en los dos')
    q.add_argument('--para-responsable', action='store_true', help='con --informe-fase2: compone el informe aparte para Responsable (marcas «pendiente_responsable» y recortes del punto 8), nunca el informe para el cliente')
    q.set_defaults(func=cmd_brechas)
    q = sub.add_parser('cotejar', help='dice si una afirmacion se sostiene en un precepto, SIN reproducir su texto')
    q.add_argument('identificador', help='p.ej. EN 12830:2018::ap.5.3.4')
    q.add_argument('afirmacion', help='lo que el informe afirma de esa clausula')
    q.add_argument('--ambito', action='append', default=[])
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_cotejar)
    q = sub.add_parser('buscar', help='busqueda de texto completo. Lo que se escribe es TEXTO, no una expresion de FTS5: se busca como frase literal, con su puntuacion')
    q.add_argument('consulta', help='p.ej. "2026/339", "EN 12830:2018"')
    q.add_argument('--limite', type=_entero_positivo, default=10)
    q.add_argument('--ambito', action='append', default=[])
    q.add_argument('--json', action='store_true')
    q.add_argument('--con-obras', action='store_true', help='con --json, la salida es {"obras": [...], "resultados": [...]}: delante, las obras de la base que se llaman como el texto buscado (sin la opcion, solo la lista de resultados)')
    q.set_defaults(func=cmd_buscar)
    q = sub.add_parser('fundamento', help='la ruta del precepto que contiene una frase literal')
    q.add_argument('frase')
    q.add_argument('--obra', default=None, help='restringe a una obra: identificador, alias o parte del titulo')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_fundamento)
    q = sub.add_parser('vigencia', help='vigencia de las normas (derogadas, modificadas despues de la version de la base), de la consulta guardada al BOE y a la UE')
    q.add_argument('obra', nargs='?', default=None, help='una obra (identificador o alias); sin ella, todas')
    q.add_argument('--actualizar', action='store_true', help='pregunta al BOE y a la UE (red) y rehace la consulta guardada junto a la base')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_vigencia)
    q = sub.add_parser('historial-boe', help='historial de redacciones de cada precepto de las normas del BOE de la base (que norma dio la redaccion vigente y las anteriores), de la consulta guardada al BOE')
    q.add_argument('--actualizar', action='store_true', help='pregunta al BOE (red; una peticion por norma) y rehace la consulta guardada junto a la base (o en --salida)')
    q.add_argument('--salida', default=None, metavar='RUTA', help='el fichero de la consulta guardada, en vez del de junto a la base: con --actualizar se escribe ahi; sin el, se lee de ahi')
    q.add_argument('--obra', default=None, help='una norma (identificador o alias): su resumen y los bloques del BOE sin ruta en la base')
    q.add_argument('--ruta', default=None, help='con --obra: las redacciones de un precepto, p. ej. anexo.III/ap.4')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_historial_boe)
    q = sub.add_parser('cotejo', help='el texto oficial (BOE, EUR-Lex o el propio PDF) con que `revisar` coteja cada literal: instantaneas, testigo de un precepto y medicion de la base frente a su testigo')
    q.add_argument('--actualizar', action='store_true', help='pregunta al BOE y a CELLAR (red) y rehace las dos instantaneas junto a la base (o en --salida)')
    q.add_argument('--salida', default=None, metavar='CARPETA', help='la carpeta de las instantaneas, en vez de la de junto a la base: con --actualizar se escriben ahi; sin el, se leen de ahi')
    q.add_argument('--obra', default=None, help='una obra (identificador o alias): con --ruta, el testigo de un precepto')
    q.add_argument('--ruta', default=None, help='con --obra: p. ej. art.14 o anexo.III/ap.4')
    q.add_argument('--medir', action='store_true', help='que porcentaje de una muestra de frases de la base esta en su testigo, por familia (BOE, UE, PDF)')
    q.add_argument('--muestra', type=_entero_positivo, default=300, help='con --medir: frases por familia (por defecto 300)')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_cotejo)
    q = sub.add_parser('comprobar-carpeta', help='comprueba la carpeta de una tanda de correos antes de enviarla: cada fichero de preguntas.json verificado con su instruccion, la version para enviar (ENVIAR_*.txt) solo pierde identificadores y marcas, y la tanda archivada. Solo lee. Sale con 0 si esta LISTO PARA ENVIAR, con 1 si no y con 2 si la carpeta no se puede leer')
    q.add_argument('carpeta', help='la carpeta de la tanda (con su preguntas.json)')
    q.add_argument('--archivada-en', default=None, metavar='DIR', help='la carpeta del archivo con la que comparar byte a byte (por defecto, archivo_entregas\\<nombre de la carpeta> si existe)')
    q.add_argument('--momento', choices=('antes', 'despues'), default='antes', help='antes o despues del envio: una tanda no archivada (o distinta del archivo) es AVISO antes y NO LISTO despues')
    q.add_argument('--revision-independiente', action='store_true', help='ademas, la revision independiente de la interpretacion de cada correo (`claude -p`; R23/R25): cada objecion con pruebas verificables y cada revision que no se pudo hacer son un problema (NO LISTO). Todas las llamadas de la tanda van a la vez; tarda de 1 a 5 minutos')
    q.add_argument('--pasadas', type=_entero_positivo, default=None, metavar='N', help='con --revision-independiente: cuantas revisiones independientes por correo, cada una una llamada distinta al modelo (por defecto 2)')
    q.add_argument('--json', action='store_true')
    q.set_defaults(func=cmd_comprobar_carpeta)
    sub.add_parser('info', help='estado de la base').set_defaults(func=cmd_info)
    sub.add_parser('obras', help='lista de obras ingeridas').set_defaults(func=cmd_obras)
    a = p.parse_args(argv)
    if not getattr(a, 'ambito', None):
        a.ambito = ['publico']
    return a.func(a)
if __name__ == '__main__':
    raise SystemExit(main())
