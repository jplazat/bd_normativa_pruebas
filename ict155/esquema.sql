-- Esquema de la base de conocimiento normativo ICT155. Fase 1.
-- Artefacto derivado: se reconstruye entero desde la biblioteca en cualquier momento.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- capa fisica
CREATE TABLE documento (
  id                INTEGER PRIMARY KEY,
  ruta_relativa     TEXT    NOT NULL UNIQUE,
  sha256            TEXT    NOT NULL,
  bytes             INTEGER NOT NULL,
  mtime_utc         TEXT    NOT NULL,
  paginas           INTEGER,
  hash_texto        TEXT,
  motor_extraccion  TEXT,
  clase_derechos    TEXT    NOT NULL,   -- publico | licenciado
                                        -- | reservado | cliente_nda
  estado_ingesta    TEXT    NOT NULL,   -- ingerido | registrado_fuera_de_alcance
                                        -- | derechos_restringidos | sin_capa_texto
  motivo_estado     TEXT,
  extraido_en       TEXT
);
CREATE INDEX ix_doc_estado ON documento(estado_ingesta);

-- ---------------------------------------------------------------------- obra
CREATE TABLE obra (
  id                     INTEGER PRIMARY KEY,
  identificador_canonico TEXT NOT NULL UNIQUE,
  tipo                   TEXT NOT NULL,
  titulo                 TEXT NOT NULL,
  emisor                 TEXT,
  -- De donde sale `emisor`. Sin esto, dentro de un ano el campo tendra aspecto
  -- de dato leido del documento y sera una convencion de nomenclatura. Es lo
  -- que paso con el JCGM atribuido a ILAC: no fallo la lectura, fallo la fuente
  -- de la que se dedujo.
  --
  --   declarado_en_documento     leido del propio documento, con pagina
  --   inferido_de_nombre_fichero deducido del prefijo. Vale, pero se dice
  --   discrepante                el declarado y el inferido no coinciden, y no
  --                              se elige entre ellos
  --   sin_emisor                 no se ha podido establecer
  emisor_metodo          TEXT NOT NULL DEFAULT 'sin_emisor',
  -- Donde lo dice el documento, cuando el metodo es declarado_en_documento.
  emisor_fundamento      TEXT,
  -- La FRASE literal con que el documento se nombra a si mismo, tal como la
  -- transcribio el agente. Va aparte de `emisor` a proposito, y la separacion
  -- la impuso una prueba: `emisor` es un NOMBRE ("JCGM"), y la frase suele ser
  -- el titulo del acto ("DIRECTIVA 2014/53/UE DEL PARLAMENTO EUROPEO Y DEL
  -- CONSEJO de 16 de abril de 2014"), que nombra al emisor dentro de una
  -- oracion. Meter la oracion en `emisor` daba un campo con forma de nombre y
  -- contenido de titulo, y la capa de consulta lo imprime como nombre.
  --
  -- Destilar "Parlamento Europeo y Consejo" de esa oracion es una LECTURA, y
  -- las lecturas las hace ICT155. Mientras no las haga, la frase queda aqui con
  -- su ruta al lado, que es material verificable, y `emisor` conserva lo que
  -- tuviera.
  emisor_frase           TEXT,
  fecha_norma            TEXT,
  -- Que fuerza tiene lo que dice esta obra. NO es lo mismo que `tipo`, que es
  -- la familia de analizador: bajo `tipo='guia'` conviven WELMEC y EA, que
  -- orientan, las guias del CEM, a las que una norma espanola remite, y
  -- certificados, que son prueba. Un campo que parece decir una cosa y dice
  -- otra es peor que no tenerlo.
  --
  --   vinculante              obliga por si misma
  --   vinculante_por_remision una norma le da fuerza que por si sola no tiene
  --   orientativo             orienta y no obliga
  --   prueba_documental       acredita un hecho, no establece una regla
  --   indeterminado           nadie lo ha verificado todavia
  caracter_juridico      TEXT NOT NULL DEFAULT 'indeterminado',
  -- El precepto que establece ese caracter, citado por su ruta. Sin el, el
  -- valor solo puede ser 'indeterminado'.
  --
  -- Existe porque "las guias del CEM obligan por remision del RD 244/2016" es
  -- una afirmacion plausible que nadie ha verificado. Grabada sin fundamento
  -- seria, dentro de un ano, una certeza de la casa que nadie sabe de donde
  -- salio. Con el fundamento al lado se comprueba en un minuto. Es la misma
  -- disciplina de `metodo_extraccion`, aplicada a una clasificacion.
  caracter_juridico_fundamento TEXT,
  jurisdiccion           TEXT NOT NULL,    -- ES | UE | OTRA
  CHECK (caracter_juridico IN ('vinculante', 'vinculante_por_remision',
                               'orientativo', 'prueba_documental',
                               'indeterminado')),
  -- Un valor distinto de 'indeterminado' EXIGE fundamento. Sin esta condicion
  -- el campo se rellena de afirmaciones plausibles que nadie ha comprobado, que
  -- es exactamente lo que no puede pasar.
  CHECK (caracter_juridico = 'indeterminado'
         OR (caracter_juridico_fundamento IS NOT NULL
             AND trim(caracter_juridico_fundamento) <> '')),
  CHECK (emisor_metodo IN ('declarado_en_documento', 'inferido_de_nombre_fichero',
                           'discrepante', 'sin_emisor')),
  -- Un emisor leido del documento tiene que decir DONDE lo dice. La misma
  -- disciplina que caracter_juridico_fundamento.
  CHECK (emisor_metodo <> 'declarado_en_documento'
         OR (emisor_fundamento IS NOT NULL AND trim(emisor_fundamento) <> '')),
  CHECK (emisor IS NOT NULL OR emisor_metodo = 'sin_emisor')
);

CREATE TABLE obra_alias (
  obra_id INTEGER NOT NULL REFERENCES obra(id) ON DELETE CASCADE,
  alias   TEXT    NOT NULL,
  alias_norm TEXT NOT NULL,
  PRIMARY KEY (obra_id, alias_norm)
);
CREATE INDEX ix_alias_norm ON obra_alias(alias_norm);

-- ------------------------------------------------------------------- version
-- completitud es lo que autoriza a responder "no existe": solo un ejemplar
-- completo permite afirmar la ausencia de un precepto.
CREATE TABLE version (
  id                  INTEGER PRIMARY KEY,
  obra_id             INTEGER NOT NULL REFERENCES obra(id) ON DELETE CASCADE,
  documento_id        INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  etiqueta            TEXT    NOT NULL,
  es_consolidada      INTEGER NOT NULL DEFAULT 0,
  fecha_consolidacion TEXT,
  -- Fecha de la EDICION, que no es lo mismo que la de consolidacion. Una guia
  -- no se consolida: se reescribe, y la reescritura puede decir lo contrario
  -- que la anterior. Por eso las ediciones conviven como versiones de la misma
  -- obra y ninguna sustituye a la otra.
  fecha_edicion       TEXT,
  idioma              TEXT    NOT NULL,
  completitud         TEXT    NOT NULL DEFAULT 'completa',  -- completa | extracto
                                                            -- | preview | parcial
                                                            -- | ocr_defectuoso
  cabecera_origen     TEXT,
  UNIQUE (obra_id, etiqueta, idioma)
);
CREATE INDEX ix_version_obra ON version(obra_id);

-- ------------------------------------------------------------------ precepto
CREATE TABLE precepto (
  id                  INTEGER PRIMARY KEY,
  version_id          INTEGER NOT NULL REFERENCES version(id) ON DELETE CASCADE,
  padre_id            INTEGER REFERENCES precepto(id) ON DELETE CASCADE,
  ruta_estructural    TEXT    NOT NULL,
  tipo_unidad         TEXT    NOT NULL,
  numero              TEXT,
  etiqueta_humana     TEXT    NOT NULL,
  titulo              TEXT,
  texto_literal       TEXT    NOT NULL,
  -- De donde sale el texto, y no son intercambiables:
  --   capa_texto               la capa de texto nativa del PDF. Autoridad plena.
  --   ocr                      reconocimiento optico. Puede tener un digito mal
  --                            y nadie lo ve. Nunca se presenta como literal
  --                            sin decir que es OCR.
  --   transcripcion_verificada  transcrita a mano y cotejada contra el original.
  --                            Maxima autoridad despues de la capa nativa.
  metodo_extraccion   TEXT    NOT NULL DEFAULT 'capa_texto',
  marca_consolidacion TEXT,
  pagina_inicio       INTEGER NOT NULL,
  pagina_fin          INTEGER NOT NULL,
  orden               INTEGER NOT NULL,
  UNIQUE (version_id, ruta_estructural)
);
CREATE INDEX ix_precepto_version ON precepto(version_id, orden);
CREATE INDEX ix_precepto_ruta    ON precepto(ruta_estructural);
CREATE INDEX ix_precepto_padre   ON precepto(padre_id);

-- ---------------------------------------------------------------------- celda
-- Una tabla de dos dimensiones no tiene linealizacion canonica: quien la cita la
-- lee por filas e inserta signos que representan su estructura, y la extraccion
-- devuelve las celdas por columnas. Comparar las dos como cadena no esta bien
-- definido, y por eso tres casos del arnes llevaban meses en rojo.
--
-- La salida no es acertar con la linealizacion, es no necesitarla: la tabla se
-- guarda con su estructura y una cita se verifica comprobando que cada valor
-- esta Y en que fila y columna.
CREATE TABLE celda (
  precepto_id INTEGER NOT NULL REFERENCES precepto(id) ON DELETE CASCADE,
  fila        INTEGER NOT NULL,
  columna     INTEGER NOT NULL,
  valor       TEXT    NOT NULL,
  valor_norm  TEXT    NOT NULL,   -- para buscar sin acentos ni puntuacion
  PRIMARY KEY (precepto_id, fila, columna)
);
CREATE INDEX ix_celda_valor ON celda(valor_norm);

-- FTS5 con contenido externo: no duplica texto y se reconstruye desde precepto.
CREATE VIRTUAL TABLE precepto_fts USING fts5(
  etiqueta_humana, titulo, texto_literal,
  content='precepto', content_rowid='id',
  tokenize="unicode61 remove_diacritics 2"
);

-- El indice guarda el texto PLEGADO (R14, 11-oct-2026): los exponentes en superindice (10¹², 10⁻⁶, m³) se indexan como sus cifras y signos corrientes (1012, 10-6, m3), igual
-- que `superindices.plegar` pliega la consulta; asi «10^12», «10-6» y «m3» encuentran el texto aunque este guarde el superindice. El plegado cambia caracteres de palabra
-- por caracteres de palabra y separadores por separadores, asi que el numero de fichas por texto no cambia y `snippet()` (que relee `precepto`) sigue alineado.
-- Los tres disparadores tienen que plegar IGUAL: el 'delete' de FTS5 necesita los mismos valores que se indexaron.
CREATE TRIGGER precepto_ai AFTER INSERT ON precepto BEGIN
  INSERT INTO precepto_fts(rowid, etiqueta_humana, titulo, texto_literal)
  VALUES (new.id, replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(new.etiqueta_humana,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(coalesce(new.titulo,''),'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(new.texto_literal,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'));
END;
CREATE TRIGGER precepto_ad AFTER DELETE ON precepto BEGIN
  INSERT INTO precepto_fts(precepto_fts, rowid, etiqueta_humana, titulo, texto_literal)
  VALUES ('delete', old.id, replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(old.etiqueta_humana,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(coalesce(old.titulo,''),'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(old.texto_literal,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'));
END;
CREATE TRIGGER precepto_au AFTER UPDATE ON precepto BEGIN
  INSERT INTO precepto_fts(precepto_fts, rowid, etiqueta_humana, titulo, texto_literal)
  VALUES ('delete', old.id, replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(old.etiqueta_humana,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(coalesce(old.titulo,''),'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(old.texto_literal,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'));
  INSERT INTO precepto_fts(rowid, etiqueta_humana, titulo, texto_literal)
  VALUES (new.id, replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(new.etiqueta_humana,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(coalesce(new.titulo,''),'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'), replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(new.texto_literal,'⁰','0'),'¹','1'),'²','2'),'³','3'),'⁴','4'),'⁵','5'),'⁶','6'),'⁷','7'),'⁸','8'),'⁹','9'),'⁻','-'),'⁺','+'));
END;

-- -------------------------------------------------------------------- ingesta
CREATE TABLE ingesta (
  id               INTEGER PRIMARY KEY,
  ejecutada_en     TEXT NOT NULL,
  git_commit       TEXT,
  n_documentos     INTEGER,
  n_versiones      INTEGER,
  n_preceptos      INTEGER,
  huella_contenido TEXT
);

-- ----------------------------------------------------------------- mobiliario
-- Cabeceras y pies de pagina de cada guia (`#` es el numero de pagina). Los
-- rellena la ingesta y los usa el comparador de literales para quitarlos de los
-- dos lados, solo al comparar con ese documento. NO entra en la huella de
-- contenido: no cambia el texto de ningun precepto. Ver `ict155/mobiliario.py`.
CREATE TABLE mobiliario (
  documento_id INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  patron       TEXT    NOT NULL,
  PRIMARY KEY (documento_id, patron)
);

-- ------------------------------------------------------------ tablas de guias
-- Todas las tablas de todas las paginas de cada guia, con sus filas y columnas
-- (4-oct-2026, "que cada celda conserve su columna"). Una tabla que sigue en la
-- pagina siguiente con la misma cabecera es la misma tabla. Aparte de `celda`,
-- que sigue guardando las de los preceptos de tipo tabla. Entran en la huella.
CREATE TABLE tabla_pdf (
  id            INTEGER PRIMARY KEY,
  documento_id  INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  orden         INTEGER NOT NULL,
  pagina_inicio INTEGER NOT NULL,
  pagina_fin    INTEGER NOT NULL,
  n_filas       INTEGER NOT NULL,
  n_columnas    INTEGER NOT NULL,
  UNIQUE (documento_id, orden)
);
CREATE TABLE celda_pdf (
  tabla_id   INTEGER NOT NULL REFERENCES tabla_pdf(id) ON DELETE CASCADE,
  fila       INTEGER NOT NULL,
  columna    INTEGER NOT NULL,
  valor      TEXT    NOT NULL,
  valor_norm TEXT    NOT NULL,
  pagina     INTEGER NOT NULL,
  PRIMARY KEY (tabla_id, fila, columna)
);
CREATE INDEX ix_celda_pdf_valor ON celda_pdf(valor_norm);
