"""La ruta de un precepto es una ESTRUCTURA, no una cadena.

La cadena `art.3.1.b` es una **proyeccion** de la estructura, no el dato. Si la
cadena fuera el dato, cada ambiguedad quedaria congelada en la representacion y
resolverla despues obligaria a reprocesar el corpus entero. Con la estructura
como dato, todas son decisiones de renderizado que se pueden tomar mas tarde.

Las ambiguedades que esto deja ABIERTAS a proposito, y que hoy no se resuelven:

  - «punto 3.2.1 del anexo II»: "3.2.1" es UN nivel con numeral decimal, y
    escrito con puntos es indistinguible de tres niveles. Se guarda como un
    nivel cuyo numeral es "3.2.1" y cuyo sistema es `decimal`.
  - «articulo 3.1»: homofono de «articulo 3, apartado 1» cuando la obra tiene
    articulos de numeral decimal. Se guarda como se escribio y se anota que la
    lectura no esta decidida.
  - `art.3.2`: apartado 2 o numero 2. La gramatica posicional presupone que bajo
    un articulo solo hay apartados, y en el corpus espanol eso es falso. Por eso
    cada nivel lleva su TIPO y no se deduce de su posicion.
  - `art.4.a`: letra colgando del articulo, o apartado elidido por el citante.
    Se guarda el hueco como tal.
  - «letra b), segundo guion» y «letra b), inciso ii)»: el mismo nivel fisico
    con dos nombres en el mismo acto. Los tipos admiten alias.

Y el sistema de numeracion se conserva: `anexo.II` y `anexo.2` no son lo mismo
si la obra tiene dos series.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Tipos de nivel. Los alias existen porque el mismo nivel fisico se nombra de
# dos maneras dentro del mismo acto, y elegir una al vuelo perderia la otra.
ALIAS_TIPO = {
    "articulo": "art", "art": "art",
    "apartado": "ap", "ap": "ap", "punto": "ap", "clausula": "ap",
    "letra": "letra",
    "inciso": "inciso", "guion": "inciso", "guión": "inciso",
    "numero": "num", "num": "num", "número": "num",
    "anexo": "anexo", "apendice": "apend", "apéndice": "apend",
    "tabla": "tabla", "figura": "figura",
    "titulo": "titulo", "capitulo": "cap", "seccion": "sec",
    "disposicion": "disp",
    # R16 (12-oct-2026). `libro`: los libros 2 y siguientes de un texto refundido (`libro.2/titulo.I/capitulo.I`, RDL 1/2007); el
    # primero lleva las rutas de siempre, sin prefijo. `req`: el bloque de requisito de una guia que lo numera con un codigo
    # (`req.U1`, `req.I4-1`; WELMEC 7.2 de 2025), de primer nivel y con el codigo tal como lo imprime la guia.
    "libro": "libro",
    "requisito": "req", "requirement": "req", "req": "req",
}

ROMANO = re.compile(r"^[IVXLCDM]+$", re.I)
# El codigo de un bloque de requisito: una o dos letras, un numero y, en los de instrumento, un segundo numero tras un guion
# (`U1`, `L4`, `I4-1`).
CODIGO_DE_REQUISITO = re.compile(r"^[A-Z]{1,2}\d+(?:-\d+)?$", re.I)
DECIMAL = re.compile(r"^\d+(?:\.\d+)+$")
ARABIGO = re.compile(r"^\d+$")
LETRA = re.compile(r"^[a-zñ]$", re.I)
ORDINAL_ROMANO_MIN = re.compile(r"^[ivxlcdm]+$")


# Tipos de nivel que se numeran en romanos. En ellos, un numeral de un solo
# caracter como "I" o "V" es un romano y no una letra de subdivision. Sin esta
# distincion, "Anexo I" producia la ruta "anexo.i", que no existe, y el sistema
# respondia PRECEPTO_INEXISTENTE sobre un anexo que si estaba ingerido: una
# negacion falsa con apariencia de fundada, que es el peor error posible aqui.
# El tipo se llama `titulo` (ver ALIAS_TIPO). Hasta el 1-oct-2026 aqui ponia
# "tit", y "título I" daba `titulo.i`: PRECEPTO_INEXISTENTE sobre un titulo que
# la base tiene. Revision P1, ver PREDICCION_revision_P1.md.
TIPOS_ROMANOS = {"anexo", "apend", "lib", "titulo", "cap", "sec", "parte"}


def sistema_de(numeral: str, tipo: str = "") -> str:
    """Como esta escrito el numeral. No es cosmetica: distingue series.

    `tipo` desempata entre letra y romano cuando el numeral tiene un solo
    caracter: "I" es letra en una subdivision y romano en un anexo.
    """
    n = (numeral or "").strip()
    if (tipo or "").lower() == "req" and CODIGO_DE_REQUISITO.match(n):
        return "codigo"
    if DECIMAL.match(n):
        return "decimal"
    if ARABIGO.match(n):
        return "arabigo"
    if (tipo or "").lower() in TIPOS_ROMANOS and ROMANO.match(n):
        return "romano"
    # Una division numerada por letra, como el anexo A de una norma EN, va en
    # mayuscula igual que un romano: la ficha guarda `anexo.A`, y sin esto "Anexo
    # A" daba `anexo.a` y "Anexo D" (D es romana) `anexo.D`. Revision P7.
    if (tipo or "").lower() in TIPOS_ROMANOS and LETRA.match(n):
        return "letra_de_division"
    if LETRA.match(n):
        return "letra"
    if ROMANO.match(n):
        return "romano_min" if ORDINAL_ROMANO_MIN.match(n) else "romano"
    return "otro"


@dataclass(frozen=True)
class Nivel:
    """Un escalon de la ruta: que es, como se numera y como estaba escrito."""
    tipo: str                    # art, ap, letra, inciso, anexo...
    numeral: str                 # "3", "3.2.1", "b", "XI"
    sistema: str = ""            # arabigo, decimal, letra, romano...
    literal: str = ""            # como aparecia en la cita, para trazabilidad

    def __post_init__(self):
        if not self.sistema:
            object.__setattr__(self, "sistema",
                               sistema_de(self.numeral, self.tipo))

    @property
    def canonico(self) -> str:
        """La proyeccion de este nivel. Los romanos van en mayuscula."""
        n = self.numeral
        if self.sistema in ("romano", "letra_de_division", "codigo"):
            n = n.upper()
        elif self.sistema == "letra":
            n = n.lower()
        return f"{self.tipo}.{n}"


@dataclass
class RutaEstructurada:
    """Lista ordenada de niveles, mas lo que no se ha decidido.

    `dudas` no es decoracion: es lo que impide que una lectura provisional se
    convierta en un hecho por el mero paso del tiempo. Quien renderice puede
    consultarla; quien no, al menos no la borra.
    """
    niveles: list[Nivel] = field(default_factory=list)
    dudas: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.niveles)

    def anadir(self, tipo: str, numeral: str, literal: str = "") -> None:
        t = ALIAS_TIPO.get(tipo.lower(), tipo.lower())
        self.niveles.append(Nivel(tipo=t, numeral=str(numeral).strip(),
                                  literal=literal or f"{tipo} {numeral}"))

    def dudar(self, motivo: str) -> None:
        if motivo not in self.dudas:
            self.dudas.append(motivo)

    # ------------------------------------------------------- proyecciones

    @property
    def cadena(self) -> str | None:
        """La ruta canonica de toda la vida: `anexo.XI/apend.II/tabla.2`.

        Regla de proyeccion, y es una convencion de escritura, no una verdad
        sobre el documento: **solo los hijos de un articulo se encadenan con
        punto** (`art.3.1.b`). Todo lo demas abre tramo con barra, porque
        reinicia numeracion. Cambiar esta regla no obliga a reprocesar nada:
        por eso el dato es la estructura.
        """
        if not self.niveles:
            return None
        tramos: list[list[str]] = []
        for n in self.niveles:
            cuelga = (tramos and tramos[-1] and n.tipo in HIJOS_DE_ARTICULO
                      and self._raiz_de_tramo(tramos) == "art")
            if cuelga:
                tramos[-1].append(n.numeral.lower() if n.sistema == "letra"
                                  else n.numeral)
            else:
                tramos.append([n.canonico])
        return "/".join(".".join(t) for t in tramos)

    @staticmethod
    def _raiz_de_tramo(tramos: list[list[str]]) -> str:
        return tramos[-1][0].split(".", 1)[0] if tramos and tramos[-1] else ""

    @property
    def profundidad(self) -> int:
        return len(self.niveles)

    def tipos(self) -> list[str]:
        return [n.tipo for n in self.niveles]


# Los niveles que un articulo lleva colgando y que la convencion escribe con
# punto detras del articulo, sin repetir el tipo.
HIJOS_DE_ARTICULO = {"ap", "letra", "inciso", "num"}

# Niveles que reinician la numeracion y por eso abren tramo propio en la ruta.
# Dentro de un anexo la numeracion vuelve a empezar, asi que la cadena si forma
# parte de la ruta. Libro, titulo, capitulo y seccion NO: los articulos se
# numeran de corrido en toda la obra y ninguna cita real menciona la cadena
# entera, asi que son atributos del precepto y no tramos de su ruta.
ABREN_TRAMO = {"anexo", "apend", "tabla", "figura", "disp"}

# Los que son atributos y nunca ruta.
SOLO_ATRIBUTO = {"lib", "titulo", "cap", "sec"}


# El libro primero de una obra con libros no lleva prefijo (`titulo.I`, `titulo.I/capitulo.II`: RDL 1/2007), pero quien cita
# escribe `libro.1/titulo.I`. `consulta.ruta_efectiva` lo traduce, y solo cuando la ruta con prefijo no existe y la otra si.
PREFIJO_LIBRO_PRIMERO = "libro.1/"


def sin_libro_primero(ruta: str) -> str | None:
    """`libro.1/X` -> `X`. None si la ruta no empieza por `libro.1/` o no trae nada detras (`libro.1` a secas no cambia)."""
    if ruta.startswith(PREFIJO_LIBRO_PRIMERO) and len(ruta) > len(PREFIJO_LIBRO_PRIMERO):
        return ruta[len(PREFIJO_LIBRO_PRIMERO):]
    return None
