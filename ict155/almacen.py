"""Compatibilidad de importación con el consumidor compartido con Cowork."""
import sys
from cowork import almacen_lectura
sys.modules[__name__] = almacen_lectura
