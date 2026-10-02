"""Métricas determinísticas de texto (Python puro + textstat, sin LLM).

Se calculan y muestran en cada evaluación:
- Legibilidad en español: índices Fernández-Huerta y Szigriszt-Pazos (textstat).
- Riqueza léxica: TTR y MTLD (lexical-diversity).
- Estadísticas básicas: palabras totales y por sección, longitud media de oración.
- Citas y referencias: detección heurística por regex de citas en texto estilo
  APA (autor, año) y de la lista de referencias; conteos y dos listas de
  inconsistencia MARCADAS COMO APROXIMADAS.
- Completitud estructural: secciones presentes sobre el total de la rúbrica.

Las métricas de validación del instrumento (QWK, ICC, etc.) NO van aquí: se
calculan en cli/validate.py sobre un conjunto de proyectos contra jurados.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from graph.segmenter import ResultadoSegmentacion
from ingest.extractors import DocumentoExtraido

# ── Modelos de salida ────────────────────────────────────────────────────────


class Legibilidad(BaseModel):
    fernandez_huerta: Optional[float] = None
    szigriszt_pazos: Optional[float] = None
    interpretacion: Optional[str] = None  # banda del índice Fernández-Huerta


class RiquezaLexica(BaseModel):
    ttr: Optional[float] = None
    mtld: Optional[float] = None


class CitasReferencias(BaseModel):
    citas_en_texto: int = 0
    referencias_en_lista: int = 0
    citas_sin_referencia: list[str] = Field(default_factory=list)
    referencias_nunca_citadas: list[str] = Field(default_factory=list)
    aproximado: bool = True  # heurístico por regex; siempre se marca como tal


class Completitud(BaseModel):
    presentes: int
    total: int
    ratio: float


class MetricasDeterministicas(BaseModel):
    palabras_totales: int
    palabras_por_seccion: dict[str, int]
    longitud_media_oracion: Optional[float] = None
    legibilidad: Legibilidad
    riqueza_lexica: RiquezaLexica
    citas_referencias: CitasReferencias
    completitud: Completitud


# ── Legibilidad (textstat) ───────────────────────────────────────────────────

_BANDAS_FH = [
    (90, "muy fácil"), (80, "fácil"), (70, "algo fácil"), (60, "normal"),
    (50, "algo difícil"), (30, "difícil"), (0, "muy difícil"),
]


def _legibilidad(texto: str) -> Legibilidad:
    if len(texto.split()) < 30:
        return Legibilidad()
    import textstat

    textstat.set_lang("es")
    fh = round(float(textstat.fernandez_huerta(texto)), 2)
    sp = round(float(textstat.szigriszt_pazos(texto)), 2)
    interpretacion = next((nombre for umbral, nombre in _BANDAS_FH if fh >= umbral), "muy difícil")
    return Legibilidad(fernandez_huerta=fh, szigriszt_pazos=sp, interpretacion=interpretacion)


# ── Riqueza léxica ───────────────────────────────────────────────────────────

_RE_PALABRA = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def _tokens(texto: str) -> list[str]:
    return [t.lower() for t in _RE_PALABRA.findall(texto)]


def _mtld_direccion(tokens: list[str], umbral: float = 0.72) -> float:
    """Una pasada del MTLD (McCarthy y Jarvis, 2010): cuenta factores donde el
    TTR acumulado cae bajo 0.72 (con mínimo de 10 tokens por factor, como la
    implementación de referencia de lexical-diversity), más factor parcial."""
    if not tokens:
        return 0.0
    factores = 0.0
    tipos: set[str] = set()
    conteo = 0
    ttr = 1.0
    for i, token in enumerate(tokens):
        conteo += 1
        tipos.add(token)
        ttr = len(tipos) / conteo
        # El último tramo siempre cuenta como factor parcial (nunca completo),
        # igual que la implementación de referencia.
        if i + 1 < len(tokens) and ttr < umbral and conteo >= 10:
            factores += 1
            tipos = set()
            conteo = 0
            ttr = 1.0
    factores += (1 - ttr) / (1 - umbral)
    return len(tokens) / factores if factores > 0 else 0.0


def _mtld(tokens: list[str]) -> float:
    """MTLD bidireccional: promedio de la pasada hacia adelante y hacia atrás
    (implementación propia; evita depender de pkg_resources, retirado de
    setuptools >= 81)."""
    return (_mtld_direccion(tokens) + _mtld_direccion(list(reversed(tokens)))) / 2


def _riqueza_lexica(texto: str) -> RiquezaLexica:
    tokens = _tokens(texto)
    if len(tokens) < 50:
        return RiquezaLexica()
    ttr = round(len(set(tokens)) / len(tokens), 4)
    return RiquezaLexica(ttr=ttr, mtld=round(_mtld(tokens), 2))


# ── Oraciones ────────────────────────────────────────────────────────────────

_RE_ORACION = re.compile(r"[.!?]+(?:\s|$)")


def _longitud_media_oracion(texto: str) -> Optional[float]:
    oraciones = [o.strip() for o in _RE_ORACION.split(texto) if len(o.split()) >= 3]
    if not oraciones:
        return None
    return round(sum(len(o.split()) for o in oraciones) / len(oraciones), 2)


# ── Citas APA vs lista de referencias (heurístico) ───────────────────────────

_APELLIDO = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñü'\-]+"
# Narrativa: "García (2020)", "García y López (2021)", "Pérez et al. (2019)"
_RE_CITA_NARRATIVA = re.compile(
    rf"({_APELLIDO})(?:\s*(?:,|y|e|&)\s*{_APELLIDO})*(?:\s+et\s+al\.?)?\s*\((\d{{4}})[a-z]?\)"
)
# Parentética: contenido de paréntesis con año; se separa por ";"
_RE_PARENTESIS = re.compile(r"\(([^()]*\d{4}[a-z]?[^()]*)\)")
_RE_CITA_EN_PARENTESIS = re.compile(rf"({_APELLIDO})[^;()]*?(\d{{4}})[a-z]?")
# Inicio de una entrada de la lista de referencias: "Apellido, ..." o
# "Apellido Compuesto, ..." (las entradas APA suelen partirse en varias
# líneas: se separa por inicios de entrada y se busca el año DENTRO de cada
# entrada completa).
_RE_INICIO_ENTRADA = re.compile(rf"\n(?=\s*{_APELLIDO}(?:\s+{_APELLIDO})?,\s)")
_RE_APELLIDO_ENTRADA = re.compile(rf"^\s*({_APELLIDO}(?:\s+{_APELLIDO})?)\s*,")
_RE_ANIO_ENTRADA = re.compile(r"\((\d{4})[a-z]?\)")

_RE_TITULO_REFERENCIAS = re.compile(
    r"^\s*(?:\d{1,2}[\.\)]?\s*)?(REFERENCIAS(?:\s+BIBLIOGR[ÁA]FICAS)?|BIBLIOGRAF[ÍI]A)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_RE_FIN_REFERENCIAS = re.compile(r"^\s*(ANEXOS?|AP[ÉE]NDICES?)\s*$", re.IGNORECASE | re.MULTILINE)


def _extraer_lista_referencias(texto_completo: str) -> str:
    m = _RE_TITULO_REFERENCIAS.search(texto_completo)
    if not m:
        return ""
    resto = texto_completo[m.end():]
    fin = _RE_FIN_REFERENCIAS.search(resto)
    return resto[: fin.start()] if fin else resto


def _tokens_apellido(apellido: str) -> set[str]:
    """'zéniz ramos' → {'zéniz', 'ramos'}; ignora partículas cortas ('de', 'la')."""
    return {t for t in re.split(r"[\s\-]+", apellido.strip()) if len(t) >= 3}


def _apellidos_equivalentes(a: str, b: str) -> bool:
    """Apellidos compuestos: emparejan si comparten algún token significativo.

    La cita narrativa suele capturar solo UN apellido y no siempre el primero:
    'Ramos et al. (2024)' debe emparejar con la entrada 'Zéniz Ramos, D. F.'
    y 'Maldonado et al. (2023)' con 'Castro Maldonado, J. J.'."""
    return a == b or bool(_tokens_apellido(a) & _tokens_apellido(b))


def _emparejadas(pares_a: set[tuple[str, str]], pares_b: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Elementos de A con al menos un equivalente (apellido~, mismo año) en B."""
    return {
        (apellido, anio)
        for apellido, anio in pares_a
        if any(anio == anio_b and _apellidos_equivalentes(apellido, apellido_b)
               for apellido_b, anio_b in pares_b)
    }


def _formatear(pares: set[tuple[str, str]]) -> list[str]:
    return sorted(f"{apellido} ({anio})" for apellido, anio in pares)


def _citas_referencias(texto_cuerpo: str, texto_completo: str) -> CitasReferencias:
    citas: set[tuple[str, str]] = set()
    for m in _RE_CITA_NARRATIVA.finditer(texto_cuerpo):
        citas.add((m.group(1).lower(), m.group(2)))
    for m in _RE_PARENTESIS.finditer(texto_cuerpo):
        for fragmento in m.group(1).split(";"):
            cm = _RE_CITA_EN_PARENTESIS.search(fragmento)
            # Evitar falsos positivos tipo "(ver Tabla 3, 2020)" exige apellido al inicio
            if cm and fragmento.strip().startswith(cm.group(1)):
                citas.add((cm.group(1).lower(), cm.group(2)))

    lista = _extraer_lista_referencias(texto_completo)
    referencias: set[tuple[str, str]] = set()
    for entrada in _RE_INICIO_ENTRADA.split("\n" + lista):
        apellido = _RE_APELLIDO_ENTRADA.match(entrada)
        anio = _RE_ANIO_ENTRADA.search(entrada)
        if apellido and anio:
            referencias.add((apellido.group(1).lower(), anio.group(1)))

    return CitasReferencias(
        citas_en_texto=len(citas),
        referencias_en_lista=len(referencias),
        citas_sin_referencia=_formatear(citas - _emparejadas(citas, referencias)),
        referencias_nunca_citadas=_formatear(referencias - _emparejadas(referencias, citas)),
    )


# ── Punto de entrada ─────────────────────────────────────────────────────────


def calcular_metricas(
    doc: DocumentoExtraido, segmentacion: ResultadoSegmentacion
) -> MetricasDeterministicas:
    presentes = segmentacion.presentes
    texto_cuerpo = "\n\n".join(s.texto for s in presentes) or doc.texto_completo

    return MetricasDeterministicas(
        palabras_totales=len(texto_cuerpo.split()),
        palabras_por_seccion={s.seccion_id: s.palabras for s in segmentacion.secciones},
        longitud_media_oracion=_longitud_media_oracion(texto_cuerpo),
        legibilidad=_legibilidad(texto_cuerpo),
        riqueza_lexica=_riqueza_lexica(texto_cuerpo),
        citas_referencias=_citas_referencias(texto_cuerpo, doc.texto_completo),
        completitud=Completitud(
            presentes=len(presentes),
            total=len(segmentacion.secciones),
            ratio=round(len(presentes) / len(segmentacion.secciones), 4)
            if segmentacion.secciones
            else 0.0,
        ),
    )
