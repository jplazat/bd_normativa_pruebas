"""Public CI documentation."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ict155 import consulta, config, vigencia, calidad_textual
from pruebas import estructura_completa_top30 as censo
from pruebas import soporte_alta_top30_r28_2026_10_19 as top30
REPO = Path(__file__).resolve().parents[1]
INCISOS_625 = 'a) requisitos específicos uniformes para la realización de controles oficiales para hacer frente a los peligros y riesgos uniformes reconocidos de:\ni) la presencia en la cadena agroalimentaria de OMG para la producción de alimentos y piensos\nii) el cultivo de OMG para la producción de alimentos y piensos'

class TestIncisos(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.execute('CREATE TABLE precepto(version_id, ruta_estructural, texto_literal)')
        self.addCleanup(self.con.close)

    def poner(self, ruta, texto, version=1):
        self.con.execute('INSERT INTO precepto VALUES (?,?,?)', (version, ruta, texto))

    def buscar(self, ruta):
        r = consulta._antecesor_que_la_imprime(self.con, 1, ruta)
        return r['ruta_estructural'] if r is not None else None

    def test_romanos_reales_del_citante_sin_aviso(self):
        self.poner('art.23.2.a', INCISOS_625)
        for inciso in ('i', 'ii'):
            with self.subTest(inciso=inciso):
                self.assertEqual(self.buscar('art.23.2.a.' + inciso), 'art.23.2.a')

    def test_letra_no_separada_en_ancestro_inmediato(self):
        self.poner('art.8.1', '1. Reglas: a) Primera; b) Segunda.')
        self.assertEqual(self.buscar('art.8.1.b'), 'art.8.1')

    def test_romano_en_linea_y_tras_coma(self):
        self.poner('art.8.a', 'a) Reglas: i) Primera, ii) Segunda; iii) Tercera.')
        for n in ('i', 'ii', 'iii'):
            with self.subTest(n=n):
                self.assertEqual(self.buscar('art.8.a.' + n), 'art.8.a')

    def test_remisiones_y_palabras_no_son_rotulos(self):
        for texto in ('a) Véase el inciso i) de otro artículo.', 'a) Véase i) en otro lugar.', 'a) Requisitos i) y ii) del artículo anterior.', 'a) Primera; xi) Undécima.', 'a) Mini) palabra.'):
            with self.subTest(texto=texto):
                self.con.execute('DELETE FROM precepto')
                self.poner('art.8.a', texto)
                self.assertIsNone(self.buscar('art.8.a.i'))

    def test_no_busca_en_hermano_otra_version_ni_padre_inventado(self):
        self.poner('art.8.a', 'a) Sin incisos.')
        self.poner('art.8.b', 'b) Reglas: i) Otra regla.')
        self.poner('art.8.a', 'a) Reglas: i) Otra edición.', version=2)
        for ruta in ('art.8.a.i', 'art.8.z.i', 'art.8.b.z.i'):
            with self.subTest(ruta=ruta):
                self.assertIsNone(self.buscar(ruta))

    def test_numeros_y_remisiones_conservan_el_contrato(self):
        self.poner('ap.5', '5. Reglas. 5.3 Tercera regla; véase 5.4 en otro lugar.')
        self.assertEqual(self.buscar('ap.5.3'), 'ap.5')
        self.assertIsNone(self.buscar('ap.5.4'))
        self.assertIsNone(self.buscar('ap.5.999'))

    def test_el_agregado_no_se_salta_un_hijo_numerico_ni_una_letra(self):
        self.poner('art.8', 'Artículo 8. 1. Reglas: a) Primera; b) Segunda.')
        self.poner('art.8.1', '1. Reglas: a) Primera; b) Segunda.')
        self.assertIsNone(self.buscar('art.8.a'))
        self.assertEqual(self.buscar('art.8.1.a'), 'art.8.1')
        self.poner('art.9.1', '1. Reglas: a) Primera: i) Interior; ii) Segundo interior; b) Segunda.')
        self.assertIsNone(self.buscar('art.9.1.i'))
        self.assertIsNone(self.buscar('art.9.1.ii'))

    def test_la_letra_i_no_se_confunde_con_un_romano_interior(self):
        self.poner('art.8.1', '1. Reglas: h) Octava; i) Novena; j) Décima.')
        self.assertEqual(self.buscar('art.8.1.i'), 'art.8.1')

    def test_el_rotulo_del_padre_no_acredita_un_hijo_del_mismo_nombre(self):
        self.poner('art.8.a', 'a) Reglas: i) Primera; ii) Segunda.')
        self.assertIsNone(self.buscar('art.8.a.a'))
        self.assertEqual(self.buscar('art.8.a.i'), 'art.8.a')

    def test_series_de_remisiones_y_notas_de_tabla_no_son_subdivisiones(self):
        casos = [('art.8.1', '1. Se aplican las letras a), b), c) y d) del artículo 7.', 'c'), ('art.8.a', 'a) Según los incisos i), ii) y iii) del artículo 7.', 'ii'), ('art.8.1', '1. Unidad neper (g, i) belio (h, i) y otras unidades.', 'i'), ('art.8.1', '1. Ángulo plano grado (a, b) º y minuto.', 'b'), ('art.8', 'Artículo 8. Objeto. 1) Reglas: a) Primera; b) Segunda.', 'a'), ('art.8', 'Artículo 8. Se sustituye por el texto siguiente: «3. a) Regla ajena».', 'a'), ('art.8.a', 'a) Primera; b) Otra letra hermana.', 'b')]
        for padre, texto, hijo in casos:
            with self.subTest(padre=padre, hijo=hijo):
                self.con.execute('DELETE FROM precepto')
                self.poner(padre, texto)
                self.assertIsNone(self.buscar(padre + '.' + hijo))

class TestRespuesta(unittest.TestCase):

    def test_api_sin_aviso_localiza_el_inciso_sin_inventar_literal(self):
        from pruebas.soporte_ing4 import memoria
        con = memoria('Artículo 23\n1. Primera regla.\n2. Reglas sintéticas.', 'CELEX-39999R0001')
        self.addCleanup(con.close)
        padre = con.execute('SELECT * FROM precepto WHERE ruta_estructural="art.23.2"').fetchone()
        con.execute('INSERT INTO precepto(version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES(?,?,?,?,?,?,?,?,?,?)', (padre['version_id'], padre['id'], 'art.23.2.a', 'letra', 'a', 'Letra a)', INCISOS_625, 30, 30, 100))
        with patch.object(calidad_textual, 'cargar', return_value=[]):
            r = consulta.resolver(con, 'CELEX-39999R0001::art.23.2.a.i')
            self.assertEqual(r.estado, consulta.CONTENIDO_EN_ANCESTRO)
            self.assertEqual(r.ambito_localizado, 'art.23.2.a')
            self.assertEqual(r.version_id, padre['version_id'])
            self.assertEqual((r.pagina_inicio, r.pagina_fin), (30, 30))
            self.assertIsNone(r.texto_literal)
            self.assertFalse(r.reproducible)
            self.assertIn('no la trocea aparte', r.detalle)
            self.assertEqual(consulta.resolver(con, 'CELEX-39999R0001::art.23.2.a.zzzz').estado, consulta.PRECEPTO_INEXISTENTE)

class TestContextos(unittest.TestCase):

    def rutas(self, texto):
        hs, _ = censo.censo_texto(texto)
        return {h.ruta: h.padre for h in hs}

    def test_999_capitulo_nuevo_cierra_seccion_y_la_siguiente_es_suya(self):
        texto = 'ANEXO IV\nCAPÍTULO III\nSECCIÓN D\n===== PÁGINA 52 =====\nCAPÍTULO IV\nCondiciones específicas para la aplicación de las excepciones previstas en el capítulo II\nSECCIÓN A\n===== PÁGINA 69 =====\nCAPÍTULO V\nSECCIÓN A\n'
        rutas = self.rutas(texto)
        self.assertIn('anexo.IV/capitulo.IV', rutas)
        self.assertEqual(rutas['anexo.IV/capitulo.V/seccion.A'], 'anexo.IV/capitulo.V')
        self.assertNotIn('anexo.IV/seccion.D/capitulo.IV', rutas)

    def test_titulo_anexo_e_instruccion_reinician_contextos(self):
        rutas = self.rutas('TÍTULO I\nCAPÍTULO I\nSECCIÓN A\nTÍTULO II\nSECCIÓN B\nANEXO I\nCAPÍTULO I\nSECCIÓN A\nANEXO II\nSECCIÓN B\nINSTRUCCIÓN IF-01\nSECCIÓN C\n')
        self.assertEqual(rutas['titulo.II/seccion.B'], 'titulo.II')
        self.assertEqual(rutas['anexo.II/seccion.B'], 'anexo.II')
        self.assertEqual(rutas['seccion.C'], None)

    def test_anexo_sin_capitulo_no_cambia(self):
        rutas = self.rutas('ANEXO I\nSECCIÓN A\nPrimera regla.\nSECCIÓN B\nSegunda regla.')
        self.assertEqual(rutas, {'anexo.I': None, 'anexo.I/seccion.A': 'anexo.I', 'anexo.I/seccion.B': 'anexo.I'})

    def test_orden_seccion_capitulo_de_882_no_se_invierte(self):
        rutas = self.rutas('ANEXO IV\nSECCIÓN A\nOperaciones.\nSECCIÓN B\nImportes mínimos.\nCAPÍTULO I\nMataderos.\nCAPÍTULO II\nSalas de despiece.\nANEXO V\nSECCIÓN A\nOperaciones o controles.\nSECCIÓN B\nTasas.\nCAPÍTULO I\n')
        self.assertEqual(rutas['anexo.IV/seccion.B/capitulo.I'], 'anexo.IV/seccion.B')
        self.assertEqual(rutas['anexo.IV/seccion.B/capitulo.II'], 'anexo.IV/seccion.B')
        self.assertEqual(rutas['anexo.V/seccion.B/capitulo.I'], 'anexo.V/seccion.B')

class TestVigencia(unittest.TestCase):

    def test_orden_usa_el_acceso_del_producto_sin_sidecar(self):
        with tempfile.TemporaryDirectory() as t:
            bd = Path(t) / 'conocimiento.sqlite'
            with patch.object(top30, 'BASE', bd), patch.object(config, 'BD', bd):
                self.assertIsNone(vigencia.instantanea_actual(bd.parent / 'vigencia.json'))
                top30.TestBaseTop30('test_la_orden_se_expone_como_derogada_con_fecha').test_la_orden_se_expone_como_derogada_con_fecha()
            self.assertEqual(list(Path(t).iterdir()), [])

    def test_ruta_explicita_no_usa_complementos_y_guardada_prevalece(self):
        with tempfile.TemporaryDirectory() as t:
            bd = Path(t) / 'conocimiento.sqlite'
            p = Path(t) / 'vigencia.json'
            with patch.object(config, 'BD', bd):
                self.assertIsNone(vigencia.instantanea_actual(p))
                original = {'obras': {'BOE-A-1989-5084': {'consulta': {'estado': None}}}}
                p.write_text(json.dumps(original), encoding='utf-8')
                self.assertEqual(vigencia.instantanea_actual(p), original)
                self.assertEqual(vigencia.instantanea_actual()['obras']['BOE-A-1989-5084'], original['obras']['BOE-A-1989-5084'])

    def test_rd1945_derogacion_con_excepciones_fecha_y_pagina(self):
        data = json.loads((REPO / 'datos/vigencia_r2.json').read_text(encoding='utf-8'))
        r = vigencia.vigencia_de('BOE-A-1983-19755', data, hoy='2026-10-20')
        self.assertEqual(r['estado'], 'derogada_con_excepciones')
        self.assertEqual(r['fecha_derogacion'], '2025-07-03')
        self.assertEqual(r['evidencia_local']['pagina_pdf'], 3)
        self.assertIn('única.a)', r['excepciones'])
        self.assertIn('DEROGADA CON EXCEPCIONES el 2025-07-03', vigencia.texto(r))
        self.assertIn('No se determinan', ' '.join(r['avisos']))

    def test_nuevo_estado_se_presenta_de_forma_general(self):
        data = {'obras': {'BOE-A-2099-1': {'consulta': {'estado': 'derogada_con_excepciones', 'fecha_derogacion': '2099-01-01', 'excepciones': 'Disposición sintética', 'fuente': 'BOE', 'evidencia_local': {'pagina_pdf': 2}}}}}
        r = vigencia.vigencia_de('BOE-A-2099-1', data, hoy='2099-01-02')
        self.assertIn('CON EXCEPCIONES el 2099-01-01', vigencia.texto(r))
        self.assertEqual(r['excepciones'], 'Disposición sintética')

    def test_derogacion_total_orden_no_cambia(self):
        data = json.loads((REPO / 'datos/vigencia_top30.json').read_text(encoding='utf-8'))
        r = vigencia.vigencia_de('BOE-A-1989-5084', data, hoy='2026-10-20')
        self.assertEqual((r['estado'], r['fecha_derogacion']), ('derogada', '2015-12-01'))
        self.assertIn('DEROGADA el 2015-12-01', vigencia.texto(r))
if __name__ == '__main__':
    unittest.main()
