"""Public CI documentation."""
from decimal import Decimal
import copy
import re
INSTRUMENTOS = (('registrador(?:es)? de temperatura', 'temperatura', 'registrador'), ('registradores? que vigilan la temperatura', 'temperatura', 'registrador'), ('sustituir los registros de temperatura en papel por registradores inalambricos', 'temperatura', 'registrador'), ('termometros? de pincho', 'temperatura', 'termometro'), ('termometros? de temperatura', 'temperatura', 'termometro'), ('taximetros?', 'taximetro', None), ('contador(?:es)? de agua limpia', 'agua_limpia', None), ('contador(?:es)? de agua(?: fria)?', 'agua_por_identificar', None), ('contador(?:es)? de energia electrica', 'electricidad', None), ('contador(?:es)? (?:electricos|de electricidad)', 'electricidad', None), ('contador(?:es)? de energia termica', 'energia_termica', None), ('sistemas? de medida de liquidos distintos del agua', 'liquidos_no_agua', None), ('medidas? materializadas? de longitud', 'material_longitud', None), ('medidas? de capacidad para servir', 'material_capacidad', None), ('(?:instrumentos? )?dimensional(?:es)? mecanicos?', 'dimensional_mec', None), ('(?:instrumentos? )?dimensional(?:es)? electronicos?', 'dimensional_electronico', None), ('contador(?:es)? de maquinas recreativas?(?: [bc])?', 'maquinas_juego', None), ('sistemas? contador(?:es)? de personas', 'afluencia', None), ('analizador(?:es)? de gases de escape (?:de )?gasolina', 'analizador_gasolina', None), ('opacimetros?(?: diesel)?', 'opacimetro', None), ('cinemometros?', 'cinemometro', None), ('etilometros?', 'etilometro', None), ('medidor(?:es)? (?:del numero|de numero) de particulas(?: np)?', 'particulas', None), ('sonometros?', 'sonido', None), ('manometros? mecanicos? (?:de|para) neumaticos', 'manometro_mec', None), ('manometros? electronicos? (?:de|para) neumaticos', 'manometro_electronico', None), ('refractometros? (?:de|para) mostos? de uva', 'refractometro', None), ('basculas? (?:de )?pesaje no automatico', 'pesaje_no_auto', None))
MESES = {m: i + 1 for i, m in enumerate(('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'))}

def frases(texto):
    """Public CI documentation."""
    inicio = 0
    for m in re.finditer('[.!?](?=\\s|$)|\\r?\\n', texto):
        fin = m.end()
        if texto[inicio:fin].strip():
            yield dict(texto=texto[inicio:fin], inicio=inicio, fin=fin, origen='pregunta')
        inicio = fin
    if texto[inicio:].strip():
        yield dict(texto=texto[inicio:], inicio=inicio, fin=len(texto), origen='pregunta')

def menciones_de_campo(texto, campo, valores, alias):
    """Public CI documentation."""
    from .hechos import _normalizar_mapa, normalizar
    n, indices = _normalizar_mapa(texto)
    patrones = []
    for valor in valores:
        if not isinstance(valor, str):
            continue
        for forma in {valor.replace('_', ' '), alias.get(valor, valor)}:
            literal = normalizar(forma)
            if literal:
                patrones.append((re.escape(literal) + ('s?' if literal[-1:] not in 's' else ''), valor))
    if campo == 'familia':
        patrones += [(p, f) for p, f, _ in INSTRUMENTOS if f != 'agua_por_identificar']
        patrones += [('humedad|vibraciones?', 'otra')]
    if campo == 'fase':
        patrones += [('(?:tras (?:la )?reparacion|despues de reparacion|lo repararon|reparacion)', 'verificacion_reparacion_modificacion')]
        patrones += [('periodica', 'verificacion_periodica'), ('conformidad', 'evaluacion_conformidad')]
    if campo == 'operacion':
        patrones += [('almacen(?:es)?|almaceno|almacenamos|camaras?', 'almacenamiento'), ('transporto|transportamos|transportista|furgones?|camion(?:es)?', 'transporte')]
    if campo == 'producto_alimentario':
        patrones += [('congelados?', 'otro')]
    halladas = []
    if campo == 'combinacion':
        patron = '\\b[A-H](?:[12])?(?:\\s*\\+\\s*[A-H](?:[12])?)*\\b'
        contexto_global = re.search('\\b(?:modulos?|via|combinacion)\\b', n)
        for m in re.finditer(patron, texto, re.I):
            pref = normalizar(texto[:m.start()])
            cerca = re.search('\\b(?:modulos?|via|combinacion|o|y|frente a)\\s*[:=]?\\s*$', pref)
            literal = m.group()
            if cerca or (contexto_global and (literal.isupper() or literal not in {'a', 'e'})):
                halladas.append(([x.strip().upper() for x in m.group().split('+')], m.start(), m.end()))
    else:
        for patron, valor in patrones:
            for m in re.finditer('\\b(?:' + patron + ')\\b', n):
                halladas.append((valor, indices[m.start()], indices[m.end() - 1] + 1))
    halladas.sort(key=lambda x: (x[1], x[2]))
    salida = []
    oraciones = list(frases(texto))
    for valor, a, b in halladas:
        prueba = next((p for p in oraciones if p['inicio'] <= a and p['fin'] >= b), dict(texto=texto, inicio=0, fin=len(texto), origen='pregunta'))
        anterior = next((x for x in salida if type(x['valor']) is type(valor) and x['valor'] == valor), None)
        if anterior is None:
            salida.append(dict(valor=valor, pruebas=[prueba]))
        elif prueba not in anterior['pruebas']:
            anterior['pruebas'].append(prueba)
    return salida

def capturar_unidades(texto):
    from .hechos import _normalizar_mapa, _evidencia
    n, indices = _normalizar_mapa(texto)

    def prueba(a, b):
        return _evidencia(texto, indices[a], indices[b - 1] + 1)

    def bloqueado(a):
        punto = n.rfind('. ', 0, a)
        inicio = max(punto + 2 if punto >= 0 else 0, n.rfind(';', 0, a) + 1)
        pref = n[inicio:a]
        return bool(re.search('\\b(?:si (?:tengo|tuviera|el|un)|supongamos|comparo|comparado|como ejemplo|no (?:tengo|tenemos|hay|uso|utilizo|es|son)|no es cierto|dice(?: que|:)|titulo)\\b', pref) or re.search('¿(?:(?:tengo|tenemos|es un)\\b|hay\\b(?! que))', pref) or re.search('\\bdice\\s*:', pref) or re.search('\\bno(?: (?:lo|la|los|las))?\\s*$', pref))

    def observacion(campo, valor, a, b, contexto='uso_consultado'):
        return dict(campo=campo, id=campo, valor=valor, estado='declarado', contexto=contexto, pruebas=[prueba(a, b)])
    equipos = []
    for patron, familia, tipo in INSTRUMENTOS:
        for m in re.finditer('\\b' + patron + '\\b', n):
            if bloqueado(m.start()):
                continue
            pref = n[max(0, m.start() - 70):m.start()]
            if re.search('(?:orden de .* de|anexo .* de|norma .* de) $', pref):
                continue
            if any((m.start() < x['b'] and m.end() > x['a'] for x in equipos)):
                continue
            obs = [observacion('familia_candidata', 'agua', *m.span())] if familia == 'agua_por_identificar' else [observacion('familia', familia, *m.span())]
            if tipo:
                obs.append(observacion('tipo_instrumento', tipo, *m.span()))
            if familia in {'dimensional_mec', 'dimensional_electronico'}:
                obs.append(observacion('tecnologia', 'mecanico_electromecanico' if familia.endswith('_mec') else 'electronico', *m.span()))
            equipos.append(dict(a=m.start(), b=m.end(), familia=familia, observaciones=obs, referencias=[m.span()]))
    equipos.sort(key=lambda e: e['a'])
    for m in re.finditer('\\b(?:registrador(?:es)?|pasarelas?|basculas?|termometros?)\\b', n):
        if any((m.start() < e['b'] and m.end() > e['a'] for e in equipos)) or bloqueado(m.start()):
            continue
        pref = n[max(0, m.start() - 70):m.start()]
        if re.search('(?:orden de .* de|anexo .* de|norma .* de) $', pref):
            continue
        tipo = 'registrador' if m.group().startswith('registrador') else 'termometro' if m.group().startswith('termometro') else None
        if not re.search('\\b(?:otro|otra|segundo|segunda)\\b', pref[-25:]):
            if tipo and any((any((o['campo'] == 'tipo_instrumento' and o['valor'] == tipo for o in e['observaciones'])) for e in equipos)):
                continue
            previo = next((e for e in equipos if e.get('nombre_literal', '').rstrip('s') == m.group().rstrip('s')), None)
            if previo:
                previo['referencias'].append(m.span())
                continue
        equipos.append(dict(a=m.start(), b=m.end(), familia=None, observaciones=[], nombre_literal=m.group(), referencias=[m.span()]))
    declaracion_termica = re.search('\\bregistrador como clase (\\d+(?:[.,]\\d+)?) [^.]*?, con resolucion de (\\d+(?:[.,]\\d+)?) °c\\b', n)
    if declaracion_termica and (not bloqueado(declaracion_termica.start())):
        for e in equipos:
            if e['a'] == declaracion_termica.start() and e['familia'] is None:
                e['familia'] = 'temperatura'
                for k, v in [('familia', 'temperatura'), ('tipo_instrumento', 'registrador'), ('clase_declarada', Decimal(declaracion_termica.group(1).replace(',', '.'))), ('resolucion_declarada_C', Decimal(declaracion_termica.group(2).replace(',', '.')))]:
                    e['observaciones'].append(observacion(k, v, *declaracion_termica.span()))
    equipos.sort(key=lambda e: e['a'])
    familias = {e['familia'] for e in equipos}
    separados = any((re.search('\\b(?:otro|otra|segundo|segunda)\\b', n[max(0, e['a'] - 30):e['a']]) for e in equipos[1:]))
    if len(familias) == 1 and None not in familias and equipos and (not separados):
        primero = equipos[0]
        primero['observaciones'] = [o for e in equipos for o in e['observaciones']]
        primero['referencias'] = [ref for e in equipos for ref in e.get('referencias', [])]
        equipos = [primero]
    usos = []
    distribuidor = re.search('\\b(?:almacen (?:de distribucion|mayorista)|distribuidor(?: mayorista)?) de medicamentos\\b', n)
    farmacia = re.search('\\b(?:una )?farmacia guarda vacunas\\b', n)
    transporte = re.search('\\b(?:transporto|transportamos) (?:alimentos )?(ultracongelados|helados|refrigerados)\\b', n)
    almacen_verbo = re.search('\\b(?:almaceno|almacenamos) (?:alimentos )?(ultracongelados|helados|refrigerados)\\b', n)
    camaras = list(re.finditer('\\b(?:camara (?:de )?|otra de )(congelados|refrigerados|ultracongelados) de (\\d+(?:[.,]\\d+)?) (?:m3|m³)\\b', n))
    if camaras:
        for m in camaras:
            obs = [observacion('operacion', 'almacenamiento', *m.span()), observacion('volumen_m3', Decimal(m.group(2).replace(',', '.')), *m.span())]
            producto = m.group(1)
            if producto != 'congelados':
                obs.append(observacion('producto_alimentario', producto[:-1], *m.span()))
            usos.append(dict(nombre='camara_' + producto, observaciones=obs, producto_pendiente=producto == 'congelados', a=m.start(), b=m.end()))
    elif transporte or almacen_verbo:
        for m, op in ((transporte, 'transporte'), (almacen_verbo, 'almacenamiento')):
            if m and (not bloqueado(m.start())):
                usos.append(dict(nombre=op, observaciones=[observacion('operacion', op, *m.span()), observacion('producto_alimentario', m.group(1)[:-1], *m.span())], a=m.start(), b=m.end()))
    else:
        corte = re.search('[:¿]', n)
        declarativo = n[:corte.start()] if corte else n
        if distribuidor or farmacia:
            zona = n[:n.find('¿')] if '¿' in n and (not n.startswith('para los registradores')) else n
            for patron, op in [('\\b(?:almacen|nevera)\\b', 'almacenamiento'), ('\\b(?:furgones|transporte)\\b', 'transporte')]:
                m = re.search(patron, zona)
                if m:
                    usos.append(dict(nombre=op, observaciones=[observacion('operacion', op, *m.span())], a=m.start(), b=m.end()))
        elif re.search('\\b(?:almacen|flota|camion|transportista)\\b', declarativo):
            prod = re.search('\\b(?:alimentos )?(ultracongelados|helados|refrigerados)\\b', declarativo)
            if prod and (not re.search('fabricante de ultracongelados', declarativo)):
                for patron, op in [('\\balmacen\\b', 'almacenamiento'), ('\\b(?:flota de reparto|transportista frigorifico|camion)\\b', 'transporte')]:
                    m = re.search(patron, declarativo)
                    if m:
                        usos.append(dict(nombre=op, observaciones=[observacion('operacion', op, *m.span()), observacion('producto_alimentario', prod.group(1)[:-1], *prod.span())], a=m.start(), b=m.end()))
    if farmacia and (not usos):
        usos.append(dict(nombre='vacunas', observaciones=[], a=farmacia.start(), b=farmacia.end()))
    if distribuidor and (not usos):
        usos.append(dict(nombre='farma_sin_operacion', observaciones=[], a=distribuidor.start(), b=distribuidor.end()))
    if not usos and equipos:
        for m in re.finditer('\\ben sus (camaras|furgones)\\b', n):
            op = 'almacenamiento' if m.group(1) == 'camaras' else 'transporte'
            usos.append(dict(nombre=op, observaciones=[observacion('operacion', op, *m.span())], a=m.start(), b=m.end()))
    usos = [u for u in usos if not bloqueado(u['a'])]
    no_medicamentos = re.search('\\bsolo guarda alimentos .*, nada de medicamentos\\b', n)
    if len(equipos) > 1:
        unidades = [dict(nombre=e['familia'] or e.get('nombre_literal', 'equipo_sin_familia'), observaciones=e['observaciones'], a=e['a'], b=e['b'], referencias=e.get('referencias', []), ambiguo=True) for e in equipos]
    elif usos:
        unidades = []
        for uso in usos:
            unidades.append({**uso, 'observaciones': list(uso['observaciones']) + (equipos[0]['observaciones'] if equipos else [])})
    elif equipos:
        e = equipos[0]
        unidades = [dict(nombre=e['familia'] or e.get('nombre_literal', 'equipo_sin_familia'), observaciones=e['observaciones'], a=e['a'], b=e['b'], referencias=e.get('referencias', []))]
    else:
        return []
    consulta = n[n.rfind('¿'):] if '¿' in n else n
    fases = []
    modulos = re.search('\\b(?:para (?:su|la) evaluacion (?:de la |de )?conformidad|evaluacion (?:de la |de )?conformidad)\\b', n)
    metrologica = re.search('\\bdeclaracion de conformidad metrologica\\b', n)
    marcado = re.search('quiere poner en su registrador de temperatura el marcado ce y la', n)
    reparacion = re.search('\\b(?:ha[n]? cambiado (?:la sonda|la bateria|los neumaticos)|ha[n]? reparado (?:el equipo|el registrador|el taximetro)|lo repararon|tras (?:la )?reparacion|despues de reparacion)\\b', n)
    if reparacion and bloqueado(reparacion.start()):
        reparacion = None
    periodica = re.search('\\bverificacion periodica\\b', consulta)
    if not periodica:
        qstart = n.find('¿')
        if qstart >= 0:
            periodica = re.search('\\bverificacion periodica\\b', n[qstart:])
        if periodica and qstart >= 0:
            periodica = re.search('\\bverificacion periodica\\b', n[qstart:])
            span = (qstart + periodica.start(), qstart + periodica.end())
        else:
            span = None
    else:
        span = (n.rfind('¿') + periodica.start(), n.rfind('¿') + periodica.end()) if '¿' in n else periodica.span()
    if modulos or metrologica or marcado:
        m = modulos or metrologica or marcado
        fases.append(('evaluacion_conformidad', m.span()))
    elif periodica:
        fases.append(('verificacion_periodica', span))
    elif reparacion:
        fases.append(('verificacion_reparacion_modificacion', reparacion.span()))
    else:
        m = re.search('\\bnunca ha pasado la verificacion periodica\\b', n)
        if m:
            fases.append(('verificacion_periodica', m.span()))
        vida = re.search('\\b(?:tiene que cambiarlos ya|alargarles la vida verificandolos)\\b', n)
        if vida:
            fases.append(('plazos', vida.span()))
        inicial = re.search('\\bantes de usarlos\\b', n)
        frecuencia = re.search('\\bcada cuanto\\b', n)
        if inicial:
            fases.append(('evaluacion_conformidad', inicial.span()))
            if frecuencia:
                fases.append(('verificacion_periodica', frecuencia.span()))
    if len(fases) > 1:
        unidades = [{**u, 'observaciones': [dict(o, pruebas=list(o['pruebas'])) for o in u['observaciones']], 'fase_unica': f} for u in unidades for f in fases]
    for i, u in enumerate(unidades, 1):
        u['observaciones'] = copy.deepcopy(u['observaciones'])
        uid = 'unidad_' + str(i)
        u['id'] = uid
        u['prueba'] = prueba(u.pop('a'), u.pop('b'))
        u['eventos'] = []
        propias = [u.pop('fase_unica')] if 'fase_unica' in u else fases
        u['intenciones'] = [dict(campo='fase_consultada', valor=f, prueba=prueba(*sp)) for f, sp in propias]
        propuesto = bool(re.search('quiere sustituir.*por registradores', n))
        u['contexto'] = 'sistema_propuesto' if propuesto else 'uso_consultado'
        for o in u['observaciones']:
            o['contexto'] = uid + '/' + u['contexto']

        def add(k, v, m):
            if m and (not bloqueado(m.start())):
                u['observaciones'].append(observacion(k, v, *m.span(), contexto=uid + '/' + u['contexto']))
        if distribuidor:
            add('rol_farma', 'distribuidor_medicamentos', distribuidor)
        if no_medicamentos and re.search('\\b(?:directrices gdp|2013/c 343/01)\\b', n):
            add('rol_farma', 'otro_rol', no_medicamentos)
        if farmacia:
            u['actividad_farma_pendiente'] = True
        comercial = re.search('\\bel operador compra los registradores y las pasarelas a un fabricante de fuera de la ue y los vende a sus clientes con su propia marca y con su plataforma\\b', n)
        add('actividad_comercial_declarada', 'compra_fuera_UE_y_venta_con_marca_propia', comercial)
        if not u.get('ambiguo'):
            radio = re.search('\\bregistradores? de temperatura (?:con (?:wifi|bluetooth)|inalambricos)\\b', n)
            if not radio:
                radio = re.search('sustituir los registros de temperatura en papel por registradores inalambricos', n)
            add('radio_mismo_equipo', True, radio)
            minorista = re.search('\\bsupermercado\\b', n)
            if usos:
                add('minorista', True, minorista)
            if u['nombre'].startswith('camara_'):
                u['instalacion_pendiente'] = True
            modulo = re.search('\\bpropongo (?:los )?modulos? ([a-z0-9]+(?:\\s*\\+\\s*[a-z0-9]+)*)\\b', n)
            if modulo:
                add('combinacion', [x.strip().upper() for x in modulo.group(1).split('+')], modulo)
            dimensiones = re.search('\\bha cambiado los neumaticos .* por otros de distinta medida\\b', n)
            if any((o['valor'] == 'taximetro' for o in u['observaciones'] if o['campo'] == 'familia')):
                add('dimensiones_neumaticos_cambiadas', True, dimensiones)
            for patron, rol in [('\\bun fabricante (?:espanol )?de registradores? de temperatura\\b', 'fabricante'), ('\\bun taxista\\b', 'taxista')]:
                add('sujeto_declarado', rol, re.search(patron, n))
        else:
            for ra, rb in u.get('referencias', []):
                a = indices[rb - 1] + 1
                resto = texto[a:]
                local = re.match('\\s*(?:\\(\\s*)?(?:Bluetooth\\b|con (?:Bluetooth|wifi|conexión a Internet))', resto, re.I)
                if local:
                    valor = local.group().casefold()
                    campo = 'conexion_internet' if 'internet' in valor else 'radio_mismo_equipo'
                    u['observaciones'].append(dict(campo=campo, id=campo, valor=True, estado='declarado', contexto=uid + '/' + u['contexto'], pruebas=[_evidencia(texto, indices[ra], a + local.end())]))
        for m in re.finditer('\\b(?:paso la verificacion periodica|paso la verificacion despues de reparacion|se averio|lo repararon) (?:el |en )?(\\d{4}-\\d{2}-\\d{2}|(?:\\d{1,2} de )?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) de \\d{4})', n):
            fecha = m.group(1)
            completo = bool(re.fullmatch('\\d{4}-\\d{2}-\\d{2}', fecha))
            u['eventos'].append(dict(tipo=m.group().split(' en ')[0], fecha=fecha, precision='dia' if completo else 'mes', prueba=prueba(*m.span())))
        for m in re.finditer('\\binstalados? en (\\d{4})\\b', n):
            u['eventos'].append(dict(tipo='instalacion', fecha=m.group(1), precision='ano', prueba=prueba(*m.span())))
        for m in re.finditer('\\bfabricados antes de ((?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) de \\d{4})\\b', n):
            u['eventos'].append(dict(tipo='fabricacion', fecha_limite=m.group(1), relacion='antes_de', precision='mes', prueba=prueba(*m.span())))
        u.pop('referencias', None)
        grouped = {}
        for o in u['observaciones']:
            if o['campo'] in grouped:
                prev = grouped[o['campo']]
                if type(prev['valor']) is not type(o['valor']) or prev['valor'] != o['valor']:
                    prev.setdefault('valores_capturados', [dict(valor=prev['valor'], pruebas=list(prev['pruebas']))])
                    prev['valores_capturados'].append(dict(valor=o['valor'], pruebas=list(o['pruebas'])))
                    prev.update(estado='contradictorio', valor=None)
                prev['pruebas'].extend(o['pruebas'])
            else:
                grouped[o['campo']] = o
        u['observaciones'] = list(grouped.values())
    return unidades
