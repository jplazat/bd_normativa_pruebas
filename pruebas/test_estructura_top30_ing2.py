"""Public CI documentation."""
import json
import sqlite3
from pathlib import Path
import unittest
from ict155 import parsers
from ict155 import consulta
from ict155.extraccion import TextoPdf
from pruebas import estructura_completa_top30 as ec
FIXTURES = Path(__file__).parent / 'fixtures/top30_ing2_textos_publicos.json'

def fixture(ident):
    dato = json.loads(FIXTURES.read_text(encoding='utf-8'))[ident]
    paginas = [p['texto'] for p in dato['paginas']]
    if ident.startswith('BOE-'):
        paginas[0] = 'LEGISLACIÓN CONSOLIDADA\nReferencia: ' + ident + '\nTEXTO CONSOLIDADO\n' + paginas[0]
    return TextoPdf(ruta_relativa=dato['ruta_relativa'], paginas=paginas)

def parsear(ident, pdf=None):
    pdf = pdf or fixture(ident)
    return {p.ruta: p for p in parsers.analizar('boe' if ident.startswith('BOE-') else 'eurlex', pdf).preceptos}

def filas(ps):
    return [dict(ruta=p.ruta, padre=p.padre, texto=p.texto, tipo=p.tipo) for p in ps.values()]

class TestReparacionesTexto(unittest.TestCase):

    def test_sanidad_114_115_116_y_sus_limites(self):
        ps = parsear('BOE-A-1986-10499')
        self.assertTrue({'art.114', 'art.115', 'art.116', 'art.116.3'} <= ps.keys())
        self.assertNotIn('Artículo ciento quince.', ps['art.114'].texto)
        self.assertNotIn('Artículo ciento dieciséis.', ps['art.115'].texto)
        self.assertIn('art.115.a', ps)

    def test_89108_articulo13_separado_en_texto_real(self):
        ps = parsear('CELEX-31989L0108')
        self.assertIn('art.13', ps)
        self.assertNotIn('Artículo 13', ps['art.12'].texto)
        self.assertNotIn('Artículo 14', ps['art.13'].texto)

    def test_89108_separador_pegado_como_en_flujo_de_ingesta(self):
        pdf = fixture('CELEX-31989L0108')
        pdf.paginas = [s.replace('Artículo 13', '__________ Artículo 13') for s in pdf.paginas]
        ps = parsear('CELEX-31989L0108', pdf)
        self.assertIn('art.13', ps)
        self.assertNotIn('Artículo 13', ps['art.12'].texto)
        self.assertIn('__________ Artículo 13', ps['art.13'].texto)

    def test_625_166_sin_espacio_en_fixture_real(self):
        pdf = fixture('CELEX-32017R0625')
        self.assertIn('Artículo166', pdf.texto)
        ps = parsear('CELEX-32017R0625', pdf)
        self.assertIn('art.166', ps)
        self.assertNotIn('Artículo166', ps['art.165'].texto)
        self.assertNotIn('Artículo 167', ps['art.166'].texto)

    def test_anexos_sin_numero_conservan_capitulos_y_padre(self):
        for ident in ('BOE-A-2010-927', 'CELEX-31980L0181'):
            ps = parsear(ident)
            for n in ('I', 'II', 'III', 'IV'):
                with self.subTest(ident=ident, capitulo=n):
                    self.assertEqual(ps[f'anexo.sn/capitulo.{n}'].padre, 'anexo.sn')
                    self.assertNotIn(f'capitulo.{n}', ps)
            if ident == 'BOE-A-2010-927':
                self.assertIn('kilogramo', ps['anexo.sn/capitulo.I'].texto)

    def test_definiciones_numeradas_y_letras_de_1025(self):
        casos = {'CELEX-32018L1972': ('art.2.20', 'interferencia perjudicial'), 'CELEX-32012R1025': ('art.2.1.c', 'norma armonizada'), 'CELEX-32017R0745': ('art.2.1', 'producto sanitario'), 'CELEX-32017R0746': ('art.2.2', 'diagnóstico in vitro'), 'CELEX-32016R0679': ('art.4.2', 'tratamiento')}
        for ident, (ruta, termino) in casos.items():
            with self.subTest(ident=ident):
                ps = parsear(ident)
                self.assertIn(termino, ps[ruta].texto)
                self.assertEqual(ps[ruta].padre, ruta.rsplit('.', 1)[0])
                self.assertIn(ps[ruta].texto, ps[ruta.split('.')[0] + '.' + ruta.split('.')[1]].texto)

    def test_2018_las_42_definiciones_y_sus_limites(self):
        ps = parsear('CELEX-32018L1972')
        self.assertTrue({f'art.2.{n}' for n in range(1, 43)} <= ps.keys())
        self.assertNotIn('21)', ps['art.2.20'].texto)
        self.assertIn('interferencia perjudicial', ps['art.2'].texto)

    def test_2002_letras_con_hueco_sin_inventar_e(self):
        ps = parsear('CELEX-32002L0058')
        self.assertIn('datos de tráfico', ps['art.2.b'].texto)
        self.assertIn('datos de localización', ps['art.2.c'].texto)
        self.assertNotIn('art.2.e', ps)
        self.assertNotIn('c)', ps['art.2.b'].texto)

    def test_otras_normas_no_reciben_definiciones_ni_letras_con_huecos(self):
        pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=['02099R0001 — ES — 01.01.2099\nArtículo 2\nDefiniciones\n1) «alfa»: uno.\n2) «beta»: dos.'])
        ps = {p.ruta: p for p in parsers.analizar_eurlex(pdf).preceptos}
        self.assertNotIn('art.2.1', ps)
        p = parsers.Precepto(ruta='art.2', tipo='articulo', numero='2', etiqueta='Artículo 2', titulo=None, lineas=['a) Alfa.', 'c) Gamma.'])
        self.assertEqual([p.ruta for p in parsers.subdividir([p])], ['art.2'])

    def test_remisiones_y_articulos_entrecomillados_no_abren_articulos(self):
        pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=['02099R0001 — ES — 01.01.2099\nArtículo 1\nObjeto\nArtículo166 del Reglamento anterior.\n«Artículo166» es una cita.\nTexto.'])
        self.assertNotIn('art.166', {p.ruta for p in parsers.analizar_eurlex(pdf).preceptos})

    def test_numeracion_reiniciada_no_inventa_definiciones(self):
        p = parsers.Precepto(ruta='art.2', tipo='articulo', numero='2', etiqueta='Artículo 2', titulo=None, lineas=['1) «alfa»: uno.', '2) «beta»: dos.', '1) Otra lista.'])
        self.assertEqual(parsers._definiciones_numeradas(p), [])

class TestComprobadorIndependiente(unittest.TestCase):

    def test_encuentra_absorciones_115_13_166_sin_importar_parser(self):
        for fuente, esperado, contenedor in [('Artículo ciento catorce.\nUno.\nArtículo ciento quince.\nDos.', 'art.115', 'art.114'), ('Artículo 12\nUno.\nArtículo 13\nDos.', 'art.13', 'art.12'), ('Artículo 165\nUno.\nArtículo166\nDos.', 'art.166', 'art.165')]:
            with self.subTest(esperado=esperado):
                hs, _ = ec.censo_texto(fuente, 'boe' if 'ciento' in fuente else 'eurlex')
                r = ec.comparar(hs, [dict(ruta=contenedor, tipo='articulo', padre=None, texto=fuente)])
                self.assertIn(esperado, {h['ruta'] for h in r['faltantes']})
                self.assertIn(esperado, {h['ruta'] for h in r['absorbidos']})

    def test_no_acepta_ruta_vacia_ni_solo_rotulo(self):
        texto = 'Artículo 1\nRegla completa.'
        for valor in ('', 'Artículo 1'):
            r = ec.comprobar_norma(texto, [dict(ruta='art.1', tipo='articulo', padre=None, texto=valor)])
            self.assertFalse(r['correcta'])
        self.assertTrue(ec.comprobar_norma(texto, [dict(ruta='art.1', tipo='articulo', padre=None, texto=texto)])['correcta'])

    def test_anexo_rotulo_con_hijos_no_se_declara_vacio(self):
        texto = 'ANEXO\nCAPÍTULO I\nContenido.'
        filas = [dict(ruta='anexo.sn', tipo='anexo', padre=None, texto='ANEXO'), dict(ruta='anexo.sn/capitulo.I', tipo='capitulo', padre='anexo.sn', texto='CAPÍTULO I Contenido.')]
        self.assertTrue(ec.comprobar_norma(texto, filas)['correcta'])
        filas[1]['padre'] = None
        self.assertTrue(ec.comprobar_norma(texto, filas)['jerarquia'])

    def test_ignora_indice_y_tabla_correspondencias_pero_no_una_mencion(self):
        texto = 'Artículo 1\nVéase la tabla de correspondencias.\nArtículo 2\nRegla.\nANEXO I\nTABLA DE CORRESPONDENCIAS\nArtículo 9\nArtículo 10'
        hs, _ = ec.censo_texto(texto)
        self.assertEqual([h.ruta for h in hs], ['art.1', 'art.2', 'anexo.I'])
        hs, _ = ec.censo_texto('Artículo 9.....3\nTEXTO CONSOLIDADO\nArtículo 1. Objeto.\nRegla.', 'boe')
        self.assertEqual([h.ruta for h in hs], ['art.1'])

    def test_subdivisiones_presentes_no_se_pueden_eximir_por_ancestro(self):
        texto = 'Artículo 2\nDefiniciones\n1) «alfa»: clase primera.\na) Subclase.\nc) Otra subclase.\n2) «beta»: clase segunda.'
        r = ec.comprobar_norma(texto, [dict(ruta='art.2', tipo='articulo', padre=None, texto=texto)])
        self.assertFalse(r['correcta'])
        self.assertIn('art.2.1.c', {h['ruta'] for h in r['faltantes']})
        self.assertIn('art.2.1.c', {h['ruta'] for h in r['absorbidos']})

    def test_un_rotulo_no_soportado_queda_pendiente_sin_falso_verde(self):
        texto = 'Artículo 1\nRegla.\nArtículo centésimo.\nOtra regla.'
        r = ec.comprobar_norma(texto, [dict(ruta='art.1', tipo='articulo', padre=None, texto=texto)])
        self.assertFalse(r['correcta'])
        self.assertEqual(r['candidatos_pendientes'][0]['motivo'], 'rotulo_no_clasificado_o_remision')

    def test_itc_distingue_indice_epigrafe_y_potencia_de_tabla(self):
        texto = 'INSTRUCCIÓN TÉCNICA COMPLEMENTARIA (ITC) BT-52\nÍndice\n1. Objeto.\n2. Definiciones.\n1. Objeto\n1. Una regla interna.\n2. Otra regla interna.\n2. Definiciones\n2.300 W'
        hs, candidatos = ec.censo_texto(texto, 'boe')
        self.assertEqual([h.ruta for h in hs], ['itc.BT-52', 'itc.BT-52/ap.1', 'itc.BT-52/ap.2'])
        self.assertEqual(candidatos, [])

class TestConsultaSobreTexto(unittest.TestCase):

    def test_rutas_reparadas_resuelven_en_sqlite_en_memoria(self):
        """Public CI documentation."""
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        con.executescript((Path(parsers.__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
        requeridos = {'BOE-A-1986-10499': ['art.115', 'art.116'], 'BOE-A-2010-927': ['anexo.sn/capitulo.I'], 'CELEX-31989L0108': ['art.13'], 'CELEX-32017R0625': ['art.166'], 'CELEX-31980L0181': ['anexo.sn/capitulo.I'], 'CELEX-32018L1972': ['art.2.20'], 'CELEX-32012R1025': ['art.2.1.c'], 'CELEX-32002L0058': ['art.2.b', 'art.2.c'], 'CELEX-32017R0745': ['art.2.1'], 'CELEX-32017R0746': ['art.2.2'], 'CELEX-32016R0679': ['art.4.1', 'art.4.2']}
        try:
            for ident, rutas in requeridos.items():
                ps = parsear(ident)
                doc = con.execute('INSERT INTO documento (ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES (?,?,?,?,?,?)', (ident + '.pdf', 'sintetico', 0, '2099-01-01', 'publico', 'ingerido')).lastrowid
                obra = con.execute('INSERT INTO obra (identificador_canonico,tipo,titulo,jurisdiccion) VALUES (?,?,?,?)', (ident, 'boe' if ident.startswith('BOE') else 'eurlex', ident, 'ES' if ident.startswith('BOE') else 'UE')).lastrowid
                ver = con.execute('INSERT INTO version (obra_id,documento_id,etiqueta,idioma) VALUES (?,?,?,?)', (obra, doc, 'fixture', 'es')).lastrowid
                ids = {}
                for orden, p in enumerate(ps.values()):
                    ids[p.ruta] = con.execute('INSERT INTO precepto (version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES (?,?,?,?,?,?,?,?,?,?)', (ver, ids.get(p.padre), p.ruta, p.tipo, p.numero, p.etiqueta, p.texto, p.pagina_inicio, p.pagina_fin, orden)).lastrowid
                for ruta in rutas:
                    with self.subTest(ident=ident, ruta=ruta):
                        resultado = consulta.resolver(con, f'{ident}::{ruta}')
                        self.assertEqual(resultado.estado, 'ENCONTRADO')
                        self.assertEqual(resultado.texto_literal, ps[ruta].texto)
        finally:
            con.close()
if __name__ == '__main__':
    unittest.main()
