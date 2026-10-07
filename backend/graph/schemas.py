"""Esquemas de salida estructurada del panel y del resultado agregado (pydantic v2)."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

# ── Salidas estructuradas de los jueces (una llamada por par juez-sección) ───

NivelTresNiveles = Literal["cumple", "parcial", "no_cumple"]
NivelDicotomico = Literal["cumple", "no_cumple"]

# La coherencia interna 1-5 (juicio global del panel) se retiró: tenía bajo acuerdo entre jueces
# (CCI = 0.40). La reemplaza la coherencia global (graph/coherencia_global.py), con nota por regla fija.
# "coherencia_interna" sigue admitida en el Literal para poder leer evaluaciones anteriores.
DIMENSIONES_TRANSVERSALES = ("formalidad_registro", "claridad_tono")


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


# ── Salidas estructuradas de los análisis de coherencia (externos a la rúbrica) ──

FuncionToulmin = Literal["afirmacion", "dato", "garantia", "respaldo", "refutacion", "ninguno"]


class EtiquetaOracion(BaseModel):
    id: int
    funcion: FuncionToulmin
    responde_en: Optional[int] = Field(default=None, description="Solo para refutacion: id de la oración que "
                                                                 "responde a la objeción; null si no se responde.")


class RespuestaArgumentacion(BaseModel):
    etiquetas: list[EtiquetaOracion]


TipoContradiccion = Literal["variables", "unidad_analisis", "proposito", "diseno", "muestreo",
                            "numero_correspondencia", "otra"]


class Contradiccion(BaseModel):
    tipo: TipoContradiccion
    seccion_a: str = Field(description="Nombre de la primera sección involucrada")
    cita_a: str = Field(description="Fragmento LITERAL de la primera sección, 30 palabras o menos")
    seccion_b: str = Field(description="Nombre de la segunda sección involucrada")
    cita_b: str = Field(description="Fragmento LITERAL de la segunda sección, 30 palabras o menos")
    explicacion: str = Field(description="Por qué ambas partes se contradicen, 30 palabras o menos")


class RespuestaCoherencia(BaseModel):
    contradicciones: list[Contradiccion] = Field(default_factory=list)


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


class OracionArgumentativa(BaseModel):
    id: int
    oracion: str
    funcion: str
    responde_en: Optional[int] = None
    calificadores: list[str] = Field(default_factory=list)


class SeccionArgumentativa(BaseModel):
    seccion_id: str
    nombre: str
    elegible: bool
    palabras: int = 0
    proporcion_oraciones: float = 0.0
    oraciones: int = 0
    conteo: dict[str, int] = Field(default_factory=dict)
    oraciones_con_calificador: int = 0
    refutaciones_respondidas: int = 0
    presentes: list[str] = Field(default_factory=list)
    indice_estructural: Optional[float] = None  # componentes de Toulmin presentes / 6
    nivel: Optional[int] = None  # 0-5, adaptado de Erduran et al. (2004); solo descriptivo
    detalle: list[OracionArgumentativa] = Field(default_factory=list)


class ResultadoArgumentacion(BaseModel):
    """Índice argumentativo (Toulmin): coherencia DENTRO de las secciones argumentativas."""

    version: str
    modelo: str
    secciones: list[SeccionArgumentativa] = Field(default_factory=list)
    indice_proyecto: Optional[float] = None  # media de las secciones elegibles


class ContradiccionVerificada(Contradiccion):
    gravedad: Literal["nucleo", "menor"]


class ResultadoCoherenciaGlobal(BaseModel):
    """Coherencia global: contradicciones verificadas entre partes del proyecto y nota por regla fija."""

    version: str
    modelo: str
    nota: int  # 1-5
    contradicciones_nucleo: int = 0
    contradicciones_menores: int = 0
    propuestas: int = 0
    contradicciones: list[ContradiccionVerificada] = Field(default_factory=list)
    rechazadas: list[dict] = Field(default_factory=list)


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
    # Análisis de coherencia externos a la rúbrica: no alteran sus puntajes. None si no se ejecutaron.
    argumentacion: Optional[ResultadoArgumentacion] = None
    coherencia_global: Optional[ResultadoCoherenciaGlobal] = None
    panel: PanelInfo = Field(default_factory=PanelInfo)
    costo: Costo = Field(default_factory=Costo)
