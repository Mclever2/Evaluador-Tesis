import { ClipboardCheck, LogOut, MessageSquare, PlusIcon, Trash2, X } from "lucide-react";

import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import type { ConversacionResumen } from "@/lib/historial";
import { cn } from "@/lib/utils";

interface SidebarProps {
  email: string | null;
  conversaciones: ConversacionResumen[];
  conversacionActiva: string | null;
  onNueva: () => void;
  onSeleccionar: (id: string) => void;
  onEliminar: (id: string) => void;
  onLogout: () => void;
  /** Estado del cajón en móvil; en ≥md es columna fija. */
  abierto?: boolean;
  onCerrar?: () => void;
}

export default function Sidebar({
  email,
  conversaciones,
  conversacionActiva,
  onNueva,
  onSeleccionar,
  onEliminar,
  onLogout,
  abierto = false,
  onCerrar,
}: SidebarProps) {
  return (
    <aside
      className={cn(
        "w-72 shrink-0 h-screen flex flex-col bg-white/55 dark:bg-zinc-900/50 backdrop-blur-xl border-r border-border no-imprimir",
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50 max-md:shadow-2xl max-md:transition-transform max-md:duration-300",
        abierto ? "max-md:translate-x-0" : "max-md:-translate-x-full",
      )}
    >
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <div className="flex items-center gap-2 font-semibold text-[15px]">
          <ClipboardCheck className="w-5 h-5 text-primary" />
          ECM
        </div>
        <button
          onClick={onCerrar}
          className="md:hidden p-1.5 -mr-1.5 rounded-lg hover:bg-muted text-muted-foreground"
          aria-label="Cerrar menú"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="px-4">
        <Button
          onClick={() => {
            onNueva();
            onCerrar?.();
          }}
          variant="outline"
          className="w-full rounded-2xl justify-start gap-2 bg-card/70"
        >
          <PlusIcon className="w-4 h-4" />
          Nueva evaluación
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto mt-3 min-h-0 px-4">
        {conversaciones.length === 0 && (
          <p className="text-[13px] text-muted-foreground px-1">
            Tus evaluaciones aparecerán aquí.
          </p>
        )}
        <ul className="space-y-0.5">
          {conversaciones.map((conversacion) => (
            <li key={conversacion.id} className="group relative">
              <button
                onClick={() => {
                  onSeleccionar(conversacion.id);
                  onCerrar?.();
                }}
                className={cn(
                  "w-full text-left rounded-xl px-3 py-2 text-[13px] flex items-center gap-2 transition-colors",
                  conversacion.id === conversacionActiva
                    ? "bg-accent text-accent-foreground font-medium"
                    : "hover:bg-muted text-foreground/80",
                )}
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate pr-5">{conversacion.titulo}</span>
              </button>
              <button
                onClick={() => onEliminar(conversacion.id)}
                title="Eliminar evaluación del historial"
                className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="px-4 pb-4 flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="text-xs text-muted-foreground truncate">{email ?? ""}</span>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Button variant="ghost" size="icon" title="Cerrar sesión" onClick={onLogout}>
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
