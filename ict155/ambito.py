"""Public CI documentation."""
from __future__ import annotations
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from . import almacen, afirmaciones, config, consulta, revision
RUTA_REGLAS = config.REPO / 'cowork' / 'reglas_ambito.json'
SENTIDOS = ('aplica', 'excluye')
RE_NIEGA = re.compile('no se aplica|no (?:le |les )?son? aplicable|no result[ao] aplicable|no es de aplicaci|queda(?:n)? exclui|qued[oa] fuera del ambito|no (?:le |les )?obliga|no est[ae](?:n)? obligad|no alcanza')

class ReglasMal(ValueError):
    """Public CI documentation."""

    def __init__(self, errores: list[str], ruta=None):
        self.errores = list(errores)
        n = len(self.errores)
        super().__init__(f"{ruta or RUTA_REGLAS} no es válido ({n} problema{('s' if n != 1 else '')}):\n" + '\n'.join((f'  - {e}' for e in self.errores)))

@dataclass(frozen=True)
class Regla:
    id: str
    norma: tuple[str, ...]
    cuando: tuple[tuple[re.Pattern, ...], ...]
    sentido: str
    ancla: str | None
    fuente: str | None
    literal: str
    contraejemplo: str
    motivo: str
    estado: str

@dataclass(frozen=True)
class Hallazgo:
    regla: str
    identificador: str
    frase: str
    ancla: str | None
    fuente: str | None
    motivo: str

    def dict(self) -> dict:
        return {'regla': self.regla, 'identificador': self.identificador, 'frase': self.frase, 'ancla': self.ancla, 'fuente': self.fuente, 'motivo': self.motivo}

def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())

def _lleva_tildes(expresion: str) -> bool:
    return any((unicodedata.combining(c) for c in unicodedata.normalize('NFD', expresion)))

def _normas_de(etiqueta: str, valor, mios: list[str]) -> tuple[str, ...]:
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list) or not valor or (not all((_texto(v) for v in valor))):
        mios.append(f'{etiqueta}: «norma» tiene que ser un texto o una lista no vacía de textos no vacíos')
        return ()
    return tuple((v.strip() for v in valor))

def _cuando_de(etiqueta: str, cuando, mios: list[str]) -> tuple[tuple[re.Pattern, ...], ...]:
    grupos: list[tuple[re.Pattern, ...]] = []
    if not isinstance(cuando, list) or not cuando:
        mios.append(f'{etiqueta}: «cuando» tiene que ser una lista no vacía de grupos')
        return ()
    for g, grupo in enumerate(cuando, 1):
        if not isinstance(grupo, list) or not grupo:
            mios.append(f'{etiqueta}: «cuando», grupo {g}: tiene que ser una lista no vacía de expresiones')
            continue
        expresiones: list[re.Pattern] = []
        for expr in grupo:
            if not _texto(expr):
                mios.append(f'{etiqueta}: «cuando», grupo {g}: hay una expresión vacía o que no es texto')
                continue
            try:
                rx = re.compile(expr)
            except re.error as e:
                mios.append(f'{etiqueta}: «cuando», grupo {g}: la expresión {expr!r} no compila ({e})')
                continue
            if _lleva_tildes(expr):
                mios.append(f'{etiqueta}: «cuando», grupo {g}: la expresión {expr!r} lleva tildes o eñes y el texto se compara sin ellas: no casaría nunca')
                continue
            if rx.search(''):
                mios.append(f'{etiqueta}: «cuando», grupo {g}: la expresión {expr!r} casa con el texto vacío')
                continue
            expresiones.append(rx)
        grupos.append(tuple(expresiones))
    return tuple(grupos)

def _regla_de(i: int, r, vistos: set[str], errores: list[str]) -> Regla | None:
    if not isinstance(r, dict):
        errores.append(f'regla {i}: no es un objeto')
        return None
    mios: list[str] = []
    ident = r.get('id')
    etiqueta = f'regla «{ident}»' if _texto(ident) else f'regla {i}'
    if not _texto(ident):
        mios.append(f'{etiqueta}: falta «id» (un texto no vacío)')
    elif ident in vistos:
        mios.append(f'{etiqueta}: «id» repetido')
    else:
        vistos.add(ident)
    normas = _normas_de(etiqueta, r.get('norma'), mios)
    cuando = _cuando_de(etiqueta, r.get('cuando'), mios)
    sentido = r.get('sentido', 'aplica')
    if sentido not in SENTIDOS:
        mios.append(f'{etiqueta}: «sentido» tiene que ser uno de {SENTIDOS}')
    ancla = r.get('ancla')
    if ancla is not None and (not _texto(ancla)):
        mios.append(f'{etiqueta}: «ancla» tiene que ser un texto no vacío o null')
    fuente = r.get('fuente')
    if ancla is None and (not _texto(fuente)):
        mios.append(f'{etiqueta}: «ancla» es null: hace falta «fuente» (un texto no vacío) que diga de dónde sale la regla')
    if ancla is not None and fuente is not None:
        mios.append(f'{etiqueta}: «ancla» no es null: «fuente» no hace falta (quítala o pon «ancla»: null)')
    for campo in ('literal', 'contraejemplo', 'motivo'):
        if not _texto(r.get(campo)):
            mios.append(f'{etiqueta}: falta «{campo}» (un texto no vacío)')
    if r.get('estado') is not None and (not isinstance(r.get('estado'), str)):
        mios.append(f'{etiqueta}: «estado» tiene que ser un texto')
    errores.extend(mios)
    if mios:
        return None
    return Regla(ident.strip(), normas, cuando, sentido, ancla.strip() if ancla else None, fuente.strip() if fuente else None, r['literal'].strip(), r['contraejemplo'].strip(), r['motivo'].strip(), (r.get('estado') or '').strip())

def cargar(ruta=None) -> list[Regla]:
    """Public CI documentation."""
    ruta = Path(ruta) if ruta else RUTA_REGLAS
    try:
        datos = json.loads(almacen.leer(ruta).decode('utf-8-sig'))
    except OSError as e:
        raise ReglasMal([f'no se puede leer el fichero: {e.strerror or e}'], ruta) from None
    except (UnicodeDecodeError, ValueError) as e:
        raise ReglasMal([f'no es un JSON en UTF-8 válido ({e})'], ruta) from None
    if not isinstance(datos, dict) or not isinstance(datos.get('reglas'), list) or (not datos['reglas']):
        raise ReglasMal(['falta «reglas»: tiene que ser una lista no vacía de reglas'], ruta)
    errores: list[str] = []
    vistos: set[str] = set()
    reglas = [x for i, r in enumerate(datos['reglas'], 1) if (x := _regla_de(i, r, vistos, errores)) is not None]
    if errores:
        raise ReglasMal(errores, ruta)
    return reglas

def normalizar(texto: str) -> str:
    """Public CI documentation."""
    plano = ''.join((c for c in unicodedata.normalize('NFKD', (texto or '').lower()) if not unicodedata.combining(c)))
    return ' '.join(plano.split())

def _cuando_casa(regla: Regla, texto_normalizado: str) -> bool:
    return all((any((rx.search(texto_normalizado) for rx in grupo)) for grupo in regla.cuando))

def _canonico(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...], memoria: dict[str, tuple[str, str] | None]) -> tuple[str, str] | None:
    """Public CI documentation."""
    if identificador not in memoria:
        r = consulta.resolver(con, identificador, ambitos)
        canonico = None
        if r.estado == consulta.ENCONTRADO and r.obra:
            ruta = consulta.partir_identificador(identificador)[1]
            if ruta and r.version_id is not None:
                ruta = consulta.ruta_efectiva(con, r.version_id, ruta)
            canonico = (r.obra, ruta)
        memoria[identificador] = canonico
    return memoria[identificador]

def _cubre(citada: str, pedida: str) -> bool:
    """Public CI documentation."""
    return citada == pedida or citada.startswith((pedida + '.', pedida + '/'))

def _coincide_norma(con: sqlite3.Connection, ident: str, normas: tuple[str, ...], ambitos: tuple[str, ...], memoria: dict[str, tuple[str, str] | None]) -> bool:
    """Public CI documentation."""
    c = _canonico(con, ident, ambitos, memoria)
    if c is None:
        return False
    obra, ruta = c
    for n in normas:
        cn = _canonico(con, n, ambitos, memoria)
        if cn is None:
            continue
        obra_n, ruta_n = cn
        if obra == obra_n and (not ruta_n or _cubre(ruta, ruta_n)):
            return True
    return False

def _frase_en(frases: list, pos: int, texto: str) -> str:
    """Public CI documentation."""
    for f in frases:
        if f.ini <= pos < f.fin:
            return texto[f.ini:f.fin].strip()
    return ' '.join(texto[max(0, pos - 160):pos + 160].split())

def comprobar(con: sqlite3.Connection, respuesta: str, pregunta: str, ambitos: tuple[str, ...]=('publico',), reglas: list[Regla] | None=None, citas_contexto: tuple[str, ...]=()) -> list[Hallazgo]:
    """Public CI documentation."""
    reglas = cargar() if reglas is None else reglas
    sin_sello = revision.sin_lineas_de_sello(respuesta)
    texto_busqueda = normalizar(pregunta) + '\n' + normalizar(sin_sello)
    idents = revision.identificadores_del_borrador(sin_sello)
    contexto = [c.strip() for c in citas_contexto if isinstance(c, str) and c.strip()]
    if not idents and (not contexto):
        return []
    frases = afirmaciones.frases_del_borrador(sin_sello)
    memoria: dict[str, tuple[str, str] | None] = {}
    vistos: set[tuple[str, int]] = set()
    salida: list[Hallazgo] = []
    frase_contexto = ' '.join(sin_sello.split())
    candidatos = [(ini, ident, _frase_en(frases, ini, sin_sello)) for ini, _fin, ident in idents]
    candidatos += [(None, ident, frase_contexto) for ident in contexto]
    for regla in reglas:
        if not _cuando_casa(regla, texto_busqueda):
            continue
        metodologica = False
        if regla.id == 'ambito_gmp_fabricacion_no_distribuidor':
            plano = normalizar(sin_sello)
            metodologica = bool(re.search('anexo\\s+(?:11|15)[^.;\\n]{0,100}no (?:le |les )?obliga', plano) and re.search('\\bguia\\b|\\bmetodologic', plano))
            for clausula in re.split('[.;\\n]', plano):
                if re.search('\\bdistribuidor\\b', clausula) and re.search('anexo\\s+(?:11|15)|\\bgmp\\b|pic/s', clausula) and re.search('\\bdebe cumplir\\b|\\besta obligado\\b|\\bobliga', clausula) and (not RE_NIEGA.search(clausula)):
                    metodologica = False
                    break
        for _ini, ident, frase in candidatos:
            if not _coincide_norma(con, ident, regla.norma, ambitos, memoria):
                continue
            if regla.id == 'ambito_rd782_no_alcanza_transportista_ni_farmacia_hospitalaria':
                local = normalizar(frase)
                destinatario_obligado = re.search('(?:farmacia|hospital|transportista)[^.;]{0,50}(?:debe|esta obligad)|obliga\\w*\\s+(?:a\\s+)?(?:la\\s+|el\\s+)?(?:farmacia|hospital|transportista)', local)
                sujeto_distribuidor = re.search('(?:para|a) las entidades de distribucion|cubre al distribuidor|no cita entre ellos a la (?:oficina de )?farmacia', local)
                if sujeto_distribuidor and (not destinatario_obligado):
                    continue
            clave = (regla.id, frase)
            if clave in vistos:
                continue
            niega = bool(RE_NIEGA.search(normalizar(frase))) or metodologica
            dispara = not niega if regla.sentido == 'aplica' else niega
            if not dispara:
                continue
            vistos.add(clave)
            salida.append(Hallazgo(regla.id, ident, frase, regla.ancla, regla.fuente, regla.motivo))
    return salida

def a_dict(hallazgos: list[Hallazgo]) -> dict:
    return {'hallazgos': [h.dict() for h in hallazgos], 'n': len(hallazgos)}
PREFIJO_FUERA_DE_AMBITO = 'FUERA DE ÁMBITO'

def _motivo(h: Hallazgo) -> str:
    """Public CI documentation."""
    gobierna = f'`{h.ancla}`' if h.ancla else h.fuente or 'la doctrina firmada'
    return f'{PREFIJO_FUERA_DE_AMBITO}: la cita de `{h.identificador}` no respeta su ámbito de aplicación (ver {gobierna}): {h.motivo}'

def motivos_entrega(con: sqlite3.Connection, respuesta: str, pregunta: str | None) -> list[str]:
    """Public CI documentation."""
    return [_motivo(h) for h in comprobar(con, respuesta, pregunta or '')]

def hallazgos_veredicto(con: sqlite3.Connection, texto: str, citas_contexto: tuple[str, ...]=()) -> list[Hallazgo]:
    """Public CI documentation."""
    return comprobar(con, texto, '', citas_contexto=citas_contexto)
