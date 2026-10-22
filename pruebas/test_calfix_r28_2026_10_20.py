"""Public CI documentation."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ict155 import calidad_textual, cli, config, consulta, db, interruptores, vigencia
from cowork import servidor_mcp as servidor
TEXTO = 'Texto enteramente inventado para la prueba de calidad.'
HUELLA = 'a' * 64

def aviso():
    return dict(obra='SINTETICA-CON-AVISO', ruta='art.1', sha256_pdf=HUELLA, localizacion='Página sintética 1', detalle='Fórmula inventada sin certificar', testigo='sintetico.png', no_certificado='formula_omitida', paginas_pdf=[1])

class TestCalfix(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='calfix_')
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.registro = self.raiz / 'calidad_textual.json'
        entorno = {k: v for k, v in os.environ.items() if not k.startswith(('ICT155_CONTROLES', 'ICT155_COWORK', 'ICT155_ALMACEN', 'ICT155_HECHOS'))}
        entorno.update(LOCALAPPDATA=str(self.raiz / 'local'), ICT155_DATOS=str(self.raiz / 'bd'), ICT155_BIBLIOTECA=str(self.raiz / 'biblioteca'))
        self.enterContext(patch.dict(os.environ, entorno, clear=True))
        for nombre, valor in dict(DATOS_REPO=self.raiz, BD=self.raiz / 'bd/conocimiento.sqlite', DIR_DATOS=self.raiz / 'bd', BIBLIOTECA=self.raiz / 'biblioteca').items():
            self.enterContext(patch.object(config, nombre, valor))
        controles = self.raiz / 'controles.json'
        controles.write_text(json.dumps({'controles': dict.fromkeys(interruptores.CONTROLES_CONOCIDOS, 'apagado')}), encoding='utf-8')
        self.enterContext(patch.object(interruptores, 'RUTA_CONTROLES', controles))
        self.enterContext(patch.object(cli, '_salida_utf8', lambda: None))
        limites = self.raiz / 'limites.json'
        limites.write_text('{"preceptos":[],"generales":[]}', encoding='utf-8')
        self.enterContext(patch.object(servidor, 'LIMITES_JSON', str(limites)))
        self.enterContext(patch.object(servidor, 'audit'))
        self.con = sqlite3.connect(':memory:')
        self.addCleanup(self.con.close)
        self.con.row_factory = sqlite3.Row
        self.con.executescript((Path(consulta.__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
        for i, nombre in enumerate(('SINTETICA-AJENA', 'SINTETICA-CON-AVISO'), 1):
            self.con.execute("INSERT INTO documento(id,ruta_relativa,sha256,bytes,mtime_utc,paginas,clase_derechos,estado_ingesta) VALUES(?,?,?,1,'2026-01-01',1,'publico','ingerido')", (i, f'sintetico{i}.pdf', HUELLA))
            self.con.execute("INSERT INTO obra(id,identificador_canonico,tipo,titulo,jurisdiccion) VALUES(?,?,'guia','Obra inventada','OTRA')", (i, nombre))
            self.con.execute("INSERT INTO version(id,obra_id,documento_id,etiqueta,idioma) VALUES(?,?,?,'2026','es')", (i, i, i))
            self.con.execute("INSERT INTO precepto(version_id,ruta_estructural,tipo_unidad,etiqueta_humana,texto_literal,pagina_inicio,pagina_fin,orden) VALUES(?,'art.1','articulo','Artículo 1',?,1,1,1)", (i, TEXTO))
        self.con.execute("INSERT INTO ingesta(ejecutada_en,git_commit,n_documentos,n_versiones,n_preceptos,huella_contenido) VALUES('2026-01-01T00:00:00Z','SINTETICO',2,2,2,'HUELLA_SINTETICA')")
        self.con.commit()
        self.con.execute('PRAGMA query_only=ON')
        self.assertEqual(self.con.execute('PRAGMA query_only').fetchone()[0], 1)
        self.enterContext(patch.object(db, 'conectar', return_value=self.con))
        self.escribir_registro()

    def escribir_registro(self, datos=None, encoding='utf-8'):
        self.registro.write_text(json.dumps(datos if datos is not None else {'esquema': 1, 'avisos': [aviso()]}), encoding=encoding)

    def cli(self, argumentos):
        out, err = (io.StringIO(), io.StringIO())
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argumentos)
        return (rc, out.getvalue(), err.getvalue())

    def orden(self, comando, obra, formato_json=True):
        args = [comando, obra + '::art.1']
        if comando == 'cotejar':
            args.append(TEXTO)
        return args + (['--json'] if formato_json else [])

    def romper(self, estado):
        self.registro.unlink(missing_ok=True)
        if estado == 'roto':
            self.registro.write_text('{', encoding='utf-8')
        elif estado == 'esquema':
            self.registro.write_text('{}', encoding='utf-8')
        elif estado == 'codificacion':
            self.registro.write_bytes(b'\xff')

    def test_obra_ajena_registro_ausente_roto_esquema_y_codificacion(self):
        for estado in ('ausente', 'roto', 'esquema', 'codificacion'):
            self.romper(estado)
            for comando in ('cita', 'cotejar'):
                for formato_json in (False, True):
                    with self.subTest(estado=estado, comando=comando, json=formato_json):
                        rc, out, err = self.cli(self.orden(comando, 'SINTETICA-AJENA', formato_json))
                        self.assertEqual(rc, 2)
                        self.assertEqual(out, '')
                        self.assertIn('calidad', err.lower())
                        self.assertIn('calidad_textual', err)
                        self.assertNotIn('Traceback', err)

    def test_bom_equivale_a_utf8_para_obra_ajena_en_ambas_ordenes(self):
        antes = [self.cli(self.orden(c, 'SINTETICA-AJENA')) for c in ('cita', 'cotejar')]
        self.escribir_registro(encoding='utf-8-sig')
        despues = [self.cli(self.orden(c, 'SINTETICA-AJENA')) for c in ('cita', 'cotejar')]
        self.assertEqual(antes, despues)
        self.assertTrue(all((rc == 0 and (not err) for rc, _, err in despues)))
        self.assertNotIn('calidad_textual', json.loads(despues[0][1]))

    def test_obra_con_aviso_bom_no_pierde_advertencias_y_roto_falla_cerrado(self):
        for encoding in ('utf-8', 'utf-8-sig'):
            self.escribir_registro(encoding=encoding)
            rc, out, err = self.cli(self.orden('cita', 'SINTETICA-CON-AVISO'))
            self.assertEqual((rc, err), (0, ''))
            d = json.loads(out)
            self.assertEqual(d['calidad_textual'][0]['detalle'], aviso()['detalle'])
            self.assertIn('AVISO DE CALIDAD TEXTUAL', d['detalle'])
            for estado in ('ausente', 'roto', 'esquema'):
                self.romper(estado)
                for comando in ('cita', 'cotejar'):
                    with self.subTest(encoding=encoding, estado=estado, comando=comando):
                        rc, out, err = self.cli(self.orden(comando, 'SINTETICA-CON-AVISO'))
                        self.assertEqual(rc, 2)
                        self.assertEqual(out, '')
                        self.assertIn('calidad_textual', err)
                        self.assertNotIn('Traceback', err)

    def test_lector_expone_excepcion_propia_para_lectura_y_validacion(self):
        error = getattr(calidad_textual, 'ErrorDeCalidad', None)
        self.assertIsNotNone(error)
        for estado in ('ausente', 'roto', 'esquema', 'codificacion'):
            self.romper(estado)
            with self.subTest(estado=estado), self.assertRaises(error):
                calidad_textual.cargar()
        malos = [[], {'esquema': 2, 'avisos': []}, {'esquema': True, 'avisos': []}, {'esquema': 1, 'avisos': [None]}, {'esquema': 1, 'avisos': [dict(aviso(), obra='')]}, {'esquema': 1, 'avisos': [dict(aviso(), no_certificado=[])]}, {'esquema': 1, 'avisos': [dict(aviso(), paginas_pdf=[0])]}, {'esquema': 1, 'avisos': [aviso(), aviso()]}]
        for registro in malos:
            self.escribir_registro(registro)
            with self.subTest(registro=registro), self.assertRaises(error):
                calidad_textual.cargar()
        with patch.object(Path, 'read_text', side_effect=PermissionError('denegado')):
            with self.assertRaises(error):
                calidad_textual.cargar()

    def test_cowork_usa_cli_real_y_devuelve_iserror_para_ambas_obras_y_ordenes(self):
        with patch.object(servidor, 'ejecutar', side_effect=lambda args, entrada=None: self.cli(args)):
            for estado in ('ausente', 'roto', 'esquema'):
                self.romper(estado)
                for obra in ('SINTETICA-AJENA', 'SINTETICA-CON-AVISO'):
                    for comando in ('cita', 'cotejar'):
                        args = {'identificador': obra + '::art.1'}
                        if comando == 'cotejar':
                            args['afirmacion'] = TEXTO
                        with self.subTest(estado=estado, obra=obra, comando=comando):
                            r = servidor.call_tool('normativa_' + comando, args)
                            self.assertTrue(r['isError'])
                            texto = r['content'][0]['text']
                            self.assertIn('rc=2', texto)
                            self.assertIn('calidad_textual', texto)
                            self.assertNotIn('Traceback', texto)

    def test_info_y_cowork_solo_cambian_linea_vigencia_sin_fecha(self):
        for consultado in (None, ''):
            datos = {'consultado': consultado, 'obras': {'SINTETICA': {}}}
            with patch.object(vigencia, 'instantanea_actual', return_value=datos):
                rc, salida, err = self.cli(['info'])
            self.assertEqual((rc, err), (0, ''))
            linea = next((l for l in salida.splitlines() if l.startswith('vigencia :')))
            self.assertEqual(linea, 'vigencia : complemento sin fecha de consulta (BOE y CELLAR), 1 normas')
            self.assertNotIn('None', salida)
            with patch.object(servidor, 'ejecutar', return_value=(rc, salida, err)):
                r = servidor.call_tool('normativa_estado', {})
            self.assertFalse(r['isError'])
            self.assertEqual(r['content'][0]['text'], salida.strip())
            with patch.object(vigencia, 'instantanea_actual', return_value={**datos, 'consultado': '2026-10-20'}):
                _, fechada, _ = self.cli(['info'])
            self.assertEqual([l for l in salida.splitlines() if not l.startswith('vigencia :')], [l for l in fechada.splitlines() if not l.startswith('vigencia :')])
            self.assertIn('vigencia : consultada 2026-10-20 (BOE y CELLAR), 1 normas', fechada)
        with patch.object(vigencia, 'instantanea_actual', return_value=None):
            self.assertIn('vigencia : SIN CONSULTAR (ict155.cli vigencia --actualizar)', self.cli(['info'])[1])
if __name__ == '__main__':
    unittest.main()
