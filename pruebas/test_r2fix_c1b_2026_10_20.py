"""C1B: las filas de magnitudes del motor no son apartados inexistentes."""
import unittest

from pruebas import estructura_completa_top30 as censo


class TestC1B(unittest.TestCase):
    def censar(self, *lineas):
        texto = '\n'.join(['TEXTO CONSOLIDADO', 'ITC-BT-52',
                           'INSTALACIONES DE RECARGA', *lineas])
        return censo.censo_calibrado(texto, 'boe')

    def test_potencias_reales_bt52_no_son_apartados(self):
        # BOE-A-2002-18099, motor pp. 279 y 282: dos filas breves.
        for fila in ('13.856 W 22.170 W',
                     '11.085 W 22.170 W 34.641 W 43.647 W'):
            with self.subTest(fila=fila):
                hs, pendientes, fuera = self.censar('1. POTENCIA', fila,
                                                   '2. PROTECCIÓN', 'Texto de protección.')
                self.assertEqual({h.ruta for h in hs},
                                 {'itc.BT-52', 'itc.BT-52/ap.1', 'itc.BT-52/ap.2'})
                self.assertFalse(pendientes)
                self.assertFalse(fuera)

    def test_fila_de_magnitudes_no_se_fragmenta_como_epigrafes(self):
        fila = '13.856 W 22.170 W'
        self.assertEqual(censo._fragmentos_inline(fila), [fila])

    def test_otras_unidades_y_decimales_sinteticos(self):
        for fila in ('1.500 kW 2.250 kW', '1.250 mm 2.500 mm',
                     '1,5 kW 2,25 kW', '230 V 400 V', '20 A 32 A'):
            with self.subTest(fila=fila):
                hs, pendientes, fuera = self.censar('1. CAMPO', fila,
                                                   '2. MEDIDAS', 'Texto.')
                self.assertEqual(len(hs), 3)
                self.assertFalse(pendientes)
                self.assertFalse(fuera)

    def test_apartado_real_con_magnitudes_sigue_siendo_exigible(self):
        hs, pendientes, fuera = self.censar('1. POTENCIA', '1.1 Valores de 13.856 W y 22.170 W.',
                                           '2. PROTECCIÓN', 'Texto.')
        self.assertIn('itc.BT-52/ap.1.1', {h.ruta for h in hs})
        comparacion = censo.comparar(hs, [])
        self.assertIn('itc.BT-52/ap.1.1', {h['ruta'] for h in comparacion['faltantes']})

    def test_no_se_descarta_prosa_tras_una_unidad(self):
        hs, _, _ = self.censar('1. CAMPO', '2.250 W previstos para la instalación.')
        self.assertIn('itc.BT-52/ap.2.250', {h.ruta for h in hs})


if __name__ == '__main__':
    unittest.main()
