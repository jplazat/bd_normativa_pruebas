"""Public CI documentation."""
import json
import sqlite3
import unittest
from pathlib import Path
from ict155 import afirmaciones as af, cotejo_original, entrega, revision
from cowork import servidor_mcp
DECISION = 'Tu decisión (sesión 2, pregunta 13) fue exigir prueba documental de que el equipo estaba de verdad en servicio a 24-10-2020, porque la instalación no basta.'
CLIENTE = 'Según el cliente, el registrador dispone de un certificado de verificación periódica fechado el 2 de mayo de 2024.'
HECHOS = [DECISION, CLIENTE, 'Responsable decidió pedir prueba documental de que el equipo estaba en servicio el 24/10/2020.', 'La decisión de Responsable fue solicitar evidencia documental de que el registrador estaba en servicio el 2020-10-24.', 'El cliente declara que la última verificación periódica se realizó hace dos años.', 'Según el cliente, la última verificación periódica se realizó el 2 de mayo de 2024.', 'En el expediente consta que la última verificación periódica se realizó el 2024-05-02.', 'El cliente declara que el equipo dispone de un certificado de verificación periódica fechado el 2024-05-02.', 'En el expediente consta que el registrador dispone de un certificado de verificación periódica fechado el 02/05/2024.', 'El inventario aportado identifica el aparato como modelo TR-7 y número de serie 12345.', 'La fotografía facilitada muestra un precinto roto junto al conector del equipo.', 'El cliente tiene un termómetro registrador en una cámara de congelados.']
NORMATIVAS = ['El titular deberá verificar el registrador cada dos años.', 'El plazo de verificación periódica de este instrumento es de dos años.', 'No es obligatorio verificar el registrador instalado en esta cámara.', 'La Orden ICT/155/2020 no se aplica a la cámara del cliente.', 'El certificado aportado demuestra que el equipo cumple todos los requisitos legales.', 'Según el cliente, la norma permite usar siempre el equipo sin verificación periódica.', 'Responsable decidió que el titular deberá verificar el registrador cada dos años.', 'Tu decisión (sesión 2, pregunta 13) fue que no es obligatorio verificar el equipo.', 'En el expediente consta que no es obligatorio verificar el registrador.', 'El cliente declara que el plazo de verificación periódica es de tres años.', 'Según el cliente, el certificado de verificación periódica sigue vigente durante cuatro años.', 'Responsable decidió exigir prueba documental porque la Orden obliga a todos los titulares.', 'Responsable decidió exigir prueba documental de que el equipo cumple todos los requisitos legales.', 'La decisión de Responsable fue exigir prueba documental de que el equipo estaba en servicio el 24/10/2020 y está exento de verificación.', 'Según el cliente, la última verificación periódica se realizó hace dos años y por tanto cumple el plazo legal.', 'En el expediente consta que el registrador dispone de un certificado de verificación periódica fechado el 02/05/2024, por lo que no debe verificarse.', 'El cliente declara que la última verificación periódica se realizó cada dos años.', 'Según el cliente, la última verificación periódica se realizó el 2 de mayo de 2024 porque la norma exige ese plazo.', 'El cliente conserva un certificado de verificación periódica de hace dos años.', 'Según el cliente, la Orden ICT/155/2020 está derogada.', 'En el expediente consta que la norma no tiene ninguna obligación de verificar.', 'Responsable dijo que la base no tiene ninguna obligación de verificación periódica.', 'Tu decisión fue exigir que el titular deberá conservar siempre los registros.', 'El cliente declaró que no hay sanción por incumplir el plazo de verificación periódica.']

class RevisionFP2(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript((Path(__file__).parents[1] / 'ict155/esquema.sql').read_text(encoding='utf-8'))
        self.con.execute('PRAGMA query_only=ON')
        self.assertEqual(self.con.execute('PRAGMA query_only').fetchone()[0], 1)
        self.addCleanup(self.con.close)

    def revisar(self, texto):
        return revision.revisar(self.con, texto, huella_base='fp2-sintetica', datos_vigencia={}, datos_historial={}, tabla_sucesion=[], datos_cotejo=cotejo_original.Datos())

    def assertHecho(self, texto):
        fs = af.frases_del_borrador(texto)
        self.assertTrue(fs)
        self.assertTrue(all((not af.es_normativa(f.texto) for f in fs)))
        inf = self.revisar(texto)
        self.assertEqual(inf.cobertura.normativas, 0)
        self.assertEqual(inf.cobertura.comprobadas, 0)
        self.assertEqual(inf.cobertura.opinion, 0)
        self.assertFalse(any((c.tipo == af.SIN_COMPROBAR for c in inf.comprobaciones)))
        self.assertIn('la revisión no ha comprobado nada', inf.linea())

    def assertNormativa(self, texto):
        self.assertTrue(any((af.es_normativa(f.texto) for f in af.frases_del_borrador(texto))))
        inf = self.revisar(texto)
        self.assertGreater(inf.cobertura.sin_comprobar, 0)
        self.assertIn('LA RESPUESTA NO ESTÁ LISTA', inf.linea())

    def test_hechos_en_markdown_y_crlf(self):
        for t in ('- ' + DECISION, '**' + CLIENTE + '**', '1. ' + CLIENTE, '## Hechos del caso\r\n\r\n' + DECISION):
            with self.subTest(texto=t):
                self.assertHecho(t)

    def test_hechos_no_abren_exencion_de_seccion(self):
        t = '## Hechos del caso (declarados, no comprobados)\n\n' + CLIENTE + '\n\n' + NORMATIVAS[0]
        inf = self.revisar(t)
        self.assertEqual(inf.cobertura.sin_comprobar, 1)
        self.assertEqual(inf.cobertura.normativas, 1)
        self.assertEqual(next((c.linea for c in inf.comprobaciones if c.tipo == af.SIN_COMPROBAR)), 5)

    def test_cola_normativa_con_punto_y_punto_y_coma(self):
        for hecho in (DECISION, CLIENTE, HECHOS[4]):
            for separador in ('. ', '; ', ', ', ': '):
                with self.subTest(hecho=hecho, separador=separador):
                    self.assertNormativa(hecho.rstrip('.') + separador + NORMATIVAS[0])

    def test_obligatorio_en_un_relato_no_exime_una_regla(self):
        self.assertNormativa('Responsable dijo que es obligatorio verificar el registrador cada dos años.')

    def test_hecho_no_oculta_identificador_inexistente(self):
        inf = self.revisar(CLIENTE + '\n\n`BOE-A-2020-2573::art.999`')
        self.assertTrue(any((c.tipo == 'identificador' and c.nivel == revision.ERROR for c in inf.comprobaciones)))

    def test_revisor_y_formato_cowork_coinciden(self):
        inf = self.revisar(DECISION + '\n\n' + CLIENTE)
        _, txt, _ = servidor_mcp.formatear('normativa_revisar', ['revisar', '-', '--json'], json.dumps(inf.dict()), {'borrador': DECISION + '\n\n' + CLIENTE})
        self.assertIn(inf.linea(), txt)
        self.assertNotIn('LA RESPUESTA NO ESTÁ LISTA', txt)

    def test_verificacion_repite_clasificacion_y_sello(self):
        texto = DECISION + '\n\n' + CLIENTE
        inf = self.revisar(texto)
        v = entrega.verificar(self.con, texto + '\n\n' + inf.linea(), huella_base='fp2-sintetica', datos_vigencia={}, datos_historial={}, tabla_sucesion=[], datos_cotejo=cotejo_original.Datos())
        self.assertTrue(v.valida, v.motivos)
        self.assertEqual(v.sello_correcto, inf.linea())
        self.assertEqual(v.informe.cobertura.normativas, 0)

def _caso(texto, metodo):

    def test(self):
        getattr(self, metodo)(texto)
    return test
for _i, _texto in enumerate(HECHOS, 1):
    setattr(RevisionFP2, f'test_hecho_{_i:02d}', _caso(_texto, 'assertHecho'))
for _i, _texto in enumerate(NORMATIVAS, 1):
    setattr(RevisionFP2, f'test_contraejemplo_{_i:02d}', _caso(_texto, 'assertNormativa'))
if __name__ == '__main__':
    unittest.main()
