import { useState } from "react";
import { Check, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { EvaluarBody, RubricaInfo } from "@/types";

const SEMANAS = [1, 2, 3, 4, 5, 6, 7];

interface EvalConfigCardProps {
  rubricas: RubricaInfo[];
  deshabilitado: boolean;
  onEvaluar: (cuerpo: EvaluarBody) => void;
}

/** Selector visible de rúbrica y modo antes de evaluar (especifica_v1 + completo por defecto). */
export default function EvalConfigCard({ rubricas, deshabilitado, onEvaluar }: EvalConfigCardProps) {
  const [rubrica, setRubrica] = useState("especifica_v1");
  const [modo, setModo] = useState<"completo" | "progresivo">("completo");
  const [semanas, setSemanas] = useState<number[]>([1]);
  const [incluirAdmin, setIncluirAdmin] = useState(true);

  const esFicha = rubrica.startsWith("ficha_upao");

  function alternarSemana(semana: number) {
    setSemanas((previas) =>
      previas.includes(semana) ? previas.filter((s) => s !== semana) : [...previas, semana].sort(),
    );
  }

  function evaluar() {
    const cuerpo: EvaluarBody = { rubric: rubrica, mode: modo };
    if (modo === "progresivo") cuerpo.semanas_activas = semanas;
    if (esFicha) cuerpo.incluir_administrativos = incluirAdmin;
    onEvaluar(cuerpo);
  }

  return (
    <div className="glass rounded-2xl p-4 space-y-3">
      <div>
        <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
          Rúbrica
        </p>
        <div className="flex flex-wrap gap-2">
          {rubricas.map((r) => (
            <button
              key={r.id}
              onClick={() => setRubrica(r.id)}
              className={cn(
                "rounded-full px-3.5 py-1.5 text-[13px] border transition-colors flex items-center gap-1.5",
                rubrica === r.id
                  ? "bg-accent text-accent-foreground border-primary/40 font-medium"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {rubrica === r.id && <Check className="w-3.5 h-3.5" />}
              {r.id} · {r.items} ítems · máx {r.puntaje_maximo}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
          Modo
        </p>
        <div className="bg-muted rounded-xl p-1 grid grid-cols-2 text-[13px] font-medium max-w-xs">
          {(["completo", "progresivo"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setModo(m)}
              className={cn(
                "py-1.5 rounded-lg transition-all capitalize",
                modo === m ? "bg-card shadow-sm" : "text-muted-foreground",
              )}
            >
              {m}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-[12px] text-muted-foreground">
          {modo === "completo"
            ? "Las 15 secciones cuentan; una sección ausente puntúa 0."
            : "Solo puntúan las secciones de las semanas activas; el total se normaliza sobre el máximo activo."}
        </p>
      </div>

      {modo === "progresivo" && (
        <div>
          <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
            Semanas activas
          </p>
          <div className="flex flex-wrap gap-1.5">
            {SEMANAS.map((semana) => (
              <button
                key={semana}
                onClick={() => alternarSemana(semana)}
                className={cn(
                  "w-8 h-8 rounded-full text-[13px] border transition-colors tabular-nums",
                  semanas.includes(semana)
                    ? "bg-primary text-primary-foreground border-primary font-medium"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {semana}
              </button>
            ))}
          </div>
        </div>
      )}

      {esFicha && (
        <label className="flex items-center gap-2 text-[13px] cursor-pointer">
          <input
            type="checkbox"
            checked={incluirAdmin}
            onChange={(e) => setIncluirAdmin(e.target.checked)}
            className="accent-[#007AFF]"
          />
          Incluir aspectos administrativos (ítems 28–31)
        </label>
      )}

      <div className="pt-1">
        <Button
          onClick={evaluar}
          disabled={deshabilitado || (modo === "progresivo" && semanas.length === 0)}
          className="rounded-full px-5 gap-2 shadow-md shadow-primary/25"
        >
          <Play className="w-4 h-4" />
          Evaluar proyecto
        </Button>
      </div>
    </div>
  );
}
