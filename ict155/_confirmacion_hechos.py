"""Public CI documentation."""
import copy
import re
EXTRA = {'primera_o_sucesiva': {'enum': ['primera', 'sucesiva']}, 'tipo_agua': {'enum': ['limpia', 'otra']}, 'tipo_pesaje': {'enum': ['no_automatico', 'automatico']}, 'fecha_introduccion_mercado': {'type': 'string', 'format': 'date'}, 'familia_candidata': {'type': 'string', 'minLength': 1}, 'uso_autocontrol': {'type': 'boolean'}, 'actividad_farma': {'enum': ['farmacia', 'otra']}, 'radio_mismo_equipo': {'type': 'boolean'}, 'conexion_internet': {'type': 'boolean'}, 'equipo_uso_evento': {'type': 'string', 'minLength': 1}, 'naturaleza_intervencion': {'type': 'string', 'minLength': 1}, 'actividad_comercial_declarada': {'type': 'string', 'minLength': 1}, 'sujeto_declarado': {'type': 'string', 'minLength': 1}, 'clase_declarada': {'type': 'number'}, 'resolucion_declarada_C': {'type': 'number'}}
PRIORIDAD = ['familia', 'fase', 'operacion', 'producto_alimentario', 'rol_farma', 'actividad_farma', 'uso_autocontrol', 'minorista', 'combinacion']
AVISO = 'SUGERENCIA SIN COMPROBAR'
SUGERENCIA = 'sugerencia_sin_comprobar'
CONFLICTO = 'valores_en_conflicto'
PENDIENTES = {SUGERENCIA, CONFLICTO}

def dominio(datos, campo, lector=None):
    cache = datos.__dict__.setdefault('_dominios_respuesta', {})
    key = (campo, lector)
    if key not in cache:
        cache[key] = _dominio(datos, campo, lector)
    return copy.deepcopy(cache[key])

def _dominio(datos, campo, lector=None):
    """Public CI documentation."""
    from . import hechos as h
    if campo == 'combinacion':
        return {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'enum': ['A', 'A1', 'A2', 'B', 'C', 'C1', 'C2', 'D', 'D1', 'E', 'E1', 'F', 'F1', 'G', 'H', 'H1']}}
    if campo in EXTRA:
        return copy.deepcopy(EXTRA[campo])
    if campo == 'regla':
        return {'enum': sorted({r['id'] for r in datos.matriz_b2['reglas'] + datos.matriz_b2['lectores']})}
    if campo == 'celda':
        return {'enum': [r['id'] for r in datos.arboles['arboles']]}
    schemas = [copy.deepcopy(x['tipo_valor']) for x in datos.por_nombre.get(campo, [])]
    root, _, sub = campo.partition('.')
    tipos = {'fecha': {'type': 'string', 'format': 'date'}, 'instante': {'type': 'string', 'format': 'date-time'}, 'booleano': {'type': 'boolean'}, 'bool': {'type': 'boolean'}, 'numero': {'type': 'number'}, 'entero': {'type': 'integer'}, 'int': {'type': 'integer'}, 'texto': {'type': 'string', 'minLength': 1}, 'modulos': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}, 'lista': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}}
    propios = []
    for r in datos.matriz_b2['reglas'] + datos.matriz_b2['lectores']:
        if lector and r['id'] != lector:
            continue
        for e in r['entradas'] + h.b2.declaracion_validez(r)['entradas_validez']:
            if e['campo'] != root:
                continue
            if sub:
                if e['tipo'] == 'documento' and sub in e['estructura']:
                    s = e['estructura'][sub]
                    if isinstance(s, dict):
                        propios.append(copy.deepcopy(s))
                    elif isinstance(s, list):
                        propios.append({'enum': s})
                    elif isinstance(s, str):
                        propios.append(copy.deepcopy(tipos.get(s, {'type': 'string', 'minLength': 1})))
                continue
            if e['tipo'] == 'documento':
                propios.append({'type': 'object'})
                if e.get('nullable'):
                    propios.append({'type': 'null'})
            else:
                s = copy.deepcopy(tipos.get(e['tipo'], {'type': 'string', 'minLength': 1}))
                if e['tipo'] == 'enum':
                    s = {'enum': e['valores']}
                if e['tipo'] == 'lista' and 'elementos' in e:
                    s['items'] = {'enum': e['elementos']}
                if 'dominio' in e:
                    s = {'enum': e['dominio']}
                propios.append(s)
                if e.get('nullable'):
                    propios.append({'type': 'null'})
    schemas = propios if lector and propios else schemas if campo in {'familia', 'fase'} and schemas else schemas + propios
    if not schemas:
        return {'type': 'string', 'minLength': 1}
    unique = []
    for s in schemas:
        if s not in unique:
            unique.append(s)
    return unique[0] if len(unique) == 1 else {'anyOf': unique}

def _valido(valor, schema):
    from .hechos import _validar
    if 'anyOf' in schema:
        return any((_valido(valor, s) for s in schema['anyOf']))
    if schema.get('type') == 'null':
        return valor is None
    if schema.get('type') == 'object':
        return isinstance(valor, dict)
    if schema.get('type') == 'array':
        return isinstance(valor, list) and len(valor) >= schema.get('minItems', 0) and (not schema.get('uniqueItems') or len({repr(v) for v in valor}) == len(valor)) and all((_valido(v, schema.get('items', {})) for v in valor))
    if valor is None and schema.get('type') is not None:
        return False
    return _validar(valor, schema)

def _enums(schema):
    return schema.get('enum', []) + [v for s in schema.get('anyOf', []) for v in _enums(s)]

def _proponer(obs, pregunta, datos):
    from . import hechos as h
    from ._captura_hechos import frases, menciones_de_campo
    o = copy.deepcopy(obs)
    campo = o['campo']
    valores = menciones_de_campo(pregunta, campo, _enums(dominio(datos, campo)), datos.gramatica['ALIAS'])
    for candidato in o.pop('valores_capturados', []):
        if not any((h._igual(candidato['valor'], m['valor']) for m in valores)):
            valores.append(candidato)
    soporte = [dict(texto=pregunta, inicio=0, fin=len(pregunta), origen='pregunta')]
    if len(pregunta) > 1200:
        pruebas = o['pruebas'] + [p for m in valores for p in m['pruebas']]
        nombres = {h.normalizar(campo.replace('_', ' '))}
        nombres.update((h.normalizar(fijo) for nombre, fijo, _ in datos.plantillas if nombre == campo))
        soporte = [p for p in frases(pregunta) if any((re.search('\\b' + re.escape(n) + '\\b', h.normalizar(p['texto'])) for n in nombres if n)) or any((p['inicio'] < s['fin'] and p['fin'] > s['inicio'] for s in pruebas))]
    o.update(pruebas=soporte, advertencia=AVISO, estado=SUGERENCIA)
    if len(valores) > 1:
        o.update(estado=CONFLICTO, valor=None, valores_mencionados=valores)
    return o

def preparar(pregunta, captura, datos, hechos, respuestas):
    from . import hechos as h
    c = copy.deepcopy(captura)
    for m in c['menciones']:
        m['advertencia'] = AVISO

    def proponer(o):
        return _proponer(o, pregunta, datos)
    c['observaciones'] = [proponer(o) for o in c['observaciones']]
    for u in c['unidades']:
        u['observaciones'] = [proponer(o) for o in u['observaciones']]
        for i in u['intenciones']:
            o = proponer(dict(campo='fase', id='fase', valor=i['valor'], contexto=u['id'], pruebas=[i['prueba']]))
            u['observaciones'].append(o)
            i.update(estado=o['estado'], prueba=o['pruebas'][0])
        if u.get('actividad_farma_pendiente'):
            p = u['prueba']
            u['observaciones'].append(proponer(dict(campo='actividad_farma', id='actividad_farma', valor='farmacia', contexto=u['id'], pruebas=[p])))
        n = h.normalizar(pregunta)
        if re.search('comprueba con termometros de pincho la temperatura.*plan de autocontrol', n):
            u['observaciones'].append(proponer(dict(campo='uso_autocontrol', id='uso_autocontrol', valor=True, contexto=u['id'], pruebas=[dict(texto=pregunta, inicio=0, fin=len(pregunta), origen='pregunta')])))
        for e in u['eventos']:
            contexto = proponer(dict(campo='fecha_evento', valor=e.get('fecha', e.get('fecha_limite')), pruebas=[e['prueba']]))
            e.update(estado=contexto['estado'], advertencia=AVISO, prueba=contexto['pruebas'][0], pruebas=contexto['pruebas'])
        consulta_periodica = any((i['valor'] == 'verificacion_periodica' for i in u['intenciones']))
        verificaciones = [e for e in u['eventos'] if 'verificacion' in e['tipo']] if consulta_periodica else []
        if verificaciones:
            e = verificaciones[-1]
            u['observaciones'].append(proponer(dict(campo='primera_o_sucesiva', id='primera_o_sucesiva', valor='sucesiva', contexto=u['id'], pruebas=[e['prueba']])))
        completas = [e for e in verificaciones if e.get('precision') == 'dia']
        if completas:
            e = completas[-1]
            u['observaciones'].append(proponer(dict(campo='certificado_previo', id='fecha_certificado_anterior', valor=e['fecha'], contexto=u['id'], pruebas=[e['prueba']])))
    if len(c['unidades']) == 1:
        campos = {o['campo'] for o in c['unidades'][0]['observaciones']}
        c['unidades'][0]['observaciones'].extend((o for o in c['observaciones'] if o['campo'] not in campos))
    if not c['unidades']:
        c['unidades'] = [dict(id='unidad_1', nombre='consulta', contexto='uso_consultado', observaciones=copy.deepcopy(c['observaciones']), intenciones=[], eventos=[])]
    for u in c['unidades']:
        u['advertencia'] = AVISO
        for campo in PRIORIDAD:
            if any((o['campo'] == campo for o in u['observaciones'])):
                continue
            valores = h._captura_hechos.menciones_de_campo(pregunta, campo, _enums(dominio(datos, campo)), datos.gramatica['ALIAS'])
            if len(valores) > 1:
                u['observaciones'].append(proponer(dict(campo=campo, id=campo, valor=None, contexto=u['id'], pruebas=[p for m in valores for p in m['pruebas']])))
    c['respuestas_explicitas'] = []
    for fuente, entradas in [('hecho_adicional', hechos), ('respuesta', respuestas)]:
        iterable = [f'{k}={h.b2.volcar_json(v, ensure_ascii=False)}' for k, v in entradas.items()] if isinstance(entradas, dict) else entradas
        for literal in iterable:
            if not isinstance(literal, str) or '=' not in literal:
                raise h.ErrorDeHechos('Cada respuesta debe tener la forma id=valor')
            key, token = literal.split('=', 1)
            key, token = (key.strip(), token.strip())
            uid, sep, campo = key.partition('.')
            if not uid.startswith('unidad_'):
                uid = None
                campo = key
            elif not sep:
                raise h.ErrorDeHechos('Indique unidad_N.hecho_id=valor')
            if uid and uid not in {u['id'] for u in c['unidades']}:
                raise h.ErrorDeHechos(f'Unidad desconocida: {uid}')
            conocidos = set(h._plantillas(datos)) | set(datos.hechos) | datos.campos_b2 | set(EXTRA) | {'celda', 'regla'}
            conocidos |= {o['campo'] for u in c['unidades'] for o in u['observaciones']}
            if campo not in conocidos:
                raise h.ErrorDeHechos(f'Hecho desconocido: {campo}')
            targets = [u for u in c['unidades'] if u['id'] == uid] if uid else c['unidades']
            if not uid and len(targets) > 1 and (campo not in {'celda', 'regla'}):
                raise h.ErrorDeHechos(f'Hay varias unidades; indique unidad_N.{campo}')
            grupo = c['observaciones'] if campo in {'celda', 'regla'} and uid is None else targets[0]['observaciones']
            anterior = next((o for o in grupo if o['campo'] == campo and o['estado'] in PENDIENTES), None)
            try:
                valor = h.b2.cargar_json(token)
            except ValueError:
                valor = token
            if fuente == 'respuesta' and isinstance(valor, str):
                if anterior and anterior['estado'] == CONFLICTO and (h.normalizar(valor) in {'si', 'no'}):
                    raise h.ErrorDeHechos(f'Hay varios valores de {campo}; indique el valor elegido')
                if h.normalizar(valor) == 'si' and anterior:
                    valor = anterior['valor']
                elif h.normalizar(valor) == 'no' and anterior:
                    anterior['estado'] = 'descartado'
                    c['respuestas_explicitas'].append(dict(id=key, valor='no', estado='rechazo_explicito', literal=literal))
                    continue
                elif valor.casefold().startswith('otro:'):
                    valor = valor.split(':', 1)[1].strip()
                    if campo == 'familia' and h.normalizar(valor) in {'humedad', 'vibraciones'}:
                        valor = 'otra'
                elif h.normalizar(valor) in {'si', 'no'} and _valido(True, dominio(datos, campo)):
                    valor = h.normalizar(valor) == 'si'
            if not _valido(valor, dominio(datos, campo)):
                raise h.ErrorDeHechos(f'Valor no admitido para {campo}: {token}')
            obs = dict(campo=campo, id=h._id_valor(datos, campo, valor), valor=valor, estado='confirmado', contexto=uid or (targets[0]['id'] if len(targets) == 1 else 'ruta_explicita'), pruebas=[dict(texto=literal, inicio=0, fin=len(literal), origen=fuente)])
            confirmadas = [o for o in grupo if o['campo'] == campo and o['estado'] in {'confirmado', 'contradictorio'}]
            if any((not h._igual(o['valor'], valor) for o in confirmadas)):
                obs.update(estado='contradictorio', valor=None)
                for o in confirmadas:
                    o.update(estado='contradictorio', valor=None)
            for o in grupo:
                if o['campo'] == campo and o['estado'] in PENDIENTES:
                    o['estado_captura'] = o['estado']
                    o['estado'] = 'sustituido_por_respuesta'
            grupo.append(obs)
            if grupo is not c['observaciones'] and len(c['unidades']) == 1:
                c['observaciones'].append(obs)
            c['respuestas_explicitas'].append(copy.deepcopy(obs))
    for u in c['unidades']:
        for o in u['observaciones']:
            if not o['contexto'].startswith(u['id'] + '/'):
                o['contexto'] = u['id'] + '/' + o['contexto']
        identidades = {}
        for o in u['observaciones']:
            if o['estado'] == 'confirmado':
                rol = o['campo'].split('.')[0] if '.' in o['campo'] else 'uso_consultado'
                identidades.setdefault((o['id'], rol), []).append(o)
        for grupo in identidades.values():
            if any((not h._igual(h._valor_identidad(o), h._valor_identidad(grupo[0])) for o in grupo)):
                for o in grupo:
                    o.update(estado='contradictorio', valor=None)
        v = h._valores(u)
        for campo, valor in [('familia', 'agua_limpia' if v.get('tipo_agua') == 'limpia' else 'pesaje_no_auto' if v.get('tipo_pesaje') == 'no_automatico' else None)]:
            if valor is not None and campo not in v:
                src = next((o for o in u['observaciones'] if o['campo'] in {'tipo_agua', 'tipo_pesaje'} and o['estado'] == 'confirmado'))
                u['observaciones'].append({**src, 'campo': campo, 'id': campo, 'valor': valor, 'alias_de': src['campo']})
    return c

def _preguntar(datos, campo, uid=None, texto=None, obs=None):
    from . import hechos as h
    p = h._pregunta(datos, campo)
    p.update(unidad=uid, respuesta_id=(uid + '.' if uid else '') + campo)
    if texto:
        p['pregunta'] = texto
    if obs:
        p.update(motivo='confirmar_hecho', estado_propuesta=obs['estado'], advertencia=AVISO, pruebas=obs['pruebas'], respuestas_confirmacion=['si', 'no', 'otro: VALOR'])
        nombre = {'familia': 'la familia del equipo', 'fase': 'la fase consultada', 'combinacion': 'la combinación de módulos', 'operacion': 'la operación', 'producto_alimentario': 'el producto'}.get(campo, campo.replace('_', ' '))
        if obs['estado'] == CONFLICTO:
            p.update(valores_mencionados=copy.deepcopy(obs['valores_mencionados']), respuestas_confirmacion=['VALOR', 'otro: VALOR'])
            opciones = '; '.join((f"{m['valor']}: " + ' '.join((s['texto'] for s in m['pruebas'])) for m in obs['valores_mencionados']))
            p['pregunta'] = f'{AVISO}. Aparecen varios valores para {nombre}; no se sugiere ninguno. ¿Cuál es el valor? {opciones}'
        else:
            p['valor_propuesto'] = obs['valor']
            p['pregunta'] = f"{AVISO}. ¿Qué valor confirma para {nombre}? Sugerencia: {obs['valor']}. Sí / No / Otro: VALOR"
    return p

def _confirmaciones(datos, u):
    from .hechos import _valores
    v = _valores(u)
    candidatos = [o for o in u['observaciones'] if o['estado'] in PENDIENTES]
    if v.get('certificado_previo') is not None or v.get('fecha_certificado_anterior') is not None:
        candidatos = [o for o in candidatos if o['campo'] != 'primera_o_sucesiva']
    candidatos.sort(key=lambda o: PRIORIDAD.index(o['campo']) if o['campo'] in PRIORIDAD else len(PRIORIDAD))
    out = []
    vistos = set()
    for o in candidatos:
        if o['campo'] in vistos:
            continue
        vistos.add(o['campo'])
        out.append(_preguntar(datos, o['campo'], u['id'], obs=o))
    return out

def _plan(u, datos):
    """Public CI documentation."""
    from . import hechos as h
    v = h._valores(u)
    seleccion = []
    if 'regla' in v:
        return dict(rutas=[('B2', v['regla'])], foco=None, regla_explicita=True)
    if 'celda' in v:
        return dict(rutas=[('B3', v['celda'])], foco=None, regla_explicita=True)
    if v.get('familia') and v.get('fase'):
        seleccion = [('B2', c['id']) for c in datos.matriz_b2['celdas'] if c['instrumento_id'] == v['familia'] and c['fase'] == v['fase']]
    op = v.get('operacion')
    prod = v.get('producto_alimentario')
    vias = []
    if v.get('rol_farma') in {'distribuidor_medicamentos', 'otro_rol'} or v.get('actividad_farma') == 'farmacia':
        if op == 'almacenamiento' or v.get('actividad_farma') == 'farmacia':
            vias = ['B3-18']
        elif op in {'transporte', 'distribucion'}:
            vias = ['B3-19']
    elif prod == 'ultracongelado' and op == 'transporte':
        vias = ['B3-01', 'B3-02']
    elif prod == 'ultracongelado' and op == 'almacenamiento' and (not u.get('instalacion_pendiente')):
        vias = ['B3-03', 'B3-04']
    elif prod == 'helado' and op in {'almacenamiento', 'transporte'}:
        vias = ['B3-08', 'B3-09'] + (['B3-10'] if op == 'transporte' else ['B3-11'])
    elif prod == 'refrigerado' and v.get('minorista') is True:
        vias = ['B3-16', 'B3-17']
    if v.get('familia') == 'temperatura' and v.get('uso_autocontrol') is True:
        vias += ['B3-21', 'B3-24']
    return dict(rutas=seleccion + [('B3', cid) for cid in vias], foco='modulos' if 'combinacion' in v else 'TX-K' if v.get('familia') == 'taximetro' and v.get('dimensiones_neumaticos_cambiadas') is not None else None)

def _pendiente(u, datos):
    from . import hechos as h
    v = h._valores(u)
    nombre = u['nombre']
    if nombre.startswith('bascula') and 'tipo_pesaje' not in v:
        return _preguntar(datos, 'tipo_pesaje', u['id'])
    if nombre == 'agua_por_identificar' and 'tipo_agua' not in v:
        return _preguntar(datos, 'tipo_agua', u['id'])
    if 'familia' not in v:
        return _preguntar(datos, 'familia', u['id'])
    if 'fase' not in v:
        return _preguntar(datos, 'fase', u['id'])
    return None

def _documental(pregunta, captura):
    """Public CI documentation."""
    from .hechos import normalizar
    n = normalizar(pregunta)
    if re.search('\\b(?:2024/2847|2023/1542|2014/53/ue|ciberresiliencia|ciberseguridad|trazabilidad|iso/iec 27001|tabla 2 del apendice ii)\\b', n):
        return True
    if all((u['nombre'] == 'consulta' for u in captura['unidades'])) and re.search('\\b(?:preceptos|anexo|apartado|orden|registros|registro|prueba|juicio)\\b', n):
        return True
    return not any((u['observaciones'] for u in captura['unidades'])) and bool(re.search('\\b(?:reglamento|directiva|norma|articulo|notificar|certificado|citar|cita|en 12830|iso)\\b', n))

def comprobar_presentacion(exp):
    """Public CI documentation."""
    errores = []
    if exp.get('estado') == 'apagado':
        return errores
    q = exp['pregunta']
    entero = [dict(texto=q, inicio=0, fin=len(q), origen='pregunta')]
    if exp.get('soporte_consulta') != entero:
        errores.append('consulta_sin_soporte_integro')
    for u in exp.get('unidades', []):
        for o in u['observaciones']:
            if o['estado'] in {'confirmado', 'contradictorio'}:
                continue
            if o.get('advertencia') != AVISO:
                errores.append('captura_sin_advertencia:' + o['campo'])
            if len(q) <= 1200 and o.get('pruebas') != entero:
                errores.append('soporte_recortado:' + o['campo'])
            for p in o.get('pruebas', []):
                if p.get('origen') != 'pregunta' or p['texto'] != q[p['inicio']:p['fin']]:
                    errores.append('soporte_no_literal:' + o['campo'])
            if o['estado'] == CONFLICTO and (o['valor'] is not None or len(o.get('valores_mencionados', [])) < 2):
                errores.append('conflicto_con_sugerencia:' + o['campo'])
        for p in u.get('hechos_faltantes', []):
            if p['motivo'] != 'confirmar_hecho':
                continue
            if AVISO not in p['pregunta']:
                errores.append('pregunta_sin_advertencia:' + p['campo'])
            if p.get('estado_propuesta') == CONFLICTO and 'valor_propuesto' in p:
                errores.append('pregunta_conflicto_con_sugerencia:' + p['campo'])
    return errores

def expediente(base, captura, datos):
    from . import hechos as h
    pregunta = base['pregunta']
    unidades = captura['unidades']
    evaluaciones = []
    celdas = []
    pendientes = []
    rutas_explicitas = [(tipo, o['valor']) for o in captura['observaciones'] if o['estado'] == 'confirmado' for campo, tipo in [('regla', 'B2'), ('celda', 'B3')] if o['campo'] == campo]
    documental = _documental(pregunta, captura) and (not rutas_explicitas)
    for u in unidades:
        confirmadas = [o for o in u['observaciones'] if o['estado'] == 'confirmado']
        v = h._valores(u)
        propias = []
        plan = _plan(u, datos) if not rutas_explicitas else dict(rutas=rutas_explicitas, foco=None)
        u['plan'] = plan
        u['intenciones'] = [dict(campo='fase_consultada', valor=o['valor'], estado='confirmado', prueba=o['pruebas'][0]) for o in confirmadas if o['campo'] == 'fase']
        for tipo, cid in plan['rutas']:
            if rutas_explicitas or plan.get('regla_explicita'):
                e = (h.evaluar_b2 if tipo == 'B2' else h.evaluar_b3)(cid, {'observaciones': confirmadas}, datos)
                e.update(unidad=u['id'])
            elif tipo == 'B2':
                e = h._evaluar_celda_b2(cid, {**u, 'observaciones': confirmadas}, plan, pregunta, datos)
            else:
                e = {**h.evaluar_b3(cid, {'observaciones': confirmadas}, datos), 'unidad': u['id']}
            seleccion = [o for o in captura['observaciones'] if o['estado'] == 'confirmado' and o['campo'] in {'regla', 'celda'}] if rutas_explicitas else confirmadas
            e.update(hechos_en_evaluacion=copy.deepcopy(confirmadas), seleccion_por=copy.deepcopy(seleccion))
            propias.append(e)
            celdas.append(dict(tipo=tipo, id=e.get('celda', cid), unidad=u['id']))
        confirmaciones = _confirmaciones(datos, u)
        faltantes = [p for e in propias for p in e['hechos_faltantes']]
        for p in faltantes:
            p.update(unidad=u['id'], respuesta_id=u['id'] + '.' + p['campo'])
            p.setdefault('valores_admitidos', dominio(datos, p['campo']))
        conflictos = [o for o in u['observaciones'] if o['estado'] == 'contradictorio']
        if conflictos:
            faltantes.insert(0, _preguntar(datos, conflictos[0]['campo'], u['id']))
        if not propias and (not confirmaciones) and (not documental) and (not conflictos):
            p = _pendiente(u, datos)
            if p:
                faltantes.append(p)
        u['hechos_faltantes'] = confirmaciones + faltantes
        u['siguiente_pregunta'] = u['hechos_faltantes'][0] if u['hechos_faltantes'] else None
        pendientes += u['hechos_faltantes']
        evaluaciones += propias
    pendientes.sort(key=lambda p: p['motivo'] != 'confirmar_hecho')
    observaciones = unidades[0]['observaciones'] if len(unidades) == 1 else []
    resultado = evaluaciones[0]['resultado'] if len(evaluaciones) == 1 and len(unidades) == 1 else 'depende'
    estado = evaluaciones[0]['estado'] if len(evaluaciones) == 1 and len(unidades) == 1 else 'varias_vias' if evaluaciones else 'pendiente_confirmacion' if pendientes else 'pendiente_documental'
    out = {**base, 'estado': estado, 'soporte_consulta': [dict(texto=pregunta, inicio=0, fin=len(pregunta), origen='pregunta')], 'hechos': observaciones, 'unidades': unidades, 'celdas_tipificadas': celdas, 'celdas_reglas': evaluaciones, 'resultado': resultado, 'preceptos': sorted({p for e in evaluaciones for p in e['preceptos']}), 'hechos_faltantes': pendientes, 'siguiente_pregunta': pendientes[0] if pendientes else None, 'hechos_desconocidos': [hid for hid in datos.hechos if not any((o['id'] == hid and o['estado'] == 'confirmado' for u in unidades for o in u['observaciones']))], 'menciones': captura['menciones'], 'texto_no_tipificado': captura['no_interpretado'], 'respuestas_explicitas': captura['respuestas_explicitas'], 'fuentes_sha256': datos.huellas, 'camino': dict(tipo='matrices' if evaluaciones else 'busqueda_documental' if documental or not pendientes else 'confirmacion', consulta_recuperacion=pregunta, accion='confirmar_hechos' if any((p['motivo'] == 'confirmar_hecho' for p in pendientes)) else 'preguntar_o_revisar' if pendientes else 'recuperar_y_cotejar_documentos', busqueda_normal=dict(orden='buscar', consulta=pregunta, estado='pendiente_ejecucion'))}
    errores = h.comprobar_confirmaciones(out, datos)
    if errores:
        raise h.ErrorDeHechos('Invariante de confirmación: ' + str(errores))
    return out
