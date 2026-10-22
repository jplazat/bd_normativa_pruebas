"""Public CI documentation."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ict155 import validador

def test_la_cursiva_se_quita_cuando_envuelve_un_tramo():
    assert validador._norm('de _cualquier solución técnica_ que') == 'de cualquier solución técnica que'

def test_el_guion_bajo_dentro_de_palabra_no_se_toca():
    for entero in ('une_en_12830', 'art_5_bis', 'boe_a_2016_5530'):
        assert validador._norm(entero) == entero

def test_un_guion_bajo_suelto_no_se_come_media_frase():
    assert validador._norm('el valor _ y el otro') == 'el valor _ y el otro'

def test_reconoce_la_declaracion_de_una_persona():
    for linea in ('el responsable de calidad declaró que «el registrador se contrasta»', 'el gerente manifestó que «el equipo cumple la norma»', 'el director técnico afirma que «la verificación la hacía el taller»', 'la empresa titular sostiene que «nunca se comunicó nada»', 'el jefe de mantenimiento indicó en el acta que «se retiraron»'):
        pos = linea.index('«')
        assert validador._es_declaracion_de_persona(linea, pos), linea

def test_el_verbo_normativo_no_se_confunde_con_uno_de_decir():
    for linea in ('el artículo 5 dispone que «el fabricante deberá»', 'el apartado 3 establece que «se aplicará lo previsto»', 'la norma indica que «el ensayo se repetirá»', 'el precepto señala que «no procede la exención»'):
        pos = linea.index('«')
        assert not validador._es_declaracion_de_persona(linea, pos), linea

def test_gana_el_verbo_mas_cercano_a_la_comilla():
    linea = 'el gerente declaró que conocía la norma, cuyo artículo 5 dispone que «el fabricante deberá conservar el registro»'
    pos = linea.index('«')
    assert not validador._es_declaracion_de_persona(linea, pos)
    linea = 'sobre el artículo 5 del Real Decreto 244/2016, el gerente manifestó que «nadie nos informó de esa obligación»'
    pos = linea.index('«')
    assert validador._es_declaracion_de_persona(linea, pos)

def test_la_ventana_no_salta_a_la_frase_anterior():
    linea = 'el gerente declaró lo que consta en acta. El artículo 5 del Real Decreto 244/2016 dispone que «el fabricante deberá»'
    pos = linea.index('«')
    assert not validador._es_declaracion_de_persona(linea, pos)

def test_la_frase_de_una_posicion_es_la_que_la_contiene():
    linea = 'Primera frase. Segunda frase con «algo dentro».'
    a, b = validador._frase_de(linea, linea.index('«'))
    assert linea[a:b].startswith('Segunda')
    a, b = validador._frase_de(linea, 2)
    assert linea[a:b].startswith('Primera')
