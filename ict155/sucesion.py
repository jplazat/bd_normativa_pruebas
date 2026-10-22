"""Public CI documentation."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from . import almacen, config, consulta, interruptores
RUTA_TABLA = config.REPO / 'cowork' / 'sucesores_revisados.json'
EQUIVALENCIAS = ('total', 'parcial')
LARGO_MINIMO_NOTA, LARGO_MAXIMO_NOTA = (10, 330)
SIN_ENTRADA = 'no consta en la tabla revisada de sucesión de preceptos (eso no prueba que su contenido no siga en otro sitio: si la norma que la deroga está en la base, léela)'
NOTA_DE_APARTADOS = '(El precepto citado no tiene entrada propia en la tabla: se enseñan las de sus apartados, cada una válida solo para el suyo.)'
_CACHE: dict = {}

class ErrorDeTabla(RuntimeError):
    """Public CI documentation."""

def _mal(ruta: Path, error: str) -> list[dict]:
    """Public CI documentation."""
    modo = interruptores.modo('relacionados_cierra')
    if modo == 'bloquea':
        raise ErrorDeTabla(f'{ruta} falta o está roto ({error}): no se puede calcular la sucesión de preceptos derogados')
    if modo == 'sombra':
        interruptores.anotar_sombra('relacionados_cierra', {'fichero': str(ruta), 'error': error})
    return []

def _procesar(datos) -> list[dict]:
    return [p for p in datos.get('sucesiones') or [] if isinstance(p, dict) and isinstance(p.get('origen'), str) and p.get('origen') and isinstance(p.get('sucesor'), str) and p.get('sucesor')]

def _forma_obra_ruta(valor: str) -> bool:
    """Public CI documentation."""
    obra, separador, resto = valor.partition('::')
    return bool(separador) and bool(obra.strip()) and bool(resto.strip())

def _forma_mal(datos) -> str | None:
    """Public CI documentation."""
    if not isinstance(datos, dict):
        return 'la raíz no es un objeto'
    pares = datos.get('sucesiones')
    if not isinstance(pares, list):
        return '«sucesiones» tiene que ser una lista'
    for i, p in enumerate(pares):
        if not isinstance(p, dict):
            return f'sucesiones[{i}] no es un objeto'
        for campo in ('origen', 'sucesor'):
            valor = p.get(campo)
            if not (isinstance(valor, str) and valor.strip()):
                return f'sucesiones[{i}]: falta «{campo}» (un texto no vacío)'
            if not _forma_obra_ruta(valor):
                return f'sucesiones[{i}]: «{campo}» no tiene forma obra::ruta ({valor!r})'
        if p.get('equivalencia') not in EQUIVALENCIAS:
            return f"sucesiones[{i}]: «equivalencia» tiene que ser «total» o «parcial» ({p.get('equivalencia')!r})"
        if not (isinstance(p.get('nota'), str) and p.get('nota').strip()):
            return f'sucesiones[{i}]: falta «nota» (un texto no vacío)'
    return None

def cargar(ruta=None) -> list[dict]:
    """Public CI documentation."""
    ruta = Path(ruta) if ruta else RUTA_TABLA
    modo = interruptores.modo('relacionados_cierra')
    modo_almacen = almacen.modo_para(ruta)
    try:
        marca = (str(ruta), ruta.stat().st_mtime_ns, modo) if modo_almacen == 'apagado' else None
    except OSError as e:
        return _mal(ruta, str(e.strerror or e))
    if marca is None or marca not in _CACHE:
        try:
            datos = json.loads(almacen.leer(ruta, modo=modo_almacen).decode('utf-8-sig'))
        except (OSError, ValueError) as e:
            return _mal(ruta, str(e))
        if modo == 'bloquea':
            motivo = _forma_mal(datos)
            if motivo:
                return _mal(ruta, motivo)
            try:
                pares = _procesar(datos)
            except (AttributeError, TypeError, KeyError) as e:
                return _mal(ruta, str(e))
        else:
            try:
                pares = _procesar(datos)
            except AttributeError as e:
                return _mal(ruta, str(e))
            except TypeError as e:
                if modo == 'sombra':
                    return _mal(ruta, str(e))
                raise
            if modo == 'sombra':
                motivo = _forma_mal(datos)
                if motivo:
                    interruptores.anotar_sombra('relacionados_cierra', {'fichero': str(ruta), 'error': motivo})
        _CACHE.clear()
        _CACHE[marca] = pares
    return _CACHE[marca]

def _de_los_apartados(pares: list[dict], obra: str, ruta: str) -> list[dict]:
    """Public CI documentation."""
    dentro = (f'{obra}::{ruta}.', f'{obra}::{ruta}/')
    return [dict(p, apartado=p['origen'].partition('::')[2]) for p in pares if p['origen'].startswith(dentro)]

def sucesores_de(obra: str, ruta: str | None, tabla: list[dict] | None=None) -> list[dict]:
    """Public CI documentation."""
    pares = cargar() if tabla is None else tabla
    cita = (ruta or '').strip()
    if not cita:
        return []
    actual = cita
    while actual:
        propios = [p for p in pares if p['origen'] == f'{obra}::{actual}']
        if propios and actual == cita:
            return propios
        if propios:
            return propios + _de_los_apartados(pares, obra, cita)
        actual = consulta.ruta_padre(actual) or ''
    return _de_los_apartados(pares, obra, cita)

def obras_de_origen(tabla: list[dict] | None=None) -> set[str]:
    """Public CI documentation."""
    return {p['origen'].partition('::')[0] for p in (cargar() if tabla is None else tabla)}

def lineas(sucesores: list[dict]) -> list[str]:
    """Public CI documentation."""
    if not sucesores:
        return [f'  Contenido equivalente vigente: {SIN_ENTRADA}.']
    cabecera = ['  Contenido equivalente vigente:']
    if any((p.get('apartado') for p in sucesores)):
        cabecera.append(f'    {NOTA_DE_APARTADOS}')
    return cabecera + [f"    - {('[apartado ' + p['apartado'] + '] ' if p.get('apartado') else '')}{p['sucesor']} ({p.get('equivalencia') or '?'}): {p.get('nota') or ''}".rstrip() for p in sucesores]

def frase(sucesores: list[dict]) -> str:
    """Public CI documentation."""
    vistos = dict.fromkeys((f"{p['sucesor']} ({p.get('equivalencia') or '?'}" + (f", solo del apartado {p['apartado']}" if p.get('apartado') else '') + ')' for p in sucesores))
    return ', '.join(vistos)

def validar(tabla: list[dict], con: sqlite3.Connection, datos_vigencia: dict | None) -> list[str]:
    """Public CI documentation."""
    problemas: list[str] = []
    vistos: set[tuple[str, str]] = set()
    estados = {k: (o.get('consulta') or {}).get('estado') for k, o in ((datos_vigencia or {}).get('obras') or {}).items()}
    for p in tabla:
        o, s = (p.get('origen') or '', p.get('sucesor') or '')
        if (o, s) in vistos:
            problemas.append(f'par repetido: {o} -> {s}')
        vistos.add((o, s))
        if p.get('equivalencia') not in EQUIVALENCIAS:
            problemas.append(f"{o} -> {s}: equivalencia {p.get('equivalencia')!r} (total o parcial)")
        nota = p.get('nota') or ''
        if not LARGO_MINIMO_NOTA <= len(nota) <= LARGO_MAXIMO_NOTA:
            problemas.append(f'{o} -> {s}: la nota mide {len(nota)} caracteres')
        for lado, ident in (('origen', o), ('sucesor', s)):
            if '::' not in ident:
                problemas.append(f'{o} -> {s}: el {lado} no es obra::ruta')
                continue
            r = consulta.resolver(con, ident)
            if r.estado != consulta.ENCONTRADO:
                problemas.append(f'{o} -> {s}: el {lado} {ident} no resuelve ({r.estado})')
            elif r.obra != ident.partition('::')[0]:
                problemas.append(f'{o} -> {s}: el {lado} resuelve a otra obra ({r.obra})')
        if datos_vigencia is not None:
            if estados.get(o.partition('::')[0]) != 'derogada':
                problemas.append(f'{o}: su obra no consta derogada en la consulta de vigencia')
            if estados.get(s.partition('::')[0]) not in (None, 'vigente'):
                problemas.append(f"{s}: la obra sucesora no consta vigente ({estados.get(s.partition('::')[0])})")
        if o.partition('::')[0] == s.partition('::')[0]:
            problemas.append(f'{o} -> {s}: origen y sucesor son de la misma obra')
    return problemas
