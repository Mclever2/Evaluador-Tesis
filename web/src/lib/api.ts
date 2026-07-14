// Cliente de la API del ECM. Todas las peticiones pasan por el proxy /api de
// Vite y adjuntan la clave simple (X-Access-Key) si el despliegue la exige.

import type {
  EvaluarBody,
  ProyectoInfo,
  RegistroEvaluacion,
  ReporteIndexacion,
  RubricaInfo,
} from "@/types";

const BASE = "/api";
const CLAVE_KEY = "ecm-clave";

// Token de sesión de Supabase (lo actualiza App con onAuthStateChange).
// Cuando Supabase está configurado, el backend exige este Bearer.
let tokenSesion: string | null = null;

export function setTokenSesion(token: string | null) {
  tokenSesion = token;
}

export function claveGuardada(): string {
  return localStorage.getItem(CLAVE_KEY) ?? "";
}

export function guardarClave(clave: string) {
  localStorage.setItem(CLAVE_KEY, clave);
}

function cabeceras(extra?: Record<string, string>): Record<string, string> {
  const clave = claveGuardada();
  return {
    ...(tokenSesion ? { Authorization: `Bearer ${tokenSesion}` } : {}),
    ...(clave ? { "X-Access-Key": clave } : {}),
    ...(extra ?? {}),
  };
}

async function procesar<T>(respuesta: Response): Promise<T> {
  if (respuesta.status === 401) throw new Error("CLAVE_INVALIDA");
  if (!respuesta.ok) {
    let detalle = `Error ${respuesta.status}`;
    try {
      const cuerpo = await respuesta.json();
      if (cuerpo?.detail) detalle = String(cuerpo.detail);
    } catch {
      /* cuerpo no JSON */
    }
    throw new Error(detalle);
  }
  return respuesta.json() as Promise<T>;
}

export async function verificarAcceso(): Promise<"ok" | "clave"> {
  try {
    const r = await fetch(`${BASE}/health`, { headers: cabeceras() });
    if (r.status === 401) return "clave";
    return "ok";
  } catch {
    return "ok"; // backend caído: la app muestra el error al usar
  }
}

export async function listarRubricas(): Promise<RubricaInfo[]> {
  return procesar(await fetch(`${BASE}/rubrics`, { headers: cabeceras() }));
}

export async function subirProyecto(archivo: File): Promise<ProyectoInfo> {
  const forma = new FormData();
  forma.append("archivo", archivo);
  return procesar(
    await fetch(`${BASE}/projects/upload`, { method: "POST", headers: cabeceras(), body: forma }),
  );
}

export async function obtenerReporteIndexacion(projectId: string): Promise<ReporteIndexacion> {
  return procesar(
    await fetch(`${BASE}/projects/${projectId}/index-report`, { headers: cabeceras() }),
  );
}

export async function lanzarEvaluacion(
  projectId: string,
  cuerpo: EvaluarBody,
): Promise<{ evaluation_id: string }> {
  return procesar(
    await fetch(`${BASE}/projects/${projectId}/evaluate`, {
      method: "POST",
      headers: cabeceras({ "Content-Type": "application/json" }),
      body: JSON.stringify(cuerpo),
    }),
  );
}

export async function obtenerEvaluacion(evaluationId: string): Promise<RegistroEvaluacion> {
  return procesar(await fetch(`${BASE}/evaluations/${evaluationId}`, { headers: cabeceras() }));
}

/** Consume el SSE de progreso con fetch (EventSource no admite encabezados). */
export async function streamEventos(
  evaluationId: string,
  onEvento: (evento: Record<string, unknown>) => void,
): Promise<void> {
  const respuesta = await fetch(`${BASE}/evaluations/${evaluationId}/events`, {
    headers: cabeceras(),
  });
  if (!respuesta.ok || !respuesta.body) return;
  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    buffer += decodificador.decode(value, { stream: true });
    const bloques = buffer.split("\n\n");
    buffer = bloques.pop() ?? "";
    for (const bloque of bloques) {
      for (const linea of bloque.split("\n")) {
        if (linea.startsWith("data:")) {
          try {
            onEvento(JSON.parse(linea.slice(5).trim()));
          } catch {
            /* línea no JSON (ping) */
          }
        }
      }
    }
  }
}

export async function preguntarSobreInforme(
  evaluationId: string,
  pregunta: string,
): Promise<{ respuesta: string }> {
  return procesar(
    await fetch(`${BASE}/evaluations/${evaluationId}/chat`, {
      method: "POST",
      headers: cabeceras({ "Content-Type": "application/json" }),
      body: JSON.stringify({ pregunta }),
    }),
  );
}

async function descargarBlob(ruta: string, nombre: string) {
  const respuesta = await fetch(`${BASE}${ruta}`, { headers: cabeceras() });
  if (!respuesta.ok) throw new Error(`No se pudo exportar (${respuesta.status})`);
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  enlace.click();
  URL.revokeObjectURL(url);
}

export function exportarEvaluacion(evaluationId: string, formato: "json" | "csv") {
  return descargarBlob(
    `/evaluations/${evaluationId}/export?format=${formato}`,
    `${evaluationId}.${formato}`,
  );
}

export function exportarConsolidado() {
  return descargarBlob("/evaluations/export/consolidated.csv", "consolidado_ecm.csv");
}
