"""Public CI documentation."""
from __future__ import annotations
import ast
import sys
from collections import Counter
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
TABLAS = ('ALIAS', 'NT_TROCEADAS', 'FAMILIA_EXPLICITA', 'FAMILIA_POR_DEFECTO', 'METADATOS_POR_DOCUMENTO', 'METODO_POR_DOCUMENTO', 'TABLA', 'SIN_CLASIFICAR', 'TITULOS_OFICIALES', 'TITULO_DE_PORTADA_SIN_TEXTO')
FICHEROS = ('ict155/catalogo.py', 'ict155/caracter.py')

def _claves(nodo: ast.Dict) -> list[str]:
    """Public CI documentation."""
    out = []
    for k in nodo.keys:
        if k is None:
            continue
        try:
            out.append(str(ast.literal_eval(k)))
        except ValueError:
            trozos = [n.value for n in ast.walk(k) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            junto = ''.join(trozos)
            out.append(junto if junto else f'<sin literal, linea {k.lineno}>')
    return out

def test_ninguna_clave_repetida_en_el_codigo():
    problemas = []
    for rel in FICHEROS:
        ruta = RAIZ / rel
        if not ruta.exists():
            continue
        arbol = ast.parse(ruta.read_text(encoding='utf-8'))
        for nodo in ast.walk(arbol):
            objetivos = []
            if isinstance(nodo, ast.Assign):
                objetivos = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
                valor = nodo.value
            elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and (nodo.func.attr == 'update') and isinstance(nodo.func.value, ast.Name) and nodo.args:
                objetivos = [nodo.func.value.id]
                valor = nodo.args[0]
            else:
                continue
            if not isinstance(valor, ast.Dict):
                continue
            for nombre in objetivos:
                if nombre not in TABLAS:
                    continue
                for clave, n in Counter(_claves(valor)).items():
                    if n > 1:
                        problemas.append(f'{rel}: la clave {clave!r} aparece {n} veces en {nombre}, y Python se queda solo con la ultima')
    assert not problemas, 'Hay claves repetidas y eso BORRA datos sin avisar:\n  ' + '\n  '.join(problemas)
if __name__ == '__main__':
    test_ninguna_clave_repetida_en_el_codigo()
    print('sin hallazgos: ninguna tabla del catalogo repite una clave. Comprobado leyendo el codigo fuente con `ast`, no el diccionario ya construido, que no recuerda lo que perdio.')
