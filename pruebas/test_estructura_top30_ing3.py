"""Public CI documentation."""
import json
from pathlib import Path
import unittest
from ict155 import parsers
from ict155.extraccion import TextoPdf
from pruebas import estructura_completa_top30 as ec

def fixture(ident):
    dato = json.loads((Path(__file__).parent / 'fixtures/top30_ing3_motor_publico.json').read_text(encoding='utf-8'))[ident]
    paginas = [p['texto'] for p in dato['paginas']]
    if ident.startswith('BOE'):
        paginas[0] = 'Referencia: ' + ident + '\nTEXTO CONSOLIDADO\n' + paginas[0]
    return TextoPdf(ruta_relativa=dato['fuente'].replace('.motor.txt', '.pdf'), paginas=paginas)

class TestMotor(unittest.TestCase):

    def test_sanidad_encabezado_y_dos_primeros_apartados_en_un_renglon(self):
        ps = {p.ruta: p for p in parsers.analizar('boe', fixture('BOE-A-1986-10499')).preceptos}
        self.assertEqual(ps['art.84.1'].texto, '1. (Derogado)')
        self.assertIn('Este Estatuto-Marco', ps['art.84.2'].texto)
        self.assertNotIn('3. Las normas', ps['art.84.2'].texto)
        unicos = [p for p in ps.values() if p.ruta.endswith('/capitulo.unico')]
        self.assertEqual(len(unicos), 2)

    def test_articulo_13_con_apartado_inline_y_limites(self):
        ps = {p.ruta: p for p in parsers.analizar('eurlex', fixture('CELEX-31989L0108')).preceptos}
        self.assertIn('art.13', ps)
        self.assertIn('art.13.1', ps)
        self.assertIn('art.13.2', ps)
        self.assertNotIn('Artículo 13', ps['art.12'].texto)
        self.assertNotIn('Artículo 14', ps['art.13'].texto)
        self.assertEqual(ps['art.13'].marca, 'B')

    def test_marca_de_cabecera_no_se_pierde_ni_absorbe_encabezado(self):
        pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=['02099R0001 — ES — 01.01.2099 — 001.001 — 1 ▼M2\nArtículo 1 1. Primera regla.\n2. Segunda regla.'])
        ps = {p.ruta: p for p in parsers.analizar('eurlex', pdf).preceptos}
        self.assertEqual(ps['art.1'].marca, 'M2')
        self.assertEqual(ps['art.1.2'].marca, 'M2')
        self.assertNotIn('02099R0001', ps['art.1'].texto)

    def test_remision_minuscula_y_comillas_no_crean_articulo(self):
        pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=['Artículo 1\nObjeto\nArtículo 2 del acto anterior.\n«Artículo 3 1. Es una cita».\nartículo 4 1. Remisión.'])
        self.assertEqual([p.ruta for p in parsers.analizar('eurlex', pdf).preceptos if p.tipo == 'articulo'], ['art.1'])

    def test_anexo_sin_numeral_admite_apartado_explicito(self):
        pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=['Referencia: BOE-A-2099-1\nTEXTO CONSOLIDADO\nANEXO\nApartado 1. Primera regla.\nApartado 2. Segunda regla.'])
        ps = {p.ruta: p for p in parsers.analizar('boe', pdf).preceptos}
        self.assertEqual(ps['anexo.sn/ap.1'].padre, 'anexo.sn')
        self.assertNotIn('Apartado 2.', ps['anexo.sn/ap.1'].texto)

    def test_rd2032_apartados_anidados_sin_confundir_celdas(self):
        ps = {p.ruta: p for p in parsers.analizar('boe', fixture('BOE-A-2010-927')).preceptos}
        base = 'anexo.sn/capitulo.I'
        self.assertEqual(ps[base + '/ap.2.1'].padre, base + '/ap.2')
        self.assertIn('El segundo', ps[base + '/ap.2.1'].texto)
        self.assertNotIn('2.2 El metro', ps[base + '/ap.2.1'].texto)
        self.assertIn('kilogramo', ps[base].texto)
        self.assertNotIn('anexo.sn/capitulo.IV/ap.60', ps)

    def test_746_rotulos_en_columna_se_unen_al_cuerpo_por_orden(self):
        ps = {p.ruta: p for p in parsers.analizar('eurlex', fixture('CELEX-32017R0746')).preceptos}
        for letra, ancla in [('b', '31 a 46'), ('c', 'artículo 97'), ('d', 'artículo 100'), ('e', 'clase D'), ('f', 'sistemas electrónicos'), ('h', 'artículo 110'), ('i', '2024'), ('j', '2030')]:
            with self.subTest(letra=letra):
                texto = ps['art.113.3.' + letra].texto
                self.assertIn(ancla, texto)
                self.assertTrue(texto.startswith(letra + ') '))
        self.assertNotIn('el artículo 5', ps['art.113.3.h'].texto)
        self.assertNotIn('31 de diciembre de 2030', ps['art.113.3.i'].texto)

    def test_no_asigna_rotulos_si_los_parrafos_no_son_separables(self):
        lp = [('Artículo 1', 1), ('b) c)', 1), ('Comienzo sin cierre', 1), ('de la misma oración.', 1)]
        self.assertEqual(parsers._reubicar_rotulos_sueltos_ue(lp), lp)

    def test_reubicar_rotulos_conserva_todo_el_texto_y_las_paginas(self):
        from collections import Counter
        import re
        lp = [('Artículo 1', 1), ('▼B b) c)', 2), ('Primera regla;', 2), ('Segunda regla.', 2)]
        salida = parsers._reubicar_rotulos_sueltos_ue(lp)
        fichas = lambda filas: Counter(re.findall('\\w+|[^\\w\\s]', ' '.join((s for s, _ in filas))))
        self.assertEqual(fichas(lp), fichas(salida))
        self.assertEqual([p for _, p in lp], [p for _, p in salida])
        self.assertIn(('b) Primera regla;', 2), salida)

    def test_no_reubica_rotulos_fuera_del_articulado(self):
        lp = [('ANEXO I', 1), ('Artículo 99', 1), ('b) c)', 1), ('Primera regla;', 1), ('Segunda regla.', 1)]
        self.assertEqual(parsers._reubicar_rotulos_sueltos_ue(lp), lp)

class TestCalibracion(unittest.TestCase):

    def test_ue_anexo_no_exige_numeracion_interior_pero_articulo_si(self):
        texto = 'Artículo 1\n1. Uno.\n2. Dos.\nANEXO I\n1. Regla interior.\n2. Otra regla.'
        filas = [dict(ruta='art.1', tipo='articulo', padre=None, texto='Artículo 1 1. Uno. 2. Dos.'), dict(ruta='anexo.I', tipo='anexo', padre=None, texto='ANEXO I 1. Regla interior. 2. Otra regla.')]
        r = ec.comprobar_norma(texto, filas, 'eurlex', criterio='calibrado', identificador='CELEX-32099R0001')
        self.assertEqual({h['ruta'] for h in r['faltantes']}, {'art.1.1', 'art.1.2'})
        self.assertTrue(r['fuera_de_alcance'])

    def test_encabezado_inline_no_puede_desaparecer_del_censo(self):
        hs, _ = ec.censo_texto('Artículo 13 1. Una regla.\n2. Otra regla.')
        self.assertIn('art.13', {h.ruta for h in hs})

    def test_cabecera_marca_y_articulo_en_la_misma_linea(self):
        texto = '02099R0001 — ES — 01.01.2099 — 001.001 — 1 ▼M2 Artículo 1 1. Primera regla.\n2. Segunda regla.'
        hs, _ = ec.censo_texto(texto)
        self.assertIn('art.1', {h.ruta for h in hs})
        ps = {p.ruta: p for p in parsers.analizar('eurlex', TextoPdf(ruta_relativa='sintetico.pdf', paginas=[texto])).preceptos}
        self.assertEqual(ps['art.1'].marca, 'M2')
        self.assertIn('art.1.2', ps)

    def test_censo_calibrado_no_depende_de_las_filas_objetivo(self):
        texto = 'Artículo 1\n1. Uno.\na) Alfa.\nb) Beta.\n2. Dos.'
        r = ec.comprobar_norma(texto, [], 'eurlex', criterio='calibrado', identificador='CELEX-32099R0001')
        self.assertTrue({'art.1', 'art.1.1', 'art.1.1.a', 'art.1.1.b', 'art.1.2'} <= {h['ruta'] for h in r['faltantes']})

    def test_censo_no_pierde_las_letras_agrupadas_en_un_renglon(self):
        texto = 'Artículo 1\n1. Uno.\nb) c) d)\nRegla B.\nRegla C.\nRegla D.\n2. Dos.'
        r = ec.comprobar_norma(texto, [], 'eurlex', criterio='calibrado')
        self.assertTrue({'art.1.1.b', 'art.1.1.c', 'art.1.1.d'} <= {h['ruta'] for h in r['faltantes']})

    def test_ordinal_de_letra_sin_soporte_se_publica_como_limite(self):
        r = ec.comprobar_norma('Artículo 1\nUna regla.\nf bis) Otra regla.', [], 'eurlex', criterio='calibrado')
        self.assertTrue(any((x['motivo'] == 'ordinal_de_letra_sin_ruta_propia_en_contrato_calibrado' for x in r['fuera_de_alcance'])))

    def test_rubrica_sin_cuerpo_no_es_precepto_completo(self):
        r = ec.comprobar_norma('Artículo 1 Objeto\nRegla necesaria.', [dict(ruta='art.1', tipo='articulo', padre=None, texto='Artículo 1 Objeto')])
        self.assertFalse(r['correcta'])

    def test_indices_cabecera_pegada_y_correspondencias_no_inventan_encabezados(self):
        hs, _ = ec.censo_texto('CAPÍTULO I. Del índice\nTEXTO CONSOLIDADO Última modificación: hoy\nArtículo 1. Objeto.\nRegla.\nLEGISLACIÓN CONSOLIDADA ANEXO I\nRegla del anexo.', 'boe')
        self.assertEqual([h.ruta for h in hs], ['art.1', 'anexo.I'])
        hs, cs = ec.censo_texto('Artículo 1\nRegla.\nANEXO IV TABLA DE CORRESPONDENCIAS\nArtículo 99\nAnexo')
        self.assertEqual([h.ruta for h in hs], ['art.1', 'anexo.IV'])
        self.assertEqual(cs, [])
if __name__ == '__main__':
    unittest.main()
