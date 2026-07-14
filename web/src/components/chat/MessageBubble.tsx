import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { ClipboardCheck } from "lucide-react";

interface MessageBubbleProps {
  rol: "user" | "assistant";
  contenido?: string;
  children?: ReactNode;
  ancho?: boolean;
}

export default function MessageBubble({ rol, contenido, children, ancho = false }: MessageBubbleProps) {
  if (rol === "user") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[78%] rounded-3xl rounded-br-lg bg-primary text-primary-foreground px-5 py-3 text-[15px] leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {contenido}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-card shadow-sm border border-border grid place-items-center shrink-0">
        <ClipboardCheck className="w-5 h-5 text-primary" />
      </div>
      <div className={ancho ? "min-w-0 flex-1" : "max-w-[85%] glass rounded-3xl rounded-tl-lg px-5 py-4 text-[15px]"}>
        {contenido && (
          <div className="prose-informe">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{contenido}</ReactMarkdown>
          </div>
        )}
        {children}
      </div>
    </motion.div>
  );
}
