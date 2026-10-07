import { useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Download,
  FileJson,
  MinusCircle,
  Printer,
  Users,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { exportarEvaluacion } from "@/lib/api";
import {
  colorNivel,
  colorNivelItem,
  etiquetaNivelItem,
  NOMBRE_COMPONENTE,
  NOMBRE_CONTRADICCION,
  NOMBRE_DIMENSION,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { EvaluacionResultado, ItemEvaluado, SeccionEvaluada } from "@/types";

function IconoNivel({ item }: { item: ItemEvaluado }) {
  const nivel = item.nivel_final;
  if (nivel == null) return <MinusCircle className="w-3.5 h-3.5" />;
  if (nivel === "cumple" || nivel === 3) return <CheckCircle2 className="w-3.5 h-3.5" />;
  if (nivel === "no_cumple" || nivel === 0) return <XCircle className="w-3.5 h-3.5" />;
  return <AlertTriangle className="w-3.5 h-3.5" />;
}

function FilaItem({ item }: { item: ItemEvaluado }) {
  return (
    <li className="py-2.5 border-b border-border/60 last:border-0">
      <div className="flex items-start gap-3">
        <span className="shrink-0 w-9 h-8 rounded-xl bg-muted grid place-items-center text-xs font-semibold tabular-nums">
          {item.id}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-snug">{item.criterio}</p>
          {item.evidencia && (
            <p className="mt-1 text-[12px] italic text-muted-foreground leading-snug">
              Evidencia: {item.evidencia}
            </p>
          )}
          {item.observacion && (
            <p className="mt-0.5 text-[12px] text-muted-foreground leading-snug">{item.observacion}</p>
          )}
          {Object.keys(item.niveles_jueces).length > 0 && (
            <p className="mt-1 text-[11px] text-muted-foreground/80 tabular-nums">
              {Object.entries(item.niveles_jueces)
                .map(([juez, nivel]) => `${juez}: ${etiquetaNivelItem(nivel)}`)
                .join(" · ")}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className={cn("flex items-center gap-1 justify-end text-xs font-medium", colorNivelItem(item.nivel_final))}>
            <IconoNivel item={item} /> {etiquetaNivelItem(item.nivel_final)}
            {item.discrepancia && (
              <span title="Discrepancia entre jueces: revisar manualmente">
                <Users className="w-3.5 h-3.5 text-[#FF9500]" />
              </span>
            )}
          </div>
          <div className="mt-0.5 text-sm font-semibold tabular-nums">
            {item.puntaje}/{item.puntaje_max}
          </div>
        </div>
      </div>
    </li>
  );
}

function SeccionAcordeon({ seccion, abierta, onToggle }: {
  seccion: SeccionEvaluada;
  abierta: boolean;
  onToggle: () => void;
}) {
  const ratio = seccion.subtotal != null && seccion.max ? seccion.subtotal / seccion.max : 0;
  const color = !seccion.activa
    ? "text-muted-foreground"
    : ratio >= 0.8
      ? "text-[#34C759]"
      : ratio >= 0.5
        ? "text-[#FF9500]"
        : "text-destructive";
  return (
    <section className="glass rounded-2xl overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className="text-xs font-semibold text-muted-foreground tabular-nums w-9">{seccion.id}</span>
        <span className="flex-1 text-sm font-medium truncate">
          {seccion.nombre}
          {!seccion.presente && seccion.activa && (
            <span className="ml-2 text-xs text-destructive">no encontrada</span>
          )}
          {!seccion.activa && <span className="ml-2 text-xs text-muted-foreground">no activa</span>}
        </span>
        <span className={cn("text-sm font-semibold tabular-nums", color)}>
          {seccion.subtotal != null ? `${seccion.subtotal}/${seccion.max}` : `—/${seccion.max}`}
        </span>
        <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", abierta && "rotate-180")} />
      </button>
      {abierta && seccion.items.length > 0 && (
        <ul className="px-4 pb-3">
          {seccion.items.map((item) => (
            <FilaItem key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default function ResultDetail({
  resultado,
  evaluationId,
  onCerrar,
}: {
  resultado: EvaluacionResultado;
  evaluationId: string;
  onCerrar: () => void;
}) {
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set([resultado.secciones[0]?.id]));
  const [todasAbiertas, setTodasAbiertas] = useState(false);
  const color = colorNivel(resultado.nivel);
  const metricas = resultado.metricas_deterministicas;

  function alternar(id: string) {
    setAbiertas((previas) => {
      const nuevas = new Set(previas);
      if (nuevas.has(id)) nuevas.delete(id);
      else nuevas.add(id);
      return nuevas;
    });
  }

  function expandirTodo() {
    if (todasAbiertas) {
      setAbiertas(new Set());
    } else {
      setAbiertas(new Set(resultado.secciones.map((s) => s.id)));
    }
    setTodasAbiertas(!todasAbiertas);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="absolute inset-0 z-30 bg-background flex flex-col detalle-imprimible"
    >
      <div className="border-b border-border bg-card/60 backdrop-blur-xl">
        <div className="mx-auto max-w-4xl px-5 py-4 flex items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-full no-imprimir" onClick={onCerrar}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="font-semibold text-lg truncate">Informe de calidad metodológica</h1>
            <p className="text-xs text-muted-foreground">
              {resultado.rubric_id} · modo {resultado.mode} ·{" "}
              {new Date(resultado.timestamp).toLocaleString("es")} · prompts {resultado.prompts_hash}
            </p>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Total</div>
            <div className="text-xl font-bold tabular-nums" style={{ color }}>
              {resultado.total}/{resultado.puntaje_max_activo}
            </div>
            <div className="text-[11px] font-medium" style={{ color }}>
              {resultado.nivel}
              {resultado.total_normalizado != null && ` · ${resultado.total_normalizado}/100`}
              {resultado.nota_vigesimal != null && ` · ${resultado.nota_vigesimal}/20`}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-5 py-6 space-y-4">
          <div className="flex flex-wrap gap-2 no-imprimir">
            <Button size="sm" variant="outline" className="rounded-full h-8 text-xs gap-1.5 bg-card/60" onClick={expandirTodo}>
              <ChevronDown className="w-3.5 h-3.5" />
              {todasAbiertas ? "Colapsar todo" : "Expandir todo"}
            </Button>
            <Button size="sm" variant="outline" className="rounded-full h-8 text-xs gap-1.5 bg-card/60" onClick={() => window.print()}>
              <Printer className="w-3.5 h-3.5" />
              Imprimir
            </Button>
            <Button size="sm" variant="outline" className="rounded-full h-8 text-xs gap-1.5 bg-card/60" onClick={() => exportarEvaluacion(evaluationId, "json")}>
              <FileJson className="w-3.5 h-3.5" />
              Exportar JSON
            </Button>
            <Button size="sm" variant="outline" className="rounded-full h-8 text-xs gap-1.5 bg-card/60" onClick={() => exportarEvaluacion(evaluationId, "csv")}>
              <Download className="w-3.5 h-3.5" />
              Exportar CSV
            </Button>
          </div>

          <section className="glass rounded-3xl p-5">
            <h2 className="font-semibold flex items-center gap-2 mb-3">
              <Award className="w-4 h-4 text-primary" /> Subtotales por sección
            </h2>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5">
              {resultado.secciones.map((s) => {
                const ratio = s.subtotal != null && s.max ? s.subtotal / s.max : 0;
                return (
                  <div key={s.id} className="flex items-center gap-2 text-[13px]">
                    <span className="w-9 text-muted-foreground tabular-nums">{s.id}</span>
                    <span className="flex-1 truncate">{s.nombre}</span>
                    <div className="w-20 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, ratio * 100)}%`,
                          backgroundColor: s.activa ? colorNivel(ratio >= 0.9 ? "Excelente" : ratio >= 0.75 ? "Bueno" : ratio >= 0.6 ? "Regular" : "Insuficiente") : "#8884",
                        }}
                      />
                    </div>
                    <span className="w-14 text-right font-medium tabular-nums">
                      {s.subtotal != null ? `${s.subtotal}/${s.max}` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          {resultado.secciones.map((seccion) => (
            <SeccionAcordeon
              key={seccion.id}
              seccion={seccion}
              abierta={abiertas.has(seccion.id)}
              onToggle={() => alternar(seccion.id)}
            />
          ))}

          <div className="grid sm:grid-cols-2 gap-4">
            <section className="glass rounded-3xl p-5">
              <h2 className="font-semibold mb-3">Dimensiones transversales</h2>
              <ul className="space-y-3">
                {resultado.dimensiones_transversales.map((d) => (
                  <li key={d.dimension} className="text-[13px]">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{NOMBRE_DIMENSION[d.dimension] ?? d.dimension}</span>
                      <span className="font-semibold tabular-nums">{d.mediana ?? "—"}/5</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary/80"
                        style={{ width: `${((d.mediana ?? 0) / 5) * 100}%` }}
                      />
                    </div>
                    <p className="mt-1 text-muted-foreground leading-snug">{d.justificacion}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Escala 1–5 por mediana del panel. No reemplazan al puntaje de rúbrica.
              </p>
            </section>

            <section className="glass rounded-3xl p-5">
              <h2 className="font-semibold flex items-center gap-2 mb-3">
                <BarChart3 className="w-4 h-4 text-primary" /> Métricas de texto
              </h2>
              {metricas ? (
                <ul className="text-[13px] space-y-1.5">
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Fernández-Huerta</span>
                    <span className="font-medium tabular-nums">
                      {metricas.legibilidad.fernandez_huerta ?? "—"}{" "}
                      {metricas.legibilidad.interpretacion && `(${metricas.legibilidad.interpretacion})`}
                    </span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Szigriszt-Pazos</span>
                    <span className="font-medium tabular-nums">{metricas.legibilidad.szigriszt_pazos ?? "—"}</span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">TTR / MTLD</span>
                    <span className="font-medium tabular-nums">
                      {metricas.riqueza_lexica.ttr ?? "—"} / {metricas.riqueza_lexica.mtld ?? "—"}
                    </span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Palabras totales</span>
                    <span className="font-medium tabular-nums">{metricas.palabras_totales.toLocaleString("es")}</span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Long. media de oración</span>
                    <span className="font-medium tabular-nums">{metricas.longitud_media_oracion ?? "—"} palabras</span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Citas / referencias</span>
                    <span className="font-medium tabular-nums">
                      {metricas.citas_referencias.citas_en_texto} / {metricas.citas_referencias.referencias_en_lista}
                    </span>
                  </li>
                  <li className="flex justify-between">
                    <span className="text-muted-foreground">Completitud estructural</span>
                    <span className="font-medium tabular-nums">
                      {metricas.completitud.presentes}/{metricas.completitud.total}
                    </span>
                  </li>
                  {metricas.citas_referencias.citas_sin_referencia.length > 0 && (
                    <li className="pt-1.5 text-[12px] text-[#FF9500]">
                      Citas sin referencia (aprox.): {metricas.citas_referencias.citas_sin_referencia.join("; ")}
                    </li>
                  )}
                  {metricas.citas_referencias.referencias_nunca_citadas.length > 0 && (
                    <li className="text-[12px] text-[#FF9500]">
                      Referencias nunca citadas (aprox.): {metricas.citas_referencias.referencias_nunca_citadas.join("; ")}
                    </li>
                  )}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No disponibles.</p>
              )}
            </section>
          </div>

          {(resultado.argumentacion || resultado.coherencia_global) && (
            <div className="grid sm:grid-cols-2 gap-4">
              <section className="glass rounded-3xl p-5">
                <h2 className="font-semibold mb-1">Coherencia global</h2>
                {resultado.coherencia_global ? (
                  <>
                    <p className="text-[13px] flex items-center justify-between">
                      <span className="text-muted-foreground">
                        {resultado.coherencia_global.contradicciones_nucleo} del núcleo ·{" "}
                        {resultado.coherencia_global.contradicciones_menores} menores
                      </span>
                      <span className="font-semibold tabular-nums">{resultado.coherencia_global.nota}/5</span>
                    </p>
                    {resultado.coherencia_global.contradicciones.length === 0 ? (
                      <p className="mt-2 text-[13px] text-muted-foreground">Sin contradicciones entre las partes del proyecto.</p>
                    ) : (
                      <ul className="mt-2 space-y-2.5">
                        {resultado.coherencia_global.contradicciones.map((c, i) => (
                          <li key={i} className="text-[12px] leading-snug">
                            <span
                              className={cn(
                                "font-medium",
                                c.gravedad === "nucleo" ? "text-destructive" : "text-[#FF9500]",
                              )}
                            >
                              {NOMBRE_CONTRADICCION[c.tipo] ?? c.tipo} ({c.gravedad === "nucleo" ? "núcleo" : "menor"})
                            </span>
                            <p className="mt-0.5">
                              <span className="text-muted-foreground">{c.seccion_a}:</span> «{c.cita_a}»
                            </p>
                            <p>
                              <span className="text-muted-foreground">{c.seccion_b}:</span> «{c.cita_b}»
                            </p>
                            <p className="text-muted-foreground">{c.explicacion}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">No disponible.</p>
                )}
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Nota por regla fija a partir de contradicciones con citas verificadas. No reemplaza al puntaje de rúbrica.
                </p>
              </section>

              <section className="glass rounded-3xl p-5">
                <h2 className="font-semibold mb-3">Índice argumentativo (Toulmin)</h2>
                {resultado.argumentacion ? (
                  <ul className="space-y-3">
                    {resultado.argumentacion.secciones.map((s) => (
                      <li key={s.seccion_id} className="text-[13px]">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{s.nombre}</span>
                          <span className="font-semibold tabular-nums">
                            {s.indice_estructural == null ? "—" : `${Math.round(s.indice_estructural * 100)}%`}
                          </span>
                        </div>
                        {s.elegible ? (
                          <>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {["afirmacion", "dato", "garantia", "respaldo", "calificador", "refutacion"].map((c) => (
                                <span
                                  key={c}
                                  className={cn(
                                    "px-1.5 py-0.5 rounded-md text-[11px]",
                                    s.presentes.includes(c) ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
                                  )}
                                >
                                  {NOMBRE_COMPONENTE[c]}
                                </span>
                              ))}
                            </div>
                            <p className="mt-1 text-[11px] text-muted-foreground">
                              Nivel {s.nivel}/5 · {s.oraciones} oraciones
                            </p>
                          </>
                        ) : (
                          <p className="mt-1 text-[12px] text-muted-foreground">
                            No analizada: la sección no está redactada completa ({s.palabras} palabras propias).
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">No disponible.</p>
                )}
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Componentes de Toulmin presentes sobre 6. No reemplaza al puntaje de rúbrica.
                </p>
              </section>
            </div>
          )}

          <section className="glass rounded-3xl p-5">
            <h2 className="font-semibold flex items-center gap-2 mb-2">
              <Users className="w-4 h-4 text-primary" /> Acuerdo del panel
            </h2>
            <p className="text-[13px]">
              {resultado.panel.pct_discrepancia}% de ítems con discrepancia (
              {resultado.panel.items_marcados.length} marcados para revisión humana)
              {resultado.panel.panel_incompleto && " · PANEL INCOMPLETO: hubo fallas de API registradas"}
            </p>
            {resultado.panel.items_marcados.length > 0 && (
              <p className="mt-1.5 text-[12px] text-muted-foreground">
                Ítems marcados: {resultado.panel.items_marcados.join(", ")}
              </p>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground tabular-nums">
              Jueces: {Object.entries(resultado.config_modelos).map(([j, m]) => `${j}=${m}`).join(" · ")} · seed{" "}
              {resultado.seed} · temperatura {resultado.temperature} · {resultado.costo.tokens_entrada + resultado.costo.tokens_salida}{" "}
              tokens{resultado.costo.usd_estimado != null && ` · $${resultado.costo.usd_estimado} estimado`}
            </p>
          </section>
        </div>
      </div>
    </motion.div>
  );
}
