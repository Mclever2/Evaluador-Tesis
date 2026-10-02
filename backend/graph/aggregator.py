"""Agregador del panel: consolida las calificaciones de los jueces.

Reglas (todas deterministas, sin LLM):
- Mapeo ordinal en la rúbrica ponderada: cumple = 2, parcial = 1, no_cumple = 0.
- Rúbrica dicotómica: cumple = 1, no_cumple = 0. Con 3 jueces la mediana es el
  VOTO DE MAYORÍA (2 de 3); con un hueco (2 jueces) la mediana inferior exige
  que ambos digan cumple. `discrepancia = True` cuando el ítem no es unánime
  (rango 1): en binario no existe el rango 2 de la escala de 3 niveles.
- Nivel final por ítem: MEDIANA de los jueces disponibles. Con número par de
  jueces (hueco en el panel) se usa la mediana inferior (criterio conservador
  y determinista).
- `discrepancia = True` cuando el rango entre jueces es 2 o más (en la escala
  de 3 niveles equivale a que un juez dijo cumple y otro no_cumple; en la
  ficha 0-3 se generaliza a rango >= 2).
- Puntaje del ítem según la rúbrica: cumple → peso, parcial → valor literal de
  la tabla, no_cumple → 0. En escala 0-3 el puntaje es la mediana directa.
- Sección ausente en modo activo: todos sus ítems puntúan 0 con la observación
  "sección no encontrada".
- Modo progresivo: solo puntúan las secciones activas; el total se reporta
  crudo y normalizado sobre el puntaje máximo activo.
- La observación final por ítem se sintetiza SIN inventar contenido: se toma
  la observación del primer juez cuyo nivel coincide con la mediana (y se
  antepone una marca cuando hay discrepancia).
"""

from __future__ import annotations

from typing import Optional

from graph.schemas import (
    DIMENSIONES_TRANSVERSALES,
    DimensionTransversal,
    ItemEvaluado,
    PanelInfo,
    SeccionEvaluada,
    ResultadoJuez,
)
from graph.segmenter import MIN_PALABRAS_EVALUABLES, ResultadoSegmentacion
from rubrics.models import ItemRubrica, Rubrica

_ORDINAL = {"no_cumple": 0, "parcial": 1, "cumple": 2}
_NIVEL_POR_ORDINAL = {v: k for k, v in _ORDINAL.items()}
_ORDINAL_DICOTOMICO = {"no_cumple": 0, "cumple": 1}
_NIVEL_POR_ORDINAL_DICOTOMICO = {v: k for k, v in _ORDINAL_DICOTOMICO.items()}

_OBS_AUSENTE = "Sección no encontrada en el proyecto."
_OBS_VACIA = "Sección presente pero sin contenido evaluable (vacía o solo texto de la plantilla)."
_OBS_SIN_PANEL = "Sin calificación del panel para este ítem (falla de API registrada)."
_EVIDENCIA_AUSENTE = "no se encontró evidencia"


def mediana_inferior(valores: list[int]) -> int:
    """Mediana ordinal; con cantidad par devuelve la inferior (conservadora)."""
    ordenados = sorted(valores)
    return ordenados[(len(ordenados) - 1) // 2]


def _puntaje_ponderado(item: ItemRubrica, ordinal: int) -> float:
    if ordinal >= 2:
        return item.peso
    if ordinal == 1:
        return item.parcial if item.parcial is not None else round(item.peso / 2, 2)
    return 0.0


def _consolidar_item(
    rubrica: Rubrica,
    item: ItemRubrica,
    respuestas: dict[int, Optional[object]],
) -> ItemEvaluado:
    """respuestas: juez → CalificacionItem (ponderada o escala) o None si no calificó."""
    escala_directa = rubrica.tipo == "escala_0_3"
    dicotomica = rubrica.tipo == "dicotomica"
    ordinal = _ORDINAL_DICOTOMICO if dicotomica else _ORDINAL
    niveles_jueces: dict[str, Optional[object]] = {}
    ordinales: list[int] = []
    calificaciones = {}

    for juez, calificacion in sorted(respuestas.items()):
        clave = f"juez{juez}"
        if calificacion is None:
            niveles_jueces[clave] = None
            continue
        calificaciones[juez] = calificacion
        if escala_directa:
            niveles_jueces[clave] = calificacion.puntaje
            ordinales.append(calificacion.puntaje)
        else:
            niveles_jueces[clave] = calificacion.nivel
            ordinales.append(ordinal[calificacion.nivel])

    if not ordinales:
        return ItemEvaluado(
            id=item.id,
            criterio=item.criterio,
            niveles_jueces=niveles_jueces,
            nivel_final=None,
            puntaje=0.0,
            puntaje_max=3.0 if escala_directa else item.peso,
            discrepancia=False,
            evidencia="",
            observacion=_OBS_SIN_PANEL,
        )

    mediana = mediana_inferior(ordinales)
    umbral_discrepancia = 1 if dicotomica else 2
    discrepancia = (max(ordinales) - min(ordinales)) >= umbral_discrepancia

    if escala_directa:
        nivel_final: object = mediana
        puntaje = float(mediana)
        puntaje_max = 3.0
        coincide = lambda c: c.puntaje == mediana  # noqa: E731
    elif dicotomica:
        nivel_final = _NIVEL_POR_ORDINAL_DICOTOMICO[mediana]
        puntaje = item.peso if mediana == 1 else 0.0
        puntaje_max = item.peso
        coincide = lambda c: _ORDINAL_DICOTOMICO[c.nivel] == mediana  # noqa: E731
    else:
        nivel_final = _NIVEL_POR_ORDINAL[mediana]
        puntaje = _puntaje_ponderado(item, mediana)
        puntaje_max = item.peso
        coincide = lambda c: _ORDINAL[c.nivel] == mediana  # noqa: E731

    # Síntesis sin inventar: primer juez (por orden) cuyo nivel es la mediana.
    representante = next(
        (c for _, c in sorted(calificaciones.items()) if coincide(c)),
        next(iter(calificaciones.values())),
    )
    observacion = representante.observacion
    if discrepancia:
        observacion = f"[Discrepancia entre jueces] {observacion}"

    detalle_jueces = {
        f"juez{juez}": c.model_dump(exclude={"item_id"}) for juez, c in sorted(calificaciones.items())
    }
    return ItemEvaluado(
        id=item.id,
        criterio=item.criterio,
        niveles_jueces=niveles_jueces,
        detalle_jueces=detalle_jueces,
        nivel_final=nivel_final,
        puntaje=round(puntaje, 2),
        puntaje_max=puntaje_max,
        discrepancia=discrepancia,
        evidencia=representante.evidencia,
        observacion=observacion,
    )


def _item_ausente(rubrica: Rubrica, item: ItemRubrica, observacion: str = _OBS_AUSENTE) -> ItemEvaluado:
    escala_directa = rubrica.tipo == "escala_0_3"
    return ItemEvaluado(
        id=item.id,
        criterio=item.criterio,
        nivel_final=0 if escala_directa else "no_cumple",
        puntaje=0.0,
        puntaje_max=3.0 if escala_directa else item.peso,
        evidencia=_EVIDENCIA_AUSENTE,
        observacion=observacion,
    )


def _consolidar_transversales(resultados: list[ResultadoJuez]) -> list[DimensionTransversal]:
    consolidadas: list[DimensionTransversal] = []
    for dimension in DIMENSIONES_TRANSVERSALES:
        puntajes_jueces: dict[str, Optional[int]] = {}
        valores: list[int] = []
        justificaciones: dict[int, str] = {}
        for resultado in sorted(resultados, key=lambda r: r.juez):
            clave = f"juez{resultado.juez}"
            calificacion = None
            if resultado.transversales:
                calificacion = next(
                    (d for d in resultado.transversales.dimensiones if d.dimension == dimension),
                    None,
                )
            if calificacion is None:
                puntajes_jueces[clave] = None
            else:
                puntajes_jueces[clave] = calificacion.puntaje
                valores.append(calificacion.puntaje)
                justificaciones[resultado.juez] = calificacion.justificacion

        mediana = mediana_inferior(valores) if valores else None
        justificacion = ""
        if mediana is not None:
            for juez in sorted(justificaciones):
                if puntajes_jueces[f"juez{juez}"] == mediana:
                    justificacion = justificaciones[juez]
                    break
            else:
                justificacion = next(iter(justificaciones.values()), "")
        consolidadas.append(
            DimensionTransversal(
                dimension=dimension,
                puntajes_jueces=puntajes_jueces,
                mediana=mediana,
                justificacion=justificacion,
            )
        )
    return consolidadas


def agregar(
    rubrica: Rubrica,
    segmentacion: ResultadoSegmentacion,
    resultados: list[ResultadoJuez],
    modo: str,
    secciones_activas: set[str],
) -> tuple[list[SeccionEvaluada], dict, list[DimensionTransversal], PanelInfo]:
    """Consolida el panel. Devuelve (secciones, totales, transversales, panel)."""
    presentes = {s.seccion_id for s in segmentacion.presentes}
    palabras_por_seccion = {s.seccion_id: s.palabras_evaluables for s in segmentacion.presentes}
    secciones_out: list[SeccionEvaluada] = []
    items_evaluados = 0
    items_discrepantes: list[str] = []
    huecos: list[str] = []
    for resultado in resultados:
        huecos.extend(f"juez{resultado.juez} {h}" for h in resultado.huecos)

    for seccion in rubrica.secciones:
        activa = seccion.id in secciones_activas
        presente = seccion.id in presentes

        if not activa:
            secciones_out.append(
                SeccionEvaluada(
                    id=seccion.id, nombre=seccion.nombre, presente=presente,
                    activa=False, subtotal=None, max=seccion.puntaje_max,
                )
            )
            continue

        if not presente:
            items = [_item_ausente(rubrica, item) for item in seccion.items]
            secciones_out.append(
                SeccionEvaluada(
                    id=seccion.id, nombre=seccion.nombre, presente=False, activa=True,
                    subtotal=0.0, max=seccion.puntaje_max, items=items,
                )
            )
            continue

        if palabras_por_seccion.get(seccion.id, 0) < MIN_PALABRAS_EVALUABLES:
            # Presente pero sin contenido evaluable: los jueces no la reciben.
            items = [_item_ausente(rubrica, item, observacion=_OBS_VACIA) for item in seccion.items]
            secciones_out.append(
                SeccionEvaluada(
                    id=seccion.id, nombre=seccion.nombre, presente=True, activa=True,
                    subtotal=0.0, max=seccion.puntaje_max, items=items,
                )
            )
            continue

        items: list[ItemEvaluado] = []
        for item in seccion.items:
            respuestas: dict[int, Optional[object]] = {}
            for resultado in resultados:
                respuesta_seccion = resultado.secciones.get(seccion.id)
                if respuesta_seccion is None:
                    respuestas[resultado.juez] = None
                    continue
                respuestas[resultado.juez] = next(
                    (c for c in respuesta_seccion.calificaciones if c.item_id == item.id),
                    None,
                )
            consolidado = _consolidar_item(rubrica, item, respuestas)
            if consolidado.nivel_final is not None:
                items_evaluados += 1
                if consolidado.discrepancia:
                    items_discrepantes.append(f"{seccion.id}.{item.id}")
            items.append(consolidado)

        subtotal = round(sum(i.puntaje for i in items), 2)
        secciones_out.append(
            SeccionEvaluada(
                id=seccion.id, nombre=seccion.nombre, presente=True, activa=True,
                subtotal=subtotal, max=seccion.puntaje_max, items=items,
            )
        )

    activas = [s for s in secciones_out if s.activa]
    total = round(sum(s.subtotal or 0.0 for s in activas), 2)
    max_activo = round(sum(s.max for s in activas), 2)

    totales: dict = {"total": total, "puntaje_max_activo": max_activo}
    # Total normalizado a escala 100 siempre que el máximo activo no sea el de
    # la rúbrica completa: modo progresivo, o ficha sin aspectos
    # administrativos (crudo sobre 87 + normalizado a 100).
    if max_activo and (modo == "progresivo" or max_activo != rubrica.puntaje_maximo):
        totales["total_normalizado"] = round(total / max_activo * 100, 2)
        base_nivel: Optional[float] = totales["total_normalizado"]
    else:
        totales["total_normalizado"] = None
        base_nivel = total if max_activo else None
    totales["nivel"] = rubrica.nivel_para(base_nivel) if base_nivel is not None else None

    # Nota vigesimal: solo con la ficha completa (todas las secciones activas).
    totales["nota_vigesimal"] = (
        rubrica.nota_vigesimal(total)
        if modo == "completo" and max_activo == rubrica.puntaje_maximo
        else None
    )

    panel = PanelInfo(
        pct_discrepancia=(
            round(len(items_discrepantes) / items_evaluados * 100, 2) if items_evaluados else 0.0
        ),
        items_marcados=items_discrepantes,
        panel_incompleto=bool(huecos),
        huecos=huecos,
    )
    return secciones_out, totales, _consolidar_transversales(resultados), panel
