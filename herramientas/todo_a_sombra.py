"""Vía de emergencia de los controles nuevos (R27, 17-oct-2026).

Si algo va mal con un control que está en `bloquea` (o en `sombra` y molesta), esta herramienta lo baja sin esperar a un
despliegue: escribe en el fichero local que `ict155.interruptores` ya respeta (`%LOCALAPPDATA%\\ict155\\cowork\\
controles_local.json`, o donde diga `ICT155_COWORK_AUDIT_DIR`) todos los controles de `cowork/controles.json` en
«sombra», o en «apagado» con `--apagar`. NO toca el fichero versionado: lo aprobado sigue siendo lo aprobado, esto es
solo la palanca de emergencia que ya preveía `interruptores.py` (el local solo puede BAJAR un modo, nunca subirlo).

Si el fichero local ya tenía un control más bajo que el objetivo (p.ej. ya en «apagado» y el objetivo es «sombra»), se
conserva: esta herramienta nunca sube nada. Un fichero local roto se trata como si no tuviera nada escrito (se
sobrescribe entero).

R27-S2h (18-oct-2026, REVISION_GPT7A hallazgos 8, 9, 10 y 13):
- (9) El límite de cada control es su entrada explícita en el local o, si no tiene, la del comodín («*»); se escribe
  el MENOR entre ese límite y el objetivo. Antes, un comodín sin entradas nombradas se perdía sin más (ninguna lo
  "heredaba") y cada control pasaba al objetivo completo: con un local `{"*":"apagado"}` y aprobados en «bloquea»,
  la vía de emergencia SUBÍA los modos a «sombra» en vez de dejarlos en «apagado». El comodín se conserva en lo
  escrito si ya era igual o más bajo que el objetivo, para que los controles futuros (los que aún no están en
  `cowork/controles.json`) sigan bajados.
- (10) La escritura es atómica: un temporal completo en la misma carpeta, sustituido con `os.replace`. Después se
  vuelve a leer con `interruptores.modo()` (salvo que `cowork/controles.json` esté roto, caso en que `modo()` ya
  falla cerrado por su cuenta) y, si algún control no quedó en el objetivo o más bajo, esta herramienta sale con
  rc≠0 diciendo cuál y por qué.
- (8) Si `ICT155_CONTROLES_FORZADOS` está definida, manda sobre lo que acaba de escribir esta herramienta (tiene más
  prioridad que el fichero local): se avisa por stderr y se sale con rc≠0 aunque la escritura haya ido bien, porque
  en producción esa variable no debe existir.
- (13) Al final se imprime, por control, el modo efectivo que queda (comprobado con `modo()`) y la orden exacta para
  deshacerlo.

R27-S2i (18-oct-2026, REVISION_WF1 sección S2h, hallazgos S2h-1 a S2h-5):
- (S2h-1) `nuevo_contenido` ya no se limita a los controles de `cowork/controles.json`: parte de TODAS las claves
  del local (también el comodín «*» y los controles que no están en la lista, por ejemplo uno de un despliegue
  futuro) y deja cada una en el MENOR entre lo que tenía y el objetivo. El comodín se escribe siempre con ese
  mismo mínimo (antes, si estaba por encima del objetivo, se perdía sin más y los controles no listados quedaban
  sin bajar: SUBÍAN en el siguiente despliegue). El límite «nombre propio o, si no, el comodín» para los controles
  SÍ listados sigue igual que antes.
- (S2h-2) `_escribir_atomico` reintenta `os.replace` unas pocas veces (5 × 0,2 s) si otro programa tiene abierto el
  fichero (`PermissionError`, frecuente en Windows con Cowork, un editor o un antivirus) y siempre borra el
  temporal al salir, también si `write_text` falla a medias. Si sigue sin poder escribir, `main` no muere con un
  traceback: avisa en español llano que NO se ha bajado nada y por qué, con un código de salida propio (5).
- (S2h-3) `ICT155_CONTROLES_FORZADOS` se comprueba ANTES de escribir nada (antes solo fallaba más tarde, al
  comprobar con `modo()`, con un traceback técnico y sin el aviso de la variable). Si está mal escrita, avisa en
  español llano y sale con rc≠0 (6) sin escribir ni morir.
- (S2h-4) Si ya había un local antes de esta orden, se copia a `controles_local.json.antes_<AAAAMMDD-HHMMSS>` en la
  misma carpeta ANTES de sustituirlo. El mensaje final dice cómo volver a como estaba copiando esa copia encima
  del local (o, si no había fichero, que basta con borrarlo) y avisa de que borrar el fichero sin restaurar la
  copia vuelve TODOS los controles a lo aprobado, incluidos los que ya estaban bajados antes de esta orden.
- (S2h-5) Un argumento no reconocido ya no imprime el docstring de desarrollador entero: un mensaje corto en
  español llano («Argumento no reconocido… NO se ha bajado nada. Uso: …») y rc=2 (se mantiene ese código, no el 64
  que proponía la revisión, porque `pruebas/test_interruptores_r27_2026_10_17.py` —que este mismo encargo exige
  mantener en verde— ya fija rc=2 para este caso; ver el informe).

R27-S2g (18-oct-2026, hallazgo 7): si `cowork/controles.json` está tan roto que ni se puede leer su lista de controles
(`ict155.interruptores.ErrorDeControles`: un BOM, un JSON inválido, un modo desconocido...), esta herramienta NO puede
morir con un traceback: es la vía de emergencia, y justo entonces es cuando más hace falta. Se usa en su lugar la lista
fija de los controles de hoy (`interruptores.CONTROLES_CONOCIDOS`) y se avisa de que hay que restaurar el fichero
versionado desde git cuanto antes.

R27-S7c (18-oct-2026, AG5-N2): en ese caso, `interruptores.modo()` sigue fallando CERRADO con `cowork/controles.json`
roto (es lo correcto: la palanca NUNCA debe rescatar un despliegue roto). Esta herramienta escribe igualmente el local
con la lista fija, pero ya NO sale con el mismo rc=0 que cuando todo va bien: sale con un código distinto de 0, y el
AVISO, por stderr, dice que lo escrito no tendrá efecto hasta restaurar `cowork/controles.json` (con la orden exacta) y
que, después de restaurarlo, los controles quedan bajados por lo que escribió esta herramienta hasta que se borre.

Uso (desde la raíz del repositorio, con el intérprete de producción):
  C:\\Python314\\python.exe -X utf8 herramientas\\todo_a_sombra.py             # todos los controles a «sombra»
  C:\\Python314\\python.exe -X utf8 herramientas\\todo_a_sombra.py --apagar    # todos los controles a «apagado»
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ict155 import interruptores  # noqa: E402

ORDEN = {m: i for i, m in enumerate(interruptores.MODOS)}
# ACTIVO es el nivel bloqueante del almacén; la palanca debe poder comprobarlo
# y avisar si un forzado impide bajarlo, sin un KeyError.
ORDEN["activo"] = ORDEN["bloquea"]


def nuevo_contenido(aprobados: dict[str, str], actual: dict[str, str], objetivo: str) -> dict[str, str]:
    """El modo de cada control aprobado: el MENOR entre su límite actual y `objetivo` (nunca sube, solo baja o deja
    igual). El límite de un control es su entrada explícita en `actual`, o si no tiene, la del comodín `"*"`
    (hallazgo 9).

    R27-S2i (hallazgo S2h-1): además, NUNCA se pierde una bajada que ya hubiera en `actual`. Se parte de TODAS sus
    claves (también controles que todavía no están en `aprobados`, de un despliegue futuro) y cada una se deja en
    el MENOR entre lo que tenía y `objetivo`. El comodín se escribe siempre con ese mismo mínimo, esté o no por
    encima del objetivo (antes, si estaba por encima, se perdía del todo y los controles no listados quedaban sin
    ningún límite: SUBÍAN al desplegarse). Esto no cambia el límite «nombre propio o, si no, comodín» de los
    controles que SÍ están en `aprobados`, que sigue como antes (hallazgo 9)."""
    comodin = actual.get("*")
    nuevo: dict[str, str] = {}
    # Hallazgo S2h-1: todas las claves del local, también las que no están en `aprobados`, bajadas al objetivo.
    for nombre, valor in actual.items():
        if nombre == "*" or valor not in ORDEN:
            continue
        nuevo[nombre] = valor if ORDEN[valor] < ORDEN[objetivo] else objetivo
    # Hallazgo 9 (como ahora): el límite de un control aprobado es su propia entrada o, si no tiene, el comodín.
    for c in aprobados:
        limite = actual[c] if c in actual and actual[c] in ORDEN else comodin
        nuevo[c] = limite if limite is not None and ORDEN[limite] < ORDEN[objetivo] else objetivo
    # Hallazgo S2h-1: el comodín se conserva SIEMPRE, topado al objetivo, para bajar también lo que no se conoce.
    if comodin is not None and comodin in ORDEN:
        nuevo["*"] = comodin if ORDEN[comodin] < ORDEN[objetivo] else objetivo
    return nuevo


def _escribir_atomico(ruta: Path, contenido: dict) -> None:
    """Hallazgo 10: un temporal completo en la misma carpeta (mismo sistema de ficheros que `ruta`, para que
    `os.replace` sea atómico) y lo sustituye de un golpe; nunca deja `ruta` a medio escribir.

    R27-S2i (hallazgo S2h-2): en Windows, `os.replace` falla con `PermissionError` si en ese instante otro proceso
    tiene abierto `ruta` (una lectura de Cowork, un editor o un antivirus). Unos pocos reintentos cortos (5 × 0,2 s)
    bastan para el caso normal. El temporal se borra siempre al salir, con éxito o sin él (si `os.replace` tuvo
    éxito ya no existe en esa ruta, y borrarlo entonces es un no-op). Si sigue sin poder sustituirlo, se relanza la
    excepción para que `main` avise en español llano en vez de morir con un traceback."""
    tmp = ruta.with_name(f"{ruta.name}.tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
        for intento in range(5):
            try:
                os.replace(tmp, ruta)
                return
            except PermissionError:
                if intento == 4:
                    raise
                time.sleep(0.2)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv not in ([], ["--apagar"]):
        # R27-S2i (hallazgo S2h-5): mensaje corto en español llano, sin el docstring de desarrollador. Se mantiene
        # rc=2 (no el 64 que proponía la revisión): pruebas/test_interruptores_r27_2026_10_17.py, que este mismo
        # encargo exige mantener en verde, ya fija ese código de salida para este caso (ver el informe).
        print(f"Argumento no reconocido: {' '.join(argv)!r}. NO se ha bajado nada. Uso: TODO_A_SOMBRA.cmd (todo a "
              "sombra) o TODO_A_SOMBRA.cmd --apagar (todo apagado).")
        return 2
    objetivo = "apagado" if argv == ["--apagar"] else "sombra"

    # R27-S2i (hallazgo S2h-3): se comprueba ANTES de escribir nada (antes solo fallaba más tarde, al comprobar con
    # `modo()`, con un traceback técnico y sin el aviso de la variable).
    try:
        interruptores._forzados()
    except interruptores.ErrorDeControles as e:
        print(f"AVISO: {interruptores.VARIABLE_FORZADOS} está mal escrita ({e}): esa variable manda sobre todo y en "
              "producción NO debe existir; corrígela o bórrala. NO se ha bajado nada.", file=sys.stderr)
        return 6

    roto = False
    try:
        aprobados = interruptores._aprobados()
    except interruptores.ErrorDeControles as e:
        roto = True
        print(f"AVISO: {e}: se usa la lista fija de controles de hoy ({', '.join(interruptores.CONTROLES_CONOCIDOS)}) "
              "en vez de la de cowork/controles.json.", file=sys.stderr)
        # R27-S7c (AG5-N2): `modo()` sigue leyendo el `cowork/controles.json` roto y sigue fallando cerrado
        # (ErrorDeControles) en los tres controles: lo que se escribe aquí no tiene NINGÚN efecto hasta que se
        # restaure. Por eso la orden exacta para restaurarlo y el aviso de que, después, lo escrito aquí se queda
        # bajando los controles hasta que se borre.
        print("Restaura `cowork/controles.json` con `git checkout -- cowork/controles.json` cuanto antes: hasta "
              "entonces esta orden NO SIRVE (interruptores.modo() sigue fallando cerrado). Después de restaurarlo, "
              f"los controles que acaba de escribir esta orden en {interruptores.ruta_local()} se quedan bajados "
              "hasta que borres ese fichero.", file=sys.stderr)
        aprobados = dict.fromkeys(interruptores.CONTROLES_CONOCIDOS, objetivo)
    actual, avisos = interruptores._local()
    for a in avisos:
        print(a)
    nuevo = nuevo_contenido(aprobados, actual, objetivo)
    ruta = interruptores.ruta_local()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # R27-S2i (hallazgo S2h-4): si ya había un local, una copia ANTES de sustituirlo, para poder volver a como
    # estaba exactamente (y no solo «borrar el fichero», que también deshace lo que ya estuviera bajado antes).
    copia_antes: Path | None = None
    if ruta.exists():
        sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        copia_antes = ruta.with_name(f"{ruta.name}.antes_{sello}")
        shutil.copy2(ruta, copia_antes)

    try:
        _escribir_atomico(ruta, {"controles": nuevo})
    except OSError:
        # R27-S2i (hallazgo S2h-2): os.replace no pudo sustituir ni tras los reintentos (otro programa tiene
        # abierto el fichero): nada técnico para la persona responsable, y NO se ha bajado nada (el local anterior queda intacto).
        print(f"NO se ha bajado nada: no se pudo escribir {ruta} (otro programa lo tiene abierto); cierra Cowork o "
              "el editor y vuelve a lanzarlo.", file=sys.stderr)
        return 5

    print(f"escrito {ruta}:")
    fallos: list[tuple[str, str]] = []
    for c in sorted(aprobados):
        conservado = " (conservado: ya estaba más bajo que el objetivo)" if nuevo[c] != objetivo else ""
        if roto:
            # `modo()` ya falla cerrado con `cowork/controles.json` roto (aviso aparte, más arriba): no hay nada
            # real que comprobar todavía, lo escrito no tiene efecto hasta que se restaure.
            print(f"  {c}: {nuevo[c]}{conservado} (sin comprobar: cowork/controles.json sigue roto)")
            continue
        # Hallazgo 10: vuelve a leer, por la vía normal (`modo()`), lo que de verdad ha quedado tras la escritura.
        efectivo = interruptores.modo(c)
        if ORDEN[efectivo] > ORDEN[objetivo]:
            fallos.append((c, efectivo))
            print(f"  {c}: {efectivo}{conservado} (¡SIGUE POR ENCIMA de {objetivo}!)")
        else:
            print(f"  {c}: {efectivo}{conservado}")
    if copia_antes is not None:
        print(f"\nPara volver a como estaba ANTES de esta orden: copia {copia_antes} sobre {ruta}. También puedes "
              f"editar {ruta} y quitar (o subir) solo la entrada del control afectado (o la del comodín \"*\"). "
              f"Borrar {ruta} sin restaurar antes esa copia vuelve TODOS los controles a lo aprobado, incluidos los "
              "que ya estaban bajados antes de esta orden.")
    else:
        print(f"\nPara deshacer esta vía de emergencia: borra {ruta} (eso vuelve TODOS los controles a lo "
              f"aprobado), o edita ese fichero y quita (o sube) la entrada del control afectado (o la del comodín "
              "\"*\").")

    rc = 2 if roto else 0

    if fallos:
        detalle = "; ".join(f"{c} quedó en {m}, por encima de {objetivo}" for c, m in fallos)
        print(f"ERROR: tras volver a leer, no todos los controles quedaron en {objetivo} o más bajo: {detalle}.",
              file=sys.stderr)
        rc = 3

    forzado = os.environ.get(interruptores.VARIABLE_FORZADOS)
    if forzado:
        print(f"AVISO: {interruptores.VARIABLE_FORZADOS} está definida ({forzado!r}): esa variable manda sobre lo "
              "que acaba de escribir esta orden (tiene más prioridad que el fichero local que escribe la palanca); "
              "en producción esa variable NO debe existir.", file=sys.stderr)
        if rc == 0:
            rc = 4

    return rc


if __name__ == "__main__":
    sys.exit(main())
