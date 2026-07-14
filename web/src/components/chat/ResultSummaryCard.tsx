import { motion } from "framer-motion";
import { Download, FileJson, Maximize2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { exportarEvaluacion } from "@/lib/api";
import { colorNivel, NOMBRE_DIMENSION, porcentajeTotal } from "@/lib/format";
import type { EvaluacionResultado } from "@/types";

interface ResultSummaryCardProps {
  resultado: EvaluacionResultado;
  evaluationId: string;
  onVerDetalle: () => void;
}

function Anillo({ resultado }: { resultado: EvaluacionResultado }) {
  const pct = Math.max(0, Math.min(100, porcentajeTotal(resultado)));
  const radio = 52;
  const circunferencia = 2 * Math.PI * radio;
  const color = colorNivel(resultado.nivel);
  return (
    <div className="relative w-36 h-36 shrink-0">
      <svg viewBox="0 0 128 128" className="w-full h-full -rotate-90">
        <circle cx="64" cy="64" r={radio} fill="none" strokeWidth="10" className="stroke-muted" />
        <motion.circle
          cx="64"
          cy="64"
          r={radio}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={circunferencia}
          initial={{ strokeDashoffset: circunferencia }}
          animate={{ strokeDashoffset: circunferencia * (1 - pct / 100) }}
          transition={{ duration: 1.1, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-2xl font-bold tabular-nums leading-none">
            {resultado.total.toLocaleString("es")}
          </div>
          <div className="text-[11px] text-muted-foreground tabular-nums">
            / {resultado.puntaje_max_activo}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ResultSummaryCard({ resultado, evaluationId, onVerDetalle }: ResultSummaryCardProps) {
  const color = colorNivel(resultado.nivel);
  return (
    <div className="w-full glass rounded-3xl p-5">
      <div className="flex flex-wrap items-center gap-5">
        <Anillo resultado={resultado} />
        <div className="min-w-0 flex-1">
          <div
            className="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold"
            style={{ color, backgroundColor: `${color}1f` }}
          >
            {resultado.nivel ?? "Sin nivel"}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Rúbrica <span className="font-medium text-foreground">{resultado.rubric_id}</span> · modo{" "}
            <span className="font-medium text-foreground">{resultado.mode}</span>
            {resultado.total_normalizado != null && (
              <>
                {" "}
                · normalizado{" "}
                <span className="font-medium text-foreground tabular-nums">
                  {resultado.total_normalizado}/100
                </span>
              </>
            )}
            {resultado.nota_vigesimal != null && (
              <>
                {" "}
                · nota vigesimal{" "}
                <span className="font-medium text-foreground tabular-nums">
                  {resultado.nota_vigesimal}/20
                </span>
              </>
            )}
          </p>
          <p className="mt-1.5 text-[13px] text-muted-foreground flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5" />
            Acuerdo del panel: {(100 - resultado.panel.pct_discrepancia).toFixed(1)}% ·{" "}
            {resultado.panel.items_marcados.length} ítems con discrepancia
            {resultado.panel.panel_incompleto && " · panel incompleto"}
          </p>
          {resultado.dimensiones_transversales.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {resultado.dimensiones_transversales.map((d) => (
                <span key={d.dimension} className="rounded-full bg-muted px-2.5 py-1 text-[11.5px]">
                  {NOMBRE_DIMENSION[d.dimension] ?? d.dimension}:{" "}
                  <span className="font-semibold tabular-nums">{d.mediana ?? "—"}/5</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-border/60 flex flex-wrap gap-2">
        <Button size="sm" onClick={onVerDetalle} className="rounded-full h-8 text-xs gap-1.5">
          <Maximize2 className="w-3.5 h-3.5" />
          Ver informe completo
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="rounded-full h-8 text-xs gap-1.5 bg-card/60"
          onClick={() => exportarEvaluacion(evaluationId, "json")}
        >
          <FileJson className="w-3.5 h-3.5" />
          JSON
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="rounded-full h-8 text-xs gap-1.5 bg-card/60"
          onClick={() => exportarEvaluacion(evaluationId, "csv")}
        >
          <Download className="w-3.5 h-3.5" />
          CSV
        </Button>
      </div>
    </div>
  );
}
