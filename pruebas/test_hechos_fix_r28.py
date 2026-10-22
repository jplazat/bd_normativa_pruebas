"""Public CI documentation."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cowork import controles_lectura
from ict155 import cli, interruptores

class ControlesCLI(unittest.TestCase):

    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix='.hechosfix-', dir=cli.config.REPO)
        self.addCleanup(temporal.cleanup)
        self.tmp = Path(temporal.name)
        entorno = patch.dict(os.environ, {'LOCALAPPDATA': str(self.tmp), 'ICT155_COWORK_AUDIT_DIR': str(self.tmp / 'audit')})
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop(interruptores.VARIABLE_FORZADOS, None)
        self.pregunta = self.tmp / 'pregunta.md'
        self.pregunta.write_text('¿Cada cuánto hay que verificar el termómetro del congelador?', encoding='utf-8')

    def salida(self, argumentos):
        out, err = (io.StringIO(), io.StringIO())
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argumentos)
        return (rc, out.getvalue(), err.getvalue())

    def comprobar_cierre(self, argumentos, mensaje):
        rc, out, err = self.salida(argumentos)
        self.assertEqual(rc, 2)
        self.assertEqual(out, '')
        self.assertNotIn('Traceback', err)
        self.assertIn(mensaje, err)

    def test_controles_ausentes_en_obligatorios_y_cita(self):
        self.assertIs(interruptores.ErrorDeControles, controles_lectura.ErrorDeControles)
        with patch.object(interruptores, 'RUTA_CONTROLES', self.tmp / 'no_existe.json'):
            for argumentos in (['obligatorios', str(self.pregunta)], ['cita', 'BOE-A-2006-21277::art.13']):
                with self.subTest(orden=argumentos[0]):
                    self.comprobar_cierre(argumentos, 'los controles fallan cerrados')

    def test_controles_rotos_no_se_convierten_en_apagado(self):
        rota = self.tmp / 'rota.json'
        rota.write_text('{esto no es json', encoding='utf-8')
        with patch.object(interruptores, 'RUTA_CONTROLES', rota):
            self.comprobar_cierre(['obligatorios', str(self.pregunta)], 'los controles fallan cerrados')

    def test_hechos_explicitos_con_ensayo_no_eluden_controles_ausentes(self):
        with patch.object(interruptores, 'RUTA_CONTROLES', self.tmp / 'no_existe.json'):
            self.comprobar_cierre(['hechos', 'Consulta sintética', '--ensayo'], 'los controles fallan cerrados')

    def test_error_de_controles_durante_una_orden_tambien_se_captura(self):

        def ejecutar(_a):
            return interruptores.modo('control_inexistente_de_prueba')
        with patch.object(cli, 'cmd_info', side_effect=ejecutar):
            self.comprobar_cierre(['info'], 'control desconocido')

    def test_forzados_invalidos_se_rechazan(self):
        with patch.dict(os.environ, {interruptores.VARIABLE_FORZADOS: '{roto'}):
            self.comprobar_cierre(['obligatorios', str(self.pregunta)], 'ICT155_CONTROLES_FORZADOS no es JSON')

    def test_orden_valida_conserva_su_codigo_en_los_tres_modos(self):
        for modo in ('apagado', 'sombra', 'bloquea'):
            with self.subTest(modo=modo), patch.dict(os.environ, {interruptores.VARIABLE_FORZADOS: json.dumps({'entrada_hechos': modo})}), patch.object(cli, 'cmd_info', return_value=7):
                self.assertEqual(self.salida(['info']), (7, '', ''))

    def test_otros_errores_no_se_ocultan_como_error_de_controles(self):
        with patch.object(cli, 'cmd_info', side_effect=RuntimeError('error ajeno a controles')):
            with self.assertRaisesRegex(RuntimeError, 'error ajeno a controles'):
                self.salida(['info'])
