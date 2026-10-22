"""Public CI documentation."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ict155 import catalogo, caracter, calidad_textual, config, consulta, ingesta
REPO = Path(__file__).resolve().parents[1]
IDS = {'CELEX-31987R2658', 'CELEX-32008R1272', 'CELEX-32006R1907'}

def alta():
    return json.loads((REPO / 'datos/alta_r2.json').read_text(encoding='utf-8'))

class TestR2Sin3(unittest.TestCase):

    def test_28_activas_y_tres_aplazadas_con_trazabilidad(self):
        d = alta()
        self.assertEqual(len(d['normas']), 28)
        self.assertEqual({r['identificador'] for r in d['aplazadas']}, IDS)
        self.assertFalse(IDS & {r['identificador'] for r in d['normas']})
        for r in d['aplazadas']:
            self.assertEqual(r['estado'], 'APLAZADA')
            self.assertEqual(r['version_excluida'], 'v2-A')
            self.assertTrue(r['motivo_aplazamiento'])
            self.assertEqual(len(r['sha256_pdf']), 64)
            self.assertTrue(catalogo.aplazado(r['ruta_relativa']))
            self.assertFalse(catalogo.en_nucleo(r['ruta_relativa']))
            self.assertNotIn(r['nombre'], catalogo.ALIAS)
            self.assertNotIn(r['identificador'], catalogo.TITULOS_OFICIALES)
            self.assertNotIn(r['identificador'], caracter.TABLA)
            self.assertNotIn(r['ruta_relativa'], catalogo.METADATOS_POR_DOCUMENTO)
        for r in d['normas']:
            self.assertFalse(catalogo.aplazado(r['ruta_relativa']))
            self.assertTrue(catalogo.en_nucleo(r['ruta_relativa']))

    def test_censo_no_incluye_aplazadas_aunque_reaparezcan_los_pdf(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for r in alta().get('aplazadas', []) + alta()['normas'][:1]:
                p = root / r['ruta_relativa']
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            with patch.object(config, 'BIBLIOTECA', root):
                self.assertEqual(ingesta.documentos_biblioteca(), [alta()['normas'][0]['ruta_relativa']])

    def test_ingesta_directa_no_abre_ni_registra_una_aplazada(self):
        for r in alta().get('aplazadas', []):
            with self.subTest(obra=r['identificador']), patch.object(ingesta.extraccion, 'extraer', side_effect=AssertionError('No leer PDF')), patch.object(ingesta, '_insert_documento', side_effect=AssertionError('No registrar')):
                result = ingesta.ingerir_documento(None, r['ruta_relativa'])
                self.assertEqual(result['estado'], 'aplazado_v2a')
                self.assertEqual(result['preceptos'], 0)

    def test_identificadores_y_alias_responden_como_norma_ausente(self):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        con.executescript((REPO / 'ict155/esquema.sql').read_text(encoding='utf-8'))
        control = consulta.resolver(con, 'CELEX-39999R9999::art.1')
        self.assertEqual(control.estado, consulta.NO_CONSTA)
        for r in alta().get('aplazadas', []):
            for name in [r['identificador'], *r['alias']]:
                for suffix in ('', '::art.1', '::anexo.I/ap.1'):
                    with self.subTest(nombre=name, ruta=suffix):
                        result = consulta.resolver(con, name + suffix)
                        self.assertEqual(result.estado, control.estado)
                        self.assertTrue(result.detalle)
                        self.assertFalse(result.texto_literal)
                        self.assertFalse(result.calidad_textual)
        con.execute("INSERT INTO obra(id,identificador_canonico,tipo,titulo,jurisdiccion) VALUES(1,'CELEX-39999R0001','eurlex','Sintética','UE')")
        con.execute("INSERT INTO documento(id,ruta_relativa,sha256,bytes,mtime_utc,clase_derechos,estado_ingesta) VALUES(1,'sintetico.pdf','sintetico',0,'2099-01-01','publico','ingerido')")
        con.execute("INSERT INTO version(id,obra_id,documento_id,etiqueta,idioma) VALUES(1,1,1,'sintética','es')")
        con.execute("INSERT INTO precepto(version_id,ruta_estructural,tipo_unidad,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES(1,'art.1','articulo','Artículo 1','Texto sintético.',1,1,1)")
        result = consulta.resolver(con, 'CELEX-39999R0001::art.1')
        self.assertEqual(result.estado, consulta.ENCONTRADO)
        self.assertEqual(result.texto_literal, 'Texto sintético.')

    def test_avisos_apartados_se_conservan_sin_publicarse(self):
        activos = calidad_textual.cargar()
        self.assertFalse(IDS & {a['obra'] for a in activos})
        archivo = json.loads((REPO / 'datos/calidad_textual_aplazadas_v2a.json').read_text(encoding='utf-8'))
        self.assertEqual({a['obra'] for a in archivo['avisos']}, IDS)
        self.assertTrue(archivo['avisos'])
if __name__ == '__main__':
    unittest.main()
