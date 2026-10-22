"""Public CI documentation."""
from __future__ import annotations
import re
import sqlite3
from . import consulta, fundamento
from .contexto import RE_NORMA
from .parsers import ORD_DISPOSICION
LARGO_AMBITO = 6000
LARGO_DEFINICION = 700
MAXIMO_DEFINICIONES = 8
MAXIMO_REMISIONES = 12
RE_ROTULO_AMBITO = re.compile('(?i)\\b(?:[áa]mbito|objeto)\\b')
RE_ROTULO_DEFINICIONES = re.compile('(?i)definici|terminolog')
RE_TERMINO_CON_DOS_PUNTOS = re.compile('^\\s*(?:[a-zñ]\\)|\\d{1,2}\\)|\\d{1,2}\\.)?\\s*[«“\\"]?([^:«»“”\\"\\n]{3,80}?)[»”\\"]?\\s*:')
RE_ART = re.compile('(?i)\\bart[íi]culos?\\s+(\\d{1,3}(?:\\.\\d{1,2}){0,2})(?:\\s*(bis|ter))?')
RE_IF = re.compile('\\b(?:Instrucci[oó]n\\s+)?(IF-\\d{2})\\b')
RE_AP_DE_ESTA_INSTRUCCION = re.compile('(?i)\\bapartados?\\s+(\\d{1,2}(?:\\.\\d{1,2}){0,3})\\s+de\\s+(?:esta|la\\s+presente)\\s+instrucci')
RE_APARTADO = re.compile('(?i)\\bapartados?\\s+(\\d{1,2})\\b(?!\\s*(?:\\.\\d|de\\s+(?:esta|la)))')

def _corta(s: str, n: int) -> str:
    s = ' '.join((s or '').split())
    return s if len(s) <= n else s[:n - 1] + '…'

def _filas(con: sqlite3.Connection, version_id: int) -> list[sqlite3.Row]:
    return con.execute('SELECT ruta_estructural AS ruta, tipo_unidad AS tipo, etiqueta_humana AS etiqueta, titulo, texto_literal AS texto, pagina_inicio, pagina_fin, padre_id FROM precepto WHERE version_id=? ORDER BY orden', (version_id,)).fetchall()

def _pieza(obra: str, f, largo: int | None) -> dict:
    d = {'identificador': f"{obra}::{f['ruta']}", 'etiqueta': f['etiqueta'], 'titulo': f['titulo'], 'paginas': f"{f['pagina_inicio']}" + (f"-{f['pagina_fin']}" if f['pagina_fin'] != f['pagina_inicio'] else '')}
    if largo:
        d['texto'] = _corta(f['texto'], largo)
    return d

def _patron_del_termino(termino: str) -> re.Pattern | None:
    palabras = fundamento.normalizar(termino).split()
    if not palabras or sum((len(p) for p in palabras)) < 5:
        return None
    return re.compile('\\b' + '\\s+'.join((re.escape(p) + '(?:s|es)?' for p in palabras)) + '\\b')

def _definiciones(filas, cited_ruta: str, texto_citado: str, obra: str) -> list[dict]:
    rutas = [f['ruta'] for f in filas]
    contenedores = [f['ruta'] for f in filas if f['titulo'] and RE_ROTULO_DEFINICIONES.search(f['titulo'])]
    if not contenedores:
        return []
    plano = ' ' + fundamento.normalizar(texto_citado) + ' '
    halladas = []
    for f in filas:
        r = f['ruta']
        if r == cited_ruta or not any((r.startswith(c + '.') or r.startswith(c + '/') for c in contenedores)):
            continue
        if any((x.startswith(r + '.') or x.startswith(r + '/') for x in rutas)):
            continue
        termino = (f['titulo'] or '').strip().rstrip('.')
        if not termino:
            m = RE_TERMINO_CON_DOS_PUNTOS.match(f['texto'] or '')
            termino = m.group(1).strip() if m else ''
        patron = _patron_del_termino(termino) if termino else None
        if patron and patron.search(plano):
            halladas.append((len(fundamento.normalizar(termino).split()), termino, f))
    halladas.sort(key=lambda x: -x[0])
    vistos, salida = (set(), [])
    for _, termino, f in halladas:
        if termino.lower() in vistos:
            continue
        vistos.add(termino.lower())
        salida.append({'termino': termino, **_pieza(obra, f, LARGO_DEFINICION)})
        if len(salida) >= MAXIMO_DEFINICIONES:
            break
    return salida

def _ambito(filas, cited_ruta: str, obra: str) -> list[dict]:
    salida = []
    for f in filas:
        if f['padre_id'] is None and f['tipo'] == 'articulo' and f['titulo'] and RE_ROTULO_AMBITO.search(f['titulo']):
            if f['ruta'] != cited_ruta:
                salida.append(_pieza(obra, f, LARGO_AMBITO))
        if len(salida) >= 2:
            break
    return salida

def _padre(ruta: str) -> str | None:
    return consulta.ruta_padre(ruta)

def _rutas_remitidas(texto: str, ruta: str) -> list[str]:
    """Public CI documentation."""
    salida: list[str] = []
    for m in RE_ART.finditer(texto):
        if RE_NORMA.search(texto[m.end():m.end() + 70]) or re.match('\\s+(?:del|de\\s+la)\\s+(?!presente|este)', texto[m.end():m.end() + 25]):
            continue
        salida.append(f'art.{m.group(1)}' + (f'.{m.group(2).lower()}' if m.group(2) else ''))
    for m in RE_IF.finditer(texto):
        salida.append(f'itc.{m.group(1)}')
    itc = re.match('^(itc\\.IF-\\d{2})', ruta)
    if itc:
        for m in RE_AP_DE_ESTA_INSTRUCCION.finditer(texto):
            salida.append(f'{itc.group(1)}/ap.{m.group(1)}')
    art = re.match('^(art\\.(\\d{1,3}))\\.\\d', ruta)
    if art:
        for m in RE_APARTADO.finditer(texto):
            salida.append(f'{art.group(1)}.{m.group(1)}')
        for m in re.finditer('(?i)\\bapartados?\\s+(\\d{1,3})\\.(\\d{1,2})\\b', texto):
            if m.group(1) == art.group(2):
                salida.append(f'{art.group(1)}.{m.group(2)}')
    return list(dict.fromkeys((r for r in salida if r != ruta and (not ruta.startswith(r + '.')))))
MAXIMO_REMITENTES_CON_FRAGMENTO = 8
MAXIMO_REMITENTES_EN_LISTA = 40
LARGO_FRAGMENTO = 150
_NUM = '\\d{1,3}(?:\\.\\d{1,2}){0,2}'
RE_REF_ARTICULO = re.compile(f'(?i)\\b(?:art[íi]culos?|arts?\\.)\\s*({_NUM})((?:\\s*(?:,|y|e|o)\\s*{_NUM})*)(?!\\s*(?:bis|ter|qu[aá]ter)\\b)')
RE_REF_APARTADO = re.compile('(?i)\\b(?:apartados?|puntos?)\\s+(\\d{1,2}(?:\\.\\d{1,2}){0,3})((?:\\s*(?:,|y|e)\\s*\\d{1,2}(?:\\.\\d{1,2})*)*)')
RE_REF_APENDICE = re.compile('(?i)\\bap[ée]ndices?\\s+([IVXLC]+|\\d+|(?-i:[A-Z]))\\b')
RE_REF_ANEXO = re.compile('(?i)\\banexos?\\s+([IVXLC]+|\\d+|(?-i:[A-Z]))\\b')
RE_REF_CAPITULO = re.compile('(?i)\\bcap[íi]tulos?\\s+([IVXLC]+)\\b')
RE_REF_DISPOSICION = re.compile(f'(?i)\\bdisposici[óo]n(?:es)?\\s+(adicional|transitoria|derogatoria|final)\\s+({ORD_DISPOSICION})')
RE_ANTES_DEL_ARTICULO = re.compile('(?i)(?:apartados?|puntos?)\\s+(\\d+(?:\\.\\d+)*)\\s+del?\\s+(?:el\\s+)?$')
RE_APARTADOS_TRAS_ARTICULO = re.compile('(?i)^\\s*,?\\s*(?:apartados?|puntos?)\\s+(\\d{1,2}(?:\\.\\d{1,2})*)((?:\\s*(?:,|y|e)\\s*\\d{1,2}(?:\\.\\d{1,2})*)*)')
RE_APARTADO_TRAS_ARTICULO_PREVIO = re.compile('(?i)\\bart[íi]culos?\\s*\\d{1,3}(?:\\.\\d{1,2})*\\s*,?\\s*$')
RE_ANAFORA_ANTES = re.compile('(?i)\\b(?:su|sus|dicho|dicha|dichos|dichas|citado|citada|mismo|misma)\\s+$')
RE_MODIFICA_OTRA_NORMA = re.compile('(?i)queda(?:n)?\\s+redactad|se\\s+añade|nueva\\s+redacci[oó]n|se\\s+modifica')
PROPIOS = frozenset(('esta', 'este', 'presente', 'dicha', 'dicho'))
ESPECIFICADORES = frozenset(('apartado', 'apartados', 'punto', 'puntos', 'letra', 'letras', 'párrafo', 'parrafo', 'párrafos', 'parrafos', 'inciso', 'incisos', 'primero', 'segundo', 'tercero', 'último', 'ultimo'))
RE_TROZO_DE_ESPECIFICADOR = re.compile('^(?:\\d+(?:\\.\\d+)*|[a-zñ]\\)|\\([a-zñ]\\))$')
CONECTORES = frozenset(('y', 'e', 'o', 'a', 'al', 'ni'))

def _de_quien(tail: str) -> str | None:
    """Public CI documentation."""
    palabras = re.findall(',|[^\\s,]+', tail[:140])
    i = 0
    while i < len(palabras):
        p = palabras[i].lower()
        if p == ',' or p in ESPECIFICADORES or p in CONECTORES or RE_TROZO_DE_ESPECIFICADOR.match(p):
            i += 1
            continue
        break
    if i >= len(palabras) or palabras[i].lower() not in ('de', 'del'):
        return None
    i += 1
    if i < len(palabras) and palabras[i].lower() in ('la', 'el', 'los', 'las'):
        i += 1
    if i >= len(palabras):
        return None
    return 'propio' if palabras[i].lower().rstrip('.,;:') in PROPIOS else 'ajeno'

def _recipiente(ruta: str, clase: str) -> str | None:
    """Public CI documentation."""
    patron = {'anexo': '^(anexo\\.[^/]+)', 'apendice': '^(anexo\\.[^/]+/apend\\.[^/]+)', 'instruccion': '^((?:reglamento/)?itc\\.[^/]+)', 'articulo': '^(art\\.\\d+)'}[clase]
    m = re.match(patron, ruta)
    return m.group(1) if m else None

def _numeros(primero: str, resto: str) -> list[str]:
    return [primero] + re.findall('\\d{1,3}(?:\\.\\d{1,2})*', resto or '')

def _referencias_internas(texto: str, ruta: str) -> list[tuple[str, int, int]]:
    """Public CI documentation."""
    salida: list[tuple[str, int, int]] = []
    inicio = len(texto) - len(texto.lstrip())

    def ajeno_o_propio(fin: int):
        return _de_quien(texto[fin:fin + 140])

    def propia_etiqueta(m) -> bool:
        """Public CI documentation."""
        if m.start() > inicio + 1:
            return False
        siguiente = texto[m.end():m.end() + 6].lstrip()[:1]
        return siguiente in ('.', ':') or texto[m.start():m.start() + 4].isupper()

    def anafora(m) -> bool:
        return bool(RE_ANAFORA_ANTES.search(texto[max(0, m.start() - 12):m.start()]))
    for m in RE_REF_ARTICULO.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or ajeno_o_propio(m.end()) == 'ajeno':
            continue
        previo = RE_ANTES_DEL_ARTICULO.search(texto[max(0, m.start() - 40):m.start()])
        numeros = _numeros(m.group(1), m.group(2))
        tras = RE_APARTADOS_TRAS_ARTICULO.match(texto[m.end():m.end() + 80]) if len(numeros) == 1 else None
        if tras:
            for ap in _numeros(tras.group(1), tras.group(2)):
                salida.append((f'art.{numeros[0]}.{ap}', m.start(), m.end() + tras.end()))
            continue
        for n in numeros:
            destino = f'art.{n}'
            if previo and len(numeros) == 1 and ('.' not in n):
                destino = f'art.{n}.{previo.group(1)}'
            salida.append((destino, m.start(), m.end()))
    for m in RE_REF_APARTADO.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or RE_APARTADO_TRAS_ARTICULO_PREVIO.search(texto[max(0, m.start() - 30):m.start()]):
            continue
        resto = texto[m.end():m.end() + 140]
        quien = re.match('(?i)^\\s*,?\\s*(?:de|del)\\s+(?:la\\s+|el\\s+)?(esta|este|presente|dicha|dicho)\\s+(anexo|ap[ée]ndice|art[íi]culo|instrucci[óo]n)', resto)
        if quien:
            clase = {'anexo': 'anexo', 'apendice': 'apendice', 'apéndice': 'apendice', 'articulo': 'articulo', 'artículo': 'articulo', 'instruccion': 'instruccion', 'instrucción': 'instruccion'}[quien.group(2).lower()]
            base = _recipiente(ruta, clase)
            if base:
                for n in _numeros(m.group(1), m.group(2)):
                    salida.append((f'{base}.{n}' if clase == 'articulo' else f'{base}/ap.{n}', m.start(), m.end() + quien.end()))
            continue
        if re.match('(?i)^\\s*,?\\s*(?:de|del)\\s', resto):
            continue
        base = _recipiente(ruta, 'instruccion') or _recipiente(ruta, 'anexo') or None
        art = re.match('^(art\\.\\d+)(?:\\.|$)', ruta)
        if art:
            for n in _numeros(m.group(1), m.group(2)):
                salida.append((f'{art.group(1)}.{n}', m.start(), m.end()))
        elif base:
            apend = _recipiente(ruta, 'apendice')
            for n in _numeros(m.group(1), m.group(2)):
                salida.append((f'{apend or base}/ap.{n}', m.start(), m.end()))
    for m in RE_REF_APENDICE.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or ajeno_o_propio(m.end()) == 'ajeno':
            continue
        base = _recipiente(ruta, 'anexo')
        if base:
            salida.append((f'{base}/apend.{(m.group(1).upper() if len(m.group(1)) == 1 else m.group(1))}', m.start(), m.end()))
    for m in RE_REF_ANEXO.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or ajeno_o_propio(m.end()) == 'ajeno':
            continue
        salida.append((f'anexo.{m.group(1).upper()}', m.start(), m.end()))
    for m in RE_REF_CAPITULO.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or ajeno_o_propio(m.end()) == 'ajeno':
            continue
        salida.append((f'capitulo.{m.group(1).upper()}', m.start(), m.end()))
    from .parsers import ordinal_a_numero
    for m in RE_REF_DISPOSICION.finditer(texto):
        if propia_etiqueta(m) or anafora(m) or ajeno_o_propio(m.end()) == 'ajeno':
            continue
        numero = ordinal_a_numero(m.group(2))
        if re.fullmatch('\\d+(?:\\s+\\w+)?', numero):
            salida.append((f'disp.{m.group(1).lower()}.{numero}', m.start(), m.end()))
    return salida

def _cuelga_de(ruta: str, de: str) -> bool:
    return ruta == de or ruta.startswith(de + '.') or ruta.startswith(de + '/')

def _fragmento(texto: str, ini: int, fin: int) -> str:
    a, b = (max(0, ini - 70), min(len(texto), fin + 70))
    f = ' '.join(texto[a:b].split())
    if a > 0 and ' ' in f:
        f = '… ' + f.split(' ', 1)[1]
    if b < len(texto) and ' ' in f:
        f = f.rsplit(' ', 1)[0] + ' …'
    return _corta(f, LARGO_FRAGMENTO + 8)

def remitentes(filas, ruta: str, obra: str) -> dict:
    """Public CI documentation."""
    menciones: dict[str, list[tuple[str, int, int]]] = {}
    por_ruta = {f['ruta']: f for f in filas}
    for f in filas:
        r, texto = (f['ruta'], f['texto'] or '')
        if not r or _cuelga_de(r, ruta) or _cuelga_de(ruta, r) or (f['tipo'] in ('preambulo', 'cabecera')) or (r in ('preambulo', 'cabecera')):
            continue
        if r.startswith('disp.') and '«' in texto and RE_MODIFICA_OTRA_NORMA.search(texto):
            continue
        hallazgos = [h for h in _referencias_internas(texto, r) if _cuelga_de(h[0], ruta)]
        if hallazgos:
            menciones[r] = hallazgos

    def firma(r, h):
        t = por_ruta[r]['texto']
        return (h[0], ' '.join(t[h[1]:h[2]].lower().split()))
    firmas = {r: {firma(r, h) for h in hs} for r, hs in menciones.items()}
    finales = []
    for r in menciones:
        propias = set(firmas[r])
        for otra in menciones:
            if otra != r and _cuelga_de(otra, r):
                propias -= firmas[otra]
        if propias:
            finales.append((r, next((h for h in menciones[r] if firma(r, h) in propias))))
    if not finales:
        return {}
    orden = {f['ruta']: i for i, f in enumerate(filas)}
    finales.sort(key=lambda x: orden[x[0]])
    lista = [{'identificador': f'{obra}::{r}', 'ruta': r, 'fragmento': _fragmento(por_ruta[r]['texto'], h[1], h[2])} for r, h in finales]
    return {'total': len(lista), 'obra': obra, 'rutas': [x['ruta'] for x in lista[:MAXIMO_REMITENTES_EN_LISTA]], 'ejemplos': lista[:MAXIMO_REMITENTES_CON_FRAGMENTO]}

def contexto(con: sqlite3.Connection, identificador: str, ambitos: tuple[str, ...]=('publico',)) -> dict:
    """Public CI documentation."""
    r = consulta.resolver(con, identificador, ambitos)
    if r.estado not in (consulta.ENCONTRADO, consulta.CONTENIDO_EN_ANCESTRO) or not r.version_id:
        return {}
    _, ruta = consulta.partir_identificador(identificador)
    if not ruta:
        return {}
    ruta = consulta.ruta_efectiva(con, r.version_id, ruta)
    obra = r.obra
    filas = _filas(con, r.version_id)
    texto = r.texto_literal or ''
    salida: dict = {'precepto': f'{obra}::{ruta}'}
    amb = _ambito(filas, ruta, obra)
    if amb:
        salida['ambito'] = amb
    defs = _definiciones(filas, ruta, texto, obra)
    if defs:
        salida['definiciones'] = defs
    por_ruta = {f['ruta']: f for f in filas}
    padre = _padre(ruta)
    if padre and padre in por_ruta:
        salida['padre'] = _pieza(obra, por_ruta[padre], 400)
    remisiones = []
    for rr in _rutas_remitidas(texto, ruta):
        if rr in por_ruta:
            remisiones.append(_pieza(obra, por_ruta[rr], None))
    nombres_propios = {fundamento.normalizar(a) for a in (r.obra_titulo or '', obra)}
    for m in RE_NORMA.finditer(texto):
        nombre = ' '.join(m.group(0).split())
        if fundamento.normalizar(nombre) in nombres_propios:
            continue
        otra = consulta.resolver(con, nombre, ambitos)
        if otra.obra == obra:
            continue
        en_base = otra.estado not in (consulta.NO_CONSTA,)
        remisiones.append({'norma': nombre, 'en_la_base': en_base, **({'obra': otra.obra} if en_base and otra.obra else {})})
    if remisiones:
        vistos, unicas = (set(), [])
        for x in remisiones:
            k = x.get('identificador') or x.get('norma')
            if k not in vistos:
                vistos.add(k)
                unicas.append(x)
        salida['remisiones'] = unicas[:MAXIMO_REMISIONES]
    inversas = remitentes(filas, ruta, obra)
    if inversas:
        salida['remitentes'] = inversas
    return salida

def texto(ctx: dict) -> str:
    """Public CI documentation."""
    if not ctx or len(ctx) <= 1:
        return ''
    out = ['', '──── CONTEXTO OBLIGATORIO (léelo antes de concluir nada de este precepto) ────']
    for p in ctx.get('ambito', []):
        out += [f"ÁMBITO · {p['identificador']} ({p['etiqueta']}, p. {p['paginas']})", f"  {p['texto']}"]
        if p['texto'].endswith('…'):
            out.append(f"  (recortado: cita {p['identificador']} para leerlo entero)")
    for p in ctx.get('definiciones', []):
        out += [f"DEFINICIÓN de «{p['termino']}» · {p['identificador']} (p. {p['paginas']})", f"  {p['texto']}"]
    if 'padre' in ctx:
        p = ctx['padre']
        out += [f"PADRE · {p['identificador']} ({p['etiqueta']}{(' — ' + p['titulo'] if p.get('titulo') else '')})", f"  {p['texto']}"]
    for x in ctx.get('remisiones', []):
        if 'identificador' in x:
            out.append(f"REMITE A · {x['identificador']} ({x['etiqueta']}{(' — ' + x['titulo'] if x.get('titulo') else '')})")
        else:
            out.append(f"REMITE A · {x['norma']} — " + ('en la base' + (f" ({x['obra']})" if x.get('obra') else '') if x['en_la_base'] else 'NO ESTÁ EN LA BASE'))
    r = ctx.get('remitentes')
    if r:
        mas = f", … (y {r['total'] - len(r['rutas'])} más)" if r['total'] > len(r['rutas']) else ''
        out.append(f"REMITEN A ESTE PRECEPTO · {r['obra']} ({r['total']}): {', '.join(r['rutas'])}{mas}")
        out += [f"  · {e['ruta']} — {e['fragmento']}" for e in r['ejemplos']]
    return '\n'.join(out)
