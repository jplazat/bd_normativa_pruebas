"""Public CI documentation."""
from collections import Counter
from contextlib import contextmanager
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from pruebas import soporte_h34_r28_2026_10_21 as soporte
from pruebas.soporte_h34_r28_2026_10_21 import ANTIGUO, PUBLICADO, almacen, escribir_json, interruptores

@contextmanager
def contar_contenido():
    cuentas = Counter()
    abrir = io.open

    def registrar(ruta, *args, **kwargs):
        cuentas[Path(ruta)] += 1
        return abrir(ruta, *args, **kwargs)
    with patch.object(io, 'open', registrar):
        yield cuentas

class CacheH34B(unittest.TestCase):
    setUp = soporte.H3.setUp
    bajar = soporte.H3.bajar

    def test_coste_estable_y_tras_bajada_solo_relee_local(self):
        self.bajar('sombra')
        aprobados, local = (interruptores.RUTA_CONTROLES, interruptores.ruta_local())
        with contar_contenido() as cuentas:
            for _ in range(12):
                self.assertEqual(almacen.leer(self.ruta), ANTIGUO)
            self.assertEqual((cuentas[aprobados], cuentas[local]), (1, 1))
            self.bajar('apagado')
            cuentas.clear()
            with patch.object(almacen, '_publicada', side_effect=AssertionError('apagado')):
                for _ in range(12):
                    self.assertEqual(almacen.leer(self.ruta), ANTIGUO)
            self.assertEqual((cuentas[aprobados], cuentas[local]), (0, 1))
            self.assertEqual(cuentas[self.ruta], 12)

    def test_local_in_situ_mismo_tamano_y_mtime_invalida(self):
        self.bajar('sombra')
        self.assertEqual(almacen.modo_para(self.ruta), 'sombra')
        local = interruptores.ruta_local()
        antes = local.stat()
        bruto = local.read_bytes().replace(b'"sombra"', b'"activo"')
        local.write_bytes(bruto)
        os.utime(local, ns=(antes.st_atime_ns, antes.st_mtime_ns))
        self.assertEqual((local.stat().st_size, local.stat().st_mtime_ns), (antes.st_size, antes.st_mtime_ns))
        with contar_contenido() as cuentas:
            for _ in range(12):
                self.assertEqual(almacen.modo_para(self.ruta), 'activo')
            self.assertEqual(cuentas[local], 1)
            self.assertEqual(cuentas[interruptores.RUTA_CONTROLES], 0)

    def test_reemplazo_aprobados_mismo_tamano_y_mtime_invalida(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        ruta = interruptores.RUTA_CONTROLES
        antes = ruta.stat()
        temporal = ruta.with_suffix('.reemplazo')
        temporal.write_bytes(ruta.read_bytes().replace(b'"activo"', b'"sombra"'))
        os.utime(temporal, ns=(antes.st_atime_ns, antes.st_mtime_ns))
        os.replace(temporal, ruta)
        with contar_contenido() as cuentas:
            for _ in range(12):
                self.assertEqual(almacen.modo_para(self.ruta), 'sombra')
            self.assertEqual(cuentas[ruta], 1)

    def test_aprobados_ausentes_no_reutilizan_cache_y_se_recuperan(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        ruta = interruptores.RUTA_CONTROLES
        ruta.unlink()
        for _ in range(2):
            with self.assertRaises(interruptores.ErrorDeControles):
                almacen.leer(self.ruta)
        escribir_json(ruta, {'controles': {'almacen_unico': 'apagado'}})
        self.assertEqual(almacen.leer(self.ruta), ANTIGUO)

    def test_error_metadatos_relee_y_no_conserva_modo_viejo(self):
        self.assertEqual(almacen.leer(self.ruta), PUBLICADO)
        self.bajar('apagado')
        with patch.object(almacen, '_identidad_control', side_effect=OSError('sintético')):
            self.assertEqual(almacen.leer(self.ruta), ANTIGUO)
        self.assertEqual(almacen.leer(self.ruta), ANTIGUO)

    def test_escritura_durante_lectura_no_guarda_identidad_vieja(self):
        original = interruptores._aprobados
        ruta = interruptores.RUTA_CONTROLES
        llamadas = []

        def cambiar(p):
            dato = original(p)
            llamadas.append(p)
            if len(llamadas) == 1:
                escribir_json(ruta, {'controles': {'almacen_unico': 'apagado'}})
            return dato
        with patch.object(interruptores, '_aprobados', cambiar):
            self.assertEqual(almacen.modo_para(self.ruta), 'apagado')
        self.assertEqual(len(llamadas), 2)
if __name__ == '__main__':
    unittest.main()
