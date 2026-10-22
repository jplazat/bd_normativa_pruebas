"""Public CI documentation."""
from __future__ import annotations
import hashlib
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass, field
from . import afirmaciones, comillas, consulta, cotejo_original, db, fundamento, historial_boe, interruptores, relacionados, sucesion, vigencia
from .contexto import RE_NORMA
OK, AVISO, ERROR = ('OK', 'AVISO', 'ERROR')
NIVELES = (ERROR, AVISO, OK)
RE_LINEA_DE_SELLO = afirmaciones.RE_SELLO
RE_LINEA_DE_BASE = afirmaciones.RE_LINEA_DE_BASE
RE_CODIGO_DE_SELLO = re.compile('(?i)\\[sello:\\s*([0-9a-f]{8})\\]')
LARGO_DEL_CODIGO = 8

def _lineas_de_sello(lineas: list[str]) -> tuple[list[bool], list[bool]]:
    """Public CI documentation."""
    es_sello, es_base, tras_sello = ([], [], False)
    for linea in lineas:
        sello = bool(RE_LINEA_DE_SELLO.search(linea))
        base = tras_sello and (not sello) and bool(RE_LINEA_DE_BASE.match(linea))
        es_sello.append(sello)
        es_base.append(base)
        tras_sello = sello or (tras_sello and (not linea.strip()))
    return (es_sello, es_base)

def lineas_de_sello(texto: str) -> list[str]:
    """Public CI documentation."""
    lineas = texto.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    es_sello, _ = _lineas_de_sello(lineas)
    return [l.strip() for l, s in zip(lineas, es_sello) if s]

def sin_lineas_de_sello(texto: str) -> str:
    """Public CI documentation."""
    lineas = texto.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    es_sello, es_base = _lineas_de_sello(lineas)
    return '\n'.join(('' if s or b else l for l, s, b in zip(lineas, es_sello, es_base))).rstrip()

def normalizar_para_el_sello(texto: str) -> str:
    """Public CI documentation."""
    lineas = unicodedata.normalize('NFC', sin_lineas_de_sello(texto)).split('\n')
    salida: list[str] = []
    for linea in (l.rstrip() for l in lineas):
        if not linea and salida and (not salida[-1]):
            continue
        salida.append(linea)
    return '\n'.join(salida).strip()

def codigo_de_sello(texto: str) -> str:
    """Public CI documentation."""
    return hashlib.sha256(normalizar_para_el_sello(texto).encode('utf-8')).hexdigest()[:LARGO_DEL_CODIGO]

def codigo_de_una_linea_de_sello(linea: str) -> str | None:
    """Public CI documentation."""
    m = RE_CODIGO_DE_SELLO.search(linea)
    return m.group(1).lower() if m else None
RE_IDENT_TICK = re.compile('`([^`\\n]{1,200}?::[^`\\n]+?)`')
RE_IDENT_SUELTO = re.compile('(?<![\\w`])((?:…|\\.\\.\\.|BOE-A-\\d{4}-\\d+|CELEX-[0-9A-Z]+|ICT155-[\\w.\\-]+)::[\\w.\\-/ñ]+)')
ABREVIADA = ('…', '...')
RE_OBRA_SOLA = re.compile('(?<![\\w-])(BOE-A-\\d{4}-\\d+|CELEX-[0-9A-Z]+)(?!::|[\\w-])')
RE_COMILLAS = re.compile('«([^»\\n]+)»|“([^”\\n]+)”|\\"([^\\"\\n]{8,})\\"')
RE_BLOQUE = re.compile('(?m)^[ \\t]*>[ \\t]?(.*)$')
RE_ELISION = re.compile('\\s*(?:\\[\\s*(?:…|\\.\\.\\.)\\s*\\]|\\(\\s*(?:…|\\.\\.\\.)\\s*\\)|…|\\.\\.\\.)\\s*')
MINIMO_PALABRAS = fundamento.MINIMO_PALABRAS
RE_CONDICION = re.compile('(?i)\\b(cuando|si|salvo|excepto|con excepci[oó]n de|siempre que|en su caso|a menos que|s[oó]lo|s[oó]lamente|[uú]nicamente|en caso de|sin perjuicio|no obstante|cuando proceda|si procede)\\b')
RE_EXCEPCION_SIGUE = re.compile('(?i)^\\s*(no obstante|sin perjuicio|sin embargo|salvo|excepto|con excepci[oó]n|se exceptúa|quedan? exceptuad)')
RE_MARCA_DE_ELEMENTO = re.compile('(?:^|\\s)(?:[a-zñ]\\)|\\d{1,2}(?:\\.\\d{1,2})*\\.?)\\s')
RE_PAGINAS = re.compile('(?i)\\b(?:p\\.|pp\\.|p[áa]g\\.|p[áa]gina|p[áa]ginas)\\s*(\\d{1,4})(?:\\s*(?:-|–|a|y)\\s*(\\d{1,4}))?')
DISTANCIA_PAGINAS = 40
RE_DISPOSICION_CON_SUBRUTA = re.compile('^((?:reglamento/)?disp\\.[a-z]+\\.\\d+)\\.\\S+$')
RE_REESCRIBE = re.compile('(?i)queda(?:n)?\\s+redactad|se\\s+añade|nueva\\s+redacci[oó]n|se\\s+modifica')

@dataclass
class Comprobacion:
    nivel: str
    tipo: str
    cita: str
    detalle: str
    identificador: str | None = None
    linea: int = 0

@dataclass
class Informe:
    comprobaciones: list[Comprobacion] = field(default_factory=list)
    huella_base: str | None = None
    preceptos_base: int | None = None
    cobertura: afirmaciones.Cobertura = field(default_factory=afirmaciones.Cobertura)
    codigo: str | None = None

    def resumen(self) -> dict:
        """Public CI documentation."""

        def cuenta(cs):
            return {'ok': sum((1 for c in cs if c.nivel == OK)), 'avisos': sum((1 for c in cs if c.nivel == AVISO)), 'errores': sum((1 for c in cs if c.nivel == ERROR))}
        todas = cuenta(self.comprobaciones)
        citas = cuenta([c for c in self.comprobaciones if c.tipo in afirmaciones.TIPOS_DE_CITA])
        riesgo = cuenta([c for c in self.comprobaciones if c.tipo not in afirmaciones.TIPOS_DE_CITA and c.tipo != afirmaciones.SIN_COMPROBAR])
        return {**todas, 'total': len(self.comprobaciones), 'citas': citas, 'riesgo': riesgo, 'normativas': self.cobertura.normativas, 'comprobadas': self.cobertura.comprobadas, 'sin_comprobar': self.cobertura.sin_comprobar, 'opinion': self.cobertura.opinion, 'refutadas': self.cobertura.refutadas}

    def linea(self) -> str:
        """Public CI documentation."""
        r = self.resumen()
        c, k = (r['citas'], r['riesgo'])
        n_citas, n_riesgo = (sum(c.values()), sum(k.values()))
        partes = [f"{n_citas} {('cita comprobada' if n_citas == 1 else 'citas comprobadas')} ({c['ok']} bien, {c['avisos']} avisos, {c['errores']} errores)"]
        if n_riesgo:
            partes.append(f"{n_riesgo} {('comprobación' if n_riesgo == 1 else 'comprobaciones')} de riesgo ({k['ok']} bien, {k['avisos']} avisos, {k['errores']} errores)")
        s, o = (r['sin_comprobar'], r['opinion'])
        partes.append(f"{s} {('afirmación normativa sin comprobar' if s == 1 else 'afirmaciones normativas sin comprobar')}")
        partes.append(f"{o} {('marcada' if o == 1 else 'marcadas')} como opinión")
        linea = 'Comprobado por la base: ' + '; '.join(partes) + '.'
        if s or r['errores']:
            falta = []
            if r['errores']:
                falta.append('corrige cada ERROR')
            if s:
                falta.append('cita cada afirmación normativa sin comprobar con su identificador `obra::ruta` o márcala como opinión')
            linea += ' LA RESPUESTA NO ESTÁ LISTA PARA ENTREGARSE: ' + ' y '.join(falta) + '.'
        elif r['avisos']:
            linea += ' Atiende cada aviso antes de entregar.'
        elif not n_citas and (not r['normativas']):
            linea += ' No se ha detectado ninguna cita ni afirmación normativa: la revisión no ha comprobado nada.'
        else:
            linea += ' Todo lo normativo detectado está citado o marcado; lo concluido sigue siendo de Responsable.'
        return linea + (f' [sello: {self.codigo}]' if self.codigo else '')

    def dict(self) -> dict:
        return {'resumen': self.resumen(), 'linea': self.linea(), 'sello': self.codigo, 'cobertura': self.cobertura.dict(), 'huella_base': self.huella_base, 'preceptos_base': self.preceptos_base, 'comprobaciones': [asdict(c) for c in self.comprobaciones]}

    def texto(self) -> str:
        cab = f"REVISIÓN DEL BORRADOR CONTRA LA BASE (huella {(self.huella_base or '?')[:8]}, {self.preceptos_base or '?'} preceptos)\n{self.linea()}"
        filas = sorted(self.comprobaciones, key=lambda c: (NIVELES.index(c.nivel), c.linea))
        cuerpo = [f'{c.nivel:<6} {c.tipo:<13} línea {c.linea:<4} {c.cita}\n       → {c.detalle}' for c in filas]
        return '\n'.join([cab, ''] + cuerpo)

def _corta(s: str, n: int=110) -> str:
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n - 1] + '…'

def _linea(texto: str, pos: int) -> int:
    return texto.count('\n', 0, pos) + 1

def _bloques(texto: str) -> list[tuple[int, int]]:
    """Public CI documentation."""
    tramos, inicio = ([], 0)
    for m in re.finditer('\\n[ \\t]*\\n', texto):
        tramos.append((inicio, m.start()))
        inicio = m.end()
    tramos.append((inicio, len(texto)))
    return tramos

def identificadores_del_borrador(texto: str) -> list[tuple[int, int, str]]:
    """Public CI documentation."""
    vistos: list[tuple[int, int, str]] = []
    ocupado: list[tuple[int, int]] = []
    for m in RE_IDENT_TICK.finditer(texto):
        vistos.append((m.start(), m.end(), m.group(1).strip()))
        ocupado.append((m.start(), m.end()))
    for m in RE_IDENT_SUELTO.finditer(texto):
        if any((a <= m.start() < b for a, b in ocupado)):
            continue
        vistos.append((m.start(), m.end(), m.group(1)))
    obras_solas = [(m.start(), m.group(1)) for m in RE_OBRA_SOLA.finditer(texto) if not any((a <= m.start() < b for a, b, _ in vistos))]
    eventos = sorted([(a, b, i) for a, b, i in vistos] + [(p, None, o) for p, o in obras_solas])
    salida, obra = ([], None)
    for a, b, ident in eventos:
        if b is None:
            obra = ident
            continue
        ident = ident.rstrip('.,;:')
        cab, _, ruta = ident.partition('::')
        cab = cab.strip()
        if cab in ABREVIADA:
            ident = f'{obra}::{ruta}' if obra else ident
        else:
            obra = cab
        salida.append((a, b, ident))
    return salida

def literales_del_borrador(texto: str) -> list[tuple[int, str]]:
    """Public CI documentation."""
    salida: list[tuple[int, str]] = []
    bloque: list[str] = []
    inicio = None
    for m in RE_BLOQUE.finditer(texto):
        if inicio is not None and texto[fin_prev:m.start()].strip():
            salida.append((inicio, ' '.join(bloque)))
            bloque, inicio = ([], None)
        if inicio is None:
            inicio = m.start()
        bloque.append(m.group(1).strip())
        fin_prev = m.end()
    if inicio is not None:
        salida.append((inicio, ' '.join(bloque)))
    en_bloque = {p for p, _ in salida}
    lineas_de_bloque = {_linea(texto, p) for p in en_bloque}
    for a, b in comillas.tramos(texto):
        lit = texto[a + 1:b - 1]
        if _linea(texto, a) in lineas_de_bloque:
            continue
        salida.append((a, lit))
    return sorted(salida)

def _identificadores_que_gobiernan(texto: str, pos: int, idents: list[tuple[int, int, str]], bloques: list[tuple[int, int]]) -> list[str]:
    """Public CI documentation."""
    ini = texto.rfind('\n', 0, pos) + 1
    fin = texto.find('\n', pos)
    fin = len(texto) if fin < 0 else fin
    mismo = [i for a, b, i in idents if ini <= a < fin]
    if mismo:
        return list(dict.fromkeys(mismo))
    k = next((i for i, (a, b) in enumerate(bloques) if a <= pos <= b), None)
    if k:
        a0, b0 = bloques[k - 1]
        previo = texto[a0:b0].strip()
        if previo and '\n' not in previo:
            return list(dict.fromkeys((i for a, b, i in idents if a0 <= a <= b0)))
    return []

def _fragmentos(literal: str) -> list[str]:
    """Public CI documentation."""
    return [f.strip(' .,;:') for f in RE_ELISION.split(literal) if f.strip(' .,;:')]

def _palabras(s: str) -> list[str]:
    return fundamento.normalizar(s).split()

def _esta_en(fragmentos: list[str], texto: str) -> bool:
    t = ' ' + fundamento.normalizar(texto) + ' '
    desde = 0
    for f in fragmentos:
        i = t.find(' ' + fundamento.normalizar(f) + ' ', desde)
        if i < 0:
            return False
        desde = i + 1
    return True

def _texto_de(con: sqlite3.Connection, ident: str) -> tuple[consulta.Respuesta, str]:
    r, texto = consulta.texto_de_ambito(con, ident)
    return (r, texto or r.texto_literal or '')

def _gobierno_de_la_frase(literal: str, texto: str) -> list[str]:
    """Public CI documentation."""
    palabras = re.findall('\\w+', fundamento.normalizar(_fragmentos(literal)[0] if _fragmentos(literal) else literal))
    if len(palabras) < 2:
        return []
    plano = ' '.join(texto.split())
    m = re.search('\\W+'.join((re.escape(p) for p in palabras)), plano, re.I)
    if not m:
        return []
    avisos = []
    antes = plano[:m.start()]
    corte = max(antes.rfind('. '), antes.rfind('; '), antes.rfind(': '))
    marcas = [x.end() for x in RE_MARCA_DE_ELEMENTO.finditer(antes)]
    if marcas:
        corte = max(corte, marcas[-1] - 2)
    prefijo = antes[corte + 2:].strip() if corte >= 0 else antes.strip()
    if prefijo and RE_CONDICION.search(prefijo):
        avisos.append(f'deja fuera la condición de su frase: «…{_corta(prefijo, 160)}»')
    ultimo = _fragmentos(literal)[-1] if _fragmentos(literal) else literal
    pal_fin = re.findall('\\w+', fundamento.normalizar(ultimo))
    mf = re.search('\\W+'.join((re.escape(p) for p in pal_fin)), plano[m.start():], re.I) if pal_fin else None
    fin = m.start() + mf.end() if mf else m.end()
    resto_frase = re.split('(?<=[.;])\\s', plano[fin:], maxsplit=1)
    cola = resto_frase[0].strip(' .;')
    if cola and RE_CONDICION.search(cola):
        avisos.append(f'la frase sigue con una condición: «{_corta(cola, 160)}»')
    if len(resto_frase) > 1 and RE_EXCEPCION_SIGUE.match(resto_frase[1]):
        avisos.append(f'le sigue una excepción: «{_corta(resto_frase[1], 160)}»')
    return avisos

def _subruta_no_fiable(con: sqlite3.Connection, ident: str) -> str | None:
    cab, ruta = consulta.partir_identificador(ident)
    m = RE_DISPOSICION_CON_SUBRUTA.match(ruta or '')
    if not m:
        return None
    r, texto = _texto_de(con, f'{cab}::{m.group(1)}')
    if r.estado != consulta.ENCONTRADO or '«' not in texto or (not RE_REESCRIBE.search(texto)):
        return None
    return f'«{ruta}» es una subruta de {m.group(1)}, que reescribe otra norma: su número es de la norma modificada. Cita la disposición, su apartado ordinal (Uno, Dos…) y el artículo de la norma modificada.'

def _paginas_declaradas(texto: str, fin_ident: int, siguiente: int) -> tuple[int, int] | None:
    tramo = texto[fin_ident:min(siguiente, fin_ident + DISTANCIA_PAGINAS)]
    if '\n' in tramo:
        tramo = tramo.split('\n', 1)[0]
    m = RE_PAGINAS.search(tramo)
    if not m:
        return None
    a = int(m.group(1))
    return (a, int(m.group(2) or a))

def revisar(con: sqlite3.Connection, borrador: str, ambitos: tuple[str, ...]=('publico',), huella_base: str | None=None, *, datos_vigencia: dict | None=None, hoy: str | None=None, tabla_sucesion: list[dict] | None=None, afirmaciones_de_riesgo: bool=True, datos_historial: dict | None=None, datos_cotejo: cotejo_original.Datos | None=None) -> Informe:
    """Public CI documentation."""
    inf = Informe()
    inf.codigo = codigo_de_sello(borrador)
    borrador = sin_lineas_de_sello(borrador)
    try:
        inf.huella_base = huella_base or db.huella_contenido(con)
        inf.preceptos_base = con.execute('SELECT count(*) FROM precepto').fetchone()[0]
    except Exception:
        pass
    idents = identificadores_del_borrador(borrador)
    bloques = _bloques(borrador)
    resueltos: dict[str, tuple[consulta.Respuesta, str]] = {}
    for k, (a, b, ident) in enumerate(idents):
        linea = _linea(borrador, a)
        if ident.split('::', 1)[0].strip() in ABREVIADA:
            inf.comprobaciones.append(Comprobacion(ERROR, 'identificador', ident, 'abreviado («…::») sin un identificador completo antes', None, linea))
            continue
        if ident not in resueltos:
            resueltos[ident] = _texto_de(con, ident)
        r, _ = resueltos[ident]
        if r.estado == consulta.ENCONTRADO:
            det = f"{r.etiqueta_humana or ''} — {r.paginas or 'páginas ?'}"
            inf.comprobaciones.append(Comprobacion(OK, 'identificador', ident, det, ident, linea))
        elif r.estado == consulta.CONTENIDO_EN_ANCESTRO:
            inf.comprobaciones.append(Comprobacion(AVISO, 'identificador', ident, f'no es un precepto propio: está impreso dentro de «{r.etiqueta_humana}». Cita ese precepto.', ident, linea))
        else:
            inf.comprobaciones.append(Comprobacion(ERROR, 'identificador', ident, f"{r.estado}: {r.detalle or 'no resuelve'}", ident, linea))
            continue
        if r.calidad_textual:
            inf.comprobaciones.append(Comprobacion(AVISO, 'calidad_textual', ident, r.detalle, ident, linea))
        siguiente = idents[k + 1][0] if k + 1 < len(idents) else len(borrador)
        pags = _paginas_declaradas(borrador, b, siguiente)
        if pags and r.pagina_inicio and r.pagina_fin:
            if pags[1] < r.pagina_inicio or pags[0] > r.pagina_fin:
                inf.comprobaciones.append(Comprobacion(AVISO, 'paginas', f'{ident} p. {pags[0]}' + (f'-{pags[1]}' if pags[1] != pags[0] else ''), f'el precepto está en {r.paginas}', ident, linea))
        nota = _subruta_no_fiable(con, ident)
        if nota:
            inf.comprobaciones.append(Comprobacion(AVISO, 'subruta', ident, nota, ident, linea))
    errores_comillas: list[tuple[int, int]] = []
    para_comillas = borrador
    for patron in (afirmaciones.RE_CERCADO, afirmaciones.RE_LINEA_DE_CITA):
        para_comillas = patron.sub(lambda m: re.sub('[^\\n]', ' ', m.group(0)), para_comillas)
    comillas.tramos(para_comillas, errores_comillas)
    for a, b in errores_comillas:
        inf.comprobaciones.append(Comprobacion(ERROR, 'comillas', _corta(borrador[a:b]), 'comillas sin cerrar o con cierres cruzados: cierra cada nivel en su renglón antes de revisar el literal', None, _linea(borrador, a)))
    cotejo = [datos_cotejo]
    sin_consulta: dict[str, tuple[int, cotejo_original.Cotejo]] = {}
    for pos, literal in literales_del_borrador(borrador):
        linea = _linea(borrador, pos)
        fragmentos = _fragmentos(literal)
        n_palabras = sum((len(_palabras(f)) for f in fragmentos))
        if n_palabras < 2:
            continue
        candidatos = _identificadores_que_gobiernan(borrador, pos, idents, bloques)
        cita = f'«{_corta(literal)}»'
        validos = [i for i in candidatos if i in resueltos and resueltos[i][0].estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO)]
        hallado = next((i for i in validos if _esta_en(fragmentos, resueltos[i][1])), None)
        if hallado:
            avisos = _gobierno_de_la_frase(literal, resueltos[hallado][1])
            natural = resueltos[hallado][0].naturaleza_del_texto
            if natural:
                avisos.insert(0, f'está en {hallado}, pero ese texto no es el literal de la norma ({natural}): no lo presentes como literal sin cotejarlo con la página del documento')
            if cotejo[0] is None:
                cotejo[0] = cotejo_original.datos_actuales()
            r_hallada = resueltos[hallado][0]
            ruta_hallada = consulta.partir_identificador(hallado)[1]
            if r_hallada.version_id and ruta_hallada:
                ruta_hallada = consulta.ruta_efectiva(con, r_hallada.version_id, ruta_hallada)
            try:
                cot = cotejo_original.cotejar(con, r_hallada.version_id, ruta_hallada, fragmentos, cotejo[0])
            except Exception as e:
                cot = cotejo_original.Cotejo(cotejo_original.SIN_CONSULTA, None, r_hallada.obra, f'el cotejo ha fallado ({type(e).__name__}: {e})')
            if cot.estado == cotejo_original.SIN_TESTIGO:
                if natural:
                    avisos.pop(0)
                inf.comprobaciones.append(Comprobacion(ERROR, 'cotejo', cita, cotejo_original.detalle_sin_testigo(cot), hallado, linea))
            elif cot.estado == cotejo_original.DISTINTO:
                inf.comprobaciones.append(Comprobacion(ERROR, 'cotejo', cita, cotejo_original.detalle_distinto(hallado, cot), hallado, linea))
            elif cot.estado == cotejo_original.SIN_CONSULTA:
                sin_consulta.setdefault(cot.obra or hallado, (linea, cot))
            if avisos:
                for av in avisos:
                    inf.comprobaciones.append(Comprobacion(AVISO, 'literal', cita, av, hallado, linea))
            elif cot.estado == cotejo_original.OK:
                inf.comprobaciones.append(Comprobacion(OK, 'literal', cita, cotejo_original.detalle_ok(hallado, cot), hallado, linea))
            elif cot.estado == cotejo_original.SIN_CONSULTA:
                inf.comprobaciones.append(Comprobacion(OK, 'literal', cita, f'está en {hallado}', hallado, linea))
            continue
        ident = ' / '.join(candidatos) if candidatos else None
        if n_palabras < MINIMO_PALABRAS:
            if validos:
                inf.comprobaciones.append(Comprobacion(AVISO, 'literal', cita, f'no está en {ident} (frase corta: no se busca en el resto)', ident, linea))
            continue
        trozo = max(fragmentos, key=lambda f: len(_palabras(f)))
        loc = fundamento.localizar(con, trozo)
        donde = ', '.join((f'{c.identificador}::{c.ruta}' for c in loc.candidatos[:4]))
        if loc.estado == fundamento.LOCALIZADO:
            lugar = loc.fundamento
            _, t_lugar = _texto_de(con, lugar)
            entero = _esta_en(fragmentos, t_lugar)
            if ident:
                det = f'no está en {ident}; está en {lugar}' + ('' if entero else ' (y no entero)')
                inf.comprobaciones.append(Comprobacion(ERROR, 'literal', cita, det, ident, linea))
            else:
                avisos = _gobierno_de_la_frase(literal, t_lugar) if entero else []
                det = f'está en {lugar}, pero el borrador no pone su identificador al lado' + ('' if entero else ' (y no entero)')
                inf.comprobaciones.append(Comprobacion(AVISO, 'literal', cita, det, lugar, linea))
                for av in avisos:
                    inf.comprobaciones.append(Comprobacion(AVISO, 'literal', cita, av, lugar, linea))
        elif loc.estado == fundamento.AMBIGUO:
            det = (f'no está en {ident}; ' if ident else '') + f'aparece en varios preceptos: {donde}'
            inf.comprobaciones.append(Comprobacion(ERROR if ident else AVISO, 'literal', cita, det, ident, linea))
        else:
            det = (f'no está en {ident}' if ident else 'no lleva identificador') + '; no está literal en la base (¿paráfrasis entre comillas?)'
            inf.comprobaciones.append(Comprobacion(ERROR, 'literal', cita, det, ident, linea))
    for obra_sin_consulta, (linea_de_la_obra, cot) in sin_consulta.items():
        inf.comprobaciones.append(Comprobacion(AVISO, 'cotejo', obra_sin_consulta, cotejo_original.detalle_sin_consulta(cot), obra_sin_consulta, linea_de_la_obra))
    citadas: dict[str, tuple[str, int]] = {}
    for a, _b, ident in idents:
        r = resueltos.get(ident, (None, ''))[0]
        if r is not None and r.obra:
            citadas.setdefault(r.obra, (ident.split('::', 1)[0], _linea(borrador, a)))
    vistas: set[str] = set()
    for m in RE_NORMA.finditer(borrador):
        nombre = ' '.join(m.group(0).split())
        if nombre in vistas:
            continue
        vistas.add(nombre)
        r = consulta.resolver(con, nombre, ambitos)
        if r.estado == consulta.NO_CONSTA:
            inf.comprobaciones.append(Comprobacion(AVISO, 'norma', nombre, 'la base no tiene esta norma: no afirmes nada de su contenido ni de su vigencia como si saliera de la base (lo que diga de ella otra norma que sí está, cítalo de esa norma); si hace falta, hay que añadirla', None, _linea(borrador, m.start())))
        elif r.obra:
            citadas.setdefault(r.obra, (nombre, _linea(borrador, m.start())))
    datos = datos_vigencia if datos_vigencia is not None else vigencia.instantanea_actual()
    for obra, (como, linea) in citadas.items():
        v = vigencia.vigencia_de(obra, datos, hoy)
        if v and v['avisos']:
            inf.comprobaciones.append(Comprobacion(AVISO, 'vigencia', como, '; '.join(v['avisos']) + '. Dilo en la respuesta.', obra, linea))
    if afirmaciones_de_riesgo:
        estado_literal: dict[int, str | None] = {}
        for pos, literal in literales_del_borrador(borrador):
            cita = f'«{_corta(literal)}»'
            niveles = [c.nivel for c in inf.comprobaciones if c.tipo in ('literal', 'cotejo') and c.linea == _linea(borrador, pos) and (c.cita == cita)]
            estado_literal[pos] = ERROR if ERROR in niveles else AVISO if AVISO in niveles else OK if niveles else None
        try:
            historial = datos_historial if datos_historial is not None else historial_boe.instantanea_actual()
            analizador = afirmaciones.Analizador(con, borrador, idents, resueltos, estado_literal, bloques, ambitos, datos, hoy, tabla_sucesion, historial)
            nuevas, inf.cobertura = analizador.analizar(afirmaciones.frases_del_borrador(borrador))
            inf.comprobaciones.extend(nuevas)
        except (sucesion.ErrorDeTabla, relacionados.ErrorDeTabla, interruptores.ErrorDeControles):
            raise
        except Exception as e:
            inf.comprobaciones.append(Comprobacion(ERROR, 'analisis', 'análisis de las frases', f'el análisis de las frases ha fallado ({type(e).__name__}: {e}): la prosa del borrador NO se ha revisado. Dilo y revisa las citas a mano.', None, 0))
    return inf
