"""Public CI documentation."""
import unittest
from ict155 import consulta, parsers
from ict155.extraccion import TextoPdf
from pruebas.test_r2fix_c2_2026_10_20 import memoria

class TestCompatibilidad(unittest.TestCase):

    def test_boe_anterior_conserva_padres_sin_perder_articulos(self):
        texto = 'LEGISLACIÓN CONSOLIDADA\nReferencia: BOE-A-1986-10499\nTÍTULO VII\nTransparencia y sostenibilidad del gasto sanitario\nArtículo ciento catorce. Límites de gasto sanitario.\nTexto de control.\nArtículo ciento quince. Consecuencias de la superación del límite.\nOtro texto de control.\nArtículo ciento dieciséis. Transparencia.\nCierre.'
        pdf = TextoPdf('sintetico.pdf', paginas=[texto])
        antes = {p.ruta: p for p in parsers.analizar_boe(pdf).preceptos}
        ahora = {p.ruta: p for p in parsers.analizar('boe', pdf).preceptos}
        for ruta in ('art.114', 'art.115', 'art.116'):
            self.assertIn(ruta, antes)
            self.assertEqual(ahora[ruta], antes[ruta])

    def test_otro_boe_anterior_conserva_sus_padres(self):
        pdf = TextoPdf('sintetico.pdf', paginas=['LEGISLACIÓN CONSOLIDADA\nReferencia: BOE-A-2007-16478\nCAPÍTULO I\nControl\nArtículo 1. Primero.\nTexto sintético.'])
        antes = parsers.analizar_boe(pdf).preceptos
        ahora = parsers.analizar('boe', pdf).preceptos
        self.assertEqual(ahora, antes)

    def test_alta_r2_sigue_enlazando(self):
        pdf = TextoPdf('sintetico.pdf', paginas=['LEGISLACIÓN CONSOLIDADA\nReferencia: BOE-A-2022-21135\nCAPÍTULO III\nRegistro de los movimientos de leche\nArtículo 7. Registro.\nTexto sintético.\nArtículo 8. Comunicación.\nCierre.'])
        ps = {p.ruta: p for p in parsers.analizar('boe', pdf).preceptos}
        self.assertEqual(ps['art.7'].padre, 'capitulo.III')
        self.assertEqual(ps['art.8'].padre, 'capitulo.III')

    def test_ordinal_impreso_conserva_el_contenedor_previo(self):
        texto = 'ANEXO XIII\nEVALUACIÓN DEL FUNCIONAMIENTO\n1. Control inicial.\n2. Segundo control.\n2.1. Primero.\n2.2. Segundo.\n2.3. Estudios.\n2.3.1. Diseño.\n2.3.2. Plan de estudio del funcionamiento clínico\na) Texto sintético.\nz) Otro texto.\na bis) Lista sintética de características.\na ter) Bibliografía sintética.\n2.3.3. Control posterior.'
        ps = parsers.analizar('eurlex', TextoPdf('sintetico.pdf', paginas=[texto])).preceptos
        con = memoria(ps)
        self.addCleanup(con.close)
        for ordinal in ('bis', 'ter'):
            r = consulta.resolver(con, 'CELEX-39999R0001::anexo.XIII/ap.2.3.2.a ' + ordinal)
            self.assertEqual(r.estado, consulta.CONTENIDO_EN_ANCESTRO)
            self.assertEqual(r.ambito_localizado, 'anexo.XIII')
            self.assertIsNone(r.texto_literal)
        falsa = consulta.resolver(con, 'CELEX-39999R0001::anexo.XIII/ap.2.3.3.a bis')
        self.assertNotEqual(falsa.estado, consulta.CONTENIDO_EN_ANCESTRO)

    def test_remision_a_ordinal_no_impide_serie_segura(self):
        texto = 'ANEXO I\n1. Primer punto sintético.\nSe aplica la letra a bis) de otra disposición.\n2. Segundo punto sintético.'
        ps = parsers.analizar('eurlex', TextoPdf('sintetico.pdf', paginas=[texto])).preceptos
        self.assertIn('anexo.I/ap.1', {p.ruta for p in ps})
if __name__ == '__main__':
    unittest.main()
