import { useRef, useState } from "react";
import { ArrowUpIcon, Paperclip } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAutoResizeTextarea } from "@/hooks/use-auto-resize-textarea";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  ocupado: boolean;
  hayEvaluacion: boolean;
  onEnviar: (texto: string) => void;
  onArchivo: (archivo: File) => void;
}

export default function ChatInput({ ocupado, hayEvaluacion, onEnviar, onArchivo }: ChatInputProps) {
  const [mensaje, setMensaje] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({ minHeight: 48, maxHeight: 160 });

  const puedeEnviar = mensaje.trim().length > 0 && !ocupado && hayEvaluacion;

  function enviar() {
    if (!puedeEnviar) return;
    onEnviar(mensaje.trim());
    setMensaje("");
    adjustHeight(true);
  }

  return (
    <div className="relative glass rounded-3xl">
      <Textarea
        ref={textareaRef}
        value={mensaje}
        disabled={ocupado}
        onChange={(e) => {
          setMensaje(e.target.value);
          adjustHeight();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            enviar();
          }
        }}
        placeholder={
          ocupado
            ? "El panel está trabajando…"
            : hayEvaluacion
              ? "Pregunta sobre el informe: «¿por qué el ítem 4.2 salió parcial?», «¿qué evidencia usó el panel?»…"
              : "Las preguntas se habilitan cuando exista una evaluación."
        }
        className={cn(
          "w-full px-5 py-3.5 resize-none border-none rounded-3xl",
          "bg-transparent text-[15px]",
          "focus-visible:ring-0 focus-visible:ring-offset-0",
          "placeholder:text-muted-foreground min-h-[48px]",
        )}
        style={{ overflow: "hidden" }}
      />

      <div className="flex items-center justify-between px-3 pb-3">
        <div className="flex items-center gap-1.5">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onArchivo(f);
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            size="icon"
            title="Subir otro proyecto (PDF o DOCX)"
            className="rounded-full text-muted-foreground hover:text-foreground"
            onClick={() => fileRef.current?.click()}
            disabled={ocupado}
          >
            <Paperclip className="w-4 h-4" />
          </Button>
          <span className="text-[12px] text-muted-foreground hidden sm:block">
            El chat responde solo sobre el informe; este sistema no mejora textos.
          </span>
        </div>

        <Button
          size="icon"
          disabled={!puedeEnviar}
          onClick={enviar}
          className="rounded-full shadow-md shadow-primary/25"
        >
          <ArrowUpIcon className="w-4 h-4" />
          <span className="sr-only">Enviar</span>
        </Button>
      </div>
    </div>
  );
}
