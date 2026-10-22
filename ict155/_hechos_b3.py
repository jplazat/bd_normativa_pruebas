"""Public CI documentation."""
import math
import operator
from decimal import Decimal

def _numero_finito(v):
    return type(v) is int or (type(v) is float and math.isfinite(v)) or (type(v) is Decimal and v.is_finite())
FIELDS = ('medir', 'registrar', 'anexo_XI')

def unknown():
    return dict.fromkeys(FIELDS, 'depende')

def evaluar_expr(expr, hechos):
    if 'todos' in expr:
        results = [evaluar_expr(e, hechos) for e in expr['todos']]
        return False if False in results else None if None in results else True
    if 'alguno' in expr:
        results = [evaluar_expr(e, hechos) for e in expr['alguno']]
        return True if True in results else None if None in results else False
    if 'no' in expr:
        value = evaluar_expr(expr['no'], hechos)
        return None if value is None else not value
    key, op, expected = (expr['hecho'], expr['operador'], expr['valor'])
    if key not in hechos or hechos[key] is None:
        return None
    value = hechos[key]
    if key == 'volumen_m3' and (not _numero_finito(value) or value <= 0):
        return None
    if op == 'existe':
        return True
    if op in ('eq', 'ne'):
        if type(value) is not type(expected):
            return None
        equal = value == expected
        return equal if op == 'eq' else not equal
    if op == 'in':
        candidates = [x for x in expected if type(x) is type(value)]
        return None if not candidates else value in candidates
    if not _numero_finito(value) or not _numero_finito(expected):
        return None
    return {'lt': operator.lt, 'lte': operator.le, 'gt': operator.gt, 'gte': operator.ge}[op](value, expected)

def evaluar_detallado(cid, hechos, rows):
    if not isinstance(hechos, dict):
        return {'resultados': unknown(), 'reglas_disparadas': [], 'estado': 'hechos_invalidos'}
    active = []
    for row in rows:
        if not any((p['matriz'] == 'B3' and p['celda_id'] == cid and p['componente'].startswith('rama_') for p in row['proyecciones'])):
            continue
        if evaluar_expr(row['condicion'], hechos) is True:
            triple = {k: row['detalle'][k] for k in FIELDS}
            effects = {e['decision']: e['valor'] for e in row['efectos']}
            if triple != {k: effects[k] for k in FIELDS}:
                raise ValueError(row['id'] + ': efecto y detalle discordantes')
            active.append((row['id'], triple))
    if not active:
        triple = unknown()
        state = 'sin_rama'
    elif len(active) > 1:
        triple = dict.fromkeys(FIELDS, 'conflicto')
        state = 'conflicto'
    else:
        triple = active[0][1]
        state = 'rama_propuesta'
    return {'resultados': triple, 'reglas_disparadas': [x[0] for x in active], 'estado': state}

def evaluar_con_reglas(cid, hechos, rows):
    return evaluar_detallado(cid, hechos, rows)['resultados']
