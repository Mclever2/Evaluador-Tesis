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

_RE_PREFIJO_NUM = re.compile(
    r"^(?:cap[ií]tulo\s+[ivxlcmd\d]+\s*[:.\-]?\s*|(?:\d{1,2}(?:\.\d{1,2})*|[IVXLCMD]+)\s*[\.\)\-:]?\s+)",
    re.IGNORECASE,
)
_RE_NUMERACION = re.compile(r"^\s*((?:\d{1,2}\.)+\d{0,2}|\d{1,2}|[IVXLCMD]+)[\.\)]?\s+")
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
    texto: str = ""


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


def _puntuar(candidato_norm: str, alias: str) -> int:
    if candidato_norm == alias:
        return 3
    if candidato_norm.startswith(alias) and len(candidato_norm) <= len(alias) + 30:
        return 2
    if alias.startswith(candidato_norm) and len(candidato_norm) >= 6:
        return 2
    if f" {alias} " in f" {candidato_norm} " and len(candidato_norm) <= len(alias) + 45:
        return 1
    return 0


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
                           puntaje=puntaje_max, numeracion=numeracion)
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
        # Preferir encabezados NUMERADOS: descarta celdas de tabla o menciones
        # sueltas que empatan con el alias (p. ej. "Tipo de investigación"
        # dentro de la matriz de consistencia).
        numerados = [m for m in en_orden if m.numeracion]
        eleccion = (numerados or en_orden or mejores)[0]
        if not en_orden:
            advertencias.append(
                f"{seccion.id} ({seccion.nombre}): encabezado fuera del orden esperado "
                f"del documento (pág. {eleccion.linea.pagina}); revisar la segmentación."
            )
        elegidos[seccion.id] = eleccion
        ultimo_indice = max(ultimo_indice, eleccion.linea.indice)

    # 3) Cortes ordenados por posición en el documento.
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
                    advertencias.append(
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
            advertencias.append(
                f"{seccion.id} ({seccion.nombre}): solo {palabras} palabras; "
                "posiblemente aún no redactada."
            )

    encontradas = sum(1 for s in secciones if s.presente)
    if encontradas < umbral_llm and fallback_llm is not None:
        return fallback_llm(doc, rubrica)
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

    return ResultadoSegmentacion(
        secciones=secciones,
        advertencias=advertencias,
        paginas_indice=paginas_indice,
    )
