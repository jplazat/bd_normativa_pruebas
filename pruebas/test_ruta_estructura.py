"""La ruta es una estructura y la cadena es su proyeccion.

Lo que estas pruebas fijan no es como se escribe una ruta, sino que **la cadena
no es el dato**. Si mañana se decide que `art.3.1.b` se escribe de otra manera,
estas pruebas cambian y el corpus no se reprocesa.

Y fijan lo contrario de lo habitual: que las ambiguedades siguen ABIERTAS. Un
sistema que las cierra en silencio es peor que uno que las declara, porque el
que las declara se puede corregir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import ruta as R                       # noqa: E402
from ict155.consulta import estructura_de_cita     # noqa: E402


def tipos_y_numerales(cita: str):
    e = estructura_de_cita(cita)
    return [(n.tipo, n.numeral) for n in e.niveles]


# ------------------------------------------------ la estructura es el dato

def test_la_cadena_sale_de_la_estructura():
    e = estructura_de_cita("artículo 3, apartado 1, letra b)")
    assert [n.tipo for n in e.niveles] == ["art", "ap", "letra"]
    assert e.cadena == "art.3.1.b"


def test_cambiar_la_proyeccion_no_toca_la_estructura():
    """Se construye la ruta a mano y se comprueba que proyectar no la altera."""
    r = R.RutaEstructurada()
    r.anadir("anexo", "XI")
    r.anadir("apendice", "II")
    r.anadir("tabla", "2")
    antes = [(n.tipo, n.numeral, n.sistema) for n in r.niveles]
    assert r.cadena == "anexo.XI/apend.II/tabla.2"
    assert [(n.tipo, n.numeral, n.sistema) for n in r.niveles] == antes


def test_cada_nivel_lleva_su_tipo_y_no_se_deduce_de_la_posicion():
    """`art.3.2` no dice si el 2 es apartado o numero. El nivel si lo dice."""
    e = estructura_de_cita("artículo 3, apartado 2")
    assert e.niveles[-1].tipo == "ap"


# ------------------------------- el sistema de numeracion no se normaliza

def test_romano_y_arabigo_no_son_lo_mismo():
    """`anexo.II` y `anexo.2` se distinguen: una obra puede tener dos series."""
    assert tipos_y_numerales("anexo II") == [("anexo", "II")]
    assert tipos_y_numerales("anexo 2") == [("anexo", "2")]
    assert estructura_de_cita("anexo II").niveles[0].sistema == "romano"
    assert estructura_de_cita("anexo 2").niveles[0].sistema == "arabigo"


def test_el_numeral_decimal_es_un_nivel_no_varios():
    """«punto 3.2.1» es UN nivel, y se guarda como tal."""
    e = estructura_de_cita("punto 3.2.1 del anexo II")
    assert [n.tipo for n in e.niveles] == ["anexo", "ap"]
    assert e.niveles[-1].numeral == "3.2.1"
    assert e.niveles[-1].sistema == "decimal"


# --------------------------------- las ambiguedades quedan declaradas

@pytest.mark.parametrize("cita,fragmento", [
    ("artículo 3.1", "numeral decimal"),
    ("artículo 4, letra a)", "elidido"),
    ("punto 3.2.1 del anexo II", "puntos"),
    ("letras d), e) y f) del artículo 3", "letras"),
])
def test_lo_que_no_esta_decidido_se_declara(cita, fragmento):
    e = estructura_de_cita(cita)
    assert e.dudas, f"{cita!r} no declara ninguna duda"
    assert any(fragmento in d for d in e.dudas), e.dudas


def test_una_cita_sin_ambiguedad_no_inventa_dudas():
    """El control: declarar dudas en todo seria tan inutil como no declarar."""
    assert not estructura_de_cita("anexo XI, apartado 3").dudas
    assert not estructura_de_cita("artículo 3, apartado 1, letra b)").dudas


# ------------------------- el mismo nivel con dos nombres es el mismo nivel

def test_los_alias_de_tipo_llevan_al_mismo_nivel():
    """«punto» es «apartado»; «guion» es «inciso». Mismo nivel fisico."""
    assert R.ALIAS_TIPO["punto"] == R.ALIAS_TIPO["apartado"]
    assert R.ALIAS_TIPO["guion"] == R.ALIAS_TIPO["inciso"]
    assert tipos_y_numerales("punto 4")[0][0] == tipos_y_numerales("apartado 4")[0][0]


# ------------------- los ancestros estructurales no son tramos de la ruta

def test_libro_titulo_capitulo_y_seccion_son_atributos_no_ruta():
    """La ruta canonica es la mas corta que identifica: `art.345`.

    Los articulos se numeran de corrido en toda la obra y ninguna cita real
    menciona la cadena entera. Exigirla obligaria al validador a inferir en vez
    de resolver.
    """
    assert R.SOLO_ATRIBUTO == {"lib", "titulo", "cap", "sec"}
    assert not (R.SOLO_ATRIBUTO & R.ABREN_TRAMO)


def test_dentro_de_un_anexo_la_cadena_si_es_ruta():
    """Ahi la numeracion reinicia, asi que el anexo forma parte de la ruta."""
    assert estructura_de_cita("anexo XI, apartado 3").cadena == "anexo.XI/ap.3"
    assert "anexo" in R.ABREN_TRAMO
