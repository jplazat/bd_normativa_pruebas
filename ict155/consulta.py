"""Resolucion de identificadores y busqueda.

La regla que manda: nunca se responde "no existe" sobre un documento que no se
ha ingerido. El sistema distingue estructuralmente tres cosas distintas, y
confundir la segunda con la tercera convierte al validador en una fabrica de
falsos negativos.
"""
from __future__ import annotations
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date
from . import config, superindices
from .ruta import sin_libro_primero
ENCONTRADO = 'ENCONTRADO'
PRECEPTO_INEXISTENTE = 'PRECEPTO_INEXISTENTE'
FUERA_DE_ALCANCE = 'FUERA_DE_ALCANCE'
DERECHOS_RESTRINGIDOS = 'DERECHOS_RESTRINGIDOS'
NO_CONSTA = 'NO_CONSTA_EN_BIBLIOTECA'
OBRA_AMBIGUA = 'OBRA_AMBIGUA'
EDICION_AMBIGUA = 'EDICION_AMBIGUA'
RUTA_AMBIGUA = 'RUTA_AMBIGUA'
CONTENIDO_EN_ANCESTRO = 'CONTENIDO_EN_ANCESTRO'
REPRODUCIBLES = ('publico', 'licenciado')

def _publicada_desde(edicion: str) -> str:
    """La fecha mas temprana en la que consta que una edicion ya existia.

    De un nombre de fichero solo se saca el ano. Suponer el 1 de enero pondria
    una reescritura en vigor once meses antes de lo demostrable, que es
    exactamente el error que la regla quiere evitar. Con ano a secas se toma el
    final del ano; con fecha completa, la fecha.
    """
    return f'{edicion}-12-31' if len(edicion) == 4 else edicion
RX_FECHA_CITA = re.compile('^\\d{4}-\\d{2}-\\d{2}$')
RX_ANIO_CITA = re.compile('^\\d{4}$')

def es_anio(fecha: str | None) -> bool:
    return bool(RX_ANIO_CITA.match(fecha or ''))

def ruta_efectiva(con: sqlite3.Connection, version_id: int, ruta: str) -> str:
    """`libro.1/X` es `X` en una obra con libros (el primero no lleva prefijo), pero solo si `libro.1/X` no existe y `X`
    si. Cualquier otra ruta queda como esta."""
    alt = sin_libro_primero(ruta)
    if alt is None:
        return ruta

    def existe(r: str) -> bool:
        return con.execute('SELECT 1 FROM precepto WHERE version_id=? AND ruta_estructural=? LIMIT 1', (version_id, r)).fetchone() is not None
    return alt if not existe(ruta) and existe(alt) else ruta

def fecha_bien_escrita(fecha: str | None) -> bool:
    """AAAA-MM-DD y una fecha que existe. Lo mismo vale aqui y en la linea de
    ordenes, que rechaza antes de consultar."""
    if not RX_FECHA_CITA.match(fecha or ''):
        return False
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return False
    return True
LOCALIZADO_SIN_TEXTO = 'LOCALIZADO_SIN_TEXTO'
MODO_TEXTO = 'texto'
MODO_LOCALIZAR = 'localizar'
PRELACION = ('capa_texto', 'transcripcion_verificada', 'ocr')
FUERZA = {'vinculante': 'OBLIGA por si misma', 'vinculante_por_remision': 'OBLIGA por remision de una norma', 'orientativo': 'ORIENTA, no obliga', 'prueba_documental': 'PRUEBA un hecho, no establece una regla', 'indeterminado': 'CARACTER JURIDICO SIN VERIFICAR: nadie ha comprobado si obliga o solo orienta'}
AUTORIDAD = {'capa_texto': 'texto nativo del PDF', 'transcripcion_verificada': 'transcrito a mano y cotejado contra el original', 'ocr': 'RECONOCIMIENTO OPTICO: puede contener errores de caracter. No citar como literal sin cotejar la pagina'}
NOMBRE_COMPLETITUD = {'completa': 'COMPLETA', 'parcial': 'PARCIAL', 'extracto': 'EXTRACTO', 'preview': 'VISTA PREVIA', 'ocr_defectuoso': 'OCR DEFECTUOSO'}

def naturaleza_del_texto(etiqueta: str | None, completitud: str | None, metodo: str | None=None) -> str | None:
    """Que es el texto de un precepto cuando NO es el de la capa de texto de un ejemplar completo del documento (12-oct-2026:
    `normativa_cita("EN 13486:2023::ap.4")` ponia «TEXTO LITERAL» a una ficha en espanol escrita por ICT155, mezcla de resumen y
    frases inglesas entrecomilladas). None si lo es. Lo dicen la etiqueta de la version («transcripcion verificada»,
    «reconocimiento optico»), el metodo de extraccion del precepto y la completitud del ejemplar."""
    e = (etiqueta or '').casefold()
    partes = []
    if e.startswith('transcripcion') or metodo == 'transcripcion_verificada':
        partes.append('transcripción de ICT155, NO es el literal de la norma: solo lo entrecomillado es literal')
    if e.startswith('reconocimiento') or metodo == 'ocr':
        partes.append('reconocimiento óptico: puede tener errores de lectura')
    if completitud and completitud != 'completa':
        if completitud == 'ocr_defectuoso':
            partes.append('ejemplar con OCR DEFECTUOSO: puede tener errores de lectura')
        else:
            partes.append(f'ejemplar {NOMBRE_COMPLETITUD.get(completitud, completitud.upper())}: no es la norma entera')
    return '; '.join(partes) or None

@dataclass
class Respuesta:
    estado: str
    identificador: str | None = None
    etiqueta_humana: str | None = None
    titulo: str | None = None
    texto_literal: str | None = None
    obra: str | None = None
    obra_titulo: str | None = None
    version: str | None = None
    version_id: int | None = None
    fecha_consolidacion: str | None = None
    idioma: str | None = None
    completitud: str | None = None
    fichero: str | None = None
    pagina_inicio: int | None = None
    pagina_fin: int | None = None
    marca_consolidacion: str | None = None
    reproducible: bool = True
    metodo_extraccion: str | None = None
    regimen: str | None = None
    caracter_juridico: str | None = None
    caracter_juridico_fundamento: str | None = None
    emisor: str | None = None
    detalle: str | None = None
    candidatos: list | None = None
    ambito_pedido: str | None = None
    ambito_localizado: str | None = None
    preceptos_localizados: int = 0
    naturaleza_del_texto: str | None = None
    calidad_textual: list[dict] | None = None

    @property
    def paginas(self) -> str:
        """Donde cotejar: intervalo cuando cruza pagina, numero cuando no.

        Los preceptos que cruzan pagina son MAYORIA en este corpus (anchura
        mediana de dos paginas, maxima de doce), asi que devolver una sola es
        falso la mayor parte del tiempo y manda al revisor a media cita.
        """
        if self.pagina_inicio is None:
            return ''
        if self.pagina_fin and self.pagina_fin != self.pagina_inicio:
            return f'paginas {self.pagina_inicio} a {self.pagina_fin}'
        return f'pagina {self.pagina_inicio}'

    @property
    def fuerza(self) -> str:
        """Una linea sobre que obliga y que orienta, con su fundamento."""
        c = self.caracter_juridico or 'indeterminado'
        texto = FUERZA.get(c, c)
        if c == 'indeterminado':
            return texto
        return f'{texto} ({self.caracter_juridico_fundamento})'

    @property
    def autoridad(self) -> str:
        """Como de fiable es el texto que se devuelve, en una linea."""
        return AUTORIDAD.get(self.metodo_extraccion or '', '')

    def dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}
SEP = '::'
CLASES_DE_RUTA = {'art', 'ap', 'anexo', 'apend', 'itc', 'disp', 'capitulo', 'tabla', 'titulo', 'seccion', 'preambulo', 'req', 'libro', 'cabecera', 'pag', 'formula_final', 'reglamento'}
FORMAS_LARGAS_DE_CLASE = {'articulo': 'art', 'apartado': 'ap', 'punto': 'ap', 'clausula': 'ap', 'apendice': 'apend', 'disposicion': 'disp', 'requisito': 'req'}

def _sin_tildes(s: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

def ruta_canonica(ruta: str) -> str:
    """La ruta con la clase de cada tramo en la forma de la base: `anexo.XI/apendice.III` -> `anexo.XI/apend.III`; `apartado.2` ->
    `ap.2`; `artículo.5` -> `art.5`; `disposicion.final.2` -> `disp.final.2`; `capítulo.II` -> `capitulo.II`. Solo cambia el nombre
    de la clase (sin distinguir caja ni tildes): el numeral, y toda clase que no es una forma larga conocida, se quedan como estaban.

    R27-S7f (18-oct-2026, hallazgo 3 de REVISION_AG8.md): una letra de subapartado cerrada con paréntesis, como se
    escribe a menudo en prosa (`art.22.1.f)`, `art.23.1.a)`), se cita igual que sin él: el `)` final que sigue a una
    letra tras un punto se quita antes de resolver (la base no lo lleva). Solo el ÚLTIMO tramo puede llevarlo (el de
    después de la última `/`): un paréntesis a mitad de ruta no es esta grafía y se deja tal cual."""
    partes = ruta.split('/')
    tramos = []
    for i, tramo in enumerate(partes):
        if i == len(partes) - 1:
            tramo = re.sub('(?<=\\.[a-zñ])\\)$', '', tramo, flags=re.IGNORECASE)
        clase, punto, resto = tramo.partition('.')
        plana = _sin_tildes(clase).lower()
        nueva = FORMAS_LARGAS_DE_CLASE.get(plana) or (plana if plana in CLASES_DE_RUTA else None)
        tramos.append(nueva + punto + resto if nueva else tramo)
    return '/'.join(tramos)

def partir_identificador(ident: str) -> tuple[str, str]:
    """Parte `obra[@fecha]::ruta` en sus dos mitades.

    El separador es `::` y no `/` porque los nombres de obra llevan barras
    dentro ("Ley 32/2014", "Orden ICT/155/2020", "Directrices 2013/C 343/01").
    Partir por la primera barra dejaba "Ley 32" como obra y "2014/art.8.1" como
    ruta, y todas las consultas devolvian "no existe" sobre normas que si
    estaban cargadas: exactamente el falso negativo que el acta prohibe.

    La ruta sale con las clases en la forma de la base (`ruta_canonica`): `apendice.III` es `apend.III`.
    """
    cab, _, ruta = ident.strip().partition(SEP)
    return (cab.strip(), ruta_canonica(ruta.strip()))

def norm_alias(s: str) -> str:
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join((c for c in s if unicodedata.category(c) != 'Mn'))
    s = re.sub('\\bn\\.?[ºo°]\\s*(?=\\d)', '', s)
    s = re.sub('[^a-z0-9/]+', ' ', s)
    s = re.sub('\\s+', ' ', s).strip()
    return re.sub('^(guia|guias|norma|acuerdo|reglamento|orden|directiva|decision|comunicacion|directrices)\\s+(?:de\\s+la|de\\s+los|del|de|la|el)\\s+', '\\1 ', s)

def _tokens_designacion(s: str) -> list[str]:
    """La designacion partida en tokens comparables, sin acentos ni puntuacion."""
    s = unicodedata.normalize('NFD', (s or '').lower())
    s = ''.join((c for c in s if unicodedata.category(c) != 'Mn'))
    return [t for t in re.split('[^a-z0-9]+', s) if t]
_TOKENS_GENERICOS_OBRA = frozenset(('ict155', 'doc'))

def obra_por_designacion(con: sqlite3.Connection, nombre: str) -> str | None:
    """El canonico de la obra REGISTRADA cuya designacion coincide con `nombre`,
    aunque NO haya fila de alias que las enlace.

    Existe para una sola distincion, la de C-08 (g): 'no consta la obra' y
    'consta la obra pero le falta el alias' son cosas distintas, y `resolver` las
    confunde en NO_CONSTA porque solo mira la tabla de alias. La ISO/IEC 27001
    esta registrada (una vista previa) y sin embargo el acta imprimia 'no consta
    en la biblioteca' sobre ella: una negacion falsa sobre algo que consta.

    Aqui se mira la obra directamente: si sus tokens de cabecera —saltando
    'ict155'/'doc'— empiezan por los de la designacion citada, es la misma obra.
    Se exige que la designacion citada traiga al menos un token numerico (el
    numero de la norma), para no casar 'ISO' con la primera ISO cualquiera.
    Devuelve el canonico si hay una y solo una; None si ninguna o si varias
    empatan, porque un empate no es un alias que falta sino una ambiguedad.
    """
    claves = _tokens_designacion(nombre)
    if not claves or not any((t.isdigit() for t in claves)):
        return None
    out: list[str] = []
    for canonico, titulo in con.execute('SELECT identificador_canonico, titulo FROM obra'):
        for campo in (canonico, titulo):
            toks = _tokens_designacion(campo)
            i = 0
            while i < len(toks) and toks[i] in _TOKENS_GENERICOS_OBRA:
                i += 1
            if toks[i:i + len(claves)] == claves:
                out.append(canonico)
                break
    out = list(dict.fromkeys(out))
    return out[0] if len(out) == 1 else None
from .parsers import ORD_ARTICULO as _ORD_ART
RE_ART = re.compile(f'(?:art[íi]culos?\\s+|\\barts?\\.\\s*)(\\d+(?:\\s?{_ORD_ART})?)(?:\\.(\\d+))?(?:\\.(\\d+))?', re.I)
RE_AP_SUELTO = re.compile('(?:apartados?|puntos?)\\s+(\\d+(?:\\.\\d+)*)', re.I)
RE_LETRA = re.compile('letras?\\s+([a-zñ])\\)', re.I)
RE_LETRAS_VARIAS = re.compile('\\b([a-zñ])\\)', re.I)
RE_ANEXO = re.compile('(?:anexos?|anejos?)\\s+([IVXLC]+|\\d+|(?-i:[A-Z]))\\b', re.I)
RE_APEND = re.compile('ap[ée]ndice\\s+([IVXLC]+|\\d+|(?-i:[A-Z]))\\b', re.I)
RE_TABLA = re.compile('tabla\\s+(\\d+)', re.I)
from .parsers import ORD_DISPOSICION as _ORD_DISPOSICION
RE_DISP = re.compile('disposici[óo]n\\s+(adicional|transitoria|derogatoria|final)\\s+(' + _ORD_DISPOSICION + ')', re.I)
RE_TITULO_DIV = re.compile('(?i:t[íi]tulo)\\s+([IVXLC]+)\\b')
RE_CLAUSULA = re.compile('cl[áa]usula\\s+(\\d+(?:\\.\\d+)*)', re.I)
RX_SEPARADOR_DE_LISTA = re.compile('(?:[,;]|\\s(?:y|e)\\b)\\s*$', re.I)

def division_que_cierra_enumeracion(cita: str) -> bool:
    """Si la cita nombra una unidad menor y DESPUES, tras un separador de lista,
    el anexo o el apendice que podria contenerla."""
    base = re.sub('\\([^)]*\\)', ' ', cita)
    menores = (RE_ART, RE_AP_SUELTO, RE_CLAUSULA, RE_TABLA)
    for division, antes_de_ella in ((RE_ANEXO, menores + (RE_APEND,)), (RE_APEND, menores)):
        m = division.search(base)
        if not m:
            continue
        antes = base[:m.start()]
        if RX_SEPARADOR_DE_LISTA.search(antes) and any((x.search(antes) for x in antes_de_ella)):
            return True
    return False

def estructura_de_cita(cita: str):
    """Traduce la parte estructural de una cita humana a ESTRUCTURA.

    Esta es la funcion primaria. `ruta_de_cita()` es su proyeccion a cadena y se
    conserva porque medio sistema la llama, pero el dato es lo que sale de aqui:
    lista ordenada de niveles con su tipo, su numeral y su sistema de numeracion.

    Lo que NO se decide aqui, y queda anotado en `dudas` en vez de resuelto a la
    fuerza: si "3.1" es un articulo decimal o un articulo con apartado, si una
    letra que cuelga de un articulo tiene un apartado elidido en medio, y si un
    numeral con puntos es un nivel o varios.
    """
    from .ruta import RutaEstructurada
    r = RutaEstructurada()
    base = re.sub('\\([^)]*\\)', ' ', cita)
    if division_que_cierra_enumeracion(cita):
        r.dudar("'{}' cierra una enumeracion con un anexo o un apendice: no se sabe si contiene lo anterior".format(cita.strip()))
        return r
    anexo = RE_ANEXO.search(base)
    apend = RE_APEND.search(base)
    art = RE_ART.search(base)
    ap = RE_AP_SUELTO.search(base)
    letra = RE_LETRA.search(base)
    tabla = RE_TABLA.search(base)
    disp = RE_DISP.search(base)
    clau = RE_CLAUSULA.search(base)
    if disp:
        from .parsers import ordinal_a_numero, sin_tilde
        r.anadir('disposicion', f'{sin_tilde(disp.group(1).lower())}.{ordinal_a_numero(disp.group(2))}', disp.group(0))
        return r
    if anexo:
        r.anadir('anexo', _numeral_de_division(base, anexo), anexo.group(0))
    if apend:
        r.anadir('apendice', _numeral_de_division(base, apend), apend.group(0))
    if art:
        from .parsers import numeral_articulo
        r.anadir('articulo', numeral_articulo(art.group(1)), art.group(0))
        if art.group(2):
            r.anadir('apartado', art.group(2))
            r.dudar("'{}' se ha leido como articulo mas apartado; en una obra con articulos de numeral decimal seria un solo nivel".format(art.group(0).strip()))
        if art.group(3):
            r.anadir('apartado', art.group(3))
        if ap and (not tabla) and (not art.group(2)):
            r.anadir('apartado', ap.group(1), ap.group(0))
    elif ap and (not tabla):
        r.anadir('apartado', ap.group(1), ap.group(0))
        if DECIMAL_SUELTO.match(ap.group(1)):
            r.dudar("'{}' lleva puntos: puede ser un nivel con numeral decimal o varios niveles".format(ap.group(1)))
    elif clau:
        r.anadir('clausula', clau.group(1), clau.group(0))
    if tabla:
        r.anadir('tabla', tabla.group(1), tabla.group(0))
    if not r and RE_TITULO_DIV.search(base):
        r.anadir('titulo', _numeral_de_division(base, RE_TITULO_DIV.search(base)))
    letras = RE_LETRAS_VARIAS.findall(base)
    if len(letras) > 1:
        r.dudar('la cita nombra {} letras; el ambito es el apartado entero'.format(len(letras)))
    elif letra and r:
        r.anadir('letra', letra.group(1).lower(), letra.group(0))
        if r.tipos()[-2:-1] == ['art']:
            r.dudar('la letra cuelga directamente del articulo: puede haber un apartado elidido por quien cito')
    return r
DECIMAL_SUELTO = re.compile('^\\d+(?:\\.\\d+)+$')
from .parsers import ORD_DIV as _ORD_DIV, numeral_division as _numeral_division
RX_ORDINAL_DE_DIVISION = re.compile(_ORD_DIV)

def _numeral_de_division(base: str, m: re.Match) -> str:
    """El numeral de la division casada en `m`, con su ordinal si lo lleva."""
    numeral = m.group(1).upper()
    o = RX_ORDINAL_DE_DIVISION.match(base, m.end())
    return _numeral_division(f'{numeral} {o.group(0).strip()}') if o else numeral

def ruta_de_cita(cita: str) -> str | None:
    """Proyeccion a cadena de `estructura_de_cita()`.

    Se conserva porque medio sistema la llama. **No es el dato**: cambiar la
    convencion de escritura de las rutas no obliga a reprocesar el corpus,
    porque lo que se guarda es la estructura.
    """
    return estructura_de_cita(cita).cadena
RE_VARIOS_ART = re.compile('art[íi]culos\\s+(\\d+(?:\\.\\d+)*)\\s*(?:,\\s*(\\d+(?:\\.\\d+)*)\\s*)*(?:y|e|,)\\s*(\\d+(?:\\.\\d+)*)', re.I)
RE_NUM_SUELTO = re.compile('\\d+(?:\\.\\d+)*')

def rutas_de_cita(cita: str) -> list[str]:
    """Todas las rutas que designa una cita, no solo la primera.

    Devuelve lista vacia si la cita no designa ninguna. Para el caso corriente
    de una sola ruta devuelve exactamente `[ruta_de_cita(cita)]`, de modo que
    quien no necesite el plural puede seguir con la funcion de siempre.
    """
    m = RE_VARIOS_ART.search(cita or '')
    if m:
        numeros = RE_NUM_SUELTO.findall(m.group(0))
        vistos, out = (set(), [])
        for n in numeros:
            r = f'art.{n}'
            if r not in vistos:
                vistos.add(r)
                out.append(r)
        if len(out) > 1:
            return out
    una = ruta_de_cita(cita)
    return [una] if una else []

def alias_de_cita(cita: str) -> str:
    return cita.split(',')[0].strip()

def alias_candidatos(cita: str) -> list[str]:
    """Del alias mas corto al mas largo. El corto puede empatar entre obras."""
    limpia = re.sub('\\([^)]*\\)', ' ', cita)
    limpia = re.sub('\\s+', ' ', limpia).strip(' .,;')
    trozos = [x.strip() for x in limpia.split(',') if x.strip()]
    out = []
    for i in range(1, len(trozos) + 1):
        cand = ', '.join(trozos[:i])
        if cand not in out:
            out.append(cand)
    return out
RX_PARTE_DE_NORMA = re.compile('\\b(\\d{3,})\\s*-\\s*(\\d+)\\b')

def _parte_de(nombre: str) -> tuple[str, str] | None:
    m = RX_PARTE_DE_NORMA.search(nombre or '')
    return (m.group(1), m.group(2)) if m else None
RX_ANYO_DE_EDICION = re.compile('(?:19|20)\\d{2}')

def _token_de_edicion(t: str) -> bool:
    """Si ese token puede sobrar en un nombre sin que sea otra norma.

    Sobran: el anyo (`2018`), y cualquier token que no EMPIECE por digito
    (`v2.2.2` de una ETSI, `rev4` de una guia de ENAC, `A1` de una modificacion).
    NO sobra un token que empieza por digito y no es un anyo: eso es la
    continuacion del numero de la norma, y quedarse antes de el es citar otro
    numero. Es lo que separa `EN 300` de `EN 300 328`.

    Tampoco sobra una MARCA DE QUE EL EJEMPLAR NO ES EL VIGENTE O EL COMPLETO
    (12-oct-2026): «borrador», «parcial», «preview»... No es una edicion de la
    norma, es OTRO documento. Con ella como «edicion que sobra», quien citaba
    `Anexo 22` a secas alcanzaba por prefijo el alias `Anexo 22 borrador 2025`, y un
    nombre generico llegaba a un borrador.
    """
    if t in MARCAS_DE_EJEMPLAR_NO_VIGENTE:
        return False
    return bool(RX_ANYO_DE_EDICION.fullmatch(t)) or not t[:1].isdigit()
MARCAS_DE_EJEMPLAR_NO_VIGENTE = frozenset(('borrador', 'draft', 'parcial', 'partial', 'preview', 'extracto', 'extract', 'superada', 'superseded', 'obsoleta', 'anulada'))

def _prefijo_en_frontera_de_token(citado: str, guardado: str) -> bool:
    """Si uno de los dos nombres es prefijo del otro y lo que sobra es edicion.

    Es el primer freno de la vuelta por prefijo, y distingue las dos unicas cosas
    que la vuelta mezclaba:

        "EN 12830 2018"  frente a  "EN 12830"    -> sobra un token entero y es un
                                                    anyo. Es la misma norma.
        "EN 30032"       frente a  "EN 300328"   -> el corte cae DENTRO del token
                                                    del numero. No es la misma
                                                    norma: es otro numero.
        "EN 300"         frente a  "EN 300 328"  -> el corte cae en frontera de
                                                    token, pero lo que sobra
                                                    (`328`) es la continuacion
                                                    del numero, no una edicion.
                                                    Tampoco es la misma norma.

    Sin esto, cualquier recorte del numero alcanzaba la norma entera. Medido el
    9-ago-2026 sobre la base de produccion (`_mediciones/c17/30_antes.txt`): los
    13 recortes del banco alcanzaban otra obra, `EN 1` alcanzaba tres y contestaba
    OBRA_AMBIGUA, y `Ley 32`, `Real Decreto 244` y `Orden ICT/155` contestaban
    ENCONTRADO sobre la Ley 32/2014, el RD 244/2016 y la Orden ICT/155/2020.

    Se compara sobre `norm_alias`, que ya ha quitado acentos y puntuacion y ha
    dejado la barra dentro del token ("ley 32/2014" es UN token): asi
    "Orden ICT/155" no es prefijo de "Orden ICT/155/2020", que es lo correcto,
    porque el numero de la orden no esta completo.

    Y EL FRENO SOLO MIRA UN LADO, que es donde esta el fallo. Lo que sobra tiene
    que parecer una edicion **cuando el que se queda corto es el nombre citado**:
    ahi es donde un numero incompleto alcanza la norma entera. Cuando el nombre
    citado es el LARGO, la norma esta nombrada del todo y lo que sobra es glosa
    del autor; eso se acepta. Lo enseno el caso N53 del arnes, que se puso rojo
    con la primera version de este freno: cita «Decisión de Ejecución (UE)
    2025/138 (normas armonizadas EN 18031 con restricciones)» y la base guarda
    «Decisión de Ejecución (UE) 2025/138». El alias esta entero dentro de la cita;
    rechazarla por el `18031` de la glosa era rechazar una cita correcta.

    LA EXCEPCION DE LA PARTE, que conserva a proposito el limite que C-16 dejo
    declarado: quien cita `ISO 2859` no ha dicho parte, y hasta hoy alcanzaba la
    obra de la `ISO 2859-1`. Ese comportamiento no lo cambia esta reparacion, que
    va contra los recortes del numero y no contra las familias. Decidir a que
    parte responde una familia es diseno y sigue pendiente.
    """
    a = norm_alias(citado).split()
    b = norm_alias(guardado).split()
    if a[:len(b)] == b:
        return True
    if b[:len(a)] != a:
        return False
    sobra = b[len(a):]
    if all((_token_de_edicion(t) for t in sobra)):
        return True
    parte = _parte_de(guardado)
    return bool(parte) and sobra == [parte[1]]
RX_UN_ANYO = re.compile('(?:19|20)\\d{2}')

def _anyo_pedido(citado: str, guardado: str) -> str | None:
    """El ano que el nombre citado pone JUSTO detras del alias guardado: `EN 13486:2001` sobre el alias `EN 13486` -> `2001`.
    None si no hay ninguno (o si lo que sigue no es un ano suelto: `ILAC-P14:09/2020`, «de 2014»)."""
    a, b = (norm_alias(citado).split(), norm_alias(guardado).split())
    if len(a) > len(b) and a[:len(b)] == b and RX_UN_ANYO.fullmatch(a[len(b)]):
        return a[len(b)]
    return None

def _anyos_de_la_obra(con: sqlite3.Connection, obra_id: int) -> set[str]:
    """Los anos de edicion o de consolidacion de los ejemplares de la obra. Vacio si ninguno se conoce."""
    anyos = set()
    for f in con.execute('SELECT fecha_edicion, fecha_consolidacion FROM version WHERE obra_id=?', (obra_id,)):
        anyos |= {v[:4] for v in f if v and RX_UN_ANYO.match(v)}
    return anyos

def _detalle_de_ediciones(con: sqlite3.Connection, nombre: str, rechazadas: list) -> str:
    """Que ediciones de esa norma hay en la base, para decirlo cuando se pidio una que no esta."""
    a = norm_alias(nombre).split()
    raiz = ' '.join((t for t in a if not RX_UN_ANYO.fullmatch(t)))
    obras = {f['identificador_canonico']: f['id'] for f in rechazadas}
    for f in con.execute('SELECT DISTINCT o.id, o.identificador_canonico FROM obra o JOIN obra_alias al ON al.obra_id=o.id WHERE al.alias_norm = ? OR al.alias_norm LIKE ?', (raiz, raiz + ' %')):
        obras.setdefault(f['identificador_canonico'], f['id'])
    return '; '.join((f"{i} (edicion {', '.join(sorted(_anyos_de_la_obra(con, oid))) or 'sin ano conocido'})" for i, oid in sorted(obras.items())))

def _obra_por_alias(con: sqlite3.Connection, alias: str, rechazadas: list | None=None):
    """Las obras que lleva un nombre. `rechazadas`, si se pasa, recibe las que el nombre alcanzaba y se descartaron por el ano."""
    n = norm_alias(alias)
    filas = con.execute('SELECT DISTINCT o.* FROM obra o JOIN obra_alias a ON a.obra_id=o.id WHERE a.alias_norm = ?', (n,)).fetchall()
    if filas:
        return filas
    filas = con.execute("SELECT o.*, a.alias AS alias_casado FROM obra o JOIN obra_alias a ON a.obra_id=o.id WHERE a.alias_norm LIKE ? OR ? LIKE a.alias_norm || '%'", (n + '%', n)).fetchall()
    parte_citada = _parte_de(alias)
    vistas, out = (set(), [])
    for f in filas:
        parte_alias = _parte_de(f['alias_casado'])
        if not _prefijo_en_frontera_de_token(alias, f['alias_casado']):
            continue
        if parte_citada and parte_alias != parte_citada:
            continue
        pedido = _anyo_pedido(alias, f['alias_casado'])
        if pedido:
            propios = _anyos_de_la_obra(con, f['id'])
            if propios and pedido not in propios:
                if rechazadas is not None and all((r['id'] != f['id'] for r in rechazadas)):
                    rechazadas.append(f)
                continue
        if f['id'] not in vistas:
            vistas.add(f['id'])
            out.append(f)
    return out
RX_TRAS_EL_NUMERO = '(?![\\d.])\\s*(?=[^\\W\\d_]|[(«\\"\'0-9]|$)'
RX_NUMERO_INICIAL = re.compile('(\\d+(?:\\.\\d+)*)\\.?\\s')
RX_ANTES_DEL_NUMERO = re.compile('(?i)\\b(?:see|vease|véase|clause|clauses|subclause|apartado|apartados|art[íi]culo|art[íi]culos|paragraph|paragraphs|point|points|p[áa]rrafo|p[áa]rrafos|n[úu]mero|n[úu]meros|inciso|incisos|punto|puntos|section|according\\s+to|conforme\\s+a|segun|según|in|en|de|del|and|y|o|or|to|a)\\s*$')
RX_ANTES_PEGADO = '(?<![\\d.])'
_GUIAS_CON_AUTORIDAD: frozenset[str] | None = None
CLASES_QUE_UNA_GUIA_NO_NIEGA = frozenset({'anexo', 'apend', 'capitulo'})

def guias_con_autoridad() -> frozenset[str]:
    """Guias cuyo troceado se ha MEDIDO y no pierde ni una clausula impresa.

    Solo estas pueden responder `PRECEPTO_INEXISTENTE`. Todas las demas se
    abstienen.

    INVERTIDA EL 7 DE AGOSTO DE 2026, y la inversion es el punto. Nacio el dia
    antes como lista de guias que SI pierden clausulas —las 42 que midio K-01—
    y todo lo que no estaba en ella conservaba la autoridad de negar. Eso deja
    abierto el lado peligroso: **una guia que nadie ha medido negaba igual**.
    Se vio al meter cuatro EN de ETSI que nadie ha medido y que iban a poder
    decir "ese apartado no existe" sobre un troceado del que no sabemos nada.

    Ahora la autoridad se demuestra, no se presume. La lista sale de
    `datos/guias_con_troceado_medido.json`, que la produce
    `pruebas/generar_guias_con_troceado_incompleto.py` a partir de la medicion
    K-01: son las guias examinadas por el detector independiente en las que
    salio cero.

    Si el fichero no esta, se devuelve el conjunto VACIO, y ahora eso es el lado
    SEGURO: ninguna guia niega, todas se abstienen. Antes un fichero ausente
    devolvia a todas la autoridad en silencio.
    """
    global _GUIAS_CON_AUTORIDAD
    if _GUIAS_CON_AUTORIDAD is None:
        ruta = config.DATOS_REPO / 'guias_con_troceado_medido.json'
        try:
            d = json.loads(ruta.read_text(encoding='utf-8'))
            _GUIAS_CON_AUTORIDAD = frozenset(d.get('limpias', {}))
        except FileNotFoundError:
            _GUIAS_CON_AUTORIDAD = frozenset()
    return _GUIAS_CON_AUTORIDAD

def _imprime_el_numero(texto: str | None, numero: str) -> bool:
    """El texto imprime ese numero de clausula COMO ENCABEZADO, no como remision.

    "vease 5.3.4" dentro de una frase es una remision, no un encabezado, y
    contarla haria decir que la clausula esta ahi cuando lo unico que hay es su
    nombre. Es el mismo error que C-04 estuvo a punto de cometer con "...set out
    in Article 3. Such information...", y por el que aquel control se cambio.

    Tres condiciones, y las tres hacen falta:

      PEGADO    el numero no va precedido de un digito ni de un punto, para que
                "2.1" no case dentro de "12.1" ni "1.10" dentro de "6.1.10".
                Anadido el 7-ago-2026 por C-11: es el accidente mas numeroso de
                los dos que encontro C-07.
      DELANTE   el numero no va precedido de una palabra de remision.
      DETRAS    le sigue una rubrica que empieza por mayuscula, digito, comilla
                o parentesis. Se admite pegada ("5.3.4General"), que es como el
                `-layout` deja algunas guias, y se rechaza que le siga otro
                digito, para que "5.3" no case dentro de "5.34".
    """
    if not texto or not numero:
        return False
    patron = RX_ANTES_PEGADO + re.escape(numero) + RX_TRAS_EL_NUMERO
    for m in re.finditer(patron, texto):
        if not RX_ANTES_DEL_NUMERO.search(texto[max(0, m.start() - 40):m.start()]):
            return True
    return False

def _imprime_inciso_directo(con, version_id, fila, inciso):
    """Rótulo dentro del padre real, excluyendo sus hijos ya separados.

    El artículo agregado puede contener a) dentro de su apartado 2: eso no
    acredita art.N.a. Tampoco el romano de una letra acredita art.N.2.i.
    """
    texto = re.sub('[^\\S\\n]+', ' ', fila['texto_literal'] or '').strip()
    padre = fila['ruta_estructural']
    hijos = con.execute('SELECT ruta_estructural, texto_literal FROM precepto WHERE version_id=? AND ruta_estructural LIKE ?', (version_id, padre + '.%')).fetchall()
    for hijo in hijos:
        if ruta_padre(hijo['ruta_estructural']) != padre:
            continue
        cuerpo = re.sub('[^\\S\\n]+', ' ', hijo['texto_literal'] or '').strip()
        if cuerpo:
            texto = texto.replace(cuerpo, ' ')
    propio = re.match(re.escape(padre.rsplit('.', 1)[-1]) + '\\)\\s+', texto)
    if propio:
        texto = texto[propio.end():]
    texto = re.sub('^(?:Art[íi]culo|Article)\\s+\\d+(?:\\s+bis)?\\.?\\s*', '', texto)
    texto = re.sub('^' + re.escape(padre.rsplit('.', 1)[-1]) + '[.)]\\s+', '', texto)
    from .parsers import ORD_LATINO
    sufijo = ORD_LATINO
    rotulos = list(re.finditer('(?:^|[;:.,]\\s+|\\n\\s*)([a-zñ]|[ivxlcdm]+)(\\s+' + sufijo + ')?\\)\\s+\\S', texto))
    padre_letra = re.fullmatch('[a-zñ](?:\\s+' + sufijo + ')?', padre.rsplit('.', 1)[-1])
    if padre_letra and (not re.fullmatch('[ivxlcdm]+', inciso)):
        return False
    for k, m in enumerate(rotulos):
        antes = texto[:m.start(1)]
        if antes.rfind('(') > antes.rfind(')') or re.search('\\b(?:letras?|p[áa]rrafos?|incisos?|puntos?)\\s+[a-zñivxlcdm]+\\)(?:\\s*(?:,|y|e|o)\\s*[a-zñivxlcdm]+\\))*\\s*(?:,|y|e|o)?\\s*$', antes, re.I) or re.match('(?:y|e|o|and|or)\\b', texto[m.end() - 1:], re.I):
            continue
        if padre_letra and (m[2] or not re.fullmatch('[ivxlcdm]+', m[1])):
            break
        if m[1] != inciso or m[2]:
            continue
        numeros = list(re.finditer('(?<![\\w.])\\d{1,3}(?:\\s+' + sufijo + ')?[.)]\\s+', antes))
        if any((not RX_ANTES_DEL_NUMERO.search(antes[max(0, n.start() - 40):n.start()]) for n in numeros)):
            continue
        if not padre_letra and re.fullmatch('[ivxlcdm]+', inciso):
            letras = [x[1] + (x[2] or '') for x in rotulos[:k] if len(x[1]) == 1 or x[2]]
            if letras and (len(inciso) != 1 or len(letras[-1]) != 1 or ord(inciso) != ord(letras[-1]) + 1):
                continue
        return True
    return False

def _antecesor_que_la_imprime(con: sqlite3.Connection, version_id: int, ruta: str):
    """El precepto de nivel superior dentro del cual esta impresa la clausula.

    Se sube por la ruta de uno en uno (`ap.5.3.4` -> `ap.5.3` -> `ap.5`) hasta
    dar con un precepto que exista. Si existe Y su texto imprime el numero
    pedido, esa es la respuesta: la clausula esta ahi dentro y el troceado no la
    separa. Si existe y NO lo imprime, se para y no se sigue subiendo: forzar la
    busqueda hasta encontrar algo es como se fabrican las rutas.
    """
    partes = ruta.split('.')
    numero = '.'.join(partes[1:])
    if len(partes) < 3 or not numero:
        return None
    for i in range(len(partes) - 1, 1, -1):
        fila = con.execute('SELECT * FROM precepto WHERE version_id=? AND ruta_estructural=?', (version_id, '.'.join(partes[:i]))).fetchone()
        if fila is None:
            continue
        texto = fila['texto_literal']
        if _imprime_el_numero(texto, numero):
            return fila
        m = RX_NUMERO_INICIAL.match((texto or '').lstrip())
        if m:
            relativo = m.group(1) + '.' + '.'.join(partes[i:])
            if _imprime_el_numero(texto, relativo):
                return fila
        if i == len(partes) - 1 and re.fullmatch('(?:[a-zñ]|[ivxlcdm]+)', partes[-1]) and (not re.fullmatch('art\\.[^.]+', fila['ruta_estructural'].rsplit('/', 1)[-1])) and _imprime_inciso_directo(con, version_id, fila, partes[-1]):
            return fila
        if ruta.startswith('itc.') and i == len(partes) - 1 and re.fullmatch('[a-zñ]', partes[-1]) and re.search(f'(?:^|[\\s.;:]){partes[-1]}\\)\\s', texto or ''):
            return fila
        return None
    return None
MAXIMO_CERCANOS = 12
_ROMANOS = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}

def ruta_padre(ruta: str) -> str | None:
    """La ruta del padre: `anexo.XI/ap.9` -> `anexo.XI`; `art.8.1` -> `art.8`; `ap.3.a` -> `ap.3`. None en un primer nivel."""
    tramos = ruta.split('/')
    ultimo = tramos[-1]
    if ultimo.count('.') >= 2:
        return '/'.join(tramos[:-1] + [ultimo.rsplit('.', 1)[0]])
    if len(tramos) > 1:
        return '/'.join(tramos[:-1])
    return None

def _valor_del_numeral(ruta: str) -> int | None:
    """El numeral con que acaba la ruta, como numero para medir distancias: `ap.9` -> 9, `anexo.XI` -> 11, `ap.3.a` -> 1
    (la letra a). None si no es un entero, un romano ni una letra."""
    n = ruta.split('/')[-1].rsplit('.', 1)[-1]
    if n.isdigit():
        return int(n)
    if n and n.isupper() and all((c in _ROMANOS for c in n)):
        total = 0
        for c, siguiente in zip(n, n[1:] + ' '):
            v = _ROMANOS[c]
            total += -v if _ROMANOS.get(siguiente, 0) > v else v
        return total
    if len(n) == 1 and n.isalpha():
        return ord(n.lower()) - 96
    return None

def rutas_cercanas(con: sqlite3.Connection, version_id: int, ruta: str, maximo: int=MAXIMO_CERCANOS) -> list[str]:
    """Los preceptos que SI existen y estan mas cerca de una ruta que no existe: su padre mas cercano (se sube de uno en
    uno hasta dar con uno que exista) y los hijos de ese padre, que son los hermanos de lo pedido. Para
    `anexo.XI/ap.9`, que no existe: `anexo.XI`, `anexo.XI/ap.1`..`ap.6` y los apendices del XI, y no los `anexo.I/...`,
    que es lo que salia cuando solo se miraba el principio de la ruta (12-oct-2026).

    Primero el padre, luego los hermanos de la misma clase que lo pedido (`ap.` con `ap.`; si son mas que `maximo`, los
    de numeral mas parecido) y luego los demas (los `apend.`), cada grupo en el orden del documento. Sin ningun padre
    que exista, los hermanos son los preceptos de primer nivel."""
    filas = con.execute('SELECT ruta_estructural, orden FROM precepto WHERE version_id=? ORDER BY orden', (version_id,)).fetchall()
    existentes = {f['ruta_estructural'] for f in filas}
    padre = ruta_padre(ruta)
    while padre is not None and padre not in existentes:
        padre = ruta_padre(padre)
    hijos = [f['ruta_estructural'] for f in filas if ruta_padre(f['ruta_estructural']) == padre]
    clase = ruta.split('/')[-1].rsplit('.', 1)[0]
    mismos = [h for h in hijos if h.split('/')[-1].rsplit('.', 1)[0] == clase]
    otros = [h for h in hijos if h not in mismos]
    sitio = maximo - (1 if padre is not None else 0)
    if len(mismos) > sitio:
        pedido = _valor_del_numeral(ruta)
        if pedido is not None and all((_valor_del_numeral(h) is not None for h in mismos)):
            cerca = sorted(mismos, key=lambda h: (abs(_valor_del_numeral(h) - pedido), mismos.index(h)))[:sitio]
            mismos = [h for h in mismos if h in cerca]
        else:
            mismos = mismos[:sitio]
    salida = ([padre] if padre is not None else []) + mismos
    return salida + otros[:max(0, maximo - len(salida))]

def rutas_con_otra_clase(con: sqlite3.Connection, version_id: int, ruta: str, posicion: int, maximo: int=5) -> list[str]:
    """Las rutas de la version iguales a `ruta` salvo que el tramo `posicion` tiene OTRA clase con el mismo numeral: para
    `anexo.XI/appendix.III`, `anexo.XI/apend.III`. Vacia si el tramo no lleva numeral o no hay ninguna."""
    tramos = ruta.split('/')
    clase, _, numeral = tramos[posicion].partition('.')
    if not numeral:
        return []
    antes, despues = (tramos[:posicion], tramos[posicion + 1:])
    salida = []
    for otra, in con.execute('SELECT ruta_estructural FROM precepto WHERE version_id=? AND ruta_estructural LIKE ? ORDER BY orden', (version_id, '%.' + numeral + '%')):
        t = otra.split('/')
        if len(t) != len(tramos) or t[:posicion] != antes or t[posicion + 1:] != despues:
            continue
        c, _, n = t[posicion].partition('.')
        if c != clase and n.casefold() == numeral.casefold():
            salida.append(otra)
    return salida[:maximo]

def obras_que_casan(con: sqlite3.Connection, texto: str) -> list[sqlite3.Row]:
    """Las obras cuyo identificador canonico o alias casa con `texto`, con la misma regla con que `resolver` encuentra
    la obra de una cita (el alias con su vuelta por prefijo y su freno), y si no hay ninguna, la obra cuya designacion
    empieza por el texto (`obra_por_designacion`). Vacia si el texto no es el nombre de ninguna obra."""
    t = (texto or '').strip()
    if not norm_alias(t):
        return []
    filas = con.execute('SELECT * FROM obra WHERE identificador_canonico = ? COLLATE NOCASE', (t,)).fetchall() or _obra_por_alias(con, t)
    if not filas:
        canonico = obra_por_designacion(con, t)
        if canonico:
            filas = con.execute('SELECT * FROM obra WHERE identificador_canonico = ?', (canonico,)).fetchall()
    vistas, salida = (set(), [])
    for f in filas:
        if f['id'] not in vistas:
            vistas.add(f['id'])
            salida.append(f)
    return salida

def obras_para_buscar(con: sqlite3.Connection, texto: str, ambitos: tuple[str, ...]=('publico',)) -> list[dict]:
    """Lo que `buscar` ensena delante de los fragmentos cuando el texto buscado es el nombre de una obra de la base: su
    identificador, como se cita, y de cada ejemplar si esta completo, parcial o es un extracto, su regimen y si la base
    tiene su texto. Sin esto, buscar «EN 12830:2018» ensenaba las menciones en otras normas y la copia PARCIAL, y no que
    la base TIENE la norma entera (12-oct-2026). Un ejemplar de un regimen que el ambito no ve no se ensena."""
    n = norm_alias(texto)
    salida = []
    for o in obras_que_casan(con, texto):
        versiones = []
        for v in con.execute('SELECT v.etiqueta, v.completitud, v.idioma, d.clase_derechos AS regimen, d.estado_ingesta, (SELECT count(*) FROM precepto p WHERE p.version_id = v.id) AS preceptos FROM version v JOIN documento d ON d.id = v.documento_id WHERE v.obra_id = ? ORDER BY v.id', (o['id'],)):
            if v['regimen'] in REPRODUCIBLES or v['regimen'] in ambitos:
                versiones.append(dict(v))
        if not versiones:
            continue
        alias = [a['alias'] for a in con.execute('SELECT alias FROM obra_alias WHERE obra_id = ?', (o['id'],)) if a['alias'] != o['identificador_canonico']]
        alias.sort(key=lambda a: (norm_alias(a) != n, len(a), a))
        ficha = {'identificador': o['identificador_canonico'], 'titulo': o['titulo'], 'tipo': o['tipo'], 'alias': alias[:4], 'versiones': versiones}
        ficha['lineas'] = lineas_de_obra(ficha)
        salida.append(ficha)
    return salida

def lineas_de_obra(o: dict) -> list[str]:
    """Una obra que se llama como el texto buscado, en pocos renglones: identificador, como se cita y, por ejemplar, si
    esta completo o parcial, su regimen y si la base tiene su texto. Lo escribe la base y lo ensenan igual la linea de
    ordenes y la extension de Cowork."""
    lineas = [f"{o['identificador']}   {(o['titulo'] or '')[:80]}"]
    citar = o['alias'][0] if o['alias'] else o['identificador']
    lineas.append(f'   se cita como «{citar}::ruta»' + (f" o «{o['identificador']}::ruta»" if o['alias'] else ''))
    for v in o['versiones']:
        completitud = NOMBRE_COMPLETITUD.get(v['completitud'], str(v['completitud']).upper())
        texto = f"   {v['etiqueta']} ({v['idioma']}): {completitud}, {v['preceptos']} preceptos · régimen: {v['regimen']}"
        if v['estado_ingesta'] != 'ingerido':
            texto += f" · SIN TEXTO en la base ({v['estado_ingesta']})"
        natural = naturaleza_del_texto(v['etiqueta'], v['completitud'])
        if natural:
            texto += f' · {natural}'
        if v['completitud'] != 'completa':
            texto += '. Que un apartado no salga aquí no prueba que la norma no lo tenga'
        lineas.append(texto)
    return lineas

def resolver(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',), modo: str=MODO_TEXTO) -> Respuesta:
    from . import calidad_textual
    r = _resolver(con, identificador, ambitos, modo)
    ruta = r.ambito_localizado or partir_identificador(identificador)[1]
    return calidad_textual.aplicar(con, r, ruta)

def _contenedor_de_letra_ordinal(con, version_id, ruta):
    """La foto conserva «f bis)» dentro de f), incluidos anexos.

    Se admite el ordinal separado o pegado en la consulta; solo se localiza
    si el contenedor inmediato imprime el rótulo como inicio de un elemento,
    seguido de cuerpo. Una remisión «la letra f bis)» no demuestra existencia.
    """
    m = re.fullmatch('(.+\\.)([a-zñ])\\s*(bis|ter|quater|quinquies)\\)?', ruta)
    if not m:
        return None
    patron = '(?:^|[;:.]\\s+)' + re.escape(m[2]) + '\\s+' + re.escape(m[3]) + '\\)\\s+\\S'
    for candidata in (m[1] + m[2], m[1][:-1]):
        fila = con.execute('SELECT * FROM precepto WHERE version_id=? AND ruta_estructural=?', (version_id, candidata)).fetchone()
        if fila is None:
            continue
        return fila if re.search(patron, fila['texto_literal'] or '') else None
    punto = re.fullmatch('(anexo\\.[^/]+(?:/(?:capitulo|seccion)\\.[^/]+)*)/ap\\.(\\d+(?:\\.\\d+)*)', m[1][:-1])
    if punto:
        scope, numero = punto.groups()
        filas = con.execute('SELECT * FROM precepto WHERE version_id=? AND (ruta_estructural=? OR substr(ruta_estructural,1,?)=?) ORDER BY length(texto_literal),ruta_estructural', (version_id, scope, len(scope) + 1, scope + '/')).fetchall()
        for fila in filas:
            tramo = _texto_de_punto_impreso(fila['texto_literal'], numero)
            if tramo and re.search(patron, tramo):
                return fila
    return None

def _texto_de_punto_impreso(texto, numero):
    """Punto decimal hasta el siguiente hermano; excluye remisiones internas."""
    encabezados = []
    for h in re.finditer('(?<![\\w.])(\\d{1,3}(?:\\.\\d{1,3})+)\\.?\\s+(?=[A-ZÁÉÍÓÚÑ])', texto or ''):
        if not RX_ANTES_DEL_NUMERO.search(texto[max(0, h.start() - 40):h.start()]):
            encabezados.append(h)
    for k, h in enumerate(encabezados):
        if h[1] != numero:
            continue
        fin = next((sig.start() for sig in encabezados[k + 1:] if not sig[1].startswith(numero + '.')), len(texto))
        return texto[h.end():fin]
    return None

def _resolver(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',), modo: str=MODO_TEXTO) -> Respuesta:
    """Resuelve `obra[@fecha]::ruta` o `obra` y devuelve texto y procedencia.

    `modo` decide que se hace con un documento de regimen restringido:
    MODO_TEXTO no devuelve nada, MODO_LOCALIZAR devuelve fichero y pagina sin
    imprimir el texto. La restriccion se impone aqui y no en el sistema de
    ficheros: el mismo PDF responde distinto segun lo que se le pida.
    """
    ident = identificador.strip()
    cab, ruta = partir_identificador(ident)
    obra_id, _, fecha = cab.partition('@')
    rechazadas: list = []
    filas = con.execute('SELECT * FROM obra WHERE identificador_canonico = ?', (obra_id,)).fetchall() or _obra_por_alias(con, obra_id, rechazadas)
    if not filas:
        return Respuesta(estado=NO_CONSTA, identificador=ident, detalle=f'no consta {obra_id!r} en esa edicion: la base tiene {_detalle_de_ediciones(con, obra_id, rechazadas)}' if rechazadas else f'no consta obra ni alias para {obra_id!r}')
    if len(filas) > 1:
        con_texto = [f for f in filas if con.execute('SELECT 1 FROM precepto p JOIN version v ON v.id=p.version_id WHERE v.obra_id=? LIMIT 1', (f['id'],)).fetchone()]
        if len(con_texto) != 1:
            return Respuesta(estado=OBRA_AMBIGUA, identificador=ident, candidatos=[f['identificador_canonico'] for f in filas])
        filas = con_texto
    obra = filas[0]
    q = 'SELECT v.*, d.ruta_relativa, d.clase_derechos, d.estado_ingesta FROM version v JOIN documento d ON d.id=v.documento_id WHERE v.obra_id=?'
    par = [obra['id']]
    q += " ORDER BY coalesce(v.fecha_consolidacion, v.fecha_edicion, '') DESC, v.id DESC"
    vers = con.execute(q, par).fetchall()
    ediciones = sorted({v['fecha_edicion'] for v in vers if v['fecha_edicion']})
    if len(ediciones) > 1:
        if not fecha:
            return Respuesta(estado=EDICION_AMBIGUA, identificador=ident, obra=obra['identificador_canonico'], obra_titulo=obra['titulo'], candidatos=[f"{obra['identificador_canonico']}@{e}" for e in ediciones], detalle='la obra tiene ' + str(len(ediciones)) + ' ediciones (' + ', '.join(ediciones) + ') y la cita no dice cual. Anade @fecha: con fecha se elige la vigente entonces')
        if es_anio(fecha):
            del_anio = [e for e in ediciones if e[:4] == fecha]
            if len(del_anio) != 1:
                return Respuesta(estado=EDICION_AMBIGUA, identificador=ident, obra=obra['identificador_canonico'], obra_titulo=obra['titulo'], candidatos=[f"{obra['identificador_canonico']}@{e}" for e in del_anio or ediciones], detalle=f'con @{fecha} ' + (f"hay {len(del_anio)} ediciones de ese ano ({', '.join(del_anio)})" if del_anio else 'no hay ninguna edicion de ese ano') + f". La obra tiene {len(ediciones)} ({', '.join(ediciones)}): precisa la fecha AAAA-MM-DD")
            vers = [v for v in vers if v['fecha_edicion'] == del_anio[0]]
            fecha = None
        elif not fecha_bien_escrita(fecha):
            return Respuesta(estado=EDICION_AMBIGUA, identificador=ident, obra=obra['identificador_canonico'], obra_titulo=obra['titulo'], candidatos=[f"{obra['identificador_canonico']}@{e}" for e in ediciones], detalle=f'la fecha {fecha!r} no es AAAA-MM-DD valida y con ella no se elige edicion. La obra tiene {len(ediciones)} (' + ', '.join(ediciones) + ')')
        vigentes = [v for v in vers if fecha is None or _publicada_desde(v['fecha_edicion'] or '9999') <= fecha]
        if not vigentes:
            return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], candidatos=[f"{obra['identificador_canonico']}@{e}" for e in ediciones], detalle=f'ninguna edicion consta publicada el {fecha}: de la primera, de {ediciones[0]}, solo se sabe el ano')
        vers = sorted(vigentes, key=lambda v: v['fecha_edicion'] or '', reverse=True)
    if not vers:
        return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], detalle='la obra consta pero no hay version ingerida')
    ingeridas = [x for x in vers if x['estado_ingesta'] == 'ingerido']
    if ingeridas:
        vers = ingeridas

    def rango(fila):
        m = con.execute('SELECT metodo_extraccion FROM precepto WHERE version_id=? LIMIT 1', (fila['id'],)).fetchone()
        met = m[0] if m else 'ocr'
        return PRELACION.index(met) if met in PRELACION else len(PRELACION)
    if len(vers) > 1:
        vers = sorted(vers, key=rango)
    v = vers[0]
    if ruta and len(vers) > 1:
        candidatas = sorted(vers, key=rango)
        con_ese = [f for f in candidatas if con.execute('SELECT 1 FROM precepto WHERE version_id=? AND ruta_estructural=? LIMIT 1', (f['id'], ruta)).fetchone()]
        v = (con_ese or candidatas)[0]
    restringido = v['clase_derechos'] not in REPRODUCIBLES and v['clase_derechos'] not in ambitos
    if restringido and modo != MODO_LOCALIZAR:
        return Respuesta(estado=DERECHOS_RESTRINGIDOS, identificador=ident, obra=obra['identificador_canonico'], fichero=v['ruta_relativa'], reproducible=False, regimen=v['clase_derechos'], detalle=f"regimen {v['clase_derechos']}: no se devuelve texto. Repite en modo localizar para saber donde esta")
    if v['estado_ingesta'] != 'ingerido':
        return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], fichero=v['ruta_relativa'], detalle=f"documento registrado pero no ingerido ({v['estado_ingesta']})")
    base = Respuesta(estado=LOCALIZADO_SIN_TEXTO if restringido else ENCONTRADO, identificador=ident, obra=obra['identificador_canonico'], obra_titulo=obra['titulo'], version=v['etiqueta'], version_id=v['id'], fecha_consolidacion=v['fecha_consolidacion'], idioma=v['idioma'], completitud=v['completitud'], fichero=v['ruta_relativa'], regimen=v['clase_derechos'], caracter_juridico=obra['caracter_juridico'], caracter_juridico_fundamento=obra['caracter_juridico_fundamento'], emisor=obra['emisor'], reproducible=v['clase_derechos'] in REPRODUCIBLES)
    if not ruta:
        n = con.execute('SELECT count(*) FROM precepto WHERE version_id=?', (v['id'],)).fetchone()[0]
        base.etiqueta_humana = obra['titulo']
        base.detalle = f'ambito: documento completo, {n} preceptos'
        base.pagina_inicio, base.pagina_fin = (1, con.execute('SELECT paginas FROM documento WHERE id=?', (v['documento_id'],)).fetchone()[0])
        return base
    ruta = ruta_efectiva(con, v['id'], ruta)
    p = con.execute('SELECT * FROM precepto WHERE version_id=? AND ruta_estructural=?', (v['id'], ruta)).fetchone()
    if p is None:
        contenedor = _contenedor_de_letra_ordinal(con, v['id'], ruta)
        if contenedor is not None:
            base.estado = CONTENIDO_EN_ANCESTRO
            base.ambito_pedido = ruta
            base.ambito_localizado = contenedor['ruta_estructural']
            base.preceptos_localizados = 1
            base.etiqueta_humana = contenedor['etiqueta_humana']
            base.pagina_inicio = contenedor['pagina_inicio']
            base.pagina_fin = contenedor['pagina_fin']
            base.metodo_extraccion = contenedor['metodo_extraccion']
            base.reproducible = False
            base.detalle = 'LOCALIZADO EN SU CONTENEDOR ' + base.ambito_localizado + ': el rótulo con ordinal está impreso allí; no tiene ruta propia. Consulta ese contenedor y coteja sus páginas del PDF'
            return base
        if v['completitud'] == 'completa':
            cercanos = [r[0] for r in con.execute('SELECT ruta_estructural FROM precepto WHERE version_id=? AND ruta_estructural LIKE ? LIMIT 8', (v['id'], ruta.split('.')[0] + '%')).fetchall()]
            hijas = [c for c in cercanos if c.startswith(ruta + '.')]
            if hijas and '.' not in ruta:
                return Respuesta(estado=RUTA_AMBIGUA, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], candidatos=sorted(hijas), detalle=f'{ruta!r} no designa un precepto: el documento tiene {len(hijas)}. Precisa cual. `sn` es el que no lleva numeral' if any((h.endswith('.sn') for h in hijas)) else f'{ruta!r} no designa un precepto: hay {len(hijas)}')
            prefijo_pedido = None
            for posicion, tramo in enumerate(ruta.split('/')):
                clase = tramo.split('.')[0]
                hay = con.execute('SELECT 1 FROM precepto WHERE version_id = ? AND (ruta_estructural LIKE ? OR ruta_estructural LIKE ?) LIMIT 1', (v['id'], clase + '.%', '%/' + clase + '.%')).fetchone()
                if hay is None:
                    prefijo_pedido = clase
                    break
            if prefijo_pedido is not None:
                parecidas = rutas_con_otra_clase(con, v['id'], ruta, posicion)
                if parecidas:
                    return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], completitud=v['completitud'], candidatos=parecidas, ambito_pedido=ruta, detalle=f"este ejemplar no tiene ninguna unidad `{prefijo_pedido}.`, pero si {' y '.join(('`' + p + '`' for p in parecidas))}: ¿quieres decir {' o '.join(('`' + p + '`' for p in parecidas))}? La base nombra esa division de otra forma; no es que no este troceada")
                return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], completitud=v['completitud'], ambito_pedido=ruta, detalle=f'este ejemplar no tiene NINGUNA unidad de clase `{prefijo_pedido}.` troceada, asi que no puede afirmar que esta no exista: lo que falta puede ser el troceado y no el precepto')
            anc = _antecesor_que_la_imprime(con, v['id'], ruta)
            if anc is not None:
                r = Respuesta(estado=CONTENIDO_EN_ANCESTRO, identificador=ident, obra=obra['identificador_canonico'], obra_titulo=obra['titulo'], version=v['etiqueta'], version_id=v['id'], fichero=v['ruta_relativa'], completitud=v['completitud'], regimen=v['clase_derechos'], caracter_juridico=obra['caracter_juridico'], caracter_juridico_fundamento=obra['caracter_juridico_fundamento'], emisor=obra['emisor'], etiqueta_humana=anc['etiqueta_humana'], pagina_inicio=anc['pagina_inicio'], pagina_fin=anc['pagina_fin'], metodo_extraccion=anc['metodo_extraccion'], ambito_pedido=ruta, ambito_localizado=anc['ruta_estructural'], preceptos_localizados=1, reproducible=False, detalle=f"la clausula esta impresa dentro de {anc['ruta_estructural']!r} y este sistema no la trocea aparte. No es que no exista: es que no se separa. Para leerla, cita {anc['ruta_estructural']!r}; para verificar una afirmacion sobre ella, cotejala contra esa ruta")
                return r
            if obra['tipo'] == 'guia' and any((t.split('.')[0] in CLASES_QUE_UNA_GUIA_NO_NIEGA for t in ruta.split('/'))):
                return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], completitud=v['completitud'], candidatos=rutas_cercanas(con, v['id'], ruta), ambito_pedido=ruta, detalle='la autoridad de esta guia para negar se midio sobre sus clausulas, no sobre sus anexos, apendices ni capitulos: no puede afirmar que esta division no exista')
            if obra['tipo'] == 'guia' and obra['identificador_canonico'] not in guias_con_autoridad():
                return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], completitud=v['completitud'], candidatos=rutas_cercanas(con, v['id'], ruta), ambito_pedido=ruta, detalle='el ejemplar esta completo pero su troceado no: en las guias este sistema pierde clausulas impresas (medido el 6-ago-2026) y no puede afirmar que esta no exista. Busca su rotulo con `buscar`, o cotejala contra la clausula de nivel superior')
            return Respuesta(estado=PRECEPTO_INEXISTENTE, identificador=ident, obra=obra['identificador_canonico'], version=v['etiqueta'], fichero=v['ruta_relativa'], completitud='completa', candidatos=rutas_cercanas(con, v['id'], ruta), detalle='el precepto no aparece en el ejemplar completo')
        return Respuesta(estado=FUERA_DE_ALCANCE, identificador=ident, obra=obra['identificador_canonico'], fichero=v['ruta_relativa'], completitud=v['completitud'], detalle=f"ejemplar {v['completitud']}: no se puede afirmar la ausencia")
    base.etiqueta_humana = p['etiqueta_humana']
    base.titulo = p['titulo']
    base.pagina_inicio = p['pagina_inicio']
    base.pagina_fin = p['pagina_fin']
    base.marca_consolidacion = p['marca_consolidacion']
    base.metodo_extraccion = p['metodo_extraccion']
    base.naturaleza_del_texto = naturaleza_del_texto(v['etiqueta'], v['completitud'], p['metodo_extraccion'])
    if not restringido:
        base.texto_literal = p['texto_literal']
    else:
        base.detalle = f"regimen {v['clase_derechos']}: existe y esta localizado, pero su texto no se reproduce"
    return base

def texto_de_ambito(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',)) -> tuple[Respuesta, str]:
    """Devuelve la respuesta y el texto sobre el que comprobar una atribucion.

    Si el identificador apunta a un precepto, el texto es el del precepto y su
    subarbol. Si apunta a la version entera, el texto es el de la version.
    Respuesta.texto_literal conserva el texto propio de la unidad (puede ser
    solo un rótulo); el segundo valor reúne el ámbito y declara cuántas
    unidades se localizaron, sin certificar su fidelidad.
    """
    from . import calidad_textual
    r = _resolver(con, identificador, ambitos)
    if r.estado != ENCONTRADO:
        ruta = r.ambito_localizado or partir_identificador(identificador)[1]
        calidad_textual.aplicar(con, r, ruta)
        return (r, '')
    cab, ruta = partir_identificador(identificador)
    vid = r.version_id
    ruta = ruta_efectiva(con, vid, ruta) if ruta else ruta
    if ruta:
        filas_p = con.execute('WITH RECURSIVE ambito(id) AS (SELECT id FROM precepto WHERE version_id=? AND (ruta_estructural=? OR ruta_estructural LIKE ? OR ruta_estructural LIKE ?) UNION SELECT p.id FROM precepto p JOIN ambito a ON p.padre_id=a.id WHERE p.version_id=?) SELECT ruta_estructural, titulo, texto_literal FROM precepto WHERE id IN (SELECT id FROM ambito) ORDER BY orden', (vid, ruta, ruta + '.%', ruta + '/%', vid)).fetchall()
    else:
        filas_p = con.execute('SELECT ruta_estructural, titulo, texto_literal FROM precepto WHERE version_id=? ORDER BY orden', (vid,)).fetchall()
    rutas = [f['ruta_estructural'] for f in filas_p if f['ruta_estructural']]
    calidad_textual.aplicar(con, r, ruta, rutas_incluidas=rutas)
    r.ambito_pedido = ruta or 'documento completo'
    r.preceptos_localizados = len(filas_p)
    if not rutas:
        r.ambito_localizado = None
    elif len(rutas) == 1:
        r.ambito_localizado = rutas[0]
    else:
        r.ambito_localizado = f'{rutas[0]}..{rutas[-1]} ({len(rutas)} preceptos)'
    if ruta and len(rutas) > 1:
        r.detalle = '; '.join((x for x in (r.detalle, f'texto_literal conserva el texto propio (rótulo o cuerpo) de la unidad; el texto de ámbito reúne {len(rutas)} preceptos localizados, incluidos sus descendientes; esta agrupación no certifica la fidelidad del texto') if x))
    return (r, '\n'.join((f['texto_literal'] for f in filas_p)))
RX_TOKEN_FTS = re.compile('[^\\W_]+', re.UNICODE)

def frase_fts5(texto: str) -> str | None:
    """La busqueda de un humano, convertida en FRASE literal de FTS5.

    `buscar` pasaba el texto CRUDO a `MATCH`. Eso expone la sintaxis de consulta
    de FTS5 —comillas, parentesis, `AND`, `*`, `:`, `^`— sin haberla documentado
    en ningun sitio ni haberla probado nunca: `buscar "2026/339"` moria con
    `fts5: syntax error near "/"`, y el usuario no habia escrito ninguna
    expresion, habia escrito el numero de un reglamento.

    Se elige FRASE y no lista de terminos porque es lo que el usuario quiere
    decir: "2026/339" es una cita, no "2026 en alguna parte y 339 en otra". El
    tokenizador parte igual dentro de las comillas, asi que la frase busca los
    dos tokens SEGUIDOS, que es lo que hay en el texto.

    Devuelve None cuando no queda ni un token que buscar (cadena vacia, solo
    puntuacion, un `*` suelto). Un None es "no hay busqueda que hacer", y quien
    llama devuelve lista vacia SIN preguntar a la base: preguntar con una frase
    vacia es otro error de sintaxis, y este modulo no cambia un fallo por otro.
    """
    tokens = RX_TOKEN_FTS.findall(superindices.plegar(texto or ''))
    if not tokens:
        return None
    return '"' + ' '.join(tokens).replace('"', '""') + '"'

def buscar(con: sqlite3.Connection, consulta: str, limite: int=20, ambitos: tuple[str, ...]=('publico',)):
    """Busqueda de texto completo. `consulta` es un TEXTO, no una expresion FTS5.

    Ver `frase_fts5`: lo que llega se busca como frase literal. Quien quiera la
    sintaxis de FTS5 no la tiene aqui, y es deliberado: estaba disponible por
    accidente, sin documentar y sin probar, y lo unico que producia era que una
    cita con barra matara la orden.
    """
    expr = frase_fts5(consulta)
    if expr is None:
        return []
    tokens_crudos = RX_TOKEN_FTS.findall(consulta or '')
    sin_plegar = '"' + ' '.join(tokens_crudos).replace('"', '""') + '"' if tokens_crudos else None
    if sin_plegar and sin_plegar != expr:
        expr = f'{expr} OR {sin_plegar}'
    filas = con.execute("\n        SELECT p.id, p.ruta_estructural, p.etiqueta_humana, p.titulo,\n               o.identificador_canonico AS obra, o.titulo AS obra_titulo,\n               v.etiqueta AS version, d.ruta_relativa AS fichero, d.clase_derechos,\n               p.pagina_inicio, bm25(precepto_fts) AS puntuacion,\n               snippet(precepto_fts, 2, '[', ']', ' ... ', 18) AS fragmento\n        FROM precepto_fts\n        JOIN precepto p ON p.id = precepto_fts.rowid\n        JOIN version  v ON v.id = p.version_id\n        JOIN obra     o ON o.id = v.obra_id\n        JOIN documento d ON d.id = v.documento_id\n        WHERE precepto_fts MATCH ?\n        ORDER BY puntuacion LIMIT ?\n    ", (expr, limite * 3)).fetchall()
    out = []
    for f in filas:
        if f['clase_derechos'] not in REPRODUCIBLES and f['clase_derechos'] not in ambitos:
            continue
        out.append(dict(f))
        if len(out) >= limite:
            break
    return out
