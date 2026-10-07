// Tipos espejo del backend (graph/schemas.py y app/main.py)

export interface SeccionReporte {
  id: string;
  nombre: string;
  presente: boolean;
  encontrado_como: string | null;
  pagina_inicio: number | null;
  pagina_fin: number | null;
  palabras: number;
}

export interface ReporteAnonimizacion {
  reemplazos: Record<string, number>;
  advertencias: string[];
}

export interface ReporteIndexacion {
  metodo: "heuristica" | "llm";
  paginas_indice: number[];
  secciones: SeccionReporte[];
  no_encontradas: string[];
  advertencias: string[];
  anonimizacion: ReporteAnonimizacion | null;
}

export interface ProyectoInfo {
  project_id: string;
  nombre: string;
  tipo: string;
  paginas: number;
  palabras: number;
  reporte_indexacion: ReporteIndexacion;
}

export interface RubricaInfo {
  id: string;
  nombre: string;
  tipo: string;
  puntaje_maximo: number;
  secciones: number;
  items: number;
}

export type NivelJuez = string | number | null;

export interface ItemEvaluado {
  id: string;
  criterio: string;
  niveles_jueces: Record<string, NivelJuez>;
  nivel_final: NivelJuez;
  puntaje: number;
  puntaje_max: number;
  discrepancia: boolean;
  evidencia: string;
  observacion: string;
}

export interface SeccionEvaluada {
  id: string;
  nombre: string;
  presente: boolean;
  activa: boolean;
  subtotal: number | null;
  max: number;
  items: ItemEvaluado[];
}

export interface DimensionTransversal {
  dimension: string;
  puntajes_jueces: Record<string, number | null>;
  mediana: number | null;
  justificacion: string;
}

export interface MetricasDeterministicas {
  palabras_totales: number;
  palabras_por_seccion: Record<string, number>;
  longitud_media_oracion: number | null;
  legibilidad: {
    fernandez_huerta: number | null;
    szigriszt_pazos: number | null;
    interpretacion: string | null;
  };
  riqueza_lexica: { ttr: number | null; mtld: number | null };
  citas_referencias: {
    citas_en_texto: number;
    referencias_en_lista: number;
    citas_sin_referencia: string[];
    referencias_nunca_citadas: string[];
    aproximado: boolean;
  };
  completitud: { presentes: number; total: number; ratio: number };
}

export interface PanelInfo {
  pct_discrepancia: number;
  items_marcados: string[];
  panel_incompleto: boolean;
  huecos: string[];
}

export interface SeccionArgumentativa {
  seccion_id: string;
  nombre: string;
  elegible: boolean;
  palabras: number;
  oraciones: number;
  conteo: Record<string, number>;
  oraciones_con_calificador: number;
  refutaciones_respondidas: number;
  presentes: string[];
  indice_estructural: number | null;
  nivel: number | null;
}

export interface ResultadoArgumentacion {
  version: string;
  modelo: string;
  secciones: SeccionArgumentativa[];
  indice_proyecto: number | null;
}

export interface ContradiccionVerificada {
  tipo: string;
  seccion_a: string;
  cita_a: string;
  seccion_b: string;
  cita_b: string;
  explicacion: string;
  gravedad: "nucleo" | "menor";
}

export interface ResultadoCoherenciaGlobal {
  version: string;
  modelo: string;
  nota: number;
  contradicciones_nucleo: number;
  contradicciones_menores: number;
  propuestas: number;
  contradicciones: ContradiccionVerificada[];
}

export interface EvaluacionResultado {
  project_id: string;
  rubric_id: string;
  mode: "completo" | "progresivo";
  timestamp: string;
  config_modelos: Record<string, string>;
  seed: number;
  temperature: number;
  prompts_hash: string;
  reporte_indexacion: ReporteIndexacion;
  secciones: SeccionEvaluada[];
  total: number;
  puntaje_max_activo: number;
  total_normalizado: number | null;
  nivel: string | null;
  nota_vigesimal: number | null;
  dimensiones_transversales: DimensionTransversal[];
  metricas_deterministicas: MetricasDeterministicas | null;
  // Análisis de coherencia externos a la rúbrica (ausentes en evaluaciones anteriores)
  argumentacion?: ResultadoArgumentacion | null;
  coherencia_global?: ResultadoCoherenciaGlobal | null;
  panel: PanelInfo;
  costo: { tokens_entrada: number; tokens_salida: number; usd_estimado: number | null };
}

export interface RegistroEvaluacion {
  id: string;
  project_id: string;
  rubric_id: string;
  mode: string;
  estado: "pendiente" | "ejecutando" | "completada" | "error";
  error?: string | null;
  resultado?: EvaluacionResultado;
}

export interface PasoProgreso {
  id: number;
  texto: string;
  estado: "activo" | "completado";
}

export interface Mensaje {
  id: string;
  rol: "user" | "assistant";
  tipo?: "texto" | "indexacion" | "config" | "resultado";
  contenido?: string;
  proyecto?: ProyectoInfo;
  resultado?: EvaluacionResultado;
  evaluationId?: string;
}

export interface EvaluarBody {
  rubric: string;
  mode: "completo" | "progresivo";
  semanas_activas?: number[];
  incluir_administrativos?: boolean;
}
