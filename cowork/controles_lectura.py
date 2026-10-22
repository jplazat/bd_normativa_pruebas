"""Interruptores de los controles nuevos de R27 (17-oct-2026).

Cada control nuevo tiene tres modos:
- «apagado»: no hace nada; la salida es byte a byte la de antes del control.
- «sombra»: calcula, lo anota en sombra.log y, si tiene salida para Responsable, la da como «PARA MIRAR»; NO cambia ningún
  veredicto, ni la línea de estado, ni el sello.
- «bloquea»: cambia el veredicto, con su motivo.

De dónde sale el modo, de más a menos fuerte:
1. ICT155_CONTROLES_FORZADOS (solo pruebas y Puerta 0): JSON {"control": "modo"} o {"*": "modo"}. Manda sobre todo.
2. El fichero local %LOCALAPPDATA%\\ict155\\cowork\\controles_local.json: solo puede BAJAR un modo (bloquea → sombra →
   apagado), nunca subirlo. Si está roto, se ignora y queda un AVISO visible en `avisos()`.
3. cowork/controles.json, versionado: los modos aprobados. Se suben solo con un despliegue y el OK de Responsable. Si falta o
   está roto, falla CERRADO (ErrorDeControles): un despliegue roto no puede pasar por bueno.

Un nombre de control que no está en cowork/controles.json es un error (ErrorDeControles), no un «apagado»: así una
errata en el código no apaga un control en silencio.

EXCEPCIÓN explícita a la regla de oro (R27-S2c, 17-oct-2026, hallazgos 3 y 6): la regla de oro («apagado = byte a byte como
antes») protege el VEREDICTO que da un control, no la validación de que los DATOS que ese control usa están bien escritos. La
validación de FORMATO de un campo nuevo introducido por R27 (por ejemplo `acepta_hoja` en `cowork/temas_obligatorios.json`, para
`cubre_estricto`, o los campos nuevos de una revisión en el registro de brechas, para `brechas_r27`) no depende del modo del
control que luego usa ese campo: un dato mal escrito falla con un error claro en los tres modos, apagado incluido, porque no
debe quedar latente —sin que nadie lo note— hasta que el control suba a «bloquea». Que el control esté apagado no es licencia
para que la configuración o el registro estén rotos. Ver `ict155/completitud.cargar` y `ict155/brechas.leer_registro`.
"""
from __future__ import annotations
import datetime
import json
import os
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
MODOS = ('apagado', 'sombra', 'bloquea')
_ORDEN = {m: i for i, m in enumerate(MODOS)}
_ORDEN['activo'] = _ORDEN['bloquea']

def _modo_valido(nombre, valor):
    return isinstance(valor, str) and (valor in MODOS or (nombre == 'almacen_unico' and valor == 'activo'))
RUTA_CONTROLES = REPO / 'cowork' / 'controles.json'
VARIABLE_FORZADOS = 'ICT155_CONTROLES_FORZADOS'
CONTROLES_CONOCIDOS = ('cifras', 'cubre_estricto', 'relacionados_cierra', 'negacion_base', 'brechas_r27', 'ambito', 'temas_r27', 'almacen_unico', 'entrada_hechos')

class ErrorDeControles(RuntimeError):
    pass

def _dir_registro() -> Path:
    return Path(os.environ.get('ICT155_COWORK_AUDIT_DIR') or Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'ict155' / 'cowork')

def ruta_local() -> Path:
    return _dir_registro() / 'controles_local.json'

def ruta_sombra() -> Path:
    return _dir_registro() / 'sombra.log'

def _aprobados(ruta=None) -> dict[str, str]:
    ruta = Path(ruta) if ruta else RUTA_CONTROLES
    try:
        datos = json.loads(ruta.read_bytes().decode('utf-8-sig'))
        controles = datos['controles']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ErrorDeControles(f'{ruta} falta o está roto ({e}): los controles fallan cerrados') from e
    if not isinstance(controles, dict) or any((not _modo_valido(n, m) for n, m in controles.items())):
        raise ErrorDeControles(f'{ruta}: modo desconocido; valen {MODOS}')
    return dict(controles)

def _decodificar_local(datos: bytes) -> str:
    """UTF-8 (con o sin marca BOM) o, si lleva la marca de UTF-16 (lo que escribe PowerShell 5.1 con `>` o
    `Out-File` sin `-Encoding`), UTF-16 (R27-S2g, hallazgo 9)."""
    if datos[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return datos.decode('utf-16')
    return datos.decode('utf-8-sig')

def _modo_local(nombre: str, valor, avisos: list[str]) -> str | None:
    """`valor` como modo de `nombre`, o `None` y un aviso si no se entiende: una errata en UNA entrada (un modo que
    no es de los válidos) no tira el fichero local entero, solo esa entrada (R27-S2g, hallazgo 9)."""
    if _modo_valido(nombre, valor):
        return valor
    avisos.append(f'AVISO: {ruta_local()}: {nombre!r}: {valor!r} no es un modo válido {MODOS}; se ignora esa entrada')
    return None

def _local() -> tuple[dict[str, str], list[str]]:
    """Los modos que pide `controles_local.json` (`modo()` decide si bajan: el local nunca sube nada) y los avisos
    de lo que no se ha entendido. R27-S2g (hallazgo 9): acepta BOM y UTF-16 con BOM, ignora las claves que empiezan
    por «_» (la propia `_nota` del formato de `cowork/controles.json`, si alguien copia su forma) y, si una entrada
    no se entiende, solo esa se ignora (con un aviso): el resto del fichero sigue mandando. `"*"` vale como nombre de
    control (igual que en `ICT155_CONTROLES_FORZADOS`, pero aquí también solo para bajar: lo aplica `modo()`)."""
    ruta = ruta_local()
    if not ruta.exists():
        return ({}, [])
    try:
        datos = json.loads(_decodificar_local(ruta.read_bytes()))
    except (OSError, ValueError) as e:
        return ({}, [f'AVISO: {ruta} está roto ({e}) y se ignora; mandan los modos aprobados'])
    bruto = datos.get('controles', datos) if isinstance(datos, dict) else datos
    if not isinstance(bruto, dict):
        return ({}, [f'AVISO: {ruta} está roto (no es un objeto de controles) y se ignora; mandan los modos aprobados'])
    avisos: list[str] = []
    controles: dict[str, str] = {}
    for nombre, valor in bruto.items():
        if not isinstance(nombre, str) or nombre.startswith('_'):
            continue
        m = _modo_local(nombre, valor, avisos)
        if m is not None:
            controles[nombre] = m
    return (controles, avisos)

def _forzados() -> dict[str, str]:
    valor = os.environ.get(VARIABLE_FORZADOS)
    if not valor:
        return {}
    try:
        datos = json.loads(valor)
    except ValueError as e:
        raise ErrorDeControles(f'{VARIABLE_FORZADOS} no es JSON: {e}') from e
    if not isinstance(datos, dict) or any((not _modo_valido(n, m) for n, m in datos.items())):
        raise ErrorDeControles(f'{VARIABLE_FORZADOS}: modo desconocido; valen {MODOS}')
    return datos

def conservar_almacen_forzado(valor: str) -> str:
    """Cambiar otros controles conserva el modo explícito del almacén.

    Mantiene los errores de JSON y permite ensayar el almacén expresamente.
    """
    try:
        anterior = json.loads(os.environ.get(VARIABLE_FORZADOS, '{}'))
        nuevos = json.loads(valor)
    except (ValueError, TypeError):
        return valor
    if isinstance(anterior, dict) and isinstance(nuevos, dict) and ('almacen_unico' in anterior) and ('almacen_unico' not in nuevos):
        return json.dumps({**nuevos, 'almacen_unico': anterior['almacen_unico']})
    return valor

def modo(nombre: str, ruta=None) -> str:
    aprobados = _aprobados(ruta)
    if nombre not in aprobados:
        raise ErrorDeControles(f'control desconocido: {nombre!r} (no está en cowork/controles.json)')
    forzados = _forzados()
    if nombre in forzados:
        return forzados[nombre]
    if '*' in forzados:
        return forzados['*']
    m = aprobados[nombre]
    local, _ = _local()
    candidato = local[nombre] if nombre in local else local.get('*')
    if candidato is not None and _ORDEN[candidato] < _ORDEN[m]:
        m = candidato
    return m

def avisos() -> list[str]:
    return _local()[1]
_SEPARADORES_DE_LINEA = {'\u2028': '\\u2028', '\u2029': '\\u2029', '\x85': '\\u0085'}

def anotar_sombra(nombre: str, detalle: dict) -> None:
    """Una línea JSON por disparo en sombra. Nunca rompe la llamada: si no se puede escribir, se pierde la anotación.

    R27-S2g (18-oct-2026, hallazgo 12): `json.dumps(..., ensure_ascii=False)` no escapa U+2028, U+2029 ni U+0085 (no
    son `\\n` para Python, pero sí lo son para `str.splitlines()`, que es como los leen `herramientas/parte.py` y
    `herramientas/precision_sombra.py`): una frase de la prosa que los lleve partía el registro en dos renglones y
    rompía esa lectura. Se escapan ellos tres, a mano, después de serializar: todo lo demás (tildes, eñes) sigue
    legible tal cual, como antes."""
    try:
        ruta = ruta_sombra()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        linea = {'hora': datetime.datetime.now().isoformat(timespec='seconds'), 'control': nombre, **detalle}
        texto = json.dumps(linea, ensure_ascii=False)
        for feo, escapado in _SEPARADORES_DE_LINEA.items():
            texto = texto.replace(feo, escapado)
        with open(ruta, 'a', encoding='utf-8') as f:
            f.write(texto + '\n')
    except OSError:
        pass
