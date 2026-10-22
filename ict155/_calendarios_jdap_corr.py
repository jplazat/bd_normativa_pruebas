"""Public CI documentation."""
import re
ISO = re.compile('^\\d{4}-\\d{2}-\\d{2}$')
TEMPORALES = {'no_excede_mes', 'cumple_plazo', 'cumple_antelacion', 'no_excede_periodo', 'solicitud_en_plazo', 'cumplimiento_documentado', 'cumple_retirada', 'cumple_solicitud', 'antes_vencimiento'}
FECHAS_DE_ORIGEN = {'origen', 'origen_evento', 'frontera_general', 'frontera_cisterna'}
ORIGENES_POR_REGLA = {'AG-REGIMEN': {'/calculo_regimen_general/referencia'}, 'GAS-SUSTITUCION13': {'/origen_calendario'}, 'EL-SOFTWARE-ENTRADA': {'/entrada_orden'}, 'RC-COHORTES': {'/entrada'}}

def reservar_fechas(salida, calendario):
    fechas = []

    def limpiar(x, path=''):
        if isinstance(x, str) and ISO.fullmatch(x) and (path.rsplit('/', 1)[-1] not in FECHAS_DE_ORIGEN) and (path not in ORIGENES_POR_REGLA.get(salida.get('id'), set())):
            fechas.append(path)
            return None
        if isinstance(x, dict):
            return {k: limpiar(v, path + '/' + k) for k, v in x.items()}
        if isinstance(x, list):
            return [limpiar(v, path + '/' + str(i)) for i, v in enumerate(x)]
        return x
    resultado = limpiar(salida['resultado'])
    if not fechas:
        return salida

    def neutralizar(x):
        if isinstance(x, dict):
            return {k: None if k in TEMPORALES and isinstance(v, bool) else neutralizar(v) for k, v in x.items()}
        if isinstance(x, list):
            return [neutralizar(v) for v in x]
        return x
    resultado = neutralizar(resultado)
    pregunta = {'hecho_id': 'calendario_administrativo_oficial', 'campo': 'calendario_administrativo_oficial', 'pregunta': 'Aporte el calendario administrativo oficial del territorio, su periodo y la constancia de revision del computo de este plazo.', 'motivo': 'B2-CALENDARIOS_calendario_y_computo_por_acreditar', 'unidad': None, 'destinatario': 'persona_revisora_con_soporte_documental'}
    faltantes = [pregunta] + salida['hechos_faltantes']
    return {**salida, 'resultado': resultado, 'estado': 'pendiente_calendario_y_computo', 'motivo': 'No fechar plazos reales sin calendario administrativo oficial del territorio y cotejo de su aplicacion.', 'siguiente_pregunta': pregunta, 'hechos_faltantes': faltantes, 'reglas_aplicables': [], 'campos_fecha_pendientes': fechas, 'calendario_aportado_sin_validar': calendario is not None, 'fecha_definitiva_expediente': None, 'criterio_origen_agua_gas': 'Fin vigente y dia exacto decididos en sesion 2 conservados en contrato y hechos; el calendario no cambia el origen.', 'publicable': False}
