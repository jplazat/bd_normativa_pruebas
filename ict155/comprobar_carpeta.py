"""Public CI documentation."""
from __future__ import annotations
import difflib
import json
import re
import sqlite3
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from . import almacen, ambito, completitud, config, db, entrega, historial_boe, interruptores, relacionados, revision, sucesion, vigencia
from . import revision_independiente as ri
LISTO = 'LISTO PARA ENVIAR'
NO_LISTO = 'NO LISTO'
ANTES, DESPUES = ('antes', 'despues')
MOMENTOS = (ANTES, DESPUES)
EN_EL_REGISTRO = {True: 'LISTO', False: 'NO_LISTO'}
CONTRATO = 'preguntas.json'
PREFIJO_ENVIAR = 'ENVIAR_'
ARCHIVO_ENTREGAS = config.BIBLIOTECA / '03_Proyecto_BD_Normativa' / 'archivo_entregas'
PRIMERA_LINEA_LISTO = '{listo}: {n} correos verificados; las versiones para enviar solo pierden identificadores y marcas'
SIN_ENVIAR = 'se enviará tal cual el verificado: quita tú la línea de sello'
AVISO_MD_SUELTO = 'está en la carpeta pero no en preguntas.json (los índices y notas no van en .md)'
NO_ARCHIVADA = 'no archivada o distinta'
MAXIMO_DIFERENCIAS_ENSENADAS = 40
CONTEXTO = 6
MAXIMO_TROZO = 300
MAXIMO_ALINEACION = 4000000

class CarpetaIlegible(Exception):
    """Public CI documentation."""

class ContratoMalo(Exception):
    """Public CI documentation."""

def _mensaje_tabla_rota(e: Exception) -> str:
    if isinstance(e, almacen.ErrorDeAlmacen):
        return str(e)
    if isinstance(e, interruptores.ErrorDeControles):
        return f'{e}. Restaura `cowork/controles.json` desde git: la palanca no sirve en este caso.'
    return f'{e}. Restaura la tabla desde git o baja el control con `D:\\Proyectos\\r27\\TODO_A_SOMBRA.cmd`.'
ID, MARCA, SUELTO, NEXO, DURA = ('id', 'marca', 'suelto', 'nexo', 'dura')
RE_PIEZA = re.compile('`[^`\\n]*`|\\(\\s*opini[óo]n\\s*\\)|\\d+(?:[.,]\\d+)*|\\w+|[^\\w\\s]', re.IGNORECASE)
RE_MARCA = re.compile('\\(\\s*opini[óo]n\\s*\\)', re.IGNORECASE)
SIGNOS_SUELTOS = frozenset('(),;·.')

@dataclass(frozen=True)
class Pieza:
    texto: str
    ini: int
    fin: int
    clase: str

def _normal(texto: str) -> str:
    """Public CI documentation."""
    return unicodedata.normalize('NFC', texto.replace('\r\n', '\n').replace('\r', '\n'))

def _clase(p: str) -> str:
    if p.startswith('`'):
        return ID
    if RE_MARCA.fullmatch(p):
        return MARCA
    if p in SIGNOS_SUELTOS:
        return SUELTO
    if p == 'y':
        return NEXO
    return DURA

def piezas(texto: str) -> list[Pieza]:
    """Public CI documentation."""
    return [Pieza(m.group(0), m.start(), m.end(), _clase(m.group(0))) for m in RE_PIEZA.finditer(texto)]

def _tramo_valido(tramo: list[Pieza]) -> bool:
    """Public CI documentation."""
    if not tramo or any((p.clase == DURA for p in tramo)):
        return False
    if not any((p.clase in (ID, MARCA) for p in tramo)):
        return False
    for k, p in enumerate(tramo):
        if p.clase != NEXO:
            continue
        antes = next((q for q in reversed(tramo[:k]) if q.clase != SUELTO), None)
        despues = next((q for q in tramo[k + 1:] if q.clase != SUELTO), None)
        if antes is None or despues is None or antes.clase != ID or (despues.clase != ID):
            return False
    return True

def se_deriva(a: list[Pieza], b: list[Pieza]) -> bool:
    """Public CI documentation."""
    ta, tb = ([p.texto for p in a], [p.texto for p in b])
    n, m = (len(a), len(b))
    vistos: set[tuple[int, int]] = set()
    pila = [(0, 0)]
    while pila:
        i, j = pila.pop()
        if (i, j) in vistos:
            continue
        vistos.add((i, j))
        if j == m:
            if i == n or _tramo_valido(a[i:]):
                return True
            continue
        k = i
        while k < n:
            if (k == i or _tramo_valido(a[i:k])) and ta[k] == tb[j]:
                pila.append((k + 1, j + 1))
            if a[k].clase == DURA:
                break
            k += 1
    return False

@dataclass
class Diferencia:
    """Public CI documentation."""
    tipo: str
    antes: str
    despues: str
    contexto_antes: str
    contexto_despues: str

    def texto(self) -> str:
        if self.tipo == 'quitado':
            que = f'se quitó «{self.antes}»'
        elif self.tipo == 'añadido':
            que = f'se añadió «{self.despues}»'
        else:
            que = f'se cambió «{self.antes}» por «{self.despues}»'
        return f'{que}. Antes: «{self.contexto_antes}». Después: «{self.contexto_despues}»'

def _recortar(s: str, maximo: int=MAXIMO_TROZO) -> str:
    s = re.sub('\\s*\\n\\s*', ' ¶ ', s.strip())
    s = re.sub('[ \\t]{2,}', ' ', s)
    return s if len(s) <= maximo else s[:maximo].rstrip() + f'… (+{len(s) - maximo} caracteres)'

def _trozo(s: str, ps: list[Pieza], i1: int, i2: int) -> str:
    """Public CI documentation."""
    return s[ps[i1].ini:ps[i2 - 1].fin] if i2 > i1 else ''

def _con_contexto(s: str, ps: list[Pieza], i1: int, i2: int) -> str:
    ini, fin = (max(0, i1 - CONTEXTO), min(len(ps), i2 + CONTEXTO))
    if fin <= ini:
        return ''
    return ('…' if ini > 0 else '') + _recortar(_trozo(s, ps, ini, fin), MAXIMO_TROZO + 160) + ('…' if fin < len(ps) else '')

def _sin_lo_borrable_de_los_bordes(ps: list[Pieza], i1: int, i2: int) -> tuple[int, int]:
    """Public CI documentation."""
    duras = [k for k in range(i1, i2) if ps[k].clase == DURA]
    if not duras:
        return (i1, i2)
    ini, fin = (duras[0], duras[-1] + 1)
    if not any((p.clase in (ID, MARCA) for p in ps[i1:ini])):
        ini = i1
    if not any((p.clase in (ID, MARCA) for p in ps[fin:i2])):
        fin = i2
    return (ini, fin)

def diferencias(verificado: str, enviado: str) -> list[Diferencia]:
    """Public CI documentation."""
    sa, sb = (_normal(verificado), _normal(enviado))
    a, b = (piezas(sa), piezas(sb))
    if se_deriva(a, b):
        return []
    ta, tb = ([p.texto for p in a], [p.texto for p in b])
    pre = suf = 0
    if len(ta) * len(tb) > MAXIMO_ALINEACION:
        while pre < min(len(ta), len(tb)) and ta[pre] == tb[pre]:
            pre += 1
        while suf < min(len(ta), len(tb)) - pre and ta[-1 - suf] == tb[-1 - suf]:
            suf += 1
    medio_a, medio_b = (ta[pre:len(ta) - suf], tb[pre:len(tb) - suf])
    out: list[Diferencia] = []
    if len(medio_a) * len(medio_b) > MAXIMO_ALINEACION:
        i1, i2, j1, j2 = (pre, len(ta) - suf, pre, len(tb) - suf)
        return [Diferencia('añadido' if i2 <= i1 else 'quitado' if j2 <= j1 else 'cambiado', _recortar(_trozo(sa, a, i1, min(i2, i1 + 40))), _recortar(_trozo(sb, b, j1, min(j2, j1 + 40))), _con_contexto(sa, a, i1, min(i1 + 1, len(a))), _con_contexto(sb, b, j1, min(j1 + 1, len(b))))]
    sm = difflib.SequenceMatcher(a=medio_a, b=medio_b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            continue
        i1, i2, j1, j2 = (i1 + pre, i2 + pre, j1 + pre, j2 + pre)
        if op == 'delete' and _tramo_valido(a[i1:i2]):
            continue
        solo_borrable = i2 > i1 and all((p.clase != DURA for p in a[i1:i2]))
        if op == 'insert' or (op == 'replace' and solo_borrable):
            tipo = 'añadido'
        elif op == 'delete':
            tipo = 'quitado'
        else:
            tipo = 'cambiado'
        c1, c2 = _sin_lo_borrable_de_los_bordes(a, i1, i2) if tipo != 'añadido' else (i1, i2)
        antes = _recortar(_trozo(sa, a, c1, c2)) if tipo != 'añadido' else ''
        despues = _recortar(_trozo(sb, b, j1, j2)) if tipo != 'quitado' else ''
        out.append(Diferencia(tipo, antes, despues, _con_contexto(sa, a, i1, i2), _con_contexto(sb, b, j1, j2)))
    if not out:
        primera = next((k for k in range(min(len(a), len(b))) if ta[k] != tb[k]), min(len(a), len(b)))
        out.append(Diferencia('cambiado', _recortar(_trozo(sa, a, primera, min(primera + 3, len(a)))), _recortar(_trozo(sb, b, primera, min(primera + 3, len(b)))), _con_contexto(sa, a, primera, min(primera + 1, len(a))), _con_contexto(sb, b, primera, min(primera + 1, len(b)))))
    return out

@dataclass
class Problema:
    fichero: str
    texto: str

    def dict(self) -> dict:
        return {'fichero': self.fichero, 'texto': self.texto}

@dataclass
class Resultado:
    carpeta: str = ''
    momento: str = ANTES
    correos: list[str] = field(default_factory=list)
    con_envio: list[str] = field(default_factory=list)
    sin_envio: list[str] = field(default_factory=list)
    veredictos: dict[str, str] = field(default_factory=dict)
    problemas: list[Problema] = field(default_factory=list)
    avisos: list[Problema] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    archivo: str | None = None
    archivada: bool = False
    revision_pedida: bool = False
    pasadas: int = 0
    objeciones: int = 0
    revisiones_no_hechas: int = 0
    segundos_revision: float = 0.0
    revisiones: dict[str, ri.Resultado] = field(default_factory=dict)
    error_tabla: bool = False

    @property
    def n(self) -> int:
        return len(self.correos)

    @property
    def k(self) -> int:
        return len(self.problemas)

    @property
    def listo(self) -> bool:
        return not self.problemas

    @property
    def primera_linea(self) -> str:
        if not self.listo:
            return f"{NO_LISTO}: {self.k} {('problema' if self.k == 1 else 'problemas')}"
        base = f'{LISTO}: {self.n} correos verificados; '
        if self.n and (not self.sin_envio):
            return PRIMERA_LINEA_LISTO.format(listo=LISTO, n=self.n)
        if self.con_envio:
            return base + f'{len(self.con_envio)} versiones para enviar solo pierden identificadores y marcas; {len(self.sin_envio)} sin versión para enviar ({SIN_ENVIAR})'
        return base + f'sin versiones para enviar ({SIN_ENVIAR})'

    def estado(self) -> str:
        """Public CI documentation."""
        base = f'REVCARPETA={EN_EL_REGISTRO[self.listo]};N={self.n};K={self.k}'
        if not self.revision_pedida:
            return base
        return base + (';REVIND=NO_HECHA' if self.revisiones_no_hechas else f';REVIND={self.objeciones}') + f';PASADAS={self.pasadas}'

    def linea_de_revision(self) -> str:
        """Public CI documentation."""
        con_objeciones = sum((1 for r in self.revisiones.values() if r.hecha and r.objeciones))
        pasadas = f"{self.pasadas} {('pasada' if self.pasadas == 1 else 'pasadas')} por correo"
        return f"Revisión independiente ({pasadas}, {round(self.segundos_revision)} s): {self.objeciones} {('objeción' if self.objeciones == 1 else 'objeciones')} en {con_objeciones} de {len(self.revisiones)} correos; {self.revisiones_no_hechas} sin poder hacerse (cada una es un problema: sin ella la tanda no está lista)."

    def texto(self) -> str:
        out = [self.primera_linea, '']
        if not self.listo:
            por_fichero: dict[str, list[str]] = {}
            for p in self.problemas:
                por_fichero.setdefault(p.fichero or '(la carpeta)', []).append(p.texto)
            for fichero, textos in por_fichero.items():
                out.append(fichero)
                out += [f'  - {t}' for t in textos[:MAXIMO_DIFERENCIAS_ENSENADAS]]
                if len(textos) > MAXIMO_DIFERENCIAS_ENSENADAS:
                    out.append(f'  - … y {len(textos) - MAXIMO_DIFERENCIAS_ENSENADAS} más (no se enseñan: arregla las anteriores y vuelve a comprobar)')
            out.append('')
        if self.avisos:
            out.append('Avisos (no tumban, pero hay que leerlos):')
            out += [f"  - {(p.fichero + ': ' if p.fichero else '')}{p.texto}" for p in self.avisos]
            out.append('')
        if self.notas:
            out.append('Notas:')
            out += [f'  - {t}' for t in self.notas]
            out.append('')
        if self.revision_pedida:
            out += [self.linea_de_revision(), '']
        if self.archivada:
            out.append(f'Archivo: archivada con los mismos ficheros ({self.archivo}).')
        elif self.listo:
            out.append('Archivo: aún no archivada. Después del envío, archívala y vuelve a comprobar con momento=despues.')
        revision_dice = f" Y {self.pasadas} {('revisión independiente' if self.pasadas == 1 else 'revisiones independientes')} de la interpretación de cada correo (otro modelo, sin el contexto de la conversación): cada objeción es un problema." if self.revision_pedida else ''
        out += ['', f'Carpeta comprobada: {self.carpeta} (momento: {self.momento}).', 'Qué comprueba: cada fichero de preguntas.json verificado con su instrucción; que la versión para enviar solo pierde identificadores, marcas «(opinión)» y los signos que quedan sueltos; y el archivo, byte a byte.' + revision_dice + ' Que el contenido sea correcto lo decide Responsable.']
        return '\n'.join(out).rstrip() + '\n'

    def dict(self) -> dict:
        d = {'listo': self.listo, 'primera_linea': self.primera_linea, 'n': self.n, 'k': self.k, 'momento': self.momento, 'problemas': [p.dict() for p in self.problemas], 'avisos': [p.dict() for p in self.avisos], 'notas': self.notas, 'veredictos': self.veredictos, 'con_envio': self.con_envio, 'sin_envio': self.sin_envio, 'archivo': self.archivo, 'archivada': self.archivada, 'estado': self.estado(), 'texto': self.texto()}
        if self.revision_pedida:
            d['revision_independiente'] = {'pasadas': self.pasadas, 'objeciones': self.objeciones, 'no_hechas': self.revisiones_no_hechas, 'segundos': round(self.segundos_revision, 1), 'por_fichero': {f: {'hecha': r.hecha, 'fallo': r.fallo, 'omitida': r.omitida, 'objeciones': len(r.objeciones), 'en_cache': r.en_cache, 'segundos': round(r.segundos, 1), 'n_descartadas': r.n_descartadas} for f, r in self.revisiones.items()}}
        return d

def leer_contrato(carpeta: Path) -> dict[str, str]:
    """Public CI documentation."""
    ruta = carpeta / CONTRATO
    try:
        datos = json.loads(ruta.read_bytes().decode('utf-8-sig'))
    except FileNotFoundError:
        raise ContratoMalo(f'falta {CONTRATO} (el contrato: qué ficheros se envían y la instrucción de Responsable de cada uno): sin él no se puede comprobar nada') from None
    except OSError as e:
        raise ContratoMalo(f'{CONTRATO} no se puede leer ({e.strerror or e})') from None
    except UnicodeDecodeError:
        raise ContratoMalo(f'{CONTRATO} no está en UTF-8') from None
    except ValueError as e:
        raise ContratoMalo(f'{CONTRATO} no es un JSON válido ({e})') from None
    if not isinstance(datos, dict) or any((not isinstance(k, str) or not isinstance(v, str) for k, v in datos.items())):
        raise ContratoMalo(f'{CONTRATO} tiene que ser un objeto {{"fichero": "instrucción de Responsable"}} con textos')
    if not datos:
        raise ContratoMalo(f'{CONTRATO} no lista ningún fichero')
    return datos

def _leer_texto(ruta: Path) -> str:
    """Public CI documentation."""
    return ruta.read_bytes().decode('utf-8-sig')

def _por_nombre(entradas: dict[str, Path], nombre: str) -> Path | None:
    """Public CI documentation."""
    if nombre in entradas:
        return entradas[nombre]
    return next((p for k, p in entradas.items() if k.casefold() == nombre.casefold()), None)

def _archivo_de(carpeta: Path, archivada_en, archivo_raiz) -> Path | None:
    """Public CI documentation."""
    if archivada_en is not None:
        return Path(archivada_en)
    candidata = Path(archivo_raiz if archivo_raiz is not None else ARCHIVO_ENTREGAS) / carpeta.name
    return candidata if candidata.is_dir() else None

def _misma_carpeta(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False

def _comparar_archivo(carpeta: Path, archivo: Path, nombres: list[str]) -> str | None:
    """Public CI documentation."""
    if not archivo.is_dir():
        return 'no existe la carpeta del archivo'
    faltan, distintos = ([], [])
    for nombre in nombres:
        en_archivo = archivo / nombre
        if not en_archivo.is_file():
            faltan.append(nombre)
            continue
        try:
            if (carpeta / nombre).read_bytes() != en_archivo.read_bytes():
                distintos.append(nombre)
        except OSError:
            distintos.append(nombre)
    if not faltan and (not distintos):
        return None
    partes = []
    if faltan:
        partes.append('faltan en el archivo: ' + ', '.join(faltan))
    if distintos:
        partes.append('distintos del archivo: ' + ', '.join(distintos))
    return '; '.join(partes)

def _revision_de_la_tanda(res: Resultado, preparadas: dict[str, ri.Preparada], fallos_de_preparacion: dict[str, ri.Resultado], revisiones: int, hilos: int, ejecutor, cache: bool) -> None:
    """Public CI documentation."""
    t0 = time.monotonic()
    tareas = [(nombre, p) for nombre in res.correos if nombre in preparadas and (not preparadas[nombre].omitida) for p in range(1, revisiones + 1)]
    resultados: dict[str, list[ri.Resultado]] = {nombre: [] for nombre in preparadas}
    if tareas:
        with ThreadPoolExecutor(max_workers=min(hilos, len(tareas)), thread_name_prefix='comprobar') as pool:
            futuros = [(nombre, pool.submit(ri.ejecutar_o_fallo, preparadas[nombre], pasada=p, ejecutor=ejecutor, cache=cache)) for nombre, p in tareas]
            for nombre, futuro in futuros:
                resultados[nombre].append(futuro.result())
    res.segundos_revision = round(time.monotonic() - t0, 1)
    for nombre in res.correos:
        if nombre in preparadas:
            ind = ri.combinar(preparadas[nombre], resultados[nombre], revisiones)
        elif nombre in fallos_de_preparacion:
            ind = fallos_de_preparacion[nombre]
        else:
            continue
        res.revisiones[nombre] = ind
        if ind.hecha:
            res.objeciones += len(ind.objeciones)
            res.problemas += [Problema(nombre, o.motivo) for o in ind.objeciones]
        else:
            res.revisiones_no_hechas += 1
            res.problemas.append(Problema(nombre, ind.motivo_de_fallo))

def comprobar(con: sqlite3.Connection, carpeta, archivada_en=None, *, momento: str=ANTES, revision_independiente: bool=False, revisiones: int=1, hilos: int=6, ambitos: tuple[str, ...]=('publico',), huella_base: str | None=None, datos_vigencia: dict | None=None, tabla_sucesion: list[dict] | None=None, temas: list[completitud.Tema] | None=None, archivo_raiz=None, datos_historial: dict | None=None, modelo_revision: str | None=None, ejecutor_revision: ri.Ejecutor | None=None, cache_revision: bool=True) -> Resultado:
    """Public CI documentation."""
    if momento not in MOMENTOS:
        raise ValueError(f'momento tiene que ser uno de {MOMENTOS}, no {momento!r}')
    if isinstance(revisiones, bool) or not isinstance(revisiones, int) or revisiones < 1:
        raise ValueError(f'revisiones tiene que ser un entero desde 1, no {revisiones!r}')
    if isinstance(hilos, bool) or not isinstance(hilos, int) or hilos < 1:
        raise ValueError(f'hilos tiene que ser un entero desde 1, no {hilos!r}')
    carpeta = Path(carpeta)
    try:
        entradas = {p.name: p for p in carpeta.iterdir() if p.is_file()}
    except OSError as e:
        raise CarpetaIlegible(f'no se puede leer la carpeta {str(carpeta)!r}: {e.strerror or e}') from None
    res = Resultado(carpeta=str(carpeta), momento=momento)
    try:
        contrato = leer_contrato(carpeta)
    except ContratoMalo as e:
        res.problemas.append(Problema(CONTRATO, str(e)))
        return res
    res.correos = sorted(contrato, key=str.casefold)
    if revision_independiente:
        res.revision_pedida, res.pasadas = (True, revisiones)
    huella_base = db.huella_contenido(con) if huella_base is None else huella_base
    datos_vigencia = vigencia.instantanea_actual() if datos_vigencia is None else datos_vigencia
    try:
        if tabla_sucesion is None:
            tabla_sucesion = sucesion.cargar()
        relacionados.cargar()
        if temas is None:
            temas = completitud.cargar()
        if interruptores.modo('ambito') == 'bloquea':
            ambito.cargar()
    except (sucesion.ErrorDeTabla, relacionados.ErrorDeTabla, interruptores.ErrorDeControles, completitud.TemasMal, ambito.ReglasMal) as e:
        res.problemas.append(Problema('', _mensaje_tabla_rota(e)))
        res.error_tabla = True
        if revision_independiente:
            res.revisiones_no_hechas = len(res.correos)
        return res
    preparadas: dict[str, ri.Preparada] = {}
    fallos_de_preparacion: dict[str, ri.Resultado] = {}
    if revision_independiente:
        datos_historial = historial_boe.instantanea_actual() if datos_historial is None else datos_historial
    ficheros_a_archivar: list[str] = [CONTRATO]
    for nombre in res.correos:
        instruccion = contrato[nombre]
        if Path(nombre).name != nombre or nombre in ('.', '..'):
            res.problemas.append(Problema(nombre, 'el nombre no es el de un fichero de la carpeta (en preguntas.json van solo nombres de fichero, sin ruta)'))
            continue
        ruta = _por_nombre(entradas, nombre)
        if ruta is None:
            res.problemas.append(Problema(nombre, 'está en preguntas.json pero no en la carpeta'))
            continue
        ficheros_a_archivar.append(ruta.name)
        try:
            texto = _leer_texto(ruta)
        except OSError as e:
            res.problemas.append(Problema(nombre, f'no se puede leer ({e.strerror or e})'))
            continue
        except UnicodeDecodeError:
            res.problemas.append(Problema(nombre, 'no está en UTF-8'))
            continue
        if not instruccion.strip():
            res.problemas.append(Problema(nombre, 'su instrucción en preguntas.json está vacía: sin ella no se puede comprobar que esté completo'))
            continue
        v = entrega.verificar(con, texto, ambitos, huella_base, datos_vigencia=datos_vigencia, tabla_sucesion=tabla_sucesion, pregunta=instruccion, temas=temas, datos_historial=datos_historial)
        res.veredictos[nombre] = v.veredicto
        if not v.valida:
            res.problemas += [Problema(nombre, f'{v.veredicto}: {m}') for m in v.motivos] or [Problema(nombre, v.veredicto)]
        elif v.veredicto == entrega.VALIDA_CON_AVISOS:
            res.avisos += [Problema(nombre, f'{v.veredicto} · {c.nivel} · {c.tipo} · línea {c.linea} · {c.cita} → {c.detalle}') for c in v.avisos]
        if revision_independiente:
            try:
                preparadas[nombre] = ri.preparar(con, instruccion, texto, ambitos, v.informe.huella_base, datos_vigencia=datos_vigencia, datos_historial=datos_historial, modelo=modelo_revision)
            except Exception as e:
                fallos_de_preparacion[nombre] = ri.Resultado(fallo=f'error inesperado en la revisión ({type(e).__name__}: {e})', pasadas=revisiones)
        enviar = _por_nombre(entradas, f'{PREFIJO_ENVIAR}{Path(nombre).stem}.txt')
        if enviar is None:
            res.sin_envio.append(nombre)
            continue
        res.con_envio.append(nombre)
        try:
            enviado = _leer_texto(enviar)
        except OSError as e:
            res.problemas.append(Problema(enviar.name, f'no se puede leer ({e.strerror or e})'))
            continue
        except UnicodeDecodeError:
            res.problemas.append(Problema(enviar.name, 'no está en UTF-8'))
            continue
        if not enviado.strip():
            res.problemas.append(Problema(enviar.name, 'está vacía'))
            continue
        if revision.lineas_de_sello(enviado):
            res.problemas.append(Problema(enviar.name, 'lleva todavía la línea de sello: quítala (no va en lo que se envía)'))
        for d in diferencias(revision.sin_lineas_de_sello(texto), revision.sin_lineas_de_sello(enviado)):
            res.problemas.append(Problema(enviar.name, d.texto()))
    if revision_independiente:
        _revision_de_la_tanda(res, preparadas, fallos_de_preparacion, revisiones, hilos, ejecutor_revision, cache_revision)
    esperados = {f'{PREFIJO_ENVIAR}{Path(c).stem}.txt'.casefold() for c in res.correos}
    listados = {c.casefold() for c in res.correos}
    for nombre in sorted(entradas, key=str.casefold):
        if nombre.casefold().startswith(PREFIJO_ENVIAR.casefold()):
            ficheros_a_archivar.append(nombre)
            if nombre.casefold() not in esperados:
                res.problemas.append(Problema(nombre, 'es una versión para enviar de un fichero que no está en preguntas.json: no se ha verificado ni se puede comprobar'))
        elif nombre.casefold().endswith('.md') and nombre.casefold() not in listados:
            res.avisos.append(Problema(nombre, AVISO_MD_SUELTO))
    if res.sin_envio:
        res.notas.append(f"sin versión para enviar ({', '.join(res.sin_envio)}): {SIN_ENVIAR}")
    archivo = _archivo_de(carpeta, archivada_en, archivo_raiz)
    if archivo is not None and _misma_carpeta(carpeta, archivo):
        res.archivo, res.archivada = ('es la propia carpeta del archivo', True)
    elif archivo is not None:
        res.archivo = archivo.name if archivada_en is None else str(archivo)
        difiere = _comparar_archivo(carpeta, archivo, sorted(set(ficheros_a_archivar), key=str.casefold))
        res.archivada = difiere is None
        if difiere is not None:
            donde = Problema('', f'{NO_ARCHIVADA}: {difiere}')
            (res.problemas if momento == DESPUES else res.avisos).append(donde)
    else:
        donde = Problema('', f'{NO_ARCHIVADA}: no hay carpeta de archivo para esta tanda (archivo_entregas\\{carpeta.name})')
        (res.problemas if momento == DESPUES else res.avisos).append(donde)
    return res
