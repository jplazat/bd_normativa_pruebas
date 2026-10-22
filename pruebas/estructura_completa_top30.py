"""Censo independiente del TEXTO frente a una ingesta SQLite (siempre solo lectura).

No importa parsers ni infiere encabezados a partir de la BD. Acepta cualquier
directorio de extracciones *.motor.txt (preferidas) o *.normal.txt con páginas, y obras BOE
o CELEX identificadas en el nombre. --manifiesto permite otros nombres/obras.
No certifica fórmulas, imágenes ni fidelidad de extracción. Los rótulos dudosos
se publican como candidatos pendientes, nunca como ausencia en la fuente.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata


def clave(s):
    s = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', s)
    return ''.join(c.casefold() for c in unicodedata.normalize('NFKD', s)
                   if c.isalnum())


def sin_tilde(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c))


def cardinal(s):
    """Numerales impresos en palabras, sin el límite del parser examinado."""
    s = sin_tilde(s.lower()).strip()
    unidades = 'cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve'.split()
    decenas = dict(zip('treinta cuarenta cincuenta sesenta setenta ochenta noventa'.split(), range(30, 100, 10)))
    if s in unidades:
        return unidades.index(s)
    if s in ('cien', 'ciento'):
        return 100
    if s.startswith('ciento '):
        resto = cardinal(s[7:])
        return 100 + resto if resto is not None else None
    if s in decenas:
        return decenas[s]
    a, _, b = s.partition(' y ')
    if a in decenas and b in unidades[1:10]:
        return decenas[a] + unidades.index(b)
    return None


PAGINA = re.compile(r'^===== PÁGINA (\d+) =====\s*$')
ART = re.compile(r'^(?:Artículo|Articulo|Artitulo|Article)\s*(\d+(?:\s*(?:bis|ter|quater|quinquies|sexies|septies))?|[úu]nico|[a-záéíóúñ ]+)(?:\.\s*(.*)|\s*)$')
ART_RUBRICA = re.compile(r'^(?:Artículo|Articulo|Article)\s*(\d+(?:\s*(?:bis|ter|quater|quinquies|sexies|septies))?)\s+([A-ZÁÉÍÓÚ].*)$')
ANEXO = re.compile(r'^(?:ANEXO|Anexo|ANEJO|Anejo|ANNEX|Annex)(?:\s+([IVXLCDM]+|\d+|[ÚU]NICO)(?:[.:]?\s+([A-ZÁÉÍÓÚ].*))?)?$')
DIV = re.compile(r'^(CAP[ÍI]TULO|CHAPTER|T[ÍI]TULO|TITLE|SECCI[ÓO]N|SECTION)\s+((?:PRELIMINAR|[ÚU]NICO|PRIMERO|[IVXLCDM]+|[A-Z]|\d+)(?: bis)?)[:.]?(?:\s+([A-ZÁÉÍÓÚ].*))?$')
ITC = re.compile(r'^INSTRUCCI[ÓO]N(?: T[ÉE]CNICA COMPLEMENTARIA(?: \(ITC\))?)?\s+((?:ITC-)?[A-Z]{2,4}-\d+)(?:\s+.*)?$')
NUMERO = re.compile(r'^(\d{1,3}(?:\.\d{1,3})*)([.)])?(?:\s+|$)')
LETRA = re.compile(r'^([a-zñ]{1,2})\)(?:\s+|$)')
FILA_MAGNITUDES = re.compile(r'(?:\d+(?:[.,]\d+)*\s+(?:W|kW|V|A|mA|Hz|mm|cm|m|kg|g|ml|l|%)(?:\s+|$))+')

# Contrato calibrado con las versiones 47,36,41,20,9,14 de la foto lad:
# CE 37/2005, MID, UE 2019/1020, RD 244/2016, ICT/155/2020, RD 1109/1991.
# Se exige el articulado, sus series de >=2 apartados n. y sus letras; también
# anexos/divisiones y los «Apartado N.» expresos del BOE. La foto NO subdivide
# listas decimales de los anexos UE (MID: 26 anexos/capítulos y 0 apartados de
# anexo), ni n) de definiciones con carácter general, ni secciones UE fuera
# del anexo. No se exigen esas rutas, aunque se conserva su censo en la salida.
# ING2 añadió definiciones n) en estas cinco obras públicas; se mantienen como
# contrato explícito. ING3 añade los apartados de capítulos BOE de anexo sin
# numeral, pedido expreso del encargo (no se generaliza a anexos numerados).
# El perfil NO consulta las filas objetivo para decidir qué debe existir.
DEFINICIONES = {'CELEX-32012R1025':'art.2','CELEX-32017R0745':'art.2',
                'CELEX-32017R0746':'art.2','CELEX-32016R0679':'art.4',
                'CELEX-32018L1972':'art.2'}
CRITERIO_CALIBRADO = 'ING3: articulado/apartados/letras y divisiones citables; listas interiores de anexo no exigibles salvo Apartado BOE y capítulos de anexo BOE sin numeral.'


@dataclass
class Encabezado:
    ruta: str
    tipo: str
    padre: str | None
    pagina: int
    linea: int
    literal: str
    ancla: str = ''


def _fragmentos_inline(s):
    """Recupera límites de enumeración del texto almacenado (sin sus saltos).

    Solo censa candidatos: el perfil decide luego si la serie es exigible.
    Se conserva la línea física de origen para todos sus fragmentos.
    """
    if FILA_MAGNITUDES.fullmatch(s):
        return [s]  # celdas numéricas con unidad, no una serie de epígrafes
    cortes = []
    apertura = NUMERO.match(s)
    anterior = apertura[1] if apertura else None
    for m in re.finditer(r'\s+(?=(?:\d{1,3}(?:\.\d{1,2})+[.)]?|\d{1,3}[.)])\s+[A-ZÁÉÍÓÚÑ«"(])',s):
        previa = re.search(r'([\wáéíóúñ]+)\s*$',s[:m.start()])
        if previa and sin_tilde(previa[1].lower()) in ('articulo','apartado','articulos','apartados','numero','numeros','anexo','anexos','tabla','tablas','figura','figuras','p','pag','pagina','paginas'):
            continue
        if re.search(r'\b\d+(?:\s*,\s*\d+)*\s+(?:y|o)\s*$',s[:m.start()]):
            continue  # «volúmenes 0 y 1. Además...» es prosa, no apartado 1
        numero = NUMERO.match(s[m.end():])[1]
        if anterior is None:
            if numero!='1':
                continue
        elif '.' not in numero and ('.' in anterior or int(numero)!=int(anterior)+1):
            continue  # constante «símbolo 1», potencia «10», remisión «y 8»
        anterior=numero
        cortes.append(m.start())
    for m in re.finditer(r'(?<=[;:.])\s+(?=[a-zñ]{1,2}\)\s)',s):
        cortes.append(m.start())
    posiciones = [0] + sorted(set(cortes)) + [len(s)]
    return [s[a:b].strip() for a,b in zip(posiciones,posiciones[1:]) if s[a:b].strip()]


def lineas_fuente(texto, desplegar=False):
    pagina = 1
    for n, linea in enumerate(texto.splitlines(), 1):
        m = PAGINA.match(linea.strip())
        if m:
            pagina = int(m[1])
            continue
        s = unicodedata.normalize('NFC', linea).replace('\u00ad', '').strip()
        s = re.sub(r'^LEGISLACI[ÓO]N CONSOLIDADA\s+(?=\S)','',s)
        # Marcas de consolidación y membretes: reglas independientes del parser.
        s = re.sub(r'[►▼◄]\s*[A-Z]\d*\b', '', s).replace('◄', '').strip()
        if re.match(r'^\d{4,5}[A-Z]\d{4}\s*[—-]', s):
            resto=re.sub(r'^\d{4,5}[A-Z]\d{4}\s*[—-]\s*[A-Z]{2}\s*[—-]\s*\d{2}\.\d{2}\.\d{4}\s*[—-]\s*\d{3}\.\d{3}\s*[—-]\s*\d+\b\s*','',s)
            if resto==s or not resto:
                continue
            s=resto
        if s in ('BOLETÍN OFICIAL DEL ESTADO', 'LEGISLACIÓN CONSOLIDADA'):
            continue
        s = re.sub(r'^_{3,}\s*(?=Art[íi]culo)', '', s)
        grupo = re.fullmatch(r'(?:(\d{1,3}\.)\s*)?((?:[a-zñ]\)\s*){2,})',s)
        if grupo:
            if grupo[1]:
                yield n,pagina,grupo[1]
            for letra in re.findall(r'[a-zñ]\)',grupo[2]):
                yield n,pagina,letra
            continue
        # Xpdf junta encabezado y primer apartado sin rúbrica intermedia.
        inline = re.match(r'^((?:Artículo|Articulo|Article)\s*\d+)\s+(\d{1,2}\.\s+.*)$', s)
        if inline:
            yield n, pagina, inline[1]
            yield n, pagina, inline[2]
        else:
            for fragmento in (_fragmentos_inline(s) if desplegar else [s]):
                yield n, pagina, fragmento


def censo_texto(texto, familia='eurlex', desplegar=False):
    """Devuelve encabezados y candidatos ambiguos, con línea/página del texto.

    Las subdivisiones se censan por lo IMPRESO, incluidas las no soportadas
    por el parser. Una numeración reiniciada o duplicada queda pendiente.
    """
    lineas = list(lineas_fuente(texto,desplegar))
    if familia == 'boe':
        comienzos = [k for k, (_, _, s) in enumerate(lineas) if re.match(r'^TEXTO (?:CONSOLIDADO|ORIGINAL)\b',s)]
        if comienzos:
            lineas = lineas[comienzos[-1] + 1:]
    encontrados, candidatos, bloques = [], [], []
    anexo = titulo = capitulo = seccion = apendice = None
    division_superior = None
    tabla = False
    cita = 0
    actual = None
    for posicion, (n, pag, s) in enumerate(lineas):
        if re.search(r'(?:\.\s*){4,}', s):  # índice BOE espaciado
            continue
        if re.search(r'\.{2,}', s):       # entradas de índices con relleno
            continue
        proximo = ' '.join(t for _, _, t in lineas[posicion:posicion+4] if t)
        if (s.startswith(('TABLA', 'CORRELATION TABLE'))
                and re.match(r'^(?:TABLA DE CORRESPONDENCIAS|CORRELATION TABLE)\b', proximo)):
            tabla = True
        if tabla:
            if actual:
                actual[1].append((n, pag, s))
            continue
        h = None
        m = ANEXO.match(s)
        instruccion = ITC.match(s)
        if not instruccion and familia == 'boe':
            instruccion = re.match(r'^ITC-(BT-\d{2})\.?(?:\s+.*)?$', s)
        a = ART.match(s) or ART_RUBRICA.match(s)
        if instruccion and not cita:
            anexo = titulo = capitulo = seccion = apendice = None
            division_superior = None
            h = Encabezado('itc.' + instruccion[1], 'instruccion', None, pag, n, s)
        elif m and not cita:
            num = sin_tilde(m[1] or 'sn')
            anexo, titulo = f'anexo.{num.lower() if num in ("UNICO", "ÚNICO") else num}', None
            capitulo = seccion = None
            division_superior = None
            apendice = None
            h = Encabezado(anexo, 'anexo', None, pag, n, s)
        elif a and not cita and not (familia == 'eurlex' and anexo):
            num = a[1].strip()
            if not num[0].isdigit() and sin_tilde(num.lower()) != 'unico':
                z = re.fullmatch(r'(.+?)( bis)?', num)
                valor = cardinal(z[1])
                if valor is None:
                    a = None
                else:
                    num = str(valor) + ('bis' if z[2] else '')
            if a:
                # Sanidad usa la ruta histórica 105bis; UE conserva «6 bis».
                num = sin_tilde(num.lower())
                if familia == 'eurlex':
                    num = re.sub(r'(?<=\d)(?=[a-z])', ' ', num)
                base = anexo + '/' if anexo and familia == 'boe' else ''
                h = Encabezado(base + 'art.' + num, 'articulo', anexo if base else None, pag, n, s)
        elif not cita:
            ax = re.match(r'^AP[ÉE]NDICE\s+([IVXLCDM]+|\d+)\b',s)
            ap = re.match(r'^Apartado\s+(\d+)\.\s*(.*)',s)
            tb = re.match(r'^Tabla\s+(\d+)\b',s)
            if ax and anexo and familia == 'boe':
                apendice = anexo + '/apend.' + ax[1]
                h = Encabezado(apendice,'apendice',anexo,pag,n,s)
            elif ap and anexo and familia == 'boe':
                padre = apendice or anexo
                h = Encabezado(padre+'/ap.'+ap[1],'apartado_explicito',padre,pag,n,s)
            elif tb and anexo and familia == 'boe' and anexo!='anexo.sn':
                padre = apendice or anexo
                h = Encabezado(padre+'/tabla.'+tb[1],'tabla',padre,pag,n,s)
            m = DIV.match(s)
            if m and not h:
                tipo = 'capitulo' if m[1].startswith(('CAP', 'CHA')) else 'seccion' if m[1].startswith(('SEC', 'SECTION')) else 'titulo'
                num = 'I' if m[2] == 'PRIMERO' else m[2]
                if sin_tilde(num) in ('UNICO','PRELIMINAR'):
                    num=sin_tilde(num).lower()
                # La primera división del anexo fija su orden impreso:
                # 999/2001 tiene capítulo > sección; 882/2004 tiene sección
                # > capítulo. No se impone una jerarquía universal ni se
                # conserva el contexto interior al abrir un nuevo hermano.
                if anexo and tipo in ('capitulo', 'seccion') and division_superior is None:
                    division_superior = tipo
                if tipo == 'capitulo':
                    padre = seccion if division_superior == 'seccion' else titulo or anexo
                elif tipo == 'seccion':
                    padre = titulo or anexo if division_superior == 'seccion' else capitulo or titulo or anexo
                else:
                    padre = anexo
                ruta = (padre + '/' if padre else '') + tipo + '.' + num
                h = Encabezado(ruta, tipo, padre, pag, n, s)
                if tipo == 'titulo':
                    titulo = ruta
                    capitulo = seccion = None
                    division_superior = None
                if tipo == 'capitulo':
                    capitulo = ruta
                    if division_superior != 'seccion':
                        seccion = None
                if tipo == 'seccion':
                    seccion = ruta
                    if division_superior == 'seccion':
                        capitulo = None
            elif (s.startswith(('Disposición ', '«Artículo', '«CAP', '«ANEX'))
                  or re.match(r'^(?:Secci[óo]n\s+\d+\.[ªa]|Hecho en|Done at)\b',s)):
                actual = None  # no atribuir sus números al artículo anterior
        if h:
            encontrados.append(h)
            actual = (h, [])
            bloques.append(actual)
            cita = 0
            if h.tipo=='anexo' and re.search(r'\bTABLA DE CORRESPONDENCIAS\b',s,re.I):
                tabla=True
        elif actual:
            actual[1].append((n, pag, s))
        if not h and not cita and re.match(r'^(?:Artículo|Articulo|Article|ANEXO|Anexo|ANNEX|CAPÍTULO|CAPITULO|CHAPTER)\b', s):
            candidatos.append(dict(pagina=pag,linea=n,literal=s,motivo='rotulo_no_clasificado_o_remision'))
        # Una cita que abre otro articulado no crea artículos de esta obra.
        if s.startswith(('«Artículo', '«Art', '«CAP', '«ANEX')):
            cita = max(0, cita + s.count('«') - s.count('»'))
        elif cita:
            cita = max(0, cita + s.count('«') - s.count('»'))

    # Rótulos repetidos por índice/cuerpo: el cuerpo (última aparición) prevalece.
    principales = {h.ruta: h for h in encontrados}
    for h, cuerpo in bloques:
        if principales[h.ruta] is not h:
            continue
        utiles = [s for _, _, s in cuerpo if s and not s.isdigit() and not s.startswith(('▼', '►'))
                  and not re.match(r'^_{3,}|^\(\d+\)\s*DO\b',s)]
        h.ancla = ' '.join(utiles)[:160]
        rubricas_itc = {}
        if h.tipo == 'instruccion':
            indice = next((i for i, (_, _, s) in enumerate(cuerpo)
                           if re.match(r'^(?:0\.\s*)?indice\b', sin_tilde(s).lower())), None)
            if indice is not None:
                primera = False
                for i in range(indice+1,len(cuerpo)):
                    mm = NUMERO.match(cuerpo[i][2])
                    if mm:
                        if mm[1] == '1' and primera:
                            cuerpo = cuerpo[i:]
                            break
                        primera |= mm[1] == '1'
                        rubricas_itc[mm[1]] = clave(cuerpo[i][2][mm.end():])
        numero_actual = None
        vistos = set()
        comillas = 0
        for k, (n, pag, s) in enumerate(cuerpo):
            protegida = comillas > 0
            comillas = max(0,comillas+s.count('«')-s.count('»'))
            if protegida:
                continue
            m = NUMERO.match(s)
            if m and (m[2] or '.' in m[1]):
                resto = s[m.end():]
                if FILA_MAGNITUDES.fullmatch(s) or re.fullmatch(r'(?:W|kW|V|A|mA|Hz|mm|cm|m|kg|g|ml|l|%)', resto):
                    continue  # valor de una celda, no encabezado
                # El cuerpo en mayúsculas prevalece sobre un índice antiguo. El índice
                # sigue ayudando a distinguir las listas en prosa («2. Otra regla...»).
                autonoma = resto.isupper() or re.fullmatch(r'\((?:Derogad[oa]|Suprimid[oa]|Anulad[oa])\)\.?',resto)
                if rubricas_itc and not autonoma and (m[1] not in rubricas_itc or not clave(resto).startswith(rubricas_itc[m[1]])):
                    continue
                if re.match(r'^(?:de|del|y|o|a|apartado|letra)\b', resto):
                    continue  # una remisión cortada por el salto de línea
                num = m[1]
                if h.tipo in ('articulo','apartado_explicito'):
                    # Numeración antigua con prefijo del propio artículo.
                    prefijo = h.ruta.split('art.')[-1] + '.'
                    if h.tipo == 'articulo' and num.startswith(prefijo):
                        num = num[len(prefijo):]
                    ruta = h.ruta + '.' + num
                    padre = ruta.rsplit('.', 1)[0] if '.' in num else h.ruta
                else:
                    ruta = h.ruta + '/ap.' + num
                    padre = h.ruta if '.' not in num else h.ruta + '/ap.' + num.rsplit('.', 1)[0]
                if ruta in vistos:
                    candidatos.append(dict(ruta=ruta, pagina=pag, linea=n, motivo='numeracion_repetida_o_lista_interior'))
                    continue
                vistos.add(ruta)
                numero_actual = ruta
                ancla = resto or ' '.join(t for _, _, t in cuerpo[k+1:k+5] if t)[:100]
                encontrados.append(Encabezado(ruta, 'apartado', padre, pag, n, s, ancla))
            elif (m := LETRA.match(s)) and h.tipo in ('articulo','apartado_explicito'):
                # Los romanos de sublistas no son letras del mismo nivel.
                siguiente = next((LETRA.match(t)[1] for _, _, t in cuerpo[k+1:] if LETRA.match(t)), None)
                romano = m[1] in ('i','v','x') and siguiente == {'i':'ii','v':'vi','x':'xi'}[m[1]]
                if len(m[1]) > 1 or romano:
                    candidatos.append(dict(ruta=h.ruta, pagina=pag, linea=n, motivo='letra_doble_o_romano'))
                    continue
                padre = numero_actual or h.ruta
                ruta = padre + '.' + m[1]
                if ruta in vistos:
                    candidatos.append(dict(ruta=ruta, pagina=pag, linea=n, motivo='letra_repetida'))
                    continue
                vistos.add(ruta)
                encontrados.append(Encabezado(ruta, 'letra', padre, pag, n, s, s[m.end():][:160]))
    resultado = {h.ruta: h for h in encontrados}
    return list(resultado.values()), candidatos


def filas_sql(con, identificador):
    # Todas las versiones: nunca mezclar rutas de versiones distintas.
    versiones = con.execute('SELECT v.id FROM version v JOIN obra o ON o.id=v.obra_id WHERE o.identificador_canonico=? ORDER BY v.id', (identificador,)).fetchall()
    if len(versiones) != 1:
        raise ValueError(f'{identificador}: se esperaba una versión para el texto; hay {len(versiones)}. Seleccione --version-id.')
    return filas_version(con, versiones[0][0])


def filas_version(con, version_id):
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('SELECT p.ruta_estructural AS ruta,p.tipo_unidad AS tipo,p.texto_literal AS texto,q.ruta_estructural AS padre FROM precepto p LEFT JOIN precepto q ON q.id=p.padre_id WHERE p.version_id=? ORDER BY p.orden', (version_id,))]


def comparar(encabezados, filas):
    """Compara también padre y contenido; no basta con que exista la ruta."""
    por_ruta = {r['ruta']: r for r in filas}
    normalizados = {r['ruta']: clave(r['texto']) for r in filas}
    faltantes, absorbidos, jerarquia, vacios, solo_rotulo = [], [], [], [], []
    for h in encabezados:
        r = por_ruta.get(h.ruta)
        if r is None:
            faltantes.append(asdict(h))
            # El rótulo numérico por sí solo es ambiguo: exigir el comienzo del
            # texto para subdivisiones. Para artículos, basta su encabezado.
            fragmento = h.literal
            if h.ancla and clave(h.ancla) not in clave(h.literal):
                fragmento += ' ' + h.ancla
            aguja = clave(fragmento if h.tipo not in ('articulo', 'anexo', 'capitulo', 'titulo') else h.literal)
            if len(aguja) >= 6:
                contenedores = [ruta for ruta, t in normalizados.items() if aguja in t]
                if contenedores:
                    absorbidos.append(dict(ruta=h.ruta, contenedores=contenedores, pagina=h.pagina, linea=h.linea))
        elif h.padre != r.get('padre'):
            jerarquia.append(dict(ruta=h.ruta, esperado=h.padre, actual=r.get('padre')))
    for r in filas:
        if not r['texto'].strip():
            vacios.append(r['ruta'])
    for h in encabezados:
        # Una línea que ya lleva TODO el cuerpo no es un mero rótulo; ocurre
        # con el texto aplanado almacenado en la base de calibración.
        rotulo = bool(re.fullmatch(r'(?:(?:Artículo|Articulo|Article)\s*\d+\.?|(?:ANEXO|Anexo|ANNEX)(?:\s+[IVXLCDM\d]+)?|\d+[.)]|[a-zñ]\))',h.literal))
        rotulo |= bool(h.ancla and clave(h.ancla) not in clave(h.literal))
        if rotulo and h.ruta in normalizados and normalizados[h.ruta] == clave(h.literal):
            solo_rotulo.append(dict(ruta=h.ruta, con_hijos=any(r.get('padre') == h.ruta for r in filas)))
    extras = [r['ruta'] for r in filas if r['tipo'] in ('articulo', 'anexo', 'capitulo') and r['ruta'] not in {h.ruta for h in encabezados}]
    return dict(encabezados=[asdict(h) for h in encabezados], faltantes=faltantes, absorbidos=absorbidos,
                jerarquia=jerarquia, vacios=vacios, solo_rotulo=solo_rotulo, extras_principales=extras)


def censo_calibrado(texto, familia='eurlex', identificador=None):
    """Contrato fijo derivado de la foto de verdad, independiente del objetivo.

    Conserva todo candidato no exigible con su motivo. Nunca usa existencia de
    rutas de la base a comprobar para rebajar el contrato.
    """
    hs, candidatos = censo_texto(texto,familia,desplegar=True)
    fuera = []
    for n,pag,s in lineas_fuente(texto):
        if re.match(r'^[a-zñ]\s+(?:bis|ter|quater|quinquies)\)',s):
            fuera.append(dict(linea=n,pagina=pag,literal=s,motivo='ordinal_de_letra_sin_ruta_propia_en_contrato_calibrado'))
    excluir = {}
    por = {h.ruta:h for h in hs}
    arranques = {n for n,_,s in lineas_fuente(texto) if NUMERO.match(s)}
    alfabeto = 'abcdefghijklmnñopqrstuvwxyz'
    letras_anteriores={}
    for h in hs:
        if h.tipo == 'seccion' and familia == 'eurlex' and not h.ruta.startswith('anexo.'):
            excluir[h.ruta]='seccion_UE_del_articulado_no_direccionada_en_foto'
        if '/ap.' in h.ruta and h.tipo in ('apartado','letra') and not any(x.tipo=='apartado_explicito' and (h.ruta.startswith(x.ruta+'.') or h.ruta==x.ruta) for x in hs):
            ampliacion = familia=='boe' and re.match(r'^anexo\.sn/capitulo\.[^/]+/ap\.',h.ruta)
            if not ampliacion and not h.ruta.startswith('itc.'):
                excluir[h.ruta]='numeracion_interior_de_anexo_no_direccionada_en_foto'
        if h.tipo=='letra':
            letra=h.ruta.rsplit('.',1)[-1]
            anterior=letras_anteriores.get(h.padre)
            letras_anteriores[h.padre]=letra
            if letra in ('i','v','x') and anterior!=alfabeto[alfabeto.index(letra)-1]:
                excluir[h.ruta]='romano_o_letra_ambigua_sin_antecesora_alfabetica'
    for h in hs:
        if h.tipo not in ('articulo','apartado_explicito'):
            continue
        directos = [x for x in hs if x.tipo=='apartado' and x.padre==h.ruta]
        definicion = DEFINICIONES.get(identificador)==h.ruta
        aptos = [x for x in directos if re.match(r'^\d+(?:\.\d+)?\.',x.literal) or definicion]
        # Como en la foto, una numeración entera pegada detrás de una rúbrica
        # sin ningún arranque propio no da apartados. Sí se exige cuando el
        # cuerpo abre línea o cuando el encabezado empieza ya por «N 1. …».
        if not definicion and not any(x.linea in arranques for x in aptos):
            aptos=[]
        if len(aptos)<2:
            aptos=[]
        validos = {x.ruta for x in aptos}
        for x in directos:
            if x.ruta not in validos:
                excluir[x.ruta]='apartado_unico_o_numeracion_n_parentesis_no_direccionada_en_foto'
            if any(c.get('ruta')==x.ruta and c['motivo']=='numeracion_repetida_o_lista_interior' for c in candidatos):
                excluir[x.ruta]='numeracion_reiniciada_sin_segunda_ruta_univoca'
        # 5.2 dentro de un apartado 5 es numeración interior, no un segundo
        # nivel de apartado del artículo. Excepción: 6.1 con prefijo de su
        # propio artículo se normaliza a 1 durante el censo (RD 1109/1991).
        for x in hs:
            if x.tipo=='apartado' and x.ruta.startswith(h.ruta+'.') and x.padre!=h.ruta:
                excluir[x.ruta]='numeracion_decimal_interior_del_apartado'
        # Las letras sin apartados solo son citables si hay una serie a,b,c…
        letras = [x for x in hs if x.tipo=='letra' and x.padre==h.ruta]
        serie=[x.ruta.rsplit('.',1)[-1] for x in letras]
        repetida=any(c.get('ruta','').rsplit('.',1)[0]==h.ruta and c['motivo']=='letra_repetida' for c in candidatos)
        con_hueco = identificador=='CELEX-32002L0058' and h.ruta=='art.2'
        if serie and (repetida or not (len(serie)>=2 and serie[0]=='a' and all(len(x)==1 for x in serie) and (con_hueco or serie==list(alfabeto[:len(serie)])))):
            for x in letras:
                excluir[x.ruta]='serie_de_letras_sin_apartado_no_citable_en_foto'
    for h in hs:
        razon=excluir.get(h.ruta)
        if not razon:
            razon=next((motivo for ruta,motivo in excluir.items() if h.ruta.startswith(ruta+'.')),None)
        if razon:
            fuera.append(dict(asdict(h),motivo=razon))
    rutas_fuera={x['ruta'] for x in fuera if 'ruta' in x}
    exigibles=[h for h in hs if h.ruta not in rutas_fuera]
    pendientes=[]
    for c in candidatos:
        ruta=c.get('ruta','')
        razon=None
        if ruta in rutas_fuera or (ruta.startswith('anexo.') and familia=='eurlex'):
            razon='candidato_de_estructura_no_direccionada_en_foto'
        elif c['motivo'] in ('letra_doble_o_romano','letra_repetida'):
            razon='romano_o_lista_repetida_sin_ruta_propia_en_contrato'
        elif c['motivo']=='numeracion_repetida_o_lista_interior':
            razon='lista_reiniciada_sin_segunda_ruta_univoca_en_contrato'
        elif c['motivo']=='rotulo_no_clasificado_o_remision' and re.match(r'^(?:Artículo|Articulo|Article|ANEXO|Anexo|ANNEX)\s*\d+\s+[a-záéíóú]',c.get('literal','')):
            razon='remision_del_cuerpo'
        elif c['motivo']=='rotulo_no_clasificado_o_remision' and familia=='eurlex' and c.get('literal','').startswith(('Artículo','Article')) and any(h.tipo=='anexo' and h.linea<c['linea'] for h in hs):
            razon='remision_o_fila_de_tabla_dentro_del_anexo_UE'
        if razon:
            fuera.append(dict(c,motivo_calibracion=razon))
        else:
            pendientes.append(c)
    return exigibles,pendientes,fuera


def comprobar_norma(texto, filas, familia='eurlex', *, criterio='impreso', identificador=None):
    if criterio=='calibrado':
        hs,candidatos,fuera=censo_calibrado(texto,familia,identificador)
    else:
        hs, candidatos = censo_texto(texto, familia)
        fuera=[]
    r = comparar(hs, filas)
    r['criterio']=CRITERIO_CALIBRADO if criterio=='calibrado' else 'Censo amplio de lo impreso (no calibrado)'
    r['fuera_de_alcance']=fuera
    r['candidatos_pendientes'] = candidatos
    r['sin_encabezados'] = not hs
    r['correcta'] = bool(hs) and not any(r[k] for k in ('faltantes', 'jerarquia', 'vacios', 'extras_principales', 'candidatos_pendientes')) and not any(not x['con_hijos'] for x in r['solo_rotulo'])
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True, type=Path)
    ap.add_argument('--textos', required=True, type=Path)
    ap.add_argument('--salida', required=True, type=Path)
    ap.add_argument('--manifiesto', type=Path, help='JSON: [{identificador,texto,familia,version_id?}]')
    ap.add_argument('--version-id', type=int, help='Solo para un único texto/obra')
    ap.add_argument('--criterio',choices=('calibrado','impreso'),default='calibrado')
    args = ap.parse_args(argv)
    if args.manifiesto:
        entradas = json.loads(args.manifiesto.read_text(encoding='utf-8'))
    else:
        entradas = []
        fuentes={fp.name.removesuffix('.normal.txt'):fp for fp in args.textos.glob('*.normal.txt')}
        fuentes.update({fp.name.removesuffix('.motor.txt'):fp for fp in args.textos.glob('*.motor.txt')})
        for fp in sorted(fuentes.values()):
            m = re.search(r'(BOE-A-\d+-\d+|CELEX-\d{5}[A-Z]\d{4})', fp.name)
            if not m:
                ap.error(f'Sin identificador en {fp.name}; use --manifiesto')
            entradas.append(dict(identificador=m[0], texto=fp.name, familia='boe' if m[0].startswith('BOE-') else 'eurlex'))
    if not entradas:
        ap.error('No hay textos: no se permite un resultado verde vacío')
    if args.version_id and len(entradas) != 1:
        ap.error('--version-id exige un único texto en --manifiesto')
    base = args.base.resolve()
    # Una errata de ruta no crea una base vacía.
    con = sqlite3.connect(base.as_uri() + '?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    assert con.execute('PRAGMA query_only').fetchone()[0] == 1
    resultados = []
    try:
        for e in entradas:
            fp = args.textos / e['texto']
            texto = fp.read_text(encoding='utf-8')
            try:
                vid = e.get('version_id') or args.version_id
                if vid:
                    ident = con.execute('SELECT o.identificador_canonico FROM version v JOIN obra o ON o.id=v.obra_id WHERE v.id=?', (vid,)).fetchone()
                    if not ident or ident[0] != e['identificador']:
                        raise ValueError('version_id no pertenece a la obra del texto')
                filas = filas_version(con, vid) if vid else filas_sql(con, e['identificador'])
                r = comprobar_norma(texto, filas, e['familia'],criterio=args.criterio,identificador=e['identificador'])
            except ValueError as ex:
                r = dict(correcta=False, error=str(ex))
            r.update(identificador=e['identificador'], texto=str(fp), sha256_texto=hashlib.sha256(fp.read_bytes()).hexdigest())
            resultados.append(r)
            print(e['identificador'], 'encabezados',len(r.get('encabezados',[])), 'faltantes',len(r.get('faltantes',[])),
                  'absorbidos',len(r.get('absorbidos',[])), 'jerarquia',len(r.get('jerarquia',[])),
                  'vacios',len(r.get('vacios',[])), 'pendientes',len(r.get('candidatos_pendientes',[])), flush=True)
    finally:
        con.close()
    resumen = dict(base=str(base), solo_lectura=True, normas=len(resultados), correctas=sum(r['correcta'] for r in resultados), resultados=resultados,
                   alcance='Estructura extraída del texto; no certifica fidelidad, fórmulas ni páginas sin capa textual.')
    args.salida.write_text(json.dumps(resumen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CORRECTAS',resumen['correctas'],'/',resumen['normas'])
    return 0 if resumen['correctas'] == resumen['normas'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
