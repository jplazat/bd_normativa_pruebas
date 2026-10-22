"""Public CI documentation."""
from __future__ import annotations
from pruebas.almacen_soporte import conservar_almacen_forzado, limpiar_forzados
import json
from pathlib import Path
import pytest
from ict155 import ambito, brechas, cli, config, db, entrega, interruptores, relacionados, revision, sucesion
pytestmark = pytest.mark.skipif(not config.BD.exists(), reason='hace falta una base')
RAIZ = Path(__file__).resolve().parent.parent

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    yield c
    c.close()

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    limpiar_forzados(monkeypatch, raising=False)
    relacionados._CACHE.clear()
    sucesion._CACHE.clear()
    yield
    relacionados._CACHE.clear()
    sucesion._CACHE.clear()

def _forzar(monkeypatch, **modos: str) -> None:
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, conservar_almacen_forzado(json.dumps(modos)))

def _sellado(con, texto: str) -> str:
    return texto.rstrip('\n') + '\n\n' + revision.revisar(con, texto).linea() + '\n'

def _reglas_rotas(monkeypatch, tmp_path, contenido: str='{esto no es json') -> Path:
    """Public CI documentation."""
    ruta = tmp_path / 'reglas_rotas.json'
    ruta.write_text(contenido, encoding='utf-8')
    monkeypatch.setattr(ambito, 'RUTA_REGLAS', ruta)
    return ruta

def _lineas_sombra(tmp_path) -> list[dict]:
    ruta = tmp_path / 'registro' / 'sombra.log'
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines()]

def test_entrega_verificar_con_reglas_de_ambito_rotas_en_sombra_no_cambia_nada(con, tmp_path, monkeypatch):
    texto = _sellado(con, 'Respuesta sin nada que ver con normas: `BOE-A-1996-21021::art.16`.\n')
    v_apagado = entrega.verificar(con, texto)
    _forzar(monkeypatch, ambito='sombra')
    _reglas_rotas(monkeypatch, tmp_path)
    v = entrega.verificar(con, texto)
    assert v.veredicto == v_apagado.veredicto and v.motivos == v_apagado.motivos
    lineas = _lineas_sombra(tmp_path)
    assert len(lineas) == 1 and lineas[0]['control'] == 'ambito' and ('error' in lineas[0])
    assert 'ReglasMal' in lineas[0]['error']

def test_brechas_comprobar_con_reglas_de_ambito_rotas_en_sombra_no_rompe(con, tmp_path, monkeypatch):
    _forzar(monkeypatch, ambito='sombra')
    _reglas_rotas(monkeypatch, tmp_path)
    reg = {'brechas': [{'id': 'B-1', 'estado': 'abierta', 'fecha_estado': '2026-08-05', 'citas': [], 'revisiones': [{'numero': 1, 'fecha': '2026-10-17', 'veredicto': 'parcial', 'documento_aportado': 'cualquier prosa, sin identificadores.', 'que_falta': '', 'citas': [], 'no_aplica': []}]}]}
    resultados = brechas.comprobar(con, reg)
    assert not any((h.tipo == 'fuera_de_ambito' for h in resultados.hallazgos))
    lineas = [l for l in _lineas_sombra(tmp_path) if l['control'] == 'ambito']
    assert len(lineas) == 1 and 'error' in lineas[0] and (lineas[0]['brecha'] == 'B-1')

def test_cli_verificar_entrega_con_reglas_de_ambito_rotas_en_bloquea_da_rc2_sin_traceback(con, tmp_path, monkeypatch, capsys):
    _forzar(monkeypatch, ambito='bloquea')
    ruta = _reglas_rotas(monkeypatch, tmp_path)
    texto = _sellado(con, 'Respuesta sin nada que ver con normas: `BOE-A-1996-21021::art.16`.\n')
    fichero = tmp_path / 'respuesta.md'
    fichero.write_text(texto, encoding='utf-8')
    rc = cli.main(['verificar-entrega', str(fichero)])
    salida, err = capsys.readouterr()
    assert rc == 2
    assert 'Traceback' not in salida and 'Traceback' not in err
    assert 'No se ha podido comprobar' in err and str(ruta) in err

def test_cli_brechas_con_reglas_de_ambito_rotas_en_bloquea_da_rc2_sin_traceback(con, tmp_path, monkeypatch, capsys):
    _forzar(monkeypatch, ambito='bloquea')
    ruta = _reglas_rotas(monkeypatch, tmp_path)
    registro = tmp_path / 'registro.json'
    registro.write_text(json.dumps({'brechas': [{'id': 'B-1', 'estado': 'abierta', 'fecha_estado': '2026-08-05', 'citas': [], 'revisiones': [{'numero': 1, 'fecha': '2026-10-17', 'veredicto': 'parcial', 'documento_aportado': '', 'que_falta': '', 'citas': [], 'no_aplica': []}]}]}), encoding='utf-8')
    rc = cli.main(['brechas', str(registro)])
    salida, err = capsys.readouterr()
    assert rc == 2
    assert 'Traceback' not in salida and 'Traceback' not in err
    assert 'No se ha podido comprobar' in err and str(ruta) in err

def test_cli_comprobar_carpeta_con_reglas_de_ambito_rotas_en_bloquea_da_rc2_sin_traceback(tmp_path, monkeypatch, capsys):
    """Public CI documentation."""
    _forzar(monkeypatch, ambito='bloquea')
    ruta = _reglas_rotas(monkeypatch, tmp_path)
    carpeta = tmp_path / 'carpeta'
    carpeta.mkdir()
    (carpeta / 'preguntas.json').write_text(json.dumps({'x.md': 'una instrucción cualquiera'}), encoding='utf-8')
    rc = cli.main(['comprobar-carpeta', str(carpeta)])
    salida, err = capsys.readouterr()
    assert rc == 2
    assert 'Traceback' not in salida and 'Traceback' not in err
    assert 'No se ha podido comprobar' in err and str(ruta) in err

def test_entrega_verificar_con_reglas_de_ambito_sanas_en_bloquea_no_cambia(con):
    """Public CI documentation."""
    texto = _sellado(con, 'Respuesta sin nada que ver con normas: `BOE-A-1996-21021::art.16`.\n')
    v = entrega.verificar(con, texto)
    assert not any((m.startswith(ambito.PREFIJO_FUERA_DE_AMBITO) for m in v.motivos))

def _con_bom(ruta: Path, contenido: dict) -> Path:
    ruta.write_bytes(b'\xef\xbb\xbf' + json.dumps(contenido, ensure_ascii=False).encode('utf-8'))
    return ruta

def test_controles_json_con_bom_funciona_igual_que_sin_bom(tmp_path):
    sin_bom = tmp_path / 'sin_bom.json'
    sin_bom.write_text(json.dumps({'controles': {'cifras': 'bloquea'}}), encoding='utf-8')
    con_bom = _con_bom(tmp_path / 'con_bom.json', {'controles': {'cifras': 'bloquea'}})
    assert interruptores.modo('cifras', con_bom) == interruptores.modo('cifras', sin_bom) == 'bloquea'

def test_controles_local_con_bom_funciona_igual_que_sin_bom(tmp_path):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'bloquea'}}), encoding='utf-8')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    _con_bom(interruptores.ruta_local(), {'controles': {'cifras': 'sombra'}})
    assert interruptores.modo('cifras', ruta) == 'sombra'
    assert interruptores.avisos() == []

@pytest.mark.parametrize('mod, clave, bueno', [pytest.param(relacionados, 'grupos', {'grupos': [{'nombre': 'g', 'disparadores': 'zzz', 'contexto': 'yyy', 'preceptos': [{'identificador': 'Orden ICT/155/2020::art.18', 'nota': 'una nota cualquiera'}]}]}, id='relacionados'), pytest.param(sucesion, 'sucesiones', {'sucesiones': [{'origen': 'BOE-A-1996-750::art.23', 'sucesor': 'BOE-A-2020-2573::art.18', 'equivalencia': 'total', 'nota': 'una nota cualquiera, de largo razonable'}]}, id='sucesion')])
def test_tabla_con_bom_en_bloquea_funciona_igual_que_sin_bom(monkeypatch, tmp_path, mod, clave, bueno):
    _forzar(monkeypatch, relacionados_cierra='bloquea')
    sin_bom = tmp_path / 'sin_bom.json'
    sin_bom.write_text(json.dumps(bueno, ensure_ascii=False), encoding='utf-8')
    con_bom = _con_bom(tmp_path / 'con_bom.json', bueno)
    assert mod.cargar(con_bom) == mod.cargar(sin_bom)
    assert len(mod.cargar(sin_bom)) == 1

def test_todo_a_sombra_con_controles_json_roto_no_revienta_y_avisa(tmp_path, monkeypatch, capsys):
    """Public CI documentation."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('todo_a_sombra_s2g', RAIZ / 'herramientas' / 'todo_a_sombra.py')
    tas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tas)
    roto = tmp_path / 'controles_rotos.json'
    roto.write_text('{esto no es json en absoluto', encoding='utf-8')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', roto)
    rc = tas.main([])
    salida, err = capsys.readouterr()
    assert rc != 0
    assert 'Traceback' not in salida and 'Traceback' not in err
    assert 'AVISO' in err
    assert 'git checkout -- cowork/controles.json' in err
    escrito = json.loads(interruptores.ruta_local().read_text(encoding='utf-8'))['controles']
    assert set(escrito) == set(interruptores.CONTROLES_CONOCIDOS)
    assert all((m == 'sombra' for m in escrito.values()))

@pytest.mark.parametrize('mod, clave', [(relacionados, 'grupos'), (sucesion, 'sucesiones')])
def test_tabla_con_lista_vacia_en_bloquea_es_valida_no_rota(monkeypatch, tmp_path, mod, clave):
    _forzar(monkeypatch, relacionados_cierra='bloquea')
    ruta = tmp_path / 'vacia.json'
    ruta.write_text(json.dumps({clave: []}), encoding='utf-8')
    assert mod.cargar(ruta) == []

def test_local_con_utf16_funciona(tmp_path):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'bloquea'}}), encoding='utf-8')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_bytes(json.dumps({'controles': {'cifras': 'apagado'}}).encode('utf-16'))
    assert interruptores.modo('cifras', ruta) == 'apagado'
    assert interruptores.avisos() == []

def test_local_con_clave_nota_se_ignora_y_el_resto_manda(tmp_path):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'bloquea'}}), encoding='utf-8')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'_nota': 'a mano', 'controles': {'_nota': 'x', 'cifras': 'apagado'}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == 'apagado'
    assert interruptores.avisos() == []

def test_local_con_comodin_baja_todo_menos_lo_nombrado(tmp_path):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'bloquea', 'cubre_estricto': 'bloquea'}}), encoding='utf-8')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'*': 'apagado', 'cifras': 'sombra'}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == 'sombra'
    assert interruptores.modo('cubre_estricto', ruta) == 'apagado'
    assert interruptores.avisos() == []

def test_local_con_una_entrada_que_no_se_entiende_solo_ignora_esa(tmp_path):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'bloquea', 'cubre_estricto': 'bloquea'}}), encoding='utf-8')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'cifras': 'modo_que_no_existe', 'cubre_estricto': 'sombra'}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == 'bloquea'
    assert interruptores.modo('cubre_estricto', ruta) == 'sombra'
    avisos = interruptores.avisos()
    assert len(avisos) == 1 and 'cifras' in avisos[0] and ('modo_que_no_existe' in avisos[0])

@pytest.mark.parametrize('separador', ['\u2028', '\u2029', '\x85'])
def test_anotar_sombra_escapa_los_separadores_de_linea(separador):
    interruptores.anotar_sombra('cifras', {'detalle': f'antes{separador}despues'})
    texto = interruptores.ruta_sombra().read_text(encoding='utf-8')
    assert len(texto.splitlines()) == 1
    d = json.loads(texto.strip())
    assert d['detalle'] == f'antes{separador}despues'

def test_anotar_sombra_sigue_legible_para_tildes_y_enies():
    interruptores.anotar_sombra('cifras', {'detalle': 'una frase con tildes, eñes y mayúsculas: Ñ'})
    texto = interruptores.ruta_sombra().read_text(encoding='utf-8')
    assert '\\u00f1' not in texto and 'ñ' in texto
