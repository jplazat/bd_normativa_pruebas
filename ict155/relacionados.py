"""Public CI documentation."""
from __future__ import annotations
import json
import re
from pathlib import Path
from . import almacen, config, interruptores
RUTA_TABLA = config.REPO / 'cowork' / 'preceptos_relacionados.json'
_CACHE: dict = {}

class ErrorDeTabla(RuntimeError):
    """Public CI documentation."""

def _mal(ruta: Path, error: str) -> list[dict]:
    """Public CI documentation."""
    modo = interruptores.modo('relacionados_cierra')
    if modo == 'bloquea':
        raise ErrorDeTabla(f'{ruta} falta o está roto ({error}): no se pueden calcular los preceptos relacionados')
    if modo == 'sombra':
        interruptores.anotar_sombra('relacionados_cierra', {'fichero': str(ruta), 'error': error})
    return []

def _procesar(datos) -> list[dict]:
    grupos = []
    for g in datos.get('grupos') or []:
        grupos.append({**g, '_cuando': re.compile(g['disparadores'], re.I), '_contexto': re.compile(g['contexto'], re.I)})
    return grupos

def _forma_mal(datos) -> str | None:
    """Public CI documentation."""
    if not isinstance(datos, dict):
        return 'la raíz no es un objeto'
    grupos = datos.get('grupos')
    if not isinstance(grupos, list):
        return '«grupos» tiene que ser una lista'
    for i, g in enumerate(grupos):
        if not isinstance(g, dict):
            return f'grupos[{i}] no es un objeto'
        for campo in ('nombre', 'disparadores', 'contexto'):
            if not (isinstance(g.get(campo), str) and g.get(campo).strip()):
                return f'grupos[{i}]: falta «{campo}» (un texto no vacío)'
        preceptos = g.get('preceptos')
        if not isinstance(preceptos, list):
            return f'grupos[{i}]: «preceptos» tiene que ser una lista'
        for j, p in enumerate(preceptos):
            if not (isinstance(p, dict) and isinstance(p.get('identificador'), str) and p.get('identificador').strip()):
                return f'grupos[{i}].preceptos[{j}]: falta «identificador» (un texto no vacío)'
            if not (isinstance(p.get('nota'), str) and p.get('nota').strip()):
                return f'grupos[{i}].preceptos[{j}]: falta «nota» (un texto no vacío)'
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
                grupos = _procesar(datos)
            except (KeyError, TypeError, re.error, AttributeError) as e:
                return _mal(ruta, str(e))
        else:
            try:
                grupos = _procesar(datos)
            except (KeyError, TypeError, re.error) as e:
                return _mal(ruta, str(e))
            except AttributeError as e:
                if modo == 'sombra':
                    return _mal(ruta, str(e))
                raise
            if modo == 'sombra':
                motivo = _forma_mal(datos)
                if motivo:
                    interruptores.anotar_sombra('relacionados_cierra', {'fichero': str(ruta), 'error': motivo})
        _CACHE.clear()
        _CACHE[marca] = grupos
    return _CACHE[marca]

def que_grupos_tocan(texto: str, grupos: list[dict] | None=None) -> list[dict]:
    """Public CI documentation."""
    return [g for g in (cargar() if grupos is None else grupos) if g['_cuando'].search(texto) and g['_contexto'].search(texto)]
