"""Juego sistematico de encabezados: ordinales, marcas y divisiones.

Nace de la reparacion del 5 de agosto de 2026, predicha en
PREDICCION_encabezados_no_citables.md. La adenda 9 exige que un error se valide
"con un juego generado sistematicamente, no con ese caso": si estas pruebas
cubrieran solo los articulos y las divisiones que fallaron, estarian ajustadas a
la Directiva 2001/83-CE y al Reglamento 2016/161, que son justo los dos
documentos que destaparon el defecto.

Por eso aqui no hay casos escogidos: hay productos cartesianos.

  C1  los VEINTITRES ordinales latinos, no los cuatro que fallaron.
  C2  la marca de consolidacion en sus CUATRO posiciones posibles.
  C3  CUATRO clases de division x DOS maquetaciones x DOS numeraciones.

Y la mitad que de verdad importa: los negativos. Una expresion que reconoce mas
encabezados tambien puede reconocer remisiones del cuerpo, y un encabezado
inventado parte un precepto en dos por la mitad, que es peor que no reconocerlo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import parsers as P                          # noqa: E402

# --------------------------------------------------------------------- C1
# Los ordinales que el legislador europeo usa de verdad. La lista se escribe
# entera, no se recorta a los que aparecen hoy en el corpus: un ordinal que
# todavia no ha aparecido aparecera en cuanto entre una consolidacion nueva.
ORDINALES = [
    "bis", "ter", "quater", "quáter", "quinquies", "sexies", "septies",
    "octies", "nonies", "decies", "undecies", "duodecies", "terdecies",
    "quaterdecies", "quindecies", "sexdecies", "septdecies", "octodecies",
    "novodecies", "vicies", "unvicies", "duovicies", "tervicies",
    "quatervicies",
]


@pytest.mark.parametrize("ordinal", ORDINALES)
def test_ordinal_latino_ue(ordinal):
    """"Articulo 107 <ordinal>" se reconoce y captura el numeral entero."""
    m = P.RE_UE["articulo"].match(f"Artículo 107 {ordinal}")
    assert m, f"no se reconoce el ordinal {ordinal!r}"
    assert m.group(1) == f"107 {ordinal}"


@pytest.mark.parametrize("ordinal", ORDINALES)
def test_ordinal_latino_ue_con_rubrica(ordinal):
    """El mismo, con rubrica pegada, que es la maquetacion de la Serie L."""
    m = P.RE_UE["articulo"].match(f"Artículo 12 {ordinal} Obligaciones")
    assert m, f"no se reconoce el ordinal {ordinal!r} con rubrica"
    assert m.group(1) == f"12 {ordinal}"
    assert m.group(2) == "Obligaciones"


@pytest.mark.parametrize("ordinal", ORDINALES)
def test_ordinal_latino_boe(ordinal):
    m = P.RE_BOE["articulo"].match(f"Artículo 5 {ordinal}. Objeto.")
    assert m, f"no se reconoce el ordinal {ordinal!r} en el BOE"
    assert m.group(1) == f"5 {ordinal}"


def test_ordinal_prefijo_no_trunca():
    """El fallo que el \\b evita: "ter" casando dentro de "terdecies".

    Sin la frontera de palabra la alternativa corta gana, deja "decies" suelto y
    el encabezado entero deja de reconocerse. Se comprueba en las tres parejas
    donde un ordinal es prefijo de otro.
    """
    for corto, largo in (("ter", "terdecies"), ("decies", "duodecies"),
                         ("vicies", "unvicies")):
        m = P.RE_UE["articulo"].match(f"Artículo 9 {largo}")
        assert m and m.group(1) == f"9 {largo}", (
            f"{largo!r} se trunca a {corto!r}")


# --------------------------------------------------------------------- C2
MARCA = "▼"   # la marca de bloque de EUR-Lex
FLECHA_A = "►"
FLECHA_C = "◄"


def _limpiar_ue(s: str) -> str:
    """Lo que analizar_eurlex hace con una linea antes de reconocerla."""
    s = s.strip()
    if P.MARCA_BLOQUE.match(s):
        return ""
    mi = P.MARCA_INICIO.match(s)
    if mi:
        s = s[mi.end():].strip()
    if FLECHA_A in s or FLECHA_C in s:
        s = P.MARCA_INLINE.sub("", s).strip()
    if P.MARCA_RESTO.search(s):
        s = P.MARCA_RESTO.sub(" ", s).strip()
        s = re.sub(r"\s{2,}", " ", s)
    return s


POSICIONES = {
    "sola":     f"{MARCA}M3",
    "al_abrir": f"{MARCA}B Artículo 20",
    "en_medio": f"Artículo 20 {FLECHA_A}C1 texto {FLECHA_C} final",
    "al_final": f"Artículo 40 {MARCA}M2",
}


@pytest.mark.parametrize("posicion", sorted(POSICIONES))
def test_marca_en_las_cuatro_posiciones(posicion):
    """Ninguna marca sobrevive a la limpieza, este donde este en la linea."""
    limpia = _limpiar_ue(POSICIONES[posicion])
    assert MARCA not in limpia and FLECHA_A not in limpia and FLECHA_C not in limpia
    if posicion == "sola":
        assert limpia == ""
    else:
        assert limpia.startswith("Artículo ")


def test_marca_al_final_deja_reconocer_el_articulo():
    """El caso del RED: "Articulo 40 [marca]M2", rubrica en la linea siguiente.

    Con la marca sin quitar, la expresion espera una rubrica en mayuscula, se
    encuentra la marca, y el articulo entero se queda sin trocear.
    """
    m = P.RE_UE["articulo"].match(_limpiar_ue(POSICIONES["al_final"]))
    assert m and m.group(1) == "40"


# --------------------------------------------------------------------- C3
# Cuatro clases x dos maquetaciones x dos numeraciones.
CLASES = {
    "capitulo": ("CAPÍTULO", P.RE_UE["capitulo"], P.RE_BOE["capitulo"]),
    "titulo":   ("TÍTULO", P.RE_UE["titulo_div"], P.RE_BOE["titulo_div"]),
    "anexo":    ("ANEXO", P.RE_UE["anexo"], P.RE_BOE["anexo"]),
    "apendice": ("APÉNDICE", None, P.RE_BOE["apendice"]),
}
NUMERACIONES = {"romana": "IV", "arabiga": "4"}
MAQUETACIONES = {"numeral_solo": "", "rubrica_pegada": " DISPOSICIONES GENERALES"}


@pytest.mark.parametrize("clase", sorted(CLASES))
@pytest.mark.parametrize("numeracion", sorted(NUMERACIONES))
@pytest.mark.parametrize("maquetacion", sorted(MAQUETACIONES))
def test_division_las_dieciseis_combinaciones(clase, numeracion, maquetacion):
    palabra, rx_ue, rx_boe = CLASES[clase]
    numeral = NUMERACIONES[numeracion]
    linea = f"{palabra} {numeral}{MAQUETACIONES[maquetacion]}"
    for rx in (rx_ue, rx_boe):
        if rx is None:
            continue
        m = rx.match(linea)
        assert m, f"no se reconoce {linea!r}"
        assert m.group(1) == numeral, f"numeral mal capturado en {linea!r}"


@pytest.mark.parametrize("clase", sorted(CLASES))
@pytest.mark.parametrize("caja", ["BIS", "bis", "Bis"])
@pytest.mark.parametrize("rubrica", ["", " DISPOSICIONES GENERALES"])
def test_una_division_con_bis_es_otra_division(clase, caja, rubrica):
    """El caso que destruyo dos divisiones de normas vigentes el 5-ago-2026.

    "CAPITULO V BIS" no es el capitulo V con una rubrica que empieza por BIS: es
    otra division. Con la regla de la rubrica pegada, leerlo mal producia la
    misma ruta que el capitulo V y la ingesta descartaba la segunda en silencio.

    Se prueba en las TRES cajas porque la caja era lo que decidia entre destruir
    el texto y solo perder la citabilidad, y eso no puede depender de como lo
    imprima el boletin.
    """
    palabra, rx_ue, rx_boe = CLASES[clase]
    linea = f"{palabra} V {caja}{rubrica}"
    for rx in (rx_ue, rx_boe):
        if rx is None:
            continue
        m = rx.match(linea)
        assert m, f"no se reconoce {linea!r}"
        assert m.group(1).split()[0] == "V"
        assert m.group(1).split()[1].lower() == "bis", (
            f"el ordinal se pierde en {linea!r}: {m.group(1)!r}")
        assert P.numeral_division(m.group(1)) == "V bis", (
            f"la ruta no normaliza la caja: {P.numeral_division(m.group(1))!r}")


def test_la_division_con_bis_no_colisiona_con_la_de_al_lado():
    """Lo que de verdad importa: dos rutas distintas, no una."""
    for palabra, rx, _ in [CLASES["capitulo"]]:
        a = rx.match(f"{palabra} V Requisitos del equipo")
        b = rx.match(f"{palabra} V BIS Redistribucion de alimentos")
        assert a and b
        assert P.numeral_division(a.group(1)) != P.numeral_division(b.group(1))


def test_anejo_es_anexo_y_la_ruta_dice_anexo():
    """Decision de ICT155 del 5-ago-2026: ANEJO se reconoce, la palabra es ANEXO.

    El RD 237/2000 titula ANEJO. Sin esto el analizador nunca abria contexto de
    anexo y sus trece apendices no eran citables.
    """
    for numeral in ("1", "IV"):
        m = P.RE_BOE["anexo"].match(f"ANEJO {numeral}")
        assert m and m.group(1) == numeral
    # Y la ruta no menciona nunca 'anejo'.
    assert "anejo" not in P.ruta_anexo("2")
    assert P.ruta_anexo("2") == "anexo.2"


# --------------------------------------------------- los negativos, que pesan igual
# Una expresion mas permisiva puede empezar a reconocer remisiones del cuerpo.
# Un encabezado inventado parte un precepto en dos por la mitad, y eso es peor
# que no reconocerlo: el texto sigue estando, pero deja de poder citarse entero.
REMISIONES = [
    "Artículo 3 del Reglamento Delegado (UE) 2022/30",
    "CAPÍTULO IV del anexo citado",
    "ANEXO II del Real Decreto 244/2016",
    "TÍTULO III de la Ley 32/2014, de Metrología",
    "APÉNDICE III del anexo XI de la Orden ICT/155/2020",
    "ANEJO 2 del real decreto citado",
]


@pytest.mark.parametrize("linea", REMISIONES)
def test_una_remision_del_cuerpo_no_es_un_encabezado(linea):
    todas = [P.RE_UE["articulo"], P.RE_UE["capitulo"], P.RE_UE["titulo_div"],
             P.RE_UE["anexo"], P.RE_BOE["capitulo"], P.RE_BOE["titulo_div"],
             P.RE_BOE["anexo"], P.RE_BOE["apendice"]]
    casan = [rx.pattern[:28] for rx in todas if rx.match(linea)]
    assert not casan, f"{linea!r} se toma por encabezado en {casan}"


def test_el_discriminante_es_la_mayuscula_no_la_longitud():
    """Lo que separa una rubrica de una remision es la mayuscula inicial.

    Se comprueba en positivo y en negativo sobre la misma linea, para que la
    prueba no pase por casualidad de longitud.
    """
    assert P.RE_UE["capitulo"].match("CAPÍTULO V Vigilancia del mercado")
    assert not P.RE_UE["capitulo"].match("CAPÍTULO V del reglamento anterior")
