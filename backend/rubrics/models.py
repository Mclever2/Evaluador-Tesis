"""Modelos de datos de las rúbricas del ECM (pydantic v2).

Las rúbricas son archivos de configuración del sistema, versionados como JSON
en backend/rubrics/. Soportan dos tipos:

- "ponderada_3_niveles" (especifica_v1): cada ítem tiene un peso propio y un
  valor de "parcial" definido en la propia tabla fuente (se respeta tal cual,
  con sus redondeos, p. ej. peso 0.75 con parcial 0.38).
- "escala_0_3" (ficha_upao_v1): cada ítem se califica con un entero 0 a 3 y el
  total puede convertirse a nota vigesimal con la tabla oficial.
- "dicotomica" (dicotomica_v2): cada ítem vale 1 (Cumple) o 0 (No cumple), sin
  nivel intermedio; el total es la suma simple de 100 ítems.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ItemRubrica(BaseModel):
    """Un criterio evaluable. `criterio` es el texto literal de la fuente."""

    id: str
    criterio: str
    peso: float
    # Puntaje cuando el nivel es "parcial". Solo aplica a ponderada_3_niveles;
    # se toma literalmente de la tabla fuente (no se recalcula).
    parcial: Optional[float] = None
    referencia: Optional[str] = None


class SeccionRubrica(BaseModel):
    """Sección (especifica_v1) o bloque (ficha_upao_v1) de la rúbrica."""

    id: str
    nombre: str
    puntaje_max: float
    # Encabezados alternativos con los que la sección suele aparecer en los
    # proyectos (normalizados: minúsculas y sin tildes). Los usa el segmentador.
    aliases: list[str] = Field(default_factory=list)
    items: list[ItemRubrica]

    def suma_pesos(self) -> float:
        return round(sum(i.peso for i in self.items), 2)


class NivelCalidad(BaseModel):
    min: float
    max: float
    etiqueta: str
    accion: Optional[str] = None


class ConversionVigesimal(BaseModel):
    """Fila de la tabla oficial puntaje total → nota vigesimal (ficha UPAO)."""

    min: int
    max: int
    nota: int


class Rubrica(BaseModel):
    id: str
    nombre: str
    tipo: Literal["ponderada_3_niveles", "escala_0_3", "dicotomica"]
    escala: dict[str, float]
    niveles_calidad: list[NivelCalidad] = Field(default_factory=list)
    secciones: list[SeccionRubrica]
    conversion_vigesimal: Optional[list[ConversionVigesimal]] = None

    @property
    def puntaje_maximo(self) -> float:
        return round(sum(s.puntaje_max for s in self.secciones), 2)

    @property
    def total_items(self) -> int:
        return sum(len(s.items) for s in self.secciones)

    def seccion(self, seccion_id: str) -> SeccionRubrica:
        for s in self.secciones:
            if s.id == seccion_id:
                return s
        raise KeyError(f"Sección {seccion_id!r} no existe en la rúbrica {self.id!r}")

    def nivel_para(self, total: float) -> Optional[str]:
        """Etiqueta de calidad para un puntaje total (bandas continuas)."""
        if not self.niveles_calidad:
            return None
        for nivel in sorted(self.niveles_calidad, key=lambda n: n.min, reverse=True):
            if total >= nivel.min:
                return nivel.etiqueta
        return self.niveles_calidad[-1].etiqueta

    def nota_vigesimal(self, total: float) -> Optional[int]:
        """Nota 0-20 según la tabla oficial. Solo para rúbricas que la incluyen."""
        if not self.conversion_vigesimal:
            return None
        entero = round(total)
        for fila in self.conversion_vigesimal:
            if fila.min <= entero <= fila.max:
                return fila.nota
        return None
