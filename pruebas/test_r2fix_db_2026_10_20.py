"""Public CI documentation."""
import sqlite3
import unittest
from unittest.mock import patch
from ict155 import consulta, calidad_textual

class TestFronteras(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.execute('CREATE TABLE precepto(version_id, ruta_estructural, texto_literal)')
        self.addCleanup(self.con.close)

    def poner(self, ruta, texto):
        self.con.execute('INSERT INTO precepto VALUES (1,?,?)', (ruta, texto))

    def buscar(self, ruta):
        r = consulta._antecesor_que_la_imprime(self.con, 1, ruta)
        return None if r is None else r['ruta_estructural']

    def test_f_bis_absorbido_no_acredita_romanos_de_f(self):
        self.poner('art.113.3.f', 'f) Regla sintética;\nf bis) a más tardar seis meses después de la fecha establecida en la letra f), párrafo primero, del presente apartado:\ni) los productos para los que el fabricante haya realizado una evaluación de la conformidad;\nii) los productos introducidos en el mercado con arreglo al artículo 110;\nf ter) Otra regla.')
        for inciso in ('i', 'ii'):
            with self.subTest(inciso=inciso):
                self.assertIsNone(self.buscar('art.113.3.f.' + inciso))

    def test_f_bis_localizado_si_acredita_sus_romanos(self):
        self.poner('art.1.f bis', 'f bis) Reglas: i) Primera; ii) Segunda; f ter) Otra regla.')
        for inciso in ('i', 'ii'):
            self.assertEqual(self.buscar('art.1.f bis.' + inciso), 'art.1.f bis')

    def test_sufijos_cierran_el_padre_antes_del_romano(self):
        for sufijo in ('bis', 'ter', 'quater', 'quinquies', 'sexies', 'septies', 'octies', 'nonies', 'decies', 'undecies', 'duodecies', 'terdecies', 'quáter', 'octodecies', 'quatervicies'):
            for separador in ('; ', '\n', '. '):
                with self.subTest(sufijo=sufijo, separador=separador):
                    self.con.execute('DELETE FROM precepto')
                    self.poner('art.1.f', 'f) Regla' + separador + 'f ' + sufijo + ') Reglas: i) Ajena; ii) Ajena.')
                    self.assertIsNone(self.buscar('art.1.f.i'))
                    self.assertIsNone(self.buscar('art.1.f.ii'))

    def test_hermano_sin_sufijo_y_nivel_interior_no_acreditan_romano(self):
        for texto in ('f) Regla; g) Reglas: i) Ajena.', 'f) Regla; f bis) 1. Reglas: i) Ajena.', 'f) Regla; 1. Reglas: i) Interior.', 'f) Regla; 1 bis) Reglas: i) Interior.'):
            with self.subTest(texto=texto):
                self.con.execute('DELETE FROM precepto')
                self.poner('art.1.f', texto)
                self.assertIsNone(self.buscar('art.1.f.i'))

    def test_romanos_anteriores_al_hermano_y_remision_a_bis_se_conservan(self):
        self.poner('art.1.f', 'f) Reglas: i) Primera; ii) Según la letra f bis) del artículo 2; f bis) Otra regla.')
        for inciso in ('i', 'ii'):
            self.assertEqual(self.buscar('art.1.f.' + inciso), 'art.1.f')

    def test_apartado_numerico_con_letra_bis_no_salta_nivel(self):
        self.poner('art.1.1', '1. Reglas: a bis) Interior: i) Primera; ii) Segunda; b) Regla.')
        self.assertIsNone(self.buscar('art.1.1.i'))
        self.assertIsNone(self.buscar('art.1.1.ii'))
        self.assertEqual(self.buscar('art.1.1.b'), 'art.1.1')

    def test_control_sintetico_h4(self):
        self.poner('art.23.2.a', 'a) Reglas: i) Primera; ii) Segunda.')
        self.assertEqual(self.buscar('art.23.2.a.i'), 'art.23.2.a')
        self.assertIsNone(self.buscar('art.23.2.a.zzzz'))

    def test_remisiones_enumeradas_antes_de_romanos_no_cierran_el_padre(self):
        self.poner('art.54.3.a', 'a) Se aplican las letras a), b) y c), teniendo en cuenta: i) Primera; ii) Segunda; iii) Tercera; iv) Cuarta; v) Quinta.')
        for inciso in ('i', 'ii', 'iii', 'iv', 'v'):
            self.assertEqual(self.buscar('art.54.3.a.' + inciso), 'art.54.3.a')

class TestAvisoCronobacter(unittest.TestCase):

    def setUp(self):
        self.avisos = calidad_textual.cargar()
        self.aviso = next((a for a in self.avisos if a.get('origen') == 'R28-R2FIX-DB'), None)

    def test_fila_y_pagina_no_certificadas_expresamente(self):
        self.assertIsNotNone(self.aviso)
        self.assertEqual((self.aviso['obra'], self.aviso['ruta'], self.aviso['paginas_pdf'], self.aviso['no_certificado']), ('CELEX-32005R2073', 'anexo.I', [12], 'filas_de_tabla'))
        for texto in ('1.24', 'Cronobacter spp.', 'no certificada'):
            self.assertIn(texto, self.aviso['detalle'])

    def test_aviso_se_aplica_solo_a_su_obra_ambito_y_huella(self):
        self.assertIsNotNone(self.aviso)
        con = sqlite3.connect(':memory:')
        self.addCleanup(con.close)
        con.execute('CREATE TABLE documento(id, sha256)')
        con.execute('CREATE TABLE version(id, documento_id)')
        con.execute('INSERT INTO documento VALUES (1,?)', (self.aviso['sha256_pdf'],))
        con.execute('INSERT INTO version VALUES (1,1)')

        def respuesta(obra):
            return consulta.Respuesta(estado=consulta.ENCONTRADO, identificador=obra + '::anexo.I', obra=obra, version_id=1, texto_literal='CrMon9ob_ac_t_er____ spp.')
        with patch.object(calidad_textual, 'cargar', return_value=[self.aviso]):
            r = calidad_textual.aplicar(con, respuesta(self.aviso['obra']), 'anexo.I')
            self.assertEqual(r.texto_literal, 'CrMon9ob_ac_t_er____ spp.')
            self.assertIn('no certificada', r.naturaleza_del_texto)
            self.assertEqual(len(r.calidad_textual), 1)
            self.assertFalse(calidad_textual.aplicar(con, respuesta(self.aviso['obra']), 'art.2').calidad_textual)
            self.assertFalse(calidad_textual.aplicar(con, respuesta('CELEX-39999R0001'), 'anexo.I').calidad_textual)
            con.execute('UPDATE documento SET sha256=?', ('0' * 64,))
            self.assertFalse(calidad_textual.aplicar(con, respuesta(self.aviso['obra']), 'anexo.I').calidad_textual)
if __name__ == '__main__':
    unittest.main()
