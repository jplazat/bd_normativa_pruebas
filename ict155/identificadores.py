"""Public CI documentation."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from . import consulta, contexto
from .parsers import fecha_es
RE_ID_BOE = re.compile('\\bBOE-A-\\d{4}-\\d{1,6}\\b')
RE_ID_CELEX = re.compile('\\bCELEX[\\s:\\-]*(3\\d{4}[A-Z]\\d{4})\\b')
RE_PAREN_TRAS_NORMA = re.compile('^(?:,?\\s+de\\s+\\d{1,2}\\s+de\\s+[a-zñáéíóú]+(?:\\s+de\\s+\\d{4})?)?\\s*\\(([^()]*)\\)')
RE_ENTRADA = contexto.RE_ENTRADA
RE_NUM_FECHA_CITADO = re.compile('[«\\"\']?BOE[»\\"\']?\\s*n[úu]m\\.?\\s*(\\d+)\\s*,?\\s*de\\s+(\\d{1,2}\\s+de\\s+[a-zñáéíóú]+\\s+de\\s+\\d{4})', re.I)
RE_PUBLICADO_EN = re.compile('Publicado\\s+en\\s*:?\\s*[«\\"\']?BOE[»\\"\']?\\s*n[úu]m\\.?\\s*(\\d+)\\s*,?\\s*de\\s+(\\d{1,2}\\s+de\\s+[a-zñáéíóú]+\\s+de\\s+\\d{4})', re.I)

@dataclass
class Defecto:
    linea: int
    norma: str
    citado: str
    de_la_base: str
    obra: str
    donde: str
    motivos: list[str] = field(default_factory=list)
    numero_citado: str | None = None
    numero_base: str | None = None
    fecha_citada: str | None = None
    fecha_base: str | None = None

    @property
    def motivo(self) -> str:
        return '; '.join(self.motivos)

@dataclass
class Resultado:
    comprobados: int = 0
    defectos: list[Defecto] = field(default_factory=list)
_MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')

def fecha_legible(iso: str) -> str:
    """Public CI documentation."""
    a, m, d = iso.split('-')
    return f'{int(d)} de {_MESES[int(m) - 1]} de {a}'

def _ids_de(texto: str) -> list[str]:
    """Public CI documentation."""
    vistos: list[tuple[int, str]] = [(m.start(), m.group(0)) for m in RE_ID_BOE.finditer(texto)]
    vistos += [(m.start(), f'CELEX-{m.group(1)}') for m in RE_ID_CELEX.finditer(texto)]
    return list(dict.fromkeys((i for _, i in sorted(vistos))))

def _nombres(texto: str) -> list[str]:
    return list(dict.fromkeys((' '.join(m.group(0).split()) for m in contexto.RE_NORMA.finditer(texto))))

def _entradas(lineas: list[str]) -> list[tuple[int, str, str]]:
    """Public CI documentation."""
    out, i = ([], 0)
    while i < len(lineas):
        m = RE_ENTRADA.match(lineas[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lineas) and lineas[j].strip() and (not RE_ENTRADA.match(lineas[j])):
            j += 1
        out.append((i + 1, m.group(1), ' '.join(lineas[i:j])))
        i = j
    return out

def _obra_unica(con, nombre: str):
    filas = consulta._obra_por_alias(con, nombre)
    ids = {f['id'] for f in filas}
    return filas[0] if len(ids) == 1 else None

def _publicaciones_de_la_base(con, obra_id: int) -> set[tuple[str, str]]:
    """Public CI documentation."""
    out: set[tuple[str, str]] = set()
    for t, in con.execute("SELECT p.texto_literal FROM precepto p JOIN version v ON v.id=p.version_id WHERE v.obra_id=? AND p.ruta_estructural='cabecera'", (obra_id,)):
        for m in RE_PUBLICADO_EN.finditer(' '.join(t.split())):
            f = fecha_es(m.group(2))
            if f:
                out.add((m.group(1), f))
    return out

def _pares(texto: str) -> list[tuple[int, str, str, str, str]]:
    """Public CI documentation."""
    lineas = texto.split('\n')
    pares: dict[tuple[int, str, str], tuple[str, str]] = {}
    for n, ln in enumerate(lineas, 1):
        for m in contexto.RE_NORMA.finditer(ln):
            p = RE_PAREN_TRAS_NORMA.match(ln[m.end():])
            if p:
                for i in _ids_de(p.group(1)):
                    pares.setdefault((n, ' '.join(m.group(0).split()), i), ('en linea', ''))
    for n, titulo, entrada in _entradas(lineas):
        nombres = _nombres(titulo)
        if len(nombres) != 1:
            continue
        pegados = set()
        for m in contexto.RE_NORMA.finditer(entrada):
            p = RE_PAREN_TRAS_NORMA.match(entrada[m.end():])
            if p:
                pegados.update(_ids_de(p.group(1)))
        for i in _ids_de(entrada):
            if i in pegados:
                continue
            pares.setdefault((n, nombres[0], i), ('entrada', entrada))
    return [(n, norma, i, d, e) for (n, norma, i), (d, e) in pares.items()]

def comprobar(con, texto: str) -> Resultado:
    """Public CI documentation."""
    res = Resultado()
    boletin_visto: set[tuple[int, str]] = set()
    for n, norma, citado, donde, entrada in _pares(texto):
        obra = _obra_unica(con, norma)
        if obra is None:
            continue
        canonico = obra['identificador_canonico']
        if not (RE_ID_BOE.fullmatch(canonico) or canonico.startswith('CELEX-')):
            continue
        if citado.split('-')[0] != canonico.split('-')[0]:
            continue
        res.comprobados += 1
        d = Defecto(linea=n, norma=norma, citado=citado, de_la_base=canonico, obra=canonico, donde=donde)
        if citado != canonico:
            d.motivos.append(f'el identificador citado ({citado}) no es el de la norma ({canonico})')
        primera = (n, norma) not in boletin_visto
        boletin_visto.add((n, norma))
        citadas = {(m.group(1), fecha_es(m.group(2))) for m in RE_NUM_FECHA_CITADO.finditer(entrada)} if entrada and primera else set()
        base = _publicaciones_de_la_base(con, obra['id']) if citadas else set()
        if len(citadas) == 1 and len(base) == 1 and (None not in {f for _, f in citadas}):
            (nc, fc), (nb, fb) = (next(iter(citadas)), next(iter(base)))
            d.numero_citado, d.numero_base = (nc, nb)
            d.fecha_citada, d.fecha_base = (fc, fb)
            if (nc, fc) != (nb, fb):
                d.motivos.append(f'el boletín citado (núm. {nc}, de {fecha_legible(fc)}) no es el de la norma (núm. {nb}, de {fecha_legible(fb)})')
        if d.motivos:
            res.defectos.append(d)
    res.defectos.sort(key=lambda x: (x.linea, x.citado))
    return res
