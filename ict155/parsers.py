"""Analizadores por familia documental.

No hay analizador generico que valga. Un texto legal se trocea por su jerarquia
propia (capitulo, articulo, apartado, letra, anexo, apendice) y nunca por numero
de caracteres: si la unidad almacenada no coincide con la unidad citable, no hay
validacion de citas posible, que es todo el objeto del sistema.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, replace

from .extraccion import MOTOR_TEXTO_BOE, ExtraccionError, TextoPdf, limpiar_lineas

# ----------------------------------------------------------------- utilidades

ORDINALES = {
    "unica": 1, "unico": 1, "primera": 1, "primero": 1, "segunda": 2, "segundo": 2,
    "tercera": 3, "tercero": 3, "cuarta": 4, "cuarto": 4, "quinta": 5, "quinto": 5,
    "sexta": 6, "sexto": 6, "septima": 7, "septimo": 7, "octava": 8, "octavo": 8,
    "novena": 9, "noveno": 9, "decima": 10, "decimo": 10, "undecima": 11,
    "duodecima": 12, "decimotercera": 13, "decimocuarta": 14, "decimoquinta": 15,
    # De la decimosexta en adelante (5-oct-2026): la Ley 11/2022 llega a la trigesima.
    # Hasta entonces la ruta llevaba la palabra ("disp.adicional.decimosexta").
    "decimosexta": 16, "decimosexto": 16, "decimoseptima": 17, "decimoseptimo": 17,
    "decimoctava": 18, "decimoctavo": 18, "decimonovena": 19, "decimonoveno": 19,
    "vigesima": 20, "vigesimo": 20, "trigesima": 30, "trigesimo": 30,
    "cuadragesima": 40, "cuadragesimo": 40,
}

_SIN_TILDE = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


# Un ordinal compuesto: la decena y la unidad en dos palabras ("vigesima primera"). Con
# una sola palabra, las disposiciones adicionales vigesima primera a vigesima novena de
# la Ley 11/2022 tenian todas la ruta de la vigesima y la ingesta tiraba las nueve
# (5-oct-2026). Lo comparten la ingesta y la consulta.
ORD_COMPUESTO = (r"(?:vig|trig|cuadrag)[ée]sim[ao]\s+(?:primer[ao]|segund[ao]|tercer[ao]|cuart[ao]|"
                 r"quint[ao]|sext[ao]|s[ée]ptim[ao]|octav[ao]|noven[ao])")


def sin_tilde(s: str) -> str:
    return s.translate(_SIN_TILDE)


def ordinal_a_numero(palabra: str) -> str:
    p = sin_tilde(palabra.strip().lower())
    partes = p.split()
    if len(partes) >= 2 and re.fullmatch(ORD_LATINO, partes[-1]):
        # «tercera bis» es una disposición propia, no la tercera repetida.
        return ordinal_a_numero(' '.join(partes[:-1])) + ' ' + partes[-1]
    if (len(partes) == 2 and ORDINALES.get(partes[0]) in (20, 30, 40)
            and 1 <= ORDINALES.get(partes[1], 0) <= 9):
        return str(ORDINALES[partes[0]] + ORDINALES[partes[1]])
    return str(ORDINALES.get(p, palabra.strip().lower()))


# La cabecera de pagina del consolidado del BOE PEGADA al primer renglon del cuerpo: "LEGISLACION CONSOLIDADA
# ANEXO XIX" (Orden ICT/155/2020), "... ANEXO VII" a "X" (RD 188/2016), "... ANEXO II" (Orden ITC/3701/2006). El
# renglon no casaba con RUIDO ni empezaba por ANEXO: el anexo no se abria y su texto quedaba dentro del anterior,
# asi que su cita respondia PRECEPTO_INEXISTENTE (8-oct-2026, cotejo con el XML consolidado del BOE).
RE_CABECERA_BOE_PEGADA = re.compile(r"^\s*LEGISLACI[ÓO]N CONSOLIDADA\s+(?=\S)", re.I)

# Ruido de maquetacion que se repite en cada pagina.
RUIDO = (
    re.compile(r"^\s*BOLET[ÍI]N OFICIAL DEL ESTADO\s*$", re.I),
    re.compile(r"^\s*LEGISLACI[ÓO]N CONSOLIDADA\s*$", re.I),
    re.compile(r"^\s*P[áa]gina\s+\d+\s*$", re.I),
    re.compile(r"^\s*Este documento es un instrumento de documentaci[óo]n.*$", re.I),
    re.compile(r"^\s*Este texto es exclusivamente un instrumento de documentaci[óo]n.*$", re.I),
    re.compile(r"^\s*Diario Oficial de la Uni[óo]n Europea\s*$", re.I),
    re.compile(r"^\s*Official Journal of the European Union\s*$", re.I),
    # La misma cabecera en un solo renglon con su folio y su fecha, en un orden o en el otro:
    # "L 96/112 Diario Oficial de la Union Europea 29.3.2014". Asi la da la lectura en el orden
    # interno del PDF (`extraccion.DOCUMENTOS_EN_ORDEN_INTERNO`, 8-oct-2026).
    re.compile(r"^\s*(?:[LC]\s+\d{1,4}/\d{1,4}|\d{1,2}\.\d{1,2}\.\d{4})\s+"
               r"(?:Diario Oficial de la Uni[óo]n Europea|Official Journal of the European Union)\s+"
               r"(?:[LC]\s+\d{1,4}/\d{1,4}|\d{1,2}\.\d{1,2}\.\d{4})\s*$", re.I),
    # 02014L0030 — ES — ... y, con cuatro cifras, 2014L0032 — ES — ... (la MID consolidada:
    # hasta el 7-oct-2026 se exigian cinco y su pie estaba dentro de 76 preceptos).
    re.compile(r"^\s*\d{4,5}[A-Z]\d{4}\s+[—-]\s+[A-Z]{2}\s+[—-].*$"),
    re.compile(r"^\s*ES\s+Serie\s+[LC]\s*$"),
    # El numero de pagina entre rayas: "- 55 -" (VIM, UNECE ATP, EURAMET cg-8).
    re.compile(r"^\s*[-–]\s*\d{1,4}\s*[-–]\s*$"),
)

# Ruido propio de los documentos del BOE (11-oct-2026; docs/PREDICCION_texto_boe_2026-10-11.md), que se descarta en
# `analizar_boe` y en ningun otro analizador. Lo que el PDF imprime una sola vez, en la ultima pagina, y se quedaba pegado al
# final del ultimo precepto: los dos pies de «sin valor juridico» (a veces con «LEGISLACION CONSOLIDADA» pegado delante, que
# `RE_CABECERA_BOE_PEGADA` ya quita) y el pie del diario; y el membrete «Sec. I. Pag. N» de cada pagina del diario, que cambia
# de una a otra y no lo ve `lineas_repetidas`.
RUIDO_BOE = (
    re.compile(r"^\s*Este texto consolidado no tiene valor jur[íi]dico\.?\s*$", re.I),
    re.compile(r"^\s*Este documento es de car[áa]cter informativo y no tiene valor jur[íi]dico\.?\s*$", re.I),
    re.compile(r"^\s*https?://www\.boe\.es\s+D\.\s*L\.:.*ISSN.*$", re.I),
    re.compile(r"^\s*Sec\.\s+[IVX]+\.\s+P[áa]g\.\s+\d+\s*$", re.I),
)
# «Pagina N» PEGADO al final de un renglon de texto («...en el equipo radioelectrico: Pagina 37», RD 188/2016): el pie de
# pagina que Xpdf junta con el ultimo renglon. Solo se quita si N es el numero de la pagina del PDF en que esta (el pie de
# verdad lleva siempre el de su pagina).
RE_PAGINA_PEGADA = re.compile(r"\s+P[áa]gina\s+(\d+)\s*$")
# El mismo pie «sin valor juridico» PEGADO al final de un renglon de texto, tras «LEGISLACION CONSOLIDADA ... control del tiempo de
# respuesta.» (Orden ICT/155/2020, ultima pagina del anexo XXI): solo en la ultima pagina del documento.
RE_PIE_PEGADO_AL_FINAL = re.compile(
    r"\s+(?:Este texto consolidado no tiene valor jur[íi]dico|Este documento es de car[áa]cter informativo y no tiene valor "
    r"jur[íi]dico)\.?\s*$", re.I)

# Un entero solo en su linea. Casi siempre es ruido (un numero de pagina, de
# linea o de nota), pero en una tabla extraida celda a celda es el valor de la
# celda. Por eso no va en RUIDO: lo decide `motivos_de_enteros`. Revision P8 bis,
# ver PREDICCION_revision_P8bis.md.
RE_NUMERO_SUELTO = re.compile(r"^\s*\d+\s*$")

# Linea del indice de un texto del BOE: lleva puntos suspensivos de relleno.
# Los puntos conductores de un indice TERMINAN EN NUMERO DE PAGINA. Los de una
# linea de relleno de formulario, no. Esa es la diferencia, y no la longitud:
# el anexo del RD 237/2000 es un acta de ensayo ATP en blanco, con lineas como
# "Estac. de ensayo: ......................", y el patron anterior se las comia
# igual que se come una entrada de indice. Ese documento llevaba meses al 74,7 %
# de cobertura por esto.
#
# ENTRADAS PEGADAS (12-oct-2026, c138; docs de la revision c137, defecto D2). Xpdf junta a veces varias entradas de un indice en UNA linea
# («1. STRUCTURE....... 39 2. WATER METERS....... 41 3. GAS METERS... 47 ... 6. MEASURING SYSTEMS FOR THE CONTINUOUS AND DYNAMIC MEASUREMENT OF»,
# con el final de la ultima entrada en la linea siguiente). Si la linea acaba en el titulo cortado y no en un numero, la primera forma no la reconocia y el
# preambulo de la WELMEC 7.2 guardaba cinco entradas del indice, cortado a mitad de la sexta. Una linea con DOS o MAS «puntos de relleno + numero de pagina»
# es un indice aunque no acabe en numero. El numero de pagina es un entero solo (seguido de espacio o del final): «.......... 2. Empresa inscrita...» de un
# formulario en blanco (Orden ICT/155/2020, anexo XX) lleva punto detras del numero y no cuenta.
_PUNTOS_Y_PAGINA = r"(?:\.\s*){4,}\d{1,4}(?=\s|$)"
INDICE = re.compile(r"\.\s*\.\s*\.\s*\..*?\d+\s*$|" + _PUNTOS_Y_PAGINA + r".*?" + _PUNTOS_Y_PAGINA)

# Marcas de consolidacion de EUR-Lex: ▼B, ▼M1 en linea propia; ►C1 ... ◄ en linea.
# B es el texto base; M y C requieren numero. El cierre no lleva codigo:
# en «Isomalt ◄ Maltitol» la M pertenece al contenido, no a la marca.
_CODIGO_MARCA = r"(B|[MC]\d+)(?![^\W_])"
MARCA_BLOQUE = re.compile(r"^\s*[\u25bc\u25ba]\s*" + _CODIGO_MARCA + r"\s*$")
MARCA_INLINE = re.compile(r"\u25ba\s*" + _CODIGO_MARCA + r"|\u25c4")
# La marca puede abrir la linea del propio encabezado: "\u25bcB Art\u00edculo 2".
MARCA_INICIO = re.compile(r"^\s*[\u25bc\u25ba]\s*" + _CODIGO_MARCA + r"\s+(?=\S)")


# La marca puede ir DETRAS del numeral: "Articulo 40 [marca]M2", con la rubrica
# en la linea siguiente. Ni MARCA_BLOQUE (exige linea propia), ni MARCA_INICIO
# (exige abrir la linea), ni MARCA_INLINE (solo trata las marcas de
# rectificacion) la cazaban, y el articulo 40 del RED quedaba sin trocear.
# Regla general: una marca de consolidacion nunca es contenido, este donde este.
MARCA_RESTO = re.compile(r"[▼]\s*" + _CODIGO_MARCA)

# La tabla de correspondencias: el ultimo anexo de casi todo texto consolidado
# de la UE. Dos columnas, la izquierda con las divisiones de la norma DEROGADA y
# la derecha con las de la nueva. pdftotext aplana la tabla y cada celda queda
# sola al principio de una linea, que es justo donde el analizador busca
# encabezados. Resultado medido el 6-ago-2026: el articulo 1 de la RoHS, de la
# 2014/35 y de la RED en ingles NO era su articulo 1, era la tabla; y la MID
# tenia ocho anexos inventados, anexo.A a anexo.H, que son anexos de la
# Directiva 2004/22/CE, derogada.
#
# Conviene decir por que no bastaba `quedarse_con_el_cuerpo`, que ya existia
# para esto: elige, entre dos apariciones del mismo numero, la que tiene MAS
# TEXTO. El articulo 1 de una directiva es corto ("Objeto: la presente Directiva
# establece..."), y el bloque aplanado de la tabla es largo. La heuristica
# elegia la tabla. Una regla de "gana el mas largo" no puede distinguir un
# articulo breve de una lista de referencias.
#
# Sus filas no son encabezados. Un anexo posterior con rotulo y rubrica
# propios puede, sin embargo, cerrar la tabla (ver _anexo_tras_correspondencias).
RX_TABLA_CORRESP = re.compile(
    r"(?i)\btabla\s+de\s+correspondencias\b|\bcorrelation\s+table\b")
# El anexo SIN NUMERO cuya rubrica, en el MISMO renglon, es la tabla de correspondencias: "ANEXO TABLA DE
# CORRESPONDENCIAS" (Reglamento 2023/988 consolidado, 8-oct-2026). `RE_UE["anexo"]` solo admite "ANEXO" a secas o
# con numero, y el renglon no abria anexo: la tabla entera acababa en el texto del articulo 52.
RE_ANEXO_TABLA_CORRESP = re.compile(
    r"(?i)^\s*(?:ANEXO|ANNEX)\s+((?:tabla\s+de\s+correspondencias|correlation\s+table)\b.*?)\s*$")

# Comillas de apertura con que el BOE reproduce el texto nuevo de una norma
# modificativa. No son parte del encabezado que abren. Ver el comentario largo
# en `analizar_boe`, donde se usa, y pruebas/medir_anexos_entrecomillados.py.
COMILLAS_APERTURA = "«“”‘’\"'"

# El legislador europeo numera con la serie latina completa, no con los tres
# primeros ordinales. El codigo de medicamentos (2001/83-CE) llega hasta
# "octodecies". Admitir solo bis/ter/quater dejaba quince articulos sin trocear
# y producia un falso PRECEPTO_INEXISTENTE sobre articulado impreso en un
# ejemplar ingerido entero, que es la peor respuesta que este sistema da.
# El \b del final no es decorativo: sin el, la alternativa "ter" casa dentro de
# "terdecies", deja "decies" suelto y el encabezado deja de reconocerse entero.
ORD_LATINO = (r"(?:bis|ter|qu[áa]ter|quinquies|sexies|septies|octies|"
              r"nonies|decies|undecies|duodecies|terdecies|quaterdecies|"
              r"quindecies|sexdecies|septdecies|octodecies|novodecies|vicies|"
              r"unvicies|duovicies|tervicies|quatervicies)\b")

# Compartido por el encabezado del BOE y la cita humana, como los artículos.
ORD_DISPOSICION = rf"(?:{ORD_COMPUESTO}|[a-zñáéíóú]+)(?:\s+{ORD_LATINO})?"

# Y la serie CASTELLANA, que el legislador mezcla con la latina sin avisar. La
# Directiva 2001/83-CE imprime "Articulo 16 bis", "16 ter", "16 quater" y a
# continuacion "16 quinto", "16 sexto", "16 septimo", "16 octavo", "16 nono" y
# "16 decimo". Sin ella, esos seis articulos no existian y el art.16 quater se
# los tragaba: media 12.894 caracteres frente a los 267 de su hermano.
ORD_CASTELLANO = (r"(?:primero|segundo|tercero|cuarto|quinto|sexto|"
                  r"s[ée]ptimo|octavo|noveno|nono|d[ée]cimo|und[ée]cimo|"
                  r"duod[ée]cimo|decimotercero|decimocuarto|decimoquinto|"
                  r"decimosexto|decimos[ée]ptimo|decimoctavo|decimonoveno|"
                  r"vig[ée]simo)\b")

# El vocabulario de ordinales de un articulo es UNO y lo comparten la ingesta y
# la consulta (ver consulta.RE_ART). Aqui compartir es lo correcto y conviene
# distinguirlo de lo que salio mal el 5 de agosto: un detector que AUDITA no
# puede compartir listas con lo que audita, porque entonces mide su propio
# vocabulario. Dos piezas que tienen que COINCIDIR si deben compartirlo: si
# divergen, el sistema almacena con un nombre y busca con otro.
ORD_ARTICULO = rf"(?:{ORD_LATINO}|{ORD_CASTELLANO})"


RX_ORDINAL_PEGADO = re.compile(rf"^(\d+)(?=(?i:{ORD_ARTICULO}))")


def numeral_articulo(s: str) -> str:
    """El numeral de un articulo tal como va en la ruta.

    El ordinal, en minuscula y sin tildes; el numero, como esta. Sin quitar la
    tilde la ruta seria `art.16 séptimo` y quien citara "septimo" recibiria un
    PRECEPTO_INEXISTENTE, que es el defecto que esta reparacion viene a quitar.
    Con ella, y aplicando la misma normalizacion en la consulta, las dos
    grafias llevan al mismo sitio.

    Y el ordinal pegado al numero se separa: "16bis" y "16 bis" son el mismo
    articulo y tienen que dar la misma ruta (revision P17, ver
    PREDICCION_revision_P17.md).
    """
    s = RX_ORDINAL_PEGADO.sub(r"\1 ", s.strip())
    partes = re.sub(r"\s+", " ", s).split(" ")
    if len(partes) == 1:
        return partes[0]
    return partes[0] + " " + " ".join(sin_tilde(p.lower()) for p in partes[1:])

# Numeral de una division: romano, arabigo o una letra suelta. Se dan los tres.
# Y puede llevar ordinal latino detras, exactamente igual que el de un articulo:
# "ANEXO I BIS" es una division distinta de "ANEXO I", como art.16 bis lo es de
# art.16. Sin esto, el 5 de agosto de 2026 se destruyeron dos divisiones de
# normas vigentes: el Capitulo V bis del Anexo II del Reglamento 852/2004 y el
# Anexo I bis del RD 188/2016. La regla de la rubrica pegada leia "V BIS" como
# numeral V mas rubrica BIS, la ruta colisionaba con la del Capitulo V verdadero
# y la ingesta descartaba la segunda en silencio.
#
# El (?i:...) es necesario: dos de estas expresiones NO llevan re.I, y el BOE
# escribe BIS y bis para lo mismo. De hecho la caja decidia si la division se
# destruia o solo perdia citabilidad, que es el hallazgo que destapo el caso.
#
# El ordinal va en su propia pieza porque la consulta lo comparte (revision P3,
# ver PREDICCION_revision_P3.md): la ingesta crea `anexo.I bis` y la consulta
# tiene que leer "anexo I bis" con el mismo vocabulario. NUM_DIV queda igual.
ORD_DIV = rf"\s+(?i:{ORD_LATINO})"
NUM_DIV = rf"(?:[IVXLC]+|\d+|[A-Z])(?:{ORD_DIV})?"


def numeral_division(s: str) -> str:
    """El numeral tal como va en la ruta: ordinal latino en minuscula.

    El ejemplar imprime BIS o bis indistintamente. Una ruta que dependiera de la
    caja obligaria a acertar con ella al citar, que es la misma razon por la que
    `unico` va sin tilde. Se normaliza el ordinal y se deja el numeral como esta:
    los romanos son mayusculas y ahi la caja si significa.
    """
    partes = s.split()
    if not partes:
        # Un anexo sin numeral: "ANEXO" a secas. El grupo viene vacio y la ruta
        # sale sin sufijo, que es lo correcto. Sin esta guarda, la primera
        # version reventaba con IndexError y tumbaba la ingesta de cinco
        # documentos enteros, entre ellos la Directiva 2001/83-CE. Se vio porque
        # el recuento de preceptos cayo de 12.364 a 10.797: el fallo fue ruidoso
        # y la comprobacion lo cazo antes de publicar nada.
        return ""
    if len(partes) == 1:
        return partes[0]
    return partes[0] + " " + " ".join(p.lower() for p in partes[1:])

# Una rubrica empieza en mayuscula; una remision del cuerpo sigue en minuscula
# ("del anexo II del Reglamento..."). Es el mismo discriminante que ya usaba el
# encabezado de articulo de EUR-Lex, aplicado ahora a las divisiones: un
# encabezado de division admite rubrica en la misma linea, igual que uno de
# articulo. Exigir que el numeral cerrase la linea dejaba 217 divisiones sin
# trocear en 62 documentos de 101.
# El (?-i:...) no es adorno: varias de estas expresiones llevan re.I para
# admitir "Annex" o "Anexo", y con re.I la clase [A-Z] casa tambien minusculas,
# de modo que el discriminante dejaba de discriminar y "ANEXO II del Real
# Decreto 244/2016" se reconocia como encabezado. Lo caza el juego sistematico.
RUBRICA = r"(?:\s+((?-i:[A-ZÁÉÍÓÚÑ]).*))?"


@dataclass
class Precepto:
    ruta: str
    tipo: str
    numero: str | None
    etiqueta: str
    titulo: str | None
    lineas: list[str] = field(default_factory=list)
    pagina_inicio: int = 1
    pagina_fin: int = 1
    padre: str | None = None
    marca: str | None = None
    metodo: str = "capa_texto"
    # Una entrada de indice que el analizador reconocio como tal (ver `_trocear_guia`):
    # pierde frente a la aparicion del cuerpo en `quedarse_con_el_cuerpo`. No se guarda.
    de_indice: bool = False

    @property
    def texto(self) -> str:
        return limpiar_lineas("\n".join(self.lineas))

    @property
    def sin_texto_aun(self) -> bool:
        """Ningun renglon con texto todavia. Los renglones en blanco que abren un precepto (el preambulo de
        un documento cuya primera pagina esta vacia: las guias CEM C-01 a C-05, ILAC G27) no cuentan para
        decir donde empieza: su pagina de comienzo es la del primer renglon con texto (9-oct-2026)."""
        return not any(x.strip() for x in self.lineas)


@dataclass
class Analisis:
    preceptos: list[Precepto] = field(default_factory=list)
    identificador: str | None = None
    titulo: str | None = None
    fecha_consolidacion: str | None = None
    es_consolidada: bool = False
    cabecera: str | None = None
    idioma: str = "es"


# Lo que cuenta como borde de la pagina para la regla de las lineas repetidas, y
# que parte de las apariciones de una linea tiene que caer en el (4-oct-2026).
LINEAS_DE_BORDE = 3
EN_EL_BORDE = 0.8
# Maquetacion que la extraccion pone a veces en medio de la pagina: la fecha de la
# cabecera del DOUE ("13.8.2008") y el pie de verificacion del BOE ("cve: ...
# Verificable en http://www.boe.es").
RE_SOLO_FECHA = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{4}\s*$")
RE_PIE_DE_VERIFICACION = re.compile(r"\bcve:|https?://|www\.", re.I)


def lineas_repetidas(pdf: TextoPdf, umbral: float = 0.5) -> set[str]:
    """Lineas que se repiten en la mayoria de las paginas: membrete o pie.

    Regla general y no una lista de documentos conocidos: lo que aparece igual
    en mas de la mitad de las paginas de un documento es maquetacion, no
    contenido. En la Guia CEM C-01 el membrete del Centro Espanol de Metrologia
    se extraia como texto en medio de una frase y la partia en dos, de modo que
    una cita literal correcta dejaba de encontrarse.
    """
    if pdf.n_paginas < 4:
        return set()
    from collections import Counter
    c: Counter = Counter()
    en_borde: Counter = Counter()
    for pag in pdf.paginas:
        lineas = [x.strip() for x in pag.split("\n") if x.strip()]
        borde = set(lineas[:LINEAS_DE_BORDE] + lineas[-LINEAS_DE_BORDE:])
        for ln in {x for x in lineas if len(x) > 3}:
            c[ln] += 1
            if ln in borde:
                en_borde[ln] += 1
    minimo = max(3, int(pdf.n_paginas * umbral))
    # No se descarta una linea larga: un parrafo repetido es contenido.
    #
    # Y una linea repetida EN MEDIO de la pagina tampoco, salvo que sea solo una
    # fecha o un pie de verificacion (4-oct-2026, "que no se pierda nada de los
    # originales"). Hasta entonces se quitaba cualquier repetida, y en las guias
    # hechas con tablas se iban las cabeceras de columna ("DIRECTIVE 2014/31/EU
    # (NAWID)", "Provisions in Annex II, module D" en la WELMEC 8.6) y celdas que
    # se repiten fila a fila ("ISO/IEC 17065" en la EA-2/17 S1). Medido: 16 de 112
    # documentos; ver docs/PREDICCION_tablas_sin_perdida_2026-10-04.md. La
    # cabecera o el pie de verdad va en el borde de la pagina casi siempre.
    #
    # Y la que lleva el CODIGO DEL PROPIO DOCUMENTO tambien es maquetacion, este
    # donde este: la cabecera del CGA-ENAC-OCML ("CGA-ENAC-OCML Rev.4, Mayo 2021
    # Series 1, 4, 5, 7 y 13") sale en medio de la pagina y, si se queda, el
    # analizador deja de ver "Anexo IV" al principio de pagina y mete el anexo IV
    # dentro del III (primera medicion del 4-oct-2026, refutada).
    identidad = _codigos_del_fichero(pdf.ruta_relativa)
    return {ln for ln, n in c.items()
            if n >= minimo and len(ln) <= 120
            and (en_borde[ln] >= EN_EL_BORDE * n
                 or RE_SOLO_FECHA.match(ln) or RE_PIE_DE_VERIFICACION.search(ln)
                 or _lleva_codigo(ln, identidad))}


# Una cabecera o un pie con el numero de pagina en el mismo renglon, o con otros espacios
# ("JCGM © 2008 - Reservados todos los derechos          10", "14   ETSI EN 300 328 V2.2.2
# (2019-07)"), o revuelto por Xpdf ("JCGM © 2012 – Reservados todos los de-r5ec1ho- s",
# "EEll ppaappeell ddee llaa..." de la negrita) cambia en cada pagina y `lineas_repetidas` no
# lo ve (7-oct-2026). Ver `lineas_de_maquetacion`.
RE_NUMERO_EN_EL_BORDE = re.compile(r"^\s*(\d{1,4})\s+(.*?)\s*$|^\s*(.*?)\s+(\d{1,4})\s*$")
LETRAS_MINIMAS_DE_MEZCLA = 12


def _sin_numero_de_pagina(ln: str) -> tuple[str, int | None]:
    """(renglon sin el numero del principio o del final y con los espacios juntos, numero)."""
    m = RE_NUMERO_EN_EL_BORDE.match(ln)
    if not m:
        return " ".join(ln.split()), None
    if m.group(1) is not None:
        return " ".join(m.group(2).split()), int(m.group(1))
    return " ".join(m.group(3).split()), int(m.group(4))


def _letras(ln: str) -> tuple:
    from collections import Counter
    return tuple(sorted(Counter(ch for ch in ln.casefold() if ch.isalpha()).items()))


def _cifras(ln: str):
    from collections import Counter
    return Counter(ch for ch in ln if ch.isdigit())


def lineas_de_maquetacion(pdf: TextoPdf) -> set[str]:
    """Las lineas repetidas (`lineas_repetidas`) y, en el borde de las paginas (no en la
    primera, de la que salen el titulo y el emisor), sus variantes:

    - la misma cabecera o pie con el numero de pagina al principio o al final, o con otros
      espacios. El numero es el de la pagina si su diferencia con el indice de la pagina es
      la misma en la mitad o mas de sus apariciones (y en tres o mas): asi "4 Requirements"
      no se confunde con una cabecera "Requirements";
    - el renglon con exactamente las mismas letras que una cabecera o pie, o que esa misma
      dos veces: la mezcla que hace Xpdf de dos capas superpuestas. La suma de dos distintas
      no cuenta: en el Reglamento de ciberresiliencia es una nota al pie que repite la
      cabecera.

    `lineas_repetidas` no cambia: de ella sale tambien el mobiliario del validador."""
    repetidas = lineas_repetidas(pdf)
    return repetidas | _variantes_de_maquetacion(pdf, repetidas)


def _variantes_de_maquetacion(pdf: TextoPdf, repetidas: set[str]) -> set[str]:
    """Las variantes de `lineas_de_maquetacion`, sin las repetidas."""
    from collections import Counter, defaultdict
    if pdf.n_paginas < 4 or not repetidas:
        return set()
    bases = {" ".join(x.split()) for x in repetidas}
    # Por las letras de cada cabecera (o de ella dos veces), las cifras que tiene que llevar.
    letras_de: dict[tuple, list] = defaultdict(list)
    for x in bases:
        if sum(ch.isalpha() for ch in x) >= LETRAS_MINIMAS_DE_MEZCLA:
            una, cif = dict(_letras(x)), _cifras(x)
            letras_de[tuple(sorted(una.items()))].append(cif)
            letras_de[tuple(sorted((k, 2 * v) for k, v in una.items()))].append(cif + cif)
    candidatos: list[tuple[int, str]] = []
    for i, pag in enumerate(pdf.paginas):
        if i == 0:
            continue
        lineas = [x.strip() for x in pag.split("\n") if x.strip()]
        for ln in set(lineas[:LINEAS_DE_BORDE] + lineas[-LINEAS_DE_BORDE:]):
            if ln not in repetidas:
                candidatos.append((i + 1, ln))
    desfases: dict[str, Counter] = defaultdict(Counter)
    for pag, ln in candidatos:
        clave, n = _sin_numero_de_pagina(ln)
        if n is not None and clave in bases:
            desfases[clave][n - pag] += 1
    variantes = set()
    for pag, ln in candidatos:
        if " ".join(ln.split()) in bases:
            # La misma cabecera con otros espacios.
            variantes.add(ln)
            continue
        clave, n = _sin_numero_de_pagina(ln)
        if clave in bases:
            # Cabecera con un numero separable: solo vale si es el de la pagina.
            if n is None:
                variantes.add(ln)
            else:
                total = sum(desfases[clave].values())
                d, veces = desfases[clave].most_common(1)[0]
                if n - pag == d and veces >= 3 and 2 * veces >= total:
                    variantes.add(ln)
            continue
        # Revuelta: las mismas letras y todas las cifras de la cabecera, con hasta cuatro de
        # mas (las del numero de pagina metido dentro).
        if sum(ch.isalpha() for ch in ln) < LETRAS_MINIMAS_DE_MEZCLA:
            continue
        cif = _cifras(ln)
        for necesarias in letras_de.get(_letras(ln), ()):
            if not (necesarias - cif) and sum((cif - necesarias).values()) <= 4:
                variantes.add(ln)
                break
    return variantes


def _codigos_del_fichero(ruta_relativa: str) -> set[str]:
    """Las palabras del nombre del fichero que pueden ser su codigo: seis caracteres
    o mas, con alguna letra ("CGA-ENAC-OCML", "WELMEC", "EudraLex")."""
    nombre = re.split(r"[\\/]", ruta_relativa or "")[-1].rsplit(".", 1)[0]
    return {t.casefold() for t in nombre.split("_")
            if len(t) >= 6 and re.search(r"[^\W\d_]", t)}


def _lleva_codigo(linea: str, codigos: set[str]) -> bool:
    return any(t.casefold() in codigos for t in re.findall(r"[\w][\w\-.]*", linea))


# CABECERAS Y PIES EN TIRADA, SOLO EN LAS GUIAS (11-oct-2026; docs/PREDICCION_cabeceras_dentro_2026-10-11.md).
# `lineas_repetidas` y sus variantes quitan el renglon que se repite ENTERO en la mitad de las paginas. Se le
# escapan cuatro cosas, y dejaban la cabecera o el pie de una pagina dentro del texto del precepto (y, si caian al
# final, alargaban su rango de paginas hasta la pagina siguiente):
#
#  1. La cabecera PARTIDA de otra manera en cada pagina: un renglon en unas, dos o tres en otras (el VIM de la capa
#     duplicada: «Traducción del VIM-3ª edición (2012)» y «(incluye pequeñas correcciones)»; la ENAC: «Control
#     Metrológico del Estado: Requisitos de competencia técnica de organismos notificados, de control metrológico y
#     autorizados de verificación» en uno, dos o tres renglones). Ninguna forma llega sola a la mitad de las paginas;
#     juntas, si.
#  2. La cabecera de las paginas IMPARES (o la de las pares): la JCGM 106 pone «JCGM 106:2012. Primera edición en
#     español. 2015» en 33 de 74 paginas, que son casi todas las impares y no llegan a la mitad del documento.
#  3. La cabecera pegada al titulo corriente del capitulo («Expresión de la incertidumbre de medida: 2008 (Esp)
#     Ejemplos» en la GUM), o dos cabeceras en un solo renglon («WELMEC Guide 7.2 Software Guide Version 2026»).
#  4. El numero de pagina «n/N» del pie (ENAC: «1/1», «5/5»), que no es un entero suelto.
#
# La regla. Una TIRADA es de 1 a TIRADA_MAXIMA renglones seguidos que caen enteros dentro de los LINEAS_DE_BORDE
# primeros o ultimos de una pagina. En las paginas que no son la primera se quita la tirada cuyo texto, sin blancos,
#   (a) es el de una cabecera o un pie que ya se quita (`lineas_repetidas` y sus variantes), partido de otra manera;
#   (b) se repite como tirada en la mitad de las paginas, o en la mitad de las pares o de las impares, y en
#       PAGINAS_MINIMAS_EN_TIRADA o mas, y el 80 % de las paginas donde aparece lo lleva en el borde;
#   (c) se escribe como una sucesion de cabeceras o pies conocidos (dos cabeceras en un renglon);
#   (d) es una cabecera conocida o descubierta (b) seguida en el mismo renglon de un titulo corriente: sin cifras y
#       tras dos blancos, o el mismo en TITULOS_CORRIENTES paginas (una cifra tras la cabecera es un numero de
#       pagina: «Page 4», y esas no se tocan); o
#   (e) es «n/N» y hay uno asi en el borde de la mitad de las paginas.
# Las de un solo renglon descubiertas en (b) se quitan en cualquier sitio de la pagina, como las repetidas. Nunca se
# toca la primera pagina (de ella salen el titulo y el emisor), ni una tirada que se quita ya entera, ni una que no
# tenga mas que renglones de tres caracteres o menos («ES», «▼B»). Solo las guias: la legislacion (BOE y EUR-Lex)
# tiene su mobiliario conocido en `RUIDO`.
TIRADA_MAXIMA = 3
PAGINAS_MINIMAS_EN_TIRADA = 8
LARGO_MINIMO_DE_TIRADA = 8
LARGO_MAXIMO_DE_TIRADA = 360
LARGO_MINIMO_DE_CABECERA = 16
LARGO_MAXIMO_DE_TITULO_CORRIENTE = 80
TITULOS_CORRIENTES = 3
RE_CELDAS = re.compile(r"\s{2,}")
RE_N_DE_M = re.compile(r"^\d{1,3}/\d{1,3}$")


def _es_n_de_m(texto: str) -> bool:
    """«3/5»: el numero de pagina de un pie, con n entre 1 y N."""
    if not RE_N_DE_M.match(texto):
        return False
    n, m = (int(x) for x in texto.split("/"))
    return 1 <= n <= m


def _es_de_guia(pdf: TextoPdf) -> bool:
    from . import catalogo
    return catalogo.familia(pdf.ruta_relativa or "") == "guia"


def _clave_de_maquetacion(texto: str) -> str:
    return "".join(texto.split())


def _zona_de_borde(n: int) -> set[int]:
    return set(range(min(LINEAS_DE_BORDE, n))) | set(range(max(0, n - LINEAS_DE_BORDE), n))


def _tiradas_del_borde(n: int, zona: set[int]):
    """(inicio, largo) de las tiradas de renglones seguidos que caen enteras en la zona de borde."""
    for s in sorted(zona):
        for largo in range(1, TIRADA_MAXIMA + 1):
            if s + largo > n or (s + largo - 1) not in zona:
                break
            yield s, largo


def _se_escribe_con(clave: str, bases: list[str]) -> bool:
    """Si `clave` es una sucesion de claves de cabeceras o pies conocidos, sin sobrar ni faltar una letra."""
    if not (any(clave.startswith(b) for b in bases) and any(clave.endswith(b) for b in bases)):
        return False
    alcanza = [False] * (len(clave) + 1)
    alcanza[0] = True
    for i in range(len(clave)):
        if alcanza[i]:
            for b in bases:
                if clave.startswith(b, i):
                    alcanza[i + len(b)] = True
    return alcanza[-1]


def _resto_tras(texto: str, clave: str) -> tuple[int, str] | None:
    """Si `texto` empieza por `clave` (sin contar los blancos) y sigue, tras algun blanco, con algo mas: (cuantos
    blancos, eso que sigue)."""
    j = 0
    for i, c in enumerate(texto):
        if c.isspace():
            continue
        if c != clave[j]:
            return None
        j += 1
        if j == len(clave):
            resto = texto[i + 1:]
            sin = resto.lstrip()
            return (len(resto) - len(sin), sin) if sin and resto[:1].isspace() else None
    return None


def _titulo_corriente(resto: str, hueco: int) -> bool:
    """Lo que sigue a una cabecera en su renglon es un titulo corriente: con letras, corto, sin cifras y tras mas de
    un blanco (una cifra tras la cabecera es un numero de pagina: «Page 4»)."""
    return (hueco >= 2 and any(c.isalpha() for c in resto) and len(resto) <= LARGO_MAXIMO_DE_TITULO_CORRIENTE
            and not any(c.isdigit() for c in resto))


def _maquetacion_en_tirada(pdf: TextoPdf, repetidas: set[str],
                           variantes: set[str]) -> tuple[dict[int, frozenset[int]], set[str]]:
    """({indice de pagina: indices (en el texto de la pagina partido por saltos) de los renglones de cabecera o pie
    que hay que quitar ademas de los que ya quitan `lineas_repetidas` y sus variantes}, los textos de lo que se
    quita, con los blancos juntos y «#/#» para el «n/N»). Ver arriba."""
    from collections import defaultdict
    paginas = pdf.paginas
    n = len(paginas)
    if n < 4 or pdf.n_paginas < 4:
        return {}, set()
    quitadas = repetidas | variantes
    # Por pagina, sus renglones con texto: (indice, texto, ya se quita, sin sustancia).
    vistas: list[list[tuple[int, str, bool, bool]]] = []
    for i, pag in enumerate(paginas):
        lin = []
        for k, ln in enumerate(pag.split("\n")):
            t = ln.strip()
            if t:
                ya = (any(r.match(ln) for r in RUIDO) or t in (quitadas if i else repetidas)
                      or RE_NUMERO_SUELTO.match(t) is not None)
                lin.append((k, t, ya, len(t) <= 3))
        vistas.append(lin)

    def texto_de(tramo) -> str:
        return " ".join(" ".join(t.split()) for _, t, _, _ in tramo)

    def sin_novedad(tramo) -> bool:
        return all(ya or sin for _, _, ya, sin in tramo)

    minimo = max(PAGINAS_MINIMAS_EN_TIRADA, int(n * 0.5))
    clases = [set(range(0, n, 2)), set(range(1, n, 2))]
    minimo_clase = [max(PAGINAS_MINIMAS_EN_TIRADA, int(len(c) * 0.5)) for c in clases]

    # 1. Las tiradas del borde de cada pagina y en cuantas paginas sale cada una.
    en_borde: dict[str, set[int]] = defaultdict(set)
    texto_de_clave: dict[str, str] = {}
    de_un_renglon: set[str] = set()
    cabezas: dict[str, set[int]] = defaultdict(set)
    n_de_m: set[int] = set()
    for i, lin in enumerate(vistas):
        zona = _zona_de_borde(len(lin))
        for s, largo in _tiradas_del_borde(len(lin), zona):
            tramo = lin[s:s + largo]
            if sin_novedad(tramo):
                continue
            texto = texto_de(tramo)
            if LARGO_MINIMO_DE_TIRADA <= len(texto) <= LARGO_MAXIMO_DE_TIRADA:
                c = _clave_de_maquetacion(texto)
                en_borde[c].add(i)
                texto_de_clave.setdefault(c, texto)
                if largo == 1:
                    de_un_renglon.add(c)
        for s in zona:
            t = lin[s][1]
            if _es_n_de_m(t):
                n_de_m.add(i)
            celdas = [x for x in RE_CELDAS.split(t) if x]
            if (len(celdas) >= 2 and len(celdas[0]) >= LARGO_MINIMO_DE_CABECERA
                    and _titulo_corriente(" ".join(celdas[1:]), 2)):
                cabezas[_clave_de_maquetacion(celdas[0])].add(i)

    # 2. Cuales llegan: la mitad de las paginas, o de las pares, o de las impares; y casi siempre en el borde.
    candidatas = {c for c, ps in en_borde.items()
                  if len(ps) >= minimo or any(len(ps & clases[p]) >= minimo_clase[p] for p in (0, 1))}
    candidatas_cabecera = {c for c, ps in cabezas.items() if len(ps | en_borde.get(c, set())) >= minimo}
    en_cualquier_sitio: dict[str, set[int]] = defaultdict(set)
    if candidatas or candidatas_cabecera:
        for i, lin in enumerate(vistas):
            for s in range(len(lin)):
                for largo in range(1, TIRADA_MAXIMA + 1):
                    if s + largo > len(lin):
                        break
                    c = _clave_de_maquetacion(texto_de(lin[s:s + largo]))
                    if c in candidatas or c in candidatas_cabecera:
                        en_cualquier_sitio[c].add(i)
                celdas = [x for x in RE_CELDAS.split(lin[s][1]) if x]
                if len(celdas) >= 2:
                    c = _clave_de_maquetacion(celdas[0])
                    if c in candidatas_cabecera:
                        en_cualquier_sitio[c].add(i)
    nuevas = {c for c in candidatas if len(en_borde[c]) >= 0.8 * len(en_cualquier_sitio[c])}
    cabeceras_nuevas = {c for c in candidatas_cabecera
                        if len(cabezas[c] | en_borde.get(c, set())) >= 0.8 * len(en_cualquier_sitio[c])}
    pie_n_de_m = len(n_de_m) >= minimo

    # 3. Los renglones que se quitan.
    conocidas = {_clave_de_maquetacion(q) for q in quitadas if len(q.strip()) > 3}
    claves_conocidas = conocidas | nuevas | cabeceras_nuevas
    bases = sorted(c for c in claves_conocidas if len(c) >= LARGO_MINIMO_DE_TIRADA)
    cabeceras = [c for c in bases if len(c) >= LARGO_MINIMO_DE_CABECERA - 2]
    # Las descubiertas de un solo renglon se quitan en cualquier sitio de la pagina, como las repetidas.
    planas = (nuevas & de_un_renglon) | cabeceras_nuevas
    # Los titulos corrientes que se repiten: una cabecera y «Ejemplos» en 18 paginas.
    titulos: dict[tuple[str, str], set[int]] = defaultdict(set)
    for i, lin in enumerate(vistas):
        if i:
            for s in _zona_de_borde(len(lin)):
                _, t, ya, _ = lin[s]
                if not ya:
                    for c in cabeceras:
                        r = _resto_tras(t, c)
                        if r:
                            titulos[(c, _clave_de_maquetacion(r[1]))].add(i)

    quitar: dict[int, set[int]] = defaultdict(set)
    textos: set[str] = set()
    for i, lin in enumerate(vistas):
        if i == 0:
            continue
        zona = _zona_de_borde(len(lin))
        for s, largo in _tiradas_del_borde(len(lin), zona):
            tramo = lin[s:s + largo]
            if sin_novedad(tramo):
                continue
            texto = texto_de(tramo)
            c = _clave_de_maquetacion(texto)
            if LARGO_MINIMO_DE_TIRADA <= len(texto) <= LARGO_MAXIMO_DE_TIRADA and (
                    c in claves_conocidas or _se_escribe_con(c, bases)):
                quitar[i].update(k for k, _, _, _ in tramo)
                textos.add(texto)
        for k, t, ya, _ in lin:
            if not ya and _clave_de_maquetacion(t) in planas:
                quitar[i].add(k)
                textos.add(" ".join(t.split()))
        for s in zona:
            k, t, ya, _ = lin[s]
            if ya or k in quitar[i]:
                continue
            if pie_n_de_m and _es_n_de_m(t):
                quitar[i].add(k)
                textos.add("#/#")
                continue
            for c in cabeceras:
                r = _resto_tras(t, c)
                if r and (_titulo_corriente(r[1], r[0])
                          or len(titulos[(c, _clave_de_maquetacion(r[1]))]) >= TITULOS_CORRIENTES):
                    quitar[i].add(k)
                    textos.add(" ".join(t.split()))
                    break
    return {i: frozenset(ks) for i, ks in quitar.items() if ks}, textos


def textos_de_maquetacion_en_tirada(pdf: TextoPdf) -> list[str]:
    """Los textos de lo que `paginas_vivas` quita de un documento como cabecera o pie en tirada, para el mobiliario del
    validador (`mobiliario.detectar`): una cita copiada del PDF lleva esos renglones y el texto guardado ya no."""
    if not _es_de_guia(pdf):
        return []
    repetidas = lineas_repetidas(pdf)
    return sorted(_maquetacion_en_tirada(pdf, repetidas, _variantes_de_maquetacion(pdf, repetidas))[1])


# Revision P8 bis: cuando un entero suelto es una celda. Las medidas salen de la
# medicion local de P8 (PREDICCION_revision_P8.md, Resultado): una celda vive
# entre lineas cortas; un numero de linea, de nota o de pagina, entre lineas
# largas, y la numeracion de lineas va de uno en uno.
VECINA_CORTA = 25       # caracteres: hasta aqui, una vecina de celda
VECINA_LARGA = 40       # caracteres: desde aqui, una vecina de prosa
TIRADA_MINIMA = 5       # enteros de uno en uno, separados por texto, en una pagina
# Entrada numerada de un indice o de un encabezado: "5 Principios basicos",
# "5.1 Generalidades", "B.2 Ejemplo". Detras del numero, una letra.
RE_ENTRADA_INDICE = re.compile(
    r"^\s*(?:\d+(?:\.\d+){0,3}|[A-Z](?:\.\d+){1,3})\.?\s+[^\W\d]")
# Entrada de indice con puntos de relleno cuyo numero de pagina ha salido en la
# linea siguiente: la misma linea que INDICE, sin el numero al final.
RE_PUNTOS_SIN_PAGINA = re.compile(r"\.\s*\.\s*\.\s*\.\s*$")
# Campana cero errores, punto 6: dos formas de ruido que P8 bis dejaba pasar.
#
# Un indice sin puntos de relleno: EA 4-02 M pone en su pagina 3 "CONTENTS" y
# debajo, en lineas propias, los numeros de seccion y de pagina entre titulos en
# mayusculas. No hay puntos ni entradas numeradas, asi que la regla del indice no
# lo veia y entraban 29 numeros en el preambulo. Lo que si tiene es el rotulo: si
# una de las primeras lineas de la pagina es solo el rotulo de un indice, la
# pagina es un indice y sus enteros sueltos no son celdas.
RE_ROTULO_INDICE = re.compile(
    r"^\s*(?:TABLE\s+OF\s+CONTENTS|CONTENTS|[ÍI]NDICE(?:\s+GENERAL)?|SUMARIO"
    r"|CONTENIDOS?|TABLE\s+DES\s+MATI[ÈE]RES|INHALTSVERZEICHNIS)\s*$", re.I)
LINEAS_DEL_ROTULO = 3   # el rotulo va arriba: entre las tres primeras lineas
# El numero de disposicion del BOE de papel (anterior a la serie BOE-A): un
# entero en su linea, justo encima del titulo de la disposicion ("21021" y
# debajo "ORDEN de 2 de septiembre de 1996..."). No es una celda.
RE_TITULO_DISPOSICION = re.compile(
    r"^\s*(?:ORDEN|REAL\s+DECRETO(?:-LEY)?|DECRETO|LEY(?:\s+ORG[ÁA]NICA)?"
    r"|RESOLUCI[ÓO]N|CORRECCI[ÓO]N|CIRCULAR|INSTRUCCI[ÓO]N|ACUERDO)\s+de\s")
DIGITOS_DISPOSICION = 5
CELDA = "celda"


def paginas_vivas(pdf: TextoPdf) -> list[list[str]]:
    """Las lineas de cada pagina sin el ruido de RUIDO ni la maquetacion
    (`lineas_de_maquetacion`) y, en las guias, sin las cabeceras y pies en tirada
    (`_maquetacion_en_tirada`). Los enteros sueltos siguen aqui: los filtra
    `lineas_con_pagina`."""
    repetidas = lineas_repetidas(pdf)
    # Las variantes, nunca en la primera pagina: de ella salen el titulo y el emisor.
    variantes = _variantes_de_maquetacion(pdf, repetidas)
    con_variantes = repetidas | variantes
    # Las cabeceras y los pies en tirada (solo las guias): ver `_maquetacion_en_tirada`.
    en_tirada = _maquetacion_en_tirada(pdf, repetidas, variantes)[0] if _es_de_guia(pdf) else {}
    return [[ln for k, ln in enumerate(pag.split("\n"))
             if not any(r.match(ln) for r in RUIDO)
             and ln.strip() not in (con_variantes if i else repetidas)
             and k not in en_tirada.get(i, ())]
            for i, pag in enumerate(pdf.paginas)]


def paginas_con_indice(paginas: list[list[str]]) -> set[int]:
    """Las paginas (desde 1) que son de un indice por SUS ENTEROS SUELTOS: tres o mas justo detras de una
    entrada numerada, en orden no decreciente (el numero de pagina de cada entrada, que Xpdf pone en su propio
    renglon), o con el rotulo de un indice entre sus primeras lineas. Sin puntos de relleno: es lo que distingue
    la segunda pagina del indice de la JCGM 101 ("9.2 Modelo aditivo" / "44"), que `_lineas_de_guia` no ve.
    Es la regla "indice" de `motivos_de_enteros`, que la usa para decidir que enteros son de un indice."""
    indice: set[int] = set()
    for i, v in enumerate(paginas, start=1):
        ls = [ln.strip() for ln in v if ln.strip()]
        sueltos = [(j, int(t)) for j, t in enumerate(ls) if RE_NUMERO_SUELTO.match(t)]
        if not sueltos:
            continue
        tras_entrada = [n for j, n in sueltos if j > 0 and RE_ENTRADA_INDICE.match(ls[j - 1])]
        if len(tras_entrada) >= 3 and all(a <= b for a, b in zip(tras_entrada, tras_entrada[1:])):
            indice.add(i)
        if any(RE_ROTULO_INDICE.match(t) for t in ls[:LINEAS_DEL_ROTULO]):
            indice.add(i)
    return indice


def desfases_de_paginacion(paginas: list[list[str]]) -> set[int]:
    """Los desfases (numero impreso menos numero de pagina del PDF) que firman la numeracion de paginas del documento: un entero solo en su renglon cuyo valor
    menos el de su pagina se repite en tres paginas o mas y en una de cada cuatro. Es la regla "pagina" de `motivos_de_enteros`, que la usa y la comparte con
    `sin_numero_de_pagina_pegado`."""
    from collections import defaultdict
    paginas_de = defaultdict(set)
    for i, v in enumerate(paginas, start=1):
        for ln in v:
            if RE_NUMERO_SUELTO.match(ln):
                paginas_de[int(ln) - i].add(i)
    minimo = max(3, -(-len(paginas) // 4))
    return {d for d, ps in paginas_de.items() if len(ps) >= minimo}


# Palabras (sin tilde, en minuscula) tras las que un entero al final de la pagina es una referencia («see chapter 5», «Table 3», «page 12») y no su numero impreso.
PALABRAS_DE_REFERENCIA_AL_PIE = frozenset({
    "page", "pages", "p", "pp", "chapter", "clause", "clauses", "section", "annex", "appendix", "table", "figure", "fig", "no", "n", "item", "step", "part", "article",
    "art", "paragraph", "para", "point", "class", "version", "level", "group", "type", "pagina", "paginas", "pag", "capitulo", "apartado", "tabla", "figura", "anexo",
    "apendice", "articulo", "num", "numero", "punto", "paso", "parte", "clase", "nivel", "grupo", "tipo", "norma", "iso", "en", "une", "oiml", "r", "d", "c", "v"})
RE_PIE_CON_NUMERO = re.compile(r"^(?P<texto>.*?\S)\s+(?P<n>\d{1,4})$")


def sin_numero_de_pagina_pegado(lp: list[tuple[str, int]], desfases: set[int]) -> tuple[list[tuple[str, int]], int]:
    """(el flujo sin el numero de pagina que Xpdf pego al final del ULTIMO renglon de la pagina, cuantos). 12-oct-2026, c138 (defecto D4 de la revision c137): en la
    pagina 17 de la WELMEC 7.2 el pie «17» salio detras de la nota al pie («3 For an explanation of risk classes, see WELMEC Guide 7.1, chapter 5.2. 17») y el
    texto del precepto decia «...chapter 5.2. 17 Required Documentation R1/D1».

    Es el numero de la pagina cuando su valor menos el de la pagina del PDF es un desfase que firma la numeracion del documento (`desfases_de_paginacion`: el mismo
    que usa `motivos_de_enteros` para los enteros sueltos), y no va detras de una palabra de referencia («Table 12», «chapter 5»). Solo el final de la ultima linea con texto
    de cada pagina: es donde se imprime el pie, y ahi no cabe otra cosa que el numero."""
    if not desfases:
        return lp, 0
    ultima: dict[int, int] = {}
    for k, (ln, pag) in enumerate(lp):
        if ln.strip():
            ultima[pag] = k
    cambios: dict[int, str] = {}
    for pag, k in ultima.items():
        m = RE_PIE_CON_NUMERO.match(lp[k][0].rstrip())
        if not m or int(m.group("n")) - pag not in desfases:
            continue
        palabras = [sin_tilde(x.lower().strip(".,;:()[]")) for x in m.group("texto").split()]
        previa = palabras[-1] if palabras else ""
        # tras una palabra de referencia es una referencia; y detras de dos enteros («12 7 4») es una fila de cifras, no un pie
        if previa in PALABRAS_DE_REFERENCIA_AL_PIE or (previa.isdigit() and len(palabras) > 1 and palabras[-2].isdigit()):
            continue
        cambios[k] = m.group("texto")
    if not cambios:
        return lp, 0
    return [(cambios.get(k, ln), pag) for k, (ln, pag) in enumerate(lp)], len(cambios)


def motivos_de_enteros(paginas: list[list[str]]) -> dict[tuple[int, int], str]:
    """Para cada entero suelto, (pagina, posicion en su pagina) -> motivo.

    El motivo es CELDA si se conserva. Si no, la primera regla que lo descarta,
    y basta una:

    - "borde": abre o cierra la pagina (contando solo las lineas no vacias que
      quedan tras el ruido). Es la regla de P8.
    - "documento": el documento numera en prosa. Entre los enteros que no van
      en un borde ni detras de una linea de puntos de relleno, la mitad o mas
      (y al menos tres) van entre dos vecinas de VECINA_LARGA o mas: asi
      numeran sus lineas los borradores de EudraLex y sus notas el PIC/S PI
      011-3. En ese documento no se conserva ninguno. Los de detras de los
      puntos no cuentan: son el numero de pagina de un indice del BOE, que va
      entre lineas largas de puntos y no dice nada de como numera el texto.
    - "pagina": su valor menos el numero de pagina del PDF es un desfase que se
      repite en tres paginas o mas, y en una de cada cuatro: la firma de la
      numeracion de paginas, este donde este el numero dentro de la pagina.
    - "indice": va justo detras de una linea que acaba en puntos de relleno, o
      la pagina es un indice: tres o mas enteros justo detras de una entrada
      numerada, en orden no decreciente.
      Tambien, desde la campana cero errores, la pagina que lleva el rotulo de
      un indice ("CONTENTS", "INDICE"...) en una de sus LINEAS_DEL_ROTULO
      primeras lineas, aunque no tenga puntos de relleno.
    - "disposicion": un entero de hasta DIGITOS_DISPOSICION cifras justo encima
      del titulo de una disposicion del BOE ("ORDEN de...", "REAL DECRETO..."):
      el numero de disposicion del boletin de papel.
    - "tirada": forma parte de una serie de uno en uno, separada por texto, de
      TIRADA_MINIMA enteros o mas en la misma pagina: numeracion de lineas.
    - "prosa": ninguna de sus dos vecinas tiene VECINA_CORTA caracteres o menos.

    R2FIX-A: un bloque con cabecera de tabla y varias filas numéricas puede
    conservar celdas entre etiquetas largas o al borde, y no es un índice
    inferido solo por la numeración de sus filas. Siguen mandando el índice
    explícito, los puntos de relleno y las firmas de página/línea/documento.
    Las vecinas son las lineas no vacias mas proximas de la misma pagina.
    """
    from collections import defaultdict
    llenas = [[k for k, ln in enumerate(v) if ln.strip()] for v in paginas]

    def texto(i: int, j: int) -> str:
        return paginas[i - 1][llenas[i - 1][j]].strip()

    sueltos = [(i, j, int(texto(i, j)))
               for i, ll in enumerate(llenas, start=1) for j in range(len(ll))
               if RE_NUMERO_SUELTO.match(texto(i, j))]
    motivos: dict[tuple[int, int], str] = {}
    if not sueltos:
        return motivos

    def interior(i: int, j: int) -> bool:
        return 0 < j < len(llenas[i - 1]) - 1

    def larga(i: int, j: int) -> bool:
        return (len(texto(i, j - 1)) >= VECINA_LARGA
                and len(texto(i, j + 1)) >= VECINA_LARGA)

    def tras_puntos(i: int, j: int) -> bool:
        return j > 0 and bool(RE_PUNTOS_SIN_PAGINA.search(texto(i, j - 1)))

    # Los enteros de una pagina de INDICE tampoco dicen como numera el texto el documento (12-oct-2026, c138; defecto D3 de la revision c137): son el numero de
    # clausula de cada entrada, que Xpdf pone en su renglon entre lineas largas de puntos («1» / «Scope ........ 6»). Con ellos la EN 12830 salia «numerada» (cuatro
    # entradas del indice entre lineas largas, de siete enteros que no van en un borde) y perdia TODOS sus enteros sueltos del cuerpo: el «0» de la tabla D.2
    # («+25 / 0 / -20 / (+)T / (-)T») y los «1», «2» de la tabla de la pagina 25.
    indice = paginas_con_indice(paginas)
    dentro = [(i, j) for i, j, _ in sueltos if interior(i, j) and not tras_puntos(i, j) and i not in indice]
    en_prosa = sum(1 for i, j in dentro if larga(i, j))
    numerado = en_prosa >= 3 and 2 * en_prosa >= len(dentro)

    desfases = desfases_de_paginacion(paginas)

    # El tamaño de una etiqueta no distingue prosa de tabla: una descripción
    # de alimento puede ocupar varios renglones. Se exige una cabecera y al
    # menos dos renglones numéricos, con tres valores en total. El bloque acaba
    # ante prosa, una nota o una nueva unidad normativa; no se extiende a toda
    # la página por el mero hecho de que esta contenga una tabla.
    cabecera_tabla = re.compile(
        r"^(?:tabla|cuadro|table)\s+(?:\d+|[A-Z])(?:[ .:—-]|$)"
        r"|\bplan\s+de\s+muestreo\b"
        r"|\b(?:mg|µg|μg|g|mmol)\s*/\s*(?:kg|l|ml)\b"
        r"|^(?:n[úu]mero\s+de\s+(?:horas|interrupciones|animales)"
        r"|tama[ñn]o\s+m[íi]nimo\s+de\s+la\s+muestra)\b", re.I)
    fin_tabla = re.compile(
        r"^(?:Art[íi]culo\s|CAP[ÍI]TULO\s|ANEXO\s|Disposici[óo]n\s"
        r"|\([*\d]+\)\s|\d+\.\s+[^\W\d])")
    fila_numerica = re.compile(r"^[<>≤≥+−\-\d][\d\s.,%<>≤≥+−\-]*$")
    celdas_tabla: set[tuple[int, int]] = set()
    for i, ll in enumerate(llenas, start=1):
        ls = [texto(i, j) for j in range(len(ll))]
        if any(RE_ROTULO_INDICE.match(s) for s in ls[:LINEAS_DEL_ROTULO]):
            continue
        inicio = None

        def cerrar(fin: int) -> None:
            if inicio is None:
                return
            filas = [s for s in ls[inicio:fin] if fila_numerica.fullmatch(s)]
            valores = sum(bool(re.match(r"^\d+\b", s)) for s in ls[inicio:fin])
            if len(filas) >= 2 and valores >= 3:
                celdas_tabla.update((i, j) for j in range(inicio, fin))

        for j, s in enumerate(ls):
            if (fin_tabla.match(s) or RE_PUNTOS_SIN_PAGINA.search(s)
                    or RE_PUNTOS_DE_INDICE.search(s)
                    or (len(s) > 160 and not re.match(r"^\d+\.\d+\b", s))):
                cerrar(j)
                inicio = None
            if len(s) <= 120 and cabecera_tabla.search(s):
                if inicio is None:
                    inicio = j
        cerrar(len(ls))

    por_pagina = defaultdict(list)
    for i, j, n in sueltos:
        por_pagina[i].append((j, n))
    tirada: set[tuple[int, int]] = set()
    for i, lista in por_pagina.items():
        serie = lista[:1]
        for (j0, n0), (j1, n1) in zip(lista, lista[1:]):
            # Seguidos en la lista de enteros de la pagina, uno mas que el
            # anterior y con al menos una linea de texto entre los dos.
            if n1 == n0 + 1 and j1 > j0 + 1:
                serie.append((j1, n1))
                continue
            if len(serie) >= TIRADA_MINIMA:
                tirada.update((i, j) for j, _ in serie)
            serie = [(j1, n1)]
        if len(serie) >= TIRADA_MINIMA:
            tirada.update((i, j) for j, _ in serie)

    def es_encabezado_de_borde(i: int, j: int, n: int) -> bool:
        if j != 0 or i in indice or len(llenas[i - 1]) < 2:
            return False
        sig = texto(i, 1)
        if (not re.match(r"^[A-ZÁÉÍÓÚÑ]", sig) or RE_PUNTOS_SIN_PAGINA.search(sig)
                or RE_PUNTOS_DE_INDICE.search(sig) or RE_MES.match(sig)
                or sig.split(None, 1)[0].strip(",.;:") in PALABRAS_DE_ENLACE):
            return False
        return any(re.match(rf"^\s*{n}\.1\b", texto(i, k)) for k in range(2, len(llenas[i - 1])))

    for i, j, n in sueltos:
        # Una firma de paginación en una celda es ambigua: no se rescata aquí.
        # Tampoco una tirada de numeración marginal ni un documento numerado.
        # El aviso de fidelidad del ámbito remite al PDF cuando sea necesario.
        es_celda_tabla = ((i, j) in celdas_tabla and not numerado
                         and n - i not in desfases and (i, j) not in tirada
                         and not tras_puntos(i, j)
                         and not (not interior(i, j) and n == i)
                         and not (interior(i, j) and len(texto(i, j)) <= DIGITOS_DISPOSICION
                                  and RE_TITULO_DISPOSICION.match(texto(i, j + 1))))
        if es_celda_tabla:
            motivo = CELDA
        elif not interior(i, j):
            motivo = CELDA if es_encabezado_de_borde(i, j, n) else "borde"
        elif numerado:
            motivo = "documento"
        elif n - i in desfases:
            motivo = "pagina"
        elif i in indice or tras_puntos(i, j):
            motivo = "indice"
        elif (len(texto(i, j)) <= DIGITOS_DISPOSICION
              and RE_TITULO_DISPOSICION.match(texto(i, j + 1))):
            motivo = "disposicion"
        elif (i, j) in tirada:
            motivo = "tirada"
        elif (len(texto(i, j - 1)) > VECINA_CORTA
              and len(texto(i, j + 1)) > VECINA_CORTA):
            motivo = "prosa"
        else:
            motivo = CELDA
        motivos[(i, llenas[i - 1][j])] = motivo
    return motivos


def lineas_con_pagina(pdf: TextoPdf, quitar_ajeno: bool = True) -> list[tuple[str, int]]:
    paginas = paginas_vivas(pdf)
    motivos = motivos_de_enteros(paginas)
    lp = [(ln.rstrip(), i)
          for i, vivas in enumerate(paginas, start=1)
          for k, ln in enumerate(vivas)
          if not RE_NUMERO_SUELTO.match(ln) or motivos.get((i, k)) == CELDA]
    # El numero de pagina que Xpdf pego al final del ultimo renglon de la pagina (c138): ver `sin_numero_de_pagina_pegado`. Antes que las notas: la nota al pie
    # con el numero detras no coincidiria letra a letra con la que lee PyMuPDF.
    lp = sin_numero_de_pagina_pegado(lp, desfases_de_paginacion(paginas))[0]
    # El texto ajeno de las normas de la UE (R11, 11-oct-2026): el folio del Diario y las notas al pie, solo si la extraccion lo pide (`texto_ajeno_ue`: la familia
    # `eurlex` y, desde la R15, las guias de la carpeta de la UE, que ademas llevan la maquetacion que PyMuPDF confirma: `maquetacion_del_pdf`). Los BOE y cualquier
    # otro TextoPdf no pasan por aqui. Ver `texto_ajeno_ue` y `maquetacion_pymupdf`. Desde la R15b, ademas, las guias revisadas a mano que no son del Diario
    # (`catalogo.GUIAS_CON_MAQUETACION_REVISADA`) llevan `maquetacion_del_pdf` SIN `texto_ajeno_ue`: solo se quitan las piezas de maquetacion, no los folios ni las notas del Diario.
    if quitar_ajeno and (getattr(pdf, "texto_ajeno_ue", False) or getattr(pdf, "maquetacion_del_pdf", None)):
        from . import texto_ajeno_ue
        lp = texto_ajeno_ue.quitar_del_flujo(lp, pdf.notas_del_diario, pdf.n_paginas, getattr(pdf, "maquetacion_del_pdf", None), getattr(pdf, "texto_ajeno_ue", False))[0]
    return lp


MESES = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}


def fecha_es(texto: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+de\s+([a-zñáéíóú]+)\s+de\s+(\d{4})", texto, re.I)
    if not m:
        return None
    mes = MESES.get(sin_tilde(m.group(2).lower()))
    return f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}" if mes else None


# ----------------------------------------------------------------------- BOE

# El texto limpio del BOE (extraccion.extraer_texto_boe) rotula su cuerpo "TEXTO
# ORIGINAL", que es lo que dice la propia pagina del BOE. Solo se lee asi cuando
# el motor es el del texto del BOE: en un PDF, esa linea no abre el cuerpo.
RE_INICIO_DEL_CUERPO_TEXTO_BOE = r"^\s*TEXTO (?:CONSOLIDADO|ORIGINAL)\s*$"

# R28-ING1: la Ley General de Sanidad escribe «Artículo cuarenta.», no «40».
# Se activa solo para BOE-A-1986-10499 y conserva el encabezado literal.
RE_ARTICULO_SANIDAD = re.compile(r"^Artículo\s+([a-záéíóúñ ]+)\.\s*(.*)$")
CARDINALES_SANIDAD = {
    palabra: n for n, palabra in enumerate((
        '', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho',
        'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince',
        'dieciseis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte',
        'veintiuno', 'veintidos', 'veintitres', 'veinticuatro', 'veinticinco',
        'veintiseis', 'veintisiete', 'veintiocho', 'veintinueve')) if n
}
DECENAS_SANIDAD = dict(zip(
    ('treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa'),
    range(30, 100, 10)))
RE_ITC_BT52 = re.compile(
    r"^INSTRUCCI[ÓO]N T[ÉE]CNICA COMPLEMENTARIA \(ITC\) (BT-52)(?:\s+([A-ZÁÉÍÓÚÑ].*))?$"
)
RE_ITC_REBT = re.compile(r"^ITC-(BT-\d{2})\.?(?:\s+([A-ZÁÉÍÓÚÑ].*))?$")


def _numero_articulo_sanidad(palabras: str) -> str | None:
    p = sin_tilde(' '.join(palabras.split())).lower()
    bis = p.endswith(' bis')
    if bis:
        p = p[:-4]
    centena = 100 if p.startswith('ciento ') else 0
    if centena:
        p = p[7:]
    if p in ('cien', 'ciento'):
        n = 100
    elif p in CARDINALES_SANIDAD:
        n = centena + CARDINALES_SANIDAD[p]
    elif p in DECENAS_SANIDAD:
        n = centena + DECENAS_SANIDAD[p]
    else:
        decena, sep, unidad = p.partition(' y ')
        if not sep or decena not in DECENAS_SANIDAD or not 1 <= CARDINALES_SANIDAD.get(unidad, 0) <= 9:
            return None
        n = centena + DECENAS_SANIDAD[decena] + CARDINALES_SANIDAD[unidad]
    return str(n) + ('bis' if bis else '') if 1 <= n <= 116 else None


RE_BOE = {
    # «LIBRO SEGUNDO Contratos y garantias» (12-oct-2026, R16): el nivel por encima del titulo en los textos refundidos que lo tienen
    # (RDL 1/2007: cuatro libros). Cada libro vuelve a numerar sus titulos y capitulos; sin reconocerlo, los de los libros 2 a 4 chocaban
    # con los del libro 1 (`titulo.I`, `titulo.I/capitulo.I`...) y sus encabezados se sumaban al final del articulo anterior. En
    # mayuscula y con el ordinal en letra, como los imprime el BOE: «el libro segundo de la Ley...» en una frase no cuenta.
    "libro":      re.compile(rf"^\s*LIBRO\s+(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO){RUBRICA}\s*$"),
    # La rubrica puede ir en la misma linea que el numeral, y de hecho es lo
    # mayoritario ("CAPITULO IV MODALIDADES DE VERIFICACION..."). Ver RUBRICA.
    "capitulo":   re.compile(rf"^\s*CAP[ÍI]TULO\s+({NUM_DIV}|[ÚU]NICO|PRELIMINAR){RUBRICA}\s*$"),
    # «TITULO PRELIMINAR» (Ley 39/2015) y «TITULO PRIMERO» (RD 1468/1988, que sigue con «TITULO II»): se quedaban pegados al final del
    # preambulo o de la disposicion anterior (11-oct-2026). Van en ruta como `preliminar` y `primero`, en minuscula como `unico`:
    # no son romanos y una ruta no puede depender de la caja.
    "titulo_div": re.compile(rf"^\s*T[ÍI]TULO\s+({NUM_DIV}|PRELIMINAR|PRIMERO){RUBRICA}\s*$"),
    # «Seccion 2.ª Fases y ejecucion del control...» (11-oct-2026): el nivel entre el capitulo y el articulo, que el
    # analizador no tenia y dejaba su linea pegada al final del articulo anterior (55 filas del comparador de texto). La
    # rubrica empieza en mayuscula: «Seccion 3.ª del Capitulo III...» es una remision, no un encabezado.
    "seccion":    re.compile(rf"^\s*Secci[óo]n\s+(\d+)\.\s?[ªa]{RUBRICA}\s*$"),
    # "Articulo unico" cuando la norma solo tiene uno. No es una rareza: es como
    # se redacta una norma modificativa, y son justo las que modifican la Orden
    # ICT/155/2020. En el RD 249/2025 el contenido dispositivo entero es su
    # articulo unico, asi que sin esto la norma esta en la base y no es citable.
    # La "A" en mayuscula (5-oct-2026): "artículo 5.3, h), de la presente Ley..." al
    # principio de un renglon de la Ley 21/1992 es texto, no un articulo 5 que chocaba
    # con el de verdad y se perdia en la ingesta.
    # "Artitulo" es una errata del propio BOE: el articulo 7 del RD 2200/1995 consolidado (8-oct-2026).
    "articulo":   re.compile(rf"^\s*(?-i:A)rt[íi][ct]ulo\s+(\d+(?:\s?{ORD_ARTICULO})?|[úu]nico)\.\s*(.*)$", re.I),
    "disposicion": re.compile(
        rf"^\s*Disposici[óo]n\s+(adicional|transitoria|derogatoria|final)\s+({ORD_DISPOSICION})"
        r"\.?\s*(.*)$", re.I),
    # La disposicion SIN ordinal ("Disposicion transitoria. Registradores de
    # temperatura en servicio."): la unica de su clase, que los BOE de los anos 90
    # rotulan sin decir "unica". Expresion estrecha, a proposito: la clase, un
    # punto y la rubrica. Antes su texto iba dentro del ultimo articulo y una cita
    # literal de la disposicion se confirmaba contra el articulo 27. Medido el 4 de
    # octubre de 2026: no hay otra en toda la base de produccion. La ruta sigue la
    # convencion de "unica" (`ordinal_a_numero`), que es a lo que traduce
    # `ruta_de_cita`: `disp.transitoria.1`.
    "disposicion_sin_ordinal": re.compile(
        r"^\s*Disposici[óo]n\s+(adicional|transitoria|derogatoria|final)\.\s*(.*)$", re.I),
    # Anexo sin ordinal: mismo patron que el ANNEX a secas de EUR-Lex. El grupo
    # queda vacio y la ruta sale sin sufijo.
    # ANEJO es sinonimo de ANEXO en el BOE, y la palabra que el sistema usa es
    # ANEXO: la ruta y la etiqueta van normalizadas, decision de ICT155 del
    # 5-ago-2026. El RD 237/2000 titula ANEJO, el analizador solo reconocia
    # ANEXO, nunca abria contexto de anexo y por eso sus TRECE apendices no eran
    # citables. El numeral puede ser arabigo: ese mismo real decreto los numera
    # asi. La linea impresa se conserva en el texto del precepto, de modo que la
    # palabra que usa la norma no se pierde; lo que se normaliza es la ruta.
    # La rubrica solo existe si hubo numeral. Dejar los dos grupos opcionales e
    # independientes permitia que la rubrica se tragara el numeral y que "ANEXO
    # II del Real Decreto 244/2016" pasara por encabezado. Lo caza el juego
    # sistematico, no un caso concreto.
    "anexo":      re.compile(rf"^\s*ANE(?:XO|JO)(?:\s+({NUM_DIV}|[ÚU]NICO){RUBRICA})?\s*$", re.I),
    "apendice":   re.compile(rf"^\s*AP[ÉE]NDICE\s+({NUM_DIV}){RUBRICA}\s*$", re.I),
    "apartado":   re.compile(r"^\s*Apartado\s+(\d+)\.\s*(.*)$"),
    "tabla":      re.compile(r"^\s*Tabla\s+(\d+)\.?\s*(.*)$"),
    # La instruccion tecnica complementaria de un reglamento de seguridad industrial (7-oct-2026,
    # RD 552/2019): "INSTRUCCIÓN IF-11" en su renglon y en MAYUSCULAS, con la rubrica detras o en
    # el renglon siguiente. "la Instrucción IF-12 (Instalaciones eléctricas)" es texto. Antes no se
    # reconocia y las 21 instrucciones (175 paginas) caian en la ultima disposicion del Reglamento.
    "instruccion": re.compile(
        r"^\s*INSTRUCCI[ÓO]N\s+(?:T[ÉE]CNICA\s+COMPLEMENTARIA\s+)?((?:ITC-)?[A-Z]{2,4}-\d{1,3})\.?"
        r"(?:\s+([A-ZÁÉÍÓÚÑ].*))?\s*$"),
    # El rotulo del reglamento que aprueba el real decreto ("REGLAMENTO DE SEGURIDAD PARA
    # INSTALACIONES FRIGORÍFICAS"), en mayusculas y en su renglon. Ver `analizar_boe`.
    "reglamento": re.compile(
        r"^\s*REGLAMENTO\s+(?:DE|DEL|PARA|SOBRE|GENERAL|T[ÉE]CNICO)\s[A-ZÁÉÍÓÚÑ ,.\-]+$"),
}




# La linea de cabecera de pagina del BOE original: "Num. 74 Martes 25 de marzo
# de 2025" o la variante con «BOE» delante que usan los consolidados.
RE_BOLETIN = re.compile(r"(?:«?BOE»?\s*)?N[uú]m\.\s*\d+.{0,40}?\d{1,2}\s+de\s+"
                        r"\w+\s+de\s+\d{4}")


# Un anexo sin numeral va a `anexo.sn`, no a `anexo` a secas. `anexo` a secas
# ya significa "el anexo" en un documento que solo tiene uno, y reutilizarlo
# haria que dos cosas distintas compartieran ruta. La colision no apareceria
# hoy: apareceria dentro de meses, en una consulta que nadie sabria interpretar.
# Es el mismo caso de la Orden de 1996 robandole el alias al RD 2200/1995.
SIN_NUMERAL = "sn"


def ruta_anexo(ordinal: str | None) -> str:
    """La ruta de un anexo, con ordinal o marcado como sin numeral."""
    return f"anexo.{ordinal}" if ordinal else f"anexo.{SIN_NUMERAL}"


# Instrucciones tecnicas complementarias (7-oct-2026, RD 552/2019). Su ruta es `itc.IF-11` y la de
# sus apartados `itc.IF-11/ap.4`. Un apartado es "1. Titulo" (con punto) o "1.1 Titulo", "3.2.1
# Titulo", con el titulo en mayuscula, y solo abre si sigue la numeracion (`_siguientes_de`): en el
# texto hay listas numeradas y tablas con cifras que no son apartados.
RUTA_INSTRUCCION = "itc"
# Hasta CINCO niveles («3.5.2.2.1», 11-oct-2026): con cuatro, los puntos «3.5.2.2.1» a «3.5.2.2.4» de la IF-06 y los «2.1.3.2.1» y
# «2.1.3.2.2» de la IF-16 se quedaban dentro del «3.5.2.2» y del «2.1.3.2» (RD 552/2019).
RE_AP_DE_INSTRUCCION = re.compile(
    r"^\s*(\d{1,2}\.|\d{1,2}(?:\.\d{1,2}){1,4}\.?)\s+((?-i:[A-ZÁÉÍÓÚÑ¿«(]).*)$")
RE_INDICE_DE_INSTRUCCION = re.compile(r"^\s*(?:0\.\s*)?[ÍI]NDICE\b")
# Cada entrada de un renglon de indice: "1. Titulo", "1.1 Titulo", "3.2.1 Titulo".
RE_ENTRADA_DE_INSTRUCCION = re.compile(
    r"(?:^|(?<=\s))(\d{1,2}\.|\d{1,2}(?:\.\d{1,2}){1,4}\.?)(?=\s+[A-ZÁÉÍÓÚÑ¿«(])")
RENGLONES_DE_RUBRICA = 3
RE_APENDICE_DE_INSTRUCCION = re.compile(
    r"^\s*(?:LEGISLACI[ÓO]N CONSOLIDADA\s+)?AP[ÉE]NDICE\s+(\d{1,2})(?:\s+(.*))?$")


def _siguientes_de(ultimo: str | None) -> set[str]:
    """Los numeros que pueden venir detras del apartado `ultimo`: el primer hijo, o el siguiente
    en cualquiera de sus niveles ("3.2.2" -> "3.2.2.1", "3.2.3", "3.3", "4")."""
    if not ultimo:
        return {"1"}
    u = ultimo.split(".")
    salida = {".".join(u + ["1"])}
    for j in range(len(u)):
        salida.add(".".join(u[:j] + [str(int(u[j]) + 1)]))
    return salida


def _entradas_de_indice(s: str) -> list[tuple[str, str]]:
    """Las entradas de un renglon de indice de instruccion, con su rubrica: "1. Generalidades.
    2. Relación de términos." -> [("1", "Generalidades."), ("2", "Relación de términos.")]."""
    ms = list(RE_ENTRADA_DE_INSTRUCCION.finditer(s))
    return [(m.group(1).rstrip("."),
             s[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(s)].strip())
            for i, m in enumerate(ms)]


def _misma_rubrica(del_indice: str, del_cuerpo: str) -> bool:
    """Si el texto que sigue a un numero del cuerpo empieza por la rubrica de su entrada del
    indice. Tolera la diferencia menuda ("Puertas isotermas." / "Puerta isoterma.")."""
    a, b = _titulo_comparable(del_indice), _titulo_comparable(del_cuerpo)
    n = min(len(a), 40)
    return n >= 3 and difflib.SequenceMatcher(None, a[:n], b[:n]).ratio() >= 0.75


def _trozos_de_instruccion(s: str, ultimo: str | None,
                           rubricas: dict[str, str]) -> list[tuple[str | None, str]]:
    """Un renglon del cuerpo de una instruccion, partido por los apartados que empiezan en el.

    El PDF del BOE junta un parrafo entero en un renglon, con los subapartados dentro: "1.2
    Sistemas indirectos. En general ... 1.2.1 Sistema indirecto cerrado. Un sistema ...". Se
    corta donde empieza un numero que sigue la numeracion (`_siguientes_de`) y va al principio
    del renglon o detras de un punto. Una rubrica autonoma en mayusculas abre primer nivel
    aunque el indice conserve un titulo antiguo. Para las listas en prosa se mantiene el
    contraste del indice: "2. Informar al personal... 3. Aislar..." dentro de la IF-14 no son
    sus apartados 2 y 3. Los trozos sin numero son texto del apartado en curso.
    """
    cortes: list[tuple[int, str]] = []
    esperado = ultimo
    for m in RE_ENTRADA_DE_INSTRUCCION.finditer(s):
        num = m.group(1).rstrip(".")
        antes = s[:m.start()].rstrip()
        if num not in _siguientes_de(esperado) or (antes and not antes.endswith(".")):
            continue
        resto = s[m.end():].strip()
        rubrica_autonoma = not antes and (resto.isupper() or re.fullmatch(
            r"\((?:Derogad[oa]|Suprimid[oa]|Anulad[oa])\)\.?", resto))
        if "." not in num and rubricas and not (rubrica_autonoma or
                num in rubricas and _misma_rubrica(rubricas[num], s[m.end():])):
            continue
        cortes.append((m.start(), num))
        esperado = num
    if not cortes:
        return [(None, s)]
    trozos: list[tuple[str | None, str]] = []
    if cortes[0][0] > 0:
        trozos.append((None, s[:cortes[0][0]].rstrip()))
    for i, (pos, num) in enumerate(cortes):
        fin = cortes[i + 1][0] if i + 1 < len(cortes) else len(s)
        trozos.append((num, s[pos:fin].rstrip()))
    return trozos


def _rubrica_de_apartado(resto: str) -> str:
    """La rubrica de un apartado de instruccion: su primera frase si detras viene el texto."""
    m = re.match(r"^(.{3,160}?\.)\s+\S", resto)
    return m.group(1) if m else resto.strip()


# El encabezado de un articulo pegado al final del renglon anterior: "...competente. Articulo 3. Vida
# util." (RD 244/2016, anexo III) o tres seguidos, "...aplicables. Articulo 51. Acreditacion.
# (Derogado). Articulo 52. ..." (RD 2200/1995). Sin partirlo el articulo no existia y su texto se
# quedaba en el anterior: `anexo.III/art.2.1` daba el texto del 3.1 (8-oct-2026). Solo tras fin de
# frase, con mayuscula detras y con el numero que toca (ver `partir_articulos_pegados`).
RE_ARTICULO_PEGADO = re.compile(
    r"(?<=[.:;)])\s+(?=(?-i:A)rt[íi][ct]ulo\s+(\d+)\.\s+[«(A-ZÁÉÍÓÚ])")


def partir_articulos_pegados(lp: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Parte un renglon delante del encabezado pegado del articulo SIGUIENTE al ultimo abierto.

    El ultimo abierto es el ultimo renglon que empieza por "Articulo N." (sin comilla: los
    articulos que reproduce una norma modificativa van entrecomillados y no cuentan). Una
    remision ("...en el articulo 7.") no es el numero que toca ni lleva mayuscula detras.
    """
    salida: list[tuple[str, int]] = []
    ultimo: int | None = None
    for ln, pag in lp:
        resto = ln
        while True:
            m = RE_BOE["articulo"].match(resto)
            if m and m.group(1).strip().isdigit():
                ultimo = int(m.group(1))
            corte = None
            if ultimo is not None:
                corte = next((k for k in RE_ARTICULO_PEGADO.finditer(resto)
                              if int(k.group(1)) == ultimo + 1), None)
            if corte is None:
                salida.append((resto, pag))
                break
            salida.append((resto[:corte.start()], pag))
            resto = resto[corte.end():]
    return salida


# El TITULO del reglamento que aprueba un real decreto, detras de su firma: «REGLAMENTO» y el resto sin una sola minuscula
# («REGLAMENTO POR EL QUE SE ESTABLECEN LOS REQUISITOS...», RD 188/2016). `RE_BOE["reglamento"]` solo reconoce los que siguen
# a «DE», «DEL», «PARA»...; el titulo, con cualquier palabra, se reconoce aqui (11-oct-2026).
RE_TITULO_REGLAMENTO = re.compile(r"^\s*REGLAMENTO\s[^a-zñáéíóúü]{6,}$")


def _es_encabezado_de_precepto(s: str, en_anexo: bool) -> bool:
    """Si el renglon abre un precepto de los que `analizar_boe` reconoce (articulo, disposicion, capitulo, titulo, anexo,
    instruccion y, dentro de un anexo, apendice, tabla y apartado)."""
    s_enc = s.lstrip(COMILLAS_APERTURA) if s[0] in COMILLAS_APERTURA else s
    if any(RE_BOE[k].match(s_enc) for k in ("anexo", "capitulo", "titulo_div", "instruccion")):
        return True
    if any(RE_BOE[k].match(s) for k in ("articulo", "disposicion", "disposicion_sin_ordinal")):
        return True
    if en_anexo:
        return bool(RE_BOE["apendice"].match(s_enc) or RE_BOE["tabla"].match(s) or RE_BOE["apartado"].match(s))
    return False


def _sigue_un_encabezado(lineas: list[tuple[str, int]], k: int, en_anexo: bool) -> bool:
    """Si el primer renglon con texto detras del renglon `k` abre un precepto (`_es_encabezado_de_precepto`)."""
    for ln, _ in lineas[k + 1:k + 12]:
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub("", ln.strip())
        if not s or any(r.match(s) for r in RUIDO_BOE):
            continue
        return _es_encabezado_de_precepto(s, en_anexo)
    return False


def _sigue_reglamento_articulado(lineas: list[tuple[str, int]], k: int) -> bool:
    """ANEXO como presentación del reglamento aprobado, no como su contenedor.

    Exige la rúbrica del reglamento y, justo detrás, su primer encabezado.
    El llamador exige además anexo sin numeral y disposiciones finales previas.
    """
    siguientes = []
    for ln, _ in lineas[k + 1:k + 12]:
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub('', ln.strip())
        if not s or any(r.match(s) for r in RUIDO_BOE):
            continue
        siguientes.append(s)
        if len(siguientes) == 2:
            break
    return (len(siguientes) == 2
            and bool(re.fullmatch(r'REGLAMENTO\s+(?:DE|DEL|PARA|SOBRE|GENERAL|T[ÉE]CNICO)\s+.+',
                                  siguientes[0], re.I))
            and any(RE_BOE[tipo].match(siguientes[1])
                    for tipo in ('capitulo', 'titulo_div', 'articulo')))


def analizar_boe(pdf: TextoPdf) -> Analisis:
    from . import estructura_r3b
    correccion_r3b = estructura_r3b.de_pdf(pdf)
    an = Analisis()
    texto_p1 = pdf.paginas[0] if pdf.paginas else ""
    m = re.search(r"Referencia:\s*(\S+)", texto_p1)
    an.identificador = m.group(1).strip() if m else None
    lineas_p1 = [l.strip() for l in texto_p1.split("\n") if l.strip()]
    if len(lineas_p1) > 1:
        an.titulo = lineas_p1[1]
    todo = pdf.texto
    mu = re.search(r"[ÚU]ltima modificaci[óo]n:\s*([^\n]+)", todo)
    if mu:
        crudo = mu.group(1).strip()
        an.cabecera = crudo
        an.es_consolidada = True
        an.fecha_consolidacion = fecha_es(crudo)

    lp = lineas_con_pagina(pdf)
    # El arranque (donde acaba el indice, que lineas son cabecera) se decide sin
    # los enteros sueltos que `lineas_con_pagina` conserva como celdas: antes de
    # P8 no estaban, y contandolos crecia el tope del indice y la cabecera perdia
    # lineas (doce consolidados en la medicion de P8). Revision P8 bis.
    sin_sueltos = [i for i, (ln, _) in enumerate(lp) if not RE_NUMERO_SUELTO.match(ln)]
    # El cuerpo empieza tras el indice. El indice usa puntos de relleno.
    inicio = 0
    for i, (ln, _) in enumerate(lp):
        if re.match(RE_INICIO_DEL_CUERPO_TEXTO_BOE if pdf.motor == MOTOR_TEXTO_BOE
                    else r"^\s*TEXTO CONSOLIDADO", ln):
            inicio = i + 1
            break
    else:
        # El indice vive al principio. Buscar la ultima linea con puntos de
        # relleno en TODO el documento es peligroso: un patron de puntos en una
        # tabla del cuerpo descartaba el documento entero. El RD 188/2016 no
        # consolidado se quedaba en el 1,2 % de su texto por esto.
        tope = max(20, len(sin_sueltos) // 5)
        ultimo = max((i for i in sin_sueltos[:tope] if INDICE.search(lp[i][0])),
                     default=-1)
        inicio = ultimo + 1

    preceptos: list[Precepto] = []
    # La cabecera bibliografica entra como precepto propio. El analizador salta
    # todo lo anterior a TEXTO CONSOLIDADO, que es indice y cabecera, y con ello
    # se perdian el numero y la fecha de boletin: justo el dato sobre el que se
    # cometieron los errores de julio. La auditoria de 40 fragmentos lo detecto.
    # Cada renglon de la cabecera lleva la pagina de la que sale (`cab_paginas`): el ultimo, "TEXTO
    # CONSOLIDADO Ultima modificacion...", esta detras del indice, en la pagina 3 a 9 segun la norma (9-oct-2026;
    # hasta entonces la cabecera decia pagina 1-1 y su texto llegaba a la 9).
    cab_con_pagina = [(ln, pg) for ln, pg in lp[:inicio]
                      if ln.strip() and not INDICE.search(ln)
                      and not RE_NUMERO_SUELTO.match(ln)][:8]
    cab_lineas = [ln for ln, _ in cab_con_pagina]
    cab_paginas = [pg for _, pg in cab_con_pagina]
    # En un PDF original del BOE, sin "TEXTO CONSOLIDADO", no hay nada antes del
    # cuerpo: el numero y la fecha de boletin van en la cabecera de pagina, que
    # `lineas_con_pagina` descarta por repetida, y ademas repartida en tres
    # lineas sueltas ("Num. 89" / "BOLETIN OFICIAL DEL ESTADO" / "Sabado 12 de
    # abril de 2025"). Se recuperan de la pagina 1, donde son dato y no
    # mobiliario. Sin esto no hay contra que contrastar la fecha de un BOE no
    # consolidado.
    # La linea que abre el cuerpo ("TEXTO CONSOLIDADO Última modificación: 27 de diciembre
    # de 2025") no estaba en ningun precepto (5-oct-2026): entra en la cabecera.
    if inicio > 0 and lp[inicio - 1][0].strip() not in cab_lineas and re.sub(
            r"(?i)texto\s+(?:consolidado|original)", "", lp[inicio - 1][0]).strip():
        cab_lineas.append(lp[inicio - 1][0].strip())
        cab_paginas.append(lp[inicio - 1][1])
    if not cab_lineas:
        cab_lineas = [l.strip() for l in texto_p1.split("\n") if l.strip()][:8]
        cab_paginas = [1] * len(cab_lineas)
    if cab_lineas:
        preceptos.append(Precepto(
            ruta="cabecera", tipo="cabecera", numero=None,
            etiqueta="Cabecera bibliográfica", titulo=None,
            lineas=cab_lineas, pagina_inicio=min(cab_paginas), pagina_fin=max(cab_paginas)))
    # Precepto de preambulo: nada de lo que venga antes del primer encabezado
    # reconocido puede quedarse fuera. Ver medir_cobertura.py.
    actual: Precepto | None = Precepto(
        ruta="preambulo", tipo="preambulo", numero=None,
        etiqueta="Preámbulo", titulo=None, pagina_inicio=1, pagina_fin=1)
    ctx_anexo: str | None = None
    ctx_apendice: str | None = None
    ctx_capitulo: str | None = None
    ctx_titulo: str | None = None
    # EL LIBRO EN CURSO (12-oct-2026, R16). El primero que abre el documento lleva las rutas de siempre (`titulo.I`,
    # `titulo.I/capitulo.II`): ponerles prefijo mataria rutas que ya se citan. Los demas llevan `libro.N/` por delante
    # (`libro.2/titulo.I/capitulo.I`). Los articulos no cambian: `art.N` es unico en todo el texto.
    ctx_libro: str | None = None
    etiqueta_libro: str | None = None
    libro_sin_prefijo: str | None = None
    # La instruccion tecnica complementaria en curso (RE_BOE["instruccion"]): el ultimo apartado
    # abierto, los renglones de rubrica que aun pueden venir y si se esta en su indice.
    ctx_itc: str | None = None
    itc_ultimo: str | None = None
    itc_rubrica = 0
    itc_indice = False
    itc_primero: str | None = None
    itc_rubricas: dict[str, str] = {}   # numero -> rubrica, de su indice
    itc_en_apendice = itc_rubrica_apendice = False
    # El cuerpo del reglamento que aprueba el real decreto (RE_BOE["reglamento"]): sus
    # disposiciones chocaban con las del real decreto ("adicional unica" y "adicional primera"
    # son las dos `disp.adicional.1`) y van a `reglamento/disp...`.
    visto_disp_final = False
    ctx_reglamento = False
    # LA DIVISION EN CURSO, de la que cuelgan las secciones (11-oct-2026): la ruta y la etiqueta del ultimo anexo, titulo o
    # capitulo abierto, y las rutas de seccion ya usadas (una repetida es texto, no se tira).
    ruta_division: str | None = None
    etiqueta_division: str | None = None
    rutas_de_seccion: set[str] = set()
    # LA CITA ABIERTA dentro de una disposicion (11-oct-2026): las comillas « » sin cerrar de lo que lleva la disposicion
    # desde que se abrio. Una disposicion que reescribe otra norma la reproduce entrecomillada, con sus capitulos y articulos,
    # y eso es texto de la disposicion (RD 782/2013, disp. final 1.ª: el capitulo IX y el articulo 57 del RD 824/2010).
    citas = 0
    reglamento_abierto = False

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None

    def abrir(ruta, tipo, numero, etiqueta, titulo, pagina, padre, encabezado=None):
        nonlocal actual, citas
        cerrar()
        citas = 0
        actual = Precepto(ruta=ruta, tipo=tipo, numero=numero, etiqueta=etiqueta,
                          titulo=titulo or None, pagina_inicio=pagina,
                          pagina_fin=pagina, padre=padre)
        if encabezado:
            actual.lineas.append(encabezado)

    lineas_boe = partir_articulos_pegados(lp[inicio:])
    for k_ln, (ln, pag) in enumerate(lineas_boe):
        if INDICE.search(ln):
            continue
        s = RE_CABECERA_BOE_PEGADA.sub("", ln.strip())
        # El ruido propio del BOE (pies de «sin valor juridico», membrete del diario) y el «Pagina N» pegado al final de un
        # renglon: ver RUIDO_BOE.
        if s and any(r.match(s) for r in RUIDO_BOE):
            continue
        mp = RE_PAGINA_PEGADA.search(s) if s else None
        if mp and int(mp.group(1)) == pag:
            s = s[:mp.start()].rstrip()
        mp = RE_PIE_PEGADO_AL_FINAL.search(s) if s and pag == pdf.n_paginas else None
        if mp:
            s = s[:mp.start()].rstrip()
        if not s:
            if actual:
                actual.lineas.append("")
            continue
        # Dentro de una disposicion: el renglon abre una cita («CAPITULO IX, «ANEXO I), o ya hay una cita abierta.
        en_disp = actual is not None and actual.tipo == "disposicion"
        citado = en_disp and s[0] in COMILLAS_APERTURA
        dentro_de_cita = en_disp and citas > 0
        # Una norma que reescribe un anexo imprime el texto nuevo ENTRECOMILLADO:
        #
        #     Uno. El anexo III queda redactado del siguiente modo:
        #     «ANEXO III
        #
        # La comilla de apertura no es parte del encabezado. Sin quitarla,
        # `RE_BOE["anexo"]` no casaba, `ctx_anexo` no se ponia nunca, y los
        # articulos de los dos anexos reescritos caian los dos en primer nivel:
        # sus rutas chocaban, uno se perdia y el otro se quedaba con los
        # apartados del primero.
        #
        # Medido el 6-ago-2026: 13 encabezados ciegos en 3 documentos, de ellos
        # DIEZ en la Orden ITU/1475/2024, que es la norma que modifica la propia
        # Orden ICT/155/2020 y el mayor contribuyente de descartes del corpus
        # con 188. Ver pruebas/medir_anexos_entrecomillados.py.
        #
        # El encabezado se guarda como esta impreso, con su comilla: se corrige
        # lo que el analizador MIRA, no lo que la base GUARDA.
        #
        # SOLO PARA DIVISIONES, y esto se aprendio rompiendolo. La primera
        # version quitaba la comilla antes de probar TODOS los patrones, y la
        # Ley 32/2014 de Metrologia perdio 4,3 puntos de cobertura: en sus
        # disposiciones finales modifica la Ley 21/1992 de Industria y
        # reproduce entrecomillados sus articulos 15, 16, 18, 31 y 34, que
        # pasaron a ser `art.15` .. `art.34` DE LA LEY 32/2014 y chocaron con
        # los suyos propios.
        #
        # El texto entrecomillado es de la norma MODIFICADA, no de esta. Una
        # division entrecomillada abre un contexto donde ese texto vive con
        # ruta propia (`anexo.III/art.1`) y no choca con nada. Un articulo
        # entrecomillado suelto no tiene de que colgar, asi que crear para el
        # una ruta de primer nivel es atribuirle a esta norma un articulo
        # ajeno. Se deja fuera a proposito.
        s_enc = s.lstrip(COMILLAS_APERTURA) if s[0] in COMILLAS_APERTURA else s

        m = RE_BOE["anexo"].match(estructura_r3b.encabezado_boe(s_enc, correccion_r3b))
        if m and not citado:
            # Sin ordinal la ruta es `anexo.sn`, no `anexo.UNICO`.
            # Inventar un ordinal que la norma no escribe obliga a adivinarlo
            # tambien al citar.
            numero_anexo = numeral_division((m.group(1) or "").upper())
            ctx_anexo = numero_anexo
            # RF1: RD 2200/1995 p.10 imprime «ANEXO» antes del título del
            # reglamento aprobado y su capítulo I. Se conserva ese rótulo,
            # pero el articulado es el cuerpo del reglamento (art.N), no una
            # numeración interna de anexo. No afecta a un anexo sin numeral
            # con contenido propio, como el del RD 2032/2009.
            if (not numero_anexo and visto_disp_final
                    and _sigue_reglamento_articulado(lineas_boe, k_ln)):
                ctx_anexo = None
            ctx_apendice = None
            ctx_capitulo = None
            ctx_titulo = None
            ctx_itc = None
            ruta_ax = ruta_anexo(numero_anexo or None)
            ruta_division, etiqueta_division = ruta_ax, f"Anexo {numero_anexo}".strip()
            abrir(ruta_ax, "anexo", numero_anexo or None,
                  f"Anexo {numero_anexo}".strip(),
                  (m.group(2) or "").strip() or None, pag, None, s)
            continue

        m = RE_BOE["instruccion"].match(s_enc)
        if not m and an.identificador == "BOE-A-2014-13681":
            m = RE_ITC_BT52.match(s_enc)
        if not m and an.identificador == "BOE-A-2002-18099":
            # ING5: los rótulos del REBT no llevan «INSTRUCCIÓN» delante.
            # Se conserva el contrato de las demás obras BOE.
            m = RE_ITC_REBT.match(s_enc)
        if m:
            ctx_itc = m.group(1)
            ctx_anexo = ctx_apendice = ctx_capitulo = ctx_titulo = None
            ruta_division = etiqueta_division = None
            itc_ultimo, itc_indice, itc_primero, itc_rubricas = None, False, None, {}
            itc_en_apendice = itc_rubrica_apendice = False
            rubrica = (m.group(2) or "").strip()
            itc_rubrica = 0 if rubrica else RENGLONES_DE_RUBRICA
            abrir(f"{RUTA_INSTRUCCION}.{ctx_itc}", "instruccion", ctx_itc,
                  f"Instrucción {ctx_itc}", rubrica or None, pag, None, s)
            continue

        if ctx_itc:
            # Dentro de una instruccion no hay articulos, capitulos ni disposiciones: esos
            # rotulos son texto. Solo cuentan su rubrica, su indice y sus apartados.
            ruta_itc = f"{RUTA_INSTRUCCION}.{ctx_itc}"
            en_la_cabeza = actual is not None and actual.ruta == ruta_itc
            # Los apendices de la instruccion ("APÉNDICE 1", a veces con el membrete de la
            # pagina pegado delante) van al final: lo que sigue ya no es de ningun apartado y,
            # sin esto, las tablas y los modelos caian en el ultimo. Dentro de un apendice no se
            # abren apartados; su rubrica va detras o en el renglon siguiente.
            m = RE_APENDICE_DE_INSTRUCCION.match(s)
            if m:
                rubrica = (m.group(2) or "").strip()
                abrir(f"{ruta_itc}/apend.{m.group(1)}", "apendice", m.group(1),
                      f"Instrucción {ctx_itc}, Apéndice {m.group(1)}", rubrica or None, pag,
                      ruta_itc, s)
                itc_en_apendice, itc_rubrica_apendice = True, not rubrica
                continue
            if itc_en_apendice:
                if itc_rubrica_apendice and actual is not None and len(s) <= 150:
                    actual.titulo = s
                itc_rubrica_apendice = False
                if actual:
                    actual.lineas.append(s)
                    actual.pagina_fin = pag
                continue
            if itc_rubrica and en_la_cabeza:
                if (s == s.upper() and re.search(r"[A-ZÁÉÍÓÚÑ]{3}", s)
                        and not RE_INDICE_DE_INSTRUCCION.match(s)
                        and not (an.identificador == "BOE-A-2002-18099" and RE_AP_DE_INSTRUCCION.match(s))):
                    actual.titulo = f"{actual.titulo} {s}" if actual.titulo else s
                    actual.lineas.append(s)
                    actual.pagina_fin = pag
                    itc_rubrica -= 1
                    continue
            itc_rubrica = 0
            en_el_cuerpo = itc_ultimo is not None or not en_la_cabeza
            if not en_el_cuerpo:
                # La cabeza: rubrica, indice y lo que haya antes del primer apartado. El indice
                # empieza en "ÍNDICE" (solo o con entradas detras) y acaba en el segundo "1."
                # suelto: el primero es su entrada y el segundo, el cuerpo. La entrada "1."
                # puede ir tambien en un renglon de varias entradas, en el de "ÍNDICE" o antes
                # de el (IF-08 del RD 552/2019). Un renglon con varias entradas ("1.1
                # Generalidades. 1.2 Aislamiento.") es del indice y nunca abre apartado.
                m = RE_AP_DE_INSTRUCCION.match(s)
                entradas = _entradas_de_indice(s)
                num = m.group(1).rstrip(".") if m and len(entradas) <= 1 else None
                if RE_INDICE_DE_INSTRUCCION.match(s):
                    itc_indice = True
                if num is None and any(n == "1" for n, _ in entradas):
                    itc_primero = "1"
                if itc_indice:
                    if num == "1" and itc_primero is None:
                        itc_primero = "1"
                        num = None
                    elif num != "1":
                        num = None
                en_el_cuerpo = num == "1"
                if not en_el_cuerpo:
                    # Lo de la cabeza es indice: sus rubricas deciden luego los apartados de
                    # primer nivel (ver `_trozos_de_instruccion`).
                    for n, r in entradas:
                        itc_rubricas.setdefault(n, r)
            trozos = (_trozos_de_instruccion(s, itc_ultimo, itc_rubricas) if en_el_cuerpo
                      else [(None, s)])
            for num, trozo in trozos:
                if num:
                    padre = f"{ruta_itc}/ap.{num.rsplit('.', 1)[0]}" if "." in num else ruta_itc
                    resto = trozo[RE_ENTRADA_DE_INSTRUCCION.match(trozo).end():].strip()
                    abrir(f"{ruta_itc}/ap.{num}", "apartado", num,
                          f"Instrucción {ctx_itc}, apartado {num}", _rubrica_de_apartado(resto),
                          pag, padre, trozo)
                    itc_ultimo = num
                elif actual:
                    if not actual.lineas:
                        actual.pagina_inicio = pag
                    actual.lineas.append(trozo)
                    actual.pagina_fin = pag
            continue

        if visto_disp_final and ctx_anexo is None and not reglamento_abierto and RE_TITULO_REGLAMENTO.match(s_enc):
            # El TITULO del reglamento que aprueba el real decreto, detras de la firma («REGLAMENTO POR EL QUE SE ESTABLECEN...»,
            # «REGLAMENTO DE SEGURIDAD PARA INSTALACIONES FRIGORIFICAS»): es el encabezado de lo que sigue, no el final de la
            # ultima disposicion (11-oct-2026). Abre un precepto de cabecera, `reglamento`, con sus renglones de rubrica.
            reglamento_abierto = True
            ctx_reglamento = ctx_reglamento or bool(RE_BOE["reglamento"].match(s_enc))
            ruta_division = etiqueta_division = None
            abrir("reglamento", "reglamento", None, "Reglamento", s, pag, None, s)
            continue

        if visto_disp_final and ctx_anexo is None and RE_BOE["reglamento"].match(s_enc):
            # El renglon sigue siendo texto, como antes; lo que cambia es la ruta de las
            # disposiciones que vienen detras.
            ctx_reglamento = True

        # «Seccion N.ª Rubrica» seguida de un encabezado que abre precepto (articulo, capitulo, anexo, disposicion...): es un
        # precepto de una linea, `<division>/seccion.N`, y no se traga el texto de lo que sigue. Si lo que sigue es texto (los
        # apartados «1. Clases de exactitud» de las secciones de un anexo), la linea se queda en su anexo, como el XML la cuenta.
        m = RE_BOE["seccion"].match(s) if not (citado or dentro_de_cita) else None
        if m and (_sigue_un_encabezado(lineas_boe, k_ln, ctx_anexo is not None)
                  or (correccion_r3b == 'BOE-A-2015-10566'
                      and estructura_r3b.empieza_subseccion(lineas_boe, k_ln))):
            numero_s = m.group(1)
            ruta_s = f"{ruta_division}/seccion.{numero_s}" if ruta_division else f"seccion.{numero_s}"
            if ruta_s not in rutas_de_seccion:
                rutas_de_seccion.add(ruta_s)
                cerrar()
                preceptos.append(Precepto(
                    ruta=ruta_s, tipo="seccion", numero=numero_s,
                    etiqueta=(f"{etiqueta_division}, Sección {numero_s}" if etiqueta_division else f"Sección {numero_s}"),
                    titulo=(m.group(2) or "").strip() or None, lineas=[s], pagina_inicio=pag, pagina_fin=pag,
                    padre=ruta_division))
                continue

        m = RE_BOE["apendice"].match(s_enc)
        if m and ctx_anexo is not None:
            ctx_apendice = numeral_division(m.group(1).upper())
            r = f"{ruta_anexo(ctx_anexo)}/apend.{ctx_apendice}"
            abrir(r, "apendice", ctx_apendice,
                  f"Anexo {ctx_anexo}, Apéndice {ctx_apendice}",
                  (m.group(2) or "").strip() or None, pag, ruta_anexo(ctx_anexo), s)
            continue

        m = RE_BOE["tabla"].match(s)
        if m and ctx_anexo:
            base = ruta_anexo(ctx_anexo) + (f"/apend.{ctx_apendice}" if ctx_apendice else "")
            et = f"Anexo {ctx_anexo}" + (f", Apéndice {ctx_apendice}" if ctx_apendice else "") \
                 + f", Tabla {m.group(1)}"
            abrir(f"{base}/tabla.{m.group(1)}", "tabla", m.group(1), et,
                  m.group(2).strip() or None, pag, base, s)
            continue

        m = RE_BOE["apartado"].match(s)
        if m and ctx_anexo is not None:
            base = ruta_anexo(ctx_anexo) + (f"/apend.{ctx_apendice}" if ctx_apendice else "")
            r = f"{base}/ap.{m.group(1)}"
            et = f"Anexo {ctx_anexo}" + (f", Apéndice {ctx_apendice}" if ctx_apendice else "") \
                 + f", apartado {m.group(1)}"
            abrir(r, "apartado", m.group(1), et, m.group(2).strip() or None, pag, base, s)
            continue

        # El encabezado de un libro: abre su precepto (`libro.N`), olvida el titulo y el capitulo en curso, y los que vengan detras
        # llevaran su prefijo. No dentro de una cita entrecomillada de una disposicion ni de un anexo.
        m = RE_BOE["libro"].match(s) if not (citado or dentro_de_cita or ctx_anexo is not None) else None
        if m:
            ctx_libro = ordinal_a_numero(m.group(1))
            if libro_sin_prefijo is None:
                libro_sin_prefijo = ctx_libro
            etiqueta_libro = f"Libro {m.group(1).lower()}"
            ctx_titulo = ctx_capitulo = None
            ruta_division, etiqueta_division = f"libro.{ctx_libro}", etiqueta_libro
            abrir(f"libro.{ctx_libro}", "libro", ctx_libro, etiqueta_libro, (m.group(2) or "").strip() or None, pag, None, s)
            continue

        m = RE_BOE["capitulo"].match(s_enc) or RE_BOE["titulo_div"].match(s_enc)
        # Un capitulo o titulo que abre una cita dentro de una disposicion, o que viene con la cita abierta, es texto de la
        # disposicion (RD 782/2013, disp. final 1.ª), no una division de esta norma.
        if m and not (citado or dentro_de_cita):
            ctx_capitulo = numeral_division(m.group(1))
            if sin_tilde(ctx_capitulo) in ("PRELIMINAR", "PRIMERO", "UNICO"):
                ctx_capitulo = sin_tilde(ctx_capitulo).lower()
            # Se mira la linea SIN la comilla, igual que el patron que la
            # reconocio. Mirando `s`, "«CAPITULO IX" del RD 782/2013 no empezaba
            # por "CAP" y el capitulo se guardaba como `titulo.IX`. Lo encontro
            # C-02 el 6-ago-2026 refutando esta misma tanda: la reparacion abria
            # bien la division y la nombraba mal. No perdia texto ni rompia
            # citas, y por eso no lo habia visto ninguna medicion de las mias:
            # ninguna comparaba el TIPO de la division con lo que imprime el
            # documento.
            tipo = "capitulo" if s_enc.upper().lstrip().startswith("CAP") else "titulo"
            # Un capitulo DENTRO de un anexo pertenece al anexo, y la ruta lo
            # dice. Decision de ICT155 del 5-ago-2026. No es una regla sobre tres
            # documentos: un anexo tiene numeracion interna propia que vuelve a
            # empezar en I, y tratarla como la del articulado hace que dos cosas
            # distintas compartan ruta. Es la misma regla que esta funcion ya
            # aplica a apendices, tablas y apartados.
            base = ruta_anexo(ctx_anexo) + "/" if ctx_anexo is not None else ""
            et = ((f"Anexo {ctx_anexo}, " if ctx_anexo is not None else "")
                  + f"{'Capítulo' if tipo == 'capitulo' else 'Título'} {ctx_capitulo}")
            padre = ruta_anexo(ctx_anexo) if ctx_anexo is not None else None
            # Un titulo (o un capitulo sin titulo) de los libros 2 y siguientes cuelga de su libro y lleva su prefijo (R16).
            pre_libro, et_libro = "", ""
            if ctx_anexo is None and ctx_libro and ctx_libro != libro_sin_prefijo:
                pre_libro, et_libro = f"libro.{ctx_libro}/", f"{etiqueta_libro}, "
                base, padre, et = pre_libro, f"libro.{ctx_libro}", et_libro + et
            # Un capitulo dentro de un titulo del articulado cuelga del titulo, igual que
            # dentro de un anexo cuelga del anexo (5-oct-2026): la Ley 11/2022 y la 9/2014
            # vuelven a numerar sus capitulos en cada titulo, las rutas chocaban y la
            # ingesta tiraba el segundo capitulo I con su rubrica y sus secciones.
            if ctx_anexo is None and tipo == "titulo":
                ctx_titulo = ctx_capitulo
            elif ctx_anexo is None and ctx_titulo:
                base, padre = f"{pre_libro}titulo.{ctx_titulo}/", f"{pre_libro}titulo.{ctx_titulo}"
                et = f"{et_libro}Título {ctx_titulo}, Capítulo {ctx_capitulo}"
            ruta_division, etiqueta_division = f"{base}{tipo}.{ctx_capitulo}", et
            abrir(f"{base}{tipo}.{ctx_capitulo}", tipo, ctx_capitulo, et,
                  (m.group(2) or "").strip() or None, pag, padre, s)
            continue

        m = RE_BOE["articulo"].match(s)
        en_letras = (RE_ARTICULO_SANIDAD.match(s)
                     if an.identificador == "BOE-A-1986-10499" and not m else None)
        num_letras = _numero_articulo_sanidad(en_letras.group(1)) if en_letras else None
        if (m or num_letras) and not dentro_de_cita:
            # "unico" sin tilde en la ruta: una ruta no lleva acentos, igual
            # que `disp.derogatoria.1` tampoco los lleva. Con tilde habria que
            # acertar con ella al citar.
            num = num_letras or (sin_tilde(re.sub(r"\s+", " ", m.group(1).strip())).lower()
                   if m.group(1).strip().lower().startswith(("ú", "u"))
                   else numeral_articulo(m.group(1)))
            base = ruta_anexo(ctx_anexo) + "/" if ctx_anexo is not None else ""
            et = (f"Anexo {ctx_anexo}, artículo {num}" if ctx_anexo is not None else f"Artículo {num}")
            rubrica = (en_letras if num_letras else m).group(2).strip() or None
            abrir(f"{base}art.{num}", "articulo", num, et, rubrica,
                  pag, ruta_anexo(ctx_anexo) if ctx_anexo is not None else None, s)
            if re.match(r'^1\.\s',rubrica or ''):
                # Sin rúbrica: el primer apartado comparte línea con el
                # encabezado, incluso si el 2 también va pegado (Sanidad 84).
                inicio_cuerpo=(en_letras if num_letras else m).start(2)
                actual.lineas=[s[:inicio_cuerpo].rstrip(),s[inicio_cuerpo:]]
                actual.titulo=None
            continue

        # La Orden histórica tiene dos apartados dispositivos, sin artículos.
        # No se interpretan ordinales en su anexo ni en ninguna otra norma.
        if (an.identificador == "BOE-A-1989-5084" and ctx_anexo is None
                and not (citado or dentro_de_cita) and s in ("Primero.", "Segundo.")):
            num = "1" if s == "Primero." else "2"
            abrir(f"ap.{num}", "apartado", num, s.rstrip('.'), None, pag, None, s)
            continue

        # Las disposiciones del reglamento aprobado van con prefijo (ver `ctx_reglamento`).
        pre_r, pre_e = ("reglamento/", "Reglamento, d") if ctx_reglamento else ("", "D")

        m = RE_BOE["disposicion_sin_ordinal"].match(s)
        if m:
            clase = m.group(1).lower()
            abrir(f"{pre_r}disp.{sin_tilde(clase)}.1", "disposicion", "1",
                  f"{pre_e}isposición {clase} única", m.group(2).strip() or None, pag, None, s)
            visto_disp_final = visto_disp_final or clase == "final"
            continue

        m = RE_BOE["disposicion"].match(s)
        if m:
            clase, ordinal = m.group(1).lower(), ordinal_a_numero(m.group(2))
            r = f"{pre_r}disp.{sin_tilde(clase)}.{ordinal}"
            abrir(r, "disposicion", ordinal,
                  f"{pre_e}isposición {clase} {m.group(2).lower()}", m.group(3).strip() or None,
                  pag, None, s)
            visto_disp_final = visto_disp_final or clase == "final"
            continue

        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag
            if actual.tipo == "disposicion":
                citas = max(0, citas + s.count("«") - s.count("»"))

    cerrar()
    an.preceptos = subdividir_anexo_sin_numeral(subdividir(
        preceptos, listas_interiores=pdf.ruta_relativa in DOCUMENTOS_CON_LISTAS_INTERIORES, boe=True)
    )
    return an


# -------------------------------------------------------------------- EUR-Lex

RE_UE = {
    # Dos maquetaciones conviven en EUR-Lex y hay que contemplar las dos:
    #  - consolidada antigua: "Articulo 14" en linea propia, rubrica en la
    #    linea siguiente.
    #  - Serie L nueva (actos desde ~2023): "Articulo 14 Obligaciones de
    #    informacion de los fabricantes", numero y rubrica en la misma linea.
    # Contemplar solo la primera dejaba sin trocear los actos recientes: en el
    # CRA se detectaban 23 encabezados de los 71 articulos que tiene.
    # En la Serie L el encabezado y el comienzo del cuerpo pueden compartir
    # linea entera: "Articulo 71 Entrada en vigor y aplicacion 1. El presente
    # Reglamento entrara en vigor...". Por eso no se limita la longitud.
    # El discriminante frente a una remision del cuerpo ("Articulo 3 del
    # Reglamento Delegado...") es la mayuscula: una rubrica empieza en
    # mayuscula, una remision sigue en minuscula.
    "articulo": re.compile(
        rf"^\s*Art[íi]culo\s*(\d+(?:\s?{ORD_ARTICULO})?)"
        r"(?:\s+((?:[A-ZÁÉÍÓÚÑ]|\d{1,2}\.\s+[A-ZÁÉÍÓÚÑ«\"]).*))?\s*$"),
    "article_en": re.compile(
        r"^\s*Article\s+(\d+[a-z]?)(?:\s+([A-Z].*))?\s*$"),
    # Un acto con un solo anexo lo titula "ANEXO" o "ANNEX" a secas, sin
    # numeral. Exigir el espacio y el numero dejaba ese anexo fuera del troceado
    # entero: la Decision 2025/138 perdia asi toda su tabla de normas
    # armonizadas, que es lo unico que el acto anade.
    # Y las tres divisiones admiten rubrica en la misma linea, igual que el
    # articulo: es la maquetacion mayoritaria ("CAPITULO IV MODALIDADES DE
    # VERIFICACION..."). Con el numeral obligado a cerrar la linea, el
    # Reglamento 2016/161 creaba 4 capitulos de 11, y el corpus entero perdia
    # 217 divisiones en 62 documentos de 101.
    "anexo":    re.compile(rf"^\s*(?:ANEXO|ANNEX)(?:\s+({NUM_DIV}|[ÚU]NICO){RUBRICA})?\s*$", re.I),
    # Dos puntos tras el numeral: "CAPÍTULO V: HIGIENE PARA EL DESPIECE Y EL
    # DESHUESADO", y "CAPÍTULO IX:" con la rubrica en la linea siguiente, en el
    # anexo III del Reglamento 853/2004. Ultima tanda de la campana cero
    # errores, ver PREDICCION_ultima_tanda_encabezados.md y SECCION_UE.
    "capitulo": re.compile(rf"^\s*(?:CAP[ÍI]TULO|CHAPTER)\s+(PRIMERO|{NUM_DIV}):?{RUBRICA}\s*$", re.I),
    "titulo_div": re.compile(rf"^\s*(?:T[ÍI]TULO|TITLE)\s+({NUM_DIV}):?{RUBRICA}\s*$", re.I),
}
# La seccion de un anexo: "SECCIÓN I: CARNE DE UNGULADOS DOMÉSTICOS", "SECCIÓN
# IV. REQUISITOS APLICABLES A LOS ALIMENTOS CONGELADOS...". Solo en mayusculas y
# solo dentro de un anexo: las "Sección 1" del articulado (Reglamento 765/2008,
# GPSR) no se tocan. Hace falta para los dos puntos de arriba: cada seccion del
# anexo III del 853/2004 vuelve a numerar sus capitulos desde el I, y sin el
# nivel de seccion el capitulo I de la seccion II tendria la ruta del de la
# seccion I, la ingesta descartaria el segundo y su texto desapareceria.
SECCION_UE = re.compile(rf"^\s*(?:SECCI[ÓO]N|SECTION)\s+({NUM_DIV})\s*[:.]?{RUBRICA}\s*$")

# La cabecera de pagina de un consolidado de EUR-Lex. Con re.M: si la extraccion
# pone antes el aviso ("Este texto es exclusivamente un instrumento de
# documentacion..."), sin re.M el `^` solo miraba el principio del texto y el
# ejemplar salia como no consolidado. Sospecha S1, ver PREDICCION_revision_S1.md.
CAB_CONSOLIDADA = re.compile(
    r"^\s*0?(\d{4})([A-Z])(\d{4})\s*[—-]\s*([A-Z]{2})\s*[—-]\s*(\d{2}\.\d{2}\.\d{4})", re.M)

# La cabecera del Diario Oficial pegada al encabezado del primer articulo de la pagina: "Official
# Journal of the European Union Article 9" (RED en ingles: articulos 9, 14, 31 y 42). Sin quitarla
# el articulo no existia y su texto se quedaba en el anterior (8-oct-2026). Y lo que viene detras en
# esas paginas, el folio y la fecha ("L 153/75", "22.5.2014"), no es la rubrica del articulo.
RE_CABECERA_DOUE_PEGADA = re.compile(
    r"^(?:Official Journal of the European Union|Diario Oficial de la Uni[óo]n Europea)\s+"
    r"(?=(?:Art[íi]culo|Article)\s+\d)")
RE_FOLIO_DOUE = re.compile(r"^\s*(?:[LC]\s+\d{1,4}/\d{1,4}|\d{1,2}\.\d{1,2}\.\d{4}|[A-Z]{2})\s*$")

# La FORMULA FINAL del acto (R11, 11-oct-2026): «Hecho en Bruselas, el 20 de julio de 2023.» / «Done at Brussels, 28 January 2025.», y detras las firmas («Por la Comision
# La Presidenta Ursula VON DER LEYEN»). No es parte del ultimo articulo —se le pegaba, y un cotejo con el texto oficial veia texto que el articulo no tiene— ni es
# texto ajeno: es la firma del acto, con su fecha. Va a un precepto propio, `formula_final`, que dura hasta el siguiente encabezado (un anexo, normalmente).
RE_FORMULA_FINAL = re.compile(
    r"^\s*(?:Hecho\s+en|Done\s+at)\s+[^\d,]{2,40},\s*(?:el\s+)?\d{1,2}(?:\.?\s?[ºo°])?\s+(?:de\s+)?[A-Za-zÁÉÍÓÚáéíóúñ]+\s+(?:de\s+)?\d{4}\b")


RE_CAB_UE_CON_FOLIO = re.compile(
    r"^\s*\d{4,5}[A-Z]\d{4}\s*[—-]\s*[A-Z]{2}\s*[—-]\s*"
    r"\d{2}\.\d{2}\.\d{4}\s*[—-]\s*\d{3}\.\d{3}\s*[—-]\s*\d+\b[^\S\n]*")


def _conservar_restos_de_cabecera_ue(pdf: TextoPdf) -> TextoPdf:
    """El folio puede compartir línea con una marca o con el primer encabezado.

    RUIDO descarta la línea completa. Separar antes SOLO el membrete completo
    conserva la marca (atributo del precepto) y el contenido que viene detrás.
    No modifica el TextoPdf que recibe el llamante.
    """
    paginas = ["\n".join(RE_CAB_UE_CON_FOLIO.sub("", ln) for ln in p.split("\n"))
               for p in pdf.paginas]
    return replace(pdf, paginas=paginas)


def _reubicar_rotulos_sueltos_ue(lp: list[tuple[str,int]]) -> list[tuple[str,int]]:
    """Dos columnas que Xpdf lee por columnas: rótulos, después sus párrafos.

    Solo dentro del articulado, con al menos dos letras consecutivas SIN
    contenido y otros tantos comienzos de párrafo: cada cuerpo anterior al
    último ha de cerrar frase. No completa texto ni cruza un encabezado.
    Si no hay correspondencia inequívoca se conserva la entrada original.
    """
    def limpia(ln):
        return MARCA_INLINE.sub('',MARCA_RESTO.sub('',ln)).strip()
    def rotulos(s):
        return re.findall(r'([a-zñ])\)',s) if re.fullmatch(r'(?:[a-zñ]\)\s*)+',s) else []
    salida=list(lp)
    en_articulo=False
    en_anexo=False
    k=0
    alfabeto='abcdefghijklmnñopqrstuvwxyz'
    while k<len(lp):
        s=limpia(lp[k][0])
        if not en_anexo and (RE_UE['articulo'].match(s) or RE_UE['article_en'].match(s)):
            en_articulo=True
        elif RE_UE['anexo'].match(s):
            en_articulo=False
            en_anexo=True
        # Xpdf también agrupa el número del apartado delante de la columna
        # de letras: «3. a) b) c) d)», y luego imprime la introducción.
        prefijo = re.fullmatch(r'(\d{1,3}\.\s*)((?:[a-zñ]\)\s*){2,})', s)
        letras=rotulos(prefijo[2] if prefijo else s) if en_articulo else []
        if not letras:
            k+=1
            continue
        indices=[k]
        j=k+1
        while j<len(lp):
            sig=limpia(lp[j][0])
            nuevas=rotulos(sig)
            if nuevas:
                letras.extend(nuevas)
                indices.append(j)
            elif sig:
                break
            j+=1
        serie=''.join(letras)
        if len(letras)<2 or serie not in alfabeto:
            k=j
            continue
        introduccion = None
        if prefijo:
            # La introducción sigue siendo del apartado. Sin su cierre «:»
            # no hay evidencia suficiente para asignar los cuerpos.
            if (j >= len(lp) or not limpia(lp[j][0]).endswith(':')
                    or lp[j][1] != lp[k][1]):
                k=j
                continue
            introduccion = j
            j+=1
        cuerpos=[]
        for n in range(j,min(len(lp),j+2*len(letras)+8)):
            t=limpia(lp[n][0])
            if not t:
                continue
            if (re.match(r'^(?:Art[íi]culo|Article|ANEXO|ANNEX|CAP[ÍI]TULO|CHAPTER|\d+[.)]|[a-zñ]+\)|[—–])',t)
                    or RE_FORMULA_FINAL.match(t)):
                break
            cuerpos.append(n)
            if len(cuerpos)==len(letras):
                break
            if not RE_CIERRA_FRASE.search(t):
                break
        if len(cuerpos)!=len(letras):
            k=j
            continue
        # Retira solo los rótulos de sus líneas; conserva marcas y páginas.
        for n in indices:
            ln,pag=salida[n]
            salida[n]=(re.sub(r'[a-zñ]\)\s*','',ln).rstrip(),pag)
        if introduccion is not None:
            # Un «3.» solo en una línea no abre apartado en el troceador.
            # Une su introducción conservando las marcas intermedias.
            ln,pag=salida[k]
            salida[k]=(re.sub(r'\d{1,3}\.\s*$','',ln).rstrip(),pag)
            ln,pag=salida[introduccion]
            salida[introduccion]=(prefijo[1].strip()+' '+ln,pag)
        for letra,n in zip(letras,cuerpos):
            ln,pag=salida[n]
            salida[n]=(letra+') '+ln,pag)
        k=cuerpos[-1]+1
    return salida


def _anexo_tras_correspondencias(s: str, lp: list[tuple[str, int]], k: int) -> bool:
    """Distingue un anexo nuevo de las referencias impresas en las celdas.

    Exige el rotulo editorial en mayusculas y una rubrica propia, en el
    mismo renglon o en el siguiente util. «Anexo VII», «ANEXO VII Anexo V»
    y dos referencias en renglones consecutivos siguen siendo filas.
    """
    if not re.match(r"^(?:ANEXO|ANNEX)\b", s):
        return False
    m = RE_UE["anexo"].match(s)
    if not m:
        return False
    rubrica = (m.group(2) or "").strip()
    if not rubrica:
        for ln, _ in lp[k + 1:]:
            t = MARCA_INLINE.sub("", MARCA_RESTO.sub("", ln)).strip()
            if not t or any(rx.match(t) for rx in RUIDO):
                continue
            rubrica = t
            break
    return bool(re.match(r"^[A-ZÁÉÍÓÚÑ]", rubrica)
                and not re.match(r"^(?:Anexos?|Annex(?:es)?|Art[íi]culos?|Articles?|"
                                 r"Reglamento|Regulation|Directiva|Directive|Presente)\b", rubrica, re.I))


def analizar_eurlex(pdf: TextoPdf) -> Analisis:
    from . import estructura_r3b
    correccion_r3b = estructura_r3b.de_pdf(pdf)
    an = Analisis()
    todo = pdf.texto
    m = CAB_CONSOLIDADA.search(todo)
    if m:
        anio, letra, num, idioma, fecha = m.groups()
        an.identificador = f"CELEX-3{anio}{letra}{num}"
        an.es_consolidada = True
        d, mo, y = fecha.split(".")
        an.fecha_consolidacion = f"{y}-{mo}-{d}"
        an.cabecera = m.group(0).strip()
        an.idioma = idioma.lower()
    else:
        m2 = re.search(r"^\s*(?:C/)?(\d{4})/(\d+)\s*$", todo[:4000], re.M)
        if m2:
            an.identificador = f"DOUE-{m2.group(1)}-{m2.group(2)}"
        an.cabecera = todo[:120].replace("\n", " ").strip()
    if re.search(r"\bEN L series\b|Official Journal", todo[:3000]):
        an.idioma = "en"

    lp = _reubicar_rotulos_sueltos_ue(lineas_con_pagina(_conservar_restos_de_cabecera_ue(pdf)))
    preceptos: list[Precepto] = []
    # Precepto de preambulo: nada de lo que venga antes del primer encabezado
    # reconocido puede quedarse fuera. Ver medir_cobertura.py.
    actual: Precepto | None = Precepto(
        ruta="preambulo", tipo="preambulo", numero=None,
        etiqueta="Preámbulo", titulo=None, pagina_inicio=1, pagina_fin=1)
    ctx_anexo: str | None = None
    marca_actual: str | None = None
    n_articulos = 0
    n_formulas = 0

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None

    def abrir(ruta, tipo, numero, etiqueta, titulo, pagina, padre, encabezado=None):
        nonlocal actual
        cerrar()
        actual = Precepto(ruta=ruta, tipo=tipo, numero=numero, etiqueta=etiqueta,
                          titulo=titulo, pagina_inicio=pagina, pagina_fin=pagina,
                          padre=padre, marca=marca_actual)
        if encabezado:
            actual.lineas.append(encabezado)

    esperando_titulo: Precepto | None = None
    # Las referencias de la tabla no abren divisiones; si hay un anexo
    # posterior con rotulo y rubrica propios, termina este estado.
    en_tabla_corresp = False
    # Secciones y capitulos dentro del anexo en curso (SECCION_UE). Dentro de
    # cada anexo manda el orden: el primero de los dos niveles que aparece es
    # el de arriba. En el 853/2004 la seccion va primero:
    # `anexo.III/seccion.I/capitulo.V`.
    seccion_en_anexo: str | None = None
    capitulo_en_anexo: str | None = None
    nivel_de_arriba: str | None = None
    # El titulo del articulado en curso: un capitulo fuera de un anexo cuelga de el
    # (5-oct-2026). La Directiva 2001/83 vuelve a numerar sus capitulos en cada titulo.
    titulo_en_curso: str | None = None

    for k, (ln, pag) in enumerate(lp):
        s = ln.strip()
        mb = MARCA_BLOQUE.match(s)
        if mb:
            marca_actual = mb.group(1)
            continue
        # La marca de consolidacion puede compartir linea con el encabezado:
        # "▼B Artículo 2". Exigir que la linea empiece por "Articulo" perdia el
        # articulo entero y todo su cuerpo. Se separa la marca y se sigue.
        mi = MARCA_INICIO.match(s)
        if mi:
            marca_actual = mi.group(1)
            s = s[mi.end():].strip()
            if not s:
                continue
        # ►C1 ... ◄ dentro de la linea: la marca es atributo, no texto.
        if "\u25ba" in s or "\u25c4" in s:
            # Una flecha sin codigo reconocido ya se quitaba como ornamento.
            # Conserva ese comportamiento, sin consumir ninguna letra detras.
            s = MARCA_INLINE.sub("", s).replace("\u25ba", "").strip()
        # Y la que va DETRAS del numeral: "Articulo 40 [marca]M2". No la cazaba
        # ninguna de las tres anteriores, y por eso ese articulo del RED quedaba
        # sin trocear y respondia PRECEPTO_INEXISTENTE.
        if MARCA_RESTO.search(s):
            resto = MARCA_RESTO.findall(s)
            if resto:
                marca_actual = resto[-1]
            s = MARCA_RESTO.sub(" ", s).strip()
            s = re.sub(r"\s{2,}", " ", s)
        s = RE_CABECERA_DOUE_PEGADA.sub("", s)
        # Un separador gráfico puede quedar pegado al encabezado de la página
        # siguiente (89/108/CEE, art. 13). Solo se retira del texto que se MIRA;
        # el encabezado almacenado conserva el separador y su texto original.
        encabezado_literal = s
        s = re.sub(r"^_{3,}\s*(?=Art[íi]culo\s*\d)", "", s)
        if not s:
            if actual:
                actual.lineas.append("")
            continue

        # La rubrica "TABLA DE CORRESPONDENCIAS" en el renglon siguiente al del anexo ("ANEXO VI" /
        # "TABLA DE CORRESPONDENCIAS"): asi la da la lectura en el orden interno de la Directiva
        # 2014/31/UE, y sin esto la fila "Anexo VII Anexo V" abria un anexo VII que no existe
        # (8-oct-2026). El renglon de la rubrica va al texto del anexo, como hasta ahora.
        if (not en_tabla_corresp and actual is not None and actual.tipo == "anexo"
                and not any(ln.strip() for ln in actual.lineas[1:])
                and (RX_TABLA_CORRESP.search(s)
                     or (correccion_r3b == 'CELEX-32011R0010' and estructura_r3b.TABLA.search(s)))):
            en_tabla_corresp = True

        if en_tabla_corresp and _anexo_tras_correspondencias(s, lp, k):
            en_tabla_corresp = False

        # Las filas nombran divisiones de la norma derogada. Se conservan
        # dentro de la tabla, sin abrir articulos ni anexos ficticios.
        if en_tabla_corresp:
            if actual:
                if not actual.lineas:
                    actual.pagina_inicio = pag
                actual.lineas.append(s)
                actual.pagina_fin = pag
            continue

        # La formula final: precepto propio (ver RE_FORMULA_FINAL). Solo con un acto abierto y fuera del preambulo (los considerandos no firman).
        if actual is not None and actual.tipo != "preambulo" and RE_FORMULA_FINAL.match(s):
            n_formulas += 1
            abrir("formula_final" if n_formulas == 1 else f"formula_final.{n_formulas}", "formula_final", None,
                  "Fórmula final" if n_formulas == 1 else f"Fórmula final ({n_formulas})", None, pag, None, s)
            esperando_titulo = None
            continue

        m = RE_UE["anexo"].match(s)
        if correccion_r3b == 'CELEX-32019R2144' and not s.startswith('ANEXO '):
            # F5: las minúsculas de las celdas son remisiones; los cuatro
            # rótulos propios del ejemplar están impresos en versales.
            m = None
        m_tc = None if m else RE_ANEXO_TABLA_CORRESP.match(s)
        if not m and not m_tc and correccion_r3b == 'CELEX-32007L0045':
            m_tc = estructura_r3b.ANEXO_SIN_NUMERAL.match(s)
        if m or m_tc:
            ctx_anexo = numeral_division((m.group(1) or "").upper()) if m else ""
            seccion_en_anexo = capitulo_en_anexo = nivel_de_arriba = None
            titulo_en_curso = None
            ruta_ax = ruta_anexo(ctx_anexo or None)
            abrir(ruta_ax, "anexo", ctx_anexo or None,
                  f"Anexo {ctx_anexo}".strip(),
                  ((m.group(2) or "").strip() if m else m_tc.group(1)) or None,
                  pag, None, s)
            esperando_titulo = None
            if RX_TABLA_CORRESP.search(s):
                en_tabla_corresp = True
            continue

        m = RE_UE["articulo"].match(s) or RE_UE["article_en"].match(s)
        if m:
            num = numeral_articulo(m.group(1))
            n_articulos += 1
            rubrica = (m.group(2) or "").strip() or None
            cuerpo_inline = bool(rubrica and re.match(r'^\d{1,2}\.\s', rubrica))
            lineas_articulo = [encabezado_literal]
            if cuerpo_inline:
                # Xpdf: «Artículo 13 1. Los Estados…». El 1 es cuerpo, no
                # rúbrica. Separarlo permite subdividir también el 2 pegado.
                inicio_cuerpo = len(encabezado_literal) - len(rubrica)
                lineas_articulo = [encabezado_literal[:inicio_cuerpo].rstrip(), rubrica]
                rubrica = None
            if rubrica:
                corte = re.search(r"\s(?=\d{1,2}\.\s+[A-ZÁÉÍÓÚa-z])", rubrica)
                if corte:
                    rubrica = rubrica[:corte.start()].strip() or None
            # El encabezado se almacena en forma canonica "Articulo N.
            # Rubrica." Las dos maquetaciones de EUR-Lex lo imprimen
            # distinto (la antigua en dos lineas, la nueva en una) y la
            # unidad citable es la misma: sin canonizar, el mismo precepto
            # se recupera con o sin punto segun el ano de publicacion.
            p = Precepto(ruta=f"art.{num}", tipo="articulo", numero=num,
                         etiqueta=f"Artículo {num}", titulo=rubrica, lineas=lineas_articulo,
                         pagina_inicio=pag, pagina_fin=pag, marca=marca_actual)
            cerrar()
            actual = p
            # Si la rubrica venia en la misma linea, no hay que esperarla
            # en la siguiente: esa ya es cuerpo del articulo.
            esperando_titulo = None if rubrica or cuerpo_inline else p
            continue
        m = SECCION_UE.match(s) if ctx_anexo is not None else None
        if m:
            num_sec = numeral_division(m.group(1))
            nivel_de_arriba = nivel_de_arriba or "seccion"
            padre = ruta_anexo(ctx_anexo or None)
            et = f"Anexo {ctx_anexo}".strip()
            if nivel_de_arriba == "capitulo" and capitulo_en_anexo:
                padre += f"/capitulo.{capitulo_en_anexo}"
                et += f", Capítulo {capitulo_en_anexo}"
            else:
                seccion_en_anexo, capitulo_en_anexo = num_sec, None
            abrir(f"{padre}/seccion.{num_sec}", "seccion", num_sec,
                  f"{et}, Sección {num_sec}", (m.group(2) or "").strip() or None,
                  pag, padre, s)
            esperando_titulo = None
            continue

        m = RE_UE["capitulo"].match(s) or RE_UE["titulo_div"].match(s)
        # Un capitulo DENTRO de un anexo cuelga del anexo, no del acto.
        # Decision de ICT155 del 5-ago-2026, predicha antes en
        # PREDICCION_anidar_divisiones_en_anexo.md (commit b470002).
        # Hasta hoy se creaban todos en primer nivel y la consecuencia
        # estaba medida: el Reglamento 852/2004
        # imprime CAPITULO I a V en su articulado y otra vez CAPITULO I a
        # XII dentro del Anexo II. Al crearlos todos en primer nivel, las
        # rutas colisionan, la ingesta resuelve la colision en silencio y el
        # texto del anexo desaparece. Es el mecanismo del que avisa la
        # adenda del 3 de agosto: las rutas planas destruyen contenido.
        # Anidando, cada uno cuelga del suyo y los doce son citables por
        # separado, que es lo que hace falta: en higiene alimentaria los
        # requisitos sustantivos viven precisamente en el anexo.
        if m:
            num_div = numeral_division(m.group(1))
            if sin_tilde(num_div).upper() == "PRIMERO":
                num_div = "I"
            tipo = "capitulo" if sin_tilde(s.upper()).lstrip().startswith(("CAP", "CHA")) else "titulo"
            # El encabezado va al texto del precepto, igual que en el BOE.
            # Sin esto, al reconocer "CAPITULO IV MODALIDADES DE
            # VERIFICACION..." la rubrica desaparecia del texto_literal: ni
            # en el capitulo nuevo ni en el precepto anterior. Reconocer
            # mas estructura no puede costar texto buscable.
            base = ruta_anexo(ctx_anexo) + "/" if ctx_anexo is not None else ""
            et = ((f"Anexo {ctx_anexo}, " if ctx_anexo is not None else "")
                  + f"{'Capítulo' if tipo == 'capitulo' else 'Título'} {num_div}")
            padre = ruta_anexo(ctx_anexo) if ctx_anexo is not None else None
            if ctx_anexo is None and tipo == "titulo":
                titulo_en_curso = num_div
            elif ctx_anexo is None and titulo_en_curso:
                base, padre = f"titulo.{titulo_en_curso}/", f"titulo.{titulo_en_curso}"
                et = f"Título {titulo_en_curso}, Capítulo {num_div}"
            if ctx_anexo is not None and tipo == "capitulo":
                nivel_de_arriba = nivel_de_arriba or "capitulo"
                if nivel_de_arriba == "seccion" and seccion_en_anexo:
                    padre = f"{ruta_anexo(ctx_anexo)}/seccion.{seccion_en_anexo}"
                    base = padre + "/"
                    et = (f"Anexo {ctx_anexo}, Sección {seccion_en_anexo}, "
                          f"Capítulo {num_div}")
                else:
                    capitulo_en_anexo = num_div
            abrir(f"{base}{tipo}.{num_div}", tipo, num_div, et,
                  (m.group(2) or "").strip() or None, pag, padre, s)
            esperando_titulo = None
            continue

        if esperando_titulo is not None:
            # El folio o la fecha de la pagina entre "Article N" y su rubrica (RE_FOLIO_DOUE): al
            # texto, como hasta ahora, y se sigue esperando la rubrica.
            if RE_FOLIO_DOUE.match(s):
                esperando_titulo.lineas.append(s)
                esperando_titulo.pagina_fin = pag
                continue
            # La linea inmediatamente posterior a "Articulo N" es su rubrica.
            # Va tambien al texto: la rubrica forma parte del precepto y sin
            # ella el texto literal empieza por el apartado 1.
            if len(s) < 200 and not re.match(r"^\d+\.", s):
                esperando_titulo.titulo = s
                esperando_titulo.lineas.append(s)
                esperando_titulo = None
                continue
            esperando_titulo = None

        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag

    cerrar()
    # La numeración n) de estas definiciones se ha cotejado en el texto público.
    # No cambia la interpretación de listas dentro de otras normas.
    definiciones = {
        "CELEX-32012R1025": "art.2", "CELEX-32017R0745": "art.2",
        "CELEX-32017R0746": "art.2", "CELEX-32016R0679": "art.4",
        "CELEX-32018L1972": "art.2",
    }
    an.preceptos = subdividir(
        quedarse_con_el_cuerpo(preceptos),
        definiciones=frozenset({definiciones[an.identificador]}) if an.identificador in definiciones else frozenset(),
        letras_con_huecos=frozenset({"art.2"}) if an.identificador == "CELEX-32002L0058" else frozenset(),
        numeracion_modificativa=an.identificador == 'CELEX-32017R0625')
    return an


# Detras del numero de un encabezado no va una palabra de enlace en minuscula: "4.4 y
# sgtes." (indice alfabetico del GUM), "3.2 of the Directive 2014/53/EU" (renglon partido
# de la ETSI EN 301 489-1), "4.3.1.13 or 4.3.2.12" (celda). Con mayuscula si puede ir
# ("5.1 The Accreditation Body shall...", "9.1.1 Los ejemplos..."). 5-oct-2026.
PALABRAS_DE_ENLACE = frozenset({
    "y", "e", "o", "u", "ni", "de", "del", "la", "el", "los", "las", "en", "a", "al", "con",
    "por", "para", "and", "or", "of", "to", "in", "the", "for", "with", "on", "at", "by", "nor"})


def sigue_una_frase(p: Precepto) -> bool:
    """El encabezado del precepto es la continuacion de una frase."""
    palabras = p.texto.split(None, 2)
    return len(palabras) > 1 and palabras[1].strip(",.;:") in PALABRAS_DE_ENLACE


def _sumar(destino: Precepto, p: Precepto, delante: bool = False) -> None:
    """Las lineas de `p` pasan a `destino`, con sus paginas: el texto no se tira."""
    destino.lineas = (p.lineas + destino.lineas) if delante else (destino.lineas + p.lineas)
    destino.pagina_inicio = min(destino.pagina_inicio, p.pagina_inicio)
    destino.pagina_fin = max(destino.pagina_fin, p.pagina_fin)


def quedarse_con_el_cuerpo(preceptos: list[Precepto],
                           tipos: tuple[str, ...] = ("articulo",),
                           paginas_de_indice: frozenset = frozenset(),
                           paginas_de_entradas: frozenset = frozenset()) -> list[Precepto]:
    """De cada ruta repetida, una; el texto de las demas no se tira.

    Tanto el indice del principio como la tabla de correspondencias del final repiten
    los mismos numeros, con dos o tres lineas debajo en lugar del cuerpo. Hasta el
    5-oct-2026 se conservaba la aparicion con mas texto y las otras se tiraban CON SU
    TEXTO: 463 lineas de los PDF no estaban en ningun precepto, y la mas larga no
    siempre es la del cuerpo (VIM 2.47 era el indice alfabetico; el articulo 15 de la
    Directiva 2014/31, una fila de la tabla de correspondencias). Ahora:

    - gana, en un articulo, la aparicion del articulado a la de dentro de un anexo; en
      un apartado de guia, la que no esta en una pagina de indice y no sigue una frase
      (`sigue_una_frase`); si no, la mas larga, y entre iguales la primera;
    - la que pierde se suma, en su sitio, al precepto anterior en el orden del
      documento (al siguiente si es la primera): su texto queda donde estaba.
    - LA PAGINA no sigue al texto cuando gana una entrada de indice (9-oct-2026): si la que
      gana esta toda en paginas de indice y hay otra aparicion de la ruta que no lo es, el
      precepto se queda con SU texto y con las paginas de esa aparicion del cuerpo. Un
      apartado que en el cuerpo es solo su titulo ("9.2 Modelo aditivo", JCGM 101) empata en
      longitud con su entrada del indice, y en el empate gana la primera: el texto es el
      mismo renglon, pero la pagina era la 6 (el indice) y el apartado esta en la 53. Cambiar
      quien gana cambiaria el texto de sus vecinos, asi que se cambia solo la pagina.
      `paginas_de_entradas` son las paginas de indice que el analizador no trata como tal
      (sin rotulo ni puntos de relleno: `paginas_con_indice`); solo sirven para esto.
      Limite conocido: JCGM 106 ap. 9.4.7 empieza en la pagina 43 y gana la aparicion de la 44, una copia que
      `-layout` pone en esa pagina de la capa de texto de la 43. No hay regla de paginas que lo arregle: de las
      72 rutas de guia en que gana una aparicion posterior a otra, las otras 71 estan bien puestas (ETSI EN 301
      511 4.2.x...) y "la aparicion mas temprana" las movia todas.

    Se probaron antes siete reglas de numeracion creciente sobre todo el corpus;
    fallaban con apartados falsos al lado o con documentos de varias numeraciones
    (docs/PREDICCION_texto_que_pierde_el_analizador_2026-10-05.md).
    """
    from collections import defaultdict
    en_anexo, del_articulado = False, {}
    for p in preceptos:
        if p.tipo in ("anexo", "apendice"):
            en_anexo = True
        del_articulado[id(p)] = not en_anexo
    por_ruta: dict[str, list] = defaultdict(list)
    for k, p in enumerate(preceptos):
        if p.tipo in tipos:
            por_ruta[p.ruta].append((k, p))

    def preferencia(kp):
        k, p = kp
        if p.tipo == "articulo":
            return (del_articulado[id(p)], True, True, True, len(p.texto), -k)
        if p.tipo == "apartado":
            return (True, not p.de_indice and p.pagina_inicio not in paginas_de_indice,
                    del_articulado[id(p)], not sigue_una_frase(p), len(p.texto), -k)
        return (True, True, True, True, len(p.texto), -k)

    ganan = {id(max(l, key=preferencia)[1]) for l in por_ruta.values()}
    salida: list[Precepto] = []
    sin_sitio: list[Precepto] = []
    for p in preceptos:
        if p.tipo in tipos and id(p) not in ganan:
            if salida:
                _sumar(salida[-1], p)
            else:
                sin_sitio.append(p)
            continue
        for q in reversed(sin_sitio):
            _sumar(p, q, delante=True)
        sin_sitio = []
        salida.append(p)
    if paginas_de_indice or paginas_de_entradas:
        _pagina_del_cuerpo(por_ruta, ganan, preferencia, paginas_de_indice | paginas_de_entradas)
    return salida


def _pagina_del_cuerpo(por_ruta: dict[str, list], ganan: set, preferencia, paginas_del_indice) -> None:
    """Ver `quedarse_con_el_cuerpo`: la que gana esta toda en paginas de indice y otra aparicion no -> sus
    paginas. Solo toca `pagina_inicio` y `pagina_fin` del que gana."""
    def de_indice(p: Precepto) -> bool:
        return p.de_indice or (p.pagina_inicio in paginas_del_indice and p.pagina_fin in paginas_del_indice)

    for lista in por_ruta.values():
        if len(lista) < 2:
            continue
        gana = [p for _, p in lista if id(p) in ganan]
        if not gana or not de_indice(gana[0]):
            continue
        cuerpo = [kp for kp in lista if id(kp[1]) not in ganan and not de_indice(kp[1])]
        if cuerpo:
            b = max(cuerpo, key=preferencia)[1]
            gana[0].pagina_inicio, gana[0].pagina_fin = b.pagina_inicio, b.pagina_fin
            if b.titulo and gana[0].titulo and gana[0].titulo != b.titulo:
                m_pag = re.search(r"\s+(\d{1,3})$", gana[0].titulo)
                if m_pag and gana[0].titulo[:m_pag.start()].strip() == b.titulo.strip():
                    gana[0].titulo = b.titulo
                    gana[0].lineas = [re.sub(r"\s+" + m_pag.group(1) + r"$", "", ln) for ln in gana[0].lineas]


def sin_rutas_repetidas(preceptos: list[Precepto]) -> list[Precepto]:
    """Red de seguridad: dos preceptos con la misma ruta no llegan a la ingesta, que
    tiraba el segundo entero (en produccion, 26 con texto que no estaba en ningun otro
    sitio; 5-oct-2026). Si su texto ya esta en otro precepto (un apartado repetido
    dentro de una disposicion que reproduce otra norma esta en su padre), sobra; si
    no, se suma al anterior."""
    vistas: set[str] = set()
    salida: list[Precepto] = []
    for p in preceptos:
        if p.ruta not in vistas:
            vistas.add(p.ruta)
            salida.append(p)
            continue
        mio = " ".join(p.texto.split())
        if any(mio in " ".join(q.texto.split()) for q in salida):
            continue
        if salida:
            _sumar(salida[-1], p)
    return salida


# ---------------------------------------------------------------------- guias

# Un encabezado de guia es un numero de esquema seguido de texto. La rubrica
# puede ser corta ("3.3. Equipo") o un parrafo entero ("2.1 The PIC/S Guide to
# Good Manufacturing Practices is the basis for GMP inspections..."), asi que no
# se limita su longitud.
_RE_GUIA_AP_BASE = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\.?\s+(\[?[^\W\d].*)$")
# R17e (14-oct-2026): dos erratas de la capa OCR de la EN 18031-1 que impedian abrir un apartado, y que se leen igual en cualquier
# documento: (1) una coma detras de un numero de tres o cuatro niveles («x.y.z, Guidance», seguido de mayuscula); (2) el codigo de
# requisito entre corchetes pegado al numero, sin espacio («x.y[ABC] Titulo»). Con las dos, el grupo 1 es el numero y el 2 el titulo,
# igual que en el caso normal, y el resto del analizador no cambia.
RE_GUIA_AP_COMA = re.compile(r"^\s*(\d+(?:\.\d+){2,3}),\s+([A-ZÁÉÍÓÚÑ].*)$")
RE_GUIA_AP_CODIGO = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?(\[[A-Z][A-Za-z0-9\-]*\]\s*[^\W\d].*)$")


class _CabeceraDeGuia:
    """Prueba en orden las formas de un encabezado de apartado de guia; `match` devuelve la primera coincidencia (grupo 1 = numero,
    grupo 2 = titulo) o None. Se llama RE_GUIA_AP porque ocupa su sitio: todo el codigo que la usa solo llama a `match`."""

    def __init__(self, *expresiones):
        self._expresiones = expresiones

    def match(self, s, *args):
        for e in self._expresiones:
            m = e.match(s, *args)
            if m:
                return m
        return None


RE_GUIA_AP = _CabeceraDeGuia(_RE_GUIA_AP_BASE, RE_GUIA_AP_COMA, RE_GUIA_AP_CODIGO)
# El VIM pone detras del numero el de la edicion anterior entre parentesis: "1.10 (1.13)
# unidad de base, f", "1.2 (1.1, nota 2 ) naturaleza de una magnitud". Sin esto, 80 de sus
# definiciones no eran apartado y "VIM 2.1" devolvia el rotulo de una figura (6-oct-2026).
# Numero con punto y otro numero dentro del parentesis: "1 (AVS) Full notified body
# control" (una celda) y "4 (18) conformity assessment body" (una remision) no lo son.
# Tambien sin espacio delante del parentesis ("4.4(5.1) intervalo nominal") y con dos
# ("2.53 (3.15) (3.16) correccion, f"): las dos solo estan en el VIM (6-oct-2026, VIM y VIML).
RE_GUIA_AP_ANTIGUO = re.compile(
    r"^\s*(\d+(?:\.\d+){1,3})\.?\s*(?:\(\d[^()]{0,24}\)\s*)+([^\W\d].*)$")
# El numero solo en su renglon, con o sin el antiguo entre parentesis, y el termino en el
# renglon siguiente: "1.29" / "escala de referencia convencional, f" (VIM), "0.01" / "0.01" /
# "metrology" (OIML V1, a dos columnas). Ver `_trocear_guia` y `_sigue_la_numeracion`.
RE_GUIA_AP_SOLO = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?\s*(?:\(\d[^()]{0,24}\)\s*)*$")
# Una nota del traductor ("1 N. del T. La referencia a los idiomas...", VIM) no es un
# encabezado: gastaba el 1 y el 2 y los capitulos del VIM no abrian.
RE_NOTA_DEL_TRADUCTOR = re.compile(r"N\.\s*del\s*T\.")
# Una nota al pie numerada que continua la cuenta de primer nivel abria un apartado ("5 The
# manufacturer should always take into account...", WELMEC 7.2:2026; "13 Where there is no
# UPS...", OMS). Nota al pie: numero sin punto en las LINEAS_DE_PIE ultimas lineas de su
# pagina, una frase de PALABRAS_DE_NOTA palabras o mas, y PAGINAS_DE_NOTA paginas o mas
# despues del apartado de primer nivel anterior (6-oct-2026).
LINEAS_DE_PIE = 3
PALABRAS_DE_NOTA = 8
PAGINAS_DE_NOTA = 5
# Una fecha al principio de linea no es un encabezado: "9 October 2020 Revision of the
# annexes" (tabla de revisiones de la WELMEC 7.2:2025), "25 September 2007" (PIC/S).
RE_MES = re.compile(
    r"(?i:enero|febrero|marzo|abril|mayo|junio|julio|agosto|se?ptiembre|octubre|noviembre|"
    r"diciembre|january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\b")
RE_GUIA_TABLA = re.compile(r"^\s*(?:Tabla|Table)\s+(\d+)\b\s*\.?\s*(.*)$", re.I)

# Divisiones de una guia: anexo, apendice y capitulo. Campana cero errores,
# punto 7 (PREDICCION_campana_divisiones_en_guias.md). Hasta el 3 de octubre de
# 2026 el analizador de guias no las conocia: el texto del anexo A del GUM, de
# los apendices de EA 4-02 M o de los capitulos de las Directrices GDP caia en
# el cuerpo del ultimo apartado abierto, y `anexo.A` no se podia citar.
#
# La palabra va en mayusculas o con inicial mayuscula, nunca en minuscula ("as
# described in annex IX" es una remision). El numeral, en mayuscula. Detras: o
# nada (con un asterisco de nota, como "Annex J*" del GUM), o un separador y
# una rubrica en mayuscula ("Annex 1: Example of...", "CHAPTER 1 — QUALITY
# MANAGEMENT", "Annex III. Instrument-Specific Requirements"), o una rubrica
# en mayuscula sin separador ("ANNEX 1 Overview of documents...", o "Annex A
# (informative)" de los JCGM). Una coma
# detras del numeral es una remision o una celda ("Annex I, 8.2") y no se
# acepta; una minuscula, tampoco, salvo arriba de la pagina (ver abajo).
RE_GUIA_DIV = re.compile(
    r"^\s*(?P<clase>ANNEX|Annex|ANEXO|Anexo|APPENDIX|Appendix|AP[ÉE]NDICE|Ap[ée]ndice"
    r"|CHAPTER|Chapter|CAP[ÍI]TULO|Cap[íi]tulo)\s+(?P<num>[IVXLC]+|\d+|[A-Z]{1,2})"
    r"\s*[*∗]?(?:\s*(?P<sep>[.:—–-])(?:\s*(?P<rub>[A-ZÁÉÍÓÚÑ].*)"
    r"|\s*(?P<minsep>[a-záéíóúñ].*))?"
    r"|\s+(?P<rub2>[A-ZÁÉÍÓÚÑ(].*)|\s+(?P<min>[a-záéíóúñ].*))?\s*$")
# Tras ":" o raya, la rubrica puede ir en minuscula arriba de la pagina:
# "Annex 1: applicable Directives and Regulations" a "Annex 5: conformity
# assessment procedures MID/NAWI" de WELMEC 5.2:2025. Tras un punto no: "Annex
# F. the..." es el final de una frase. Ultima tanda de la campana cero errores.
SEPARADORES_DE_RUBRICA = (":", "—", "–", "-")
# Dos guardas, porque las guias citan anexos de la MID en tablas y en el texto:
#  - Un encabezado de division va en las LINEAS_DE_CABECERA primeras lineas de
#    su pagina: asi empiezan los anexos del GUM, del JCGM 101 y 106, los
#    apendices de EA 4-02 M y los anexos de las guias WELMEC. Las celdas
#    "Annex I" de la tabla de terminos de WELMEC 8.1 van a media pagina.
#  - O, a media pagina, con separador de rubrica (":" o raya) y rubrica toda en
#    mayusculas: los capitulos de las Directrices GDP ("CAPITULO 5:
#    OPERACIONES") empiezan donde acaba el anterior.
# Y nunca en una pagina de indice, ni una linea que acaba en numero de pagina.
# Una continuacion en minuscula ("Annex 1 of the test report: Checklists...",
# WELMEC 7.2:2025) solo vale arriba de la pagina. Y la numeracion de cada clase
# empieza por la primera (1, A o I) y no retrocede: "Annex II Module H1 of the
# MID" a principio de pagina no abre un anexo II en una guia sin anexo I.
LINEAS_DE_CABECERA = 3
# Puntos de relleno de una entrada de indice, con o sin el numero de pagina
# detras, y cuantas lineas asi hacen falta para que una pagina siga el indice.
RE_PUNTOS_DE_INDICE = re.compile(r"(?:\.\s*){4,}\d*")
LINEAS_DE_INDICE = 3
# Una rubrica que acaba en numero de pagina es una linea de indice. El numero
# de pagina va separado por un espacio (o un espacio y un punto) del texto: "...
# 64", "... .64". Hasta la ultima tanda de la campana cero errores bastaba con
# acabar en cifra, y eso tiraba encabezados de verdad: "APPENDIX A - Sample
# Checklist for meeting the requirements of ISO/IEC 17025:2017" (ILAC G8, p.
# 17), y con el, por la serie, los apendices B y C; y casi seguro "Annex E
# Comentario omitido para la distribucion publica.
# Table E.1" de la EN 12830:2018. Es la regla que ya usa el detector de
# divisiones. Ver PREDICCION_ultima_tanda_encabezados.md.
RE_RUBRICA_CON_PAGINA = re.compile(r"(?<![:\-])\s\.?\s*(?:\d{1,3}|[ivxlc]+)\s*$", re.I)
TIPO_DIV_GUIA = {"ANNEX": "anexo", "ANEXO": "anexo", "APPENDIX": "apendice",
                 "APENDICE": "apendice", "APÉNDICE": "apendice",
                 "CHAPTER": "capitulo", "CAPITULO": "capitulo",
                 "CAPÍTULO": "capitulo"}
SEGMENTO_DIV_GUIA = {"anexo": "anexo", "apendice": "apend", "capitulo": "capitulo"}
ETIQUETA_DIV_GUIA = {"anexo": "Anexo", "apendice": "Apéndice", "capitulo": "Capítulo"}


def division_de_guia(s: str, posicion: int, pagina_de_indice: bool):
    """(tipo, numeral, rubrica, abre_serie) si la linea abre una division de
    guia, o None.

    `posicion` es el lugar de la linea entre las lineas no vacias de su pagina,
    contando desde 0. `abre_serie` dice si la division puede empezar su serie
    aunque su numeral no sea el primero (1, A o I): arriba de la pagina y en
    forma fuerte, separador ":" o raya y rubrica toda en mayusculas. Es
    "APPENDIX C – REVISION TABLE" de ILAC G27, que no tiene apendices A ni B
    (ultima tanda de la campana cero errores). "Annex II Module H1 of the MID",
    arriba de una pagina de WELMEC 8.2, no tiene ni lo uno ni lo otro.
    """
    if pagina_de_indice:
        return None
    m = RE_GUIA_DIV.match(s)
    if not m:
        return None
    if m.group("minsep") and m.group("sep") not in SEPARADORES_DE_RUBRICA:
        return None
    rubrica = (m.group("rub") or m.group("rub2") or m.group("min")
               or m.group("minsep") or "").strip()
    if rubrica and RE_RUBRICA_CON_PAGINA.search(rubrica):
        return None
    # Una rubrica que acaba en puntos de relleno es una entrada de indice, lleve
    # o no el numero de pagina detras ("Annex B (informative): Type of Mobile
    # Stations......", EN 301 511, p. 5).
    if rubrica and RE_PUNTOS_SIN_PAGINA.search(rubrica):
        return None
    arriba = posicion < LINEAS_DE_CABECERA
    en_mayusculas = bool(rubrica) and not any(c.islower() for c in rubrica)
    a_media = m.group("sep") in (":", "—", "–") and en_mayusculas
    if not (arriba or a_media or encabezado_en_mayusculas(m, rubrica)):
        return None
    tipo = TIPO_DIV_GUIA[m.group("clase").upper()]
    return tipo, m.group("num"), rubrica or None, bool(arriba and a_media)


# La palabra de una division dentro de una rubrica: "ANEXO I REQUISITOS ...
# NOTIFICANTES ANEXO II CONSIDERACIONES ..." es el indice de la CGA-ENAC-OCML
# que Xpdf 4.00 junta en una linea, no un encabezado.
RE_NOMBRA_DIVISION = re.compile(
    r"\b(?:ANNEX|ANEXO|APPENDIX|AP[ÉE]NDICE|CHAPTER|CAP[ÍI]TULO)\s+(?:[IVXLC]+|\d+|[A-Z])\b",
    re.I)


def encabezado_en_mayusculas(m: re.Match, rubrica: str) -> bool:
    """La forma "ANEXO II CONSIDERACIONES ESPECIFICAS SOBRE ...": la palabra en
    mayusculas, el numeral y una rubrica toda en mayusculas, sin separador.

    Vale a media pagina, como la forma con ":" o raya. Ultima tanda de la
    campana cero errores: en la CGA-ENAC-OCML, con Xpdf 4.00, el membrete
    ocupa las tres primeras lineas de cada pagina y el encabezado del anexo
    cae en la cuarta o la quinta. Una remision dentro de una frase no lleva la
    palabra ni la rubrica en mayusculas, y las celdas "Annex I" de WELMEC 8.1
    ni lo uno ni lo otro. Tampoco vale si la rubrica nombra otra division: es
    un indice juntado en una linea.
    """
    return (bool(m.group("rub2")) and m.group("sep") is None
            and m.group("clase").isupper()
            and not any(c.islower() for c in rubrica)
            and len(rubrica.split()) >= 2
            and not RE_NOMBRA_DIVISION.search(rubrica))


def sistema_de(num: str) -> str:
    """El sistema de un numeral que empieza serie sin ser el primero: cifras,
    arabigo; una letra sola, letra (salvo la I); si no, romano."""
    if num.isdigit():
        return "arabigo"
    if len(num) == 1 and num != "I":
        return "letra"
    return "romano"


def valor_de_numeral(num: str, sistema: str) -> int | None:
    """El orden de un numeral de division en su sistema, o None si no es de el.

    El sistema lo fija el primer numeral de la serie: "1" arabigo, "A" letras,
    "I" romanos. Sin eso, la "C" del GUM o la "V" de WELMEC 7.2 no se sabrian
    leer: son letra en una serie y romano en la otra.
    """
    if sistema == "arabigo":
        return int(num) if num.isdigit() else None
    if sistema == "letra":
        if len(num) == 1 and num.isalpha():
            return ord(num) - ord("A") + 1
        if len(num) == 2 and num.isalpha():
            return (ord(num[0]) - ord("A") + 1) * 26 + (ord(num[1]) - ord("A") + 1)
        return None
    if not num or any(c not in "IVXLC" for c in num):
        return None
    romanos = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for a, b in zip(num, num[1:] + " "):
        v = romanos[a]
        total += -v if romanos.get(b, 0) > v else v
    return total


SISTEMA_DEL_PRIMERO = {"1": "arabigo", "A": "letra", "I": "romano"}


def analizar_guia(pdf: TextoPdf, *, legado: bool = False) -> Analisis:
    """Guias y documentos de criterio: se trocean por apartado numerado.

    Dos reglas generales de formato, y las dos hicieron falta:

    1. **La ruta es jerarquica.** El numero de esquema punteado ya identifica el
       apartado sin ambiguedad ("ap.3.3.1") y cuelga de su padre ("ap.3.3").
       Con rutas planas, el "1." de una lista dentro de la seccion 3
       colisionaba con la seccion 1 y la regla de desempate descartaba
       contenido real. (Hasta el 1-oct-2026 este parrafo decia que el numero
       escueto colgaba de la seccion como "ap.3.3/p.2"; el codigo nunca ha
       creado rutas `/p.`: ese numero va al cuerpo, por la regla 2.)

    2. **Un numero escueto solo abre apartado si continua la secuencia.** En una
       guia la numeracion de apartados es monotonica. Un "1." que aparece
       despues de la seccion 3 no es la seccion 1 otra vez: es un elemento de
       lista, y va al cuerpo del apartado en curso.

    R13 (11-oct-2026, docs/PREDICCION_guias_apartados_2026-10-11.md) afina la regla 2 sin cambiarla de fondo, porque con ella
    sola un solo encabezado que no se reconocia arrastraba a todos los siguientes de primer nivel, y una nota al pie o una lista
    podia quedarse con el numero de un capitulo de verdad:

    - un encabezado pegado a mitad de renglon abre su apartado cuando es exactamente el que toca (`_pegado`);
    - una nota o un punto de lista sin hijos no abre el numero cuyo capitulo, con hijos, vuelve pocas paginas despues;
    - un numero de primer nivel solo en su renglon (sin punto), un hueco de uno o dos capitulos con hijos detras y el capitulo
      0 abren con la evidencia que se dice en `_trocear_guia`; nada de esto dentro de un anexo;
    - el titulo de un apartado punteado puede empezar por comilla.

    `legado=True` devuelve lo de antes de la R13 (la sonda de `-layout` de `extraccion` mide con eso). Una ruta que el
    analizador de antes ya sacaba no se vuelve a abrir partiendo un renglon.
    """
    an = Analisis()
    lineas_p1 = [l.strip() for l in (pdf.paginas[0] if pdf.paginas else "").split("\n") if l.strip()]
    an.titulo = lineas_p1[0] if lineas_p1 else None
    an.cabecera = " ".join(lineas_p1[:3])[:200]

    lp, paginas_de_indice = _lineas_de_guia(pdf)
    # R13: lo que sacaba el analizador hasta esta ronda. Un encabezado pegado a mitad de renglon cuya ruta ya estaba ahi no se
    # abre (ver `_pegado`). `legado=True` (la sonda de -layout de `extraccion`) devuelve exactamente eso.
    if legado:
        return _analizar_guia_con(an, lp, paginas_de_indice, pdf, partir=False, rutas_de_hoy=frozenset())
    de_hoy = frozenset(p.ruta for p in _analizar_guia_con(Analisis(), lp, paginas_de_indice, pdf, partir=False,
                                                          rutas_de_hoy=frozenset()).preceptos)
    an = _analizar_guia_con(an, lp, paginas_de_indice, pdf, partir=True, rutas_de_hoy=de_hoy)
    # Los bloques de requisito (`req.<codigo>`) de las guias que los numeran con un codigo (R16): se sacan de los preceptos de hoy.
    from . import catalogo, requisitos_welmec
    if (pdf.ruta_relativa or "") in catalogo.GUIAS_CON_BLOQUES_DE_REQUISITO:
        an.preceptos = requisitos_welmec.partir_en_requisitos(an.preceptos, lp, Precepto)
    # R17b/c: En ISO/IEC 27001:2022, los 93 controles de la tabla A.1 van dentro de anexo.A (anexo.A/ap.5.1 ... anexo.A/ap.8.34)
    # Documentado en catalogo.DOCUMENTOS_CON_ADAPTADOR_SINGULAR.
    if catalogo.DOCUMENTOS_CON_ADAPTADOR_SINGULAR.get(pdf.ruta_relativa or "") == "iso_27001_controles_anexo_a":
        an.preceptos = _partir_controles_iso_27001(pdf, an.preceptos, lp, paginas_de_indice)
    # R17c: Contraportada comercial de BSI en normas tecnicas (ej. EN 55032 p.110):
    # 'NO COPYING WITHOUT BSI PERMISSION...', 'British Standards Institution (BSI)' no es norma.
    an.preceptos = _quitar_contraportada_bsi(an.preceptos, lp)
    return an


MARCAS_DE_CONTRAPORTADA_BSI = ("NO COPYING WITHOUT BSI PERMISSION", "British Standards Institution (BSI)")


def _quitar_contraportada_bsi(preceptos: list[Precepto], lp: list[tuple[str, int]]) -> list[Precepto]:
    """Si el ultimo precepto contiene la contraportada comercial de BSI (`MARCAS_DE_CONTRAPORTADA_BSI`), se retira de las lineas del precepto y su `pagina_fin`
    pasa a ser la de la ultima linea que queda, leida en `lp` (R17d: antes se restaba 1 sin mirar cuantas paginas ocupaba la contraportada)."""
    if not preceptos:
        return preceptos
    ultimo = preceptos[-1]
    idx_bsi = None
    for i, ln in enumerate(ultimo.lineas):
        if any(marca in ln for marca in MARCAS_DE_CONTRAPORTADA_BSI):
            idx_bsi = i
            break
    if idx_bsi is None:
        return preceptos
    ultimo.lineas = ultimo.lineas[:idx_bsi]
    # Si termina en lineas en blanco, quitarlas
    while ultimo.lineas and not ultimo.lineas[-1].strip():
        ultimo.lineas.pop()
    # La primera linea de la contraportada en el flujo de lineas con su pagina (la del precepto, desde su pagina de comienzo) y, antes de ella, la ultima con texto.
    marca_k = next((k for k, (ln, pag) in enumerate(lp)
                    if pag >= ultimo.pagina_inicio and any(marca in ln for marca in MARCAS_DE_CONTRAPORTADA_BSI)), None)
    if marca_k is not None:
        k = marca_k - 1
        while k >= 0 and not lp[k][0].strip():
            k -= 1
        if k >= 0:
            ultimo.pagina_fin = max(ultimo.pagina_inicio, lp[k][1])
    return preceptos


# Los 93 controles del anexo A de la ISO/IEC 27001:2022 (Tabla A.1), en el orden de la tabla: los cuatro grupos 5 (37), 6 (8), 7 (14) y 8 (34). Es del propio estandar, no de la base.
CONTROLES_ISO_27001 = tuple([f"5.{i}" for i in range(1, 38)] + [f"6.{i}" for i in range(1, 9)]
                            + [f"7.{i}" for i in range(1, 15)] + [f"8.{i}" for i in range(1, 35)])
RE_CONTROL_ISO_27001 = re.compile(r"[5-8]\.\d{1,2}")
RE_GRUPO_ISO_27001 = re.compile(r"[5-8]")


def _partir_controles_iso_27001(pdf: TextoPdf, preceptos_cuerpo: list[Precepto], lp: list[tuple[str, int]],
                                paginas_de_indice: set[int]) -> list[Precepto]:
    """Separa el cuerpo de ISO/IEC 27001:2022 (clausulas 4 a 10 limpias) y extrae los 93 controles
    de la Tabla A.1 del Anexo A con rutas propias anexo.A/ap.5.1 ... anexo.A/ap.8.34 colgando de anexo.A.

    R17d: los controles salen de las FILAS de la tabla (numero | titulo | «Control» + texto), leidas con PyMuPDF (`tablas.filas_de_las_tablas`, las mismas que guarda `celda_pdf`),
    no de los renglones de Xpdf: en las filas altas Xpdf saca el texto del control despues del numero de la fila siguiente (30 de los 93 salian mal) y el rotulo de pagina
    «Table A.1 (continued)» se colaba en el texto. Una fila de grupo («6», «7», «8» y su nombre) abre el primer control de su grupo; la del grupo 5 viene antes de la primera
    fila y se queda en `anexo.A`, como el resto del texto previo a la tabla. Si la tabla no da exactamente los 93 controles en orden, falla en voz alta."""
    from . import tablas
    # Los limites salen del propio documento (donde empieza Annex A y donde empieza Bibliography fuera de indices)
    annex_a_idx = next(k for k, (ln, pag) in enumerate(lp)
                       if pag not in paginas_de_indice and not RE_PUNTOS_DE_INDICE.search(ln) and ln.strip().startswith("Annex A"))
    bib_idx = next(k for k, (ln, pag) in enumerate(lp)
                   if k > annex_a_idx and pag not in paginas_de_indice and not RE_PUNTOS_DE_INDICE.search(ln) and ln.strip().startswith("Bibliography"))
    annex_a_pag = lp[annex_a_idx][1]

    body_precepts = [p for p in preceptos_cuerpo if p.pagina_inicio < annex_a_pag]

    # El texto del anexo A hasta la primera fila de la tabla: el de siempre (de «Annex A» hasta el primer numero de control)
    re_ctrl_in = re.compile(
        r"(?:^|(?<=\s))(5\.(?:[1-9]|[12]\d|3[0-7])|6\.[1-8]|7\.(?:[1-9]|1[0-4])|8\.(?:[1-9]|[12]\d|3[0-4]))(?=\s|$)"
    )
    primero = next(((k, m.start(1)) for k in range(annex_a_idx, bib_idx) for m in re_ctrl_in.finditer(lp[k][0])), None)
    if primero is None:
        raise ExtraccionError("ISO/IEC 27001: no se encuentra el primer control de la Tabla A.1 en el anexo A")
    first_ctrl_k, first_ctrl_pos = primero
    annex_lines = [lp[k][0] for k in range(annex_a_idx, first_ctrl_k)]
    if first_ctrl_pos > 0:
        annex_lines.append(lp[first_ctrl_k][0][:first_ctrl_pos])

    p_annex_A = Precepto(
        ruta="anexo.A", tipo="anexo", numero="A", etiqueta="Anexo A",
        titulo="(normative) Information security controls reference",
        lineas=annex_lines, pagina_inicio=lp[annex_a_idx][1],
        pagina_fin=lp[first_ctrl_k][1], padre=None
    )

    controles: list[dict] = []
    grupo: str | None = None
    for pagina, fila in tablas.filas_de_las_tablas(pdf.ruta_relativa, pdf.paginas, annex_a_pag, lp[bib_idx][1]):
        celdas = [c.strip() for c in fila]
        primera = celdas[0] if celdas else ""
        resto = [c for c in celdas[1:] if c]
        if RE_CONTROL_ISO_27001.fullmatch(primera):
            controles.append(dict(numero=primera, titulo=celdas[1] if len(celdas) > 1 else "",
                                  texto=" ".join(celdas[2:]).strip(), grupo=grupo, pagina_inicio=pagina, pagina_fin=pagina))
            grupo = None
        elif RE_GRUPO_ISO_27001.fullmatch(primera) and len(resto) == 1:
            if controles:
                grupo = f"{primera} {resto[0]}"
        elif not primera and resto and controles:
            # el resto de una fila que sigue en otra pagina
            controles[-1]["texto"] = (controles[-1]["texto"] + " " + " ".join(resto)).strip()
            controles[-1]["pagina_fin"] = pagina
        elif any(celdas):
            raise ExtraccionError(f"ISO/IEC 27001: fila de la Tabla A.1 que no se reconoce (p. {pagina}): {celdas[:3]}")
    if tuple(c["numero"] for c in controles) != CONTROLES_ISO_27001:
        raise ExtraccionError(f"ISO/IEC 27001: la Tabla A.1 da {len(controles)} controles y no los {len(CONTROLES_ISO_27001)} esperados, en orden")

    ctrl_precepts = []
    for c in controles:
        num = c["numero"]
        lineas = ([c["grupo"]] if c["grupo"] else []) + [f"{num} {c['titulo']}".strip(), c["texto"]]
        ctrl_precepts.append(Precepto(
            ruta=f"anexo.A/ap.{num}",
            tipo="apartado",
            numero=num,
            etiqueta=f"Anexo A, apartado {num}",
            titulo=c["titulo"] or None,
            lineas=lineas,
            pagina_inicio=c["pagina_inicio"],
            pagina_fin=c["pagina_fin"],
            padre="anexo.A"
        ))

    return body_precepts + [p_annex_A] + ctrl_precepts


def _analizar_guia_con(an: Analisis, lp, paginas_de_indice, pdf, *, partir: bool, rutas_de_hoy: frozenset) -> Analisis:
    """El resto de `analizar_guia` (ver alli), con o sin las mejoras de la R13."""
    # Una division que se vuelve a abrir lejos de donde se abrio no es un
    # encabezado (ver `_trocear_guia`): se trocea otra vez sin ella.
    preceptos, repetidas = _trocear_guia(lp, paginas_de_indice, frozenset(), partir=partir, cadena=partir,
                                         rutas_de_hoy=rutas_de_hoy)
    if repetidas:
        preceptos, _ = _trocear_guia(lp, paginas_de_indice, frozenset(repetidas), partir=partir, cadena=partir,
                                     rutas_de_hoy=rutas_de_hoy)
    # Un indice sin rotulo ni puntos solo se reconoce al llegar al cuerpo, cuando un
    # numero de primer nivel se vuelve a abrir con el mismo titulo (`de_indice`). Sus
    # paginas se trocean otra vez como las del indice alfabetico: ahi no se abre
    # apartado. (OMS TRS 961, 6-oct-2026: los subapartados que en el cuerpo son solo
    # titulo empataban con su entrada del indice y ganaba la primera, y seis entradas
    # sin pareja en el cuerpo servian el indice como si fuera el apartado.) Como con
    # la maquetacion de Xpdf, la segunda pasada solo se queda si no pierde ninguna ruta
    # de fuera de esas paginas: sin las entradas del indice, la cuenta de primer nivel
    # empieza otra vez en el cuerpo, y un cuerpo que no empieza por el 1 dejaria de abrir.
    sin_rotulo = frozenset({p.pagina_inicio for p in preceptos if p.de_indice}
                           - set(paginas_de_indice))
    if sin_rotulo:
        otra, repetidas = _trocear_guia(lp, paginas_de_indice, frozenset(), sin_rotulo, partir=partir, cadena=partir,
                                        rutas_de_hoy=rutas_de_hoy)
        if repetidas:
            otra, _ = _trocear_guia(lp, paginas_de_indice, frozenset(repetidas), sin_rotulo, partir=partir, cadena=partir,
                                    rutas_de_hoy=rutas_de_hoy)
        if {p.ruta for p in otra} >= {p.ruta for p in preceptos if p.pagina_inicio not in sin_rotulo}:
            preceptos = otra
    # El indice y el cuerpo producen las mismas rutas: ver `quedarse_con_el_cuerpo`.
    an.preceptos = quedarse_con_el_cuerpo(
        preceptos, ("apartado", "tabla", "anexo", "apendice", "capitulo"),
        frozenset(paginas_de_indice | _paginas_de_indice_alfabetico(lp) | sin_rotulo),
        # Solo para la pagina de lo que gana (nunca para elegir): las paginas de indice sin rotulo ni puntos
        # de relleno, que se reconocen por el numero de pagina de cada entrada.
        frozenset(paginas_con_indice(paginas_vivas(pdf))))
    return an


# El rotulo de un indice alfabetico ("Índice alfabético" del VIM y del GUM), arriba de la
# pagina. Solo sirve para elegir entre dos apariciones de un apartado (5-oct-2026): no
# cambia nada mas de esas paginas.
RE_ROTULO_ALFABETICO = re.compile(
    r"^\s*(?:[ÍI]NDICE\s+ALFAB[ÉE]TICO|ALPHABETICAL\s+INDEX|INDEX(?:\s+ALPHAB[ÉE]TIQUE)?)\s*$", re.I)
# El indice alfabetico sigue en las paginas siguientes a la del rotulo mientras cada una
# tenga LETRAS_DE_INDICE o mas renglones que son solo una letra mayuscula (la de cada
# grupo): VIM, JCGM 101, GUM y OIML V1 solo rotulan la primera (6-oct-2026, VIM y VIML).
RE_LETRA_DE_INDICE = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ]\s*$")
LETRAS_DE_INDICE = 2


def _paginas_de_indice_alfabetico(lp: list[tuple[str, int]]) -> set[int]:
    primeras: dict[int, list[str]] = {}
    for ln, pag in lp:
        if ln.strip() and len(primeras.setdefault(pag, [])) < LINEAS_DE_CABECERA:
            primeras[pag].append(ln.strip())
    paginas = {pag for pag, ls in primeras.items() if any(RE_ROTULO_ALFABETICO.match(x) for x in ls)}
    letras: dict[int, int] = {}
    for ln, pag in lp:
        if RE_LETRA_DE_INDICE.match(ln):
            letras[pag] = letras.get(pag, 0) + 1
    for pag in sorted(letras):
        if pag - 1 in paginas and letras[pag] >= LETRAS_DE_INDICE:
            paginas.add(pag)
    return paginas


def _lineas_de_guia(pdf: TextoPdf) -> tuple[list[tuple[str, int]], set[int]]:
    """Las lineas con su pagina y, para las divisiones (punto 7 de la campana),
    que paginas son de indice."""
    lp = lineas_con_pagina(pdf)
    primeras: dict[int, list[str]] = {}
    for ln, pag in lp:
        if ln.strip() and len(primeras.setdefault(pag, [])) < LINEAS_DE_CABECERA:
            primeras[pag].append(ln.strip())
    paginas_de_indice = {pag for pag, ls in primeras.items()
                         if any(RE_ROTULO_INDICE.match(x) for x in ls)}
    # El indice sigue en las paginas siguientes, sin rotulo, mientras cada una
    # tenga LINEAS_DE_INDICE o mas lineas con puntos de relleno. Ultima tanda de
    # la campana cero errores (PREDICCION_ultima_tanda_indice_no_abre.md): la
    # pagina 5 de la ETSI EN 301 511 es la continuacion del indice de la 3 y su
    # "Annex A (informative):" abria un anexo.A con el texto del indice. Hace
    # falta la cadena desde el rotulo: una pagina suelta con lineas de puntos
    # puede ser un formulario, como la 19 de WELMEC 8.3, que abre su anexo 1.
    con_puntos: dict[int, int] = {}
    for ln, pag in lp:
        if RE_PUNTOS_DE_INDICE.search(ln):
            con_puntos[pag] = con_puntos.get(pag, 0) + 1
    for pag in sorted(paginas_de_indice):
        siguiente = pag + 1
        while con_puntos.get(siguiente, 0) >= LINEAS_DE_INDICE:
            paginas_de_indice.add(siguiente)
            siguiente += 1

    # R17c: Regla general para definiciones pegadas a mitad de linea:
    # Dentro del capitulo de «Terms and definitions» / «Términos y definiciones»,
    # un numero de definicion del mismo capitulo (ej. 3.N), en mitad de renglon
    # y seguido del termino en minuscula, abre una definicion nueva en linea propia.
    lp = _partir_definiciones_en_linea(lp, paginas_de_indice)

    return lp, paginas_de_indice


RE_CAP_TERMINOS = re.compile(
    r"^\s*(?:[1-9]\d*|[IVXLC]+)?\.?\s*(?:terms\s+and\s+definitions|t[ée]rminos\s+y\s+definiciones|terms,\s+definitions)\b",
    re.I
)


def _partir_definiciones_en_linea(lp: list[tuple[str, int]], paginas_de_indice: set[int]) -> list[tuple[str, int]]:
    """En guias/normas tecnicas, dentro del capitulo de terminos y definiciones,
    si una definicion quedo pegada tras texto en el mismo renglon (ej. '... 3.16 external interface...'),
    se parte en un renglon propio para abrir su precepto correspondiente."""
    cap_idx = None
    cap_num = None
    for k, (ln, pag) in enumerate(lp):
        if pag in paginas_de_indice:
            continue
        m = RE_CAP_TERMINOS.match(ln)
        if m:
            cap_idx = k
            m_num = re.match(r"^\s*([1-9]\d*|[IVXLC]+)", ln)
            cap_num = m_num.group(1) if m_num else "3"
            break
    if cap_idx is None:
        return lp

    siguiente_cap = len(lp)
    next_num = str(int(cap_num) + 1) if cap_num.isdigit() else None
    for k in range(cap_idx + 1, len(lp)):
        ln, pag = lp[k]
        if pag in paginas_de_indice:
            continue
        if next_num and re.match(rf"^\s*{next_num}\b", ln):
            siguiente_cap = k
            break
        elif re.match(r"^\s*(?:Annex|Anexo|Bibliography|Bibliograf[íi]a)\b", ln, re.I):
            siguiente_cap = k
            break

    rx_def = re.compile(rf"(?<=\S)\s+({re.escape(cap_num)}\.\d{{1,3}})\s+([a-z\u00e0-\u00ff])")
    # R17d: el numero que abre una definicion a mitad de renglon tiene que ser el SIGUIENTE de la serie: el de la mas alta que abre un renglon (o que ya se partio) mas uno.
    # Una fuente citada (\u00ab[SOURCE: ..., 3.1 quantity...]\u00bb) lleva un numero del mismo capitulo y una palabra en minuscula, y no abre nada.
    rx_abre = re.compile(rf"^\s*{re.escape(cap_num)}\.(\d{{1,3}})(?=\s|$)")
    ultimo = 0

    lp_nueva = []
    for k, (ln, pag) in enumerate(lp):
        if cap_idx < k < siguiente_cap and pag not in paginas_de_indice:
            curr_ln = ln
            partido = False
            m_abre = rx_abre.match(ln)
            if m_abre:
                ultimo = max(ultimo, int(m_abre.group(1)))
            while True:
                m = next((x for x in rx_def.finditer(curr_ln) if int(x.group(1).rsplit(".", 1)[1]) == ultimo + 1), None)
                if not m:
                    break
                partido = True
                ultimo += 1
                izq = curr_ln[:m.start()].rstrip()
                lp_nueva.append((izq, pag))
                curr_ln = curr_ln[m.start(1):]
            if partido:
                lp_nueva.append((curr_ln, pag))
            else:
                lp_nueva.append((ln, pag))
        else:
            lp_nueva.append((ln, pag))
    return lp_nueva


def divisiones_repetidas(pdf: TextoPdf) -> set[tuple[str, str]]:
    """Las divisiones (tipo, numeral) que el analizador de guias no abre porque
    se repiten lejos en el documento. Para el detector de divisiones, que asi
    no las cuenta como encabezados que faltan."""
    lp, paginas_de_indice = _lineas_de_guia(pdf)
    return _trocear_guia(lp, paginas_de_indice, frozenset())[1]


# El encabezado de pagina que repite la division en curso ("Anexo IV" arriba de
# cada pagina del anexo IV de la CGA-ENAC-OCML) esta, como mucho, a esta
# distancia de su aparicion anterior.
PAGINAS_DE_ENCABEZADO_REPETIDO = 2


def _no_es_encabezado(m: re.Match, pagina: int, alfabeticas: set[int], de_indice: set[int],
                      siguiente: str) -> bool:
    """Un numero al principio de linea que no abre apartado (6-oct-2026):
    - en una pagina del indice alfabetico;
    - en una pagina de indice, si es una entrada del indice: lleva puntos de relleno o la
      linea siguiente no es texto (otro encabezado, un numero de pagina, puntos). Una pagina
      puede acabar el indice y empezar el cuerpo ("1 Objeto y campo de aplicacion" en la
      pagina 5 del extracto de la UNE-EN 12830): ese encabezado si abre;
    - seguido de una palabra de enlace en minuscula ("4.3.1.8 or 4.3.2.7", "13.1 of EN
      ISO/IEC 17020") o de un mes (una fecha: "9 October 2020");
    - con una parte de tres cifras o mas ("30.052 dB dB", "1.0000 B/A" de la EA 4-02).
    El "0.2" del GUM y el "1.04" de la OIML V1 si son apartados."""
    if pagina in alfabeticas:
        return True
    if pagina in de_indice and (RE_PUNTOS_DE_INDICE.search(m.group(0)) or not siguiente
                                or RE_PUNTOS_DE_INDICE.search(siguiente)
                                or RE_NUMERO_SUELTO.match(siguiente)
                                or RE_GUIA_AP.match(siguiente) or RE_GUIA_AP_ANTIGUO.match(siguiente)):
        return True
    palabras = m.group(2).split(None, 1)
    if palabras and palabras[0].strip(",.;:") in PALABRAS_DE_ENLACE:
        return True
    if RE_NOTA_DEL_TRADUCTOR.match(m.group(2)):
        return True
    if RE_MES.match(m.group(2)):
        return True
    return any(len(x) >= 3 for x in m.group(1).split("."))


def _mas_uno(parte: str) -> str:
    """El numero siguiente con el mismo ancho: "09" -> "10", "01" -> "02", "9" -> "10"."""
    return f"{int(parte) + 1:0{len(parte)}d}"


def _sigue_la_numeracion(num: str, ultimo: str | None, top: int) -> bool:
    """Si `num` puede ser el apartado que viene: el siguiente de `ultimo` (el ultimo apartado
    con punto que se abrio) en cualquiera de sus niveles, o el primer hijo de ese siguiente o
    de `ultimo`, o el primer hijo del capitulo en curso o del que viene. Separa un encabezado
    con el numero solo en su renglon de una celda de tabla ("0.48" / "Standard")."""
    candidatos: set[str] = set()
    if ultimo:
        u = ultimo.split(".")
        for j in range(len(u)):
            siguiente = u[:j] + [_mas_uno(u[j])]
            candidatos.add(".".join(siguiente))
            candidatos |= {".".join(siguiente + [h]) for h in ("1", "01")}
        candidatos |= {".".join(u + [h]) for h in ("1", "01")}
    for t in (top, top + 1):
        candidatos |= {f"{t}.1", f"{t}.01"}
    return num in candidatos


def _cuelga_de_lo_abierto(num: str, ultimo: str | None, top: int) -> bool:
    """Si `num` cuelga de una division abierta: con dos niveles, de un capitulo que es el
    en curso, el siguiente, o el del ultimo apartado con punto (o su siguiente); con mas,
    de `ultimo` o de uno de sus antecesores. En una tabla de la WELMEC 8.7 los numeros de
    la ISO/IEC 17020 ("6.2.1", "8.2.1") van seguidos y en su columna, pero su "6.2" no se
    abre nunca: la fila sale partida y lo que queda detras del numero es de otra fila."""
    partes = num.split(".")
    u = ultimo.split(".") if ultimo else []
    if len(partes) == 2:
        capitulos = {top, top + 1}
        if u:
            capitulos |= {int(u[0]), int(u[0]) + 1}
        return int(partes[0]) in capitulos
    padre = ".".join(partes[:-1])
    return padre in {".".join(u[:i]) for i in range(1, len(u) + 1)}


# R17f (14-oct-2026): dentro de un anexo, una tabla cita los apartados de OTRA norma. La tabla F.1 de la EN 55032 (p. 80) tiene una columna
# con las clausulas de la ISO/IEC 17025 («5.10.1», «5.10.3.1 a) y e)», «5.10 all (5.10.2 especially)») y cada cita abria un apartado que la
# norma no tiene (`ap.5.10`, `ap.5.10.1`, `ap.5.10.3.1`: su capitulo 5 no tiene hijos). Un numero punteado al principio de renglon abre
# apartado por si solo (ver `procesar`), asi que la regla no puede mirar el numero: mira de donde viene. Dentro de un anexo, un numero
# punteado NO abre apartado cuando las dos cosas a la vez: (1) no continua la numeracion abierta (ni es el siguiente ni cuelga de lo
# abierto, `_sigue_la_numeracion` y `_cuelga_de_lo_abierto`) y (2) lo que lleva detras no es una rubrica: empieza por minuscula
# («all (5.10.2...», «a) and e)»). Una palabra de remision con mayuscula («See», «For») no vale: «The stored data shall be protected...»
# es un apartado numerado de verdad (OIML D 31) y `PALABRAS_DE_ENLACE` la incluye.
def _cita_de_otra_numeracion(m: re.Match, en_anexo: bool, ultimo: str | None, top: int) -> bool:
    if not en_anexo or "." not in m.group(1) or not m.group(2).lstrip()[:1].islower():
        return False
    return not (_sigue_la_numeracion(m.group(1), ultimo, top) and _cuelga_de_lo_abierto(m.group(1), ultimo, top))


# R17g (15-oct-2026): tablas de historial de versiones al final del documento (ETSI EN 301 511 p. 27 y EN 301 908-1 p. 26).
# Rótulo de división o anexo dedicado a la historia de versiones: las filas de sus tablas son números de versión («1.0.0»,
# «11.1.1»), no apartados técnicos de la norma.
RE_HISTORIAL_ANEXO = re.compile(r"^\s*(?:\([a-z]+\)\s*[:—–-]?\s*)?(?:Change|Revision|Document)\s+history\b", re.I)


# R17g (15-oct-2026): un número punteado al principio de renglón no abre apartado si es la continuación
# de una frase partida (ej. '... as defined in' / '3.1.18. This frequency...' en EN 55032 p.29):
# no continúa la numeración abierta, la ruta ya existe en lo que va de documento y el renglón
# anterior no tenía puntuación final y terminaba en una palabra de referencia/enlace.
def _es_continuacion_de_frase(m: re.Match, prev: str, rutas_abiertas: set[str],
                              ultimo_con_punto: str | None, ultimo_top: int) -> bool:
    num = m.group(1)
    if "." not in num or f"ap.{num}" not in rutas_abiertas:
        return False
    if (_sigue_la_numeracion(num, ultimo_con_punto, ultimo_top)
            and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top)):
        return False
    p = prev.rstrip()
    if not p:
        return False
    return (not RE_FIN_DE_FRASE.search(p)
            and _ultima_palabra_de(p) in PALABRAS_DE_REFERENCIA)


RE_EMPIEZA_NUMERO = re.compile(r"^(\d{1,3})\s+\S")


def _empieza_bloque_de_notas(resto: list[str], n: int) -> bool:
    """Si las lineas que quedan en la pagina detras de la nota `n` son el resto de un bloque
    de notas al pie: notas numeradas seguidas (n+1, n+2...), continuaciones en minuscula o el
    numero de pagina ("- 75 -", "75"). Un encabezado de verdad lleva detras su texto, que
    empieza en mayuscula. Las notas de la bibliografia del VIM, de la 6 a la 15, llenan el
    final de su pagina; sin maquetacion de Xpdf salen pegadas en tres renglones."""
    esperado = n + 1
    for x in resto:
        m = RE_EMPIEZA_NUMERO.match(x)
        if m:
            if int(m.group(1)) != esperado:
                return False
            esperado += 1
        elif re.match(r"[\dA-ZÁÉÍÓÚÑ]", x) and not RE_NUMERO_SUELTO.match(x):
            return False
    return True


def _titulo_comparable(titulo: str) -> str:
    """El titulo para ver si dos encabezados son el mismo: en minuscula, sin puntos de
    relleno ni signos, con los espacios juntos."""
    return " ".join(re.sub(r"[^\w\s]", " ", titulo.lower()).split())


def _titulo_del_renglon_siguiente(s: str, pag: int, k: int, lp: list[tuple[str, int]],
                                  siguiente_k: list, alfabeticas: set[int],
                                  paginas_de_indice: set[int], ultimo_con_punto: str | None,
                                  ultimo_top: int) -> str | None:
    """El titulo de un encabezado con el numero solo en su renglon (`RE_GUIA_AP_SOLO`), o
    None si no lo es. El titulo es el renglon siguiente de la misma pagina, si empieza por
    letra; si el siguiente repite el numero (la otra columna de la OIML V1), el de despues.
    Y solo si el numero sigue la numeracion (`_sigue_la_numeracion`): un numero suelto en
    una tabla seguido de texto no es un encabezado. No en paginas de indice."""
    ms = RE_GUIA_AP_SOLO.match(s)
    if not ms or pag in alfabeticas or pag in paginas_de_indice:
        return None
    num = ms.group(1)
    if num == ultimo_con_punto or any(len(x) >= 3 for x in num.split(".")):
        return None
    if not (_sigue_la_numeracion(num, ultimo_con_punto, ultimo_top)
            and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top)):
        return None
    j = siguiente_k[k]
    if j is not None and lp[j][1] == pag:
        otro = RE_GUIA_AP_SOLO.match(lp[j][0])
        if otro and otro.group(1) == num:
            j = siguiente_k[j]
    if j is None or lp[j][1] != pag:
        return None
    titulo = lp[j][0].strip()
    if not re.match(r"[^\W\d]", titulo) or RE_PUNTOS_DE_INDICE.search(titulo):
        return None
    palabras = titulo.split(None, 1)
    if palabras[0].strip(",.;:") in PALABRAS_DE_ENLACE or RE_MES.match(titulo):
        return None
    return titulo


# ----------------------------------------------------------------------------------------------------------------------
# R13 (11-oct-2026): encabezados que la regla de «principio de renglon» no ve.
# Ver docs/PREDICCION_guias_apartados_2026-10-11.md.
#
# El flujo de Xpdf junta a veces el titulo de un apartado con el parrafo de antes o con el de despues: Annex 11 (en) pag. 2,
# «General 1. Risk Management»; pag. 4, «8. Printouts 8.1 It should be possible ... data. 8.2 For records ...»; EN 12830 pag.
# 20, «... the primary source of power. 5.9.5 Electrical power disturbances ...». Para `_trocear_guia` esos numeros no existen,
# y con ellos se pierde la cadena de primer nivel (`ultimo_top + 1`): todos los apartados que siguen quedan dentro del ultimo
# que se abrio. Aqui se parte el renglon donde el numero cumple TODO esto:
#  - es exactamente el que toca en la numeracion abierta (`_sigue_la_numeracion` y `_cuelga_de_lo_abierto` si lleva punto;
#    `ultimo_top + 1` y con punto si es de primer nivel);
#  - lo que lo antecede acaba en un signo de fin de frase o en un parentesis o corchete que se cierra, o es el titulo del
#    apartado que abre ese mismo renglon (solo numeros punteados), o es una etiqueta corta sin signo («General», «Project
#    Phase»; solo primer nivel), o el renglon siguiente empieza por un hijo de ese numero (borradores EudraLex de 2025, que
#    llevan numerados los renglones del margen y los dejan pegados delante: «... substances. 17 2. Principles»); y la ultima
#    palabra no es una remision («see», «apartado», «Fig.»...);
#  - lo que lo sigue empieza por mayuscula;
#  - el primer nivel, ademas, tiene detras un apartado hijo o el que toca en la numeracion (`con_evidencia`);
#  - la ruta que nace no existe ya en lo que sacaba el analizador antes de esta ronda (`rutas_de_hoy`), ni se ha abierto ya en
#    esta pasada.
# Es SOLO partir: el renglon se corta en dos y cada mitad va a su precepto; no se pierde ni se cambia ni se duplica texto.
# R13, pieza 2: un numero de primer nivel SOLO en su renglon, sin punto, con el titulo en el siguiente («3» / «GENERAL POLICY»,
# EA-2/17; «4» / «Convenciones y notacion», JCGM 106; «1» / «INTRODUCTION», EURAMET cg-20).
RE_NUMERO_SOLO = re.compile(r"^\s*(\d{1,3})\.?\s*$")
# R13, pieza 3: el titulo de un apartado punteado puede empezar por una comilla («9.3 “User Requirement Specifications”, (URS),
# requirements should...», PIC/S PI 011-3). Por un parentesis no: «1.28 (1.22)» es el numero antiguo del VIM y el termino va
# debajo (`RE_GUIA_AP_SOLO`).
RE_GUIA_AP_COMILLA = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?\s+([«“\"„‘].*)$")
# R17e (14-oct-2026): el titulo puede empezar por un codigo entre corchetes («6.2 [AUM] Authentication mechanism», EN 18031-1), que RE_GUIA_AP
# ya admite al principio de renglon; sin el corchete aqui, esos encabezados pegados a mitad de renglon no abrian apartado.
RE_PEGADO = re.compile(r"(?<=\s)(\d{1,3}(?:\.\d{1,3}){0,3})(\.?)(?=\s+\[?[A-ZÁÉÍÓÚÑ])")
RE_FIN_DE_FRASE = re.compile(r"[.;:?!][)\]”»\"'’]*$")
RE_CIERRE = re.compile(r"[)\]]$")      # «... (e.g. battery of vehicle) 5.9.2 Autonomous supply»
ETIQUETA_MAXIMA = 5      # palabras de la etiqueta corta que puede ir delante de un encabezado de primer nivel
HUECO_MAXIMO = 2         # capitulos seguidos que pueden faltar en la cadena de primer nivel
DENSIDAD_DE_INDICE = 0.5  # una pagina con mas renglones candidatos que esta parte es un indice
PALABRAS_DE_REFERENCIA = PALABRAS_DE_ENLACE | frozenset({
    # el numero que sigue a estas palabras es una REMISION, una cifra o un numero de lista, no un encabezado
    "see", "clause", "clauses", "section", "sections", "paragraph", "paragraphs", "para", "item", "items", "point", "points",
    "article", "articles", "annex", "annexes", "appendix", "appendices", "chapter", "chapters", "table", "tables", "figure",
    "figures", "fig", "figs", "eq", "eqs", "equation", "equations", "note", "notes", "step", "steps", "subclause", "subclauses",
    "cf", "per", "under", "from", "than", "number", "no", "nº", "version", "edition", "part", "parts", "rule", "rules",
    "requirement", "requirements", "class", "type", "level", "range", "between", "above", "below", "about", "approx", "min",
    "max", "also", "iso", "iec", "en", "etsi", "oiml", "welmec", "ilac", "ea", "jcgm", "ref", "refs", "reference", "references",
    "véase", "ver", "numeral", "numerales", "subapartado", "subapartados", "cláusula", "cláusulas", "pág", "págs", "apdo",
    "art", "arts", "cap", "sec", "sect", "tabla", "tablas", "figura", "figuras", "anexo", "anexos", "apéndice", "apéndices",
    "capítulo", "capítulos", "apartado", "apartados", "artículo", "artículos", "punto", "puntos", "epígrafe", "epígrafes",
    "párrafo", "párrafos", "sección", "secciones", "ecuación", "ecuaciones", "versión", "edición", "parte", "partes",
    "e.g", "i.e", "etc", "vs", "p", "pp"})


def _ultima_palabra_de(texto: str) -> str:
    palabras = texto.split()
    return palabras[-1].strip("()[],;:.«»\"“”'‘’").casefold() if palabras else ""


def _etiqueta_corta(pre: str) -> bool:
    """«General», «Project Phase», «Fase de proyecto»: hasta ETIQUETA_MAXIMA palabras, la primera con mayuscula, sin cifras ni
    signos de puntuacion, y la ultima no es una remision."""
    palabras = pre.split()
    return (0 < len(palabras) <= ETIQUETA_MAXIMA and palabras[0][:1].isupper()
            and not any(c.isdigit() for c in pre) and not any(c in pre for c in ".;:?!,()")
            and _ultima_palabra_de(pre) not in PALABRAS_DE_REFERENCIA)


def _numeros_de_candidatas(lp: list[tuple[str, int]], alfabeticas: set[int], paginas_de_indice: set[int],
                           siguiente_linea: list[str], siguiente_k: list) -> list[str | None]:
    """Para cada renglon, el numero con que EMPIEZA si es un encabezado posible (los mismos filtros que el bucle de
    `_trocear_guia`, sin su estado), o None. Sirve para saber que viene detras de un encabezado (`con_evidencia`)."""
    salida: list[str | None] = [None] * len(lp)
    for k, (ln, pag) in enumerate(lp):
        s = ln.strip()
        if not s or INDICE.search(s):
            continue
        m = RE_GUIA_AP.match(s) or RE_GUIA_AP_ANTIGUO.match(s) or RE_GUIA_AP_COMILLA.match(s)
        if m and len(m.group(1)) <= 11 and not _no_es_encabezado(m, pag, alfabeticas, paginas_de_indice, siguiente_linea[k]):
            salida[k] = m.group(1)
            continue
        if pag in alfabeticas or pag in paginas_de_indice:
            continue
        ms = RE_GUIA_AP_SOLO.match(s)
        if ms:
            salida[k] = ms.group(1)
            continue
        ml = RE_NUMERO_SOLO.match(s)
        if ml and _titulo_tras_numero_solo(lp, k, pag, siguiente_k):
            salida[k] = str(int(ml.group(1)))
    return salida


def _titulo_tras_numero_solo(lp: list[tuple[str, int]], k: int, pag: int, siguiente_k: list) -> str | None:
    """El titulo de un numero de primer nivel solo en su renglon: el renglon siguiente de la misma pagina, si empieza por
    mayuscula, no es una entrada de indice y no empieza por una palabra de enlace ni por un mes."""
    j = siguiente_k[k]
    if j is None or lp[j][1] != pag:
        return None
    titulo = lp[j][0].strip()
    if not re.match(r"[A-ZÁÉÍÓÚÑ]", titulo) or RE_PUNTOS_DE_INDICE.search(titulo) or INDICE.search(titulo):
        return None
    if titulo.split(None, 1)[0].strip(",.;:") in PALABRAS_DE_ENLACE or RE_MES.match(titulo):
        return None
    return titulo


def _pegado(t: str, desde: int, es_apartado: bool, ultimo_top: int, ultimo_con_punto: str | None,
            ya: set, con_evidencia, hijo_detras) -> tuple[int, str, re.Match] | None:
    """El primer encabezado pegado en `t[desde:]` que cumple las condiciones de arriba: (donde empieza su numero, el numero,
    la coincidencia de `RE_GUIA_AP` sobre el resto), o None. `es_apartado`: `t` es el renglon de un apartado recien abierto y
    `desde` es donde empieza su titulo."""
    for m in RE_PEGADO.finditer(t, max(desde, 1)):
        num, punto = m.group(1), m.group(2)
        if f"ap.{num}" in ya:
            continue
        pre = t[:m.start()].rstrip()
        if not pre or _ultima_palabra_de(pre) in PALABRAS_DE_REFERENCIA:
            continue
        mr = RE_GUIA_AP.match(t[m.start():])
        if not mr or len(num) > 11:
            continue
        antecede = RE_FIN_DE_FRASE.search(pre) or RE_CIERRE.search(pre) or hijo_detras(num)
        if "." not in num:
            if punto != "." or int(num) != ultimo_top + 1 or not con_evidencia(int(num)):
                continue
            if not (antecede or _etiqueta_corta(pre)):
                continue
        else:
            if not (_sigue_la_numeracion(num, ultimo_con_punto, ultimo_top)
                    and _cuelga_de_lo_abierto(num, ultimo_con_punto, ultimo_top)):
                continue
            if not (antecede or es_apartado):
                continue
        return m.start(), num, mr
    return None



def _trocear_guia(lp: list[tuple[str, int]], paginas_de_indice: set[int],
                  excluir: frozenset, indice_sin_rotulo: frozenset = frozenset(), *,
                  partir: bool = False, cadena: bool = False, rutas_de_hoy: frozenset = frozenset()
                  ) -> tuple[list[Precepto], set]:
    """El troceado de una guia, y las divisiones que se repiten lejos.

    Ultima tanda de la campana cero errores (PREDICCION_ultima_tanda_encabezados.md,
    "una guarda previa"). Una division que vuelve a aparecer con el mismo
    numeral:

    - a PAGINAS_DE_ENCABEZADO_REPETIDO paginas o menos de su ultima aparicion,
      y siendo la ultima abierta de su clase, es el encabezado de pagina que la
      repite: no abre otra y va al texto. Antes se abria otra vez y
      `quedarse_con_el_cuerpo` tiraba todos los trozos menos el mas largo;
    - mas lejos, no es un encabezado: es una celda o una remision que se repite
      por el documento ("Annex I" en la columna de referencias de la tabla de
      terminos de WELMEC 8.1, que con Xpdf 4.00 cae arriba de las paginas 12,
      36, 44 y 47 y fabricaba `anexo.I`). Se devuelve en `repetidas`, y quien
      llama vuelve a trocear con ella en `excluir`: no se abre en ninguna de
      sus apariciones y sus lineas van al texto.

    R13 (11-oct-2026). `partir`: parte un renglon donde hay un encabezado pegado (`_pegado`). `cadena`: afina el primer nivel.
    Para saber que viene detras de un renglon se precalcula el numero de cada renglon candidato (`_numeros_de_candidatas`); un
    candidato «tiene hijos» si el siguiente candidato empieza por `N.`. Con `cadena`:

    - *duplicado con hijos*: un `N` de primer nivel que seria el que toca pero no tiene hijos, y dentro de PAGINAS_DE_NOTA
      paginas vuelve a salir un `N` que si los tiene (sin contar el candidato que viene justo detras: un titulo bilingue repite
      el numero), no abre. Era una nota al pie o un punto de lista. No dentro de un anexo;
    - *numero solo en su renglon*: `N` y debajo un titulo con mayuscula; abre si es `ultimo_top + 1`, la pagina no es casi toda
      de candidatos y detras viene un hijo suyo o una racha (`N+1` y luego `N+2`). No dentro de un anexo;
    - *hueco*: un `N` con `ultimo_top + 1 < N <= ultimo_top + 1 + HUECO_MAXIMO` y con hijos detras abre, salvo que lo que se
      salta vuelva mas adelante con hijos (`se_salta_un_capitulo_que_vuelve`: esta fuera de orden, no falta), en una pagina que
      es casi toda de candidatos (un indice) o dentro de un anexo;
    - *capitulo 0*: `0` con `0.1` detras y antes de cualquier otro primer nivel. No reinicia la cuenta de paginas de las notas;
    - el titulo de un apartado punteado puede empezar por comilla (`RE_GUIA_AP_COMILLA`) si es el que toca.
    """
    preceptos: list[Precepto] = []
    actual: Precepto | None = Precepto(
        ruta="preambulo", tipo="preambulo", numero=None,
        etiqueta="Preámbulo", titulo=None, pagina_inicio=1, pagina_fin=1)
    ultimo_top = 0          # ultimo numero de seccion de primer nivel aceptado
    pagina_del_ultimo_top = 1
    titulos_de_primer_nivel: dict[int, tuple[str, Precepto]] = {}
    # Las entradas de un indice no abren apartado (ver `_no_es_encabezado`): gastaban el
    # numero y el del cuerpo ya no abria ("1 Alcance" de la JCGM 101).
    # En `indice_sin_rotulo` (ver `analizar_guia`) tampoco.
    alfabeticas = _paginas_de_indice_alfabetico(lp) | set(indice_sin_rotulo)
    siguiente_linea: list[str] = [""] * len(lp)
    proxima = ""
    for _k in range(len(lp) - 1, -1, -1):
        siguiente_linea[_k] = proxima
        if lp[_k][0].strip():
            proxima = lp[_k][0].strip()
    lineas_por_pagina: dict[int, int] = {}
    lineas_de_pagina: dict[int, list[str]] = {}
    for _ln, _pag in lp:
        if _ln.strip():
            lineas_por_pagina[_pag] = lineas_por_pagina.get(_pag, 0) + 1
            lineas_de_pagina.setdefault(_pag, []).append(_ln.strip())
    siguiente_k: list[int | None] = [None] * len(lp)
    _prox = None
    for _k in range(len(lp) - 1, -1, -1):
        siguiente_k[_k] = _prox
        if lp[_k][0].strip():
            _prox = _k
    ultimo_con_punto: str | None = None   # ultimo apartado con punto que se abrio
    ruta_seccion: str | None = None   # seccion en curso, para colgar de ella
    pagina_en_curso, posicion = None, -1
    ultima_div: dict[str, tuple[str, int]] = {}   # por clase: sistema y ultimo valor
    ultima_pagina: dict[tuple[str, str], int] = {}   # por division: donde se vio
    repetidas: set[tuple[str, str]] = set()

    def cerrar():
        nonlocal actual
        if actual is not None and actual.texto:
            preceptos.append(actual)
        actual = None

    rutas_abiertas: set[str] = set()      # las rutas de apartado que esta pasada ha abierto
    en_anexo = False                      # ya se ha abierto un anexo o un apendice: su numeracion vuelve a empezar
    en_historial = False                  # anexo dedicado a historial de versiones (ETSI): sus filas no abren apartados
    ultimo_renglon_con_texto = ""         # ultimo renglon no vacio, para detectar continuaciones de frase partida
    numero_candidata = (_numeros_de_candidatas(lp, alfabeticas, paginas_de_indice, siguiente_linea, siguiente_k)
                        if partir or cadena else [])
    siguiente_candidata: list[int | None] = [None] * len(lp)
    candidatas_de_primer_nivel: dict[int, list[int]] = {}
    if partir or cadena:
        _prox = None
        for _k in range(len(lp) - 1, -1, -1):
            siguiente_candidata[_k] = _prox
            if numero_candidata[_k] is not None:
                _prox = _k
                if numero_candidata[_k].isdigit():
                    candidatas_de_primer_nivel.setdefault(int(numero_candidata[_k]), []).insert(0, _k)
    candidatas_en_pagina: dict[int, int] = {}
    for _k, _n in enumerate(numero_candidata):
        if _n is not None:
            candidatas_en_pagina[lp[_k][1]] = candidatas_en_pagina.get(lp[_k][1], 0) + 1

    def detras_de(k: int) -> str | None:
        """El numero del renglon candidato que viene despues del renglon `k`."""
        sig = siguiente_candidata[k]
        return numero_candidata[sig] if sig is not None else None

    def con_hijos(k: int, n: int) -> bool:
        """Detras del renglon `k` viene un apartado hijo de `n` («5» y luego «5.1»). Un titulo bilingue repite el numero en
        el renglon siguiente («0. Basic terms» / «0. Termes fondamentaux», OIML V 1): ese renglon no cuenta, el titulo es uno."""
        sig = siguiente_candidata[k]
        saltos = 0
        while sig is not None and numero_candidata[sig] == str(n) and saltos < 2:
            sig, saltos = siguiente_candidata[sig], saltos + 1
        otro = numero_candidata[sig] if sig is not None else None
        return otro is not None and otro.startswith(f"{n}.")

    def hay_otro_con_hijos(k: int, n: int, pag: int) -> bool:
        """Dentro de las PAGINAS_DE_NOTA paginas siguientes vuelve a salir el numero `n` de primer nivel y ese si tiene hijos.
        No cuenta el renglon candidato que viene justo detras: un titulo bilingue repite el numero («1. Metrology and its
        legal aspects» / «1. Aspects legaux de la metrologie», OIML V 1) y los dos son el mismo apartado."""
        return any(k2 > k and k2 != siguiente_candidata[k] and lp[k2][1] - pag <= PAGINAS_DE_NOTA and con_hijos(k2, n)
                   for k2 in candidatas_de_primer_nivel.get(n, ()))

    def densidad_de_candidatas(pag: int) -> float:
        """Que parte de los renglones con texto de la pagina son candidatos a encabezado: un indice sin puntos de relleno (JCGM
        101) lo es casi todo."""
        return candidatas_en_pagina.get(pag, 0) / max(lineas_por_pagina.get(pag, 1), 1)

    def se_salta_un_capitulo_que_vuelve(k: int, n: int) -> bool:
        """Entre `ultimo_top` y `n` hay un numero que mas adelante SI sale con hijos: no falta, esta fuera de orden."""
        return any(k2 > k and con_hijos(k2, m) for m in range(ultimo_top + 1, n) for k2 in candidatas_de_primer_nivel.get(m, ()))

    def titulo_de_numero_solo(s: str, k: int, pag: int) -> str | None:
        """R13, pieza 2: el titulo de un numero de primer nivel solo en su renglon, o None. Solo si es el que toca
        (`ultimo_top + 1`) y detras viene un hijo suyo o el numero siguiente."""
        ml = RE_NUMERO_SOLO.match(s)
        if not ml or pag in alfabeticas or pag in paginas_de_indice or int(ml.group(1)) != ultimo_top + 1:
            return None
        titulo = _titulo_tras_numero_solo(lp, k, pag, siguiente_k)
        otro = detras_de(k)
        n = int(ml.group(1))
        if titulo is None or otro is None or densidad_de_candidatas(pag) >= DENSIDAD_DE_INDICE:
            return None
        if otro.startswith(f"{n}."):
            return titulo
        # sin hijos, una racha: detras viene el n+1 y detras de el, el n+2 o un hijo suyo (una tabla con una columna de
        # numeros no suele llevar mas de uno o dos seguidos con su titulo)
        if otro != str(n + 1):
            return None
        sig = siguiente_candidata[k]
        despues = numero_candidata[siguiente_candidata[sig]] if siguiente_candidata[sig] is not None else None
        return titulo if despues is not None and (despues == str(n + 2) or despues.startswith(f"{n + 1}.")) else None

    def abrir_apartado(num: str, titulo: str, linea: str, pag: int) -> None:
        """Abre el apartado `num` con `linea` como primer renglon (R13: lo comparten el encabezado de principio de renglon y el
        pegado a mitad de renglon)."""
        nonlocal actual, ultimo_top, pagina_del_ultimo_top, ruta_seccion, ultimo_con_punto
        cerrar()
        partes = num.split(".")
        if len(partes) > 1:
            padre = f"ap.{'.'.join(partes[:-1])}"
            ruta_seccion = f"ap.{num}"
            ultimo_con_punto = num
        else:
            padre = None
            ultimo_top = int(partes[0])
            if ultimo_top > 0:      # el capitulo 0 no cuenta para la regla de las notas al pie (OIML V 1: la nota 1 de la p. 9)
                pagina_del_ultimo_top = pag
            ruta_seccion = f"ap.{num}"
        rutas_abiertas.add(f"ap.{num}")
        actual = Precepto(ruta=f"ap.{num}", tipo="apartado", numero=num,
                          etiqueta=f"Apartado {num}", titulo=titulo,
                          lineas=[linea], pagina_inicio=pag, pagina_fin=pag,
                          padre=padre)
        if len(partes) == 1:
            titulos_de_primer_nivel.setdefault(int(partes[0]), (_titulo_comparable(titulo), actual))

    def procesar(s: str, k_ln: int, pag: int) -> tuple[str, int]:
        """Un renglon. Devuelve ("apartado", donde empieza su titulo) si abrio un apartado, ("texto", 0) si lo sumo al
        precepto en curso y ("otro", 0) si abrio una division o una tabla (o un apartado con el numero solo en su renglon)."""
        nonlocal actual, ultimo_top, pagina_del_ultimo_top, ruta_seccion, ultimo_con_punto, en_anexo, en_historial
        div = division_de_guia(s, posicion, pag in paginas_de_indice)
        if div and (div[0], div[1]) in excluir:
            div = None
        if div:
            previo = ultima_div.get(div[0])
            if previo is None:
                sistema = SISTEMA_DEL_PRIMERO.get(div[1])
                if sistema is None and div[3]:
                    sistema = sistema_de(div[1])
                if sistema is None:
                    div = None
                else:
                    ultima_div[div[0]] = (sistema, valor_de_numeral(div[1], sistema))
            else:
                valor = valor_de_numeral(div[1], previo[0])
                if valor is None or valor < previo[1]:
                    div = None
                else:
                    ultima_div[div[0]] = (previo[0], valor)
        if div:
            clave = (div[0], div[1])
            vista = ultima_pagina.get(clave)
            if vista is not None:
                ultima_pagina[clave] = pag
                if pag - vista > PAGINAS_DE_ENCABEZADO_REPETIDO:
                    repetidas.add(clave)
                div = None
            else:
                ultima_pagina[clave] = pag
        if div:
            tipo, num, rubrica, _ = div
            cerrar()
            if tipo in ("anexo", "apendice"):
                en_anexo = True
                rub_siguiente = siguiente_linea[k_ln] if k_ln < len(siguiente_linea) else ""
                en_historial = bool(RE_HISTORIAL_ANEXO.search(rubrica or "")
                                    or RE_HISTORIAL_ANEXO.search(rub_siguiente))
            else:
                en_historial = False
            actual = Precepto(ruta=f"{SEGMENTO_DIV_GUIA[tipo]}.{num}", tipo=tipo,
                              numero=num, etiqueta=f"{ETIQUETA_DIV_GUIA[tipo]} {num}",
                              titulo=rubrica, lineas=[s], pagina_inicio=pag,
                              pagina_fin=pag, padre=None)
            return "otro", 0

        if en_historial:
            if actual:
                if actual.sin_texto_aun:
                    actual.pagina_inicio = pag
                actual.lineas.append(s)
                actual.pagina_fin = pag
            return "texto", 0

        mt = RE_GUIA_TABLA.match(s)
        if mt:
            cerrar()
            # Las tablas de una guia se numeran correlativamente en todo el
            # documento, no dentro de cada apartado, y asi es como se citan.
            # Colgarlas de la seccion las hacia inalcanzables por "Tabla 1".
            actual = Precepto(ruta=f"tabla.{mt.group(1)}", tipo="tabla",
                              numero=mt.group(1), etiqueta=f"Tabla {mt.group(1)}",
                              titulo=mt.group(2).strip() or None,
                              lineas=[s], pagina_inicio=pag, pagina_fin=pag,
                              padre=ruta_seccion)
            return "otro", 0

        m = RE_GUIA_AP.match(s) or RE_GUIA_AP_ANTIGUO.match(s)
        if m is None and cadena:
            # R13, pieza 3: «9.3 “User Requirement...»: el titulo empieza por comilla; solo si es el que toca.
            mq = RE_GUIA_AP_COMILLA.match(s)
            if (mq and len(mq.group(1)) <= 11 and _sigue_la_numeracion(mq.group(1), ultimo_con_punto, ultimo_top)
                    and _cuelga_de_lo_abierto(mq.group(1), ultimo_con_punto, ultimo_top)):
                m = mq
        titulo_aparte = None
        if not m:
            titulo_aparte = _titulo_del_renglon_siguiente(
                s, pag, k_ln, lp, siguiente_k, alfabeticas, paginas_de_indice,
                ultimo_con_punto, ultimo_top)
        if titulo_aparte:
            num = RE_GUIA_AP_SOLO.match(s).group(1)
            cerrar()
            partes = num.split(".")
            padre = f"ap.{'.'.join(partes[:-1])}"
            ruta_seccion = f"ap.{num}"
            ultimo_con_punto = num
            rutas_abiertas.add(f"ap.{num}")
            actual = Precepto(ruta=f"ap.{num}", tipo="apartado", numero=num,
                              etiqueta=f"Apartado {num}", titulo=titulo_aparte,
                              lineas=[s], pagina_inicio=pag, pagina_fin=pag, padre=padre)
            return "otro", 0
        if m is None and not titulo_aparte and cadena and not en_anexo:
            titulo_sin_punto = titulo_de_numero_solo(s, k_ln, pag)
            if titulo_sin_punto:
                abrir_apartado(str(int(RE_NUMERO_SOLO.match(s).group(1))), titulo_sin_punto, s, pag)
                return "otro", 0
        if m and len(m.group(1)) <= 11 and not _no_es_encabezado(
                m, pag, alfabeticas, paginas_de_indice, siguiente_linea[k_ln]) and not _cita_de_otra_numeracion(
                m, en_anexo, ultimo_con_punto, ultimo_top) and not _es_continuacion_de_frase(
                m, ultimo_renglon_con_texto, rutas_abiertas, ultimo_con_punto, ultimo_top):
            num = m.group(1)
            partes = num.split(".")
            if len(partes) > 1:
                # Numero punteado: identifica el apartado por si solo.
                acepta = True
            else:
                # Numero escueto: solo si continua la secuencia, y no si es una nota al pie.
                n = int(partes[0])
                nota = ((posicion >= lineas_por_pagina.get(pag, 0) - LINEAS_DE_PIE
                         or _empieza_bloque_de_notas(lineas_de_pagina[pag][posicion + 1:], n))
                        and len(s.split()) >= PALABRAS_DE_NOTA
                        and pag - pagina_del_ultimo_top >= PAGINAS_DE_NOTA)
                acepta = n == ultimo_top + 1 and not nota
                # O si vuelve a abrir un numero que ya salio con el mismo titulo y se quedo
                # en el titulo, sin texto: era una entrada de indice y el cuerpo repite su
                # titulo (OMS TRS 961, cuyo indice no tiene rotulo ni puntos). Uno con texto
                # no: la CGA-ENAC-OCML repite los titulos de sus secciones en su segunda
                # parte y se reabrian.
                repite_entrada = False
                if n in titulos_de_primer_nivel:
                    mio = _titulo_comparable(m.group(2))
                    antes, previo = titulos_de_primer_nivel[n]
                    solo_titulo = sum(1 for x in previo.lineas if x.strip()) <= 1
                    repite_entrada = solo_titulo and len(mio) >= 4 and antes.startswith(mio)
                acepta = acepta or repite_entrada
                if cadena:
                    if (acepta and not repite_entrada and not en_anexo and not con_hijos(k_ln, n)
                            and hay_otro_con_hijos(k_ln, n, pag)):
                        # Una nota al pie o un punto de lista que se queda con el numero del capitulo de verdad (el 6 de la
                        # PIC/S PI 011-3, los puntos 1 a 5 de la Recomendacion INC-1 del GUM): el capitulo, con sus hijos,
                        # viene pocas paginas despues. El renglon se queda como texto del apartado en curso.
                        acepta = False
                    elif (not acepta and n == 0 and ultimo_top == 0 and not titulos_de_primer_nivel
                          and con_hijos(k_ln, 0) and m.group(2)[:1].isupper()):
                        # El capitulo 0 de una Introduccion con 0.1, 0.2... (GUM, OIML V 1).
                        acepta = True
                    elif (not acepta and not nota and not en_anexo and 1 < n - ultimo_top <= HUECO_MAXIMO + 1
                          and con_hijos(k_ln, n)
                          and m.group(2)[:1].isupper() and densidad_de_candidatas(pag) < DENSIDAD_DE_INDICE
                          and not se_salta_un_capitulo_que_vuelve(k_ln, n)):
                        # Un hueco en la cadena de primer nivel: el capitulo que falta no se reconocio (su numero cae en una
                        # pagina de enteros sueltos, o el titulo en otro renglon) y este trae su N.1 detras. No si lo que se
                        # salta vuelve mas adelante (WELMEC 8.6: los puntos 6 y 7 de un anexo de la MID citado van delante
                        # del 5 y del 6 del cuerpo) ni en una pagina que es casi toda de candidatos (un indice, JCGM 101).
                        acepta = True
                if acepta and repite_entrada:
                    # La aparicion anterior era la entrada del indice: pierde frente a esta
                    # en `quedarse_con_el_cuerpo` aunque sea mas larga.
                    previo.de_indice = True
            if acepta:
                abrir_apartado(num, m.group(2).strip(), s, pag)
                return "apartado", m.start(2)

        if actual:
            if actual.sin_texto_aun:
                actual.pagina_inicio = pag
            actual.lineas.append(s)
            actual.pagina_fin = pag
        return "texto", 0

    def partir_pegados(clase: str, inicio: int, k_ln: int, pag: int) -> None:
        """R13: parte el renglon que acaba de entrar en `actual` donde hay un encabezado pegado (ver `_pegado`). Cada vez
        que parte, el resto abre su apartado y se sigue buscando en el."""
        def detras() -> str | None:
            sig = siguiente_candidata[k_ln]
            return numero_candidata[sig] if sig is not None else None

        def con_evidencia(n: int) -> bool:
            otro = detras()
            return otro is not None and (otro == str(n + 1) or otro.startswith(f"{n}."))

        def hijo_detras(num: str) -> bool:
            otro = detras()
            return otro is not None and otro.startswith(f"{num}.")

        es_apartado = clase == "apartado"
        while actual is not None and actual.lineas:
            t = actual.lineas[-1]
            corte = _pegado(t, inicio, es_apartado, ultimo_top, ultimo_con_punto,
                            rutas_abiertas | rutas_de_hoy, con_evidencia, hijo_detras)
            if corte is None:
                return
            pos, num, mr = corte
            pre, resto = t[:pos].rstrip(), t[pos:]
            actual.lineas[-1] = pre
            if es_apartado:
                # el titulo del apartado de antes acaba donde empieza el pegado
                mp = RE_GUIA_AP.match(pre) or RE_GUIA_AP_ANTIGUO.match(pre)
                if mp:
                    actual.titulo = mp.group(2).strip()
                    if "." not in actual.numero and titulos_de_primer_nivel.get(int(actual.numero), (None, None))[1] is actual:
                        titulos_de_primer_nivel[int(actual.numero)] = (_titulo_comparable(actual.titulo), actual)
            abrir_apartado(num, mr.group(2).strip(), resto, pag)
            es_apartado, inicio = True, mr.start(2)


    for k_ln, (ln, pag) in enumerate(lp):
        s = ln.strip()
        if s:
            if pag != pagina_en_curso:
                pagina_en_curso, posicion = pag, -1
            posicion += 1
        if not s or INDICE.search(s):
            if actual:
                actual.lineas.append("")
            continue
        clase, inicio = procesar(s, k_ln, pag)
        if s:
            ultimo_renglon_con_texto = s
        if partir and clase != "otro" and pag not in alfabeticas and pag not in paginas_de_indice:
            partir_pegados(clase, inicio, k_ln, pag)
    cerrar()
    return preceptos, repetidas


# ------------------------------------------------ subdivision en apartados/letras

# Documentos en los que `subdividir` reconoce la lista numerada dentro de un apartado (ver alli).
# DECLARADOS UNO A UNO, y por que: la regla, aplicada a toda la base el 7-oct-2026, cambiaba tambien
# la particion de cinco documentos que ya estaban (Ley 32/2014 disp. final 3.a, Ley 9/2014 disp.
# finales 2.a y 7.a, RD 782/2013 disp. final 1.a, RD 244/2016 anexo II art. 3 y anexo III art. 2),
# casi todos disposiciones que reproducen otra norma y, en el RD 244/2016, con una numeracion
# ambigua en el propio BOE. Esos cinco quedan como estaban hasta leerlos a mano
# (docs/PREDICCION_rd1021_lista_interior_2026-10-07.md).
#
# El RD 244/2016 entra el 8-oct-2026, leido a mano contra el PDF (pagina 77): su anexo II, articulo 3,
# imprime "1. Errores permitidos:" con una lista 1-2-3 dentro y despues "2. Entornos climaticos",
# "3. Entornos mecanicos", "4. Entornos electromagneticos". Los otros cuatro siguen fuera: reproducen
# otra norma y la regla no arregla sus rutas (docs/PREDICCION_encabezados_pegados_y_listas_2026-10-08.md).
DOCUMENTOS_CON_LISTAS_INTERIORES = frozenset({
    "01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/"
    "BOE_RD1021-2022_higiene_alimentos_comercio_minorista_consolidado.pdf",
    "01_Conocimiento/Fuentes_primarias/01_Legislacion_ES/BOE_RD244-2016_consolidado.pdf",
})

RE_AP_NUM = re.compile(r"^\s*(\d{1,2})\.\s+(?=[«\"A-ZÁÉÍÓÚa-zñ(])")
RE_LETRA = re.compile(r"^\s*([a-zñ])\)\s+")
# El apartado 1 pegado a la rubrica, en el mismo renglon: "Articulo 4. Uso restrictivo. 1. La
# etiqueta..." (RD 244/2016, anexo III), "Comercializacion y puesta en servicio 1. Los Estados..."
# (Directiva 2014/31/UE). Ver `subdividir`.
RE_APARTADO_1_PEGADO = re.compile(r"(?<=\S)\s+(?=1\.\s+[«\"A-ZÁÉÍÓÚ(])")


# La palabra que va delante de un numero o de una letra con parentesis cuando lo que sigue es una REMISION y no un apartado o una letra
# nuevos («el artículo 6. Ley...», «la letra a) El...», «de o) La...»). Solo para los renglones del BOE con el siguiente apartado o letra
# pegado SIN signo delante (11-oct-2026).
PALABRAS_DE_REMISION = frozenset({
    "artículo", "artículos", "apartado", "apartados", "párrafo", "párrafos", "número", "números", "núm", "letra", "letras", "punto", "puntos",
    "epígrafe", "epígrafes", "anexo", "anexos", "capítulo", "capítulos", "título", "títulos", "libro", "libros", "sección", "secciones",
    "disposición", "disposiciones", "ley", "leyes", "real", "decreto", "directiva", "reglamento", "orden", "norma", "tabla", "figura",
    "cláusula", "y", "o", "e", "u", "a", "al", "de", "del", "en", "con", "por", "ni", "el", "la", "los", "las", "según", "conforme"})


def _palabra_anterior(texto: str) -> str:
    palabras = texto.split()
    return palabras[-1].strip("(),;:.«»\"“”").casefold() if palabras else ""


def partir_apartados_pegados(lineas: list[str], re_ap: re.Pattern, prefijo: str | None = None, boe: bool = False) -> list[str]:
    """APARTADO N+1 PEGADO AL N, a mitad de renglon (8-oct-2026, ronda de completar).

    Cuando el PDF no deja espacio entre dos apartados, la extraccion los junta en un parrafo: "...sera de
    un mes. 3. Contra la resolucion..." (Ley 39/2015, art. 124). `subdividir` solo reconoce un apartado a
    principio de renglon, asi que el 3 no existia y su cita respondia PRECEPTO_INEXISTENTE. En produccion
    pasaba en la Orden ICT/155/2020 (anexo III, ap. 4.4; anexo IV, ap. 4.3), el RD 244/2016 (art. 27.2) y
    otras. Se parte SOLO si el numero es exactamente el siguiente al ultimo apartado abierto a principio de
    renglon, viene detras de punto, dos puntos o punto y coma, y le sigue mayuscula. Una cita a otro numero
    ("en el apartado 3. 5. Las...") no cumple la secuencia y no se toca. Y si ese mismo numero abre un renglon
    mas abajo en el mismo precepto, tampoco: el apartado ya existe y partir aqui lo duplicaria.

    Solo en el BOE (`boe`, 11-oct-2026): tambien detras de «(Anulado)», «(Suprimido)» o «(Derogado)», que son el apartado entero
    y no acaban en punto («2. (Anulado) 3. Lo previsto...», Ley 39/2015, disp. final 1.ª; «3. (Suprimido) 4. En el ambito...»,
    RD 106/2008, art. 10); y con el numero del articulo por delante cuando el articulo los numera asi («6.4 ... 6.5 Los
    organos...», RD 1109/1991, art. 6: `prefijo`); y detras de una palabra en minuscula, sin signo ninguno («5. Ley 21/1995, de 6 de
    julio, reguladora de los viajes combinados 6. Ley 23/2003...», RDL 1/2007, disp. derogatoria unica), salvo que la palabra anterior
    sea de remision (`PALABRAS_DE_REMISION`)."""
    numeros = [(lambda m: int(next(g for g in m.groups() if g)) if m else None)(re_ap.match(ln)) for ln in lineas]
    salida: list[str] = []
    ultimo: int | None = None
    for k, ln in enumerate(lineas):
        if numeros[k] is not None:
            ultimo = numeros[k]
        resto = ln
        while ultimo is not None:
            if ultimo + 1 in numeros[k + 1:]:
                break
            detras = r"(?<=[.:;])"
            numero = rf"{ultimo + 1}\."
            if boe:
                detras = (r"(?:(?<=[.:;])|(?<=\(Anulado\))|(?<=\(Suprimido\))|(?<=\(Derogado\))|(?<=\(Anulada\))|(?<=\(Suprimida\))"
                          r"|(?<=\(Derogada\))|(?<=[a-záéíóúüñ]))")
                if prefijo:
                    numero = rf"(?:{ultimo + 1}\.|{prefijo}\.{ultimo + 1}\.?)"
            c = None
            for cc in re.finditer(rf"{detras}\s+(?={numero}\s+[«\"A-ZÁÉÍÓÚ(])", resto):
                # detras de una letra en minuscula (sin signo): solo si esa palabra no es de remision
                if boe and resto[cc.start() - 1:cc.start()].islower() and _palabra_anterior(resto[:cc.start()]) in PALABRAS_DE_REMISION:
                    continue
                c = cc
                break
            if not c:
                break
            salida.append(resto[:c.start()])
            resto = resto[c.end():]
            ultimo += 1
        salida.append(resto)
    return salida


ALFABETO_DE_LETRAS = "abcdefghijklmnñopqrstuvwxyz"
# Una letra de serie, sencilla o doble: tras la z siguen aa), ab)... (las definiciones del RD 244/2016, art. 2,
# llegan a la ax); las del RD 106/2008, art. 3, pasan de la z). Puede ir sola en su renglon, con el texto en el
# siguiente ("f)" / "AEE que se beneficiaban de una exencion...", Directiva 2011/65/UE, art. 4.4).
RE_LETRA_SERIE = re.compile(r"^\s*([a-zñ]{1,2})\)(?:\s+|$)")
ROMANOS_DE_LETRA = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
# Un «i)», «v)» o «x)» que SI sigue a la serie (h->i, u->v, w->x) puede ser la letra o el primer renglon de una sublista
# romana de la letra anterior («h) …: i) uno; ii) dos;»). Es sublista si lo que viene detras es el romano siguiente
# («ii)», «vi)», «xi)») en el renglon de al lado o dentro del suyo; una letra no abre una lista que empiece por el 2.
SIGUIENTE_ROMANO = {"i": "ii", "v": "vi", "x": "xi"}


def _romano_de_sublista(rotulo: str, lineas: list[str], k: int) -> bool:
    """El renglon `k` abre una sublista romana (y no la letra `rotulo`): el siguiente rotulo de lista que aparece, en
    este mismo renglon (pegado, tras puntuacion) o a principio de uno de los de abajo, es el romano siguiente."""
    siguiente = SIGUIENTE_ROMANO.get(rotulo)
    if siguiente is None:
        return False
    if re.search(r"[.;:,]\s+%s\)(?:\s|$)" % siguiente, lineas[k]):
        return True
    for ln in lineas[k + 1:]:
        m = RE_LETRA_SERIE.match(ln)
        if m:
            return m.group(1) == siguiente
    return False


def _comillas_netas(ln: str) -> int:
    """Comillas que abre el renglon menos las que cierra: «» y tambien las tipograficas “”."""
    return ln.count("«") - ln.count("»") + ln.count("“") - ln.count("”")


def _se_cierra_mas_abajo(abiertas: int, netas: list[int], k: int) -> bool:
    """Con `abiertas` comillas abiertas al empezar el renglon `k`, alguno de los renglones k.. del apartado las deja a
    cero. Una « que no se cierra en todo el apartado es una comilla suelta (el PDF perdio la de cierre) y no protege
    las letras de debajo."""
    acumuladas = abiertas
    for n in netas[k:]:
        acumuladas += n
        if acumuladas <= 0:
            return True
    return False


def _siguientes(letra: str) -> list[str]:
    """Las letras que pueden seguir a `letra` en una serie. La ñ puede estar o no (el BOE la usa; la UE en
    español, no): tras la n valen la ñ y la o. Tras la z, la aa; tras la az, la ba."""
    if letra == "z":
        return ["aa"]
    cabeza, ultima = letra[:-1], letra[-1]
    if ultima == "z":
        return [s + "a" for s in _siguientes(cabeza)]
    i = ALFABETO_DE_LETRAS.index(ultima)
    return [cabeza + ALFABETO_DE_LETRAS[i + 1]] + ([cabeza + "o"] if ultima == "n" else [])


def _letras_seguidas(letras: list[str]) -> bool:
    """a, b, c... sin saltos ni vueltas a empezar."""
    if len(letras) < 2 or letras[0] != "a":
        return False
    return all(despues in _siguientes(antes) for antes, despues in zip(letras, letras[1:]))


def _siguientes_letras(ultima: str | None) -> list[str]:
    return ["a"] if ultima is None else _siguientes(ultima)


# Lo de delante de la coma es OTRA LETRA citada ("los parrafos a), b)"), no el final de un texto entre parentesis
# ("(precintado, identificacion del programa informatico y precauciones analogas.), c) informacion...", RD 244/2016
# anexo I art. 5.6, que si es la lista).
RE_LETRA_CITADA_AL_FINAL = re.compile(r"(?:^|[\s(«])[a-zñ]{1,2}(?:\s+bis)?\)$")


def _comillas(texto: str, abiertas: int, minimo: int) -> tuple[int, int]:
    """Las comillas «» abiertas al final de `texto` y el minimo que se alcanzo por el camino."""
    for ch in texto:
        if ch == "«":
            abiertas += 1
        elif ch == "»":
            abiertas -= 1
            minimo = min(minimo, abiertas)
    return abiertas, minimo


def partir_letras_pegadas(lineas: list[str], boe: bool = False) -> list[str]:
    """LETRA PEGADA a mitad de renglon (9-oct-2026), como `partir_apartados_pegados`: "...los siguientes: a) ...;
    b) ..." (Ley 39/2015 art. 116, Ley 11/2022 disp. adicionales 21-23). Solo la letra que toca en la serie, detras
    de punto, dos puntos, punto y coma o coma (y la ultima, tambien tras «, y» o «; y»: «…h) …, y i) …», RD 562/2025
    art. 39.1 llegaba a la p) y le faltaba la q)), y si esa letra no abre un renglon mas abajo. Aqui no se exige
    mayuscula: en el BOE las letras empiezan casi siempre en minuscula. La conjuncion se queda en la letra anterior.

    La COMA (ronda de las letras en apartado): el PDF junta en un parrafo las letras que acaban en coma ("a) una
    descripcion general del instrumento de medida, b) los esquemas...", RD 244/2016 art. 13.3). Pero no detras de
    otra letra: "los parrafos a), b) y c)" es una cita. Y las COMILLAS: si la cita que contiene la letra anterior se
    cierra antes de la candidata, la candidata es de otra lista (Ley 9/2014, disp. final 2.ª: la b) del art. 39 bis
    de la LSSI que reescribe, y detras, ya en el art. 40, «… c) La reincidencia…»). Las comillas que se abren y se
    cierran dentro de la letra ("ac) «Mensurando»: … ad)") no cuentan.

    Solo en el BOE (`boe`, 11-oct-2026), dos cambios mas. (1) La conjuncion («y», «o», «e», «u», «o en») sin signo delante:
    «…requisitos esenciales aplicables o b) existen deficiencias…» (RD 188/2016, art. 35.5), «…veinticuatro horas o b) –35 °C…»
    (RD 1021/2022, art. 8.1), «…del Vino, o en q) Normativa autonomica…» (RD 562/2025, art. 39.1); con las mismas guardas de cita.
    (3) La letra siguiente pegada sin signo ni conjuncion, con mayuscula detras («…contra el fraude fiscal o) El incumplimiento…», RDL
    1/2007, art. 47.ñ), salvo que la palabra anterior sea de remision (`PALABRAS_DE_REMISION`).
    (2) Una letra que vuelve a abrir un renglon mas abajo solo la excusa si es de la MISMA lista: se mira hasta el siguiente
    «a)», porque una lista nueva en el mismo apartado repite las letras («c) …, d) …» / «e) …» / «3.2 …» con su propia «d)»,
    RD 244/2016, anexo I, arts. 9.3, 10.5, 16.3 y 17.3)."""
    abren = [(lambda m: m.group(1) if m else None)(RE_LETRA_SERIE.match(ln)) for ln in lineas]
    salida: list[str] = []
    ultima: str | None = None
    abiertas = 0          # comillas abiertas al principio del renglon
    en_letra = minimo = 0  # las abiertas donde empezo la ultima letra, y el minimo desde entonces
    for k, ln in enumerate(lineas):
        # Un romano que no sigue a la letra en curso es de su sublista («i) uno; ii) dos; b) …»): no cambia de letra y
        # la «b)» pegada detras se parte (11-oct-2026; antes tomaba el «ii)» por la letra en curso y no la partia).
        if abren[k] is not None and not (abren[k] in ROMANOS_DE_LETRA and (
                ultima is None or abren[k] not in _siguientes(ultima))):
            ultima, en_letra, minimo = abren[k], abiertas, abiertas
        resto = ln
        while True:
            debajo = abren[k + 1:]
            if boe and ultima is not None and "a" in debajo:
                debajo = debajo[:debajo.index("a")]       # solo lo que queda de esta lista
            cands = [l for l in _siguientes_letras(ultima) if l not in debajo]
            if not cands:
                break
            corte = None
            patron = r"(?<=[.:;,])\s+(?:[yoeu]\s+)?(?=(%s)\)(?:\s|$))" % "|".join(cands)
            if boe:
                patron = (r"(?:(?<=[.:;,])\s+(?:(?:[yoeu]|o en)\s+)?|(?<=[^\s.:;,])\s+(?:[yoeu]|o en)\s+"
                          r"|(?<=[a-záéíóúüñ0-9])\s+(?=(?:%s)\)\s+[A-ZÁÉÍÓÚÑ]))(?=(%s)\)(?:\s|$))"
                          % ("|".join(cands), "|".join(cands)))
            for c in re.finditer(patron, resto):
                antes = resto[:c.start()]
                if boe and not c.group(0).strip() and antes[-1:] not in ".:;," and (
                        _palabra_anterior(antes) in PALABRAS_DE_REMISION or RE_LETRA_CITADA_AL_FINAL.search(antes)):
                    continue      # sin signo ni conjuncion: solo si la palabra anterior no es de remision
                if (antes.endswith(",") or c.group(0).strip()) and RE_LETRA_CITADA_AL_FINAL.search(
                        antes.rstrip(",;").rstrip()):
                    continue      # "los parrafos a), b) y c)", "las letras a), b), y c)": una cita, no la lista
                if _comillas(resto[:c.start()], abiertas, minimo)[1] < en_letra:
                    break
                corte = c
                break
            if corte is None:
                break
            abiertas, minimo = _comillas(resto[:corte.start()], abiertas, minimo)
            salida.append(resto[:corte.end()].rstrip())      # con la conjuncion, si la hay
            resto = resto[corte.end():]
            ultima, en_letra, minimo = corte.group(1), abiertas, abiertas
        salida.append(resto)
        abiertas, minimo = _comillas(resto, abiertas, minimo)
    return salida


# Lo que sigue a la ultima letra y sigue siendo SUYO: su sublista. Un ordinal (1.º, 2.ª) o un numero con parentesis
# (1), 2)) solo si empieza en 1 o sigue al anterior de la letra: "48) «representante autorizado...»" detras de la
# letra d) es la definicion 48 del articulo, no una sublista de la d) (Reglamento 2023/1542, art. 3.1). Un guion o
# una raya (las sublistas de la UE).
RE_ORDINAL_DE_LETRA = re.compile(r"^\s*(\d{1,2})\.?\s?[ºª°]")
RE_NUMERO_DE_LETRA = re.compile(r"^\s*(\d{1,3})\)")
RE_GUION_DE_LETRA = re.compile(r"^\s*[–—\-•·▪]")
RE_CIERRA_FRASE = re.compile(r"[.;][»\"”)\]]*\s*$")
# Ruido de pagina que se queda dentro de un parrafo y no decide nada: "Sec. I. Pág. 51604" (cabecera del BOE),
# "Página 10-3" (la Orden ICT/155/2020 consolidada), la raya de una nota al pie.
RE_RUIDO_EN_PARRAFO = re.compile(r"^\s*(?:Sec\.\s+[IVX]+\.\s+P[áa]g\.\s+\d+|P[áa]gina\s+\d+(?:\s*-\s*\d+)?|_{3,})\s*$",
                                 re.I)


def _hasta_donde_llega_la_ultima_letra(lb: list[str], boe: bool = False) -> list[str]:
    """La ultima letra de una serie acaba donde acaba su parrafo, no al final del precepto (9-oct-2026).

    Detras de la lista el precepto suele cerrar con parrafos suyos: "Los agentes economicos podran presentar la
    informacion a que se refiere el parrafo primero..." (Directivas 2014/30, 31, 32, 35 y 53), "La aplicacion de la
    Norma UNE 82503... proporcionara presuncion de conformidad" (Orden ICT/155/2020, anexo X, ap. 3). Si la letra se
    los quedaba, `fundamento` atribuia la presuncion de la UNE a la letra c) (el modulo H1) y `cotejar` la daba por
    buena. Se medio sobre los 93 parrafos que seguian a una ultima letra en toda la base.

    La letra sigue mientras el renglon anterior no cierre frase (con dos puntos, lo que viene es lo que anuncia), o
    el renglon empiece en minuscula (sigue la frase: "así como un dispositivo...", 2001/83 art. 54.o) o por un
    ordinal o un guion (su sublista). El primer parrafo que empieza de otro modo detras de un punto es del padre, y
    con el todo lo que sigue. El padre conserva el texto entero: lo que la letra no se queda sigue citado alli.

    Salvo que la sublista de ordinales de la letra siga MAS ABAJO: entonces ese parrafo es de la letra (RD 552/2019,
    art. 12.1.b: «Se entenderá satisfecho el requisito de los párrafos i) e ii) anteriores...» va entre el 2.º y el 3.º
    de la letra b), y cortar ahi se llevaba fuera el 3.º, el 4.º y el 5.º). Medido, para las letras dentro de un
    apartado, en docs/PREDICCION_letras_en_apartado_2026-10-09.md."""
    vivas = [k for k, ln in enumerate(lb) if ln.strip() and not RE_RUIDO_EN_PARRAFO.match(ln)
             and not any(r.match(ln) for r in RUIDO)]
    ordinal = numero = 0          # el ultimo 1.º, 2.º... y el ultimo 1), 2)... de la sublista de la letra
    for pos, (antes, k) in enumerate(zip(vivas, vivas[1:])):
        ln = lb[k].lstrip()
        mo, mn = RE_ORDINAL_DE_LETRA.match(ln), RE_NUMERO_DE_LETRA.match(ln)
        if mo and int(mo.group(1)) in (1, ordinal + 1):
            ordinal = int(mo.group(1))
            continue
        if mn and int(mn.group(1)) in (1, numero + 1):
            numero = int(mn.group(1))
            continue
        if not (mo or mn) and (ln[:1].islower() or RE_GUION_DE_LETRA.match(ln)):
            continue
        if not RE_CIERRA_FRASE.search(lb[antes]):
            continue
        if ordinal and any((m := RE_ORDINAL_DE_LETRA.match(lb[j])) and int(m.group(1)) == ordinal + 1
                           for j in vivas[pos + 2:]):
            continue
        return _sin_formula_de_cierre(lb[:antes + 1], boe)
    return _sin_formula_de_cierre(lb[:vivas[-1] + 1] if vivas else lb, boe)


# La formula final de un acto de la UE es del acto, nunca de una letra, aunque el PDF la junte en el mismo parrafo que
# la ultima letra del ultimo articulo («c) el capitulo VIII sera aplicable a partir del 18 de agosto de 2025. El
# presente Reglamento sera obligatorio en todos sus elementos…», Reglamento 2023/1542, art. 96.2).
RE_FORMULA_DE_CIERRE = re.compile(r"\s+(?=El presente Reglamento será obligatorio en todos sus elementos"
                                  r"|Los destinatarios de la presente Directiva serán)")


# La formula de cierre de un acto del BOE: «Dado en Madrid, el 6 de mayo de 2016.» (reales decretos) y «Por tanto, Mando a todos
# los espanoles, particulares y autoridades, que guarden y hagan guardar esta ley.» (leyes), con la firma y lo que sigue. La
# disposicion final la lleva (el XML la cuenta aparte, como firma, y el comparador lo admite), pero su ultimo apartado o letra no
# (11-oct-2026: RD 188/2016 disp. final 4.2, Ley 11/2022 disp. final 6.2, RD 562/2025 disp. final 4.2). Solo en el BOE (`boe`).
RE_CIERRE_DEL_ACTO_BOE = re.compile(
    r"(?:^|\s+)(?=Dado en [A-ZÁÉÍÓÚÑ][^,.]{1,40},\s+(?:a|el)\s+\d|Por tanto, Mando a todos los españoles)")


def _sin_formula_de_cierre(lb: list[str], boe: bool = False) -> list[str]:
    for k, ln in enumerate(lb):
        m = RE_FORMULA_DE_CIERRE.search(ln)
        if m:
            return lb[:k] + ([ln[:m.start()]] if ln[:m.start()].strip() else [])
    return _sin_cierre_del_acto_boe(lb) if boe else lb


def _sin_cierre_del_acto_boe(lb: list[str]) -> list[str]:
    for k, ln in enumerate(lb):
        m = RE_CIERRE_DEL_ACTO_BOE.search(ln)
        if m:
            return lb[:k] + ([ln[:m.start()]] if ln[:m.start()].strip() else [])
    return lb


def letras_sin_apartado(p: Precepto, lineas: list[str], boe: bool = False, permitir_huecos: bool = False) -> list[Precepto]:
    """LAS LETRAS DE UN PRECEPTO SIN APARTADOS NUMERADOS (9-oct-2026).

    `subdividir` solo partia letras DENTRO de un apartado numerado. Un articulo sin apartados ("Articulo 9.
    Examen y ensayos. ... a) Examen administrativo: ... b) Examen metrologico: ...", Orden ICT/155/2020) dejaba
    sus letras sin ruta, y `art.9.b` respondia PRECEPTO_INEXISTENTE. Eran 136 preceptos de la base.

    Solo si las letras abren renglon y forman UNA serie seguida desde la a) (al menos dos). Si la serie salta o
    vuelve a empezar (dos listas en el mismo articulo), no se parte: no se adivina de que lista es cada letra.
    Una letra dentro de unas comillas abiertas en el propio precepto es de la norma que este reescribe, no suya
    (Ley 32/2014, disp. final 4.ª: «2. El Gobierno establecera... a) los consumidores... b) los productores...»,
    que es el art. 16.2 de la Ley 24/2013), y no se parte. La ultima letra acaba con su parrafo
    (`_hasta_donde_llega_la_ultima_letra`)."""
    letras: list[tuple[str, list[str]]] = []
    cl: str | None = None
    cb: list[str] = []
    comillas = 0
    partidas = partir_letras_pegadas(lineas, boe)
    for k, ln in enumerate(partidas):
        m = RE_LETRA_SERIE.match(ln) if comillas == 0 else None
        if m and (len(m.group(1)) == 2 or m.group(1) in ROMANOS_DE_LETRA) and (
                cl is None or m.group(1) not in _siguientes(cl)):
            m = None
        if m and _romano_de_sublista(m.group(1), partidas, k):
            m = None      # «h) …: i) uno; ii) dos;»: la i) es la sublista de la h), no la letra siguiente
        if m:
            if cl is not None:
                letras.append((cl, cb))
            cl, cb = m.group(1), [ln]
        elif cl is not None:
            cb.append(ln)
        comillas = max(0, comillas + ln.count("«") - ln.count("»"))
    if cl is not None:
        letras.append((cl, cb))
    serie = [l for l, _ in letras]
    creciente = (len(serie) >= 2 and serie[0] == 'a'
                 and all(len(l) == 1 for l in serie)
                 and all(ALFABETO_DE_LETRAS.index(a) < ALFABETO_DE_LETRAS.index(b)
                         for a, b in zip(serie, serie[1:])))
    if not (_letras_seguidas(serie) or (permitir_huecos and creciente)):
        return []
    # La letra siguiente pegada detras de una conjuncion, al principio de un renglon ("b) Reglamento (CE) no
    # 854/2004, / y c) Directiva 2004/41/CE. Sin embargo, no se aplicara antes del...", Reglamento 853/2004, art. 15)
    # o a mitad ("b) impulsar la existencia de espacios de conexion de acceso publico y c) fomentar medidas
    # educativas...", Ley 11/2022, disp. adicional 16.a): la serie no esta completa y la ultima se quedaria la que
    # falta (y el cierre del articulo). No se parte.
    ultima, lb = letras[-1]
    sigue = re.compile(r"(?:^|\s)[yoeu]\s+(?:%s)\)\s" % "|".join(_siguientes(ultima)))
    if any(sigue.search(ln) for ln in lb):
        return []
    letras[-1] = (ultima, _hasta_donde_llega_la_ultima_letra(lb, boe))
    return [Precepto(ruta=f"{p.ruta}.{letra}", tipo="letra", numero=letra,
                     etiqueta=f"{p.etiqueta}, letra {letra})", titulo=None, lineas=lb,
                     pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin, padre=p.ruta, marca=p.marca)
            for letra, lb in letras]


def _definiciones_numeradas(p: Precepto) -> list[Precepto]:
    """Definiciones n), sin reescribir texto ni interpretar remisiones interiores."""
    bloques = []
    for ln in p.lineas:
        m = re.match(r'^\s*(\d{1,3})\)(?:\s|$)', ln)
        if m:
            bloques.append((m.group(1), [ln]))
        elif bloques:
            bloques[-1][1].append(ln)
    numeros = [int(n) for n, _ in bloques]
    # Una segunda lista reiniciada no se puede atribuir a una misma ruta.
    if len(numeros) < 2 or numeros[0] != 1 or any(a >= b for a, b in zip(numeros, numeros[1:])):
        return []
    hijos = []
    for num, lineas in bloques:
        hijo = Precepto(ruta=f'{p.ruta}.{num}', tipo='apartado', numero=num,
                        etiqueta=f'{p.etiqueta}.{num}', titulo=None, lineas=lineas,
                        pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin,
                        padre=p.ruta, marca=p.marca)
        hijos.append(hijo)
        hijos.extend(letras_sin_apartado(hijo, lineas))
    return hijos


def subdividir(preceptos: list[Precepto], listas_interiores: bool = False, boe: bool = False,
               definiciones: frozenset[str] = frozenset(),
               letras_con_huecos: frozenset[str] = frozenset(),
               numeracion_modificativa: bool = False) -> list[Precepto]:
    """Parte articulos y apartados de anexo en sus apartados numerados y letras.

    El padre conserva el texto completo: una cita al articulo entero debe
    devolver el articulo entero, y una cita al apartado, solo el apartado.
    """
    salida: list[Precepto] = []
    for p in preceptos:
        salida.append(p)
        if p.tipo not in ("articulo", "apartado", "disposicion"):
            continue
        if numeracion_modificativa:
            hijos = _subdividir_modificaciones_numeradas(p)
            if hijos is not None:
                salida.extend(hijos)
                continue
        # Los apartados de una instruccion tecnica ya salen partidos por su numeracion; lo que
        # quede numerado dentro (listas) es texto (7-oct-2026, RD 552/2019).
        if p.ruta.startswith(RUTA_INSTRUCCION + "."):
            continue
        if p.ruta in definiciones:
            hijos = _definiciones_numeradas(p)
            if hijos:
                salida.extend(hijos)
                continue
        lineas = [l for l in p.lineas]
        # Algunos reales decretos antiguos numeran los apartados con el prefijo
        # del articulo: el RD 1109/1991 escribe "Articulo 6.o" y sus apartados
        # son "6.1.", "6.2." en lugar de "1.", "2.". Se admiten las dos formas.
        re_ap = RE_AP_NUM
        if p.tipo == "articulo" and p.numero and p.numero.isdigit():
            # Con prefijo de articulo el punto final es opcional: el RD 1109/1991
            # escribe "6.1." y "6.2" en el mismo articulo. Sin prefijo se sigue
            # exigiendo el punto, porque "2 personas" no es un apartado.
            re_ap = re.compile(
                r"^\s*(?:%s\.(\d{1,2})\.?|(\d{1,2})\.)\s+(?=[«\"A-ZÁÉÍÓÚa-zñ(])"
                % re.escape(p.numero))
        # APARTADO 1 PEGADO A LA RUBRICA (8-oct-2026). Basta otro apartado posterior: el 2
        # tambien puede estar pegado y solo el 3 abrir renglon (RD 1955/2000, art. 26).
        # Sin esto existia N.2 y no N.1: la cita del 1 respondia PRECEPTO_INEXISTENTE (RD 244/2016
        # anexo III arts. 2, 4 y 8; Directivas 2014/31/UE y 2014/35/UE).
        abren = {next(g for g in m.groups() if g) for m in (re_ap.match(ln) for ln in lineas) if m}
        prefijo = p.numero if boe and p.tipo == "articulo" and p.numero and p.numero.isdigit() else None
        # Numeracion antigua: «Articulo 3. Rubrica. 3.1 ...» y «3.2 (Derogado)» pegado al
        # final de un 3.1.x. La continuidad prefijada prueba que no es una cifra de la rubrica.
        siguiente_prefijado = prefijo and any(re.search(
            rf"(?<=[.;:)])\s+{re.escape(prefijo)}\.2\.?\s+[«\"A-ZÁÉÍÓÚ(]", ln) for ln in lineas)
        if "1" not in abren and (any(int(n) > 1 for n in abren) or siguiente_prefijado):
            primero = (re.compile(rf"(?<=\S)\s+(?=(?:1\.|{re.escape(prefijo)}\.1\.?)\s+[«\"A-ZÁÉÍÓÚ(])")
                       if prefijo else RE_APARTADO_1_PEGADO)
            for k in range(min(2, len(lineas))):
                c1 = next((c for c in primero.finditer(lineas[k])
                           if _palabra_anterior(lineas[k][:c.start()]) not in PALABRAS_DE_REMISION), None)
                if c1:
                    lineas[k:k + 1] = [lineas[k][:c1.start()], lineas[k][c1.end():]]
                    break
        lineas = partir_apartados_pegados(
            lineas, re_ap, p.numero if p.tipo == "articulo" and p.numero and p.numero.isdigit() else None, boe)
        bloques: list[tuple[str, list[str]]] = []
        actual_num: str | None = None
        buf: list[str] = []
        # LISTA INTERIOR (7-oct-2026, RD 1021/2022). Un "1." que vuelve a salir con un apartado ya
        # abierto empieza una lista numerada DENTRO del apartado (las filas de una tabla), y sus
        # numeros no son apartados: el articulo 4 del RD 1021/2022 tiene en su apartado 1 una tabla
        # de 11 filas numeradas, y "art.4.2" daba la fila "Despojos..." en vez del apartado 2. La
        # lista sigue mientras sus numeros sigan; el siguiente apartado es el que continua la
        # numeracion de fuera. Si un numero vale para las dos, es de la lista cuando el mismo numero
        # vuelve a salir mas abajo (el de fuera todavia no ha llegado). Sin un "1." repetido, nada
        # cambia. Solo en DOCUMENTOS_CON_LISTAS_INTERIORES (`listas_interiores`).
        numeros = [int(next(g for g in m.groups() if g)) if m else None
                   for m in (re_ap.match(ln) for ln in lineas)]
        anidado: int | None = None
        for k, ln in enumerate(lineas):
            n = numeros[k]
            if listas_interiores and n is not None and actual_num is not None:
                fuera = int(actual_num) + 1
                if anidado is None and n == 1:
                    anidado, n = 1, None
                elif anidado is not None:
                    if n == anidado + 1 and (n != fuera or n in numeros[k + 1:]):
                        anidado, n = n, None
                    elif n == fuera:
                        anidado = None
                    else:
                        n = None
            if n is not None:
                if actual_num is not None:
                    bloques.append((actual_num, buf))
                actual_num = next(g for g in re_ap.match(ln).groups() if g)
                buf = [ln]
            elif actual_num is not None:
                buf.append(ln)
        if actual_num is not None:
            bloques.append((actual_num, buf))
        if len(bloques) < 2:
            # Sin apartados numerados, las letras cuelgan del propio precepto (9-oct-2026).
            salida.extend(letras_sin_apartado(p, lineas, boe, p.ruta in letras_con_huecos))
            continue
        apartados_con_letras: set[str] = set()
        for num, buf in bloques:
            if boe and p.tipo == "disposicion":
                buf = _sin_cierre_del_acto_boe(buf)      # la formula de cierre es de la disposicion, no del apartado
            hijo = Precepto(
                ruta=f"{p.ruta}.{num}", tipo="apartado", numero=num,
                etiqueta=f"{p.etiqueta}.{num}" if p.tipo == "articulo" else f"{p.etiqueta}, {num}",
                titulo=None, lineas=buf, pagina_inicio=p.pagina_inicio,
                pagina_fin=p.pagina_fin, padre=p.ruta, marca=p.marca)
            salida.append(hijo)
            # Si este apartado ya tiene su serie de letras extraida en un bloque anterior del mismo
            # precepto, es una norma citada repetida (Ley 32/2014 disp. final 3.ª: en su punto Siete el art. 31
            # de la Ley 21/1992 reescribe «2. Son infracciones graves...» y «3. Son infracciones leves...»
            # con sus propias letras a-r y a-i; el BOE oficial solo guarda la primera serie, `dos_series`).
            if hijo.ruta in apartados_con_letras:
                continue
            # letras dentro del apartado. Las pegadas a mitad de renglon se parten como en los preceptos sin apartados
            # (`partir_letras_pegadas`; RD 188/2016 art. 2.1 perdia de la g a la r); una doble (aa, ab...) solo si sigue
            # a la anterior, para no tomar por letra un romano ("ii)"). El apartado conserva sus renglones (`buf`).
            # Mientras haya comillas abiertas en la letra en curso Y se cierren mas abajo del apartado, las letras que
            # aparecen son del texto citado, no letras nuevas del apartado (Ley 9/2014 disp. final 2.ª: el apartado junta
            # los arts. 39 bis y 40 de la LSSI que reescribe, cada uno con su a), b)...; Ley 32/2014 disp. final 3.ª).
            # Balance neto de « », y tambien de “ ”. Una comilla que no se cierra en todo el apartado es suelta y no
            # protege nada (antes de esto una « huerfana dejaba sin letras al resto del apartado). Sin comillas, una
            # segunda lista del mismo apartado (puntos 3.1 y 3.2 del anexo I del RD 244/2016; parrafos primero y segundo
            # del 853/2004 art. 10.1) se queda como estaba: sus letras siguientes apuntan a su texto.
            # Un «i)», «v)» o «x)» que sigue a la serie pero abre una sublista romana (lo que viene es «ii)», «vi)»,
            # «xi)») no es la letra siguiente sino la sublista de la anterior (`_romano_de_sublista`).
            letras: list[tuple[str, list[str]]] = []
            cl: str | None = None
            cb: list[str] = []
            comillas_en_letra = 0     # comillas netas abiertas en la letra en curso
            partidas = partir_letras_pegadas(buf, boe)
            netas = [_comillas_netas(ln) for ln in partidas]
            for k, ln in enumerate(partidas):
                # Una cita abierta que se cierra mas abajo del apartado protege las letras de dentro. Una comilla que
                # no se cierra en todo el apartado es suelta y no protege nada (11-oct-2026).
                en_cita = comillas_en_letra > 0 and _se_cierra_mas_abajo(comillas_en_letra, netas, k)
                m = None if en_cita else RE_LETRA_SERIE.match(ln)
                if m and (len(m.group(1)) == 2 or m.group(1) in ROMANOS_DE_LETRA) and (
                        cl is None or m.group(1) not in _siguientes(cl)):
                    m = None
                if m and _romano_de_sublista(m.group(1), partidas, k):
                    m = None      # «h) …: i) uno; ii) dos;»: la i) es la sublista de la h), no la letra siguiente
                if m:
                    if cl is not None:
                        if m.group(1) == "a":
                            # otra lista en el apartado: la letra anterior es la ultima de la suya y acaba con su
                            # parrafo (RD 244/2016 anexo I art. 12.5: la e) del punto 5.1 se quedaba el 5.2)
                            cb = _hasta_donde_llega_la_ultima_letra(cb, boe)
                        letras.append((cl, cb))
                    cl, cb = m.group(1), [ln]
                    comillas_en_letra = max(0, netas[k])
                elif cl is not None:
                    cb.append(ln)
                    comillas_en_letra = max(0, comillas_en_letra + netas[k])
            if cl is not None:
                letras.append((cl, cb))
            # La ultima letra del apartado tambien acaba con su parrafo (9-oct-2026, ronda siguiente a la de las letras
            # sin apartado): se quedaba los parrafos de cierre del apartado y, en los anexos del RD 244/2016, sus puntos
            # 4.3 y 4.4 (anexo I, art. 9.4.b). Medido en docs/PREDICCION_letras_en_apartado_2026-10-09.md.
            if letras:
                letras[-1] = (letras[-1][0], _hasta_donde_llega_la_ultima_letra(letras[-1][1], boe))
                apartados_con_letras.add(hijo.ruta)
            for letra, lb in letras:
                salida.append(Precepto(
                    ruta=f"{hijo.ruta}.{letra}", tipo="letra", numero=letra,
                    etiqueta=f"{hijo.etiqueta}, letra {letra})", titulo=None, lineas=lb,
                    pagina_inicio=hijo.pagina_inicio, pagina_fin=hijo.pagina_fin,
                    padre=hijo.ruta, marca=p.marca))
    return salida


def _subdividir_modificaciones_numeradas(p: Precepto) -> list[Precepto] | None:
    """Lista 1, 2… dentro del apartado 1 que modifica otro reglamento.

    2017/625 arts. 154, 164 y 165 imprimen dos niveles consecutivos de «1.».
    Conservar solo la primera ruta .1 dejaba sus letras bajo otro texto.
    Se conserva el apartado exterior entero y se da un nivel propio a la
    lista interior (.1.1.a); no se suman dos apartados con igual número.
    El despliegue se limita al alta 2017/625, como las listas ya cotejadas.
    """
    if p.tipo != 'articulo':
        return None
    unos = [i for i, ln in enumerate(p.lineas)
            if re.match(r'^\s*1\.\s', ln)]
    if len(unos) < 2 or not re.search(r'\bse modifica como sigue:\s*$', p.lineas[unos[0]]):
        return None
    exteriores = subdividir([p], listas_interiores=True)
    salida = []
    interiores = set()
    for q in exteriores[1:]:
        if any(q.ruta.startswith(r + '.') for r in interiores):
            continue
        salida.append(q)
        if q.tipo != 'apartado' or q.padre != p.ruta or q.numero != '1':
            continue
        inicio = next((i for i, ln in enumerate(q.lineas) if i and re.match(r'^\s*1\.\s', ln)), None)
        if inicio is not None:
            interior = replace(q, lineas=q.lineas[inicio:])
            salida.extend(subdividir([interior])[1:])
            interiores.add(q.ruta)
    return salida


def subdividir_anexo_sin_numeral(preceptos: list[Precepto]) -> list[Precepto]:
    """Apartados decimales de capítulos de un anexo BOE sin numeral.

    El capítulo conserva su texto íntegro. La numeración reinicia en cada
    capítulo; 2.1 cuelga de 2 y nunca se interpreta una cantidad de una tabla.
    No se extiende a los anexos numerados ni a las listas de EUR-Lex.
    """
    rx = re.compile(r'^\s*(\d{1,2}(?:\.\d{1,2})*)\.?\s+(?=[A-ZÁÉÍÓÚÑ«])')
    salida = []
    for p in preceptos:
        salida.append(p)
        if p.tipo != 'capitulo' or p.padre != 'anexo.sn':
            continue
        lineas = list(p.lineas)
        for k in range(min(8,len(lineas))):
            corte = re.search(r'\s+(?=1\.\s+[A-ZÁÉÍÓÚÑ])', lineas[k])
            if corte:
                lineas[k:k+1] = [lineas[k][:corte.start()], lineas[k][corte.end():]]
                break
        # Tras abrir el 1, Xpdf puede haber unido el 2 con su último párrafo.
        preparadas = []
        ultimo = None
        for ln in lineas:
            m = rx.match(ln)
            if m and '.' not in m[1]:
                ultimo = int(m[1])
            corte = (re.search(r'\s+(?='+str(ultimo+1)+r'\.\s+[A-ZÁÉÍÓÚÑ])',ln)
                     if ultimo is not None else None)
            if corte:
                preparadas.extend([ln[:corte.start()],ln[corte.end():]])
                ultimo += 1
            else:
                preparadas.append(ln)
        lineas = preparadas
        bloques: dict[str, list[str]] = {}
        activo = None
        for ln in lineas:
            m = rx.match(ln)
            if m:
                num = m.group(1)
                # Si no existe su prefijo, una celda decimal no abre jerarquía.
                if '.' in num and num.rsplit('.', 1)[0] not in bloques:
                    m = None
                elif num not in bloques or num == activo:
                    activo = num
                    bloques.setdefault(num, [])
                else:
                    m = None  # otra lista reiniciada no reemplaza la primera
            if activo:
                for num, buf in bloques.items():
                    if activo == num or activo.startswith(num + '.'):
                        buf.append(ln)
        if len(bloques) < 2:
            continue
        for num, buf in bloques.items():
            padre = p.ruta if '.' not in num else p.ruta + '/ap.' + num.rsplit('.', 1)[0]
            salida.append(Precepto(
                ruta=p.ruta + '/ap.' + num, tipo='apartado', numero=num,
                etiqueta=f'{p.etiqueta}, apartado {num}', titulo=None, lineas=buf,
                pagina_inicio=p.pagina_inicio, pagina_fin=p.pagina_fin,
                padre=padre, marca=p.marca))
    return salida


def _respaldo_documento(pdf: TextoPdf, an: Analisis) -> Analisis:
    """Un acto corto sin estructura reconocible sigue siendo citable entero."""
    if an.preceptos:
        return an
    an.preceptos = [Precepto(
        ruta="documento", tipo="documento", numero=None,
        etiqueta=an.titulo or "documento completo", titulo=None,
        lineas=[p for p in pdf.paginas], pagina_inicio=1,
        pagina_fin=max(1, pdf.n_paginas))]
    return an


def vincular_articulado_a_divisiones(preceptos: list[Precepto]) -> list[Precepto]:
    """Enlaza el articulado BOE sin cambiar sus rutas públicas art.N.

    Las divisiones ya reconocidas delimitan el ámbito por orden documental.
    Una disposición, un anexo o una ITC cierran el articulado anterior.
    """
    niveles = {"reglamento": 0, "libro": 1, "titulo": 2, "capitulo": 3, "seccion": 4}
    pila: list[Precepto] = []
    salida = []
    for original in preceptos:
        p = original
        if p.tipo in niveles and not p.ruta.startswith(("anexo.", "itc.")):
            while pila and niveles[pila[-1].tipo] >= niveles[p.tipo]:
                pila.pop()
            if p.padre is None and pila:
                p = replace(p, padre=pila[-1].ruta)
            pila.append(p)
        elif p.tipo == "articulo" and re.fullmatch(r"art\.[^/]+", p.ruta):
            if p.padre is None and pila:
                p = replace(p, padre=pila[-1].ruta)
        elif p.tipo in {"cabecera", "preambulo", "disposicion", "formula_final", "anexo", "instruccion"}:
            pila.clear()
        salida.append(p)
    return salida


def _bloques_de_anexo(p: Precepto) -> list[Precepto]:
    """Desglose conservador: partes/capítulos y una serie numérica sin reinicios.

    El contenedor conserva íntegro su texto. Los nuevos hijos heredan el
    intervalo de páginas del contenedor: no se inventa una página más precisa.
    """
    if RX_TABLA_CORRESP.search(p.texto):
        return []
    # El contrato previo localiza las letras con ordinal en este contenedor.
    # Crear un punto intermedio cambia ese resultado aunque conserve el texto.
    # Hasta migrar también ese contrato, no se amplían estos bloques. Una
    # remisión en prosa a «a bis)» no es un rótulo y no bloquea el desglose.
    if any(re.match(r"^\s*[a-zñ]\s+(?:bis|ter|quater|quinquies)\)\s*", ln)
           for ln in p.lineas):
        return []
    divisiones = re.compile(
        r"^\s*(PARTE|Cap[íi]tulo)\s+([A-Z]|\d{1,3})\s*[.—:–-]?\s+([A-ZÁÉÍÓÚÑ].*)$")
    encontradas = [(k, divisiones.match(ln)) for k, ln in enumerate(p.lineas)
                   if k > 0 and divisiones.match(ln)]
    if encontradas:
        # El primer nivel impreso manda; el otro se trata dentro de cada hijo.
        encontradas = [(k, m) for k, m in encontradas if m[1] == encontradas[0][1][1]]
        # Las entradas de índice repiten los rótulos antes del cuerpo. Una
        # división repetida solo abre por su última aparición documental.
        ultimas = {(m[1], m[2]): (k, m) for k, m in encontradas}
        cortes = sorted(ultimas.values(), key=lambda x: x[0])
        if len(ultimas) != len(encontradas):
            # Solo descartar un índice compacto anterior al cuerpo. Una
            # repetición con prosa intercalada puede ser continuación: dudar.
            indices = {k for k, _ in encontradas}
            if any(k >= cortes[0][0] and k != ultimas[(m[1], m[2])][0]
                   for k, m in encontradas):
                return []
            if any(ln.strip() and k not in indices for k, ln in enumerate(p.lineas)
                   if encontradas[0][0] <= k < cortes[0][0]):
                return []
        hijos = []
        for n, (inicio, m) in enumerate(cortes):
            fin = cortes[n+1][0] if n+1 < len(cortes) else len(p.lineas)
            tipo = "parte" if m[1] == "PARTE" else "capitulo"
            hijo = replace(p, ruta=f"{p.ruta}/{tipo}.{m[2]}", tipo=tipo,
                numero=m[2], etiqueta=f"{p.etiqueta}, {m[1]} {m[2]}",
                titulo=m[3], lineas=p.lineas[inicio:fin], padre=p.ruta)
            hijos.append(hijo)
            hijos.extend(_bloques_de_anexo(hijo))
        return hijos

    punto = re.compile(
        r"^\s*(\d{1,3}(?:\.\d{1,3}){1,4}\.?(?=\s)|\d{1,3}[.)])\s+([A-ZÁÉÍÓÚÑ«¿].*)$")
    cortes = [(k, m[1].rstrip('.)')) for k, ln in enumerate(p.lineas)
              if (m := punto.match(ln))]
    if len(cortes) < 2:
        return []
    primero = cortes[0][1]
    if '.' in primero:
        # Los 1., 2., 3. interiores al 3.3 son una lista de ese punto,
        # no hermanos del 3.1 y 3.2 del capítulo.
        prefijo = primero.rsplit('.', 1)[0] + '.'
        cortes = [(k, num) for k, num in cortes if num.startswith(prefijo)]
    inicios = {'1'}
    if p.tipo == 'capitulo' and p.numero and p.numero.isdigit():
        inicios.add(p.numero+'.1')
    if primero not in inicios:
        return []
    ultimo = None
    vistos = set()
    for _, num in cortes:
        if num in vistos or (ultimo is not None and num not in _siguientes_de(ultimo)):
            return []
        vistos.add(num)
        ultimo = num
    hijos = []
    for n, (inicio, num) in enumerate(cortes):
        # El punto padre incluye sus subpuntos; un hermano termina su ámbito.
        fin = next((k for k, otro in cortes[n+1:] if not otro.startswith(num+'.')), len(p.lineas))
        anterior = num.rsplit('.', 1)[0] if '.' in num else None
        padre = f'{p.ruta}/ap.{anterior}' if anterior in vistos else p.ruta
        hijos.append(replace(p, ruta=f'{p.ruta}/ap.{num}', tipo='apartado',
            numero=num, etiqueta=f'{p.etiqueta}, punto {num}', titulo=None,
            lineas=p.lineas[inicio:fin], padre=padre))
    return hijos


def subdividir_puntos_de_anexo(preceptos: list[Precepto]) -> list[Precepto]:
    """Añade unidades citables de anexos UE sin alterar unidades existentes."""
    rutas = {p.ruta for p in preceptos}
    salida = []
    for p in preceptos:
        salida.append(p)
        if (p.ruta.startswith('anexo.') and p.tipo in {'anexo', 'capitulo', 'seccion', 'apendice'}
                and not any(r.startswith(p.ruta+'/') for r in rutas)):
            salida.extend(h for h in _bloques_de_anexo(p) if h.ruta not in rutas)
    return salida


def analizar(familia: str, pdf: TextoPdf) -> Analisis:
    # R3ALTAS: contrato parcial explícito de cuatro textos largos. El motor
    # conserva todo el PDF; esta selección exige su ruta y huella registradas.
    from . import alcance_r3
    pdf = alcance_r3.para_trocear(pdf)
    an = _respaldo_documento(pdf, _ANALIZADORES[familia](pdf))
    an.preceptos = sin_rutas_repetidas(an.preceptos)
    if familia == 'boe':
        # C2B: la regla de enlace es general, pero su despliegue se limita a
        # las ocho altas BOE de alta_r2.json. Las obras ya existentes conservan
        # su jerarquía hasta una migración propia; no se rebaja su comprobador.
        altas_boe_r2 = {
            'BOE-A-1983-19755', 'BOE-A-2000-24019', 'BOE-A-2002-18099',
            'BOE-A-2011-11604', 'BOE-A-2011-15623', 'BOE-A-2013-13645',
            'BOE-A-2015-710', 'BOE-A-2022-21135',
        }
        if an.identificador is None or an.identificador in altas_boe_r2 or alcance_r3.activa(pdf.ruta_relativa, pdf.sha256):
            an.preceptos = vincular_articulado_a_divisiones(an.preceptos)
    elif familia == 'eurlex':
        an.preceptos = subdividir_puntos_de_anexo(an.preceptos)
    return an


_ANALIZADORES = {"boe": analizar_boe, "eurlex": analizar_eurlex, "guia": analizar_guia}
ANALIZADORES = {k: (lambda pdf, f=k: analizar(f, pdf)) for k in _ANALIZADORES}
