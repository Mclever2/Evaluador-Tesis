import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { ClipboardCheck, Eye, EyeOff, Loader2 } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

/** Inicio de sesión con Supabase. SIN registro: los usuarios se crean desde
 * el panel de Supabase (Authentication → Users). */
export default function LoginGate() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setError(null);
    setCargando(true);
    const { error: excepcion } = await supabase.auth.signInWithPassword({ email, password });
    setCargando(false);
    if (excepcion) {
      setError(
        excepcion.message === "Invalid login credentials"
          ? "Correo o contraseña incorrectos."
          : excepcion.message,
      );
    }
    // Con sesión válida, App reacciona vía onAuthStateChange.
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
          <h1 className="font-semibold text-lg">Iniciar sesión</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Acceso solo para usuarios autorizados del estudio.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label className="text-sm font-medium">Correo</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@correo.com"
                className="mt-1.5 w-full rounded-xl border border-input bg-card px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Contraseña</label>
              <div className="relative mt-1.5">
                <input
                  type={verPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Tu contraseña"
                  className="w-full rounded-xl border border-input bg-card pl-3.5 pr-11 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                  type="button"
                  onClick={() => setVerPassword((v) => !v)}
                  title={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 w-8 h-8 grid place-items-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  {verPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-xl px-3.5 py-2.5">
                {error}
              </p>
            )}

            <Button type="submit" disabled={cargando} className="w-full rounded-xl h-11 text-base">
              {cargando && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Entrar
            </Button>
          </form>
        </div>

        <p className="mt-5 text-center text-xs text-muted-foreground">
          Las cuentas las crea el administrador del estudio desde Supabase; aquí no hay registro.
        </p>
      </motion.div>
    </div>
  );
}
