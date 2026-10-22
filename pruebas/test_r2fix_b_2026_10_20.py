"""Public CI documentation."""
import re
import sqlite3
import unittest
from pathlib import Path
from contextlib import closing
from ict155 import consulta, parsers
from ict155.extraccion import TextoPdf

def analizar(*paginas):
    return {p.ruta: p for p in parsers.analizar('eurlex', TextoPdf('publico.pdf', paginas=list(paginas))).preceptos}

class TestMarcas(unittest.TestCase):

    def test_real_1333_anexo_ii_p44(self):
        texto = 'Sorbitoles Manitol ►C12 Isomalt ◄ Maltitoles Lactitol Xilitol Eritritol'
        p = analizar('ANEXO II\n' + texto)['anexo.II']
        self.assertIn('Isomalt Maltitoles', p.texto)

    def test_real_1333_anexo_iii_p344(self):
        texto = 'Sorbitol Manitol ►C13 Isomalt ◄ Maltitol Lactitol Xilitol Eritritol'
        p = analizar('ANEXO III\n' + texto)['anexo.III']
        self.assertIn('Isomalt Maltitol', p.texto)

    def test_cierre_no_consume_letras_ni_codigos_del_contenido(self):
        for contenido in ('Maltitol', 'Calcio', 'Boro', 'M', 'B', 'C', 'M1', 'C12', 'B2'):
            with self.subTest(contenido=contenido):
                self.assertEqual(parsers.MARCA_INLINE.sub('', '◄ ' + contenido).strip(), contenido)

    def test_aperturas_estrictas(self):
        for marca in ('B', 'M1', 'M12', 'C1', 'C13'):
            with self.subTest(marca=marca):
                self.assertEqual(parsers.MARCA_INLINE.sub('', '►' + marca + ' texto ◄').strip(), 'texto')
        for texto in ('►Maltitol', '►Calcio', '►Boro', '►M', '►C', '►M1extra', '►B2'):
            with self.subTest(texto=texto):
                self.assertEqual(parsers.MARCA_INLINE.sub('', texto), texto)

    def test_marcas_de_bloque_inicio_y_resto_estrictas(self):
        for marca in ('B', 'M1', 'C12'):
            with self.subTest(marca=marca):
                self.assertEqual(parsers.MARCA_BLOQUE.fullmatch('▼' + marca)[1], marca)
                self.assertEqual(parsers.MARCA_INICIO.match('►' + marca + ' Artículo 2')[1], marca)
                self.assertEqual(parsers.MARCA_RESTO.sub('', 'Texto ▼' + marca).strip(), 'Texto')
        for contenido in ('Maltitol', 'Calcio', 'Boro', 'M', 'C', 'M1extra', 'B2'):
            with self.subTest(contenido=contenido):
                self.assertIsNone(parsers.MARCA_BLOQUE.fullmatch('▼' + contenido))
                self.assertIsNone(parsers.MARCA_INICIO.match('►' + contenido + ' texto'))
                self.assertEqual(parsers.MARCA_RESTO.sub('', '▼' + contenido), '▼' + contenido)

    def test_sin_marcas_no_cambia(self):
        texto = 'Manitol Maltitol Calcio Boro M1 C12 B2.'
        self.assertIn(texto, analizar('ANEXO I\n' + texto)['anexo.I'].texto)

    def test_flecha_sin_codigo_no_mutila_el_contenido(self):
        p = analizar('ANEXO I\n►Maltitol ►Calcio ►Boro ►A1')['anexo.I']
        self.assertIn('Maltitol Calcio Boro A1', p.texto)
        self.assertNotIn('►', p.texto)

    def test_marca_real_del_motor_junto_a_separador_grafico(self):
        self.assertEqual(parsers.MARCA_RESTO.sub('', '▼M115_______'), '_______')
        self.assertEqual(parsers.MARCA_INLINE.sub('', '►C12_______'), '_______')

class TestCorrespondencias(unittest.TestCase):

    def test_real_1375_p30_p31(self):
        pp = analizar('ANEXO VI\nTabla de correspondencias\nArtículos 1 a 5\nArtículos 1 a 5\nAnexo I, capítulo I\nAnexo I, capítulo I\nAnexo V\n—\nAnexo VI', '▼M2\nANEXO VII\nTerceros países o sus regiones que aplican las excepciones contempladas en el artículo 13, apartado 2\nGB\nReino')
        self.assertIn('anexo.VII', pp)
        self.assertNotIn('ANEXO VII', pp['anexo.VI'].texto)
        self.assertEqual((pp['anexo.VI'].pagina_inicio, pp['anexo.VI'].pagina_fin), (1, 1))
        self.assertEqual((pp['anexo.VII'].pagina_inicio, pp['anexo.VII'].pagina_fin), (2, 2))
        self.assertIn('Terceros países', pp['anexo.VII'].texto)

    def test_filas_no_abren_anexo(self):
        filas = 'Anexo VII Anexo V\nAnexo VIII —\nAnexo VII\nAnexo V\nANEXO VII ANEXO V\nANEXO VIII\n—\nArtículo 1\nArtículo 2'
        pp = analizar('Artículo 1\nObjeto\nCuerpo original.\nANEXO VI\nTABLA DE CORRESPONDENCIAS\n' + filas)
        self.assertEqual(set(pp), {'art.1', 'anexo.VI'})
        self.assertIn('Anexo VII Anexo V', pp['anexo.VI'].texto)
        self.assertIn('Cuerpo original.', pp['art.1'].texto)

    def test_continuacion_de_tabla_en_otra_pagina(self):
        pp = analizar('ANEXO VI\nTABLA DE CORRESPONDENCIAS\nArtículo 1\nArtículo 2', 'ANEXO VII\nANEXO V\nArtículo 3\nArtículo 4')
        self.assertEqual(set(pp), {'anexo.VI'})
        self.assertIn('ANEXO VII', pp['anexo.VI'].texto)

    def test_siguiente_anexo_ingles(self):
        pp = analizar('ANNEX II\nCorrelation table\nArticle 1\nArticle 2', 'ANNEX III\nCountries applying the exemptions\nGB')
        self.assertIn('anexo.III', pp)
        self.assertNotIn('ANNEX III', pp['anexo.II'].texto)

    def test_sin_tabla_conserva_anexos(self):
        pp = analizar('ANEXO I\nContenido primero.\nANEXO II\nContenido segundo.')
        self.assertEqual(set(pp), {'anexo.I', 'anexo.II'})
        self.assertIn('Contenido primero.', pp['anexo.I'].texto)
        self.assertIn('Contenido segundo.', pp['anexo.II'].texto)

class TestConsulta(unittest.TestCase):

    def _consultar(self, ident, paginas, rutas):
        """Public CI documentation."""
        ps = analizar(*paginas)
        with closing(sqlite3.connect(':memory:')) as con:
            con.row_factory = sqlite3.Row
            con.executescript((Path(parsers.__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
            doc = con.execute('INSERT INTO documento (ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES (?,?,?,?,?,?)', (ident + '.pdf', 'sintetico', 0, '2099-01-01', 'publico', 'ingerido')).lastrowid
            obra = con.execute('INSERT INTO obra (identificador_canonico,tipo,titulo,jurisdiccion) VALUES (?,?,?,?)', (ident, 'eurlex', ident, 'UE')).lastrowid
            ver = con.execute('INSERT INTO version (obra_id,documento_id,etiqueta,idioma) VALUES (?,?,?,?)', (obra, doc, 'fixture', 'es')).lastrowid
            ids = {}
            for orden, p in enumerate(ps.values()):
                ids[p.ruta] = con.execute('INSERT INTO precepto (version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES (?,?,?,?,?,?,?,?,?,?)', (ver, ids.get(p.padre), p.ruta, p.tipo, p.numero, p.etiqueta, p.texto, p.pagina_inicio, p.pagina_fin, orden)).lastrowid
            con.commit()
            con.execute('PRAGMA query_only=ON')
            self.assertEqual(con.execute('PRAGMA query_only').fetchone()[0], 1)
            return {ruta: consulta.resolver(con, ident + '::' + ruta) for ruta in rutas}

    def test_api_h2_conserva_ambas_denominaciones(self):
        rs = self._consultar('CELEX-32008R1333', ['ANEXO II\nSorbitoles Manitol ►C12 Isomalt ◄ Maltitoles Lactitol', 'ANEXO III\nSorbitol Manitol ►C13 Isomalt ◄ Maltitol Lactitol'], ['anexo.II', 'anexo.III'])
        for ruta, denominacion in [('anexo.II', 'Maltitoles'), ('anexo.III', 'Maltitol')]:
            with self.subTest(ruta=ruta):
                self.assertEqual(rs[ruta].estado, 'ENCONTRADO')
                self.assertIn('Isomalt ' + denominacion, rs[ruta].texto_literal)

    def test_api_h3_separa_textos_y_paginas(self):
        rs = self._consultar('CELEX-32015R1375', ['Artículo 13\nRequisitos sanitarios de importación\nCuerpo de control.', 'ANEXO VI\nTabla de correspondencias\nAnexo VII Anexo V\nAnexo VI', '▼M2\nANEXO VII\nTerceros países o sus regiones\nGB'], ['art.13', 'anexo.VI', 'anexo.VII'])
        for ruta, pag in [('art.13', 1), ('anexo.VI', 2), ('anexo.VII', 3)]:
            with self.subTest(ruta=ruta):
                self.assertEqual(rs[ruta].estado, 'ENCONTRADO')
                self.assertEqual((rs[ruta].pagina_inicio, rs[ruta].pagina_fin), (pag, pag))
        self.assertNotIn('ANEXO VII', rs['anexo.VI'].texto_literal)
        self.assertIn('Terceros países', rs['anexo.VII'].texto_literal)
if __name__ == '__main__':
    unittest.main()
