"""Public CI documentation."""
import sqlite3
import unittest
from pathlib import Path
from ict155 import consulta, parsers
from ict155.extraccion import TextoPdf

def analizar(texto, familia='eurlex'):
    return parsers.analizar(familia, TextoPdf('sintetico.pdf', paginas=[texto])).preceptos

def memoria(ps, ident='CELEX-39999R0001'):
    con = sqlite3.connect(':memory:')
    con.row_factory = sqlite3.Row
    con.executescript((Path(parsers.__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
    con.execute("INSERT INTO documento(id,ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES(1,'publico.pdf','sintetico',0,'2099-01-01','publico','ingerido')")
    con.execute("INSERT INTO obra(id,identificador_canonico,tipo,titulo,jurisdiccion) VALUES(1,?,'eurlex','Sintético','UE')", (ident,))
    con.execute("INSERT INTO version(id,obra_id,documento_id,etiqueta,idioma) VALUES(1,1,1,'sintética','es')")
    ids = {}
    for orden, p in enumerate(ps):
        ids[p.ruta] = con.execute('INSERT INTO precepto(version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES(1,?,?,?,?,?,?,?,?,?)', (ids.get(p.padre), p.ruta, p.tipo, p.numero, p.etiqueta, p.texto, p.pagina_inicio, p.pagina_fin, orden)).lastrowid
    return con

class TestContenedores(unittest.TestCase):

    def comprobar(self, texto, ruta, articulos):
        ps = analizar(texto, 'boe')
        con = memoria(ps)
        self.addCleanup(con.close)
        r, ambito = consulta.texto_de_ambito(con, 'CELEX-39999R0001::' + ruta)
        self.assertEqual(r.estado, consulta.ENCONTRADO)
        for n in articulos:
            art = consulta.resolver(con, 'CELEX-39999R0001::art.' + str(n))
            self.assertTrue(art.texto_literal)
            self.assertIn(art.texto_literal, ambito)
        self.assertGreater(len(ambito), len(r.texto_literal))
        self.assertIn('rótulo', r.detalle)

    def test_rd989_capitulo_iii(self):
        self.comprobar('TEXTO CONSOLIDADO\nCAPÍTULO III\nRegistro de los movimientos de leche\nArtículo 7. Registro de entregas de leche, recibo de entregas y registro de movimientos.\nArtículo 8. Comunicación de movimientos a la «base de datos Letra Q».', 'capitulo.III', [7, 8])

    def test_rebt_reglamento(self):
        self.comprobar('TEXTO CONSOLIDADO\nDisposición final primera.\nTexto sintético.\nREGLAMENTO ELECTROTÉCNICO PARA BAJA TENSIÓN\nArtículo 1. Objeto.\na) Preservar la seguridad de las personas y los bienes.\nArtículo 29. Guía técnica.', 'reglamento', [1, 29])

    def test_ley24_titulo_x(self):
        self.comprobar('TEXTO CONSOLIDADO\nTÍTULO X\nRégimen de inspecciones, infracciones y sanciones\nCAPÍTULO I\nInspecciones\nArtículo 61. Facultades de inspección.\nCAPÍTULO II\nInfracciones y sanciones\nArtículo 80. Efectos de la resolución.', 'titulo.X', [61, 80])

    def test_no_arrastra_capitulo_siguiente_ni_disposiciones(self):
        ps = analizar('TEXTO CONSOLIDADO\nCAPÍTULO I\nUno\nArtículo 1. Primero.\nCAPÍTULO II\nDos\nArtículo 10. Décimo.\nDisposición final primera. Fin.', 'boe')
        con = memoria(ps)
        self.addCleanup(con.close)
        _, t = consulta.texto_de_ambito(con, 'CELEX-39999R0001::capitulo.I')
        self.assertIn('Artículo 1.', t)
        self.assertNotIn('Artículo 10.', t)
        self.assertNotIn('Disposición final', t)

class TestPuntosAnexo(unittest.TestCase):

    def test_1169_anexo_v_punto_7(self):
        texto = 'ANEXO V\nALIMENTOS EXENTOS DEL REQUISITO DE INFORMACIÓN NUTRICIONAL OBLIGATORIA\n'
        texto += '1. Productos sin transformar que incluyen un solo ingrediente o una sola categoría de ingredientes.\n'
        texto += ''.join((f'{n}. Texto sintético de control.\n' for n in range(2, 7)))
        texto += '7. Productos contemplados por la Directiva 1999/4/CE del Parlamento Europeo y del Consejo, de 22 de febrero de 1999, relativa a los extractos de café y los extractos de achicoria (1), granos de café enteros o molidos y granos de café descafeinado enteros o molidos.\n8. Texto sintético siguiente.'
        ps = analizar(texto)
        r = {p.ruta: p for p in ps}
        self.assertIn('anexo.V/ap.7', r)
        self.assertIn('Directiva 1999/4/CE', r['anexo.V/ap.7'].texto)
        self.assertNotIn('8. Texto', r['anexo.V/ap.7'].texto)
        self.assertEqual(r['anexo.V/ap.7'].padre, 'anexo.V')
        self.assertIn('7. Productos', r['anexo.V'].texto)

    def test_1169_anexo_vi_parte_a_punto_3(self):
        texto = 'ANEXO VI\nDENOMINACIÓN DEL ALIMENTO Y MENCIONES ESPECÍFICAS QUE LO ACOMPAÑAN\n'
        texto += 'PARTE A — MENCIONES OBLIGATORIAS QUE ACOMPAÑAN A LA DENOMINACIÓN DEL ALIMENTO\n'
        texto += '1. Texto sintético primero.\n2. Texto sintético segundo.\n'
        texto += '3. Los alimentos tratados con radiaciones ionizantes llevarán una de las indicaciones siguientes:\n'
        texto += '«irradiado» o «tratado con radiación ionizante», y otras indicaciones conforme a lo dispuesto en la Directiva 1999/2/CE\n'
        texto += 'PARTE B — CONTROL SINTÉTICO\n1. Otra parte.\n2. Cierre.'
        r = {p.ruta: p for p in analizar(texto)}
        self.assertIn('anexo.VI/parte.A/ap.3', r)
        p = r['anexo.VI/parte.A/ap.3']
        self.assertIn('Directiva 1999/2/CE', p.texto)
        self.assertNotIn('PARTE B', p.texto)
        self.assertEqual(p.padre, 'anexo.VI/parte.A')

    def test_2073_capitulo_3_punto_32(self):
        texto = 'ANEXO I\nÍNDICE\nCapítulo 3. Normas para la toma de muestras y preparación de estas para las pruebas\n'
        texto += 'Capítulo 1. Criterios de seguridad alimentaria\nContenido sintético de tabla.\n'
        texto += 'Capítulo 2. Criterios de higiene de los procesos\nContenido sintético.\n'
        texto += 'Capítulo 3. Normas para la toma de muestras y preparación de estas para las pruebas\n'
        texto += '3.1. Normas generales para la toma de muestras y preparación de estas para las pruebas\n'
        texto += '3.2. Muestreo bacteriológico en los mataderos y en los locales que producen carne picada, preparados de carne, carne separada mecánicamente y carne\nfresca\n'
        texto += 'Normas de muestreo para las canales de bovinos, porcinos, ovinos, caprinos y equinos\n'
        texto += '3.3. Normas de muestreo para los brotes\n'
        texto += '1. Pruebas preliminares del lote de semillas\n2. Muestreo y pruebas de los brotes y del agua de riego utilizada\n3. Frecuencia de muestreo'
        r = {p.ruta: p for p in analizar(texto)}
        self.assertIn('anexo.I/capitulo.3/ap.3.2', r)
        self.assertIn('canales de bovinos', r['anexo.I/capitulo.3/ap.3.2'].texto)
        self.assertNotIn('3.3.', r['anexo.I/capitulo.3/ap.3.2'].texto)

    def test_1333_anexo_i_punto_5(self):
        texto = 'ANEXO I\nClases funcionales de aditivos alimentarios\n'
        texto += ''.join((f'{n}. Texto sintético de control.\n' for n in range(1, 5)))
        texto += '5. «Soportes»: sustancias empleadas para disolver, diluir, dispersar o modificar físicamente de otra manera un aditivo alimentario\n'
        texto += '6. «Acidulantes»: sustancias que incrementan la acidez de un producto alimenticio o le confieren un sabor ácido, o ambas cosas.'
        r = {p.ruta: p for p in analizar(texto)}
        self.assertIn('anexo.I/ap.5', r)
        self.assertIn('«Soportes»', r['anexo.I/ap.5'].texto)
        self.assertNotIn('«Acidulantes»', r['anexo.I/ap.5'].texto)

    def test_sin_lista_no_inventa_unidades(self):
        texto = 'ANEXO I\nÁMBITO\nSe aplica el punto 1. de otra norma.\n5 mg/kg\n20 30 40'
        ps = analizar(texto)
        self.assertEqual([p.ruta for p in ps], ['anexo.I'])
        self.assertIn('20 30 40', ps[0].texto)

    def test_numeracion_reiniciada_ambigua_no_se_desglosa(self):
        texto = 'ANEXO I\n1. Primero.\n2. Segundo.\n1. Lista interior.\n2. Otro interior.'
        self.assertEqual([p.ruta for p in analizar(texto)], ['anexo.I'])

    def test_tabla_de_correspondencias_no_inventa_puntos(self):
        texto = 'ANEXO I\nTABLA DE CORRESPONDENCIAS\n1. Norma antigua.\n2. Norma nueva.'
        self.assertEqual([p.ruta for p in analizar(texto)], ['anexo.I'])

    def test_repeticion_con_cuerpo_no_se_toma_por_indice(self):
        texto = 'ANEXO I\nCapítulo 1. Primer encabezado\nTexto que debe conservarse.\n'
        texto += 'Capítulo 1. Primer encabezado\nContinuación.\nCapítulo 2. Segundo encabezado\nFinal.'
        self.assertEqual([p.ruta for p in analizar(texto)], ['anexo.I'])

    def test_decimales_anidados_y_limites(self):
        texto = 'ANEXO I\n1. Padre.\n1.1. Hijo primero.\n1.2. Hijo segundo.\n2. Hermano.'
        r = {p.ruta: p for p in analizar(texto)}
        self.assertEqual(r['anexo.I/ap.1.1'].padre, 'anexo.I/ap.1')
        self.assertIn('1.2.', r['anexo.I/ap.1'].texto)
        self.assertNotIn('2. Hermano', r['anexo.I/ap.1'].texto)
if __name__ == '__main__':
    unittest.main()
