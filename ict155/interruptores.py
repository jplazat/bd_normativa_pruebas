"""Compatibilidad de importación con la capa compartida de controles.

Ambas entradas designan el mismo módulo: cachés, excepciones y ajustes de
pruebas conservan su identidad. Cowork no necesita importar ict155.
"""
import sys
from cowork import controles_lectura
sys.modules[__name__] = controles_lectura
