import { useEffect, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { motion } from "framer-motion";
import { ClipboardCheck, Download, Loader2, Menu } from "lucide-react";

import AccessGate from "@/components/AccessGate";
import FondoLiquido from "@/components/FondoLiquido";
import LoginGate from "@/components/LoginGate";
import ResultDetail from "@/components/ResultDetail";
import ThemeToggle from "@/components/ThemeToggle";
import ChatInput from "@/components/chat/ChatInput";
import EvalConfigCard from "@/components/chat/EvalConfigCard";
import IndexReportCard from "@/components/chat/IndexReportCard";
import MessageBubble from "@/components/chat/MessageBubble";
import ProgressTimeline from "@/components/chat/ProgressTimeline";
import ResultSummaryCard from "@/components/chat/ResultSummaryCard";
import Sidebar from "@/components/chat/Sidebar";
import UploadZone from "@/components/chat/UploadZone";
import { Button } from "@/components/ui/button";
import {
  exportarConsolidado,
  lanzarEvaluacion,
  listarRubricas,
  obtenerEvaluacion,
  preguntarSobreInforme,
  setTokenSesion,
  streamEventos,
  subirProyecto,
  verificarAcceso,
} from "@/lib/api";
import {
  cargarMensajes,
  crearConversacion,
  eliminarConversacion,
  guardarEvaluacion,
  guardarMensaje,
  listarConversaciones,
  setNotificadorErrores,
  type ConversacionResumen,
} from "@/lib/historial";
import { supabase, supabaseHabilitado } from "@/lib/supabase";
import type {
  EvaluarBody,
  EvaluacionResultado,
  Mensaje,
  PasoProgreso,
  ProyectoInfo,
  RubricaInfo,
} from "@/types";

let _id = 0;
const nuevoId = () => `m${Date.now()}_${_id++}`;

type Puerta = "verificando" | "clave" | "abierta";

export default function App() {
  // Acceso: con Supabase → sesión; sin Supabase → clave simple opcional.
  const [sesion, setSesion] = useState<Session | null>(null);
  const [cargandoSesion, setCargandoSesion] = useState(supabaseHabilitado);
  const [puerta, setPuerta] = useState<Puerta>(supabaseHabilitado ? "abierta" : "verificando");

  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [rubricas, setRubricas] = useState<RubricaInfo[]>([]);
  const [proyecto, setProyecto] = useState<ProyectoInfo | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [evaluando, setEvaluando] = useState(false);
  const [preguntando, setPreguntando] = useState(false);
  const [pasos, setPasos] = useState<PasoProgreso[]>([]);
  const [archivoPendiente, setArchivoPendiente] = useState<File | null>(null);
  const [detalle, setDetalle] = useState<{ resultado: EvaluacionResultado; id: string } | null>(null);
  const [ultimaEvaluacion, setUltimaEvaluacion] = useState<{ id: string; resultado: EvaluacionResultado } | null>(null);

  // Historial (solo con Supabase)
  const [conversaciones, setConversaciones] = useState<ConversacionResumen[]>([]);
  const [convActiva, setConvActiva] = useState<string | null>(null);
  const [navAbierto, setNavAbierto] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const erroresMostrados = useRef<Set<string>>(new Set());

  // Errores de guardado del historial: visibles en el hilo (sin persistirse,
  // para no entrar en bucle) y solo una vez por tipo de error.
  useEffect(() => {
    setNotificadorErrores((mensaje) => {
      if (erroresMostrados.current.has(mensaje)) return;
      erroresMostrados.current.add(mensaje);
      setMensajes((previos) => [
        ...previos,
        { id: nuevoId(), rol: "assistant", contenido: `⚠️ Historial de Supabase — ${mensaje}` },
      ]);
    });
    return () => setNotificadorErrores(null);
  }, []);

  // ── Sesión de Supabase ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!supabase) return;
    supabase.auth
      .getSession()
      .then(({ data }) => {
        setSesion(data.session);
        setTokenSesion(data.session?.access_token ?? null);
      })
      .finally(() => setCargandoSesion(false));
    const { data: sub } = supabase.auth.onAuthStateChange((_evento, nueva) => {
      setSesion(nueva);
      setTokenSesion(nueva?.access_token ?? null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!supabaseHabilitado) {
      verificarAcceso().then((estado) => setPuerta(estado === "clave" ? "clave" : "abierta"));
    }
  }, []);

  const autenticado = supabaseHabilitado ? sesion !== null : puerta === "abierta";

  useEffect(() => {
    if (autenticado) {
      listarRubricas().then(setRubricas).catch(() => setRubricas([]));
      cargarConversaciones();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autenticado]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [mensajes, pasos]);

  async function cargarConversaciones() {
    setConversaciones(await listarConversaciones());
  }

  function agregarMensaje(mensaje: Omit<Mensaje, "id">, convId?: string | null) {
    setMensajes((previos) => [...previos, { ...mensaje, id: nuevoId() }]);
    guardarMensaje(convId ?? convActiva, mensaje as Mensaje);
  }

  // ── Historial ──────────────────────────────────────────────────────────────
  function nuevaEvaluacion() {
    if (evaluando || subiendo) return;
    setConvActiva(null);
    setMensajes([]);
    setProyecto(null);
    setUltimaEvaluacion(null);
    setDetalle(null);
    setPasos([]);
  }

  async function seleccionarConversacion(id: string) {
    if (evaluando || subiendo) return;
    setConvActiva(id);
    setDetalle(null);
    const cargados = await cargarMensajes(id);
    setMensajes(cargados.map((m) => ({ ...m, id: nuevoId() })));

    const resumen = conversaciones.find((c) => c.id === id);
    const proyectoGuardado =
      resumen?.proyecto ?? cargados.find((m) => m.tipo === "indexacion")?.proyecto ?? null;
    setProyecto(proyectoGuardado);

    const ultimoResultado = [...cargados]
      .reverse()
      .find((m) => m.tipo === "resultado" && m.resultado && m.evaluationId);
    setUltimaEvaluacion(
      ultimoResultado
        ? { id: ultimoResultado.evaluationId!, resultado: ultimoResultado.resultado! }
        : null,
    );
  }

  async function borrarConversacion(id: string) {
    await eliminarConversacion(id);
    if (id === convActiva) nuevaEvaluacion();
    cargarConversaciones();
  }

  async function cerrarSesion() {
    await supabase?.auth.signOut();
    setTokenSesion(null);
    nuevaEvaluacion();
    setConversaciones([]);
  }

  // ── Subida ─────────────────────────────────────────────────────────────────
  async function subir(archivo: File) {
    setSubiendo(true);
    try {
      const info = await subirProyecto(archivo);
      // Cada proyecto abre una conversación nueva en el historial.
      setMensajes([]);
      setUltimaEvaluacion(null);
      setProyecto(info);
      const convId = await crearConversacion(info.nombre, info);
      setConvActiva(convId);
      if (convId) cargarConversaciones();

      agregarMensaje({ rol: "assistant", tipo: "indexacion", proyecto: info }, convId);
      agregarMensaje(
        {
          rol: "assistant",
          tipo: "config",
          contenido:
            "Proyecto indexado y anonimizado. Elige la rúbrica y el modo, y lanza la evaluación del panel de jueces:",
        },
        convId,
      );
    } catch (exc) {
      agregarMensaje({
        rol: "assistant",
        contenido: `⚠️ No pude procesar el archivo: ${exc instanceof Error ? exc.message : exc}`,
      });
    } finally {
      setSubiendo(false);
    }
  }

  function manejarArchivo(archivo: File) {
    if (proyecto) setArchivoPendiente(archivo);
    else subir(archivo);
  }

  // ── Evaluación ─────────────────────────────────────────────────────────────
  function aplicarEvento(evento: Record<string, unknown>) {
    const tipo = String(evento.tipo ?? "");
    setPasos((previos) => {
      const completados = previos.map((p) => ({ ...p, estado: "completado" as const }));
      if (tipo === "fase") {
        return [...completados, { id: previos.length, texto: String(evento.detalle ?? ""), estado: "activo" as const }];
      }
      if (tipo === "juez_seccion") {
        return [
          ...completados,
          { id: previos.length, texto: `Juez ${evento.juez} calificó ${evento.seccion}`, estado: "completado" as const },
        ];
      }
      if (tipo === "juez_transversales") {
        return [
          ...completados,
          { id: previos.length, texto: `Juez ${evento.juez} calificó las dimensiones transversales`, estado: "completado" as const },
        ];
      }
      return previos;
    });
  }

  async function evaluar(cuerpo: EvaluarBody) {
    if (!proyecto) return;
    const convId = convActiva;
    setEvaluando(true);
    setPasos([]);
    agregarMensaje(
      {
        rol: "user",
        contenido: `Evaluar con ${cuerpo.rubric} en modo ${cuerpo.mode}${
          cuerpo.semanas_activas ? ` (semanas ${cuerpo.semanas_activas.join(", ")})` : ""
        }`,
      },
      convId,
    );
    try {
      const { evaluation_id } = await lanzarEvaluacion(proyecto.project_id, cuerpo);
      await streamEventos(evaluation_id, aplicarEvento);

      const registro = await obtenerEvaluacion(evaluation_id);
      if (registro.estado === "completada" && registro.resultado) {
        setUltimaEvaluacion({ id: evaluation_id, resultado: registro.resultado });
        guardarEvaluacion(convId, evaluation_id, registro.resultado);
        agregarMensaje(
          {
            rol: "assistant",
            tipo: "resultado",
            resultado: registro.resultado,
            evaluationId: evaluation_id,
          },
          convId,
        );
        agregarMensaje(
          {
            rol: "assistant",
            contenido:
              "Evaluación completada. Puedes abrir el informe completo, exportarlo o preguntarme " +
              "sobre cualquier ítem (por qué salió en ese nivel, qué evidencia se usó).",
          },
          convId,
        );
      } else {
        agregarMensaje(
          {
            rol: "assistant",
            contenido: `⚠️ La evaluación terminó con error: ${registro.error ?? "desconocido"}. Verifica la clave de OpenAI del backend y reintenta.`,
          },
          convId,
        );
      }
    } catch (exc) {
      agregarMensaje(
        { rol: "assistant", contenido: `⚠️ ${exc instanceof Error ? exc.message : exc}` },
        convId,
      );
    } finally {
      setEvaluando(false);
      setPasos([]);
    }
  }

  // ── Preguntas sobre el informe ─────────────────────────────────────────────
  async function preguntar(texto: string) {
    if (!ultimaEvaluacion) return;
    agregarMensaje({ rol: "user", contenido: texto });
    setPreguntando(true);
    try {
      const { respuesta } = await preguntarSobreInforme(ultimaEvaluacion.id, texto);
      agregarMensaje({ rol: "assistant", contenido: respuesta });
    } catch (exc) {
      agregarMensaje({
        rol: "assistant",
        contenido: `⚠️ No pude responder: ${exc instanceof Error ? exc.message : exc}`,
      });
    } finally {
      setPreguntando(false);
    }
  }

  // ── Puertas de acceso ──────────────────────────────────────────────────────
  if (supabaseHabilitado) {
    if (cargandoSesion) {
      return <div className="min-h-screen grid place-items-center text-muted-foreground">Cargando…</div>;
    }
    if (!sesion) return <LoginGate />;
  } else {
    if (puerta === "verificando") {
      return <div className="min-h-screen grid place-items-center text-muted-foreground">Cargando…</div>;
    }
    if (puerta === "clave") return <AccessGate onAcceso={() => setPuerta("abierta")} />;
  }

  const vacio = mensajes.length === 0;
  const ocupado = subiendo || evaluando || preguntando;

  return (
    <div className="h-screen flex overflow-hidden">
      {supabaseHabilitado && (
        <Sidebar
          abierto={navAbierto}
          onCerrar={() => setNavAbierto(false)}
          email={sesion?.user.email ?? null}
          conversaciones={conversaciones}
          conversacionActiva={convActiva}
          onNueva={nuevaEvaluacion}
          onSeleccionar={seleccionarConversacion}
          onEliminar={borrarConversacion}
          onLogout={cerrarSesion}
        />
      )}
      {supabaseHabilitado && navAbierto && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setNavAbierto(false)}
          aria-hidden
        />
      )}

      <main className="flex-1 flex flex-col relative min-w-0">
        <FondoLiquido intenso={evaluando} />

        <header className="shrink-0 border-b border-border bg-card/60 backdrop-blur-xl z-10 no-imprimir">
          <div className="mx-auto max-w-3xl px-5 h-14 flex items-center gap-2">
            {supabaseHabilitado && (
              <button
                onClick={() => setNavAbierto(true)}
                className="md:hidden p-2 -ml-2 rounded-xl hover:bg-muted"
                aria-label="Abrir menú"
              >
                <Menu className="w-5 h-5" />
              </button>
            )}
            <ClipboardCheck className="w-5 h-5 text-primary" />
            <span className="font-semibold truncate">Evaluador de Calidad Metodológica</span>
            <span className="hidden sm:inline text-[11px] text-muted-foreground rounded-full bg-muted px-2.5 py-1">
              Panel de 3 jueces · doble ciego
            </span>
            <div className="ml-auto flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="rounded-full text-xs gap-1.5 text-muted-foreground"
                title="Descargar el CSV consolidado (una fila por proyecto)"
                onClick={() => exportarConsolidado().catch(() => undefined)}
              >
                <Download className="w-3.5 h-3.5" />
                Consolidado
              </Button>
              {!supabaseHabilitado && <ThemeToggle />}
            </div>
          </div>
        </header>

        {vacio ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
              <h1 className="text-3xl font-semibold tracking-tight">
                ¿Qué proyecto <span className="text-gradient">evaluamos</span> hoy?
              </h1>
              <p className="mt-2 text-muted-foreground max-w-lg">
                Sube el proyecto de tesis: se segmenta por secciones, se anonimiza (doble ciego) y un
                panel de 3 jueces LLM lo califica con la rúbrica.
              </p>
            </motion.div>
            <div className="w-full max-w-2xl">
              <UploadZone subiendo={subiendo} etapa="Extrayendo texto, anonimizando y segmentando…" onArchivo={manejarArchivo} />
              <p className="mt-3 text-center text-[11px] text-muted-foreground">
                Instrumento de medición: evalúa y reporta puntajes con evidencia. No mejora ni reescribe textos.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-3xl px-5 py-6 space-y-5">
                {proyecto && (
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Proyecto: <span className="font-medium text-foreground/80">{proyecto.nombre}</span>
                    </span>
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Rúbrica por defecto: <span className="font-medium text-foreground/80">especifica_v1 · completo</span>
                    </span>
                  </div>
                )}

                {mensajes.map((m) => {
                  if (m.tipo === "indexacion" && m.proyecto) {
                    return (
                      <MessageBubble key={m.id} rol="assistant" ancho>
                        <IndexReportCard proyecto={m.proyecto} />
                      </MessageBubble>
                    );
                  }
                  if (m.tipo === "config") {
                    return (
                      <MessageBubble key={m.id} rol="assistant" ancho>
                        {m.contenido && <p className="text-[15px] mb-3">{m.contenido}</p>}
                        <EvalConfigCard rubricas={rubricas} deshabilitado={ocupado} onEvaluar={evaluar} />
                      </MessageBubble>
                    );
                  }
                  if (m.tipo === "resultado" && m.resultado && m.evaluationId) {
                    const { resultado, evaluationId } = m;
                    return (
                      <MessageBubble key={m.id} rol="assistant" ancho>
                        <ResultSummaryCard
                          resultado={resultado}
                          evaluationId={evaluationId}
                          onVerDetalle={() => setDetalle({ resultado, id: evaluationId })}
                        />
                      </MessageBubble>
                    );
                  }
                  return <MessageBubble key={m.id} rol={m.rol} contenido={m.contenido} />;
                })}

                {evaluando && (
                  <div className="glass rounded-3xl px-5 py-4">
                    <ProgressTimeline pasos={pasos} />
                  </div>
                )}
                {(subiendo || preguntando) && (
                  <div className="glass rounded-3xl px-5 py-4 text-sm text-muted-foreground flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    {subiendo ? "Procesando el documento…" : "Consultando el informe…"}
                  </div>
                )}
              </div>
            </div>

            <div className="px-5 pb-5 no-imprimir">
              <div className="mx-auto max-w-3xl">
                {archivoPendiente && (
                  <div className="glass rounded-2xl px-4 py-3 mb-3 flex flex-wrap items-center gap-3 text-sm">
                    <span className="font-medium truncate">{archivoPendiente.name}</span>
                    <span className="text-muted-foreground">
                      ¿Evaluar este nuevo proyecto? (se abre una nueva conversación)
                    </span>
                    <div className="flex gap-2 ml-auto">
                      <Button size="sm" variant="outline" className="rounded-full" onClick={() => setArchivoPendiente(null)}>
                        Cancelar
                      </Button>
                      <Button
                        size="sm"
                        className="rounded-full"
                        onClick={() => {
                          subir(archivoPendiente);
                          setArchivoPendiente(null);
                        }}
                      >
                        Sí, nuevo proyecto
                      </Button>
                    </div>
                  </div>
                )}

                <ChatInput
                  ocupado={ocupado}
                  hayEvaluacion={ultimaEvaluacion !== null}
                  onEnviar={preguntar}
                  onArchivo={manejarArchivo}
                />
                <p className="mt-2 text-center text-[11px] text-muted-foreground">
                  Los puntajes del panel se validan contra jurados humanos; los ítems con discrepancia requieren revisión.
                </p>
              </div>
            </div>
          </>
        )}

        {detalle && (
          <ResultDetail
            resultado={detalle.resultado}
            evaluationId={detalle.id}
            onCerrar={() => setDetalle(null)}
          />
        )}
      </main>
    </div>
  );
}
