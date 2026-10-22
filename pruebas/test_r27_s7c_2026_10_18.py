"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import importlib.util
import json
from pathlib import Path
import pytest
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
from ict155 import completitud, config, consulta, db, interruptores
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base (LOCALAPPDATA/ict155/bd)')
ACEPTA = 'Ley 32/2014::art.12'
ALIAS_BOE = 'BOE-A-2014-13359'
HOJA_EXISTENTE = 'Ley 32/2014::art.12.2'
HOJA_BOE_EXISTENTE = 'BOE-A-2014-13359::art.12.2'
HOJA_INEXISTENTE_LEY = 'Ley 32/2014::art.12.999'
HOJA_INEXISTENTE_BOE = 'BOE-A-2014-13359::art.12.999'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

def _escribe(tmp_path, datos, nombre='temas.json') -> Path:
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta

def _tema(acepta, acepta_hoja) -> dict:
    obligatorio = {'acepta': list(acepta), 'por_que': 'el plazo tras una reparación', 'acepta_hoja': list(acepta_hoja)}
    return {'id': 't', 'nombre': 'Reparación de instrumentos', 'cuando': [['zzz']], 'obligatorios': [obligatorio]}

def _carga(tmp_path, acepta=(ACEPTA,), acepta_hoja=(HOJA_EXISTENTE,)) -> list[completitud.Tema]:
    return completitud.cargar(_escribe(tmp_path, {'temas': [_tema(acepta, acepta_hoja)]}))

def test_boe_con_ruta_inexistente_carga_antes_fallaba(con, tmp_path):
    """Public CI documentation."""
    assert consulta.resolver(con, HOJA_INEXISTENTE_BOE, ('publico',)).estado == consulta.PRECEPTO_INEXISTENTE
    temas = _carga(tmp_path, acepta_hoja=(HOJA_INEXISTENTE_BOE,))
    assert temas[0].obligatorios[0].acepta_hoja == (HOJA_INEXISTENTE_BOE,)

def test_ley_con_ruta_inexistente_misma_grafia_ya_cargaba_y_sigue(tmp_path):
    """Public CI documentation."""
    temas = _carga(tmp_path, acepta_hoja=(HOJA_INEXISTENTE_LEY,))
    assert temas[0].obligatorios[0].acepta_hoja == (HOJA_INEXISTENTE_LEY,)

def test_la_existencia_de_la_ruta_del_ancla_la_sigue_mirando_validar_contra_la_base(con, tmp_path):
    """Public CI documentation."""
    temas = _carga(tmp_path, acepta_hoja=(HOJA_INEXISTENTE_BOE,))
    malos = completitud.validar_contra_la_base(con, temas)
    assert len(malos) == 1 and malos[0].startswith(f'{HOJA_INEXISTENTE_BOE} [t]: ')

def test_una_obra_de_verdad_distinta_con_ruta_inexistente_sigue_fallando(tmp_path):
    """Public CI documentation."""
    with pytest.raises(completitud.TemasMal, match='tiene que ser igual o estar por debajo de alguno de «acepta»'):
        _carga(tmp_path, acepta_hoja=('Otra ley::art.12.999',))

def test_hoja_en_grafia_larga_carga_sin_abrir_la_base(tmp_path, monkeypatch):
    """Public CI documentation."""
    llamadas = []
    original = db.conectar
    monkeypatch.setattr(db, 'conectar', lambda *a, **kw: (llamadas.append(1), original(*a, **kw))[1])
    temas = _carga(tmp_path, acepta=(ACEPTA,), acepta_hoja=('Ley 32/2014::articulo.12.2',))
    assert temas[0].obligatorios[0].acepta_hoja == ('Ley 32/2014::articulo.12.2',)
    assert llamadas == []

def test_acepta_en_grafia_larga_hoja_corta_tambien_carga(tmp_path):
    """Public CI documentation."""
    temas = _carga(tmp_path, acepta=('Ley 32/2014::articulo.12',), acepta_hoja=(HOJA_EXISTENTE,))
    assert temas[0].obligatorios[0].acepta_hoja == (HOJA_EXISTENTE,)

@pytest.mark.parametrize('hoja', ['Ley 32/2014::Art.12.2', 'Ley 32/2014::ARTICULO.12.2'])
def test_otras_grafias_de_la_clase_tambien_cargan(tmp_path, hoja):
    temas = _carga(tmp_path, acepta_hoja=(hoja,))
    assert temas[0].obligatorios[0].acepta_hoja == (hoja,)

def test_grafia_larga_que_no_es_subapartado_de_verdad_sigue_fallando(tmp_path):
    """Public CI documentation."""
    with pytest.raises(completitud.TemasMal, match='tiene que ser igual o estar por debajo de alguno de «acepta»'):
        _carga(tmp_path, acepta_hoja=('Ley 32/2014::articulo.99',))

@pytest.fixture
def tas(monkeypatch):
    spec = importlib.util.spec_from_file_location('todo_a_sombra_s7c', RAIZ / 'herramientas' / 'todo_a_sombra.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    monkeypatch.setenv('ICT155_ALMACEN_CONTEXTO', 'compatibilidad_historica')
    monkeypatch.delenv(interruptores.VARIABLE_FORZADOS, raising=False)

@pytest.mark.parametrize('argv, objetivo', [([], 'sombra'), (['--apagar'], 'apagado')])
def test_controles_json_roto_sale_con_rc_distinto_de_cero_y_avisa_por_stderr(tmp_path, monkeypatch, capsys, tas, argv, objetivo):
    roto = tmp_path / 'controles_rotos.json'
    roto.write_text('{esto no es json en absoluto', encoding='utf-8')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', roto)
    rc = tas.main(argv)
    salida, err = capsys.readouterr()
    assert rc != 0
    assert 'Traceback' not in salida and 'Traceback' not in err
    assert 'AVISO' in err and 'git checkout -- cowork/controles.json' in err
    assert 'no sirve' in err.lower() or 'NO SIRVE' in err
    escrito = json.loads(interruptores.ruta_local().read_text(encoding='utf-8'))['controles']
    assert set(escrito) == set(interruptores.CONTROLES_CONOCIDOS)
    assert all((m == objetivo for m in escrito.values()))

def test_controles_json_roto_modo_sigue_fallando_cerrado_pese_a_la_palanca(tmp_path, monkeypatch, tas):
    """Public CI documentation."""
    roto = tmp_path / 'controles_rotos.json'
    roto.write_text('{esto no es json en absoluto', encoding='utf-8')
    monkeypatch.setattr(interruptores, 'RUTA_CONTROLES', roto)
    with pytest.raises(interruptores.ErrorDeControles):
        interruptores.modo('cifras')
    rc = tas.main([])
    assert rc != 0
    with pytest.raises(interruptores.ErrorDeControles):
        interruptores.modo('cifras')

def test_controles_json_valido_sigue_saliendo_con_rc_cero(tmp_path, monkeypatch, tas):
    """Public CI documentation."""
    valido = tmp_path / 'controles.json'
    valido.write_text(json.dumps({'controles': {'cifras': 'bloquea', 'cubre_estricto': 'bloquea', 'relacionados_cierra': 'bloquea', 'negacion_base': 'bloquea', 'brechas_r27': 'bloquea', 'ambito': 'bloquea', 'temas_r27': 'bloquea'}}), encoding='utf-8')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', valido)
    rc = tas.main([])
    assert rc == 0
