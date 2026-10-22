"""Public CI documentation."""
import json
from . import config
TIPOS = frozenset({'orden_de_palabras', 'formula_corrupta', 'formula_omitida', 'filas_de_tabla', 'estructura_no_desglosada', 'version_no_acreditada'})

class ErrorDeCalidad(ValueError):
    """Public CI documentation."""

def cargar(ruta=None):
    ruta = ruta or config.DATOS_REPO / 'calidad_textual.json'
    try:
        d = json.loads(ruta.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, RecursionError) as e:
        raise ErrorDeCalidad(f'calidad_textual: no se puede leer {ruta} ({type(e).__name__})') from e
    if not isinstance(d, dict) or type(d.get('esquema')) is not int or d['esquema'] != 1 or (not isinstance(d.get('avisos'), list)):
        raise ErrorDeCalidad('calidad_textual: esquema no válido')
    vistos = set()
    for a in d['avisos']:
        if not isinstance(a, dict):
            raise ErrorDeCalidad('calidad_textual: aviso no válido')
        for campo in ('obra', 'ruta', 'sha256_pdf', 'localizacion', 'detalle', 'testigo'):
            if not isinstance(a.get(campo), str) or not a[campo].strip():
                raise ErrorDeCalidad('calidad_textual: falta ' + campo)
        if len(a['sha256_pdf']) != 64 or any((c not in '0123456789abcdef' for c in a['sha256_pdf'])) or (not isinstance(a.get('no_certificado'), str)) or (a['no_certificado'] not in TIPOS) or (not isinstance(a.get('paginas_pdf'), list)) or (not a['paginas_pdf']) or any((type(p) is not int or p < 1 for p in a['paginas_pdf'])):
            raise ErrorDeCalidad('calidad_textual: páginas, huella o tipo no válidos')
        if len(set(a['paginas_pdf'])) != len(a['paginas_pdf']):
            raise ErrorDeCalidad('calidad_textual: páginas repetidas en un aviso')
        clave = (a['obra'], a['ruta'], a['sha256_pdf'], a['no_certificado'], tuple(sorted(a['paginas_pdf'])))
        if clave in vistos:
            raise ErrorDeCalidad('calidad_textual: aviso duplicado')
        vistos.add(clave)
    return d['avisos']

def _incluye(ancestro, ruta):
    return ancestro == '*' or not ancestro or (bool(ruta) and (ruta == ancestro or ruta.startswith((ancestro + '.', ancestro + '/'))))

def aplicar(con, respuesta, ruta, rutas_incluidas=()):
    """Public CI documentation."""
    rutas = (ruta, *rutas_incluidas)
    avisos = [a for a in cargar() if a['obra'] == respuesta.obra and any((_incluye(a['ruta'], r) or _incluye(r, a['ruta']) for r in rutas))]
    if not avisos:
        return respuesta
    version_id = respuesta.version_id
    if version_id is None and respuesta.fichero:
        versiones = con.execute('SELECT v.id FROM version v JOIN documento d ON d.id=v.documento_id JOIN obra o ON o.id=v.obra_id WHERE o.identificador_canonico=? AND d.ruta_relativa=?', (respuesta.obra, respuesta.fichero)).fetchall()
        if len(versiones) == 1:
            version_id = versiones[0][0]
    if version_id is None:
        return respuesta
    doc = con.execute('SELECT d.sha256 FROM version v JOIN documento d ON d.id=v.documento_id WHERE v.id=?', (version_id,)).fetchone()
    avisos = [dict(a, fichero=respuesta.fichero) for a in avisos if doc and a['sha256_pdf'] == doc[0]]
    if avisos:
        respuesta.calidad_textual = avisos
        if respuesta.estado == 'PRECEPTO_INEXISTENTE' and any((a['no_certificado'] == 'estructura_no_desglosada' for a in avisos)):
            respuesta.estado = 'FUERA_DE_ALCANCE'
            respuesta.detalle = 'estructura no desglosada: no se puede afirmar la ausencia del precepto; consultar las páginas del PDF indicadas en el aviso'
        mensaje = 'AVISO DE CALIDAD TEXTUAL: ' + '; '.join((a['ruta'] + ': ' + a['detalle'] for a in avisos))
        respuesta.detalle = '; '.join((x for x in (respuesta.detalle, mensaje) if x))
        respuesta.naturaleza_del_texto = '; '.join((x for x in (respuesta.naturaleza_del_texto, 'texto con contenido no certificado: ' + mensaje) if x))
    return respuesta
