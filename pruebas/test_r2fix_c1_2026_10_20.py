"""Public CI documentation."""
import unittest
from ict155 import parsers
from ict155.extraccion import TextoPdf
from pruebas import estructura_completa_top30 as censo

def analizar(*lineas):
    pdf = TextoPdf('publico_sintetico.pdf', paginas=['\n'.join(['Referencia: BOE-A-2099-1', 'Norma de prueba', 'TEXTO CONSOLIDADO', *lineas])])
    return {p.ruta: p for p in parsers.analizar('boe', pdf).preceptos}

class TestC1(unittest.TestCase):

    def test_capitulo_preliminar_fuera_del_preambulo(self):
        ps = analizar('Exposición de motivos.', 'CAPÍTULO PRELIMINAR', 'Disposiciones generales', 'Artículo 1. Objeto.', 'Texto del objeto.')
        self.assertIn('capitulo.preliminar', ps)
        self.assertNotIn('CAPÍTULO PRELIMINAR', ps['preambulo'].texto)
        self.assertIn('Disposiciones generales', ps['capitulo.preliminar'].texto)

    def test_rebt_rubrica_del_cuerpo_prevalece(self):
        ps = analizar('INSTRUCCIÓN ZZ-03', 'EMPRESAS INSTALADORAS', 'ÍNDICE', '1. OBJETO', '2. INSTALADORES AUTORIZADOS', '3. CLASIFICACIÓN DE LOS INSTALADORES AUTORIZADOS', '1. OBJETO', 'Texto del objeto.', '2. EMPRESA INSTALADORA E INSTALADOR EN BAJA TENSIÓN.', '2.1 Empresa instaladora en baja tensión es la persona física o jurídica', '3. CLASIFICACIÓN DE LAS EMPRESAS INSTALADORAS EN BAJA TENSIÓN.', 'Texto de clasificación.')
        self.assertEqual(ps['itc.ZZ-03/ap.2'].padre, 'itc.ZZ-03')
        self.assertEqual(ps['itc.ZZ-03/ap.2.1'].padre, 'itc.ZZ-03/ap.2')
        self.assertIn('Texto de clasificación.', ps['itc.ZZ-03/ap.3'].texto)
        self.assertNotIn('INSTALADORES AUTORIZADOS', ps['itc.ZZ-03/ap.2'].texto)

    def test_articulo_primer_apartado_pegado_y_segundo_pegado(self):
        ps = analizar('Artículo 26. Calidad global. 1. Los indicadores de medida de la calidad global de la red de transporte son la energía', 'a) Energía no suministrada (ENS), que mide la energía cortada al sistema (MWh)', 'b) Tiempo de interrupción medio (TIM).', 'c) La disponibilidad de una red se expresa por el porcentaje del tiempo total.', 'Se aplica el progreso tecnológico. 2. Los valores del ENS, TIM, e ID de referencia serán los siguientes:', '3. El operador del sistema y gestor de la red de transporte será responsable.')
        self.assertIn('art.26.1', ps)
        self.assertIn('art.26.2', ps)
        self.assertIn('art.26.3', ps)
        self.assertEqual(ps['art.26.1.a'].padre, 'art.26.1')
        self.assertNotIn('art.26.a', ps)
        self.assertNotIn('2. Los valores', ps['art.26.1'].texto)

    def test_articulo_prefijado_y_derogados_pegados(self):
        ps = analizar('Artículo 3. Infracciones en materia de protección al consumidor. 3.1 Son infracciones por alteración, adulteración o fraude en bienes y servicios', '3.1.1 La elaboración, distribución, suministro o venta de bienes', '3.1.2 La elaboración, distribución, suministro o venta de bienes', '3.1.4 (Derogado) 3.1.5 (Derogado) 3.2 (Derogado) 3.3 (Derogado)')
        self.assertEqual(ps['art.3.2'].texto, '3.2 (Derogado)')
        self.assertEqual(ps['art.3.3'].texto, '3.3 (Derogado)')
        self.assertIn('3.1.5 (Derogado)', ps['art.3.1'].texto)
        self.assertNotIn('art.3.1.2', ps)

    def test_lista_interior_no_es_otro_apartado_de_itc(self):
        ps = analizar('INSTRUCCIÓN ZZ-14', 'ACTUACIONES', 'ÍNDICE', '1. Obligaciones.', '2. Registro.', '1. Obligaciones.', '1.1 Avisos.', 'Pasos: 1. Avisar. 2. Informar al personal. 3. Aislar componentes.', '2. Registro.', 'Texto del registro.')
        self.assertIn('2. Informar al personal.', ps['itc.ZZ-14/ap.1.1'].texto)
        self.assertEqual(ps['itc.ZZ-14/ap.2'].titulo, 'Registro.')
        self.assertNotIn('itc.ZZ-14/ap.3', ps)

    def test_apartado_suprimido_no_interrumpe_la_secuencia(self):
        ps = analizar('INSTRUCCIÓN ZZ-03 ACTUACIONES', 'ÍNDICE', '1. OBJETO', '2. ACTIVIDADES', '3. OBLIGACIONES', '1. OBJETO', 'Texto inicial.', '2. (Suprimido)', '3. OBLIGACIONES NUEVAS', 'Texto final.')
        self.assertEqual(ps['itc.ZZ-03/ap.2'].texto, '2. (Suprimido)')
        self.assertEqual(ps['itc.ZZ-03/ap.3'].texto, '3. OBLIGACIONES NUEVAS Texto final.')

    def test_remision_no_crea_primer_apartado(self):
        ps = analizar('Artículo 8. Objeto.', 'Se remite al apartado 1. Los criterios se fijan en otra norma.', 'Texto sin enumeración.', 'Artículo 9. Condiciones.', 'Texto general.')
        self.assertNotIn('art.8.1', ps)

    def test_remision_no_crea_primero_aunque_haya_un_tercero(self):
        ps = analizar('Artículo 8. Objeto.', 'Se remite al apartado 1. Los criterios están en otra norma.', '3. Este rótulo aislado no demuestra un apartado primero propio.')
        self.assertNotIn('art.8.1', ps)

    def test_capitulo_preliminar_en_remision_es_texto(self):
        ps = analizar('Artículo 1. Objeto.', 'El CAPÍTULO PRELIMINAR contiene las disposiciones generales.', 'capítulo preliminar de otra norma.', 'Artículo 2. Definición.', 'Texto de definición.')
        self.assertNotIn('capitulo.preliminar', ps)

    def test_indice_numerado_no_es_un_apartado_ni_un_aviso(self):
        text = '\n'.join(['TEXTO CONSOLIDADO', 'ITC-BT-31', 'INSTALACIONES CON FINES ESPECIALES. PISCINAS Y FUENTES', '0. ÍNDICE', '1. CAMPO DE APLICACIÓN 2. PISCINAS Y PEDILUVIOS', '2.1 Clasificación de los volúmenes 2.2 Prescripciones generales', '1. CAMPO DE APLICACIÓN', 'Texto del campo.', '2. PISCINAS Y PEDILUVIOS', '2.1 Clasificación de los volúmenes', 'Texto de los volúmenes.', '2.2 Prescripciones generales', 'Texto de prescripciones. Fuera de los volúmenes 0 y 1. Además las luminarias estarán protegidas.', 'Figura 1. Ejemplo de volúmenes'])
        hs, pendientes, fuera = censo.censo_calibrado(text, 'boe')
        self.assertNotIn('itc.BT-31/ap.0', {h.ruta for h in hs})
        self.assertFalse(pendientes, pendientes)
        self.assertFalse(fuera, fuera)
if __name__ == '__main__':
    unittest.main()
