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
ALIAS_TIPO = {'articulo': 'art', 'art': 'art', 'apartado': 'ap', 'ap': 'ap', 'punto': 'ap', 'clausula': 'ap', 'letra': 'letra', 'inciso': 'inciso', 'guion': 'inciso', 'guión': 'inciso', 'numero': 'num', 'num': 'num', 'número': 'num', 'anexo': 'anexo', 'apendice': 'apend', 'apéndice': 'apend', 'tabla': 'tabla', 'figura': 'figura', 'titulo': 'titulo', 'capitulo': 'cap', 'seccion': 'sec', 'disposicion': 'disp', 'libro': 'libro', 'requisito': 'req', 'requirement': 'req', 'req': 'req'}
ROMANO = re.compile('^[IVXLCDM]+$', re.I)
CODIGO_DE_REQUISITO = re.compile('^[A-Z]{1,2}\\d+(?:-\\d+)?$', re.I)
DECIMAL = re.compile('^\\d+(?:\\.\\d+)+$')
ARABIGO = re.compile('^\\d+$')
LETRA = re.compile('^[a-zñ]$', re.I)
ORDINAL_ROMANO_MIN = re.compile('^[ivxlcdm]+$')
TIPOS_ROMANOS = {'anexo', 'apend', 'lib', 'titulo', 'cap', 'sec', 'parte'}

def sistema_de(numeral: str, tipo: str='') -> str:
    """Como esta escrito el numeral. No es cosmetica: distingue series.

    `tipo` desempata entre letra y romano cuando el numeral tiene un solo
    caracter: "I" es letra en una subdivision y romano en un anexo.
    """
    n = (numeral or '').strip()
    if (tipo or '').lower() == 'req' and CODIGO_DE_REQUISITO.match(n):
        return 'codigo'
    if DECIMAL.match(n):
        return 'decimal'
    if ARABIGO.match(n):
        return 'arabigo'
    if (tipo or '').lower() in TIPOS_ROMANOS and ROMANO.match(n):
        return 'romano'
    if (tipo or '').lower() in TIPOS_ROMANOS and LETRA.match(n):
        return 'letra_de_division'
    if LETRA.match(n):
        return 'letra'
    if ROMANO.match(n):
        return 'romano_min' if ORDINAL_ROMANO_MIN.match(n) else 'romano'
    return 'otro'

@dataclass(frozen=True)
class Nivel:
    """Un escalon de la ruta: que es, como se numera y como estaba escrito."""
    tipo: str
    numeral: str
    sistema: str = ''
    literal: str = ''

    def __post_init__(self):
        if not self.sistema:
            object.__setattr__(self, 'sistema', sistema_de(self.numeral, self.tipo))

    @property
    def canonico(self) -> str:
        """La proyeccion de este nivel. Los romanos van en mayuscula."""
        n = self.numeral
        if self.sistema in ('romano', 'letra_de_division', 'codigo'):
            n = n.upper()
        elif self.sistema == 'letra':
            n = n.lower()
        return f'{self.tipo}.{n}'

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

    def anadir(self, tipo: str, numeral: str, literal: str='') -> None:
        t = ALIAS_TIPO.get(tipo.lower(), tipo.lower())
        self.niveles.append(Nivel(tipo=t, numeral=str(numeral).strip(), literal=literal or f'{tipo} {numeral}'))

    def dudar(self, motivo: str) -> None:
        if motivo not in self.dudas:
            self.dudas.append(motivo)

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
            cuelga = tramos and tramos[-1] and (n.tipo in HIJOS_DE_ARTICULO) and (self._raiz_de_tramo(tramos) == 'art')
            if cuelga:
                tramos[-1].append(n.numeral.lower() if n.sistema == 'letra' else n.numeral)
            else:
                tramos.append([n.canonico])
        return '/'.join(('.'.join(t) for t in tramos))

    @staticmethod
    def _raiz_de_tramo(tramos: list[list[str]]) -> str:
        return tramos[-1][0].split('.', 1)[0] if tramos and tramos[-1] else ''

    @property
    def profundidad(self) -> int:
        return len(self.niveles)

    def tipos(self) -> list[str]:
        return [n.tipo for n in self.niveles]
HIJOS_DE_ARTICULO = {'ap', 'letra', 'inciso', 'num'}
ABREN_TRAMO = {'anexo', 'apend', 'tabla', 'figura', 'disp'}
SOLO_ATRIBUTO = {'lib', 'titulo', 'cap', 'sec'}
PREFIJO_LIBRO_PRIMERO = 'libro.1/'

def sin_libro_primero(ruta: str) -> str | None:
    """`libro.1/X` -> `X`. None si la ruta no empieza por `libro.1/` o no trae nada detras (`libro.1` a secas no cambia)."""
    if ruta.startswith(PREFIJO_LIBRO_PRIMERO) and len(ruta) > len(PREFIJO_LIBRO_PRIMERO):
        return ruta[len(PREFIJO_LIBRO_PRIMERO):]
    return None
