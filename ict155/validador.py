"""Public CI documentation."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from . import consulta, contexto, identificadores, mobiliario, superindices
RE_ENTRECOMILLADO = re.compile('«([^»]{25,})»')
LITERAL_OK = 'LITERAL CONFIRMADA'
LITERAL_DISCREPA = 'DISCREPA'
PRECEPTO_NO_EXISTE = 'PRECEPTO INEXISTENTE'
NO_COMPARABLE = 'NO COMPARABLE'
PARAFRASIS = 'PARAFRASIS'
CITA_A_TABLA = 'CITA A TABLA'
_MOTIVO_TABLA = 'cita a una tabla: una tabla no tiene lectura lineal unica y no se compara como cadena; se lee del PDF'
_POR_HERENCIA = 'la norma no se nombra en la frase de la cita, se hereda {0} ({1}): la atribucion esta supuesta, no determinada'
_MAPA = {'«': '"', '»': '"', '“': '"', '”': '"', '‘': "'", '’': "'", '—': '-', '–': '-', ' ': ' ', ' ': ' '}
RX_CORCHETE_EDITORIAL = re.compile('\\[(?!\\s*(?:\\.\\.\\.|…)\\s*\\])[^\\[\\]]{1,}\\]')
RX_CORCHETE_COME_ESPACIO = re.compile('\\s*' + RX_CORCHETE_EDITORIAL.pattern)
RX_ELISION = re.compile('\\[\\s*(?:\\.\\.\\.|…)\\s*\\]')
_DISCREPA_ELISION = 'ni con la elisión declarada los fragmentos citados aparecen en el precepto al que se atribuye'
_NOTA_CORCHETE_CONFIRMA = 'cita confirmada excluyendo el tramo entre corchetes que el autor marcó como adaptación ([sic] o aclaración añadida): el resto casa literal. Cotejar el corchete a mano contra la página'
_NOTA_CORCHETE_SENTIDO = 'la inserción entre corchetes altera el sentido: cotejar a mano'
_NOTA_GUION = 'la diferencia se limita a guion(es): cotejar la palabra guionada contra la página'
_TERMINOS_QUE_ALTERAN_SENTIDO = frozenset('no nunca ni sin salvo excepto tampoco not except unless without longer'.split())
RX_CURSIVA_GUION = re.compile('(?<![^\\W_])_(?=[^\\s_])([^_\\n]{1,300}?)(?<=[^\\s_])_(?![^\\W_])')
RX_MAQUETACION = (re.compile('\\s*P[áa]gina\\s+\\d+\\s+BOLET[ÍI]N OFICIAL DEL ESTADO\\s+LEGISLACI[ÓO]N CONSOLIDADA\\s*'), re.compile('\\s*BOLET[ÍI]N OFICIAL DEL ESTADO\\s+LEGISLACI[ÓO]N CONSOLIDADA\\s+P[áa]gina\\s+\\d+\\s*'), re.compile('\\s*\\b\\d{5}[A-Z]\\d{4}\\s+[—–-]\\s+[A-Z]{2}\\s+[—–-]\\s+\\d{2}\\.\\d{2}\\.\\d{4}\\s+[—–-]\\s+\\d{3}\\.\\d{3}\\s+[—–-]\\s+\\d+\\s*'), re.compile('\\s*\\b[LC]\\s+\\d+/\\d+\\s+[A-Z]{2}\\s+Diario Oficial de la Uni[óo]n Europea\\s+\\d{1,2}\\.\\d{1,2}\\.\\d{4}\\s*'), re.compile('\\s*\\b\\d{1,2}\\.\\d{1,2}\\.\\d{4}\\s+[A-Z]{2}\\s+Diario Oficial de la Uni[óo]n Europea\\s+[LC]\\s+\\d+/\\d+\\s*'))
RX_VERBO_TESTIMONIAL = re.compile('\\b(?:declar(?:a|an|ó|aron|aba|aban)|manifest(?:ó|aron|aba|aban)|afirm(?:a|an|ó|aron|aba)|sostien(?:e|en)|sostuv(?:o|ieron)|indic(?:ó|aron)|reconoc(?:e|en|ió|ieron)|admit(?:e|en|ió|ieron)|aleg(?:a|an|ó|aron)|aduc(?:e|en)|aduj(?:o|eron)|asegur(?:a|an|ó|aron)|explic(?:ó|aron)|coment(?:ó|aron)|respond(?:ió|ieron)|contest(?:ó|aron)|añad(?:ió|ieron)|neg(?:ó|aron)|niega|relat(?:ó|aron)|expus(?:o|ieron))\\b', re.I)
RX_VERBO_NORMATIVO = re.compile('\\b(?:dispon(?:e|en)|dispuso|establec(?:e|en|ió|ieron)|señal(?:a|an)|prev(?:é|én)|determin(?:a|an)|exig(?:e|en)|oblig(?:a|an)|indic(?:a|an)|dic(?:e|en)|reza|defin(?:e|en)|recog(?:e|en)|regul(?:a|an)|contempl(?:a|an)|precept(?:úa|úan)|reza\\s+así)\\b', re.I)
_ABREVIATURAS = [(re.compile('\\barts?(?:\\.\\s*|\\s+)(?=\\d)'), 'artículo '), (re.compile('\\bap(?:t?do)?(?:\\.\\s*|\\s+)(?=\\d)'), 'apartado '), (re.compile('\\bdisp\\.?\\s+'), 'disposición '), (re.compile('\\bnúm\\.?\\s+(?=\\d)'), 'número '), (re.compile('\\bpárr\\.?\\s+(?=\\d)'), 'párrafo '), (re.compile('\\bapénd\\.?\\s+'), 'apéndice ')]
RX_MATEMATICAS = re.compile('[𝐀-𝟿ﬀ-ﬆ]')

def _plegar_matematicas(s: str) -> str:
    return RX_MATEMATICAS.sub(lambda m: unicodedata.normalize('NFKC', m.group(0)), s)

def _norm(s: str, guiones: bool=True) -> str:
    """Public CI documentation."""
    s = superindices.plegar(_plegar_matematicas(unicodedata.normalize('NFC', s or '')))
    s = re.sub('\xad\\s*', '', s)
    for rx in RX_MAQUETACION:
        s = rx.sub(' ', s)
    s = re.sub('\\*\\*|__|\\*|`', '', s)
    s = RX_CURSIVA_GUION.sub('\\1', s)
    s = re.sub('\\[\\s*\\.\\.\\.\\s*\\]|\\[…\\]', '', s)
    s = re.sub('\\[([^\\[\\]]{1,40})\\]', '\\1', s)
    for a, b in _MAPA.items():
        s = s.replace(a, b)
    s = s.replace('►', '').replace('◄', '').replace('▼', '')
    s = re.sub('\\s+', ' ', s).strip().lower()
    if guiones:
        s = re.sub('(?<=[^\\W\\d_])-(?=[^\\W\\d_])', '', s)
    for patron, entero in _ABREVIATURAS:
        s = patron.sub(entero, s)
    return s
_ABREVIATURAS_CERRADAS = [(re.compile('\\bn[úu]m\\.'), 'número'), (re.compile('\\bn\\.[º°o](?=\\s|\\d|$)|\\bn[º°](?=\\s|\\d|$)'), 'número'), (re.compile('\\barts\\.'), 'artículos'), (re.compile('\\bart\\.'), 'artículo'), (re.compile('\\bapdos\\.'), 'apartados'), (re.compile('\\bapdo\\.'), 'apartado'), (re.compile('\\bp[áa]gs\\.'), 'páginas'), (re.compile('\\bp[áa]g\\.'), 'página'), (re.compile('\\bpárr\\.'), 'párrafo'), (re.compile('\\bcap\\.'), 'capítulo'), (re.compile('\\bsec\\.'), 'sección'), (re.compile('\\bfig\\.'), 'figura'), (re.compile('\\bvol\\.'), 'volumen'), (re.compile('\\bed\\.'), 'edición')]

def _expandir_abreviaturas(s: str) -> str:
    for patron, entero in _ABREVIATURAS_CERRADAS:
        s = patron.sub(entero, s)
    return re.sub('\\s+', ' ', s)

def coincide_salvo_abreviatura(cita: str, recuperado: str) -> bool:
    """Public CI documentation."""
    a, b = (_norm(cita), _norm(recuperado))
    if a in b:
        return False
    return _expandir_abreviaturas(a) in _expandir_abreviaturas(b)
_NOTA_ABREVIATURA = 'coincide salvo abreviatura: el texto casa con el del precepto cuando se expanden las abreviaturas; no se da por literal ni se acusa, se coteja a mano contra la pagina'
_NOTA_MOBILIARIO = 'coincide quitando cabeceras y pies de pagina del documento: la cita cruza de pagina'
MINIMO_PALABRAS_SIN_MOBILIARIO = 5
MINIMA_PARTE_SIN_MOBILIARIO = 0.6

@lru_cache(maxsize=512)
def _rx_mobiliario(patrones: tuple[str, ...]):
    return mobiliario.compilar(patrones, _norm)

def mobiliario_de_fichero(con, ruta_relativa: str | None):
    """Public CI documentation."""
    return _rx_mobiliario(mobiliario.patrones_de(con, ruta_relativa))

def mobiliario_de(con, r):
    """Public CI documentation."""
    return mobiliario_de_fichero(con, getattr(r, 'fichero', None))
_NOTA_FILAS = 'coincide leyendo la tabla por filas: el texto del precepto la trae en otro orden de lectura'

def lecturas_por_filas(con, r, recuperado: str | None) -> tuple[str, ...]:
    """Public CI documentation."""
    from . import tablas
    return tuple((tablas.lectura_por_filas(filas) for filas in tablas.filas_para_validar(con, getattr(r, 'fichero', None), getattr(r, 'pagina_inicio', None), getattr(r, 'pagina_fin', None), recuperado)))

def casa_literal(cita: str, recuperado: str, rx=None, por_filas: tuple[str, ...]=()) -> tuple[bool, str | None]:
    """Public CI documentation."""
    a, b = (_norm(cita), _norm(recuperado or ''))
    if a in b:
        return (True, None)
    if rx is not None:
        a2, b2 = (mobiliario.quitar(a, rx), mobiliario.quitar(b, rx))
        if (a2, b2) != (a, b) and len(a2.split()) >= MINIMO_PALABRAS_SIN_MOBILIARIO and (len(a2) >= MINIMA_PARTE_SIN_MOBILIARIO * len(a)) and (a2 in b2):
            return (True, 'mobiliario')
    for lectura in por_filas:
        if len(a.split()) >= MINIMO_PALABRAS_SIN_MOBILIARIO and a in _norm(lectura):
            return (True, 'filas')
    return (False, None)

def _nota_de(como: str | None) -> str | None:
    return {'mobiliario': _NOTA_MOBILIARIO, 'filas': _NOTA_FILAS}.get(como)

def _es_tabla(ident: str | None) -> bool:
    """Public CI documentation."""
    if not ident or consulta.SEP not in ident:
        return False
    return ident.split(consulta.SEP, 1)[1].split('/')[-1].startswith('tabla.')

def _solo_difiere_en_guion(cita: str, recuperado: str) -> bool:
    """Public CI documentation."""
    return _norm(cita, guiones=False) not in _norm(recuperado, guiones=False)

@dataclass
class Hallazgo:
    linea: int
    clase: str
    norma: str | None = None
    referencia: str | None = None
    identificador: str | None = None
    atribuido: str | None = None
    recuperado: str | None = None
    motivo: str | None = None
    ambito: str | None = None
    contexto: str = ''

def _otra_lo_tiene(con, cita, ruta: str, norma_elegida: str, candidatas: tuple | None=None) -> str | None:
    """Public CI documentation."""
    if not ruta:
        return None
    for otra in cita.candidatas if candidatas is None else candidatas:
        if otra == norma_elegida:
            continue
        r = consulta.resolver(con, f'{otra}{consulta.SEP}{ruta}')
        if r.estado == consulta.ENCONTRADO:
            return otra
    return None

def _lo_contiene(con, norma: str, cita: str, fecha: str | None=None) -> bool:
    """Public CI documentation."""
    if RX_ELISION.search(cita):
        return False
    _, r, recuperado = _resolver_ambito(con, norma, fecha)
    return r.estado == consulta.ENCONTRADO and casa_literal(cita, recuperado, mobiliario_de(con, r), lecturas_por_filas(con, r, recuperado))[0]

def _resolver_ambito(con, ident: str, fecha: str | None=None):
    """Public CI documentation."""
    norma, _, ruta = ident.partition(consulta.SEP)
    if fecha and '@' not in norma:
        norma = f'{norma}@{fecha}'
    for cand in consulta.alias_candidatos(norma):
        r0 = consulta.resolver(con, cand)
        if r0.estado not in (consulta.OBRA_AMBIGUA, consulta.NO_CONSTA):
            ident = f'{cand}{consulta.SEP}{ruta}' if ruta else cand
            break
    return (ident, *consulta.texto_de_ambito(con, ident))

def _aviso_multiedicion(con, r) -> str:
    """Public CI documentation."""
    vid = getattr(r, 'version_id', None)
    if not vid:
        return ''
    fila = con.execute('SELECT count(DISTINCT fecha_edicion) n FROM version WHERE obra_id=(SELECT obra_id FROM version WHERE id=?) AND fecha_edicion IS NOT NULL', (vid,)).fetchone()
    if not fila or (fila['n'] or 0) <= 1:
        return ''
    ed = getattr(r, 'version', None)
    return f'. Se comparó contra la {ed}' if ed else '. Se comparó contra una de las ediciones de la obra'
RE_FECHA_DOC = re.compile('\\b(\\d{1,2})\\s+de\\s+([a-záéíóú]+)\\s+de\\s+(20\\d{2})\\b', re.I)
_MESES = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()

def fecha_del_documento(texto: str) -> str | None:
    """Public CI documentation."""
    m = RE_FECHA_DOC.search(chr(10).join(texto.split(chr(10))[:40]))
    if not m:
        return None
    mes = _MESES.index(m.group(2).lower()) + 1 if m.group(2).lower() in _MESES else 0
    return f'{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}' if mes else None
_PROFUNDIDAD_MAXIMA: dict[int, tuple] = {}

def olvidar_cache() -> None:
    """Public CI documentation."""
    _PROFUNDIDAD_MAXIMA.clear()

def profundidad_maxima(con) -> dict:
    """Public CI documentation."""
    guardado = _PROFUNDIDAD_MAXIMA.get(id(con))
    if guardado is None or guardado[0] is not con:
        topes: dict[str, int] = {}
        for ruta, in con.execute('SELECT ruta_estructural FROM precepto'):
            ultimo = ruta.split('/')[-1]
            p = ultimo.split('.')[0]
            n = ultimo.count('.') + 1
            if n > topes.get(p, 0):
                topes[p] = n
        guardado = _PROFUNDIDAD_MAXIMA[id(con)] = (con, topes)
    return guardado[1]
_MARCAS_DE_IDIOMA = {'es': ('de', 'la', 'el', 'que', 'los', 'para', 'con', 'por', 'una', 'del'), 'en': ('the', 'of', 'shall', 'and', 'to', 'in', 'for', 'this', 'be', 'is'), 'fr': ('le', 'les', 'des', 'et', 'pour', 'dans', 'sur', 'est', 'une', 'aux'), 'de': ('der', 'die', 'und', 'von', 'mit', 'den', 'das', 'fur', 'ist', 'im')}
RX_PALABRA = re.compile('[^\\W\\d_]+', re.UNICODE)
_MINIMO_MARCAS = 3
_VENTAJA = 2

def idioma_del_texto(texto: str | None) -> str | None:
    """Public CI documentation."""
    palabras = RX_PALABRA.findall((texto or '').lower())
    if len(palabras) < 8:
        return None
    cuenta = {k: sum((p in ws for p in palabras)) for k, ws in _MARCAS_DE_IDIOMA.items()}
    orden = sorted(cuenta.items(), key=lambda kv: -kv[1])
    (mejor, n), (_, segundo) = (orden[0], orden[1])
    if n < _MINIMO_MARCAS or n < _VENTAJA * segundo:
        return None
    return mejor

def idioma_debil_para_abstenerse(texto: str | None) -> str | None:
    """Public CI documentation."""
    palabras = RX_PALABRA.findall((texto or '').lower())
    if len(palabras) < 3:
        return None
    con_marcas = [k for k, ws in _MARCAS_DE_IDIOMA.items() if any((p in ws for p in palabras))]
    return con_marcas[0] if len(con_marcas) == 1 else None

def por_que_no_se_puede_acusar(con, ident: str, r, idioma_documento: str):
    """Public CI documentation."""
    _, _, ruta = ident.partition(consulta.SEP)
    if ruta:
        ultimo = ruta.split('/')[-1]
        niveles = ultimo.count('.') + 1
        prefijo = ultimo.split('.')[0]
        tope = profundidad_maxima(con).get(prefijo)
        if tope and niveles > tope:
            return f'no verificable: la ruta leida tiene {niveles} niveles y ninguna unidad `{prefijo}.` del corpus pasa de {tope}. La cita no se ha entendido, asi que no se juzga'
    idioma = (r.idioma or '').lower()
    if idioma and idioma not in ('?', '') and (idioma_documento not in idioma):
        return f"no verificable: el ejemplar esta en '{idioma}' y el documento en '{idioma_documento}'; una comparacion literal entre idiomas distintos no sostiene una acusacion"
    return None
_MOTIVO_OCR_DEFECTUOSO = 'no verificable: el ejemplar es un OCR defectuoso y su texto lleva errores de reconocimiento; una cita correcta puede no casar con el. Cotejar contra la pagina impresa'

def _no_acusar_sobre_ocr_defectuoso(con, hallazgos: list[Hallazgo]) -> None:
    """Public CI documentation."""
    for h in hallazgos:
        if h.clase == LITERAL_DISCREPA and h.identificador:
            r = consulta.resolver(con, h.identificador)
            if r.completitud == 'ocr_defectuoso':
                h.clase = NO_COMPARABLE
                h.motivo = _MOTIVO_OCR_DEFECTUOSO

def validar(con, texto: str, fecha: str | None=None, idioma_documento: str='es') -> list[Hallazgo]:
    """Public CI documentation."""
    texto = unicodedata.normalize('NFC', texto)
    lineas = texto.split('\n')
    fecha = fecha or fecha_del_documento(texto)
    citas = contexto.localizar_citas(texto)
    heredables = contexto.normas_heredables(texto)
    candidatas = contexto.candidatas_de_linea(texto)
    por_linea: dict[int, list] = {}
    for c in citas:
        por_linea.setdefault(c.linea, []).append(c)
    out: list[Hallazgo] = []
    for i, ln in enumerate(lineas, 1):
        dentro = [r for m in RE_ENTRECOMILLADO.finditer(ln) for r in [range(m.start(1), m.end(1))]]
        propias = [c for c in por_linea.get(i, []) if not any((c.posicion in d for d in dentro))]
        atras = []
        for k in (i - 1, i - 2):
            if k < 1 or not lineas[k - 1].strip():
                break
            atras = por_linea.get(k) or atras
            if atras:
                break
        for m in RE_ENTRECOMILLADO.finditer(ln):
            cita = m.group(1)
            h = Hallazgo(linea=i, clase=NO_COMPARABLE, atribuido=cita, contexto=ln.strip()[:170])
            if _es_declaracion_de_persona(ln, m.start()):
                h.motivo = 'no verificable: lo entrecomillado es lo que declaro una persona, no texto de una norma. No hay precepto contra el que cotejarlo'
                out.append(h)
                continue
            previas = [c for c in propias if c.posicion < m.start()]
            posteriores = [c for c in propias if c.posicion >= m.end()]
            gobernante = previas[-1] if previas else posteriores[0] if posteriores else atras[-1] if atras else None
            if gobernante is None:
                norma = _norma_unica_en_frase(ln, m.start(), (m.start(1), m.end(1)))
                amb = 'frase'
                if not norma:
                    norma, amb = (heredables.get(i, (None, None))[0], 'parrafo')
                    if not norma:
                        norma, amb = (heredables.get(i, (None, None))[1], 'seccion')
                if not norma:
                    duenos = [n for n in candidatas.get(i, ()) if _lo_contiene(con, n, cita, fecha)]
                    if len(duenos) != 1:
                        h.motivo = 'el texto entrecomillado no va precedido de una cita ni de una norma unica' if not duenos else f'el texto aparece en {len(duenos)} normas de la seccion y no se puede atribuir'
                        out.append(h)
                        continue
                    h.norma, h.ambito, h.clase = (duenos[0], 'texto', LITERAL_OK)
                    h.identificador = duenos[0]
                    out.append(h)
                    continue
                h.norma = norma
                h.ambito = amb
                ident, r, recuperado = _resolver_ambito(con, norma, fecha)
                h.identificador = ident
                if r.estado != consulta.ENCONTRADO:
                    h.motivo = f"{r.estado}: {(r.detalle or '')[:110]}"
                elif RX_ELISION.search(cita):
                    if _elision_casa(cita, recuperado):
                        h.clase = NO_COMPARABLE
                        h.motivo = _elision_motivo(con, r, ident, cita, recuperado)
                    elif amb != 'frase':
                        h.motivo = _POR_HERENCIA.format(amb, norma)
                    else:
                        h.clase = LITERAL_DISCREPA
                        h.motivo = _DISCREPA_ELISION
                elif (casa := casa_literal(cita, recuperado, mobiliario_de(con, r), lecturas_por_filas(con, r, recuperado)))[0]:
                    h.clase = LITERAL_OK
                    if casa[1]:
                        h.motivo = _nota_de(casa[1])
                    elif _solo_difiere_en_guion(cita, recuperado):
                        h.motivo = _NOTA_GUION
                elif amb != 'frase':
                    h.motivo = _POR_HERENCIA.format(amb, norma)
                elif coincide_salvo_abreviatura(cita, recuperado):
                    h.clase = NO_COMPARABLE
                    h.motivo = _NOTA_ABREVIATURA
                else:
                    h.clase = LITERAL_DISCREPA
                    h.motivo = 'el texto entrecomillado no aparece en el documento al que se atribuye'
                if h.clase == LITERAL_DISCREPA:
                    h.motivo += _aviso_multiedicion(con, r)
                out.append(h)
                continue
            if previas and gobernante is previas[-1]:
                a_cita, b_cita = _frase_de(ln, m.start())
                if not a_cita <= gobernante.posicion < b_cita:
                    tramo = _frase_de(ln, gobernante.posicion)
                    hermanas = [c for c in previas if _frase_de(ln, c.posicion) == tramo]
                    if len(hermanas) > 1:
                        duenos = []
                        for c in hermanas:
                            if c.ambigua or not c.identificador:
                                continue
                            _, _r, _rec = _resolver_ambito(con, c.identificador, fecha)
                            if _r.estado == consulta.ENCONTRADO and casa_literal(cita, _rec or '', mobiliario_de(con, _r), lecturas_por_filas(con, _r, _rec))[0]:
                                duenos.append(c)
                        if len(duenos) == 1:
                            gobernante = duenos[0]
                        else:
                            h.norma = gobernante.norma
                            h.referencia = gobernante.referencia
                            h.ambito = gobernante.ambito
                            h.motivo = f'la frase de la cita no nombra precepto y la anterior nombra {len(hermanas)}: la atribucion no esta determinada'
                            out.append(h)
                            continue
            h.norma = gobernante.norma
            h.referencia = gobernante.referencia
            h.ambito = gobernante.ambito
            if gobernante.ambigua or not gobernante.identificador:
                h.motivo = gobernante.motivo or 'atribucion no determinada'
                out.append(h)
                continue
            ambito_g = 'entrada' if gobernante.por_entrada else gobernante.ambito
            ident, r, recuperado = _resolver_ambito(con, gobernante.identificador, fecha)
            h.identificador = ident
            idioma_cita = idioma_del_texto(cita)
            sin_base = por_que_no_se_puede_acusar(con, ident, r, idioma_cita or idioma_documento)
            if not sin_base and idioma_cita is None:
                debil = idioma_debil_para_abstenerse(cita)
                if debil and debil != idioma_documento:
                    sin_base = por_que_no_se_puede_acusar(con, ident, r, debil)
            if sin_base:
                if r.estado == consulta.ENCONTRADO and (not RX_ELISION.search(cita)) and (casa := casa_literal(cita, recuperado, mobiliario_de(con, r), lecturas_por_filas(con, r, recuperado)))[0]:
                    h.clase = LITERAL_OK
                    h.motivo = _nota_de(casa[1]) if casa[1] else _NOTA_GUION if _solo_difiere_en_guion(cita, recuperado) else None
                else:
                    h.motivo = sin_base
                out.append(h)
                continue
            if r.estado == consulta.PRECEPTO_INEXISTENTE:
                otra = _otra_lo_tiene(con, gobernante, gobernante.ruta, gobernante.norma)
                if ambito_g != 'frase':
                    h.motivo = _POR_HERENCIA.format(ambito_g, gobernante.norma)
                elif otra:
                    h.motivo = f'atribuido a {gobernante.norma}, que no tiene ese precepto, pero {otra} si lo tiene: la atribucion no esta determinada'
                else:
                    h.clase = PRECEPTO_NO_EXISTE
                    h.motivo = 'el precepto no aparece en el ejemplar completo'
            elif r.estado != consulta.ENCONTRADO:
                h.motivo = f"{r.estado}: {(r.detalle or '')[:110]}"
            elif RX_ELISION.search(cita):
                if _elision_casa(cita, recuperado):
                    h.clase = NO_COMPARABLE
                    h.motivo = _elision_motivo(con, r, ident, cita, recuperado)
                elif ambito_g != 'frase':
                    h.motivo = _POR_HERENCIA.format(ambito_g, gobernante.norma)
                elif _es_tabla(ident):
                    h.clase = CITA_A_TABLA
                    h.motivo = _MOTIVO_TABLA
                else:
                    h.clase = LITERAL_DISCREPA
                    h.recuperado = _recorte(_norm(recuperado), _norm(cita))
                    h.motivo = _DISCREPA_ELISION
            elif (casa := casa_literal(cita, recuperado, mobiliario_de(con, r), lecturas_por_filas(con, r, recuperado)))[0]:
                h.clase = LITERAL_OK
                if casa[1]:
                    h.motivo = _nota_de(casa[1])
                elif _solo_difiere_en_guion(cita, recuperado):
                    h.motivo = _NOTA_GUION
            elif ambito_g != 'frase':
                h.motivo = _POR_HERENCIA.format(ambito_g, gobernante.norma)
            else:
                veredicto = _corchete_editorial(cita, recuperado) if RX_CORCHETE_EDITORIAL.search(cita) else None
                if veredicto == 'confirma':
                    h.clase = LITERAL_OK
                    h.motivo = _NOTA_CORCHETE_CONFIRMA
                elif veredicto == 'sentido':
                    h.clase = NO_COMPARABLE
                    h.motivo = _NOTA_CORCHETE_SENTIDO
                elif veredicto == 'abstiene':
                    h.clase = NO_COMPARABLE
                    h.motivo = 'adaptacion editorial declarada: la divergencia cae dentro del corchete editorial de la cita. No se acusa; cotejar a mano contra la pagina'
                elif _es_tabla(ident):
                    h.clase = CITA_A_TABLA
                    h.motivo = _MOTIVO_TABLA
                elif coincide_salvo_abreviatura(cita, recuperado):
                    h.clase = NO_COMPARABLE
                    h.motivo = _NOTA_ABREVIATURA
                else:
                    h.clase = LITERAL_DISCREPA
                    h.recuperado = _recorte(_norm(recuperado), _norm(cita))
                    h.motivo = 'el texto entrecomillado no aparece literalmente en el precepto al que se atribuye'
                    if RX_CORCHETE_EDITORIAL.search(cita):
                        h.motivo += '. La cita lleva corchete editorial, con el que el autor declara que ha adaptado el original: cotejala a mano contra la pagina'
            if h.clase == LITERAL_DISCREPA:
                h.motivo = (h.motivo or '') + _aviso_multiedicion(con, r)
            out.append(h)
        entrecomilladas = bool(RE_ENTRECOMILLADO.search(ln))
        for c in propias:
            if entrecomilladas or c.ambigua or (not c.identificador) or (not c.ruta):
                continue
            if c.ambito != 'frase' or c.por_entrada:
                continue
            ident, r, _ = _resolver_ambito(con, c.identificador, fecha)
            if por_que_no_se_puede_acusar(con, ident, r, idioma_documento):
                continue
            if r.estado == consulta.PRECEPTO_INEXISTENTE and (not _otra_lo_tiene(con, c, c.ruta, c.norma)):
                out.append(Hallazgo(linea=i, clase=PRECEPTO_NO_EXISTE, norma=c.norma, referencia=c.referencia, identificador=ident, ambito=c.ambito, motivo='el precepto no aparece en el ejemplar completo', contexto=c.contexto))
    _no_acusar_sobre_ocr_defectuoso(con, out)
    return out

def _recorte(recuperado: str, cita: str) -> str:
    pal = cita.split()
    for k in range(min(10, len(pal)), 2, -1):
        i = recuperado.find(' '.join(pal[:k]))
        if i >= 0:
            return recuperado[i:i + len(cita) + 60]
    return recuperado[:200]

def _corchete_altera_sentido(cita: str) -> bool:
    """Public CI documentation."""
    for m in RX_CORCHETE_EDITORIAL.finditer(cita):
        contenido = m.group(0)[1:-1].lower()
        palabras = re.findall('[a-záéíóúñ]+', contenido)
        if any((p in _TERMINOS_QUE_ALTERAN_SENTIDO for p in palabras)):
            return True
    return False

def _corchete_editorial(cita: str, recuperado: str) -> str | None:
    """Public CI documentation."""
    if _norm(RX_CORCHETE_COME_ESPACIO.sub('', cita)) in _norm(recuperado):
        if _corchete_altera_sentido(cita):
            return 'sentido'
        return 'confirma'
    rec = _norm(recuperado)
    pos = 0
    for frag in RX_CORCHETE_EDITORIAL.split(cita):
        fn = _norm(frag)
        if not fn:
            continue
        idx = rec.find(fn, pos)
        if idx < 0:
            return None
        pos = idx + len(fn)
    return 'abstiene'

def _elision_casa(cita: str, recuperado: str) -> bool:
    """Public CI documentation."""
    rec = _norm(recuperado)
    pos = 0
    for frag in RX_ELISION.split(cita):
        fn = _norm(frag)
        if not fn:
            continue
        idx = rec.find(fn, pos)
        if idx < 0:
            return False
        pos = idx + len(fn)
    return True

def _subarbol(con, version_id: int, ruta: str) -> list:
    """Public CI documentation."""
    if version_id is None:
        return []
    if ruta:
        return con.execute('SELECT ruta_estructural, texto_literal FROM precepto WHERE version_id=? AND (ruta_estructural=? OR ruta_estructural LIKE ? OR ruta_estructural LIKE ?) ORDER BY orden', (version_id, ruta, ruta + '.%', ruta + '/%')).fetchall()
    return con.execute('SELECT ruta_estructural, texto_literal FROM precepto WHERE version_id=? ORDER BY orden', (version_id,)).fetchall()

def _elision_motivo(con, r, ident: str, cita: str, recuperado: str) -> str:
    """Public CI documentation."""
    rec = _norm(recuperado)
    marcas: list[tuple[str, int, int]] = []
    pos = 0
    for frag in RX_ELISION.split(cita):
        fn = _norm(frag)
        if not fn:
            continue
        idx = rec.find(fn, pos)
        if idx < 0:
            idx = pos
        marcas.append((fn, idx, idx + len(fn)))
        pos = idx + len(fn)
    posiciones = ', '.join((str(m[1]) for m in marcas))
    saltos = [marcas[k + 1][1] - marcas[k][2] for k in range(len(marcas) - 1)]
    salto = max(saltos) if saltos else 0
    _, ruta = consulta.partir_identificador(ident)
    unidades = [(row['ruta_estructural'], _norm(row['texto_literal'] or '')) for row in _subarbol(con, getattr(r, 'version_id', None), ruta)]
    rutas_frag = []
    for fn, _i, _f in marcas:
        candidatas = [ru for ru, tn in unidades if fn in tn]
        rutas_frag.append(max(candidatas, key=len) if candidatas else None)
    presentes = [ru for ru in rutas_frag if ru]
    distintos = len(set(presentes)) > 1
    sub = f" y en subapartados distintos ({', '.join(dict.fromkeys(presentes))})" if distintos else ''
    return f'fragmentos de la cita (con elisión declarada) localizados en el precepto en las posiciones {posiciones} del texto normalizado, con un salto máximo entre fragmentos de {salto} caracteres{sub}: la recomposición NO está verificada, cotejar a mano contra la página'

def _frase_de(linea: str, pos: int) -> tuple[int, int]:
    """Public CI documentation."""
    for a, b in contexto.frases(linea):
        if a <= pos < b:
            return (a, b)
    return (0, len(linea))

def _es_declaracion_de_persona(linea: str, pos: int) -> bool:
    """Public CI documentation."""
    a, _ = _frase_de(linea, pos)
    ventana = linea[a:pos]
    testimonial = [m.end() for m in RX_VERBO_TESTIMONIAL.finditer(ventana)]
    if not testimonial:
        return False
    normativo = [m.end() for m in RX_VERBO_NORMATIVO.finditer(ventana)]
    return not normativo or max(testimonial) > max(normativo)

def _norma_unica_en_frase(linea: str, pos: int, hueco: tuple[int, int]) -> str | None:
    """Public CI documentation."""
    for ini, fin in contexto.frases(linea):
        if ini <= pos < fin:
            n = list(dict.fromkeys((m.group(0) for m in contexto.RE_NORMA.finditer(linea[ini:fin]) if not hueco[0] <= ini + m.start() < hueco[1])))
            return n[0] if len(n) == 1 else None
    return None
CENSO_COMPROBADA = 'COMPROBADA'
CENSO_NO_COMPARABLE = 'NO_COMPARABLE'
CENSO_SIN_RUTA = 'SIN_RUTA'
CENSO_SIN_ALIAS = 'SIN_ALIAS'
CENSO_AMBIGUA = 'AMBIGUA'
CENSO_NO_RECUPERABLE = 'NO_RECUPERABLE'
CENSO_PRECEPTO_INEXISTENTE = 'PRECEPTO_INEXISTENTE'
CENSO_DISCREPA = 'DISCREPA'
CENSO_TABLA = 'TABLA_SE_LEE_DEL_PDF'
CATEGORIAS_DEL_CENSO = frozenset((CENSO_COMPROBADA, CENSO_NO_COMPARABLE, CENSO_SIN_RUTA, CENSO_SIN_ALIAS, CENSO_AMBIGUA, CENSO_NO_RECUPERABLE, CENSO_PRECEPTO_INEXISTENTE, CENSO_DISCREPA, CENSO_TABLA))
CATEGORIAS_QUE_ACUSAN = frozenset((CENSO_PRECEPTO_INEXISTENTE, CENSO_DISCREPA))
ESTADOS_DE_CONSULTA = frozenset((consulta.ENCONTRADO, consulta.PRECEPTO_INEXISTENTE, consulta.FUERA_DE_ALCANCE, consulta.DERECHOS_RESTRINGIDOS, consulta.NO_CONSTA, consulta.OBRA_AMBIGUA, consulta.EDICION_AMBIGUA, consulta.RUTA_AMBIGUA, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO))
_CATEGORIA_DE_CLASE = {LITERAL_OK: CENSO_COMPROBADA, LITERAL_DISCREPA: CENSO_DISCREPA, PRECEPTO_NO_EXISTE: CENSO_PRECEPTO_INEXISTENTE, NO_COMPARABLE: CENSO_NO_COMPARABLE, PARAFRASIS: CENSO_COMPROBADA, CITA_A_TABLA: CENSO_TABLA}

@dataclass
class FilaDelCenso:
    """Public CI documentation."""
    linea: int
    posicion: int
    referencia: str
    norma: str | None = None
    identificador: str | None = None
    categoria: str = ''
    estado: str | None = None
    motivo: str = ''
    contexto: str = ''
    clase_validador: str | None = None
    cualificador: str | None = None

def referencias_vistas(texto: str) -> list:
    """Public CI documentation."""
    return [c for c in contexto.localizar_citas(texto) if c.ambito == 'frase' and c.referencia]

def identificadores_defectuosos(con, texto: str):
    """Public CI documentation."""
    return identificadores.comprobar(con, texto)

def referencias_fuera_del_censo(texto: str) -> list:
    """Public CI documentation."""
    return [c for c in contexto.localizar_citas(texto) if c.referencia and c.ambito != 'frase' and (c.motivo != contexto.MOTIVO_NOMBRE_DE_DOCUMENTO)]
_PREFIJO_CANDIDATO = {'anexo': 'anexo', 'anexos': 'anexo', 'apendice': 'apend', 'apéndice': 'apend', 'apéndices': 'apend', 'apendices': 'apend', 'clausula': 'ap', 'cláusula': 'ap', 'cláusulas': 'ap', 'clausulas': 'ap', 'tabla': 'tabla', 'tablas': 'tabla', 'articulo': 'art', 'artículo': 'art', 'artículos': 'art', 'articulos': 'art', 'apartado': 'ap', 'apartados': 'ap'}

def _rutas_candidatas(referencia: str) -> list[str]:
    """Public CI documentation."""
    palabras = (referencia or '').split()
    if len(palabras) < 2:
        return []
    pref = _PREFIJO_CANDIDATO.get(palabras[0].lower())
    if not pref:
        return []
    rotulo = palabras[1].strip('.,;:')
    if not re.fullmatch('[\\wIVXLC][\\w.\\-]*', rotulo):
        return []
    return list(dict.fromkeys([f'{pref}.{rotulo}', f'{pref}.{rotulo.upper()}']))

def _citas_atras(lineas: list[str], por_linea: dict, i: int) -> list:
    """Public CI documentation."""
    atras: list = []
    for k in (i - 1, i - 2):
        if k < 1 or not lineas[k - 1].strip():
            break
        atras = por_linea.get(k) or atras
        if atras:
            break
    return atras

def _linea_del_entrecomillado(lineas: list[str], i: int) -> int | None:
    """Public CI documentation."""
    if RE_ENTRECOMILLADO.search(lineas[i - 1]):
        return i
    for k in (i - 1, i - 2):
        if k < 1 or not lineas[k - 1].strip():
            return None
        if RE_ENTRECOMILLADO.search(lineas[k - 1]):
            return k
    return None

def _atribucion_del_entrecomillado(con, ln: str, propias: list, atras: list, c, fecha, discute=None) -> tuple[str, str]:
    """Public CI documentation."""
    for m in RE_ENTRECOMILLADO.finditer(ln):
        previas = [x for x in propias if x.posicion < m.start()]
        posteriores = [x for x in propias if x.posicion >= m.end()]
        g = previas[-1] if previas else posteriores[0] if posteriores else atras[-1] if atras else None
        if g is None or (g.linea, g.posicion) == (c.linea, c.posicion):
            continue
        literal = ln[m.start(1):m.end(1)]
        a_fr, b_fr = _frase_de(ln, m.start())
        misma_frase = a_fr <= g.posicion < b_fr
        if g.identificador and misma_frase and (discute is not None) and discute(g):
            return (CENSO_NO_COMPARABLE, f'el texto entrecomillado lo gobierna `{g.referencia}`, cuya atribucion a una norma no esta determinada: aqui no se compara literal')
        if g.identificador and misma_frase:
            return (CENSO_NO_COMPARABLE, f'el texto entrecomillado lo gobierna `{g.referencia}` ({g.norma}), en la misma frase: no es este precepto quien responde de el, y aqui no se compara literal')
        gruta = consulta.ruta_de_cita(g.referencia)
        if gruta:
            _, rg, rec = _resolver_ambito(con, f'{c.norma}{consulta.SEP}{gruta}', fecha)
            if rg.estado == consulta.ENCONTRADO and casa_literal(literal, rec or '', mobiliario_de(con, rg), lecturas_por_filas(con, rg, rec))[0]:
                return (CENSO_NO_COMPARABLE, f'el texto entrecomillado aparece en `{g.referencia}` de {c.norma}, precepto que consta en el ejemplar pero queda fuera del denominador (campana aparte): no es este precepto quien responde de el')
        normas_frase = list(dict.fromkeys((mm.group(0) for mm in contexto.RE_NORMA.finditer(ln[a_fr:b_fr]))))
        apartado_suelto = 'apartado suelto' in (getattr(g, 'motivo', '') or '')
        if misma_frase and getattr(g, 'ambigua', False) and (len(normas_frase) >= 2) and (not apartado_suelto):
            return (CENSO_NO_COMPARABLE, f"`{g.referencia}` es una remision ambigua entre {len(normas_frase)} normas de la frase ({', '.join(normas_frase)}): la atribucion no esta determinada. No es una autocita sin norma")
        if misma_frase:
            return (CENSO_NO_COMPARABLE, f'el texto entrecomillado es una autocita del informe (`{g.referencia}`) sin norma detras: no hay precepto contra el que compararlo')
        break
    return (CENSO_COMPROBADA, 'el precepto existe en el ejemplar y se recupera su texto; el entrecomillado de la linea no se atribuye a otra cita')
_DIVISIONES = frozenset({'anexo', 'apend', 'capitulo', 'titulo', 'seccion', 'parte', 'libro'})
RX_PEGADA_POR_DE = re.compile('\\s*,?\\s*(?:de|del)\\s+', re.I)

def _es_division(ruta: str | None) -> bool:
    return bool(ruta) and ruta.split('/')[0].split('.')[0] in _DIVISIONES

def _anexo_de_eudralex_ajeno(c, ln: str, numeros: set[str]) -> bool:
    """Public CI documentation."""
    m = re.fullmatch('anexo\\.(\\d+)', c.ruta or '')
    if not m or m.group(1) not in numeros or 'eudralex' in (c.norma or '').lower():
        return False
    return not RX_PEGADA_POR_DE.match(ln[c.posicion + len(c.referencia):])

def _norma_ligada(c, ln: str) -> bool:
    """Public CI documentation."""
    resto = ln[c.posicion + len(c.referencia):]
    propia = re.escape(c.norma) if c.norma else '(?!x)x'
    return bool(re.match(f'\\s*,?\\s*(?:de|del)\\s+(?:la\\s+|el\\s+|las\\s+|los\\s+)?(?:norma\\b|est[aá]ndar\\b|{propia})', resto))

def _atribucion_discutida(con, c, ln: str, fecha, numeros: set[str], normas_del_documento: tuple=()) -> str | None:
    """Public CI documentation."""
    if c.ambigua or not c.identificador or c.ambito != 'frase' or c.por_entrada:
        return None
    if numeros and _anexo_de_eudralex_ajeno(c, ln, numeros):
        return f'el informe nombra en otra frase el `{c.referencia}` de EudraLex Volumen 4 y aqui la frase nombra {c.norma}: la atribucion no esta determinada'
    if _es_division(c.ruta) and (not _norma_ligada(c, ln)):
        _, r, _ = _resolver_ambito(con, c.identificador, fecha)
        if r.estado != consulta.ENCONTRADO:
            otra, donde = (_otra_lo_tiene(con, c, c.ruta, c.norma), 'la misma seccion')
            if not otra:
                otra = _otra_lo_tiene(con, c, c.ruta, c.norma, normas_del_documento)
                donde = 'otro punto del documento'
            if otra:
                return f'`{c.ruta}` no se localiza en {c.norma} ({r.estado}) y {otra}, nombrada en {donde}, si la contiene, y la norma no esta ligada a la referencia: la atribucion no esta determinada'
    return None

def censo(con, texto: str, fecha: str | None=None, idioma_documento: str='es', hallazgos: list[Hallazgo] | None=None) -> list[FilaDelCenso]:
    """Public CI documentation."""
    texto = unicodedata.normalize('NFC', texto)
    fecha = fecha or fecha_del_documento(texto)
    lineas = texto.split('\n')
    vistas = referencias_vistas(texto)
    if hallazgos is None:
        hallazgos = validar(con, texto, fecha, idioma_documento)
    por_linea_citas: dict[int, list] = {}
    for cc in contexto.localizar_citas(texto):
        por_linea_citas.setdefault(cc.linea, []).append(cc)
    numeros_eudralex = {m.group(1) for m in contexto.RE_NOMBRE_CON_ANEXO.finditer(texto)}
    normas_del_documento = tuple(dict.fromkeys((m.group(0) for m in contexto.RE_NORMA.finditer(texto))))
    ya_dicho: dict[tuple[int, str], list[Hallazgo]] = {}
    for h in hallazgos:
        if h.referencia:
            ya_dicho.setdefault((h.linea, h.referencia), []).append(h)
    filas: list[FilaDelCenso] = []
    for c in vistas:
        f = FilaDelCenso(linea=c.linea, posicion=c.posicion, referencia=c.referencia, norma=c.norma, identificador=c.identificador, contexto=c.contexto)
        pendientes = ya_dicho.get((c.linea, c.referencia))
        discutida = _atribucion_discutida(con, c, lineas[c.linea - 1], fecha, numeros_eudralex, normas_del_documento)
        if pendientes:
            h = pendientes.pop(0)
            f.clase_validador = h.clase
            if h.clase not in _CATEGORIA_DE_CLASE:
                raise ValueError(f'clase del validador sin categoria de censo: {h.clase!r}')
            if discutida and h.clase == NO_COMPARABLE:
                f.categoria = CENSO_AMBIGUA
                f.motivo = discutida
            else:
                f.categoria = _CATEGORIA_DE_CLASE[h.clase]
                f.identificador = h.identificador or c.identificador
                f.motivo = h.motivo or _motivo_de_clase(h.clase)
                if h.identificador:
                    f.estado = consulta.resolver(con, h.identificador).estado
        elif c.ambigua:
            f.categoria = CENSO_AMBIGUA
            f.motivo = c.motivo or 'la cita no se resuelve a una sola norma: no hay contra que comprobarla'
        elif discutida:
            f.categoria = CENSO_AMBIGUA
            f.motivo = discutida
        elif not c.identificador:
            f.categoria = CENSO_SIN_ALIAS
            f.motivo = 'la frase determina la norma pero la base no le conoce identificador: no hay obra contra la que resolver'
        elif not c.ruta:
            promovida = None
            for cand in _rutas_candidatas(c.referencia):
                ident, r, _ = _resolver_ambito(con, f'{c.norma}{consulta.SEP}{cand}', fecha)
                if r.estado == consulta.ENCONTRADO:
                    promovida = (ident, r)
                    break
            if promovida:
                ident, r = promovida
                unidad = ident.split(consulta.SEP)[-1]
                f.identificador, f.estado = (ident, r.estado)
                if _linea_del_entrecomillado(lineas, c.linea):
                    f.categoria = CENSO_NO_COMPARABLE
                    f.motivo = f'el precepto existe y se recupera por una ruta candidata (`{unidad}`); el texto entrecomillado de la linea se atribuye a otra cita, asi que aqui no se compara literal'
                else:
                    f.categoria = CENSO_COMPROBADA
                    f.motivo = f'el traductor no dio ruta, pero la referencia resuelve a `{unidad}`: el precepto existe en el ejemplar y se recupera su texto'
            else:
                _, r_obra, _ = _resolver_ambito(con, c.norma, fecha)
                f.categoria = CENSO_SIN_RUTA
                f.estado = r_obra.estado
                f.motivo = f'se reconoce la norma (obra: {r_obra.estado}) pero no la unidad citada: `{c.referencia}` no se traduce a ruta estructural'
        else:
            ident, r, _ = _resolver_ambito(con, c.identificador, fecha)
            f.identificador, f.estado = (ident, r.estado)
            detalle = ' '.join((r.detalle or '').split())[:160]
            if r.estado == consulta.ENCONTRADO:
                lq = _linea_del_entrecomillado(lineas, c.linea)
                if lq:
                    ln = lineas[lq - 1]
                    dentro = [range(mm.start(1), mm.end(1)) for mm in RE_ENTRECOMILLADO.finditer(ln)]
                    propias = [x for x in por_linea_citas.get(lq, []) if not any((x.posicion in d for d in dentro))]
                    atras = _citas_atras(lineas, por_linea_citas, lq)
                    f.categoria, f.motivo = _atribucion_del_entrecomillado(con, ln, propias, atras, c, fecha, discute=lambda g: _atribucion_discutida(con, g, lineas[g.linea - 1], fecha, numeros_eudralex, normas_del_documento))
                else:
                    f.categoria = CENSO_COMPROBADA
                    f.motivo = 'el precepto existe en el ejemplar y se recupera su texto'
            elif r.estado == consulta.PRECEPTO_INEXISTENTE and c.por_entrada:
                f.categoria = CENSO_NO_COMPARABLE
                f.motivo = 'atribuida por la entrada de bibliografia, no por su frase: el ejemplar no tiene esa unidad, pero la atribucion esta supuesta y no se acusa'
            elif r.estado == consulta.PRECEPTO_INEXISTENTE:
                f.categoria = CENSO_PRECEPTO_INEXISTENTE
                f.motivo = detalle or 'el precepto no aparece en el ejemplar completo'
            elif r.estado == consulta.NO_CONSTA and (canonico := consulta.obra_por_designacion(con, c.norma)):
                rc = consulta.resolver(con, canonico)
                f.categoria = CENSO_SIN_ALIAS
                f.identificador = canonico
                f.estado = rc.estado
                f.motivo = f'la obra consta en la base como `{canonico}` (estado {rc.estado}) pero ninguna fila de alias enlaza la cita `{c.norma}` con ella: falta el alias, no la obra'
            elif r.estado in ESTADOS_DE_CONSULTA:
                f.categoria = CENSO_NO_RECUPERABLE
                f.motivo = f'{r.estado}: {detalle}' if detalle else r.estado
            else:
                raise ValueError(f'estado de consulta desconocido: {r.estado!r} sobre {ident!r}')
        if c.cualificador:
            f.cualificador = c.cualificador
            unidad = f.identificador.split(consulta.SEP)[-1] if f.identificador else c.ruta or 'la ruta'
            f.motivo = f'{f.motivo} [la cita nombra {c.cualificador} y la ruta `{unidad}` no la recoge: lo comprobado es la unidad padre, no {c.cualificador}]'.strip()
        if f.categoria not in CATEGORIAS_DEL_CENSO:
            raise ValueError(f'fila del censo sin categoria cerrada: {f!r}')
        filas.append(f)
    return filas

def _motivo_de_clase(clase: str) -> str:
    """Public CI documentation."""
    return {LITERAL_OK: 'el texto entrecomillado aparece literalmente en el precepto', PARAFRASIS: 'parafrasis: no hay literal que comparar, solo existencia'}.get(clase, 'sin motivo declarado por el validador')

def resumen_del_censo(filas: list[FilaDelCenso]) -> dict[str, int]:
    """Public CI documentation."""
    cuenta: dict[str, int] = {}
    for f in filas:
        clave = f'{f.categoria}({f.estado})' if f.categoria == CENSO_NO_RECUPERABLE else f.categoria
        cuenta[clave] = cuenta.get(clave, 0) + 1
    return dict(sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0])))
