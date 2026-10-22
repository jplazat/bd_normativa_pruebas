"""Servidor MCP de SOLO CONSULTA de la base normativa ICT155 para Claude Cowork (7-oct-2026).

Cowork lo lanza en PC1 por la extension `normativa-ict155` (paquete .mcpb). Habla MCP por stdio
(JSON-RPC 2.0, una linea por mensaje) y no tiene dependencias: el protocolo va a mano, como en
la extension del correo (`cowork_mail_broker`).

QUE PUEDE HACER. Solo las ordenes de consulta de `ict155.cli`, que abren la base en modo de solo
lectura (`mode=ro`): buscar, cita, fundamento, cotejar, revisar, verificar-entrega, obligatorios, obras e info. Nunca
`reconstruir`, nunca otro ambito que el publico (la base decide que se reproduce y que solo se
localiza) y nunca escribe en la carpeta del proyecto. Cada orden es un proceso aparte con los
argumentos en lista (sin consola de por medio), sin heredar la entrada estandar del servidor (que
es la tuberia del protocolo) y sobre la base de produccion (`ICT155_DATOS` se quita del entorno).
`revisar` recibe el borrador por su entrada estandar, no como argumento; `verificar-entrega`, la respuesta final y la
pregunta de Responsable (un objeto JSON, con `--entrada-json`); `obligatorios`, la pregunta.

REGISTRO. Cada llamada deja una linea en %LOCALAPPDATA%\\ict155\\cowork\\audit.log: hora,
herramienta, identificador (una referencia normativa) y estado. El texto libre (lo que se busca,
la afirmacion que se coteja, el borrador que se revisa, la respuesta que se verifica, la pregunta de Responsable) NO se guarda: solo su
largo y el principio de su huella, porque puede llevar datos de un cliente. Desde la 1.7.0 el estado de `normativa_revisar` lleva el
codigo de sello del borrador (SELLO=) y el de `normativa_verificar_entrega`, el veredicto y los dos codigos (el del texto, SELLO=,
y el de la linea de sello que traia la respuesta, PRESENTE=): se cruzan sin guardar el texto.

R24 (1.12.0, 16-oct-2026): la comprobacion antes de enviar una tanda de correos. `normativa_comprobar_carpeta(carpeta, momento)` comprueba, sola, lo que Claude Code
hacia a mano antes de cada envio a clientes: que cada fichero de `preguntas.json` sea exactamente lo verificado (si Cowork tocó algo después de verificar, el sello ya no
vale), que la version para enviar (`ENVIAR_*.txt`) solo pierda identificadores y marcas «(opinion)» (palabra a palabra: un «no» quitado o una cifra cambiada es NO LISTO,
con el trozo antes y despues) y que la tanda este archivada con los mismos ficheros. Dice `LISTO PARA ENVIAR` o que falla. Es la unica herramienta que recibe una RUTA:
solo de carpetas bajo `D:\\OneDrive\\ICT155.COM\\` (absoluta, resuelta y sin «..»; cualquier otra cosa es error de argumento). En el registro va `REVCARPETA=LISTO|NO_LISTO;N=…;K=…`
y la huella de la ruta: nunca nombres de fichero ni texto de los correos (llevan datos de clientes).

R20 (1.8.0, 14-oct-2026): que una respuesta no pueda callar lo obligatorio del tema de la pregunta. El sello de R19 garantiza que lo
dicho es cierto, no que esté todo. `normativa_obligatorios(pregunta)` da, para la pregunta de Responsable tal cual, lo que no puede faltar
(la lista es `cowork/temas_obligatorios.json`, que valida Responsable: no la decide el modelo) y `normativa_verificar_entrega(respuesta,
pregunta)` no deja pasar una respuesta que lo calle: `INCOMPLETA: falta citar …` y veredicto NO VÁLIDA. La pregunta se pide en las
dos llamadas, literal; en el registro va como `pregunta=len=…:sha=…` (el mismo largo y la misma huella en las dos permiten ver que
fue la misma pregunta) y el estado de la verificación lleva `TEMAS=` y `FALTAN=`.

R23 (1.11.0, 16-oct-2026): una segunda lectura de la INTERPRETACIÓN, hecha por la propia extensión. El código ya garantizaba que lo citado existe, es
exacto y está vigente y que no falta lo obligatorio; no que la respuesta lo lea bien (la primera versión de unos correos atribuía al dueño de la mercancía una
obligación que el RD 1109/1991 pone en las empresas responsables del transporte). `normativa_verificar_entrega` llama ahora siempre a `verificar-entrega
--revision-independiente`: `ict155.revision_independiente` lanza `claude -p` (sin herramientas, sin servidores MCP, sin sesión guardada y sin los ajustes del
usuario) con la pregunta, la respuesta sin su sello y los textos que cita, y el código solo deja pasar las objeciones que traen pruebas verificables en esos textos;
cada una es un motivo de ENTREGA NO VÁLIDA. Si la revisión no se puede hacer, la entrega no vale (falla cerrado). El estado del registro lleva `REVIND=<n>` o
`REVIND=NO_HECHA`, nunca texto. La verificación tarda ahora decenas de segundos (una segunda lectura con un modelo): `TIEMPO_MAXIMO_POR_ORDEN` lo permite y la
revisión guarda su resultado en `%LOCALAPPDATA%\\ict155\\cowork\\revision_independiente\\` para no pagarla dos veces por el mismo texto. Si la petición `tools/call` trae
`_meta.progressToken`, el servidor manda un `notifications/progress` cada ~10 s mientras dura la llamada (`_Latidos`), por si el cliente reinicia su plazo con cada aviso; sin
token no manda nada. Si el cliente corta igualmente, la revisión que ya se hizo queda en la caché y repetir la llamada responde enseguida.

R25 (1.13.0, 17-oct-2026): dos revisiones independientes en la comprobación de carpeta. Medido el 16-oct en producción, la revisión independiente caza siempre los
errores gruesos pero no es determinista en los sutiles (la misma respuesta, revisada dos veces, dio 0 objeciones y luego 1 objeción real), y `normativa_comprobar_carpeta`
no la hacía: si Cowork retocaba un correo y lo volvía a sellar sin pasar por `normativa_verificar_entrega`, la carpeta daba LISTO sin que el texto final tuviera segunda lectura.
Ahora `normativa_comprobar_carpeta` llama SIEMPRE a `comprobar-carpeta --revision-independiente --pasadas 2` (como `verificar-entrega`, no hay forma de pedirla sin ella): cada
correo pasa por dos revisiones independientes (dos llamadas distintas a `claude -p`, todas las de la tanda a la vez, hasta 6 en paralelo); cada objeción es un problema de ese
correo (la objeción entera) y la tanda queda NO LISTO; una revisión que no se pueda hacer también lo es. La primera revisión reaprovecha la caché de `normativa_verificar_entrega`.
La orden tarda de 1 a 5 minutos: plazo de 900 s y los mismos latidos `notifications/progress` que la verificación. El registro de la llamada añade las cifras de la revisión
(`REVCARPETA=…;N=…;K=…;REVIND=<objeciones>|NO_HECHA;PASADAS=<n>`, solo números).

R26 (1.14.0, 17-oct-2026): `normativa_verificar_entrega` también hace DOS revisiones independientes (`verificar-entrega --pasadas 2`). En la prueba real
del 17-oct (Cowork con una pregunta difícil de reparación de registradores), una sola revisión dejó pasar dos errores sutiles que una segunda vio. Las dos van a la
vez: tarda lo mismo y cuesta el doble (unos 0,16 USD). El registro añade `;PASADAS=2` al estado de la verificación.

R22 (1.10.0, 16-oct-2026): cada literal se coteja con el ORIGINAL. `revisar` comprobaba que cada literal estaba en el precepto que cita, pero en el
texto de la base, que es una extracción. Ahora, además, cada literal que sale bien se coteja con el texto oficial del BOE (consolidado, o el del Diario), de
EUR-Lex (por CELLAR) o con el propio PDF (PyMuPDF): si coincide sigue siendo OK («cotejado con …») con el mismo recuento y la misma línea de sello; si el original
dice otra cosa, ERROR de tipo `cotejo` con el trozo del original; si no hay original con que cotejar (reconocimiento óptico, transcripción), ERROR; si el original no
se ha consultado, un AVISO por obra. Las instantáneas (`texto_oficial_boe.json`, `texto_oficial_ue.json`, junto a la base) se rehacen con `ict155.cli cotejo
--actualizar` desde Claude Code, no desde aquí. Es de solo lectura, como todo lo demás.

R21 (1.9.0, 15-oct-2026): quién dio cada redacción. La base guarda una sola redacción de cada norma y nada decía qué norma la dio: una
respuesta vio que el anexo III, apartado 4, de la Orden ICT/155/2020 no coincide con el texto de la Orden ITU/1475/2024 y concluyó, sin
razón, que la vigencia estaba mal (la redacción vigente la dio la Orden ITU/1072/2025). `normativa_cita` trae ahora, detrás de la
vigencia, un bloque REDACCIÓN (el historial de redacciones del BOE de ese precepto, de la consulta guardada `historial_boe.json`, que
se hace con `ict155.cli historial-boe --actualizar` desde Claude Code, no desde aquí): la norma que dio la vigente, las anteriores y,
si la base es anterior a la vigente, un AVISO. Es de solo lectura, como todo lo demás.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
import unicodedata
VERSION = '1.14.0'
DEFAULT_PROTOCOL = '2025-06-18'
PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROYECTO not in sys.path:
    sys.path.insert(0, PROYECTO)
from cowork import almacen_lectura as almacen
from cowork import controles_lectura as controles
AUDIT_DIR = os.environ.get('ICT155_COWORK_AUDIT_DIR') or os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'ict155', 'cowork')
AUDIT_LOG = os.path.join(AUDIT_DIR, 'audit.log')
LIMITES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'limites_conocidos.json')
LIMITES_DE_USO = 'D:\\Proyectos\\bd_normativa\\LIMITES_DE_USO.md'
AVISO_SIN_PAGINA = 'La base no sabe en qué página está este precepto (el texto viene del BOE sin páginas): buscarlo en el PDF.'
SIN_ENTRADA_SUCESION = 'no consta en la tabla revisada de sucesión de preceptos (eso no prueba que su contenido no siga en otro sitio: si la norma que la deroga está en la base, léela)'
NOTA_DE_APARTADOS_SUCESION = '(El precepto citado no tiene entrada propia en la tabla: se enseñan las de sus apartados, cada una válida solo para el suyo.)'
CLAVES_PAGINAS_DOCUMENTO = ('paginas_documento', 'paginas_del_documento', 'n_paginas', 'total_paginas')
TIEMPO_MAXIMO = 90
TIEMPO_MAXIMO_POR_ORDEN = {'brechas': 600, 'verificar-entrega': 480}
try:
    LATIDO_SEGUNDOS = float(os.environ.get('ICT155_COWORK_LATIDO') or 10) or 10
except ValueError:
    LATIDO_SEGUNDOS = 10.0
TIEMPO_MAXIMO_POR_ORDEN['comprobar-carpeta'] = 900
RAIZ_PERMITIDA = 'D:\\OneDrive\\ICT155.COM'
LARGO_MAXIMO_ARGUMENTO = 2000
LARGO_MAXIMO_BORRADOR = 60000
LARGO_MAXIMO_RESPUESTA = LARGO_MAXIMO_BORRADOR + 2000
LARGO_MAXIMO_PREGUNTA = 20000
LARGO_MAXIMO_REGISTRO = 2 * 1024 * 1024
LARGO_MAXIMO_ERROR_REGISTRO = 100000
LARGO_MAXIMO_TEXTO = 15000
ORDENES = ('buscar', 'cita', 'fundamento', 'cotejar', 'revisar', 'obras', 'info', 'vigencia', 'brechas', 'verificar-entrega', 'obligatorios', 'comprobar-carpeta', 'hechos')
INSTRUCCION = 'Cita cada uno en la respuesta, para aplicarlo o para explicar por qué no aplica; callarlo hace la entrega NO VÁLIDA (INCOMPLETA).'
NO_EXHAUSTIVA = 'La lista no es exhaustiva: que no haya tema no significa que la respuesta esté completa.'
AVISO_LICENCIADO = 'AVISO: es una norma con LICENCIA de uso de Responsable (régimen «licenciado»). Puedes leerla para trabajar, pero no copies su texto en documentos para terceros (informes a clientes): cita la referencia (norma, apartado, página) y, como mucho, una frase corta entre comillas.'
SERVER_INSTRUCTIONS = 'Este servidor consulta la BASE NORMATIVA de ICT155 (metrología legal): BOE (Orden ICT/155/2020, Ley 32/2014, RD 244/2016, RD 1109/1991, RD 552/2019 de instalaciones frigoríficas con sus instrucciones IF-01 a IF-21, RD 1021/2022 de higiene de los alimentos en el comercio al por menor…), EUR-Lex (MID 2014/32/UE, RED, Reglamento (CE) 37/2005…), guías WELMEC, OIML (V1 = VIML), VIM, GUM y JCGM, EA, ILAC, OMS, ETSI y las normas UNE/EN con licencia. Úsalo SIEMPRE que Responsable pregunte qué dice una norma, una definición, un requisito o un error máximo, o pida citar o comprobar una cita: es la fuente de verdad, no tu memoria. Es de SOLO CONSULTA.\n\nEs la ÚNICA vía para consultar esa base: no ejecutes `python -m ict155.cli` ni comandos de PowerShell o de terminal sobre D:\\Proyectos\\bd_normativa, ni copies sus ficheros. Esa vía no avisa de las licencias de las normas ni deja registro de la consulta.\n\nCómo:\n0. Antes de buscar, llama a normativa_obligatorios con la pregunta de Responsable tal cual. Lo que devuelva se cita en la respuesta, para aplicarlo o para explicar por qué no aplica; callarlo hace la entrega NO VÁLIDA (INCOMPLETA). La pregunta va entera y sin tocar (si Responsable pegó un correo, con el correo): el tema se detecta por sus palabras y no vale resumirla ni reformularla. La lista no es exhaustiva: que no haya tema no significa que la respuesta esté completa.\n1. normativa_buscar(texto) para encontrar dónde aparece algo (devuelve el identificador de cada sitio). Si el texto es el nombre de una norma de la base («EN 12830:2018»), la salida empieza por esas OBRAS, con su identificador, si están completas o son parciales y su régimen: mira ahí antes de decir que la base no tiene una norma o un apartado (solo un ejemplar COMPLETO permite concluir que algo no existe).\n2. normativa_cita(identificador) para el texto literal y su procedencia (obra, versión, fichero, página). Identificador = obra::ruta, p. ej. "Orden ICT/155/2020::anexo.XI/ap.1", "VIM::ap.4.26", "MID::art.4", "OIML V1::ap.0.01", "Ley 32/2014::art.8.1"; las instrucciones técnicas de un reglamento, así: "RD 552/2019::itc.IF-01/ap.1". normativa_obras lista las obras y sus identificadores. Detrás del texto viene un CONTEXTO OBLIGATORIO: el ámbito de la norma, las definiciones de los términos que usa el precepto, su padre y sus remisiones (diciendo si la base las tiene). LÉELO ENTERO antes de concluir: ahí están las exclusiones, las excepciones y las definiciones que cambian la respuesta.\n3. normativa_fundamento(frase) dice qué precepto contiene una frase literal; normativa_cotejar(identificador, afirmacion) dice si las palabras de una afirmación están en ese precepto, sin reproducir su texto (útil con normas con derechos).\n4. normativa_revisar(borrador): OBLIGATORIO antes de entregar a Responsable cualquier respuesta con citas. Comprueba contra la base cada identificador, cada literal (que está en el precepto que cita, entero, sin dejar fuera la condición de su frase ni la excepción que le sigue), las páginas, las rutas que no son fiables y las normas que la base no tiene; y, desde la 1.6.0, cada FRASE de tu prosa: cuáles son afirmaciones normativas, cuáles comprobó el código y cuáles no. Corrige cada ERROR, atiende cada AVISO (cita la condición o la excepción, cambia la ruta, di que la base no tiene la norma) y vuelve a revisar hasta que no quede ningún ERROR NI ninguna afirmación normativa sin comprobar. Termina tu respuesta con la LÍNEA DE COBERTURA que devuelve (la PRIMERA línea del resultado: «Comprobado por la base: N citas comprobadas (…); K afirmaciones normativas sin comprobar; M marcadas como opinión. … [sello: XXXXXXXX]»), copiada TAL CUAL, entera y con su código, como ÚLTIMA línea de la respuesta: es OBLIGATORIA y no se maquilla (no se reescribe, no se resume, no se pasa a otro formato, no se le añade nada). El código del sello es del texto que revisaste: si cambias una sola palabra, una cifra o una cita después de revisar, el sello deja de valer y hay que VOLVER A REVISAR. Esa línea comprueba lo citado y la cobertura de tu prosa, no lo concluido: que la respuesta entera esté bien no lo dice nadie salvo Responsable.\n5. normativa_verificar_entrega(respuesta, pregunta): el ÚLTIMO paso, sobre la respuesta FINAL tal como la vas a entregar, con su línea de sello como última línea, y con la pregunta de Responsable LITERAL (la misma del paso 0, tal cual). Vuelve a revisar el texto sin esa línea, comprueba que el sello es el de ese texto y que la respuesta cita lo obligatorio del tema de la pregunta. La primera línea del resultado es el veredicto: «ENTREGA VÁLIDA» o «ENTREGA VÁLIDA CON AVISOS» (atiende cada aviso que trae) y solo entonces se entrega; «ENTREGA NO VÁLIDA: …» dice los motivos (no hay sello, el sello está retocado, el código no es el de este texto, hay errores, quedan afirmaciones sin comprobar, «INCOMPLETA: falta citar …» un precepto obligatorio del tema): se ARREGLA lo que dice (lo INCOMPLETO, citando ese precepto con su identificador `obra::ruta`, para aplicarlo o para explicar por qué no aplica; nunca callándolo), se vuelve a revisar y a verificar. No se entrega una respuesta NO VÁLIDA, ni resumida, ni con una nota que explique los avisos, ni con otra línea de sello: Responsable y quien reciba la respuesta pueden repetir esta comprobación, y si el sello se ha tocado se nota. La lista de lo obligatorio no es exhaustiva: que la verificación no encuentre ningún tema no significa que la respuesta esté completa. Desde la 1.11.0, la verificación final incluye una revisión independiente de la interpretación (otro modelo, sin el contexto de la conversación, lee tu respuesta contra los textos que cita): cada OBJECIÓN se resuelve cambiando el texto (o marcándolo como opinión si es una lectura); si crees que una objeción es errónea, díselo a Responsable con la objeción entera; no se entrega con objeciones. Tarda hasta un minuto o dos: espera el resultado; si la llamada da error por tiempo, repítela igual (la revisión ya hecha queda guardada y la segunda vez responde enseguida). Si dice que no se ha podido hacer, vuelve a verificar y, si persiste, avisa a Responsable.\n\nCómo estructurar la respuesta (1.6.0): separa dos partes. «Lo que dice la norma (comprobado)»: solo lo que cita la base, con su identificador al lado. «Lectura de ICT155 (opinión)»: tu interpretación, tus consejos, tus comparaciones («es más limpio citar…», «puedes dejar de apoyarte en…»), lo que has visto fuera de la base y todo lo que la base no puede confirmar (por qué una norma dice lo que dice, qué decía antes de su consolidación, qué hay en un documento que no está en la base). Una respuesta NO está terminada mientras queden afirmaciones normativas sin comprobar: cada una se cita con su identificador `obra::ruta` en la misma frase, en su renglón o en un encabezado de un renglón justo encima, o se marca como opinión (bajo un rótulo que empiece por «Opinión», «Lectura de ICT155» o «Valoración», o con «(opinión)» al final de la frase). Lo que la revisión no pueda comprobar nunca es «comprobado»: es «sin comprobar» o es tu opinión.\n\nCómo escribir las citas, para que la revisión las pueda comprobar:\n- Cada literal entre «» o en cita de bloque (>), con su identificador obra::ruta entre comillas invertidas (`…`) en el mismo renglón (en una tabla, en la misma fila), o en un encabezado de un solo renglón justo encima, separado por una línea en blanco; y su página.\n- Lo que no sea literal va sin comillas: es tu paráfrasis.\n\nReglas:\n- Solo pon entre comillas, como literal, lo que devuelva normativa_cita, con su procedencia. Lo demás es tu paráfrasis y así debe decirse. Y solo si el rótulo dice «TEXTO LITERAL»: si dice «TEXTO (transcripción de ICT155…)», «TEXTO (reconocimiento óptico…)» o «TEXTO (ejemplar PARCIAL…)», no es el literal de la norma (en la transcripción, solo lo entrecomillado lo es) y la revisión lo avisa.\n- «La base no lo tiene» no es «no hay obligación»: si una norma no está en la base (la revisión lo avisa), dilo así y no afirmes nada de su contenido ni de su vigencia.\n- VIGENCIA: cada cita de una norma trae un bloque VIGENCIA, de la consulta guardada al BOE y a la UE. Si trae un AVISO (derogada, DEROGACIÓN posterior, modificada después de la versión que tiene la base, modificación que la base no tiene, consulta vieja), dilo SIEMPRE en la respuesta, junto a la cita: no presentes como vigente un texto que la fuente oficial da por derogado o por modificado. Una «DEROGACIÓN posterior» puede tener efecto diferido y ser parcial: lee el acto (normativa_cita) antes de decir si la norma sigue vigente. La revisión también lo avisa (tipo «vigencia»). normativa_vigencia(obra) da el detalle.\n- REDACCIÓN (1.9.0): la cita de un precepto de una norma del BOE trae un bloque REDACCIÓN, de la consulta guardada al BOE: qué norma dio la redacción vigente de ese precepto y quiénes las anteriores. Cuando la pregunta trate de cambios de una norma, di qué norma dio la redacción vigente según ese bloque (no concluyas que la vigencia está mal porque el texto consolidado no coincida con el de una norma anterior: mira antes quién dio la vigente). Lo que la base no tiene (el texto de las redacciones anteriores) no se afirma: solo se sabe quién las dio y desde cuándo. Si el bloque avisa de que la base no tiene la redacción vigente de ese precepto, dilo SIEMPRE junto a la cita.\n- COTEJO (1.10.0): cada literal se coteja con el original (BOE, EUR-Lex o el PDF); si la revisión da ERROR de cotejo, usa la redacción del original que te muestra o quita las comillas y cita cláusula y página. Un texto que no tiene original con que cotejarse (reconocimiento óptico, transcripción) no se entrecomilla: cita la cláusula y la página.\n- normativa_brechas(registro): comprueba contra la base todas las citas de un registro de brechas y su última revisión; úsalo tras cada lote de verificación.\n- SUCESIÓN Y REMISIONES (1.6.0): si una norma está derogada, su cita trae «Contenido equivalente vigente: …» (tabla revisada de sucesión de preceptos): una frase puede estar derogada y su prohibición seguir en otro precepto vigente; no la llames «derecho muerto» sin decir dónde sigue. «(total)» = el sucesor dice lo mismo; «(parcial)» = solo una parte, y la nota dice qué falta y dónde sigue; «[apartado X]» = vale solo para ese apartado. Detrás del contexto, «REMITEN A ESTE PRECEPTO» lista los preceptos de la misma obra que lo invocan (un «si su anexo lo permite» se resuelve ahí): léelos antes de cerrar una excepción. La revisión comprueba «solo existe en…» contra toda la base, las derogaciones y vigencias contra la consulta guardada, «X modificó `Y::ruta`» contra el historial de redacciones (OK si lo confirma; ERROR si el historial dice que X no dio ninguna redacción de ese precepto), y avisa de «porque X modificó…», de las negaciones («la base no tiene…», «no dice…»: di qué buscaste), de los consejos y de los absolutos.\n- No generalices más allá del texto: si una conclusión depende de un término que la norma no define o de una condición, preséntala como duda para el criterio de Responsable.\n- Si el estado no es ENCONTRADO (FUERA_DE_ALCANCE, EDICION_AMBIGUA, CONTENIDO_EN_ANCESTRO, NO_CONSTA…), díselo a Responsable tal cual y sigue la indicación que trae (añadir @fecha, citar el padre…). No completes de memoria.\n- Normas con LICENCIA (UNE/EN): se pueden leer para trabajar, pero su texto no se copia en documentos para clientes; se cita la referencia. Las de derechos restringidos solo se localizan.\n- La base no interpreta: da el texto. Que una afirmación «coincida» no prueba que sea correcta, y que la revisión salga limpia tampoco: comprueba lo citado, no lo concluido. Interpretar es de Responsable.\n- Antes de enviar una tanda a clientes, `normativa_comprobar_carpeta` sobre su carpeta: solo se envía si dice LISTO PARA ENVIAR. Después del envío, archívala y vuelve a llamarla con momento=despues.\n- Si una herramienta falla, di el error tal cual; no busques otra vía (ni Desktop Commander ni scripts).'
TOOLS = [{'name': 'normativa_buscar', 'orden': 'buscar', 'description': 'VÍA OFICIAL para consultar la base normativa de ICT155 (no uses la terminal ni python -m ict155.cli). Busca un texto literal en toda la base (frase, número, referencia como "2014/32" o "EN 12830"). Devuelve dónde aparece: identificador para citar, título, página y un fragmento. Si el texto es el nombre de una norma de la base ("EN 12830:2018"), empieza por esas OBRAS: su identificador, si el ejemplar está completo o es parcial y su régimen; mira ahí antes de concluir que la base no tiene una norma o un apartado.', 'inputSchema': {'type': 'object', 'properties': {'texto': {'type': 'string', 'description': 'Lo que se busca, tal cual (no es una expresión de búsqueda).'}, 'limite': {'type': 'integer', 'description': 'Máximo de resultados (1 a 30; por defecto 10).'}}, 'required': ['texto']}}, {'name': 'normativa_cita', 'orden': 'cita', 'description': 'VÍA OFICIAL para citar la base normativa de ICT155 (no uses la terminal). Devuelve el texto literal de un precepto y su procedencia (obra, versión, fichero, página, régimen de derechos). Con localizar=true solo dice dónde está, sin el texto. Por defecto, detrás del texto devuelve el CONTEXTO OBLIGATORIO: el ámbito de la norma, las definiciones de los términos que usa el precepto, su padre, sus remisiones (diciendo si la base las tiene) y los preceptos de la misma obra que REMITEN A ÉL. De una norma derogada, su bloque de vigencia dice también dónde sigue su contenido («Contenido equivalente vigente»). De una norma del BOE, detrás de la vigencia trae el bloque REDACCIÓN: qué norma dio la redacción vigente de ese precepto y quiénes las anteriores (y un AVISO si la base tiene una redacción anterior a la vigente). Hay que leerlo entero antes de concluir nada del precepto.', 'inputSchema': {'type': 'object', 'properties': {'identificador': {'type': 'string', 'description': 'obra::ruta, p. ej. "Orden ICT/155/2020::anexo.XI/ap.1" o "VIM::ap.4.26".'}, 'localizar': {'type': 'boolean', 'description': 'true: solo la ubicación (fichero y página), sin texto.'}, 'contexto': {'type': 'boolean', 'description': 'Por defecto true: añade detrás del texto el contexto obligatorio (ámbito, definiciones, padre y remisiones). false solo si ya lo tienes leído.'}}, 'required': ['identificador']}}, {'name': 'normativa_fundamento', 'orden': 'fundamento', 'description': 'Dice qué precepto contiene una frase literal (para encontrar el fundamento de una cita).', 'inputSchema': {'type': 'object', 'properties': {'frase': {'type': 'string', 'description': 'La frase, tal cual aparece en la norma.'}, 'obra': {'type': 'string', 'description': 'Opcional: restringe a una obra (identificador, alias o parte del título).'}}, 'required': ['frase']}}, {'name': 'normativa_cotejar', 'orden': 'cotejar', 'description': 'Dice si las palabras de una afirmación están en un precepto (COINCIDE / NO_COINCIDE y qué palabras faltan), SIN reproducir el texto del precepto.', 'inputSchema': {'type': 'object', 'properties': {'identificador': {'type': 'string', 'description': 'obra::ruta del precepto.'}, 'afirmacion': {'type': 'string', 'description': 'Lo que se afirma de ese precepto.'}}, 'required': ['identificador', 'afirmacion']}}, {'name': 'normativa_obligatorios', 'orden': 'obligatorios', 'description': 'PRIMER PASO, ANTES DE BUSCAR: dada la pregunta de Responsable TAL CUAL (entera; si pegó un correo, con el correo), dice qué temas de la lista de lo obligatorio (la valida Responsable, no el modelo) toca y, de cada uno, los preceptos que la respuesta tiene que citar (con su identificador obra::ruta) y por qué. Se citan para aplicarlos o para explicar por qué no aplican; callarlos hace la entrega NO VÁLIDA (INCOMPLETA) en normativa_verificar_entrega. La lista no es exhaustiva: que no devuelva ningún tema no significa que la respuesta esté completa. De solo lectura.', 'inputSchema': {'type': 'object', 'properties': {'pregunta': {'type': 'string', 'maxLength': LARGO_MAXIMO_PREGUNTA, 'description': 'La pregunta de Responsable, tal cual y entera (sin resumir ni reformular); si pegó un correo, con el correo.'}}, 'required': ['pregunta']}}, {'name': 'normativa_revisar', 'orden': 'revisar', 'description': 'OBLIGATORIO antes de entregar a Responsable una respuesta con citas. Comprueba el borrador contra la base: cada identificador, cada literal (que esté en el precepto citado, entero, sin dejar fuera la condición de su frase ni la excepción que le sigue), las páginas, las rutas poco fiables y las normas que la base no tiene; y cada frase de tu prosa: qué afirmaciones normativas están comprobadas, cuáles no (AVISO «sin_comprobar») y cuáles marcaste como opinión, con detectores de «solo existe en…», derecho derogado, «X modificó Y», negaciones, consejos y absolutos. Devuelve una tabla OK / AVISO / ERROR con una línea por comprobación y la LÍNEA DE COBERTURA («Comprobado por la base: N citas comprobadas (…); K afirmaciones normativas sin comprobar; M marcadas como opinión. … [sello: XXXXXXXX]»), la primera línea del resultado, que se copia TAL CUAL (entera, con su código) como última línea de la respuesta. El código es del texto revisado: si cambias algo después, vuelve a revisar. Una respuesta con afirmaciones sin comprobar NO está lista: cada una se cita con su identificador o se marca como opinión («Lectura de ICT155 (opinión)»). Corrige cada ERROR, atiende cada AVISO y vuelve a revisar; el último paso, antes de entregar, es normativa_verificar_entrega sobre la respuesta final.', 'inputSchema': {'type': 'object', 'properties': {'borrador': {'type': 'string', 'maxLength': LARGO_MAXIMO_BORRADOR, 'description': 'El texto completo de la respuesta que se va a entregar, tal cual: con los literales entre «» o en cita de bloque (>) y su identificador obra::ruta entre comillas invertidas (`…`).'}}, 'required': ['borrador']}}, {'name': 'normativa_verificar_entrega', 'orden': 'verificar-entrega', 'description': 'ÚLTIMO PASO antes de entregar a Responsable una respuesta con citas, sobre la respuesta FINAL, con su línea de sello como última línea y sin tocar nada más. Busca la línea de sello (la de «Comprobado por la base: …[sello: XXXXXXXX]» que devolvió normativa_revisar), vuelve a revisar el texto sin ella y compara. La PRIMERA línea del resultado es el veredicto: «ENTREGA VÁLIDA» (el sello es el de este texto, sin errores ni afirmaciones sin comprobar ni avisos), «ENTREGA VÁLIDA CON AVISOS» (lo mismo, pero quedan avisos que atender) o «ENTREGA NO VÁLIDA: motivos» (no hay sello; el sello está retocado y no es la línea que da la herramienta; el código no corresponde al texto porque cambió después de revisarlo; hay errores; quedan afirmaciones normativas sin comprobar; o la respuesta está INCOMPLETA: «INCOMPLETA: falta citar …» por cada precepto obligatorio del tema de la pregunta que calla). Exige la pregunta de Responsable TAL CUAL, entera (la misma de normativa_obligatorios): sin ella no se puede comprobar que esté completa. Solo se entrega si es VÁLIDA o VÁLIDA CON AVISOS; si no lo es, se arregla (se cita lo que falta, para aplicarlo o para explicar por qué no aplica; no se resume ni se reescribe el sello) y se vuelve a revisar. Debajo da los temas detectados, la línea de sello correcta para ese texto y los avisos. La lista de lo obligatorio no es exhaustiva: que no haya tema no significa que la respuesta esté completa. Desde la 1.11.0 la verificación final incluye una REVISIÓN INDEPENDIENTE de la interpretación (otro modelo, sin el contexto de la conversación, lee la respuesta contra los textos que cita; desde la 1.14.0, DOS revisiones a la vez, y vale la unión de sus objeciones; tarda hasta un minuto o dos): cada OBJECIÓN se resuelve cambiando el texto (o marcándolo como opinión si es una lectura); si crees que una objeción es errónea, díselo a Responsable con la objeción entera; no se entrega con objeciones, ni si la revisión no se ha podido hacer (vuelve a verificar y, si persiste, avisa a Responsable). De solo lectura.', 'inputSchema': {'type': 'object', 'properties': {'respuesta': {'type': 'string', 'maxLength': LARGO_MAXIMO_RESPUESTA, 'description': 'El texto completo de la respuesta que se va a entregar, tal cual, con la línea de sello que devolvió normativa_revisar como última línea.'}, 'pregunta': {'type': 'string', 'maxLength': LARGO_MAXIMO_PREGUNTA, 'description': 'La pregunta de Responsable, TAL CUAL y entera (la misma que diste a normativa_obligatorios); si pegó un correo, con el correo. No la resumas ni la reformules.'}}, 'required': ['respuesta', 'pregunta']}}, {'name': 'normativa_obras', 'orden': 'obras', 'description': 'Lista las obras de la base (identificador, número de preceptos, versión y título). Con filtro, solo las que lo contienen.', 'inputSchema': {'type': 'object', 'properties': {'filtro': {'type': 'string', 'description': 'Opcional: texto que debe aparecer en la línea (p. ej. "WELMEC", "2014/32").'}}}}, {'name': 'normativa_estado', 'orden': 'info', 'description': 'Estado de la base: fecha de la última reconstrucción, número de documentos y preceptos, huella, y fecha de la consulta de vigencia.', 'inputSchema': {'type': 'object', 'properties': {}}}, {'name': 'normativa_comprobar_carpeta', 'orden': 'comprobar-carpeta', 'description': 'ANTES DE ENVIAR una tanda de correos a clientes: comprueba la carpeta de la tanda (la que tiene preguntas.json, los borradores verificados y, si los hay, sus versiones ENVIAR_*.txt). Hace sola cuatro comprobaciones: (1) que cada fichero de preguntas.json sea exactamente lo verificado (la verificación de normativa_verificar_entrega con la instrucción de Responsable: si se tocó algo después de verificar, una cabecera o una coma, el sello ya no vale); (2) que la versión para enviar (ENVIAR_*.txt) solo pierda identificadores `…`, marcas «(opinión)» y los signos que quedan sueltos, palabra a palabra: un «no» quitado, una cifra cambiada o una palabra añadida es NO LISTO, con el trozo exacto antes y después; (3) que la tanda esté archivada en archivo_entregas con los mismos ficheros, byte a byte; (4) dos REVISIONES INDEPENDIENTES de la interpretación de cada correo (otro modelo, sin el contexto de la conversación, lee el correo contra los textos que cita; son dos llamadas distintas por correo, porque una sola no es determinista en los errores sutiles): una OBJECIÓN es NO LISTO, y sale entera bajo el correo (la frase, la explicación, el literal con su identificador y la propuesta); se arregla cambiando el texto (o marcándolo como opinión si es una lectura) y luego normativa_revisar → normativa_verificar_entrega → otra vez normativa_comprobar_carpeta; si una revisión no se ha podido hacer, tampoco está LISTO. Esta comprobación tarda de 1 a 5 minutos: espera el resultado. La primera revisión reaprovecha la de normativa_verificar_entrega si el texto no ha cambiado. La PRIMERA línea del resultado es el veredicto: «LISTO PARA ENVIAR: N correos verificados; …» o «NO LISTO: K problemas», con la lista entera de problemas por fichero. SOLO se envía si dice LISTO PARA ENVIAR; un NO LISTO se arregla (no se envía ni se maquilla) y se vuelve a comprobar. Los avisos (un .md que no está en preguntas.json, una tanda aún sin archivar) no tumban, pero se leen. Con momento=antes (por defecto), una tanda aún no archivada es AVISO; después del envío, archívala y vuelve a llamar con momento=despues: entonces «no archivada o distinta» es NO LISTO. Solo acepta carpetas bajo D:\\OneDrive\\ICT155.COM\\. Que el contenido sea correcto lo decide Responsable. De solo lectura.', 'inputSchema': {'type': 'object', 'properties': {'carpeta': {'type': 'string', 'maxLength': LARGO_MAXIMO_ARGUMENTO, 'description': 'Ruta absoluta de Windows de la carpeta de la tanda, bajo D:\\OneDrive\\ICT155.COM\\ y sin «..», p. ej. "D:\\OneDrive\\ICT155.COM\\00_Empresa\\Desarrollo_Negocio\\borradores_para_revisar\\2026-10-16_tanda".'}, 'momento': {'type': 'string', 'enum': ['antes', 'despues'], 'description': '«antes» del envío (por defecto): una tanda sin archivar es AVISO. «despues» del envío: sin archivar, o distinta del archivo, es NO LISTO.'}}, 'required': ['carpeta']}}, {'name': 'normativa_vigencia', 'orden': 'vigencia', 'description': 'Vigencia de una norma (o de todas) según la consulta guardada al BOE y a la UE (CELLAR): vigente, derogada (cuándo y por qué norma), modificada después de la versión que tiene la base (con qué norma y si la base la tiene; si la modificación es una DEROGACIÓN, lo dice y avisa de que puede tener efecto diferido y de que hay que leer el acto). Acepta el número a secas ("2022/30"). Si la base no tiene esa norma, lo dice y remite a normativa_buscar. Solo legislación: las guías y normas técnicas no tienen.', 'inputSchema': {'type': 'object', 'properties': {'obra': {'type': 'string', 'description': 'Opcional: la norma (identificador o alias, p. ej. "MID", "RD 244/2016"). Sin ella, todas.'}}}}, {'name': 'normativa_brechas', 'orden': 'brechas', 'description': 'Comprueba contra la base todas las citas de un registro de brechas de una auditoría (fichero .json) y muestra la última revisión de cada brecha: citas verificadas o con problema (inexistentes, ambiguas, literal que no está, norma modificada o derogada) y brechas sin revisión o con la última en no_cumple o parcial. Úsalo tras cada lote de verificación. Que haya citas con ERROR no es un fallo de la herramienta: el informe se devuelve igualmente. Si el registro está mal formado, devuelve todos sus problemas. De las normas con licencia no reproduce texto.', 'inputSchema': {'type': 'object', 'properties': {'registro': {'type': 'string', 'description': 'Ruta absoluta de Windows al registro de brechas, un fichero .json de menos de 2 MB, p. ej. "D:\\ruta\\registro.json".'}}, 'required': ['registro']}}]
TOOL_BY_NAME = {t['name']: t for t in TOOLS}
TOOL_HECHOS = {'name': 'normativa_hechos', 'orden': 'hechos', 'description': 'Entrada por hechos: toda captura es una SUGERENCIA SIN COMPROBAR. Devuelve la consulta como soporte y pregunta antes de evaluar. Si hay varios valores no sugiere ninguno. Reenvíe el mismo texto y las respuestas explícitas acumuladas; puede corregir la sugerencia.', 'inputSchema': {'type': 'object', 'properties': {'pregunta': {'type': 'string'}, 'respuestas': {'type': 'object', 'description': 'Mapa unidad_N.campo a valor JSON confirmado'}, 'hechos': {'type': 'object', 'description': 'Hechos suministrados explícitamente por el usuario'}}, 'required': ['pregunta'], 'additionalProperties': False}}
TOOL_BY_NAME[TOOL_HECHOS['name']] = TOOL_HECHOS

def _hechos_habilitados():
    return controles.modo('entrada_hechos') != 'apagado'

def _argumentos_hechos(arguments):
    if not isinstance(arguments, dict):
        raise ArgumentoMalo('los argumentos deben ser un objeto')
    _pregunta(arguments)
    if set(arguments) - {'pregunta', 'hechos', 'respuestas'}:
        raise ArgumentoMalo('argumento no admitido')
    for campo in ('hechos', 'respuestas'):
        if campo in arguments and (not isinstance(arguments[campo], dict)):
            raise ArgumentoMalo(f'{campo} debe ser un objeto de valores JSON')

def _hechos_apagados(pregunta):
    """Respuesta inerte del contrato R28-C4/4, sin ejecutar la CLI ni cargar tablas."""
    return json.dumps({'version': 'R28-C4/4', 'pregunta': pregunta, 'modo': 'apagado', 'ensayo': False, 'publicable': False, 'alcance': 'Toda captura es una SUGERENCIA SIN COMPROBAR. Vía documental pendiente de confirmación y cotejo.', 'estado': 'apagado', 'hechos': [], 'hechos_faltantes': [], 'celdas_reglas': [], 'resultado': 'depende', 'preceptos': [], 'siguiente_pregunta': None, 'camino': {'tipo': 'control_apagado'}}, ensure_ascii=False, indent=2)

class ArgumentoMalo(ValueError):
    pass

def _texto(arguments: dict, clave: str, obligatorio: bool=True) -> str | None:
    v = arguments.get(clave)
    if v is None or (isinstance(v, str) and (not v.strip())):
        if obligatorio:
            raise ArgumentoMalo(f"falta '{clave}'")
        return None
    if not isinstance(v, str):
        raise ArgumentoMalo(f"'{clave}' tiene que ser texto")
    if len(v) > LARGO_MAXIMO_ARGUMENTO or '\x00' in v:
        raise ArgumentoMalo(f"'{clave}' es demasiado largo")
    return v.strip()

def _borrador(arguments: dict, clave: str='borrador', maximo: int=LARGO_MAXIMO_BORRADOR) -> str:
    """El borrador a revisar (o, con `clave="respuesta"`, la respuesta a verificar), tal cual (sin recortar los espacios del
    principio: el informe da el numero de linea de cada cita y tiene que ser el del texto que mando el hilo)."""
    v = arguments.get(clave)
    if v is None or (isinstance(v, str) and (not v.strip())):
        raise ArgumentoMalo(f"falta '{clave}'")
    if not isinstance(v, str):
        raise ArgumentoMalo(f"'{clave}' tiene que ser texto")
    if '\x00' in v:
        raise ArgumentoMalo(f"'{clave}' contiene caracteres no válidos")
    if len(v) > maximo:
        raise ArgumentoMalo(f"'{clave}' es demasiado largo ({len(v)} caracteres; el máximo es {maximo}): revísalo por partes")
    return v

def _respuesta(arguments: dict) -> str:
    """La respuesta final a verificar (`normativa_verificar_entrega`): el borrador revisado más su línea de sello."""
    return _borrador(arguments, 'respuesta', LARGO_MAXIMO_RESPUESTA)

def _pregunta(arguments: dict) -> str:
    """La pregunta de Responsable (R20), tal cual: entera y sin recortar (el tema se detecta por sus palabras). Obligatoria en
    `normativa_verificar_entrega` y en `normativa_obligatorios`; nunca va como argumento de la orden ni al registro en claro."""
    v = arguments.get('pregunta')
    if v is None or (isinstance(v, str) and (not v.strip())):
        raise ArgumentoMalo("falta 'pregunta': la pregunta de Responsable, tal cual y entera (si pegó un correo, con el correo)")
    if not isinstance(v, str):
        raise ArgumentoMalo("'pregunta' tiene que ser texto")
    if '\x00' in v:
        raise ArgumentoMalo("'pregunta' contiene caracteres no válidos")
    if len(v) > LARGO_MAXIMO_PREGUNTA:
        raise ArgumentoMalo(f"'pregunta' es demasiado larga ({len(v)} caracteres; el máximo es {LARGO_MAXIMO_PREGUNTA}): quita lo que no sea la pregunta (firmas, el historial de un correo)")
    return v

def _registro(arguments: dict) -> str:
    """La ruta del registro de brechas, validada: absoluta, .json, un fichero que existe y pesa menos de 2 MB."""
    v = _texto(arguments, 'registro')
    if not os.path.isabs(v):
        raise ArgumentoMalo("'registro' tiene que ser una ruta absoluta (p. ej. D:\\ruta\\registro.json)")
    if not v.casefold().endswith('.json'):
        raise ArgumentoMalo("'registro' tiene que ser un fichero .json")
    try:
        st = os.stat(v)
    except OSError:
        raise ArgumentoMalo(f"'registro' no existe o no se puede leer: {v}") from None
    if not stat.S_ISREG(st.st_mode):
        raise ArgumentoMalo(f"'registro' no es un fichero: {v}")
    if st.st_size >= LARGO_MAXIMO_REGISTRO:
        raise ArgumentoMalo(f"'registro' es demasiado grande ({st.st_size} bytes; el máximo son {LARGO_MAXIMO_REGISTRO - 1})")
    return v

def _carpeta(arguments: dict) -> str:
    """La carpeta de la tanda de `normativa_comprobar_carpeta` (R24), validada y RESUELTA: ruta absoluta de Windows con unidad (nada de rutas de red ni con el
    prefijo `\\\\?\\`), sin «..», sin caracteres que Windows no admite en un nombre, que exista, que sea una carpeta y que, ya resuelta (enlaces y nombres
    cortos incluidos), quede BAJO `RAIZ_PERMITIDA`. Lo que se pasa a la orden es la ruta resuelta, no la que escribió el hilo."""
    v = _texto(arguments, 'carpeta')
    if not re.match('^[A-Za-z]:[\\\\/]', v):
        raise ArgumentoMalo("'carpeta' tiene que ser una ruta absoluta de Windows con su unidad (p. ej. D:\\OneDrive\\ICT155.COM\\00_Empresa\\...)")
    if '..' in re.split('[\\\\/]+', v):
        raise ArgumentoMalo("'carpeta' no puede llevar «..»")
    if re.search('[<>"|?*\\x00-\\x1f]', v) or ':' in v[2:]:
        raise ArgumentoMalo("'carpeta' lleva caracteres que no son de una ruta de carpeta")
    resuelta = os.path.realpath(v)
    raiz = os.path.realpath(RAIZ_PERMITIDA)
    a, b = (os.path.normcase(resuelta), os.path.normcase(raiz))
    try:
        dentro = a != b and os.path.commonpath([a, b]) == b
    except ValueError:
        dentro = False
    if not dentro:
        raise ArgumentoMalo(f"'carpeta' tiene que estar bajo {RAIZ_PERMITIDA}\\ (la biblioteca de ICT155): esa ruta no")
    if not os.path.isdir(resuelta):
        raise ArgumentoMalo("'carpeta' no existe o no es una carpeta")
    return resuelta

def _momento(arguments: dict) -> str:
    """`antes` (por defecto) o `despues` del envío. Se admite «después» con tilde."""
    v = arguments.get('momento')
    if v is None or (isinstance(v, str) and (not v.strip())):
        return 'antes'
    if not isinstance(v, str):
        raise ArgumentoMalo("'momento' tiene que ser texto: «antes» o «despues»")
    m = ''.join((c for c in unicodedata.normalize('NFD', v.strip().casefold()) if not unicodedata.combining(c)))
    if m not in ('antes', 'despues'):
        raise ArgumentoMalo("'momento' tiene que ser «antes» o «despues» (del envío)")
    return m

def argumentos_de_la_orden(nombre: str, arguments: dict) -> list[str]:
    """La lista de argumentos de `ict155.cli` para una herramienta. Solo ordenes de consulta."""
    tool = TOOL_BY_NAME[nombre]
    orden = tool['orden']
    assert orden in ORDENES
    if orden == 'hechos':
        _argumentos_hechos(arguments)
        return ['hechos', '-', '--entrada-json']
    if orden == 'buscar':
        limite = arguments.get('limite', 10)
        if isinstance(limite, bool) or not isinstance(limite, int):
            raise ArgumentoMalo("'limite' tiene que ser un número entero")
        limite = max(1, min(30, limite))
        return ['buscar', _texto(arguments, 'texto'), '--limite', str(limite), '--json', '--con-obras']
    if orden == 'cita':
        args = ['cita', _texto(arguments, 'identificador')]
        if arguments.get('localizar') is True:
            args.append('--localizar')
        if arguments.get('contexto') is not False:
            args.append('--contexto')
        return args + ['--json']
    if orden == 'fundamento':
        args = ['fundamento', _texto(arguments, 'frase'), '--json']
        obra = _texto(arguments, 'obra', obligatorio=False)
        if obra:
            args[2:2] = ['--obra', obra]
        return args
    if orden == 'cotejar':
        return ['cotejar', _texto(arguments, 'identificador'), _texto(arguments, 'afirmacion'), '--json']
    if orden == 'revisar':
        _borrador(arguments)
        return ['revisar', '-', '--json']
    if orden == 'verificar-entrega':
        _respuesta(arguments)
        _pregunta(arguments)
        return ['verificar-entrega', '-', '--json', '--entrada-json', '--revision-independiente', '--pasadas', '2']
    if orden == 'obligatorios':
        _pregunta(arguments)
        return ['obligatorios', '-', '--json']
    if orden == 'obras':
        _texto(arguments, 'filtro', obligatorio=False)
        return ['obras']
    if orden == 'comprobar-carpeta':
        return ['comprobar-carpeta', '--momento', _momento(arguments), '--json', '--revision-independiente', '--pasadas', '2', '--', _carpeta(arguments)]
    if orden == 'brechas':
        return ['brechas', '--ambito', 'publico', '--', _registro(arguments)]
    if orden == 'vigencia':
        obra = _texto(arguments, 'obra', obligatorio=False)
        return ['vigencia', '--json'] + (['--', obra] if obra else [])
    return ['info']

def entrada_de_la_orden(nombre: str, arguments: dict) -> str | None:
    """Lo que la orden lee por su entrada estandar: el borrador de `revisar`, la respuesta y la pregunta de `verificar-entrega` (un objeto JSON,
    solo ASCII: ningun caracter ni salto de linea se transforma por el camino), la pregunta de `obligatorios`; las demas, nada."""
    orden = TOOL_BY_NAME[nombre]['orden']
    if orden == 'hechos':
        _argumentos_hechos(arguments)
        return json.dumps(arguments)
    if orden == 'revisar':
        return _borrador(arguments)
    if orden == 'verificar-entrega':
        return json.dumps({'respuesta': _respuesta(arguments), 'pregunta': _pregunta(arguments)})
    if orden == 'obligatorios':
        return _pregunta(arguments)
    return None

def ejecutar(args: list[str], entrada: str | None=None) -> tuple[int, str, str]:
    """Una orden de consulta de `ict155.cli`, en un proceso aparte y sobre la base de produccion.

    `entrada` es el texto que la orden lee por su entrada estandar (el borrador de `revisar`). Sin
    ella la orden NO hereda la del servidor, que es la tuberia JSON-RPC con Cowork: se le da una
    entrada vacia (`DEVNULL`), para que nada de lo que llegue por ahi pueda leerlo un hijo."""
    assert args and args[0] in ORDENES, args
    entorno = {k: v for k, v in os.environ.items() if k not in ('ICT155_DATOS', 'ICT155_LAYOUT_GUIAS')}
    entorno['PYTHONIOENCODING'] = 'utf-8'
    entorno.setdefault('ICT155_REVISION_CACHE_DIR', os.path.join(AUDIT_DIR, 'revision_independiente'))
    opciones = {'input': entrada.encode('utf-8')} if entrada is not None else {'stdin': subprocess.DEVNULL}
    r = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'ict155.cli', *args], cwd=PROYECTO, env=entorno, capture_output=True, timeout=TIEMPO_MAXIMO_POR_ORDEN.get(args[0], TIEMPO_MAXIMO), **opciones)

    def _a_texto(b: bytes | None) -> str:
        return (b or b'').decode('utf-8', errors='replace').replace('\r\n', '\n')
    return (r.returncode, _a_texto(r.stdout), _a_texto(r.stderr))

def _huella(s: str | None) -> str:
    if not s:
        return '-'
    return f"len={len(s)}:sha={hashlib.sha256(s.encode('utf-8')).hexdigest()[:10]}"

def audit(nombre: str, arguments: dict, estado: str, ms: int) -> None:
    try:
        os.makedirs(AUDIT_DIR, exist_ok=True)
        ident = arguments.get('identificador') or arguments.get('obra') or '-'
        libre = arguments.get('texto') or arguments.get('frase') or arguments.get('afirmacion') or arguments.get('filtro') or arguments.get('borrador') or arguments.get('respuesta') or arguments.get('registro') or arguments.get('carpeta')
        pregunta = arguments.get('pregunta')
        campo_pregunta = '\tpregunta=%s' % _huella(pregunta if isinstance(pregunta, str) else None) if 'pregunta' in arguments else ''
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write('%s\t%s\tid=%s\ttexto=%s%s\testado=%s\tms=%d\n' % (datetime.datetime.now().isoformat(timespec='seconds'), nombre, str(ident)[:120].replace('\t', ' '), _huella(libre if isinstance(libre, str) else None), campo_pregunta, estado, ms))
    except Exception:
        pass

def log_err(msg: str) -> None:
    try:
        sys.stderr.write('[normativa_ict155] %s\n' % msg)
        sys.stderr.flush()
    except Exception:
        pass

def _corta(texto: str) -> str:
    if len(texto) <= LARGO_MAXIMO_TEXTO:
        return texto
    return texto[:LARGO_MAXIMO_TEXTO] + f'\n[… cortado: el precepto tiene {len(texto)} caracteres; pide una subdivisión más concreta (p. ej. …/ap.2) para el resto]'

def _texto_contexto(ctx: dict) -> str:
    """El contexto obligatorio de un precepto, para leerlo. Es `ict155.contexto_norma.texto` con el mismo
    formato, escrito aqui para que el servidor siga sin importar nada de `ict155` (una prueba compara los dos)."""
    if not ctx or len(ctx) <= 1:
        return ''
    out = ['', '──── CONTEXTO OBLIGATORIO (léelo antes de concluir nada de este precepto) ────']
    for p in ctx.get('ambito', []):
        out += [f"ÁMBITO · {p['identificador']} ({p['etiqueta']}, p. {p['paginas']})", f"  {p['texto']}"]
        if p['texto'].endswith('…'):
            out.append(f"  (recortado: cita {p['identificador']} para leerlo entero)")
    for p in ctx.get('definiciones', []):
        out += [f"DEFINICIÓN de «{p['termino']}» · {p['identificador']} (p. {p['paginas']})", f"  {p['texto']}"]
    if 'padre' in ctx:
        p = ctx['padre']
        out += [f"PADRE · {p['identificador']} ({p['etiqueta']}{(' — ' + p['titulo'] if p.get('titulo') else '')})", f"  {p['texto']}"]
    for x in ctx.get('remisiones', []):
        if 'identificador' in x:
            out.append(f"REMITE A · {x['identificador']} ({x['etiqueta']}{(' — ' + x['titulo'] if x.get('titulo') else '')})")
        else:
            out.append(f"REMITE A · {x['norma']} — " + ('en la base' + (f" ({x['obra']})" if x.get('obra') else '') if x['en_la_base'] else 'NO ESTÁ EN LA BASE'))
    r = ctx.get('remitentes')
    if r:
        mas = f", … (y {r['total'] - len(r['rutas'])} más)" if r['total'] > len(r['rutas']) else ''
        out.append(f"REMITEN A ESTE PRECEPTO · {r['obra']} ({r['total']}): {', '.join(r['rutas'])}{mas}")
        out += [f"  · {e['ruta']} — {e['fragmento']}" for e in r['ejemplos']]
    return '\n'.join(out)

def _texto_vigencia(v: dict | None) -> str:
    """El bloque VIGENCIA. Es `ict155.vigencia.texto` con el mismo formato, escrito aqui para que el servidor siga
    sin importar nada de `ict155` (una prueba compara los dos)."""
    if not v:
        return ''
    cab = f"──── VIGENCIA ({v.get('fuente') or 'sin fuente'}, consultada {(v.get('consultado') or 'nunca')[:10]}) ────"
    lineas = [cab]
    if v.get('estado'):
        version = v.get('fecha_version_base')
        lineas.append(f"  Estado: {v['estado']}." + (f' Versión de la base: {version}.' if version else ''))
    if v['avisos']:
        lineas += [f'  AVISO: {a}' for a in v['avisos']]
    else:
        lineas.append('  Sin modificaciones posteriores a la versión de la base según la fuente oficial.')
    if v.get('estado') == 'derogada' and 'sucesion' in v:
        suc = v['sucesion']
        if suc:
            lineas.append('  Contenido equivalente vigente:')
            if any((p.get('apartado') for p in suc)):
                lineas.append(f'    {NOTA_DE_APARTADOS_SUCESION}')
            lineas += [f"    - {('[apartado ' + p['apartado'] + '] ' if p.get('apartado') else '')}{p['sucesor']} ({p.get('equivalencia') or '?'}): {p.get('nota') or ''}".rstrip() for p in suc]
        else:
            lineas.append(f'  Contenido equivalente vigente: {SIN_ENTRADA_SUCESION}.')
    if v.get('aviso_fuente'):
        lineas.append(f"  {v['aviso_fuente']}.")
    return '\n'.join(lineas)
AVISO_BOE_HISTORIAL = 'Fuente: Agencia Estatal Boletín Oficial del Estado; el texto consolidado es informativo'

def _sin_tildes(s: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

def _con_articulo(nombre: str) -> str:
    primera = _sin_tildes(nombre.split()[0]).lower() if nombre.split() else ''
    if primera in ('orden', 'ley', 'resolucion', 'instruccion', 'circular', 'directiva', 'correccion'):
        return 'la ' + nombre
    if primera in ('real', 'decreto', 'reglamento', 'acuerdo', 'convenio'):
        return 'el ' + nombre
    return nombre

def _quien_dio(r: dict) -> str:
    if r['en_la_base'] and r.get('cita_como'):
        return f"{_con_articulo(r['cita_como'])} ({r['id_norma']})"
    if r['en_la_base']:
        return f"la norma {r['id_norma']}"
    return f"la norma {r['id_norma']} (que la base NO tiene)"

def _desde_historial(r: dict, verbo: str='vigente desde') -> str:
    if r.get('fecha_vigencia'):
        return f"{verbo} {r['fecha_vigencia']}"
    return f"publicada el {r['fecha_publicacion']}" if r.get('fecha_publicacion') else ''

def _anterior_historial(r: dict) -> str:
    if r['original']:
        return 'original' + (f' ({_desde_historial(r)})' if _desde_historial(r) else '')
    nombre = f"{r['cita_como']} ({r['id_norma']})" if r.get('cita_como') else f"{r['id_norma']}" + ('' if r['en_la_base'] else ' (la base NO tiene esa norma)')
    return nombre + (f", {_desde_historial(r, 'desde')}" if _desde_historial(r, 'desde') else '')

def _texto_historial(h: dict | None) -> str:
    """El bloque REDACCIÓN. Es `ict155.historial_boe.texto` con el mismo formato, escrito aqui para que el servidor siga sin importar
    nada de `ict155` (una prueba compara los dos)."""
    if not h:
        return ''
    lineas = [f"──── REDACCIÓN (BOE, consultada {(h.get('consultado') or 'nunca')[:10]}) ────"]
    if h.get('estado') == 'ok':
        if h.get('ascendiente'):
            titulo = h['bloque'].get('titulo')
            lineas.append(f"  El BOE no da versiones de {h['ruta']} por separado: este es el historial de su ascendiente {h['ruta_bloque']}" + (f' («{titulo}»)' if titulo else '') + '.')
        reds, vigente = (h['redacciones'], h.get('vigente'))
        if vigente is not None:
            v = reds[vigente]
            desde = _desde_historial(v)
            anteriores = reds[:vigente]
            if v['original'] and (not anteriores):
                lineas.append('  Redacción original, sin modificaciones' + (f' ({desde}).' if desde else '.'))
            elif v['original']:
                lineas.append('  Redacción vigente: la original' + (f', {desde}.' if desde else '.'))
            else:
                base = f"La base tiene esa norma: se cita como «{v['cita_como']}::…»." if v['en_la_base'] and v.get('cita_como') else ''
                lineas.append(f'  Redacción vigente: dada por {_quien_dio(v)}' + (f', {desde}.' if desde else '.') + (f' {base}' if base else ''))
            if anteriores:
                tiene = h.get('base_tiene_la_vigente')
                nota = 'la base solo guarda la vigente' if tiene else 'la base guarda una anterior a la vigente: ver el AVISO' if tiene is False else 'la base guarda una sola de ellas'
                lineas.append(f'  Redacciones anteriores ({nota}): ' + '; '.join((_anterior_historial(r) for r in anteriores)) + '.')
        for r in reds:
            if r['futura']:
                lineas.append(f"  Redacción futura: dada por {_quien_dio(r)}, vigente desde {r.get('fecha_vigencia') or '?'} (aún no en vigor).")
    for a in h.get('avisos') or []:
        lineas.append(f'  AVISO: {a}')
    if h.get('estado') == 'ok':
        lineas.append(f'  {AVISO_BOE_HISTORIAL}.')
    return '\n'.join(lineas)

def _cargar_limites() -> tuple[list[tuple[str, 're.Pattern', str]], list[str]]:
    """(preceptos, generales) de `limites_conocidos.json`. Si falta o esta roto, o una entrada esta mal, se
    registra el error y se sigue sin ella: la extension responde igual que sin el fichero."""
    try:
        datos = json.loads(almacen.leer(LIMITES_JSON, encoding='utf-8'))
        if not isinstance(datos, dict):
            raise ValueError('el JSON no es un objeto')
    except (OSError, ValueError) as e:
        log_err(f'limites_conocidos.json no se puede leer ({e}): se responde sin límites conocidos')
        return ([], [])
    preceptos = []
    for i, e in enumerate(datos.get('preceptos') or []):
        try:
            if not all((isinstance(e.get(k), str) and e[k] for k in ('obra', 'ruta', 'aviso'))):
                raise ValueError('faltan obra, ruta o aviso')
            preceptos.append((e['obra'].casefold(), re.compile(e['ruta']), e['aviso']))
        except (AttributeError, ValueError, re.error) as ex:
            log_err(f'limites_conocidos.json: la entrada {i} de «preceptos» se ignora ({ex})')
    generales = datos.get('generales')
    generales = [g for g in generales if isinstance(g, str) and g.strip()] if isinstance(generales, list) else []
    return (preceptos, generales)

def _avisos_de_limites(obras: list, ruta: str | None) -> list[str]:
    """Los avisos de las entradas que casan: la obra es subcadena (sin mayusculas) de alguno de los textos
    de `obras` (identificador canonico, titulo, alias escrito) y la ruta casa con la expresion."""
    if not ruta:
        return []
    pajar = [o.casefold() for o in obras if isinstance(o, str) and o]
    return [aviso for obra, patron, aviso in _cargar_limites()[0] if any((obra in p for p in pajar)) and patron.search(ruta)]

def _aviso_documento_entero(d: dict) -> list[str]:
    """Regla general: el precepto ocupa el documento entero (de la pagina 1 a la ultima, en un documento de mas
    de 3): la base no sabe en que pagina esta. Sin el numero de paginas del documento en la salida, no se aplica."""
    total = next((d[k] for k in CLAVES_PAGINAS_DOCUMENTO if isinstance(d.get(k), int) and (not isinstance(d.get(k), bool))), None)
    if total is not None and total > 3 and (d.get('pagina_inicio') == 1) and (d.get('pagina_fin') == total):
        return [AVISO_SIN_PAGINA]
    return []

def _texto_limites(avisos: list[str], prefijo: str='') -> str:
    if not avisos:
        return ''
    return '\n'.join(['', '──── LÍMITE CONOCIDO DE ESTE PRECEPTO ────'] + [f'  {prefijo}AVISO: {a}' for a in avisos])

def _texto_limites_generales() -> str:
    generales = _cargar_limites()[1]
    if not generales:
        return ''
    return '\n'.join(['', '──── LÍMITES GENERALES ────'] + [f'- {g}' for g in generales] + ['', f'Lista completa y fechada: {LIMITES_DE_USO}'])

def _paginas(inicio, fin) -> str:
    """«página 58» si el precepto cabe en una, «páginas 58-59» si cruza."""
    if inicio is not None and (fin is None or fin == inicio):
        return f'página {inicio}'
    return f'páginas {inicio}-{fin}'
RE_RESUMEN_CITAS = re.compile('Citas: \\d+\\. Verificadas: (\\d+)\\. Con aviso: (\\d+)\\. Con error: (\\d+)\\.')
_ORDEN_NIVEL = {'ERROR': 0, 'AVISO': 1, 'OK': 2}

def _formatear_revision(d: dict) -> tuple[str, str]:
    """(texto para el modelo, estado para el registro) de la revision de un borrador."""
    r = d.get('resumen') or {}
    ok, avisos, errores, total = (int(r.get(k) or 0) for k in ('ok', 'avisos', 'errores', 'total'))
    sello = d.get('linea') or f'Comprobado por la base: {ok} correctas, {avisos} avisos, {errores} errores (de {total}).'
    lineas = [sello, f"Base: huella {(d.get('huella_base') or '?')[:8]}, {d.get('preceptos_base') or '?'} preceptos."]
    if not total:
        lineas.append('No se ha encontrado ninguna cita que comprobar: los identificadores van como `obra::ruta` entre comillas invertidas y los literales entre «» o en cita de bloque (>).')
    comprobaciones = sorted(d.get('comprobaciones') or [], key=lambda c: (_ORDEN_NIVEL.get(c.get('nivel'), 9), c.get('linea') or 0))
    if comprobaciones:
        lineas.append('')
    for c in comprobaciones:
        lineas.append(f"{c.get('nivel')} · {c.get('tipo')} · línea {c.get('linea')} · {c.get('cita')} → {c.get('detalle')}")
    sello = d.get('sello')
    return ('\n'.join(lineas), f'OK={ok};AVISO={avisos};ERROR={errores}' + (f';SELLO={sello}' if sello else ''))

def _motivo_incompleta(f: dict) -> str:
    """Es `ict155.completitud.Falta.motivo` con el mismo formato (una prueba compara los dos). R27-S7b (18-oct-2026,
    hallazgo 4): con `cita_que_no_cubre` (solo `cubre_estricto` en «bloquea», con un ancla ya validada), añade qué se citó
    que no basta; antes se perdía aquí aunque la CLI sí lo decía."""
    base = f"INCOMPLETA: falta citar {f.get('identificador')} ({f.get('por_que')}) [tema «{f.get('nombre')}»]"
    cita = f.get('cita_que_no_cubre')
    return base if not cita else base + f': citar {cita} no lo cubre'

def _lineas_de_completitud(d: dict) -> list[str]:
    """Lo que R20 dice de la pregunta. Es `ict155.entrega.Veredicto.lineas_de_completitud` con el mismo formato, escrito aqui para que el
    servidor siga sin importar nada de `ict155` (una prueba compara los dos)."""
    if not d.get('pregunta_dada'):
        return ['Nota: sin la pregunta no se ha comprobado que la respuesta esté completa.']
    temas, nombres, faltan = (d.get('temas') or [], d.get('temas_nombres') or [], d.get('faltan') or [])
    if not temas:
        return ['Temas de la pregunta: ninguno de la lista de lo obligatorio (cowork/temas_obligatorios.json). ' + NO_EXHAUSTIVA]
    out = ['Temas de la pregunta (lista de lo obligatorio): ' + '; '.join((f'«{n}» [{i}]' for i, n in zip(temas, nombres))) + '.']
    if faltan:
        out += ['Lo que falta se puede citar para aplicarlo o para explicar por qué no aplica; callarlo hace la entrega NO VÁLIDA (INCOMPLETA):'] + [f'  - {_motivo_incompleta(f)}' for f in faltan]
    else:
        out.append('La respuesta cita todos los obligatorios de esos temas; la lista no es exhaustiva, así que eso no prueba que la respuesta esté completa.')
    return out

def _lineas_de_revision(r: dict) -> list[str]:
    """Lo que se cuenta de la revisión independiente (R23, 1.11.0). Es `ict155.revision_independiente.Resultado.lineas` con el mismo formato, escrito aquí para que
    el servidor siga sin importar nada de `ict155` (una prueba compara los dos). Cada objeción trae su motivo ya escrito por `ict155` (`motivo`)."""
    if not r.get('hecha'):
        return [f"Revisión independiente: NO SE HA PODIDO HACER ({r.get('fallo') or 'sin causa'}). La entrega no vale sin ella: vuelve a verificar y, si persiste, avisa a Responsable."]
    descartadas = int(r.get('n_descartadas') or 0)
    descartes = f'; el código descartó {descartadas} sin pruebas verificables' if descartadas else ''
    if r.get('omitida'):
        return [f"Revisión independiente: sin objeciones ({r['omitida']}){descartes}."]
    pasadas = r.get('pasadas') if isinstance(r.get('pasadas'), int) and (not isinstance(r.get('pasadas'), bool)) else 1
    cab = (f'{pasadas} pasadas: ' if pasadas > 1 else '') + f"{r.get('modelo')}, {round(r.get('segundos') or 0)} s, {('en caché' if r.get('en_cache') else 'nueva')}"
    objeciones = r.get('objeciones') or []
    if not objeciones:
        return [f'Revisión independiente: sin objeciones ({cab}){descartes}.']
    n = len(objeciones)
    out = [f"Revisión independiente ({cab}): {n} {('objeción' if n == 1 else 'objeciones')}{descartes}. Cada OBJECIÓN se resuelve cambiando el texto (o marcándolo como opinión si es una lectura); si crees que una objeción es errónea, díselo a Responsable con la objeción entera; no se entrega con objeciones:"]
    return out + [f"  {i}. {o.get('motivo')}" for i, o in enumerate(objeciones, 1)]

def _formatear_obligatorios(d: dict) -> tuple[str, str]:
    """(texto para el modelo, estado para el registro) de lo obligatorio de una pregunta. Es `ict155.completitud.texto` con el mismo
    formato, escrito aqui para que el servidor siga sin importar nada de `ict155` (una prueba compara los dos).

    R27-S7b (18-oct-2026, hallazgos 0 y 4): `hoja_bloquea`, si viene en un obligatorio (solo con `cubre_estricto` en
    «bloquea» y un ancla ya validada por Responsable: ver `ict155.completitud.a_dict`), se enseña aparte; una `ict155.cli`
    anterior no manda esa clave y no cambia nada.

    R27-S7d (18-oct-2026, decisión de Responsable «máximo detalle»): `hoja_bloquea_regla` == "todos" cambia la frase a «hay
    que citar TODOS»; un obligatorio `solo_con` que `ict155.completitud.a_dict` ya ha dejado fuera (apagado o sombra)
    no llega aquí: `obligatorios` solo trae los visibles, como con `n_obligatorios`.

    R27-S7f (18-oct-2026, hallazgo 7 de REVISION_AG8.md): con `hoja_bloquea_regla` == "todos", cada hoja de
    `hoja_bloquea` lleva debajo su propio motivo (`hoja_bloquea_por_que`, clave->texto) en una línea con «·», y se
    omite el «(también vale: ...)» de las otras normas de `acepta` (contradecía «hay que citar TODOS»). Ver
    `ict155.completitud.texto` sobre el mismo formato."""
    temas = d.get('temas') or []
    estado = f"TEMAS={','.join((t.get('id') or '?' for t in temas)) or '-'};OBLIGATORIOS={sum((len(t.get('obligatorios') or []) for t in temas))}"
    if not temas:
        return ('La pregunta no cae en ningún tema de la lista de lo obligatorio. ' + NO_EXHAUSTIVA, estado)
    n = len(temas)
    out = [f"La pregunta cae en {n} {('tema' if n == 1 else 'temas')} de la lista de lo obligatorio. {INSTRUCCION} {NO_EXHAUSTIVA}"]
    for t in temas:
        obligatorios = t.get('obligatorios') or []
        if not obligatorios:
            continue
        out += ['', f"TEMA «{t.get('nombre')}» [{t.get('id')}]"]
        for o in obligatorios:
            acepta = o.get('acepta') or [o.get('identificador')]
            hoja = o.get('hoja_bloquea') or []
            regla_todos = bool(hoja and o.get('hoja_bloquea_regla') == 'todos')
            otros = f" (también vale: {', '.join(acepta[1:])})" if len(acepta) > 1 and (not regla_todos) else ''
            linea = f"  - {o.get('identificador')}{otros} — {o.get('por_que')}"
            if hoja:
                if regla_todos:
                    alternativa = 'o el artículo entero'
                    if len({h.partition('::')[0] for h in hoja}) > 1:
                        articulos = list(dict.fromkeys((f"{obra}::art.{ruta.split('.')[1]}" for obra, _, ruta in (h.partition('::') for h in hoja) if ruta.startswith('art.'))))
                        alternativa = f"o los artículos enteros {' y '.join(articulos)}; cada artículo entero cubre solo las hojas de su propia obra"
                    linea += f" [en «bloquea» hay que citar TODOS: {', '.join(hoja)} ({alternativa})]"
                else:
                    linea += f" [en «bloquea» solo cubre citar {', '.join(hoja)}, o el artículo entero]"
            out.append(linea)
            if regla_todos:
                por_que_hoja = o.get('hoja_bloquea_por_que') or {}
                for h in hoja:
                    out.append(f"      · {h} — {por_que_hoja.get(h, o.get('por_que'))}")
    return ('\n'.join(out), estado)

def _formatear_verificacion(d: dict) -> tuple[str, str]:
    """(texto para el modelo, estado para el registro) de la verificacion de una entrega. Es `ict155.entrega.Veredicto.texto` con el
    mismo formato, escrito aqui para que el servidor siga sin importar nada de `ict155` (una prueba compara los dos): el veredicto en la
    primera linea, la linea de sello correcta para ese texto y los errores y avisos."""
    correcta = d.get('sello_correcto') or ''
    lineas = [d.get('primera_linea') or d.get('veredicto') or 'ENTREGA NO VÁLIDA', ''] + _lineas_de_completitud(d) + ['']
    if d.get('revision_independiente'):
        lineas += _lineas_de_revision(d['revision_independiente']) + ['']
    lineas += ['Línea de sello correcta para este texto (cópiala tal cual, entera y con su código, como última línea de la respuesta; si cambias una sola palabra del texto, vuelve a revisar):', correcta]
    presentes = d.get('sello_presente') or []
    if presentes and presentes != [correcta]:
        lineas += ['', 'Línea de sello que lleva la respuesta:'] + presentes
    r = d.get('resumen') or {}
    citas = r.get('citas') or {}
    if d.get('valida') and (not sum((int(v or 0) for v in citas.values()))) and (not r.get('normativas')):
        lineas += ['', 'Nota: la revisión no ha encontrado ninguna cita ni afirmación normativa: no ha comprobado nada.']
    filas = d.get('comprobaciones') or []
    if filas:
        lineas.append('')
        lineas += [f"{c.get('nivel')} · {c.get('tipo')} · línea {c.get('linea')} · {c.get('cita')} → {c.get('detalle')}" for c in filas]
    estado = d.get('estado') or ('VALIDA' if d.get('valida') else 'NO_VALIDA')
    pasadas = (d.get('revision_independiente') or {}).get('pasadas')
    if isinstance(pasadas, int) and (not isinstance(pasadas, bool)) and (pasadas > 1):
        estado += f';PASADAS={pasadas}'
    return ('\n'.join(lineas), estado)

def formatear(nombre: str, args: list[str], salida: str, arguments: dict) -> tuple[bool, str, str]:
    """(ok, texto para el modelo, estado para el registro)."""
    orden = args[0]
    if orden in ('obras', 'info'):
        lineas = salida.strip().splitlines()
        filtro = (arguments.get('filtro') or '').strip().casefold()
        if orden == 'obras' and filtro:
            lineas = [l for l in lineas if filtro in l.casefold()]
            if not lineas:
                return (True, f"Ninguna obra contiene «{arguments.get('filtro')}».", 'VACIO')
        if orden == 'info' and (generales := _texto_limites_generales()):
            lineas.append(generales)
        return (True, '\n'.join(lineas), 'OK')
    if orden == 'brechas':
        m = RE_RESUMEN_CITAS.search(salida)
        return (True, salida.strip(), f'VERIFICADAS={m.group(1)};AVISO={m.group(2)};ERROR={m.group(3)}' if m else 'OK')
    d = json.loads(salida)
    if orden == 'hechos':
        return (True, salida.removesuffix('\n'), d['estado'])
    if orden == 'buscar':
        obras = d.get('obras') or [] if isinstance(d, dict) else []
        d = d.get('resultados') or [] if isinstance(d, dict) else d
        cabecera = ''
        if obras:
            cabecera = f"OBRAS DE LA BASE que se llaman «{arguments.get('texto')}» (primero esto: la base TIENE estas normas; cítalas con normativa_cita):\n" + '\n'.join(('\n'.join(o.get('lineas') or [o.get('identificador') or '?']) for o in obras)) + '\n\n'
        if not d:
            if obras:
                return (True, cabecera + 'Sin más resultados para ese texto en el contenido de la base (ámbito público).', 'OBRAS')
            return (True, 'Sin resultados para ese texto en la base (ámbito público).', 'VACIO')
        partes = []
        for f in d:
            ident = f"{f.get('obra')}::{f.get('ruta_estructural')}"
            aviso = '  [norma con licencia: no copiar su texto a terceros]' if f.get('clase_derechos') == 'licenciado' else ''
            partes.append(f"- {ident}  (p. {f.get('pagina_inicio')}){aviso}\n  {f.get('etiqueta_humana') or ''}. {f.get('titulo') or ''}\n  {(f.get('fragmento') or '').strip()}")
        return (True, cabecera + f'{len(d)} resultado(s). Para el literal, normativa_cita con el identificador:\n\n' + '\n'.join(partes), 'OK')
    if orden == 'revisar':
        texto, estado = _formatear_revision(d)
        return (True, texto, estado)
    if orden == 'verificar-entrega':
        texto, estado = _formatear_verificacion(d)
        return (True, texto, estado)
    if orden == 'obligatorios':
        texto, estado = _formatear_obligatorios(d)
        return (True, texto, estado)
    if orden == 'comprobar-carpeta':
        estado = f"REVCARPETA={('LISTO' if d.get('listo') is True else 'NO_LISTO')};N={int(d.get('n') or 0)};K={int(d.get('k') or 0)}"
        rev = d.get('revision_independiente')
        if isinstance(rev, dict):

            def _n(v) -> int:
                return v if isinstance(v, int) and (not isinstance(v, bool)) and (v >= 0) else 0
            estado += (';REVIND=NO_HECHA' if _n(rev.get('no_hechas')) else f";REVIND={_n(rev.get('objeciones'))}") + f";PASADAS={_n(rev.get('pasadas'))}"
        return (True, d.get('texto') or d.get('primera_linea') or 'NO LISTO', estado)
    if orden == 'cita':
        estado = d.get('estado') or '?'
        ctx = d.pop('contexto', None) or {}
        contexto = _texto_contexto(ctx)
        vig = _texto_vigencia(d.pop('vigencia', None))
        hist = _texto_historial(d.pop('historial', None))
        if hist:
            vig = (vig + '\n\n' if vig else '') + hist
        limites = ''
        if d.get('obra') and estado in ('ENCONTRADO', 'CONTENIDO_EN_ANCESTRO', 'LOCALIZADO_SIN_TEXTO'):
            ident = d.get('identificador') or arguments.get('identificador') or ''
            limites = _texto_limites(_avisos_de_limites([d.get('obra'), d.get('obra_titulo'), ident.partition('::')[0].partition('@')[0].strip()], ident.partition('::')[2].strip()) + _aviso_documento_entero(d))
        contexto = '\n'.join((x for x in ('\n' + vig if vig else '', limites, contexto) if x))
        if estado != 'ENCONTRADO':
            return (True, json.dumps(d, ensure_ascii=False, indent=2) + ('\n' + contexto if contexto else ''), estado)
        texto = d.get('texto_literal')
        cab = [f"[{estado}] {d.get('identificador')}", f"{d.get('etiqueta_humana') or ''}. {d.get('titulo') or ''}".strip(), f"obra: {d.get('obra')} — {d.get('obra_titulo') or ''}", f"versión: {d.get('version')} | fichero: {d.get('fichero')} | {_paginas(d.get('pagina_inicio'), d.get('pagina_fin'))}", f"régimen: {d.get('regimen')} | carácter jurídico: {d.get('caracter_juridico')} | emisor: {d.get('emisor')}"]
        if d.get('regimen') == 'licenciado':
            cab.append(AVISO_LICENCIADO)
        if texto:
            natural = d.get('naturaleza_del_texto')
            cab += ['', f'TEXTO ({natural}):' if natural else 'TEXTO LITERAL:', _corta(texto)]
        else:
            cab += ['', '(Sin texto: solo la ubicación.)']
        if d.get('tablas'):
            cab += ['', 'Tablas del precepto (estructura):', _corta(json.dumps(d.get('tablas'), ensure_ascii=False))]
        if contexto:
            cab.append(contexto)
        return (True, '\n'.join(cab), estado)
    if orden == 'vigencia':
        obras = d.get('obras') or {}
        if not d.get('consultado'):
            cab = ['No hay consulta de vigencia guardada en la base: no se sabe si las normas siguen vigentes. Díselo a Responsable (la consulta se actualiza desde Claude Code, no desde aquí).']
        else:
            cab = [f"Consulta de vigencia del {d['consultado'][:10]} (BOE y Oficina de Publicaciones de la UE)."]
        otras = d.get('otras_copias') or {}
        for obra, v in obras.items():
            if v is None:
                cab.append(f'\n{obra}: no es legislación (no hay vigencia que consultar).')
            else:
                cab.append(f'\n{obra}\n' + _texto_vigencia(v))
                if otras.get(obra):
                    cab.append(f"  La base tiene otras copias de esta misma norma ({', '.join(otras[obra])}): la vigencia es la de la norma, pero la versión de cada copia puede ser otra.")
        sin_norma = d.get('no_esta_en_la_base') or {}
        for nombre, info in sin_norma.items():
            menciones = (info or {}).get('menciones') or []
            cab.append(f'\n{nombre}: la base NO tiene esa norma (ninguna obra se llama así): no se sabe su vigencia ni su contenido, y no hay que afirmar nada de ellos. Búscala con normativa_buscar: puede estar mencionada en otras normas que sí están' + (f" (por ejemplo en {', '.join(menciones)})" if menciones else '') + '. Lo que diga de ella otra norma se cita de esa otra norma.')
        avisos = sum((1 for v in obras.values() if v and v.get('avisos')))
        return (True, '\n'.join(cab), f'OBRAS={len(obras)};CON_AVISO={avisos}' + (f';NO_ESTA={len(sin_norma)}' if sin_norma else ''))
    if orden == 'fundamento':
        texto = json.dumps(d, ensure_ascii=False, indent=2)
        candidatos = [c for c in d.get('candidatos') or [] if isinstance(c, dict)]
        for c in candidatos:
            ident = c.get('identificador') or ''
            avisos = _avisos_de_limites([c.get('obra'), ident.partition('::')[0]], c.get('ruta') or ident.partition('::')[2].strip())
            texto += _texto_limites(avisos, f'{ident} · ' if len(candidatos) > 1 else '')
        return (True, texto, d.get('estado') or '?')
    if orden == 'cotejar':
        texto = json.dumps(d, ensure_ascii=False, indent=2)
        cab, _, ruta = (arguments.get('identificador') or '').partition('::')
        texto += _texto_limites(_avisos_de_limites([cab.partition('@')[0]], ruta.strip()))
        return (True, texto + '\n\nCoincidir no prueba que la afirmación sea correcta: acota el trabajo de quien valida, no lo sustituye.', d.get('estado') or '?')
    return (True, salida, 'OK')

def call_tool(nombre: str, arguments: dict | None) -> dict:
    arguments = ({} if arguments is None else arguments) if nombre == 'normativa_hechos' else arguments or {}
    if nombre not in TOOL_BY_NAME:
        return _result(False, f'Herramienta desconocida: {nombre}')
    t0 = time.monotonic()
    try:
        args = argumentos_de_la_orden(nombre, arguments)
        if nombre == 'normativa_hechos' and (not _hechos_habilitados()):
            audit(nombre, arguments, 'apagado', 0)
            return _result(True, _hechos_apagados(arguments['pregunta']))
    except (ArgumentoMalo, controles.ErrorDeControles) as e:
        audit(nombre, arguments if isinstance(arguments, dict) else {}, 'ARGUMENTO_MALO', 0)
        return _result(False, f'Error en los argumentos: {e}')
    try:
        rc, salida, err = ejecutar(args, entrada_de_la_orden(nombre, arguments))
    except subprocess.TimeoutExpired:
        audit(nombre, arguments, 'TIEMPO_AGOTADO', int((time.monotonic() - t0) * 1000))
        plazo = TIEMPO_MAXIMO_POR_ORDEN.get(TOOL_BY_NAME[nombre]['orden'], TIEMPO_MAXIMO)
        return _result(False, f'La consulta tardó más de {plazo} s y se cortó.')
    ms = int((time.monotonic() - t0) * 1000)
    if nombre == 'normativa_hechos' and rc == 2 and (not salida.strip()):
        try:
            motivo = json.loads(err)['motivo']
        except (ValueError, KeyError, TypeError):
            pass
        else:
            audit(nombre, arguments, 'ARGUMENTO_MALO', 0)
            return _result(False, f'Error en los argumentos: {motivo}')
    if rc != 0 and (not salida.strip()) and (TOOL_BY_NAME[nombre]['orden'] == 'brechas'):
        motivo = '\n'.join((l for l in err.splitlines() if 'pymupdf' not in l)).strip() or 'sin detalle'
        audit(nombre, arguments, f'REGISTRO_NO_VALIDO_rc{rc}', ms)
        return _result(False, f'No se ha podido comprobar el registro (rc={rc}):\n{motivo[-LARGO_MAXIMO_ERROR_REGISTRO:]}')
    if rc != 0 and (not salida.strip()):
        motivo = '\n'.join((l for l in err.splitlines() if 'pymupdf' not in l))[-800:]
        audit(nombre, arguments, f'ERROR_rc{rc}', ms)
        return _result(False, f'La base devolvió un error (rc={rc}): {motivo}')
    if rc == 2 and TOOL_BY_NAME[nombre]['orden'] == 'comprobar-carpeta':
        audit(nombre, arguments, f'ERROR_TABLA_rc{rc}', ms)
        try:
            texto = json.loads(salida).get('texto') or salida
        except (ValueError, AttributeError, TypeError):
            texto = salida
        return _result(False, texto)
    try:
        ok, texto, estado = formatear(nombre, args, salida, arguments)
    except (ValueError, KeyError, TypeError) as e:
        audit(nombre, arguments, 'SALIDA_RARA', ms)
        return _result(False, f'Respuesta inesperada de la base ({e}): {salida[:800]}')
    audit(nombre, arguments, estado, 0 if nombre == 'normativa_hechos' else ms)
    return _result(ok, texto)

def _result(ok: bool, text: str) -> dict:
    return {'content': [{'type': 'text', 'text': text}], 'isError': not ok}

def handle(msg: dict) -> dict | None:
    method = msg.get('method')
    mid = msg.get('id')
    if method == 'initialize':
        proto = (msg.get('params') or {}).get('protocolVersion') or DEFAULT_PROTOCOL
        return {'jsonrpc': '2.0', 'id': mid, 'result': {'protocolVersion': proto, 'capabilities': {'tools': {}}, 'instructions': SERVER_INSTRUCTIONS, 'serverInfo': {'name': 'normativa_ict155', 'version': VERSION}}}
    if method in ('notifications/initialized', 'initialized', 'notifications/cancelled'):
        return None
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {}}
    if method == 'tools/list':
        catalogo = TOOLS + ([TOOL_HECHOS] if _hechos_habilitados() else [])
        pub = [{'name': t['name'], 'description': t['description'], 'inputSchema': t['inputSchema'], 'annotations': {'readOnlyHint': True}} for t in catalogo]
        return {'jsonrpc': '2.0', 'id': mid, 'result': {'tools': pub}}
    if method == 'tools/call':
        params = msg.get('params') or {}
        meta = params.get('_meta')
        with _Latidos(meta.get('progressToken') if isinstance(meta, dict) else None):
            return {'jsonrpc': '2.0', 'id': mid, 'result': call_tool(params.get('name'), params.get('arguments'))}
    if mid is not None:
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': f'Method not found: {method}'}}
    return None
_ESCRITURA = threading.Lock()

def send(obj: dict) -> None:
    datos = json.dumps(obj, ensure_ascii=False).encode('utf-8') + b'\n'
    with _ESCRITURA:
        sys.stdout.buffer.write(datos)
        sys.stdout.buffer.flush()

class _Latidos:
    """Con `with _Latidos(token):`, mientras dura el bloque manda `notifications/progress` (`progress` 1, 2, 3… y los segundos transcurridos en `message`) cada `LATIDO_SEGUNDOS`.
    Sin `progressToken` valido (un texto o un entero) no hace nada. Nunca rompe la llamada: un fallo al escribir un latido se calla y el hilo termina; al salir del bloque
    el hilo se para antes de que el servidor escriba la respuesta."""

    def __init__(self, token):
        self.token = token if isinstance(token, (str, int)) and (not isinstance(token, bool)) else None
        self.parar = threading.Event()
        self.hilo = None

    def _latir(self) -> None:
        t0, n = (time.monotonic(), 0)
        try:
            while not self.parar.wait(LATIDO_SEGUNDOS):
                n += 1
                send({'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progressToken': self.token, 'progress': n, 'message': f'verificando: {round(time.monotonic() - t0)} s'}})
        except Exception as e:
            log_err(f'latido de progreso: {e}')

    def __enter__(self):
        if self.token is not None:
            self.hilo = threading.Thread(target=self._latir, name='latidos', daemon=True)
            self.hilo.start()
        return self

    def __exit__(self, *args):
        self.parar.set()
        if self.hilo is not None:
            self.hilo.join(timeout=2)
        return False

def main() -> None:
    log_err(f'arrancado v{VERSION}; proyecto={PROYECTO}')
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            log_err(f'linea no-JSON ignorada: {e}')
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            log_err(f"excepcion manejando {msg.get('method')}: {e}")
            resp = {'jsonrpc': '2.0', 'id': msg.get('id'), 'error': {'code': -32603, 'message': f'error interno: {e}'}} if msg.get('id') is not None else None
        if resp is not None:
            send(resp)
if __name__ == '__main__':
    main()
