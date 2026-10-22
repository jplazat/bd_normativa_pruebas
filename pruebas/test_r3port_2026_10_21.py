"""Portabilidad por ejemplar: datos y cuerpos sintéticos, sin bases instaladas."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ict155 import alcance_r3, config, estructura_r3b, extraccion


def limpiar_registros():
    for fun in (alcance_r3.altas, getattr(alcance_r3, '_registro', None),
                alcance_r3.perfiles, estructura_r3b._por_ejemplar):
        if hasattr(fun, 'cache_clear'):
            fun.cache_clear()


class TestPortabilidadR3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ICT155_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.datos = self.root/'datos'
        self.datos.mkdir()
        self.ns = [dict(identificador=ident, ruta_relativa=ident+'.pdf',
                        sha256_pdf=hashlib.sha256(ident.encode()).hexdigest())
                   for ident in sorted(estructura_r3b.OBRAS | {'CELEX-32005R0396'})]
        (self.datos/'alta_r3.json').write_text(json.dumps(dict(normas=self.ns)), encoding='utf-8')
        (self.datos/'alcance_r3.json').write_text(json.dumps(dict(perfiles={
            'CELEX-32005R0396': dict(anexos=['I'])})), encoding='utf-8')
        self.lib = self.root/'biblioteca_con_otro_nombre'
        self.crear_lib(self.lib)
        self.addCleanup(limpiar_registros)
        limpiar_registros()
        for campo, valor in (('DATOS_REPO', self.datos), ('BIBLIOTECA', self.lib),
                             ('REPO', self.root/'wt/r3port')):
            ctx = patch.object(config, campo, valor)
            ctx.start()
            self.addCleanup(ctx.stop)

    def crear_lib(self, lib):
        lib.mkdir()
        for n in self.ns:
            (lib/n['ruta_relativa']).write_bytes(n['identificador'].encode())

    def comprobar_activas(self):
        for n in self.ns:
            with self.subTest(obra=n['identificador']):
                self.assertTrue(alcance_r3.activa(n['ruta_relativa']))
                self.assertEqual(estructura_r3b.identidad(n['ruta_relativa'], n['sha256_pdf']),
                                 n['identificador'] if n['identificador'] in estructura_r3b.OBRAS else None)
        n = next(n for n in self.ns if n['identificador']=='CELEX-32005R0396')
        pdf = extraccion.TextoPdf(n['ruta_relativa'], sha256=n['sha256_pdf'],
                                 paginas=['Artículo 1\nRegla sintética.', 'ANEXO I\nElegido.', 'ANEXO II\nFuera.'])
        self.assertEqual(alcance_r3.para_trocear(pdf).paginas, pdf.paginas[:2]+[''])

    def test_otro_nombre_activa_perfil_y_las_seis_reparaciones(self):
        self.comprobar_activas()
        original = self.root/'biblioteca_r3'
        self.crear_lib(original)
        with patch.object(config, 'BIBLIOTECA', original):
            self.comprobar_activas()

    def test_nombre_original_no_activa_alterado_ni_ausente(self):
        original = self.root/'biblioteca_r3'
        self.crear_lib(original)
        with patch.object(config, 'BIBLIOTECA', original):
            for n in self.ns:
                path = original/n['ruta_relativa']
                data = path.read_bytes()
                self.assertTrue(alcance_r3.activa(n['ruta_relativa']))
                # Mismo tamaño: la invalidación no puede depender solo del tamaño.
                path.write_bytes(bytes([data[0]^1])+data[1:])
                self.assertFalse(alcance_r3.activa(n['ruta_relativa']))
                self.assertIsNone(estructura_r3b.identidad(n['ruta_relativa'], n['sha256_pdf']))
                pdf = extraccion.TextoPdf(n['ruta_relativa'], paginas=['Sin anexos.'], sha256=n['sha256_pdf'])
                self.assertIs(alcance_r3.para_trocear(pdf), pdf)
                with patch.object(extraccion, '_paginas_de_xpdf') as raw:
                    self.assertEqual(extraccion._orden_paginas_r3b(path, n['ruta_relativa'], pdf.paginas, 1), (pdf.paginas, ''))
                    raw.assert_not_called()
                path.unlink()
                self.assertFalse(alcance_r3.activa(n['ruta_relativa']))
                self.assertIsNone(estructura_r3b.identidad(n['ruta_relativa'], n['sha256_pdf']))
                self.assertIs(alcance_r3.para_trocear(pdf), pdf)
                self.assertEqual(extraccion._orden_paginas_r3b(path, n['ruta_relativa'], pdf.paginas, 1), (pdf.paginas, ''))
                # Una ausencia previa no debe quedar memorizada al aparecer el PDF.
                path.write_bytes(data)
                self.assertTrue(alcance_r3.activa(n['ruta_relativa']))

    def test_huella_compartida_una_lectura_por_fichero_y_version(self):
        n = self.ns[0]
        path = self.lib/n['ruta_relativa']
        with patch.object(config, 'abrir_biblioteca', wraps=config.abrir_biblioteca) as abrir:
            for _ in range(3):
                self.assertTrue(alcance_r3.activa(n['ruta_relativa']))
                self.assertEqual(extraccion.sha256_fichero(path), n['sha256_pdf'])
                self.assertEqual(estructura_r3b.identidad(n['ruta_relativa'], n['sha256_pdf']), n['identificador'])
            self.assertEqual(abrir.call_count, 1)
            path.write_bytes(path.read_bytes()+b'x')
            self.assertFalse(alcance_r3.activa(n['ruta_relativa']))
            self.assertEqual(abrir.call_count, 2)

    def test_ruta_no_registrada_y_huella_del_llamador_incorrecta(self):
        with patch.object(config, 'abrir_biblioteca') as abrir:
            self.assertFalse(alcance_r3.activa('fuera.pdf'))
            self.assertFalse(alcance_r3.activa('../fuera.pdf'))
            abrir.assert_not_called()
        n = self.ns[0]
        self.assertIsNone(estructura_r3b.identidad(n['ruta_relativa'], 'f'*64))


if __name__ == '__main__':
    unittest.main()
