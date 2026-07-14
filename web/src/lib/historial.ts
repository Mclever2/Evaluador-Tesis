// Historial persistente en Supabase: conversaciones, mensajes y calificaciones.
// Todas las funciones son no-op (devuelven null/[]) si Supabase no está
// configurado. Los errores NUNCA se tragan en silencio: se registran en la
// consola y se notifican a la UI vía setNotificadorErrores.

import { supabase } from "@/lib/supabase";
import type { EvaluacionResultado, Mensaje, ProyectoInfo } from "@/types";

export interface ConversacionResumen {
  id: string;
  titulo: string;
  creada_en: string;
  project_id: string | null;
  proyecto: ProyectoInfo | null;
}

let notificar: ((mensaje: string) => void) | null = null;

/** La App registra aquí cómo mostrar errores de guardado al usuario. */
export function setNotificadorErrores(fn: ((mensaje: string) => void) | null) {
  notificar = fn;
}

function reportar(operacion: string, error: unknown): void {
  const detalle =
    (error as { message?: string })?.message ?? (typeof error === "string" ? error : JSON.stringify(error));
  console.error(`[ECM historial] ${operacion}:`, error);
  notificar?.(`${operacion}: ${detalle}`);
}

async function usuarioActual(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.user.id ?? null;
}

export async function listarConversaciones(): Promise<ConversacionResumen[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("conversaciones")
    .select("id, titulo, creada_en, project_id, proyecto")
    .order("creada_en", { ascending: false });
  if (error) {
    reportar("No se pudo listar el historial", error);
    return [];
  }
  return (data as ConversacionResumen[]) ?? [];
}

export async function crearConversacion(
  titulo: string,
  proyecto: ProyectoInfo,
): Promise<string | null> {
  if (!supabase) return null;
  const user_id = await usuarioActual();
  const { data, error } = await supabase
    .from("conversaciones")
    .insert({ titulo, project_id: proyecto.project_id, proyecto, ...(user_id ? { user_id } : {}) })
    .select("id")
    .single();
  if (error || !data) {
    reportar("No se pudo crear la conversación en el historial", error ?? "sin datos");
    return null;
  }
  return data.id as string;
}

export async function guardarMensaje(convId: string | null, mensaje: Mensaje): Promise<void> {
  if (!supabase || !convId) return;
  const metadata: Record<string, unknown> = {};
  if (mensaje.proyecto) metadata.proyecto = mensaje.proyecto;
  if (mensaje.resultado) metadata.resultado = mensaje.resultado;
  if (mensaje.evaluationId) metadata.evaluationId = mensaje.evaluationId;
  const user_id = await usuarioActual();
  const { error } = await supabase.from("mensajes").insert({
    conversacion_id: convId,
    rol: mensaje.rol,
    tipo: mensaje.tipo ?? "texto",
    contenido: mensaje.contenido ?? null,
    metadata,
    ...(user_id ? { user_id } : {}),
  });
  if (error) reportar("No se pudo guardar un mensaje del historial", error);
}

export async function cargarMensajes(convId: string): Promise<Omit<Mensaje, "id">[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("mensajes")
    .select("rol, tipo, contenido, metadata")
    .eq("conversacion_id", convId)
    .order("creado_en", { ascending: true });
  if (error) {
    reportar("No se pudo cargar la conversación", error);
    return [];
  }
  return ((data ?? []) as Array<Record<string, unknown>>).map((fila) => {
    const metadata = (fila.metadata ?? {}) as Record<string, unknown>;
    return {
      rol: fila.rol as Mensaje["rol"],
      tipo: (fila.tipo as Mensaje["tipo"]) ?? "texto",
      contenido: (fila.contenido as string) ?? undefined,
      proyecto: metadata.proyecto as ProyectoInfo | undefined,
      resultado: metadata.resultado as EvaluacionResultado | undefined,
      evaluationId: metadata.evaluationId as string | undefined,
    };
  });
}

export async function eliminarConversacion(convId: string): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase.from("conversaciones").delete().eq("id", convId);
  if (error) reportar("No se pudo eliminar la conversación", error);
}

export async function guardarEvaluacion(
  convId: string | null,
  evaluationId: string,
  resultado: EvaluacionResultado,
): Promise<void> {
  if (!supabase) return;
  const user_id = await usuarioActual();
  const { error } = await supabase.from("evaluaciones").upsert({
    id: evaluationId,
    conversacion_id: convId,
    project_id: resultado.project_id,
    rubric_id: resultado.rubric_id,
    mode: resultado.mode,
    total: resultado.total,
    nivel: resultado.nivel,
    nota_vigesimal: resultado.nota_vigesimal,
    resultado,
    ...(user_id ? { user_id } : {}),
  });
  if (error) reportar("No se pudo guardar la calificación en Supabase", error);
}
