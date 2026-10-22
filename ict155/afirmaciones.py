"""Public CI documentation."""
from __future__ import annotations
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from . import almacen, comillas, config, consulta, fundamento, historial_boe, interruptores, relacionados, sucesion, vigencia
from .contexto import RE_NORMA
OK, AVISO, ERROR = ('OK', 'AVISO', 'ERROR')
TIPOS_DE_CITA = ('identificador', 'literal', 'cotejo', 'paginas', 'subruta', 'norma', 'vigencia')
SIN_COMPROBAR = 'sin_comprobar'
AVISOS_QUE_LA_OPINION_APAGA = ('negacion', 'consejo', 'absoluto', SIN_COMPROBAR)
RE_CERCADO = re.compile('(?ms)^[ \\t]*```.*?^[ \\t]*```[ \\t]*$')
RE_LINEA_DE_CITA = re.compile('(?m)^[ \\t]*>.*$')
RE_COMILLAS_EN_LINEA = re.compile('«[^»\\n]+»|“[^”\\n]+”|\\"[^\\"\\n]{8,}\\"')
RE_TITULO = re.compile('^\\s{0,3}(#{1,6})\\s+(.*?)\\s*#*\\s*$')
RE_SOLO_NEGRITA = re.compile('^\\s*(?:\\*\\*|__)(.+?)(?:\\*\\*|__)\\s*:?\\s*$')
RE_SEPARADOR_DE_TABLA = re.compile('^\\s*\\|?\\s*:?-{2,}:?\\s*(\\|\\s*:?-{2,}:?\\s*)*\\|?\\s*$')
_MARCAS_DE_LINEA = '[ \\t>*_`#•\\-]*'
RE_SELLO = re.compile('(?i)^' + _MARCAS_DE_LINEA + 'comprobado\\s+por\\s+la\\s+base\\s*:?[*_]*\\s*\\d+\\s+(?:citas?\\s+comprobadas?|correctas?)\\b|^' + _MARCAS_DE_LINEA + '\\[sello:\\s*[0-9a-f]{8}\\]\\s*$')
RE_LINEA_DE_BASE = re.compile('(?i)^' + _MARCAS_DE_LINEA + 'base:\\s*huella\\s+(?:[0-9a-f]{8}|\\?),\\s*(?:\\d+|\\?)\\s+preceptos\\.?\\s*$')
RE_ROTULO_DE_OPINION = re.compile('(?i)^\\W*(?:\\d+[.)]\\s*)?(opini[óo]n|lectura\\s+de\\s+ict155|valoraci[óo]n)\\b')
RE_ROTULO_EN_LINEA = re.compile('(?i)^\\W*(?:opini[óo]n|lectura\\s+de\\s+ict155|valoraci[óo]n)[^.:]{0,40}[.:)\\*]')
RE_MARCA_DE_OPINION_AL_FINAL = re.compile('(?i)\\(\\s*opini[óo]n\\s*\\)\\s*[.!?)»\\"]*\\s*$')
RE_ABREVIATURA = re.compile('(?i)\\b(?:art|arts|apdo|apdos|apart|núm|n[º°o]|pág|págs|pp|p|ap|aprox|cap|etc|ej|vs|sr|sra|dr|dra|ud|uds|tel|dpto|cfr|cf|sec|vol|ed|sig|ss|ref|dir|pto|ptos|fig|tab)\\.$')
RE_FIN_DE_FRASE = re.compile('(?<=[.!?…])(?:\\*\\*|__|[*_»”\\"\')\\]])*\\s+(?=[A-ZÁÉÍÓÚÑ¿¡«“\\"(\\[*_`§])')
RE_IDENT_EN_TEXTO = re.compile('`[^`\\n]{1,200}?::[^`\\n]+?`|(?:BOE-A-\\d{4}-\\d+|CELEX-[0-9A-Z]+|ICT155-[\\w.\\-]+)::[\\w.\\-/ñ]+')

@dataclass
class Frase:
    ini: int
    fin: int
    texto: str
    linea: int
    parrafo: int
    opinion: bool = False

def _enmascarar(texto: str) -> str:
    """Public CI documentation."""
    m = texto
    for r in (RE_CERCADO, RE_LINEA_DE_CITA):
        m = r.sub(lambda x: re.sub('[^\\n]', ' ', x.group(0)), m)
    partes, desde = ([], 0)
    for a, b in comillas.tramos(m):
        partes.extend((m[desde:a], '§' * (b - a)))
        desde = b
    return ''.join(partes) + m[desde:]

def _limpiar(s: str) -> str:
    s = RE_IDENT_EN_TEXTO.sub('ID', s)
    s = re.sub('§+', '«…»', s)
    s = re.sub('\\*\\*|__|`', '', s)
    s = re.sub('(?<![\\w*])\\*(?=\\S)([^*\\n]+?)(?<=\\S)\\*(?![\\w*])', '\\1', s)
    s = re.sub('^\\s*(?:[-*+•]\\s+|\\d{1,2}[.)]\\s+)', '', s)
    s = s.replace('|', ' ; ')
    return ' '.join(s.split()).strip(' ;')

def _frases_de_una_linea(linea: str, base: int) -> list[tuple[int, int]]:
    """Public CI documentation."""
    cortes = [0]
    for m in RE_FIN_DE_FRASE.finditer(linea):
        if RE_ABREVIATURA.search(linea[max(0, m.start() - 8):m.start()]):
            continue
        cortes.append(m.end())
    cortes.append(len(linea))
    salida = []
    for a, b in zip(cortes, cortes[1:]):
        trozo = linea[a:b]
        if trozo.strip():
            salida.append((base + a + len(trozo) - len(trozo.lstrip()), base + a + len(trozo.rstrip())))
    return salida

def frases_del_borrador(borrador: str) -> list[Frase]:
    """Public CI documentation."""
    mascara = _enmascarar(borrador)
    frases: list[Frase] = []
    parrafo, previa_en_blanco, off = (0, True, 0)
    estado: tuple[str, int] | None = None
    opinion_de_parrafo = False
    lineas, mascaras = (borrador.split('\n'), mascara.split('\n'))
    for n, (linea, lm) in enumerate(zip(lineas, mascaras), 1):
        inicio = off
        off += len(linea) + 1
        if not lm.strip():
            if not previa_en_blanco:
                parrafo += 1
            previa_en_blanco, opinion_de_parrafo = (True, False)
            continue
        previa_en_blanco = False
        if RE_SELLO.match(linea) or RE_SEPARADOR_DE_TABLA.match(lm):
            continue
        if n < len(mascaras) and lm.lstrip().startswith('|') and RE_SEPARADOR_DE_TABLA.match(mascaras[n]):
            continue
        t = RE_TITULO.match(linea)
        negrita = RE_SOLO_NEGRITA.match(linea)
        if t:
            nivel, rotulo = (len(t.group(1)), t.group(2))
            if RE_ROTULO_DE_OPINION.match(rotulo):
                estado = ('t', nivel)
            elif not (estado and estado[0] == 't' and (nivel > estado[1])):
                estado = None
            parrafo += 1
            continue
        if negrita and len(negrita.group(1)) <= 90 and (not negrita.group(1).rstrip().endswith(('.', '!', '?'))):
            if RE_ROTULO_DE_OPINION.match(negrita.group(1)):
                estado = ('n', 0)
            elif estado and estado[0] == 'n':
                estado = None
            continue
        plano = re.sub('^\\s*(?:[-*+•]\\s+|\\d{1,2}[.)]\\s+)?(?:\\*\\*|__)?', '', linea)
        if RE_ROTULO_EN_LINEA.match(plano):
            opinion_de_parrafo = True
        en_opinion = bool(estado) or opinion_de_parrafo
        for a, b in _frases_de_una_linea(lm, inicio):
            limpia = _limpiar(lm[a - inicio:b - inicio])
            if len(limpia) < 3:
                continue
            frases.append(Frase(a, b, limpia, n, parrafo, en_opinion or bool(RE_MARCA_DE_OPINION_AL_FINAL.search(borrador[a:b]))))
    return frases
RE_NOMBRE_DE_NORMA = re.compile('(?i)\\b(?:orden|real\\s+decreto(?:\\s+legislativo)?|rd|rdl|ley|reglamento|directiva|decreto|decisi[óo]n|resoluci[óo]n)\\s+(?:\\((?:ce|ue)\\)\\s*)?(?:n\\.?[º°o]\\s*)?(?:[A-Z]{2,4}/)?\\d+(?:/\\d+)?|\\b[A-Z]{2,4}/\\d{1,5}/\\d{4}\\b|\\b(?:orden|ley|real\\s+decreto|reglamento)\\s+de\\s+(?:\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+)?\\d{4}\\b|\\b(?:UNE-)?EN\\s?\\d{3,}|\\bISO(?:/IEC)?\\s+\\d+|\\bWELMEC\\b|\\bOIML\\b|\\bILAC\\b|\\bGUM\\b|\\bVIM\\b|\\bMID\\b|\\bRSIF\\b|\\bRITE\\b|\\b(?:la|el|esta|este|dicha|dicho)\\s+(?:norma|orden|ley|reglamento|directiva|real\\s+decreto)\\b')
RE_REFERENCIA_A_PRECEPTO = re.compile('(?i)\\b(?:art[íi]culos?\\s+\\d|arts?\\.\\s*\\d|apartados?\\s+\\d|anexos?\\s+(?:[IVXLC]+|\\d+)\\b|ap[ée]ndices?\\s+(?:[IVXLC]+|\\d+)\\b|disposici[óo]n\\s+(?:adicional|transitoria|derogatoria|final)|cap[íi]tulo\\s+[IVXLC]+\\b|cl[áa]usula\\s+\\d|IF-\\d{2}\\b|tabla\\s+\\d)')
RE_VERBO_FUERTE = re.compile('(?i)\\b(?:obliga\\w*|obligatori\\w+|obligaci\\w+|exig\\w+|prohib\\w+|prohíb\\w+|establec\\w+|dispon\\w+|dispuest\\w+|derog\\w+|derecho\\s+muerto|ya\\s+no\\s+rige\\w*|obsolet\\w+|modific\\w+|sustitu\\w+|vigent\\w+|vigencia|en\\s+vigor|no\\s+(?:podr[áa]n?|puede|pueden)|deber[áa]n?|tiene(?:n)?\\s+que|sanci\\w+|infracci\\w+|multa\\w*|inhabilit\\w+)')
RE_VERBO_DEBIL = re.compile('(?i)\\b(?:plazo\\w*|permit\\w+|autoriz\\w+|fij\\w+|regul\\w+|aplic\\w+|incumpl\\w+|cumpl\\w+|verificaci[óo]n(?:es)?\\s+peri[óo]dic\\w+|control\\s+metrol[óo]gic\\w+|etiqueta\\w*|precint\\w+|certificad\\w+|conform\\w+|debe(?:n)?\\s+(?:ser|estar|tener|cumplir|hacer|realizar|solicitar|colocar|comunicar|conservar|mantener|someter|superar)|puede(?:n)?\\s+(?:usarse|utilizarse|acogerse))')
RE_CANTIDAD = re.compile('(?i)\\b(?:\\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|doce|treinta|cuarenta|sesenta|noventa)\\s+(?:d[ií]as|meses|a[ñn]os|horas|semanas)\\b|\\bcada\\s+(?:\\w+\\s+){0,2}(?:a[ñn]os?|meses|d[ií]as)\\b|\\b(?:anual|bienal|semestral)(?:es|mente)?\\b')
RE_ANUNCIO = re.compile('(?i)^\\W*(?:responsable,?\\s*)?(?:aqu[ií]\\s+(?:tienes|va)|esto\\s+es\\s+(?:lo\\s+que|un\\s+borrador)|te\\s+dejo|a\\s+continuaci[óo]n|lo\\s+que\\s+(?:dice|sigue)|todo\\s+es\\s+borrador|queda\\s+as[ií]|as[ií]\\s+(?:est[áa]|es|son|queda)\\s+[^.?!:]{0,90}:\\W*$|(?:he|hemos)\\s+(?:comprobado|consultado|revisado|le[ií]do|buscado|mirado|verificado|cotejado)\\b)')
RE_EXHAUSTIVO = re.compile('(?i)\\b(?:la|el|las|los)\\s+[úu]nic[oa]s?\\b|\\bno\\s+hay\\s+otr[oa]s?\\b|\\bninguna\\s+otra\\b|\\bsolo\\s+hay\\b')
RE_DE_LA_BASE_O_LA_NORMA = re.compile('(?i)\\b(?:la\\s+base|la\\s+norma|la\\s+orden|el\\s+reglamento|el\\s+real\\s+decreto|la\\s+ley|cl[áa]usula|apartado|precepto|art[íi]culo)\\b')
RE_ESTADO_DEL_TEXTO = re.compile('(?i)\\b(?:arrastra|lleva\\s+(?:pegad[oa]|delante|detr[aá]s)|sale\\s+(?:desordenad|aplanad|mezclad|cortad|pegad)\\w*|aparece\\s+(?:pegad|mezclad)\\w*|trae\\s+pegad\\w*|(?:texto|ficha)\\s+(?:de\\s+la\\s+base\\s+)?(?:est[áa]|sale)\\s+(?:truncad|cortad|incomplet)\\w*)')
RE_DEBE = re.compile('(?i)\\b(?:debe(?:n)?|puede(?:n)?|ha(?:n)?\\s+de|solicitar[áa]|realizar[áa]|colocar[áa])\\b')
RE_LIMITE_PROPIO = re.compile('(?i)^\\W*(?:responsable,?\\s*)?(?:(?:no\\s+)?(?:he|hemos)\\s+(?:revisado|comprobado|le[ií]do|mirado|consultado|verificado|cotejado|podido|visto|buscado|intentado|probado|abierto)\\b|no\\s+puedo\\s+(?:comprobar|afirmar|citar|decir|asegurar|confirmar|darte|ense[ñn]arte)\\b|no\\s+tengo\\b|lo\\s+normativo\\s+est[áa]\\s+sacado\\b|fuera\\s+de\\s+la\\s+base\\b|(?:lo\\s+he|las?\\s+he|los\\s+he)\\s+(?:buscado|consultado|comprobado|le[ií]do|mirado)\\b|(?:busqu[ée]|consult[ée]|mir[ée])\\b|no\\s+sé\\b|por\\s+eso\\s+no\\s+puedo\\b|no\\s+he\\s+(?:analizado)\\b)')
RE_LIMITE_EN_LA_FRASE = re.compile('(?i)\\bno\\s+(?:la|lo|las|los)\\s+he\\s+(?:consultado|revisado|mirado|comprobado|analizado|le[ií]do)\\b|\\bno\\s+he\\s+(?:analizado|mirado|le[ií]do)\\b')
RE_VERBO_FINITO = re.compile('(?i)\\b(?:es|son|est[áa]n?|ser[áa]n?|establece[n]?|dice[n]?|dispone[n]?|exige[n]?|obliga[n]?|proh[ií]be[n]?|fija[n]?|regula[n]?|remite[n]?|permite[n]?|deroga[n]?|modifica[n]?|puede[n]?|debe[n]?|tiene[n]?|hay|incluye[n]?|contiene[n]?|recoge[n]?)\\b')
RE_OFERTA = re.compile('(?i)^\\W*(?:responsable,?\\s*)?(?:si\\s+(?:quieres|lo\\s+necesitas|prefieres|me\\s+(?:das|dices|pasas|confirmas))\\b|d[ií]me\\b|p[ée]game\\b|p[áa]same\\b|av[ií]same\\b|puedo\\s+(?:citarte|mirar|buscar|revisar|prepararte|ense[ñn]arte)\\b|te\\s+(?:cito|dejo|preparo|paso|propongo|ense[ñn]o)\\b|entonces\\s+te\\b|ind[ií]came\\b|dime\\b|que\\s+(?:te\\s+)?\\w+(?:ras|ses)\\b)')
RE_ROTULO_INTERROGATIVO = re.compile('(?i)^\\W*(?:qu[ée]|c[óo]mo|cu[áa]ndo|qui[ée]n|d[óo]nde|por\\s+qu[ée]|cu[áa]nto|cu[áa]l)\\b[^?!:]{0,110}:\\W*$')
RE_DELEGACION = re.compile('(?i)\\b(?:lo\\s+decides\\s+t[úu]|(?:es\\s+)?(?:una\\s+)?cuesti[óo]n\\s+de\\s+criterio(?:\\s+tuy[oa])?|tu\\s+criterio\\s+manda|habr[ií]a\\s+que\\s+(?:ver|mirar|comprobar|confirmar|revisar)|hay\\s+que\\s+(?:ver|saber|mirar|comprobar|confirmar))\\b')
RE_ROTULO_DE_PRECEPTO = re.compile('(?i)^\\W*(?:apartado|anexo|ap[ée]ndice|art[íi]culo|cap[íi]tulo|tabla|cl[áa]usula|disposici[óo]n\\s+\\w+)\\s+[\\w.]+(?:\\s*,\\s*(?:apartado|ap[ée]ndice|tabla|letra)\\s+[\\w.]+)*\\s*(?:[:–\\-]\\s+[^.;:]{0,170})?[.:]?\\W*$')
_FECHA_DE_HECHO = '(?:\\d{1,2}[/-]\\d{1,2}[/-]\\d{4}|\\d{4}-\\d{2}-\\d{2}|\\d{1,2}\\s+de\\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\\s+de\\s+\\d{4})'
_ORIGEN_DE_HECHO = '(?:seg[úu]n\\s+el\\s+cliente,\\s*|el\\s+cliente\\s+declara\\s+que\\s+|en\\s+el\\s+expediente\\s+consta\\s+que\\s+)'
_EQUIPO_DE_HECHO = '(?:el\\s+equipo|el\\s+registrador)'
RE_HECHOS_DEL_CASO = tuple((re.compile(p + '\\.?', re.I) for p in ('(?:tu\\s+decisi[óo]n|la\\s+decisi[óo]n\\s+de\\s+Responsable)(?:\\s+\\(sesi[óo]n\\s+\\d+,\\s*pregunta\\s+\\d+\\))?\\s+fue\\s+(?:exigir|pedir|solicitar)\\s+(?:prueba|evidencia)\\s+documental\\s+de\\s+que\\s+' + _EQUIPO_DE_HECHO + '\\s+estaba\\s+(?:de\\s+verdad\\s+)?en\\s+servicio\\s+(?:a|el)\\s+' + _FECHA_DE_HECHO + '(?:,\\s*porque\\s+la\\s+instalaci[óo]n\\s+no\\s+basta)?', 'Responsable\\s+decidi[óo]\\s+(?:exigir|pedir|solicitar)\\s+(?:prueba|evidencia)\\s+documental\\s+de\\s+que\\s+' + _EQUIPO_DE_HECHO + '\\s+estaba\\s+(?:de\\s+verdad\\s+)?en\\s+servicio\\s+(?:a|el)\\s+' + _FECHA_DE_HECHO + '(?:,\\s*porque\\s+la\\s+instalaci[óo]n\\s+no\\s+basta)?', _ORIGEN_DE_HECHO + _EQUIPO_DE_HECHO + '\\s+dispone\\s+de\\s+un\\s+certificado\\s+de\\s+verificaci[óo]n\\s+peri[óo]dica\\s+fechado\\s+el\\s+' + _FECHA_DE_HECHO, _ORIGEN_DE_HECHO + 'la\\s+[úu]ltima\\s+verificaci[óo]n\\s+peri[óo]dica\\s+se\\s+realiz[óo]\\s+(?:el\\s+' + _FECHA_DE_HECHO + '|hace\\s+(?:\\d{1,4}|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|doce)\\s+(?:a[ñn]os?|meses?|d[ií]as?))')))

def es_hecho_del_caso(limpia: str) -> bool:
    """Public CI documentation."""
    return any((p.fullmatch(limpia.strip()) for p in RE_HECHOS_DEL_CASO))

def es_normativa(limpia: str) -> bool:
    """Public CI documentation."""
    if limpia.rstrip().endswith('?') or len(limpia.split()) < 5:
        return False
    if re.sub('[\\sID;,.:()\\-–0-9pPsS]', '', limpia) == '':
        return False
    if es_hecho_del_caso(limpia):
        return False
    niega = RE_NEGACION_DE_LA_NORMA.search(limpia) or RE_NEGACION_DE_LA_BASE.search(limpia) or re.search('(?i)\\bno\\s+(?:aparece|figura|existe|hay|est[áa]n?|consta)\\b', limpia)
    if (RE_LIMITE_PROPIO.match(limpia) or RE_OFERTA.match(limpia)) and (not niega):
        return False
    if RE_ROTULO_INTERROGATIVO.match(limpia):
        return False
    if RE_DELEGACION.search(limpia) and (not niega):
        return False
    fuerte = RE_VERBO_FUERTE.search(limpia)
    if RE_LIMITE_EN_LA_FRASE.search(limpia) and (not fuerte) and (not niega):
        return False
    if RE_ROTULO_DE_PRECEPTO.match(limpia) and (not RE_DEBE.search(limpia)) and (not RE_VERBO_FINITO.search(limpia)):
        return False
    if RE_ANUNCIO.match(limpia) and (not fuerte):
        return False
    debiles = {m.group(0).lower() for m in RE_VERBO_DEBIL.finditer(limpia)} | ({'cantidad'} if RE_CANTIDAD.search(limpia) else set())
    nombra = RE_NOMBRE_DE_NORMA.search(limpia)
    exhaustiva = RE_EXHAUSTIVO.search(limpia) and RE_DE_LA_BASE_O_LA_NORMA.search(limpia)
    de_ella = nombra and (RE_NEGACION_DE_LA_NORMA.search(limpia) or RE_REFUTACION.search(limpia) or RE_CONSEJO.search(limpia))
    return bool(fuerte or RE_REFERENCIA_A_PRECEPTO.search(limpia) or (nombra and debiles) or (len(debiles) >= 2) or exhaustiva or RE_ESTADO_DEL_TEXTO.search(limpia) or de_ella)
RE_EXCLUSIVIDAD = re.compile('(?i)\\b(?:s[óo]lo|solamente|[úu]nicamente|exclusivamente)\\b|\\bla\\s+[úu]nica\\s+(?:norma|obra|fuente|vez|sede)\\b|\\bno\\s+aparece\\s+en\\s+ninguna\\s+otra\\b')
RE_DEROGACION = re.compile('(?i)\\bderogad[ao]s?\\b|\\bderecho\\s+muerto\\b|\\bya\\s+no\\s+(?:rige|rigen|vale|valen|est[áa]n?\\s+en\\s+vigor|se\\s+aplica)\\b|\\bno\\s+(?:est[áa]n?|es|son)\\s+(?:ya\\s+)?(?:en\\s+vigor|vigentes?)\\b|\\bdej[óo]\\s+de\\s+(?:estar\\s+)?(?:vigente|aplicarse|regir)\\b|\\bsin\\s+vigencia\\b|\\bobsolet[ao]s?\\b')
RE_DEROGA_ACTIVA = re.compile('(?i)\\bderog(?:a|ó|an|aron|ando)\\b')
RE_DERECHO_MUERTO = re.compile('(?i)\\bderecho\\s+muerto\\b|\\bya\\s+no\\s+(?:rige|rigen|vale|valen|se\\s+aplica)\\b|\\bobsolet[ao]s?\\b|\\bno\\s+sirve\\b|\\bno\\s+se\\s+puede\\s+citar\\b')
RE_VIGENTE = re.compile('(?i)\\b(?:est[áa]n?\\s+(?:plenamente\\s+)?vigentes?|siguen?\\s+(?:plenamente\\s+)?(?:vigentes?|en\\s+vigor)|se\\s+mantiene(?:n)?\\s+vigentes?|(?:es|son)\\s+(?:la\\s+)?(?:norma\\s+)?vigentes?|norma\\s+vigente|texto\\s+(?:consolidado\\s+)?vigente|est[áa]\\s+en\\s+vigor|(?:figura|figuran|consta|constan|aparece|aparecen)\\s+como\\s+vigentes?|da(?:n)?\\s+(?:por|como)\\s+vigentes?|vigente\\s+(?:desde|hasta|en\\s+la\\s+versi[óo]n))\\b')
RE_NEGADOR_ANTES = re.compile('(?i)\\b(?:no|ya\\s+no|dej[óo]\\s+de|nunca)\\s+(?:\\w+\\s+){0,2}$')
RE_PARCIAL = re.compile('(?i)\\bparcial\\w*|\\bderog\\w+\\s+(?:el|los)\\s+art')
RE_MODIFICA = re.compile('(?i)\\b(?:modific(?:a|an|ó|aron|ada|ado|adas|ados)|reform(?:a|ó|aron|ada)|enmend(?:ó|aron|ada)|actualiz(?:a|ó|aron|ada)|reescrib(?:e|ió|en)|a[ñn]adi(?:ó|eron)|introdujo|introdujeron|redact(?:ó|aron)|nueva\\s+redacci[óo]n)\\b')
RE_PASIVA_POR = re.compile('(?i)\\b(?:modificad[ao]s?|reformad[ao]s?|enmendad[ao]s?|actualizad[ao]s?)\\s+por\\b')
RE_ANAFORA_DE_NORMAS = re.compile('(?i)\\b(?:las\\s+dos|los\\s+dos|ambas|ambos|la\\s+de\\s+\\d{4}|la\\s+primera|la\\s+segunda|esta|[ée]sta|aquella|todas|es[ae]\\s+(?:orden|norma|ley|disposici[óo]n|reglamento|decreto)|dicha\\s+\\w+|a\\s+su\\s+vez)\\b')
RE_CAUSAL = re.compile('(?i)\\bporque\\b|\\bya\\s+que\\b|\\bgracias\\s+a\\b|\\bdebido\\s+a\\b|\\bpor\\s+(?:la|el)\\s+(?:reforma|modificaci[óo]n|cambio)\\b|\\btras\\s+(?:la|el)\\s+(?:reforma|modificaci[óo]n|cambio)\\b')
RE_CAMBIO_DE_CONTENIDO = re.compile('(?i)\\b(?:ya|ahora)\\s+(?:dice|establece|fija|exige|recoge|incluye|contiene|prev[eé]|es\\s+de)\\b|\\bantes\\s+(?:dec[ií]a|establec[ií]a|fijaba|exig[ií]a|era)\\b|\\bpas[óo]\\s+a\\b|\\bsubi[óo]\\b|\\bse\\s+(?:ampli[óo]|redujo|elev[óo]|endureci[óo])\\b|\\bcambi[óo]\\s+(?:de|el|la|su)\\b')
RE_NEGACION_DE_LA_BASE = re.compile('(?i)\\bla\\s+base\\s+no\\s+(?:tiene|contiene|recoge|incluye|dispone\\s+de|trae|cuenta\\s+con)\\b|\\bno\\s+(?:est[áa]n?|figura(?:n)?|consta(?:n)?|aparece(?:n)?|existe(?:n)?|hay)\\s+(?:\\w+\\s+){0,4}?en\\s+la\\s+base\\b|\\bno\\s+est[áa]n?\\s+trocead[ao]s?\\b|\\bno\\s+(?:la|lo|las|los)\\s+tiene\\s+la\\s+base\\b')
RE_NEGACION_DE_LA_NORMA = re.compile('(?i)\\bno\\s+(?:dice|dicen|regula|regulan|prev[eé]n?|establece|establecen|fija|fijan|define|definen|contiene|contienen|recoge|recogen|menciona|mencionan|incluye|incluyen|indica|indican|exige|exigen|obliga|obligan|impone|imponen|proh[ií]be|proh[ií]ben|especifica|especifican|aclara|determina|se\\s+pronuncia|hay\\s+(?:ning[úu]n|art[íi]culo|apartado|precepto|norma|obligaci[óo]n|plazo)|existe(?:n)?\\s+(?:ning[úu]n|art[íi]culo|apartado|precepto|norma|obligaci[óo]n|plazo)|tiene(?:n)?\\s+(?:un|una|ning[úu]n|ninguna)\\s+(?:art[íi]culo|apartado|precepto|norma|obligaci[óo]n))\\b|\\bninguna?\\s+(?:norma|obligaci[óo]n|precepto|art[íi]culo|apartado)\\b|\\bsin\\s+(?:ninguna?\\s+)?(?:consecuencia|sanci[óo]n)s?\\b|\\bno\\s+por\\s+\\w+|\\bno\\s+(?:tiene|tienen|conlleva|conllevan|implica|implican|supone|suponen|trae|traen)\\s+(?:consecuencias?|sanci[óo]n|efectos?|pena|multa|responsabilidad)\\b')
RE_NEGACION_DE_LA_BASE_DIRECTA = re.compile('(?i)^la\\s+base\\s+no\\b')
RE_NEGACION_BASE_R27 = re.compile('(?i)\\bla\\s+base\\s+no\\s+(?:tiene|contiene|recoge|incluye|dispone\\s+de|trae|cuenta\\s+con|resuelve|regula|trata|cubre)\\b|\\bno\\s+(?:est[áa]n?|figura(?:n)?|consta(?:n)?|aparec(?:e|en|i[óo]|ieron)|existe(?:n)?|hay|resuelve(?:n)?|regula(?:n)?|trata(?:n)?|cubre(?:n)?)\\s+(?:\\w+\\s+){0,4}?en\\s+la\\s+base\\b|\\bno\\s+est[áa]n?\\s+trocead[ao]s?\\b|\\bno\\s+(?:la|lo|las|los)\\s+tiene\\s+la\\s+base\\b')
RE_NEGACION_APLICABILIDAD_R27 = re.compile('(?i)\\bno\\s+se\\s+aplica(?:n)?\\b|\\bno\\s+(?:es|son)\\s+obligatori[ao]s?\\b|\\bno\\s+obliga(?:n)?\\b')
RE_DECLARA_BUSQUEDA_R27 = re.compile('(?i)\\bb[uú]squedas?\\s+(?:hechas?|realizadas?)\\s+en\\s+la\\s+base\\b|(?<!no\\s)\\b(?:busqu[ée]|he\\s+buscado|buscando|busco)\\b[^.\\n]{0,120}?\\ben\\s+la\\s+base\\b|\\ben\\s+la\\s+base\\b[^.\\n]{0,80}?(?<!no\\s)\\b(?:busqu[ée]|he\\s+buscado|buscando|busco)\\b|`?normativa_(?:buscar|obras|cita)`?')
RE_NO_DECLARA_BUSQUEDA_R27 = re.compile('(?i)\\bno\\s+(?:he\\s+|hemos\\s+)?buscad[oa]\\b|\\bno\\s+busqu[ée]\\b|\\bsin\\s+buscar\\b|\\bno\\s+(?:he\\s+|hemos\\s+)?us[ée]\\b[^.\\n]{0,60}?\\bnormativa_(?:buscar|obras|cita)\\b|\\bno\\s+se\\s+(?:ha\\s+|han\\s+)?utiliz[óo]\\b[^.\\n]{0,60}?\\bnormativa_(?:buscar|obras|cita)\\b|\\b(?:deber[ií]as|deber[ií]an|recomiendo|recomendable|conviene|convendr[ií]a|habr[ií]a\\s+que|podr[ií]as?|puedes)\\b[^.\\n]{0,60}?\\bnormativa_(?:buscar|obras|cita)\\b|\\bnormativa_(?:buscar|obras|cita)\\b[^.\\n]{0,40}?\\b(?:despu[ée]s|m[áa]s\\s+tarde|si\\s+hiciera\\s+falta|si\\s+fuera\\s+necesario|en\\s+el\\s+futuro|la\\s+pr[óo]xima\\s+vez)\\b')
RE_RELLENO_DE_LISTA = re.compile('(?i)(?:[\\s,]|\\b(?:y|e|o|ni|siquiera|tampoco|como\\s+obra|como\\s+norma|completos?|completas?|enteros?|enteras?|el|la|los|las|norma|obra|de|del)\\b)*')
RE_RELLENO_TRAS_LA_NORMA = re.compile('(?i)[\\s,]*(?:\\b(?:tampoco|todav[ií]a|a[uú]n|ya|siquiera)\\b[\\s,]*)*')
RE_REFUTACION = re.compile('(?i)\\bte\\s+(?:lo|la|los|las)\\s+pueden\\s+(?:rebatir|discutir|impugnar)\\b|\\bte\\s+pueden\\s+(?:rebatir|discutir)\\b|\\bno\\s+(?:se\\s+)?sostiene\\b|\\bno\\s+es\\s+(?:cierto|verdad)\\s+que\\b|\\bes\\s+falso\\s+que\\b|\\bno\\s+puedes\\s+(?:decir|afirmar)\\b|\\bno\\s+se\\s+puede\\s+(?:decir|afirmar)\\b')
RE_CONSEJO = re.compile('(?i)\\b(?:dej(?:a|ar|es)\\s+de\\s+(?:apoyarte|citar|usar|utilizar|aplicar|referirte)|puedes\\s+dejar\\s+de|ya\\s+no\\s+(?:hace\\s+falta|es\\s+necesario|necesitas|tienes\\s+que|hay\\s+que)|no\\s+hace\\s+falta\\s+(?:ya\\s+)?(?:citar|usar|apoyarte)|en\\s+lugar\\s+de\\s+(?:citar|usar|apoyarte)|en\\s+vez\\s+de\\s+(?:citar|usar|apoyarte)|sustituye\\s+a|puedes\\s+(?:prescindir|olvidarte)|conviene\\s+(?:dejar|sustituir|cambiar|actualizar|citar|usar|reformular|poner)|te\\s+recomiendo|recomiendo\\s+(?:citar|usar|sustituir)|mejor\\s+(?:citar|usar|apoyarte)|puedes\\s+citar\\s+directamente|deber[ií]as|lo\\s+(?:m[áa]s\\s+)?(?:limpio|prudente|mejor|recomendable|seguro|sensato)\\s+es)\\b')
RE_EMPIRICO = re.compile('(?i)\\b(?:la\\s+(?:frase|norma|cita|forma)\\s+que\\s+m[áa]s\\s+se\\s+(?:usa|cita)|la\\s+que\\s+m[áa]s\\s+(?:se\\s+)?(?:usa|cita)|m[áa]s\\s+se\\s+usa|casi\\s+nadie|todo\\s+el\\s+mundo|la\\s+m[áa]s\\s+(?:usada|habitual|com[úu]n|citada))\\b')
RE_ABSOLUTO = re.compile('(?i)\\b(?:siempre|nunca|jam[áa]s|en\\s+ning[úu]n\\s+caso|sin\\s+excepci[óo]n|cualquier|todos\\s+los|todas\\s+las|ning[úu]n|ninguna?|la\\s+[úu]nica|el\\s+[úu]nico|casi\\s+nadie|todo\\s+el\\s+mundo|la\\s+que\\s+m[áa]s|la\\s+m[áa]s\\s+(?:usada|habitual|com[úu]n)|m[áa]s\\s+se\\s+usa|por\\s+completo)\\b')
RE_TERMINOS_JURIDICOS_CON_UNICA = re.compile('(?i)\\b(?:disposici[óo]n\\s+\\w+\\s+[úu]nica|[úu]nica\\s+disposici[óo]n|derogatoria\\s+[úu]nica|final\\s+[úu]nica|transitoria\\s+[úu]nica|adicional\\s+[úu]nica|art[íi]culo\\s+[úu]nico)\\b')
RE_FECHA_NUMERICA = re.compile('\\b(\\d{1,2})[/-](\\d{1,2})[/-](\\d{4})\\b')
RE_FECHA_LARGA = re.compile('(?i)\\b(\\d{1,2})\\s+de\\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\\s+de\\s+(\\d{4})\\b')
MESES = {m: i for i, m in enumerate(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'], 1)}
MESES['setiembre'] = 9
RE_FECHA_DE_EFECTO = re.compile('(?i)\\b(?:el|desde\\s+el|con\\s+efectos?(?:\\s+desde)?\\s+el|a\\s+partir\\s+del)\\s+$')
RE_NUMERO_SUELTO = re.compile('(?<![\\w/.])((?:19|20)\\d{2}/\\d{1,4}|\\d{1,4}/(?:19|20)\\d{2})(?![\\w/])')
RE_ES_AGENTE = re.compile('(?i)\\bpor\\s+(?:la|el|los|las)?\\s*(?:(?:nueva|presente|citada|vigente|propia)\\s+)?$')
RE_ORDEN_DE_ANIO = re.compile('(?i)\\b(Orden|Real\\s+Decreto|Ley|Reglamento|Decreto)\\s+de(?:l)?\\s+(?:\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+)?(\\d{4})\\b')
RE_CODIGO_DE_ORDEN = re.compile('(?<![\\w/])([A-Z]{2,4}/\\d{1,5}/\\d{4})(?![\\w/])')
RE_NORMA_NUMERADA = re.compile('(?i)\\b(Reglamento|Directiva|Decisi[óo]n|Ley|Real\\s+Decreto)\\s+(?:\\((?:CE|UE)\\)\\s*)?(?:n\\.?[º°o]\\s*)?(\\d+/\\d+(?:/[A-Z]{2})?)')
CALIFICADORES_DE_PARTE = re.compile('(?i)\\b(?:art[íi]culo|apartado|anexo|ap[ée]ndice|texto|cap[íi]tulo|cl[áa]usula|punto|control|versi[óo]n|edici[óo]n|traducci[óo]n|ejemplar|tabla|figura|ecuaci[óo]n|disposici[óo]n|secci[óo]n|parte|letra)\\b')
RE_SOLO_IDENTIFICADORES = re.compile('[\\sID;,.:()\\-–0-9]|\\bpp?\\.?\\b|p[áa]ginas?', re.I)

@dataclass
class Resultado:
    """Public CI documentation."""
    comprobaciones: list = field(default_factory=list)
    verificada: bool = False
    no_comprobable: bool = False
    refutada: bool = False
    derogacion_dicha: bool = False

@dataclass
class Cobertura:
    """Public CI documentation."""
    normativas: int = 0
    comprobadas: int = 0
    sin_comprobar: int = 0
    opinion: int = 0
    refutadas: int = 0

    def dict(self) -> dict:
        return {'normativas': self.normativas, 'comprobadas': self.comprobadas, 'sin_comprobar': self.sin_comprobar, 'opinion': self.opinion, 'refutadas': self.refutadas}

class Analizador:

    def __init__(self, con: sqlite3.Connection, borrador: str, idents, resueltos, estado_literal, bloques, ambitos, datos_vigencia: dict | None, hoy: str | None, tabla_sucesion: list[dict] | None, datos_historial: dict | None=None):
        from . import revision
        self.rev = revision
        self.con, self.borrador, self.idents, self.resueltos = (con, borrador, idents, resueltos)
        self.estado_literal, self.bloques, self.ambitos = (estado_literal, bloques, ambitos)
        self.datos, self.hoy = (datos_vigencia, hoy)
        self.historial = datos_historial
        self.tabla = sucesion.cargar() if tabla_sucesion is None else tabla_sucesion
        self.tabla_relacionados = relacionados.cargar()
        self._nombres: dict[str, str | None] = {}
        self._vig: dict[str, dict | None] = {}
        self._titulos: dict[str, str] = {}
        self._nombradas: dict[tuple, list[tuple[int, str]]] = {}
        self._ausentes: dict[str, bool] = {}
        self._corpus = None
        self.pares_por_parrafo: dict[int, list[dict]] = {}
        self.grupos_dichos: set[str] = set()
        self._r27_limites: dict[str, list[re.Pattern]] | None = None

    def _obra_de(self, nombre: str) -> str | None:
        clave = ' '.join(nombre.split())
        if clave not in self._nombres:
            r = consulta.resolver(self.con, clave, self.ambitos)
            self._nombres[clave] = r.obra if r.obra and r.estado != consulta.NO_CONSTA else None
        return self._nombres[clave]

    def _obra_por_orden_de_anio(self, tipo: str, anio: str) -> str | None:
        clave = f'{tipo.lower()}|{anio}'
        if clave not in self._nombres:
            filas = self.con.execute('SELECT identificador_canonico FROM obra WHERE titulo LIKE ? COLLATE NOCASE', (f'{tipo} de %{anio}%',)).fetchall()
            self._nombres[clave] = filas[0][0] if len(filas) == 1 else None
        return self._nombres[clave]

    def _obra_por_numero(self, numero: str) -> str | None:
        """Public CI documentation."""
        clave = f'num|{numero}'
        if clave not in self._nombres:
            obras, _otras, _no = vigencia.obras_de_la_norma(self.con, numero)
            self._nombres[clave] = obras[0] if len(obras) == 1 else None
        return self._nombres[clave]

    def obras_nombradas(self, limpia: str, ini: int=0, fin: int=0) -> list[tuple[int, str]]:
        """Public CI documentation."""
        clave = (limpia, ini, fin)
        if clave in self._nombradas:
            return self._nombradas[clave]
        hallazgos: list[tuple[int, str]] = []
        for a, b, ident in self.idents:
            if ini <= a < fin and ident in self.resueltos and self.resueltos[ident][0].obra:
                hallazgos.append((-1, self.resueltos[ident][0].obra))
        for patron, prefijo in ((RE_NORMA, ''), (RE_NORMA_NUMERADA, '')):
            for m in patron.finditer(limpia):
                o = self._obra_de(m.group(0))
                if o:
                    hallazgos.append((m.start(), o))
        for m in RE_CODIGO_DE_ORDEN.finditer(limpia):
            o = self._obra_de('Orden ' + m.group(1)) or self._obra_de(m.group(1))
            if o:
                hallazgos.append((m.start(), o))
        for m in RE_ORDEN_DE_ANIO.finditer(limpia):
            o = self._obra_por_orden_de_anio(m.group(1), m.group(2))
            if o:
                hallazgos.append((m.start(), o))
        for m in RE_NUMERO_SUELTO.finditer(limpia):
            o = self._obra_por_numero(m.group(1))
            if o:
                hallazgos.append((m.start(), o))
        vistas, salida = (set(), [])
        for pos, o in sorted(hallazgos):
            if o not in vistas:
                vistas.add(o)
                salida.append((pos, o))
        self._nombradas[clave] = salida
        return salida

    def vig(self, obra: str) -> dict | None:
        if obra not in self._vig:
            self._vig[obra] = vigencia.vigencia_de(obra, self.datos, self.hoy)
        return self._vig[obra]

    def registro(self, obra: str) -> dict | None:
        return ((self.datos or {}).get('obras') or {}).get(obra)

    def titulo(self, obra: str) -> str:
        if obra not in self._titulos:
            f = self.con.execute('SELECT titulo FROM obra WHERE identificador_canonico=?', (obra,)).fetchone()
            self._titulos[obra] = f[0] or '' if f else ''
        return self._titulos[obra]

    def nombre_corto(self, obra: str) -> str:
        f = self.con.execute('SELECT a.alias FROM obra_alias a JOIN obra o ON o.id=a.obra_id WHERE o.identificador_canonico=? AND a.alias != o.identificador_canonico ORDER BY length(a.alias) LIMIT 1', (obra,)).fetchone()
        return f'{f[0]} ({obra})' if f else obra

    def modifica(self, x: str, y: str) -> str | None:
        """Public CI documentation."""
        reg = self.registro(y)
        ofic_x = vigencia.identificador_oficial(x)
        if reg and ofic_x and (ofic_x in {m.get('id') for m in (reg.get('consulta') or {}).get('modificaciones') or []}):
            return 'vigencia'
        tit = fundamento.normalizar(self.titulo(x))
        if 'modific' in tit:
            alias = [r[0] for r in self.con.execute('SELECT a.alias_norm FROM obra_alias a JOIN obra o ON o.id=a.obra_id WHERE o.identificador_canonico=?', (y,))]
            if any((len(a) >= 6 and re.search('\\d', a) and (a in tit) for a in alias)):
                return 'titulo'
            ofic_y = vigencia.identificador_oficial(y)
            if ofic_y and any((n.replace('/', ' ') in tit for n in vigencia.numeros_de_la_norma(ofic_y, self.titulo(y)))):
                return 'titulo'
        return None

    def _ids_en(self, a: int, b: int) -> list[str]:
        return [x for p, q, x in self.idents if a <= p < b]

    def _obras_de_ids(self, ids: list[str]) -> set[str]:
        return {self.resueltos[x][0].obra for x in ids if x in self.resueltos and self.resueltos[x][0].obra}

    def gobierno(self, f: Frase, frases: list[Frase], i: int) -> list[str]:
        """Public CI documentation."""
        propios = self._ids_en(f.ini, f.fin)
        if propios:
            return list(dict.fromkeys(propios))
        nombradas = {o for _p, o in self.obras_nombradas(f.texto)}

        def coherente(ids: list[str]) -> list[str]:
            return ids if ids and (not nombradas or nombradas <= self._obras_de_ids(ids)) else []
        vecinas = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(frases) and frases[j].linea == f.linea:
                vecinas += self._ids_en(frases[j].ini, frases[j].fin)
        gob = coherente(list(dict.fromkeys(vecinas)))
        if gob:
            return gob
        for k, (a, b) in enumerate(self.bloques):
            if a <= f.ini <= b and k:
                a0, b0 = self.bloques[k - 1]
                previo = self.borrador[a0:b0].strip()
                if previo and '\n' not in previo:
                    gob = coherente(list(dict.fromkeys(self._ids_en(a0, b0))))
                    if gob:
                        return gob
                break
        siguiente = frases[i + 1] if i + 1 < len(frases) else None
        if siguiente is not None and siguiente.parrafo == f.parrafo:
            return []
        fin_linea = self.borrador.find('\n', f.fin)
        if self.borrador[f.fin:fin_linea if fin_linea >= 0 else len(self.borrador)].strip():
            return []
        k = next((n for n, (a, b) in enumerate(self.bloques) if a <= f.ini <= b), None)
        if k is None:
            return []
        for j in (k + 1, k + 2):
            if j >= len(self.bloques):
                return []
            a, b = self.bloques[j]
            parrafo = self.borrador[a:b]
            if all((l.lstrip().startswith('>') for l in parrafo.split('\n') if l.strip())):
                continue
            ids = self._ids_en(a, b)
            if '\n' not in parrafo.strip() and ids and (len(RE_SOLO_IDENTIFICADORES.sub(' ', RE_IDENT_EN_TEXTO.sub('', parrafo)).split()) <= 3):
                return coherente(list(dict.fromkeys(ids)))
            return []
        return []

    def contexto_de(self, i: int, frases: list[Frase], gob: list[str]) -> tuple[list[str], list[str]]:
        """Public CI documentation."""
        f = frases[i]
        idents = [x for a, b, x in self.idents if f.ini <= a < f.fin] + list(gob)
        previas = [g for g in frases[max(0, i - 2):i] if g.parrafo == f.parrafo]
        for g in previas:
            idents += [x for a, b, x in self.idents if g.ini <= a < g.fin]
        obras: list[str] = []
        for x in dict.fromkeys(idents):
            r = self.resueltos.get(x, (None, ''))[0]
            if r is not None and r.obra and (r.obra not in obras):
                obras.append(r.obra)
        for g in [f] + previas:
            for _p, o in self.obras_nombradas(g.texto, g.ini, g.fin):
                if o not in obras:
                    obras.append(o)
        return (list(dict.fromkeys(idents)), obras)

    def _c(self, nivel, tipo, f: Frase, detalle: str, ident=None):
        return self.rev.Comprobacion(nivel, tipo, self.rev._corta(f.texto), detalle, ident, f.linea)

    def _literales_de(self, f: Frase) -> list[tuple[int, int]]:
        return [(a + f.ini, b + f.ini) for a, b in comillas.tramos(self.borrador[f.ini:f.fin])]

    def fechas_de_efecto(self, limpia: str) -> list[str]:
        salida = []
        for m in RE_FECHA_NUMERICA.finditer(limpia):
            if RE_FECHA_DE_EFECTO.search(limpia[max(0, m.start() - 22):m.start()]):
                salida.append(f'{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}')
        for m in RE_FECHA_LARGA.finditer(limpia):
            if RE_FECHA_DE_EFECTO.search(limpia[max(0, m.start() - 22):m.start()]):
                salida.append(f'{int(m.group(3)):04d}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}')
        return salida

    def sucesores_de_los_preceptos(self, idents: list[str], parrafo: int) -> list[dict]:
        """Public CI documentation."""
        pares: list[dict] = list(self.pares_por_parrafo.get(parrafo, []))
        for x in idents:
            r = self.resueltos.get(x, (None, ''))[0]
            if r is not None and r.obra:
                for p in sucesion.sucesores_de(r.obra, consulta.partir_identificador(x)[1], self.tabla):
                    if p not in pares:
                        pares.append(p)
        return pares

    def exclusividad(self, f: Frase, res: Resultado):
        m = RE_EXCLUSIVIDAD.search(f.texto)
        if not m:
            return
        grandes = [(a, b) for a, b in self._literales_de(f) if len(fundamento.normalizar(self.borrador[a + 1:b - 1]).split()) >= fundamento.MINIMO_PALABRAS]
        if not grandes:
            return
        buscada = self.borrador[grandes[0][0] + 1:grandes[0][1] - 1]
        aguja = fundamento.normalizar(buscada)
        if self._corpus is None:
            self._corpus = fundamento._corpus(self.con)
        holders: dict[str, list[str]] = {}
        for ident, _t, ruta, _e, _pi, _pf, texto, _al in self._corpus:
            if aguja in texto:
                holders.setdefault(vigencia.identificador_oficial(ident) or ident, []).append(f'{ident}::{ruta}')
        resto = re.split('(?i)\\b(?:y\\s+no|ni|no\\s+en)\\b', f.texto[m.end():].replace('«…»', ' '))[0]
        nombradas = {vigencia.identificador_oficial(o) or o for _p, o in self.obras_nombradas(resto)}
        if not nombradas:
            nombradas = {vigencia.identificador_oficial(o) or o for _p, o in self.obras_nombradas('', f.ini, f.fin)}
        etiqueta = '«' + self.rev._corta(buscada, 60) + '»'
        lista = lambda fams: ', '.join(sorted(fams))
        if not holders:
            res.comprobaciones.append(self._c(ERROR, 'exclusividad', f, f'{etiqueta} no está literal en ninguna obra de la base: no puede existir solo en las que la frase nombra'))
            res.refutada = True
            return
        if not nombradas:
            res.comprobaciones.append(self._c(AVISO, 'exclusividad', f, f'la frase dice que {etiqueta} solo está en algún sitio, pero no nombra una obra que la base reconozca: la base la tiene en {lista(holders)}. Cita las obras.'))
            res.no_comprobable = True
            return
        de_mas, de_menos = (set(holders) - nombradas, nombradas - set(holders))
        if de_mas or de_menos:
            partes = []
            if de_menos:
                partes.append(f'no está en {lista(de_menos)}, que la frase nombra')
            if de_mas:
                partes.append(f'NO solo está ahí: la base la tiene también en {lista(de_mas)} (por ejemplo ' + '; '.join((holders[o][0] for o in sorted(de_mas))) + ')')
            res.comprobaciones.append(self._c(ERROR, 'exclusividad', f, f'{etiqueta} ' + '; '.join(partes)))
            res.refutada = True
            return
        donde = ', '.join((h for o in sorted(holders) for h in holders[o][:2]))
        res.comprobaciones.append(self._c(OK, 'exclusividad', f, f'{etiqueta} está exactamente en {lista(holders)} ({donde}): coincide con las obras que la frase nombra'))
        res.verificada = True
        pares: list[dict] = []
        for o in holders:
            for h in holders[o]:
                obra, _, ruta = h.partition('::')
                for p in sucesion.sucesores_de(obra, ruta, self.tabla):
                    if p not in pares:
                        pares.append(p)
        if pares:
            self.pares_por_parrafo.setdefault(f.parrafo, []).extend((p for p in pares if p not in self.pares_por_parrafo.get(f.parrafo, [])))
        if all(((self.vig(o) or {}).get('estado') == 'derogada' for o in holders)):
            res.derogacion_dicha = True
            if pares:
                res.comprobaciones.append(self._c(AVISO, 'derogacion', f, 'todas las obras donde está esa frase constan DEROGADAS, pero su contenido sigue en: ' + sucesion.frase(pares) + '. Dilo en la respuesta.'))
            else:
                res.comprobaciones.append(self._c(AVISO, 'derogacion', f, 'todas las obras donde está esa frase constan DEROGADAS; no consta contenido equivalente en la tabla revisada de sucesión (eso no prueba que no lo haya).'))

    def derogacion_y_vigencia(self, f: Frase, res: Resultado, idents: list[str], obras: list[str]):
        propias = [o for _p, o in self.obras_nombradas(f.texto, f.ini, f.fin)]
        activa = RE_DEROGA_ACTIVA.search(f.texto)
        if activa and len(propias) >= 2:
            self._deroga_a(f, res, activa)
            return
        deroga = RE_DEROGACION.search(f.texto)
        vigente = next((m for m in RE_VIGENTE.finditer(f.texto) if not RE_NEGADOR_ANTES.search(f.texto[max(0, m.start() - 24):m.start()])), None)
        if not deroga and (not vigente):
            return
        agentes = {o for p, o in self.obras_nombradas(f.texto, f.ini, f.fin) if p > 0 and RE_ES_AGENTE.search(f.texto[max(0, p - 24):p])}
        sujeto_propio = [o for o in propias if o not in agentes]
        obras_todas, obras = (obras, [o for o in obras if o not in agentes])
        marca = deroga or vigente
        inmediato = None
        for p, o in self.obras_nombradas(f.texto, f.ini, f.fin):
            if 0 <= p < marca.start() and marca.start() - p <= 90 and (o not in agentes):
                inmediato = o
        anaforico = deroga and RE_ANAFORA_DE_NORMAS.search(f.texto)
        sujetos = [inmediato] if inmediato and (not anaforico) else list(dict.fromkeys(propias + obras_todas)) if anaforico else sujeto_propio or obras
        candidatas = [o for o in sujetos if self.vig(o) and self.vig(o).get('estado') is not None]
        if not candidatas:
            return
        derogadas = [o for o in candidatas if self.vig(o)['estado'] == 'derogada']
        vigentes = [o for o in candidatas if self.vig(o)['estado'] != 'derogada']
        explicito = inmediato is not None and candidatas == [inmediato]
        if deroga:
            if not derogadas:
                if activa:
                    return
                posterior = [o for o in vigentes if any((a.startswith(('DEROGACIÓN posterior', 'posible DEROGACIÓN', 'DEROGACIÓN posterior aprobada')) for a in self.vig(o)['avisos']))]
                if posterior:
                    res.comprobaciones.append(self._c(AVISO, 'derogacion', f, f"{self.nombre_corto(posterior[0])} consta {self.vig(posterior[0])['estado']}, con una derogación posterior que la consulta anota (puede tener efecto diferido y ser parcial): " + next((a for a in self.vig(posterior[0])['avisos'] if 'DEROGACIÓN' in a))[:230] + '. Lee el acto antes de fechar la derogación.', posterior[0]))
                    res.no_comprobable = True
                    return
                nivel = ERROR if explicito and (not RE_PARCIAL.search(f.texto)) else AVISO
                res.comprobaciones.append(self._c(nivel, 'derogacion', f, f"la frase da por derogada a {self.nombre_corto(vigentes[0])}, y la consulta de vigencia guardada la da por {self.vig(vigentes[0])['estado'].upper()}" + (' (la derogación puede ser parcial: léela en la fuente)' if nivel == AVISO else ''), vigentes[0]))
                res.refutada, res.no_comprobable = (nivel == ERROR, nivel == AVISO)
                return
            relatos = []
            for o in derogadas:
                v = self.vig(o)
                relatos.append(f"{self.nombre_corto(o)} consta DEROGADA el {v.get('fecha_derogacion') or '?'} por " + (', '.join((d.get('id') or '?' for d in v.get('derogada_por') or [])) or 'norma no indicada'))
            fechas = self.fechas_de_efecto(f.texto)
            if fechas and (not set(fechas) <= {self.vig(o).get('fecha_derogacion') for o in derogadas}):
                res.comprobaciones.append(self._c(AVISO, 'derogacion', f, '; '.join(relatos) + f". Las fechas de la frase ({', '.join(fechas)}) no coinciden con las de la consulta guardada."))
                res.no_comprobable = True
                return
            oficiales_nombradas = {vigencia.identificador_oficial(o) or o for o in propias}
            nombra_al_que_deroga = all(({d.get('id') for d in self.vig(o).get('derogada_por') or []} and {d.get('id') for d in self.vig(o).get('derogada_por') or []} <= oficiales_nombradas for o in derogadas))
            muerto = bool(RE_DERECHO_MUERTO.search(f.texto))
            if nombra_al_que_deroga and (not muerto):
                res.comprobaciones.append(self._c(OK, 'derogacion', f, '; '.join(relatos) + ': coincide con lo que dice la frase'))
                res.verificada = True
                return
            if res.derogacion_dicha and (not muerto):
                res.verificada = True
                return
            pares = self.sucesores_de_los_preceptos(idents, f.parrafo)
            suc = ' Contenido equivalente vigente: ' + sucesion.frase(pares) + '.' if pares else ' No consta contenido equivalente en la tabla revisada de sucesión (eso no prueba que no lo haya).'
            cola = ' Dilo en la respuesta' + (': «derecho muerto» y similares no valen mientras el contenido siga vigente.' if pares and muerto else '.')
            res.comprobaciones.append(self._c(AVISO, 'derogacion', f, '; '.join(relatos) + '. La norma está derogada, pero su contenido puede seguir en otro sitio.' + suc + cola))
            if muerto:
                res.no_comprobable = True
            else:
                res.verificada = True
            return
        if derogadas:
            nivel = ERROR if explicito else AVISO
            v = self.vig(derogadas[0])
            res.comprobaciones.append(self._c(nivel, 'vigencia_afirmada', f, f"la frase da por vigente a {self.nombre_corto(derogadas[0])}, que consta DEROGADA el {v.get('fecha_derogacion') or '?'} por {', '.join((d.get('id') or '?' for d in v.get('derogada_por') or [])) or 'norma no indicada'}" + ('' if explicito else ' (la frase nombra más normas: puede referirse a otra)'), derogadas[0]))
            res.refutada, res.no_comprobable = (nivel == ERROR, nivel == AVISO)
            return
        con_avisos = [o for o in candidatas if self.vig(o)['avisos']]
        if con_avisos:
            v = self.vig(con_avisos[0])
            res.comprobaciones.append(self._c(AVISO, 'vigencia_afirmada', f, f"{self.nombre_corto(con_avisos[0])} consta {v['estado']}, pero: " + '; '.join(v['avisos'][:2]) + '. Dilo.', con_avisos[0]))
            res.no_comprobable = True
            return
        v = self.vig(candidatas[0])
        res.comprobaciones.append(self._c(OK, 'vigencia_afirmada', f, ', '.join((self.nombre_corto(o) for o in candidatas[:3])) + f" {('consta' if len(candidatas) == 1 else 'constan')} {v['estado']}{('' if len(candidatas) == 1 else 's')} en la consulta de vigencia del {(v.get('consultado') or '?')[:10]}, sin modificaciones posteriores a la versión de la base", candidatas[0]))
        res.verificada = True

    def _deroga_a(self, f: Frase, res: Resultado, activa):
        """Public CI documentation."""
        nombradas = self.obras_nombradas(f.texto, f.ini, f.fin)
        posibles = [o for p, o in nombradas if p >= 0]
        antes = [o for p, o in nombradas if 0 <= p < activa.start()]
        despues = [o for p, o in nombradas if p > activa.end()]
        if not antes or not despues:
            return
        x, y = (antes[-1], despues[0])
        vy = self.vig(y)
        derogantes = {d.get('id') for d in (vy or {}).get('derogada_por') or []}
        if vy and vy.get('estado') == 'derogada' and ((vigencia.identificador_oficial(x) or x) in derogantes):
            res.comprobaciones.append(self._c(OK, 'derogacion', f, f"la consulta de vigencia dice que {self.nombre_corto(y)} fue derogada el {vy.get('fecha_derogacion') or '?'} por {self.nombre_corto(x)}"))
            res.verificada = True
        else:
            estado = (vy or {}).get('estado') or 'sin consulta'
            res.comprobaciones.append(self._c(AVISO, 'derogacion', f, f'la base no confirma que {self.nombre_corto(x)} derogue a {self.nombre_corto(y)} (consta {estado}' + (f", derogada por {', '.join(sorted((d for d in derogantes if d)))}" if derogantes else '') + '). Si la derogación es parcial o con efecto diferido, léelo en el acto.'))
            res.no_comprobable = True

    def historial_de_la_frase(self, f: Frase, x: str, y: str) -> tuple[str | None, str]:
        """Public CI documentation."""
        x_oficial = vigencia.identificador_oficial(x)
        if self.historial is None or not x_oficial or (not vigencia.RE_BASE_BOE.match(x_oficial)) or (not vigencia.RE_BASE_BOE.match(y)):
            return (None, '')
        rutas = [r for r in dict.fromkeys((consulta.partir_identificador(i)[1] for i in self._ids_en(f.ini, f.fin) if '::' in i and i in self.resueltos and (self.resueltos[i][0] is not None) and (self.resueltos[i][0].obra == y))) if r]
        confirman, contradicen, sin_decir = ([], [], [])
        for ruta in rutas:
            h = historial_boe.historial_de(y, ruta, self.historial, con=self.con, hoy=self.hoy)
            if not h or h['estado'] != historial_boe.ESTADO_OK or h['ascendiente']:
                sin_decir.append(ruta)
                continue
            dieron = [r for r in h['redacciones'] if not r['original']]
            suya = [r for r in dieron if r['id_norma'] == x_oficial]
            (confirman if suya else contradicen).append((ruta, h, dieron, suya))
        if sin_decir or not (confirman or contradicen) or (confirman and contradicen):
            return (None, '')
        if confirman:
            partes = []
            for ruta, h, _dieron, suya in confirman:
                r = suya[-1]
                es_la_vigente = h['redacciones'].index(r) == h.get('vigente')
                partes.append(f"el historial de redacciones del BOE de {y}::{ruta} lista a {self.nombre_corto(x)} entre quienes dieron sus redacciones ({('dio la redacción vigente' if es_la_vigente else 'dio una redacción anterior a la vigente')}, vigente desde {r.get('fecha_vigencia') or r.get('fecha_publicacion') or '?'})")
            return ('confirma', '; '.join(partes))
        partes = []
        for ruta, _h, dieron, _suya in contradicen:
            quienes = ', '.join((r['cita_como'] or r['id_norma'] for r in dieron)) or 'ninguna: es la redacción original, sin modificaciones'
            partes.append(f'el historial de redacciones del BOE de {y}::{ruta} NO lista a {self.nombre_corto(x)} entre quienes dieron sus redacciones ({quienes})')
        return ('contradice', '; '.join(partes) + '. La frase dice que esa norma modificó el precepto y el BOE no lo confirma: corrígela, o nombra la norma que dio la redacción (normativa_cita del precepto la dice).')

    def modificacion_y_causalidad(self, f: Frase, res: Resultado, idents: list[str], obras: list[str]):
        modifica = RE_MODIFICA.search(f.texto)
        causal = RE_CAUSAL.search(f.texto)
        cambio = RE_CAMBIO_DE_CONTENIDO.search(f.texto)
        nombradas = self.obras_nombradas(f.texto, f.ini, f.fin)
        if not modifica:
            if causal and (cambio or any((p >= causal.end() - 1 for p, _o in nombradas))):
                res.comprobaciones.append(self._c(AVISO, 'modificacion', f, 'causalidad o cambio de contenido: la base guarda la versión consolidada de cada norma y no puede confirmar por qué un precepto dice lo que dice ni que antes dijera otra cosa. Márcalo como opinión o cita el acto y deja sin explicar el porqué.'))
                res.no_comprobable = True
            return
        pasiva = RE_PASIVA_POR.search(f.texto)
        if pasiva:
            antes = [o for p, o in nombradas if 0 <= p < pasiva.start()]
            despues = [o for p, o in nombradas if p >= pasiva.end() - 3]
            y, x = (antes[-1] if antes else None, despues[0] if despues else None)
        else:
            antes = [o for p, o in nombradas if 0 <= p < modifica.start()]
            despues = [o for p, o in nombradas if p > modifica.end()]
            x, y = (antes[-1] if antes else None, despues[0] if despues else None)
        if y is None:
            y = next((o for o in obras if o != x), None)
        if not x or not y:
            res.comprobaciones.append(self._c(AVISO, 'modificacion', f, 'dice que una norma modifica algo, pero no se reconoce qué norma modifica ni cuál es modificada: nómbralas o cita sus identificadores para poder comprobarlo.'))
            res.no_comprobable = True
            return
        veredicto, del_historial = self.historial_de_la_frase(f, x, y)
        if veredicto == 'contradice':
            res.comprobaciones.append(self._c(ERROR, 'modificacion', f, del_historial))
            res.refutada = True
            return
        rel = self.modifica(x, y) or ('historial' if veredicto == 'confirma' else None)
        if not rel:
            res.comprobaciones.append(self._c(AVISO, 'modificacion', f, f'la base no confirma que {self.nombre_corto(x)} modifique a {self.nombre_corto(y)} (ni la consulta de vigencia ni el título del acto lo dicen). No lo presentes como comprobado.'))
            res.no_comprobable = True
            return
        confirma = f'la base confirma que {self.nombre_corto(x)} modifica a {self.nombre_corto(y)}'
        rutas_y = [consulta.partir_identificador(i)[1] for i in idents if self.resueltos.get(i, (None, ''))[0] is not None and self.resueltos[i][0].obra == y and ('::' in i)]
        trae = ''
        for ruta in rutas_y:
            r = consulta.resolver(self.con, f'{x}::{ruta}', self.ambitos)
            if r.estado == consulta.ENCONTRADO:
                trae = f" y trae {x}::{ruta} con su redacción ({r.paginas or 'páginas ?'})"
                break
        contenido = cambio or causal or re.search('(?i)\\b(?:ese|dicho|este)\\s+(?:apartado|art[íi]culo|anexo|precepto)\\b', f.texto)
        if veredicto == 'confirma' and (not contenido):
            res.comprobaciones.append(self._c(OK, 'modificacion', f, f'{confirma} ({del_historial})'))
            res.verificada = True
        elif contenido or rutas_y:
            res.comprobaciones.append(self._c(AVISO, 'modificacion', f, confirma + trae + '. NO puede confirmar qué decía antes ni que el contenido cambiara: la base solo tiene la versión consolidada (más el acto como norma propia). El cambio de contenido o su causa es opinión, no comprobado.' + (f' Lo que sí consta: {del_historial}.' if veredicto == 'confirma' else '')))
            res.no_comprobable = True
        else:
            res.comprobaciones.append(self._c(OK, 'modificacion', f, confirma + ' (por ' + ('la consulta de vigencia' if rel == 'vigencia' else 'su título') + ')'))
            res.verificada = True

    @staticmethod
    def _nombres_de_norma(texto: str) -> list[str]:
        """Public CI documentation."""
        vistos: list[str] = []
        for patron in (RE_NORMA, RE_NORMA_NUMERADA):
            for m in patron.finditer(texto):
                n = ' '.join(m.group(0).split())
                if n not in vistos:
                    vistos.append(n)
        return vistos

    def _norma_ausente(self, nombre: str) -> bool:
        """Public CI documentation."""
        if nombre not in self._ausentes:
            self._ausentes[nombre] = consulta.resolver(self.con, nombre, self.ambitos).estado == consulta.NO_CONSTA
        return self._ausentes[nombre]

    def _normas_que_niega(self, texto: str, base: re.Match) -> tuple[list[str], list[str]]:
        """Public CI documentation."""
        nombradas = self._nombres_de_norma(texto)
        negadas: list[str] = []
        if RE_NEGACION_DE_LA_BASE_DIRECTA.match(base.group(0)):
            pos = base.end()
            while True:
                pos = RE_RELLENO_DE_LISTA.match(texto, pos).end()
                m = RE_NORMA.match(texto, pos) or RE_NORMA_NUMERADA.match(texto, pos)
                if not m:
                    break
                negadas.append(' '.join(m.group(0).split()))
                pos = m.end()
        else:
            antes = texto[:base.start()]
            previas = [m for p in (RE_NORMA, RE_NORMA_NUMERADA) for m in p.finditer(antes)]
            if previas:
                ultima = max(previas, key=lambda m: m.end())
                if RE_RELLENO_TRAS_LA_NORMA.fullmatch(antes[ultima.end():]):
                    negadas.append(' '.join(ultima.group(0).split()))
        return (negadas, nombradas)

    def _ausencia_de_normas(self, f: Frase, res: Resultado, base: re.Match) -> bool:
        """Public CI documentation."""
        negadas, nombradas = self._normas_que_niega(f.texto, base)
        if not negadas:
            return False
        for n in negadas:
            if self._norma_ausente(n):
                continue
            r = consulta.resolver(self.con, n, self.ambitos)
            if not r.obra:
                continue
            completa = self.con.execute("SELECT count(*) FROM precepto p JOIN version v ON v.id=p.version_id JOIN obra ob ON ob.id=v.obra_id WHERE ob.identificador_canonico=? AND v.completitud='completa'", (r.obra,)).fetchone()[0]
            if completa:
                res.comprobaciones.append(self._c(ERROR, 'negacion', f, f'la frase dice que la base no tiene a {self.nombre_corto(r.obra)}, y la base SÍ tiene esa obra completa ({completa} preceptos): no es verdad', r.obra))
                res.refutada = True
                return True
        if not all((self._norma_ausente(n) for n in negadas)):
            return False
        lista = ', '.join((f'«{n}»' for n in negadas))
        if all((self._norma_ausente(n) for n in nombradas)):
            res.comprobaciones.append(self._c(OK, 'ausencia', f, f'la base no tiene {lista}: la comprobación `norma` lo confirma (ninguna obra de la base se llama así). No dice nada de su contenido ni de su vigencia'))
            res.verificada = True
            return True
        res.comprobaciones.append(self._c(AVISO, 'negacion', f, f'la base no tiene {lista} (la comprobación `norma` lo confirma), pero la frase dice algo más de otras normas que la base sí tiene: cítalas con su identificador o márcalo como opinión.'))
        res.no_comprobable = True
        return True

    def negaciones(self, f: Frase, res: Resultado):
        base = RE_NEGACION_DE_LA_BASE.search(f.texto)
        norma = RE_NEGACION_DE_LA_NORMA.search(f.texto)
        refuta = RE_REFUTACION.search(f.texto)
        if not (base or norma or refuta):
            return
        if base and self._ausencia_de_normas(f, res, base):
            return
        if base:
            antes = f.texto[:base.start()]
            despues = f.texto[base.end():base.end() + 80]
            alcance = antes[-80:] + ' ' + despues[:60] if 'tiene' not in base.group(0) else despues[:60]
            for _p, o in self.obras_nombradas(alcance):
                if CALIFICADORES_DE_PARTE.search(alcance):
                    break
                completa = self.con.execute("SELECT count(*) FROM precepto p JOIN version v ON v.id=p.version_id JOIN obra ob ON ob.id=v.obra_id WHERE ob.identificador_canonico=? AND v.completitud='completa'", (o,)).fetchone()[0]
                if completa:
                    res.comprobaciones.append(self._c(ERROR, 'negacion', f, f'la frase dice que la base no tiene a {self.nombre_corto(o)}, y la base SÍ tiene esa obra completa ({completa} preceptos): no es verdad', o))
                    res.refutada = True
                    return
            res.comprobaciones.append(self._c(AVISO, 'negacion', f, 'negación sobre lo que tiene la base: el código no puede probar una ausencia. La respuesta debe decir qué buscó (herramienta y texto exacto, p. ej. normativa_buscar «…») o marcarlo como opinión.'))
            res.no_comprobable = True
            return
        if refuta and (not norma):
            res.comprobaciones.append(self._c(AVISO, 'negacion', f, 'valoración sobre lo que se puede rebatir o sostener: es interpretación, no comprobada. Cita el precepto que la apoya (y los que la matizan) o márcala como opinión.'))
            res.no_comprobable = True
            return
        res.comprobaciones.append(self._c(AVISO, 'negacion', f, 'afirma que la norma NO dice o NO tiene algo (o que algo no tiene consecuencia): es una ausencia, y el código no puede probarla. La respuesta debe decir qué buscó o citar lo que sí hay al lado; si es tu lectura, márcala como opinión.'))
        res.no_comprobable = True

    def _r27_ventana_parrafo(self, f: Frase) -> str:
        """Public CI documentation."""
        for a, b in self.bloques:
            if a <= f.ini <= b:
                return self.borrador[a:f.fin]
        return f.texto

    def _r27_cargar_limites(self) -> dict[str, list[re.Pattern]]:
        """Public CI documentation."""
        ruta_limites = config.REPO / 'cowork' / 'limites_conocidos.json'
        modo_almacen = almacen.modo_para(ruta_limites)
        if modo_almacen != 'apagado' or getattr(self, '_r28_limites_modo', 'apagado') != modo_almacen:
            self._r27_limites = None
        self._r28_limites_modo = modo_almacen
        if self._r27_limites is None:
            limites: dict[str, list[re.Pattern]] = {}
            descartados = 0
            try:
                datos = json.loads(almacen.leer(ruta_limites, encoding='utf-8', modo=modo_almacen))
                preceptos = datos.get('preceptos') if isinstance(datos, dict) else None
                if preceptos is None:
                    preceptos = []
                elif not isinstance(preceptos, list):
                    descartados += 1
                    preceptos = []
                for p in preceptos:
                    if not isinstance(p, dict):
                        continue
                    obra = p.get('obra')
                    if obra is not None and (not isinstance(obra, str)):
                        descartados += 1
                        continue
                    if not obra:
                        continue
                    ruta = p.get('ruta')
                    if ruta is not None and (not isinstance(ruta, str)):
                        descartados += 1
                        continue
                    try:
                        limites.setdefault(obra, []).append(re.compile(ruta or '.'))
                    except re.error:
                        descartados += 1
            except (OSError, ValueError):
                limites = {}
            if descartados:
                print(f'aviso: cowork/limites_conocidos.json tiene {descartados} precepto(s) con tipos inválidos; se descartan sin afectar a la revisión', file=sys.stderr)
            self._r27_limites = limites
        return self._r27_limites

    def _r27_hueco_documentado(self, obra: str, f: Frase | None=None) -> bool:
        """Public CI documentation."""
        limites = self._r27_cargar_limites()
        patrones = limites.get(obra)
        if not patrones:
            return False
        if f is not None:
            rutas_citadas = [ident.split('::', 1)[1] for a, b, ident in self.idents if f.ini <= a < f.fin and '::' in ident and (ident.split('::', 1)[0] == obra)]
            if rutas_citadas:
                return any((rx.search(ruta) for rx in patrones for ruta in rutas_citadas))
        return True

    def _r27_ruta_inexistente_en_obra_completa(self, f: Frase) -> bool:
        """Public CI documentation."""
        for a, b, ident in self.idents:
            if f.ini <= a < f.fin:
                r = self.resueltos.get(ident, (None, ''))[0]
                if r is not None and r.estado == consulta.PRECEPTO_INEXISTENTE:
                    return True
        return False

    @staticmethod
    def _r27_alcance_de_negacion(texto: str, m: re.Match) -> str:
        """Public CI documentation."""
        ini = texto.rfind(';', 0, m.start())
        ini = ini + 1 if ini != -1 else 0
        fin = texto.find(';', m.end())
        fin = fin if fin != -1 else len(texto)
        return texto[ini:fin]

    def _r27_respaldada(self, f: Frase) -> bool:
        """Public CI documentation."""
        ventana = self._r27_ventana_parrafo(f)
        if RE_DECLARA_BUSQUEDA_R27.search(ventana) and (not RE_NO_DECLARA_BUSQUEDA_R27.search(ventana)):
            return True
        if self._r27_ruta_inexistente_en_obra_completa(f):
            return True
        m = RE_NEGACION_BASE_R27.search(f.texto)
        alcance = self._r27_alcance_de_negacion(f.texto, m) if m else f.texto
        for n in self._nombres_de_norma(alcance):
            obra = self._obra_de(n)
            if obra and self._r27_hueco_documentado(obra, f):
                return True
            if self._norma_ausente(n):
                return True
        return False

    def _r27_negacion_base(self, frases: list[Frase], comprobaciones: list):
        """Public CI documentation."""
        modo = interruptores.modo('negacion_base')
        if modo == 'apagado':
            return
        for f in frases:
            if f.texto.rstrip().endswith('?'):
                continue
            negaciones = list(RE_NEGACION_BASE_R27.finditer(f.texto))
            if negaciones:
                tipos = []
                for m in negaciones:
                    antes = re.split('[;.!?]', f.texto[:m.start()])[-1]
                    if not re.match('(?i)la\\s+base\\s+no\\b', f.texto[m.start():]) and (not re.search('(?i)\\b(?:norma|ley|art[ií]culo|reglamento|precepto|plazo)\\b', antes)) and re.search('(?i)\\b(?:los hechos|las circunstancias|la intenci[oó]n)\\b[^;.!?]{0,70}$', antes):
                        tipos.append('hechos_privados')
                    elif re.match('(?i)la\\s+base\\s+no\\s+resuelve\\s+si\\b', f.texto[m.start():]):
                        tipos.append('interpretacion')
                    else:
                        tipos.append('sobre_base')
                tipo = 'sobre_base' if 'sobre_base' in tipos else tipos[0]
            elif RE_NEGACION_APLICABILIDAD_R27.search(f.texto):
                tipo = 'aplicabilidad'
            else:
                continue
            if tipo == 'sobre_base' and self._r27_respaldada(f):
                continue
            frase_corta = self.rev._corta(f.texto)
            if modo == 'bloquea' and tipo == 'sobre_base':
                comprobaciones.append(self._c(ERROR, 'negacion_base', f, f'NEGACIÓN SOBRE LA BASE SIN COMPROBAR: {frase_corta}; añade la búsqueda que hiciste o quítala'))
            else:
                interruptores.anotar_sombra('negacion_base', {'tipo': tipo, 'frase': frase_corta, 'linea': f.linea})

    def consejos(self, f: Frase, res: Resultado):
        if not RE_CONSEJO.search(f.texto):
            return
        extra = ''
        partes = []
        for _p, o in self.obras_nombradas(f.texto, f.ini, f.fin)[:3]:
            v = self.vig(o)
            if v and v.get('estado'):
                partes.append(f"{self.nombre_corto(o)} consta {v['estado'].upper()}" + (f" ({v['avisos'][0]})" if v['avisos'] else '') + f" en la consulta del {(v.get('consultado') or '?')[:10]}")
        if partes:
            extra = ' ' + '; '.join(partes) + ': el consejo no viene de la base.'
        res.comprobaciones.append(self._c(AVISO, 'consejo', f, 'consejo o cambio de criterio presentado en la respuesta: márcalo como opinión.' + extra))
        res.no_comprobable = True

    def absolutos(self, f: Frase, res: Resultado):
        limpio = RE_TERMINOS_JURIDICOS_CON_UNICA.sub(' ', f.texto)
        empirico = RE_EMPIRICO.search(limpio)
        if empirico:
            res.comprobaciones.append(self._c(AVISO, 'absoluto', f, f'afirmación sobre el uso o el conocimiento del sector («{empirico.group(0)}»): ninguna base normativa lo contiene. Quítala o márcala como opinión.'))
            res.no_comprobable = True
            return
        exhaustivo = RE_EXHAUSTIVO.search(limpio) if RE_DE_LA_BASE_O_LA_NORMA.search(limpio) else None
        if exhaustivo:
            res.comprobaciones.append(self._c(AVISO, 'absoluto', f, f'exhaustividad sobre la base o la norma («{exhaustivo.group(0)}»): el código no comprueba que no haya otra. Di en qué buscaste (normativa_buscar «…») o quítalo.'))
            res.no_comprobable = True
            return
        m = RE_ABSOLUTO.search(limpio)
        if m:
            res.comprobaciones.append(self._c(AVISO, 'absoluto', f, f'absoluto en una frase normativa («{m.group(0)}»): ¿lo dice así la norma o es tu lectura? Si no lo comprobaste en todo el texto, quítalo o márcalo como opinión.'))
        estado = RE_ESTADO_DEL_TEXTO.search(limpio)
        if estado:
            res.comprobaciones.append(self._c(AVISO, 'estado_del_texto', f, f'afirma un defecto del texto que guarda la base («{estado.group(0)}»): esos defectos cambian con cada reconstrucción de la base. Compruébalo con normativa_cita ahora y di la huella de la base, o no lo des por hecho.'))
            res.no_comprobable = True

    def habla_de_una_norma_que_la_base_no_tiene(self, f: Frase) -> bool:
        """Public CI documentation."""
        if len(f.texto.split()) < 5 or RE_LIMITE_PROPIO.match(f.texto) or RE_OFERTA.match(f.texto) or f.texto.rstrip().endswith('?'):
            return False
        for patron in (RE_NORMA, RE_NORMA_NUMERADA):
            for m in patron.finditer(f.texto):
                nombre = ' '.join(m.group(0).split())
                if self._obra_de(nombre) is None and consulta.resolver(self.con, nombre, self.ambitos).estado == consulta.NO_CONSTA:
                    return True
        return False

    def analizar(self, frases: list[Frase]):
        comprobaciones: list = []
        cobertura = Cobertura()
        for i, f in enumerate(frases):
            normativa = es_normativa(f.texto) or self.habla_de_una_norma_que_la_base_no_tiene(f)
            res = Resultado()
            gob: list[str] = []
            if normativa:
                gob = self.gobierno(f, frases, i)
                idents, obras = self.contexto_de(i, frases, gob)
                self.exclusividad(f, res)
                self.derogacion_y_vigencia(f, res, idents, obras)
                self.modificacion_y_causalidad(f, res, idents, obras)
                self.negaciones(f, res)
                self.consejos(f, res)
                self.absolutos(f, res)
            else:
                if RE_EXCLUSIVIDAD.search(f.texto):
                    self.exclusividad(f, res)
                if RE_NEGACION_DE_LA_BASE.search(f.texto):
                    self.negaciones(f, res)
            if not normativa and (not res.comprobaciones):
                continue
            cobertura.normativas += 1
            if not gob:
                gob = self.gobierno(f, frases, i)
            gobernada = any((self.resueltos.get(g, (None, ''))[0] is not None and self.resueltos[g][0].estado == consulta.ENCONTRADO for g in gob))
            literales_ok = all((self.estado_literal.get(a) in (None, OK) for a, _b in self._literales_de(f)))
            if f.opinion:
                comprobaciones += [c for c in res.comprobaciones if c.tipo not in AVISOS_QUE_LA_OPINION_APAGA]
                cobertura.opinion += 1
                continue
            comprobaciones += res.comprobaciones
            if res.refutada:
                cobertura.refutadas += 1
                continue
            if (gobernada or res.verificada) and literales_ok and (not res.no_comprobable):
                cobertura.comprobadas += 1
                continue
            cobertura.sin_comprobar += 1
            motivo = '; su cita tiene avisos o errores en un literal' if gobernada and (not literales_ok) else '; ninguna comprobación automática cubre lo que afirma' if res.no_comprobable else ''
            comprobaciones.append(self._c(AVISO, SIN_COMPROBAR, f, 'afirmación normativa sin comprobar' + motivo + ': cítala con su identificador `obra::ruta` en la misma frase (o en el encabezado de un renglón de encima) o márcala como opinión («(opinión)» al final o un bloque «Lectura de ICT155»).'))
            self.relacionados(f, comprobaciones)
        self._r27_negacion_base(frases, comprobaciones)
        return (comprobaciones, cobertura)

    def relacionados(self, f: Frase, salida: list):
        """Public CI documentation."""
        citados = [x for _a, _b, x in self.idents]
        for g in relacionados.que_grupos_tocan(f.texto, self.tabla_relacionados):
            if g['nombre'] in self.grupos_dichos:
                continue
            hallados = []
            for p in g['preceptos']:
                ident = p['identificador']
                if any((c == ident or c.startswith(ident + '.') or c.startswith(ident + '/') or ident.startswith(c + '.') or ident.startswith(c + '/') for c in citados)):
                    continue
                r = consulta.resolver(self.con, ident, self.ambitos)
                if r.estado == consulta.ENCONTRADO:
                    hallados.append(f"`{ident}` ({p['nota']})")
            if hallados:
                self.grupos_dichos.add(g['nombre'])
                salida.append(self._c(AVISO, 'relacionados', f, f"sobre {g['nombre']}, la base tiene también: " + '; '.join(hallados) + '. Léelos antes de afirmar que no hay consecuencia o cuál es: la respuesta no los cita.'))
