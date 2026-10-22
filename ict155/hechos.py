"""Public CI documentation."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property, lru_cache
import hashlib
import itertools
import os
from pathlib import Path
import re
import unicodedata
from . import _hechos_b2 as b2, _hechos_b3 as b3, _captura_hechos, config, interruptores
DIRECTORIO = config.REPO / 'datos' / 'hechos'
CAMPOS_TRIPLE = ('medir', 'registrar', 'anexo_XI')

class ErrorDeHechos(ValueError):
    """Public CI documentation."""

def normalizar(texto):
    return ' '.join(''.join((c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')).casefold().split())

def _normalizar_mapa(texto):
    chars, indices = ([], [])
    for i, c in enumerate(texto):
        for char in unicodedata.normalize('NFD', c).casefold():
            if unicodedata.category(char) == 'Mn':
                continue
            char = ' ' if char.isspace() else char
            if char == ' ' and (not chars or chars[-1] == ' '):
                continue
            chars.append(char)
            indices.append(i)
    return (''.join(chars).rstrip(), indices)

def _leer(ruta):
    try:
        return b2.cargar_json(Path(ruta).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as e:
        raise ErrorDeHechos(f'No se pueden cargar los hechos: {ruta}: {e}') from e

@dataclass
class Datos:
    diccionario: dict
    orden: dict
    arboles: dict
    matriz_b3: dict
    reglas_b3: list
    matriz_b2: dict
    gramatica: dict
    huellas: dict

    @cached_property
    def hechos(self):
        return {h['id']: h for h in self.diccionario['hechos']}

    @cached_property
    def por_nombre(self):
        out = {}
        for h in self.diccionario['hechos']:
            for nombre in {h['id']} | {o.get('nombre') for o in h['origenes']}:
                out.setdefault(nombre, []).append(h)
        return out

    @cached_property
    def plantillas(self):
        return [(campo, normalizar(forma.split('{}')[0]), '{}' in forma) for campo, formas in _plantillas(self).items() for forma in formas]

    @cached_property
    def campos_b2(self):
        campos = set()
        for r in self.matriz_b2['reglas']:
            for e in r['entradas'] + b2.declaracion_validez(r)['entradas_validez']:
                campos.add(e['campo'])
                if e['tipo'] == 'documento':
                    campos.update((e['campo'] + '.' + k for k in e['estructura']))
        return campos

    @cached_property
    def tablas_b3(self):
        tablas = {}
        for a in self.arboles['arboles']:
            keys = tuple(a['dominios'])
            domains = tuple((tuple(a['dominios'][k]) for k in keys))
            rows = tuple(itertools.product(*domains))
            labels = tuple((tuple(_plan_arbol(a['arbol'], dict(zip(keys, row)))['resultado_documental']) for row in rows))
            tablas[a['id']] = (keys, domains, rows, labels)
        return tablas

    @cached_property
    def planes_b3(self):
        return {}

def cargar(ruta=None):
    """Public CI documentation."""
    p = Path(ruta or os.environ.get('ICT155_HECHOS_DICCIONARIO') or DIRECTORIO / 'diccionario_hechos_v7_corr.json')
    if p.is_dir():
        p /= next((n for n in ('diccionario_hechos_v7_corr.json', 'diccionario_hechos_v7.json', 'diccionario_hechos_v6.json', 'diccionario_hechos_v5.json', 'diccionario_hechos_v4.json') if (p / n).exists()), 'diccionario_hechos_v3.json')
    generacion = {'diccionario_hechos_v7_corr.json': 8, 'diccionario_hechos_v7.json': 7, 'diccionario_hechos_v6.json': 6, 'diccionario_hechos_v5.json': 5, 'diccionario_hechos_v4.json': 4}.get(p.name, 3)
    nombres = (f'orden_preguntas_v{generacion}.json', f'arboles_B3_v{generacion}.json', 'matriz_aplicabilidad_anexoXI_v3.json', 'reglas_M3_v3_3_jdap1.json', {8: 'contratos_B2_v14_corr.json', 7: 'contratos_B2_v14.json', 6: 'contratos_B2_v13.json', 5: 'contratos_B2_v12.json', 4: 'contratos_B2_v11.json'}[generacion], 'gramatica_explicita.json') if generacion >= 4 else ('orden_preguntas_v3.json', 'arboles_B3_v3.json', 'matriz_aplicabilidad_anexoXI_v2.json', 'reglas_M3_v2.json', 'contratos_B2_v10.json', 'gramatica_explicita.json')
    if generacion == 8:
        nombres = ('orden_preguntas_v7_corr.json', 'arboles_B3_v7_corr.json', 'matriz_aplicabilidad_anexoXI_v3.json', 'reglas_M3_v3_3_jdap1.json', 'contratos_B2_v14_corr.json', 'gramatica_explicita.json')
    paths = [p] + [p.parent / n for n in nombres]
    d, o, a, m3, r3, m2, g = [_leer(x) for x in paths]
    try:
        version_dh, version_b2 = {8: ('7.0_corr', '14.0.0_corr'), 7: ('7.0', '14.0.0'), 6: ('6.0', '13.0.0'), 5: ('5.0', '12.0.0'), 4: ('4.0', '11.0.0'), 3: ('3.0', '10.0.0')}[generacion]
        if any((x['version'] != version_dh for x in (d, o, a))):
            raise ErrorDeHechos('Versiones DH discordantes')
        if m2['version'] != version_b2:
            raise ErrorDeHechos('Version de contratos B2 discordante')
        ids = [h['id'] for h in d['hechos']]
        if len(ids) != len(set(ids)) or not ids:
            raise ErrorDeHechos('Diccionario sin hechos o con IDs repetidos')
        for key, records in (('árboles', a['arboles']), ('celdas', m3['celdas']), ('reglas B3', r3['reglas']), ('reglas B2', m2['reglas'])):
            names = [r['id'] for r in records]
            if len(names) != len(set(names)) or not names:
                raise ErrorDeHechos(f'{key}: IDs repetidos o lista vacía')
        for h in d['hechos']:
            h['tipo_valor']
            h['pregunta_neutra']
        if {r['id'] for r in a['arboles']} != {r['id'] for r in m3['celdas']}:
            raise ErrorDeHechos('Árboles y celdas B3 discordantes')
        (g['PATRONES'], g['ALIAS'], o['planes_B2'])
    except (KeyError, TypeError) as e:
        raise ErrorDeHechos(f'Contrato de hechos incompleto: {e}') from e
    return Datos(d, o, a, m3, r3['reglas'], m2, g, {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in paths})

def _igual(a, b):
    return type(a) is type(b) and a == b

def _validar(v, schema):
    if 'enum' in schema and (not any((_igual(v, x) for x in schema['enum']))):
        return False
    t = schema.get('type')
    if t == 'boolean':
        return type(v) is bool
    if t == 'integer':
        return type(v) is int
    if t == 'number':
        return type(v) in (int, Decimal) and (not isinstance(v, Decimal) or v.is_finite())
    if t == 'string':
        if not isinstance(v, str) or len(v.strip()) < schema.get('minLength', 0):
            return False
        if 'pattern' in schema and (not re.fullmatch(schema['pattern'], v)):
            return False
        if schema.get('format') == 'date':
            try:
                b2.fecha(v)
            except b2.Insuficiente:
                return False
        if schema.get('format') == 'date-time':
            try:
                b2.instante(v)
            except b2.Insuficiente:
                return False
    if t == 'array':
        return isinstance(v, list) and all((_validar(x, schema.get('items', {})) for x in v))
    return True

def _mapa(datos, campo, lector=None):
    """Public CI documentation."""
    candidatos = []
    for h in datos.por_nombre.get(campo, []):
        if any((o.get('nombre') == campo and (lector is None or o.get('lector') == lector or (lector.startswith('B3-') and o.get('lector', '').startswith(lector + '/'))) for o in h['origenes'])):
            candidatos.append(h['id'])
    if len(candidatos) == 1:
        return candidatos[0]
    return campo if campo in datos.hechos else None

def _schema(datos, campo):
    ss = []
    for h in datos.por_nombre.get(campo, []):
        ss.append(h['tipo_valor'])
    if campo in datos.gramatica['DOCUMENTOS']:
        return [{'type': 'null'}]
    return ss or [{'type': 'string', 'minLength': 1}]

def _id_valor(datos, campo, valor):
    ident = _mapa(datos, campo)
    if ident:
        return ident
    candidatos = [h['id'] for h in datos.por_nombre.get(campo, []) if 'enum' in h['tipo_valor'] and _validar(valor, h['tipo_valor'])]
    return candidatos[0] if len(candidatos) == 1 else campo

def _valor_identidad(obs):
    if obs['id'] == 'operacion' and obs['campo'] == 'uso' and (obs['valor'] == 'almacen'):
        return 'almacenamiento'
    return obs['valor']

def _valor(texto, campo, datos):
    n = normalizar(texto)
    if campo == 'fecha_verificacion_propuesta' and n == 'ninguna (solo se consulta el vencimiento)':
        return None
    if n in ('no consta', 'desconocido', 'desconocida', 'no se sabe'):
        return None
    if campo in datos.gramatica['DOCUMENTOS']:
        raise ErrorDeHechos('La ausencia documental no lleva valor')
    if campo == 'uso' and n == 'almacenamiento':
        return 'almacen'
    schemas = _schema(datos, campo)
    if any((s.get('type') == 'boolean' for s in schemas)):
        if n in ('si', 'no'):
            return n == 'si'
    enums = [x for s in schemas for x in s.get('enum', [])]
    for x in enums:
        if n in (normalizar(str(x)), normalizar(datos.gramatica['ALIAS'].get(x, str(x)))):
            return x
    if n == 'espana' and campo == 'regimen_metrologico':
        return 'ES'
    if n == 'espana' and campo == 'establecimiento':
        return 'Espana'
    if any((s.get('type') == 'array' for s in schemas)):
        return [x.strip() for x in texto.split('+')]
    if any((s.get('type') in ('integer', 'number') for s in schemas)):
        if re.fullmatch('[-+]?\\d+(?:[.,]\\d+)?', texto.strip()):
            return Decimal(texto.replace(',', '.')) if ',' in texto or '.' in texto else int(texto)
    if any((s.get('type') == 'string' for s in schemas)):
        return texto.strip()
    raise ErrorDeHechos(f'Valor no normalizable para {campo}: {texto!r}')

def _plantillas(datos):
    patrones = dict(datos.gramatica['PATRONES'])
    for doc, etiqueta in datos.gramatica['DOCUMENTOS'].items():
        patrones[doc] = [f'No se aporta el {etiqueta}', f'No se ha aportado el {etiqueta}']
        for sub, nombre in datos.gramatica['SUBCAMPOS'].items():
            patrones[f'{doc}.{sub}'] = [f'En el {etiqueta}, {nombre}: {{}}', f'Respecto al {etiqueta}, {nombre}: {{}}']
    return patrones

def _evidencia(texto, inicio, fin, origen='pregunta'):
    return {'texto': texto[inicio:fin], 'inicio': inicio, 'fin': fin, 'origen': origen}

def _declaracion_libre(clausula):
    """Public CI documentation."""
    n = normalizar(clausula)
    equipo = re.fullmatch('(?:tengo|tenemos|utilizo|utilizamos|el equipo es|mi equipo es) (?:un |una )?(registrador de temperatura|termometro|taximetro)', n)
    if equipo:
        instrumento = equipo.group(1)
        if instrumento == 'taximetro':
            return [('familia', 'taximetro')]
        return [('familia', 'temperatura'), ('tipo_instrumento', 'registrador' if instrumento.startswith('registrador') else 'termometro')]
    operacion = re.fullmatch('(transporto|transportamos|almaceno|almacenamos) (?:alimentos )?(ultracongelados|helados|refrigerados)', n)
    if operacion:
        return [('operacion', 'transporte' if operacion.group(1).startswith('transport') else 'almacenamiento'), ('producto_alimentario', operacion.group(2)[:-1])]
    volumen = re.fullmatch('mi camara de existencias (?:tiene un volumen de|es de) (\\d+(?:[.,]\\d+)?) (?:m³|m3|metros cubicos)', n)
    if volumen:
        return [('almacen', 'camara_existencias'), ('volumen_m3', Decimal(volumen.group(1).replace(',', '.')))]
    return []

def _menciones(pregunta):
    patrones = {'fecha': '\\b\\d{4}-\\d{2}-\\d{2}\\b|\\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\\s+de\\s+\\d{4}\\b|\\b(?:en|desde|antes de)\\s+\\d{4}\\b', 'cantidad': '[−-]?\\d+(?:[.,]\\d+)?\\s*(?:m³|m3|metros cúbicos|gramos|°C|años|meses)\\b', 'instrumento': '\\b(?:registrador(?:es)?(?:\\s+de temperatura)?|termómetro(?:s)?(?: de pincho)?|báscula(?:s)?|taxímetro(?:s)?|contador(?:es)?(?: de agua| de energía eléctrica)?|pasarela(?:s)?)\\b', 'producto': '\\b(?:ultracongelados?|congelados?|refrigerados?|helados?|vacunas|medicamentos)\\b', 'sujeto': '\\b(?:fabricante|reparador|distribuidor|transportista|titular|operador|laboratorio|administrador|taxista|farmacia|comunidad de propietarios)\\b'}
    return [{'tipo': tipo, 'valor_literal': m.group(), 'prueba': _evidencia(pregunta, *m.span()), 'estado': 'soporte_sin_asignacion_a_equipo_uso_evento'} for tipo, patron in patrones.items() for m in re.finditer(patron, pregunta, re.I)]

def _capturar_gramatica(pregunta, datos=None):
    """Public CI documentation."""
    if not isinstance(pregunta, str) or not pregunta.strip():
        raise ErrorDeHechos('La pregunta debe ser texto no vacío')
    datos = datos or cargar()
    observaciones, no_interpretado = ([], [])
    declaraciones_estructuradas = 0
    patrones = _plantillas(datos)
    prefijos = datos.gramatica['INICIOS']
    inicio = 0
    for prefijo in prefijos:
        m = re.match(re.escape(prefijo).replace('\\ ', '\\s+'), pregunta, re.I)
        if m:
            inicio = m.end()
            break
    cuerpo = pregunta[inicio:]
    fin_pregunta = re.search('\\.\\s*¿', cuerpo)
    if fin_pregunta:
        cuerpo = cuerpo[:fin_pregunta.start()]
    pos = inicio
    for parte in cuerpo.split(';'):
        off = pos + len(parte) - len(parte.lstrip())
        clausula = parte.strip().rstrip('.')
        normal, indices = _normalizar_mapa(clausula)
        pos += len(parte) + 1
        encontrados = []
        for campo, fijo, tiene_valor in datos.plantillas:
            if tiene_valor and normal.startswith(fijo + ' '):
                cut = indices[len(fijo)]
                valor = clausula[cut:].strip()
                if valor:
                    encontrados.append((campo, valor, len(fijo)))
            elif not tiene_valor and normal == fijo:
                encontrados.append((campo, None, len(normal)))
        mayor = max((x[2] for x in encontrados), default=0)
        encontrados = list(dict.fromkeys(((k, v) for k, v, n in encontrados if n == mayor)))
        if len(encontrados) == 1:
            declaraciones_estructuradas += 1
            campo, valor = encontrados[0]
            try:
                v = None if valor is None else _valor(valor, campo, datos)
                estado = 'ausente_documental' if valor is None else 'declarado'
                if valor is not None and normalizar(valor) in ('desconocido', 'desconocida', 'no se sabe'):
                    estado = 'desconocido'
                observaciones.append({'campo': campo, 'id': _id_valor(datos, campo, v), 'valor': v, 'estado': estado, 'contexto': campo.split('.')[0] if '.' in campo else 'uso_consultado', 'pruebas': [_evidencia(pregunta, off, off + len(clausula))]})
            except ErrorDeHechos as e:
                no_interpretado.append({'texto': clausula, 'motivo': str(e)})
        elif clausula:
            libres = _declaracion_libre(clausula)
            for campo, v in libres:
                observaciones.append({'campo': campo, 'id': campo, 'valor': v, 'estado': 'declarado', 'contexto': 'uso_consultado', 'pruebas': [_evidencia(pregunta, off, off + len(clausula))]})
            if not libres:
                no_interpretado.append({'texto': clausula, 'motivo': 'sin_declaracion_tipificada_univoca'})
    grupos = {}
    for obs in observaciones:
        grupos.setdefault(obs['campo'], []).append(obs)
    salida = []
    for campo, grupo in grupos.items():
        obs = dict(grupo[0])
        obs['pruebas'] = [p for x in grupo for p in x['pruebas']]
        if any((not _igual(x['valor'], obs['valor']) or x['estado'] != obs['estado'] for x in grupo)):
            obs['valores_capturados'] = [dict(valor=x['valor'], pruebas=x['pruebas']) for x in grupo]
            obs.update(estado='contradictorio', valor=None)
        salida.append(obs)
    por_identidad = {}
    for obs in salida:
        por_identidad.setdefault((obs['id'], obs['contexto']), []).append(obs)
    for grupo in por_identidad.values():
        if any((not _igual(_valor_identidad(o), _valor_identidad(grupo[0])) for o in grupo)):
            for obs in grupo:
                obs.update(estado='contradictorio', valor=None)
    return {'observaciones': salida, 'menciones': _menciones(pregunta), 'no_interpretado': no_interpretado, 'declaraciones_estructuradas': declaraciones_estructuradas, 'unidades': _captura_hechos.capturar_unidades(pregunta)}

def capturar(pregunta, datos=None, hechos=(), respuestas=()):
    from . import _confirmacion_hechos
    datos = datos or cargar()
    captura = _capturar_gramatica(pregunta, datos)
    return _confirmacion_hechos.preparar(pregunta, captura, datos, hechos, respuestas)

def _valores(captura):
    return {o['campo']: o['valor'] for o in captura['observaciones'] if o['estado'] == 'confirmado'}

def _pregunta(datos, campo, lector=None, motivo='falta_hecho'):
    hid = _mapa(datos, campo, lector) or campo
    h = datos.hechos.get(hid, {})
    cv = h.get('captura_v2', {})
    texto = '¿En qué fecha se propone la siguiente verificación? Si solo consulta el vencimiento y no hay actuación propuesta, indíquelo expresamente.' if campo == 'fecha_verificacion_propuesta' else f"¿Qué consta sobre {campo.replace('_', ' ')}?"
    from ._confirmacion_hechos import dominio
    return {'hecho_id': campo, 'hecho_canonico_id': hid, 'campo': campo, 'motivo': motivo, 'respuesta_id': campo, 'valores_admitidos': dominio(datos, campo, lector), 'pregunta': cv.get('pregunta_cliente') or h.get('pregunta_neutra') or texto, 'destinatario': cv.get('destinatario_pregunta_tipificada', 'cliente_con_soporte'), 'pregunta_revision': h.get('pregunta_neutra'), 'documento': h.get('documento_acredita')}

def _resultado_desconocido():
    return dict.fromkeys(CAMPOS_TRIPLE, 'depende')

def _proyeccion_b3(datos, valores, cid):
    h = dict(valores)
    for hecho in datos.diccionario['hechos']:
        if hecho['id'] not in valores:
            continue
        for o in hecho['origenes']:
            if o.get('lector', '').startswith(cid + '/') and o.get('clase') == 'predicado':
                v = valores[hecho['id']]
                h[o['nombre']] = 'almacen' if hecho['id'] == 'operacion' and o['nombre'] == 'uso' and (v == 'almacenamiento') else v
    return h

def _plan_arbol(arbol, valores):
    """Public CI documentation."""
    if arbol['hoja']:
        return arbol
    k = arbol['hecho_id']
    if k in valores and valores[k] is not None:
        v = valores[k]

        def coincide(e):
            esperado = e['representante_prueba']
            if k == 'volumen_m3':
                return type(v) in (int, Decimal) and v > 0 and ((v < 10) == (esperado < 10))
            return _igual(v, esperado)
        opciones = [e for e in arbol['respuestas'] if coincide(e)]
        if len(opciones) != 1:
            return {'hoja': True, 'resultado_documental': ['depende'] * 3, 'invalido': k}
        return _plan_arbol(opciones[0]['siguiente'], valores)
    hijos = [{**e, 'siguiente': _plan_arbol(e['siguiente'], valores)} for e in arbol['respuestas']]
    if all((e['siguiente']['hoja'] and (not e['siguiente'].get('invalido')) for e in hijos)):
        resultados = {tuple(e['siguiente']['resultado_documental']) for e in hijos}
        if len(resultados) == 1:
            return hijos[0]['siguiente']
    return {**arbol, 'respuestas': hijos}

def _plan_finito(keys, domains, rows, labels, conocidos, prioridad):
    """Public CI documentation."""
    indices = tuple((i for i, row in enumerate(rows) if all((_igual(row[keys.index(k)], v) for k, v in conocidos.items()))))
    if not indices:
        return {'hoja': True, 'resultado_documental': ['depende'] * 3, 'invalido': next(iter(conocidos), None)}
    pendientes = tuple((j for j, k in enumerate(keys) if k not in conocidos))

    @lru_cache(None)
    def resolver(indices, pendientes):
        salidas = {labels[i] for i in indices}
        if len(salidas) == 1:
            return (0, 0, {'hoja': True, 'resultado_documental': list(next(iter(salidas)))})
        mejor = None
        for j in pendientes:
            firmas = {}
            for i in indices:
                firma = rows[i][:j] + rows[i][j + 1:]
                firmas.setdefault(firma, set()).add(labels[i])
            if not any((len(s) > 1 for s in firmas.values())):
                continue
            grupos = [tuple((i for i in indices if _igual(rows[i][j], v))) for v in domains[j]]
            hijos = [resolver(g, tuple((x for x in pendientes if x != j))) for g in grupos if g]
            score = (1 + max((h[0] for h in hijos)), len(indices) + sum((h[1] for h in hijos)), prioridad.index(keys[j]) if keys[j] in prioridad else len(prioridad), keys[j])
            if mejor is None or score < mejor[0]:
                mejor = (score, {'hoja': False, 'hecho_id': keys[j]})
        if mejor is None:
            raise ErrorDeHechos('Tabla finita sin pregunta discriminante')
        return (mejor[0][0], mejor[0][1], mejor[1])
    return resolver(indices, pendientes)[2]

def _recondicionar_b3(datos, arbol, canon):
    keys, domains, rows, labels = datos.tablas_b3[arbol['id']]
    conocidos = {}
    for k, dom in zip(keys, domains):
        if k in canon and canon[k] is not None:
            v = canon[k]
            if k == 'volumen_m3' and type(v) in (int, Decimal) and (v > 0):
                v = 1 if v < 10 else 10
            if not any((_igual(v, x) for x in dom)):
                return {'hoja': True, 'resultado_documental': ['depende'] * 3, 'invalido': k}
            conocidos[k] = v
    clave = (arbol['id'], tuple(((k, type(v).__name__, str(v)) for k, v in sorted(conocidos.items()))))
    if clave not in datos.planes_b3:
        datos.planes_b3[clave] = _plan_finito(keys, domains, rows, labels, conocidos, ['producto_alimentario', 'operacion', 'almacen', 'rol_farma', 'etapa_alimentaria', 'regimen_metrologico', 'minorista', 'volumen_m3', 'reparto_local', 'excepcion_autoridad'])
    return datos.planes_b3[clave]

def evaluar_b3(cid, captura, datos=None):
    datos = datos or cargar()
    arbol = next((a for a in datos.arboles['arboles'] if a['id'] == cid), None)
    celda = next((c for c in datos.matriz_b3['celdas'] if c['id'] == cid), None)
    if arbol is None or celda is None:
        raise ErrorDeHechos(f'Celda B3 desconocida: {cid}')
    valores = _valores(captura)
    h = _proyeccion_b3(datos, valores, cid)
    canon = dict(valores)
    for campo, v in h.items():
        hid = _mapa(datos, campo, cid)
        if hid:
            canon[hid] = 'almacenamiento' if hid == 'operacion' and v == 'almacen' else v
    invalidos = []
    for k in arbol['dominios']:
        if k in canon and canon[k] is not None:
            s = datos.hechos[k]['tipo_valor']
            if not _validar(canon[k], s) or (k == 'volumen_m3' and canon[k] <= 0):
                invalidos.append(k)
    conflictos = [o['campo'] for o in captura['observaciones'] if o['estado'] == 'contradictorio' and (_mapa(datos, o['campo'], cid) in arbol['dominios'] or o['campo'] in arbol['dominios'])]
    nodo = _recondicionar_b3(datos, arbol, canon)
    siguiente = None
    if invalidos or conflictos or nodo.get('invalido'):
        k = (invalidos + conflictos + [nodo.get('invalido')])[0]
        siguiente = _pregunta(datos, k, cid, 'corregir_hecho_invalido_o_contradictorio')
    elif not nodo['hoja']:
        siguiente = _pregunta(datos, nodo['hecho_id'], cid)
    detalle = b3.evaluar_detallado(cid, h, datos.reglas_b3)
    resultado = detalle['resultados']
    if siguiente:
        resultado = _resultado_desconocido()
    reglas = detalle['reglas_disparadas'] if not siguiente else []
    preceptos = sorted({a['obra'] + '::' + a['ruta'] for r in datos.reglas_b3 if r['id'] in reglas for a in r['anclas']})
    return {'tipo': 'B3', 'id': cid, 'estado': 'depende' if siguiente or detalle['estado'] == 'sin_rama' else detalle['estado'], 'resultado': resultado, 'reglas_aplicables': reglas, 'siguiente_pregunta': siguiente, 'hechos_faltantes': [siguiente] if siguiente else [], 'preceptos': preceptos, 'via': celda['norma_que_se_evalua'], 'alcance': celda['alcance_respuesta'], 'doctrina_pendiente': arbol['doctrina_pendiente'], 'publicable': False}

def _anidar(valores):
    out = {}
    for campo, valor in valores.items():
        partes = campo.split('.')
        if len(partes) == 1:
            out[campo] = valor
    for campo, valor in valores.items():
        if '.' not in campo:
            continue
        root, key = campo.split('.', 1)
        if root in out and (not isinstance(out[root], dict)):
            raise ErrorDeHechos(f'Documento ausente y descrito a la vez: {root}')
        out.setdefault(root, {})[key] = valor
    return out

def _plan_taxi(datos, regla, plan, valores):
    dominios = plan['dominio_finito_auditoria_v3']
    keys = tuple(dominios)
    domains = tuple((tuple(dominios[k]) for k in keys))
    rows = tuple(itertools.product(*domains))
    labels = tuple(((b2.evaluar(regla, dict(zip(keys, row)))['resultado_punto6'],) for row in rows))
    conocidos = {}
    for k in keys:
        if k not in valores or valores[k] is None:
            continue
        v = valores[k]
        if k == 'motivacion_excepcional':
            if not isinstance(v, str) or not v.strip():
                return {'invalido': k, 'hoja': False, 'hecho_id': k}
            v = domains[keys.index(k)][0 if v == 'no_aportada' else 1]
        elif type(v) is not bool:
            return {'invalido': k, 'hoja': False, 'hecho_id': k}
        conocidos[k] = v
    return _plan_finito(keys, domains, rows, labels, conocidos, list(keys))

def _evaluar_b2_calculo(rid, captura, datos=None):
    datos = datos or cargar()
    from . import _hechos_b2_jdap2, _hechos_b2_jdap3, _hechos_b2_jdap4, _hechos_b2_jdap_corr
    b2 = _hechos_b2_jdap_corr if datos.matriz_b2['version'] == '14.0.0_corr' else _hechos_b2_jdap4 if datos.matriz_b2['version'] == '14.0.0' else _hechos_b2_jdap3 if datos.matriz_b2['version'] == '13.0.0' else _hechos_b2_jdap2 if datos.matriz_b2['version'] == '12.0.0' else globals()['b2']
    regla = next((r for r in datos.matriz_b2['reglas'] + datos.matriz_b2['lectores'] if r['id'] == rid), None)
    if regla is None:
        raise ErrorDeHechos(f'Regla B2 desconocida: {rid}')
    valores = _valores(captura)
    for hecho in datos.diccionario['hechos']:
        if hecho['id'] not in valores:
            continue
        destinos = {o['nombre'] for o in hecho['origenes'] if o.get('lector') == rid}
        if len(destinos) == 1:
            valores.setdefault(next(iter(destinos)), valores[hecho['id']])
    try:
        h = _anidar(valores)
    except ErrorDeHechos as e:
        p = _pregunta(datos, str(e).split(': ')[-1], rid, 'documentacion_contradictoria')
        return {'tipo': 'B2', 'id': rid, 'estado': 'hechos_invalidos', 'resultado': 'depende', 'motivo': str(e), 'siguiente_pregunta': p, 'hechos_faltantes': [p], 'reglas_aplicables': [], 'preceptos': regla['fuentes'], 'publicable': False}
    familia = h.get('familia')
    fase = h.get('fase')
    compatible = familia is None or (isinstance(familia, str) and familia in regla['perfiles_aplicables'])
    if fase is not None and (not _validar(fase, datos.hechos['fase']['tipo_valor'])):
        compatible = False
    if familia is not None and fase is not None:
        compatible = compatible and any((c['instrumento_id'] == familia and c['fase'] == fase and (rid in c['reglas']) for c in datos.matriz_b2['celdas']))
    if not compatible:
        p = _pregunta(datos, 'familia' if familia not in regla['perfiles_aplicables'] else 'fase', rid, 'revisar_ambito_incompatible')
        return {'tipo': 'B2', 'id': rid, 'estado': 'ambito_incompatible', 'resultado': 'depende', 'motivo': 'La familia/fase declarada no corresponde a esta regla', 'siguiente_pregunta': p, 'hechos_faltantes': [p], 'reglas_aplicables': [], 'preceptos': [], 'publicable': False}
    fuentes = regla.get('fundamentos_por_perfil', {}).get(familia, regla['fuentes']) if isinstance(familia, str) else regla['fuentes']
    entradas = regla['entradas'] + b2.declaracion_validez(regla)['entradas_validez']
    general_q3 = None
    if datos.matriz_b2['version'] in ('12.0.0', '13.0.0', '14.0.0', '14.0.0_corr') and rid == 'AG-REGIMEN' and (h.get('fase') == 'verificacion_reparacion_modificacion'):
        try:
            habilitada = b2.salida_evaluada(regla, h).get('autoriza_reparacion') is True
        except (b2.Insuficiente, KeyError, ValueError, TypeError):
            habilitada = False
        if habilitada:
            general_q3 = next((r for r in datos.matriz_b2['reglas'] if r['id'] == 'AG-REPARACION-5'))
            entradas += general_q3['entradas'] + b2.declaracion_validez(general_q3)['entradas_validez']
    faltantes = []
    for entrada in entradas:
        k = entrada['campo']
        if k not in h or (h[k] is None and (not entrada.get('nullable'))):
            faltantes.append(_pregunta(datos, k, rid))
        elif entrada['tipo'] == 'documento' and h[k] is not None:
            for sub in entrada['estructura']:
                if sub not in h[k]:
                    faltantes.append(_pregunta(datos, k + '.' + sub, rid))
    for obs in captura['observaciones']:
        if obs['estado'] == 'contradictorio' and obs['campo'].split('.')[0] in {e['campo'] for e in entradas}:
            faltantes.insert(0, _pregunta(datos, obs['campo'], rid, 'corregir_hecho_contradictorio'))
    plan = next((p for p in datos.orden['planes_B2'] if p['regla_id'] == rid), {})
    orden = [e['campo_B2'] for e in plan.get('orden_condicionado', [])]
    faltantes.sort(key=lambda f: orden.index(f['campo'].split('.')[0]) if f['campo'].split('.')[0] in orden else len(orden))
    resultado, estado, motivo = ('depende', 'depende', None)
    taxi = _plan_taxi(datos, regla, plan, h) if rid == 'TX-K' else None
    if taxi is not None and (not any((p['motivo'].startswith('corregir') for p in faltantes))):
        if taxi.get('invalido'):
            faltantes = [_pregunta(datos, taxi['invalido'], rid, 'corregir_hecho_invalido')]
            estado = 'hechos_invalidos'
        elif taxi['hoja']:
            faltantes = []
            resultado = {'resultado_punto6': taxi['resultado_documental'][0]}
            estado = 'regla_propuesta'
        else:
            faltantes = [_pregunta(datos, taxi['hecho_id'], rid)]
    elif not faltantes:
        try:
            resultado = b2.evaluar_reparacion_q3_jdap2(regla, general_q3, h, h) if general_q3 is not None else b2.salida_evaluada(regla, h)
            estado = 'regla_propuesta'
        except (b2.Insuficiente, KeyError, ValueError, TypeError, ArithmeticError) as e:
            estado, motivo = ('hechos_invalidos', str(e))
            faltantes = [_pregunta(datos, entradas[0]['campo'], rid, 'corregir_contrato: ' + str(e))]
    if rid == 'TX-K' and plan.get('recoger_motivo_excepcional') and (h.get('k_recalculada') is True) and (h.get('motivacion_excepcional') is None) and (not any((p['motivo'].startswith('corregir') for p in faltantes))):
        if not any((p['campo'] == 'motivacion_excepcional' for p in faltantes)):
            faltantes.append(_pregunta(datos, 'motivacion_excepcional', rid, 'soporte_documental_DH_Q8'))
    return {'tipo': 'B2', 'id': rid, 'estado': estado, 'resultado': resultado, 'motivo': motivo, 'siguiente_pregunta': faltantes[0] if faltantes else None, 'hechos_faltantes': faltantes, 'reglas_aplicables': [rid] if not faltantes else [], 'preceptos': fuentes, 'alcance': regla.get('alcance'), 'publicable': False}

def evaluar_b2(rid, captura, datos=None, *, modo_calculo='expediente', calendario=None):
    """Public CI documentation."""
    if modo_calculo not in ('expediente', 'sintetico'):
        raise ErrorDeHechos('Modo de calculo desconocido')
    datos = datos or cargar()
    salida = _evaluar_b2_calculo(rid, captura, datos)
    if datos.matriz_b2['version'] != '14.0.0_corr':
        return salida
    if modo_calculo == 'sintetico':
        return {**salida, 'modo_calculo': 'sintetico_no_vencimiento_real'}
    from ._calendarios_jdap_corr import reservar_fechas
    return reservar_fechas(salida, calendario)

def _pregunta_relacional(campo, texto, unidad):
    return {'hecho_id': campo, 'campo': campo, 'pregunta': texto, 'motivo': 'discriminar_equipo_uso_evento', 'unidad': unidad, 'destinatario': 'cliente_con_soporte'}

def _evaluar_celda_b2(cid, unidad, plan, pregunta, datos):
    celda = next((c for c in datos.matriz_b2['celdas'] if c['id'] == cid))
    obs = [o for o in unidad['observaciones'] if o['estado'] == 'confirmado']
    valores = _valores({'observaciones': obs})
    foco = plan['foco']
    if celda['instrumento_id'] == 'temperatura' and celda['fase'] == 'verificacion_periodica':
        if 'certificado_previo' in valores or 'fecha_certificado_anterior' in valores or valores.get('primera_o_sucesiva') == 'sucesiva':
            foco = 'T-SUCESIVA'
        elif valores.get('primera_o_sucesiva') == 'primera':
            foco = 'T-PRIMERA'
    reglas = [r for r in datos.matriz_b2['reglas'] if r['id'] in celda['reglas']]
    elegidas = [r for r in reglas if foco == 'modulos' and 'modulos' in r['operador'] or r['id'] == foco]
    if len(elegidas) == 1:
        regla = elegidas[0]
        if 'perfil' in {e['campo'] for e in regla['entradas']}:
            fam = next((o for o in obs if o['campo'] == 'familia'))
            obs.append({**fam, 'campo': 'perfil', 'id': 'perfil', 'alias_de': 'familia'})
        e = evaluar_b2(regla['id'], {'observaciones': obs}, datos)
        return {**e, 'celda': cid, 'unidad': unidad['id'], 'fase_consultada': celda['fase'], 'proyeccion': obs}
    familia = celda['instrumento_id']
    if familia == 'temperatura' and celda['fase'] == 'verificacion_periodica':
        campo, texto = ('primera_o_sucesiva', '¿Es la primera verificación periódica o una sucesiva?')
    elif celda['fase'] == 'evaluacion_conformidad':
        campo, texto = ('combinacion', '¿Qué combinación de módulos se propone para la evaluación de conformidad?')
    else:
        campo, texto = ('regla', '¿Qué operación concreta de esta celda quiere examinar?')
    p = _pregunta_relacional(campo, texto, unidad['id'])
    from ._confirmacion_hechos import dominio
    p.update(respuesta_id=unidad['id'] + '.' + campo, valores_admitidos=dominio(datos, campo))
    if campo == 'regla':
        p['valores_admitidos'] = {'enum': celda['reglas']}
    return {'tipo': 'B2', 'id': cid, 'celda': cid, 'unidad': unidad['id'], 'fase_consultada': celda['fase'], 'estado': 'depende', 'resultado': 'depende', 'siguiente_pregunta': p, 'hechos_faltantes': [p], 'reglas_aplicables': [], 'reglas_candidatas': celda['reglas'], 'preceptos': celda.get('fuentes_delante', []), 'aplicabilidad_material': 'pendiente_acreditar_uso_y_ambito', 'publicable': False}

def expediente(pregunta, hechos=(), *, respuestas=(), ruta=None, ensayo=False, datos=None):
    if not isinstance(pregunta, str) or not pregunta.strip():
        raise ErrorDeHechos('La pregunta debe ser texto no vacío')
    modo = interruptores.modo('entrada_hechos')
    base = {'version': 'R28-C4/4', 'pregunta': pregunta, 'modo': modo, 'ensayo': bool(ensayo), 'publicable': False, 'alcance': 'Toda captura es una SUGERENCIA SIN COMPROBAR. Vía documental pendiente de confirmación y cotejo.'}
    if modo == 'apagado' and (not ensayo):
        return {**base, 'estado': 'apagado', 'hechos': [], 'hechos_faltantes': [], 'celdas_reglas': [], 'resultado': 'depende', 'preceptos': [], 'siguiente_pregunta': None, 'camino': {'tipo': 'control_apagado'}}
    datos = datos or cargar(ruta)
    captura = capturar(pregunta, datos, hechos, respuestas)
    from . import _confirmacion_hechos
    return _confirmacion_hechos.expediente(base, captura, datos)

def volcar(exp):
    return b2.volcar_json(exp, ensure_ascii=False, indent=2)

def comprobar_confirmaciones(exp, datos=None):
    """Public CI documentation."""
    from ._confirmacion_hechos import _plan, comprobar_presentacion
    errores = comprobar_presentacion(exp)
    unidades = {u['id']: u for u in exp.get('unidades', [])}
    datos = datos or (cargar() if exp.get('celdas_reglas') else None)
    evaluadas = {(e['tipo'], e.get('celda', e['id']), e.get('unidad')) for e in exp.get('celdas_reglas', [])}
    tipificadas = {(c['tipo'], c['id'], c.get('unidad')) for c in exp.get('celdas_tipificadas', [])}
    if evaluadas != tipificadas:
        errores.append('celdas_sin_evaluacion_confirmada')
    for e in exp.get('celdas_reglas', []):
        seleccion = e.get('seleccion_por', [])
        if not seleccion:
            errores.append('ruta_sin_hecho_confirmado:' + e['id'])
        for o in seleccion + e.get('hechos_en_evaluacion', []) + e.get('proyeccion', []):
            if o['estado'] != 'confirmado':
                errores.append('estado_no_confirmado:' + o['campo'])
            if not any((p.get('origen') in {'respuesta', 'hecho_adicional'} for p in o.get('pruebas', []))):
                errores.append('sin_respuesta_explicita:' + o['campo'])
        u = unidades.get(e.get('unidad'))
        if u is None:
            errores.append('unidad_ausente')
        else:
            valores = _valores(u)
            explicitas = [o for o in seleccion if o['campo'] in {'regla', 'celda'} and o['estado'] == 'confirmado']
            if explicitas:
                if not any((o['valor'] == e['id'] for o in explicitas)):
                    errores.append('ruta_no_confirmada:' + e['id'])
            elif (e['tipo'], e.get('celda', e['id'])) not in _plan(u, datos)['rutas']:
                errores.append('seleccion_no_derivable:' + e['id'])
            for o in e.get('hechos_en_evaluacion', []):
                if o['campo'] not in valores or not _igual(o['valor'], valores[o['campo']]):
                    errores.append('valor_no_acreditado:' + o['campo'])
    return errores
