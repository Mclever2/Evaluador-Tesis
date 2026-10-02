"""Segmentador estructural: divide el proyecto por las secciones de la rúbrica.

Heurísticas de encabezados (numeración, títulos en mayúsculas, aliases de la
rúbrica activa) con detección de páginas de índice para no confundir el índice
con los encabezados reales. La "indexación" del ECM es esta segmentación: el
proyecto del estudiante NO se vectoriza.

Reglas aprendidas de documentos UPAO reales:
- DESEMPATE POR ORDEN: si una sección tiene varios encabezados candidatos con
  el mismo puntaje (p. ej. "Tipo de investigación" aparece en GENERALIDADES y
  en el marco metodológico), se prefiere el que respeta el orden del documento
  respecto a la sección anterior de la rúbrica.
- ABSORCIÓN JERÁRQUICA: si el cuerpo directo de una sección queda casi vacío
  porque su encabezado es un contenedor (p. ej. "1.1. Descripción..." cuyo
  contenido vive en "1.1.1..."), su texto se extiende hasta el siguiente
  encabezado que NO sea sub-numeración suya. Los textos pueden solaparse entre
  secciones: cada criterio se juzga con el contexto que le corresponde.
- RÓTULOS DE TABLA: una línea que termina en ":" ("Tipo de investigación:"
  dentro de la matriz de consistencia) es un rótulo de campo, no un encabezado;
  solo gana si no hay otro candidato. En DOCX la numeración automática de Word
  no sobrevive a la extracción, así que sin esta regla el rótulo ganaba por
  orden del documento y la sección quedaba con la celda ("Aplicada", 1 palabra).
- REPARACIÓN POR CONTENIDO: si tras construir los spans una sección quedó casi
  vacía y tiene otro candidato del mismo puntaje que produce contenido real,
  se reasigna y se reconstruye (contenedores sin numeración que la absorción
  jerárquica no puede extender).

Si la heurística encuentra menos de `umbral_llm` secciones y se provee un
`fallback_llm`, se delega en él (nodo Orquestador-Segmentador).
"""

from __future__ import annotations

import re
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from anonymizer.anonymizer import ReporteAnonimizacion
from ingest.extractors import DocumentoExtraido
from rubrics.models import Rubrica
from rubrics.parser import normalizar

# Umbral de palabras bajo el cual una sección presente se marca como
# posiblemente no redactada aún.
_MIN_PALABRAS_SECCION = 50

# Cuerpo directo mínimo antes de intentar la absorción jerárquica.
_MIN_PALABRAS_ABSORCION = 30

# Secciones con menos palabras que esto no se envían a los jueces: no hay
# contenido evaluable (el agregador las puntúa 0 con observación honesta).
MIN_PALABRAS_EVALUABLES = 5

# Encabezados que no pertenecen a la rúbrica pero CIERRAN la sección anterior
# (evitan que referencias, cronograma o anexos inflen la última sección).
_LIMITES_EXTRA = [
    "referencias bibliograficas", "referencias", "bibliografia",
    "aspectos administrativos", "cronograma", "presupuesto",
    "fuentes de financiamiento", "anexos", "apendices", "apendice",
    "resumen", "abstract", "agradecimientos", "dedicatoria", "indice",
    "indice de contenidos", "tabla de contenido", "contenido",
    "indice de tablas", "indice de figuras", "introduccion",
]

# La numeración puede ir seguida de un espacio ("1.4. Justificación") o, en PDFs
# donde la extracción pierde el separador, PEGADA a la palabra ("1.4.Justificación").
# El caso pegado exige un terminador explícito (. ) - :) seguido de una letra: así
# "DELIMITACIÓN" (que parece números romanos) NO se confunde con numeración.
_SEP_NUM = r"(?:\s*[\.\)\-:]?\s+|[\.\)\-:](?=[^\W\d_]))"
_RE_PREFIJO_NUM = re.compile(
    r"^(?:cap[ií]tulo\s+[ivxlcmd\d]+\s*[:.\-]?\s*|(?:\d{1,2}(?:\.\d{1,2})*|[IVXLCMD]+)"
    + _SEP_NUM + r")",
    re.IGNORECASE,
)
_RE_NUMERACION = re.compile(
    r"^\s*((?:\d{1,2}\.)+\d{0,2}|\d{1,2}|[IVXLCMD]+)[\.\)]?(?:\s+|(?<=[.)])(?=[^\W\d_]))"
)
_RE_DEL = re.compile(r"\bdel\b")
_RE_LINEA_TOC = re.compile(r"\.{2,}\s*\d{1,4}\s*$")
_RE_TITULO_TOC = re.compile(
    r"^\s*(?:[ií]ndice|tabla de contenido|contenido)s?\b", re.IGNORECASE
)


class SeccionSegmentada(BaseModel):
    seccion_id: str
    nombre: str
    presente: bool
    encontrado_como: Optional[str] = None
    pagina_inicio: Optional[int] = None
    pagina_fin: Optional[int] = None
    palabras: int = 0
    # Palabras que no provienen de la plantilla (ingest.plantilla). None en
    # segmentaciones antiguas o construidas a mano: se usa `palabras`.
    palabras_propias: Optional[int] = None
    texto: str = ""

    @property
    def palabras_evaluables(self) -> int:
        # Las palabras propias nunca superan el total de la sección.
        if self.palabras_propias is None:
            return self.palabras
        return min(self.palabras, self.palabras_propias)


class ResultadoSegmentacion(BaseModel):
    secciones: list[SeccionSegmentada]
    advertencias: list[str] = Field(default_factory=list)
    paginas_indice: list[int] = Field(default_factory=list)
    metodo: Literal["heuristica", "llm"] = "heuristica"
    anonimizacion: Optional[ReporteAnonimizacion] = None

    @property
    def presentes(self) -> list[SeccionSegmentada]:
        return [s for s in self.secciones if s.presente]

    @property
    def no_encontradas(self) -> list[str]:
        return [f"{s.seccion_id} {s.nombre}" for s in self.secciones if not s.presente]

    def reporte(self) -> dict:
        """Reporte de indexación para API/UI: sin el texto completo."""
        return {
            "metodo": self.metodo,
            "paginas_indice": self.paginas_indice,
            "secciones": [
                {
                    "id": s.seccion_id,
                    "nombre": s.nombre,
                    "presente": s.presente,
                    "encontrado_como": s.encontrado_como,
                    "pagina_inicio": s.pagina_inicio,
                    "pagina_fin": s.pagina_fin,
                    "palabras": s.palabras,
                    "palabras_propias": s.palabras_propias,
                }
                for s in self.secciones
            ],
            "no_encontradas": self.no_encontradas,
            "advertencias": self.advertencias,
            "anonimizacion": self.anonimizacion.model_dump() if self.anonimizacion else None,
        }


class _Linea(BaseModel):
    pagina: int
    indice: int  # índice global de línea
    texto: str


class _Match(BaseModel):
    seccion_id: Optional[str]  # None → límite extra (cierra sección, no abre)
    linea: _Linea
    encabezado: str
    puntaje: int
    numeracion: Optional[str] = None  # "1.1." si el encabezado está numerado
    rotulo: bool = False  # la línea termina en ":" → rótulo de tabla/campo, no encabezado


def _es_pagina_indice(texto: str) -> bool:
    lineas = [l for l in texto.splitlines() if l.strip()]
    if any(_RE_TITULO_TOC.match(l) for l in lineas[:8]):
        return True
    con_puntos = sum(1 for l in lineas if _RE_LINEA_TOC.search(l))
    return con_puntos >= 3


def _numeracion_de(linea: str) -> Optional[str]:
    m = _RE_NUMERACION.match(linea)
    if not m:
        return None
    return m.group(1).rstrip(".") + "."


def _es_subnumeracion(hijo: Optional[str], padre: Optional[str]) -> bool:
    """True si `hijo` (p. ej. '1.1.1.') es sub-numeración de `padre` ('1.1.')."""
    if not hijo or not padre:
        return False
    return hijo != padre and hijo.startswith(padre)


def _profundidad(numeracion: Optional[str]) -> int:
    """'1.' → 1, '1.1.' → 2, 'II.' → 1, None → 0."""
    if not numeracion:
        return 0
    return numeracion.count(".") or 1


def _son_hermanos(a: Optional[str], b: Optional[str]) -> bool:
    """'1.' y '2.' son hermanos; '4.1.' y '4.2.' también; '1.' y '1.1.' no."""
    if not a or not b:
        return False
    partes_a = a.strip(".").split(".")
    partes_b = b.strip(".").split(".")
    if len(partes_a) != len(partes_b) or partes_a[:-1] != partes_b[:-1]:
        return False
    return all(p.isdigit() for p in partes_a + partes_b)


def _candidato_encabezado(linea: str) -> Optional[str]:
    """Devuelve el texto del encabezado (sin numeración) o None si no parece uno."""
    plano = linea.strip()
    if not plano or len(plano) > 90:
        return None
    if _RE_LINEA_TOC.search(plano):  # línea de índice, no encabezado real
        return None
    sin_prefijo = _RE_PREFIJO_NUM.sub("", plano).strip(" :.-")
    if not sin_prefijo:
        return None
    letras = [c for c in sin_prefijo if c.isalpha()]
    if len(letras) < 4:
        return None
    numerado = bool(_RE_PREFIJO_NUM.match(plano))
    mayusculas = sum(1 for c in letras if c.isupper()) / len(letras) >= 0.8
    if not (numerado or mayusculas or len(plano) <= 60):
        return None
    return sin_prefijo


def _sin_rotulo(matches: list[_Match]) -> list[_Match]:
    """Prefiere candidatos que no son rótulos (líneas terminadas en ":").

    Los rótulos de campo dentro de tablas ("Tipo de investigación:" en la
    matriz de consistencia) empatan con los aliases y, cuando la numeración de
    Word se pierde en la extracción DOCX, ganaban por orden del documento."""
    quedan = [m for m in matches if not m.rotulo]
    return quedan or matches


def _puntuar(candidato_norm: str, alias: str) -> int:
    # "del" ↔ "de": las plantillas UPAO escriben "Diseño de estudio" o "Formulación
    # de problema" donde la rúbrica usa "del". Se colapsa la contracción en AMBOS
    # lados, así que las variantes sin "l" empatan igual sin perder ningún match
    # previo (del→de en los dos operandos preserva las igualdades existentes).
    candidato_norm = _RE_DEL.sub("de", candidato_norm)
    alias = _RE_DEL.sub("de", alias)
    if candidato_norm == alias:
        return 3
    if candidato_norm.startswith(alias) and len(candidato_norm) <= len(alias) + 30:
        return 2
    if alias.startswith(candidato_norm) and len(candidato_norm) >= 6:
        return 2
    if f" {alias} " in f" {candidato_norm} " and len(candidato_norm) <= len(alias) + 45:
        return 1
    return 0


def _reparar_inline_titulo(
    lineas: list[_Linea],
    paginas_indice: list[int],
    rubrica: Rubrica,
    secciones: list[SeccionSegmentada],
) -> list[str]:
    """Caso especial ADITIVO: recupera el Título cuando va como rótulo con su valor
    en la MISMA línea ("Título: <enunciado largo>"), demasiado larga para ser
    candidata a encabezado (supera el límite de 90 caracteres de
    `_candidato_encabezado`).

    (La variante "Formulación DE problema" sin la "l" ya la resuelve `_puntuar`, que
    colapsa "del"↔"de".)

    Solo actúa sobre S01 si AÚN no está presente: nunca reasigna ni altera lo que la
    heurística ya resolvió, de modo que el resto de documentos no se ve afectado."""
    advertencias: list[str] = []

    s01 = next((s for s in secciones if s.seccion_id == "S01"), None)
    sec01 = next((s for s in rubrica.secciones if s.id == "S01"), None)
    if s01 is None or s01.presente or sec01 is None:
        return advertencias

    for linea in lineas:
        if linea.pagina in paginas_indice or ":" not in linea.texto:
            continue
        rotulo, valor = linea.texto.strip().split(":", 1)
        valor = valor.strip()
        rotulo_norm = normalizar(_RE_PREFIJO_NUM.sub("", rotulo).strip())
        if valor and any(_puntuar(rotulo_norm, alias) >= 2 for alias in sec01.aliases):
            secciones[secciones.index(s01)] = SeccionSegmentada(
                seccion_id="S01", nombre=sec01.nombre, presente=True,
                encontrado_como=rotulo.strip(), pagina_inicio=linea.pagina,
                pagina_fin=linea.pagina, palabras=len(valor.split()), texto=valor,
            )
            advertencias.append(
                f"S01 ({sec01.nombre}): recuperado del rótulo 'Título:' en la misma "
                f"línea que su valor (pág. {linea.pagina})."
            )
            break

    return advertencias


def segmentar(
    doc: DocumentoExtraido,
    rubrica: Rubrica,
    umbral_llm: int = 8,
    fallback_llm: Optional[Callable[[DocumentoExtraido, Rubrica], ResultadoSegmentacion]] = None,
) -> ResultadoSegmentacion:
    paginas_indice = [p.numero for p in doc.paginas if _es_pagina_indice(p.texto)]

    lineas: list[_Linea] = []
    indice = 0
    for pagina in doc.paginas:
        for texto in pagina.texto.splitlines():
            lineas.append(_Linea(pagina=pagina.numero, indice=indice, texto=texto))
            indice += 1

    # 1) Recolectar TODOS los candidatos por sección (no solo el primero).
    candidatos: dict[str, list[_Match]] = {}
    limites: list[_Match] = []
    for linea in lineas:
        if linea.pagina in paginas_indice:
            continue
        candidato = _candidato_encabezado(linea.texto)
        if candidato is None:
            continue
        cand_norm = normalizar(candidato)
        numeracion = _numeracion_de(linea.texto)

        for seccion in rubrica.secciones:
            puntaje_max, alias_ganador = 0, ""
            for alias in seccion.aliases:
                puntaje = _puntuar(cand_norm, alias)
                if puntaje > puntaje_max or (puntaje == puntaje_max and len(alias) > len(alias_ganador)):
                    puntaje_max, alias_ganador = puntaje, alias
            if puntaje_max > 0:
                candidatos.setdefault(seccion.id, []).append(
                    _Match(seccion_id=seccion.id, linea=linea, encabezado=candidato,
                           puntaje=puntaje_max, numeracion=numeracion,
                           rotulo=linea.texto.rstrip().endswith(":"))
                )

        if any(_puntuar(cand_norm, extra) >= 2 for extra in _LIMITES_EXTRA):
            limites.append(
                _Match(seccion_id=None, linea=linea, encabezado=candidato,
                       puntaje=2, numeracion=numeracion)
            )

    # 2) Asignación en orden de rúbrica con desempate por orden del documento:
    #    entre los candidatos de mayor puntaje, se prefiere el primero que
    #    aparece DESPUÉS de la última sección ya asignada.
    advertencias: list[str] = []
    elegidos: dict[str, _Match] = {}
    ultimo_indice = -1
    for seccion in rubrica.secciones:
        lista = candidatos.get(seccion.id)
        if not lista:
            continue
        mejor_puntaje = max(m.puntaje for m in lista)
        mejores = [m for m in lista if m.puntaje == mejor_puntaje]
        en_orden = [m for m in mejores if m.linea.indice > ultimo_indice]
        # Preferir encabezados NUMERADOS y luego NO-RÓTULOS: descarta celdas de
        # tabla o menciones sueltas que empatan con el alias (p. ej. "Tipo de
        # investigación:" dentro de la matriz de consistencia).
        numerados = [m for m in en_orden if m.numeracion]
        eleccion = _sin_rotulo(numerados or en_orden or mejores)[0]
        if not en_orden:
            advertencias.append(
                f"{seccion.id} ({seccion.nombre}): encabezado fuera del orden esperado "
                f"del documento (pág. {eleccion.linea.pagina}); revisar la segmentación."
            )
        elegidos[seccion.id] = eleccion
        ultimo_indice = max(ultimo_indice, eleccion.linea.indice)

    # 3) Construcción de spans a partir de una elección de encabezados. Es una
    #    función para poder RECONSTRUIR tras la reparación por contenido (4).
    def construir_secciones(
        elegidos: dict[str, _Match],
    ) -> tuple[list[SeccionSegmentada], list[str]]:
        locales: list[str] = []
        cortes: list[_Match] = sorted(
            list(elegidos.values()) + limites, key=lambda m: m.linea.indice
        )

        def construir_span(match: _Match, fin_indice: int) -> tuple[str, int, int]:
            cuerpo = lineas[match.linea.indice + 1 : fin_indice]
            texto = "\n".join(l.texto for l in cuerpo).strip()
            pagina_fin = cuerpo[-1].pagina if cuerpo else match.linea.pagina
            return texto, len(texto.split()), pagina_fin

        def fin_directo(match: _Match, aliases: list[str]) -> int:
            siguientes = [c for c in cortes if c.linea.indice > match.linea.indice]
            fin = siguientes[0].linea.indice if siguientes else len(lineas)
            # Corte suave: un encabezado HERMANO de numeración (p. ej. "1. Título"
            # seguido de "2. Equipo investigador") cierra la sección aunque no sea
            # sección de la rúbrica. Guardas anti-listas: línea corta, con pinta de
            # encabezado y sin puntuación final de oración. Un hermano que matchea
            # aliases de la MISMA sección no corta (p. ej. "1.4. Justificación"
            # sigue perteneciendo a "Importancia y justificación").
            if match.numeracion:
                for linea in lineas[match.linea.indice + 1 : fin]:
                    plano = linea.texto.strip()
                    if (
                        len(plano) <= 70
                        and not plano.endswith((".", ",", ";", ":"))
                        and _son_hermanos(_numeracion_de(plano), match.numeracion)
                    ):
                        encabezado = _candidato_encabezado(plano)
                        if encabezado is None:
                            continue
                        propio = normalizar(encabezado)
                        if any(_puntuar(propio, alias) > 0 for alias in aliases):
                            continue  # hermano de la misma sección: no corta
                        return linea.indice
            return fin

        def fin_con_absorcion(match: _Match) -> int:
            """Extiende el fin saltando cortes que son sub-numeración del encabezado."""
            for corte in cortes:
                if corte.linea.indice <= match.linea.indice:
                    continue
                if _es_subnumeracion(corte.numeracion, match.numeracion):
                    continue  # hijo del contenedor: se absorbe
                return corte.linea.indice
            return len(lineas)

        secciones: list[SeccionSegmentada] = []
        for seccion in rubrica.secciones:
            match = elegidos.get(seccion.id)
            if match is None:
                secciones.append(
                    SeccionSegmentada(seccion_id=seccion.id, nombre=seccion.nombre, presente=False)
                )
                continue

            texto, palabras, pagina_fin = construir_span(match, fin_directo(match, seccion.aliases))

            # Absorción jerárquica: encabezado contenedor con cuerpo directo vacío.
            # Solo con numeración de profundidad >= 2 ("1.1."): un contenedor de
            # primer nivel absorbería capítulos enteros de otras secciones.
            if palabras < _MIN_PALABRAS_ABSORCION and _profundidad(match.numeracion) >= 2:
                fin_extendido = fin_con_absorcion(match)
                if fin_extendido > fin_directo(match, seccion.aliases):
                    texto_ext, palabras_ext, pagina_fin_ext = construir_span(match, fin_extendido)
                    if palabras_ext > palabras:
                        locales.append(
                            f"{seccion.id} ({seccion.nombre}): encabezado contenedor; se "
                            f"absorbieron sus subsecciones ({palabras} → {palabras_ext} palabras)."
                        )
                        texto, palabras, pagina_fin = texto_ext, palabras_ext, pagina_fin_ext

            secciones.append(
                SeccionSegmentada(
                    seccion_id=seccion.id,
                    nombre=seccion.nombre,
                    presente=True,
                    encontrado_como=match.encabezado,
                    pagina_inicio=match.linea.pagina,
                    pagina_fin=pagina_fin,
                    palabras=palabras,
                    texto=texto,
                )
            )
            # El título es corto por naturaleza: no se advierte por pocas palabras.
            if palabras < _MIN_PALABRAS_SECCION and "titulo" not in normalizar(seccion.nombre):
                locales.append(
                    f"{seccion.id} ({seccion.nombre}): solo {palabras} palabras; "
                    "posiblemente aún no redactada."
                )
        return secciones, locales

    secciones, locales = construir_secciones(elegidos)

    # 4) Reparación por contenido: si el encabezado elegido dejó la sección casi
    #    vacía (contenedor sin numeración, rótulo de tabla) y la MISMA sección
    #    tiene otro candidato del mismo puntaje que sí produce contenido, se
    #    reasigna. Cubre plantillas DOCX donde la numeración de Word se pierde
    #    y la absorción jerárquica no puede actuar (p. ej. "Descripción y
    #    delimitación del problema" vacía con el contenido real bajo
    #    "Problema central del estudio").
    for _ in range(2):  # hasta dos pasadas: una reasignación puede sanar a otra
        hubo_cambio = False
        for seccion in rubrica.secciones:
            actual = elegidos.get(seccion.id)
            if actual is None:
                continue
            # El título es corto por naturaleza: "repararlo" lo reasignaría a la
            # fila "Título de la investigación" de la matriz de consistencia.
            if "titulo" in normalizar(seccion.nombre):
                continue
            seg = next(s for s in secciones if s.seccion_id == seccion.id)
            if seg.palabras >= _MIN_PALABRAS_ABSORCION:
                continue
            lista = candidatos.get(seccion.id, [])
            alternativas = sorted(
                (m for m in lista
                 if m.puntaje == actual.puntaje and m.linea.indice != actual.linea.indice),
                key=lambda m: (m.rotulo, m.linea.indice),
            )
            mejor_alt, mejor_palabras = None, seg.palabras
            for alt in alternativas:
                prueba = dict(elegidos)
                prueba[seccion.id] = alt
                secs_alt, _ = construir_secciones(prueba)
                seg_alt = next(s for s in secs_alt if s.seccion_id == seccion.id)
                if seg_alt.palabras > mejor_palabras:
                    mejor_alt, mejor_palabras = alt, seg_alt.palabras
                if seg_alt.palabras >= _MIN_PALABRAS_ABSORCION:
                    break  # primer candidato con contenido suficiente en orden
            if mejor_alt is not None:
                advertencias.append(
                    f"{seccion.id} ({seccion.nombre}): el encabezado de la pág. "
                    f"{actual.linea.pagina} dejaba {seg.palabras} palabras; se reasignó "
                    f"al de la pág. {mejor_alt.linea.pagina} ({mejor_palabras} palabras)."
                )
                elegidos[seccion.id] = mejor_alt
                secciones, locales = construir_secciones(elegidos)
                hubo_cambio = True
        if not hubo_cambio:
            break
    advertencias.extend(locales)

    # Caso especial aditivo: rescata el Título en plantillas donde el rótulo lleva
    # su valor en la misma línea. Solo llena S01 si aún no está presente.
    advertencias.extend(
        _reparar_inline_titulo(lineas, paginas_indice, rubrica, secciones)
    )
    advertencias.extend(_reparar_convenciones_upao(lineas, paginas_indice, rubrica, secciones))

    encontradas = sum(1 for s in secciones if s.presente)
    if encontradas < umbral_llm and fallback_llm is not None:
        return _anotar_palabras_propias(fallback_llm(doc, rubrica))
    if encontradas < umbral_llm:
        advertencias.append(
            f"Segmentación pobre: solo {encontradas}/{len(rubrica.secciones)} secciones "
            "detectadas por heurística. Revisar el documento o activar el respaldo LLM."
        )
    if not doc.paginacion_real:
        advertencias.append(
            "DOCX sin paginación real: las páginas del reporte son aproximadas "
            "(bloques de ~350 palabras)."
        )

    return _anotar_palabras_propias(
        ResultadoSegmentacion(
            secciones=secciones,
            advertencias=advertencias,
            paginas_indice=paginas_indice,
        )
    )


# ── Convenciones de la plantilla UPAO que los encabezados no capturan ────────
# Se aplican SOLO cuando la sección quedó sin contenido propio evaluable; nunca
# reemplazan una sección que ya tiene texto del estudiante.
_RE_CABECERA_CARATULA = re.compile(
    r"universidad\s+privada\s+antenor\s+orrego|facultad\s+de\s+ingenier[ií]a|"
    r"programa\s+de\s+estudio\s+de\s+ingenier[ií]a(\s+de)?(\s+computaci[oó]n\s+y\s+sistemas)?|"
    r"proyecto\s+de\s+tesis\s+para\s+optar\s+el\s+t[ií]tulo\s+profesional\s+de|"
    r"ingenier[oa]\s+(en|de)\s+computaci[oó]n\s+y\s+sistemas|"
    r"ingenier[ií]a\s+(en|de)\s+computaci[oó]n\s+y\s+sistemas|"
    r"(de\s+)?computaci[oó]n\s+y\s+sistemas\s*\.?|ingenier[ií]a\s*\.?",
    re.IGNORECASE,
)
_RE_FIN_CARATULA = re.compile(r"l[ií]nea\s+de\s+investigaci[oó]n", re.IGNORECASE)
_RE_PREGUNTA = re.compile(r"¿[^¿?]{15,}\?")


def _reparar_convenciones_upao(
    lineas: list[_Linea],
    paginas_indice: list[int],
    rubrica: Rubrica,
    secciones: list[SeccionSegmentada],
) -> list[str]:
    """Tres convenciones de la plantilla UPAO que la segmentación por
    encabezados no recupera:
    - S01: el título solo está en la carátula (página 1), no en "1. Título".
    - S12: la clasificación del diseño está en "Generalidades, 3.2. De acuerdo
      con la técnica de contrastación" y el apartado 4.3 sigue vacío.
    - S03: la pregunta general está dentro del párrafo de la descripción del
      problema, sin encabezado propio en línea aparte.
    """
    from ingest.plantilla import palabras_propias

    advertencias: list[str] = []
    por_id = {s.seccion_id: s for s in secciones}
    nombres = {s.id: s.nombre for s in rubrica.secciones}

    def vacia(seccion_id: str) -> bool:
        s = por_id.get(seccion_id)
        return s is None or not s.presente or palabras_propias(s.texto) < MIN_PALABRAS_EVALUABLES

    def asignar(seccion_id: str, texto: str, como: str, pagina: int, detalle: str) -> None:
        if seccion_id not in nombres or palabras_propias(texto) < MIN_PALABRAS_EVALUABLES:
            return
        nueva = SeccionSegmentada(
            seccion_id=seccion_id, nombre=nombres[seccion_id], presente=True,
            encontrado_como=como, pagina_inicio=pagina, pagina_fin=pagina,
            palabras=len(texto.split()), texto=texto,
        )
        for i, s in enumerate(secciones):
            if s.seccion_id == seccion_id:
                secciones[i] = nueva
        advertencias.append(f"{seccion_id} ({nombres[seccion_id]}): {detalle}")

    # S01 ← título de la carátula
    if vacia("S01") and lineas:
        primera = lineas[0].pagina
        caratula = " ".join(l.texto for l in lineas if l.pagina == primera)
        fin = _RE_FIN_CARATULA.search(caratula)
        if fin:
            titulo = _RE_CABECERA_CARATULA.sub(" ", caratula[: fin.start()])
            titulo = re.sub(r"\s+", " ", titulo).strip(" .:-")
            if 5 <= len(titulo.split()) <= 60:
                asignar("S01", titulo, "carátula", primera,
                        "recuperado de la carátula (el apartado '1. Título' no tiene texto propio).")

    # S12 ← Generalidades: técnica de contrastación
    if vacia("S12"):
        for i, linea in enumerate(lineas):
            if linea.pagina in paginas_indice or "tecnica de contrastacion" not in normalizar(linea.texto):
                continue
            bloque: list[str] = [linea.texto.split(":", 1)[-1] if ":" in linea.texto else ""]
            for siguiente in lineas[i + 1 : i + 30]:
                t = siguiente.texto.strip()
                fin_bloque = re.match(r"^(4\.?\s|4\.\s*l[ií]nea|ii\.)", t, re.IGNORECASE)
                if fin_bloque or "linea de investigacion" in normalizar(t):
                    break
                bloque.append(t)
            cuerpo = " ".join(b for b in bloque if b).strip()
            if palabras_propias(cuerpo) < MIN_PALABRAS_EVALUABLES:
                break  # rótulo sin desarrollo ("Experimental.") o vacío: no hay qué evaluar
            texto = "De acuerdo con la técnica de contrastación: " + cuerpo
            asignar("S12", texto, "Generalidades: técnica de contrastación", linea.pagina,
                    "tomado de Generalidades (técnica de contrastación); el apartado del diseño no tiene texto propio.")
            break

    # S03 ← preguntas dentro de la descripción del problema
    if vacia("S03") and "S02" in por_id and por_id["S02"].presente:
        preguntas = _RE_PREGUNTA.findall(por_id["S02"].texto.replace("\n", " "))
        if preguntas:
            asignar("S03", " ".join(re.sub(r"\s+", " ", p) for p in preguntas),
                    "pregunta dentro de la descripción", por_id["S02"].pagina_inicio or 0,
                    "preguntas extraídas de la descripción del problema (sin encabezado propio).")
    return advertencias


def _anotar_palabras_propias(resultado: ResultadoSegmentacion) -> ResultadoSegmentacion:
    """Cuenta en cada sección presente las palabras que no son de la plantilla.

    Una sección que solo conserva encabezados, esqueletos de tabla o ejemplos
    de la plantilla no tiene contenido evaluable: no se envía a los jueces y
    se puntúa 0 de forma determinista (Regla 3 de la rúbrica)."""
    from ingest.plantilla import palabras_propias

    for seccion in resultado.secciones:
        if seccion.presente:
            seccion.palabras_propias = palabras_propias(seccion.texto)
            if seccion.palabras_propias < MIN_PALABRAS_EVALUABLES <= seccion.palabras:
                resultado.advertencias.append(
                    f"{seccion.seccion_id} ({seccion.nombre}): solo contiene texto de la "
                    "plantilla; se puntúa 0 sin enviarla a los jueces."
                )
    return resultado
