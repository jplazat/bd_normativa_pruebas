"""Public CI documentation."""
from __future__ import annotations
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from . import almacen, config, consulta, db, interruptores, revision
RUTA_TEMAS = config.REPO / 'cowork' / 'temas_obligatorios.json'
INSTRUCCION = 'Cita cada uno en la respuesta, para aplicarlo o para explicar por qué no aplica; callarlo hace la entrega NO VÁLIDA (INCOMPLETA).'
NO_EXHAUSTIVA = 'La lista no es exhaustiva: que no haya tema no significa que la respuesta esté completa.'

class TemasMal(ValueError):
    """Public CI documentation."""

    def __init__(self, errores: list[str], ruta=None):
        self.errores = list(errores)
        n = len(self.errores)
        super().__init__(f"{ruta or RUTA_TEMAS} no es válido ({n} problema{('s' if n != 1 else '')}):\n" + '\n'.join((f'  - {e}' for e in self.errores)))

@dataclass(frozen=True)
class Obligatorio:
    acepta: tuple[str, ...]
    por_que: str
    acepta_hoja: tuple[str, ...] = ()
    estado_hoja: str = ''
    regla_hoja: str = 'uno'
    por_que_hoja: dict[str, str] = field(default_factory=dict)
    solo_con: str | None = None
    cuando_hoja: tuple[tuple[re.Pattern, ...], ...] = ()
    no_cuando_hoja: tuple[tuple[re.Pattern, ...], ...] = ()
    tope_modo: str | None = None

    @property
    def hoja_activa(self) -> tuple[str, ...]:
        """Public CI documentation."""
        return self.acepta_hoja if self.estado_hoja.strip().lower().startswith('validad') else ()

    def hoja_gatillada(self, pregunta_normalizada: str) -> bool:
        """Public CI documentation."""
        if not self.cuando_hoja:
            return True
        if not _casa(self.cuando_hoja, pregunta_normalizada):
            return False
        return not (self.no_cuando_hoja and _casa(self.no_cuando_hoja, pregunta_normalizada))

    @property
    def solo_con_activo(self) -> bool:
        """Public CI documentation."""
        return not self.estado_hoja or self.estado_hoja.strip().lower().startswith('validad')

@dataclass(frozen=True)
class Tema:
    id: str
    nombre: str
    estado: str
    cuando: tuple[tuple[re.Pattern, ...], ...]
    obligatorios: tuple[Obligatorio, ...]
    control: str | None = None
    cuando_r27: tuple[tuple[re.Pattern, ...], ...] = ()

@dataclass(frozen=True)
class Falta:
    """Public CI documentation."""
    tema: str
    nombre: str
    identificador: str
    por_que: str
    cita_que_no_cubre: str | None = None

    @property
    def motivo(self) -> str:
        base = f'INCOMPLETA: falta citar {self.identificador} ({self.por_que}) [tema «{self.nombre}»]'
        return base if not self.cita_que_no_cubre else base + f': citar {self.cita_que_no_cubre} no lo cubre'

    def dict(self) -> dict:
        d = {'tema': self.tema, 'nombre': self.nombre, 'identificador': self.identificador, 'por_que': self.por_que}
        if self.cita_que_no_cubre:
            d['cita_que_no_cubre'] = self.cita_que_no_cubre
        return d

def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())

def _lleva_tildes(expresion: str) -> bool:
    return any((unicodedata.combining(c) for c in unicodedata.normalize('NFD', expresion)))

def _grupos_de(etiqueta: str, campo: str, valor, mios: list[str], requerido: bool) -> tuple[tuple[re.Pattern, ...], ...]:
    """Public CI documentation."""
    if valor is None and (not requerido):
        return ()
    grupos: list[tuple[re.Pattern, ...]] = []
    if not isinstance(valor, list) or not valor:
        mios.append(f'{etiqueta}: «{campo}» tiene que ser una lista no vacía de grupos')
        return ()
    for g, grupo in enumerate(valor, 1):
        if not isinstance(grupo, list) or not grupo:
            mios.append(f'{etiqueta}: «{campo}», grupo {g}: tiene que ser una lista no vacía de expresiones')
            continue
        expresiones: list[re.Pattern] = []
        for expr in grupo:
            if not _texto(expr):
                mios.append(f'{etiqueta}: «{campo}», grupo {g}: hay una expresión vacía o que no es texto')
                continue
            try:
                rx = re.compile(expr)
            except (re.error, OverflowError) as e:
                mios.append(f'{etiqueta}: «{campo}», grupo {g}: la expresión {expr!r} no compila ({e})')
                continue
            if _lleva_tildes(expr):
                mios.append(f'{etiqueta}: «{campo}», grupo {g}: la expresión {expr!r} lleva tildes o eñes y la pregunta se compara sin ellas (minúsculas y sin tildes): no casaría nunca')
                continue
            if rx.search(''):
                mios.append(f'{etiqueta}: «{campo}», grupo {g}: la expresión {expr!r} casa con el texto vacío, es decir, con cualquier pregunta')
                continue
            expresiones.append(rx)
        grupos.append(tuple(expresiones))
    return tuple(grupos)
_CLAVES_OBLIGATORIO = {'acepta', 'acepta_hoja', 'por_que', 'por_que_hoja', 'estado_hoja', 'regla_hoja', 'solo_con', 'cuando_hoja', 'no_cuando_hoja', 'tope_modo'}

def _tema_de(i: int, t, vistos: set[str], errores: list[str], canonico_hoja=None) -> Tema | None:
    """Public CI documentation."""
    if not isinstance(t, dict):
        errores.append(f'tema {i}: no es un objeto')
        return None
    mios: list[str] = []
    ident = t.get('id')
    etiqueta = f'tema «{ident}»' if _texto(ident) else f'tema {i}'
    if not _texto(ident):
        mios.append(f'{etiqueta}: falta «id» (un texto no vacío)')
    elif ident in vistos:
        mios.append(f'{etiqueta}: «id» repetido')
    else:
        vistos.add(ident)
    if not _texto(t.get('nombre')):
        mios.append(f'{etiqueta}: falta «nombre» (un texto no vacío)')
    if t.get('estado') is not None and (not isinstance(t.get('estado'), str)):
        mios.append(f'{etiqueta}: «estado» tiene que ser un texto')
    control = t.get('control')
    if control is not None and control != 'temas_r27':
        mios.append(f'{etiqueta}: «control» solo puede ser "temas_r27" (o no estar)')
        control = None
    if t.get('tope_modo') is not None:
        mios.append(f'{etiqueta}: «tope_modo» va en cada obligatorio, no en el tema')
    grupos = _grupos_de(etiqueta, 'cuando', t.get('cuando'), mios, requerido=True)
    grupos_r27 = _grupos_de(etiqueta, 'cuando_r27', t.get('cuando_r27'), mios, requerido=False)
    obligatorios: list[Obligatorio] = []
    lista = t.get('obligatorios')
    if not isinstance(lista, list) or not lista:
        mios.append(f'{etiqueta}: «obligatorios» tiene que ser una lista no vacía')
    else:
        for k, o in enumerate(lista, 1):
            if not isinstance(o, dict):
                mios.append(f'{etiqueta}: obligatorio {k}: no es un objeto')
                continue
            acepta = o.get('acepta')
            malos = [] if isinstance(acepta, list) and acepta else ['«acepta» tiene que ser una lista no vacía']
            acepta_pares: list[tuple[str, str]] = []
            for a in acepta if isinstance(acepta, list) else []:
                obra, sep, ruta = a.partition('::') if isinstance(a, str) else ('', '', '')
                if not (obra.strip() and sep and ruta.strip()):
                    malos.append(f'{a!r} no es un identificador «obra::ruta»')
                else:
                    acepta_pares.append((obra.strip(), consulta.ruta_canonica(ruta.strip())))
            if not _texto(o.get('por_que')):
                malos.append('falta «por_que» (un texto no vacío)')

            def _hoja_cubierta(obra: str, ruta: str) -> bool:
                """Public CI documentation."""
                ruta = consulta.ruta_canonica(ruta)
                if any((obra == oa and _cubre(ruta, ra) for oa, ra in acepta_pares)):
                    return True
                candidatos = [(oa, ra) for oa, ra in acepta_pares if _cubre(ruta, ra)]
                if not candidatos or canonico_hoja is None:
                    return False
                return any(((ch := canonico_hoja(f'{obra}::{ra}')) is not None and (ca := canonico_hoja(f'{oa}::{ra}')) is not None and (ch[0] == ca[0]) for oa, ra in candidatos))

            def _clave_hoja(k) -> str:
                """Public CI documentation."""
                if not isinstance(k, str):
                    return k
                obra, sep, ruta = k.partition('::')
                return f'{obra.strip()}::{ruta.strip()}' if sep else k
            acepta_hoja_raw = o.get('acepta_hoja')
            acepta_hoja: list[str] = []
            if acepta_hoja_raw is not None:
                if not (isinstance(acepta_hoja_raw, list) and acepta_hoja_raw):
                    malos.append('«acepta_hoja» tiene que ser una lista no vacía si se da')
                else:
                    for h in acepta_hoja_raw:
                        obra, sep, ruta = h.partition('::') if isinstance(h, str) else ('', '', '')
                        if not (obra.strip() and sep and ruta.strip()):
                            malos.append(f'{h!r} de «acepta_hoja» no es un identificador «obra::ruta»')
                        elif not _hoja_cubierta(obra.strip(), ruta.strip()):
                            malos.append(f'{h!r} de «acepta_hoja» tiene que ser igual o estar por debajo de alguno de «acepta»')
                        else:
                            acepta_hoja.append(f'{obra.strip()}::{ruta.strip()}')
            estado_hoja_raw = o.get('estado_hoja')
            if estado_hoja_raw is not None and (not isinstance(estado_hoja_raw, str)):
                malos.append('«estado_hoja» tiene que ser un texto si se da')
            regla_hoja_raw = o.get('regla_hoja')
            if regla_hoja_raw is not None and regla_hoja_raw not in ('uno', 'todos'):
                malos.append('«regla_hoja» solo puede ser "uno" o "todos" (o no estar)')
            regla_hoja = regla_hoja_raw if regla_hoja_raw in ('uno', 'todos') else 'uno'
            if regla_hoja == 'todos' and (not acepta_hoja):
                malos.append('«regla_hoja»: "todos" no tiene sentido sin «acepta_hoja»')
            por_que_hoja_raw = o.get('por_que_hoja')
            por_que_hoja: dict[str, str] = {}
            if por_que_hoja_raw is not None:
                if not (isinstance(por_que_hoja_raw, dict) and por_que_hoja_raw):
                    malos.append('«por_que_hoja» tiene que ser un objeto no vacío si se da')
                elif not acepta_hoja:
                    malos.append('«por_que_hoja» no tiene sentido sin «acepta_hoja»')
                else:
                    for ph_k, ph_v in por_que_hoja_raw.items():
                        if _clave_hoja(ph_k) not in acepta_hoja:
                            malos.append(f'«por_que_hoja»: {ph_k!r} no está en «acepta_hoja»')
                        elif not _texto(ph_v):
                            malos.append(f'«por_que_hoja»: {ph_k!r} tiene que llevar un texto no vacío')
                    if regla_hoja == 'todos':
                        claves = {_clave_hoja(k) for k in por_que_hoja_raw}
                        faltan_pq = [h for h in acepta_hoja if h not in claves]
                        if faltan_pq:
                            malos.append(f"""«por_que_hoja»: con «regla_hoja»: "todos" hace falta un texto para cada «acepta_hoja» (falta: {', '.join(faltan_pq)})""")
            elif regla_hoja == 'todos' and len(acepta_hoja) > 1:
                malos.append('«regla_hoja»: "todos" con más de una «acepta_hoja» necesita «por_que_hoja» con el texto de cada una')
            solo_con_raw = o.get('solo_con')
            if solo_con_raw is not None and solo_con_raw != 'cubre_estricto':
                malos.append('«solo_con» solo puede ser "cubre_estricto" (o no estar)')
            solo_con = solo_con_raw if solo_con_raw == 'cubre_estricto' else None
            if solo_con and acepta_hoja:
                malos.append('«solo_con» y «acepta_hoja» no se combinan: no hay código que sepa qué hacer con los dos')
            cuando_hoja_raw = o.get('cuando_hoja')
            cuando_hoja_errores: list[str] = []
            cuando_hoja_grupos = _grupos_de(f'{etiqueta}: obligatorio {k}', 'cuando_hoja', cuando_hoja_raw, cuando_hoja_errores, requerido=False)
            malos.extend(cuando_hoja_errores)
            if cuando_hoja_raw is not None and (not acepta_hoja) and (not solo_con):
                malos.append('«cuando_hoja» no tiene sentido sin «acepta_hoja» ni «solo_con»: no hay ninguna exigencia que gatillar')
            no_cuando_hoja_raw = o.get('no_cuando_hoja')
            no_cuando_hoja_errores: list[str] = []
            no_cuando_hoja_grupos = _grupos_de(f'{etiqueta}: obligatorio {k}', 'no_cuando_hoja', no_cuando_hoja_raw, no_cuando_hoja_errores, requerido=False)
            malos.extend(no_cuando_hoja_errores)
            if no_cuando_hoja_raw is not None and cuando_hoja_raw is None:
                malos.append('«no_cuando_hoja» no tiene sentido sin «cuando_hoja»: no hay nada que exceptuar')
            tope_modo_raw = o.get('tope_modo')
            if tope_modo_raw is not None and tope_modo_raw not in ('sombra', 'apagado'):
                malos.append('«tope_modo» solo puede ser "sombra" o "apagado" (o no estar)')
            elif tope_modo_raw is not None and (not acepta_hoja) and (not solo_con):
                malos.append('«tope_modo» no tiene sentido sin «acepta_hoja» ni «solo_con»: no hay ninguna exigencia de «cubre_estricto» que topar')
            tope_modo = tope_modo_raw if tope_modo_raw in ('sombra', 'apagado') else None
            desconocidas = sorted((k2 for k2 in o if not k2.startswith('_') and k2 not in _CLAVES_OBLIGATORIO))
            if desconocidas:
                malos.append(f"clave{('s' if len(desconocidas) != 1 else '')} desconocida{('s' if len(desconocidas) != 1 else '')}: " + ', '.join((repr(k2) for k2 in desconocidas)))
            if malos:
                mios.append(f'{etiqueta}: obligatorio {k}: ' + '; '.join(malos))
                continue
            estado_hoja = estado_hoja_raw.strip() if isinstance(estado_hoja_raw, str) else ''
            por_que_hoja = {_clave_hoja(k2): v2.strip() for k2, v2 in por_que_hoja_raw.items()} if por_que_hoja_raw else {}
            obligatorios.append(Obligatorio(tuple((a.strip() for a in acepta)), o['por_que'].strip(), tuple(acepta_hoja), estado_hoja, regla_hoja, por_que_hoja, solo_con, cuando_hoja_grupos, no_cuando_hoja_grupos, tope_modo))
    errores.extend(mios)
    if mios:
        return None
    return Tema(ident.strip(), t['nombre'].strip(), (t.get('estado') or '').strip(), tuple(grupos), tuple(obligatorios), control, grupos_r27)

def cargar(ruta=None) -> list[Tema]:
    """Public CI documentation."""
    ruta = Path(ruta) if ruta else RUTA_TEMAS
    try:
        datos = json.loads(almacen.leer(ruta).decode('utf-8-sig'))
    except OSError as e:
        raise TemasMal([f'no se puede leer el fichero: {e.strerror or e}'], ruta) from None
    except (UnicodeDecodeError, ValueError) as e:
        raise TemasMal([f'no es un JSON en UTF-8 válido ({e})'], ruta) from None
    errores: list[str] = []
    if not isinstance(datos, dict) or not isinstance(datos.get('temas'), list) or (not datos['temas']):
        raise TemasMal(['falta «temas»: tiene que ser una lista no vacía de temas'], ruta)
    _con: list[sqlite3.Connection | None] = [None]
    _memoria: dict[str, tuple[str, str] | None] = {}
    _intentado = [False]

    def _canonico_hoja(ident: str) -> tuple[str, str] | None:
        if not _intentado[0]:
            _intentado[0] = True
            try:
                _con[0] = db.conectar(solo_lectura=True)
            except Exception:
                _con[0] = None
        if _con[0] is None:
            return None
        try:
            return _canonico(_con[0], ident, ('publico',), _memoria)
        except Exception:
            return None
    vistos: set[str] = set()
    try:
        temas = [t for i, x in enumerate(datos['temas'], 1) if (t := _tema_de(i, x, vistos, errores, _canonico_hoja)) is not None]
    finally:
        if _con[0] is not None:
            _con[0].close()
    if errores:
        raise TemasMal(errores, ruta)
    return temas

def normalizar(pregunta: str) -> str:
    """Public CI documentation."""
    plano = ''.join((c for c in unicodedata.normalize('NFKD', (pregunta or '').lower()) if not unicodedata.combining(c)))
    return ' '.join(plano.split())

def _casa(grupos: tuple[tuple[re.Pattern, ...], ...], p: str) -> bool:
    """Public CI documentation."""
    return bool(grupos) and all((any((rx.search(p) for rx in grupo)) for grupo in grupos))

def _deteccion(pregunta: str, temas: list[Tema]) -> tuple[list[Tema], list[Tema]]:
    """Public CI documentation."""
    if not any((t.control == 'temas_r27' or t.cuando_r27 for t in temas)):
        return ([t for t in temas if _casa(t.cuando, normalizar(pregunta))], [])
    p = normalizar(pregunta)
    modo = interruptores.modo('temas_r27')
    detectados: list[Tema] = []
    para_sombra: list[Tema] = []
    for t in temas:
        base = _casa(t.cuando, p)
        if t.control == 'temas_r27':
            if base and modo == 'bloquea':
                detectados.append(t)
            elif base and modo == 'sombra':
                para_sombra.append(t)
            continue
        if base:
            detectados.append(t)
        elif t.cuando_r27 and _casa(t.cuando_r27, p):
            if modo == 'bloquea':
                detectados.append(t)
            elif modo == 'sombra':
                para_sombra.append(t)
    return (detectados, para_sombra)

def temas_de(pregunta: str, temas: list[Tema] | None=None) -> list[Tema]:
    """Public CI documentation."""
    temas = cargar() if temas is None else temas
    detectados, _ = _deteccion(pregunta, temas)
    return detectados

def _canonico(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...], memoria: dict[str, tuple[str, str] | None]) -> tuple[str, str] | None:
    """Public CI documentation."""
    if identificador not in memoria:
        r = consulta.resolver(con, identificador, ambitos)
        canonico = None
        if r.estado == consulta.ENCONTRADO and r.obra and (r.version_id is not None):
            ruta = consulta.partir_identificador(identificador)[1]
            ruta = consulta.ruta_efectiva(con, r.version_id, ruta) if ruta else ''
            if ruta:
                canonico = (r.obra, ruta)
        memoria[identificador] = canonico
    return memoria[identificador]

def _cubre(citada: str, pedida: str) -> bool:
    """Public CI documentation."""
    return citada == pedida or citada.startswith((pedida + '.', pedida + '/'))
_ORDEN_MODO = {'apagado': 0, 'sombra': 1, 'bloquea': 2}

def _modo_para(o: Obligatorio, modo_global: str) -> str:
    """Public CI documentation."""
    if o.tope_modo is None:
        return modo_global
    return o.tope_modo if _ORDEN_MODO[o.tope_modo] < _ORDEN_MODO[modo_global] else modo_global

def _hoja_pendientes(con: sqlite3.Connection, o: Obligatorio, citas: set[tuple[str, str]], ambitos: tuple[str, ...], memoria: dict[str, tuple[str, str] | None]) -> list[str]:
    """Public CI documentation."""
    cubiertos = set()
    for h in o.hoja_activa:
        c = _canonico(con, h, ambitos, memoria)
        if c is not None and any((obra == c[0] and (_cubre(ruta, c[1]) or _cubre(c[1], ruta)) for obra, ruta in citas)):
            cubiertos.add(h)
    if o.regla_hoja == 'todos':
        return [h for h in o.hoja_activa if h not in cubiertos]
    return [] if cubiertos else [o.hoja_activa[0]]

def _cita_que_no_cubre(con: sqlite3.Connection, ident: str, cubiertas: list[tuple[str, str]], ambitos: tuple[str, ...], memoria: dict[str, tuple[str, str] | None]) -> str | None:
    """Public CI documentation."""
    c = _canonico(con, ident, ambitos, memoria)
    if c is None:
        return None
    mismas_obra = sorted((f'{obra}::{ruta}' for obra, ruta in cubiertas if obra == c[0]))
    return ', '.join(mismas_obra) if mismas_obra else None

def citados(con: sqlite3.Connection, respuesta: str, ambitos: tuple[str, ...]=('publico',), memoria: dict[str, tuple[str, str] | None] | None=None) -> set[tuple[str, str]]:
    """Public CI documentation."""
    memoria = {} if memoria is None else memoria
    sin_sello = revision.sin_lineas_de_sello(respuesta)
    return {c for _a, _b, ident in revision.identificadores_del_borrador(sin_sello) if (c := _canonico(con, ident, ambitos, memoria)) is not None}

def _condicion_r27_pendiente(o: Obligatorio, pregunta: str) -> bool:
    """Public CI documentation."""
    p = normalizar(pregunta)
    if 'RD 1109/1991::art.5.1' in o.acepta:
        return not re.search('\\bultracongelad', p) or bool(re.search('\\b(?:sin saber|no se sabe|desconoc\\w*)[^.;?]{0,70}ultracongelad|\\b(?:no son|no es|si son|si es) ultracongelad', p))
    if 'Ley 32/2014::art.22.2.d' in o.acepta:
        excede = re.search('\\bsuper\\w*[^.;?]{0,70}errores maximos permitidos', p)
        sabe = re.search('\\bsabiendo\\b|\\ba sabiendas\\b|\\bconociendo\\b|\\bsabe\\b', p)
        niega = re.search('\\b(?:sin saber|no sabe|no se sabe|desconoc\\w*|si supera)\\b', p)
        return not (excede and sabe and (not niega))
    return False

def faltan(con: sqlite3.Connection, respuesta: str, pregunta: str, ambitos: tuple[str, ...]=('publico',), temas: list[Tema] | None=None) -> list[Falta]:
    """Public CI documentation."""
    temas = cargar() if temas is None else temas
    detectados, para_sombra = _deteccion(pregunta, temas)
    confirmados = []
    for t in detectados:
        pendientes = tuple((o for o in t.obligatorios if t.control == 'temas_r27' and _condicion_r27_pendiente(o, pregunta)))
        if pendientes:
            para_sombra.append(replace(t, obligatorios=pendientes))
            confirmados.append(replace(t, obligatorios=tuple((o for o in t.obligatorios if o not in pendientes))))
        else:
            confirmados.append(t)
    detectados = confirmados
    if not detectados and (not para_sombra):
        return []
    memoria: dict[str, tuple[str, str] | None] = {}
    citas = citados(con, respuesta, ambitos, memoria)
    modo_estricto = interruptores.modo('cubre_estricto')
    p = normalizar(pregunta)
    salida: list[Falta] = []
    for t in detectados:
        for o in t.obligatorios:
            modo_o = _modo_para(o, modo_estricto)
            if o.solo_con == 'cubre_estricto':
                if modo_o == 'apagado' or not o.hoja_gatillada(p) or (not o.solo_con_activo):
                    continue
                pedidos = [c for a in o.acepta if (c := _canonico(con, a, ambitos, memoria)) is not None]
                cubiertas = [(obra, ruta) for obra, ruta in citas if any((obra == op and (_cubre(ruta, rp) or _cubre(rp, ruta)) for op, rp in pedidos))]
                if cubiertas:
                    continue
                if modo_o == 'sombra':
                    detalle = {'tema': t.id, 'obligatorio': o.acepta[0]}
                    if o.tope_modo is not None and modo_o != modo_estricto:
                        detalle['tope'] = o.tope_modo
                    interruptores.anotar_sombra('cubre_estricto', detalle)
                else:
                    salida.append(Falta(t.id, t.nombre, o.acepta[0], o.por_que))
                continue
            pedidos = [c for a in o.acepta if (c := _canonico(con, a, ambitos, memoria)) is not None]
            cubiertas = [(obra, ruta) for obra, ruta in citas if any((obra == op and _cubre(ruta, rp) for op, rp in pedidos))]
            if not cubiertas:
                salida.append(Falta(t.id, t.nombre, o.acepta[0], o.por_que))
                continue
            hoja_gatillada = bool(o.hoja_activa) and o.hoja_gatillada(p)
            if not hoja_gatillada or modo_o != 'bloquea':
                if hoja_gatillada and modo_o == 'sombra':
                    pendientes = _hoja_pendientes(con, o, citas, ambitos, memoria)
                    for ident in pendientes:
                        citado = _cita_que_no_cubre(con, ident, cubiertas, ambitos, memoria)
                        detalle = {'tema': t.id, 'obligatorio': ident, 'citado': citado or ''}
                        if o.tope_modo is not None and modo_o != modo_estricto:
                            detalle['tope'] = o.tope_modo
                        interruptores.anotar_sombra('cubre_estricto', detalle)
                continue
            pendientes = _hoja_pendientes(con, o, citas, ambitos, memoria)
            if not pendientes:
                continue
            for ident in pendientes:
                citado = _cita_que_no_cubre(con, ident, cubiertas, ambitos, memoria)
                salida.append(Falta(t.id, t.nombre, ident, o.por_que_hoja.get(ident, o.por_que), cita_que_no_cubre=citado))
    for t in para_sombra:
        for o in t.obligatorios:
            if o.solo_con == 'cubre_estricto':
                if _modo_para(o, modo_estricto) == 'apagado' or not o.hoja_gatillada(p) or (not o.solo_con_activo):
                    continue
            pedidos = [c for a in o.acepta if (c := _canonico(con, a, ambitos, memoria)) is not None]
            cubiertas = [(obra, ruta) for obra, ruta in citas if any((obra == op and _cubre(ruta, rp) for op, rp in pedidos))]
            if not cubiertas:
                interruptores.anotar_sombra('temas_r27', {'tema': t.id, 'obligatorio': o.acepta[0]})
    return salida

def validar_contra_la_base(con: sqlite3.Connection, temas: list[Tema] | None=None, ambitos: tuple[str, ...]=('publico',)) -> list[str]:
    """Public CI documentation."""
    temas = cargar() if temas is None else temas
    malos: list[str] = []
    for t in temas:
        for o in t.obligatorios:
            for a in (*o.acepta, *o.acepta_hoja):
                r = consulta.resolver(con, a, ambitos)
                if r.estado != consulta.ENCONTRADO:
                    malos.append(f'{a} [{t.id}]: {r.estado}')
    return malos

def _modo_cubre_estricto() -> str:
    """Public CI documentation."""
    try:
        return interruptores.modo('cubre_estricto')
    except interruptores.ErrorDeControles:
        return 'apagado'

def a_dict(temas: list[Tema], pregunta: str | None=None) -> dict:
    """Public CI documentation."""
    modo_global = _modo_cubre_estricto()
    p = normalizar(pregunta) if pregunta is not None else None

    def _hoja_ok(o: Obligatorio) -> bool:
        return p is None or o.hoja_gatillada(p)

    def _visible(o: Obligatorio) -> bool:
        if not o.solo_con:
            return True
        return _modo_para(o, modo_global) == 'bloquea' and _hoja_ok(o) and o.solo_con_activo

    def _obligatorio(o: Obligatorio) -> dict:
        d = {'identificador': o.acepta[0], 'acepta': list(o.acepta), 'por_que': o.por_que}
        if _modo_para(o, modo_global) == 'bloquea' and o.hoja_activa and _hoja_ok(o):
            d['hoja_bloquea'] = list(o.hoja_activa)
            if o.regla_hoja == 'todos':
                d['hoja_bloquea_regla'] = 'todos'
                d['hoja_bloquea_por_que'] = {h: o.por_que_hoja.get(h, o.por_que) for h in o.hoja_activa}
        return d
    temas_out: list[dict] = []
    n_obligatorios = 0
    for t in temas:
        obligatorios = [_obligatorio(o) for o in t.obligatorios if _visible(o)]
        n_obligatorios += len(obligatorios)
        temas_out.append({'id': t.id, 'nombre': t.nombre, 'estado': t.estado, 'obligatorios': obligatorios})
    return {'temas': temas_out, 'n_temas': len(temas), 'n_obligatorios': n_obligatorios}

def texto(temas: list[Tema], pregunta: str | None=None) -> str:
    """Public CI documentation."""
    if not temas:
        return 'La pregunta no cae en ningún tema de la lista de lo obligatorio. ' + NO_EXHAUSTIVA
    modo_global = _modo_cubre_estricto()
    p = normalizar(pregunta) if pregunta is not None else None

    def _hoja_ok(o: Obligatorio) -> bool:
        return p is None or o.hoja_gatillada(p)
    n = len(temas)
    out = [f"La pregunta cae en {n} {('tema' if n == 1 else 'temas')} de la lista de lo obligatorio. {INSTRUCCION} {NO_EXHAUSTIVA}"]
    for t in temas:
        mostrados = [o for o in t.obligatorios if not o.solo_con or (_modo_para(o, modo_global) == 'bloquea' and _hoja_ok(o) and o.solo_con_activo)]
        if not mostrados:
            continue
        out += ['', f'TEMA «{t.nombre}» [{t.id}]']
        for o in mostrados:
            bloquea_o = _modo_para(o, modo_global) == 'bloquea'
            regla_todos_activa = bool(bloquea_o and o.hoja_activa and _hoja_ok(o) and (o.regla_hoja == 'todos'))
            otros = f" (también vale: {', '.join(o.acepta[1:])})" if len(o.acepta) > 1 and (not regla_todos_activa) else ''
            linea = f'  - {o.acepta[0]}{otros} — {o.por_que}'
            if bloquea_o and o.hoja_activa and _hoja_ok(o):
                if o.regla_hoja == 'todos':
                    alternativa = 'o el artículo entero'
                    if len({h.partition('::')[0] for h in o.hoja_activa}) > 1:
                        articulos = list(dict.fromkeys((f"{obra}::art.{ruta.split('.')[1]}" for obra, _, ruta in (h.partition('::') for h in o.hoja_activa) if ruta.startswith('art.'))))
                        alternativa = f"o los artículos enteros {' y '.join(articulos)}; cada artículo entero cubre solo las hojas de su propia obra"
                    linea += f" [en «bloquea» hay que citar TODOS: {', '.join(o.hoja_activa)} ({alternativa})]"
                else:
                    linea += f" [en «bloquea» solo cubre citar {', '.join(o.hoja_activa)}, o el artículo entero]"
            out.append(linea)
            if regla_todos_activa:
                for h in o.hoja_activa:
                    out.append(f'      · {h} — {o.por_que_hoja.get(h, o.por_que)}')
    return '\n'.join(out)
