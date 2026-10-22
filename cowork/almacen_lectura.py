"""Lectura de A01–A06 desde una entrega sellada; apagado por defecto.

``leer`` es la única entrada de lectura. Las rutas explícitas ajenas a los
cinco ficheros del producto conservan su significado (pruebas/importaciones).
APAGADO no abre configuración, manifiesto ni vistas y conserva el lector y las
cachés anteriores. ACTIVO (también ``bloquea``) verifica cada lectura, sin caché
de bytes ni dependencia del fichero antiguo. SOMBRA usa el original y registra
huellas/tamaños, nunca contenido. No importa publicadores ni esquemas de reglas.
"""
from __future__ import annotations

import atexit
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid

from cowork import controles_lectura as interruptores

CONTROL = "almacen_unico"
REPO = Path(__file__).resolve().parents[1]
RUTA_CONFIG = REPO / "cowork" / "almacen_unico.json"
VISTAS = tuple("cowork/" + n + ".json" for n in (
    "temas_obligatorios", "reglas_ambito", "preceptos_relacionados",
    "sucesores_revisados", "limites_conocidos"))
_RUTAS = {REPO / v: v for v in VISTAS}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CONTADORES = Counter()
_CERROJO = threading.RLock()
_REGISTROS = {}
_CACHE_CONTROLES = {}

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _InformacionBasica(ctypes.Structure):
        _fields_ = [(n, ctypes.c_longlong) for n in
                    ("creacion", "acceso", "escritura", "cambio")]
        _fields_ += [("atributos", wintypes.DWORD)]

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _abrir_atributos = _kernel.CreateFileW
    _abrir_atributos.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE)
    _abrir_atributos.restype = wintypes.HANDLE
    _informacion = _kernel.GetFileInformationByHandleEx
    _informacion.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _informacion.restype = wintypes.BOOL
    _cerrar_handle = _kernel.CloseHandle
    _cerrar_handle.argtypes = (wintypes.HANDLE,)
    _cerrar_handle.restype = wintypes.BOOL


def _identidad_control(ruta: Path):
    """Sólo metadatos: identidad, tamaño y fechas, sin leer contenido.

    Windows expone la creación como st_ctime: se consulta además ChangeTime
    (FileBasicInfo), que cambia aunque se restaure mtime tras una escritura.
    El handle sólo pide FILE_READ_ATTRIBUTES y comparte lectura/escritura/borrado.
    """
    try:
        estado = ruta.stat()
    except FileNotFoundError:
        return None
    cambio = estado.st_ctime_ns
    if os.name == "nt":
        handle = _abrir_atributos(str(ruta), 0x80, 0x7, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            datos = _InformacionBasica()
            if not _informacion(handle, 0, ctypes.byref(datos), ctypes.sizeof(datos)):
                raise ctypes.WinError(ctypes.get_last_error())
            cambio = datos.cambio
        finally:
            _cerrar_handle(handle)
    return (estado.st_dev, estado.st_ino, estado.st_size, estado.st_mtime_ns, cambio)


def _controles_vigentes(tipo: str, ruta: Path):
    """Una lectura de contenido por identidad estable; nunca cachea errores.

    Se verifica la identidad también después de leer para no guardar una foto
    con metadatos de otra escritura. Si no se pueden consultar los metadatos,
    se invalida la foto y se usa el lector compartido sin caché.
    """
    leer = (lambda: interruptores._aprobados(ruta)) if tipo == "aprobados" else (
        lambda: interruptores._local()[0])
    with _CERROJO:
        for _ in range(3):
            try:
                antes = _identidad_control(ruta)
            except OSError:
                _CACHE_CONTROLES.pop(tipo, None)
                return leer()
            anterior = _CACHE_CONTROLES.get(tipo)
            if anterior is not None and anterior[:2] == (ruta, antes):
                return anterior[2]
            _CACHE_CONTROLES.pop(tipo, None)
            dato = leer()
            try:
                despues = _identidad_control(ruta)
            except OSError:
                return dato
            if antes == despues:
                _CACHE_CONTROLES[tipo] = (ruta, despues, dato)
                return dato
        raise interruptores.ErrorDeControles(
            f"{ruta}: controles cambiando durante la lectura; vuelve a consultar")


def _normalizar(ruta) -> str:
    try:
        return os.path.normcase(str(Path(ruta).resolve()))
    except (OSError, RuntimeError, ValueError) as e:
        raise _fallo(f"no se puede normalizar la ruta {ruta} ({e})") from e


def _vista_para(ruta) -> str | None:
    """Identidad física antes de admitir entradas locales, también enlaces duros."""
    normal = _normalizar(ruta)
    for canonica, vista in _RUTAS.items():
        if normal == _normalizar(canonica):
            return vista
    # resolve cubre enlaces simbólicos/junctions; samefile cubre enlaces duros.
    # Sólo se consulta para rutas ajenas: la ruta canónica no necesita stat.
    for canonica, vista in _RUTAS.items():
        try:
            if Path(ruta).samefile(canonica):
                return vista
        except FileNotFoundError:
            continue
        except OSError as e:
            raise _fallo(f"no se puede comprobar la identidad de {ruta} ({e})") from e
    return None


def _modo_efectivo() -> str:
    """Mismas reglas que la palanca; fotos invalidadas por metadatos actuales."""
    aprobados = _controles_vigentes("aprobados", Path(interruptores.RUTA_CONTROLES).resolve())
    if CONTROL not in aprobados:
        raise interruptores.ErrorDeControles(f"control desconocido: {CONTROL!r}")
    locales = _controles_vigentes("local", interruptores.ruta_local().resolve())
    m = aprobados[CONTROL]
    candidato = locales.get(CONTROL, locales.get("*"))
    if candidato is not None and interruptores._ORDEN[candidato] < interruptores._ORDEN[m]:
        m = candidato
    forzados = interruptores._forzados()
    return forzados.get(CONTROL, forzados.get("*", m))


def estadisticas() -> dict:
    """Contadores de consultas y lecturas, sin datos ni texto normativo."""
    with _CERROJO:
        return dict(_CONTADORES)


def _registrar(tipo: str, modo: str, vista: str | None):
    contexto = os.environ.get("ICT155_ALMACEN_CONTEXTO", "producto")
    with _CERROJO:
        _CONTADORES[f"{contexto}:{tipo}:{modo}"] += 1
        destino = os.environ.get("ICT155_ALMACEN_AUDIT_DIR")
        if not destino:
            return
        clave = (os.getpid(), destino)
        try:
            if clave not in _REGISTROS:
                carpeta = Path(destino)
                carpeta.mkdir(parents=True, exist_ok=True)
                ruta = carpeta / f"almacen-{os.getpid()}-{uuid.uuid4().hex}.jsonl"
                _REGISTROS[clave] = [ruta, 0]
            registro = _REGISTROS[clave]
            registro[1] += 1
            fila = dict(evento=tipo, modo=modo, vista=vista, contexto=contexto,
                        prueba=os.environ.get("PYTEST_CURRENT_TEST", ""),
                        secuencia=registro[1], pid=os.getpid())
            with registro[0].open("a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        except OSError as e:
            # No permitir que un lector que captura OSError oculte la pérdida
            # del testigo de modo solicitado por la batería.
            raise _fallo(f"no se puede registrar el modo efectivo en {destino} ({e})") from e


def _cerrar_registros():
    with _CERROJO:
        for (pid, _), (ruta, total) in _REGISTROS.items():
            if pid == os.getpid():
                with ruta.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(dict(evento="fin", pid=pid, total=total,
                                            contadores=estadisticas())) + "\n")


atexit.register(_cerrar_registros)


class ErrorDeAlmacen(interruptores.ErrorDeControles):
    """Fallo de entrega: reutiliza el cierre de los cinco puntos de S2b."""


def _fallo(detalle: str) -> ErrorDeAlmacen:
    return ErrorDeAlmacen(
        f"almacen_unico: {detalle}. No se ha podido comprobar; no se usa el "
        "fichero antiguo. Restaura la entrega/configuración de cowork/almacen_unico.json "
        "o baja almacen_unico a apagado en controles_local.json")


def modo_para(ruta) -> str:
    """Modo para una ruta del producto; rutas de entrada explícitas son locales."""
    vista = _vista_para(ruta)
    if vista is None:
        return "apagado"
    m = _modo_efectivo()
    _registrar("consulta", m, vista)
    return m


def _objeto(bruto: bytes, descripcion: str) -> dict:
    def pares(items):
        salida = {}
        for clave, valor in items:
            if clave in salida:
                raise ValueError(f"clave duplicada: {clave}")
            salida[clave] = valor
        return salida
    try:
        dato = json.loads(bruto.decode("utf-8-sig"), object_pairs_hook=pares,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        if not isinstance(dato, dict):
            raise ValueError("la raíz no es un objeto")
        return dato
    except (UnicodeError, ValueError) as e:
        raise _fallo(f"{descripcion} no es JSON válido ({e})") from e


def _bytes(ruta: Path, descripcion: str) -> bytes:
    try:
        return ruta.read_bytes()
    except OSError as e:
        raise _fallo(f"{descripcion} falta o no es legible: {ruta} ({e})") from e


def _publicada(vista: str) -> bytes:
    conf = _objeto(_bytes(RUTA_CONFIG, "configuración"), "configuración")
    huella = conf.get("huella_entrega")
    if not isinstance(huella, str) or not _SHA.fullmatch(huella):
        raise _fallo("configuración: huella_entrega debe ser un sha256 hexadecimal")
    # Sólo un nombre de huella, nunca una ruta arbitraria o absoluta.
    carpeta = REPO / "datos" / "almacen" / huella
    try:
        # No se resuelve el ancla datos/almacen: un enlace de ese directorio
        # tampoco puede redirigir la entrega fuera del repositorio.
        carpeta.resolve().relative_to(REPO.resolve() / "datos" / "almacen")
        (carpeta / "MANIFIESTO.json").resolve().relative_to(carpeta.resolve())
    except (OSError, ValueError) as e:
        raise _fallo(f"entrega fuera de datos/almacen: {carpeta}") from e
    manifiesto = _objeto(_bytes(carpeta / "MANIFIESTO.json", "manifiesto/entrega configurada"), "manifiesto")
    if manifiesto.get("huella_entrega") != huella:
        raise _fallo(f"manifiesto: otra huella de entrega (esperada {huella})")
    cuerpo = {k: v for k, v in manifiesto.items() if k != "huella_entrega"}
    try:
        canonico = json.dumps(cuerpo, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError) as e:
        raise _fallo(f"manifiesto no canónico ({e})") from e
    if hashlib.sha256(canonico).hexdigest() != huella:
        raise _fallo("manifiesto: sha256 del contenido no coincide con la huella de entrega")
    ficheros = manifiesto.get("ficheros")
    entrada = ficheros.get(vista) if isinstance(ficheros, dict) else None
    if not isinstance(entrada, dict) or not isinstance(entrada.get("sha256"), str) or not _SHA.fullmatch(entrada["sha256"]):
        raise _fallo(f"manifiesto sin sha256 válido para la vista {vista}")
    ruta = carpeta / vista
    try:
        ruta.resolve().relative_to(carpeta.resolve())
    except (OSError, ValueError) as e:
        raise _fallo(f"vista fuera de la entrega: {vista}") from e
    bruto = _bytes(ruta, f"vista {vista}")
    if hashlib.sha256(bruto).hexdigest() != entrada["sha256"]:
        raise _fallo(f"vista {vista}: sha256 no coincide con el manifiesto")
    if type(entrada.get("bytes")) is not int or len(bruto) != entrada["bytes"]:
        raise _fallo(f"vista {vista}: tamaño no coincide con el manifiesto")
    return bruto


def leer(ruta, *, encoding: str | None = None, modo: str | None = None):
    """Bytes, o texto con el mismo encoding/newlines que el lector anterior.

    ``modo`` permite reutilizar la consulta ya hecha para gestionar una caché.
    Es interno; los consumidores sólo lo pasan desde ``modo_para``.
    """
    ruta = Path(ruta)
    vista = _vista_para(ruta)
    m = modo_para(ruta)
    if modo is not None and modo != m:
        raise _fallo(f"modo precalculado {modo} distinto del efectivo {m}")
    _registrar("lectura" if vista else "local", m, vista)
    if m == "apagado":
        return ruta.read_bytes() if encoding is None else ruta.read_text(encoding=encoding)
    if vista is None or m not in ("sombra", "activo", "bloquea"):
        raise _fallo(f"ruta o modo no admitido: {ruta}, {m}")
    if m == "sombra":
        original = ruta.read_bytes()
        try:
            nuevo = _publicada(vista)
        except ErrorDeAlmacen as e:
            interruptores.anotar_sombra(CONTROL, {"vista": vista, "error": str(e)})
        else:
            if original != nuevo:
                interruptores.anotar_sombra(CONTROL, {
                    "vista": vista, "diferencia_bytes": True,
                    "sha256_original": hashlib.sha256(original).hexdigest(),
                    "sha256_publicada": hashlib.sha256(nuevo).hexdigest(),
                    "bytes_original": len(original), "bytes_publicada": len(nuevo)})
        bruto = original
    else:
        bruto = _publicada(vista)
    if encoding is None:
        return bruto
    with io.TextIOWrapper(io.BytesIO(bruto), encoding=encoding) as f:
        return f.read()
