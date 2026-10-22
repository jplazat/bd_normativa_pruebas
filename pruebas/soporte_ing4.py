"""Public CI documentation."""
import io
import json
import re
import sqlite3
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ict155 import consulta, parsers, cli, db, revision, calidad_textual, tablas
from ict155.extraccion import TextoPdf
from pruebas import estructura_completa_top30 as ec
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'lad_top30/ict155/bd/conocimiento.sqlite'
GRUPO = 'Artículo 123\nAplicación\n1. Primera regla.\n2. Segunda regla.\n▼C3 3. a) b) c) d)\n▼M5 ▼C3\nNo obstante lo dispuesto en el apartado 2:\nPrimera obligación;\nSegunda obligación;\nTercera obligación;\nCuarta obligación.\n4. Última regla.'

def abrir():
    c = sqlite3.connect(BASE.as_uri() + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    assert c.execute('PRAGMA query_only').fetchone()[0] == 1
    return c

def memoria(texto, ident='CELEX-32099R0001'):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript((Path(parsers.__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
    doc = c.execute('INSERT INTO documento (ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES (?,?,?,?,?,?)', ('sintetico.pdf', 'sintetico', 0, '2099-01-01', 'publico', 'ingerido')).lastrowid
    obra = c.execute('INSERT INTO obra (identificador_canonico,tipo,titulo,jurisdiccion) VALUES (?,?,?,?)', (ident, 'eurlex', 'Documento sintético', 'UE')).lastrowid
    ver = c.execute('INSERT INTO version (obra_id,documento_id,etiqueta,idioma) VALUES (?,?,?,?)', (obra, doc, 'sintético', 'es')).lastrowid
    ids = {}
    ps = parsers.analizar('eurlex', TextoPdf(ruta_relativa='sintetico.pdf', paginas=[texto])).preceptos
    for n, p in enumerate(ps):
        ids[p.ruta] = c.execute('INSERT INTO precepto (version_id,padre_id,ruta_estructural,tipo_unidad,numero,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES (?,?,?,?,?,?,?,?,?,?)', (ver, ids.get(p.padre), p.ruta, p.tipo, p.numero, p.etiqueta, p.texto, p.pagina_inicio, p.pagina_fin, n)).lastrowid
    return c

class TestGrupo(unittest.TestCase):

    def test_rotulos_detras_del_numero_entregan_su_cuerpo(self):
        c = memoria(GRUPO)
        self.addCleanup(c.close)
        for letra, cuerpo in zip('abcd', ['Primera', 'Segunda', 'Tercera', 'Cuarta']):
            r = consulta.resolver(c, 'CELEX-32099R0001::art.123.3.' + letra)
            self.assertEqual(r.estado, consulta.ENCONTRADO)
            self.assertEqual(r.texto_literal, letra + ') ' + cuerpo + ' obligación' + (';' if letra != 'd' else '.'))
        r = consulta.resolver(c, 'CELEX-32099R0001::art.123.3')
        self.assertIn('No obstante', r.texto_literal)
        self.assertNotIn('Última regla', r.texto_literal)

    def test_censo_descubre_letras_y_detecta_cada_omision(self):
        hs, _, _ = ec.censo_calibrado(GRUPO)
        self.assertTrue({'art.123.3.' + l for l in 'abcd'} <= {h.ruta for h in hs})
        c = memoria(GRUPO)
        self.addCleanup(c.close)
        rows = ec.filas_version(c, 1)
        for letra in 'abcd':
            result = ec.comprobar_norma(GRUPO, [r for r in rows if r['ruta'] != 'art.123.3.' + letra], criterio='calibrado')
            self.assertIn('art.123.3.' + letra, {h['ruta'] for h in result['faltantes']})

    def test_no_asigna_serie_no_consecutiva_ni_cuerpo_incompleto(self):
        for labels, bodies in [('a) c)', 'Primera regla;\nSegunda regla.'), ('a) b)', 'Sin cierre\ncontinuación.')]:
            lp = [('Artículo 1', 1), ('3. ' + labels, 1), ('Introducción:', 1)] + [(s, 2) for s in bodies.splitlines()]
            self.assertEqual(parsers._reubicar_rotulos_sueltos_ue(lp), lp)

class TestOrdinal(unittest.TestCase):

    def test_localiza_sin_entregar_el_contenedor_como_texto_propio(self):
        c = memoria('Artículo 1\n1. Introducción.\na) Regla A;\na bis) Regla adicional.\nb) Regla B.\n2. Cierre.')
        self.addCleanup(c.close)
        for ruta in ['art.1.1.abis', 'art.1.1.a bis', 'art.1.1.a bis)']:
            r = consulta.resolver(c, 'CELEX-32099R0001::' + ruta)
            self.assertEqual(r.estado, consulta.CONTENIDO_EN_ANCESTRO)
            self.assertEqual(r.ambito_localizado, 'art.1.1.a')
            self.assertIn('LOCALIZADO EN SU CONTENEDOR', r.detalle)
            self.assertIsNone(r.texto_literal)

    def test_una_remision_no_prueba_que_exista_el_rotulo(self):
        c = memoria('Artículo 1\n1. Introducción.\na) Véase la letra a bis) del acto anterior.\nb) Otra regla.\n2. Cierre.')
        self.addCleanup(c.close)
        for ruta in ['art.1.1.abis', 'art.1.1.ater', 'art.1.2.abis']:
            self.assertEqual(consulta.resolver(c, 'CELEX-32099R0001::' + ruta).estado, consulta.PRECEPTO_INEXISTENTE)

    def test_el_punto_de_anexo_no_toma_rotulos_de_otro_punto(self):
        texto = '23.3. Primer punto sin ordinal. 23.4. Segundo punto; a bis) Regla adicional. 23.5. Último punto.'
        self.assertNotIn('a bis)', consulta._texto_de_punto_impreso(texto, '23.3'))
        self.assertIn('a bis)', consulta._texto_de_punto_impreso(texto, '23.4'))
        self.assertNotIn('a bis)', consulta._texto_de_punto_impreso(texto, '23.5'))
        self.assertIsNone(consulta._texto_de_punto_impreso('Véase 23.4. Otra norma; a bis) cita ajena.', '23.4'))

class TestCalidad(unittest.TestCase):

    def test_registro_unico_con_paginas_y_testigos(self):
        avisos = calidad_textual.cargar()
        self.assertTrue({'orden_de_palabras', 'formula_corrupta', 'formula_omitida'} <= {a['no_certificado'] for a in avisos})
        for a in avisos:
            self.assertTrue(a['testigo'].endswith('.png') or re.search('\\.pdf; páginas? \\d+(,\\s?\\d+)*( y COTEJO_FABLE_R3\\.json fila \\d+)?$', a['testigo']), a['testigo'])

    def test_esquema_invalido_y_duplicados_fallan_explicitamente(self):
        a = calidad_textual.cargar()[0]
        for registro in [{'esquema': 2, 'avisos': []}, {'esquema': 1, 'avisos': [a, a]}, {'esquema': 1, 'avisos': [dict(a, paginas_pdf=[0])]}, {'esquema': 1, 'avisos': [dict(a, no_certificado='desconocido')]}]:
            with patch.object(Path, 'read_text', return_value=json.dumps(registro)):
                with self.assertRaises(ValueError):
                    calidad_textual.cargar()

    def test_no_aplica_a_otro_ejemplar_o_ruta_adyacente(self):
        for ident in ['CELEX-31976L0211', 'CELEX-32099R0001']:
            c = memoria('Artículo 1\nObjeto\nTexto sintético.\nArtículo 10\nTexto vecino.', ident)
            self.addCleanup(c.close)
            for sufijo in ['', '::art.1', '::art.10']:
                self.assertNotIn('calidad_textual', consulta.resolver(c, ident + sufijo).dict())

class TestTabla(unittest.TestCase):

    def test_no_basta_la_cabecera_ni_celdas_sueltas_y_rechaza_un_rival(self):
        tabla = {'filas': [['', 'Cabecera común'], ['Índice', 'Valor'], ['1', 'alfa'], ['2', 'beta']]}
        texto = 'Cabecera común Índice Valor alfa beta'
        self.assertTrue(tablas._tabla_con_indices_omitidos(tabla, texto, []))
        self.assertFalse(tablas._tabla_con_indices_omitidos(tabla, 'Cabecera común Índice Valor beta alfa', []))
        self.assertFalse(tablas._tabla_con_indices_omitidos(tabla, 'Cabecera común Índice Valor', []))
        self.assertFalse(tablas._tabla_con_indices_omitidos(tabla, 'Propio ' + texto, ['Otro ' + texto]))
        self.assertTrue(tablas._tabla_con_indices_omitidos(tabla, texto, ['Padre ' + texto]))

@unittest.skipUnless(BASE.is_file(), 'falta base top30 de pruebas')
class TestBase(unittest.TestCase):

    def setUp(self):
        self.c = abrir()
        self.addCleanup(self.c.close)

    def test_tres_avisos_en_cita_y_no_contaminan_el_articulo_vecino(self):
        for ident, tipo, pag in [('CELEX-31976L0211::art.1', 'orden_de_palabras', 2), ('CELEX-31976L0211::anexo.I', 'formula_corrupta', 8), ('BOE-A-1989-5084::anexo.sn', 'formula_omitida', 3)]:
            r = consulta.resolver(self.c, ident)
            self.assertEqual(r.estado, consulta.ENCONTRADO)
            avisos = r.dict().get('calidad_textual', [])
            self.assertTrue(any((a['no_certificado'] == tipo and pag in a['paginas_pdf'] for a in avisos)))
            self.assertIn('CALIDAD TEXTUAL', r.detalle)
            self.assertIn('no certificado', r.naturaleza_del_texto)
        self.assertNotIn('calidad_textual', consulta.resolver(self.c, 'CELEX-31976L0211::art.2').dict())

    def test_cita_texto_y_json_exponen_el_mismo_aviso(self):
        for modo_json in [False, True]:
            con = abrir()
            self.addCleanup(con.close)
            buf = io.StringIO()
            with patch.object(db, 'conectar', return_value=con), redirect_stdout(buf):
                rc = cli.cmd_cita(SimpleNamespace(identificador='CELEX-31976L0211::art.1', ambito=['publico'], json=modo_json))
            self.assertEqual(rc, 0)
            if modo_json:
                self.assertTrue(json.loads(buf.getvalue())['calidad_textual'])
            else:
                self.assertIn('CALIDAD TEXTUAL', buf.getvalue())

    def test_revisar_advierte_incluso_sin_literal_entrecomillado(self):
        r = revision.revisar(self.c, 'Consultar CELEX-31976L0211::art.1 para el análisis.')
        self.assertTrue(any((x.tipo == 'calidad_textual' for x in r.comprobaciones)))

    def test_tabla_art9_10_se_entrega_o_declara_incompleta(self):
        r = consulta.resolver(self.c, 'BOE-A-2007-16478::art.9.10')
        ts = cli._tablas_del_resultado(self.c, r)
        completa = any(([f[0] for f in t['filas'][3:]] == ['1', '2', '3', '4', '5'] for t in ts))
        aviso = any((a['no_certificado'] == 'filas_de_tabla' for a in r.dict().get('calidad_textual', [])))
        self.assertTrue(completa or aviso)

    def test_los_quince_ordinales_incluidos_anexos(self):
        from pruebas.comprobar_ing4 import ORDINALES, consulta_ordinal
        self.assertEqual(len(ORDINALES), 15)
        for obra, contenedor, rotulo in ORDINALES:
            with self.subTest(obra=obra, contenedor=contenedor, rotulo=rotulo):
                r = consulta.resolver(self.c, consulta_ordinal(obra, contenedor, rotulo))
                self.assertEqual(r.estado, consulta.CONTENIDO_EN_ANCESTRO)
                self.assertEqual(r.ambito_localizado, contenedor)
                self.assertIn('LOCALIZADO EN SU CONTENEDOR', r.detalle)
                self.assertIsNone(r.texto_literal)

    def test_ordinal_no_se_localiza_fuera_de_su_punto(self):
        for obra, ruta in [('CELEX-32017R0745', 'anexo.I/ap.23.3.a bis'), ('CELEX-32017R0746', 'anexo.I/ap.20.4.2.a bis'), ('CELEX-32017R0746', 'anexo.XIII/ap.2.3.1.a bis')]:
            r = consulta.resolver(self.c, obra + '::' + ruta)
            self.assertNotEqual(r.estado, consulta.CONTENIDO_EN_ANCESTRO)
MOTOR745 = ROOT / 'tmp/top30_texto_motor/DOUE_Reglamento_UE_2017-745_CELEX-32017R0745_consolidado_es.motor.txt'

@unittest.skipUnless(BASE.is_file() and MOTOR745.is_file(), 'falta base o dump del motor top30')
class TestMotorReal(unittest.TestCase):

    def test_h1_cuerpos_propios_y_mutacion_de_intercambio(self):
        from pruebas.comprobar_ing4 import h1_correspondencia
        raw = MOTOR745.read_text(encoding='utf-8')
        import re
        texto = re.sub('^===== PÁGINA \\d+ =====\\s*$', '', raw, flags=re.M)
        c = memoria(texto, 'CELEX-32017R0745')
        self.addCleanup(c.close)
        self.assertEqual(h1_correspondencia(c), [])
        b, cuerpo_c = [consulta.resolver(c, 'CELEX-32017R0745::art.123.3.' + l).texto_literal for l in 'bc']
        for letra, nuevo in [('b', 'b) ' + cuerpo_c[3:]), ('c', 'c) ' + b[3:])]:
            c.execute('UPDATE precepto SET texto_literal=? WHERE ruta_estructural=?', (nuevo, 'art.123.3.' + letra))
        errores = h1_correspondencia(c)
        self.assertEqual({e.split(': ')[0] for e in errores}, {'CELEX-32017R0745::art.123.3.b', 'CELEX-32017R0745::art.123.3.c'})
        self.assertTrue(ec.comprobar_norma(raw, ec.filas_version(c, 1), criterio='calibrado', identificador='CELEX-32017R0745')['correcta'])
if __name__ == '__main__':
    unittest.main()
