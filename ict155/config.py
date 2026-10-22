"""Rutas y garantias de solo lectura.

Regla que no se negocia: la biblioteca ICT155.COM se lee y no se escribe nunca.
Toda apertura de un fichero de la biblioteca pasa por abrir_biblioteca(), que
rechaza cualquier modo que no sea de lectura.
"""
from pathlib import Path
import io
import os
BIBLIOTECA = Path(os.environ.get('ICT155_BIBLIOTECA', 'D:\\OneDrive\\ICT155.COM'))
REPO = Path(__file__).resolve().parent.parent
DATOS_REPO = REPO / 'datos'
DIR_DATOS = Path(os.environ.get('ICT155_DATOS', Path(os.environ.get('LOCALAPPDATA', str(REPO / '_datos'))) / 'ict155' / 'bd'))
BD = DIR_DATOS / 'conocimiento.sqlite'
PDFTOTEXT = os.environ.get('ICT155_PDFTOTEXT', 'pdftotext')
ARGS_PDFTOTEXT = [PDFTOTEXT, '-q', '-enc', 'UTF-8']
MOTOR = os.environ.get('ICT155_MOTOR', 'xpdf')
MOTOR_XPDF = 'xpdf-4.00 -enc UTF-8'
MOTOR_PYMUPDF = 'pymupdf'
MOTOR_EXTRACCION = MOTOR_PYMUPDF if MOTOR == 'pymupdf' else MOTOR_XPDF
LAYOUT_GUIAS_POR_DEFECTO = 'paginas'
_LAYOUT_APAGADO = ('no', '0', 'off', 'false', 'apagado')

def valor_de_layout_guias(valor):
    """Valor efectivo de la bandera: "paginas", "todo" o "" (apagada)."""
    v = (valor or '').strip().lower()
    if not v:
        return LAYOUT_GUIAS_POR_DEFECTO
    if v in _LAYOUT_APAGADO:
        return ''
    if v in ('paginas', 'todo'):
        return v
    raise ValueError(f"ICT155_LAYOUT_GUIAS={valor!r}: valores validos 'paginas' (por defecto), 'todo' y 'no' (apagada)")
LAYOUT_GUIAS = valor_de_layout_guias(os.environ.get('ICT155_LAYOUT_GUIAS'))

class EscrituraEnBibliotecaError(RuntimeError):
    """Se ha intentado escribir en la biblioteca. Nunca debe ocurrir."""

def es_de_biblioteca(ruta) -> bool:
    try:
        Path(ruta).resolve().relative_to(BIBLIOTECA.resolve())
        return True
    except (ValueError, OSError):
        return False

def abrir_biblioteca(ruta, modo='r', **kw):
    """Unica via autorizada para abrir un fichero de la biblioteca."""
    if any((c in modo for c in 'wax+')):
        raise EscrituraEnBibliotecaError(f'modo {modo!r} prohibido sobre la biblioteca: {ruta}')
    if 'b' not in modo:
        kw.setdefault('encoding', 'utf-8')
    return io.open(ruta, modo, **kw)

def ruta_biblioteca(relativa) -> Path:
    """Resuelve una ruta relativa a la biblioteca, impidiendo salir de ella."""
    p = (BIBLIOTECA / str(relativa).replace('\\', '/')).resolve()
    if not es_de_biblioteca(p):
        raise EscrituraEnBibliotecaError(f'ruta fuera de la biblioteca: {relativa}')
    return p

def relativa(p) -> str:
    return Path(p).resolve().relative_to(BIBLIOTECA.resolve()).as_posix()
