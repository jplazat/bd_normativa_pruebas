"""Public CI documentation."""
import sqlite3
import unittest
from ict155 import catalogo, consulta, contexto_norma, parsers
from ict155.extraccion import TextoPdf

class TestAlcanceDeIncisos(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.execute('CREATE TABLE precepto(version_id,ruta_estructural,texto_literal)')
        self.addCleanup(self.con.close)

    def poner(self, ruta, texto):
        self.con.execute('INSERT INTO precepto VALUES(1,?,?)', (ruta, texto))

    def buscar(self, ruta):
        r = consulta._antecesor_que_la_imprime(self.con, 1, ruta)
        return None if r is None else r['ruta_estructural']

    def test_articulo_entero_no_amplia_el_contrato_de_las_instrucciones(self):
        self.poner('art.6', '6. Texto. a) Uno. b) Dos.')
        self.assertIsNone(self.buscar('art.6.b'))

    def test_los_apartados_y_romanos_de_r2fix_siguen_localizandose(self):
        self.poner('art.6.1', '1. Reglas: a) Uno; b) Dos.')
        self.poner('art.7.a', 'a) Reglas: i) Uno; ii) Dos.')
        self.assertEqual(self.buscar('art.6.1.b'), 'art.6.1')
        self.assertEqual(self.buscar('art.7.a.ii'), 'art.7.a')
        self.assertIsNone(self.buscar('art.6.1.c'))
        self.assertIsNone(self.buscar('art.7.a.iii'))

    def test_instruccion_conserva_letra_real_y_rechaza_ausente(self):
        self.poner('itc.IF-11/ap.4', '4. Reglas. a) Uno. b) Dos.')
        self.assertEqual(self.buscar('itc.IF-11/ap.4.b'), 'itc.IF-11/ap.4')
        self.assertIsNone(self.buscar('itc.IF-11/ap.4.c'))

class TestMetadatosParcial(unittest.TestCase):

    def test_titulo_declarado_bajo_la_identidad_de_la_copia_parcial(self):
        ident = 'ICT155-DOC-NORMA_PAGO_02_PARCIAL'
        rel = '01_Conocimiento/Normas_tecnicas/NORMA_PAGO_02_PARCIAL.pdf'
        self.assertEqual(catalogo.titulo_oficial(ident), catalogo.metadatos(rel)['titulo'])
        self.assertEqual(catalogo.completitud(rel), 'parcial')
        self.assertEqual(catalogo.alias_de(rel), ['BS EN 13485:2023', 'BS EN 13485'])
        self.assertNotIn('EN 13485', catalogo.alias_de(rel))

def boe(lineas):
    return parsers.analizar('boe', TextoPdf('sintetico.pdf', paginas=['Documento sintético\nReferencia: BOE-A-2099-99999\nTEXTO CONSOLIDADO\n' + '\n'.join(lineas)]))

class TestDisposicionConSufijo(unittest.TestCase):

    def test_tercera_bis_no_cuelga_sus_letras_de_la_tercera(self):
        lineas = ['Disposición final tercera. Primera materia.', '1. Primera regla.', '4. Regla de la tercera.', 'Disposición final tercera bis. Otra materia.', '1. Otra regla.', '4. Reglas de la bis:', 'a) Uno;', 'b) Dos.', 'Disposición final cuarta. Cierre.', 'Regla final.']
        por = {p.ruta: p for p in boe(lineas).preceptos}
        self.assertIn('disp.final.3 bis.4.a', por)
        self.assertNotIn('disp.final.3.4.a', por)
        self.assertNotIn('Otra materia', por['disp.final.3'].texto)
        self.assertIn(por['disp.final.3 bis.4.a'].texto, por['disp.final.3 bis.4'].texto)
        self.assertEqual(consulta.ruta_de_cita('disposición final tercera bis'), 'disp.final.3 bis')

    def test_sufijos_y_ordinal_compuesto_comparten_numeral_con_la_consulta(self):
        for ordinal, esperado in [('tercera ter', '3 ter'), ('vigésima primera bis', '21 bis'), ('vigésima primera', '21'), ('única', '1')]:
            with self.subTest(ordinal=ordinal):
                self.assertEqual(parsers.ordinal_a_numero(ordinal), esperado)
                self.assertEqual(consulta.ruta_de_cita('disposición adicional ' + ordinal), 'disp.adicional.' + esperado)

    def test_el_contexto_no_remite_de_la_bis_a_la_disposicion_sin_sufijo(self):
        referencias = contexto_norma._referencias_internas('Según la disposición final tercera bis de esta ley.', 'art.1')
        self.assertEqual([r for r, _, _ in referencias], ['disp.final.3 bis'])

class TestNumeracionModificativa(unittest.TestCase):

    def test_la_lista_modificativa_no_reemplaza_al_apartado_exterior(self):
        t = '02017R0625 — ES — 05.01.2025\nArtículo 154\nModificaciones\n1. El Reglamento (CE) n.o 1/2005 se modifica como sigue:\n1. El artículo 2 se modifica como sigue:\na) Primera modificación;\nb) Segunda modificación.\n2. Se suprime un artículo.\n3. Otra modificación.\n2. Continúan las medidas transitorias.\n3. Regla final.'
        por = {p.ruta: p for p in parsers.analizar('eurlex', TextoPdf('sintetico.pdf', paginas=[t])).preceptos}
        self.assertIn('art.154.1.1.a', por)
        self.assertNotIn('art.154.1.a', por)
        self.assertIn('Primera modificación', por['art.154.1'].texto)
        self.assertNotIn('medidas transitorias', por['art.154.1'].texto)
        self.assertTrue(por['art.154.2'].texto.startswith('2. Continúan'))
        for p in por.values():
            if p.padre in por:
                self.assertIn(p.texto, por[p.padre].texto, p.ruta)

    def test_una_serie_ordinaria_sigue_teniendo_letras_directas(self):
        t = '02017R0625 — ES — 05.01.2025\nArtículo 10\nReglas\n1. Primera regla:\na) Uno;\nb) Dos.\n2. Cierre.'
        por = {p.ruta: p for p in parsers.analizar('eurlex', TextoPdf('sintetico.pdf', paginas=[t])).preceptos}
        self.assertIn('art.10.1.a', por)
        self.assertNotIn('art.10.1.1.a', por)

    def test_lista_larga_no_absorbe_los_apartados_finales(self):
        t = '02017R0625 — ES — 05.01.2025\nArtículo 165\nModificaciones\n1. El Reglamento (CE) n.o 1/2099 se modifica como sigue:\n' + '\n'.join((f'{n}. Modificación interior {n}.' for n in range(1, 17))) + '\n2. Regla exterior segunda.\n3. Regla exterior tercera.\n4. Regla exterior cuarta.'
        por = {p.ruta: p for p in parsers.analizar('eurlex', TextoPdf('sintetico.pdf', paginas=[t])).preceptos}
        for n in range(1, 17):
            self.assertIn(f'art.165.1.{n}', por)
        for n in (2, 3, 4):
            self.assertIn('Regla exterior', por[f'art.165.{n}'].texto)
        self.assertNotIn('Regla exterior', por['art.165.1'].texto)
if __name__ == '__main__':
    unittest.main()
