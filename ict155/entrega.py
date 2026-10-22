"""Public CI documentation."""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from . import almacen, afirmaciones, ambito, cifras, completitud, interruptores, revision
from . import revision_independiente as ri
VALIDA = 'ENTREGA VÁLIDA'
VALIDA_CON_AVISOS = 'ENTREGA VÁLIDA CON AVISOS'
NO_VALIDA = 'ENTREGA NO VÁLIDA'
VEREDICTOS = (VALIDA, VALIDA_CON_AVISOS, NO_VALIDA)
EN_EL_REGISTRO = {VALIDA: 'VALIDA', VALIDA_CON_AVISOS: 'VALIDA_CON_AVISOS', NO_VALIDA: 'NO_VALIDA'}
MOTIVO_SIN_SELLO = 'no hay línea de sello (la respuesta termina con la línea que devuelve normativa_revisar, entera y con su código)'
MOTIVO_VARIOS_SELLOS = 'hay {n} líneas de sello: tiene que haber una, la que da la herramienta'
MOTIVO_SELLO_SIN_CODIGO = 'el sello está retocado: no es la línea que da la herramienta (no lleva código de sello, está escrita a mano o en otro formato)'
MOTIVO_SELLO_RETOCADO = 'el sello está retocado: no es la línea que da la herramienta para este texto (o la base o la consulta de vigencia han cambiado desde que se revisó: vuelve a revisar)'
MOTIVO_CODIGO = 'el código del sello ({presente}) no corresponde al texto (el de este texto es {esperado}): el texto cambió después de revisarlo, o el sello es de otra respuesta'

@dataclass
class Veredicto:
    veredicto: str = NO_VALIDA
    motivos: list[str] = field(default_factory=list)
    sello_correcto: str = ''
    sello_presente: list[str] = field(default_factory=list)
    codigo: str = ''
    codigo_presente: str | None = None
    informe: revision.Informe = field(default_factory=revision.Informe)
    pregunta_dada: bool = False
    temas: list[str] = field(default_factory=list)
    temas_nombres: list[str] = field(default_factory=list)
    faltan: list[completitud.Falta] = field(default_factory=list)
    independiente_pedida: bool = False
    independiente: ri.Resultado | None = None
    cifras_hallazgos: list = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return self.veredicto != NO_VALIDA

    @property
    def primera_linea(self) -> str:
        return self.veredicto + (': ' + '; '.join(self.motivos) if self.veredicto == NO_VALIDA else '')

    @property
    def avisos(self) -> list[revision.Comprobacion]:
        """Public CI documentation."""
        filas = [c for c in self.informe.comprobaciones if c.nivel in (revision.ERROR, revision.AVISO)]
        return sorted(filas, key=lambda c: (revision.NIVELES.index(c.nivel), c.linea))

    def estado(self) -> str:
        """Public CI documentation."""
        r = self.informe.resumen()
        r20 = f";TEMAS={','.join(self.temas) or '-'};FALTAN={len(self.faltan)}" if self.pregunta_dada else ';TEMAS=sin_pregunta'
        r23 = ';' + (self.independiente.estado() if self.independiente is not None else 'REVIND=NO_HECHA') if self.independiente_pedida else ''
        return f"{EN_EL_REGISTRO[self.veredicto]};SELLO={self.codigo};PRESENTE={self.codigo_presente or '-'};ERROR={r['errores']};SIN_COMPROBAR={r['sin_comprobar']}{r20}{r23}"

    def dict(self) -> dict:
        d = {'veredicto': self.veredicto, 'valida': self.valida, 'motivos': self.motivos, 'primera_linea': self.primera_linea, 'sello_correcto': self.sello_correcto, 'sello_presente': self.sello_presente, 'sello': self.codigo, 'sello_en_el_texto': self.codigo_presente, 'resumen': self.informe.resumen(), 'estado': self.estado(), 'huella_base': self.informe.huella_base, 'preceptos_base': self.informe.preceptos_base, 'pregunta_dada': self.pregunta_dada, 'temas': self.temas, 'temas_nombres': self.temas_nombres, 'faltan': [f.dict() for f in self.faltan], 'comprobaciones': [{'nivel': c.nivel, 'tipo': c.tipo, 'cita': c.cita, 'detalle': c.detalle, 'linea': c.linea} for c in self.avisos]}
        if self.independiente_pedida:
            d['revision_independiente'] = self.independiente.dict() if self.independiente is not None else {'hecha': False, 'fallo': 'no se hizo'}
        return d

    def lineas_de_completitud(self) -> list[str]:
        """Public CI documentation."""
        if not self.pregunta_dada:
            return ['Nota: sin la pregunta no se ha comprobado que la respuesta esté completa.']
        if not self.temas:
            return ['Temas de la pregunta: ninguno de la lista de lo obligatorio (cowork/temas_obligatorios.json). ' + completitud.NO_EXHAUSTIVA]
        out = ['Temas de la pregunta (lista de lo obligatorio): ' + '; '.join((f'«{n}» [{i}]' for i, n in zip(self.temas, self.temas_nombres))) + '.']
        if self.faltan:
            out += ['Lo que falta se puede citar para aplicarlo o para explicar por qué no aplica; callarlo hace la entrega NO VÁLIDA (INCOMPLETA):'] + [f'  - {f.motivo}' for f in self.faltan]
        else:
            out.append('La respuesta cita todos los obligatorios de esos temas; la lista no es exhaustiva, así que eso no prueba que la respuesta esté completa.')
        return out

    def texto(self) -> str:
        """Public CI documentation."""
        out = [self.primera_linea, ''] + self.lineas_de_completitud() + ['']
        if self.independiente_pedida and self.independiente is not None:
            out += self.independiente.lineas() + ['']
        out += ['Línea de sello correcta para este texto (cópiala tal cual, entera y con su código, como última línea de la respuesta; si cambias una sola palabra del texto, vuelve a revisar):', self.sello_correcto]
        if self.sello_presente and self.sello_presente != [self.sello_correcto]:
            out += ['', 'Línea de sello que lleva la respuesta:'] + self.sello_presente
        r = self.informe.resumen()
        if self.valida and (not sum(r['citas'].values())) and (not r['normativas']):
            out += ['', 'Nota: la revisión no ha encontrado ninguna cita ni afirmación normativa: no ha comprobado nada.']
        filas = self.avisos
        if filas:
            out.append('')
            out += [f'{c.nivel} · {c.tipo} · línea {c.linea} · {c.cita} → {c.detalle}' for c in filas]
        return '\n'.join(out)

def _sin_comprobar(n: int) -> str:
    return f'quedan {n} afirmaciones normativas sin comprobar' if n != 1 else 'queda 1 afirmación normativa sin comprobar'

def verificar(con: sqlite3.Connection, respuesta: str, ambitos: tuple[str, ...]=('publico',), huella_base: str | None=None, *, datos_vigencia: dict | None=None, hoy: str | None=None, tabla_sucesion: list[dict] | None=None, pregunta: str | None=None, temas: list[completitud.Tema] | None=None, datos_cotejo=None, revision_independiente: bool=False, datos_historial: dict | None=None, modelo_revision: str | None=None, ejecutor_revision: ri.Ejecutor | None=None, cache_revision: bool=True, revisiones: int=1) -> Veredicto:
    """Public CI documentation."""
    if isinstance(revisiones, bool) or not isinstance(revisiones, int) or revisiones < 1:
        raise ValueError(f'revisiones tiene que ser un entero desde 1, no {revisiones!r}')
    informe = revision.revisar(con, respuesta, ambitos, huella_base, datos_vigencia=datos_vigencia, hoy=hoy, tabla_sucesion=tabla_sucesion, datos_historial=datos_historial, datos_cotejo=datos_cotejo)
    correcta = informe.linea()
    presentes = revision.lineas_de_sello(respuesta)
    v = Veredicto(sello_correcto=correcta, sello_presente=presentes, codigo=informe.codigo or '', informe=informe)
    motivos: list[str] = []
    if not presentes:
        motivos.append(MOTIVO_SIN_SELLO)
    elif len(presentes) > 1:
        motivos.append(MOTIVO_VARIOS_SELLOS.format(n=len(presentes)))
    else:
        linea = presentes[0]
        v.codigo_presente = revision.codigo_de_una_linea_de_sello(linea)
        if linea != correcta:
            if v.codigo_presente is None:
                motivos.append(MOTIVO_SELLO_SIN_CODIGO)
            elif v.codigo_presente != v.codigo:
                motivos.append(MOTIVO_CODIGO.format(presente=v.codigo_presente, esperado=v.codigo))
            else:
                motivos.append(MOTIVO_SELLO_RETOCADO)
    r = informe.resumen()
    if r['errores']:
        motivos.append(f"hay {r['errores']} {('error' if r['errores'] == 1 else 'errores')} sin corregir")
    if r['sin_comprobar']:
        motivos.append(_sin_comprobar(r['sin_comprobar']))
    if pregunta is not None and pregunta.strip():
        lista = completitud.cargar() if temas is None else temas
        detectados = completitud.temas_de(pregunta, lista)
        v.pregunta_dada = True
        v.temas, v.temas_nombres = ([t.id for t in detectados], [t.nombre for t in detectados])
        v.faltan = completitud.faltan(con, respuesta, pregunta, ambitos, lista)
        motivos += [f.motivo for f in v.faltan]
    if revision_independiente:
        v.independiente_pedida = True
        try:
            if revisiones > 1:
                preparada = ri.preparar(con, pregunta, respuesta, ambitos, informe.huella_base, datos_vigencia=datos_vigencia, datos_historial=datos_historial, hoy=hoy, modelo=modelo_revision)
                v.independiente = ri.revisar_pasadas(preparada, revisiones, ejecutor=ejecutor_revision, cache=cache_revision)
            else:
                v.independiente = ri.revisar(con, pregunta, respuesta, ambitos, informe.huella_base, datos_vigencia=datos_vigencia, datos_historial=datos_historial, hoy=hoy, modelo=modelo_revision, ejecutor=ejecutor_revision, cache=cache_revision)
        except almacen.ErrorDeAlmacen:
            raise
        except Exception as e:
            v.independiente = ri.Resultado(fallo=f'error inesperado en la revisión ({type(e).__name__}: {e})')
        motivos += [o.motivo for o in v.independiente.objeciones] if v.independiente.hecha else [v.independiente.motivo_de_fallo]
    modo_cifras = interruptores.modo('cifras')
    if modo_cifras != 'apagado':
        try:
            v.cifras_hallazgos = cifras.comprobar_respuesta(con, respuesta, pregunta)
        except almacen.ErrorDeAlmacen:
            raise
        except Exception as e:
            if modo_cifras == 'bloquea':
                motivos.append('no se han podido comprobar las cifras y los plazos de la respuesta (hay una grafía que no se reconoce en la pregunta o en la respuesta): revísala y repite la verificación')
            else:
                interruptores.anotar_sombra('cifras', {'error': f'{type(e).__name__}: {e}'})
        else:
            for h in v.cifras_hallazgos:
                if modo_cifras == 'bloquea' and h.tipo in ('contradiccion', 'incoherencia') and (h.cifra_frase.unidad not in cifras.UNIDADES_SOLO_SOMBRA):
                    motivos.append(f'{h.motivo}: corrige la cifra o la cita, la que esté mal')
                else:
                    interruptores.anotar_sombra('cifras', {'tipo': h.tipo, 'identificador': h.identificador, 'cifra': h.cifra_frase.texto, 'frase': h.frase, 'motivo': h.motivo})
    modo_ambito = interruptores.modo('ambito')
    if modo_ambito == 'sombra':
        try:
            motivos_ambito = ambito.motivos_entrega(con, respuesta, pregunta)
        except almacen.ErrorDeAlmacen:
            raise
        except Exception as e:
            interruptores.anotar_sombra('ambito', {'error': f'{type(e).__name__}: {e}'})
        else:
            for m in motivos_ambito:
                interruptores.anotar_sombra('ambito', {'motivo': m})
    elif modo_ambito == 'bloquea':
        motivos += ambito.motivos_entrega(con, respuesta, pregunta)
    v.motivos = motivos
    if motivos:
        v.veredicto = NO_VALIDA
    else:
        otros = sum((1 for c in informe.comprobaciones if c.nivel == revision.AVISO and c.tipo != afirmaciones.SIN_COMPROBAR))
        v.veredicto = VALIDA_CON_AVISOS if otros else VALIDA
    return v
