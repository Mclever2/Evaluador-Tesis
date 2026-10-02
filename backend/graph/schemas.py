"""Esquemas de salida estructurada del panel y del resultado agregado (pydantic v2)."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

# ── Salidas estructuradas de los jueces (una llamada por par juez-sección) ───

NivelTresNiveles = Literal["cumple", "parcial", "no_cumple"]
NivelDicotomico = Literal["cumple", "no_cumple"]

DIMENSIONES_TRANSVERSALES = ("coherencia_interna", "formalidad_registro", "claridad_tono")


class CalificacionItemPonderado(BaseModel):
    """Calificación de un ítem en la rúbrica ponderada de 3 niveles.

    `deficiencias` va ANTES de `nivel` a propósito: la salida estructurada se
    genera en el orden de los campos, y auditar lo que falta antes de decidir
    el nivel reduce el sesgo de indulgencia (protocolo de juez auditor).
    """

    item_id: str = Field(description="Id del criterio, tal como aparece en la lista (p. ej. '1.1')")
    deficiencias: str = Field(
        description="Qué componentes del criterio faltan, están incompletos o son "
        "incorrectos, en 40 palabras o menos; 'ninguna' solo si no falta nada"
    )
    nivel: NivelTresNiveles
    evidencia: str = Field(
        description="Cita textual del proyecto de 25 palabras o menos con referencia de "
        "sección; si el nivel es no_cumple por ausencia: 'no se encontró evidencia'"
    )
    observacion: str = Field(
        description="Diagnóstico de 30 palabras o menos, sin proponer redacciones alternativas"
    )


class RespuestaSeccionPonderada(BaseModel):
    calificaciones: list[CalificacionItemPonderado]


class CalificacionItemDicotomico(BaseModel):
    """Calificación de un ítem en la rúbrica dicotómica (Cumple = 1 / No cumple = 0).

    Mismo protocolo de juez auditor: `deficiencias` antes de `nivel`. El esquema
    no admite "parcial": la salida estructurada lo impide en origen.
    """

    item_id: str = Field(description="Id del criterio, tal como aparece en la lista (p. ej. '1.1')")
    verificacion: str = Field(
        description="Componente por componente de ESTE criterio: 'componente: cita breve del "
        "texto' o 'componente: ausente'. 60 palabras o menos"
    )
    deficiencias: str = Field(
        description="Qué componentes de ESTE criterio faltan, están incompletos, son incorrectos "
        "o están contradichos, según la verificación; 'ninguna' si no falta nada"
    )
    nivel: NivelDicotomico
    evidencia: str = Field(
        description="Cita textual del proyecto de 25 palabras o menos con referencia de "
        "sección; si el nivel es no_cumple por ausencia: 'no se encontró evidencia'"
    )
    observacion: str = Field(
        description="Diagnóstico de 30 palabras o menos, sin proponer redacciones alternativas"
    )


class RespuestaSeccionDicotomica(BaseModel):
    calificaciones: list[CalificacionItemDicotomico]


class CalificacionItemEscala(BaseModel):
    """Calificación de un ítem en escala directa 0 a 3 (ficha UPAO)."""

    item_id: str
    deficiencias: str = Field(
        description="Qué componentes del criterio faltan, están incompletos o son "
        "incorrectos, en 40 palabras o menos; 'ninguna' solo si no falta nada"
    )
    puntaje: int = Field(ge=0, le=3, description="0 Insuficiente, 1 Regular, 2 Bueno, 3 Excelente")
    evidencia: str
    observacion: str


class RespuestaSeccionEscala(BaseModel):
    calificaciones: list[CalificacionItemEscala]


class CalificacionDimension(BaseModel):
    dimension: Literal["coherencia_interna", "formalidad_registro", "claridad_tono"]
    puntaje: int = Field(ge=1, le=5)
    justificacion: str = Field(description="40 palabras o menos")


class RespuestaTransversales(BaseModel):
    dimensiones: list[CalificacionDimension]


class AsignacionSeccion(BaseModel):
    seccion_id: str
    indice_linea: Optional[int] = None


class RespuestaSegmentacionLLM(BaseModel):
    asignaciones: list[AsignacionSeccion]


RespuestaSeccion = Union[RespuestaSeccionPonderada, RespuestaSeccionEscala, RespuestaSeccionDicotomica]


class ResultadoJuez(BaseModel):
    """Todo lo producido por un juez sobre un proyecto."""

    juez: int
    modelo: str
    # seccion_id → respuesta; None cuando el juez falló persistentemente (hueco)
    secciones: dict[str, Optional[RespuestaSeccion]] = Field(default_factory=dict)
    transversales: Optional[RespuestaTransversales] = None
    huecos: list[str] = Field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0


# ── Resultado agregado de la evaluación ──────────────────────────────────────

NivelJuez = Union[str, int]


class ItemEvaluado(BaseModel):
    id: str
    criterio: str
    niveles_jueces: dict[str, Optional[NivelJuez]] = Field(default_factory=dict)
    nivel_final: Optional[NivelJuez] = None
    puntaje: float = 0.0
    puntaje_max: float = 0.0
    discrepancia: bool = False
    evidencia: str = ""
    observacion: str = ""
    # Calificación completa de cada juez (verificación, deficiencias, nivel,
    # evidencia, observación): trazabilidad del voto individual.
    detalle_jueces: dict[str, dict] = Field(default_factory=dict)


class SeccionEvaluada(BaseModel):
    id: str
    nombre: str
    presente: bool
    activa: bool
    subtotal: Optional[float] = None
    max: float
    items: list[ItemEvaluado] = Field(default_factory=list)


class DimensionTransversal(BaseModel):
    dimension: str
    puntajes_jueces: dict[str, Optional[int]] = Field(default_factory=dict)
    mediana: Optional[int] = None
    justificacion: str = ""


class PanelInfo(BaseModel):
    pct_discrepancia: float = 0.0
    items_marcados: list[str] = Field(default_factory=list)
    panel_incompleto: bool = False
    huecos: list[str] = Field(default_factory=list)


class Costo(BaseModel):
    tokens_entrada: int = 0
    tokens_salida: int = 0
    usd_estimado: Optional[float] = None


class EvaluacionResultado(BaseModel):
    project_id: str
    rubric_id: str
    mode: Literal["completo", "progresivo"]
    timestamp: str
    config_modelos: dict[str, str]
    seed: int
    temperature: float
    prompts_hash: str
    reporte_indexacion: dict
    secciones: list[SeccionEvaluada]
    total: float
    puntaje_max_activo: float
    total_normalizado: Optional[float] = None
    nivel: Optional[str] = None
    nota_vigesimal: Optional[int] = None
    dimensiones_transversales: list[DimensionTransversal] = Field(default_factory=list)
    metricas_deterministicas: Optional[dict] = None  # se llena en el módulo metrics
    panel: PanelInfo = Field(default_factory=PanelInfo)
    costo: Costo = Field(default_factory=Costo)
