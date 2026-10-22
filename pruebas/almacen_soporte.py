"""Public CI documentation."""
from cowork.controles_lectura import conservar_almacen_forzado
VARIABLE = 'ICT155_CONTROLES_FORZADOS'

def limpiar_forzados(monkeypatch, *, raising=False):
    valor = conservar_almacen_forzado('{}')
    if valor != '{}':
        monkeypatch.setenv(VARIABLE, valor)
    else:
        monkeypatch.delenv(VARIABLE, raising=raising)
