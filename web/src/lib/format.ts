import type { EvaluacionResultado, NivelJuez } from "@/types";

export function colorNivel(nivel: string | null): string {
  switch (nivel) {
    case "Excelente":
      return "#34C759";
    case "Bueno":
      return "#007AFF";
    case "Regular":
      return "#FF9500";
    default:
      return "#FF3B30";
  }
}

export function porcentajeTotal(resultado: EvaluacionResultado): number {
  if (resultado.total_normalizado != null) return resultado.total_normalizado;
  if (!resultado.puntaje_max_activo) return 0;
  return (resultado.total / resultado.puntaje_max_activo) * 100;
}

export const ETIQUETA_NIVEL_ITEM: Record<string, string> = {
  cumple: "Cumple",
  parcial: "Parcial",
  no_cumple: "No cumple",
};

export function etiquetaNivelItem(nivel: NivelJuez): string {
  if (nivel == null) return "Sin panel";
  if (typeof nivel === "number") return String(nivel);
  return ETIQUETA_NIVEL_ITEM[nivel] ?? nivel;
}

export function colorNivelItem(nivel: NivelJuez): string {
  if (nivel == null) return "text-muted-foreground";
  if (typeof nivel === "number") {
    return nivel >= 3 ? "text-[#34C759]" : nivel === 2 ? "text-primary" : nivel === 1 ? "text-[#FF9500]" : "text-destructive";
  }
  return nivel === "cumple" ? "text-[#34C759]" : nivel === "parcial" ? "text-[#FF9500]" : "text-destructive";
}

export const NOMBRE_DIMENSION: Record<string, string> = {
  coherencia_interna: "Coherencia interna (versión anterior)",
  formalidad_registro: "Formalidad y registro",
  claridad_tono: "Claridad y tono",
};

export const NOMBRE_COMPONENTE: Record<string, string> = {
  afirmacion: "Afirmación",
  dato: "Datos",
  garantia: "Garantía",
  respaldo: "Respaldo",
  calificador: "Calificador",
  refutacion: "Refutación",
};

export const NOMBRE_CONTRADICCION: Record<string, string> = {
  variables: "Variables",
  unidad_analisis: "Unidad de análisis",
  proposito: "Propósito",
  diseno: "Diseño",
  muestreo: "Muestreo",
  numero_correspondencia: "Correspondencia de específicos",
  otra: "Otra",
};
