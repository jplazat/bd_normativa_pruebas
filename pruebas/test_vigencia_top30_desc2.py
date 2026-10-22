"""Public CI documentation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ict155 import vigencia as v

class VigenciaTop30(unittest.TestCase):

    def test_21_y_limites(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'pruebas') as t:
            with patch.object(v.config, 'BD', Path(t) / 'conocimiento.sqlite'):
                datos = v.instantanea_actual()
        self.assertEqual(len(datos['obras']), 123)
        top30 = json.loads((Path(__file__).resolve().parents[1] / 'datos' / 'vigencia_top30.json').read_text(encoding='utf-8'))
        top30 = top30.get('obras', top30)
        sub = [datos['obras'][k] for k in (top30.keys() if isinstance(top30, dict) else [x.get('identificador') or x.get('obra') for x in top30])]
        self.assertEqual(len(sub), 21)
        self.assertEqual(sum((x['consulta']['estado'] == 'vigente' for x in sub)), 8)
        self.assertEqual(sum((x['consulta']['estado'] is None for x in sub)), 12)
        o = v.vigencia_de('BOE-A-1989-5084', datos)
        self.assertEqual(o['estado'], 'derogada')
        self.assertEqual(o['fecha_derogacion'], '2015-12-01')
        ue = v.vigencia_de('CELEX-32017R0745', datos)
        self.assertIsNone(ue['estado'])
        self.assertIsNone(ue['fuente'])
        self.assertIn('cabeceras', ' '.join(ue['avisos']))
        boe = v.vigencia_de('BOE-A-2020-15872', datos)
        self.assertIn('análisis de modificaciones', ' '.join(boe['avisos']))
        self.assertEqual(boe['consultado'], '2026-10-19')
        self.assertIn('actualizarla', ' '.join(v.vigencia_de('BOE-A-2020-15872', datos, hoy='2027-01-01')['avisos']))
        self.assertIsNone(v.vigencia_de('BOE-A-2999-999', datos)['estado'])
        self.assertIsNone(v.vigencia_de('UNE-EN-12830', datos))

    def test_explicita_y_precedencia(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'pruebas') as t:
            p = Path(t) / 'vigencia.json'
            self.assertIsNone(v.instantanea_actual(p))
            original = {'consultado': '2026-10-20', 'obras': {'BOE-A-2020-15872': {'consulta': {'estado': None}}}}
            p.write_text(json.dumps(original), encoding='utf-8')
            self.assertEqual(v.instantanea_actual(p), original)
            with patch.object(v.config, 'BD', Path(t) / 'conocimiento.sqlite'):
                self.assertEqual(v.instantanea_actual()['obras']['BOE-A-2020-15872'], original['obras']['BOE-A-2020-15872'])
            self.assertEqual(json.loads(p.read_text()), original)
if __name__ == '__main__':
    unittest.main()
