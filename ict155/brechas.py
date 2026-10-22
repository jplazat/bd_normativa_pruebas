"""Public CI documentation."""
from __future__ import annotations
import datetime
import importlib.util
import json
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from . import almacen, ambito, cifras, completitud, config, consulta, db, fundamento, historial_boe, interruptores, relacionados, revision, sucesion, vigencia
ESTADOS = ('abierta', 'cerrada', 'reformulada', 'nueva')
VEREDICTOS = ('cumple', 'no_cumple', 'parcial', 'pendiente')
ESTADOS_REQUERIMIENTO = ('no_recibido', 'recibido_en_parte', 'recibido_con_reservas', 'recibido')
PAPELES_CITA = ('fundamento', 'apoyo', 'contexto')
VEREDICTOS_CON_AVISO = ('no_cumple', 'parcial')
OK, AVISO, ERROR = (revision.OK, revision.AVISO, revision.ERROR)
_GRAVEDAD = {OK: 0, AVISO: 1, ERROR: 2}
_RE_FECHA = re.compile('^\\d{4}-\\d{2}-\\d{2}$')
_SIN_CAPA = '(sin capa)'
CONTROL = 'brechas_r27'
TOPE_MINUTOS_POR_DEFECTO = 1440
_CATEGORIAS_BLOQUEAN = ('cumple_sin_documento', 'cita_no_tratada', 'error_revisar', 'cita_inexistente', 'cifra_cambiada', 'sin_citas', 'estado_incoherente', 'cumple_con_que_falta')
_NEGACIONES = ('no se aplica', 'no aplica', 'no es obligatori', 'no exige', 'no hay obligación', 'no es exigible')
_RE_NEGACION = re.compile('|'.join((re.escape(n) for n in _NEGACIONES)), re.IGNORECASE)
_AVISOS_DE_ESTADO = {consulta.CONTENIDO_EN_ANCESTRO: 'no es un precepto propio: su texto está impreso dentro de su ancestro; en la carencia cita su ancestro, y en la revisión la misma cláusula o el ancestro también en la carencia', consulta.DERECHOS_RESTRINGIDOS: 'norma de derechos restringidos: la base no reproduce su texto; el literal no se puede comprobar aquí (usa `cotejar`)'}
_ESTADOS_EXISTE = (consulta.ENCONTRADO, consulta.LOCALIZADO_SIN_TEXTO) + tuple(_AVISOS_DE_ESTADO)

class RegistroMalo(ValueError):
    """Public CI documentation."""

    def __init__(self, errores: list[str]):
        super().__init__('; '.join(errores))
        self.errores = errores

class ErrorDeCalculo(Exception):
    """Public CI documentation."""

def _precargar_tablas() -> None:
    sucesion.cargar()
    relacionados.cargar()

def _fecha_ok(v) -> bool:
    if not isinstance(v, str) or not _RE_FECHA.match(v):
        return False
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        return False
    return True

def _fecha_legible(v: str | None) -> str | None:
    """Public CI documentation."""
    if not _fecha_ok(v):
        return v
    d = datetime.date.fromisoformat(v)
    return f'{d.day:02d}/{d.month:02d}/{d.year:04d}'

def _identificador_invalido(ident) -> str | None:
    """Public CI documentation."""
    if not isinstance(ident, str) or '::' not in ident or (not ident.partition('::')[2].strip()):
        return 'tiene que ser obra::ruta'
    if '`' in ident or '\n' in ident:
        return 'no puede llevar comillas invertidas ni saltos de línea'
    return None

def validar(datos) -> list[str]:
    """Public CI documentation."""
    pendientes = [datos]
    while pendientes:
        valor = pendientes.pop()
        if isinstance(valor, str) and any((55296 <= ord(c) <= 57343 for c in valor)):
            return ['el registro contiene texto Unicode inválido (sustituto aislado)']
        if isinstance(valor, dict):
            pendientes.extend(valor.keys())
            pendientes.extend(valor.values())
        elif isinstance(valor, list):
            pendientes.extend(valor)
    if not isinstance(datos, dict):
        return ['el registro tiene que ser un objeto JSON con «brechas»']
    errores: list[str] = []
    for k in ('cliente', 'informe', 'version', 'valoracion_consultor', 'informe_fase1'):
        if k in datos and (not isinstance(datos[k], str)):
            errores.append(f'«{k}» tiene que ser texto')
    if 'fecha_corte' in datos and datos['fecha_corte'] is not None and (not _fecha_ok(datos['fecha_corte'])):
        errores.append(f"«fecha_corte» {datos['fecha_corte']!r} no es una fecha AAAA-MM-DD")
    if 'tope_minutos' in datos:
        tm = datos['tope_minutos']
        if isinstance(tm, bool) or not isinstance(tm, int) or tm < 0:
            errores.append('«tope_minutos» tiene que ser un entero ≥ 0')
    brechas = datos.get('brechas')
    if not isinstance(brechas, list):
        return errores + ['falta «brechas» o no es una lista']
    vistos: dict[str, int] = {}
    for i, b in enumerate(brechas, 1):
        if not isinstance(b, dict):
            errores.append(f'brecha nº {i}: tiene que ser un objeto')
            continue
        bid = b.get('id')
        if not isinstance(bid, str) or not bid.strip():
            errores.append(f'brecha nº {i}: falta «id» (texto no vacío)')
            donde = f'brecha nº {i}'
        else:
            donde = f'brecha {bid}'
            if bid in vistos:
                errores.append(f'{donde}: id repetido (también es la brecha nº {vistos[bid]})')
            vistos.setdefault(bid, i)
        if b.get('estado') not in ESTADOS:
            errores.append(f"{donde}: «estado» {b.get('estado')!r} no es válido (usa {', '.join(ESTADOS)})")
        if 'fecha_estado' in b and (not _fecha_ok(b['fecha_estado'])):
            errores.append(f"{donde}: «fecha_estado» {b['fecha_estado']!r} no es una fecha AAAA-MM-DD")
        for k in ('capa', 'titulo', 'descripcion', 'evidencia_requerida', 'evidencia_aportada', 'notas'):
            if k in b and (not isinstance(b[k], str)):
                errores.append(f'{donde}: «{k}» tiene que ser texto')
        if 'estado_requerimiento' in b and b['estado_requerimiento'] is not None and (b['estado_requerimiento'] not in ESTADOS_REQUERIMIENTO):
            errores.append(f"{donde}: «estado_requerimiento» {b['estado_requerimiento']!r} no es válido (usa {', '.join(ESTADOS_REQUERIMIENTO)})")
        if 'pendiente_responsable' in b:
            pj = b['pendiente_responsable']
            if not isinstance(pj, list):
                errores.append(f'{donde}: «pendiente_responsable» tiene que ser una lista')
            else:
                for k, m in enumerate(pj, 1):
                    if not isinstance(m, str) or not m.strip():
                        errores.append(f'{donde}, «pendiente_responsable» nº {k}: tiene que ser texto no vacío')
        citas = b.get('citas', [])
        if not isinstance(citas, list):
            errores.append(f'{donde}: «citas» tiene que ser una lista')
            citas = []
        for j, c in enumerate(citas, 1):
            if not isinstance(c, dict):
                errores.append(f'{donde}, cita nº {j}: tiene que ser un objeto')
                continue
            ident = c.get('identificador')
            if not isinstance(ident, str) or '::' not in ident or (not ident.partition('::')[2].strip()):
                errores.append(f'{donde}, cita nº {j}: «identificador» tiene que ser obra::ruta')
            elif '`' in ident or '\n' in ident:
                errores.append(f'{donde}, cita nº {j}: «identificador» no puede llevar comillas invertidas ni saltos de línea')
            if 'literal' in c and c['literal'] is not None and (not isinstance(c['literal'], str)):
                errores.append(f'{donde}, cita nº {j}: «literal» tiene que ser texto')
            if 'papel' in c and c['papel'] is not None:
                if not isinstance(c['papel'], str):
                    errores.append(f'{donde}, cita nº {j}: «papel» tiene que ser texto')
                elif c['papel'] not in PAPELES_CITA:
                    errores.append(f"{donde}, cita nº {j}: «papel» {c['papel']!r} no es válido (usa {', '.join(PAPELES_CITA)})")
        revs = b.get('revisiones', [])
        if not isinstance(revs, list):
            errores.append(f'{donde}: «revisiones» tiene que ser una lista')
            revs = []
        numeros = set()
        for j, r in enumerate(revs, 1):
            if not isinstance(r, dict):
                errores.append(f'{donde}, revisión nº {j}: tiene que ser un objeto')
                continue
            n = r.get('numero')
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                errores.append(f'{donde}, revisión nº {j}: «numero» tiene que ser un entero desde 1')
            elif n in numeros:
                errores.append(f'{donde}: la revisión {n} está repetida')
            else:
                numeros.add(n)
            if not _fecha_ok(r.get('fecha')):
                errores.append(f"{donde}, revisión nº {j}: «fecha» {r.get('fecha')!r} no es una fecha AAAA-MM-DD")
            if r.get('veredicto') not in VEREDICTOS:
                errores.append(f"{donde}, revisión nº {j}: «veredicto» {r.get('veredicto')!r} no es válido (usa {', '.join(VEREDICTOS)})")
            for k in ('documento_aportado', 'que_falta'):
                if k in r and (not isinstance(r[k], str)):
                    errores.append(f'{donde}, revisión nº {j}: «{k}» tiene que ser texto')
            if 'revisor' in r and r['revisor'] is not None and (not isinstance(r['revisor'], str)):
                errores.append(f'{donde}, revisión nº {j}: «revisor» tiene que ser texto')
            if 'minutos' in r:
                m = r['minutos']
                if isinstance(m, bool) or not isinstance(m, int) or m < 0:
                    errores.append(f'{donde}, revisión nº {j}: «minutos» tiene que ser un entero ≥ 0')
            if 'citas' in r:
                citas_r = r['citas']
                if not isinstance(citas_r, list):
                    errores.append(f'{donde}, revisión nº {j}: «citas» tiene que ser una lista')
                else:
                    for k, ident in enumerate(citas_r, 1):
                        problema = _identificador_invalido(ident)
                        if problema:
                            errores.append(f'{donde}, revisión nº {j}, «citas» nº {k}: «identificador» {problema}')
            if 'no_aplica' in r:
                no_aplica = r['no_aplica']
                if not isinstance(no_aplica, list):
                    errores.append(f'{donde}, revisión nº {j}: «no_aplica» tiene que ser una lista')
                else:
                    for k, na in enumerate(no_aplica, 1):
                        if not isinstance(na, dict):
                            errores.append(f'{donde}, revisión nº {j}, «no_aplica» nº {k}: tiene que ser un objeto')
                            continue
                        problema = _identificador_invalido(na.get('identificador'))
                        if problema:
                            errores.append(f'{donde}, revisión nº {j}, «no_aplica» nº {k}: «identificador» {problema}')
                        if not isinstance(na.get('motivo'), str):
                            errores.append(f'{donde}, revisión nº {j}, «no_aplica» nº {k}: «motivo» tiene que ser texto')
    return errores

def leer_registro(ruta) -> dict:
    """Public CI documentation."""
    try:
        with open(ruta, encoding='utf-8-sig') as f:
            datos = json.load(f)
    except OSError as e:
        raise RegistroMalo([f'no se puede leer {str(ruta)!r}: {e.strerror or e}']) from None
    except UnicodeDecodeError:
        raise RegistroMalo(['el registro no está en UTF-8']) from None
    except ValueError as e:
        raise RegistroMalo([f'el registro no es JSON válido: {e}']) from None
    errores = validar(datos)
    if errores:
        raise RegistroMalo(errores)
    return datos

@dataclass
class ResultadoCita:
    identificador: str
    nivel: str = OK
    estado: str = ''
    detalle: list[str] = field(default_factory=list)
    ok: list[str] = field(default_factory=list)

    def sube(self, nivel: str, texto: str) -> None:
        self.detalle.append(texto)
        if _GRAVEDAD[nivel] > _GRAVEDAD[self.nivel]:
            self.nivel = nivel

@dataclass
class ResultadoBrecha:
    brecha: dict
    citas: list[ResultadoCita]
    ultima_revision: dict | None
    avisos_revision: list[str]

    @property
    def nivel(self) -> str:
        niveles = [c.nivel for c in self.citas] or [AVISO]
        return max(niveles, key=_GRAVEDAD.get)

def ultima_revision(brecha: dict) -> dict | None:
    revs = brecha.get('revisiones') or []
    return max(revs, key=lambda r: r['numero']) if revs else None

def _revision_es_posterior_al_corte(r: dict, corte: str) -> bool:
    """Public CI documentation."""
    fecha = r.get('fecha')
    return not fecha or fecha > corte

def _revision_elegible_hasta_el_corte(r: dict, corte: str) -> bool:
    """Public CI documentation."""
    fecha = r.get('fecha')
    return not fecha or fecha <= corte

def ultima_revision_a_fecha(brecha: dict, corte: str | None) -> dict | None:
    """Public CI documentation."""
    if corte is None:
        return ultima_revision(brecha)
    revs = [r for r in brecha.get('revisiones') or [] if _revision_elegible_hasta_el_corte(r, corte)]
    return max(revs, key=lambda r: r['numero']) if revs else None

def _revisiones_tras_corte(brecha: dict, corte: str | None) -> list[dict]:
    """Public CI documentation."""
    if corte is None:
        return []
    return [r for r in brecha.get('revisiones') or [] if _revision_es_posterior_al_corte(r, corte)]

def _avisos_de_revision(ultima: dict | None) -> list[str]:
    if ultima is None:
        return ['sin ninguna revisión']
    if ultima['veredicto'] in VEREDICTOS_CON_AVISO:
        return [f"la última revisión (nº {ultima['numero']}, {ultima['fecha']}) es «{ultima['veredicto']}»"]
    return []

@dataclass
class HallazgoR27:
    """Public CI documentation."""
    tipo: str
    nivel: str
    brecha_id: str | None
    mensaje: str

def _partir(ident: str) -> tuple[str, str]:
    obra, _, ruta = ident.partition('::')
    return (obra.strip(), ruta.strip())

def _canonico_existe(con: sqlite3.Connection, ident: str, ambitos: tuple[str, ...], memoria: dict) -> tuple[str, str] | None:
    """Public CI documentation."""
    clave = (ident, 'existe')
    if clave not in memoria:
        r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
        canon = None
        if r.estado in _ESTADOS_EXISTE and r.obra:
            ruta = None
            if r.version_id is not None:
                cruda = consulta.partir_identificador(ident)[1]
                ruta = consulta.ruta_efectiva(con, r.version_id, cruda) if cruda else None
            ruta = ruta or r.ambito_pedido or r.ambito_localizado
            if ruta:
                canon = (r.obra, ruta)
        memoria[clave] = canon
    return memoria[clave]

def _cubierta(con: sqlite3.Connection, pedido: str, candidatos, ambitos: tuple[str, ...], memoria: dict) -> bool:
    """Public CI documentation."""
    p = completitud._canonico(con, pedido, ambitos, memoria) or _canonico_existe(con, pedido, ambitos, memoria)
    obra_p, ruta_p = p if p is not None else _partir(pedido)
    for c in candidatos:
        if not isinstance(c, str):
            continue
        canon = completitud._canonico(con, c, ambitos, memoria) or _canonico_existe(con, c, ambitos, memoria)
        if canon is None:
            if not _existe_en_base(con, c, ambitos):
                continue
            canon = _partir(c)
        obra_c, ruta_c = canon
        if obra_c == obra_p and completitud._cubre(ruta_c, ruta_p):
            return True
    return False

def _existe_en_base(con: sqlite3.Connection, ident: str, ambitos: tuple[str, ...]) -> bool:
    """Public CI documentation."""
    r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
    return r.estado in _ESTADOS_EXISTE

def _frases_de_negacion(texto: str) -> list[str]:
    """Public CI documentation."""
    if not texto:
        return []
    frases = re.split('(?<=[.;\\n])\\s+', texto)
    return [f.strip() for f in frases if f.strip() and _RE_NEGACION.search(f)]

def _borrador_cifras(identificadores: list[str], texto: str | None) -> str:
    """Public CI documentation."""
    texto = (texto or '').strip()
    idents = list(dict.fromkeys((i for i in identificadores if isinstance(i, str) and i.strip())))
    if not texto or not idents:
        return ''
    cabecera = ' '.join((f'(`{i}`)' for i in idents))
    parrafos = [p for p in re.split('\\n[ \\t]*\\n', texto) if p.strip()]
    return '\n\n'.join((f'{cabecera}\n\n{p}' for p in parrafos))

def _hallazgos_de_brecha(con: sqlite3.Connection, b: dict, ultima: dict | None, ambitos: tuple[str, ...], huella: str | None) -> list[HallazgoR27]:
    """Public CI documentation."""
    if ultima is None:
        return []
    bid = b.get('id')
    numero = ultima.get('numero')
    hallazgos: list[HallazgoR27] = []
    memoria: dict = {}
    if not (b.get('citas') or []):
        documental = bool((b.get('evidencia_requerida') or '').strip() and re.search('(?i)\\b(?:el\\s+)?informe no invoca norma para esta fila\\b', b.get('notas') or ''))
        if documental:
            hallazgos.append(HallazgoR27('sin_citas', AVISO, bid, f'revisión nº {numero}: requerimiento documental sin ancla normativa declarado expresamente; no acredita cumplimiento normativo'))
        else:
            hallazgos.append(HallazgoR27('sin_citas', ERROR, bid, f'revisión nº {numero}: la carencia no tiene ninguna cita normativa: su base no está verificada'))
    if b.get('estado') == 'cerrada' and ultima.get('veredicto') in VEREDICTOS_CON_AVISO:
        hallazgos.append(HallazgoR27('estado_incoherente', ERROR, bid, f"revisión nº {numero}: la carencia está «cerrada» pero su última revisión es «{ultima['veredicto']}»: estado incoherente"))
    numeros_vistos = {r.get('numero') for r in b.get('revisiones') or [] if isinstance(r.get('numero'), int) and (not isinstance(r.get('numero'), bool))}
    if isinstance(numero, int) and (not isinstance(numero, bool)) and (numero >= 2):
        faltan = [n for n in range(1, numero) if n not in numeros_vistos]
        if faltan:
            hallazgos.append(HallazgoR27('revision_sin_historial', AVISO, bid, f"revisión nº {numero}: faltan las revisiones nº {', '.join(map(str, faltan))}: no hay historial completo"))
    if ultima.get('veredicto') == 'cumple':
        if not (ultima.get('documento_aportado') or '').strip():
            hallazgos.append(HallazgoR27('cumple_sin_documento', ERROR, bid, f'revisión nº {numero}: «cumple» sin documento_aportado'))
        que_falta_val = (ultima.get('que_falta') or '').strip()
        if que_falta_val:
            hallazgos.append(HallazgoR27('cumple_con_que_falta', ERROR, bid, f'revisión nº {numero}: «cumple» con qué_falta no vacío: {que_falta_val}'))
    citas_rev = ultima.get('citas') or []
    no_aplica = ultima.get('no_aplica') or []
    for c in b.get('citas') or []:
        if not isinstance(c, dict) or c.get('papel') == 'contexto':
            continue
        ident = (c.get('identificador') or '').strip()
        if not ident or _cubierta(con, ident, citas_rev, ambitos, memoria):
            continue
        tratada = any((isinstance(na, dict) and (na.get('motivo') or '').strip() and isinstance(na.get('identificador'), str) and _cubierta(con, ident, [na['identificador']], ambitos, memoria) for na in no_aplica))
        if not tratada:
            hallazgos.append(HallazgoR27('cita_no_tratada', ERROR, bid, f'revisión nº {numero}: la cita `{ident}` de la carencia no está tratada en el veredicto'))
    identificadores_revision = [c for c in citas_rev if isinstance(c, str) and c.strip()] + [na['identificador'] for na in no_aplica if isinstance(na, dict) and isinstance(na.get('identificador'), str) and na['identificador'].strip()]
    for ident in identificadores_revision:
        ident = ident.strip()
        res = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
        incierta = res.estado == consulta.FUERA_DE_ALCANCE
        if incierta:
            obra, ruta = consulta.partir_identificador(ident)
            padre, separador, hoja = ruta.rpartition('/')
            numero_hoja = re.fullmatch('ap\\.(\\d+)', hoja)
            if separador and numero_hoja:
                rp = consulta.resolver(con, obra + '::' + padre, ambitos, modo=consulta.MODO_LOCALIZAR)
                if rp.estado == consulta.ENCONTRADO and rp.completitud == 'completa' and (rp.regimen == 'publico') and rp.texto_literal and (not re.search('(?<!\\d)' + re.escape(numero_hoja[1]) + '(?!\\d)', rp.texto_literal)):
                    incierta = False
        if incierta:
            hallazgos.append(HallazgoR27('cita_inexistente', AVISO, bid, f'revisión nº {numero}: la cita `{ident}` queda fuera del alcance verificable de la base; existencia pendiente de comprobar en el original'))
        elif res.estado not in _ESTADOS_EXISTE:
            hallazgos.append(HallazgoR27('cita_inexistente', ERROR, bid, f'revisión nº {numero}: la revisión cita `{ident}`, que no existe en la base: corrígelo o quítalo'))
    identificadores_carencia_todas = [c.get('identificador') for c in b.get('citas') or [] if isinstance(c, dict) and c.get('papel') != 'contexto' and isinstance(c.get('identificador'), str) and c['identificador'].strip()]
    identificadores_carencia = [ident for ident in identificadores_carencia_todas if _cubierta(con, ident, citas_rev, ambitos, memoria) or not any((isinstance(na, dict) and (na.get('motivo') or '').strip() and isinstance(na.get('identificador'), str) and _cubierta(con, ident, [na['identificador']], ambitos, memoria) for na in no_aplica))]
    identificadores_cifras = list(dict.fromkeys(identificadores_carencia + [c for c in citas_rev if isinstance(c, str) and c.strip()]))
    for campo, etiqueta in (('documento_aportado', 'documento aportado'), ('que_falta', 'qué falta')):
        es_documento = campo == 'documento_aportado'
        if es_documento and ultima.get('veredicto') != 'cumple':
            continue
        borrador_cifras = _borrador_cifras(identificadores_cifras, ultima.get(campo))
        if not borrador_cifras:
            continue
        for h in cifras.comprobar_respuesta(con, borrador_cifras):
            if h.cifra_frase.unidad == 'fecha':
                continue
            if h.tipo in ('contradiccion', 'incoherencia'):
                motivo = h.motivo
            elif h.tipo == 'sin_respaldo' and h.cifras_precepto and ('obligaciones distintas' not in h.motivo) and (es_documento or 'un intervalo o un límite' in h.motivo):
                motivo = f'''la respuesta dice "{h.cifra_frase.texto}" y {h.identificador or 'el precepto'} dice "{' / '.join((cp.texto for cp in h.cifras_precepto))}"'''
            else:
                continue
            hallazgos.append(HallazgoR27('cifra_cambiada', ERROR, bid, f'revisión nº {numero}, {etiqueta}: {motivo}'))
    borrador = '\n\n'.join((t for t in (ultima.get('documento_aportado'), ultima.get('que_falta')) if t and t.strip()))
    if borrador.strip():
        identificadores_revisar = [i for i in identificadores_cifras if consulta.resolver(con, i, ambitos).estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO)]
        borrador_revisar = _borrador_cifras(identificadores_revisar, borrador) or borrador
        informe = revision.revisar(con, borrador_revisar, ambitos, huella_base=huella)
        errores_r = [c for c in informe.comprobaciones if c.nivel == ERROR]
        if errores_r:
            detalles = []
            for c in errores_r:
                regimen = consulta.resolver(con, c.identificador, ambitos, modo=consulta.MODO_LOCALIZAR).regimen if c.identificador else None
                detalles.append(c.detalle if regimen == 'publico' else _sin_texto(c.detalle))
            detalle = '; '.join(detalles)
            hallazgos.append(HallazgoR27('error_revisar', ERROR, bid, f'revisión nº {numero}: error de «revisar» en el veredicto: {detalle}'))
    if isinstance(numero, int) and (not isinstance(numero, bool)) and (numero >= 3):
        etiqueta = 'tercera revisión' if numero == 3 else 'tercera o ulterior revisión'
        hallazgos.append(HallazgoR27('tercera_revision', AVISO, bid, f'revisión nº {numero}: {etiqueta}: fuera de lo contratado'))
    for frase in _frases_de_negacion(ultima.get('que_falta') or ''):
        hallazgos.append(HallazgoR27('negacion', AVISO, bid, frase))
    return hallazgos

def _hallazgo_minutos(registro: dict) -> HallazgoR27 | None:
    """Public CI documentation."""
    total = sum((r.get('minutos') or 0 for b in registro.get('brechas') or [] for r in b.get('revisiones') or [] if isinstance(r.get('minutos'), int) and (not isinstance(r.get('minutos'), bool))))
    tope = registro.get('tope_minutos')
    if isinstance(tope, bool) or not isinstance(tope, int) or tope <= 0:
        tope = TOPE_MINUTOS_POR_DEFECTO
    if total >= tope:
        return HallazgoR27('minutos_tope', AVISO, None, f'minutos: {total} de {tope} — tope superado')
    if total >= 0.8 * tope:
        return HallazgoR27('minutos_tope', AVISO, None, f'minutos: {total} de {tope} ({total * 100 // tope} %)')
    return None

def _sin_texto(detalle: str) -> str:
    """Public CI documentation."""
    if '«' not in detalle:
        return detalle
    return detalle.split('«', 1)[0].rstrip(' :…') + ' [texto de la norma omitido: norma con licencia]'
_LIMITES_DE_COWORK: list = [None]

def avisos_de_limites_de_cowork():
    """Public CI documentation."""
    if _LIMITES_DE_COWORK[0] is None:
        try:
            spec = importlib.util.spec_from_file_location('ict155_cowork_servidor_mcp', config.REPO / 'cowork' / 'servidor_mcp.py')
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            _LIMITES_DE_COWORK[0] = modulo._avisos_de_limites
        except almacen.ErrorDeAlmacen:
            raise
        except Exception as e:
            print(f'aviso: no se pueden cargar los límites conocidos de cowork/servidor_mcp.py ({e}); el informe sale sin ellos', file=sys.stderr)
            _LIMITES_DE_COWORK[0] = False
    return _LIMITES_DE_COWORK[0] or None

def referencia_legible(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',)) -> str:
    """Public CI documentation."""
    ident = identificador.strip()
    cab, ruta = consulta.partir_identificador(ident)
    norma = cab.partition('@')[0].strip()
    if not ruta:
        return norma
    r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
    etiqueta = r.etiqueta_humana
    if etiqueta:
        if not etiqueta[:2].isupper():
            etiqueta = etiqueta[0].lower() + etiqueta[1:]
        return f'{norma}, {etiqueta}'
    return f'{norma}, {ruta}'

def comprobar_cita(con: sqlite3.Connection, cita: dict, ambitos: tuple[str, ...], datos_vigencia: dict | None, huella_base: str | None=None, avisos_de_limites=None) -> ResultadoCita:
    ident = cita['identificador'].strip()
    r = consulta.resolver(con, ident, ambitos)
    res = ResultadoCita(ident, estado=r.estado)
    if r.estado == consulta.ENCONTRADO:
        res.ok.append(f"{r.etiqueta_humana or ''} — {r.paginas or 'páginas ?'}".strip(' —'))
    elif r.estado in _AVISOS_DE_ESTADO:
        res.sube(AVISO, f'{r.estado}: {_AVISOS_DE_ESTADO[r.estado]}')
    else:
        extra = r.detalle or ('cercanos: ' + ', '.join(map(str, r.candidatos)) if r.candidatos else 'no resuelve')
        res.sube(ERROR, f'{r.estado}: {extra}')
        return res
    literal = ' '.join((cita.get('literal') or '').split())
    if literal and r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO):
        informe = revision.revisar(con, f'`{ident}`\n\n> {literal}\n', ambitos, huella_base=huella_base)
        literales = [c for c in informe.comprobaciones if c.tipo in ('literal', 'cotejo')]
        if not literales:
            res.sube(AVISO, 'literal sin comprobar: tiene menos de dos palabras con contenido')
        for c in literales:
            detalle = c.detalle if r.regimen in (None, 'publico') else _sin_texto(c.detalle)
            if c.nivel == OK:
                res.ok.append(f'literal: {detalle}')
            else:
                res.sube(c.nivel, f'literal: {detalle}')
    elif literal:
        res.sube(AVISO, 'literal sin comprobar')
    if r.obra:
        v = vigencia.vigencia_de(r.obra, datos_vigencia)
        for a in (v or {}).get('avisos', []):
            res.sube(AVISO, f'vigencia: {a}')
    if avisos_de_limites and r.obra and (r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO)):
        escrito, _, ruta = ident.partition('::')
        for a in avisos_de_limites([r.obra, r.obra_titulo, escrito.partition('@')[0].strip()], ruta.strip()):
            res.sube(AVISO, f'límite conocido: {a}')
    return res
_CARGAR = object()

class ResultadosBrechas(list):
    """Public CI documentation."""

    def __init__(self, iterable=(), modo: str='apagado', hallazgos: list[HallazgoR27] | None=None, hallazgos_posteriores: list[HallazgoR27] | None=None):
        super().__init__(iterable)
        self.modo = modo
        self.hallazgos = hallazgos or []
        self.hallazgos_posteriores = hallazgos_posteriores or []

def comprobar(con: sqlite3.Connection, registro: dict, ambitos: tuple[str, ...]=('publico',), datos_vigencia=_CARGAR, avisos_de_limites=_CARGAR, corte: str | None=None) -> list[ResultadoBrecha]:
    """Public CI documentation."""
    _precargar_tablas()
    if datos_vigencia is _CARGAR:
        datos_vigencia = vigencia.instantanea_actual()
    if avisos_de_limites is _CARGAR:
        avisos_de_limites = avisos_de_limites_de_cowork()
    try:
        huella = db.huella_contenido(con)
    except sqlite3.Error:
        huella = None
    salida = []
    for b in registro['brechas']:
        citas = [comprobar_cita(con, c, ambitos, datos_vigencia, huella, avisos_de_limites) for c in b.get('citas') or []]
        ult = ultima_revision_a_fecha(b, corte)
        salida.append(ResultadoBrecha(b, citas, ult, _avisos_de_revision(ult)))
    modo = interruptores.modo(CONTROL)
    hallazgos: list[HallazgoR27] = []
    hallazgos_posteriores: list[HallazgoR27] = []
    if modo != 'apagado':
        for b in registro['brechas']:
            ultima_seleccionada = ultima_revision_a_fecha(b, corte)
            try:
                hallazgos += _hallazgos_de_brecha(con, b, ultima_seleccionada, ambitos, huella)
            except almacen.ErrorDeAlmacen:
                raise
            except Exception as e:
                if modo != 'sombra':
                    raise ErrorDeCalculo(f"brecha {b.get('id')}: no se puede calcular «{CONTROL}» ({type(e).__name__}: {e})") from e
                interruptores.anotar_sombra(CONTROL, {'error': f'{type(e).__name__}: {e}', 'brecha': b.get('id')})
                continue
            if corte is not None:
                ultima_real = ultima_revision(b)
                if ultima_real is not None and ultima_real is not ultima_seleccionada:
                    try:
                        hallazgos_posteriores += _hallazgos_de_brecha(con, b, ultima_real, ambitos, huella)
                    except almacen.ErrorDeAlmacen:
                        raise
                    except Exception:
                        pass
        h_minutos = _hallazgo_minutos(registro)
        if h_minutos:
            hallazgos.append(h_minutos)
        if modo == 'sombra':
            for h in hallazgos:
                interruptores.anotar_sombra(CONTROL, {'tipo': h.tipo, 'nivel': h.nivel, 'brecha': h.brecha_id, 'mensaje': h.mensaje})
        elif modo == 'bloquea':
            por_id = {r.brecha['id']: r for r in salida}
            for h in hallazgos:
                if h.tipo in _CATEGORIAS_BLOQUEAN and h.brecha_id in por_id:
                    por_id[h.brecha_id].citas.append(ResultadoCita(f'(brechas_r27) {h.tipo}', nivel=h.nivel, estado='BRECHAS_R27', detalle=[h.mensaje]))
    modo_ambito = interruptores.modo('ambito')
    if modo_ambito == 'bloquea':
        ambito.cargar()
    if modo_ambito != 'apagado':
        por_id = {r.brecha['id']: r for r in salida}
        for b in registro['brechas']:
            ultima = ultima_revision_a_fecha(b, corte)
            texto = '\n\n'.join((t for t in ((ultima or {}).get('documento_aportado'), (ultima or {}).get('que_falta')) if t and t.strip()))
            if not texto.strip():
                continue
            citas_contexto = tuple(dict.fromkeys([c.get('identificador') for c in b.get('citas') or [] if isinstance(c, dict) and isinstance(c.get('identificador'), str) and c['identificador'].strip()] + [c for c in (ultima or {}).get('citas') or [] if isinstance(c, str) and c.strip()]))
            if modo_ambito == 'sombra':
                try:
                    hallazgos_ambito = ambito.hallazgos_veredicto(con, texto, citas_contexto)
                except almacen.ErrorDeAlmacen:
                    raise
                except Exception as e:
                    interruptores.anotar_sombra('ambito', {'error': f'{type(e).__name__}: {e}', 'brecha': b['id']})
                    continue
                for h in hallazgos_ambito:
                    interruptores.anotar_sombra('ambito', h.dict() | {'brecha': b['id']})
                    hallazgos.append(HallazgoR27('fuera_de_ambito', AVISO, b['id'], f'{ambito.PREFIJO_FUERA_DE_AMBITO}: cita `{h.identificador}`: {h.motivo}'))
            elif modo_ambito == 'bloquea':
                for h in ambito.hallazgos_veredicto(con, texto, citas_contexto):
                    por_id[b['id']].citas.append(ResultadoCita(f'(ambito) {h.regla}', nivel=ERROR, estado='FUERA_DE_AMBITO', detalle=[h.motivo]))
    return ResultadosBrechas(sorted(salida, key=lambda x: -_GRAVEDAD[x.nivel]), modo=modo, hallazgos=hallazgos, hallazgos_posteriores=hallazgos_posteriores)

def _limpia(s) -> str:
    """Public CI documentation."""
    return ' '.join(str(s).split())

def _celda(s) -> str:
    """Public CI documentation."""
    return _limpia(s).replace('|', '\\|')

def _cabecera_fase2(s) -> str:
    """Public CI documentation."""
    texto = _limpia(s or '')
    if texto == NOTA_TEXTO_LICENCIA:
        return texto
    return re.sub('([\\\\`*_{}\\[\\]()<>#+!|~])', '\\\\\\1', texto)

def _cuenta(valores) -> str:
    n: dict[str, int] = {}
    for v in valores:
        n[v] = n.get(v, 0) + 1
    return ', '.join((f'{k}: {v}' for k, v in sorted(n.items()))) or 'ninguna'

def _con_punto(s: str) -> str:
    """Public CI documentation."""
    s = s.rstrip()
    return s if not s or s[-1] in '.!?:;' else s + '.'

def _campo_con_punto(texto: str, vacio: str) -> str:
    """Public CI documentation."""
    return _con_punto(texto) if texto else vacio

def informe_markdown(con: sqlite3.Connection, registro: dict, resultados: list[ResultadoBrecha], datos_vigencia=_CARGAR) -> str:
    """Public CI documentation."""
    if datos_vigencia is _CARGAR:
        datos_vigencia = vigencia.instantanea_actual()
    modo = getattr(resultados, 'modo', None) or interruptores.modo(CONTROL)
    hallazgos: list[HallazgoR27] = list(getattr(resultados, 'hallazgos', None) or [])
    citas = [c for r in resultados for c in r.citas]
    verificadas = sum((1 for c in citas if c.nivel == OK))
    con_aviso = sum((1 for c in citas if c.nivel == AVISO))
    con_error = sum((1 for c in citas if c.nivel == ERROR))
    sin_verificar = [r.brecha['id'] for r in resultados if r.nivel != OK]
    sin_revision = [r.brecha['id'] for r in resultados if r.ultima_revision is None]
    mal_revision = [r.brecha['id'] for r in resultados if r.ultima_revision and r.ultima_revision['veredicto'] in VEREDICTOS_CON_AVISO]
    try:
        huella = f"huella {db.huella_contenido(con)[:8]}, {con.execute('SELECT count(*) FROM precepto').fetchone()[0]} preceptos"
    except sqlite3.Error:
        huella = 'huella desconocida'
    consultado = (datos_vigencia or {}).get('consultado')
    consulta_vig = consultado[:10] if consultado else 'sin consulta guardada'
    L = ['# Seguimiento de brechas', '']
    if registro.get('cliente') or registro.get('informe'):
        L.append(' · '.join((x for x in (registro.get('cliente'), registro.get('informe')) if x)))
        L.append('')
    L += [f'Base: {huella}. Vigencia consultada: {consulta_vig}.', '', '## Resumen', '', f"- Brechas: {len(resultados)}. Por estado: {_cuenta((r.brecha['estado'] for r in resultados))}.", f"- Por capa: {_cuenta((_limpia(r.brecha.get('capa') or _SIN_CAPA) for r in resultados))}.", f'- Citas: {len(citas)}. Verificadas: {verificadas}. Con aviso: {con_aviso}. Con error: {con_error}.', f'- Brechas con alguna cita sin verificar (o sin citas): {len(sin_verificar)}' + (f" ({', '.join((_limpia(i) for i in sin_verificar))})." if sin_verificar else '.'), f'- Brechas sin ninguna revisión: {len(sin_revision)}' + (f" ({', '.join((_limpia(i) for i in sin_revision))})." if sin_revision else '.'), f'- Brechas cuya última revisión es «no_cumple» o «parcial»: {len(mal_revision)}' + (f" ({', '.join((_limpia(i) for i in mal_revision))})." if mal_revision else '.')]
    if modo == 'bloquea':
        h_minutos = next((h for h in hallazgos if h.tipo == 'minutos_tope'), None)
        if h_minutos:
            L.append(f'- AVISO: {h_minutos.mensaje}')
    L += ['', '## Brechas', '', 'Primero las que tienen alguna cita sin verificar.', '']
    for r in resultados:
        b = r.brecha
        L.append(f"### {_limpia(b['id'])}" + (f" · {_limpia(b['titulo'])}" if b.get('titulo') else ''))
        L.append('')
        L.append(f"- Estado: **{b['estado']}**" + (f" (desde {b['fecha_estado']})" if b.get('fecha_estado') else '') + f" · Capa: {_limpia(b.get('capa') or _SIN_CAPA)}")
        u = r.ultima_revision
        if u:
            falta = f" · falta: {_limpia(u['que_falta'])}" if u.get('que_falta') else ''
            L.append(f"- Última revisión: nº {u['numero']} ({u['fecha']}): **{u['veredicto']}**{falta}")
        else:
            L.append('- Última revisión: ninguna')
        for a in r.avisos_revision:
            L.append(f'- AVISO: {a}')
        if modo == 'bloquea':
            for h in hallazgos:
                if h.brecha_id == b['id'] and h.tipo == 'tercera_revision':
                    L.append(f'- AVISO: {h.mensaje}')
        L.append('')
        if not r.citas:
            L += ['AVISO: la brecha no tiene citas normativas: su base no está verificada.', '']
            continue
        L += ['| Cita | Resultado | Detalle |', '|---|---|---|']
        for c in r.citas:
            detalle = '; '.join(c.detalle) or '; '.join(c.ok)
            if c.detalle and c.ok:
                detalle += ' (' + '; '.join(c.ok) + ')'
            L.append(f'| `{_celda(c.identificador)}` | {c.nivel} | {_celda(detalle)} |')
        L.append('')
    L += _seccion_sombra(hallazgos, modo)
    return '\n'.join(L).rstrip() + '\n'

def _seccion_sombra(hallazgos: list[HallazgoR27], modo: str) -> list[str]:
    """Public CI documentation."""
    L: list[str] = []
    negaciones = [h for h in hallazgos if h.tipo == 'negacion']
    if modo == 'bloquea' and negaciones:
        L.append('## Para Responsable: negaciones que leer')
        L.append('')
        for h in negaciones:
            L.append(f'- {h.brecha_id}: «{h.mensaje}»')
        L.append('')
    if modo == 'sombra' or any((h.tipo == 'fuera_de_ambito' for h in hallazgos)):
        L.append('## PARA MIRAR (control en sombra)')
        L.append('')
        otros = [h for h in hallazgos if h.tipo != 'negacion']
        if otros:
            for h in otros:
                prefijo = f'{h.brecha_id}: ' if h.brecha_id else ''
                L.append(f'- {prefijo}{h.mensaje}')
        else:
            L.append('- Ninguno.')
        if negaciones:
            L.append('')
            L.append('### Para Responsable: negaciones que leer')
            L.append('')
            for h in negaciones:
                L.append(f'- {h.brecha_id}: «{h.mensaje}»')
    return L
TIPOS_INFORME_FASE2 = ('borrador', 'intermedio', 'final', 'partida')
TITULO_INFORME_FASE2 = {'partida': 'Informe de estado de partida — Fase 2'}
TRADUCCION_ESTADO_FASE2 = {'cumple': 'cerrada', 'no_cumple': 'abierta', 'parcial': 'abierta', 'pendiente': 'pendiente de un tercero'}
ESTADO_FASE2_CERRADA_FASE1 = 'cerrada en la Fase 1'
ESTADO_FASE2_REFORMULADA = 'reformulada'
ESTADO_FASE2_ABIERTA = 'abierta'
ESTADO_FASE2_NUEVA = 'nueva (detectada en este seguimiento)'
_ETIQUETA_REQUERIMIENTO = {'no_recibido': 'Pendiente: no recibido', 'recibido_en_parte': 'Recibido en parte', 'recibido_con_reservas': 'Recibido con reservas', 'recibido': 'Recibido'}
_REQUERIMIENTOS_CON_RECEPCION = frozenset({'recibido', 'recibido_en_parte', 'recibido_con_reservas'})
_SUFIJO_SIN_DETALLE = '(sin detalle en el registro)'
_SUFIJO_CON_EVIDENCIA_ANOTADA = '(hay documentación anotada en el registro)'
_ESTADOS_SIN_SUFIJO_DE_RECEPCION = ('cerrada', 'reformulada', 'nueva')
PAPEL_ETIQUETA = {'fundamento': 'Fundamento', 'apoyo': 'Apoyo', 'contexto': 'Contexto'}
CAPAS_FASE2 = ('metrologia_legal', 'integridad', 'integridad_datos', 'ciberseguridad', 'calibracion', 'trazabilidad')
_NOMBRE_CAPA = {'metrologia_legal': 'Metrología legal', 'integridad': 'Integridad', 'integridad_datos': 'Integridad de datos', 'ciberseguridad': 'Ciberseguridad', 'calibracion': 'Calibración', 'trazabilidad': 'Trazabilidad'}

class InformeFase2Bloqueado(ValueError):
    """Public CI documentation."""

def _recepcion_sin_detalle(brecha: dict, corte: str | None=None) -> bool:
    """Public CI documentation."""
    if ultima_revision_a_fecha(brecha, corte) is not None or brecha.get('estado_requerimiento') not in _REQUERIMIENTOS_CON_RECEPCION or (brecha.get('evidencia_aportada') or '').strip():
        return False
    if brecha.get('estado') == 'cerrada':
        if brecha.get('estado_requerimiento') == 'recibido_en_parte':
            return False
        return True
    return True
_RE_DOCUMENTACION_FASE2 = re.compile('document|certificad|declaraci[oó]n|\\bacta\\b|expediente|\\bhojas?\\b|\\bficha\\b|aport|recibi|adjunt|\\bescrit[oa]\\b|\\bcorreo\\b|\\binforme\\b', re.IGNORECASE)
_MARCA_EVIDENCIA_SIN_ANOTAR = 'anotar en evidencia_aportada lo que se recibió, o confirmar que no se recibió nada'
_DOCUMENTO_SIN_ANOTAR = 'sin anotar en el registro.'

def _evidencia_sin_anotar_fase2(brecha: dict, corte: str | None=None) -> bool:
    """Public CI documentation."""
    ultima = ultima_revision_a_fecha(brecha, corte)
    if ultima is not None:
        return not (ultima.get('documento_aportado') or '').strip() and bool(_RE_DOCUMENTACION_FASE2.search(ultima.get('que_falta') or ''))
    if _estado_tras_corte(brecha, corte) or (brecha.get('evidencia_aportada') or '').strip():
        return False
    return brecha.get('estado_requerimiento') in _REQUERIMIENTOS_CON_RECEPCION or bool(_RE_DOCUMENTACION_FASE2.search(brecha.get('descripcion') or ''))

def _no_recibido_con_evidencia(brecha: dict, corte: str | None=None) -> bool:
    """Public CI documentation."""
    return brecha.get('estado') not in ('reformulada', 'nueva') and ultima_revision_a_fecha(brecha, corte) is None and (brecha.get('estado_requerimiento') == 'no_recibido') and bool((brecha.get('evidencia_aportada') or '').strip())

def _cerrada_con_recepcion_parcial(brecha: dict, corte: str | None=None) -> bool:
    """Public CI documentation."""
    return brecha.get('estado') == 'cerrada' and ultima_revision_a_fecha(brecha, corte) is None and (brecha.get('estado_requerimiento') == 'recibido_en_parte')

def _cerrada_recepcion_parcial_sin_evidencia(brecha: dict, corte: str | None=None) -> bool:
    """Public CI documentation."""
    return _cerrada_con_recepcion_parcial(brecha, corte) and (not (brecha.get('evidencia_aportada') or '').strip())

def estado_fase2(brecha: dict, corte: str | None=None) -> str:
    """Public CI documentation."""
    ultima = ultima_revision_a_fecha(brecha, corte)
    if ultima is not None:
        estado = TRADUCCION_ESTADO_FASE2.get(ultima['veredicto'], ESTADO_FASE2_ABIERTA)
        if not _estado_tras_corte(brecha, corte) and brecha.get('estado') == 'cerrada' and (ultima['veredicto'] in VEREDICTOS_CON_AVISO):
            return f"{estado} (incoherencia en el registro: la carencia está marcada «cerrada» pero su última revisión, la nº {ultima['numero']}, es «{ultima['veredicto']}»)"
        return estado
    if _estado_tras_corte(brecha, corte):
        return 'estado posterior al corte; aclarar'
    if brecha.get('estado') == 'cerrada':
        return ESTADO_FASE2_CERRADA_FASE1
    if brecha.get('estado') == 'reformulada':
        return ESTADO_FASE2_REFORMULADA
    if brecha.get('estado') == 'nueva':
        return ESTADO_FASE2_NUEVA
    er = brecha.get('estado_requerimiento')
    if er in _ETIQUETA_REQUERIMIENTO:
        if _recepcion_sin_detalle(brecha, corte):
            return f'{_ETIQUETA_REQUERIMIENTO[er]} {_SUFIJO_SIN_DETALLE}'
        if _no_recibido_con_evidencia(brecha, corte):
            return f'{_ETIQUETA_REQUERIMIENTO[er]} {_SUFIJO_CON_EVIDENCIA_ANOTADA}'
        return _ETIQUETA_REQUERIMIENTO[er]
    return ESTADO_FASE2_ABIERTA

def _estado_tras_corte(brecha: dict, corte: str | None) -> bool:
    return bool(corte and brecha.get('fecha_estado') and (brecha['fecha_estado'] > corte))

def _situacion_carencia_fase2(brecha: dict, corte: str | None=None) -> str:
    """Public CI documentation."""
    ultima = ultima_revision_a_fecha(brecha, corte)
    if ultima is not None:
        return TRADUCCION_ESTADO_FASE2.get(ultima['veredicto'], ESTADO_FASE2_ABIERTA)
    if _estado_tras_corte(brecha, corte):
        return 'sin información a la fecha de corte'
    if brecha.get('estado') == 'cerrada':
        return 'cerrada en la fase 1'
    if brecha.get('estado') == 'reformulada':
        return 'reformulada'
    if brecha.get('estado') == 'nueva':
        return ESTADO_FASE2_NUEVA
    return ESTADO_FASE2_ABIERTA
_VEREDICTO_LEGIBLE_FASE2 = {'no_cumple': 'no cumple', 'parcial': 'parcial', 'cumple': 'cumple', 'pendiente': 'pendiente'}

def _incoherencia_situacion_fase2(brecha: dict, corte: str | None=None) -> str | None:
    """Public CI documentation."""
    ultima = ultima_revision_a_fecha(brecha, corte)
    if ultima is not None and (not _estado_tras_corte(brecha, corte)) and (brecha.get('estado') == 'cerrada') and (ultima['veredicto'] in VEREDICTOS_CON_AVISO):
        veredicto = _VEREDICTO_LEGIBLE_FASE2.get(ultima['veredicto'], ultima['veredicto'])
        return f"esta carencia está marcada «cerrada», pero su última revisión (nº {ultima['numero']}) es «{veredicto}»"
    if ultima is None and (not _estado_tras_corte(brecha, corte)) and (brecha.get('estado') == 'cerrada') and (brecha.get('estado_requerimiento') == 'no_recibido') and (not (brecha.get('evidencia_aportada') or '').strip()):
        return 'esta carencia está marcada «cerrada en la fase 1», pero estado_requerimiento es «no_recibido» sin evidencia_aportada que lo respalde'
    return None
_RESPUESTA_REQUERIMIENTO_FASE2 = {'no_recibido': 'pendiente: no recibido', 'recibido_en_parte': 'recibido en parte', 'recibido_con_reservas': 'recibido con reservas', 'recibido': 'recibido'}

def _respuesta_requerimiento_fase2(brecha: dict, corte: str | None=None) -> str | None:
    """Public CI documentation."""
    if ultima_revision_a_fecha(brecha, corte) is not None:
        return None
    if _estado_tras_corte(brecha, corte):
        return None
    er = brecha.get('estado_requerimiento')
    if er not in _RESPUESTA_REQUERIMIENTO_FASE2:
        return None
    if _recepcion_sin_detalle(brecha, corte) or _no_recibido_con_evidencia(brecha, corte):
        return 'pendiente de confirmar'
    return _RESPUESTA_REQUERIMIENTO_FASE2[er]

def _minutos_de_brecha(brecha: dict) -> int:
    return sum((r.get('minutos') or 0 for r in brecha.get('revisiones') or [] if isinstance(r.get('minutos'), int) and (not isinstance(r.get('minutos'), bool))))
_RE_CODIGO_INTERNO = re.compile('^(?:ICT155-DOC-|CELEX-|DOUE-|BOE-A-)', re.IGNORECASE)
_RE_EDICION = re.compile('^edicion \\d{4}$')

def _norma_corta_y_edicion(con: sqlite3.Connection, r, norma_citada: str) -> str:
    """Public CI documentation."""
    if _RE_CODIGO_INTERNO.match(norma_citada):
        if not r.obra:
            return norma_citada
        norma = historial_boe._alias_de_cita(con, r.obra)
        if _RE_CODIGO_INTERNO.match(norma) and r.obra_titulo:
            norma = r.obra_titulo
    else:
        norma = norma_citada
    if r.version and _RE_EDICION.match(r.version):
        norma = f"{norma} ({r.version.replace('edicion', 'edición')})"
    return norma
_RE_NORMA_EN = re.compile('^EN[\\s-]', re.IGNORECASE)

def referencia_legible_fase2(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',)) -> str:
    """Public CI documentation."""
    ident = identificador.strip()
    cab, ruta = consulta.partir_identificador(ident)
    norma_citada = cab.partition('@')[0].strip()
    r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
    norma = _norma_corta_y_edicion(con, r, norma_citada)
    etiqueta = r.etiqueta_humana
    if ruta and etiqueta:
        if not etiqueta[:2].isupper():
            etiqueta = etiqueta[0].lower() + etiqueta[1:]
        texto = f'{norma}, {etiqueta}'
    elif ruta:
        texto = f'{norma}, {ruta}'
    else:
        texto = norma
    if r.obra and _RE_NORMA_EN.match(r.obra) and r.paginas and ('página' not in texto) and ('pagina' not in texto):
        texto = f'{texto} ({r.paginas})'
    return texto

def _avisos_vigencia_y_base_fase2(con: sqlite3.Connection, ident: str, ambitos: tuple[str, ...], datos_vigencia, avisos_de_limites) -> list[str]:
    """Public CI documentation."""
    r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
    avisos: list[str] = []
    if r.obra:
        v = vigencia.vigencia_de(r.obra, datos_vigencia)
        avisos += [f'vigencia: {a}' for a in (v or {}).get('avisos', [])]
    if avisos_de_limites and r.obra and (r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO)):
        escrito, _, ruta = ident.partition('::')
        avisos += [f'límite conocido: {a}' for a in avisos_de_limites([r.obra, r.obra_titulo, escrito.partition('@')[0].strip()], ruta.strip())]
    return avisos

def _nombre_norma_fase2(con: sqlite3.Connection, m: dict) -> str:
    """Public CI documentation."""
    desc = m.get('titulo') or m.get('texto')
    if desc:
        return _limpia(desc)
    try:
        return historial_boe._alias_de_cita(con, m['id'])
    except almacen.ErrorDeAlmacen:
        raise
    except Exception:
        return 'una norma no identificada en la base'

@dataclass
class NotaVigenciaFase2:
    """Public CI documentation."""
    texto: str | None = None
    para_responsable: str | None = None
    bloquea: str | None = None
_RE_FECHA_LARGA = re.compile('\\b(\\d{1,2}) de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) de (\\d{4})\\b', re.IGNORECASE)
_MESES_LARGOS = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
_RE_JERGA_LIMITE = re.compile('\\bla base\\b|::|\\bnormativa_cita\\b|ICT155-DOC-|CELEX-\\d|DOUE-\\d|BOE-A-\\d|\\bPDF\\b|\\bleerlo\\b|\\bCitar\\b|\\b\\d{4}-\\d{2}-\\d{2}\\b', re.IGNORECASE)
_RE_COLETILLA_LIMITE = re.compile('(Hasta esa fecha (?:sigue aplic[aá]ndose|se aplica))\\s*:\\s*la\\s*«?modificaci[oó]n posterior»?\\s+que señala la vigencia[^.]*\\.?', re.IGNORECASE)
_RE_ESA_FECHA = re.compile('\\besa fecha\\b', re.IGNORECASE)
_RE_FECHA_CORTA = re.compile('\\b\\d{1,2}/\\d{1,2}/\\d{4}\\b')
_RE_PALABRAS_CLAVE_LIMITE = re.compile('\\bderog\\w*|\\bmodific\\w*|\\bsustituy\\w*|\\bsalvo\\b|\\bexcepto\\b|\\bcambia\\w*', re.IGNORECASE)

def _redaccion_limite_para_cliente(texto: str) -> str | None:
    """Public CI documentation."""
    original = texto
    t = texto
    t = re.sub('\\s*\\([^()]*(?:::|en la base|normativa_cita)[^()]*\\)', '', t, flags=re.IGNORECASE)
    t = _RE_FECHA_LARGA.sub(lambda m: f'{int(m[1]):02d}/{_MESES_LARGOS[m[2].lower()]:02d}/{m[3]}', t)
    t = _RE_COLETILLA_LIMITE.sub('\\1.', t)
    t = re.sub('\\bque señala la vigencia\\b', 'detectada', t, flags=re.IGNORECASE)
    t = re.sub('\\bsigue aplicándose\\b', 'se aplica', t, flags=re.IGNORECASE)
    t = ' '.join(t.split()).strip()
    if t and t[-1] not in '.!?':
        t += '.'
    if not t or _RE_JERGA_LIMITE.search(t):
        return None
    m_fecha = _RE_ESA_FECHA.search(t)
    if m_fecha and (not _RE_FECHA_CORTA.search(t[:m_fecha.start()])):
        return None
    if _RE_PALABRAS_CLAVE_LIMITE.search(original) and (not _RE_PALABRAS_CLAVE_LIMITE.search(t)):
        return None
    return t

def _limite_conocido_fase2(avisos_de_limites, obra: str | None, obra_titulo: str | None, norma_citada: str | None, ruta: str, numeros_acto: list[str] | None=None, permitir_sin_numero: bool=False) -> str | None:
    """Public CI documentation."""
    if not (avisos_de_limites and obra):
        return None
    avisos = avisos_de_limites([obra, obra_titulo, norma_citada], ruta)
    if numeros_acto:
        con_acto = [a for a in avisos if any((re.search(f'(?<![\\d/]){re.escape(n)}(?!\\d)', a) for n in numeros_acto))]
        avisos = con_acto or (avisos if permitir_sin_numero else [])
    for a in avisos:
        limpio = _redaccion_limite_para_cliente(a)
        if limpio:
            return limpio
    return None

def _acto_derogatorio_fase2(con: sqlite3.Connection, d: dict) -> str:
    """Public CI documentation."""
    titulo = d.get('titulo')
    if titulo:
        return _limpia(titulo)
    try:
        alias = historial_boe._alias_de_cita(con, d.get('id') or '')
    except almacen.ErrorDeAlmacen:
        raise
    except Exception:
        alias = 'un acto no identificado en la base'
    relacion = _limpia(d.get('texto') or '')
    return f'{alias} ({relacion})' if relacion else alias

def _nota_vigencia_fase2(con: sqlite3.Connection, v: dict | None, *, avisos_de_limites=None, obra: str | None=None, obra_titulo: str | None=None, norma_citada: str | None=None, ruta: str='', corte: str | None=None, norma_legible: str | None=None) -> NotaVigenciaFase2:
    """Public CI documentation."""
    if not v:
        return NotaVigenciaFase2()
    nombre_norma = norma_legible or norma_citada or obra_titulo or obra or 'esta norma'
    if v.get('estado') is None:
        motivo = f'no se conoce la vigencia de {nombre_norma} (sin consulta de vigencia guardada, o la norma no está en esa consulta): añade la consulta de vigencia o quita la cita'
        return NotaVigenciaFase2(bloquea=motivo, para_responsable=motivo)
    frases: list[str] = []
    para_responsable: list[str] = []
    bloqueos: list[str] = []
    if v['estado'] == 'derogada':
        derogada_por = v.get('derogada_por') or []
        por = '; '.join((_acto_derogatorio_fase2(con, d) for d in derogada_por)) or 'un acto no identificado en la base'
        numeros_deroga = [n for d in derogada_por for n in vigencia.numeros_de_la_norma(d.get('id') or '', d.get('titulo') or d.get('texto'))]
        limite_derogacion = _limite_conocido_fase2(avisos_de_limites, obra, obra_titulo, norma_citada, ruta, numeros_acto=numeros_deroga, permitir_sin_numero=not v.get('modificaciones_posteriores'))
        fecha_derogacion = v.get('fecha_derogacion')
        fecha = _fecha_legible(fecha_derogacion)
        futura = bool(fecha_derogacion) and bool(corte) and (fecha_derogacion > corte)
        if limite_derogacion:
            frases.append(limite_derogacion)
        elif futura:
            frases.append(f'Está aprobada la derogación de esta norma, por {por}' + (f', con efecto a partir del {fecha}' if fecha else '') + ', que todavía no ha entrado en vigor.')
        else:
            frases.append('Esta norma está derogada' + (f' desde el {fecha}' if fecha else '') + f', por {por}.')
            para_responsable.append(f'la norma citada está derogada, por {por}: quita la cita, justifica ante el cliente por qué se cita a pesar de la derogación, o añade el límite conocido en cowork/limites_conocidos.json si su efecto ya consta resuelto.')
            bloqueos.append(f'{nombre_norma} está derogada' + (f' desde el {fecha}' if fecha else '') + f' por {por}, y no hay límite conocido que lo matice')
    elif v['estado'] == 'anulada':
        frases.append('Esta norma ha sido anulada.')
    elif v['estado'] == 'vigencia_agotada':
        frases.append('La vigencia de esta norma ha terminado.')
    numeros = vigencia.numeros_de_la_norma(v.get('identificador_oficial') or '', obra_titulo)
    modificaciones = v.get('modificaciones_posteriores') or []
    sin_otro_acto_que_confundir = len(modificaciones) == 1 and (not v.get('derogada_por'))
    for m in modificaciones:
        nombre = _nombre_norma_fase2(con, m)
        fecha = _fecha_legible(m.get('fecha_comparada'))
        incierta = bool(m.get('dudosa') or m.get('fecha_desconocida'))
        deroga = vigencia.deroga_la_norma(m, numeros)
        numeros_m = vigencia.numeros_de_la_norma(m.get('id') or '', m.get('titulo') or m.get('texto'))
        limite_m = _limite_conocido_fase2(avisos_de_limites, obra, obra_titulo, norma_citada, ruta, numeros_acto=numeros_m, permitir_sin_numero=sin_otro_acto_que_confundir)
        if m.get('futura'):
            verbo = 'derogación' if deroga else 'modificación'
            frases.append(f'Está aprobada una {verbo} de esta norma, por {nombre}, que todavía no ha entrado en vigor.')
        elif limite_m:
            if limite_m not in frases:
                frases.append(limite_m)
        elif deroga:
            para_responsable.append(f'{nombre} deroga (o puede derogar) esta norma' + (' (fecha de comparación incierta)' if incierta else '') + '; sin un límite conocido que aclare si el efecto ya se ha producido no se puede confirmar ante el cliente: añade el límite conocido en cowork/limites_conocidos.json o quita la cita.')
            bloqueos.append(f'{nombre_norma} puede estar derogada por {nombre} y no consta, por un límite conocido, si el efecto ya se ha producido')
        else:
            frases.append(f'Se ha publicado una modificación posterior de esta norma: {nombre}' + (f', de {fecha}.' if fecha else '.'))
            para_responsable.append(f'comprobar si el precepto citado cambia con la modificación posterior, {nombre}' + (' (fecha de comparación incierta)' if incierta else ''))
    return NotaVigenciaFase2(texto=' '.join(frases) if frases else None, para_responsable='; '.join(para_responsable) or None, bloquea='; '.join(bloqueos) or None)

@dataclass
class _NotaVigenciaFase2ConCarencias:
    """Public CI documentation."""
    norma_legible: str
    nota: NotaVigenciaFase2
    ruta: str = ''
    carencias: list[str] = field(default_factory=list)

def _calcular_notas_vigencia_fase2(con: sqlite3.Connection, brechas_reg: list[dict], ambitos: tuple[str, ...], datos_vigencia, avisos_de_limites, corte: str | None) -> dict[tuple[str, str], _NotaVigenciaFase2ConCarencias]:
    """Public CI documentation."""
    notas: dict[tuple[str, str], _NotaVigenciaFase2ConCarencias] = {}
    for b in brechas_reg:
        for c in b.get('citas') or []:
            if not isinstance(c, dict) or not c.get('identificador'):
                continue
            ident = c['identificador'].strip()
            r_vig = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
            if not r_vig.obra:
                continue
            cab, ruta = consulta.partir_identificador(ident)
            ruta = ruta.strip()
            clave = (r_vig.obra, ruta)
            entrada = notas.get(clave)
            if entrada is None:
                norma_citada = cab.partition('@')[0].strip()
                norma_legible = _norma_corta_y_edicion(con, r_vig, norma_citada)
                v = vigencia.vigencia_de(r_vig.obra, datos_vigencia)
                nota = _nota_vigencia_fase2(con, v, avisos_de_limites=avisos_de_limites, obra=r_vig.obra, obra_titulo=r_vig.obra_titulo, norma_citada=norma_citada, ruta=ruta, corte=corte, norma_legible=norma_legible)
                entrada = notas[clave] = _NotaVigenciaFase2ConCarencias(norma_legible, nota, r_vig.etiqueta_humana or ruta)
            if b['id'] not in entrada.carencias:
                entrada.carencias.append(b['id'])
    return notas

def _textos_no_publicos(con: sqlite3.Connection, citas_brecha: list, ambitos: tuple[str, ...]) -> list[str]:
    """Public CI documentation."""
    obras = set()
    for c in citas_brecha or []:
        if not isinstance(c, dict) or not c.get('identificador'):
            continue
        ident = c['identificador'].strip()
        r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
        if r.obra:
            obras.add(r.obra)
        elif r.estado == consulta.OBRA_AMBIGUA:
            obras.update(r.candidatos or [])
        elif r.estado == consulta.NO_CONSTA:
            cab, _ = consulta.partir_identificador(ident)
            rechazadas = []
            consulta._obra_por_alias(con, cab.partition('@')[0], rechazadas)
            obras.update((f['identificador_canonico'] for f in rechazadas))
    return [f[0] for obra in sorted(obras) for f in con.execute("SELECT p.texto_literal FROM precepto p JOIN version v ON v.id=p.version_id JOIN documento d ON d.id=v.documento_id JOIN obra o ON o.id=v.obra_id WHERE o.identificador_canonico=? AND coalesce(d.clase_derechos,'')<>'publico'", (obra,))]
NOTA_TEXTO_LICENCIA = '[texto de norma con licencia: ver la cita]'

def _textos_publicos_citados(con: sqlite3.Connection, citas_brecha: list, ambitos: tuple[str, ...]) -> list[str]:
    """Public CI documentation."""
    textos = []
    for c in citas_brecha or []:
        if not isinstance(c, dict) or not c.get('identificador'):
            continue
        ident = c['identificador'].strip()
        r = consulta.resolver(con, ident, ambitos, modo=consulta.MODO_LOCALIZAR)
        if r.regimen != 'publico' or r.estado != consulta.ENCONTRADO:
            continue
        r = consulta.resolver(con, ident, ambitos)
        if r.regimen == 'publico' and r.estado == consulta.ENCONTRADO and r.texto_literal:
            textos.append(r.texto_literal)
    return textos

def _tachar_licencia_en_prosa(con: sqlite3.Connection, texto: str, citas_brecha: list, ambitos: tuple[str, ...], textos_precepto: list[str] | None=None, textos_publicos: list[str] | None=None) -> str:
    """Public CI documentation."""
    if not texto:
        return texto
    if textos_precepto is None:
        textos_precepto = _textos_no_publicos(con, citas_brecha, ambitos)
    if not textos_precepto:
        return texto
    if textos_publicos is None:
        textos_publicos = _textos_publicos_citados(con, citas_brecha, ambitos)
    publicos_normalizados = [' ' + fundamento.normalizar(p) + ' ' for p in textos_publicos]
    palabras = fundamento.normalizar(texto).split()
    if len(palabras) >= 12:
        tramos = {' ' + ' '.join(palabras[i:i + 12]) + ' ' for i in range(len(palabras) - 11)}
        tramos = {t for t in tramos if not any((t in p for p in publicos_normalizados))}
        normalizados = (' ' + fundamento.normalizar(p) + ' ' for p in textos_precepto)
        if any((any((t in p for t in tramos)) for p in normalizados)):
            return NOTA_TEXTO_LICENCIA

    def _reemplaza(m: re.Match) -> str:
        lit = next((g for g in m.groups() if g))
        fragmentos = [f.strip(' .,;:') for f in revision.RE_ELISION.split(lit) if f.strip(' .,;:')] or [lit]
        if any((revision._esta_en(fragmentos, t) for t in textos_publicos)):
            return m.group(0)
        if any((revision._esta_en(fragmentos, t) for t in textos_precepto)):
            return '«[texto de la norma omitido: norma con licencia]»'
        return m.group(0)
    return revision.RE_COMILLAS.sub(_reemplaza, texto)
_PROFUNDIDAD_MAXIMA_COPIA_FASE2 = 50

def proteger_registro_fase2(con: sqlite3.Connection, registro: dict, ambitos: tuple[str, ...]=('publico',)) -> tuple[dict, list[str]]:
    """Public CI documentation."""
    marcas = []
    cache = {}

    def corpus(citas):
        clave = tuple(sorted((c.get('identificador', '') for c in citas if isinstance(c, dict))))
        if clave not in cache:
            cache[clave] = (_textos_no_publicos(con, citas, ambitos), _textos_publicos_citados(con, citas, ambitos))
        return cache[clave]

    def copiar(valor, textos, ruta, profundidad=0):
        if profundidad > _PROFUNDIDAD_MAXIMA_COPIA_FASE2:
            raise ValueError(f'registro no válido: {ruta} supera los {_PROFUNDIDAD_MAXIMA_COPIA_FASE2} niveles de anidamiento permitidos')
        if isinstance(valor, str):
            seguro = _tachar_licencia_en_prosa(con, valor, [], ambitos, *textos)
            if seguro != valor:
                marcas.append(f'texto de norma con licencia omitido en {ruta}: ver la cita y revisar antes de firmar')
            return seguro
        if isinstance(valor, dict):
            return {k: copiar(v, textos, f'{ruta}.{k}', profundidad + 1) for k, v in valor.items()}
        if isinstance(valor, list):
            return [copiar(v, textos, f'{ruta}[{i}]', profundidad + 1) for i, v in enumerate(valor, 1)]
        return valor
    todas = [c for b in registro.get('brechas', []) for c in b.get('citas', [])]
    limpio = {k: copiar(v, corpus(todas), k) for k, v in registro.items() if k != 'brechas'}
    limpio['brechas'] = [copiar(b, corpus(b.get('citas') or []), f'carencia nº {i}') for i, b in enumerate(registro.get('brechas', []), 1)]
    return (limpio, marcas)
_RE_RECORTE_FINAL = re.compile('(?:siguientes|es el siguiente|following)\\s*[:.;]?\\s*$', re.IGNORECASE)
_RE_RECORTE_PUNTOS = re.compile('\\[\\s*(?:…|\\.\\.\\.)\\s*\\]')
_MOTIVO_SIN_SUJETO = 'el literal empieza sin sujeto (letra minúscula inicial): puede ser un fragmento cortado a media frase'

def _recorte_cambia_sentido(literal: str, texto_precepto: str | None=None) -> str | None:
    """Public CI documentation."""
    t = literal.strip()
    if not t:
        return None
    precepto_sin_marca = None
    if texto_precepto:
        m = revision.RE_MARCA_DE_ELEMENTO.match(texto_precepto.strip())
        precepto_sin_marca = texto_precepto[m.end():] if m else None
    si_sujeto = revision.RE_MARCA_DE_ELEMENTO.match(t) is not None or (texto_precepto and fundamento.normalizar(t) == fundamento.normalizar(texto_precepto)) or (precepto_sin_marca and fundamento.normalizar(t) == fundamento.normalizar(precepto_sin_marca))
    if t[0].islower() and (not si_sujeto):
        return _MOTIVO_SIN_SUJETO
    if _RE_RECORTE_PUNTOS.search(t):
        return 'el literal usa «[…]» para saltarse una parte del texto: puede ocultar una condición o una excepción'
    if _RE_RECORTE_FINAL.search(t):
        return 'el literal termina en «…siguientes/es el siguiente/following»: probablemente corta justo antes de una lista o condición'
    return None
_PREFIJOS_GOBIERNO = ('deja fuera la condición de su frase:', 'la frase sigue con una condición:', 'le sigue una excepción:')

@dataclass
class RequisitoFase2:
    """Public CI documentation."""
    identificador: str
    referencia: str
    literal: str | None = None
    papel: str | None = None
    avisos: list[str] = field(default_factory=list)
    recorte: str | None = None

def _requisito_fase2(con: sqlite3.Connection, cita: dict, ambitos: tuple[str, ...], huella_base: str | None=None, datos_vigencia=None, avisos_de_limites=None) -> RequisitoFase2:
    """Public CI documentation."""
    ident = cita['identificador'].strip()
    referencia = referencia_legible_fase2(con, ident, ambitos)
    papel = cita.get('papel') if cita.get('papel') in PAPEL_ETIQUETA else None
    avisos = _avisos_vigencia_y_base_fase2(con, ident, ambitos, datos_vigencia, avisos_de_limites)
    literal = ' '.join((cita.get('literal') or '').split())
    if not literal:
        return RequisitoFase2(ident, referencia, None, papel, avisos, None)
    r = consulta.resolver(con, ident, ambitos)
    if r.estado not in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO) or r.regimen != 'publico':
        return RequisitoFase2(ident, referencia, None, papel, avisos, None)
    if NOTA_TEXTO_LICENCIA in literal or '[texto de la norma omitido: norma con licencia]' in literal:
        print(f'aviso: brechas --informe-fase2: el literal de la cita `{ident}` se omite del informe para el cliente por coincidencia con texto de norma con licencia sin respaldo en un precepto público citado', file=sys.stderr)
        return RequisitoFase2(ident, referencia, None, papel, avisos, None)
    recorte = _recorte_cambia_sentido(literal, r.texto_literal)
    if recorte:
        return RequisitoFase2(ident, referencia, None, papel, avisos, recorte)
    informe = revision.revisar(con, f'`{ident}`\n\n> {literal}\n', ambitos, huella_base=huella_base)
    literales = [c for c in informe.comprobaciones if c.tipo in ('literal', 'cotejo')]
    if any((c.nivel == ERROR for c in literales)):
        motivo = '; '.join((c.detalle for c in literales if c.nivel == ERROR))
        print(f'aviso: brechas --informe-fase2: el literal de la cita `{ident}` no coteja con el texto de la base ({motivo}); se omite del informe para el cliente', file=sys.stderr)
        return RequisitoFase2(ident, referencia, None, papel, avisos, None)
    gobierno = [c.detalle for c in literales if c.nivel == AVISO and c.detalle.startswith(_PREFIJOS_GOBIERNO)]
    if gobierno:
        return RequisitoFase2(ident, referencia, None, papel, avisos, '; '.join(gobierno))
    if not literales or any((c.nivel != OK for c in literales)):
        motivo = '; '.join((c.detalle for c in literales if c.nivel != OK)) or 'no se ha encontrado en la base'
        print(f'aviso: brechas --informe-fase2: el literal de la cita `{ident}` no coteja limpio con la base ({motivo}); se omite del informe para el cliente', file=sys.stderr)
        return RequisitoFase2(ident, referencia, None, papel, avisos, None)
    return RequisitoFase2(ident, referencia, literal, papel, avisos, None)

def _orden_capas(brechas_reg: list[dict]) -> list[str]:
    presentes = dict.fromkeys((b.get('capa') or _SIN_CAPA for b in brechas_reg))
    conocidas = [c for c in CAPAS_FASE2 if c in presentes]
    otras = sorted((c for c in presentes if c not in CAPAS_FASE2 and c != _SIN_CAPA))
    return conocidas + otras + ([_SIN_CAPA] if _SIN_CAPA in presentes else [])

def _tabla_resumen_por_capa(brechas_reg: list[dict], corte: str | None=None) -> list[str]:
    L = []
    for capa in _orden_capas(brechas_reg):
        de_la_capa = [b for b in brechas_reg if (b.get('capa') or _SIN_CAPA) == capa]
        L.append(f"### {_limpia(_NOMBRE_CAPA.get(capa, capa if capa == _SIN_CAPA else capa.replace('_', ' ').capitalize()))}")
        L.append('')
        L += ['| ID | Título | Situación de la carencia | Respuesta al requerimiento | Qué aportar |', '|---|---|---|---|---|']
        for b in de_la_capa:
            respuesta = _respuesta_requerimiento_fase2(b, corte)
            situacion = _situacion_carencia_fase2(b, corte)
            aportar = _que_aportar_fase2(b, corte)
            titulo = '' if _estado_tras_corte(b, corte) else b.get('titulo') or ''
            L.append(f"| {_celda(b['id'])} | {_celda(titulo)} | {_celda(situacion)} | {_celda(respuesta or '—')} | {_celda(aportar)} |")
        L.append('')
    return L

def _que_aportar_fase2(brecha: dict, corte: str | None) -> str:
    """Public CI documentation."""
    ultima = ultima_revision_a_fecha(brecha, corte)
    situacion = _situacion_carencia_fase2(brecha, corte)
    if situacion in ('cerrada', 'cerrada en la fase 1'):
        return '—'
    if ultima is not None:
        return (ultima.get('que_falta') or '').strip() or 'sin especificar en la revisión.'
    if _estado_tras_corte(brecha, corte):
        return 'sin información a la fecha de corte.'
    return (brecha.get('evidencia_requerida') or '').strip() or '(sin especificar)'

def _descripcion_y_peticion_fase2(brecha: dict, corte: str | None) -> list[tuple[str, str]]:
    """Public CI documentation."""
    estado_posterior = _estado_tras_corte(brecha, corte)
    ultima = ultima_revision_a_fecha(brecha, corte)
    situacion = _situacion_carencia_fase2(brecha, corte)
    cerrada_fase1 = situacion == 'cerrada en la fase 1'
    cerrada_por_revision = situacion == 'cerrada'
    descripcion = '' if estado_posterior else (brecha.get('descripcion') or '').strip()
    campos = []
    if ultima is not None and (not cerrada_por_revision):
        if descripcion:
            campos.append(('Antecedente', _limpia(descripcion)))
        campos.append(('Qué falta', _limpia(_que_aportar_fase2(brecha, corte))))
    elif cerrada_por_revision:
        campos.append(('Qué faltaba', _limpia(descripcion) if descripcion else '(sin especificar).'))
    elif estado_posterior:
        campos.append(('Qué falta', 'sin información a la fecha de corte.'))
    elif cerrada_fase1:
        campos.append(('Cómo se cerró', _limpia(descripcion) if descripcion else '(sin especificar).'))
    else:
        campos.append(('Qué falta', _limpia(descripcion) if descripcion else '(sin especificar).'))
    if not cerrada_por_revision:
        evidencia_requerida = _que_aportar_fase2(brecha, corte) if not cerrada_fase1 else (brecha.get('evidencia_requerida') or '').strip()
        if evidencia_requerida == '(sin especificar)':
            evidencia_requerida = '(sin especificar).'
        etiqueta_evidencia = 'Documento que la cierra' if cerrada_fase1 else 'Qué tiene que aportar para cerrarla'
        campos.append((etiqueta_evidencia, _limpia(evidencia_requerida) if evidencia_requerida else '(sin especificar).'))
    return campos

def _es_propuesta(version: str) -> bool:
    """Public CI documentation."""
    limpio = ''.join((ch for ch in unicodedata.normalize('NFKC', version or '') if unicodedata.category(ch) != 'Cf'))
    return 'propuesta' in re.sub('\\s+', '', limpio).casefold()

def informe_fase2_markdown(con: sqlite3.Connection, registro: dict, *, tipo: str='intermedio', corte: str | None=None, ambitos: tuple[str, ...]=('publico',), fecha_emision: str | None=None, datos_vigencia=_CARGAR, avisos_de_limites=_CARGAR) -> str:
    """Public CI documentation."""
    _precargar_tablas()
    if tipo not in TIPOS_INFORME_FASE2:
        raise ValueError(f"tipo tiene que ser {', '.join(TIPOS_INFORME_FASE2)}, no {tipo!r}")
    if corte is not None and (not _fecha_ok(corte)):
        raise ValueError(f'corte tiene que ser una fecha AAAA-MM-DD, no {corte!r}')
    corte_final = corte if corte is not None else registro.get('fecha_corte')
    if corte_final is not None and (not _fecha_ok(corte_final)):
        raise ValueError(f'«fecha_corte» del registro tiene que ser una fecha AAAA-MM-DD, no {corte_final!r}')
    if tipo != 'borrador' and (not corte_final):
        raise ValueError(f'fecha de corte obligatoria para un informe «{tipo}»: pásala con --corte o ponla en «fecha_corte» del registro')
    if datos_vigencia is _CARGAR:
        datos_vigencia = vigencia.instantanea_actual()
    if avisos_de_limites is _CARGAR:
        avisos_de_limites = avisos_de_limites_de_cowork()
    registro, marcas_licencia = proteger_registro_fase2(con, registro, ambitos)
    brechas_reg = registro.get('brechas') or []
    if fecha_emision is None:
        fecha_emision = datetime.date.today().isoformat()
    corte_efectivo = min(corte_final, fecha_emision) if corte_final else corte_final
    try:
        huella = db.huella_contenido(con)
    except sqlite3.Error:
        huella = None
    requisitos: dict[int, RequisitoFase2] = {}
    for b in brechas_reg:
        for c in b.get('citas') or []:
            if not isinstance(c, dict) or not c.get('identificador'):
                continue
            requisitos[id(c)] = _requisito_fase2(con, c, ambitos, huella, datos_vigencia, avisos_de_limites)
    notas_vigencia = _calcular_notas_vigencia_fase2(con, brechas_reg, ambitos, datos_vigencia, avisos_de_limites, corte_efectivo)
    version_registro = registro.get('version') or ''
    version_propuesta = _es_propuesta(version_registro)
    valoracion_vacia = not (registro.get('valoracion_consultor') or '').strip()
    valoracion_con_licencia = any((m.startswith('texto de norma con licencia omitido en valoracion_consultor') for m in marcas_licencia))
    if tipo != 'borrador':
        partes_firmable = []
        if version_propuesta:
            partes_firmable.append(f'la versión del registro «{version_registro}» sigue diciendo «propuesta»: acepta la propuesta y pon la versión definitiva antes de emitir este informe')
        for entrada in notas_vigencia.values():
            if entrada.nota.bloquea:
                partes_firmable.append(f'{entrada.nota.bloquea} (carencia' + ('s: ' if len(entrada.carencias) != 1 else ': ') + ', '.join(entrada.carencias) + ')')
        if tipo == 'final':
            pendientes = [b['id'] for b in brechas_reg if b.get('pendiente_responsable')]
            recepciones_sin_resolver = [b['id'] for b in brechas_reg if _recepcion_sin_detalle(b, corte_efectivo) or _no_recibido_con_evidencia(b, corte_efectivo)]
            recortes_finales = []
            for b in brechas_reg:
                for c in b.get('citas') or []:
                    if not isinstance(c, dict) or not c.get('identificador'):
                        continue
                    req = requisitos[id(c)]
                    if req.recorte:
                        recortes_finales.append(f"{b['id']} (`{req.identificador}`)")
            incoherencias = [b['id'] for b in brechas_reg if _incoherencia_situacion_fase2(b, corte_efectivo)]
            estados_tras_corte = [b['id'] for b in brechas_reg if _estado_tras_corte(b, corte_efectivo) and ultima_revision_a_fecha(b, corte_efectivo) is None]
            cierres_con_recepcion_parcial = [b['id'] for b in brechas_reg if _cerrada_con_recepcion_parcial(b, corte_efectivo)]
            if pendientes:
                partes_firmable.append('quedan marcas «pendiente_responsable» sin resolver en ' + ', '.join(pendientes))
            if recepciones_sin_resolver:
                partes_firmable.append('queda la recepción sin aclarar en ' + ', '.join(recepciones_sin_resolver))
            if cierres_con_recepcion_parcial:
                partes_firmable.append('queda una cerrada con recepción parcial sin confirmar en ' + ', '.join(cierres_con_recepcion_parcial))
            if recortes_finales:
                partes_firmable.append('quedan recortes de literal sin resolver en ' + ', '.join(recortes_finales))
            if incoherencias:
                partes_firmable.append('queda una incoherencia entre la situación y la última revisión sin resolver en ' + ', '.join(incoherencias))
            if estados_tras_corte:
                partes_firmable.append('queda un estado posterior a la fecha de corte sin aclarar en ' + ', '.join(estados_tras_corte))
            if valoracion_vacia:
                partes_firmable.append('falta la valoración del consultor («valoracion_consultor» del registro)')
            elif valoracion_con_licencia:
                partes_firmable.append('la valoración del consultor contiene texto de una norma con licencia (se ha omitido): redáctala sin copiar ese texto')
        if partes_firmable:
            raise InformeFase2Bloqueado(f'el informe {tipo} no sale: ' + '; '.join(partes_firmable) + ' (usa --para-responsable para verlas)')
    L = [f"# {TITULO_INFORME_FASE2.get(tipo, 'Informe de seguimiento — Fase 2')}", '']
    ref = ' · '.join(filter(None, (_cabecera_fase2(x) for x in (registro.get('informe'), registro.get('cliente')))))
    if ref:
        L += [ref, '']
    informe_fase1 = (registro.get('informe_fase1') or '').strip()
    if informe_fase1:
        L += [f'Las actuaciones (letras) y los puntos del requerimiento remiten al informe {_limpia(informe_fase1)}.', '']
    corte_legible = _fecha_legible(corte_final) or '(sin fecha de corte)'
    consultado = ((datos_vigencia or {}).get('consultado') or '')[:10]
    if _fecha_ok(consultado):
        L += [f'Tipo de informe: **{tipo}**.', f'Fecha de corte: {corte_legible}.', f'Fecha de emisión: {_fecha_legible(fecha_emision)}.', f"Versión del registro: {_cabecera_fase2(registro.get('version')) or '(sin versión)'}.", f'Vigencia de las normas citadas comprobada el {_fecha_legible(consultado)} en BOE y EUR-Lex; normas UNE/EN/ISO citadas por referencia.', '']
    else:
        L += [f'Tipo de informe: **{tipo}**.', f'Fecha de corte: {corte_legible}.', f'Fecha de emisión: {_fecha_legible(fecha_emision)}.', f"Versión del registro: {_cabecera_fase2(registro.get('version')) or '(sin versión)'}.", 'Vigencia de las normas citadas: sin consulta de vigencia guardada; normas UNE/EN/ISO citadas por referencia.', '']
    if corte_final and fecha_emision < corte_final:
        L += [f'Documentación recibida hasta el {_fecha_legible(fecha_emision)}.', '']
    if tipo == 'borrador':
        L += ['**BORRADOR — lo revisa y firma Responsable Plaza.**', '']
    else:
        L += ['Revisado y firmado: Responsable Plaza, ICT155 — fecha: ____.', '']
    L += ['## Resumen', '', f'- Carencias: {len(brechas_reg)}. Situación: {_cuenta((_situacion_carencia_fase2(b, corte_efectivo) for b in brechas_reg))}.']
    respuestas = [r for b in brechas_reg if (r := _respuesta_requerimiento_fase2(b, corte_efectivo)) is not None]
    if respuestas:
        L.append(f'- Respuesta al requerimiento: {_cuenta(respuestas)}.')
    L.append('')
    L += _tabla_resumen_por_capa(brechas_reg, corte_efectivo)
    L += ['## Carencias', '']
    for b in brechas_reg:
        estado_posterior = _estado_tras_corte(b, corte_efectivo)
        ultima = ultima_revision_a_fecha(b, corte_efectivo)
        titulo = '' if estado_posterior else b.get('titulo')
        L.append(f"### {_limpia(b['id'])}" + (f' · {_limpia(titulo)}' if titulo else ''))
        L.append('')
        situacion = _situacion_carencia_fase2(b, corte_efectivo)
        L.append(f'- Situación de la carencia: **{situacion}**')
        respuesta = _respuesta_requerimiento_fase2(b, corte_efectivo)
        if respuesta:
            L.append(f'- Respuesta al requerimiento: **{respuesta}**')
        cerrada_fase1 = situacion == 'cerrada en la fase 1'
        cerrada_por_revision = situacion == 'cerrada'
        cerrada_para_vista = cerrada_fase1 or cerrada_por_revision
        L.extend((f'- {etiqueta}: {texto}' for etiqueta, texto in _descripcion_y_peticion_fase2(b, corte_efectivo)))
        L.append('')
        citas_brecha = [c for c in b.get('citas') or [] if isinstance(c, dict) and c.get('identificador')]
        if not citas_brecha:
            L += ['- Observación técnica; no se invoca norma.', '']
        else:
            vistas_vigencia: set[tuple[str, str]] = set()
            for c in citas_brecha:
                req = requisitos[id(c)]
                etiqueta = PAPEL_ETIQUETA.get(req.papel, 'Requisito')
                if req.literal:
                    L += [f'- **{etiqueta}** — {_limpia(req.referencia)}:', '', f'  > {req.literal}', '']
                else:
                    L.append(f'- **{etiqueta}** — {_limpia(req.referencia)}.')
                r_vig = consulta.resolver(con, req.identificador, ambitos, modo=consulta.MODO_LOCALIZAR)
                _, ruta_vista = consulta.partir_identificador(req.identificador)
                clave_vista = (r_vig.obra, ruta_vista.strip())
                if r_vig.obra:
                    entrada = notas_vigencia.get(clave_vista)
                    if entrada and entrada.nota.texto and (clave_vista not in vistas_vigencia):
                        vistas_vigencia.add(clave_vista)
                        L.append(f'- Aviso de vigencia — {_limpia(entrada.norma_legible)}: {_limpia(entrada.nota.texto)}')
            L.append('')
        es_partida = tipo == 'partida'
        ultima = ultima_revision_a_fecha(b, corte_efectivo)
        if ultima:
            documento = ultima.get('documento_aportado') or ''
            documento_mostrado = _tachar_licencia_en_prosa(con, documento, citas_brecha, ambitos) if documento.strip() else documento
            if es_partida:
                L.append(f'- Documento aportado: {_campo_con_punto(_limpia(documento_mostrado), _DOCUMENTO_SIN_ANOTAR)}')
            else:
                doc_txt = (_limpia(documento_mostrado) or _DOCUMENTO_SIN_ANOTAR).rstrip('.')
                L.append(f"- Documento aportado: {doc_txt} (última revisión nº {ultima['numero']}, {_fecha_legible(ultima['fecha'])}).")
                que_falta_txt = ultima.get('que_falta') or ''
                if que_falta_txt.strip():
                    que_falta_mostrado = _tachar_licencia_en_prosa(con, que_falta_txt, citas_brecha, ambitos)
                    L.append(f'- Nota de la última revisión: {_limpia(que_falta_mostrado)}')
                L.append(f"- Número de revisión: {ultima['numero']}.")
        else:
            if _estado_tras_corte(b, corte_efectivo):
                L.append('- Documento aportado: (sin información a la fecha de corte).')
            else:
                aportada = (b.get('evidencia_aportada') or '').strip()
                aportada_mostrada = _tachar_licencia_en_prosa(con, aportada, citas_brecha, ambitos) if aportada else aportada
                L.append(f'- Documento aportado: {_campo_con_punto(_limpia(aportada_mostrada), _DOCUMENTO_SIN_ANOTAR)}')
            if not es_partida and (not cerrada_fase1):
                L.append('- Número de revisión: ninguna todavía.')
        L.append('')
    if tipo != 'partida':
        terceras = [b for b in brechas_reg if (ultima_revision_a_fecha(b, corte_efectivo) or {}).get('numero', 0) >= 3]
        if terceras:
            L.append('## Condiciones de la revisión')
            L.append('')
            for b in terceras:
                n = ultima_revision_a_fecha(b, corte_efectivo)['numero']
                L.append(f"- {_limpia(b['id'])}: esta carencia ha necesitado una revisión nº {n}, fuera del número de revisiones incluido en el alcance contratado.")
            L.append('')
    valoracion = (registro.get('valoracion_consultor') or '').strip()
    if valoracion or tipo in ('borrador', 'final'):
        L += ['## Valoración del consultor', '', valoracion, '']
    return '\n'.join(L).rstrip() + '\n'

def informe_fase2_para_responsable_markdown(con: sqlite3.Connection, registro: dict, *, ambitos: tuple[str, ...]=('publico',), resultados=None, corte: str | None=None, fecha_emision: str | None=None, datos_vigencia=_CARGAR, avisos_de_limites=_CARGAR) -> str:
    """Public CI documentation."""
    _precargar_tablas()
    if corte is not None and (not _fecha_ok(corte)):
        raise ValueError(f'corte tiene que ser una fecha AAAA-MM-DD, no {corte!r}')
    corte_final = corte if corte is not None else registro.get('fecha_corte')
    if corte_final is not None and (not _fecha_ok(corte_final)):
        raise ValueError(f'«fecha_corte» del registro tiene que ser una fecha AAAA-MM-DD, no {corte_final!r}')
    if datos_vigencia is _CARGAR:
        datos_vigencia = vigencia.instantanea_actual()
    if avisos_de_limites is _CARGAR:
        avisos_de_limites = avisos_de_limites_de_cowork()
    corte_efectivo = min(corte_final, fecha_emision) if corte_final and fecha_emision else corte_final
    try:
        huella = db.huella_contenido(con)
    except sqlite3.Error:
        huella = None
    registro, marcas_licencia = proteger_registro_fase2(con, registro, ambitos)
    brechas_reg = registro.get('brechas') or []
    L = ['# Para Responsable — marcas pendientes de la Fase 2', '']
    ref = ' · '.join(filter(None, (_cabecera_fase2(x) for x in (registro.get('informe'), registro.get('cliente')))))
    if ref:
        L += [ref, '']
    hay_algo = bool(marcas_licencia)
    if fecha_emision and corte_final and (fecha_emision < corte_final):
        hay_algo = True
        L += ['## Fecha de emisión anterior al corte', '', f'- Marca: la fecha de emisión ({fecha_emision}) es anterior a la fecha de corte ({corte_final}); confirma que no ha entrado documentación nueva entre esas dos fechas antes de firmar.', '']
    if marcas_licencia:
        L += ['## Texto con licencia omitido', '']
        L += [f'- Marca: {m}' for m in marcas_licencia]
        L.append('')
    version_registro = registro.get('version') or ''
    if _es_propuesta(version_registro):
        hay_algo = True
        L += ['## Bloqueos del informe firmable', '', f'- Marca: la versión del registro «{_cabecera_fase2(version_registro)}» sigue diciendo «propuesta»: acepta la propuesta y pon la versión definitiva antes de emitir un informe firmable (partida, intermedio o final).', '']
    valoracion_vacia = not (registro.get('valoracion_consultor') or '').strip()
    valoracion_con_licencia = any((m.startswith('texto de norma con licencia omitido en valoracion_consultor') for m in marcas_licencia))
    if valoracion_vacia:
        hay_algo = True
        L += ['## Valoración del consultor', '', '- Marca: falta la valoración del consultor («valoracion_consultor» del registro): en partida e intermedio la sección no saldrá; en el final es obligatoria.', '']
    elif valoracion_con_licencia:
        hay_algo = True
        L += ['## Valoración del consultor', '', '- Marca: la valoración del consultor contiene texto de una norma con licencia (se ha omitido); redáctala sin copiar ese texto antes de un informe final.', '']
    notas_vigencia = _calcular_notas_vigencia_fase2(con, brechas_reg, ambitos, datos_vigencia, avisos_de_limites, corte_efectivo)
    avisos_vigencia = [entrada for entrada in notas_vigencia.values() if entrada.nota.para_responsable]
    if avisos_vigencia:
        hay_algo = True
        L += ['## Vigencia: límites o modificaciones por revisar', '']
        for entrada in avisos_vigencia:
            carencias_txt = ', '.join(entrada.carencias)
            L.append(f"- {_limpia(entrada.norma_legible)}, {_limpia(entrada.ruta)}: {_limpia(entrada.nota.para_responsable)} (carencia{('s' if len(entrada.carencias) != 1 else '')}: {carencias_txt})")
        L.append('')
    for b in brechas_reg:
        marcas = [m for m in b.get('pendiente_responsable') or [] if isinstance(m, str) and m.strip()]
        if _recepcion_sin_detalle(b, corte_efectivo):
            er = b.get('estado_requerimiento')
            marcas = marcas + [f'estado_requerimiento «{er}» sin «evidencia_aportada» en el registro: comprueba si de verdad se ha recibido algo antes de firmar.']
        if _evidencia_sin_anotar_fase2(b, corte_efectivo):
            marcas.append(_MARCA_EVIDENCIA_SIN_ANOTAR)
        if _no_recibido_con_evidencia(b, corte_efectivo):
            marcas = marcas + ['estado_requerimiento «no_recibido» con «evidencia_aportada» anotada en el registro: comprueba si de verdad no se ha recibido nada antes de firmar.']
        if _cerrada_con_recepcion_parcial(b, corte_efectivo):
            marcas = marcas + ['cerrada con recepción parcial: confirmar que el cierre no depende de lo que falta.']
        if _cerrada_recepcion_parcial_sin_evidencia(b, corte_efectivo):
            marcas = marcas + ['anotar en evidencia_aportada lo recibido (recepción parcial sin identificar en el registro).']
        posteriores = _revisiones_tras_corte(b, corte_efectivo)
        if _estado_tras_corte(b, corte_efectivo):
            marcas.append('estado posterior al corte; aclarar' if ultima_revision_a_fecha(b, corte_efectivo) is None else 'estado posterior al corte: se usa la revisión anterior o igual al corte')
        if posteriores:
            detalle = ', '.join((f"nº {r.get('numero')} ({r['fecha']})" if r.get('fecha') else f"nº {r.get('numero')} (sin fecha)" for r in sorted(posteriores, key=lambda r: r.get('numero') or 0)))
            marcas = marcas + [f'tiene revisión posterior a la fecha de corte ({corte_efectivo}): {detalle}; estas revisiones no se usan para el estado ni el documento aportado del informe.']
        incoherencia = _incoherencia_situacion_fase2(b, corte_efectivo)
        if incoherencia:
            marcas.append(f'{incoherencia}: comprobarlo antes de firmar')
        recortes = []
        for c in b.get('citas') or []:
            if not isinstance(c, dict) or not c.get('identificador'):
                continue
            req = _requisito_fase2(con, c, ambitos, huella)
            if req.recorte:
                recortes.append(req)
        nota = (b.get('notas') or '').strip()
        if not marcas and (not recortes) and (not nota):
            continue
        hay_algo = True
        L.append(f"### {_limpia(b['id'])}" + (f" · {_limpia(b['titulo'])}" if b.get('titulo') else ''))
        L.append('')
        for m in marcas:
            L.append(f'- Marca: {_limpia(m)}')
        for req in recortes:
            L.append(f'- Recorte: {_limpia(req.referencia)} (`{req.identificador}`): {req.recorte}')
        if nota:
            L.append(f'- Nota interna: {_limpia(nota)}')
        L.append('')
    seccion_sombra = _seccion_sombra(list(getattr(resultados, 'hallazgos', None) or []), getattr(resultados, 'modo', None) or 'apagado')
    if seccion_sombra:
        hay_algo = True
        L += seccion_sombra
    hallazgos_posteriores = list(getattr(resultados, 'hallazgos_posteriores', None) or [])
    if hallazgos_posteriores:
        hay_algo = True
        L.append('## Revisiones posteriores al corte: incidencias (informativo)')
        L.append('')
        for h in hallazgos_posteriores:
            prefijo = f'{h.brecha_id}: ' if h.brecha_id else ''
            L.append(f'- {prefijo}{h.mensaje}')
        L.append('')
    if not hay_algo:
        L += ['Ninguna marca pendiente ni recorte detectado.', '']
    return '\n'.join(L).rstrip() + '\n'
