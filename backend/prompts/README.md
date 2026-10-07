# Prompts del ECM

Prompts versionados en español, escritos desde cero para este sistema (estilo
G-Eval: tarea, criterios literales, escala operativa, pasos de evaluación y
salida JSON estricta). El hash SHA-256 del conjunto se registra en cada
resultado para trazabilidad (`graph/prompts.py`).

- `juez_base.md` — plantilla por sección compartida por los 3 jueces: califica
  TODOS los ítems de la sección en una sola llamada, con evidencia (cita ≤ 25
  palabras) y observación diagnóstica (≤ 30 palabras), y prohibiciones
  explícitas (no reescribir, no usar conocimiento externo, no cambiar pesos).
- `juez_roles.md` — roles de enfoque del panel (juez 1 rigor metodológico,
  juez 2 coherencia y trazabilidad, juez 3 forma académica). El rol orienta la
  atención; no cambia escala ni criterios.
- `transversales.md` — dimensiones transversales 1-5 (formalidad y registro,
  claridad y tono) con justificación breve. La coherencia interna se retiró:
  la reemplaza `coherencia_global.md`.
- `argumentacion_toulmin.md` — índice argumentativo (Toulmin, v1.1): función de
  cada oración ya numerada por el sistema, con reglas de inclusión y exclusión.
- `coherencia_global.md` — coherencia global (v1.3): lista de contradicciones
  entre dos partes del proyecto, con cita de cada una; la nota la calcula una
  regla fija.
- `segmentador.md` — respaldo LLM del segmentador estructural, solo cuando la
  heurística de encabezados no alcanza el umbral.
- `chat_informe.md` — (Fase 6) chat post-evaluación acotado al JSON del
  informe y la rúbrica, con las mismas prohibiciones del juez.

La observación final por ítem NO usa LLM: el agregador la sintetiza de forma
determinista tomando la observación del juez cuyo nivel coincide con la
mediana (sin inventar contenido nuevo).
