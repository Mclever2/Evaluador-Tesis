"""Grafo de evaluación del ECM (LangGraph).

Topología: orquestador-segmentador → (juez_1 ‖ juez_2 ‖ juez_3) → agregador.
Después del grafo se calculan, sin alterar la rúbrica: las métricas determinísticas, el índice
argumentativo de Toulmin (graph/argumentacion.py) y la coherencia global (graph/coherencia_global.py).

Los invocadores LLM se INYECTAN: los tests usan dobles con la misma firma y
nunca llaman a la API. Cada resultado registra versión de rúbrica, modo,
modelos, hash de prompts, seed, timestamp, tokens y costo estimado.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from typing import Annotated, Callable, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from anonymizer.anonymizer import ReporteAnonimizacion
from app.config import get_settings
from graph.aggregator import agregar
from graph.judges import ConfigJuez, ContextoRag, construir_configuracion_panel, evaluar_con_juez
from graph.llm import Invocador, UsoLLM, costo_usd, crear_invocador, crear_invocadores_panel
from graph.prompts import hash_prompts
from graph.schemas import Costo, EvaluacionResultado, ResultadoJuez
from graph.segmenter import ResultadoSegmentacion, segmentar
from graph.segmenter_llm import crear_fallback_llm
from ingest.extractors import DocumentoExtraido
from rubrics import RUBRICS_DIR, load_rubric
from rubrics.models import Rubrica
from rubrics.parser import normalizar

OnEvento = Callable[[dict], None]


class ConfigEvaluacion(BaseModel):
    project_id: str
    rubric_id: str = "especifica_v1"
    mode: Literal["completo", "progresivo"] = "completo"
    # Modo progresivo: semanas cuyo contenido ya corresponde entregar. Las
    # secciones activas son la UNIÓN de las semanas listadas según
    # backend/rubrics/config_semanas.json (editable sin tocar código).
    semanas_activas: Optional[list[int]] = None
    # ficha_upao_v1: excluir aspectos administrativos (ítems 28-31) cuando el
    # curso no exige cronograma ni presupuesto.
    incluir_administrativos: bool = True


def secciones_activas_para(rubrica: Rubrica, config: ConfigEvaluacion) -> set[str]:
    ids = {s.id for s in rubrica.secciones}
    if config.mode == "progresivo" and config.semanas_activas:
        ruta = RUBRICS_DIR / "config_semanas.json"
        mapa = json.loads(ruta.read_text(encoding="utf-8")).get(rubrica.id, {})
        activas: set[str] = set()
        for semana in config.semanas_activas:
            activas |= set(mapa.get(str(semana), []))
        if activas:
            ids &= activas
    if not config.incluir_administrativos:
        ids -= {s.id for s in rubrica.secciones if "administrativ" in normalizar(s.nombre)}
    return ids


class _Estado(TypedDict):
    doc: DocumentoExtraido
    rubrica: Rubrica
    config: ConfigEvaluacion
    reporte_anonimizacion: Optional[ReporteAnonimizacion]
    segmentacion: Optional[ResultadoSegmentacion]
    secciones_activas: set[str]
    resultados_jueces: Annotated[list[ResultadoJuez], operator.add]
    usos_extra: Annotated[list[UsoLLM], operator.add]
    resultado: Optional[EvaluacionResultado]


class PanelEvaluador:
    """Ensambla y ejecuta el grafo con los invocadores inyectados."""

    def __init__(
        self,
        invocadores: Optional[dict[int, Invocador]] = None,
        modelos: Optional[dict[int, str]] = None,
        contexto_rag: Optional[ContextoRag] = None,
        on_evento: Optional[OnEvento] = None,
        invocador_analisis: Optional[Invocador] = None,
        modelo_analisis: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.modelos = modelos or {
            1: settings.judge1_model, 2: settings.judge2_model, 3: settings.judge3_model
        }
        # Análisis de coherencia (Toulmin y coherencia global). En producción se crea su invocador; si
        # los jueces se inyectan (pruebas) y no se inyecta este, los análisis no se ejecutan.
        self.modelo_analisis = modelo_analisis or settings.analysis_model
        if invocador_analisis is None and invocadores is None:
            invocador_analisis = crear_invocador(self.modelo_analisis, settings)
        self.invocador_analisis = invocador_analisis
        self.invocadores = invocadores or crear_invocadores_panel(settings)
        self.contexto_rag = contexto_rag
        self.on_evento = on_evento or (lambda e: None)
        self.jueces: list[ConfigJuez] = construir_configuracion_panel(self.modelos)
        self._grafo = self._construir()

    # ── Nodos ────────────────────────────────────────────────────────────────
    def _nodo_orquestador(self, estado: _Estado) -> dict:
        self.on_evento({"tipo": "fase", "detalle": "Segmentando el proyecto por secciones"})
        usos: list[UsoLLM] = []
        fallback = crear_fallback_llm(self.invocadores[1], on_uso=usos.append)
        segmentacion = segmentar(estado["doc"], estado["rubrica"], fallback_llm=fallback)
        segmentacion.anonimizacion = estado["reporte_anonimizacion"]
        activas = secciones_activas_para(estado["rubrica"], estado["config"])
        self.on_evento(
            {"tipo": "fase",
             "detalle": f"{len(segmentacion.presentes)}/{len(estado['rubrica'].secciones)} "
                        f"secciones detectadas ({segmentacion.metodo})"}
        )
        return {"segmentacion": segmentacion, "secciones_activas": activas, "usos_extra": usos}

    def _nodo_juez(self, cfg: ConfigJuez):
        def nodo(estado: _Estado) -> dict:
            self.on_evento({"tipo": "fase", "detalle": f"Juez {cfg.numero} ({cfg.modelo}) calificando"})
            resultado = evaluar_con_juez(
                cfg,
                self.invocadores[cfg.numero],
                estado["rubrica"],
                estado["segmentacion"],
                estado["secciones_activas"],
                contexto_rag=self.contexto_rag,
                on_progreso=self.on_evento,
            )
            return {"resultados_jueces": [resultado]}

        return nodo

    def _nodo_agregador(self, estado: _Estado) -> dict:
        self.on_evento({"tipo": "fase", "detalle": "Agregando el panel (mediana y discrepancias)"})
        config = estado["config"]
        rubrica = estado["rubrica"]
        secciones, totales, transversales, panel = agregar(
            rubrica,
            estado["segmentacion"],
            estado["resultados_jueces"],
            config.mode,
            estado["secciones_activas"],
        )

        tokens_entrada = sum(r.tokens_entrada for r in estado["resultados_jueces"])
        tokens_salida = sum(r.tokens_salida for r in estado["resultados_jueces"])
        usd_total, usd_conocido = 0.0, False
        for resultado in estado["resultados_jueces"]:
            usd = costo_usd(resultado.modelo, resultado.tokens_entrada, resultado.tokens_salida)
            if usd is not None:
                usd_total += usd
                usd_conocido = True
        for uso in estado["usos_extra"]:
            tokens_entrada += uso.tokens_entrada
            tokens_salida += uso.tokens_salida
            usd = costo_usd(self.modelos[1], uso.tokens_entrada, uso.tokens_salida)
            if usd is not None:
                usd_total += usd

        settings = get_settings()
        resultado = EvaluacionResultado(
            project_id=config.project_id,
            rubric_id=rubrica.id,
            mode=config.mode,
            timestamp=datetime.now(timezone.utc).isoformat(),
            config_modelos={f"juez{n}": m for n, m in self.modelos.items()},
            seed=settings.eval_seed,
            temperature=settings.eval_temperature,
            prompts_hash=hash_prompts(),
            reporte_indexacion=estado["segmentacion"].reporte(),
            secciones=secciones,
            total=totales["total"],
            puntaje_max_activo=totales["puntaje_max_activo"],
            total_normalizado=totales["total_normalizado"],
            nivel=totales["nivel"],
            nota_vigesimal=totales["nota_vigesimal"],
            dimensiones_transversales=transversales,
            panel=panel,
            costo=Costo(
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
                usd_estimado=round(usd_total, 6) if usd_conocido else None,
            ),
        )
        self.on_evento({"tipo": "resultado", "total": resultado.total, "nivel": resultado.nivel})
        return {"resultado": resultado}

    # ── Grafo ────────────────────────────────────────────────────────────────
    def _construir(self):
        grafo = StateGraph(_Estado)
        grafo.add_node("orquestador", self._nodo_orquestador)
        for cfg in self.jueces:
            grafo.add_node(f"juez_{cfg.numero}", self._nodo_juez(cfg))
        grafo.add_node("agregador", self._nodo_agregador)

        grafo.add_edge(START, "orquestador")
        for cfg in self.jueces:
            grafo.add_edge("orquestador", f"juez_{cfg.numero}")
            grafo.add_edge(f"juez_{cfg.numero}", "agregador")
        grafo.add_edge("agregador", END)
        return grafo.compile()

    def evaluar(
        self,
        doc_anonimo: DocumentoExtraido,
        reporte_anonimizacion: Optional[ReporteAnonimizacion],
        config: ConfigEvaluacion,
    ) -> EvaluacionResultado:
        estado_final = self._grafo.invoke(
            {
                "doc": doc_anonimo,
                "rubrica": load_rubric(config.rubric_id),
                "config": config,
                "reporte_anonimizacion": reporte_anonimizacion,
                "segmentacion": None,
                "secciones_activas": set(),
                "resultados_jueces": [],
                "usos_extra": [],
                "resultado": None,
            }
        )
        resultado: EvaluacionResultado = estado_final["resultado"]

        # Métricas determinísticas (Python puro, sin LLM): acompañan cada
        # evaluación pero no alteran los puntajes de la rúbrica. Un fallo aquí
        # NO puede invalidar el resultado del panel (las ~45 llamadas ya se
        # ejecutaron): se degrada a metricas_deterministicas = None.
        from metrics.deterministic import calcular_metricas

        self.on_evento({"tipo": "fase", "detalle": "Calculando métricas determinísticas"})
        try:
            resultado.metricas_deterministicas = calcular_metricas(
                doc_anonimo, estado_final["segmentacion"]
            ).model_dump()
        except Exception as exc:  # noqa: BLE001 — degradación controlada
            resultado.metricas_deterministicas = None
            self.on_evento(
                {"tipo": "fase",
                 "detalle": f"Métricas determinísticas no disponibles ({exc}); "
                            "la calificación del panel no se ve afectada"}
            )
        self.analizar_coherencia(resultado, estado_final["segmentacion"])
        return resultado

    def analizar_coherencia(self, resultado: EvaluacionResultado, segmentacion: ResultadoSegmentacion) -> None:
        if self.invocador_analisis is not None:
            aplicar_analisis_coherencia(resultado, segmentacion, self.invocador_analisis,
                                        self.modelo_analisis, self.on_evento)


def aplicar_analisis_coherencia(
    resultado: EvaluacionResultado,
    segmentacion: ResultadoSegmentacion,
    invocador: Invocador,
    modelo: str,
    on_evento: Optional[OnEvento] = None,
) -> None:
    """Índice argumentativo (Toulmin) y coherencia global: externos a la rúbrica.

    No alteran los puntajes de la rúbrica. Como las métricas determinísticas, un fallo aquí no
    invalida la calificación del panel: el análisis afectado queda en None. Lo usan el grafo y
    cli/coherencia.py (que completa evaluaciones ya guardadas sin repetir la rúbrica).
    """
    from graph.argumentacion import analizar_argumentacion
    from graph.coherencia_global import analizar_coherencia_global

    on_evento = on_evento or (lambda e: None)
    analisis = [
        ("argumentacion", "Analizando la argumentación (Toulmin)", analizar_argumentacion),
        ("coherencia_global", "Analizando la coherencia global", analizar_coherencia_global),
    ]
    for campo, detalle, funcion in analisis:
        on_evento({"tipo": "fase", "detalle": detalle})
        try:
            valor, usos = funcion(segmentacion, invocador, modelo)
        except Exception as exc:  # noqa: BLE001 — degradación controlada
            on_evento({"tipo": "fase", "detalle": f"{detalle}: no disponible ({exc}); "
                                                 "la calificación del panel no se ve afectada"})
            continue
        setattr(resultado, campo, valor)
        for uso in usos:
            resultado.costo.tokens_entrada += uso.tokens_entrada
            resultado.costo.tokens_salida += uso.tokens_salida
            usd = costo_usd(modelo, uso.tokens_entrada, uso.tokens_salida)
            if usd is not None:
                resultado.costo.usd_estimado = round((resultado.costo.usd_estimado or 0) + usd, 6)
