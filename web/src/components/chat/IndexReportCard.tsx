import { motion } from "framer-motion";
import { AlertTriangle, EyeOff, FileText, XCircle } from "lucide-react";

import type { ProyectoInfo } from "@/types";

const ETIQUETAS_ANONIMIZACION: Record<string, string> = {
  autor: "autores",
  asesor: "asesor",
  dni: "DNI",
  correo: "correos",
  orcid: "ORCID",
};

/** Reporte de indexación: segmentación estructural + anonimización. */
export default function IndexReportCard({ proyecto }: { proyecto: ProyectoInfo }) {
  const reporte = proyecto.reporte_indexacion;
  const maxPalabras = Math.max(...reporte.secciones.map((s) => s.palabras), 1);
  const presentes = reporte.secciones.filter((s) => s.presente).length;
  const anonimizacion = reporte.anonimizacion;

  return (
    <div className="w-full">
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3 flex-wrap">
        <FileText className="w-4 h-4 text-primary" />
        <span className="font-medium text-foreground">{proyecto.nombre}</span>
        <span>
          · {proyecto.paginas} páginas · {proyecto.palabras.toLocaleString("es")} palabras ·{" "}
          {presentes}/{reporte.secciones.length} secciones
        </span>
      </div>

      {anonimizacion && (
        <div className="glass rounded-2xl p-4 mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold mb-1.5">
            <EyeOff className="w-4 h-4 text-primary" />
            Anonimización aplicada (doble ciego)
          </div>
          {Object.keys(anonimizacion.reemplazos).length > 0 ? (
            <p className="text-[13px] text-muted-foreground">
              Se enmascararon:{" "}
              {Object.entries(anonimizacion.reemplazos)
                .map(([tipo, n]) => `${ETIQUETAS_ANONIMIZACION[tipo] ?? tipo} (${n})`)
                .join(", ")}
              . El mapeo se guarda localmente y nunca se envía a los jueces.
            </p>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No se detectaron datos identificatorios que enmascarar.
            </p>
          )}
          {anonimizacion.advertencias.map((a, i) => (
            <p key={i} className="mt-1.5 text-[12px] text-[#FF9500] flex items-start gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {a}
            </p>
          ))}
        </div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="glass rounded-2xl p-4"
      >
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="font-medium pb-2">Sección</th>
              <th className="font-medium pb-2 text-right pr-3">Págs.</th>
              <th className="font-medium pb-2 text-right pr-3">Palabras</th>
              <th className="font-medium pb-2 w-1/4"></th>
            </tr>
          </thead>
          <tbody>
            {reporte.secciones.map((s) => (
              <tr key={s.id} className="border-t border-border/50">
                <td className="py-1.5 pr-2">
                  <span className="text-muted-foreground mr-1.5 tabular-nums">{s.id}</span>
                  {s.presente ? (
                    s.nombre
                  ) : (
                    <span className="text-destructive inline-flex items-center gap-1">
                      <XCircle className="w-3.5 h-3.5" /> {s.nombre} — no encontrada
                    </span>
                  )}
                </td>
                <td className="py-1.5 text-right pr-3 text-muted-foreground tabular-nums">
                  {s.presente && s.pagina_inicio != null ? `${s.pagina_inicio}–${s.pagina_fin}` : "—"}
                </td>
                <td className="py-1.5 text-right pr-3 tabular-nums">
                  {s.presente ? s.palabras.toLocaleString("es") : "—"}
                </td>
                <td className="py-1.5">
                  {s.presente && (
                    <div className="h-1 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full ${s.palabras < 50 ? "bg-[#FF9500]" : "bg-primary/70"}`}
                        style={{ width: `${Math.max(4, (s.palabras / maxPalabras) * 100)}%` }}
                      />
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {reporte.advertencias.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border/60 space-y-1">
            {reporte.advertencias.map((a, i) => (
              <p key={i} className="text-[12px] text-[#FF9500] flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {a}
              </p>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
