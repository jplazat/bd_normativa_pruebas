"""Public CI documentation."""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import importlib
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from ict155 import almacen, hechos, interruptores, relacionados, sucesion
RAIZ = Path(__file__).resolve().parents[1]
VISTA = 'cowork/limites_conocidos.json'
ANTIGUO = b'{"origen":"antiguo_sintetico"}'
PUBLICADO = b'{"origen":"almacen_sintetico"}'

def escribir_json(ruta, dato):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix('.nuevo')
    temporal.write_text(json.dumps(dato), encoding='utf-8')
    os.replace(temporal, ruta)

def preparar_almacen(carpeta):
    repo = carpeta / 'repo'
    for vista in almacen.VISTAS:
        destino = repo / vista
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(ANTIGUO)
    cuerpo = {'ficheros': {v: {'sha256': hashlib.sha256(PUBLICADO).hexdigest(), 'bytes': len(PUBLICADO)} for v in almacen.VISTAS}}
    huella = hashlib.sha256(json.dumps(cuerpo, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    entrega = repo / 'datos/almacen' / huella
    for vista in almacen.VISTAS:
        destino = entrega / vista
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(PUBLICADO)
    escribir_json(entrega / 'MANIFIESTO.json', {**cuerpo, 'huella_entrega': huella})
    escribir_json(repo / 'cowork/almacen_unico.json', {'huella_entrega': huella})
    escribir_json(carpeta / 'controles.json', {'controles': {**dict.fromkeys(interruptores.CONTROLES_CONOCIDOS, 'apagado'), 'almacen_unico': 'activo'}})

@contextmanager
def entorno_almacen(carpeta):
    """Public CI documentation."""
    repo = carpeta / 'repo'
    with ExitStack() as pila:
        pila.enter_context(patch.dict(os.environ))
        for nombre in ('ICT155_CONTROLES_FORZADOS', 'ICT155_ALMACEN_AUDIT_DIR'):
            os.environ.pop(nombre, None)
        os.environ.update(LOCALAPPDATA=str(carpeta / 'local'), ICT155_COWORK_AUDIT_DIR=str(carpeta / 'local/ict155/cowork'))
        pila.enter_context(patch.object(interruptores, 'RUTA_CONTROLES', carpeta / 'controles.json'))
        pila.enter_context(patch.object(almacen, 'REPO', repo))
        pila.enter_context(patch.object(almacen, 'RUTA_CONFIG', repo / 'cowork/almacen_unico.json'))
        pila.enter_context(patch.object(almacen, '_RUTAS', {repo / v: v for v in almacen.VISTAS}))
        yield

def palanca():
    spec = importlib.util.spec_from_file_location('h34_palanca', RAIZ / 'herramientas/todo_a_sombra.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

class H3(unittest.TestCase):

    def setUp(self):
        base = os.environ.get('ICT155_H34_TMP')
        if base:
            Path(base).mkdir(parents=True, exist_ok=True)
        self.temporal = tempfile.TemporaryDirectory(prefix='h34_', dir=base)
        self.addCleanup(self.temporal.cleanup)
        self.carpeta = Path(self.temporal.name)
        preparar_almacen(self.carpeta)
        self.pila = ExitStack()
        self.addCleanup(self.pila.close)
        self.pila.enter_context(entorno_almacen(self.carpeta))
        self.ruta = self.carpeta / 'repo' / VISTA

    def bajar(self, modo, nombre='almacen_unico'):
        escribir_json(interruptores.ruta_local(), {'controles': {nombre: modo}})

    def test_palanca_mismo_proceso_apaga_consumidor_caliente(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        salida = io.StringIO()
        with redirect_stdout(salida), redirect_stderr(io.StringIO()):
            self.assertEqual(palanca().main(['--apagar']), 0)
        self.assertIn('almacen_unico: apagado', salida.getvalue())
        self.assertEqual(interruptores.modo('almacen_unico'), 'apagado')
        self.assertEqual(almacen.modo_para(self.ruta), 'apagado')
        self.assertEqual(almacen.leer(self.ruta), ANTIGUO)

    def test_local_baja_y_se_restaura_sin_reiniciar_cinco_vistas(self):
        for vista in almacen.VISTAS:
            self.assertEqual(almacen.leer(self.carpeta / 'repo' / vista), PUBLICADO)
        for modo in ('sombra', 'apagado'):
            self.bajar(modo)
            for vista in almacen.VISTAS:
                ruta = self.carpeta / 'repo' / vista
                self.assertEqual(almacen.modo_para(ruta), modo)
                self.assertEqual(almacen.leer(ruta), ANTIGUO)
        interruptores.ruta_local().unlink()
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)

    def test_aprobados_reemplazados_sin_cambiar_tamano_ni_mtime(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        ruta = interruptores.RUTA_CONTROLES
        antes = ruta.stat()
        bruto = ruta.read_bytes().replace(b'"activo"', b'"sombra"')
        ruta.write_bytes(bruto)
        os.utime(ruta, ns=(antes.st_atime_ns, antes.st_mtime_ns))
        self.assertEqual(ruta.stat().st_size, antes.st_size)
        self.assertEqual(almacen.modo_para(self.ruta), 'sombra')
        self.assertEqual(almacen.leer(self.ruta), ANTIGUO)

    def test_aprobados_rotos_tras_lectura_activa_fallan_cerrados(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        interruptores.RUTA_CONTROLES.write_text('{', encoding='utf-8')
        with self.assertRaises(interruptores.ErrorDeControles):
            almacen.leer(self.ruta)

    def test_precedencia_comodin_local_no_sube_y_forzado_manda(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        self.bajar('apagado', '*')
        self.assertEqual(almacen.leer(self.ruta), ANTIGUO)
        self.bajar('activo')
        escribir_json(interruptores.RUTA_CONTROLES, {'controles': {'almacen_unico': 'sombra'}})
        self.assertEqual(almacen.modo_para(self.ruta), 'sombra')
        with patch.dict(os.environ, {interruptores.VARIABLE_FORZADOS: '{"almacen_unico":"activo"}'}):
            self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        self.assertEqual(almacen.modo_para(self.ruta), 'sombra')

    def test_apagado_no_consulta_entrega_y_precalculado_obsoleto_cierra(self):
        anterior = almacen.modo_para(self.ruta)
        self.bajar('apagado')
        with patch.object(almacen, '_publicada', side_effect=AssertionError('entrega apagada')):
            self.assertEqual(almacen.leer(self.ruta), ANTIGUO)
            with self.assertRaises(almacen.ErrorDeAlmacen):
                almacen.leer(self.ruta, modo=anterior)

    def test_cache_de_lectores_no_retiene_entrega_activa(self):
        for modulo, vista, clave in ((relacionados, 'cowork/preceptos_relacionados.json', 'grupos'), (sucesion, 'cowork/sucesores_revisados.json', 'sucesiones')):
            ruta = self.carpeta / 'repo' / vista
            escribir_json(ruta, {clave: []})
            modulo._CACHE.clear()
            self.addCleanup(modulo._CACHE.clear)
            with patch.object(modulo, 'RUTA_TABLA', ruta):
                with patch.object(almacen, '_publicada', return_value=json.dumps({clave: []}).encode()) as publicado:
                    modulo.cargar()
                    self.assertTrue(publicado.called)
                self.bajar('apagado')
                with patch.object(almacen, '_publicada', side_effect=AssertionError('activo retenido')):
                    self.assertEqual(modulo.cargar(), [])
                interruptores.ruta_local().unlink()

    def test_palanca_otro_proceso_afecta_consumidor_persistente(self):
        consumidor = "import json, pathlib, sys\nfrom pruebas.soporte_h34_r28_2026_10_21 import entorno_almacen, almacen, VISTA\ncarpeta=pathlib.Path(sys.argv[1])\nwith entorno_almacen(carpeta):\n for orden in sys.stdin:\n  print(json.dumps({'modo':almacen.modo_para(carpeta/'repo'/VISTA),\n                    'lectura':almacen.leer(carpeta/'repo'/VISTA).decode()}),flush=True)\n"
        entorno = {**os.environ, 'PYTHONPATH': str(RAIZ), 'PYTHONDONTWRITEBYTECODE': '1'}
        hijo = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', '-u', '-c', consumidor, str(self.carpeta)], cwd=RAIZ, env=entorno, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

        def terminar():
            if hijo.poll() is None:
                hijo.kill()
            hijo.communicate(timeout=10)
        self.addCleanup(terminar)
        hijo.stdin.write('leer\n')
        hijo.stdin.flush()
        inicial = json.loads(hijo.stdout.readline())
        self.assertEqual(inicial['modo'], 'activo')
        self.assertEqual(inicial['lectura'], PUBLICADO.decode())
        codigo = "import pathlib, sys\nfrom pruebas.soporte_h34_r28_2026_10_21 import entorno_almacen, palanca\nwith entorno_almacen(pathlib.Path(sys.argv[1])):\n sys.exit(palanca().main(['--apagar']))\n"
        cambio = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', codigo, str(self.carpeta)], cwd=RAIZ, env=entorno, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(cambio.returncode, 0, cambio.stderr)
        self.assertIn('almacen_unico: apagado', cambio.stdout)
        hijo.stdin.write('leer\n')
        hijo.stdin.flush()
        posterior = json.loads(hijo.stdout.readline())
        self.assertEqual(posterior['modo'], 'apagado')
        self.assertEqual(posterior['lectura'], ANTIGUO.decode())

class H4(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.datos = hechos.cargar()
        cls.reglas = [r for r in cls.datos.matriz_b2['reglas'] if 'modulos' in r['operador']]

    def evaluar(self, regla, combinacion, **otros):
        return hechos.b2.salida_evaluada(regla, {**otros, 'combinacion': list(combinacion)})

    def test_ag_modulos_api_revisor_ambas_permutaciones(self):
        resultados = []
        with patch.dict(os.environ, {interruptores.VARIABLE_FORZADOS: '{"entrada_hechos":"apagado"}'}):
            for combo in itertools.permutations(['B', 'F']):
                exp = hechos.expediente('Consulta ficticia', hechos={'regla': 'AG-MODULOS', 'via': 'limpia_RD_VIII', 'combinacion': list(combo)}, datos=self.datos, ensayo=True)
                self.assertEqual(exp['estado'], 'regla_propuesta')
                self.assertIsNone(exp['siguiente_pregunta'])
                self.assertTrue(exp['resultado']['combinacion_admitida'])
                declaracion = next((o for o in exp['hechos'] if o['campo'] == 'combinacion'))
                self.assertEqual(declaracion['valor'], list(combo))
                resultados.append(exp['resultado'])
        self.assertEqual(resultados[0], resultados[1])

    def variantes(self, r):
        entradas = [e for e in r['entradas'] if e['campo'] != 'combinacion']
        dominios = [e['valores'] if e['tipo'] == 'enum' else [False, True] for e in entradas]
        for valores in itertools.product(*dominios):
            yield dict(zip([e['campo'] for e in entradas], valores))

    def test_todas_las_familias_permutaciones_hasta_tres_modulos(self):
        from ict155._confirmacion_hechos import dominio
        general = dominio(self.datos, 'combinacion')['items']['enum']
        self.assertEqual(len(self.reglas), 13)
        for r in self.reglas:
            spec = next((e for e in r['entradas'] if e['campo'] == 'combinacion'))
            modulos = spec.get('elementos', general)
            for otros in self.variantes(r):
                positivo = ['A2'] if r['operador'] == 'juego_modulos' else ['B', 'D'] if r['operador'] == 'mat_modulos' else ['B', 'F']
                resultado = self.evaluar(r, positivo, **otros)
                admitida = next((v for k, v in resultado.items() if 'admitida' in k))
                if r['operador'] == 'gas_modulos' and otros['uso'] == 'otro':
                    self.assertIs(admitida, False, r['id'])
                else:
                    self.assertIs(admitida, True, r['id'])
                for n in (1, 2, 3):
                    for combo in itertools.combinations(modulos, n):
                        esperado = self.evaluar(r, combo, **otros)
                        for perm in itertools.permutations(combo):
                            with self.subTest(regla=r['id'], otros=otros, combo=perm):
                                self.assertEqual(self.evaluar(r, perm, **otros), esperado)

    def test_duplicados_vacios_y_modulos_desconocidos_se_rechazan(self):
        for r in self.reglas:
            otros = next(self.variantes(r))
            for combo in ([], ['B', 'B'], ['B', 'F', 'F'], ['DESCONOCIDO'], [17], [{}]):
                with self.subTest(regla=r['id'], combo=combo):
                    with self.assertRaises(hechos.b2.Insuficiente):
                        self.evaluar(r, combo, **otros)

    def test_combinacion_realmente_distinta_no_se_admite(self):
        r = next((r for r in self.reglas if r['id'] == 'AG-MODULOS'))
        for combo in itertools.permutations(['B', 'E']):
            self.assertFalse(self.evaluar(r, combo, via='limpia_RD_VIII')['combinacion_admitida'])

    def test_cinco_motores_rechazan_invalidos_y_respetan_permutaciones(self):
        for nombre in ('_hechos_b2', '_hechos_b2_jdap2', '_hechos_b2_jdap3', '_hechos_b2_jdap4', '_hechos_b2_jdap_corr'):
            motor = importlib.import_module('ict155.' + nombre)
            for r in self.reglas:
                for otros in self.variantes(r):
                    combos = (['B', 'F'], ['B', 'D'], ['B', 'E', 'F'], ['A2'] if r['operador'] == 'juego_modulos' else ['G'])
                    for combo in combos:
                        if any((x not in next((e for e in r['entradas'] if e['campo'] == 'combinacion')).get('elementos', combo) for x in combo)):
                            continue
                        esperado = motor.salida_evaluada(r, {**otros, 'combinacion': combo})
                        for perm in itertools.permutations(combo):
                            with self.subTest(motor=nombre, regla=r['id'], combo=perm):
                                self.assertEqual(motor.salida_evaluada(r, {**otros, 'combinacion': list(perm)}), esperado)
                    for combo in ([], ['B', 'B'], ['DESCONOCIDO']):
                        with self.subTest(motor=nombre, regla=r['id'], invalido=combo):
                            with self.assertRaises(motor.Insuficiente):
                                motor.salida_evaluada(r, {**otros, 'combinacion': combo})

    def test_api_seis_generaciones_conservan_la_misma_decision(self):
        for fichero in ('diccionario_hechos_v3.json', 'diccionario_hechos_v4.json', 'diccionario_hechos_v5.json', 'diccionario_hechos_v6.json', 'diccionario_hechos_v7.json', 'diccionario_hechos_v7_corr.json'):
            datos = hechos.cargar(RAIZ / 'datos/hechos' / fichero)
            resultados = []
            for combo in itertools.permutations(['B', 'F']):
                with self.subTest(diccionario=fichero, combo=combo):
                    exp = hechos.expediente('Consulta ficticia', hechos={'regla': 'AG-MODULOS', 'via': 'limpia_RD_VIII', 'combinacion': list(combo)}, datos=datos, ensayo=True)
                    self.assertEqual(exp['estado'], 'regla_propuesta')
                    self.assertTrue(exp['resultado']['combinacion_admitida'])
                    resultados.append(exp['resultado'])
            self.assertEqual(resultados[0], resultados[1])

    def test_api_rechaza_duplicados_vacios_y_modulos_desconocidos(self):
        for combo in ([], ['B', 'B'], ['DESCONOCIDO']):
            with self.subTest(combo=combo), self.assertRaises(hechos.ErrorDeHechos):
                hechos.expediente('Consulta ficticia', hechos={'regla': 'AG-MODULOS', 'via': 'limpia_RD_VIII', 'combinacion': combo}, datos=self.datos, ensayo=True)

    def test_calculo_no_muta_array_de_entrada(self):
        regla = next((r for r in self.reglas if r['id'] == 'AG-MODULOS'))
        combinacion = ['F', 'B']
        declarado = {'combinacion': combinacion, 'via': 'limpia_RD_VIII'}
        resultado = hechos.b2.salida_evaluada(regla, declarado)
        self.assertTrue(resultado['combinacion_admitida'])
        self.assertIs(declarado['combinacion'], combinacion)
        self.assertEqual(combinacion, ['F', 'B'])
if __name__ == '__main__':
    unittest.main()
