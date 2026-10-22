"""R27-S2h (18-oct-2026): REVISION_GPT7A.md, hallazgos 8, 9, 10 y 13 sobre la palanca de emergencia
(`herramientas/todo_a_sombra.py`) y la parte de `ict155/interruptores.py` que lee el fichero local.

- 9 (ALTA): con un local `{"*":"apagado"}` y aprobados en «bloquea», la palanca SUBÍA los modos a «sombra»: el
  comodín sin entradas nombradas se perdía del todo (`nuevo_contenido` solo miraba si el NOMBRE del control estaba
  en el local, nunca el comodín) y cada control pasaba al objetivo completo. Ahora el límite de cada control es su
  entrada explícita o, si no tiene, la del comodín; se escribe el menor entre ese límite y el objetivo, y el propio
  comodín se conserva si ya era igual o más bajo que el objetivo.
- 10 (ALTA): la escritura no era atómica y no comprobaba lo que de verdad quedó escrito. Ahora escribe a un
  temporal en la misma carpeta y lo sustituye con `os.replace`, y después vuelve a leer con `interruptores.modo()`
  (salvo que `cowork/controles.json` esté roto): si algún control no quedó en el objetivo o más bajo, sale con
  rc≠0 diciendo cuál y por qué.
- 8 (ALTA): si `ICT155_CONTROLES_FORZADOS` está definida en el entorno, manda sobre lo que acaba de escribir la
  palanca. Ahora avisa de eso por stderr y sale con rc≠0 aunque la escritura haya ido bien.
- 13: al final se imprime, por control, el modo efectivo que queda y la orden exacta para deshacerlo.

`modo()` en sí (sin fichero local y sin forzados) no se toca: sigue siendo, byte a byte, el de antes.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import pytest
from ict155 import interruptores
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
HERRAMIENTA = RAIZ / 'herramientas' / 'todo_a_sombra.py'

def _controles(ruta: Path, **modos: str) -> Path:
    ruta.write_text(json.dumps({'controles': modos}, ensure_ascii=False), encoding='utf-8')
    return ruta

@pytest.fixture
def tas():
    """Carga `todo_a_sombra.py` fresco (como `test_r27_s7c_2026_10_18.py`), para poder parchear su `interruptores`
    sin afectar a otros ficheros de prueba que importan el módulo real."""
    spec = importlib.util.spec_from_file_location('todo_a_sombra_s2h', HERRAMIENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """Registro (local + sombra.log) en una carpeta de la propia prueba, nunca en %LOCALAPPDATA% real; y sin
    forzados heredados de fuera, salvo que la prueba los ponga ella misma."""
    monkeypatch.setenv('ICT155_COWORK_AUDIT_DIR', str(tmp_path / 'registro'))
    monkeypatch.setenv('ICT155_ALMACEN_CONTEXTO', 'compatibilidad_historica')
    monkeypatch.delenv(interruptores.VARIABLE_FORZADOS, raising=False)
    return tmp_path

def test_nuevo_contenido_comodin_solo_no_sube_los_controles(tas):
    """El escenario exacto del hallazgo 9: local `{"*":"apagado"}`, aprobados en «bloquea», objetivo «sombra». Antes,
    como ningún control tenía una entrada NOMBRADA, cada uno pasaba directo al objetivo («sombra»): subía dos
    controles que el comodín ya tenía en «apagado»."""
    aprobados = {'cifras': 'bloquea', 'cubre_estricto': 'bloquea'}
    actual = {'*': 'apagado'}
    nuevo = tas.nuevo_contenido(aprobados, actual, 'sombra')
    assert nuevo['cifras'] == 'apagado'
    assert nuevo['cubre_estricto'] == 'apagado'

def test_nuevo_contenido_conserva_el_comodin_si_ya_estaba_mas_bajo(tas):
    """El comodín en sí se mantiene en lo escrito (para que los controles que todavía no existen en
    `cowork/controles.json` sigan bajados cuando se añadan)."""
    nuevo = tas.nuevo_contenido({'cifras': 'bloquea'}, {'*': 'apagado'}, 'sombra')
    assert nuevo['*'] == 'apagado'

def test_nuevo_contenido_entrada_nombrada_gana_al_comodin(tas):
    """Una entrada explícita para un control manda sobre el comodín, pero sigue topada por el objetivo (ni el
    comodín ni una entrada nombrada pueden hacer que la palanca suba un control por encima del objetivo)."""
    nuevo = tas.nuevo_contenido({'cifras': 'bloquea', 'cubre_estricto': 'bloquea'}, {'*': 'apagado', 'cifras': 'bloquea'}, 'sombra')
    assert nuevo['cifras'] == 'sombra'
    assert nuevo['cubre_estricto'] == 'apagado'
    assert nuevo['*'] == 'apagado'

def test_nuevo_contenido_comodin_mas_alto_que_el_objetivo_no_se_conserva(tas):
    """Si el comodín ya estaba por ENCIMA del objetivo (p.ej. «bloquea» con objetivo «sombra»), no tiene sentido
    conservarlo tal cual: no bajaría nada. Los controles sin entrada nombrada quedan en el objetivo de todas formas
    (el comodín, como límite, no es más bajo que el objetivo, así que `min` da el objetivo)."""
    nuevo = tas.nuevo_contenido({'cifras': 'bloquea'}, {'*': 'bloquea'}, 'sombra')
    assert nuevo['cifras'] == 'sombra'
    assert nuevo['*'] == 'sombra'

def test_nuevo_contenido_sin_comodin_ni_entrada_sigue_como_antes(tas):
    """Caso de control: sin nada en el local, cada control aprobado pasa al objetivo completo, como siempre."""
    nuevo = tas.nuevo_contenido({'cifras': 'bloquea', 'cubre_estricto': 'sombra'}, {}, 'sombra')
    assert nuevo == {'cifras': 'sombra', 'cubre_estricto': 'sombra'}

def test_e2e_comodin_solo_no_sube_los_modos_efectivos(tmp_path, monkeypatch, tas):
    """De punta a punta: escribe el local real con `{"*":"apagado"}`, ejecuta la palanca contra unos aprobados en
    «bloquea», y comprueba con `interruptores.modo()` (no solo el JSON escrito) que los controles siguen en
    «apagado»: la palanca no los subió a «sombra»."""
    aprobados_ruta = _controles(tmp_path / 'controles.json', cifras='bloquea', cubre_estricto='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    ruta_local = interruptores.ruta_local()
    ruta_local.parent.mkdir(parents=True, exist_ok=True)
    ruta_local.write_text(json.dumps({'controles': {'*': 'apagado'}}), encoding='utf-8')
    rc = tas.main([])
    assert rc == 0
    escrito = json.loads(ruta_local.read_text(encoding='utf-8'))['controles']
    assert escrito['cifras'] == 'apagado' and escrito['cubre_estricto'] == 'apagado' and (escrito['*'] == 'apagado')
    assert interruptores.modo('cifras', aprobados_ruta) == 'apagado'
    assert interruptores.modo('cubre_estricto', aprobados_ruta) == 'apagado'

def test_escritura_atomica_no_deja_temporales(tmp_path, tas):
    ruta = tmp_path / 'controles_local.json'
    tas._escribir_atomico(ruta, {'controles': {'cifras': 'sombra'}})
    assert json.loads(ruta.read_text(encoding='utf-8'))['controles'] == {'cifras': 'sombra'}
    assert list(tmp_path.glob('*.tmp*')) == []

def test_escritura_atomica_si_falla_no_toca_el_fichero_anterior(tmp_path, monkeypatch, tas):
    """Si la escritura del temporal falla a medias, el fichero que ya existía no se ha tocado: no hay un momento en
    que `ruta` esté a medio escribir, porque nunca se escribe sobre `ruta` directamente."""
    ruta = tmp_path / 'controles_local.json'
    ruta.write_text(json.dumps({'controles': {'cifras': 'apagado'}}), encoding='utf-8')
    original_write_text = Path.write_text

    def falla_si_es_temporal(self, *a, **kw):
        if '.tmp' in self.name:
            raise OSError('disco lleno (simulado)')
        return original_write_text(self, *a, **kw)
    monkeypatch.setattr(Path, 'write_text', falla_si_es_temporal)
    with pytest.raises(OSError):
        tas._escribir_atomico(ruta, {'controles': {'cifras': 'sombra'}})
    assert json.loads(ruta.read_text(encoding='utf-8'))['controles'] == {'cifras': 'apagado'}

def test_verificacion_detecta_un_control_que_no_quedo_abajo_y_sale_con_rc_no_cero(tmp_path, monkeypatch, tas, capsys):
    """Simula que, tras escribir, volver a leer con `interruptores.modo()` muestra un control que NO quedó en el
    objetivo o más bajo (como pasaría con una escritura a medias que una consulta concurrente alcanzara a leer):
    la palanca debe decirlo y salir con rc≠0, no callárselo con rc=0."""
    aprobados_ruta = _controles(tmp_path / 'controles.json', cifras='bloquea', cubre_estricto='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    real_modo = tas.interruptores.modo

    def modo_que_miente(nombre, ruta=None):
        if nombre == 'cifras':
            return 'bloquea'
        return real_modo(nombre, ruta)
    monkeypatch.setattr(tas.interruptores, 'modo', modo_que_miente)
    rc = tas.main([])
    _, err = capsys.readouterr()
    assert rc != 0
    assert 'cifras' in err and 'bloquea' in err

def test_sin_mentiras_la_verificacion_pasa_y_rc_es_cero(tmp_path, monkeypatch, tas):
    """Caso de control: sin nada que falle, la comprobación posterior a la escritura no cambia el rc=0 de siempre."""
    aprobados_ruta = _controles(tmp_path / 'controles.json', cifras='bloquea', cubre_estricto='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    rc = tas.main([])
    assert rc == 0

def test_forzados_en_el_entorno_avisa_y_sale_con_rc_no_cero_aunque_escriba_bien(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / 'controles.json', cifras='bloquea', cubre_estricto='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    monkeypatch.setenv(interruptores.VARIABLE_FORZADOS, json.dumps({'*': 'apagado'}))
    rc = tas.main([])
    _, err = capsys.readouterr()
    assert rc != 0
    assert interruptores.VARIABLE_FORZADOS in err
    assert 'producción' in err or 'produccion' in err
    escrito = json.loads(interruptores.ruta_local().read_text(encoding='utf-8'))['controles']
    assert escrito == {'cifras': 'sombra', 'cubre_estricto': 'sombra'}

def test_sin_forzados_no_hay_aviso_ni_rc_distinto(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / 'controles.json', cifras='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    rc = tas.main([])
    _, err = capsys.readouterr()
    assert rc == 0
    assert interruptores.VARIABLE_FORZADOS not in err

def test_imprime_el_modo_efectivo_por_control_y_la_orden_para_deshacer(tmp_path, monkeypatch, tas, capsys):
    aprobados_ruta = _controles(tmp_path / 'controles.json', cubre_estricto='bloquea')
    monkeypatch.setattr(tas.interruptores, 'RUTA_CONTROLES', aprobados_ruta)
    rc = tas.main([])
    salida, _ = capsys.readouterr()
    assert rc == 0
    assert 'cubre_estricto: sombra' in salida
    assert str(interruptores.ruta_local()) in salida
    assert 'borra' in salida.lower() or 'edita' in salida.lower()

def test_sin_fichero_local_y_sin_forzados_modo_es_igual_que_antes(tmp_path):
    """`modo()` por sí mismo, sin fichero local y sin `ICT155_CONTROLES_FORZADOS`, no lo toca este encargo: sigue
    siendo exactamente lo aprobado, byte a byte como antes de que existiera la palanca."""
    ruta = _controles(tmp_path / 'controles.json', cifras='bloquea', cubre_estricto='apagado')
    assert interruptores.modo('cifras', ruta) == 'bloquea'
    assert interruptores.modo('cubre_estricto', ruta) == 'apagado'

@pytest.mark.parametrize('aprobado, comodin, objetivo', [('bloquea', 'sombra', 'sombra'), ('bloquea', 'apagado', 'apagado'), ('sombra', 'apagado', 'apagado'), ('bloquea', 'bloquea', 'bloquea')])
def test_nuevo_contenido_nunca_sube_un_modo(tas, aprobado, comodin, objetivo):
    """Propiedad general (no solo el caso puntual del hallazgo 9): cualquiera que sea la combinación de aprobado,
    comodín y objetivo, el modo escrito nunca queda por ENCIMA de lo que ya tenía el comodín ni por encima del
    objetivo."""
    ORDEN = tas.ORDEN
    nuevo = tas.nuevo_contenido({'cifras': aprobado}, {'*': comodin}, objetivo)
    assert ORDEN[nuevo['cifras']] <= ORDEN[comodin]
    assert ORDEN[nuevo['cifras']] <= ORDEN[objetivo]
