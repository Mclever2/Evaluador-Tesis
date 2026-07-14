import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { ClipboardCheck, Loader2 } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { guardarClave, verificarAcceso } from "@/lib/api";

/** Puerta de acceso simple: solo aparece si el backend exige APP_ACCESS_KEY. */
export default function AccessGate({ onAcceso }: { onAcceso: () => void }) {
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setCargando(true);
    guardarClave(clave.trim());
    const estado = await verificarAcceso();
    setCargando(false);
    if (estado === "ok") {
      onAcceso();
    } else {
      setError("Clave incorrecta. Verifica con el administrador del sistema.");
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-5 relative overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <ThemeToggle />
      </div>
      <motion.div
        aria-hidden
        className="absolute -top-32 -right-32 w-[30rem] h-[30rem] rounded-full bg-[#007AFF]/12 blur-3xl"
        animate={{ y: [0, 28, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-md"
      >
        <div className="flex items-center justify-center gap-2 font-semibold mb-6">
          <ClipboardCheck className="w-6 h-6 text-primary" />
          Evaluador de Calidad Metodológica
        </div>

        <div className="glass rounded-3xl p-8">
          <h1 className="font-semibold text-lg">Acceso restringido</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Este despliegue requiere una clave de acceso.
          </p>
          <form onSubmit={onSubmit} className="mt-5 space-y-4">
            <input
              type="password"
              required
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              placeholder="Clave de acceso"
              className="w-full rounded-xl border border-input bg-card px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-xl px-3.5 py-2.5">
                {error}
              </p>
            )}
            <Button type="submit" disabled={cargando || !clave.trim()} className="w-full rounded-xl h-11">
              {cargando && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Entrar
            </Button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
