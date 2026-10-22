"""Public CI documentation."""
import re
import pytest
from ict155 import afirmaciones as af, ambito, brechas, cifras, completitud, consulta, db, interruptores

@pytest.fixture
def con():
    c = db.conectar(solo_lectura=True)
    c.execute('PRAGMA query_only=ON')
    assert c.execute('PRAGMA query_only').fetchone()[0] == 1
    yield c
    c.close()

@pytest.fixture(autouse=True)
def audit(monkeypatch, tmp_path):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path))
    monkeypatch.setenv('ICT155_CONTROLES_FORZADOS', '{"almacen_unico":"apagado","temas_r27":"bloquea"}')

@pytest.mark.parametrize('frase', ['El reglamento ficticio no tenía un plazo de seis años.', 'La redacción anterior no contenía el plazo de siete años.'])
def test_cifra_negada_no_se_atribuye_al_precepto(frase):
    assert not any((h.tipo == 'contradiccion' for h in cifras.contradicciones(frase, 'El plazo será de doce años.')))

@pytest.mark.parametrize('frase', ['El texto histórico tenía un periodo de siete años.', 'El plazo vigente es de tres años.', 'No se ha verificado el contador; el plazo vigente es de tres años.'])
def test_cifra_afirmada_sigue_comprobandose(frase):
    assert any((h.tipo == 'contradiccion' for h in cifras.contradicciones(frase, 'El plazo será de dos años.')))

def hallazgos_brecha(monkeypatch, estado=consulta.ENCONTRADO, **campos):
    monkeypatch.setattr(consulta, 'resolver', lambda *a, **k: consulta.Respuesta(estado=estado))
    ultima = dict(numero=1, fecha='2026-10-21', veredicto='parcial', documento_aportado='', que_falta='', citas=[], no_aplica=[])
    b = dict(id='DOC-1', estado='abierta', citas=[], revisiones=[ultima], **campos)
    return brechas._hallazgos_de_brecha(None, b, ultima, ('publico',), None)

def test_requerimiento_documental_explicito_no_exige_norma(monkeypatch):
    hs = hallazgos_brecha(monkeypatch, notas='El informe no invoca norma para esta fila.', evidencia_requerida='Aportar alcance del certificado.')
    assert not any((h.tipo == 'sin_citas' and h.nivel == brechas.ERROR for h in hs))
    assert any((h.tipo == 'sin_citas' and h.nivel == brechas.AVISO for h in hs))

def test_carencia_sin_justificacion_sigue_exigiendo_norma(monkeypatch):
    hs = hallazgos_brecha(monkeypatch, notas='Se exige verificar periódicamente.')
    assert any((h.tipo == 'sin_citas' and h.nivel == brechas.ERROR for h in hs))

@pytest.mark.parametrize('tipo,nivel,bloquea', [('sin_citas', brechas.AVISO, False), ('cita_inexistente', brechas.AVISO, False), ('sin_citas', brechas.ERROR, True), ('cita_no_tratada', brechas.ERROR, True)])
def test_brechas_no_promueve_un_aviso_a_error(monkeypatch, tipo, nivel, bloquea):
    monkeypatch.setattr(brechas, '_precargar_tablas', lambda: None)
    monkeypatch.setattr(db, 'huella_contenido', lambda c: 'sintetica')
    monkeypatch.setattr(interruptores, 'modo', lambda n: 'bloquea' if n == 'brechas_r27' else 'apagado')
    b = dict(id='DOC-3', estado='abierta', citas=[], revisiones=[])
    h = brechas.HallazgoR27(tipo, nivel, 'DOC-3', 'Comprobación sintética.')
    monkeypatch.setattr(brechas, '_hallazgos_de_brecha', lambda *a: [h])
    rs = brechas.comprobar(None, {'brechas': [b]}, datos_vigencia={}, avisos_de_limites={})
    assert any((c.nivel == brechas.ERROR for c in rs[0].citas)) == bloquea
    assert any((c.nivel == nivel for c in rs[0].citas))
    assert h in rs.hallazgos

@pytest.mark.parametrize('estado,nivel', [(consulta.FUERA_DE_ALCANCE, brechas.AVISO), (consulta.PRECEPTO_INEXISTENTE, brechas.ERROR)])
def test_fuera_de_alcance_no_prueba_inexistencia(monkeypatch, estado, nivel):
    monkeypatch.setattr(consulta, 'resolver', lambda *a, **k: consulta.Respuesta(estado=estado))
    ultima = dict(numero=1, veredicto='parcial', documento_aportado='', que_falta='', citas=['Obra::ap.99'])
    b = dict(id='DOC-2', estado='abierta', citas=[], revisiones=[ultima])
    hs = brechas._hallazgos_de_brecha(None, b, ultima, ('publico',), None)
    assert any((h.tipo == 'cita_inexistente' and h.nivel == nivel for h in hs))
    if estado == consulta.FUERA_DE_ALCANCE:
        assert all(('que no existe' not in h.mensaje for h in hs if h.tipo == 'cita_inexistente'))

@pytest.mark.parametrize('regimen,completitud,texto,nivel', [('publico', 'completa', '1. Requisito sintético. 2. Otro requisito.', brechas.ERROR), ('licenciado', 'completa', 'Texto sintético de prueba.', brechas.AVISO), ('publico', 'parcial', 'Texto sintético de prueba.', brechas.AVISO), ('publico', 'completa', '99. Requisito sintético que no se ha separado.', brechas.AVISO)])
def test_fuera_ancestro_publico_completo_conserva_invencion(monkeypatch, regimen, completitud, texto, nivel):

    def resolver(c, ident, *a, **k):
        if ident.endswith('/ap.99'):
            return consulta.Respuesta(estado=consulta.FUERA_DE_ALCANCE, completitud='completa')
        return consulta.Respuesta(estado=consulta.ENCONTRADO, completitud=completitud, regimen=regimen, texto_literal=texto)
    monkeypatch.setattr(consulta, 'resolver', resolver)
    ultima = dict(numero=1, veredicto='parcial', documento_aportado='', que_falta='', citas=['Obra::ap.1/ap.99'])
    b = dict(id='DOC-4', estado='abierta', citas=[], revisiones=[ultima])
    hs = brechas._hallazgos_de_brecha(None, b, ultima, ('publico',), None)
    assert any((h.tipo == 'cita_inexistente' and h.nivel == nivel for h in hs))

@pytest.mark.parametrize('texto,dispara', [('La obligación se dirige a las entidades de distribución (`RD 782/2013::art.1`).', False), ('El control cubre al distribuidor que entrega en la farmacia (`RD 782/2013::art.20.1`).', False), ('El hospital debe cumplir el RD 782/2013 (`RD 782/2013::art.2`).', True), ('El distribuidor tiene obligaciones; la farmacia hospitalaria está obligada por el RD 782/2013 (`RD 782/2013::art.2`).', True)])
def test_ambito_sujeto_obligado_no_es_destinatario(monkeypatch, texto, dispara):
    regla = ambito.Regla('ambito_rd782_no_alcanza_transportista_ni_farmacia_hospitalaria', ('RD 782/2013',), ((re.compile('hospital'),),), 'aplica', 'RD 782/2013::art.2', None, 'sintético', 'sintético', 'sintético', 'propuesta')
    monkeypatch.setattr(ambito, '_coincide_norma', lambda *a: True)
    assert bool(ambito.comprobar(None, texto, 'hospital', reglas=[regla])) == dispara

@pytest.mark.parametrize('texto,bloquea', [('Los hechos, que no están en la base, no permiten atribuir intención fraudulenta.', False), ('Las circunstancias del cliente no están en la base.', False), ('La base no resuelve si el plan equivale a una disposición reglamentaria.', False), ('La base no tiene el reglamento español de distribución de medicamentos.', True), ('La base no regula los precintos.', True), ('Los hechos no están en la base; la base no tiene el reglamento español.', True), ('Los hechos no están en la base, y la base no tiene el reglamento español.', True), ('Los hechos no están en la base, y ese artículo no está en la base.', True)])
def test_hechos_privados_e_interpretacion_no_son_ausencia_normativa(monkeypatch, texto, bloquea):
    monkeypatch.setattr(interruptores, 'modo', lambda n: 'bloquea')
    monkeypatch.setattr(interruptores, 'anotar_sombra', lambda *a: None)
    a = af.Analizador(None, texto, [], {}, {}, [(0, len(texto))], ('publico',), {}, '2026-10-21', [])
    monkeypatch.setattr(a, '_r27_respaldada', lambda f: False)
    f = af.Frase(ini=0, fin=len(texto), texto=texto, linea=1, parrafo=0)
    hs = []
    a._r27_negacion_base([f], hs)
    assert bool(hs) == bloquea

def regla_gmp():
    return ambito.Regla('ambito_gmp_fabricacion_no_distribuidor', ('GMP::ap.1',), ((re.compile('distribuidor'),),), 'aplica', None, 'doctrina', 'sintético', 'sintético', 'sintético', 'propuesta')

@pytest.mark.parametrize('texto,dispara', [('El protocolo cubre el ciclo de vida (`GMP::ap.1`).\n\nEl Anexo 11 no le obliga por sí mismo al distribuidor; se usa como guía metodológica.', False), ('El distribuidor debe cumplir el Anexo 11 (`GMP::ap.1`).', True), ('El Anexo 11 no le obliga por sí mismo al distribuidor; se usa como guía.\n\nEl distribuidor debe cumplir el Anexo 11 (`GMP::ap.1`).', True), ('El distribuidor debe cumplir el Anexo 11 (`GMP::ap.1`).\n\nOtra norma no se aplica.', True)])
def test_guia_metodologica_separada_de_obligacion(monkeypatch, texto, dispara):
    monkeypatch.setattr(ambito, '_coincide_norma', lambda *a: True)
    assert bool(ambito.comprobar(None, texto, 'distribuidor', reglas=[regla_gmp()])) == dispara

@pytest.mark.parametrize('pregunta,exigible', [('Un plan de autocontrol mide la temperatura de alimentos congelados. ¿Qué exige?', False), ('Un plan de autocontrol mide la temperatura de alimentos ultracongelados. ¿Qué exige?', True), ('Un plan de autocontrol mide la temperatura de alimentos, sin saber si son ultracongelados. ¿Qué exige?', False)])
def test_tema_ultracongelados_necesita_dato_afirmado(con, pregunta, exigible):
    fs = completitud.faltan(con, '', pregunta)
    assert any((f.identificador == 'RD 1109/1991::art.5.1' for f in fs)) == exigible

@pytest.mark.parametrize('pregunta,exigible', [('El dueño ajusta por su cuenta la báscula desviada cinco gramos. ¿Qué riesgo corre?', False), ('El dueño ajusta por su cuenta la báscula y la usa sabiendo que supera los errores máximos permitidos. ¿Qué riesgo corre?', True), ('El dueño ajusta por su cuenta la báscula, sin saber si supera los errores máximos permitidos. ¿Qué riesgo corre?', False)])
def test_tema_emp_necesita_conocimiento_y_superacion(con, pregunta, exigible):
    fs = completitud.faltan(con, '', pregunta)
    assert any((f.identificador == 'Ley 32/2014::art.22.2.d' for f in fs)) == exigible
    assert any((f.identificador == 'Ley 32/2014::art.22.3.a' for f in fs))
