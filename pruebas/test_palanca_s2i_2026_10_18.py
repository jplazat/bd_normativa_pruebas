# -*- coding: utf-8 -*-
"""R27-S2i (18-oct-2026): REVISION_WF1_S10e_S11f_S2h.md, sección S2h, hallazgos S2h-1 a S2h-5 sobre la palanca de
emergencia (`herramientas/todo_a_sombra.py`).

- S2h-1 (confirmado): `nuevo_contenido` perdía el comodín del local cuando estaba por ENCIMA del objetivo, y
  también cualquier entrada de un control que no estuviera en `cowork/controles.json` (uno de un despliegue
  futuro). Un control no listado SUBÍA. Ahora se parte de TODAS las claves del local y cada una (también el
  comodín) se deja en el menor entre lo que tenía y el objetivo.
- S2h-2 (menor): `os.replace` podía fallar con `PermissionError` si otro programa tenía abierto el fichero local:
  traceback técnico y temporal huérfano. Ahora reintenta unas pocas veces y, si sigue fallando, avisa en español
  llano y sale con rc≠0 sin morir, sin dejar temporales.
- S2h-3 (menor): con `ICT155_CONTROLES_FORZADOS` mal escrita, la palanca escribía y luego moría con un traceback en
  la comprobación. Ahora se comprueba ANTES de escribir nada.
- S2h-4 (menor): la orden «borra <ruta>» para deshacer devolvía TODOS los controles a lo aprobado, incluidos los
  que ya estaban bajados antes de la palanca, sin guardar copia. Ahora se copia el local anterior antes de
  sustituirlo.
- S2h-5 (menor): un argumento desconocido imprimía el docstring de desarrollador entero con rc=2 (el mismo código
  que «controles.json roto»), sin decir que no se había bajado nada. Ahora un mensaje corto en español llano. Se
  mantiene rc=2 (no el 64 que proponía la revisión): ver el informe, `pruebas/test_interruptores_r27_2026_10_17.py`
  (que este mismo encargo exige mantener en verde) ya fija ese código de salida para este caso.

Regla de oro: la palanca NUNCA sube un modo.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

from ict155 import interruptores

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
HERRAMIENTA = RAIZ / "herramientas" / "todo_a_sombra.py"


def _controles(ruta: Path, **modos: str) -> Path:
    ruta.write_text(json.dumps({"controles": modos}, ensure_ascii=False), encoding="utf-8")
    return ruta


@pytest.fixture
def tas():
    """Carga fresca de `todo_a_sombra.py`, como en `test_palanca_r27_2026_10_18.py`, para parchear su
    `interruptores` sin afectar a otros ficheros de prueba que importan el módulo real."""
    spec = importlib.util.spec_from_file_location("todo_a_sombra_s2i", HERRAMIENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """Registro (local + sombra.log) en una carpeta de la propia prueba, NUNCA en %LOCALAPPDATA% real; y sin
    forzados heredados de fuera, salvo que la prueba los ponga ella misma."""
    monkeypatch.setenv("ICT155_COWORK_AUDIT_DIR", str(tmp_path / "registro"))
    # COMPATIBILIDAD_HISTORICA: se prueba deliberadamente la ausencia de forzados.
    monkeypatch.setenv("ICT155_ALMACEN_CONTEXTO", "compatibilidad_historica")
    monkeypatch.delenv(interruptores.VARIABLE_FORZADOS, raising=False)
    return tmp_path


def _ruta_local() -> Path:
    return interruptores.ruta_local()


# ============================================================================================= S2h-1: ninguna bajada se pierde


def test_comodin_por_encima_del_objetivo_se_conserva_topado(tas):
    """El caso exacto de S2h-1: un comodín «bloquea» con objetivo «sombra» ya NO se pierde (antes desaparecía del
    local entero): se escribe topado al objetivo, para que un control futuro siga bajado."""
    nuevo = tas.nuevo_contenido({"cifras": "bloquea"}, {"*": "bloquea"}, "sombra")
    assert nuevo["cifras"] == "sombra"
    assert nuevo["*"] == "sombra"                                          # antes: "*" desaparecía


def test_control_no_listado_en_el_local_se_baja_en_vez_de_perderse(tas):
    """Una entrada nombrada de un control que no está en `aprobados` (uno de un despliegue futuro) ya no se pierde:
    se deja en el menor entre lo que tenía y el objetivo."""
    nuevo = tas.nuevo_contenido({"cifras": "bloquea"}, {"nuevo8": "apagado"}, "sombra")
    assert nuevo["nuevo8"] == "apagado"                                    # se conserva, más bajo que el objetivo
    assert nuevo["cifras"] == "sombra"


def test_control_no_listado_con_entrada_mas_alta_que_el_objetivo_se_topa(tas):
    nuevo = tas.nuevo_contenido({"cifras": "bloquea"}, {"nuevo8": "bloquea"}, "sombra")
    assert nuevo["nuevo8"] == "sombra"                                     # topado al objetivo, no se queda en bloquea


def test_e2e_control_futuro_no_sube_al_llegar_al_despliegue_siguiente(tmp_path, monkeypatch, tas):
    """De punta a punta, el escenario R1 de la revisión WF1: local `{"*": "sombra"}`, se lanza `--apagar`. Cuando
    llega un control nuevo (`nuevo8`) en un despliegue posterior, NO debe aparecer en `bloquea`: el comodín capado
    por la palanca tiene que seguir bajándolo."""
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    ruta_local = _ruta_local()
    ruta_local.parent.mkdir(parents=True, exist_ok=True)
    ruta_local.write_text(json.dumps({"controles": {"*": "sombra"}}), encoding="utf-8")

    rc = tas.main(["--apagar"])
    assert rc == 0

    futuro = _controles(tmp_path / "controles_con_nuevo8.json", cifras="bloquea", nuevo8="bloquea")
    assert interruptores.modo("nuevo8", futuro) == "apagado"               # nunca "bloquea": la palanca lo cubrió


# ============================================================================================= S2h-2: os.replace con reintentos, sin traceback


def test_os_replace_reintenta_y_acaba_bien_si_el_bloqueo_es_pasajero(tmp_path, monkeypatch, tas):
    ruta = tmp_path / "controles_local.json"
    ruta.write_text(json.dumps({"controles": {"cifras": "bloquea"}}), encoding="utf-8")

    original_replace = os.replace
    fallos_restantes = [2]

    def replace_que_falla_dos_veces(origen, destino):
        if fallos_restantes[0] > 0:
            fallos_restantes[0] -= 1
            raise PermissionError("Acceso denegado (simulado)")
        return original_replace(origen, destino)

    monkeypatch.setattr(tas.os, "replace", replace_que_falla_dos_veces)
    monkeypatch.setattr(tas.time, "sleep", lambda s: None)                 # la prueba no espera de verdad

    tas._escribir_atomico(ruta, {"controles": {"cifras": "sombra"}})

    assert json.loads(ruta.read_text(encoding="utf-8"))["controles"] == {"cifras": "sombra"}
    assert list(tmp_path.glob("*.tmp*")) == []                             # sin temporales huérfanos


def test_os_replace_si_sigue_bloqueado_no_deja_temporal_y_relanza(tmp_path, monkeypatch, tas):
    ruta = tmp_path / "controles_local.json"
    ruta.write_text(json.dumps({"controles": {"cifras": "bloquea"}}), encoding="utf-8")

    monkeypatch.setattr(tas.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError("Acceso denegado")))
    monkeypatch.setattr(tas.time, "sleep", lambda s: None)

    with pytest.raises(PermissionError):
        tas._escribir_atomico(ruta, {"controles": {"cifras": "sombra"}})

    assert list(tmp_path.glob("*.tmp*")) == []                             # el temporal se borra aunque falle
    assert json.loads(ruta.read_text(encoding="utf-8"))["controles"] == {"cifras": "bloquea"}   # intacto


def test_main_si_no_se_puede_escribir_avisa_en_llano_sin_traceback_y_rc_propio(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    monkeypatch.setattr(tas, "_escribir_atomico",
                         lambda *a, **k: (_ for _ in ()).throw(PermissionError("Acceso denegado (simulado)")))

    rc = tas.main([])
    salida, err = capsys.readouterr()

    assert rc not in (0, 2, 3, 4)                                         # un rc propio, no confundible con los de antes
    assert rc != 0
    assert "NO se ha bajado nada" in err
    assert "Traceback" not in salida and "Traceback" not in err           # nada técnico para la persona responsable
    assert "PermissionError" not in salida and "PermissionError" not in err


# ============================================================================================= S2h-3: ICT155_CONTROLES_FORZADOS mal escrita, comprobada ANTES de escribir


@pytest.mark.parametrize("valor", ["apagado", " ", "[]", "{\"cifras\": \"modo_raro\"}"])
def test_forzados_mal_escrita_avisa_antes_de_escribir_y_no_escribe_nada(tmp_path, monkeypatch, tas, capsys, valor):
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, valor)

    rc = tas.main([])
    salida, err = capsys.readouterr()

    assert rc != 0
    assert interruptores.VARIABLE_FORZADOS in err
    assert "Traceback" not in salida and "Traceback" not in err
    assert not _ruta_local().exists()                                    # NO se ha bajado nada: ni se escribe


def test_forzados_validos_siguen_escribiendo_como_antes(tmp_path, monkeypatch, tas):
    """Caso de control: un forzado bien formado no entra por el camino nuevo del hallazgo S2h-3 (ese sigue
    comprobándose solo al final, como ya hacía S2h)."""
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({"*": "apagado"}))

    rc = tas.main([])

    assert rc != 0                                                        # S2h: el forzado manda, rc≠0
    assert _ruta_local().exists()                                         # pero esta vez SÍ se escribió


# ============================================================================================= S2h-4: copia antes de sustituir, orden de deshacer exacta


def test_hay_local_previo_se_copia_antes_de_sustituir_y_el_mensaje_lo_dice(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea", cubre_estricto="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    ruta_local = _ruta_local()
    ruta_local.parent.mkdir(parents=True, exist_ok=True)
    contenido_previo = {"controles": {"cifras": "apagado"}}
    ruta_local.write_text(json.dumps(contenido_previo), encoding="utf-8")

    rc = tas.main([])
    salida, _ = capsys.readouterr()
    assert rc == 0

    copias = list(ruta_local.parent.glob("controles_local.json.antes_*"))
    assert len(copias) == 1
    assert json.loads(copias[0].read_text(encoding="utf-8")) == contenido_previo   # copia fiel del ANTERIOR
    assert str(copias[0]) in salida
    assert "TODOS" in salida                                               # avisa de que borrar sube TODO


def test_sin_local_previo_el_mensaje_dice_borrar_sin_mencionar_copia(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)

    rc = tas.main([])
    salida, _ = capsys.readouterr()
    assert rc == 0

    assert list(_ruta_local().parent.glob("controles_local.json.antes_*")) == []
    assert "borra" in salida.lower()


def test_restaurar_la_copia_devuelve_exactamente_lo_que_habia_antes(tmp_path, monkeypatch, tas):
    """El escenario del hallazgo: la persona responsable ya tenía `cifras` bajado a mano antes de lanzar la palanca. Con la copia,
    puede volver EXACTAMENTE a como estaba (incluido lo que ya tenía bajado), no a lo aprobado."""
    aprobados_ruta = _controles(tmp_path / "controles.json", cifras="apagado", cubre_estricto="bloquea")
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", aprobados_ruta)
    ruta_local = _ruta_local()
    ruta_local.parent.mkdir(parents=True, exist_ok=True)
    contenido_previo = {"controles": {"cubre_estricto": "apagado"}}        # ya bajado a mano, a propósito
    ruta_local.write_text(json.dumps(contenido_previo), encoding="utf-8")

    rc = tas.main([])
    assert rc == 0
    assert interruptores.modo("cubre_estricto", aprobados_ruta) == "apagado"   # conservado por la palanca

    copia = next(ruta_local.parent.glob("controles_local.json.antes_*"))
    copia.replace(ruta_local)                                              # "restaurar la copia"
    assert json.loads(ruta_local.read_text(encoding="utf-8")) == contenido_previo
    assert interruptores.modo("cubre_estricto", aprobados_ruta) == "apagado"    # sigue como antes de la palanca,
    assert interruptores.modo("cifras", aprobados_ruta) == "apagado"            # no como "borra" (que subiría todo)


# ============================================================================================= S2h-5: argumento desconocido, mensaje corto


def test_argumento_desconocido_mensaje_corto_sin_docstring(tmp_path, monkeypatch, tas, capsys):
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", _controles(tmp_path / "controles.json", cifras="bloquea"))

    rc = tas.main(["--apagado"])
    salida, _ = capsys.readouterr()

    assert rc == 2                                                        # test_interruptores_r27_2026_10_17.py lo exige
    assert "Uso" in salida
    assert "NO se ha bajado nada" in salida
    assert "Argumento no reconocido" in salida
    assert "REVISION_GPT7A" not in salida and "REVISION_WF1" not in salida   # ya no es el docstring entero
    assert len(salida.splitlines()) <= 3                                  # corto, no 45 líneas
    assert not _ruta_local().exists()                                     # no se ha escrito nada


def test_argumento_desconocido_no_escribe_nada_aunque_hubiera_local_previo(tmp_path, monkeypatch, tas):
    monkeypatch.setattr(tas.interruptores, "RUTA_CONTROLES", _controles(tmp_path / "controles.json", cifras="bloquea"))
    ruta_local = _ruta_local()
    ruta_local.parent.mkdir(parents=True, exist_ok=True)
    ruta_local.write_text(json.dumps({"controles": {"cifras": "apagado"}}), encoding="utf-8")

    rc = tas.main(["-apagar"])

    assert rc == 2
    assert json.loads(ruta_local.read_text(encoding="utf-8"))["controles"] == {"cifras": "apagado"}  # sin tocar


# ============================================================================================= regla de oro: nunca sube, con claves desconocidas y comodín incluidos


@pytest.mark.parametrize("aprobado, local, objetivo", [
    ("bloquea", {"*": "bloquea"}, "sombra"),
    ("bloquea", {"*": "bloquea", "nuevo8": "bloquea"}, "apagado"),
    ("sombra", {"nuevo8": "bloquea"}, "apagado"),
    ("bloquea", {"cifras": "apagado", "*": "bloquea"}, "sombra"),
])
def test_nunca_sube_ni_para_lo_no_listado_ni_para_el_comodin(tas, aprobado, local, objetivo):
    ORDEN = tas.ORDEN
    nuevo = tas.nuevo_contenido({"cifras": aprobado}, local, objetivo)
    for nombre, valor in nuevo.items():
        limite_previo = local.get(nombre, local.get("*"))
        if limite_previo is not None:
            assert ORDEN[valor] <= ORDEN[limite_previo]                   # nunca por encima de lo que ya tenía
        assert ORDEN[valor] <= ORDEN[objetivo]                            # ni por encima del objetivo
