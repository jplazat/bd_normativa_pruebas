"""Public CI documentation."""
from __future__ import annotations
import argparse
import csv
import datetime
import io
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from ict155 import brechas, consulta, db
AMBITOS = ('publico',)
NOTA_LICENCIA = 'norma con licencia: se cita el apartado'
SIN_CAPA = brechas._SIN_CAPA

def _nombre_capa(capa: str | None) -> str:
    """Public CI documentation."""
    c = _limpio(capa) or brechas._SIN_CAPA
    return brechas._NOMBRE_CAPA.get(c, c if c == brechas._SIN_CAPA else c.replace('_', ' ').capitalize())
ESTADOS_CON_SUBCARPETA = ('abierta', 'reformulada', 'nueva')
_INVALIDOS = re.compile('[\\x00-\\x1f\\\\/:*?"<>|]')
_RE_FECHA = re.compile('^\\d{4}-\\d{2}-\\d{2}$')
_LARGO_MAXIMO = 60
_RESERVADOS = frozenset({'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{d}' for d in '123456789'} | {f'LPT{d}' for d in '123456789'})

def _es_reservado(nombre: str) -> bool:
    """Public CI documentation."""
    return nombre.partition('.')[0].upper() in _RESERVADOS
CABECERA_CLIENTE = ['carencia', 'requisito (norma y apartado)', 'documento aportado', 'veredicto (cerrada / abierta / pendiente de un tercero)', 'qué falta (norma y apartado)', 'fecha', 'revisión (1/2)']
CABECERA_INTERNA = ['carencia', 'minutos', 'revisor', 'comprobado con']

def _limpio(s) -> str:
    return ' '.join(str(s or '').split())

def _celda(s) -> str:
    """Public CI documentation."""
    return _limpio(s).replace('|', '\\|')
_CONTROL = re.compile('[\\x00-\\x1f]')

def _sin_control(s) -> str:
    """Public CI documentation."""
    return _CONTROL.sub('', str(s or ''))

def nombre_carpeta(bid: str, titulo: str | None, usados: set[str]) -> str:
    """Public CI documentation."""
    base = bid.strip()
    titulo_limpio = _limpio(titulo)
    bruto = f'{base} - {titulo_limpio}' if titulo_limpio else base
    bruto = unicodedata.normalize('NFC', bruto)
    bruto = _limpio(_INVALIDOS.sub('', bruto))
    nombre = bruto[:_LARGO_MAXIMO].rstrip('. ')
    if not nombre:
        nombre = _limpio(_INVALIDOS.sub('', base))[:_LARGO_MAXIMO].rstrip('. ') or 'brecha'
    primero, punto, resto = nombre.partition('.')
    if _es_reservado(nombre):
        nombre = f'{primero}_{punto}{resto}'
        if len(nombre) > _LARGO_MAXIMO:
            nombre = nombre[:_LARGO_MAXIMO].rstrip('. ')
    original, n = (nombre, 2)
    while nombre.lower() in usados:
        sufijo = f' ({n})'
        nombre = original[:_LARGO_MAXIMO - len(sufijo)].rstrip('. ') + sufijo
        n += 1
    usados.add(nombre.lower())
    return nombre

@dataclass
class Requisito:
    identificador: str
    referencia: str
    literal: str | None = None
    nota: str | None = None
    papel: str | None = None

class CitaNoResuelta(RuntimeError):
    """Public CI documentation."""

def requisito_normativo(con, cita: dict) -> Requisito:
    """Public CI documentation."""
    ident = cita['identificador'].strip()
    papel = cita.get('papel') if cita.get('papel') in brechas.PAPEL_ETIQUETA else None
    referencia = brechas.referencia_legible_fase2(con, ident, AMBITOS)
    r = consulta.resolver(con, ident, AMBITOS)
    if r.estado == consulta.ENCONTRADO and r.regimen == 'publico' and r.texto_literal:
        return Requisito(ident, referencia, literal=_limpio(r.texto_literal), papel=papel)
    if r.estado in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO, consulta.LOCALIZADO_SIN_TEXTO, consulta.DERECHOS_RESTRINGIDOS):
        nota = NOTA_LICENCIA if r.regimen and r.regimen != 'publico' else 'sin literal disponible'
        return Requisito(ident, referencia, nota=nota, papel=papel)
    raise CitaNoResuelta(f'cita sin resolver en la base: {ident}')

def leeme_md(b: dict, requisitos: list[Requisito], *, campos_efectivos: list[tuple[str, str]] | None=None) -> str:
    bid, titulo = (_limpio(b['id']), _limpio(b.get('titulo')))
    L = [f'# Carencia {bid}' + (f': {titulo}' if titulo else ''), '']
    fecha_estado = brechas._fecha_legible(b['fecha_estado']) if b.get('fecha_estado') else None
    L.append(f"Estado: **{b['estado']}**" + (f' (desde {fecha_estado})' if fecha_estado else '') + f" · Capa: {_nombre_capa(b.get('capa'))}")
    L.append('')
    if campos_efectivos is None:
        descripcion = _limpio(b.get('descripcion'))
        if descripcion:
            L += [descripcion, '']
        aportar = _limpio(b.get('evidencia_requerida')) or '(sin especificar: pide los detalles a Responsable antes de reunir documentación)'
    else:
        for etiqueta, texto in campos_efectivos:
            if etiqueta in ('Antecedente', 'Qué falta', 'Qué faltaba', 'Cómo se cerró'):
                L += [f'Antecedente: {texto}' if etiqueta == 'Antecedente' else texto, '']
        campos = dict(campos_efectivos)
        aportar = campos.get('Qué tiene que aportar para cerrarla', campos.get('Documento que la cierra', '—'))
    L += ['## Qué hay que aportar', '', aportar, '']
    L += ['## Requisito normativo', '']
    if not requisitos:
        L += ['Esta carencia no tiene ninguna cita normativa registrada en el registro de seguimiento.', '']
    else:
        for req in requisitos:
            etiqueta = brechas.PAPEL_ETIQUETA.get(req.papel, 'Requisito')
            cab = f'- **{etiqueta}** — {_limpio(req.referencia)}'
            if req.literal:
                L += [cab + ':', '', f'  > {req.literal}', '']
            else:
                L += [cab + (f' ({req.nota}).' if req.nota else '.'), '']
    L += ['## Estado del documento', '', 'BORRADOR, no compartir sin la revisión de Responsable.', '']
    return '\n'.join(L).rstrip() + '\n'

def indice_md(seguimiento: list[tuple[dict, str, list[Requisito]]], cerradas: list[dict], otras: list[dict], fecha: str | None) -> str:
    L = ['# Índice — carpeta de verificación de la Fase 2', '']
    if fecha:
        L += [f'Generado el {brechas._fecha_legible(fecha)}.', '']
    L += ['| id | título | estado | capa |', '|---|---|---|---|']
    for b, _, _ in seguimiento:
        L.append(f"| {_celda(b['id'])} | {_celda(b.get('titulo'))} | {_celda(b['estado'])} | {_celda(_nombre_capa(b.get('capa')))} |")
    L += ['', f'Subcarpetas: {len(seguimiento)}.', '', '## Brechas cerradas (sin subcarpeta)', '']
    if cerradas:
        L += [f"- {_limpio(b['id'])}" + (f": {_limpio(b.get('titulo'))}" if b.get('titulo') else '') for b in cerradas]
    else:
        L.append('(ninguna)')
    if otras:
        L += ['', '## Otras brechas (sin seguimiento en esta Fase 2)', '']
        L += [f"- {_limpio(b['id'])} (estado «{b['estado']}»)" + (f": {_limpio(b.get('titulo'))}" if b.get('titulo') else '') for b in otras]
    return '\n'.join(L).rstrip() + '\n'

def _referencia_con_papel(r: Requisito) -> str:
    """Public CI documentation."""
    etiqueta = brechas.PAPEL_ETIQUETA.get(r.papel)
    return f'{etiqueta}: {r.referencia}' if etiqueta else r.referencia

def _fila_cliente(b: dict, requisitos: list[Requisito]) -> list[str]:
    """Public CI documentation."""
    req = '; '.join((_referencia_con_papel(r) for r in requisitos)) if requisitos else '(sin cita normativa)'
    return [_sin_control(b['id']), req, '', '', '', '', '']

def _fila_interna(b: dict) -> list[str]:
    return [_sin_control(b['id']), '', '', '']

def _bytes_csv(cabecera: list[str], filas: list[list[str]]) -> bytes:
    buf = io.StringIO(newline='')
    w = csv.writer(buf, delimiter=';')
    w.writerow(cabecera)
    w.writerows(filas)
    return buf.getvalue().encode('utf-8-sig')

def _bytes_xlsx_cliente(filas: list[list[str]]) -> bytes:
    import zipfile
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Verificación'
    ws.append(CABECERA_CLIENTE)
    for fila in filas:
        ws.append(fila)
    fija = datetime.datetime(2000, 1, 1)
    wb.properties.created = fija
    wb.properties.modified = fija
    bruto = io.BytesIO()
    wb.save(bruto)
    bruto.seek(0)
    salida_bruta = io.BytesIO()
    with zipfile.ZipFile(bruto) as entrada, zipfile.ZipFile(salida_bruta, 'w', zipfile.ZIP_DEFLATED) as salida:
        for pieza in entrada.infolist():
            datos = entrada.read(pieza.filename)
            if pieza.filename == 'docProps/core.xml':
                datos = re.sub(b'(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)', b'\\g<1>2000-01-01T00:00:00Z\\g<2>', datos)
            info = zipfile.ZipInfo(pieza.filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = pieza.external_attr
            salida.writestr(info, datos)
    return salida_bruta.getvalue()
_MAX_ALTERNAS = 50

def _ruta_regenerada(ruta: Path, n: int=1) -> Path:
    sufijo = 'regenerado' if n == 1 else f'regenerado{n}'
    return ruta.with_name(f'{ruta.stem}.{sufijo}{ruta.suffix}')

def _comprobar_sin_enlace(ruta: Path) -> None:
    """Public CI documentation."""
    if ruta.is_symlink():
        raise RuntimeError(f'{ruta} es un enlace: no se escribe a través de él')

def _alterna_libre(ruta: Path, contenido: bytes, etiqueta: str, avisos: list[str]) -> Path | None:
    """Public CI documentation."""
    for n in range(1, _MAX_ALTERNAS + 1):
        candidata = _ruta_regenerada(ruta, n)
        _comprobar_sin_enlace(candidata)
        if not candidata.exists():
            return candidata
        if candidata.read_bytes() == contenido:
            return None
    avisos.append(f'{etiqueta}: no se ha encontrado un nombre libre para la versión regenerada tras {_MAX_ALTERNAS} intentos (demasiadas versiones regeneradas rellenadas a mano): no se ha escrito nada')
    return None

def _escribir_o_avisar(ruta: Path, contenido: bytes, etiqueta: str, avisos: list[str]) -> None:
    """Public CI documentation."""
    _comprobar_sin_enlace(ruta)
    if ruta.exists():
        if ruta.read_bytes() == contenido:
            return
        alterna = _alterna_libre(ruta, contenido, etiqueta, avisos)
        if alterna is not None:
            alterna.write_bytes(contenido)
            avisos.append(f'{etiqueta} ya existía con un contenido distinto del que se generaría (¿rellenado a mano?): no se ha pisado; la versión nueva se ha escrito en {alterna.name}')
        return
    ruta.write_bytes(contenido)

def _escribir_interno(ruta: Path, contenido: bytes, *, reemplazar: bool, avisos: list[str]) -> None:
    """Public CI documentation."""
    _comprobar_sin_enlace(ruta)
    if ruta.exists():
        if ruta.read_bytes() == contenido:
            return
        if not reemplazar:
            avisos.append(f'{ruta.name} ya existía con un contenido distinto del que se generaría: no se ha tocado (repite con --reemplazar si quieres regenerarlo)')
            return
        alterna = _alterna_libre(ruta, contenido, ruta.name, avisos)
        if alterna is not None:
            alterna.write_bytes(contenido)
            avisos.append(f'{ruta.name} ya existía con un contenido distinto del que se generaría: no se ha pisado; la versión nueva se ha escrito en {alterna.name}')
        return
    ruta.write_bytes(contenido)

@dataclass
class Resultado:
    subcarpetas: list[str] = field(default_factory=list)
    cerradas: list[str] = field(default_factory=list)
    otras: list[str] = field(default_factory=list)
    ficheros: list[str] = field(default_factory=list)
    sobrantes: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

def _dentro(ruta: Path, raiz: Path) -> Path:
    """Public CI documentation."""
    _comprobar_sin_enlace(ruta)
    ruta_r, raiz_r = (ruta.resolve(), raiz.resolve())
    if ruta_r != raiz_r and raiz_r not in ruta_r.parents:
        raise RuntimeError(f'ruta fuera de destino: {ruta_r} (destino: {raiz_r})')
    return ruta_r

def generar(con, registro: dict, destino: Path, *, reemplazar: bool=False, fecha: str | None=None, corte: str | None=None) -> Resultado:
    """Public CI documentation."""
    if corte is None:
        corte = registro.get('fecha_corte')
    if corte is None:
        corte = datetime.date.today().isoformat()
    if not brechas._fecha_ok(corte):
        raise ValueError('--corte tiene que ser una fecha válida AAAA-MM-DD')
    if fecha is not None and (not brechas._fecha_ok(fecha)):
        raise ValueError('--fecha tiene que ser una fecha válida AAAA-MM-DD')
    corte_efectivo = min(corte, fecha or datetime.date.today().isoformat())
    destino = Path(destino)
    ruta_comprobar = destino
    while True:
        _comprobar_sin_enlace(ruta_comprobar)
        if _es_reservado(ruta_comprobar.name):
            raise RuntimeError(f'{ruta_comprobar.name!r} es un nombre de dispositivo reservado en Windows (CON, NUL, AUX, COM1...): --destino no puede tener ese nombre en ninguno de sus componentes')
        padre = ruta_comprobar.parent
        if padre == ruta_comprobar:
            break
        ruta_comprobar = padre
    destino = destino.resolve()
    if destino.exists():
        if not destino.is_dir():
            raise RuntimeError(f'{destino} existe y no es una carpeta')
        internos = []
        pendientes = [destino]
        while pendientes:
            for ruta in sorted(pendientes.pop().iterdir()):
                _comprobar_sin_enlace(ruta)
                if ruta.is_dir():
                    pendientes.append(ruta)
                elif any((m in ruta.name.casefold() for m in ('interno', '_para_responsable', '_comprobacion', '_anterior_'))):
                    internos.append(ruta.relative_to(destino).as_posix())
        if internos:
            raise RuntimeError('carpeta no generada: ficheros internos heredados dentro del destino: ' + '; '.join(sorted(internos)) + '. No se ha borrado ni movido nada')
        if any(destino.iterdir()) and (not reemplazar):
            raise RuntimeError(f'{destino} ya existe y no está vacía: repite con --reemplazar si quieres regenerar sus ficheros; el que ya tenga un contenido distinto del que se generaría no se pisa (se escribe al lado, en <nombre>.regenerado.<ext>)')
    fallos = []
    for b in registro['brechas']:
        for cita in b.get('citas') or []:
            ident = cita['identificador'].strip()
            r = consulta.resolver(con, ident, AMBITOS, modo=consulta.MODO_LOCALIZAR)
            if r.estado not in brechas._ESTADOS_EXISTE:
                fallos.append(f"{_limpio(b['id'])}: {ident}")
    if fallos:
        raise CitaNoResuelta('carpeta no generada: citas sin resolver en la base: ' + '; '.join(fallos))
    registro, marcas_licencia = brechas.proteger_registro_fase2(con, registro, AMBITOS)
    res = Resultado()
    res.avisos.extend(marcas_licencia)
    usados: set[str] = set()
    seguimiento: list[tuple[dict, str, list[Requisito]]] = []
    cerradas: list[dict] = []
    otras: list[dict] = []
    avisos_situacion: dict[str, str] = {}
    campos_por_id: dict[str, list[tuple[str, str]]] = {}
    for b in registro['brechas']:
        situacion = brechas._situacion_carencia_fase2(b, corte_efectivo)
        ultima = brechas.ultima_revision_a_fecha(b, corte_efectivo)
        es_cerrada = situacion.casefold() in (brechas.TRADUCCION_ESTADO_FASE2['cumple'].casefold(), brechas.ESTADO_FASE2_CERRADA_FASE1.casefold())
        if ultima is not None and (b['estado'] == 'cerrada') != es_cerrada:
            aviso = f"{b['id']}: estado «{b['estado']}» pero su revisión efectiva al corte {corte_efectivo} (nº {ultima['numero']}, {ultima.get('fecha') or 'sin fecha'}) es «{ultima['veredicto']}»: situación «{situacion}»; revisa la contradicción"
            avisos_situacion[b['id']] = aviso
            res.avisos.append(aviso)
        visible = dict(b)
        estado_posterior = brechas._estado_tras_corte(b, corte_efectivo)
        if estado_posterior:
            visible['titulo'] = ''
        if ultima is not None or estado_posterior:
            visible['estado'] = situacion
            visible['fecha_estado'] = ultima.get('fecha') if ultima else None
        if not es_cerrada:
            campos_por_id[b['id']] = brechas._descripcion_y_peticion_fase2(b, corte_efectivo)
            nombre = nombre_carpeta(b['id'], visible.get('titulo'), usados)
            requisitos = [requisito_normativo(con, c) for c in b.get('citas') or []]
            seguimiento.append((visible, nombre, requisitos))
        else:
            cerradas.append(visible)
    destino.mkdir(parents=True, exist_ok=True)
    esperadas = set()
    for b, nombre, requisitos in seguimiento:
        carpeta = _dentro(destino / nombre, destino)
        esperadas.add(carpeta.name)
        carpeta.mkdir(parents=True, exist_ok=True)
        res.subcarpetas.append(nombre)
        ruta_leeme = _dentro(carpeta / 'LEEME.md', destino)
        _escribir_o_avisar(ruta_leeme, leeme_md(b, requisitos, campos_efectivos=campos_por_id[b['id']]).encode('utf-8'), str(ruta_leeme.relative_to(destino)), res.avisos)
        res.ficheros.append(str(ruta_leeme.relative_to(destino)))
    for hijo in sorted(destino.iterdir()):
        if hijo.is_dir() and hijo.name not in esperadas:
            res.sobrantes.append(hijo.name)
    res.cerradas = [b['id'] for b in cerradas]
    res.otras = [b['id'] for b in otras]
    ruta_indice = _dentro(destino / 'INDICE.md', destino)
    _escribir_o_avisar(ruta_indice, indice_md(seguimiento, cerradas, otras, fecha).encode('utf-8'), str(ruta_indice.relative_to(destino)), res.avisos)
    res.ficheros.append(str(ruta_indice.relative_to(destino)))
    filas_cliente = [_fila_cliente(b, requisitos) for b, _, requisitos in seguimiento]
    ruta_csv = _dentro(destino / 'PLANTILLA_registro_verificacion.csv', destino)
    _escribir_o_avisar(ruta_csv, _bytes_csv(CABECERA_CLIENTE, filas_cliente), str(ruta_csv.relative_to(destino)), res.avisos)
    res.ficheros.append(str(ruta_csv.relative_to(destino)))
    try:
        import openpyxl
    except ImportError:
        res.avisos.append('openpyxl no está instalado: no se genera PLANTILLA_registro_verificacion.xlsx (solo la .csv; no se instala el paquete)')
    else:
        ruta_xlsx = _dentro(destino / 'PLANTILLA_registro_verificacion.xlsx', destino)
        _escribir_o_avisar(ruta_xlsx, _bytes_xlsx_cliente(filas_cliente), str(ruta_xlsx.relative_to(destino)), res.avisos)
        res.ficheros.append(str(ruta_xlsx.relative_to(destino)))
    ruta_interno = destino.parent / f'{destino.name}_INTERNO.csv'
    filas_internas = [_fila_interna(b) for b, _, _ in seguimiento]
    ids_internos = {b['id'] for b, _, _ in seguimiento}
    filas_internas += [_fila_interna(b) for b in registro['brechas'] if b['id'] in avisos_situacion and b['id'] not in ids_internos]
    for fila in filas_internas:
        aviso = avisos_situacion.get(fila[0])
        if aviso:
            fila[3] = 'AVISO: ' + _sin_control(aviso)
    _escribir_interno(ruta_interno, _bytes_csv(CABECERA_INTERNA, filas_internas), reemplazar=reemplazar, avisos=res.avisos)
    res.ficheros.append(str(ruta_interno))
    return res

def main(argv: list[str] | None=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog='El <destino>_INTERNO.csv (columnas de control de Responsable) se escribe A PROPÓSITO JUNTO a --destino, no dentro: no es del cliente y no debe compartirse con él.')
    p.add_argument('--registro', required=True, help='el JSON de ict155.brechas (fuera del repositorio)')
    p.add_argument('--destino', required=True, help='carpeta de salida (del cliente); el <destino>_INTERNO.csv de Responsable se escribe junto a ella, no dentro, a propósito (ver más abajo)')
    p.add_argument('--reemplazar', action='store_true', help='si la carpeta ya existe y no está vacía, regenera sus ficheros: el que ya tenga un contenido distinto del que se generaría no se pisa (se escribe al lado, en <nombre>.regenerado.<ext>, con un aviso); si es igual, no se toca nada')
    p.add_argument('--fecha', default=None, help='AAAA-MM-DD; fecha de emisión, si se da sale en INDICE.md; limita el contenido como en el informe')
    p.add_argument('--corte', default=None, help='AAAA-MM-DD; situación a esta fecha (por defecto, fecha_corte del registro o hoy), como en brechas --corte')
    a = p.parse_args(argv)
    if a.fecha and (not _RE_FECHA.match(a.fecha)):
        p.error('--fecha tiene que ser AAAA-MM-DD')
    try:
        registro = brechas.leer_registro(a.registro)
    except brechas.RegistroMalo as e:
        for err in e.errores:
            print(f'ERROR: {err}', file=sys.stderr)
        return 2
    con = db.conectar(solo_lectura=True)
    try:
        res = generar(con, registro, Path(a.destino), reemplazar=a.reemplazar, fecha=a.fecha, corte=a.corte)
    except CitaNoResuelta as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, OSError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    finally:
        con.close()
    print(f'Subcarpetas creadas ({len(res.subcarpetas)}): ' + (', '.join(res.subcarpetas) or 'ninguna'))
    print(f'Cerradas listadas ({len(res.cerradas)}): ' + (', '.join(res.cerradas) or 'ninguna'))
    if res.otras:
        print(f'Otras brechas listadas ({len(res.otras)}): ' + ', '.join(res.otras))
    print(f'Ficheros escritos ({len(res.ficheros)}):')
    for f in res.ficheros:
        print(f'  {f}')
    if res.sobrantes:
        print('Subcarpetas sobrantes de una ejecución anterior (no tocadas): ' + ', '.join(res.sobrantes))
    for av in res.avisos:
        print(f'AVISO: {av}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
