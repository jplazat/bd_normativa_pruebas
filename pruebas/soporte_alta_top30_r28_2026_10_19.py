"""Public CI documentation."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from pathlib import Path
from ict155 import caracter, catalogo, consulta, db, parsers, vigencia
from ict155.extraccion import TextoPdf
from pruebas import estructura_completa_top30 as estructura
RAIZ = Path(__file__).resolve().parents[3]
BASE = RAIZ / 'lad_top30/ict155/bd/conocimiento.sqlite'
FP = '01_Conocimiento/Fuentes_primarias/'
NORMAS = (('BOE-A-2020-15872', 'BOE_RD1086-2020_higiene_alimentaria_BOE-A-2020-15872_consolidado.pdf', 'RD 1086/2020'), ('BOE-A-2015-2293', 'BOE_RD126-2015_informacion_alimentaria_BOE-A-2015-2293_consolidado.pdf', 'RD 126/2015'), ('BOE-A-2011-4293', 'BOE_RD191-2011_registro_sanitario_BOE-A-2011-4293_consolidado.pdf', 'RD 191/2011'), ('BOE-A-1986-10499', 'BOE_Ley14-1986_General_Sanidad_BOE-A-1986-10499_consolidada.pdf', 'Ley 14/1986'), ('BOE-A-2010-927', 'BOE_RD2032-2009_unidades_medida_BOE-A-2010-927_consolidado.pdf', 'RD 2032/2009'), ('BOE-A-2007-16478', 'BOE_RD1110-2007_puntos_medida_BOE-A-2007-16478_consolidado.pdf', 'RD 1110/2007'), ('BOE-A-2014-13681', 'BOE_RD1053-2014_ITC_BT52_BOE-A-2014-13681_consolidado.pdf', 'RD 1053/2014'), ('BOE-A-2022-4361', 'BOE_RD184-2022_recarga_energetica_BOE-A-2022-4361_consolidado.pdf', 'RD 184/2022'), ('CELEX-31989L0108', 'DOUE_Directiva_89-108-CEE_CELEX-31989L0108_consolidada_es.pdf', 'Directiva 89/108/CEE'), ('CELEX-32011R1169', 'DOUE_Reglamento_UE_1169-2011_CELEX-32011R1169_consolidado_es.pdf', 'Reglamento (UE) 1169/2011'), ('CELEX-32017R0625', 'DOUE_Reglamento_UE_2017-625_CELEX-32017R0625_consolidado_es.pdf', 'Reglamento (UE) 2017/625'), ('CELEX-32012R1025', 'DOUE_Reglamento_UE_1025-2012_CELEX-32012R1025_consolidado_es.pdf', 'Reglamento (UE) 1025/2012'), ('CELEX-31976L0211', 'DOUE_Directiva_76-211-CEE_CELEX-31976L0211_consolidada_es.pdf', 'Directiva 76/211/CEE'), ('CELEX-31980L0181', 'DOUE_Directiva_80-181-CEE_CELEX-31980L0181_consolidada_es.pdf', 'Directiva 80/181/CEE'), ('CELEX-32002L0058', 'DOUE_Directiva_2002-58-CE_CELEX-32002L0058_consolidada_es.pdf', 'Directiva 2002/58/CE'), ('CELEX-32017R0745', 'DOUE_Reglamento_UE_2017-745_CELEX-32017R0745_consolidado_es.pdf', 'Reglamento (UE) 2017/745'), ('CELEX-32017R0746', 'DOUE_Reglamento_UE_2017-746_CELEX-32017R0746_consolidado_es.pdf', 'Reglamento (UE) 2017/746'), ('CELEX-32016R0679', 'DOUE_Reglamento_UE_2016-679_CELEX-32016R0679_consolidado_es.pdf', 'Reglamento (UE) 2016/679'), ('CELEX-32019L0713', 'DOUE_Directiva_UE_2019-713_CELEX-32019L0713_original_es.pdf', 'Directiva (UE) 2019/713'), ('CELEX-32018L1972', 'DOUE_Directiva_UE_2018-1972_CELEX-32018L1972_consolidada_es.pdf', 'Directiva (UE) 2018/1972'), ('BOE-A-1989-5084', 'BOE_Orden28-12-1988_contadores_agua_BOE-A-1989-5084_HISTORICA_DEROGADA_2015-12-01.pdf', 'Orden de 28 de diciembre de 1988'))
CITAS = (('BOE-A-2020-15872', 'art.30', 'comidas preparadas'), ('BOE-A-2015-2293', 'art.4', 'información'), ('BOE-A-2011-4293', 'art.2.1', 'inscribirán'), ('BOE-A-2011-4293', 'art.2.2', 'excluidos'), ('BOE-A-1986-10499', 'art.40.2', 'alimentos'), ('BOE-A-1986-10499', 'art.40.4', 'aliment'), ('BOE-A-2010-927', 'anexo.sn/capitulo.I', 'kilogramo'), ('BOE-A-2007-16478', 'art.9.8', 'telegestión'), ('BOE-A-2007-16478', 'art.9.9', 'tipo 3 y 4'), ('BOE-A-2014-13681', 'itc.BT-52/ap.2', 'Modo de carga 4'), ('BOE-A-2022-4361', 'art.3', 'Definiciones'), ('CELEX-31989L0108', 'art.11', 'temperatura'), ('CELEX-31989L0108', 'art.13', 'Estados miembros'), ('CELEX-32011R1169', 'art.9.1.g', 'conservación'), ('CELEX-32011R1169', 'art.25.1', 'conservación'), ('CELEX-32017R0625', 'art.15.1', 'acceso'), ('CELEX-32012R1025', 'art.2.1.c', 'norma armonizada'), ('CELEX-31976L0211', 'art.1', 'envases preparados'), ('CELEX-31976L0211', 'art.2', 'envase preparado'), ('CELEX-31976L0211', 'anexo.I', 'contenido'), ('CELEX-31980L0181', 'art.1.b', 'anexo'), ('CELEX-32002L0058', 'art.2.b', 'datos de tráfico'), ('CELEX-32002L0058', 'art.2.c', 'datos de localización'), ('CELEX-32017R0745', 'art.1.1', 'productos sanitarios'), ('CELEX-32017R0745', 'art.2.1', 'producto sanitario'), ('CELEX-32017R0746', 'art.1.1', 'diagnóstico in vitro'), ('CELEX-32017R0746', 'art.2.2', 'diagnóstico in vitro'), ('CELEX-32016R0679', 'art.4.1', 'datos personales'), ('CELEX-32016R0679', 'art.4.2', 'tratamiento'), ('CELEX-32019L0713', 'art.2.d', 'monedas virtuales'), ('CELEX-32018L1972', 'art.2', 'interferencia perjudicial'), ('CELEX-32018L1972', 'art.45', 'espectro'), ('CELEX-32018L1972', 'art.125', '2002/21/CE'), ('BOE-A-1989-5084', 'anexo.sn', 'Clases metrológicas'))

def ruta(nombre):
    return FP + ('01_Legislacion_ES/' if nombre.startswith('BOE_') else '02_Legislacion_UE/') + nombre

def analizar(ident, cuerpo):
    pdf = TextoPdf(ruta_relativa='sintetico.pdf', paginas=[f'LEGISLACIÓN CONSOLIDADA\nDocumento sintético\nReferencia: {ident}\nTEXTO CONSOLIDADO\n{cuerpo}'])
    return {p.ruta: p for p in parsers.analizar_boe(pdf).preceptos}

class TestCatalogoTop30(unittest.TestCase):

    def test_las_21_altas_son_publicas_y_vinculantes(self):
        self.assertEqual(len(NORMAS), 21)
        for ident, nombre, alias in NORMAS:
            with self.subTest(ident=ident):
                rel = ruta(nombre)
                self.assertTrue(catalogo.en_nucleo(rel))
                self.assertEqual(catalogo.clase_derechos(rel), 'publico')
                self.assertIn(alias, catalogo.alias_de(rel))
                self.assertTrue(catalogo.titulo_oficial(ident))
                cab = 'cabecera' if ident.startswith('BOE-') else 'preambulo'
                self.assertEqual(caracter.TABLA[ident][:2], ('vinculante', f'{ident}::{cab}'))

    def test_original_2019_tiene_identidad_y_edicion(self):
        rel = ruta(NORMAS[18][1])
        self.assertEqual(catalogo.metadatos(rel)['identificador'], 'CELEX-32019L0713')
        self.assertEqual(catalogo.edicion_de(rel), '2019')

    def test_sucesora_no_asume_identidad_de_la_2002_21(self):
        aliases = catalogo.alias_de(ruta(NORMAS[19][1]))
        self.assertNotIn('Directiva 2002/21/CE', aliases)
        self.assertNotIn('CELEX-32002L0021', aliases)

    def test_orden_historica_no_es_edicion_de_2015(self):
        self.assertEqual(catalogo.edicion_de(ruta(NORMAS[20][1])), '1988')

class TestTroceoTop30(unittest.TestCase):

    def test_sanidad_articulo_en_letras_conserva_literal_y_apartados(self):
        ps = analizar('BOE-A-1986-10499', 'Artículo cuarenta.\n1. Regla sintética primera.\n2. Regla sintética alimentaria.\n3. Regla sintética tercera.\n4. Regla sintética cuarta.\nArtículo cuarenta y uno.\nTexto sintético siguiente.')
        self.assertIn('art.40.2', ps)
        self.assertEqual(ps['art.40.2'].texto, '2. Regla sintética alimentaria.')
        self.assertIn('art.40.4', ps)
        self.assertTrue(ps['art.40'].texto.startswith('Artículo cuarenta.'))
        self.assertNotIn('siguiente', ps['art.40'].texto)

    def test_sanidad_articulos_ciento_y_bis(self):
        ps = analizar('BOE-A-1986-10499', 'Artículo ciento cinco bis.\nTexto A.\nArtículo ciento catorce.\nTexto B.')
        self.assertIn('art.105bis', ps)
        self.assertIn('art.114', ps)

    def test_sanidad_remision_y_cita_no_crean_articulo(self):
        ps = analizar('BOE-A-1986-10499', 'Artículo cuarenta.\nartículo cuarenta y uno. citado en minúscula.\nDisposición final primera.\n«Artículo cuarenta y dos.\nTexto ajeno.»')
        self.assertIn('art.40', ps)
        self.assertNotIn('art.41', ps)
        self.assertNotIn('art.42', ps)

    def test_fuera_de_sanidad_conserva_el_analizador_anterior(self):
        ps = analizar('BOE-A-2099-1', 'Artículo cuarenta.\nTexto sintético.')
        self.assertNotIn('art.40', ps)

    def test_bt52_sale_de_la_disposicion_final(self):
        ps = analizar('BOE-A-2014-13681', 'Disposición final décima.\nTexto de vigencia.\nINSTRUCCIÓN TÉCNICA COMPLEMENTARIA (ITC) BT-52\nInstalaciones sintéticas\nÍndice\n1. Objeto. 2. Términos. 3. Esquemas.\n1. Objeto.\nÁmbito sintético.\n2. Términos.\n«Modo de carga 1». Definición sintética.\n3. Esquemas.\nTexto posterior.')
        self.assertIn('itc.BT-52/ap.2', ps)
        self.assertIn('Modo de carga 1', ps['itc.BT-52/ap.2'].texto)
        self.assertNotIn('Modo de carga', ps['disp.final.10'].texto)
        self.assertNotIn('posterior', ps['itc.BT-52/ap.2'].texto)

    def test_bt52_no_nace_de_una_mencion_en_minuscula(self):
        ps = analizar('BOE-A-2014-13681', 'Artículo único.\nla instrucción técnica complementaria (ITC) BT-52 se menciona aquí.')
        self.assertFalse(any((r.startswith('itc.') for r in ps)))

    def test_orden_tiene_dos_apartados_y_anexo(self):
        ps = analizar('BOE-A-1989-5084', 'DISPONGO:\nPrimero.\nRegla A.\nSegundo.\nRegla B.\nDisposición final.\nEntrada sintética.\nANEXO\nTexto de anexo sintético.')
        self.assertEqual(ps['ap.1'].texto, 'Primero. Regla A.')
        self.assertEqual(ps['ap.2'].texto, 'Segundo. Regla B.')
        self.assertIn('anexo.sn', ps)

    def test_orden_no_convierte_ordinales_del_anexo_en_apartados_del_cuerpo(self):
        ps = analizar('BOE-A-1989-5084', 'ANEXO\nTexto sintético.\nPrimero.\nTexto del anexo.')
        self.assertNotIn('ap.1', ps)

    def test_numeracion_digital_de_otras_normas_se_conserva(self):
        ps = analizar('BOE-A-2099-1', 'Artículo 1. Objeto.\n1. Regla A.\n2. Regla B.\nArtículo 2. Ámbito.\nTexto final.')
        self.assertEqual(ps['art.1.2'].texto, '2. Regla B.')
        self.assertNotIn('final', ps['art.1'].texto)

@unittest.skipUnless(BASE.exists(), 'no existe la base de PRUEBAS top30')
class TestBaseTop30(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.con = db.conectar(BASE, solo_lectura=True)
        cls.con.execute('PRAGMA query_only=ON')
        assert cls.con.execute('PRAGMA query_only').fetchone()[0] == 1

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_las_21_estan_troceadas_con_titulo_caracter_y_alias(self):
        for ident, nombre, alias in NORMAS:
            with self.subTest(ident=ident):
                o = self.con.execute('SELECT titulo,caracter_juridico FROM obra WHERE identificador_canonico=?', (ident,)).fetchone()
                self.assertIsNotNone(o)
                self.assertEqual(tuple(o), (catalogo.titulo_oficial(ident), 'vinculante'))
                n = self.con.execute('SELECT count(*) FROM precepto p JOIN version v ON v.id=p.version_id JOIN obra o ON o.id=v.obra_id WHERE o.identificador_canonico=?', (ident,)).fetchone()[0]
                self.assertGreater(n, 0)
                r = consulta.resolver(self.con, alias)
                self.assertEqual((r.estado, r.obra), ('ENCONTRADO', ident))

    def test_las_remisiones_de_b5_tienen_texto_del_destino(self):
        self.assertEqual(len(CITAS), 34)
        for ident, ruta_p, termino in CITAS:
            with self.subTest(ident=ident, ruta=ruta_p):
                r = consulta.resolver(self.con, f'{ident}::{ruta_p}')
                self.assertEqual((r.estado, r.obra), ('ENCONTRADO', ident))
                self.assertIn(termino.lower(), r.texto_literal.lower())

    def test_la_estructura_del_texto_no_se_puede_dar_por_ausente(self):
        import json
        datos = json.loads((Path(__file__).parent / 'fixtures/top30_ing2_textos_publicos.json').read_text(encoding='utf-8'))
        requeridos = {'BOE-A-1986-10499': {'art.114', 'art.115', 'art.116'}, 'BOE-A-2010-927': {'anexo.sn/capitulo.I', 'anexo.sn/capitulo.IV'}, 'CELEX-31989L0108': {'art.13'}, 'CELEX-32017R0625': {'art.166'}, 'CELEX-31980L0181': {'anexo.sn/capitulo.I', 'anexo.sn/capitulo.IV'}, 'CELEX-32018L1972': {'art.2.20'}, 'CELEX-32012R1025': {'art.2.1.c'}, 'CELEX-32002L0058': {'art.2.b', 'art.2.c'}, 'CELEX-32017R0745': {'art.2.1'}, 'CELEX-32017R0746': {'art.2.2'}, 'CELEX-32016R0679': {'art.4.1', 'art.4.2'}}
        for ident, dato in datos.items():
            texto = '\n'.join((p['texto'] for p in dato['paginas']))
            hs, _ = estructura.censo_texto(texto, 'boe' if ident.startswith('BOE-') else 'eurlex')
            destinos = requeridos[ident]
            seleccion = [h for h in hs if h.ruta in destinos]
            with self.subTest(ident=ident):
                self.assertEqual({h.ruta for h in seleccion}, destinos, 'la fuente debe acreditar todos los destinos exigidos')
                resultado = estructura.comparar(seleccion, estructura.filas_sql(self.con, ident))
                self.assertEqual(resultado['faltantes'], [])
                self.assertEqual(resultado['jerarquia'], [])
                self.assertEqual(resultado['vacios'], [])

    def test_la_orden_se_expone_como_derogada_con_fecha(self):
        with patch.object(vigencia.config, 'BD', BASE):
            datos = vigencia.instantanea_actual()
        self.assertIsNotNone(datos)
        v = vigencia.vigencia_de('BOE-A-1989-5084', datos)
        self.assertEqual(v['estado'], 'derogada')
        self.assertEqual(v['fecha_derogacion'], '2015-12-01')
        self.assertIn('DEROGADA el 2015-12-01', vigencia.texto(v))
if __name__ == '__main__':
    unittest.main()
