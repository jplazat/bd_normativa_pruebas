"""Public CI documentation."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest
from ict155 import interruptores
RAIZ = Path(__file__).resolve().parent.parent
HERRAMIENTA = RAIZ / 'herramientas' / 'todo_a_sombra.py'

def _controles(ruta: Path, **modos: str) -> Path:
    ruta.write_text(json.dumps({'controles': modos}), encoding='utf-8')
    return ruta

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """Public CI documentation."""
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    monkeypatch.setenv('ICT155_ALMACEN_CONTEXTO', 'compatibilidad_historica')
    monkeypatch.delenv(interruptores.VARIABLE_FORZADOS, raising=False)
    return tmp_path

def test_modo_aprobado_se_devuelve_tal_cual(tmp_path):
    ruta = _controles(tmp_path / 'controles.json', cifras='sombra', cubre_estricto='bloquea')
    assert interruptores.modo('cifras', ruta) == 'sombra'
    assert interruptores.modo('cubre_estricto', ruta) == 'bloquea'

@pytest.mark.parametrize('modo', interruptores.MODOS)
def test_cada_modo_aprobado_vale(tmp_path, modo):
    ruta = _controles(tmp_path / 'controles.json', x=modo)
    assert interruptores.modo('x', ruta) == modo

def test_fichero_versionado_ausente_falla_cerrado(tmp_path):
    with pytest.raises(interruptores.ErrorDeControles, match='falta o está roto'):
        interruptores.modo('cifras', tmp_path / 'no_existe.json')

@pytest.mark.parametrize('contenido', ['{no es json', json.dumps({'otra_cosa': {}}), json.dumps({'controles': 'no es un dict'}), json.dumps({'controles': {'cifras': 'modo_raro'}})])
def test_fichero_versionado_roto_falla_cerrado(tmp_path, contenido):
    ruta = tmp_path / 'controles.json'
    ruta.write_text(contenido, encoding='utf-8')
    with pytest.raises(interruptores.ErrorDeControles):
        interruptores.modo('cifras', ruta)

def test_un_despliegue_roto_no_puede_pasar_por_bueno_ni_en_sombra_ni_en_apagado(tmp_path):
    """Public CI documentation."""
    ruta = tmp_path / 'controles.json'
    ruta.write_text('{roto', encoding='utf-8')
    with pytest.raises(interruptores.ErrorDeControles) as e:
        interruptores.modo('cifras', ruta)
    assert str(ruta) in str(e.value)

def test_nombre_desconocido_es_un_error_no_un_apagado(tmp_path):
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado')
    with pytest.raises(interruptores.ErrorDeControles, match='control desconocido'):
        interruptores.modo('control_que_no_existe', ruta)

@pytest.mark.parametrize('aprobado, local, esperado', [('bloquea', 'sombra', 'sombra'), ('bloquea', 'apagado', 'apagado'), ('sombra', 'apagado', 'apagado')])
def test_fichero_local_que_baja_manda(tmp_path, aprobado, local, esperado):
    ruta = _controles(tmp_path / 'controles.json', cifras=aprobado)
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'cifras': local}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == esperado

@pytest.mark.parametrize('aprobado, local', [('apagado', 'sombra'), ('apagado', 'bloquea'), ('sombra', 'bloquea')])
def test_fichero_local_que_intenta_subir_no_manda(tmp_path, aprobado, local):
    ruta = _controles(tmp_path / 'controles.json', cifras=aprobado)
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'cifras': local}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == aprobado

def test_fichero_local_con_un_control_que_no_esta_en_el_no_lo_toca(tmp_path):
    ruta = _controles(tmp_path / 'controles.json', cifras='bloquea')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'otro_control': 'apagado'}}), encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == 'bloquea'

@pytest.mark.parametrize('contenido', ['{roto', json.dumps({'controles': {'cifras': 'modo_raro'}}), json.dumps(['no es un dict'])])
def test_fichero_local_roto_se_ignora_y_avisos_lo_dice(tmp_path, contenido):
    ruta = _controles(tmp_path / 'controles.json', cifras='bloquea')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(contenido, encoding='utf-8')
    assert interruptores.modo('cifras', ruta) == 'bloquea'
    avisos = interruptores.avisos()
    assert len(avisos) == 1 and avisos[0].startswith('AVISO:') and (str(interruptores.ruta_local()) in avisos[0])

def test_sin_fichero_local_no_hay_avisos(tmp_path):
    ruta = _controles(tmp_path / 'controles.json', cifras='bloquea')
    interruptores.modo('cifras', ruta)
    assert interruptores.avisos() == []

def test_forzado_con_nombre_manda_sobre_aprobado_y_local(tmp_path, monkeypatch):
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado')
    interruptores.ruta_local().parent.mkdir(parents=True, exist_ok=True)
    interruptores.ruta_local().write_text(json.dumps({'controles': {'cifras': 'apagado'}}), encoding='utf-8')
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({'cifras': 'bloquea'}))
    assert interruptores.modo('cifras', ruta) == 'bloquea'

def test_forzado_con_comodin_manda_para_cualquier_control_no_nombrado(tmp_path, monkeypatch):
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado', cubre_estricto='apagado')
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({'*': 'sombra'}))
    assert interruptores.modo('cifras', ruta) == 'sombra' and interruptores.modo('cubre_estricto', ruta) == 'sombra'

def test_forzado_con_nombre_y_comodin_el_nombre_gana(tmp_path, monkeypatch):
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado', cubre_estricto='apagado')
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({'*': 'sombra', 'cifras': 'bloquea'}))
    assert interruptores.modo('cifras', ruta) == 'bloquea' and interruptores.modo('cubre_estricto', ruta) == 'sombra'

def test_forzado_sigue_exigiendo_un_nombre_aprobado(tmp_path, monkeypatch):
    """Public CI documentation."""
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado')
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({'*': 'bloquea'}))
    with pytest.raises(interruptores.ErrorDeControles, match='control desconocido'):
        interruptores.modo('control_que_no_existe', ruta)

@pytest.mark.parametrize('valor, mensaje', [('{no es json', 'no es JSON'), (json.dumps(['no es un dict']), 'modo desconocido'), (json.dumps({'cifras': 'modo_raro'}), 'modo desconocido')])
def test_forzado_mal_formado_falla(tmp_path, monkeypatch, valor, mensaje):
    ruta = _controles(tmp_path / 'controles.json', cifras='apagado')
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, valor)
    with pytest.raises(interruptores.ErrorDeControles, match=mensaje):
        interruptores.modo('cifras', ruta)

def test_sin_forzado_no_pasa_nada(tmp_path, monkeypatch):
    monkeypatch.setenv('ICT155_ALMACEN_CONTEXTO', 'compatibilidad_historica')
    monkeypatch.delenv(interruptores.VARIABLE_FORZADOS, raising=False)
    ruta = _controles(tmp_path / 'controles.json', cifras='sombra')
    assert interruptores.modo('cifras', ruta) == 'sombra'

def test_anotar_sombra_escribe_una_linea_json():
    interruptores.anotar_sombra('cifras', {'tema': 't', 'detalle': 'x'})
    lineas = interruptores.ruta_sombra().read_text(encoding='utf-8').splitlines()
    assert len(lineas) == 1
    d = json.loads(lineas[0])
    assert d['control'] == 'cifras' and d['tema'] == 't' and (d['detalle'] == 'x') and ('hora' in d)

def test_anotar_sombra_acumula_una_linea_por_disparo():
    interruptores.anotar_sombra('cifras', {'n': 1})
    interruptores.anotar_sombra('cifras', {'n': 2})
    lineas = interruptores.ruta_sombra().read_text(encoding='utf-8').splitlines()
    assert [json.loads(l)['n'] for l in lineas] == [1, 2]

def test_anotar_sombra_nunca_rompe_si_no_puede_escribir(monkeypatch, tmp_path):
    """Public CI documentation."""
    obstaculo = tmp_path / 'registro'
    obstaculo.write_text('soy un fichero, no una carpeta', encoding='utf-8')
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(obstaculo / 'cowork'))
    interruptores.anotar_sombra('cifras', {'n': 1})

def _ejecutar(args: list[str], env: dict) -> tuple[int, str]:
    r = subprocess.run([sys.executable, '-X', 'utf8', str(HERRAMIENTA), *args], cwd=RAIZ, env=env, capture_output=True, timeout=60)
    assert r.returncode in (0, 2), r.stderr.decode('utf-8', 'replace')
    return (r.returncode, r.stdout.decode('utf-8', 'replace'))

def _entorno(local_appdata: Path, extra: dict | None=None) -> dict:
    import os
    env = {**os.environ, 'LOCALAPPDATA': str(local_appdata), 'PYTHONIOENCODING': 'utf-8'}
    env.pop('ICT155_COWORK_AUDIT_DIR', None)
    env.pop(interruptores.VARIABLE_FORZADOS, None)
    if extra:
        env.update(extra)
    return env

def _ruta_local_de(local_appdata: Path) -> Path:
    return local_appdata / 'ict155' / 'cowork' / 'controles_local.json'

def test_todo_a_sombra_pone_todos_los_controles_aprobados_en_sombra(tmp_path):
    lad = tmp_path / 'lad'
    rc, salida = _ejecutar([], _entorno(lad))
    assert rc == 0
    escrito = json.loads(_ruta_local_de(lad).read_text(encoding='utf-8'))['controles']
    aprobados = interruptores._aprobados()
    assert set(escrito) == set(aprobados) and all((m == 'sombra' for m in escrito.values()))
    assert all((c in salida for c in escrito))

def test_todo_a_sombra_con_apagar_pone_todo_en_apagado(tmp_path):
    lad = tmp_path / 'lad'
    rc, salida = _ejecutar(['--apagar'], _entorno(lad))
    assert rc == 0
    escrito = json.loads(_ruta_local_de(lad).read_text(encoding='utf-8'))['controles']
    assert all((m == 'apagado' for m in escrito.values()))

def test_todo_a_sombra_conserva_lo_que_ya_estaba_mas_bajo(tmp_path):
    lad = tmp_path / 'lad'
    ruta_local = _ruta_local_de(lad)
    ruta_local.parent.mkdir(parents=True)
    algun_control = next(iter(interruptores._aprobados()))
    ruta_local.write_text(json.dumps({'controles': {algun_control: 'apagado'}}), encoding='utf-8')
    rc, _ = _ejecutar([], _entorno(lad))
    assert rc == 0
    escrito = json.loads(ruta_local.read_text(encoding='utf-8'))['controles']
    assert escrito[algun_control] == 'apagado'
    assert all((m == 'sombra' for c, m in escrito.items() if c != algun_control))

def test_todo_a_sombra_no_sube_lo_que_ya_estaba_en_bloquea_al_apagar(tmp_path):
    """Public CI documentation."""
    lad = tmp_path / 'lad'
    ruta_local = _ruta_local_de(lad)
    ruta_local.parent.mkdir(parents=True)
    algun_control = next(iter(interruptores._aprobados()))
    ruta_local.write_text(json.dumps({'controles': {algun_control: 'apagado'}}), encoding='utf-8')
    rc, _ = _ejecutar(['--apagar'], _entorno(lad))
    assert rc == 0
    escrito = json.loads(ruta_local.read_text(encoding='utf-8'))['controles']
    assert all((m == 'apagado' for m in escrito.values()))

def test_todo_a_sombra_con_un_fichero_local_roto_lo_sobrescribe_entero(tmp_path):
    lad = tmp_path / 'lad'
    ruta_local = _ruta_local_de(lad)
    ruta_local.parent.mkdir(parents=True)
    ruta_local.write_text('{roto', encoding='utf-8')
    rc, salida = _ejecutar([], _entorno(lad))
    assert rc == 0
    escrito = json.loads(ruta_local.read_text(encoding='utf-8'))['controles']
    assert all((m == 'sombra' for m in escrito.values()))
    assert 'AVISO' in salida

def test_todo_a_sombra_con_argumento_desconocido_sale_con_dos(tmp_path):
    rc, salida = _ejecutar(['--algo-raro'], _entorno(tmp_path / 'lad'))
    assert rc == 2 and 'Uso' in salida
