import { useCallback, useRef } from "react";

interface Opciones {
  minHeight: number;
  maxHeight: number;
}

export function useAutoResizeTextarea({ minHeight, maxHeight }: Opciones) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset = false) => {
      const nodo = textareaRef.current;
      if (!nodo) return;
      if (reset) {
        nodo.style.height = `${minHeight}px`;
        return;
      }
      nodo.style.height = `${minHeight}px`;
      nodo.style.height = `${Math.min(nodo.scrollHeight, maxHeight)}px`;
    },
    [minHeight, maxHeight],
  );

  return { textareaRef, adjustHeight };
}
