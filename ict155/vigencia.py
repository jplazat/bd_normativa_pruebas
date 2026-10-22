"""Public CI documentation."""
from __future__ import annotations
import argparse
import copy
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from . import config, consulta, db
USER_AGENT = 'ict155-bd-normativa (consulta de vigencia)'
TIMEOUT = 30
PAUSA = 0.3
REINTENTOS = 1
ESPERA_REINTENTO = 2.0
URL_BOE_API = 'https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/'
URL_BOE_XML = 'https://www.boe.es/diario_boe/xml.php?id='
URL_BOE_DOC = 'https://www.boe.es/buscar/doc.php?id='
URL_SPARQL = 'https://publications.europa.eu/webapi/rdf/sparql'
URL_EURLEX = 'https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:'
LENGUA_ES = 'http://publications.europa.eu/resource/authority/language/SPA'
LENGUA_EN = 'http://publications.europa.eu/resource/authority/language/ENG'
AVISO_BOE = 'Fuente: Agencia Estatal Boletín Oficial del Estado; el texto consolidado es informativo'
AVISO_CELLAR = 'Fuente: Oficina de Publicaciones de la UE (CELLAR); solo el Diario Oficial es auténtico'
ESQUEMA = 1
RE_BOE = re.compile('^BOE-[A-Z]-\\d{4}-\\d+$')
RE_CELEX = re.compile('^[0-9]\\d{4}[A-Z]{1,2}\\d{4}$')
RE_BASE_BOE = re.compile('^BOE-A-\\d{4}-\\d+$')
RE_BASE_CELEX = re.compile('^CELEX-(3\\d{4}[A-Z]{1,2}\\d{4})$')
CODIGOS_DEROGA_TOTAL = {210, 212, 217}
CODIGOS_DEROGA = set(range(210, 218))
CODIGOS_MODIFICA = {220, 221, 230, 231, 235, 245, 247, 270, 271, 272, 303, 401, 404, 406, 407, 408}
CODIGO_SE_DECLARA = 470
RE_EFECTO_JUDICIAL = re.compile('(?i)inconstitucional|nulidad|\\bnul[oa]s?\\b|\\banul')
IDENTIFICADOR_OFICIAL: dict[str, str] = {'ICT155-DOC-BOE_Directriz1-2017_CSM_organismos_control_y_OAVM': 'BOE-A-2017-13543', 'ICT155-DOC-BOE_RD188-2016_equipos_radioelectricos_texto_original_2016_NO_CONSOLIDADO': 'BOE-A-2016-4444', 'ICT155-DOC-Ley_11_2022_Telecom_consolidado_BOE-A-2022-10757': 'BOE-A-2022-10757', 'ICT155-DOC-DOUE_Decision_768-2008-CE_marco_comun_comercializacion_modulos_es': '32008D0768', 'ICT155-DOC-DOUE_Directiva_2014-31-UE_IPFNA_texto_original_2014_VIGENTE_sin_modificar_es': '32014L0031', 'ICT155-DOC-DOUE_Directiva_2014-53-UE_RED_texto_original_2014_en': '32014L0053', 'DOUE-2026-706': '32026L0706', 'ICT155-DOC-DOUE_Reglamento_Delegado_2022-315_modifica_2016-161_es': '32022R0315', 'ICT155-DOC-DOUE_Reglamento_CE_37-2005_temperaturas_ultracongelados_en': '32005R0037', 'ICT155-DOC-DOUE_Reglamento_CE_37-2005_temperaturas_ultracongelados_es': '32005R0037', 'ICT155-DOC-DOUE_Reglamento_CE_765-2008_texto_original_2008_NO_CITAR_arts15-29_SUPRIMIDOS_es': '32008R0765', 'ICT155-DOC-DOUE_Reglamento_Delegado_2022-30_ciberseguridad_RED_en_COMPLETO': '32022R0030', 'ICT155-DOC-DOUE_Reglamento_Delegado_2022-30_ciberseguridad_RED_es_TRUNCADO': '32022R0030', 'DOUE-2023-2444': '32023R2444', 'DOUE-2024-2847': '32024R2847', 'DOUE-2025-138': '32025D0138', 'DOUE-2026-339': '32026R0339', 'ICT155-DOC-Directiva_98_34_CE_consolidada_CELEX-01998L0034-20130101': '31998L0034', 'ICT155-DOC-Directiva_98_34_CE_original_CELEX-31998L0034': '31998L0034'}

class ErrorDeFuente(Exception):
    """Public CI documentation."""
_ultima_peticion = [0.0]
_CACHE: dict[tuple, object] = {}

def limpiar_cache() -> None:
    _CACHE.clear()

def _descargar(url: str, accept: str) -> tuple[int, bytes]:
    """Public CI documentation."""
    espera = PAUSA - (time.monotonic() - _ultima_peticion[0])
    if espera > 0:
        time.sleep(espera)
    peticion = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as r:
            return (r.status, r.read())
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read()
        except Exception:
            cuerpo = b''
        return (e.code, cuerpo)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        servidor = urllib.parse.urlsplit(url).netloc
        raise ErrorDeFuente(f"sin respuesta de {servidor}: {getattr(e, 'reason', e)}") from e
    finally:
        _ultima_peticion[0] = time.monotonic()

def _pedir(url: str, accept: str) -> tuple[int, bytes]:
    """Public CI documentation."""
    for intento in range(REINTENTOS + 1):
        ultimo = intento == REINTENTOS
        try:
            codigo, cuerpo = _descargar(url, accept)
        except ErrorDeFuente:
            if ultimo:
                raise
        else:
            if codigo < 500 or ultimo:
                return (codigo, cuerpo)
        time.sleep(ESPERA_REINTENTO)
    raise ErrorDeFuente('sin respuesta')

def _texto(s) -> str:
    return ' '.join(str(s or '').split())

def _como_lista(x) -> list:
    """Public CI documentation."""
    if x is None or x == '' or x == []:
        return []
    return x if isinstance(x, list) else [x]

def _fecha_boe(s) -> str | None:
    """Public CI documentation."""
    m = re.match('^(\\d{4})(\\d{2})(\\d{2})', (s or '').strip())
    return f'{m[1]}-{m[2]}-{m[3]}' if m else None

def _meta_json(cuerpo: bytes) -> dict:
    d = json.loads(cuerpo.decode('utf-8'))
    filas = _como_lista(d.get('data'))
    if not filas:
        raise ErrorDeFuente('BOE: /metadatos sin datos')
    f = filas[0]
    return {'titulo': _texto(f.get('titulo')), 'derogada': f.get('estatus_derogacion') == 'S', 'fecha_derogacion': _fecha_boe(f.get('fecha_derogacion')), 'anulada': f.get('estatus_anulacion') == 'S', 'fecha_anulacion': _fecha_boe(f.get('fecha_anulacion')), 'agotada': f.get('vigencia_agotada') == 'S', 'fecha_actualizacion': _fecha_boe(f.get('fecha_actualizacion')), 'fecha_publicacion': _fecha_boe(f.get('fecha_publicacion')), 'fecha_vigencia': _fecha_boe(f.get('fecha_vigencia'))}

def _ref(id_norma, codigo, relacion, texto) -> dict | None:
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        return None
    id_norma = _texto(id_norma)
    if not id_norma:
        return None
    return {'id': id_norma, 'codigo': codigo, 'relacion': _texto(relacion), 'texto': _texto(texto).lstrip(', ').strip()}

def _refs_json(cuerpo: bytes) -> list[dict]:
    """Public CI documentation."""
    d = json.loads(cuerpo.decode('utf-8'))
    filas = _como_lista(d.get('data'))
    if not filas:
        raise ErrorDeFuente('BOE: /analisis sin datos')
    refs = filas[0].get('referencias') or {}
    salida = []
    for grupo in _como_lista(refs.get('posteriores')):
        elementos = _como_lista(grupo.get('posterior')) if isinstance(grupo, dict) and 'posterior' in grupo else [grupo]
        for e in elementos:
            if not isinstance(e, dict):
                continue
            rel = e.get('relacion') or {}
            r = _ref(e.get('id_norma'), rel.get('codigo'), rel.get('texto'), e.get('texto'))
            if r:
                salida.append(r)
    return salida

def _raiz_xml_boe(cuerpo: bytes) -> ET.Element:
    try:
        raiz = ET.fromstring(cuerpo)
    except ET.ParseError as e:
        raise ErrorDeFuente(f'BOE: XML ilegible ({e})') from e
    if raiz.tag == 'error':
        raise ErrorDeFuente('BOE: ' + (_texto(raiz.findtext('descripcion')) or 'documento desconocido'))
    if raiz.find('metadatos') is None:
        raise ErrorDeFuente('BOE: el XML no trae metadatos')
    return raiz

def _meta_xml(raiz: ET.Element) -> dict:
    m = raiz.find('metadatos')

    def t(nombre):
        return (m.findtext(nombre) or '').strip()
    return {'titulo': _texto(t('titulo')), 'derogada': t('estatus_derogacion') == 'S', 'fecha_derogacion': _fecha_boe(t('fecha_derogacion')), 'anulada': t('judicialmente_anulada') == 'S', 'fecha_anulacion': _fecha_boe(t('fecha_anulacion')), 'agotada': t('vigencia_agotada') == 'S', 'fecha_actualizacion': _fecha_boe(raiz.get('fecha_actualizacion')), 'fecha_publicacion': _fecha_boe(t('fecha_publicacion')), 'fecha_vigencia': _fecha_boe(t('fecha_vigencia'))}

def _refs_xml(raiz: ET.Element) -> list[dict]:
    salida = []
    for p in raiz.findall('./analisis/referencias/posteriores/posterior'):
        palabra = p.find('palabra')
        if palabra is None:
            continue
        r = _ref(p.get('referencia'), palabra.get('codigo'), palabra.text, p.findtext('texto'))
        if r:
            salida.append(r)
    return salida

def _fechas_modificadora(id_norma: str) -> tuple[str | None, str | None, str | None]:
    """Public CI documentation."""
    if not RE_BOE.match(id_norma):
        return (None, None, None)
    clave = ('FECHAS', id_norma)
    if clave in _CACHE:
        return _CACHE[clave]
    try:
        codigo, cuerpo = _pedir(URL_BOE_XML + id_norma, 'application/xml')
        if codigo != 200:
            raise ErrorDeFuente(f'BOE: HTTP {codigo} en diario_boe de {id_norma}')
        meta = _meta_xml(_raiz_xml_boe(cuerpo))
    except ErrorDeFuente as e:
        return (None, None, str(e))
    resultado = (meta['fecha_publicacion'], meta['fecha_vigencia'], None)
    _CACHE[clave] = resultado
    return resultado

def _clasifica_ref(r: dict) -> str | None:
    c = r['codigo']
    if c in CODIGOS_DEROGA:
        return 'deroga'
    if c in CODIGOS_MODIFICA:
        return 'modifica'
    if c == CODIGO_SE_DECLARA and RE_EFECTO_JUDICIAL.search(r['texto']):
        return 'judicial'
    return None

def _boe_con_error(id_boe: str, mensaje: str) -> dict:
    return {'fuente': 'BOE', 'id': id_boe, 'titulo': None, 'estado': None, 'fecha_derogacion': None, 'derogada_por': [], 'modificaciones': [], 'fecha_actualizacion': None, 'url': URL_BOE_DOC + id_boe, 'error': mensaje}

def _consultar_boe(id_boe: str) -> dict:
    codigo, cuerpo = _pedir(URL_BOE_API + id_boe + '/metadatos', 'application/json')
    if codigo == 200:
        meta = _meta_json(cuerpo)
        codigo2, cuerpo2 = _pedir(URL_BOE_API + id_boe + '/analisis', 'application/json')
        if codigo2 != 200:
            raise ErrorDeFuente(f'BOE: HTTP {codigo2} en /analisis de {id_boe}')
        refs = _refs_json(cuerpo2)
        origen = 'legislacion-consolidada'
    elif codigo == 404:
        codigo2, cuerpo2 = _pedir(URL_BOE_XML + id_boe, 'application/xml')
        if codigo2 != 200:
            raise ErrorDeFuente(f'BOE: HTTP {codigo2} en diario_boe de {id_boe}')
        raiz = _raiz_xml_boe(cuerpo2)
        meta, refs = (_meta_xml(raiz), _refs_xml(raiz))
        origen = 'diario_boe'
    else:
        raise ErrorDeFuente(f'BOE: HTTP {codigo} en /metadatos de {id_boe}')
    if meta['anulada']:
        estado = 'anulada'
    elif meta['derogada']:
        estado = 'derogada'
    elif meta['agotada']:
        estado = 'vigencia_agotada'
    else:
        estado = 'vigente'
    derogada_por, pendientes, vistos = ([], [], set())
    for r in refs:
        if _clasifica_ref(r) is None:
            continue
        clave = (r['id'], r['codigo'], r['texto'])
        if clave in vistos:
            continue
        vistos.add(clave)
        if estado == 'derogada' and r['codigo'] in CODIGOS_DEROGA_TOTAL:
            derogada_por.append({'id': r['id'], 'texto': r['texto']})
        else:
            pendientes.append(r)
    modificaciones = []
    for r in pendientes:
        publicacion, vigencia, error = _fechas_modificadora(r['id'])
        m = {'id': r['id'], 'relacion': r['relacion'], 'codigo': r['codigo'], 'texto': r['texto'], 'fecha_publicacion': publicacion, 'fecha_vigencia': vigencia}
        if error:
            m['error_fecha'] = error
        modificaciones.append(m)
    modificaciones.sort(key=lambda m: (m['fecha_publicacion'] or '9999', m['id'], m['codigo']))
    return {'fuente': 'BOE', 'id': id_boe, 'titulo': meta['titulo'], 'estado': estado, 'fecha_derogacion': meta['fecha_derogacion'], 'fecha_anulacion': meta['fecha_anulacion'], 'derogada_por': derogada_por, 'modificaciones': modificaciones, 'fecha_actualizacion': meta['fecha_actualizacion'], 'origen': origen, 'url': URL_BOE_DOC + id_boe}

def consultar_boe(id_boe: str) -> dict:
    """Public CI documentation."""
    id_boe = (id_boe or '').strip()
    clave = ('BOE', id_boe)
    if clave in _CACHE:
        return copy.deepcopy(_CACHE[clave])
    if not RE_BOE.match(id_boe):
        return _boe_con_error(id_boe, 'identificador del BOE no válido')
    try:
        resultado = _consultar_boe(id_boe)
    except ErrorDeFuente as e:
        return _boe_con_error(id_boe, str(e))
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return _boe_con_error(id_boe, f'BOE: respuesta inesperada ({type(e).__name__}: {e})')
    _CACHE[clave] = resultado
    return copy.deepcopy(resultado)
_PREFIJOS = 'PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n'

def _sparql(consulta: str) -> list[dict]:
    """Public CI documentation."""
    url = URL_SPARQL + '?' + urllib.parse.urlencode({'query': _PREFIJOS + consulta})
    codigo, cuerpo = _pedir(url, 'application/sparql-results+json')
    if codigo != 200:
        raise ErrorDeFuente(f'CELLAR: HTTP {codigo}')
    try:
        d = json.loads(cuerpo.decode('utf-8'))
        enlaces = d['results']['bindings']
    except (ValueError, KeyError, TypeError) as e:
        raise ErrorDeFuente(f'CELLAR: respuesta que no es SPARQL JSON ({type(e).__name__})') from e
    return [{k: v.get('value') for k, v in fila.items()} for fila in enlaces]

def _obra(celex: str) -> str:
    return f'?w cdm:resource_legal_id_celex "{celex}"^^xsd:string .'

def _titulo_opcional(variable: str, lengua: str, destino: str) -> str:
    return f'OPTIONAL {{ ?e{destino} cdm:expression_belongs_to_work {variable} ; cdm:expression_title ?{destino} ; cdm:expression_uses_language <{lengua}> }}'
SIN_FECHA_CELLAR = '1001-01-01'

def _fecha_iso(s) -> str | None:
    m = re.match('^(\\d{4}-\\d{2}-\\d{2})', (s or '').strip())
    return m[1] if m and m[1] != SIN_FECHA_CELLAR else None

def _booleano(s) -> bool | None:
    s = (s or '').strip().lower()
    if s in ('1', 'true'):
        return True
    if s in ('0', 'false'):
        return False
    return None

def _normas_relacionadas(celex: str, propiedad: str) -> list[dict]:
    """Public CI documentation."""
    filas = _sparql(f"SELECT ?c ?fecha ?vigor ?titulo ?titulo_en WHERE {{\n {_obra(celex)}\n ?x cdm:{propiedad} ?w .\n ?x cdm:resource_legal_id_celex ?c .\n OPTIONAL {{ ?x cdm:work_date_document ?fecha }}\n OPTIONAL {{ ?x cdm:resource_legal_date_entry-into-force ?vigor }}\n {_titulo_opcional('?x', LENGUA_ES, 'titulo')}\n {_titulo_opcional('?x', LENGUA_EN, 'titulo_en')}\n}} LIMIT 5000")
    grupos: dict[str, dict] = {}
    for f in filas:
        g = grupos.setdefault(f['c'], {'fechas': set(), 'vigores': set(), 'titulo': None, 'titulo_en': None})
        if _fecha_iso(f.get('fecha')):
            g['fechas'].add(_fecha_iso(f['fecha']))
        if _fecha_iso(f.get('vigor')):
            g['vigores'].add(_fecha_iso(f['vigor']))
        g['titulo'] = g['titulo'] or _texto(f.get('titulo')) or None
        g['titulo_en'] = g['titulo_en'] or _texto(f.get('titulo_en')) or None
    salida = []
    for celex_x, g in grupos.items():
        vigores = sorted(g['vigores'])
        entrada = {'id': celex_x, 'titulo': g['titulo'] or g['titulo_en'], 'fecha_documento': min(g['fechas']) if g['fechas'] else None, 'fecha_vigor': vigores[0] if vigores else None}
        if len(vigores) > 1:
            entrada['fechas_vigor'] = vigores
        salida.append(entrada)
    salida.sort(key=lambda m: (m['fecha_documento'] or '9999', m['id']))
    return salida

def _cellar_con_error(celex: str, mensaje: str) -> dict:
    return {'fuente': 'CELLAR', 'id': celex, 'titulo': None, 'estado': None, 'fecha_fin_validez': None, 'fecha_entrada_vigor': None, 'derogada_por': [], 'modificaciones': [], 'ultima_consolidada': None, 'url': URL_EURLEX + celex, 'error': mensaje}

def _consultar_cellar(celex: str) -> dict:
    filas = _sparql(f"SELECT ?inforce ?endval ?eif ?titulo ?titulo_en WHERE {{\n {_obra(celex)}\n OPTIONAL {{ ?w cdm:resource_legal_in-force ?inforce }}\n OPTIONAL {{ ?w cdm:resource_legal_date_end-of-validity ?endval }}\n OPTIONAL {{ ?w cdm:resource_legal_date_entry-into-force ?eif }}\n {_titulo_opcional('?w', LENGUA_ES, 'titulo')}\n {_titulo_opcional('?w', LENGUA_EN, 'titulo_en')}\n}} LIMIT 500")
    if not filas:
        raise ErrorDeFuente(f'CELLAR: no existe el CELEX {celex}')
    en_vigor = {_booleano(f.get('inforce')) for f in filas} - {None}
    if len(en_vigor) > 1:
        raise ErrorDeFuente(f'CELLAR: valores contradictorios de «en vigor» para {celex}')
    fines = sorted({_fecha_iso(f.get('endval')) for f in filas} - {None})
    fin_validez = fines[-1] if fines and fines[-1] != '9999-12-31' else None
    vigores = sorted({_fecha_iso(f.get('eif')) for f in filas} - {None})
    titulo = next((_texto(f['titulo']) for f in filas if f.get('titulo')), None) or next((_texto(f['titulo_en']) for f in filas if f.get('titulo_en')), None)
    derogan = _normas_relacionadas(celex, 'resource_legal_repeals_resource_legal')
    modifican = _normas_relacionadas(celex, 'resource_legal_amends_resource_legal')
    consolidada = _sparql(f'SELECT ?cc ?fecha WHERE {{\n {_obra(celex)}\n ?c cdm:act_consolidated_based_on_resource_legal ?w .\n ?c cdm:resource_legal_id_celex ?cc .\n ?c cdm:act_consolidated_date ?fecha .\n}} ORDER BY DESC(?fecha) LIMIT 1')
    resultado = {'fuente': 'CELLAR', 'id': celex, 'titulo': titulo, 'estado': None, 'fecha_fin_validez': fin_validez, 'fecha_entrada_vigor': vigores[0] if vigores else None, 'derogada_por': [], 'modificaciones': [], 'ultima_consolidada': {'id': consolidada[0]['cc'], 'fecha': _fecha_iso(consolidada[0]['fecha'])} if consolidada else None, 'url': URL_EURLEX + celex}
    if not en_vigor:
        resultado['error'] = 'CELLAR no informa de si la norma está en vigor'
        resultado['modificaciones'] = [dict(m, relacion='MODIFICA') for m in modifican]
        return resultado
    if next(iter(en_vigor)):
        resultado['estado'] = 'vigente'
        resultado['modificaciones'] = sorted([dict(m, relacion='MODIFICA') for m in modifican] + [dict(m, relacion='DEROGA (parcial o con efecto futuro)') for m in derogan], key=lambda m: (m['fecha_documento'] or '9999', m['id']))
    else:
        resultado['derogada_por'] = derogan
        resultado['modificaciones'] = [dict(m, relacion='MODIFICA') for m in modifican]
        if derogan:
            resultado['estado'] = 'derogada'
        elif fin_validez:
            resultado['estado'] = 'vigencia_agotada'
        else:
            resultado['error'] = 'CELLAR dice que no está en vigor, sin norma derogatoria ni fin de validez'
    return resultado

def consultar_cellar(celex: str) -> dict:
    """Public CI documentation."""
    celex = (celex or '').strip()
    clave = ('CELLAR', celex)
    if clave in _CACHE:
        return copy.deepcopy(_CACHE[clave])
    if not RE_CELEX.match(celex):
        return _cellar_con_error(celex, 'CELEX no válido')
    try:
        resultado = _consultar_cellar(celex)
    except ErrorDeFuente as e:
        return _cellar_con_error(celex, str(e))
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return _cellar_con_error(celex, f'CELLAR: respuesta inesperada ({type(e).__name__}: {e})')
    _CACHE[clave] = resultado
    return copy.deepcopy(resultado)

def identificador_oficial(ident_base: str) -> str | None:
    """Public CI documentation."""
    if ident_base in IDENTIFICADOR_OFICIAL:
        return IDENTIFICADOR_OFICIAL[ident_base]
    if RE_BASE_BOE.match(ident_base):
        return ident_base
    m = RE_BASE_CELEX.match(ident_base)
    return m[1] if m else None

def _consultar(oficial: str) -> dict:
    if oficial.startswith('BOE-'):
        return consultar_boe(oficial)
    return consultar_cellar(oficial)

def _fecha_de_base(s) -> tuple[str | None, bool]:
    """Public CI documentation."""
    s = (s or '').strip()
    if re.match('^\\d{4}-\\d{2}-\\d{2}', s):
        return (s[:10], False)
    if re.match('^\\d{4}-\\d{2}$', s):
        return (s + '-01', True)
    if re.match('^\\d{4}$', s):
        return (s + '-01-01', True)
    return (None, False)

def fecha_de_la_version(con: sqlite3.Connection, obra_id: int) -> dict:
    """Public CI documentation."""
    candidatas = []
    for f in con.execute('SELECT fecha_consolidacion, fecha_edicion FROM version WHERE obra_id=?', (obra_id,)):
        for origen in ('fecha_consolidacion', 'fecha_edicion'):
            fecha, aprox = _fecha_de_base(f[origen])
            if fecha:
                candidatas.append((aprox, fecha, origen))
                break
    if not candidatas:
        return {'fecha_version': None, 'fecha_version_origen': None, 'fecha_version_aproximada': False}
    aprox, fecha, origen = min(candidatas)
    return {'fecha_version': fecha, 'fecha_version_origen': origen, 'fecha_version_aproximada': aprox}

def _fechas_efecto(mod: dict) -> list[str]:
    """Public CI documentation."""
    if 'fecha_publicacion' in mod:
        return [mod['fecha_publicacion']] if mod['fecha_publicacion'] else []
    vigores = mod.get('fechas_vigor') or ([mod['fecha_vigor']] if mod.get('fecha_vigor') else [])
    if vigores:
        return sorted(vigores)
    return [mod['fecha_documento']] if mod.get('fecha_documento') else []

def _anio_del_id(ident: str) -> int | None:
    m = re.match('^[A-Z]{3,4}-[A-Z]-(\\d{4})-\\d+$', ident) or re.match('^[0-9](\\d{4})[A-Z]', ident)
    return int(m[1]) if m else None

def modificaciones_posteriores(consulta: dict, fecha_version: str | None, aproximada: bool, oficiales_en_la_base: dict[str, str], hoy: str | None=None) -> list[dict] | None:
    """Public CI documentation."""
    if not fecha_version or consulta.get('estado') is None:
        return None
    hoy = hoy or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    anio_version = int(fecha_version[:4])
    salida = []
    for m in consulta.get('modificaciones', []):
        fechas = _fechas_efecto(m)
        extra = {}
        if fechas:
            nuevas = [f for f in fechas if f > fecha_version]
            if not nuevas:
                continue
            ya = [f for f in nuevas if f <= hoy]
            fecha = (ya or nuevas)[0]
            if not ya or (m.get('fecha_vigencia') or '') > hoy:
                extra['futura'] = True
            if aproximada and fecha[:4] == fecha_version[:4]:
                extra['dudosa'] = True
            if any((f <= fecha_version for f in fechas)):
                extra['dudosa'] = True
        else:
            fecha = None
            anio = _anio_del_id(m['id'])
            if anio is not None and anio < anio_version:
                continue
            extra['fecha_desconocida'] = True
        e = dict(m, fecha_comparada=fecha, **extra)
        e['obra_en_la_base'] = oficiales_en_la_base.get(m['id'])
        e['en_la_base'] = e['obra_en_la_base'] is not None
        salida.append(e)
    return salida

def _oficiales_de_la_base(identificadores: list[str]) -> dict[str, str]:
    """Public CI documentation."""
    mapa: dict[str, str] = {}
    for ident in sorted(identificadores, key=lambda i: (identificador_oficial(i) != i, i)):
        oficial = identificador_oficial(ident)
        if oficial and oficial not in mapa:
            mapa[oficial] = ident
    return mapa

def instantanea(ruta_base, progreso=None) -> dict:
    """Public CI documentation."""
    con = db.conectar(Path(ruta_base), solo_lectura=True)
    try:
        obras = con.execute('SELECT id, identificador_canonico AS ident, tipo, titulo FROM obra ORDER BY identificador_canonico').fetchall()
        fechas = {o['id']: fecha_de_la_version(con, o['id']) for o in obras}
    finally:
        con.close()
    oficiales = _oficiales_de_la_base([o['ident'] for o in obras])
    consultado = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    resultado: dict = {'esquema': ESQUEMA, 'consultado': consultado, 'fuentes': {'BOE': AVISO_BOE, 'CELLAR': AVISO_CELLAR}, 'base': {'ruta': str(ruta_base)}, 'obras': {}, 'sin_identificador_oficial': []}
    legislativas = [o for o in obras if identificador_oficial(o['ident'])]
    for n, o in enumerate(legislativas, 1):
        oficial = identificador_oficial(o['ident'])
        if progreso:
            progreso(f"[{n}/{len(legislativas)}] {o['ident']} -> {oficial}")
        consulta = _consultar(oficial)
        f = fechas[o['id']]
        resultado['obras'][o['ident']] = {'identificador_oficial': oficial, 'titulo_base': o['titulo'], **f, 'consulta': consulta, 'modificaciones_posteriores': modificaciones_posteriores(consulta, f['fecha_version'], f['fecha_version_aproximada'], oficiales, hoy=consultado[:10])}
    resultado['sin_identificador_oficial'] = [o['ident'] for o in obras if o['tipo'] in ('boe', 'eurlex') and (not identificador_oficial(o['ident']))]
    return resultado

def escribir_instantanea(datos: dict, ruta) -> None:
    """Public CI documentation."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    os.replace(temporal, ruta)

def leer_instantanea(ruta) -> dict:
    return json.loads(Path(ruta).read_text(encoding='utf-8'))

def resumen(datos: dict) -> str:
    estados: dict[str, int] = {}
    huecos: set[str] = set()
    futuras: set[str] = set()
    for o in datos['obras'].values():
        e = o['consulta'].get('estado') or 'ERROR'
        estados[e] = estados.get(e, 0) + 1
        for m in o['modificaciones_posteriores'] or []:
            if not m['en_la_base']:
                huecos.add(m['id'])
                if m.get('futura'):
                    futuras.add(m['id'])
    partes = ', '.join((f'{k}: {v}' for k, v in sorted(estados.items())))
    return f"{len(datos['obras'])} obras consultadas el {datos['consultado']} ({partes}); modificaciones posteriores que no están en la base: {len(huecos)} normas distintas (futuras, que aún no han entrado en vigor: {len(futuras)})"
DIAS_DE_VALIDEZ = 30

def ruta_instantanea() -> Path:
    """Public CI documentation."""
    return config.BD.parent / 'vigencia.json'

def instantanea_actual(ruta=None) -> dict | None:
    """Public CI documentation."""
    explicita = ruta is not None
    ruta = Path(ruta) if explicita else ruta_instantanea()
    try:
        datos = leer_instantanea(ruta)
    except (OSError, ValueError):
        datos = None
    if explicita:
        return datos
    complementos = ['vigencia_top30.json', 'vigencia_r2.json', 'vigencia_r3.json']
    for nombre in complementos:
        try:
            complemento = leer_instantanea(config.DATOS_REPO / nombre)
        except (OSError, ValueError):
            continue
        if datos is None:
            datos = {'esquema': ESQUEMA, 'consultado': None, 'fuentes': {}, 'obras': {}}
        else:
            datos = copy.deepcopy(datos)
        for fuente, aviso in complemento.get('fuentes', {}).items():
            datos.setdefault('fuentes', {}).setdefault(fuente, aviso)
        for obra, entrada in complemento.get('obras', {}).items():
            datos.setdefault('obras', {}).setdefault(obra, entrada)
    return datos

def _nombre(m: dict) -> str:
    """Public CI documentation."""
    desc = m.get('titulo') or m.get('texto') or ''
    return f"{m['id']}" + (f' ({_texto(desc)[:140]})' if desc else '')
RE_CELEX_NUMERO = re.compile('^[0-9](\\d{4})[A-Z]{1,2}(\\d{4})$')
RE_NUMERO_PROPIO = re.compile('(\\d+)/(\\d{4})')
RE_DEROGA = re.compile('(?i)\\bderogan?\\b')
RE_FIN_DE_LO_DEROGADO = re.compile('(?i)(?:\\by\\s+)?\\bse\\s+(?!derogan?\\b)\\w+|\\bpor\\s+(?:el|la|lo|los|las)\\s+que\\b|\\bque\\b|\\(\\s*texto\\s+pertinente')
LARGO_MAXIMO_DE_LO_DEROGADO = 400

def numeros_de_la_norma(oficial: str, titulo: str | None=None) -> list[str]:
    """Public CI documentation."""
    m = RE_CELEX_NUMERO.match(oficial or '')
    if m:
        ano, numero = (m[1], str(int(m[2])))
        formas = [f'{ano}/{numero}', f'{numero}/{ano}']
        if int(ano) < 2000:
            formas += [f'{ano[2:]}/{numero}', f'{numero}/{ano[2:]}']
        return formas
    m = RE_NUMERO_PROPIO.search(titulo or '') if (oficial or '').startswith('BOE-') else None
    return [f'{m[1]}/{m[2]}'] if m else []

def deroga_la_norma(m: dict, numeros: list[str]) -> bool:
    """Public CI documentation."""
    if not numeros:
        return False
    for campo in ('titulo', 'texto'):
        titulo = ' '.join(str(m.get(campo) or '').split())
        for d in RE_DEROGA.finditer(titulo):
            resto = titulo[d.end():d.end() + LARGO_MAXIMO_DE_LO_DEROGADO]
            fin = RE_FIN_DE_LO_DEROGADO.search(resto)
            derogado = resto[:fin.start()] if fin else resto
            if any((re.search(f'(?<![\\d/]){re.escape(n)}(?!\\d)', derogado) for n in numeros)):
                return True
    return False

def _obras_que_contienen(con: sqlite3.Connection, texto: str) -> list[str]:
    """Public CI documentation."""
    palabras = consulta.norm_alias(texto).split()
    if not any((re.search('\\d', p) for p in palabras)):
        return []
    salida = []
    for canonico, alias in con.execute('SELECT o.identificador_canonico, a.alias_norm FROM obra o JOIN obra_alias a ON a.obra_id = o.id ORDER BY o.identificador_canonico'):
        if canonico in salida or identificador_oficial(canonico) is None:
            continue
        resto = iter(alias.split())
        if all((any((a == p or a.startswith(p + '/') for a in resto)) for p in palabras)):
            salida.append(canonico)
    return salida

def obras_de_la_norma(con: sqlite3.Connection, texto: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Public CI documentation."""
    candidatas = [f['identificador_canonico'] for f in consulta.obras_que_casan(con, texto)]
    exacta = next((c for c in candidatas if c.casefold() == (texto or '').strip().casefold()), None)
    if exacta:
        return ([exacta], {}, []) if identificador_oficial(exacta) else ([], {}, [exacta])
    legislativas = [c for c in candidatas if identificador_oficial(c)]
    if not legislativas:
        legislativas = _obras_que_contienen(con, texto)
    if not legislativas:
        return ([], {}, candidatas)
    por_oficial: dict[str, list[str]] = {}
    for canonico, in con.execute('SELECT identificador_canonico FROM obra ORDER BY identificador_canonico'):
        oficial = identificador_oficial(canonico)
        if oficial:
            por_oficial.setdefault(oficial, []).append(canonico)
    obras, otras = ([], {})
    for oficial in dict.fromkeys((identificador_oficial(c) for c in legislativas)):
        copias = sorted(por_oficial.get(oficial) or [], key=lambda c: (c.startswith('ICT155-DOC-'), c))
        obras.append(copias[0])
        otras[copias[0]] = copias[1:]
    return (obras, otras, [])

def vigencia_de(obra: str, datos: dict | None, hoy: str | None=None) -> dict | None:
    """Public CI documentation."""
    oficial = identificador_oficial(obra)
    if oficial is None:
        return None
    if datos is None:
        return {'estado': None, 'identificador_oficial': oficial, 'consultado': None, 'avisos': ['no hay consulta de vigencia en esta base: no se sabe si la norma sigue vigente ni si se ha modificado después de la versión que tiene la base']}
    hoy = hoy or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    o = datos.get('obras', {}).get(obra)
    consultado = ((o or {}).get('consultado') or datos.get('consultado')) or ''
    try:
        dias = (datetime.fromisoformat(hoy) - datetime.fromisoformat(consultado[:10])).days
    except ValueError:
        dias = None
    if o is None:
        return {'estado': None, 'identificador_oficial': oficial, 'consultado': consultado, 'avisos': ['esta norma no está en la consulta de vigencia: no se sabe si sigue vigente']}
    c = o['consulta']
    version = o.get('fecha_version')
    if version and o.get('fecha_version_aproximada'):
        version = f'edición de {version[:4]}'
    v = {'estado': c.get('estado'), 'fuente': c.get('fuente'), 'identificador_oficial': oficial, 'fecha_version_base': version, 'consultado': consultado, 'dias': dias, 'aviso_fuente': datos.get('fuentes', {}).get(c.get('fuente')), 'url': c.get('url'), 'fecha_derogacion': c.get('fecha_derogacion'), 'derogada_por': c.get('derogada_por') or [], 'modificaciones_posteriores': o.get('modificaciones_posteriores'), 'avisos': []}
    av = v['avisos']
    if c.get('estado') is None:
        av.append(f"no se pudo consultar su vigencia ({c.get('error') or 'error de la fuente'})")
    elif c['estado'] == 'derogada_con_excepciones':
        v['excepciones'] = c.get('excepciones')
        v['evidencia_local'] = c.get('evidencia_local')
        av.append('DEROGADA CON EXCEPCIONES' + (f" el {c['fecha_derogacion']}" if c.get('fecha_derogacion') else '') + (f"; {v['excepciones']}" if v['excepciones'] else ''))
        av.append('No se determinan los artículos que conservan vigencia: hay que examinar las excepciones del acto derogador.')
    elif c['estado'] == 'derogada':
        por = '; '.join((_nombre(d) for d in v['derogada_por'])) or 'norma no indicada'
        av.append(f'DEROGADA' + (f" el {c['fecha_derogacion']}" if c.get('fecha_derogacion') else '') + f' por {por}')
    elif c['estado'] == 'anulada':
        av.append('ANULADA' + (f" el {c['fecha_anulacion']}" if c.get('fecha_anulacion') else ''))
    elif c['estado'] == 'vigencia_agotada':
        av.append('con la VIGENCIA AGOTADA' + (f" ({c['fecha_fin_validez']})" if c.get('fecha_fin_validez') else ''))
    mods = o.get('modificaciones_posteriores')
    if o.get('limites'):
        av.extend(o['limites'])
    elif mods is None and c.get('estado') is not None:
        av.append('la base no sabe la fecha de su versión: no se puede saber si se ha modificado después')
    numeros = numeros_de_la_norma(oficial, c.get('titulo') or o.get('titulo_base'))
    for m in mods or []:
        fecha = m.get('fecha_comparada') or 'fecha desconocida'
        falta = f"; su texto está en la base como {m['obra_en_la_base']}" if m.get('obra_en_la_base') else '' if m.get('en_la_base') else ', que la base NO tiene'
        if deroga_la_norma(m, numeros):
            lee = f"(normativa_cita «{m['obra_en_la_base']}»)" if m.get('obra_en_la_base') else '(en la fuente oficial)'
            if m.get('futura'):
                cab = 'DEROGACIÓN posterior aprobada que aún no ha entrado en vigor'
            elif m.get('dudosa') or m.get('fecha_desconocida'):
                cab = f"posible DEROGACIÓN posterior a la versión de la base ({v['fecha_version_base']})"
            else:
                cab = f"DEROGACIÓN posterior a la versión de la base ({v['fecha_version_base']})"
            av.append(f'{cab}: {_nombre(m)}, {fecha}{falta}. Puede tener efecto diferido (la fecha es la del acto, no la de la derogación) y ser parcial: hay que leer el acto {lee} antes de decir si la norma sigue vigente')
        elif m.get('futura'):
            av.append(f'modificación aprobada que aún no ha entrado en vigor: {_nombre(m)}, {fecha}{falta}')
        elif m.get('dudosa') or m.get('fecha_desconocida'):
            av.append(f"posible modificación posterior a la versión de la base ({v['fecha_version_base']}): {_nombre(m)}, {fecha}{falta}")
        else:
            av.append(f"MODIFICADA después de la versión de la base ({v['fecha_version_base']}): {_nombre(m)}, {fecha}{falta}")
    if dias is not None and dias > DIAS_DE_VALIDEZ:
        av.append(f'la consulta de vigencia tiene {dias} días: hay que actualizarla')
    return v

def texto(v: dict | None) -> str:
    """Public CI documentation."""
    if not v:
        return ''
    cab = f"──── VIGENCIA ({v.get('fuente') or 'sin fuente'}, consultada {(v.get('consultado') or 'nunca')[:10]}) ────"
    lineas = [cab]
    if v.get('estado'):
        version = v.get('fecha_version_base')
        lineas.append(f"  Estado: {v['estado']}." + (f' Versión de la base: {version}.' if version else ''))
    if v['avisos']:
        lineas += [f'  AVISO: {a}' for a in v['avisos']]
    else:
        lineas.append('  Sin modificaciones posteriores a la versión de la base según la fuente oficial.')
    if v.get('estado') == 'derogada' and 'sucesion' in v:
        from . import sucesion
        lineas += sucesion.lineas(v['sucesion'])
    if v.get('aviso_fuente'):
        lineas.append(f"  {v['aviso_fuente']}.")
    return '\n'.join(lineas)

def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(prog='python -m ict155.vigencia', description='Instantánea de vigencia de las normas de la base (BOE y CELLAR).')
    ap.add_argument('--salida', required=True, help='fichero JSON de la instantánea')
    ap.add_argument('--base', default=None, help='base de datos (por defecto la de producción; solo lectura)')
    args = ap.parse_args(argv)
    ruta_base = Path(args.base) if args.base else config.BD
    datos = instantanea(ruta_base, progreso=lambda s: print(s, file=sys.stderr, flush=True))
    escribir_instantanea(datos, args.salida)
    print(resumen(datos))
    print(f'escrita {args.salida}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
