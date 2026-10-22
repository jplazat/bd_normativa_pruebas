"""Public CI documentation."""
from __future__ import annotations
import copy
import json
import shutil
import sys
from pathlib import Path
import pytest
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'herramientas' / 'fase2'))
from ict155 import brechas, db
import generar_carpeta as gc
REV22 = Path('D:\\Proyectos\\r27\\tmp\\rev22')
CORTE = '2026-10-20'

@pytest.fixture(scope='module')
def con():
    c = db.conectar(solo_lectura=True)
    c.execute('PRAGMA query_only=ON')
    yield c
    c.close()

@pytest.fixture
def registros(tmp_path):
    resultado = {}
    for nombre in ('estados', 'posterior', 'interno_heredado', 'citas'):
        origen = REV22 / f'carpeta_{nombre}.json'
        copia = tmp_path / origen.name
        shutil.copy2(origen, copia)
        resultado[nombre] = brechas.leer_registro(copia)
    return resultado

def test_h4_matriz_clasifica_y_rotula_como_informe(con, registros, tmp_path):
    registro = registros['estados']
    destino = tmp_path / 'cliente'
    res = gc.generar(con, registro, destino, fecha=CORTE)
    esperadas = {b['id'] for b in registro['brechas'] if brechas._situacion_carencia_fase2(b, CORTE) == 'cerrada'}
    assert set(res.cerradas) == esperadas
    assert len(res.subcarpetas) == 12
    indice = (destino / 'INDICE.md').read_text(encoding='utf-8')
    for b in registro['brechas']:
        situacion = brechas._situacion_carencia_fase2(b, CORTE)
        if b['id'] in esperadas:
            continue
        nombre = next((n for n in res.subcarpetas if n.startswith(b['id'] + ' -')))
        leeme = (destino / nombre / 'LEEME.md').read_text(encoding='utf-8')
        assert f'Estado: **{situacion}**' in leeme
        assert f"| {b['id']} | Control sintético | {situacion} |" in indice
    assert any(('cerrada-no_cumple' in a for a in res.avisos))
    interno = (tmp_path / 'cliente_INTERNO.csv').read_text(encoding='utf-8-sig')
    for bid in ('cerrada-no_cumple', 'cerrada-parcial', 'cerrada-pendiente', 'abierta-cumple'):
        assert bid in interno and 'AVISO:' in interno

def test_h4_cli_corte_y_aviso_visible(con, registros, tmp_path, capsys):
    ruta = tmp_path / 'posterior.json'
    ruta.write_text(json.dumps(registros['posterior']), encoding='utf-8')
    destino = tmp_path / 'cliente'
    rc = gc.main(['--registro', str(ruta), '--destino', str(destino), '--corte', CORTE, '--fecha', CORTE])
    salida = capsys.readouterr()
    assert rc == 0
    assert 'AVISO:' in salida.out and 'POST-01' in salida.out
    assert 'Cerradas listadas (0)' in salida.out
    nombre = next((p for p in destino.iterdir() if p.is_dir()))
    assert 'Estado: **abierta**' in (nombre / 'LEEME.md').read_text(encoding='utf-8')
    assert 'POST-01' in (tmp_path / 'cliente_INTERNO.csv').read_text(encoding='utf-8-sig')

def test_h4_solo_revision_posterior_y_corte_por_defecto(con, registros, tmp_path, monkeypatch):
    b = registros['posterior']['brechas'][0]
    b['revisiones'] = b['revisiones'][1:]

    class Hoy(gc.datetime.date):

        @classmethod
        def today(cls):
            return cls(2026, 10, 20)
    monkeypatch.setattr(gc.datetime, 'date', Hoy)
    res = gc.generar(con, registros['posterior'], tmp_path / 'cliente')
    assert not res.cerradas and len(res.subcarpetas) == 1
    leeme = (tmp_path / 'cliente' / res.subcarpetas[0] / 'LEEME.md').read_text(encoding='utf-8')
    assert 'sin información a la fecha de corte' in leeme
    assert '21/10/2026' not in leeme

@pytest.mark.parametrize('reemplazar', [False, True])
def test_h8_enumera_todos_los_internos_sin_tocar_nada(con, registros, tmp_path, reemplazar):
    destino = tmp_path / 'cliente'
    (destino / 'sub').mkdir(parents=True)
    nombres = ['ANTIGUO_INTERNO.csv', 'sub/nota_para_responsable.md', 'sub/X_COMPROBACION.txt', 'registro_ANTERIOR_ayer.json']
    for n in nombres:
        (destino / n).write_bytes(b'CONTROL SINTETICO CONSERVADO')
    antes = {str(p.relative_to(destino)): p.read_bytes() for p in destino.rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError) as exc:
        gc.generar(con, registros['interno_heredado'], destino, reemplazar=reemplazar)
    assert all((Path(n).name in str(exc.value) for n in nombres))
    assert antes == {str(p.relative_to(destino)): p.read_bytes() for p in destino.rglob('*') if p.is_file()}
    assert not (tmp_path / 'cliente_INTERNO.csv').exists()

def test_h8_cli_negativa(con, registros, tmp_path, capsys):
    destino = tmp_path / 'cliente'
    destino.mkdir()
    (destino / 'ANTIGUO_INTERNO.csv').write_bytes(b'CONTROL SINTETICO')
    ruta = tmp_path / 'registro.json'
    ruta.write_text(json.dumps(registros['interno_heredado']), encoding='utf-8')
    rc = gc.main(['--registro', str(ruta), '--destino', str(destino), '--reemplazar'])
    salida = capsys.readouterr()
    assert rc != 0 and 'ANTIGUO_INTERNO.csv' in salida.err
    assert 'Subcarpetas creadas' not in salida.out

@pytest.mark.parametrize('cerrada', [False, True])
@pytest.mark.parametrize('ident', ['ICT155-DOC-SINTETICA_REV22@2026-10-01::apartado_interno', 'Orden ICT/155/2020::anexo.INEXISTENTE_S11J/ap.999'])
def test_h9_cita_no_resuelta_niega_antes_de_escribir(con, registros, tmp_path, capsys, ident, cerrada):
    registro = copy.deepcopy(registros['citas'])
    b = registro['brechas'][0]
    b['citas'] = [{'identificador': ident}]
    if cerrada:
        b['estado'] = 'cerrada'
    sana = copy.deepcopy(b)
    sana.update(id='SANA-01', estado='abierta', citas=[])
    registro['brechas'].insert(0, sana)
    ruta = tmp_path / 'registro.json'
    ruta.write_text(json.dumps(registro), encoding='utf-8')
    destino = tmp_path / 'cliente'
    rc = gc.main(['--registro', str(ruta), '--destino', str(destino)])
    salida = capsys.readouterr()
    assert rc != 0
    assert 'SYN-01' in salida.err and ident in salida.err
    assert not destino.exists()
    assert not (tmp_path / 'cliente_INTERNO.csv').exists()

def test_h9_resueltas_publica_y_licenciada_admitidas(registros, tmp_path):
    from soporte_generar_carpeta_r27_2026_10_17 import _obra
    con = db.crear(tmp_path / 'sintetica.sqlite')
    _obra(con, 'PUBLICA-S11J', 'Obra sintética pública', 'publico', [('art.1', 'Artículo 1', 'TEXTO PUBLICO SINTETICO S11J', 1)])
    _obra(con, 'LICENCIADA-S11J', 'Obra sintética licenciada', 'licenciado', [('art.1', 'Artículo 1', 'TEXTO LICENCIADO SINTETICO S11J', 1)])
    con.commit()
    registro = registros['citas']
    registro['brechas'][0]['citas'] = [{'identificador': f'{obra}::art.1'} for obra in ('PUBLICA-S11J', 'LICENCIADA-S11J')]
    try:
        res = gc.generar(con, registro, tmp_path / 'cliente')
    finally:
        con.close()
    assert len(res.subcarpetas) == 1
    texto = (tmp_path / 'cliente' / res.subcarpetas[0] / 'LEEME.md').read_text(encoding='utf-8')
    assert gc.NOTA_LICENCIA in texto
    assert 'TEXTO PUBLICO SINTETICO S11J' in texto
    assert 'TEXTO LICENCIADO SINTETICO S11J' not in texto
    assert 'NO_CONSTA' not in texto and 'apartado_interno' not in texto

@pytest.mark.parametrize('corte', ['2026-02-30', '20/10/2026', '2026-1-2', '0000-01-01'])
def test_corte_invalido_se_rechaza_sin_escribir(con, registros, tmp_path, corte):
    with pytest.raises(ValueError):
        gc.generar(con, registros['estados'], tmp_path / 'cliente', corte=corte)
    assert not (tmp_path / 'cliente').exists()

def test_corte_explicito_prevalece_y_emision_limita_contenido(con, registros, tmp_path):
    registro = registros['posterior']
    registro['fecha_corte'] = '2026-10-01'
    abierto = gc.generar(con, registro, tmp_path / 'abierto', corte='2026-10-22', fecha=CORTE)
    assert not abierto.cerradas and len(abierto.subcarpetas) == 1
    cerrado = gc.generar(con, registro, tmp_path / 'cerrado', corte='2026-10-22', fecha='2026-10-22')
    assert cerrado.cerradas == ['POST-01'] and (not cerrado.subcarpetas)
    assert not cerrado.avisos
