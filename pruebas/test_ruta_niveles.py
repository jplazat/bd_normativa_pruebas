"""Cada nivel citado ocupa su posicion en la ruta. Nunca se colapsa uno.

Regla general, enunciable sin mirar ningun caso concreto:

    articulo -> apartado -> letra -> inciso

Se valida con un juego de formas GENERADO SISTEMATICAMENTE, con las variantes de
redaccion castellana (nivel a nivel: "articulo 3, apartado 1, letra b)") y
europea (compacta: "articulo 3.1, letra b)"), y con el orden invertido que usa
el castellano juridico ("el apartado 1 del articulo 3").

Se valida asi y no sobre N5 a proposito. N5 pertenece a la reserva, y arreglar
mirando la reserva la gasta. La regla es general, el juego de pruebas es
generado, y N5 no interviene.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155.consulta import ruta_de_cita   # noqa: E402

ARTS = ("3", "12", "8")
APS = ("1", "4")
LETRAS = ("b", "d")


def _formas(art, ap=None, letra=None):
    """Las maneras en que un jurista escribe la misma cita."""
    if ap is None and letra is None:
        return [f"artículo {art}", f"el artículo {art}"]
    if letra is None:
        return [f"artículo {art}, apartado {ap}",          # nivel a nivel
                f"artículo {art}.{ap}",                    # compacta
                f"el apartado {ap} del artículo {art}"]    # invertida
    if ap is None:
        return [f"artículo {art}, letra {letra})"]
    return [f"artículo {art}, apartado {ap}, letra {letra})",
            f"artículo {art}.{ap}, letra {letra})",
            f"la letra {letra}) del apartado {ap} del artículo {art}"]


def _casos():
    out = []
    for art in ARTS:
        out += [(f, f"art.{art}") for f in _formas(art)]
        for ap in APS:
            out += [(f, f"art.{art}.{ap}") for f in _formas(art, ap)]
            for letra in LETRAS:
                out += [(f, f"art.{art}.{ap}.{letra}")
                        for f in _formas(art, ap, letra)]
    return out


CASOS = _casos()


@pytest.mark.parametrize("cita,esperada", CASOS,
                         ids=[c.replace(" ", "_") for c, _ in CASOS])
def test_cada_nivel_ocupa_su_posicion(cita, esperada):
    assert ruta_de_cita(cita) == esperada


def test_el_juego_cubre_las_cuatro_profundidades():
    """Que el generador no se quede corto sin que nadie lo note."""
    profundidades = {e.count(".") for _, e in CASOS}
    assert profundidades == {1, 2, 3}, profundidades
    assert len(CASOS) >= 60, f"solo {len(CASOS)} formas generadas"


def test_ningun_nivel_se_pierde_al_anadir_letra():
    """El caso que fallaba: la letra no puede comerse el apartado."""
    assert ruta_de_cita("artículo 3, apartado 1, letra b)") == "art.3.1.b"
    assert ruta_de_cita("artículo 3, apartado 1") == "art.3.1"
    assert ruta_de_cita("artículo 3") == "art.3"


def test_el_apartado_de_un_anexo_no_se_confunde_con_el_de_un_articulo():
    """Un anexo lleva sus apartados por barra, no por punto."""
    assert ruta_de_cita("anexo XI, apartado 3") == "anexo.XI/ap.3"
    assert ruta_de_cita("artículo 3, apartado 3") == "art.3.3"
