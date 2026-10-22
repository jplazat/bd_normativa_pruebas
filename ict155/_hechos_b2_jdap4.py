"""Public CI documentation."""
import calendar
import copy
from datetime import date, datetime, timedelta
import json
from decimal import Decimal, localcontext, Inexact, FloatOperation
import re
ORDEN = 'BOE-A-2020-2573::'

def declaracion_validez(r):
    """Public CI documentation."""
    op = r['operador']
    if op in CONTRATOS_NUEVOS:
        return declaracion_nueva(r)
    entradas = []
    invariantes = []
    if op == 'reparacion':
        entradas = [{'campo': 'fecha_reparacion_material', 'tipo': 'fecha', 'preceptos': [ORDEN + 'art.11.3'], 'descripcion': 'Valida el orden; nunca origina el cómputo.'}]
        invariantes = [{'id': 'I-REPARACION', 'preceptos': [ORDEN + 'art.11.3', ORDEN + 'art.14', 'BOE-A-2014-13359::art.12.4'], 'condicion': 'Resultado realizado iff fecha no nula; certificado_previo <= reparacion <= verificacion (si existe), incluso con excepcion o documentos pendientes. Igualdad diaria admitida.'}]
    elif op == 'organismo':
        invariantes = [{'id': 'I-ORGANISMO', 'preceptos': [ORDEN + 'art.7', ORDEN + 'art.14'], 'condicion': 'fecha_actuacion >= fecha_solicitud. Incumplir el maximo mensual es salida negativa, no invalidez.'}]
    elif op == 'servicio':
        invariantes = [{'id': 'I-SERVICIO', 'preceptos': [ORDEN + 'art.12', ORDEN + 'art.18', ORDEN + 'art.8'], 'condicion': 'Documentos vinculados al mismo instrumento y desfavorable; validar todas las relaciones conocidas: subsanacion y nueva solicitud >= desfavorable, nueva solicitud >= subsanacion. Anterioridad conocida invalida aun con documento ausente; igualdad de sellos: pendiente_orden_no_acreditado (J04-ORDEN-SERVICIO), sin invalidez juridica automatica.'}]
    elif op == 'muestra':
        invariantes = [{'id': 'I-MUESTRA', 'preceptos': [ORDEN + 'anexo.III/apend.III'], 'condicion': 'verificacion >= retirada_red; invariante ya existente. Superar un mes es salida negativa.'}]
    return {'entradas_validez': entradas, 'invariantes': invariantes, 'revision_validez': {'preceptos': r['fuentes'], 'conclusion': 'Orden de hechos declarado; tipos y documentos se validan antes de cualquier rama.' if invariantes else 'Sin relacion temporal adicional entre los hechos de este contrato. Tipos, dominios y documentos obligatorios; las condiciones incumplidas se calculan como salida negativa o pendiente, sin inventar otros hechos.'}}

def instante(v):
    if not isinstance(v, str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})', v):
        raise Insuficiente('instante ISO con hora y zona requerido')
    if int(v[11:13]) > 23 or int(v[14:16]) > 59 or int(v[17:19]) > 59:
        raise Insuficiente('instante ISO inválido')
    try:
        d = datetime.fromisoformat(v)
    except ValueError as e:
        raise Insuficiente('instante ISO inválido') from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise Insuficiente('instante sin zona horaria')
    return d

def validar_orden(r, h):
    """Public CI documentation."""
    op = r['operador']
    if op == 'reparacion':
        v = h['fecha_verificacion']
        if (h['resultado_verificacion'] == 'no_realizada') != (v is None):
            raise Insuficiente('I-REPARACION: resultado y fecha de verificacion incoherentes')
        if v is not None and fecha(v) < fecha(h['fecha_reparacion_material']):
            raise Insuficiente('I-REPARACION: verificacion anterior a reparacion')
        previo = fecha(h['certificado_previo'])
        if previo > fecha(h['fecha_reparacion_material']):
            raise Insuficiente('I-REPARACION: certificado previo posterior a reparacion actual')
        if v is not None and previo > fecha(v):
            raise Insuficiente('I-REPARACION: certificado previo posterior a verificacion actual')
    elif op == 'organismo':
        if fecha(h['fecha_actuacion']) < fecha(h['fecha_solicitud']):
            raise Insuficiente('I-ORGANISMO: actuacion anterior a solicitud')
    elif op == 'muestra':
        if fecha(h['verificacion']) < fecha(h['retirada_red']):
            raise Insuficiente('I-MUESTRA: verificacion anterior a retirada')
    elif op == 'servicio':
        sub, nueva = (h['documento_subsanacion'], h['documento_nueva_solicitud'])
        orden_no_acreditado = False
        if (sub is not None or nueva is not None) and h['fecha_desfavorable'] is None:
            raise Insuficiente('I-SERVICIO: documentos sin desfavorable identificado')
        if sub is not None:
            if not h['deficiencia_subsanada']:
                raise Insuficiente('I-SERVICIO: subsanacion documental contradice hecho')
            d, s = (instante(sub['momento_desfavorable']), instante(sub['momento_subsanacion']))
            if d.date() != fecha(h['fecha_desfavorable']) or s < d:
                raise Insuficiente('I-SERVICIO: subsanacion anterior o desfavorable discordante')
            orden_no_acreditado = s == d
        if nueva is not None:
            n = instante(nueva['momento_solicitud'])
            if h['fecha_solicitud'] is None or n.date() != fecha(h['fecha_solicitud']):
                raise Insuficiente('I-SERVICIO: fecha de nueva solicitud discordante')
            if sub is None and n.date() < fecha(h['fecha_desfavorable']):
                raise Insuficiente('I-SERVICIO: nueva solicitud anterior al desfavorable')
            if sub is not None:
                if nueva['instrumento'] != sub['instrumento'] or nueva['desfavorable_id'] != sub['desfavorable_id'] or nueva['subsanacion_id'] != sub['id']:
                    raise Insuficiente('I-SERVICIO: documentos no vinculados')
                if n < d:
                    raise Insuficiente('I-SERVICIO: nueva solicitud anterior al desfavorable')
                if n < s:
                    raise Insuficiente('I-SERVICIO: nueva solicitud anterior a subsanacion')
                orden_no_acreditado = orden_no_acreditado or n == s or n == d
        return orden_no_acreditado
    return False

class Insuficiente(ValueError):
    pass

class Pendiente(ValueError):
    pass

def fecha(s):
    if not isinstance(s, str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', s):
        raise Insuficiente('fecha ISO ausente o inválida')
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise Insuficiente('fecha ISO inválida') from e

def desplazar(s, meses=0, anos=0):
    d = fecha(s)
    n = d.year * 12 + d.month - 1 + meses + 12 * anos
    y, mm = divmod(n, 12)
    if d.day > calendar.monthrange(y, mm + 1)[1]:
        raise Pendiente('fin de mes o año bisiesto: criterio no resuelto')
    return date(y, mm + 1, d.day).isoformat()

def excepcion(h):
    """Public CI documentation."""
    e, r, p, a = (h[x] for x in ('documento_evaluacion', 'documento_responsable', 'parte_reparacion', 'acta_precintado'))
    if any((x is None for x in (e, r, p, a))):
        return 'pendiente_documentacion'
    if len({x['instrumento'] for x in (e, r, p, a)}) != 1:
        return 'pendiente_identidad_instrumento'
    cumple = not e['tercera_parte_cada_unidad'] and p['autor'] == r['responsable_mercado_servicio'] and (a['autor'] == r['responsable_mercado_servicio']) and a['precintos_identifican_autor'] and (p['naturaleza'] == 'reparacion_sin_modificacion')
    return 'concurre_en_hipotesis_documental' if cumple else 'no_concurre'

def _evaluar(r, hechos):
    """Public CI documentation."""
    if r['operador'] in CONTRATOS_NUEVOS:
        return evaluar_nuevo(r, hechos)
    contrato = declaracion_validez(r)
    constantes = r['constantes']
    entradas = {x['campo']: x for x in r['entradas'] + contrato['entradas_validez']}
    for k, spec in entradas.items():
        if k not in hechos:
            raise Insuficiente('falta ' + k)
        v = hechos[k]
        if v is None and spec.get('nullable'):
            continue
        tipo = spec['tipo']
        if tipo == 'fecha':
            fecha(v)
        elif tipo == 'bool' and type(v) is not bool:
            raise Insuficiente('se esperaba bool: ' + k)
        elif tipo == 'int' and (type(v) is not int or not 1900 <= v <= 2200):
            raise Insuficiente('año inválido: ' + k)
        elif tipo == 'numero' and (not numero_valido(v) or not 0 <= v < 10000):
            raise Insuficiente('número inválido: ' + k)
        elif tipo == 'texto' and (not isinstance(v, str) or not v.strip()):
            raise Insuficiente('texto vacío: ' + k)
        elif tipo == 'enum' and v not in spec['valores']:
            raise Insuficiente('valor fuera de dominio: ' + k)
        elif tipo == 'lista':
            if not isinstance(v, list):
                raise Insuficiente('lista inválida: ' + k)
            if 'elementos' in spec and any((x not in spec['elementos'] for x in v)):
                raise Insuficiente('elemento fuera de dominio: ' + k)
        elif tipo == 'documento':
            if not isinstance(v, dict) or not isinstance(v.get('id'), str) or (not v['id'].strip()):
                raise Insuficiente('documento sin identificador: ' + k)
            for nombre, t in spec['estructura'].items():
                if nombre not in v:
                    raise Insuficiente('documento incompleto: ' + k + '.' + nombre)
                if t == 'texto' and (not isinstance(v[nombre], str) or not v[nombre].strip()):
                    raise Insuficiente('texto documental inválido: ' + k + '.' + nombre)
                if t == 'bool' and type(v[nombre]) is not bool:
                    raise Insuficiente('bool documental inválido: ' + k + '.' + nombre)
                if isinstance(t, list) and v[nombre] not in t:
                    raise Insuficiente('dominio documental inválido: ' + k + '.' + nombre)
                if t == 'instante':
                    instante(v[nombre])
    h = {k: hechos[k] for k in entradas}
    orden_no_acreditado = validar_orden(r, h)
    validar_antecedentes(r, h)
    op = r['operador']
    if op == 'ambito':
        candidato = h['finalidad'] == 'cumplimiento_reglamentario' and h['actividad'] in ['transporte', 'almacenamiento', 'distribucion', 'control_productos'] and (h['disposicion_obligante'] != 'no_aportada')
        return {'candidato_XI': candidato, 'aplicabilidad_contextual_real': 'pendiente_B3'}
    if op == 'modulos':
        return {'combinacion_admitida_via_nacional': h['combinacion'] in [['B', 'D'], ['B', 'F'], ['G']]}
    if op == 'electronica':
        return {'exencion_solo_requisitos_comunes_electronicos': not h['usa_electronica'], 'demas_requisitos_ensayos': 'siguen_exigibles'}
    if op == 'sensor':
        return {'exigencia_especial_certificado_B': h['unidades_intercambiables'] and h['todos_parametros_sensor'] and (h['modulo'] == 'B'), 'decision_cambio_sensor_J02': 'exigir_certificado_fabricante_y_memoria_operacion'}
    if op == 'equivalencia':
        d = h['documento_equivalencia']
        eq = all((d[x] == 'equivalente' for x in ['exactitud', 'seguridad', 'adecuacion', 'idoneidad']))
        procede = h['procedencia'] in ['otro_Estado_UE', 'Turquia', 'origen_EEE']
        fundamento = h['documento_fundamento']['tipo'] in ['procedimiento_legal', 'certificado_conformidad']
        return {'presuncion_art5_2_en_hipotesis': procede and fundamento and eq, 'administracion_puede_pedir_documentacion': True}
    if op == 'bloqueo':
        return {'administracion_puede_impedir_comercializacion_puesta_servicio': h['acta_inspeccion']['incumplimiento_esencial']}
    if op == 'excepcion':
        return {'art12_4': excepcion(h)}
    if op == 'reparacion':
        ex = excepcion(h)
        if ex.startswith('pendiente'):
            return {'estado': ex, 'referencia': None, 'fin_periodo': None}
        if h['resultado_verificacion'] != 'no_realizada' and h['fecha_verificacion'] is None:
            raise Insuficiente('falta fecha del resultado de verificación')
        if h['resultado_verificacion'] == 'no_realizada' and h['fecha_verificacion'] is not None:
            raise Insuficiente('no realizada no puede tener fecha de actuación real')
        if ex == 'concurre_en_hipotesis_documental':
            ref, motivo = (h['certificado_previo'], 'excepcion_legal_no_altera')
        elif h['resultado_verificacion'] == 'favorable':
            ref, motivo = (h['fecha_verificacion'], 'verificacion_favorable')
        else:
            ref, motivo = (h['certificado_previo'], 'sin_nuevo_certificado_favorable')
        return {'referencia': ref, 'fin_periodo': desplazar(ref, anos=r['constantes']['anos']), 'motivo': motivo, 'autoriza_uso': False}
    if op == 'primera':
        if h['medio_fecha'] == 'sin_acreditacion':
            ref, origen = (f"{h['ano_marcado']:04d}-{constantes['inicio_supletorio']}", 'art14_3')
        else:
            if h['fecha_documentada'] is None:
                raise Insuficiente('falta fecha documentada de primera utilización')
            ref, origen = (h['fecha_documentada'], 'art14_2')
        return {'referencia': ref, 'fin_periodo': desplazar(ref, anos=r['constantes']['anos']), 'origen': origen}
    if op == 'sucesiva':
        return {'fin_periodo': desplazar(h['certificado_previo'], anos=r['constantes']['anos'])}
    if op == 'solicitud':
        limite = desplazar(h['fin_periodo'], meses=-constantes['meses'])
        return {'ultimo_dia_referencia_solicitud': limite, 'cumple_antelacion': fecha(h['fecha_solicitud']) <= fecha(limite)}
    if op == 'organismo':
        limite = desplazar(h['fecha_solicitud'], meses=constantes['meses'])
        return {'maximo_referencia': limite, 'no_excede_mes': fecha(h['fecha_actuacion']) <= fecha(limite), 'prorroga_uso_titular': False}
    if op == 'servicio':
        if orden_no_acreditado:
            return {'via_transitoria_art8_disponible': None, 'estado': 'pendiente_orden_no_acreditado', 'decision_Responsable': 'J04-ORDEN-SERVICIO', 'alcance': 'solo_esta_via_no_autorizacion_global'}
        solicitud = h['fecha_solicitud']
        admisible = solicitud is not None and (not h['periodica_vencida']) and (not (h['fecha_lugar_asignados'] and h['impedimento_imputable_titular']))
        if h['fecha_desfavorable'] is not None and admisible:
            if not h['deficiencia_subsanada']:
                admisible = False
            elif h['documento_subsanacion'] is None or h['documento_nueva_solicitud'] is None:
                return {'via_transitoria_art8_disponible': None, 'estado': 'pendiente_documentacion_nueva_solicitud', 'alcance': 'solo_esta_via_no_autorizacion_global'}
        return {'via_transitoria_art8_disponible': admisible, 'alcance': 'solo_esta_via_no_autorizacion_global'}
    if op == 'etiquetas':
        return {'etiquetar_cada_elemento_disociable': h['unidades_intercambiables']}
    if op == 'informe':
        mal = h['resultado'] == 'desfavorable'
        return {'etiqueta_inhabilitacion': mal, 'informe_y_comunicacion_administracion': mal, 'plazo_maximo_dias': constantes['dias'] if mal else None, 'calendario_fecha': 'no_calculado'}
    if op == 'reparador':
        ex = h['establecimiento'] == 'otro_Estado_UE' and h['regimen_servicio'] == 'libre_prestacion'
        return {'declaracion_responsable_necesaria': not ex, 'condicion_declaracion_satisfecha': ex or h['documento_declaracion'] is not None, 'alcance': 'solo_requisito_declaracion_no_habilitacion_integral'}
    if op == 'regimen_ensayo':
        frontera = entrada_vigor(constantes)
        if fecha(h['fecha_examen_tipo']) == fecha(frontera):
            return {'estado': 'pendiente_frontera_entrada', 'ensayos': None, 'EMP': None}
        anterior = fecha(h['fecha_examen_tipo']) < fecha(frontera)
        return {'estado': 'remision_identificada', 'ensayos': 'UNE-EN 13486:2002' if anterior else 'EN 13486:2023', 'EMP': ('UNE-EN 13485:2002' if anterior else 'EN 13485:2023') if h['tipo_instrumento'] == 'termometro' else 'UNE-EN 12830:2019'}
    if op == 'clase':
        return {'clase_coincide_con_placa': h['clase_placa'] == h['clase_propuesta'], 'impide_favorable_por_clase_distinta': h['clase_placa'] != h['clase_propuesta'], 'otros_ensayos': 'no_ejecutados'}
    if op == 'desfase':
        return {'verificacion_no_favorable_por_desfase': h['tipo_instrumento'] == 'registrador' and h['desfase_horas'] > constantes['horas'], 'otros_ensayos': 'no_ejecutados'}
    if op == 'vigilancia':
        return {'puede_comprobar_en_cualquier_momento': h['administracion_competente'] and h['sometido_control'], 'sustituye_verificacion': False}
    if op == 'uso':
        if h['fecha_consulta'] == h['fin_periodo']:
            return {'estado': 'pendiente_frontera', 'prohibicion_por_vencimiento': None}
        return {'estado': 'resuelto_en_escenario', 'prohibicion_por_vencimiento': fecha(h['fecha_consulta']) > fecha(h['fin_periodo']) and (not h['verificacion_superada'])}
    if op == 'cambio':
        c = h['dictamen_cambio']['calificacion']
        return {'tratamiento': {'pendiente_J03': 'escalar_a_Responsable', 'importante_hipotetico': 'instrumento_nuevo_nueva_evaluacion', 'reparacion_hipotetica': 'examinar_verificacion_no_exencion'}[c], 'J03': 'criterio_aprobado_calificacion_caso_por_revisar'}
    if op == 'vida':
        return {'fin_vida_base': desplazar(h['primera_instalacion'], anos=constantes['anos']), 'reinstalacion_no_reinicia': True}
    if op == 'ampliacion':
        g, c = (h['informe_gestor'], h['certificado_muestreo'])
        ok = g['lote'] == c['lote'] and g['cumple_criterios'] and (c['resultado'] == 'favorable') and c['organismo_autorizado']
        return {'ampliacion_quinquenal': ok, 'fin_ampliado': desplazar(h['fin_vigente'], anos=constantes['anos']) if ok else None}
    if op == 'sustitucion':
        fin = desplazar(h['primera_instalacion'], anos=constantes['vida_anos'])
        limite = desplazar(constantes['inicio_sustitucion'], anos=constantes['anos'])
        return {'cohorte_transitoria': fecha(fin) <= fecha(limite), 'referencia_fin_sustitucion': limite if fecha(fin) <= fecha(limite) else None, 'autoriza_uso_hasta_fecha': False}
    if op == 'aviso':
        limite = desplazar(h['siguiente_verificacion'], meses=-constantes['meses'])
        intacto = not h['lote_modificado_durante_validez']
        return {'regla_tres_meses_aplicable': intacto, 'fecha_limite_aviso': limite if intacto else None, 'cumple': fecha(h['fecha_aviso']) <= fecha(limite) and h['sujeto'] == 'gestor_constituyente' and (h['destinatario'] in ['organismo_autorizado', 'administracion_competente']) if intacto else None, 'si_modificado': 'formar_nuevo_lote_y_examinar_obligaciones'}
    if op == 'muestra':
        if fecha(h['verificacion']) < fecha(h['retirada_red']):
            raise Insuficiente('verificación anterior a retirada')
        return {'no_supera_mes': fecha(h['verificacion']) <= fecha(desplazar(h['retirada_red'], meses=constantes['meses'])), 'brevedad': 'justificar_por_separado_no_basta_cumplir_mes'}
    if op == 'sujeto':
        return {'sujeto_obligado': 'gestor' if h['modalidad'] == 'muestreo' else 'titular_instrumento'}
    if op == 'campo_g':
        esg = not h['usos_af_documentados']
        return {'regimen': 'g_inscripciones_sin_marcado_RD' if esg else 'examinar_af', 'servicio_J07': 'regimen_tecnico_documental_sin_analogia' if (esg if op == 'campo_g' else regimen == 'g_inscripciones_sin_marcado_RD') else 'examinar_ambito_af_o_documentacion'}
    if op == 'inscripciones_g':
        ok = all((h[k] for k in ['identidad_fabricante', 'Max_inscrito', 'direccion_unica', 'visibles_legibles_indelebles'])) and (not h['marcado_conformidad_RD'])
        return {'cumple_lista_inscripciones_y_marcado_g': ok, 'otros_marcados': 'examinar_otra_legislacion'}
    if op == 'taxi_k':
        if not h['k_recalculada']:
            salida = 'sin_disparador_por_recalculo_revisar_otros'
        elif h['dimensiones_neumaticos_cambiadas'] or h['motivacion_excepcional'] != 'no_aportada':
            salida = 'debe_superar_verificacion_posterior'
        else:
            salida = 'recalculo_sin_motivo_legal_aportado_no_concluir_exencion'
        return {'resultado_punto6': salida}
    if op == 'taxi_actuacion':
        return {'disparador_expreso_modificacion': h['actuacion'] in ['sustitucion_mismo_vehiculo', 'cambio_tarifas'], 'otras_actuaciones': 'examinar_regla_general'}
    if op == 'tarifas':
        tarifa = h['tipo_solicitud'] == 'cambio_tarifas'
        unidad, valor = ('dias_habiles', constantes['dias_habiles']) if tarifa else ('mes', constantes['meses'])
        return {'valor': valor, 'unidad': unidad, 'unidad_afirmada_correcta': h['unidad_afirmada'] == unidad, 'fecha_maxima': None, 'estado_fecha': 'pendiente_calendario_competente' if tarifa else 'no_calculada_en_esta_regla'}
    if op == 'cabina':
        if h['incidente'] != 'ninguno':
            return {'salida': 'nueva_verificacion_por_incidente', 'referencia_cuatrienal': None, 'coincidir_periodica': False}
        if h['ultima_revision'] is None:
            return {'salida': 'revision_en_proxima_verificacion_periodica', 'referencia_cuatrienal': None, 'coincidir_periodica': True, 'inicio_cuatro_anos': 'fecha_revision_cabina_documentada_en_proxima_periodica'}
        return {'salida': 'revision_cuatrienal', 'referencia_cuatrienal': desplazar(h['ultima_revision'], anos=constantes['anos']), 'coincidir_periodica': True}
    if op == 'crio':
        if not h['camion_cisterna'] and h['producto'] != 'ordinario':
            return {'cohorte_especial': False, 'origen': None, 'primera_referencia': None, 'frontera_entrada': 'requiere_acreditar_ambito_general'}
        frontera = entrada_vigor(constantes)
        especial = h['camion_cisterna'] and (h['producto'] in ['CO2_licuado', 'GNL'] or (h['producto'] == 'criogeno' and h['ebullicion_K'] < constantes['umbral_K'])) and (fecha(h['puesta_servicio']) < fecha(frontera))
        ref = frontera if especial else h['puesta_servicio']
        return {'cohorte_especial': especial, 'origen': ref, 'primera_referencia': desplazar(ref, anos=constantes['anos']), 'frontera_entrada': 'no_certificada'}
    raise Insuficiente('operador desconocido: ' + op)

def salida_evaluada(r, h):
    try:
        return evaluar(r, h)
    except Pendiente as e:
        return {'estado': 'pendiente_calendario', 'motivo': str(e)}
NUMEROS = {'un': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'siete': 7, 'doce': 12, 'veinte': 20, 'treinta': 30}
MESES = {v: i for i, v in enumerate(('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'), 1)}
CONSTANTES_OPERADOR = {'reparacion': {'anos': 'anos'}, 'primera': {'anos': 'anos', 'inicio_supletorio': 'mes_dia'}, 'sucesiva': {'anos': 'anos'}, 'solicitud': {'meses': 'meses'}, 'organismo': {'meses': 'meses'}, 'informe': {'dias': 'dias'}, 'regimen_ensayo': {'publicacion': 'fecha', 'demora_entrada_dias': 'dias'}, 'desfase': {'horas': 'horas'}, 'vida': {'anos': 'anos'}, 'ampliacion': {'anos': 'anos'}, 'sustitucion': {'vida_anos': 'anos', 'anos': 'anos', 'inicio_sustitucion': 'fecha'}, 'aviso': {'meses': 'meses'}, 'muestra': {'meses': 'meses'}, 'tarifas': {'dias_habiles': 'dias_habiles', 'meses': 'meses'}, 'cabina': {'anos': 'anos'}, 'crio': {'anos': 'anos', 'umbral_K': 'K', 'publicacion': 'fecha', 'demora_entrada_dias': 'dias'}}
DECISIONES_OPERADOR = {'sensor': ['J02'], 'cambio': ['J03'], 'campo_g': ['J07'], 'servicio': ['J04-ORDEN-SERVICIO']}
OPERADORES = {'ambito', 'modulos', 'electronica', 'sensor', 'equivalencia', 'bloqueo', 'excepcion', 'reparacion', 'primera', 'sucesiva', 'solicitud', 'organismo', 'servicio', 'etiquetas', 'informe', 'reparador', 'regimen_ensayo', 'clase', 'desfase', 'vigilancia', 'uso', 'cambio', 'vida', 'ampliacion', 'sustitucion', 'aviso', 'muestra', 'sujeto', 'campo_g', 'inscripciones_g', 'taxi_k', 'taxi_actuacion', 'tarifas', 'cabina', 'crio'}

def entrada_vigor(c):
    return (fecha(c['publicacion']) + timedelta(days=c['demora_entrada_dias'])).isoformat()

def numero_literal(token):
    if token in NUMEROS:
        return NUMEROS[token]
    if re.fullmatch('[0-9]+', token):
        return int(token)
    raise Insuficiente('número literal no soportado: ' + token)

def valor_anclado_v6(ancla):
    """Public CI documentation."""
    texto, unidad = (ancla['literal'], ancla['unidad'])
    patrones = {'anos': '([a-z]+|[0-9]+) años?', 'meses': '([a-z]+|[0-9]+) mes(?:es)?', 'dias': '([a-z]+|[0-9]+) días?', 'dias_habiles': '([a-z]+|[0-9]+) días? hábiles', 'horas': '([a-z]+|[0-9]+) horas?', 'K': '([0-9]+) K'}
    if unidad in patrones:
        coincidencia = re.fullmatch(patrones[unidad], texto)
        if not coincidencia:
            raise Insuficiente('fragmento numérico/unidad no interpretable')
        return numero_literal(coincidencia[1])
    if unidad in {'fecha', 'mes_dia'}:
        patron = '([0-9]{1,2}) de ([a-z]+) de ([0-9]{4})' if unidad == 'fecha' else 'el día ([0-9]{1,2}) de ([a-z]+) del año'
        c = re.fullmatch(patron, texto)
        if not c or c[2] not in MESES:
            raise Insuficiente('fragmento de fecha no interpretable')
        if unidad == 'fecha':
            return date(int(c[3]), MESES[c[2]], int(c[1])).isoformat()
        return f'{MESES[c[2]]:02d}-{int(c[1]):02d}'
    raise Insuficiente('unidad de ancla no soportada')
CONTRATOS_NUEVOS = {'agua_ambito': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-AMBITO', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.1', 'BOE-A-2016-5530::anexo.VIII/art.1'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.1', 'BOE-A-2016-5530::anexo.VIII/art.1'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_modulos': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-MODULOS', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.3', 'BOE-A-2016-5530::anexo.VIII/art.5', 'BOE-A-2016-5530::art.10.1', 'BOE-A-2016-5530::art.11.1'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.3', 'BOE-A-2016-5530::anexo.VIII/art.5', 'BOE-A-2016-5530::art.10.1', 'BOE-A-2016-5530::art.11.1'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_regimen': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-REGIMEN', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.1', 'BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/ap.6', 'BOE-A-2016-5530::art.16.3'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.1', 'BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/ap.6', 'BOE-A-2016-5530::art.16.3'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_prohibicion': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-PROHIBICION', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/ap.5', 'BOE-A-2016-5530::art.16.3'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/ap.5', 'BOE-A-2016-5530::art.16.3'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_preuso': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-PREUSO-OTROS', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.5', 'BOE-A-2020-2573::art.7', 'BOE-A-2020-2573::art.8', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.18', 'BOE-A-2014-13359::art.12.4'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.5', 'BOE-A-2020-2573::art.7', 'BOE-A-2020-2573::art.8', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.18', 'BOE-A-2014-13359::art.12.4'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_delegacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-DELEGACION', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_etiqueta': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-INSTALACION', 'preceptos': ['BOE-A-2020-2573::art.19.2'], 'condicion': 'Si hay reinstalación, primera_instalacion <= reinstalacion. Cambiar instalación no reinicia vida.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.19.2', 'BOE-A-2016-5530::anexo.III/art.3', 'BOE-A-2020-2573::anexo.III/ap.4'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_retencion': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-RETENCION', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'limite_fijado >= verificacion_muestreo si existe. Exceder mes incumple; no invalida la representación de hechos.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_intervencion_muestra': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-INTERVENCION-MUESTRA', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_repuesto': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-REPUESTO', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_plan': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-PLAN', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_lote': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-LOTE', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_homogeneidad': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-HOMOGENEIDAD', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_documentos_plazo': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-PLAZOS-DOCUMENTOS', 'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.17', 'BOE-A-2020-2573::art.18'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.17', 'BOE-A-2020-2573::art.18'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_ensayos': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-ENSAYOS', 'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_emp': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-EMP', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.I', 'BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.I', 'BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_caudales_1988': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-CAUDALES-1988', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_alimentacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-ALIMENTACION', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.I'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.I'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_volumen': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-VOLUMEN', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_incertidumbre': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-INCERTIDUMBRE', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_mismo_signo': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-MISMO-SIGNO', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.IV'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_ajuste_evaluacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-AJUSTE-EVALUACION', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.II'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.II'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_comunicacion_inmediata': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-COMUNICACION-INMEDIATA', 'preceptos': ['BOE-A-2020-2573::art.9'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.9'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_conservacion_muestra': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-CONSERVACION-MUESTRA', 'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_sustitucion_cohorte': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-SUSTITUCION-COHORTE', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::disp.transitoria.1', 'BOE-A-2020-2573::art.19.2'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::disp.transitoria.1', 'BOE-A-2020-2573::art.19.2'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'agua_ampliacion_unidad': {'entradas_validez': [], 'invariantes': [{'id': 'I-AG-AMPLIACION-UNIDAD', 'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/apend.III'], 'condicion': 'Tipos y dominios explícitos; documentos sintéticos identificados. No se infieren hechos ausentes ni autorización global.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.III/ap.4', 'BOE-A-2020-2573::anexo.III/apend.III'], 'conclusion': 'Tipos, documentos e invariantes adicionales de agua declarados y comprobados antes del cálculo. No se infieren hechos ni permisos de uso.'}}, 'tx_modulos': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-MODULOS', 'preceptos': ['BOE-A-2016-5530::anexo.XIII/art.5'], 'condicion': 'Lista de módulos expresa; no acredita ejecución ni documentación real.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.XIII/art.5'], 'conclusion': 'Lista de módulos expresa; no acredita ejecución ni documentación real.'}}, 'tx_instalacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-INSTALACION', 'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.III', 'BOE-A-2020-2573::anexo.VII/apend.II'], 'condicion': 'Documento del mismo vehículo e instrumento; nunca deducir reforma de un certificado ausente. Primera/siguientes separadas.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.III', 'BOE-A-2020-2573::anexo.VII/apend.II'], 'conclusion': 'Documento del mismo vehículo e instrumento; nunca deducir reforma de un certificado ausente. Primera/siguientes separadas.'}}, 'tx_solicitud': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-SOLICITUD', 'preceptos': ['BOE-A-2020-2573::anexo.VII/ap.4'], 'condicion': 'Actuación e identidad concretas; la mención de reinstalación presupone mismo vehículo y resto de instalación inalterado.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.VII/ap.4'], 'conclusion': 'Actuación e identidad concretas; la mención de reinstalación presupone mismo vehículo y resto de instalación inalterado.'}}, 'tx_plazo_tarifas': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-PLAZO-TARIFAS', 'preceptos': ['BOE-A-2020-2573::anexo.VII/ap.4', 'BOE-A-2020-2573::art.7'], 'condicion': 'Solicitud posterior o igual al cambio de tarifas; máximo del organismo, no prórroga del titular. Sin calendario no fechar vencimiento.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.VII/ap.4', 'BOE-A-2020-2573::art.7'], 'conclusion': 'Solicitud posterior o igual al cambio de tarifas; máximo del organismo, no prórroga del titular. Sin calendario no fechar vencimiento.'}}, 'tx_k_inicial': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-K-INICIAL', 'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.III'], 'condicion': 'Informe identificado y del mismo instrumento; error porcentual absoluto finito y autor reparador. No sustituye ensayo.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.III'], 'conclusion': 'Informe identificado y del mismo instrumento; error porcentual absoluto finito y autor reparador. No sustituye ensayo.'}}, 'tx_ensayos': {'entradas_validez': [], 'invariantes': [{'id': 'I-TX-ENSAYOS', 'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.II'], 'condicion': 'Versión identificada y facilitada por responsable; su ausencia conserva ensayo de cada tarifa.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.VII/apend.II'], 'conclusion': 'Versión identificada y facilitada por responsable; su ausencia conserva ensayo de cada tarifa.'}}, 'rc_ambito': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-AMBITO', 'preceptos': ['BOE-A-2020-2573::anexo.XX/ap.1', 'BOE-A-2020-2573::anexo.XX/ap.2'], 'condicion': 'Uso comercial expresamente documentado; otro uso no implica exención de otra normativa.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/ap.1', 'BOE-A-2020-2573::anexo.XX/ap.2'], 'conclusion': 'Uso comercial expresamente documentado; otro uso no implica exención de otra normativa.'}}, 'rc_puntos': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-PUNTOS', 'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III', 'BOE-A-2020-2573::anexo.XX/ap.6'], 'condicion': 'Censo no vacío sin duplicados; un antecedente de periódica por punto; mismo conjunto; fechas de certificados no posteriores a consulta. Antecedentes ausentes bloquean fecha.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III', 'BOE-A-2020-2573::anexo.XX/ap.6'], 'conclusion': 'Censo no vacío sin duplicados; un antecedente de periódica por punto; mismo conjunto; fechas de certificados no posteriores a consulta. Antecedentes ausentes bloquean fecha.'}}, 'rc_alcance': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-ALCANCE-RM', 'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III', 'BOE-A-2020-2573::anexo.XX/ap.5'], 'condicion': 'Intervención y precintos se declaran por separado; un punto de censo existente. Reparación no cambia reloj del conjunto en rama de punto único.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III', 'BOE-A-2020-2573::anexo.XX/ap.5'], 'conclusion': 'Intervención y precintos se declaran por separado; un punto de censo existente. Reparación no cambia reloj del conjunto en rama de punto único.'}}, 'rc_adaptacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-ADAPTACION', 'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.IV'], 'condicion': 'Certificado del mismo sistema; todos los requisitos documentales juntos, sin acreditado=true. Cronología separada en RC-PRIMERA-ADAPTADA.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.IV'], 'conclusion': 'Certificado del mismo sistema; todos los requisitos documentales juntos, sin acreditado=true. Cronología separada en RC-PRIMERA-ADAPTADA.'}}, 'rc_adaptada': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-PRIMERA-ADAPTADA', 'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.IV', 'BOE-A-2020-2573::anexo.XX/ap.6'], 'condicion': 'Adaptación <= verificación tras modificación; primera periódica desde adaptación, no certificado posterior.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.IV', 'BOE-A-2020-2573::anexo.XX/ap.6'], 'conclusion': 'Adaptación <= verificación tras modificación; primera periódica desde adaptación, no certificado posterior.'}}, 'rc_cohorte': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-COHORTES', 'preceptos': ['BOE-A-2020-2573::anexo.XX/ap.8', 'BOE-A-2020-2573::anexo.XX/ap.9', 'BOE-A-2024-27147::cabecera', 'BOE-A-2024-27147::disp.final.2'], 'condicion': 'Instalación <= primera utilización <= consulta; consulta no anterior a entrada. Igualdad en entrada y fin de ventana queda pendiente. No prorrogar por instalación tardía.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/ap.8', 'BOE-A-2020-2573::anexo.XX/ap.9', 'BOE-A-2024-27147::cabecera', 'BOE-A-2024-27147::disp.final.2'], 'conclusion': 'Instalación <= primera utilización <= consulta; consulta no anterior a entrada. Igualdad en entrada y fin de ventana queda pendiente. No prorrogar por instalación tardía.'}}, 'rc_etiquetas': {'entradas_validez': [], 'invariantes': [{'id': 'I-RC-ETIQUETAS', 'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III'], 'condicion': 'Censo no vacío y único; punto reparado identificado; etiqueta de punto no habilita conjunto. Simultaneidad exige comprobar interferencia.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.XX/apend.III'], 'conclusion': 'Censo no vacío y único; punto reparado identificado; etiqueta de punto no habilita conjunto. Simultaneidad exige comprobar interferencia.'}}, 'admin_certificado': {'entradas_validez': [], 'invariantes': [{'id': 'I-B2P-ADMIN-CERTIFICADO', 'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::art.17'], 'condicion': 'Hecho que activa obligación identificado y fechado; no fechar vencimiento sin calendario. Tres días por precintado defectuoso, diez por certificado favorable, comunicación inmediata en indicios o incumplimientos.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::art.17'], 'conclusion': 'Hecho que activa obligación identificado y fechado; no fechar vencimiento sin calendario. Tres días por precintado defectuoso, diez por certificado favorable, comunicación inmediata en indicios o incumplimientos.'}}, 'pesaje_modulos': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-MODULOS', 'preceptos': ['BOE-A-2016-5530::anexo.VI/art.5', 'BOE-A-2016-5530::anexo.VII/art.5'], 'condicion': 'Tecnología y ámbito a)-f) de no automático previamente documentados. Lista sin módulos repetidos. Electrónica/resortes solo se leen para la rama no automática; no se deduce tecnología del marcado M.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.VI/art.5', 'BOE-A-2016-5530::anexo.VII/art.5'], 'conclusion': 'Tecnología y ámbito a)-f) de no automático previamente documentados. Lista sin módulos repetidos. Electrónica/resortes solo se leen para la rama no automática; no se deduce tecnología del marcado M.'}}, 'pesaje_expediente_g': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-EXPEDIENTE-G', 'preceptos': ['BOE-A-2016-5530::anexo.VI/art.1', 'BOE-A-2016-5530::anexo.VI/art.4', 'BOE-A-2016-5530::anexo.VI/apend.III', 'BOE-A-2020-2573::anexo.I/ap.1', 'BOE-A-2020-2573::art.1'], 'condicion': 'Documento identificado y vinculado al instrumento; los seis campos describen hechos de uso sintéticos, no un booleano acreditado. No_consta no equivale a ausencia; cualquier finalidad a)-f) presente impide concluir g) exclusivo.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.VI/art.1', 'BOE-A-2016-5530::anexo.VI/art.4', 'BOE-A-2016-5530::anexo.VI/apend.III', 'BOE-A-2020-2573::anexo.I/ap.1', 'BOE-A-2020-2573::art.1'], 'conclusion': 'Documento identificado y vinculado al instrumento; los seis campos describen hechos de uso sintéticos, no un booleano acreditado. No_consta no equivale a ausencia; cualquier finalidad a)-f) presente impide concluir g) exclusivo.'}}, 'pesaje_puente': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-PUENTE', 'preceptos': ['BOE-A-2020-2573::anexo.I/apend.I/tabla.2', 'BOE-A-2020-2573::anexo.I/apend.II', 'BOE-A-2020-2573::anexo.I/apend.III'], 'condicion': '0 < nuevo máximo <= máximo original; límite vial y e positivos. Petición escrita del mismo titular e instrumento. Se usa t para respetar el dominio numérico v4. Límite vial es un hecho hipotético aportado, no una norma vial buscada ni validada.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.I/apend.I/tabla.2', 'BOE-A-2020-2573::anexo.I/apend.II', 'BOE-A-2020-2573::anexo.I/apend.III'], 'conclusion': '0 < nuevo máximo <= máximo original; límite vial y e positivos. Petición escrita del mismo titular e instrumento. Se usa t para respetar el dominio numérico v4. Límite vial es un hecho hipotético aportado, no una norma vial buscada ni validada.'}}, 'pesaje_lugar': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-LUGAR-NA', 'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV'], 'condicion': 'Dos fases por gravedad presupone sensibilidad a la gravedad. Módulo D/D1/F/F1/G previamente elegido. La primera fase exige certificado individual y conserva identidad; segunda completa ensayos pendientes.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV'], 'conclusion': 'Dos fases por gravedad presupone sensibilidad a la gravedad. Módulo D/D1/F/F1/G previamente elegido. La primera fase exige certificado individual y conserva identidad; segunda completa ensayos pendientes.'}}, 'pesaje_actos': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-ACTOS', 'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::art.17', 'BOE-A-2020-2573::art.18'], 'condicion': 'El evento es favorable/no superación de la verificación o detección del hecho indicado, en fecha completa. No se inventa calendario hábil/natural ni hora del origen; fecha límite queda pendiente.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.9', 'BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.15', 'BOE-A-2020-2573::art.17', 'BOE-A-2020-2573::art.18'], 'conclusion': 'El evento es favorable/no superación de la verificación o detección del hecho indicado, en fecha completa. No se inventa calendario hábil/natural ni hora del origen; fecha límite queda pendiente.'}}, 'pesaje_certificados': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-CERTIFICADOS', 'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV', 'BOE-A-2016-5530::anexo.I/art.5', 'BOE-A-2016-5530::anexo.I/art.17'], 'condicion': 'Acto identificado; renovación/prórroga requieren concesión explícita. Limitación a 2 y prórroga de 3 solo VI, por cambios fundamentales documentados en acto. Prórroga enlaza fin del certificado anterior. Campo fecha_origen representa inicio del nuevo período documentado, no presume que solicitud/acto reinicie el reloj.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV', 'BOE-A-2016-5530::anexo.I/art.5', 'BOE-A-2016-5530::anexo.I/art.17'], 'conclusion': 'Acto identificado; renovación/prórroga requieren concesión explícita. Limitación a 2 y prórroga de 3 solo VI, por cambios fundamentales documentados en acto. Prórroga enlaza fin del certificado anterior. Campo fecha_origen representa inicio del nuevo período documentado, no presume que solicitud/acto reinicie el reloj.'}}, 'pesaje_conservacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-CONSERVACION', 'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV', 'BOE-A-2016-5530::anexo.I/art.5', 'BOE-A-2016-5530::anexo.I/art.9', 'BOE-A-2016-5530::anexo.I/art.10', 'BOE-A-2016-5530::anexo.I/art.11', 'BOE-A-2016-5530::anexo.I/art.13', 'BOE-A-2016-5530::anexo.I/art.14', 'BOE-A-2016-5530::anexo.I/art.15', 'BOE-A-2016-5530::anexo.I/art.17'], 'condicion': 'Documentos son los enumerados en el módulo aplicable, no todo documento indiscriminado. Rama organismo solo B/H1 y hasta fin de validez. H1/E no son módulos de no automático en este anexo.'}], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.VI/apend.IV', 'BOE-A-2016-5530::anexo.I/art.5', 'BOE-A-2016-5530::anexo.I/art.9', 'BOE-A-2016-5530::anexo.I/art.10', 'BOE-A-2016-5530::anexo.I/art.11', 'BOE-A-2016-5530::anexo.I/art.13', 'BOE-A-2016-5530::anexo.I/art.14', 'BOE-A-2016-5530::anexo.I/art.15', 'BOE-A-2016-5530::anexo.I/art.17'], 'conclusion': 'Documentos son los enumerados en el módulo aplicable, no todo documento indiscriminado. Rama organismo solo B/H1 y hasta fin de validez. H1/E no son módulos de no automático en este anexo.'}}, 'pesaje_ensayo': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-ENSAYOS', 'preceptos': ['BOE-A-2020-2573::anexo.I/apend.II', 'BOE-A-2020-2573::anexo.II/apend.II', 'BOE-A-2020-2573::anexo.II/apend.II/tabla.12'], 'condicion': 'Familia técnica identificada, distinta de tecnología mecánica/electrónica. Material alternativo: características similares y justificación técnica/económica; sistema: imposibilidad segura/económica por construcción. Sin evidencia, pendiente.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.I/apend.II', 'BOE-A-2020-2573::anexo.II/apend.II', 'BOE-A-2020-2573::anexo.II/apend.II/tabla.12'], 'conclusion': 'Familia técnica identificada, distinta de tecnología mecánica/electrónica. Material alternativo: características similares y justificación técnica/económica; sistema: imposibilidad segura/económica por construcción. Sin evidencia, pendiente.'}}, 'pesaje_tiempos_tecnicos': {'entradas_validez': [], 'invariantes': [{'id': 'I-PES-TIEMPOS-TECNICOS', 'preceptos': ['BOE-A-2020-2573::anexo.II/apend.I', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.1', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.2', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.9'], 'condicion': 'Totalizador continuo; unidades declaradas por prueba. En sensibilidad y variación, vueltas enteras además de >=3 minutos; estabilidad >=15 minutos; capacidad equivalente a 10 horas a máximo caudal. Condiciones de velocidad, caudal, carga y EMP se comprueban por separado.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.II/apend.I', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.1', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.2', 'BOE-A-2020-2573::anexo.II/apend.I/tabla.9'], 'conclusion': 'Totalizador continuo; unidades declaradas por prueba. En sensibilidad y variación, vueltas enteras además de >=3 minutos; estabilidad >=15 minutos; capacidad equivalente a 10 horas a máximo caudal. Condiciones de velocidad, caudal, carga y EMP se comprueban por separado.'}}, 'gas_ambito': {'entradas_validez': [], 'invariantes': [{'id': 'I-GAS-CAUDAL', 'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.3'], 'condicion': 'Qmax > 0, presión >= 0, unidades declaradas; conversor enlazado al contador cuyo Qmax se utiliza. No inferir equivalencia másica ausente.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.1', 'BOE-A-2020-2573::anexo.IV/ap.2', 'BOE-A-2020-2573::anexo.IV/ap.3', 'BOE-A-2016-5530::anexo.IX/art.1', 'BOE-A-2016-5530::anexo.IX/art.2', 'BOE-A-2016-5530::anexo.IX/apend.I'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_modulos': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.IX/art.1', 'BOE-A-2016-5530::anexo.IX/art.3', 'BOE-A-2016-5530::anexo.IX/art.4', 'BOE-A-2016-5530::anexo.IX/art.5', 'BOE-A-2016-5530::anexo.IX/apend.I', 'BOE-A-2016-5530::anexo.IX/apend.II', 'BOE-A-2016-5530::art.10.1', 'BOE-A-2016-5530::art.11.1'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_vida': {'entradas_validez': [], 'invariantes': [{'id': 'I-GAS-VIDA', 'preceptos': ['BOE-A-2020-2573::art.19.2'], 'condicion': 'Reinstalación no anterior a primera instalación; no reinicia origen. Etiqueta conserva datos originales; ausencia impide concluir reinstalación.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::art.19', 'BOE-A-2020-2573::art.19.2', 'BOE-A-2016-5530::anexo.III/art.3'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_regimen': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.3', 'BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::anexo.IV/ap.5', 'BOE-A-2016-5530::art.16'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_sustitucion': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::art.19.2', 'BOE-A-2020-2573::disp.transitoria.1', 'BOE-A-2020-2573::disp.transitoria.1.2'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_escalon': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_residual': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_ampliacion': {'entradas_validez': [], 'invariantes': [{'id': 'I-GAS-AMPLIACION', 'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::anexo.IV/apend.III'], 'condicion': 'Demostración y certificado pertenecen al mismo objeto y modalidad; documentación ausente o discordante no acredita ampliación. Fecha de verificación expresa; cálculo del nuevo fin pendiente de criterio de origen.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::anexo.IV/apend.III', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.5', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.6', 'BOE-A-2020-2573::art.19'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_aviso': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_retencion': {'entradas_validez': [], 'invariantes': [{'id': 'I-GAS-RETENCION', 'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III'], 'condicion': 'Fin de retención no anterior a verificación de muestra. Un plazo excesivo es incumplimiento, no imposibilidad.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_delegacion': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.4', 'BOE-A-2020-2573::anexo.IV/apend.II/tabla.1', 'BOE-A-2020-2573::anexo.IV/apend.III'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_emp': {'entradas_validez': [], 'invariantes': [{'id': 'I-GAS-EMP', 'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.7', 'BOE-A-2020-2573::art.14'], 'condicion': 'Certificado de primera periódica favorable identificado y fechado, o null si no existe; no posterior a actuación. Fin inicial determinado y explícito.'}], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/ap.7', 'BOE-A-2020-2573::anexo.IV/apend.I', 'BOE-A-2020-2573::anexo.IV/apend.II', 'BOE-A-2020-2573::anexo.IV/apend.II/tabla.1', 'BOE-A-2020-2573::anexo.IV/apend.II/tabla.2', 'BOE-A-2020-2573::anexo.IV/apend.II/tabla.3', 'BOE-A-2020-2573::anexo.IV/apend.II/tabla.4', 'BOE-A-2016-5530::anexo.IX/apend.I'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_muestreo': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.5', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.6'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_homogeneidad': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_repuesto': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::anexo.IV/apend.III', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.5', 'BOE-A-2020-2573::anexo.IV/apend.III/tabla.6'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_documentos': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2020-2573::art.11', 'BOE-A-2020-2573::art.12', 'BOE-A-2020-2573::art.17', 'BOE-A-2020-2573::art.18'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_bateria': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.IX/apend.I'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}, 'gas_residencial': {'entradas_validez': [], 'invariantes': [], 'revision_validez': {'preceptos': ['BOE-A-2016-5530::anexo.IX/apend.I'], 'conclusion': 'Contrato local gas: tipos, documentos y relaciones conocidas antes de calcular; no añade permisos de uso ni resuelve doctrina.'}}}

def declaracion_nueva(r):
    d = copy.deepcopy(CONTRATOS_NUEVOS[r['operador']])
    d['revision_validez']['preceptos'] = r['fuentes']
    return d

def validar_valor_nuevo(v, s, k):
    if v is None and s.get('nullable'):
        return
    t = s['tipo']
    if t == 'fecha':
        fecha(v)
    elif t == 'instante':
        instante(v)
    elif t == 'bool' and type(v) is not bool:
        raise Insuficiente('bool inválido: ' + k)
    elif t == 'numero' and (not numero_valido(v) or not (0 <= v if k.startswith('documento_censo.') else 0 <= v < 10000)):
        raise Insuficiente('número inválido: ' + k)
    elif t == 'int' and (type(v) is not int or not 1900 <= v <= 2200):
        raise Insuficiente('año inválido: ' + k)
    elif t == 'texto' and (not isinstance(v, str) or not v.strip()):
        raise Insuficiente('texto inválido: ' + k)
    elif t == 'enum' and (type(v) not in (str, int) or v not in s['valores']):
        raise Insuficiente('dominio/enum inválido: ' + k)
    elif t == 'lista':
        if not isinstance(v, list):
            raise Insuficiente('lista inválida: ' + k)
        if 'elementos' in s and any((x not in s['elementos'] for x in v)):
            raise Insuficiente('lista inválida: ' + k)
        if s.get('unicos') and len({volcar_json(x, sort_keys=True) for x in v}) != len(v):
            raise Insuficiente('lista inválida: ' + k)
    elif t == 'documento':
        if not isinstance(v, dict) or not isinstance(v.get('id'), str) or (not v['id'].strip()):
            raise Insuficiente('documento sin id: ' + k)
        for n, typ in s['estructura'].items():
            if n not in v:
                raise Insuficiente('documento incompleto: ' + k + '.' + n)
            sp = {'tipo': 'enum', 'valores': typ} if isinstance(typ, list) else {'tipo': typ}
            validar_valor_nuevo(v[n], sp, k + '.' + n)

def evaluar_nuevo(r, hechos):
    entradas = r['entradas'] + declaracion_validez(r)['entradas_validez']
    for e in entradas:
        if e['campo'] not in hechos:
            raise Insuficiente('falta ' + e['campo'])
        validar_valor_nuevo(hechos[e['campo']], e, e['campo'])
    h = {e['campo']: hechos[e['campo']] for e in entradas}
    op = r['operador']
    if op not in {'rc_puntos', 'gas_emp'}:
        validar_antecedentes(r, h)
    if op.startswith('agua_'):
        return evaluar_agua(r, h)
    if op.startswith('gas_'):
        return evaluar_gas(r, h)
    if op.startswith('pesaje_'):
        return evaluar_pesaje(r, h)
    validar_orden_taxi(r, h)
    return evaluar_taxi(r, h)
NUMEROS.update(seis=6, ocho=8, nueve=9, diez=10, trece=13)
CONSTANTES_OPERADOR.update({'agua_regimen': {'umbral_Q3': 'm3_h', 'primera_anos': 'anos', 'sucesiva_anos': 'anos'}, 'agua_etiqueta': {'anos': 'anos'}, 'agua_retencion': {'meses': 'meses'}, 'agua_documentos_plazo': {'dias_precinto': 'dias', 'dias_favorable': 'dias', 'dias_desfavorable': 'dias'}, 'pesaje_actos': {'dias_precinto': 'dias', 'dias_favorable': 'dias', 'dias_desfavorable': 'dias'}, 'admin_certificado': {'dias_precinto': 'dias', 'dias_favorable': 'dias'}, 'agua_alimentacion': {'meses': 'meses'}, 'agua_volumen': {'factor_escala': 'numero'}, 'agua_incertidumbre': {'cobertura': 'numero', 'divisor': 'numero'}, 'agua_sustitucion_cohorte': {'vida_anos': 'anos', 'anos': 'anos', 'inicio_sustitucion': 'fecha'}, 'agua_ampliacion_unidad': {'anos': 'anos'}, 'tx_k_inicial': {'tolerancia': 'porcentaje'}, 'tx_ensayos': {'medidas_horario': 'numero', 'medidas_km': 'numero', 'velocidad_km_h': 'numero'}, 'tx_plazo_tarifas': {'dias_habiles': 'dias_habiles'}, 'rc_puntos': {'anos': 'anos'}, 'rc_adaptada': {'anos': 'anos'}, 'rc_cohorte': {'publicacion': 'fecha', 'demora_entrada_dias': 'dias', 'ventana_anos': 'anos', 'regularizacion_anos': 'anos'}, 'pesaje_puente': {'max_especial_t': 'toneladas', 'incremento_porcentaje': 'porcentaje', 'intervalos_indicacion': 'numero'}, 'pesaje_certificados': {'ordinaria_anos': 'anos', 'limitacion_anos': 'anos', 'prorroga_anos': 'anos'}, 'pesaje_conservacion': {'anos': 'anos'}, 'pesaje_tiempos_tecnicos': {'estabilidad': 'minutos', 'capacidad': 'horas', 'sensibilidad': 'minutos'}, 'gas_ambito': {'q_vida': 'm3_h', 'q_periodica': 'm3_h', 'presion': 'MPa', 'vida_anos': 'anos', 'ampliacion_anos': 'anos'}, 'gas_vida': {'anos': 'anos'}, 'gas_sustitucion': {'vida_anos': 'anos', 'periodo_anos': 'anos', 'inicio': 'fecha', 'ano_1': 'anos', 'ano_2': 'anos', 'ano_3': 'anos', 'porcentaje_1': 'porcentaje', 'porcentaje_2': 'porcentaje', 'porcentaje_3': 'porcentaje'}, 'gas_escalon': {'inicio': 'fecha', 'ano_1': 'anos', 'ano_2': 'anos', 'ano_3': 'anos', 'porcentaje_1': 'porcentaje', 'porcentaje_2': 'porcentaje', 'porcentaje_3': 'porcentaje'}, 'gas_residual': {'porcentaje': 'porcentaje'}, 'gas_ampliacion': {'anos': 'anos'}, 'gas_aviso': {'meses': 'meses'}, 'gas_retencion': {'meses': 'meses'}, 'gas_documentos': {'dias_favorable': 'dias', 'dias_desfavorable': 'dias'}, 'gas_bateria': {'anos': 'anos', 'porcentaje_aviso': 'porcentaje'}, 'gas_residencial': {'ratio': 'numero'}, 'agua_emp': {'superior': 'porcentaje', 'inferior': 'porcentaje', 'servicio_superior': 'porcentaje', 'servicio_inferior': 'porcentaje', 'nulo': 'porcentaje'}})
DECISIONES_OPERADOR.update({'ampliacion': ['AG-P01'], 'agua_regimen': ['J01'], 'agua_prohibicion': ['J01'], 'agua_ampliacion_unidad': ['AG-P01'], 'gas_ampliacion': ['GAS-J01'], 'gas_emp': ['GAS-J02'], 'gas_sustitucion': ['GAS-J02'], 'gas_escalon': ['GAS-J02'], 'gas_residual': ['GAS-J02'], 'pesaje_puente': ['PES-P01'], 'pesaje_expediente_g': ['J07'], 'rc_cohorte': ['J04'], 'tx_plazo_tarifas': ['B2-CALENDARIOS'], 'agua_documentos_plazo': ['AG-P02'], 'admin_certificado': ['B2-CALENDARIOS'], 'pesaje_actos': ['B2-CALENDARIOS'], 'gas_documentos': ['GAS-J03']})

def valor_anclado(ancla):
    if ancla.get('formato') != 'numero_contextual':
        return valor_anclado_v6(ancla)
    lit = ancla['literal']
    i = ancla['inicio_numero']
    j = ancla['fin_numero']
    if type(i) is not int or type(j) is not int or (not 0 <= i < j <= len(lit)):
        raise Insuficiente('rango de extracción literal inválido')
    token = lit[i:j]
    palabras = dict(NUMEROS, ocho=8, diez=10, seis=6, nueve=9, trece=13, sexto=6, noveno=9, decimotercer=13)
    if token in palabras:
        v = palabras[token]
    elif re.fullmatch('[0-9]+(?: [0-9]{3})*(?:[.,][0-9]+)?', token):
        norm = token.replace(' ', '').replace(',', '.')
        v = Decimal(norm) if '.' in norm else int(norm)
    else:
        raise Insuficiente('número contextual no interpretable')
    if ancla.get('conversion') == 'kg_a_t':
        if ancla['unidad'] != 'toneladas' or v % 1000:
            raise Insuficiente('conversión exacta kg/t inválida')
        v = v // 1000
    elif 'conversion' in ancla:
        raise Insuficiente('conversión no soportada')
    return v

def evaluar_agua(r, hechos):
    op = r['operador']
    h = hechos
    c = r['constantes']
    if op == 'agua_ambito':
        if not h['tuberia_cerrada_seccion_llena']:
            return {'perfil': 'fuera_del_objeto_III', 'exencion_global': False}
        limpia = h['agua_limpia'] and h['uso'] in ['residencial', 'comercial', 'industria_ligera']
        return {'perfil': 'agua_limpia' if limpia else 'agua_otros' if h['temperatura'] == 'fria' else 'fuera_del_objeto_III', 'exencion_global': False}
    if op == 'agua_modulos':
        return {'combinacion_admitida': h['combinacion'] in [['B', 'D'], ['B', 'F'], ['H1']], 'via': h['via'], 'marcado': 'CE_y_M' if h['via'] == 'limpia_RD_VIII' else 'nacional', 'conformidad_efectiva': 'no_evaluada'}
    if op == 'agua_regimen':
        if h['tipo'] == 'otros':
            reg = f"periodica_{c['primera_anos']}_{c['sucesiva_anos']}"
        elif h['Q3_m3_h'] < c['umbral_Q3']:
            reg = f"vida_util_{c['primera_anos']}_ampliable_{c['sucesiva_anos']}"
        elif h['opcion_5_6'] == 'no_acreditada':
            reg = 'pendiente_eleccion_no_inventar'
        elif h['opcion_5_6'] == 'ejercida':
            reg = f"periodica_opcional_{c['primera_anos']}_{c['sucesiva_anos']}"
        else:
            reg = f"vida_util_{c['primera_anos']}_ampliable_{c['sucesiva_anos']}"
        q3 = h['tipo'] == 'limpia' and h['Q3_m3_h'] >= c['umbral_Q3']
        elegida = q3 and h['opcion_5_6'] == 'ejercida'
        reparacion = 'permitida_regimen_general_III_5' if elegida else 'pendiente_acreditar_opcion' if q3 and h['opcion_5_6'] == 'no_acreditada' else 'prohibida_vida_limpia' if q3 else 'examinar_regla_especifica'
        return {'regimen': reg, 'opcion_disponible': q3, 'reparacion_Q3': reparacion, 'autoriza_reparacion': elegida}
    if op == 'agua_prohibicion':
        return {'prohibicion_reparar_modificar': True if h['regimen'] == 'vida_limpia' else False if h['regimen'] == 'opcion_Q3' else None, 'estado': 'expresa_III_4_4' if h['regimen'] == 'vida_limpia' else 'reparacion_permitida_regimen_general_III_5' if h['regimen'] == 'opcion_Q3' else 'sin_prohibicion_general_en_III_5', 'verificacion_favorable_autoriza_reparar': False}
    if op == 'agua_preuso':
        ex = excepcion(h)
        if ex.startswith('pendiente'):
            return {'exigencia_previa': 'pendiente_documentacion', 'art8_habilitado': False, 'autoriza_uso_global': False}
        if ex == 'concurre_en_hipotesis_documental':
            s = 'excepcion_legal_verificacion_no_necesaria'
        else:
            s = 'superada_por_esta_causa' if h['resultado_verificacion'] == 'favorable' else 'debe_superar_antes_servicio'
        return {'exigencia_previa': s, 'art8_habilitado': False, 'autoriza_uso_global': False}
    if op == 'agua_delegacion':
        d = h['documento_delegacion']
        valida = d is not None and d['firmado_por_escrito']
        return {'via': 'delegacion_escrita_gestor' if h['propietario_consumidor'] and valida else 'gestor_comunica_administracion_fija_pautas' if h['propietario_consumidor'] else 'fuera_supuesto_consumidor', 'delegacion_automatica': False}
    if op == 'agua_etiqueta':
        if h['reinstalacion'] is not None and h['reinstalacion'] < h['primera_instalacion']:
            raise Insuficiente('I-AG-INSTALACION: reinstalacion anterior a primera')
        return {'reinstalable_por_etiqueta': None if h['reinstalacion'] is None else h['etiqueta_original_preservada'], 'fin_vida_base': desplazar(h['primera_instalacion'], anos=c['anos']), 'registro_admisible_si_no_cabe_etiqueta': not h['posible_colocar_etiqueta'], 'autoriza_uso_global': False}
    if op == 'agua_retencion':
        a, b = (h['verificacion_muestreo'], h['limite_fijado'])
        if b is not None and b < a:
            raise Insuficiente('I-AG-RETENCION: limite anterior a verificacion')
        return {'plazo_fijado': b is not None, 'no_excede_mes': None if b is None else b <= desplazar(a, meses=c['meses']), 'muestra_debe_mantenerse_inalterada': b is not None}
    if op == 'agua_intervencion_muestra':
        return {'intervencion_admisible_en_muestra': h['actuacion'] in ['ninguna', 'enjuague'], 'enjuague_no_autoriza_reparacion': True}
    if op == 'agua_repuesto':
        causa = h['causa'] in ['danado_exterior', 'precinto_roto', 'no_localizado', 'mal_presentado']
        ok = causa and h['antes_inicio'] and h['justo_tras_visual'] and (not h['reemplazo_previo']) and h['seleccion_aleatoria'] and h['dentro_numero_plan']
        return {'reemplazo_admisible': ok, 'solicitud_rechazada_si_no_completable': not h['muestra_completable'], 'aceptacion_estadistica': 'no_ejecutada'}
    if op == 'agua_plan':
        return {'prohibicion_cambiar_por_inicio': h['verificacion_iniciada'], 'plan_ya_seleccionado': h['plan'], 'tablas_1_2_vinculantes': True, 'ampliacion_tabla_mas_35000': 'remision_UNE_ISO_2859_2_2012_no_ejecutada'}
    if op == 'agua_lote':
        rechazo = h['resultado_lote'] == 'rechazado'
        return {'fuera_servicio_todo_lote': rechazo, 'fuera_servicio_unidad': rechazo or not h['unidad_conforme'], 'etiqueta_unidad': not rechazo and h['unidad_conforme'] and h['unidad_en_muestra'], 'comunicar_ampliacion_titular': not rechazo and (not h['unidad_en_muestra']), 'comunicar_resultado_administracion': True}
    if op == 'agua_homogeneidad':
        a, b = (h['contador_A'], h['contador_B'])
        if a['regimen_1988'] != b['regimen_1988']:
            return {'lote_homogeneo_requisitos_minimos': False, 'calculo_estadistico': 'no_ejecutado'}
        claves = ['ano_fabricacion', 'DN', 'modelo_marca', 'explotacion']
        claves += ['clase', 'Qn'] if a['regimen_1988'] else ['Q3', 'ratio_Q3_Q1']
        return {'lote_homogeneo_requisitos_minimos': all((a[k] == b[k] for k in claves)), 'calculo_estadistico': 'no_ejecutado'}
    if op == 'agua_documentos_plazo':
        valor = {'precinto_no_cumple_funcion': c['dias_precinto'], 'favorable_reparacion': c['dias_favorable'], 'favorable_periodica': c['dias_favorable'], 'desfavorable_reparacion': c['dias_desfavorable'], 'desfavorable_periodica': c['dias_desfavorable']}[h['evento']]
        return {'maximo_dias': valor, 'origen_evento': h['fecha_evento'], 'fecha_limite': None, 'estado_fecha': 'pendiente_calendario_competente', 'comunicacion': 'administracion_electronica' if valor in [c['dias_precinto'], c['dias_desfavorable']] else 'certificado_verificacion'}
    if op == 'agua_ensayos':
        return {'impide_favorable': not h['examen_administrativo_superado'] or not h['todos_ensayos_superados'], 'ensayo_tecnico_ejecutado': False}
    if op == 'agua_emp':
        if h['zona'] == 'nulo' and h['fase'] == 'conformidad':
            return {'EMP_porcentaje_absoluto': None, 'fase': 'conformidad', 'regla_mismo_signo': 'no_aplicada_en_esta_regla', 'ensayos': 'consultar_ensayo_ausencia_flujo_no_inferir_EMP_de_IV'}
        base = c['superior'] if h['zona'] == 'superior' else c['inferior']
        emp = base if h['fase'] == 'conformidad' else c['servicio_superior'] if h['zona'] == 'superior' else c['servicio_inferior']
        if h['zona'] == 'nulo':
            emp = c['nulo']
        return {'EMP_porcentaje_absoluto': emp, 'fase': h['fase'], 'regla_mismo_signo': 'al_menos_un_error_inferior_mitad_EMP' if h['fase'] == 'en_servicio' else 'no_aplicada_en_esta_regla', 'ensayos': 'no_ejecutados'}
    if op == 'agua_caudales_1988':
        return {'equivalencia': ['Qmax', 'Qn', 'Qt', 'Qmin'] if h['puesto_servicio_orden_1988'] else ['Q4', 'Q3', 'Q2', 'Q1'], 'solo_referencias_apendice_IV': True}
    if op == 'agua_alimentacion':
        return {'reserva_minimo_mes_exigible': h['alimentacion_externa'], 'cumple_reserva_declarada': h['reserva_meses'] >= c['meses'] if h['alimentacion_externa'] else None, 'inscribir_fecha_limite_fuente_interna': True, 'cumplimiento_fisico': 'no_ensayado'}
    if op == 'agua_volumen':
        minimo = max(h['volumen_un_minuto'], c['factor_escala'] * h['intervalo_escala'])
        d = h['demostracion_incertidumbre']
        excepcion_volumen = d is not None and d['cumple_punto_2_2']
        return {'minimo_ordinario': minimo, 'cumple_solo_condicion_volumen': h['volumen_ensayo'] >= minimo or excepcion_volumen, 'certificacion_tecnica': False}
    if op == 'agua_incertidumbre':
        emp = tabla_emp(r)[h['zona_EMP']]
        if h['EMP'] != emp:
            raise Insuficiente('I-EMP-ANCLADO: EMP ajeno a tabla normativa de zona')
        return {'cumple_solo_condicion_incertidumbre': h['factor_cobertura'] == c['cobertura'] and h['incertidumbre_expandida'] * c['divisor'] <= emp, 'certificacion_tecnica': False}
    if op == 'agua_mismo_signo':
        return {'condicion_adicional_aplicable': h['todos_mismo_signo'], 'cumple_solo_condicion_adicional': h['algun_error_inferior_mitad_EMP'] if h['todos_mismo_signo'] else None, 'certificacion_tecnica': False}
    if op == 'agua_ajuste_evaluacion':
        return {'ajuste_durante_ensayos_prohibido': h['ajuste'], 'repetir_todos_ensayos_previos': h['modificacion'], 'conformidad_efectiva': 'no_evaluada'}
    if op == 'agua_comunicacion_inmediata':
        s = h['supuesto']
        return {'plazo': 'tres_dias_maximo' if s == 'precinto_no_cumple_funcion' else 'inmediato', 'destinatario': 'titular' if s == 'incumplimiento_administrativo' else 'administracion_competente', 'continuar_control_solicitado': s == 'incumplimiento_administrativo'}
    if op == 'agua_conservacion_muestra':
        return {'cumple_solo_condiciones_representacion_conservacion': all(h.values()), 'aceptacion_lote': 'no_evaluada'}
    if op == 'agua_sustitucion_cohorte':
        filtro = {'cohorte_transitoria': fecha(desplazar(h['primera_instalacion'], anos=c['vida_anos'])) <= fecha(desplazar(c['inicio_sustitucion'], anos=c['anos']))}
        aplica = h['en_servicio_2020_10_24'] and h['regimen'] == 'vida_limpia' and filtro['cohorte_transitoria']
        return {'cohorte_transitoria_completa': aplica, 'referencia_fin_sustitucion': desplazar(c['inicio_sustitucion'], anos=c['anos']) if aplica else None, 'autoriza_uso_hasta_fecha': False}
    if op == 'agua_ampliacion_unidad':
        a, b = (h['informe_gestor_unidad'], h['certificado_unidad'])
        if a is None or b is None:
            return {'ampliacion_quinquenal': None, 'estado': 'pendiente_documentacion', 'fin_ampliado': None}
        ok = a['instrumento'] == b['instrumento'] and a['cumple_criterios'] and b['organismo_autorizado'] and (b['resultado'] == 'favorable')
        return {'ampliacion_quinquenal': ok, 'estado': 'origen_fin_vigente_decidido_sin_uso_durante_demora', 'fin_ampliado': desplazar(h['fin_vigente'], anos=c['anos']) if ok else None}

def validar_orden_taxi(r, h):
    op = r['operador']
    if op == 'reparacion' and fecha(h['certificado_previo']) > fecha(h['fecha_reparacion_material']):
        raise Insuficiente('QH1: certificado previo posterior a reparacion')
    if op == 'servicio' and h['documento_nueva_solicitud'] is not None and (h['fecha_desfavorable'] is not None):
        if instante(h['documento_nueva_solicitud']['momento_solicitud']).date() < fecha(h['fecha_desfavorable']):
            raise Insuficiente('QH2: nueva solicitud anterior al desfavorable')
    if op == 'tx_plazo_tarifas' and fecha(h['fecha_solicitud']) < fecha(h['fecha_cambio']):
        raise Insuficiente('solicitud presentada como posterior anterior al cambio')
    if op == 'rc_adaptada' and fecha(h['fecha_verificacion_modificacion']) < fecha(h['fecha_adaptacion']):
        raise Insuficiente('verificacion anterior a adaptacion')
    if op == 'rc_cohorte' and (not (fecha(h['fecha_instalacion']) <= fecha(h['primera_utilizacion']) <= fecha(h['fecha_consulta']) and h['fecha_consulta'] >= entrada_vigor(r['constantes']))):
        raise Insuficiente('cronologia incoherente de instalacion y servicio')
    if op in {'rc_puntos', 'rc_etiquetas', 'rc_alcance'}:
        ps = h['puntos_instalados']
        if not ps or any((not isinstance(p, str) or not p.strip() for p in ps)) or len(set(ps)) != len(ps):
            raise Insuficiente('censo de puntos vacio o duplicado')
    if op == 'rc_puntos':
        vistos = []
        for d in h['certificados_periodica']:
            if not isinstance(d, dict) or set(d) != {'id', 'estacion', 'punto', 'fecha'} or any((not isinstance(x, str) or not x.strip() for x in d.values())):
                raise Insuficiente('certificado de punto incompleto')
            if d['estacion'] != h['estacion'] or d['punto'] not in h['puntos_instalados'] or d['punto'] in vistos:
                raise Insuficiente('identidad de punto/estacion incorrecta o duplicada')
            if fecha(d['fecha']) > fecha(h['fecha_consulta']):
                raise Insuficiente('certificado periodico futuro')
            vistos.append(d['punto'])
        validar_antecedentes(r, h)
        if h['fecha_reparacion_punto'] is not None and fecha(h['fecha_reparacion_punto']) > fecha(h['fecha_consulta']):
            raise Insuficiente('reparacion presentada como realizada es futura')
    if op == 'tx_instalacion' and h['documento'] is not None:
        if h['documento']['vehiculo'] != h['vehiculo'] or h['documento']['instrumento'] != h['instrumento']:
            raise Insuficiente('documento de instalacion de otro vehiculo/instrumento')
    if op == 'tx_k_inicial' and h['informe_k']['instrumento'] != h['instrumento']:
        raise Insuficiente('informe k de otro instrumento')
    if op == 'tx_k_inicial':
        n = h['informe_k']['error_absoluto_porcentaje']
        if not numero_valido(n) or n < 0:
            raise Insuficiente('error absoluto k no es numero finito no negativo')
    if op == 'rc_adaptacion' and h['certificado']['estacion'] != h['estacion']:
        raise Insuficiente('certificado de adaptacion de otra estacion')
    if op in {'rc_alcance', 'rc_etiquetas'} and h['punto_intervenido'] not in h['puntos_instalados']:
        raise Insuficiente('punto intervenido no pertenece al conjunto')

def evaluar_taxi(r, h):
    c = r['constantes']
    op = r['operador']
    if op == 'admin_certificado':
        ev = h['evento']
        maximo = {'precintado_no_cumple_funcion': c['dias_precinto'], 'verificacion_favorable': c['dias_favorable'], 'indicio_manipulacion': None, 'incumplimiento_administrativo': None}[ev]
        return {'origen': h['fecha_evento'], 'obligacion': {'precintado_no_cumple_funcion': 'informar_electronicamente_administracion', 'verificacion_favorable': 'emitir_certificado_verificacion', 'indicio_manipulacion': 'comunicar_administracion', 'incumplimiento_administrativo': 'poner_en_conocimiento_titular_sin_interrumpir_verificacion'}[ev], 'maximo_dias': maximo, 'inmediatez': maximo is None, 'fecha_limite': None, 'calendario': 'no_calculado'}
    if op == 'tx_modulos':
        return {'combinacion_admitida': h['combinacion'] in [['B', 'D'], ['B', 'F'], ['H1']], 'regimen': 'RD_anexo_XIII'}
    if op == 'tx_instalacion':
        d = h['documento']
        primera = h['primera_verificacion']
        if h['via'] == 'instrucciones_fabricante' and (not primera):
            return {'examen_documental_instalacion_satisfecho': None, 'exigencia': 'revisar_requisitos_generales_sucesiva_sin_extender_certificado_primera', 'otros_requisitos': 'pendientes_examen_instalacion'}
        ok = d is not None and (d['tipo'] == 'documentacion_reforma' and d['disponible'] and (not primera or d['anotada']) if h['via'] == 'reforma' else d['tipo'] == 'certificado_reparador_instrucciones_fabricante' and d['disponible'])
        return {'examen_documental_instalacion_satisfecho': bool(ok), 'exigencia': 'documentacion_reforma_disponible_y_anotacion_primera' if h['via'] == 'reforma' else 'certificado_reparador_primera', 'otros_requisitos': 'pendientes_examen_instalacion'}
    if op == 'tx_solicitud':
        etiqueta = {'reinstalacion': 'reinstalación taxímetro', 'tarifas': 'Cambio de tarifas'}[h['actuacion']]
        return {'verificacion_despues_modificacion': True, 'mencion_exigida': etiqueta, 'mencion_correcta': h['mencion'] == etiqueta, 'nueva_solicitud_exigida': True}
    if op == 'tx_k_inicial':
        return {'calculo_inicial_k_conforme_en_hipotesis': h['informe_k']['autor_reparador'] and h['informe_k']['error_absoluto_porcentaje'] <= c['tolerancia'], 'unidad': 'impulsos_por_km', 'otros_ensayos': 'pendientes'}
    if op == 'tx_ensayos':
        return {'tarifas_a_ensayar': 'una' if h['version_programa'] is not None and h['version_programa']['facilitada_por_responsable'] else 'cada_tarifa', 'minimo_medidas_horario': c['medidas_horario'], 'minimo_medidas_kilometrico': c['medidas_km'], 'velocidad_kilometrico': f"superior_{c['velocidad_km_h']}_kmh"}
    if op == 'tx_plazo_tarifas':
        return {'origen': h['fecha_solicitud'], 'maximo': c['dias_habiles'], 'unidad': 'dias_habiles', 'fecha_limite': None, 'estado': 'pendiente_calendario_competente', 'prorroga_uso_titular': False}
    if op == 'rc_ambito':
        return {'candidato_anexo_XX': h['destino_documentado'] == 'transaccion_comercial_energia_vehiculo', 'otro_uso': 'no_concluir_exencion_global'}
    if op == 'rc_puntos':
        faltan = sorted(set(h['puntos_instalados']) - {d['punto'] for d in h['certificados_periodica']})
        if faltan:
            return {'estado': 'pendiente_antecedentes_puntos', 'faltan': faltan, 'limite_exclusivo': None, 'fecha_propuesta_cumple': None}
        limite = min((desplazar(d['fecha'], anos=c['anos']) for d in h['certificados_periodica']))
        return {'estado': 'referencia_calculada', 'limite_exclusivo': limite, 'exigencia': 'realizar_antes_del_limite', 'reparacion_un_punto_no_reinicia': True, 'fecha_propuesta_cumple': h['fecha_verificacion_propuesta'] < limite}
    if op == 'rc_alcance':
        unico = h['unico_punto_intervenido'] and h['solo_precintos_de_ese_punto']
        return {'disparador_XX5': h['afecta_parte_metrologicamente_relevante'], 'ensayos_limitables_al_punto': h['afecta_parte_metrologicamente_relevante'] and unico, 'plazo_conjunto_no_se_altera': True if unico else None, 'resto': 'si_falta_condicion_examinar_conjunto_no_presuponer_exencion'}
    if op == 'rc_adaptacion':
        d = h['certificado']
        ok = all((d[k] for k in ['reparador_RCM', 'autorizacion_titular_tipo', 'examen_tipo_en_vigor', 'mismos_elementos_marca_modelo', 'mismo_diseno_construccion', 'precintado_todos_puntos', 'placa_e_inscripciones']))
        return {'adaptacion_documental_completa': ok, 'verificacion_despues_modificacion_exigida': True, 'no_autoriza_uso_global': True}
    if op == 'rc_adaptada':
        return {'origen': h['fecha_adaptacion'], 'referencia_primera': desplazar(h['fecha_adaptacion'], anos=c['anos']), 'certificado_modificacion_no_sustituye_origen': True}
    if op == 'rc_cohorte':
        inst, uso = (h['fecha_instalacion'], h['primera_utilizacion'])
        if inst in [entrada_vigor(c), desplazar(entrada_vigor(c), anos=c['ventana_anos'])] or uso == entrada_vigor(c):
            return {'estado': 'pendiente_frontera', 'cohorte': None, 'referencia_regularizacion': None}
        anterior = uso < entrada_vigor(c)
        ventana = entrada_vigor(c) < inst < desplazar(entrada_vigor(c), anos=c['ventana_anos']) and (not h['evaluacion_conformidad'])
        return {'estado': 'referencias_derivadas_no_autorizacion', 'cohorte': 'en_servicio_entrada_ap8' if anterior else 'instalacion_sin_evaluacion_ap9' if ventana else 'fuera_cohortes_especiales', 'referencia_regularizacion': desplazar(entrada_vigor(c), anos=c['regularizacion_anos']) if anterior or ventana else None, 'fin_ventana_instalar_sin_evaluacion': desplazar(entrada_vigor(c), anos=c['ventana_anos']), 'entrada': entrada_vigor(c)}
    if op == 'rc_etiquetas':
        parcial = h['modalidad'] == 'reparacion_punto_unico'
        return {'ubicacion_etiquetas': [h['punto_intervenido']] if parcial else h['puntos_instalados'], 'comprobar_interferencia': h['suministro_simultaneo'], 'etiqueta_estacion_no_sustituye_puntos': True}
    raise AssertionError(op)

def evaluar_pesaje(r, hechos):
    c = r['constantes']
    h = {s['campo']: hechos[s['campo']] for s in r['entradas'] + r['entradas_validez']}
    op = r['operador']
    if op == 'pesaje_modulos':
        tech = h['tecnologia']
        combos = [['B', 'D'], ['B', 'F'], ['G']]
        if tech == 'no_automatico':
            if not h['dispositivos_electronicos'] and (not h['resortes_equilibran_carga']):
                combos += [['D1'], ['F1']]
        else:
            combos += [['H1']]
            if tech in ['mecanico', 'electromecanico']:
                combos += [['B', 'E']]
            if tech == 'mecanico':
                combos += [['D1'], ['F1']]
        return {'combinacion_admitida': h['combinacion'] in combos, 'alcance': 'solo_opciones_no_certifica_instrumento'}
    if op == 'pesaje_expediente_g':
        d = h['expediente_usos']
        estados = [d['uso_' + k] for k in 'abcdef']
        presentes = ['masa_para_transaccion_comercial', 'masa_para_tasa_arancel_impuesto_prima_multa_remuneracion_indemnizacion_canon', 'masa_para_ley_reglamento_o_peritaje_judicial', 'pesada_pacientes_control_diagnostico_tratamiento', 'masa_preparacion_farmacia_o_fabricacion_analisis_laboratorio_farmaceutico', 'precio_masa_venta_directa_o_elaboracion_preenvasados']
        if any((x in presentes for x in estados)):
            regimen = 'examinar_af'
        elif 'no_consta' in estados:
            regimen = 'pendiente_documentacion_usos'
        else:
            regimen = 'g_inscripciones_sin_marcado_RD'
        return {'regimen': regimen, 'servicio_J07': 'regimen_tecnico_documental_sin_analogia' if (esg if op == 'campo_g' else regimen == 'g_inscripciones_sin_marcado_RD') else 'examinar_ambito_af_o_documentacion', 'exencion_global': False}
    if op == 'pesaje_puente':
        if not 0 < h['nuevo_max_t'] <= h['max_original_t'] or h['limite_vial_t'] <= 0 or h['e_t'] <= 0:
            raise Insuficiente('I-PUENTE: alcances/limite incoherentes')
        especial = h['max_original_t'] > c['max_especial_t']
        reduccion = h['nuevo_max_t'] < h['max_original_t']
        doc = h['peticion_escrita']
        peticion = doc is not None and doc['titular'] == h['titular'] and (doc['instrumento'] == h['instrumento'])
        condiciones = especial and reduccion and peticion
        exacto = h['nuevo_max_t'] <= h['limite_vial_t'] * (1 + c['incremento_porcentaje'] / 100)
        via = condiciones and exacto
        return {'via_especial_reduccion': via, 'otro_valor_de_reduccion': 'supera_limite_vial_mas_10_por_ciento' if condiciones and (not exacto) else None, 'verificacion_tras_modificacion_exigida': especial and reduccion, 'etiqueta_limitacion_tras_favorable': especial and reduccion and (h['resultado_verificacion'] == 'favorable'), 'limite_indicacion_t': h['nuevo_max_t'] + c['intervalos_indicacion'] * h['e_t'] if especial and reduccion else None, 'alcance': 'no_autoriza_modificacion_real'}
    if op == 'pesaje_lugar':
        ajeno = not h['desmontaje_transporte'] and (not h['montaje_o_intervencion']) and (h['gravedad_considerada'] or not h['sensible_gravedad'])
        if h['dos_fases'] and (not h['sensible_gravedad']):
            raise Insuficiente('I-LUGAR: dos fases por gravedad sin sensibilidad')
        return {'evaluacion_completa_fuera_uso_posible': ajeno, 'segunda_fase_en_lugar_o_zona_uso': h['dos_fases'], 'cierre_segunda_fase_no_impide_marcado': not h['dos_fases'] or h['segunda_fase_terminada'], 'alcance': 'solo_condiciones_lugar_y_fase_no_conformidad_integral'}
    if op == 'pesaje_actos':
        e = h['evento']
        n = {'favorable': c['dias_favorable'], 'desfavorable': c['dias_desfavorable'], 'precinto_no_funcional': c['dias_precinto'], 'incumplimiento_admin': 0, 'indicio_fraude': 0}[e]
        actos = {'favorable': ['emitir_certificado'], 'desfavorable': ['etiqueta_inhabilitacion', 'informe_desfavorable', 'comunicacion_electronica_administracion'], 'precinto_no_funcional': ['informar_electronicamente_administracion'], 'incumplimiento_admin': ['informar_titular_sin_interrumpir_verificacion'], 'indicio_fraude': ['comunicar_administracion']}[e]
        return {'actos': actos, 'maximo_dias': n if n else None, 'inmediatez': n == 0, 'origen': h['fecha_evento'], 'fecha_maxima': None, 'estado_fecha': 'pendiente_calendario_y_computo' if n else 'actuacion_inmediata', 'valor_afirmado_correcto': h['dias_afirmados'] == n}
    if op == 'pesaje_certificados':
        d = h['acto_certificado']
        reg = h['regimen']
        clase = d['clase_acto']
        if reg == 'no_automatico_B':
            anos = {'emision_ordinaria': c['ordinaria_anos'], 'renovacion_concedida': c['ordinaria_anos'], 'limitacion_dos_concedida': c['limitacion_anos'], 'prorroga_tres_concedida': c['prorroga_anos']}[clase]
        elif clase in ['limitacion_dos_concedida', 'prorroga_tres_concedida']:
            raise Insuficiente('I-CERT: especialidad VI no trasladable a automaticos')
        else:
            anos = c['ordinaria_anos']
        if clase == 'prorroga_tres_concedida' and d['fecha_origen'] != h['fin_certificado_anterior']:
            raise Insuficiente('I-CERT: prorroga no enlaza fin anterior')
        return {'anos_acto': anos, 'referencia': d['fecha_origen'], 'fin_referencia': desplazar(d['fecha_origen'], anos=anos), 'renovacion_automatica': False, 'periodica_servicio': 'reloj_distinto'}
    if op == 'pesaje_conservacion':
        if h['regimen'] == 'no_automatico' and h['modulo'] in ['E', 'H1']:
            raise Insuficiente('I-CONSERVACION: modulo ajeno al regimen no automatico')
        if h['sujeto'] == 'fabricante':
            return {'origen': h['introduccion_mercado'], 'fin_minimo_referencia': desplazar(h['introduccion_mercado'], anos=c['anos']), 'motivo': 'diez_anos_desde_mercado'}
        if h['modulo'] not in ['B', 'H1'] or (h['regimen'] == 'no_automatico' and h['modulo'] == 'H1'):
            raise Insuficiente('I-CONSERVACION: supuesto organismo fuera de contrato')
        return {'origen': None, 'fin_minimo_referencia': h['fin_validez_certificado'], 'motivo': 'organismo_hasta_fin_validez_certificado'}
    if op == 'pesaje_ensayo':
        rem = {'no_automatico': 'UNE-EN 45501 en vigor', 'seleccionadora': 'OIML R 51', 'llenado': 'OIML R 61', 'discontinuo': 'OIML R 107', 'continuo': 'OIML R 50', 'ferrocarril': 'OIML R 106'}[h['familia']]
        j = h['justificacion']
        sim = h['simulacion']
        if sim == 'sin_simulacion':
            aceptable = None
        elif h['familia'] == 'no_automatico':
            aceptable = None
        elif j is None:
            aceptable = None
        elif sim == 'material_alternativo':
            aceptable = j['similares'] and j['justificacion_tecnica'] and j['justificacion_economica']
        else:
            aceptable = j['constructivamente_no_seguro_economico']
        return {'remision_ensayos': rem, 'simulacion_cumple_condicion_representada': aceptable, 'ensayos_ejecutados': False, 'compatibilidad_modulos': 'comprobar_cuando_pertinente'}
    if op == 'pesaje_tiempos_tecnicos':
        tipo = h['prueba']
        limite = {'estabilidad_cero': c['estabilidad'], 'sensibilidad_cero': c['sensibilidad'], 'variacion_cero': c['sensibilidad'], 'capacidad_totalizador': c['capacidad']}[tipo]
        vueltas = h['vueltas_enteras'] if tipo in ['sensibilidad_cero', 'variacion_cero'] else True
        return {'umbral': limite, 'unidad': 'horas' if tipo == 'capacidad_totalizador' else 'minutos', 'cumple_solo_tiempo_y_vueltas': h['duracion'] >= limite and vueltas, 'otros_requisitos_tecnicos': 'pendientes_de_ensayo'}
    raise Insuficiente('operador auxiliar desconocido: ' + op)

def evaluar_gas(r, hechos):
    op = r['operador']
    c = r['constantes']
    h = {s['campo']: hechos[s['campo']] for s in r['entradas']}
    if op == 'gas_ambito':
        q = h['qmax_m3_h']
        if q <= 0:
            raise Insuficiente('I-GAS-CAUDAL: Qmax no positivo')
        doc, aso = (h['documento_caudal'], h['documento_asociacion'])
        if h['tipo'] == 'conversor':
            if aso is None or not aso['compatible'] or aso['conversor'] != h['instrumento'] or (aso['contador'] != doc['instrumento']):
                return {'regimen': 'pendiente_asociacion_documental', 'periodos_anos': None}
        elif doc['instrumento'] != h['instrumento']:
            return {'regimen': 'pendiente_identidad_caudal', 'periodos_anos': None}
        if doc['unidad_original'] == 'kg/h' and doc['conversion'] != 'aportada':
            return {'regimen': 'pendiente_equivalencia_masica', 'periodos_anos': None}
        if doc['unidad_original'] == 'm3/h' and doc['conversion'] != 'no_necesaria':
            raise Insuficiente('I-GAS-CAUDAL: declaración de unidades contradictoria')
        if q <= c['q_vida']:
            return {'regimen': 'vida_util_IV4', 'periodos_anos': [c['vida_anos'], c['ampliacion_anos']]}
        if q <= c['q_periodica'] and (not (h['red_transporte'] and h['presion_MPa'] >= c['presion'])):
            return {'regimen': 'periodica_IV5a7', 'periodos_anos': 'tabla_1_segun_instrumento_no_heredar_contador'}
        return {'regimen': 'fuera_tramos_IV3_no_exencion_global', 'periodos_anos': None}
    if op == 'gas_modulos':
        dentro = h['uso'] in ['residencial', 'comercial', 'industria_ligera']
        return {'ambito_RD_IX': dentro, 'opcion_admitida': dentro and h['combinacion'] in [['B', 'D'], ['B', 'F'], ['H1']], 'cumplimiento_efectivo': 'no_ensayado'}
    if op == 'gas_vida':
        if h['reinstalacion'] is not None and fecha(h['reinstalacion']) < fecha(h['primera_instalacion']):
            raise Insuficiente('I-GAS-VIDA: reinstalación anterior a primera instalación')
        e = h['etiqueta_original']
        if e is not None and e['primera_instalacion'] != h['primera_instalacion']:
            raise Insuficiente('I-GAS-VIDA: datos originales discordantes')
        return {'fin_vida_base': desplazar(h['primera_instalacion'], anos=c['anos']), 'reinstalacion_no_reinicia': True, 'condicion_documental_reinstalacion': 'no_hay_reinstalacion' if h['reinstalacion'] is None else 'conserva_datos_originales' if e is not None else 'pendiente_etiqueta_original_no_reinstalar'}
    if op == 'gas_regimen':
        vida = h['regimen'] == 'vida_util_IV4'
        return {'periodica_ordinaria': not vida, 'prohibicion_especifica_IV4_3': vida, 'verificacion_art8_no_elimina_prohibicion': vida}
    if op == 'gas_sustitucion':
        fin = desplazar(h['primera_instalacion'], anos=c['vida_anos'])
        return {'cohorte_13_anos': fin <= desplazar(c['inicio'], anos=c['periodo_anos']), 'origen_calendario': c['inicio'], 'referencias': [[desplazar(c['inicio'], anos=c['ano_1']), c['porcentaje_1']], [desplazar(c['inicio'], anos=c['ano_2']), c['porcentaje_2']], [desplazar(c['inicio'], anos=c['periodo_anos']), c['porcentaje_3']]] if fin <= desplazar(c['inicio'], anos=c['periodo_anos']) else [], 'autoriza_uso_hasta_fecha': False, 'frontera_antes_final_ano': 'dia_exacto_antes_aniversario_censo_documentado_requerido'}
    if op == 'gas_escalon':
        if h['porcentaje_sustituido'] > c['porcentaje_3']:
            raise Insuficiente('porcentaje del parque >100')
        ano = h['ano_escalon']
        umbral = {c['ano_1']: c['porcentaje_1'], c['ano_2']: c['porcentaje_2'], c['ano_3']: c['porcentaje_3']}[ano]
        limite = desplazar(c['inicio'], anos=ano)
        dc, corte = (h['documento_censo'], h['fecha_consulta'])
        acreditado = None
        if dc is not None:
            total, sustituidos = (dc['total'], dc['sustituidos'])
            if total <= 0 or sustituidos < 0 or sustituidos > total or (total != int(total)) or (sustituidos != int(sustituidos)):
                raise Insuficiente('I-GAS-CENSO: conteos enteros de parque invalidos')
            if corte is None or dc['fecha_corte'] != corte:
                raise Insuficiente('I-GAS-CENSO: fecha de corte no vinculada')
            if fecha(corte) < fecha(c['inicio']):
                raise Insuficiente('I-GAS-CENSO: corte anterior al inicio del calendario')
            acreditado = sustituidos * 100 >= total * umbral and fecha(corte) < fecha(limite)
        return {'origen': c['inicio'], 'referencia_aniversario': limite, 'umbral_porcentaje': umbral, 'satisface_solo_umbral_numerico': h['porcentaje_sustituido'] >= umbral, 'cumplimiento_temporal': 'censo_documentado_y_dia_exacto' if dc is not None else 'pendiente_fecha_y_censo_documentado', 'cumplimiento_documentado': acreditado}
    if op == 'gas_residual':
        if h['porcentaje_sin_sustituir'] > 100:
            raise Insuficiente('porcentaje del parque >100')
        dc = h['documento_censo']
        documental = None
        if dc is not None:
            total, sustituidos = (dc['total'], dc['sustituidos'])
            if total <= 0 or sustituidos < 0 or sustituidos > total or (total != int(total)) or (sustituidos != int(sustituidos)):
                raise Insuficiente('I-GAS-CENSO: conteos enteros de parque invalidos')
            documental = (total - sustituidos) * 100 <= total * c['porcentaje'] and h['causas_no_imputables']
        return {'condicion_residual_2_por_ciento': h['porcentaje_sin_sustituir'] <= c['porcentaje'] and h['causas_no_imputables'], 'condicion_residual_documentada': documental, 'alcance': 'solo_excepcion_al_final_ano13_no_ampliacion_individual'}
    if op == 'gas_ampliacion':
        d, c = (h['demostracion_distribuidora'], h['certificado'])
        if d is None or c is None:
            return {'ampliacion_quinquenal': None, 'estado': 'pendiente_documentacion', 'fin_ampliado': None}
        if d['objeto'] != c['objeto'] or d['modalidad'] != c['modalidad']:
            return {'ampliacion_quinquenal': None, 'estado': 'pendiente_identidad_objeto_modalidad', 'fin_ampliado': None}
        fecha(c['fecha_verificacion'])
        ok = d['aplica_apendice_III'] and c['resultado'] == 'favorable' and c['organismo_autorizado']
        fin = h['fin_vigente']
        return {'ampliacion_quinquenal': ok, 'estado': ('origen_fin_vigente_decidido_sin_uso_durante_demora' if fin is not None else 'pendiente_documentar_fin_vigente') if ok else 'no_acredita_ampliacion', 'fin_ampliado': desplazar(fin, anos=r['constantes']['anos']) if ok and fin is not None else None}
    if op == 'gas_aviso':
        intacto = not h['lote_modificado']
        limite = desplazar(h['siguiente_verificacion'], meses=-c['meses'])
        return {'regla_tres_meses_aplicable': intacto, 'fecha_limite_aviso': limite if intacto else None, 'cumple': fecha(h['fecha_aviso']) <= fecha(limite) and h['sujeto'] == 'distribuidora_constituyente' and (h['destinatario'] in ['organismo_autorizado', 'administracion_competente']) if intacto else None, 'si_modificado': 'informar_administracion_y_formar_nuevo_lote'}
    if op == 'gas_retencion':
        if fecha(h['fin_retencion']) < fecha(h['verificacion_muestra']):
            raise Insuficiente('I-GAS-RETENCION: fin anterior a verificación')
        limite = desplazar(h['verificacion_muestra'], meses=c['meses'])
        return {'retencion_fijada': h['organismo_fija_retencion'], 'maximo_referencia': limite if h['organismo_fija_retencion'] else None, 'no_supera_mes': fecha(h['fin_retencion']) <= fecha(limite) if h['organismo_fija_retencion'] else None, 'no_confundir_retirada_verificacion': True}
    if op == 'gas_delegacion':
        d = h['documento_delegacion']
        delegado = h['titular_consumidor'] and d is not None and d['firmado_consumidor'] and d['presentado_distribuidora']
        return {'delegacion_acreditada': delegado, 'si_consumidor_sin_delegacion': 'pautas_administracion_y_distribuidora_comunica' if h['titular_consumidor'] and (not delegado) else None, 'modalidad_obligado': 'compania_distribuidora' if h['modalidad'] == 'muestreo' else 'titular_instrumento'}
    if op == 'gas_emp':
        cert = h['certificado_primera_periodica']
        f = cert['fecha'] if cert is not None else None
        if f is not None and fecha(f) > fecha(h['fecha_actuacion']):
            raise Insuficiente('I-GAS-EMP: primera periódica futura')
        validar_antecedentes(r, h)
        if h['fase'] == 'periodica':
            origen = 'apendice_II'
        elif cert is not None:
            origen = 'apendice_II'
        elif h['fecha_actuacion'] == h['fin_primer_periodo']:
            origen = 'pendiente_frontera_IV7'
        elif h['fecha_actuacion'] < h['fin_primer_periodo']:
            origen = 'evaluacion_conformidad'
        else:
            origen = 'apendice_II'
        return {'EMP_fuente': origen, 'ensayos': 'apendice_II', 'autoriza_uso_vencido': False, 'EMP_numericos': 'no_ensayados'}
    if op == 'gas_muestreo':
        if h['intervencion'] != 'ninguna':
            accion = 'intervencion_prohibida_2_5'
        elif h['cambio_plan_tras_inicio']:
            accion = 'cambio_plan_prohibido_2_10'
        elif not h['muestra_completa']:
            accion = 'rechazar_solicitud_muestreo_2_8'
        elif h['lote_resultado'] == 'rechazado':
            accion = 'todas_unidades_fuera_servicio'
        elif h['unidad_muestra_conforme']:
            accion = 'etiquetar_solo_muestra_conforme_y_comunicar_resto'
        else:
            accion = 'unidad_muestra_no_conforme_fuera_servicio'
        return {'accion': accion, 'comunicacion_resultado': 'obligatoria_cuando_exista_resultado', 'no_es_ejecucion_plan_estadistico': True}
    if op == 'gas_homogeneidad':
        lote, unidad = (h['documento_lote'], h['documento_unidad'])
        iguales = all((lote[k] == unidad[k] for k in ['ano_fabricacion', 'Qmax', 'ratio_Qmax_Qmin', 'DN', 'modelo_marca', 'explotacion_suministro']))
        return {'cumple_minimos_homogeneidad_y_unico_lote': iguales and (not h['ya_otro_lote']), 'representatividad_azar_y_plan': 'requieren_prueba_separada_no_simulada'}
    if op == 'gas_repuesto':
        causa = h['causa'] in ['danado_exterior', 'precinto_roto', 'no_localizado', 'presentacion_incorrecta']
        ok = causa and h['antes_ensayos_tras_visual'] and h['primera_sustitucion'] and h['seleccion_aleatoria'] and h['dentro_numero_plan']
        return {'reemplazo_admisible_por_2_8': ok, 'si_no_completa_muestra': 'rechazar_solicitud_muestreo', 'no_convalida_reparacion_ajuste': True}
    if op == 'gas_documentos':
        favorable = h['resultado'] == 'favorable'
        return {'plazo_maximo_dias': c['dias_favorable'] if favorable else c['dias_desfavorable'], 'evento_origen': 'verificacion', 'documento': 'certificado' if favorable else 'informe_desfavorable_y_comunicacion', 'fecha_limite': None, 'estado_fecha': 'pendiente_calendario_competente_no_se_asumen_naturales'}
    if op == 'gas_bateria':
        return {'vida_fuente_cumple_minimo_5_anos': h['vida_fuente_anos'] >= c['anos'], 'advertencia_exigible_tras_90_por_ciento': h['porcentaje_vida_transcurrido'] > c['porcentaje_aviso'], 'no_es_vida_util_contador_20_anos': True}
    if op == 'gas_residencial':
        return {'condicion_clase_para_uso_residencial': h['clase'] == '1.5' or (h['clase'] == '1.0' and h['ratio_Qmax_Qmin'] >= c['ratio']), 'no_certifica_demas_requisitos': True}
    raise Insuficiente('operador gas no implementado')
OPERADORES.update(CONTRATOS_NUEVOS)

def expandir_lectores(m):
    if not isinstance(m, dict) or not any((r.get('operador') == 'lectores' for r in m.get('reglas', []))):
        return copy.deepcopy(m)
    originales = m['reglas']
    reglas = {r['id']: r for r in originales}
    lectores = {r['id']: r for r in m['lectores']}
    if len(lectores) != len(m['lectores']):
        raise Insuficiente('I-REFERENCIA: lectores duplicados')
    if set(lectores) != {i for r in originales if r['operador'] == 'lectores' for i in r['lectores']}:
        raise Insuficiente('I-REFERENCIA: catálogo de lectores discordante')
    fundamentos = {f['id']: f for f in m['fundamentos']}
    nuevos = []
    for r in originales:
        if r['operador'] != 'lectores':
            nuevos.append(copy.deepcopy(r))
            continue
        fund = fundamentos[r['fundamento_id']]
        if fund['operador'] != 'lectores' or set(fund['fuentes']) != set(r['fuentes']) or set(fund['perfiles']) != set(r['perfiles_aplicables']):
            raise Insuficiente('I-FUNDAMENTO: regla compartida discordante')
        if len(r['lectores']) != len(set(r['lectores'])):
            raise Insuficiente('I-REFERENCIA: lector repetido')
        used = set()
        for rid in r['lectores']:
            reader = copy.deepcopy(lectores[rid])
            if reader['regla_canonica'] != r['id']:
                raise Insuficiente('I-REFERENCIA: lector de otra regla')
            if not set(reader['fuentes']) <= set(r['fuentes']):
                raise Insuficiente('I-FUNDAMENTO: fuente de lector ajena')
            if not set(reader['perfiles_aplicables']) <= set(r['perfiles_aplicables']):
                raise Insuficiente('I-PERFIL: perfil de lector ajeno')
            fund = reader['fundamento_lectura']
            if reader['fundamento_id'] != fund['id'] or reader['operador'] != fund['operador'] or set(reader['fuentes']) != set(fund['fuentes']) or (not set(reader['perfiles_aplicables']) <= set(fund['perfiles'])):
                raise Insuficiente('I-FUNDAMENTO: fuente/operador/perfil ajeno al fundamento del lector')
            mapping = reader['mapa_constantes']
            used.update(mapping.values())
            reader['constantes'] = {n: r['constantes'][k] for n, k in mapping.items()}
            reader['anclajes_constantes'] = {n: [a for a in r['anclajes_constantes'][k] if a['identificador'] in reader['fuentes']] for n, k in mapping.items()}
            reader['fundamento_id'] = 'FL-' + rid
            nuevos.append(reader)
        if used != set(r['constantes']) or used != set(r['anclajes_constantes']):
            raise Insuficiente('I-CONSTANTE: constantes compartidas huérfanas')
    d = copy.deepcopy(m)
    d['reglas'] = nuevos
    d['contratos_canonicos_v7'] = copy.deepcopy(originales)
    for k in ['casos', 'pares']:
        for c in d[k]:
            regla = reglas[c['regla_id']]
            if regla['operador'] == 'lectores':
                rid = c.get('lector_id', regla['id'])
                if rid not in regla['lectores']:
                    raise Insuficiente('I-REFERENCIA: lector de caso/par ajeno')
                c['regla_id'] = rid
    cc = {c['id']: c for c in d['casos']}
    for c in d['celdas']:
        refs = []
        for rid in c['reglas']:
            r = reglas[rid]
            if r['operador'] == 'lectores':
                elegidos = {cc[x]['regla_id'] for x in c['casos'] if x in cc and cc[x]['regla_id'] in r['lectores']}
                if not elegidos:
                    raise Insuficiente('I-REFERENCIA: regla compartida sin lector enlazado en celda')
                refs.extend(sorted(elegidos))
            else:
                refs.append(rid)
        c['reglas'] = list(dict.fromkeys(refs))
    d['fundamentos'] = [dict(id=r['fundamento_id'], operador=r['operador'], fuentes=r['fuentes'], perfiles=r['perfiles_aplicables']) for r in nuevos]
    for f in d['fundamentos']:
        if f['id'] in fundamentos:
            f.update(copy.deepcopy(fundamentos[f['id']]))
    return d

def cargar_json(texto):
    return json.loads(texto, parse_float=Decimal, parse_constant=Decimal)

def volcar_json(objeto, ensure_ascii=True, indent=None, sort_keys=False, separators=None):
    """Public CI documentation."""
    sep_item, sep_key = separators or ((',', ': ') if indent is not None else (', ', ': '))
    paso = (' ' * indent if isinstance(indent, int) else indent) if indent is not None else None

    def emitir(v, nivel=0):
        if isinstance(v, Decimal):
            if not v.is_finite():
                raise Insuficiente('JSON exige número finito')
            return str(v)
        if isinstance(v, (list, dict)):
            if isinstance(v, dict):
                items = sorted(v.items()) if sort_keys else v.items()
                trozos = [json.dumps(str(k), ensure_ascii=ensure_ascii) + sep_key + emitir(x, nivel + 1) for k, x in items]
                izq, der = ('{', '}')
            else:
                trozos = [emitir(x, nivel + 1) for x in v]
                izq, der = ('[', ']')
            if not trozos:
                return izq + der
            if paso is not None:
                return izq + '\n' + paso * (nivel + 1) + (sep_item + '\n' + paso * (nivel + 1)).join(trozos) + '\n' + paso * nivel + der
            return izq + sep_item.join(trozos) + der
        return json.dumps(v, ensure_ascii=ensure_ascii, allow_nan=False)
    return emitir(objeto)

def numero_valido(v):
    return type(v) is int or (type(v) is Decimal and v.is_finite())

def normalizar_combinacion(v):
    """Public CI documentation."""
    modulos = {'A', 'A1', 'A2', 'B', 'C', 'C1', 'C2', 'D', 'D1', 'E', 'E1', 'F', 'F1', 'G', 'H', 'H1'}
    if not isinstance(v, list) or not v or any((not isinstance(x, str) or x not in modulos for x in v)):
        raise Insuficiente('combinacion: se esperaba una lista no vacía de módulos conocidos')
    if len(v) != len(set(v)):
        raise Insuficiente('combinacion: módulos repetidos')
    return sorted(v)

def normalizar_entrada(v, spec, camino):
    if camino == 'combinacion' and spec['tipo'] == 'lista':
        validar_valor_nuevo(v, spec, camino)
        return normalizar_combinacion(v)
    if v is None:
        return v
    if spec['tipo'] == 'numero':
        if not numero_valido(v):
            raise Insuficiente('número inválido: ' + camino)
        return Decimal(v)
    if spec['tipo'] == 'documento' and isinstance(v, dict):
        d = dict(v)
        for k, t in spec.get('estructura', {}).items():
            if k in d and t == 'numero':
                d[k] = normalizar_entrada(d[k], {'tipo': 'numero'}, camino + '.' + k)
        return d
    return v

def cifras_decimal(v):
    if isinstance(v, Decimal) and v.is_finite():
        t = v.as_tuple()
        return len(t.digits) + abs(t.exponent)
    if isinstance(v, dict):
        return sum((cifras_decimal(x) for x in v.values()))
    if isinstance(v, list):
        return sum((cifras_decimal(x) for x in v))
    return len(str(abs(v))) if type(v) is int else 0

def evaluar(r, hechos):
    """Public CI documentation."""
    rr = dict(r)
    esquema = CONSTANTES_OPERADOR.get(r['operador'], {})
    rr['constantes'] = {k: Decimal(v) if numero_valido(v) and esquema.get(k) not in {'anos', 'meses', 'dias', 'dias_habiles'} else v for k, v in r['constantes'].items()}
    hh = dict(hechos)
    for e in r['entradas'] + declaracion_validez(r)['entradas_validez']:
        if e['campo'] in hh:
            hh[e['campo']] = normalizar_entrada(hh[e['campo']], e, e['campo'])
    with localcontext() as ctx:
        ctx.prec = max(28, cifras_decimal(rr['constantes']) + cifras_decimal(hh) + 20)
        ctx.traps[Inexact] = True
        ctx.traps[FloatOperation] = True
        return _evaluar(r=rr, hechos=hh)
_declaracion_validez_v7 = declaracion_validez

def declaracion_validez(r):
    d = copy.deepcopy(_declaracion_validez_v7(r))
    op = r['operador']
    if op == 'sucesiva':
        d['entradas_validez'].append({'campo': 'fecha_verificacion_propuesta', 'tipo': 'fecha', 'nullable': True, 'preceptos': r['fuentes'], 'descripcion': 'Propuesta de siguiente periódica; null si solo se calcula vencimiento.'})
    if op in {'sucesiva', 'reparacion', 'rc_puntos', 'gas_emp'}:
        preceptos = [ORDEN + 'anexo.XX/apend.III', ORDEN + 'anexo.XX/ap.6'] if op == 'rc_puntos' else [ORDEN + 'art.14']
        d['invariantes'].append({'id': 'I-ANTECEDENTES', 'preceptos': preceptos, 'condicion': 'La actuación o propuesta siguiente no puede ser anterior a ninguno de los certificados periódicos usados como antecedentes presentes. Igualdad diaria admitida; null no inventa una actuación.'})
    if op == 'agua_incertidumbre':
        d['invariantes'].append({'id': 'I-EMP-ANCLADO', 'preceptos': [ORDEN + 'anexo.III/apend.I', ORDEN + 'anexo.III/apend.IV'], 'condicion': 'EMP debe coincidir con la tabla por zona del punto 1.2 de apéndice I, anclada al literal; se usa ese valor de tabla para U por divisor <= EMP. No se admite EMP de servicio ni inventado.'})
    return d
CONSTANTES_OPERADOR['agua_incertidumbre'].update(emp_superior='porcentaje', emp_inferior='porcentaje')

def validar_antecedentes(r, h):
    op = r['operador']
    propuesta, previos = (None, [])
    if op == 'sucesiva':
        propuesta, previos = (h['fecha_verificacion_propuesta'], [h['certificado_previo']])
    elif op == 'reparacion':
        propuesta, previos = (h['fecha_verificacion'], [h['certificado_previo']])
    elif op == 'rc_puntos':
        propuesta = h['fecha_verificacion_propuesta']
        previos = [c['fecha'] for c in h['certificados_periodica']]
    elif op == 'gas_emp' and h['certificado_primera_periodica'] is not None:
        propuesta, previos = (h['fecha_actuacion'], [h['certificado_primera_periodica']['fecha']])
    if propuesta is not None and any((fecha(propuesta) < fecha(x) for x in previos)):
        raise Insuficiente('I-ANTECEDENTES: propuesta/actuacion anterior a antecedente periodico')

def tabla_emp(r):
    return {zona: r['constantes']['emp_' + zona] for zona in ('superior', 'inferior')}
from decimal import Decimal as p9_elec_Decimal
from datetime import date as p9_elec_date
import re as p9_elec_re
p9_elec_O = 'BOE-A-2020-2573::'
p9_elec_R = 'BOE-A-2016-5530::'
p9_elec_CONSTANTES_ELEC = {'elec_modulos': {}, 'elec_ambito': {}, 'elec_regimen': {}, 'elec_cohorte': {'anos': 'anos', 'adicional': 'anos', 'cohorte1': 'numero', 'cohorte2': 'numero'}, 'elec_intervencion': {'anos': 'anos'}, 'elec_software_entrada': {'anos': 'anos', 'publicacion': 'fecha', 'demora_meses': 'meses'}, 'et_ambito': {}, 'et_servicio': {}, 'et_clase': {}, 'np_ambito': {'ligero_desde': 'fecha', 'pesado_desde': 'fecha'}, 'np_ensayos': {'muestras_B': 'numero', 'muestras_DF': 'numero', 'muestras_P': 'numero'}, 'np_emp': {'rel_referencia': 'porcentaje', 'rel_nominal': 'porcentaje', 'abs_max': 'numero'}, 'np_referencia': {'incertidumbre_max': 'porcentaje', 'eficiencia_min': 'numero', 'tamano_B': 'numero', 'tamano_DF': 'numero'}}
p9_elec_INVARIANTES = {'elec_regimen': ('I-EL-REGIMEN', [p9_elec_O + 'anexo.V/ap.2', p9_elec_O + 'anexo.V/ap.4', p9_elec_O + 'anexo.V/ap.5', p9_elec_R + 'art.16'], 'El anexo V fija vida útil y prohibición de reparar, sin plazo de periódica; no asignar el plazo anual de otra familia.'), 'elec_modulos': ('I-EL-MODULOS', [p9_elec_O + 'anexo.V/ap.3', p9_elec_O + 'anexo.XXI/ap.3', p9_elec_R + 'anexo.XI/art.5'], 'Combinación explícita, sin repetición; se evalúa solo la vía ordinaria.'), 'elec_ambito': ('I-EL-AMBITO', [p9_elec_O + 'anexo.V/ap.1'], 'Tipo 3 exige baja tensión; reactiva opcional no sustituye energía activa; telegestión no exime vida útil.'), 'elec_cohorte': ('I-EL-COHORTE', [p9_elec_O + 'anexo.V/ap.4'], 'Solo primera instalación; plazo adicional máximo de reposición para 2016/2017, no ampliación de vida ni permiso de uso.'), 'elec_intervencion': ('I-EL-INTERVENCION', [p9_elec_O + 'anexo.V/ap.4', p9_elec_O + 'anexo.V/ap.5'], 'Instalación <= intervención; aprobación vinculada al mismo software, organismo designado; anterioridad conocida se valida antes de pendientes. Igualdad diaria aprobación/intervención: orden no acreditado.'), 'elec_software_entrada': ('I-EL-SOFTWARE', [p9_elec_O + 'anexo.V/ap.4', p9_elec_O + 'anexo.V/ap.6', p9_elec_O + 'disp.final.5', p9_elec_O + 'cabecera'], 'Instalación <= modificación; documentos del mismo software; fecha de entrada calculada con fuente; igualdad diaria entrada/instalación o fin de vida: pendiente, no prórroga.'), 'et_ambito': ('I-ET-AMBITO', [p9_elec_R + 'anexo.XI/art.1', p9_elec_R + 'anexo.XI/art.2'], 'Criba de ámbito RD XI; subconjuntos no equivalen a termómetro aislado de cualquier finalidad.'), 'et_servicio': ('I-ET-SERVICIO', [p9_elec_R + 'anexo.XI/art.3', p9_elec_R + 'art.16', p9_elec_R + 'art.18'], 'Ausencia de plazo en el anexo de comercialización no equivale a plazo cero, libertad o exención universal. Localizar regulación específica.'), 'et_clase': ('I-ET-CLASE', [p9_elec_R + 'anexo.XI/apend.I'], 'Clases 1,2,3; uso comercial/industrial ligero exige 1 o 2; no certifica otros requisitos.'), 'np_ambito': ('I-NP-AMBITO', [p9_elec_O + 'anexo.XXI/ap.1'], 'A partir de incluye igualdad; categorías M/N, compresión, filtro diésel e ITP concurrentes.'), 'np_ensayos': ('I-NP-ENSAYOS', [p9_elec_O + 'anexo.XXI/apend.II', p9_elec_O + 'anexo.XXI/apend.III', p9_elec_O + 'anexo.XXI/apend.IV'], 'Reparación remite a conformidad producto (5 muestras, EMP referencia); periódica 3 concentraciones, EMP nominal; B al menos 9.'), 'np_emp': ('I-NP-EMP', [p9_elec_O + 'anexo.XXI/apend.I', p9_elec_O + 'anexo.XXI/apend.III', p9_elec_O + 'anexo.XXI/apend.IV'], 'EMP absoluto declarado documentalmente <= máximo público; valor del tipo no es tope libre. EMP=max(relativo,absoluto); igualdad admitida; ninguna cifra binaria.'), 'np_referencia': ('I-NP-REFERENCIA', [p9_elec_O + 'anexo.XXI/apend.II'], 'Incertidumbre expandida estrictamente inferior a 12,5%; eficiencia >0,5 a 10nm en B; en producto >=0,5 a 23nm o alternativa documental punto 2.6.')}

def p9_elec_declaracion_elec(r):
    iid, refs, cond = p9_elec_INVARIANTES[r['operador']]
    return {'entradas_validez': [], 'invariantes': [{'id': iid, 'preceptos': refs, 'condicion': cond}], 'revision_validez': {'preceptos': r['fuentes'], 'conclusion': cond}}

class p9_elec_Insuficiente(ValueError):
    pass

def p9_elec_fecha(v):
    if type(v) is not str or not p9_elec_re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', v):
        raise p9_elec_Insuficiente('fecha ISO inválida')
    try:
        return p9_elec_date.fromisoformat(v)
    except ValueError as exc:
        raise p9_elec_Insuficiente('fecha ISO inválida') from exc

def p9_elec_validar(v, e, k):
    if v is None and e.get('nullable'):
        return
    t = e['tipo']
    if t == 'fecha':
        p9_elec_fecha(v)
    elif t == 'bool':
        if type(v) is not bool:
            raise p9_elec_Insuficiente('bool inválido: ' + k)
    elif t == 'numero':
        if type(v) not in (int, p9_elec_Decimal) or not p9_elec_Decimal(v).is_finite() or v < 0:
            raise p9_elec_Insuficiente('número exacto no negativo requerido: ' + k)
    elif t == 'enum':
        if type(v) not in (str, int) or v not in e['valores']:
            raise p9_elec_Insuficiente('dominio inválido: ' + k)
    elif t == 'texto':
        if type(v) is not str or not v.strip():
            raise p9_elec_Insuficiente('texto inválido: ' + k)
    elif t == 'lista':
        if type(v) is not list or any((type(x) is not str for x in v)) or len(v) != len(set(v)):
            raise p9_elec_Insuficiente('lista de textos únicos requerida: ' + k)
    elif t == 'documento':
        if type(v) is not dict or type(v.get('id')) is not str or (not v['id'].strip()):
            raise p9_elec_Insuficiente('documento sin id: ' + k)
        for n, typ in e['estructura'].items():
            if n not in v:
                raise p9_elec_Insuficiente('documento incompleto: ' + k + '.' + n)
            sp = {'tipo': 'enum', 'valores': typ} if isinstance(typ, list) else {'tipo': typ}
            p9_elec_validar(v[n], sp, k + '.' + n)

def p9_elec_evaluar_elec(r, hechos):
    for e in r['entradas']:
        if e['campo'] not in hechos:
            raise p9_elec_Insuficiente('falta ' + e['campo'])
        p9_elec_validar(hechos[e['campo']], e, e['campo'])
    h = {e['campo']: hechos[e['campo']] for e in r['entradas']}
    c = r['constantes']
    op = r['operador']
    if op == 'elec_modulos':
        return {'combinacion_admitida': h['combinacion'] in [['B', 'D'], ['B', 'F'], ['H1']], 'solo_via_ordinaria': True}
    if op == 'elec_regimen':
        return {'afirmacion_sostenida_en_anexo_V': h['afirmacion'] == 'vida_util_sin_periodica_anexo_V', 'plazo_periodica_anexo_V': None, 'regimen': 'vida_util_y_prohibicion_reparar', 'vigilancia': 'subsiste'}
    if op == 'elec_ambito':
        ok = h['energia_activa'] and h['clase_activa'] in ['A', 'B', 'C'] and (h['uso'] in ['residencial', 'comercial', 'industria_ligera']) and (h['punto'] in ['tipo5', 'tipo4', 'tipo3_BT']) and (not h['reactiva'] or h['clase_reactiva'] in ['mejor_que3', '3'])
        return {'candidato_anexo_V': ok, 'tipo5_exige_telegestion_y_discriminacion': ok and h['punto'] == 'tipo5', 'reglamentacion_sectorial': 'pendiente_RD1110_no_inferir_conformidad'}
    if op == 'elec_cohorte':
        fin = desplazar(h['primera_instalacion'], anos=c['anos'])
        cohort = p9_elec_fecha(h['primera_instalacion']).year in [c['cohorte1'], c['cohorte2']]
        return {'fin_vida_base': fin, 'cohorte_2016_2017': cohort, 'maximo_reposicion_referencia': desplazar(fin, anos=c['adicional']) if cohort else fin, 'autoriza_uso_hasta_reposicion': False, 'ampliacion_repetible': False}
    if op in ['elec_intervencion', 'elec_software_entrada']:
        first = p9_elec_fecha(h['primera_instalacion'])
        act = p9_elec_fecha(h['fecha_intervencion'])
        if act < first:
            raise p9_elec_Insuficiente('I-EL-ORDEN: intervención anterior a instalación')
        fin = p9_elec_fecha(desplazar(h['primera_instalacion'], anos=c['anos']))
        if op == 'elec_intervencion':
            d = h['documento_aprobacion']
            if d is not None:
                if d['software_id'] != h['software_id']:
                    raise p9_elec_Insuficiente('I-EL-DOCUMENTO: software discordante')
                if p9_elec_fecha(d['fecha_aprobacion']) > act:
                    raise p9_elec_Insuficiente('I-EL-ORDEN: aprobación posterior a intervención')
            if act >= fin:
                return {'tratamiento': 'pendiente_fin_vida_no_autoriza', 'habilitacion_global': False}
            if h['actuacion'] == 'reparacion':
                return {'tratamiento': 'reparacion_prohibida_5_1', 'habilitacion_global': False}
            if not h['afecta_metrologia']:
                return {'tratamiento': 'fuera_prohibicion_5_2_revisar_otros', 'habilitacion_global': False}
            if h['actuacion'] != 'descarga_software' or not h['software_legalmente_relevante'] or h['modo_descarga'] not in ['local', 'remoto']:
                return {'tratamiento': 'modificacion_prohibida_5_2', 'habilitacion_global': False}
            if d is None:
                return {'tratamiento': 'pendiente_aprobacion_previa', 'habilitacion_global': False}
            if p9_elec_fecha(d['fecha_aprobacion']) == act:
                return {'tratamiento': 'pendiente_orden_aprobacion_mismo_dia', 'habilitacion_global': False}
            ok = d['evaluada'] and d['resultado_organismo'] == 'favorable' and d['organismo_designado']
            return {'tratamiento': 'excepcion_software_5_2' if ok else 'modificacion_prohibida_5_2', 'habilitacion_global': False}
        entrada = p9_elec_fecha(desplazar(c['publicacion'], meses=c['demora_meses']))
        d = h['documento_software']
        servicio = h['documento_servicio_entrada']
        if d is not None and (d['software_id'] != h['software_id'] or p9_elec_fecha(d['fecha_evaluacion']) > act):
            raise p9_elec_Insuficiente('I-EL-SOFTWARE: documento ajeno o posterior')
        if servicio is not None and (servicio['instrumento'] != h['instrumento_id'] or servicio['primera_instalacion'] != h['primera_instalacion'] or p9_elec_fecha(servicio['fecha_referencia']) != entrada):
            raise p9_elec_Insuficiente('I-EL-SOFTWARE: antecedente de servicio discordante')
        if first == entrada or act == fin:
            status = 'pendiente_frontera_temporal'
        elif first > entrada:
            status = 'fuera_cohorte_ap6_examinar_ap5_2'
        elif act < entrada:
            status = 'fuera_ventana_ap6'
        elif act > fin:
            status = 'vida_agotada_no_prorroga_ap6'
        elif servicio is None:
            status = 'pendiente_documento_servicio_entrada'
        elif servicio['estado_en_entrada'] != 'en_servicio':
            status = 'fuera_cohorte_ap6_examinar_ap5_2'
        elif d is None:
            status = 'pendiente_documentacion_software'
        elif p9_elec_fecha(d['fecha_evaluacion']) == act:
            status = 'pendiente_orden_evaluacion_mismo_dia'
        else:
            status = 'condiciones_ap6_satisfechas_en_hipotesis' if d['documentada'] and d['identificada'] and d['evaluacion_superada'] else 'no_cumple_ap6'
        return {'tratamiento': status, 'entrada_orden': entrada.isoformat(), 'fin_vida_base': fin.isoformat(), 'habilita_reparacion_hardware': False, 'habilitacion_global': False}
    if op == 'et_ambito':
        return {'candidato_RD_XI': h['magnitud'] == 'energia_termica_liquido' and h['uso'] in ['residencial', 'comercial', 'industria_ligera'], 'es_subconjunto': h['configuracion'] in ['sensor_flujo', 'par_temperatura', 'calculador'], 'configuracion_combinada': h['configuracion'] == 'combinado', 'requiere_evaluar_requisitos_pertinentes': True}
    if op == 'et_servicio':
        return {'afirmacion_sostenida_en_RD_XI': h['afirmacion'] == 'no_determinado_en_anexo', 'plazo_periodica': None, 'vida_util': None, 'procedimiento_reparacion': None, 'estado': 'pendiente_localizar_regulacion_especifica', 'libertad_reparar_o_usar': False}
    if op == 'et_clase':
        return {'clase_admitida_para_uso': h['clase'] in ([1, 2] if h['uso'] in ['comercial', 'industria_ligera'] else [1, 2, 3]), 'otros_requisitos': 'no_comprobados'}
    if op == 'np_ambito':
        limit = c['ligero_desde'] if h['vehiculo'] == 'ligero' else c['pesado_desde']
        return {'candidato_anexo_XXI': h['finalidad'] == 'ITP' and h['categoria'] in ['M', 'N'] and (h['motor'] == 'compresion') and h['filtro_diesel'] and (p9_elec_fecha(h['primera_matriculacion']) >= p9_elec_fecha(limit)), 'no_es_medicion_ambiental_generica': True}
    if op == 'np_ensayos':
        phase = h['fase']
        periodic = phase == 'periodica'
        exam = phase == 'conformidad_B'
        return {'concentraciones': c['muestras_B'] if exam else c['muestras_P'] if periodic else c['muestras_DF'], 'minimo': exam, 'regimen_EMP': 'nominal' if periodic else 'referencia', 'otros_ensayos': 'exigibles_no_ejecutados', 'resultado_favorable': None}
    if op == 'np_emp':
        d = h['documento_tipo']
        absolute = d['EMPabs']
        if absolute > c['abs_max']:
            raise p9_elec_Insuficiente('I-NP-EMP: EMPabs documental excede máximo público')
        rel = c['rel_nominal'] if h['fase'] == 'periodica' else c['rel_referencia']
        emp = max(h['concentracion_real'] * rel / p9_elec_Decimal(100), absolute)
        return {'EMP': emp, 'error_dentro_EMP': h['error_absoluto'] <= emp, 'regimen': 'nominal' if h['fase'] == 'periodica' else 'referencia', 'otros_ensayos': 'no_ejecutados'}
    if op == 'np_referencia':
        product = h['fase'] == 'producto_DF'
        efficiency = h['eficiencia'] >= c['eficiencia_min'] if product else h['eficiencia'] > c['eficiencia_min']
        return {'cumple_incertidumbre': h['incertidumbre_expandida'] < c['incertidumbre_max'], 'cumple_eficiencia_en_via_numerica': efficiency, 'tamano_referencia_nm': c['tamano_DF'] if product else c['tamano_B'], 'via_alternativa_punto2_6': 'no_evaluada', 'otros_requisitos': 'no_ejecutados'}
    raise p9_elec_Insuficiente('operador ELEC desconocido')

def p9_elec_instalar(core):
    """Public CI documentation."""
    global p9_elec_Insuficiente, desplazar
    p9_elec_Insuficiente = core.Insuficiente
    desplazar = core.desplazar
    anterior_eval = core._evaluar
    anterior_decl = core.declaracion_validez

    def dispatch(r, hechos):
        return p9_elec_evaluar_elec(r, hechos) if r['operador'] in p9_elec_CONSTANTES_ELEC else anterior_eval(r, hechos)

    def declare(r):
        return p9_elec_declaracion_elec(r) if r['operador'] in p9_elec_CONSTANTES_ELEC else anterior_decl(r)
    core._evaluar = dispatch
    core.declaracion_validez = declare
    core.OPERADORES.update(p9_elec_CONSTANTES_ELEC)
    core.CONSTANTES_OPERADOR.update(p9_elec_CONSTANTES_ELEC)
p9_liq_O = 'BOE-A-2020-2573::'
p9_liq_R = 'BOE-A-2016-5530::'
p9_liq_VI = p9_liq_O + 'anexo.VI/'
p9_liq_XIV = p9_liq_R + 'anexo.XIV/'
p9_liq_TAB2 = p9_liq_VI + 'apend.II/tabla.2'
p9_liq_PERFILES = ['liquidos_no_agua', 'material_capacidad', 'material_longitud']

def p9_liq_entrada(campo, tipo, fuente, **kw):
    return dict(campo=campo, tipo=tipo, preceptos=[fuente], descripcion=campo, **kw)

def p9_liq_enum(campo, valores, fuente):
    return p9_liq_entrada(campo, 'enum', fuente, valores=valores)
p9_liq_ENTRADAS = {'liq_ambito': [p9_liq_enum('tipo', ['combustible_no_gases_licuados', 'cisterna_baja_viscosidad', 'sustancias_no_combustibles_automocion', 'GLP_automocion', 'cisterna_criogeno', 'cisterna_CO2', 'cisterna_GNL', 'otro'], p9_liq_VI + 'ap.1'), p9_liq_entrada('camion_cisterna', 'bool', p9_liq_VI + 'ap.1'), p9_liq_entrada('viscosidad_mPa_s', 'numero', p9_liq_VI + 'ap.1'), p9_liq_entrada('ebullicion_C', 'numero', p9_liq_VI + 'ap.1')], 'liq_modulos': [p9_liq_entrada('combinacion', 'lista', p9_liq_R + 'anexo.XII/art.5')], 'mat_ambito': [p9_liq_enum('perfil', p9_liq_PERFILES[1:], p9_liq_XIV + 'art.2'), p9_liq_entrada('escala_unidades_legales', 'bool', p9_liq_XIV + 'art.2'), p9_liq_entrada('volumen_especifico', 'bool', p9_liq_XIV + 'art.2'), p9_liq_entrada('farmaceutico', 'bool', p9_liq_XIV + 'art.2'), p9_liq_entrada('consumo_inmediato', 'bool', p9_liq_XIV + 'art.2')], 'mat_modulos': [p9_liq_enum('perfil', p9_liq_PERFILES[1:], p9_liq_XIV + 'art.5'), p9_liq_entrada('combinacion', 'lista', p9_liq_XIV + 'art.5')], 'mat_servicio': [p9_liq_enum('fase', ['verificacion_periodica', 'verificacion_reparacion_modificacion', 'plazos', 'prohibiciones'], p9_liq_R + 'art.16'), p9_liq_enum('afirmacion', ['plazo_anual_automatico', 'exencion_universal', 'localizar_regulacion_especifica'], p9_liq_R + 'art.18')], 'mat_especialidades': [p9_liq_enum('perfil', p9_liq_PERFILES[1:], p9_liq_XIV + 'apend.I'), p9_liq_entrada('declara_partida', 'bool', p9_liq_XIV + 'apend.I'), p9_liq_entrada('exige_clase_capacidad', 'bool', p9_liq_XIV + 'apend.I'), p9_liq_entrada('capacidades_marcadas', 'lista', p9_liq_XIV + 'apend.I'), p9_liq_entrada('marcas_distinguibles', 'bool', p9_liq_XIV + 'apend.I')], 'liq_rm_alcance': [p9_liq_entrada('surtidores_comparten', 'lista', p9_liq_VI + 'apend.II'), p9_liq_entrada('precintos_especificos_levantados', 'lista', p9_liq_VI + 'apend.II'), p9_liq_entrada('precintos_comunes_levantados', 'bool', p9_liq_VI + 'apend.II')], 'liq_coincidencia': [p9_liq_entrada('fecha_certificado_propio', 'fecha', p9_liq_VI + 'apend.II'), p9_liq_entrada('nueva_fecha_periodica_propia', 'fecha', p9_liq_VI + 'apend.II'), p9_liq_entrada('fecha_periodica_otro', 'fecha', p9_liq_VI + 'apend.II'), p9_liq_entrada('fecha_verificacion_propuesta', 'fecha', p9_liq_VI + 'apend.II'), p9_liq_entrada('titularidad_propia', 'documento', p9_liq_VI + 'apend.II', estructura={'titular': 'texto', 'surtidor': 'texto', 'establecimiento': 'texto'}), p9_liq_entrada('titularidad_otro', 'documento', p9_liq_VI + 'apend.II', estructura={'titular': 'texto', 'surtidor': 'texto', 'establecimiento': 'texto'})], 'liq_etiquetas': [p9_liq_entrada('boquereles_del_surtidor_verificado', 'lista', p9_liq_VI + 'apend.II'), p9_liq_entrada('boquereles_etiquetados', 'lista', p9_liq_VI + 'apend.II')], 'liq_cohorte': [p9_liq_entrada('camion_cisterna', 'bool', p9_liq_VI + 'ap.5'), p9_liq_enum('producto', ['criogeno', 'CO2_licuado', 'GNL', 'ordinario'], p9_liq_VI + 'ap.5'), p9_liq_entrada('ebullicion_K', 'numero', p9_liq_VI + 'ap.5', nullable=True), p9_liq_entrada('puesta_servicio', 'fecha', p9_liq_VI + 'ap.5'), p9_liq_entrada('en_servicio_a_entrada', 'bool', p9_liq_VI + 'ap.5')], 'liq_crio_previos': [p9_liq_enum('familia', ['E_cisterna_criogeno_CO2_GNL'], p9_liq_TAB2), p9_liq_entrada('enfriamiento_minutos', 'numero', p9_liq_TAB2), p9_liq_entrada('rodaje_adicional_minutos', 'numero', p9_liq_TAB2), p9_liq_entrada('intervalo_sistema', 'numero', p9_liq_TAB2), p9_liq_entrada('intervalo_patron', 'numero', p9_liq_TAB2), p9_liq_entrada('cantidad_ensayo', 'numero', p9_liq_TAB2), p9_liq_entrada('cantidad_minima_medida', 'numero', p9_liq_TAB2), p9_liq_enum('unidad_cantidad', ['L', 'kg'], p9_liq_TAB2), p9_liq_entrada('mismo_liquido', 'bool', p9_liq_TAB2), p9_liq_entrada('documento_equivalencia', 'documento', p9_liq_TAB2, nullable=True, estructura={'sistema': 'texto', 'producto_medida': 'texto', 'producto_prueba': 'texto', 'equivalencia': 'bool'}), p9_liq_entrada('sistema', 'texto', p9_liq_TAB2), p9_liq_entrada('producto_medida', 'texto', p9_liq_TAB2), p9_liq_entrada('producto_prueba', 'texto', p9_liq_TAB2)], 'liq_crio_ensayo': [p9_liq_enum('familia', ['E_cisterna_criogeno_CO2_GNL'], p9_liq_TAB2), p9_liq_enum('producto', ['criogeno', 'GNL', 'CO2_licuado'], p9_liq_TAB2), p9_liq_enum('ensayo', ['130_Qmin', '40_Qmax', '70_Qmax'], p9_liq_TAB2), p9_liq_entrada('error_absoluto_porcentaje', 'numero', p9_liq_TAB2), p9_liq_entrada('incertidumbre_porcentaje', 'numero', p9_liq_VI + 'apend.I'), p9_liq_entrada('factor_cobertura', 'numero', p9_liq_TAB2), p9_liq_entrada('EMP_aportado', 'numero', p9_liq_TAB2)], 'liq_derivacion': [p9_liq_enum('familia', ['B_cisterna_baja_viscosidad', 'E_cisterna_criogeno_CO2_GNL'], p9_liq_VI + 'apend.II'), p9_liq_entrada('derivacion_o_purga', 'bool', p9_liq_VI + 'apend.II'), p9_liq_entrada('recogida_evaluacion', 'bool', p9_liq_VI + 'apend.II')], 'liq_manguera': [p9_liq_enum('familia', ['B_cisterna_baja_viscosidad'], p9_liq_VI + 'apend.II'), p9_liq_entrada('tipo_manguera_llena', 'bool', p9_liq_VI + 'apend.II'), p9_liq_entrada('reparacion_o_sustitucion_manguera', 'bool', p9_liq_VI + 'apend.II')]}
p9_liq_CONSTANTES = {'liq_ambito': {'viscosidad_max': 'mPa_s', 'magnitud_ebullicion_C': 'grados_C'}, 'mat_especialidades': {'max_capacidades': 'numero'}, 'liq_cohorte': {'publicacion': 'fecha', 'demora_entrada_dias': 'dias', 'anos': 'anos', 'umbral_K': 'K'}, 'liq_crio_previos': {'enfriamiento': 'minutos', 'rodaje': 'minutos', 'intervalos_sistema': 'numero', 'intervalos_patron': 'numero'}, 'liq_crio_ensayo': {'emp_criogeno': 'porcentaje', 'emp_CO2': 'porcentaje', 'cobertura': 'numero', 'divisor': 'numero', 'factor_reducido': 'numero'}}
p9_liq_INVARIANTES = {'liq_ambito': 'Viscosidad no negativa; ebullición en grados C declarada, sin convertir automáticamente el umbral 120 K del ap.5.', 'liq_modulos': 'Combinación sin módulos repetidos; se acepta el orden de los módulos como conjunto, sin añadir módulos.', 'mat_modulos': 'Perfil de longitud o capacidad cerrado; combinación sin módulos repetidos.', 'mat_ambito': 'Hechos declarados completos: capacidad excluye farmacéuticos y exige consumo inmediato. No presume ámbito de una fotografía.', 'mat_servicio': 'Alcance documental cerrado a RD XIV y Orden ICT/155/2020; falta de regulación localizada no equivale a exención universal.', 'mat_especialidades': 'Capacidades numéricas positivas y distintas; el máximo de tres y la exención de clase solo se aplican a capacidad para servir.', 'liq_rm_alcance': 'Identificadores únicos; los surtidores con precintos específicos levantados pertenecen al censo de elementos compartidos.', 'liq_coincidencia': 'Supuesto de surtidor ya verificado y nueva fecha de periódica determinada por su regla de origen; nueva fecha propia y propuesta no preceden al certificado propio conocido. Surtidores distintos; mismo titular y establecimiento para esta posibilidad. No alarga el plazo de ningún otro surtidor ni sustituye la antelación de solicitud.', 'liq_etiquetas': 'Identificadores únicos; etiquetados pertenecen a los boquereles del surtidor verificado.', 'liq_cohorte': 'En servicio a entrada requiere puesta en servicio no posterior a entrada; igualdad de fecha con servicio afirmado es pendiente, no selección automática de cohorte. Si consta no estar en servicio, se excluye la cohorte incluso en ese día. Ebullición obligatoria para criógeno; CO2/GNL no la necesitan y pueden declararla null, sin inventarla.', 'liq_crio_previos': 'Familia E declarada y cerrada. Magnitudes no negativas, intervalos y CMM positivos, todos expresados en la misma unidad declarada L o kg, sin conversiones; identidad del sistema/productos documental y equivalencia cuando el líquido difiere.', 'liq_crio_ensayo': 'Familia E declarada y cerrada. Cifras no negativas; k debe coincidir con 2 anclado y EMP aportado con tabla de producto. En CO2 a 130% Qmin/40% Qmax se admiten ambos candidatos literales 1,5 y 2,5 sin seleccionar uno: pendiente por tensión entre 2.1.5/2.2.5 y 3.2. Un EMP ajeno a ambos sigue siendo inválido.', 'liq_derivacion': 'Familias B/E declaradas y cerradas; solo la prohibición por derivación o purga no recogida en evaluación; no autorización global de instalación ni aplicación automática a A/C/D.', 'liq_manguera': 'Familia B declarada y cerrada. Ensayo B.1/B.2.4.2 solo tras reparación o sustitución de manguera llena; no extender a todos los tipos del VI.'}

def p9_liq_declaracion_liq(r):
    op = r['operador']
    return {'entradas_validez': [], 'invariantes': [{'id': 'I-' + op.upper().replace('_', '-'), 'preceptos': r['fuentes'], 'condicion': p9_liq_INVARIANTES[op]}], 'revision_validez': {'preceptos': r['fuentes'], 'conclusion': 'Tipos, dominios, identidades y relaciones conocidas antes de calcular; no acredita hechos reales ni aprobación humana.'}}

def p9_liq__lista_ids(v, nombre, api):
    if not isinstance(v, list) or any((not isinstance(x, str) or not x.strip() for x in v)) or len(set(v)) != len(v):
        raise api.Insuficiente('I-LIQ-LISTA: ' + nombre)

def p9_liq_evaluar_liq(r, hechos, api):
    """Public CI documentation."""
    op = r['operador']
    c = r['constantes']
    h = {}
    for e in p9_liq_ENTRADAS[op]:
        k = e['campo']
        if k not in hechos:
            raise api.Insuficiente('falta ' + k)
        v = hechos[k]
        if v is None and e.get('nullable'):
            h[k] = None
            continue
        t = e['tipo']
        if t == 'fecha':
            api.fecha(v)
        elif t == 'bool' and type(v) is not bool:
            raise api.Insuficiente('bool inválido: ' + k)
        elif t == 'enum' and v not in e['valores']:
            raise api.Insuficiente('dominio inválido: ' + k)
        elif t == 'numero' and (not api.numero_valido(v)):
            raise api.Insuficiente('número inválido: ' + k)
        elif t == 'lista' and (not isinstance(v, list)):
            raise api.Insuficiente('lista inválida: ' + k)
        elif t == 'texto' and (not isinstance(v, str) or not v.strip()):
            raise api.Insuficiente('texto inválido: ' + k)
        elif t == 'documento':
            if not isinstance(v, dict) or not isinstance(v.get('id'), str) or (not v['id'].strip()):
                raise api.Insuficiente('documento sin id: ' + k)
            for key, typ in e['estructura'].items():
                if key not in v:
                    raise api.Insuficiente('documento incompleto: ' + k + '.' + key)
                if typ == 'texto' and (not isinstance(v[key], str) or not v[key].strip()):
                    raise api.Insuficiente('texto documental inválido: ' + key)
                if typ == 'bool' and type(v[key]) is not bool:
                    raise api.Insuficiente('bool documental inválido: ' + key)
        h[k] = v
    if op == 'liq_ambito':
        if h['viscosidad_mPa_s'] < 0:
            raise api.Insuficiente('I-LIQ-AMBITO: viscosidad negativa')
        tip = h['tipo']
        cis = h['camion_cisterna']
        ok = tip in ['combustible_no_gases_licuados', 'sustancias_no_combustibles_automocion', 'GLP_automocion'] or (cis and (tip in ['cisterna_CO2', 'cisterna_GNL'] or (tip == 'cisterna_baja_viscosidad' and h['viscosidad_mPa_s'] <= c['viscosidad_max']) or (tip == 'cisterna_criogeno' and h['ebullicion_C'] < -c['magnitud_ebullicion_C'])))
        return {'incluido_VI_en_hipotesis': ok, 'otros_regimenes': 'no_excluidos_por_esta_salida'}
    if op in ['liq_modulos', 'mat_modulos']:
        p9_liq__lista_ids(h['combinacion'], 'combinacion', api)
        combo = set(h['combinacion'])
        opciones = [['B', 'F'], ['B', 'D'], ['H1'], ['G']] if op == 'liq_modulos' else [['F1'], ['D1'], ['B', 'D'], ['H'], ['G']] if h['perfil'] == 'material_longitud' else [['A2'], ['F1'], ['D1'], ['E1'], ['B', 'E'], ['B', 'D'], ['H']]
        return {'combinacion_admitida': any((combo == set(x) for x in opciones)), 'conformidad_efectiva': 'no_acreditada_por_seleccion'}
    if op == 'mat_ambito':
        ok = h['escala_unidades_legales'] if h['perfil'] == 'material_longitud' else h['volumen_especifico'] and (not h['farmaceutico']) and h['consumo_inmediato']
        return {'incluido_RD_XIV_en_hipotesis': ok, 'otros_regimenes': 'no_excluidos_por_esta_salida'}
    if op == 'mat_servicio':
        return {'estado': 'regulacion_especifica_pendiente_localizar', 'plazo_en_estas_fuentes': None, 'afirmacion_sostenida': h['afirmacion'] == 'localizar_regulacion_especifica', 'exencion_universal': False}
    if op == 'mat_especialidades':
        vals = h['capacidades_marcadas']
        if any((not api.numero_valido(x) or x <= 0 for x in vals)) or len(set(vals)) != len(vals):
            raise api.Insuficiente('I-MAT-MARCAS: capacidades positivas distintas')
        cap = h['perfil'] == 'material_capacidad'
        return {'declaracion_por_partida_seleccionada': h['declara_partida'], 'declaracion_por_partida_permitida': True, 'exigir_clase_capacidad_correcto': not h['exige_clase_capacidad'] if cap else None, 'cumple_multiples_capacidades': bool(vals) and len(vals) <= c['max_capacidades'] and h['marcas_distinguibles'] if cap else None, 'otros_requisitos': 'no_certificados'}
    if op == 'liq_rm_alcance':
        for k in ['surtidores_comparten', 'precintos_especificos_levantados']:
            p9_liq__lista_ids(h[k], k, api)
        if not h['surtidores_comparten'] or not set(h['precintos_especificos_levantados']) <= set(h['surtidores_comparten']):
            raise api.Insuficiente('I-LIQ-RM-ALCANCE: precinto ajeno o censo vacío')
        afectados = h['surtidores_comparten'] if h['precintos_comunes_levantados'] else h['precintos_especificos_levantados']
        return {'verificar_surtidores': sorted(afectados), 'estado': 'alcance_determinado' if afectados else 'sin_levantamiento_declarado_revisar_art6', 'reinicio_solo_verificados': True}
    if op == 'liq_etiquetas':
        for k in h:
            p9_liq__lista_ids(h[k], k, api)
        if not h['boquereles_del_surtidor_verificado'] or not set(h['boquereles_etiquetados']) <= set(h['boquereles_del_surtidor_verificado']):
            raise api.Insuficiente('I-LIQ-ETIQUETAS: boquerel ajeno o censo vacío')
        return {'etiquetado_por_boquerel_completo': set(h['boquereles_del_surtidor_verificado']) == set(h['boquereles_etiquetados']), 'colocacion': 'visible_encima_reposo_de_cada_boquerel_verificado'}
    if op == 'liq_coincidencia':
        propio, otro = (h['titularidad_propia'], h['titularidad_otro'])
        if propio['surtidor'] == otro['surtidor']:
            raise api.Insuficiente('I-LIQ-COINCIDENCIA: no son dos surtidores distintos')
        if any((h[k] < h['fecha_certificado_propio'] for k in ['nueva_fecha_periodica_propia', 'fecha_verificacion_propuesta'])):
            raise api.Insuficiente('I-LIQ-COINCIDENCIA: propuesta o fin anterior al certificado')
        titular = propio['titular'] == otro['titular']
        establecimiento = propio['establecimiento'] == otro['establecimiento']
        antes = h['fecha_verificacion_propuesta'] < h['nueva_fecha_periodica_propia']
        coincide = h['fecha_verificacion_propuesta'] == h['fecha_periodica_otro']
        return {'mismo_titular': titular, 'mismo_establecimiento': establecimiento, 'antes_nueva_fecha': antes, 'coincide_con_otro': coincide, 'posibilidad_por_este_inciso': titular and establecimiento and antes and coincide, 'prorroga_otro_surtidor': False}
    if op == 'liq_cohorte':
        frontera = api.entrada_vigor(c)
        if h['producto'] == 'criogeno' and h['ebullicion_K'] is None:
            raise api.Insuficiente('I-LIQ-COHORTE: falta ebullición del criógeno')
        if h['ebullicion_K'] is not None and h['ebullicion_K'] < 0:
            raise api.Insuficiente('I-LIQ-COHORTE: Kelvin negativo')
        if h['en_servicio_a_entrada'] and h['puesta_servicio'] > frontera:
            raise api.Insuficiente('I-LIQ-COHORTE: servicio declarado antes de primera utilización')
        candidato = h['camion_cisterna'] and (h['producto'] in ['CO2_licuado', 'GNL'] or (h['producto'] == 'criogeno' and h['ebullicion_K'] < c['umbral_K']))
        if candidato and h['en_servicio_a_entrada'] and (h['puesta_servicio'] == frontera):
            return {'estado': 'pendiente_cohorte_fecha_entrada', 'cohorte_especial': None, 'origen': None, 'primera_referencia': None}
        especial = candidato and h['en_servicio_a_entrada']
        return {'estado': 'cohorte_especial_determinada' if especial else 'sin_regla_especial_acreditar_regimen_ordinario', 'cohorte_especial': especial, 'origen': frontera if especial else None, 'primera_referencia': api.desplazar(frontera, anos=c['anos']) if especial else None}
    if op == 'liq_crio_previos':
        for k in ['enfriamiento_minutos', 'rodaje_adicional_minutos', 'cantidad_ensayo']:
            if h[k] < 0:
                raise api.Insuficiente('I-LIQ-PREVIOS: magnitud negativa ' + k)
        for k in ['intervalo_sistema', 'intervalo_patron', 'cantidad_minima_medida']:
            if h[k] <= 0:
                raise api.Insuficiente('I-LIQ-PREVIOS: magnitud no positiva ' + k)
        doc = h['documento_equivalencia']
        if h['mismo_liquido'] != (h['producto_medida'] == h['producto_prueba']):
            raise api.Insuficiente('I-LIQ-PREVIOS: identidad de líquidos contradictoria')
        if doc and any((doc[k] != h[k] for k in ['sistema', 'producto_medida', 'producto_prueba'])):
            raise api.Insuficiente('I-LIQ-PREVIOS: documento de otro sistema/producto')
        minimo = max(h['cantidad_minima_medida'], c['intervalos_sistema'] * h['intervalo_sistema'], c['intervalos_patron'] * h['intervalo_patron'])
        return {'cumple_enfriamiento': h['enfriamiento_minutos'] >= c['enfriamiento'], 'cumple_rodaje_adicional': h['rodaje_adicional_minutos'] >= c['rodaje'], 'cantidad_minima_ensayo': minimo, 'unidad_cantidad': h['unidad_cantidad'], 'cumple_cantidad': h['cantidad_ensayo'] >= minimo, 'liquido_admisible': h['mismo_liquido'] or bool(doc and doc['equivalencia']), 'otros_ensayos': 'no_ejecutados'}
    if op == 'liq_crio_ensayo':
        if min(h['error_absoluto_porcentaje'], h['incertidumbre_porcentaje']) < 0:
            raise api.Insuficiente('I-LIQ-EMP: magnitud negativa')
        emp = c['emp_CO2'] if h['producto'] == 'CO2_licuado' else c['emp_criogeno']
        if h['factor_cobertura'] != c['cobertura']:
            raise api.Insuficiente('I-LIQ-COBERTURA: k no coincide con literal')
        if h['producto'] == 'CO2_licuado' and h['ensayo'] != '70_Qmax':
            if h['EMP_aportado'] not in (c['emp_CO2'], c['emp_criogeno']):
                raise api.Insuficiente('I-LIQ-EMP-ANCLADO: EMP ajeno a los candidatos del literal')
            return {'estado': 'suspenso_criterio_oficial_vinculante_CO2', 'EMP_referencia': None, 'cumple_error': None, 'aviso': 'Discrepancia 2,5 % E.2.1.5/E.2.2.5 frente a 1,5 % E.3.2; sin EMP definitivo hasta criterio oficial vinculante'}
        if h['EMP_aportado'] != emp:
            raise api.Insuficiente('I-LIQ-EMP-ANCLADO: EMP ajeno al producto')
        d = c['divisor']
        u = h['incertidumbre_porcentaje']
        e = h['error_absoluto_porcentaje']
        reducido = u * d >= emp
        numerador = c['factor_reducido'] * emp - d * u if reducido else d * emp
        return {'estado': 'criterio_reducido_no_positivo_pendiente' if numerador <= 0 else 'comparacion_documental', 'EMP_referencia': emp, 'criterio': 'reducido' if reducido else 'ordinario', 'limite_numerador': numerador, 'limite_denominador': d, 'cumple_error': e * d <= numerador if numerador > 0 else None, 'favorable_global': False}
    if op == 'liq_derivacion':
        return {'no_autorizada_por_esta_causa': h['derivacion_o_purga'] and (not h['recogida_evaluacion']), 'instalacion_global': 'no_autorizada_por_esta_salida'}
    if op == 'liq_manguera':
        return {'ensayo_CMM_B_4_2_exigible': h['tipo_manguera_llena'] and h['reparacion_o_sustitucion_manguera'], 'alcance': 'solo_B_1_B_2_no_otras_familias'}
    raise api.Insuficiente('operador liq desconocido')

def p9_liq_instalar(api):
    """Public CI documentation."""
    anterior_eval = api._evaluar
    anterior_decl = api.declaracion_validez
    api.OPERADORES.update(p9_liq_ENTRADAS)
    api.CONSTANTES_OPERADOR.update({op: p9_liq_CONSTANTES.get(op, {}) for op in p9_liq_ENTRADAS})

    def evaluar(r, hechos):
        return p9_liq_evaluar_liq(r, hechos, api) if r['operador'] in p9_liq_ENTRADAS else anterior_eval(r, hechos)

    def declarar(r):
        return p9_liq_declaracion_liq(r) if r['operador'] in p9_liq_ENTRADAS else anterior_decl(r)
    api._evaluar = evaluar
    api.declaracion_validez = declarar
import copy as p9_dim_copy
p9_dim_O = 'BOE-A-2020-2573::'
p9_dim_R = 'BOE-A-2016-5530::'
p9_dim_ESPECIFICACIONES = {}
p9_dim__motor = None

def p9_dim_e(campo, tipo, fuentes, **kw):
    return dict(campo=campo, tipo=tipo, preceptos=fuentes, descripcion=campo, **kw)

def p9_dim_registrar(op, fuentes, campos, constantes=None, condicion=None):
    entradas = [p9_dim_e(nombre, tipo, fuentes, **kw) for nombre, tipo, kw in campos]
    condicion = condicion or 'Tipos y dominio explícitos; comparación documental parcial, sin aprobación ni autorización global.'
    p9_dim_ESPECIFICACIONES[op] = dict(fuentes=fuentes, entradas=entradas, unidades=constantes or {}, validez=dict(entradas_validez=[], invariantes=[dict(id='I-' + op.upper().replace('_', '-'), preceptos=fuentes, condicion=condicion)], revision_validez=dict(preceptos=fuentes, conclusion=condicion)))

def p9_dim_enum(nombre, *valores):
    return (nombre, 'enum', dict(valores=list(valores)))

def p9_dim_booleano(nombre):
    return (nombre, 'bool', {})

def p9_dim_numero(nombre):
    return (nombre, 'numero', {})

def p9_dim_documento(nombre, estructura, nullable=False):
    return (nombre, 'documento', dict(estructura=estructura, nullable=nullable))
p9_dim_registrar('dim_ambito', [p9_dim_O + 'anexo.VIII/ap.1', p9_dim_O + 'anexo.VIII/apend.I', p9_dim_R + 'anexo.XV/art.2'], [p9_dim_enum('tipo', 'longitud_cuerda_en_avance', 'area_objetos_irregulares', 'multidimensional', 'medida_materializada', 'otro'), p9_dim_booleano('naturaleza_textil_area')])
p9_dim_registrar('juego_ambito', [p9_dim_O + 'anexo.XVII/ap.1'], [p9_dim_enum('tipo_maquina', 'A', 'B', 'C', 'no_aportado'), p9_dim_enum('dispositivo', 'contador', 'complementario', 'otro')])
p9_dim_registrar('af_ambito', [p9_dim_O + 'anexo.XVIII/ap.1'], [p9_dim_booleano('local_publica_concurrencia'), p9_dim_documento('determinacion_administrativa', {'local': 'texto', 'administracion_competente': 'bool'}, nullable=True), ('local', 'texto', {})])
p9_dim_registrar('dim_modulos', [p9_dim_R + 'anexo.XV/art.5'], [p9_dim_enum('tecnologia', 'mecanico_electromecanico', 'electronico', 'incluye_software'), ('combinacion', 'lista', {'elementos': ['A', 'A2', 'B', 'D', 'D1', 'E', 'E1', 'F', 'F1', 'G', 'H', 'H1'], 'unicos': True})])
p9_dim_registrar('juego_modulos', [p9_dim_O + 'anexo.XVII/ap.3'], [('combinacion', 'lista', {'elementos': ['A', 'A2', 'B', 'D', 'F', 'G', 'H1'], 'unicos': True})])
p9_dim_registrar('juego_evaluacion', [p9_dim_O + 'anexo.XVII/apend.II'], [p9_dim_numero('contadores_presentados'), p9_dim_numero('contadores_ensayados'), p9_dim_numero('restantes_disponibles'), p9_dim_booleano('simulacion_representativa'), p9_dim_booleano('protocolos_comunicacion_aportados')], {'presentados': 'numero', 'ensayados': 'numero', 'restantes': 'numero'}, 'Conteos enteros. Tres contadores presentados, uno ensayado y dos restantes disponibles; simulación y protocolos. Lista documental, no ejecución de programas físicos.')
p9_dim_registrar('dim_longitud', [p9_dim_R + 'anexo.XV/apend.I', p9_dim_O + 'anexo.VIII/apend.I/tabla.1'], [p9_dim_enum('fase', 'evaluacion_conformidad', 'reparacion', 'periodica'), p9_dim_enum('clase', 'I', 'II', 'III'), p9_dim_numero('longitud_m'), p9_dim_numero('Lm_m'), p9_dim_numero('error_absoluto_m')], {**{'pct_' + x + '_' + c: 'porcentaje' for x in ['ec', 'serv'] for c in ['I', 'II', 'III']}, **{'min_' + c: 'numero' for c in ['I', 'II', 'III']}}, 'Magnitudes no negativas y finitas; Lm>0, longitud>=Lm. EMP se selecciona por fase/clase y se calcula exactamente; igualdad admitida. Unidades de longitud idénticas.')
p9_dim_registrar('dim_area', [p9_dim_R + 'anexo.XV/apend.I', p9_dim_O + 'anexo.VIII/apend.I/tabla.1'], [p9_dim_enum('fase', 'evaluacion_conformidad', 'reparacion', 'periodica'), p9_dim_numero('area_verdadera_dm2'), p9_dim_numero('error_absoluto_dm2'), p9_dim_numero('diferencia_sucesivas_dm2'), p9_dim_numero('escalon_dm2')], {'pct_ec': 'porcentaje', 'pct_serv': 'porcentaje', 'minimo_dm2': 'dm2'}, 'Área y escalón positivos; error absoluto y diferencia no negativos. EMP inclusivo; repetibilidad de servicio estrictamente inferior al menor de escalón y 2% del valor verdadero. No se inventa repetibilidad de evaluación.')
p9_dim_registrar('dim_multi', [p9_dim_R + 'anexo.XV/apend.I', p9_dim_O + 'anexo.VIII/apend.I/tabla.2'], [p9_dim_numero('escalon_cm'), p9_dim_numero('dimension_minima_cm'), p9_dim_numero('error_absoluto_cm'), p9_dim_numero('diferencia_indicadores_cm')], {'umbral_1_cm': 'cm', 'umbral_2_cm': 'cm', 'factor_1': 'numero', 'factor_2': 'numero', 'factor_3': 'numero', 'emp_d': 'numero'}, 'Escalón y dimensión positivos; magnitudes absolutas no negativas. d<=2, 2<d<=10, d>10. Dimensión mínima >= factor*d; error<=d; indicadores sin diferencia.')
p9_dim_registrar('dim_repetidor', [p9_dim_O + 'anexo.VIII/apend.I/tabla.1'], [p9_dim_numero('escalon_m'), p9_dim_numero('diferencia_absoluta_m')], condicion='Escalón positivo y diferencia absoluta no negativa. Diferencia menor o igual al escalón.')
p9_dim_registrar('dim_escala_area', [p9_dim_R + 'anexo.XV/apend.I', p9_dim_O + 'anexo.VIII/apend.I/tabla.1'], [p9_dim_numero('escalon_ordinario_dm2'), p9_dim_numero('escalon_ensayo_disponible_dm2')], {'ordinario': 'dm2', 'ensayo': 'dm2'})
p9_dim_registrar('juego_emp', [p9_dim_O + 'anexo.XVII/apend.I'], [p9_dim_enum('fase', 'evaluacion_conformidad', 'reparacion', 'periodica'), p9_dim_numero('error_absoluto_porcentaje')], {'emp_ec_rm': 'porcentaje', 'emp_periodica': 'porcentaje'})
p9_dim_registrar('juego_ensayos', [p9_dim_O + 'anexo.XVII/apend.III'], [p9_dim_numero('ensayos_juego'), p9_dim_booleano('jugada_con_premio')], {'minimo_ensayos': 'numero'}, 'Conteo entero no negativo. Al menos 20 ensayos O hasta obtener una jugada con premio; no certifica los demás ensayos.')
p9_dim_registrar('juego_conservacion', [p9_dim_O + 'anexo.XVII/apend.I'], [p9_dim_enum('evento', 'averia', 'ausencia_corriente', 'desconexion'), p9_dim_numero('anos_conservacion_documentados')], {'anos': 'anos'}, 'Capacidad de conservación no negativa. Al menos seis años ante avería, ausencia de corriente o desconexión; no fija por inferencia una fecha de borrado ni un origen jurídico no explicitado.')
p9_dim_registrar('juego_aptitud', [p9_dim_O + 'anexo.XVII/apend.I'], [p9_dim_booleano('fallo_comunicacion'), p9_dim_booleano('fuera_servicio_ante_fallo'), p9_dim_booleano('protocolo_bidireccional'), p9_dim_booleano('zona_contador_y_cableado_precintada'), p9_dim_booleano('sujecion_tornillos'), p9_dim_booleano('tornillos_precintados'), p9_dim_booleano('necesita_medios_descarga'), p9_dim_booleano('medios_suministrados')])
p9_dim_registrar('af_emp', [p9_dim_O + 'anexo.XVIII/apend.I'], [p9_dim_enum('ensayo', 'simulacion_conteo', 'tipo_diseno', 'puesta_servicio_personas', 'servicio_personas'), p9_dim_numero('error_absoluto_porcentaje')], {'simulacion': 'porcentaje', 'tipo': 'porcentaje', 'puesta': 'porcentaje', 'servicio': 'porcentaje'})
p9_dim_registrar('af_mediciones', [p9_dim_O + 'anexo.XVIII/apend.II/tabla.8', p9_dim_O + 'anexo.XVIII/apend.III'], [p9_dim_enum('fase', 'tipo_diseno_B_H1', 'puesta_F_D', 'reparacion', 'periodica'), p9_dim_numero('mediciones_reales')], {'tipo_diseno': 'numero', 'puesta': 'numero', 'reparacion': 'numero', 'periodica': 'numero'}, 'Número entero no negativo. Mínimos por fase: 500 B/H1, 100 F/D, 100 reparación, 50 periódica. No mezcla simulación con afluencia real.')
p9_dim_registrar('af_entorno', [p9_dim_O + 'anexo.XVIII/apend.I'], [p9_dim_enum('componente', 'sistema_informatico', 'captacion_universal'), p9_dim_booleano('a_intemperie'), p9_dim_booleano('justificacion_fabricante_no_influencia'), p9_dim_booleano('situacion_indicada_placa')], condicion='Excepción limitada a entornos climático/mecánico/electromagnético; sistema informático exige además no intemperie. Captación universal aplica 2.1.8. Siempre justificación y situación en placa; no exención de todo el instrumento.')
p9_dim_registrar('af_lugar', [p9_dim_O + 'anexo.XVIII/apend.II/tabla.8', p9_dim_O + 'anexo.XVIII/apend.III'], [p9_dim_enum('fase', 'tipo_diseno_B_H1', 'puesta_F_D', 'reparacion', 'periodica'), p9_dim_enum('lugar', 'instalacion_real', 'laboratorio', 'instalacion_representativa'), p9_dim_documento('evaluacion_no_influencia', {'no_influye_instalacion': 'bool'}, nullable=True), p9_dim_booleano('cambio_ubicacion')], condicion='En servicio y F/D la no influencia de instalación debe estar determinada en evaluación; no basta afirmación sin documento. Cambio de ubicación sin nuevos ensayos solo en supuesto F/D expresamente acreditado, sin exención general de periódica.')
p9_dim_registrar('af_conservacion', [p9_dim_O + 'anexo.XVIII/apend.I'], [p9_dim_enum('legislacion_proteccion_datos', 'permite', 'no_aportada', 'no_permite'), p9_dim_booleano('descarga_segura'), p9_dim_numero('anos_tras_desconexion')], {'anos': 'anos'}, 'Un año tras desconexión, si lo permite protección de datos y salvo descarga segura. Sin norma aplicable documentada, pendiente; nunca autoriza conservar datos prohibidos.')
p9_dim_registrar('af_instalacion', [p9_dim_O + 'anexo.XVIII/apend.I'], [p9_dim_booleano('cubre_todas_zonas'), p9_dim_booleano('evita_falsos_conteos'), p9_dim_booleano('indicadores_luminosos'), p9_dim_booleano('comunicacion_bidireccional'), p9_dim_booleano('fallo_comunicacion'), p9_dim_booleano('fuera_servicio_y_alarma')])
p9_dim_registrar('af_video', [p9_dim_O + 'anexo.XVIII/apend.II/tabla.8', p9_dim_O + 'anexo.XVIII/apend.III'], [p9_dim_booleano('usa_video'), p9_dim_booleano('registro_inequivoco_afluencia'), p9_dim_booleano('anonimato_garantizado')])
p9_dim_registrar('dim_examen', [p9_dim_O + 'art.9', p9_dim_O + 'art.15'], [p9_dim_booleano('administrativo_superado'), p9_dim_booleano('todos_ensayos_superados'), p9_dim_booleano('software_legal_relevante'), p9_dim_booleano('nombre_version_software_coinciden'), p9_dim_booleano('aplicacion_medida_coincide')])

def p9_dim_evaluar_dim(r, hechos):
    """Public CI documentation."""
    entradas = r['entradas'] + p9_dim__motor.declaracion_validez(r)['entradas_validez']
    for spec in entradas:
        k = spec['campo']
        if k not in hechos:
            raise p9_dim__motor.Insuficiente('falta ' + k)
        p9_dim__motor.validar_valor_nuevo(hechos[k], spec, k)
    h = {s['campo']: hechos[s['campo']] for s in entradas}
    c = r['constantes']
    op = r['operador']

    def positivo(*ks):
        for k in ks:
            if h[k] <= 0:
                raise p9_dim__motor.Insuficiente('I-DIM-DOMINIO: ' + k + ' debe ser positivo')

    def entero(k):
        if h[k] != h[k].to_integral_value():
            raise p9_dim__motor.Insuficiente('I-DIM-CONTEO: ' + k + ' debe ser entero')
    if op == 'dim_ambito':
        en = h['tipo'] in ['longitud_cuerda_en_avance', 'area_objetos_irregulares', 'multidimensional']
        return dict(ambito_RD_XV=en, ambito_servicio_VIII=en and (h['tipo'] != 'area_objetos_irregulares' or h['naturaleza_textil_area']), medidas_materializadas='fuera_de_este_perfil_no_exencion_global', valoracion_material='tecnica_o_profesional_si_naturaleza_dudosa', presuncion_cintas_materializadas=False)
    if op == 'juego_ambito':
        if h['tipo_maquina'] == 'no_aportado':
            return dict(ambito_XVII=None, estado='pendiente_tipo_maquina')
        return dict(ambito_XVII=h['tipo_maquina'] in ['B', 'C'] and h['dispositivo'] in ['contador', 'complementario'])
    if op == 'af_ambito':
        d = h['determinacion_administrativa']
        requisitos = dict(requiere_disposicion_local_y_proteccion_datos=True, cumplimiento_proteccion_datos=None, documentacion_cliente_pendiente=['disposicion_administracion_competente_que_determine_el_local', 'acreditacion_cumplimiento_proteccion_datos'], autoriza_uso=False)
        if not h['local_publica_concurrencia']:
            return dict(ambito_XVIII=False, estado='fuera_supuesto_no_exencion_global', **requisitos)
        if d is None:
            return dict(ambito_XVIII=None, estado='pendiente_determinacion_administrativa', **requisitos)
        if d['local'] != h['local']:
            raise p9_dim__motor.Insuficiente('I-AF-IDENTIDAD: determinacion de otro local')
        return dict(ambito_XVIII=d['administracion_competente'], estado='pendiente_acreditar_cumplimiento_proteccion_datos' if d['administracion_competente'] else 'hipotesis_documental_no_expte_real', **requisitos)
    if op == 'dim_modulos':
        opciones = [['F1'], ['E1'], ['D1'], ['B', 'F'], ['B', 'E'], ['B', 'D'], ['H'], ['H1'], ['G']] if h['tecnologia'] == 'mecanico_electromecanico' else [['B', 'F'], ['B', 'D'], ['H1'], ['G']]
        return dict(combinacion_admitida_via_nacional=h['combinacion'] in opciones)
    if op == 'juego_modulos':
        return dict(combinacion_admitida_via_nacional=h['combinacion'] == ['A2'])
    if op == 'juego_evaluacion':
        for k in ['contadores_presentados', 'contadores_ensayados', 'restantes_disponibles']:
            entero(k)
        return dict(cumple_lista_evaluacion=h['contadores_presentados'] == c['presentados'] and h['contadores_ensayados'] == c['ensayados'] and (h['restantes_disponibles'] == c['restantes']) and h['simulacion_representativa'] and h['protocolos_comunicacion_aportados'], otros_ensayos='no_certificados')
    if op == 'dim_longitud':
        positivo('longitud_m', 'Lm_m')
        if h['longitud_m'] < h['Lm_m']:
            raise p9_dim__motor.Insuficiente('I-DIM-DOMINIO: longitud menor que Lm')
        stage = 'ec' if h['fase'] == 'evaluacion_conformidad' else 'serv'
        limite = max(c['pct_' + stage + '_' + h['clase']] * h['longitud_m'] / 100, c['min_' + h['clase']] * h['Lm_m'])
        return dict(EMP_m=limite, cumple_EMP=h['error_absoluto_m'] <= limite, otros_ensayos='no_certificados')
    if op == 'dim_area':
        positivo('area_verdadera_dm2', 'escalon_dm2')
        serv = h['fase'] != 'evaluacion_conformidad'
        limite = max(c['pct_serv' if serv else 'pct_ec'] * h['area_verdadera_dm2'] / 100, c['minimo_dm2'])
        return dict(EMP_dm2=limite, cumple_EMP=h['error_absoluto_dm2'] <= limite, cumple_repetibilidad=h['diferencia_sucesivas_dm2'] < min(h['escalon_dm2'], c['pct_serv'] * h['area_verdadera_dm2'] / 100) if serv else None)
    if op == 'dim_multi':
        positivo('escalon_cm', 'dimension_minima_cm')
        d = h['escalon_cm']
        factor = c['factor_1'] if d <= c['umbral_1_cm'] else c['factor_2'] if d <= c['umbral_2_cm'] else c['factor_3']
        return dict(dimension_minima_exigida_cm=factor * d, cumple_dimension_minima=h['dimension_minima_cm'] >= factor * d, EMP_cm=c['emp_d'] * d, cumple_EMP=h['error_absoluto_cm'] <= c['emp_d'] * d, cumple_indicadores=h['diferencia_indicadores_cm'] == 0)
    if op == 'dim_repetidor':
        positivo('escalon_m')
        return dict(cumple_diferencia_repetidores=h['diferencia_absoluta_m'] <= h['escalon_m'])
    if op == 'dim_escala_area':
        return dict(cumple_escala_ordinaria=h['escalon_ordinario_dm2'] == c['ordinario'], cumple_escala_ensayo_disponible=h['escalon_ensayo_disponible_dm2'] == c['ensayo'])
    if op == 'juego_emp':
        limite = c['emp_periodica'] if h['fase'] == 'periodica' else c['emp_ec_rm']
        return dict(EMP_porcentaje=limite, cumple_EMP=h['error_absoluto_porcentaje'] <= limite)
    if op == 'juego_ensayos':
        entero('ensayos_juego')
        if h['jugada_con_premio'] and h['ensayos_juego'] == 0:
            raise p9_dim__motor.Insuficiente('I-JUEGO-ENSAYOS: premio sin ensayo')
        return dict(cumple_cantidad_ensayos=h['ensayos_juego'] >= c['minimo_ensayos'] or h['jugada_con_premio'], otros_ensayos='no_certificados')
    if op == 'juego_conservacion':
        return dict(anos_minimos=c['anos'], cumple_duracion=h['anos_conservacion_documentados'] >= c['anos'], fecha_borrado=None, origen_calendario='acreditar_minimo_6_anos_antes_de_fijar_borrado', borrado_automatico=False)
    if op == 'juego_aptitud':
        return dict(cumple_comunicacion=h['protocolo_bidireccional'] and (not h['fallo_comunicacion'] or h['fuera_servicio_ante_fallo']), cumple_precintos=h['zona_contador_y_cableado_precintada'] and (not h['sujecion_tornillos'] or h['tornillos_precintados']), cumple_medios_descarga=not h['necesita_medios_descarga'] or h['medios_suministrados'])
    if op == 'af_emp':
        key = dict(simulacion_conteo='simulacion', tipo_diseno='tipo', puesta_servicio_personas='puesta', servicio_personas='servicio')[h['ensayo']]
        limite = c[key]
        return dict(EMP_porcentaje=limite, cumple_EMP=h['error_absoluto_porcentaje'] <= limite)
    if op == 'af_mediciones':
        entero('mediciones_reales')
        key = dict(tipo_diseno_B_H1='tipo_diseno', puesta_F_D='puesta', reparacion='reparacion', periodica='periodica')[h['fase']]
        minimo = c[key]
        return dict(minimo_mediciones_reales=minimo, cumple_cantidad=h['mediciones_reales'] >= minimo, otros_ensayos='no_certificados')
    if op == 'af_entorno':
        ok = h['justificacion_fabricante_no_influencia'] and h['situacion_indicada_placa'] and (h['componente'] == 'captacion_universal' or not h['a_intemperie'])
        return dict(excepcion_solo_entornos_componente=ok, demas_requisitos='siguen_exigibles')
    if op == 'af_lugar':
        d = h['evaluacion_no_influencia']
        acreditado = d is not None and d['no_influye_instalacion']
        return dict(lugar_ensayo_admisible=h['lugar'] == 'instalacion_real' or acreditado, sin_nuevos_ensayos_por_cambio_ubicacion=h['cambio_ubicacion'] and h['fase'] == 'puesta_F_D' and acreditado, otros_controles='no_exencion_global')
    if op == 'af_conservacion':
        if h['legislacion_proteccion_datos'] != 'permite':
            return dict(estado='pendiente_regimen_proteccion_datos', exige_conservacion_por_esta_regla=None, cumple=None)
        exige = not h['descarga_segura']
        return dict(estado='hipotesis_documental', exige_conservacion_por_esta_regla=exige, cumple=h['anos_tras_desconexion'] >= c['anos'] if exige else None)
    if op == 'af_instalacion':
        ok = all((h[k] for k in ['cubre_todas_zonas', 'evita_falsos_conteos', 'indicadores_luminosos', 'comunicacion_bidireccional'])) and (not h['fallo_comunicacion'] or h['fuera_servicio_y_alarma'])
        return dict(cumple_lista_instalacion_y_alarma=ok, otros_requisitos='no_certificados')
    if op == 'af_video':
        return dict(cumple_condiciones_video=not h['usa_video'] or (h['registro_inequivoco_afluencia'] and h['anonimato_garantizado']), autoriza_identificar_personas=False)
    if op == 'dim_examen':
        return dict(posible_favorable_en_lista_declarada=h['administrativo_superado'] and h['todos_ensayos_superados'] and (not h['software_legal_relevante'] or h['nombre_version_software_coinciden']) and h['aplicacion_medida_coincide'], autoriza_uso=False)
    raise p9_dim__motor.Insuficiente('operador dim desconocido: ' + op)

def p9_dim_instalar(motor):
    global p9_dim__motor
    p9_dim__motor = motor
    motor.OPERADORES.update(p9_dim_ESPECIFICACIONES)
    motor.CONTRATOS_NUEVOS.update({k: p9_dim_copy.deepcopy(v['validez']) for k, v in p9_dim_ESPECIFICACIONES.items()})
    motor.CONSTANTES_OPERADOR.update({k: v['unidades'] for k, v in p9_dim_ESPECIFICACIONES.items()})
    original = motor.evaluar_nuevo

    def nuevo(r, h):
        return p9_dim_evaluar_dim(r, h) if r['operador'] in p9_dim_ESPECIFICACIONES else original(r, h)
    motor.evaluar_nuevo = nuevo
p9_veh_O = 'BOE-A-2020-2573::'
p9_veh_R = 'BOE-A-2016-5530::'
p9_veh_DEFINICIONES = {'veh_ambito': ([p9_veh_O + 'anexo.' + n + '/ap.1' for n in ['IX', 'X', 'XII', 'XIII']], 'Perfil cerrado y hechos de destino/función declarados; candidato no equivale a autorización.'), 'veh_modulos_h1': ([p9_veh_R + 'anexo.XVI/art.5', p9_veh_O + 'anexo.X/ap.3'], 'Perfil y lista expresa, sin módulos repetidos. Admisión documental no acredita ejecución.'), 'veh_modulos_bf': ([p9_veh_O + 'anexo.XII/ap.3', p9_veh_O + 'anexo.XIII/ap.3'], 'Perfil y lista expresa, sin módulos repetidos. Solo B+F; no importar H1 de otra familia.'), 'veh_previa': ([p9_veh_O + 'art.6', p9_veh_O + 'art.7', p9_veh_O + 'anexo.XII/ap.4', p9_veh_O + 'anexo.XIII/ap.4', 'BOE-A-2014-13359::art.12.4'], 'Intervención <= verificación <= consulta. Resultado realizado iff fecha no nula. Documentos de excepción con identidad común; XIII.4 salvo art.12.4 con tres condiciones documentadas; sin autorizacion global de uso.'), 'veh_cabina_condiciones': ([p9_veh_O + 'anexo.XII/apend.I', p9_veh_O + 'anexo.XII/apend.IV'], 'Cabina de fijo, métodos distintos y coincidencia con periódica. Revisión propuesta >= revisión anterior; ambos documentos de la misma cabina. No inventa primer origen.'), 'veh_cine_trafico': ([p9_veh_O + 'anexo.XII/apend.IV'], 'Tipo y opción de sustitución explícitos; excepción de tramo exige conjuntamente cámaras sensor, envío al centro, distancia garantizada y relojes sincronizados conformes.'), 'veh_opac_semanal': ([p9_veh_O + 'anexo.X/apend.I'], 'Fecha de comprobación no posterior a consulta; ausencia o comprobación insatisfactoria impide medir. Como maximo 7 dias entre comprobaciones con filtro (Responsable, VEH-P03a, 20/10/2026); 7 cumple, 8 no; filtro en rango y tolerancia inclusiva.'), 'veh_opac_termico': ([p9_veh_O + 'anexo.X/apend.I'], 'Calentamiento inferior al límite; sin lectura durante calentamiento. Pared no inferior al límite; excepción de gas frío exige tipo de motor, autorización manual y registro.'), 'veh_archivo': ([p9_veh_O + 'anexo.X/apend.I', p9_veh_O + 'anexo.XIII/apend.I'], 'Retención mínima inclusiva; etilómetro inferior al límite legal: no obligación de almacenar; eliminación solo con memoria llena, orden y procedimiento permitido.'), 'veh_gas_respuesta': ([p9_veh_O + 'anexo.IX/apend.I/tabla.1', p9_veh_O + 'anexo.IX/apend.II'], 'Ensayo identificado y mezcla sin O2 para respuesta/bajo caudal. Límite de tiempo inclusivo y fracción O2 final estrictamente inferior al límite.'), 'veh_gas_emp': ([p9_veh_O + 'anexo.IX/apend.I', p9_veh_O + 'anexo.IX/apend.I/tabla.1'], 'EMP por mensurando y clase: mayor entre componente absoluto de tabla y relativo; no aceptar EMP libre. Error absoluto no negativo y frontera inclusiva.'), 'veh_opac_emp': ([p9_veh_O + 'anexo.X/apend.I/tabla.1'], 'Solo comparación en k con referencia; fase selecciona tabla anclada. Umbral kref inclusivo para rama porcentual; error <= EMP. No acepta EMP aportado como criterio.'), 'veh_eti_ensayos': ([p9_veh_O + 'anexo.XIII/apend.III/tabla.2', p9_veh_O + 'anexo.XIII/apend.IV/tabla.3'], 'Fase explícita; los cinco gases de tabla con repeticiones por fase; alcance estrictamente superior al umbral añade gas al porcentaje anclado. EMP/repetibilidad OIML pendientes.'), 'veh_eti_ciclo': ([p9_veh_O + 'anexo.XIII/apend.I'], 'Tres muestras como máximo, dos correctas; primeras dos incorrectas abortan. Resultado menor de dos correctas. Diferencia absoluta estrictamente superior anula; rama relativa sin denominador normativo explícito queda pendiente.'), 'veh_remision': ([p9_veh_O + 'anexo.' + n + '/ap.6' for n in ['IX', 'X', 'XII', 'XIII']], 'Perfil y fase seleccionan ensayos/EMP y condiciones de su propio anexo. No certifica ensayos ni traslada EMP entre etapas.'), 'veh_opac_referencia': ([p9_veh_O + 'anexo.X/apend.I/tabla.1'], 'Última comparación de la referencia con la referencia nacional documentada. Propuesta no anterior al antecedente; origen nunca deducido del certificado del instrumento ensayado. Solo calcula referencia anual, sin autorizar uso ni resolver frontera de vencimiento.')}
p9_veh_ESQUEMAS = {'veh_cine_trafico': {'medidas_generales': 'numero', 'medidas_tramo': 'numero'}, 'veh_opac_semanal': {'semana_dias': 'dias', 'filtro_min': 'porcentaje', 'filtro_max': 'porcentaje', 'tolerancia_N': 'porcentaje', 'tolerancia_k': 'm_inv'}, 'veh_opac_termico': {'calentamiento_max': 'minutos', 'gas_min': 'celsius', 'pared_min': 'celsius'}, 'veh_archivo': {'opac_anos': 'anos', 'eti_anos': 'anos'}, 'veh_gas_respuesta': {'tiempo_gases': 'segundos', 'tiempo_O2': 'segundos', 'fraccion_gases': 'porcentaje', 'O2_final_max': 'porcentaje'}, 'veh_gas_emp': {'CO_0': 'porcentaje_vol', 'CO_I': 'porcentaje_vol', 'CO2': 'porcentaje_vol', 'HC_0': 'ppm_vol', 'HC_I': 'ppm_vol', 'O2': 'porcentaje_vol', 'relativo': 'porcentaje'}, 'veh_opac_emp': {'umbral_k': 'm_inv', 'eval_absoluto': 'm_inv', 'eval_porcentaje': 'porcentaje', 'servicio_absoluto': 'm_inv', 'servicio_porcentaje': 'porcentaje'}, 'veh_eti_ensayos': {'repeticiones_reparacion': 'numero', 'repeticiones_periodica': 'numero', 'umbral_alcance': 'mg_L', 'porcentaje_extra': 'porcentaje', 'gas_1': 'mg_L', 'gas_2': 'mg_L', 'gas_3': 'mg_L', 'gas_4': 'mg_L', 'gas_5': 'mg_L'}, 'veh_eti_ciclo': {'diferencia_absoluta': 'mg_L'}, 'veh_opac_referencia': {'anos': 'anos'}}

def p9_veh_contrato(op):
    fuentes, condicion = p9_veh_DEFINICIONES[op]
    return {'entradas_validez': [], 'invariantes': [{'id': 'I-' + op.upper().replace('_', '-'), 'preceptos': fuentes, 'condicion': condicion}], 'revision_validez': {'preceptos': fuentes, 'conclusion': condicion}}

def p9_veh_evaluar_veh(r, h, api):
    """Public CI documentation."""
    op = r['operador']
    c = r['constantes']
    F = api.fecha
    E = api.Insuficiente
    if 'perfil' in h and h['perfil'] not in r['perfiles_aplicables']:
        raise E('I-VEH-PERFIL: perfil fuera de regla')
    if op == 'veh_ambito':
        candidato = {'analizador_gasolina': h['motor'] == 'chispa' and h['destino'] == 'inspeccion_mantenimiento_profesional', 'opacimetro': h['motor'] == 'compresion' and h['destino'] == 'inspeccion_mantenimiento', 'cinemometro': h['mide_velocidad_vehiculos'], 'etilometro': h['destino'] in ['sancion', 'prueba_judicial', 'norma_obligante']}[h['perfil']]
        return {'candidato_anexo': candidato, 'autoriza_uso': False}
    if op in {'veh_modulos_h1', 'veh_modulos_bf'}:
        mods = h['combinacion']
        if len(mods) != len(set(mods)):
            raise E('I-VEH-MODULOS: módulos repetidos')
        permitidas = [['B', 'F']] if op == 'veh_modulos_bf' else [['B', 'D'], ['B', 'F'], ['H1']]
        return {'combinacion_admitida': mods in permitidas, 'regimen': 'RD_anexo_XVI_CE_M' if h['perfil'] == 'analizador_gasolina' else 'nacional', 'ensayos_documentos_marcado': 'pendientes'}
    if op == 'veh_previa':
        v = h['fecha_verificacion']
        inter = F(h['fecha_intervencion'])
        consulta = F(h['fecha_consulta'])
        if consulta < inter or (h['resultado'] == 'no_realizada') != (v is None) or (v is not None and (not inter <= F(v) <= consulta)):
            raise E('I-VEH-PREVIA: orden o resultado/fecha incoherentes')
        ex = api.excepcion(h)
        if ex.startswith('pendiente'):
            estado = ex
            prohibicion = h['resultado'] != 'favorable' if h['perfil'] == 'etilometro' else None
        elif ex == 'concurre_en_hipotesis_documental':
            estado = 'excepcion_legal_en_hipotesis'
            prohibicion = False
        else:
            estado = 'solo_causa_tras_intervencion'
            prohibicion = h['resultado'] != 'favorable'
        return {'estado': estado, 'prohibicion_por_falta_favorable': prohibicion, 'via_art8_disponible': False, 'autoriza_uso_global': False}
    if op == 'veh_cabina_condiciones':
        a, b = (h['revision_anterior'], h['revision_propuesta'])
        if a['cabina'] != b['cabina']:
            raise E('I-VEH-CABINA: identidad de cabina discordante')
        if F(b['fecha']) < F(a['fecha']):
            raise E('I-ANTECEDENTES: revisión anterior a antecedente de cabina')
        return {'metodos_distintos': a['metodo'] != b['metodo'], 'coincide_periodica': b['fecha'] == h['fecha_periodica'], 'condiciones_cuatrienal_satisfechas': a['metodo'] != b['metodo'] and b['fecha'] == h['fecha_periodica'], 'otros_requisitos': 'pendientes'}
    if op == 'veh_cine_trafico':
        tipo = h['tipo']
        ex = tipo == 'tramo' and all((h[x] for x in ['camaras_solo_sensores', 'envio_centro', 'distancia_garantizada', 'relojes_sincronizados_conformes']))
        if ex:
            return {'ensayos_trafico_exigidos': False, 'minimo_medidas': None, 'garantia_telematica_admisible': True}
        if tipo in ['fijo', 'estatico'] and (not h['opta_sustitucion']):
            return {'ensayos_trafico_exigidos': False, 'minimo_medidas': None, 'procedimiento': 'XII_II_A_1.1_1.2_1.3'}
        return {'ensayos_trafico_exigidos': True, 'minimo_medidas': c['medidas_tramo'] if tipo == 'tramo' else c['medidas_generales'], 'garantia_telematica_admisible': False}
    if op == 'veh_opac_semanal':
        consulta = F(h['fecha_consulta'])
        prev = h['fecha_comprobacion']
        if prev is not None and F(prev) > consulta:
            raise E('I-VEH-SEMANA: comprobación futura')
        edad = (consulta - F(prev)).days if prev is not None else None
        filtro = c['filtro_min'] <= h['filtro_N'] <= c['filtro_max']
        tolerancia = c['tolerancia_N'] if h['escala'] == 'N' else c['tolerancia_k']
        supera = filtro and h['error_absoluto'] <= tolerancia
        bloqueo = prev is None or not supera or edad > c['semana_dias']
        return {'bloqueo_medidas': bloqueo, 'estado': 'control_parcial', 'resto_requisitos': 'pendientes'}
    if op == 'veh_opac_termico':
        gas = h['temperatura_gas'] >= c['gas_min'] or (h['motor_impide_temperatura'] and h['autorizacion_manual'] and h['registro_excepcion_y_temperatura'])
        return {'calentamiento_conforme': h['calentamiento_min'] < c['calentamiento_max'], 'bloqueo_lecturas_por_estado_termico': h['en_calentamiento'] or h['temperatura_pared'] < c['pared_min'] or (not gas), 'resto_requisitos': 'pendientes'}
    if op == 'veh_archivo':
        if h['perfil'] == 'opacimetro':
            return {'conservacion_minima_conforme': h['retencion_anos'] >= c['opac_anos'], 'obligacion_almacenar': True}
        inferior = h['resultado_inferior_limite_legal']
        borrable = inferior and h['memoria_llena'] and h['orden_registro_respetado'] and (h['borrado_por'] in ['automatico', 'reparador'])
        return {'obligacion_almacenar': not inferior, 'conservacion_minima_conforme': None if inferior else h['retencion_anos'] >= c['eti_anos'], 'eliminacion_excepcion_permitida': borrable, 'limite_legal': 'dato_externo_no_calculado'}
    if op == 'veh_gas_respuesta':
        ox = h['mensurando'] == 'O2'
        return {'mezcla_ensayo_correcta': h['mezcla_sin_O2'], 'tiempo_conforme': h['segundos'] <= (c['tiempo_O2'] if ox else c['tiempo_gases']), 'indicacion_final_conforme': h['O2_final'] < c['O2_final_max'] if ox else h['porcentaje_valor_final'] >= c['fraccion_gases'], 'resto_ensayos': 'pendientes'}
    if op == 'veh_gas_emp':
        mens = h['mensurando']
        cl = h['clase']
        absval = c[mens + '_' + cl] if mens in ['CO', 'HC'] else c[mens]
        emp = max(absval, h['valor_referencia'] * c['relativo'] / 100)
        return {'EMP': emp, 'unidad': 'ppm_vol' if mens == 'HC' else 'porcentaje_vol', 'error_dentro_EMP': h['error_absoluto'] <= emp, 'resto_ensayos': 'pendientes'}
    if op == 'veh_opac_emp':
        pref = 'eval' if h['fase'] == 'evaluacion' else 'servicio'
        emp = c[pref + '_absoluto'] if h['kref'] < c['umbral_k'] else h['kref'] * c[pref + '_porcentaje'] / 100
        return {'EMP_k': emp, 'error_dentro_EMP': h['error_absoluto'] <= emp, 'alcance': 'solo_comparacion_referencia_no_toda_tabla'}
    if op == 'veh_eti_ensayos':
        reps = c['repeticiones_reparacion'] if h['fase'] == 'reparacion' else c['repeticiones_periodica']
        extra = h['alcance_maximo'] > c['umbral_alcance']
        return {'gases_tabla': [c['gas_' + str(i)] for i in range(1, 6)], 'repeticiones_por_gas': reps, 'gas_adicional': h['alcance_maximo'] * c['porcentaje_extra'] / 100 if extra else None, 'repeticiones_adicional': reps if extra else None, 'EMP_y_repetibilidad': 'remision_OIML_R126_en_vigor_pendiente'}
    if op == 'veh_eti_ciclo':
        if not h['correcta_1'] and (not h['correcta_2']):
            return {'estado': 'abortar_y_nuevo_ciclo', 'resultado_ciclo': None}
        valores = [h['valor_' + str(i)] for i in range(1, 4) if h['correcta_' + str(i)]]
        if len(valores) > 2:
            raise E('I-VEH-CICLO: no hay tercera toma tras dos correctas')
        if len(valores) < 2:
            return {'estado': 'incompleto_solo_informativo', 'resultado_ciclo': None}
        if abs(valores[0] - valores[1]) > c['diferencia_absoluta']:
            return {'estado': 'ciclo_no_valido_diferencia_absoluta', 'resultado_ciclo': None}
        if valores[0] != valores[1]:
            return {'estado': 'pendiente_criterio_porcentaje_15', 'resultado_ciclo': None, 'criterio_porcentaje_15': 'La norma no fija sobre que valor se calcula el 15 %; no se elige denominador.', 'denominador_15_porcentaje': None}
        return {'estado': 'dos_correctas_coincidentes', 'resultado_ciclo': min(valores)}
    if op == 'veh_remision':
        perfil, fase = (h['perfil'], h['fase'])
        mapa = {'analizador_gasolina': {'evaluacion': ('RD_XVI_I', 'RD_XVI_I'), 'reparacion': ('IX_II', 'IX_I'), 'periodica': ('IX_II', 'IX_I')}, 'opacimetro': {'evaluacion': ('X_II', 'X_I'), 'reparacion': ('X_III', 'X_I'), 'periodica': ('X_III', 'X_I')}, 'cinemometro': {'evaluacion': ('XII_II', 'XII_I_3.1.1'), 'reparacion': ('XII_III', 'XII_I_tabla1'), 'periodica': ('XII_IV', 'XII_I_tabla2_salvedad_tramo_aeronave')}, 'etilometro': {'evaluacion': ('XIII_II', 'XIII_II_OIML'), 'reparacion': ('XIII_III', 'XIII_III_OIML_puesta_servicio'), 'periodica': ('XIII_IV', 'XIII_IV_OIML_servicio')}}
        ens, emp = mapa[perfil][fase]
        return {'procedimiento': ens, 'EMP_fuente': emp, 'condiciones': 'XIII_V' if perfil == 'etilometro' else 'documentacion_tipo_y_anexo', 'ensayos_ejecutados': False}
    if op == 'veh_opac_referencia':
        a = h['ultima_comparacion_nacional']
        p = h['fecha_comparacion_propuesta']
        if p is not None and F(p) < F(a):
            raise E('I-ANTECEDENTES: comparación de referencia anterior al antecedente')
        return {'origen': a, 'referencia_siguiente_comparacion': api.desplazar(a, anos=c['anos']), 'frontera_cumplimiento': 'no_resuelta', 'certificado_opacimetro_no_sustituye_origen': True}
    raise E('operador VEH desconocido: ' + op)

def p9_veh_instalar(api):
    for op in p9_veh_DEFINICIONES:
        api.CONTRATOS_NUEVOS[op] = p9_veh_contrato(op)
        api.CONSTANTES_OPERADOR[op] = p9_veh_ESQUEMAS.get(op, {})
        api.DECISIONES_OPERADOR[op] = []
    api.OPERADORES.update(p9_veh_DEFINICIONES)
    anterior = api.evaluar_nuevo

    def despachar(r, hechos):
        if r['operador'] not in p9_veh_DEFINICIONES:
            return anterior(r, hechos)
        entradas = r['entradas'] + api.declaracion_validez(r)['entradas_validez']
        for e in entradas:
            if e['campo'] not in hechos:
                raise api.Insuficiente('falta ' + e['campo'])
            api.validar_valor_nuevo(hechos[e['campo']], e, e['campo'])
        h = {e['campo']: hechos[e['campo']] for e in entradas}
        return p9_veh_evaluar_veh(r, h, api)
    api.evaluar_nuevo = despachar
from decimal import Decimal as p9_pres_Decimal
p9_pres_ESQUEMAS = {'pres_ambito': {}, 'pres_modulos': {}, 'pres_sonido_historico': {'publicacion': 'fecha', 'demora_dias': 'dias', 'publicacion_orden': 'fecha', 'demora_orden_meses': 'meses'}, 'pres_sonido_ajuste': {}, 'pres_sonido_tiempo': {'resolucion': 'Pa2h'}, 'pres_man_emp': {'p1': 'kPa', 'p2': 'kPa', 't1': 'C', 't2': 'C', 'coef': 'kPa_C', 'e1': 'kPa', 'e2': 'kPa', 'e3': 'kPa', 'factor_montaje': 'numero'}, 'pres_man_adecuacion': {'resolucion': 'kPa', 'tiempo': 's', 'refresco': 'Hz'}, 'pres_man_cero': {}, 'pres_refract_emp': {'nuevo_n': 'escalon', 'nuevo_brix': 'escalon', 'nuevo_alcohol': 'escalon', 'servicio_n': 'escalon', 'servicio_brix': 'escalon', 'servicio_alcohol': 'escalon'}, 'pres_refract_deriva': {'horas': 'horas', 'minutos': 'minutos', 'fraccion': 'numero'}, 'pres_refract_antiguo': {'frontera': 'fecha', 'temperatura': 'C', 'alcohol_min': 'g_L', 'alcohol_max': 'g_L'}, 'pres_refract_material': {'resolucion': 'Brix', 'temperatura': 'C', 'inc_glucosa': 'porcentaje', 'factor_glucosa': 'numero', 'divisor': 'numero', 'nuevo_n': 'escalon', 'nuevo_brix': 'escalon', 'nuevo_alcohol': 'escalon', 'servicio_n': 'escalon', 'servicio_brix': 'escalon', 'servicio_alcohol': 'escalon'}, 'pres_refract_muestra': {'estatica': 'cL', 'dinamica': 'cL', 'minutos': 'minutos', 'inc_cero': 'escalon'}}

def p9_pres_declaracion(r):
    return {'entradas_validez': [], 'invariantes': [{'id': 'I-' + r['operador'].upper().replace('_', '-'), 'preceptos': r['fuentes'], 'condicion': 'Tipos y dominios cerrados; sin inferir fechas ni identidad. Si existen, verificacion >= puesta en servicio; cifras exactas y no negativas salvo temperatura. El incumplimiento da salida negativa, la falta documental explícita da pendiente.'}], 'revision_validez': {'preceptos': r['fuentes'], 'conclusion': 'Validar todas las entradas y relaciones conocidas antes del cálculo; sin aprobación humana ni autorización global.'}}

def p9_pres_evaluar_pres(r, hechos, api):
    specs = r['entradas']
    h = {}
    for s in specs:
        k = s['campo']
        if k not in hechos:
            raise api.Insuficiente('falta ' + k)
        v = hechos[k]
        if s['tipo'] == 'numero' and v is not None:
            if not api.numero_valido(v) or (v < 0 and k != 'temperatura_C'):
                raise api.Insuficiente('I-PRES-NUMERO: cifra inválida ' + k)
        else:
            api.validar_valor_nuevo(v, s, k)
        h[k] = v
    if 'perfil' in h and h['perfil'] not in r['perfiles_aplicables']:
        raise api.Insuficiente('I-PRES-PERFIL: hecho ajeno a regla')
    c = r['constantes']
    op = r['operador']
    if op == 'pres_ambito':
        objetos = {'manometro_mec': {'presion_neumaticos_vehiculo_motor'}, 'manometro_electronico': {'presion_neumaticos_vehiculo_motor'}, 'sonido': {'sonometro', 'exposicion_sonora', 'calibrador_acustico_asociado'}, 'refractometro': {'mosto_uva', 'mosto_concentrado', 'mosto_concentrado_rectificado'}}
        return {'dentro_objeto_anexo': h['objeto'] in objetos[h['perfil']], 'alcance': 'solo_objeto_no_exencion_de_otra_norma'}
    if op == 'pres_modulos':
        combinaciones = [['B', 'D'], ['B', 'F'], ['H1']]
        if h['perfil'].startswith('manometro'):
            combinaciones += [['G']]
        if h['perfil'] == 'manometro_mec':
            combinaciones += [['F1'], ['D1']]
        return {'combinacion_admitida_via_nacional': h['combinacion'] in combinaciones, 'regimen': 'nacional_Orden_ICT155_no_MID_por_analogia'}
    if op == 'pres_sonido_historico':
        d = h['documento_modelo']
        if d is not None and d['instrumento'] != h['instrumento']:
            raise api.Insuficiente('I-PRES-IDENTIDAD: modelo de otro instrumento')
        entrada_orden = api.fecha(api.desplazar(c['publicacion_orden'], meses=c['demora_orden_meses']))
        puesta = h['fecha_puesta_servicio']
        if puesta is None:
            return {'regimen_ensayos': 'pendiente_fecha_puesta_servicio', 'continuidad_por_ap7': None}
        if api.fecha(puesta) > entrada_orden:
            return {'regimen_ensayos': 'apendice_III_actual', 'continuidad_por_ap7': 'no_es_su_supuesto'}
        if api.fecha(puesta) == entrada_orden:
            return {'regimen_ensayos': 'pendiente_estado_servicio_entrada_orden', 'continuidad_por_ap7': None}
        if d is None:
            return {'regimen_ensayos': 'pendiente_documentacion_modelo', 'continuidad_por_ap7': None}
        from datetime import timedelta as timedelta
        entrada = api.fecha(c['publicacion']) + timedelta(days=c['demora_dias'])
        historico = api.fecha(d['fecha_cumplimiento_modelo']) < entrada
        legal = d['regimen'] in (['ITC2845_2007'] if h['tipo'] == 'exposicion_sonora' else ['FOM1998', 'ITC2845_2007'])
        if historico and (not legal):
            return {'regimen_ensayos': 'pendiente_regimen_historico_incompatible', 'continuidad_por_ap7': None}
        if not historico:
            return {'regimen_ensayos': 'apendice_III_actual', 'continuidad_por_ap7': 'no_es_su_supuesto'}
        return {'regimen_ensayos': 'apendice_III_actual_aceptacion_plena' if h['opta_ensayos_actuales'] else d['regimen'] + '_durante_vida_util', 'continuidad_por_ap7': d['controles_historicos_superados']}
    if op == 'pres_sonido_ajuste':
        aplicable = h['tipo'] in ['sonometro', 'exposicion_sonora']
        return {'precintar_ajuste': aplicable and h['ajuste'] == 'mecanico', 'anotar_eventos_certificado': aplicable and h['ajuste'] == 'software', 'clausula_no_ajuste_en_certificado': aplicable, 'anulacion_por_ajuste_posterior': aplicable and h['ajuste_posterior'], 'ensayos': 'remision_apendice_III_no_ejecutados'}
    if op == 'pres_sonido_tiempo':
        return {'tiempos_mas_cortos_admisibles': h['resolucion_Pa2h'] < c['resolucion'] and h['compatibles_norma'], 'alcance': 'solo_medidor_exposicion_apIII3'}
    if op == 'pres_man_emp':
        return {'emp_kPa': None, 'satisface_solo_limite': None, 'otros_ensayos': 'pendientes', 'estado': 'bloqueado_hasta_cotejo_tablas_fuente_oficial', 'datos_a_cotejar': h}
    if op == 'pres_man_adecuacion':
        criterio = h['criterio']
        v = h['medida']
        if h['perfil'] == 'manometro_mec' and criterio.endswith('_electronico'):
            return {'satisface_solo_criterio': None, 'criterio': criterio, 'estado': 'requisito_especifico_electronico_no_aplica_al_mecanico'}
        ok = {'resolucion_digital': v <= c['resolucion'], 'escalon_analogico': v == c['resolucion'], 'primera_indicacion_electronico': v <= c['tiempo'], 'refresco_electronico': v >= c['refresco']}[criterio]
        return {'satisface_solo_criterio': ok, 'criterio': criterio}
    if op == 'pres_man_cero':
        return {'dispositivo_admitido_por_5_6': h['modo'] in ['automatico', 'apagado_encendido'] or (h['modo'] == 'semiautomatico' and h['comprueba_presion_atmosferica']), 'otros_requisitos': 'pendientes'}
    if op == 'pres_refract_emp':
        return {'emp_escalones': None, 'satisface_solo_limite_sin_redondeo': None, 'otros_ensayos': 'pendientes', 'estado': 'bloqueado_hasta_cotejo_tablas_fuente_oficial', 'datos_a_cotejar': h}
    if op == 'pres_refract_deriva':
        tiempo = c['horas'] * 60 if h['fase'] == 'conformidad' else c['minutos']
        return {'duracion_minima_minutos': tiempo, 'ensayo_duracion_suficiente': h['duracion_minutos'] >= tiempo, 'deriva_estrictamente_inferior_medio_escalon': h['deriva_absoluta_escalones'] < c['fraccion']}
    if op == 'pres_refract_antiguo':
        puesta = h['fecha_puesta_servicio_acreditada']
        ver = h['fecha_verificacion']
        if puesta is not None and ver is not None and (api.fecha(ver) < api.fecha(puesta)):
            raise api.Insuficiente('I-PRES-ANTECEDENTES: verificación anterior a puesta en servicio')
        if puesta is None:
            return {'presentable_por_apendice_V': None, 'estado': 'pendiente_fecha_acreditada'}
        ok = api.fecha(puesta) < api.fecha(c['frontera']) and h['numero_serie'] is not None and h['precintable'] and (h['escala'] != 'Baume') and h['lectura_automatica'] and (h['compensacion_C'] == c['temperatura']) and (h['escala'] != 'alcohol' or c['alcohol_min'] <= h['g_L_por_uno_vol'] <= c['alcohol_max'])
        return {'presentable_por_apendice_V': ok, 'estado': 'condiciones_documentales_no_verificacion_superada', 'leyenda_en_instrumento_y_certificado_si_supera': True, 'sin_modo_escalon_verificacion': 'aplica_EMP_apendice_I_4_no_exencion'}
    if op == 'pres_refract_material':
        d = h['certificado_material']
        if d is None:
            return {'satisface_solo_requisitos_material': None, 'estado': 'pendiente_certificado_material'}
        if d['material'] != h['material_id']:
            raise api.Insuficiente('I-PRES-IDENTIDAD: certificado de otro material')
        pesada = h['via'] == 'sacarosa_pesada'
        if pesada:
            ok = d['emisor'] in ['INM_MRA', 'laboratorio_acreditado_material'] and h['balanza_clase_I']
        else:
            return {'satisface_solo_requisitos_material': None, 'estado': 'solo_requisitos_representados_conversion_tablas_bloqueada_hasta_cotejo_oficial', 'glucosa_factor_tabla': None, 'datos_a_cotejar': h}
        return {'satisface_solo_requisitos_material': ok, 'estado': 'solo_requisitos_representados_conversion_tablas_bloqueada_hasta_cotejo_oficial', 'glucosa_factor_tabla': None}
    if op == 'pres_refract_muestra':
        criterio = h['criterio']
        v = h['medida']
        ok = {'volumen_estatico_tipoI': v >= c['estatica'], 'volumen_dinamico_tipoI': v >= c['dinamica'], 'indicacion_tras_paso_dinamico_minutos': v <= c['minutos'], 'incertidumbre_cero_escalones': v <= c['inc_cero']}[criterio]
        return {'satisface_solo_criterio': ok, 'criterio': criterio}
    raise api.Insuficiente('operación PRES desconocida')

def p9_pres_instalar(api):
    if getattr(api, '_pres_instalado', False):
        return
    api._pres_instalado = True
    api.OPERADORES.update(p9_pres_ESQUEMAS)
    api.CONSTANTES_OPERADOR.update(p9_pres_ESQUEMAS)
    api.NUMEROS.update(mitad=p9_pres_Decimal('0.5'), cuarto=p9_pres_Decimal('0.25'), tercio=3, siguiente=1)
    original_ancla = api.valor_anclado

    def extraer_ancla(a):
        if a.get('conversion_millares_es'):
            import re as re
            token = a['literal'][a['inicio_numero']:a['fin_numero']]
            if not re.fullmatch('[0-9]{1,3}(?:\\.[0-9]{3})+', token):
                raise api.Insuficiente('I-CONSTANTE: millares españoles inválidos')
            return int(token.replace('.', ''))
        return original_ancla(a)
    api.valor_anclado = extraer_ancla
    original_declaracion = api.declaracion_validez
    original_evaluar = api._evaluar
    api.declaracion_validez = lambda r: p9_pres_declaracion(r) if r['operador'] in p9_pres_ESQUEMAS else original_declaracion(r)
    api._evaluar = lambda r, hechos: p9_pres_evaluar_pres(r, hechos, api) if r['operador'] in p9_pres_ESQUEMAS else original_evaluar(r, hechos)
_ancla_pre_v9 = valor_anclado

def valor_anclado(a):
    if a.get('formato') == 'semana_siete_dias':
        if a['literal'] != 'semanalmente' or a['unidad'] != 'dias':
            raise Insuficiente('ancla semanal inválida')
        return 7
    if a.get('formato') == 'anualmente_un_ano':
        if a['literal'] != 'anualmente' or a['unidad'] != 'anos':
            raise Insuficiente('ancla anual inválida')
        return 1
    return _ancla_pre_v9(a)

def evaluar_reparacion_q3_jdap2(regla_regimen, regla_general, hechos_regimen, hechos_reparacion):
    """Public CI documentation."""
    if regla_regimen['id'] != 'AG-REGIMEN' or regla_general['id'] != 'AG-REPARACION-5' or regla_general['operador'] != 'reparacion':
        raise Insuficiente('J01: referencias de regimen/calculo general invalidas')
    criterio = salida_evaluada(regla_regimen, hechos_regimen)
    if not criterio.get('autoriza_reparacion'):
        return {'regimen_Q3': criterio, 'calculo_regimen_general': None, 'autoriza_uso': False}
    return {'regimen_Q3': criterio, 'calculo_regimen_general': salida_evaluada(regla_general, hechos_reparacion), 'autoriza_uso': False}
import sys as _sys
for _instalar in [p9_elec_instalar, p9_liq_instalar, p9_dim_instalar, p9_veh_instalar, p9_pres_instalar]:
    _instalar(_sys.modules[__name__])
