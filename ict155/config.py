"""Rutas y garantias de solo lectura.

Regla que no se negocia: la biblioteca ICT155.COM se lee y no se escribe nunca.
Toda apertura de un fichero de la biblioteca pasa por abrir_biblioteca(), que
rechaza cualquier modo que no sea de lectura.
"""
from pathlib import Path
import io
import os

# La biblioteca. Solo lectura, siempre.
BIBLIOTECA = Path(os.environ.get("ICT155_BIBLIOTECA", r"D:\OneDrive\ICT155.COM"))

# El repositorio (codigo y pruebas). Vive fuera de OneDrive.
REPO = Path(__file__).resolve().parent.parent

# Artefactos derivados que SI viven en el repositorio: transcripciones manuales
# verificadas. No son fuente (la fuente es la ficha de trabajo de la biblioteca,
# y de ahi se lee el cuerpo en cada reconstruccion); son el mapa que dice que
# apartado de la ficha sostiene que clausula de la norma. Versionarlos es lo
# correcto: se revisan en diff como cualquier otro codigo.
DATOS_REPO = REPO / "datos"

# La base de datos es artefacto derivado: fuera del repositorio y fuera de OneDrive,
# para que ni se sincronice ni se versione. Se reconstruye con `ict155 reconstruir`.
DIR_DATOS = Path(os.environ.get(
    "ICT155_DATOS",
    Path(os.environ.get("LOCALAPPDATA", str(REPO / "_datos"))) / "ict155" / "bd",
))
BD = DIR_DATOS / "conocimiento.sqlite"

# Motor de extraccion. Xpdf 4.00 en este equipo: su codificacion por defecto es
# Latin-1 y borra en silencio el chino y el cirilico. -enc UTF-8 no es opcional.
PDFTOTEXT = os.environ.get("ICT155_PDFTOTEXT", "pdftotext")
# OJO, Y NO ES UN OLVIDO: aqui NO va `-layout`, y la regla de la casa que se le
# da a los agentes SI lo exige. Los dos lados de esa contradiccion son reales y
# el 7 de agosto de 2026 nadie sabia que existia.
#
# `-layout` conserva la disposicion de la pagina; sin el, pdftotext devuelve el
# flujo interno del PDF y una pagina puede salir como UNA SOLA LINEA. La pagina
# 12 de la EN 12830:2018 sale asi, con `4.3` y `4.3.1` incrustados a mitad de
# linea, y por eso el analizador de guias no los ve: busca encabezados al
# principio de linea y no hay principio de linea. Medido por K-02: de las 633
# clausulas perdidas, 404 tienen un rotulo que la expresion aceptaria tal cual
# y lo que falla es la estructura de linea del texto de ingesta.
#
# NO se cambia a la ligera. Con la expresion actual, pasar a `-layout`
# recuperaria 329 clausulas, PERDERIA 569 rutas hoy citables y cambiaria el
# texto de 812 preceptos. Es un cambio con encargo, prediccion y reserva nueva.
# Ver HALLAZGO_la_base_no_usa_layout.md.
ARGS_PDFTOTEXT = [PDFTOTEXT, "-q", "-enc", "UTF-8"]
# Se probo PyMuPDF como motor: conserva los guiones lexicos partidos que Xpdf
# pierde ("UNE-EN" sale "UNEEN"), pero su estructura de lineas rompe los
# analizadores, afinados sobre la de Xpdf. Medido: puerta 25 -> 20,
# clasificacion 59 -> 57 y un error de ingesta. Se queda Xpdf.
MOTOR = os.environ.get("ICT155_MOTOR", "xpdf")
# Lo que se graba en `documento.motor_extraccion`. MOTOR_EXTRACCION es el motor
# PEDIDO; el que de verdad extrajo cada documento lo lleva `TextoPdf.motor`,
# porque con ICT155_MOTOR=pymupdf un fallo de PyMuPDF cae a Xpdf (S3).
MOTOR_XPDF = "xpdf-4.00 -enc UTF-8"
MOTOR_PYMUPDF = "pymupdf"
MOTOR_EXTRACCION = (MOTOR_PYMUPDF if MOTOR == "pymupdf" else MOTOR_XPDF)
# `-layout` solo en las guias, ENCENDIDO por defecto desde el 4 de octubre de
# 2026 (decision de la persona responsable tras la medicion de la ultima tanda: 162 rutas nuevas,
# 0 perdidas). Ver docs/DISENO_layout_guias.md.
#   sin variable, o vacia   "paginas"
#   "paginas"               -layout solo en las paginas que sin el salen colapsadas
#   "no" ("0", "off")       como antes de la campana: sin -layout
#   "todo"                  -layout en todas las paginas de las guias (el
#                           escenario de K-02; sirve para medir, no para usar)
# Un valor que no sea ninguno de estos es un error: una bandera mal escrita no
# puede cambiar en silencio el texto de 896 preceptos.
LAYOUT_GUIAS_POR_DEFECTO = "paginas"
_LAYOUT_APAGADO = ("no", "0", "off", "false", "apagado")


def valor_de_layout_guias(valor):
    """Valor efectivo de la bandera: "paginas", "todo" o "" (apagada)."""
    v = (valor or "").strip().lower()
    if not v:
        return LAYOUT_GUIAS_POR_DEFECTO
    if v in _LAYOUT_APAGADO:
        return ""
    if v in ("paginas", "todo"):
        return v
    raise ValueError(
        f"ICT155_LAYOUT_GUIAS={valor!r}: valores validos 'paginas' (por "
        f"defecto), 'todo' y 'no' (apagada)")


LAYOUT_GUIAS = valor_de_layout_guias(os.environ.get("ICT155_LAYOUT_GUIAS"))


class EscrituraEnBibliotecaError(RuntimeError):
    """Se ha intentado escribir en la biblioteca. Nunca debe ocurrir."""


def es_de_biblioteca(ruta) -> bool:
    try:
        Path(ruta).resolve().relative_to(BIBLIOTECA.resolve())
        return True
    except (ValueError, OSError):
        return False


def abrir_biblioteca(ruta, modo="r", **kw):
    """Unica via autorizada para abrir un fichero de la biblioteca."""
    if any(c in modo for c in "wax+"):
        raise EscrituraEnBibliotecaError(
            f"modo {modo!r} prohibido sobre la biblioteca: {ruta}")
    if "b" not in modo:
        kw.setdefault("encoding", "utf-8")
    return io.open(ruta, modo, **kw)


def ruta_biblioteca(relativa) -> Path:
    """Resuelve una ruta relativa a la biblioteca, impidiendo salir de ella."""
    p = (BIBLIOTECA / str(relativa).replace("\\", "/")).resolve()
    if not es_de_biblioteca(p):
        raise EscrituraEnBibliotecaError(f"ruta fuera de la biblioteca: {relativa}")
    return p


def relativa(p) -> str:
    return Path(p).resolve().relative_to(BIBLIOTECA.resolve()).as_posix()
