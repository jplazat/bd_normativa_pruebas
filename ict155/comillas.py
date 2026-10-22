"""Public CI documentation."""

def tramos(texto: str, errores: list[tuple[int, int]] | None=None) -> list[tuple[int, int]]:
    """Public CI documentation."""
    parejas = {'«': '»', '“': '”', '"': '"'}
    pila: list[str] = []
    salida: list[tuple[int, int]] = []
    inicio = 0
    invalido = False
    for pos, c in enumerate(texto):
        if c in '\r\n':
            if pila and errores is not None:
                errores.append((inicio, pos))
            pila.clear()
            invalido = False
            continue
        if not pila:
            if c in parejas:
                inicio = pos
                pila.append(parejas[c])
            continue
        if c == '"' and pila[-1] == '"':
            abre = pos > inicio + 1 and texto[pos - 1].isspace() and (pos + 1 < len(texto)) and texto[pos + 1].isalnum()
            if abre:
                pila.append('"')
                continue
        if c == pila[-1]:
            pila.pop()
            if not pila:
                minimo = 8 if texto[inicio] == '"' else 1
                if not invalido and pos - inicio - 1 >= minimo:
                    salida.append((inicio, pos + 1))
                elif invalido and errores is not None:
                    errores.append((inicio, pos + 1))
                invalido = False
        elif c in parejas:
            pila.append(parejas[c])
        elif c in ('»', '”'):
            invalido = True
    if pila and errores is not None:
        errores.append((inicio, len(texto)))
    return salida
