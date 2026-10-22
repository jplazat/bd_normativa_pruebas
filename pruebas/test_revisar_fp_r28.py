"""Public CI documentation."""
import json
import sqlite3
import unittest
from pathlib import Path
from ict155 import afirmaciones, comillas, cotejo_original, revision
FIX = Path(__file__).parent / 'fixtures' / 'revisar_fp_r28' / 'destinatario_rgpd.json'

class ComillasEmparejadas(unittest.TestCase):

    def test_latinas_con_ciclo_no_valido_y_excepcion(self):
        literal = 'El equipo indicará «Ciclo no válido». No obstante, se permite repetir la medida.'
        self.assertEqual(revision.literales_del_borrador('Dice «' + literal + '»'), [(5, literal)])
        self.assertEqual(revision._gobierno_de_la_frase(literal, literal), [])

    def test_dos_niveles_de_anidamiento_latino(self):
        literal = 'Se muestra «aviso «Ciclo no válido» pendiente» hasta repetir la medida'
        self.assertEqual(revision.literales_del_borrador('«' + literal + '»'), [(0, literal)])

    def test_tipograficas_anidadas(self):
        literal = 'El equipo indicará “Ciclo no válido”. No obstante, puede repetirse.'
        self.assertEqual(revision.literales_del_borrador('“' + literal + '”'), [(0, literal)])

    def test_rectas_anidadas(self):
        literal = 'El equipo indicará "Ciclo no válido" hasta repetir la medida'
        self.assertEqual(revision.literales_del_borrador('"' + literal + '"'), [(0, literal)])

    def test_rectas_dos_niveles(self):
        literal = 'Se muestra "aviso "Ciclo no válido" pendiente" hasta repetir'
        self.assertEqual(revision.literales_del_borrador('"' + literal + '"'), [(0, literal)])

    def test_familias_mezcladas(self):
        literal = 'El equipo indicará “aviso «Ciclo no válido» pendiente” y "repetir medida"'
        self.assertEqual(revision.literales_del_borrador('«' + literal + '»'), [(0, literal)])

    def test_casos_anteriores_y_posiciones(self):
        t = 'Dice «uno dos tres cuatro» y "cinco seis siete ocho".\n“nueve diez”'
        self.assertEqual(revision.literales_del_borrador(t), [(5, 'uno dos tres cuatro'), (29, 'cinco seis siete ocho'), (54, 'nueve diez')])

    def test_rectas_cortas_siguen_sin_ser_literales(self):
        self.assertEqual(revision.literales_del_borrador('"abc" y «x» y “y”'), [(8, 'x'), (14, 'y')])

    def test_bloque_sigue_igual(self):
        t = '> primera línea «uno dos»\n> segunda línea\n\nDice «tres cuatro»'
        self.assertEqual(revision.literales_del_borrador(t), [(0, 'primera línea «uno dos» segunda línea'), (48, 'tres cuatro')])

    def test_comillas_sin_cerrar_no_producen_literal_parcial(self):
        for t in ('«El titular deberá conservar el registro.', '“El titular deberá conservar el registro.', '"El titular deberá conservar el registro.', '«El equipo muestra «Ciclo no válido» sin cierre exterior'):
            with self.subTest(t=t):
                self.assertEqual(revision.literales_del_borrador(t), [])

    def test_sin_cierre_no_absorbe_la_linea_siguiente(self):
        self.assertEqual(revision.literales_del_borrador('«sin cerrar\nDice «uno dos»'), [(17, 'uno dos')])

    def test_no_acepta_cierres_cruzados(self):
        self.assertEqual(revision.literales_del_borrador('«inicio “interior» final”'), [])

    def test_dos_citas_rectas_independientes_no_se_juntan(self):
        self.assertEqual(revision.literales_del_borrador('"uno dos tres" y "cuatro cinco seis"'), [(0, 'uno dos tres'), (17, 'cuatro cinco seis')])

    def test_dos_niveles_tipograficos(self):
        literal = 'Se muestra “aviso “Ciclo no válido” pendiente” hasta repetir'
        self.assertEqual(revision.literales_del_borrador('“' + literal + '”'), [(0, literal)])

    def test_error_de_comillas_respeta_lineas_crlf(self):
        errores = []
        self.assertEqual(comillas.tramos('«sin cierre\r\nDice «uno dos»', errores), [(18, 27)])
        self.assertEqual(errores, [(0, 11)])

    def test_precepto_real_incluye_su_excepcion(self):
        d = json.loads(FIX.read_text(encoding='utf-8'))
        literal = d['texto']
        self.assertEqual(d['clase_derechos'], 'publico')
        self.assertIn('No obstante', literal)
        borrador = f"`{d['identificador']}`: «{literal}»"
        self.assertEqual(revision.literales_del_borrador(borrador), [(borrador.index('«'), literal)])
        self.assertEqual(revision._gobierno_de_la_frase(literal, literal), [])

class RevisionCompleta(unittest.TestCase):

    def setUp(self):
        self.d = json.loads(FIX.read_text(encoding='utf-8'))
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript((Path(__file__).parents[1] / 'ict155' / 'esquema.sql').read_text(encoding='utf-8'))
        self.con.execute("INSERT INTO documento(id,ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES(1,'rgpd-publico.pdf','fixture',0,'2026-10-20','publico','ingerido')")
        self.con.execute("INSERT INTO obra(id,identificador_canonico,tipo,titulo,jurisdiccion) VALUES(1,'CELEX-32016R0679','reglamento','Reglamento (UE) 2016/679','UE')")
        self.con.execute("INSERT INTO version(id,obra_id,documento_id,etiqueta,idioma) VALUES(1,1,1,'v1','es')")
        self.con.execute("INSERT INTO precepto(version_id,ruta_estructural,tipo_unidad,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES(1,'art.4.9','articulo','Artículo 4.9',?,1,1,1)", (self.d['texto'],))
        self.con.commit()
        self.con.execute('PRAGMA query_only=ON')
        self.addCleanup(self.con.close)

    def revisar(self, texto):
        clave = cotejo_original.clave_de_version('v1', 'es')
        datos = cotejo_original.Datos(ue={'obras': {'CELEX-32016R0679': {'versiones': {clave: {'estado': 'ok', 'celex': '32016R0679', 'texto': self.d['texto']}}}}})
        return revision.revisar(self.con, texto, huella_base='fixture', datos_vigencia={}, datos_historial={}, tabla_sucesion=[], datos_cotejo=datos)

    def test_literal_real_completo_sin_aviso_de_excepcion(self):
        inf = self.revisar(f"`{self.d['identificador']}`: «{self.d['texto']}»")
        self.assertFalse([c for c in inf.comprobaciones if c.tipo == 'literal' and c.nivel != revision.OK])
        self.assertEqual(len([c for c in inf.comprobaciones if c.tipo == 'literal']), 1)

    def test_excepcion_real_omitida_sigue_avisando(self):
        parcial = self.d['texto'].split(' No obstante', 1)[0]
        inf = self.revisar(f"`{self.d['identificador']}`:\n\n> {parcial}")
        self.assertTrue(any((c.tipo == 'literal' and c.nivel == revision.AVISO and ('excepción' in c.detalle) for c in inf.comprobaciones)))

    def test_no_cerrada_conserva_la_guarda_de_prosa(self):
        inf = self.revisar('«El titular deberá conservar el registro de medidas.')
        self.assertEqual(inf.cobertura.sin_comprobar, 1)
        self.assertIn('LA RESPUESTA NO ESTÁ LISTA', inf.linea())
        self.assertFalse(any((c.tipo == 'literal' for c in inf.comprobaciones)))

    def test_grupos_mal_cerrados_siempre_bloquean_la_entrega(self):
        for t in ('«El equipo muestra «Ciclo no válido» sin cierre exterior', '«El cliente tiene un registrador en la cámara.', '“El cliente tiene un registrador en la cámara.', '"El cliente tiene un registrador en la cámara.', '«inicio “interior» final”'):
            with self.subTest(t=t):
                inf = self.revisar(t)
                self.assertTrue(any((c.tipo == 'comillas' and c.nivel == revision.ERROR for c in inf.comprobaciones)))
                self.assertIn('LA RESPUESTA NO ESTÁ LISTA', inf.linea())

    def test_comillas_de_bloque_o_codigo_son_contenido(self):
        inf = self.revisar('```\nvariable = "abierta\n```\n\n> 9) «destinatario\n')
        self.assertFalse(any((c.tipo == 'comillas' for c in inf.comprobaciones)))

    def test_hecho_simple_es_neutro_y_hecho_con_senal_normativa_no_se_exime(self):
        simple = self.revisar('El cliente tiene un termómetro registrador en una cámara de congelados.')
        self.assertEqual(simple.cobertura.normativas, 0)
        inf = self.revisar('El cliente conserva un certificado de verificación periódica de hace dos años.')
        self.assertEqual(inf.cobertura.sin_comprobar, 1)
        self.assertIn('LA RESPUESTA NO ESTÁ LISTA', inf.linea())
if __name__ == '__main__':
    unittest.main()
