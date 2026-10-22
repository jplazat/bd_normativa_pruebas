"""Public CI documentation."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from . import superindices
from .consulta import norm_alias
LOCALIZADO = 'LOCALIZADO'
AMBIGUO = 'AMBIGUO'
NO_LOCALIZADO = 'NO_LOCALIZADO'
MINIMO_PALABRAS = 4
RUTA_CABECERA = 'cabecera'
_GUION_FIN = re.compile('[-\xad]\\s*\\n\\s*')
_NO_PALABRA = re.compile('[^\\w\\s]+', re.UNICODE)
_ESPACIOS = re.compile('\\s+')

def normalizar(s: str) -> str:
    """Public CI documentation."""
    s = superindices.plegar(unicodedata.normalize('NFC', s))
    s = _GUION_FIN.sub('', s)
    s = _NO_PALABRA.sub(' ', s)
    return _ESPACIOS.sub(' ', s).strip().lower()

@dataclass
class Candidato:
    ruta: str
    etiqueta: str
    obra: str
    identificador: str
    pagina_inicio: int | None
    pagina_fin: int | None

@dataclass
class Resultado:
    estado: str
    frase: str
    candidatos: list[Candidato] = field(default_factory=list)
    motivo: str | None = None

    @property
    def ruta(self) -> str | None:
        """Public CI documentation."""
        return self.candidatos[0].ruta if self.estado == LOCALIZADO else None

    @property
    def fundamento(self) -> str | None:
        """Public CI documentation."""
        if self.estado != LOCALIZADO:
            return None
        c = self.candidatos[0]
        return f'{c.identificador}::{c.ruta}'

def _es_ascendiente(padre: str, hijo: str) -> bool:
    """Public CI documentation."""
    if padre == hijo:
        return True
    sp = re.split('[/.]', padre)
    sh = re.split('[/.]', hijo)
    return len(sp) < len(sh) and sh[:len(sp)] == sp

def _cadena_unica(rutas: list[str]) -> bool:
    """Public CI documentation."""
    orden = sorted(rutas, key=lambda r: len(re.split('[/.]', r)))
    return all((_es_ascendiente(orden[i], orden[i + 1]) for i in range(len(orden) - 1)))
_CACHE: dict[int, tuple] = {}

def _corpus(con) -> list[tuple]:
    clave = id(con)
    guardado = _CACHE.get(clave)
    if guardado is None or guardado[0] is not con:
        guardado = _CACHE[clave] = (con, [(f['ident'], f['obra'], f['ruta'], f['etiqueta'], f['pi'], f['pf'], normalizar(f['texto'] or ''), frozenset((f['alias'] or '').split('|')) - {''}) for f in con.execute("\n                SELECT p.ruta_estructural AS ruta, p.etiqueta_humana AS etiqueta,\n                       p.texto_literal AS texto, p.pagina_inicio AS pi,\n                       p.pagina_fin AS pf, o.titulo AS obra,\n                       o.identificador_canonico AS ident,\n                       (SELECT group_concat(a.alias_norm, '|') FROM obra_alias a\n                        WHERE a.obra_id = o.id) AS alias\n                FROM precepto p\n                JOIN version v ON v.id = p.version_id\n                JOIN obra o    ON o.id = v.obra_id")])
    return guardado[1]

def olvidar_cache() -> None:
    """Public CI documentation."""
    _CACHE.clear()

def localizar(con, frase: str, obra: str | None=None) -> Resultado:
    """Public CI documentation."""
    aguja = normalizar(frase)
    if len(aguja.split()) < MINIMO_PALABRAS:
        return Resultado(NO_LOCALIZADO, frase, motivo=f'la frase tiene menos de {MINIMO_PALABRAS} palabras utiles y no identifica un sitio; localizaria cualquier cosa')
    filtro = obra.lower() if obra else None
    filtro_alias = norm_alias(obra) if obra else None
    hallados = []
    for ident, titulo, ruta, etiqueta, pi, pf, texto, alias in _corpus(con):
        if filtro and filtro not in (ident.lower(), *([titulo.lower()] if titulo else [])) and (not titulo or filtro not in titulo.lower()) and (filtro_alias not in alias):
            continue
        if aguja in texto:
            hallados.append(Candidato(ruta, etiqueta, titulo, ident, pi, pf))
    if not hallados:
        return Resultado(NO_LOCALIZADO, frase, motivo='la frase no aparece en el texto extraido' + (f' de {obra}' if obra else ' de ninguna obra cargada'))
    idents = {c.identificador for c in hallados}
    if len(idents) == 1 and _cadena_unica([c.ruta for c in hallados]):
        hondo = max(hallados, key=lambda c: len(re.split('[/.]', c.ruta)))
        return Resultado(LOCALIZADO, frase, [hondo])
    if len(idents) == 1:
        cabeceras = [c for c in hallados if c.ruta == RUTA_CABECERA]
        if len(cabeceras) == 1:
            return Resultado(LOCALIZADO, frase, [cabeceras[0]])
    hallados.sort(key=lambda c: (c.identificador, c.ruta))
    return Resultado(AMBIGUO, frase, hallados, motivo=f'la frase aparece en {len(hallados)} preceptos que no son el mismo sitio, en {len(idents)} obra(s). No se elige entre ellos')
