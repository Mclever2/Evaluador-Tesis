# Sistema de diseño del ECM (extraído del frontend de MentorIA)

Fuente: `poc_langgraph_mentoria/web/` (solo frontend, según las reglas del proyecto).
Este documento es la referencia para replicar la identidad visual en el frontend nuevo
del Evaluador de Calidad Metodológica (ECM). Toda la lógica se escribe desde cero.

## Stack confirmado

- React 18 + Vite 5 + TypeScript 5.5
- Tailwind CSS 3.4 con `darkMode: "class"` y tokens HSL en variables CSS
- framer-motion (animaciones de entrada `opacity/y`), lucide-react (iconos)
- react-markdown + remark-gfm para render de informes
- react-router-dom 6
- class-variance-authority + clsx + tailwind-merge (`cn()`), @radix-ui/react-slot
- Alias `@` → `./src`; dev server con proxy `/api` → backend local
- Se EXCLUYE del ECM: @supabase/supabase-js y toda la persistencia de sesión/historial

## Paleta (variables CSS en HSL, `index.css`)

Tema claro (`:root`):

| Token | Valor | Uso |
| --- | --- | --- |
| `--background` | `240 14% 97%` | fondo general gris muy claro |
| `--foreground` | `240 6% 10%` | texto principal |
| `--card` | `0 0% 100%` | tarjetas |
| `--primary` | `211 100% 50%` | azul iOS `#007AFF`, botones y acentos |
| `--secondary` / `--muted` | `240 5% 93%` / `240 5% 94%` | fondos suaves |
| `--muted-foreground` | `240 4% 46%` | texto secundario |
| `--accent` | `211 100% 96%` (fg `211 100% 40%`) | selección activa |
| `--destructive` | `3 100% 59%` | rojo iOS |
| `--border` / `--input` | `240 6% 88%` | bordes hairline |
| `--ring` | `211 100% 50%` | focus |
| `--radius` | `1rem` | radios generosos (rounded-2xl/3xl por doquier) |

Tema oscuro (`.dark`): background `240 6% 7%`, card `240 4% 11%`, primary `211 100% 52%`,
secondary/muted `240 4% 16%`, border/input `240 4% 20%`, accent `211 70% 16%` (fg `211 100% 70%`).

Colores de estado (paleta iOS, hardcodeados en componentes):

- Verde `#34C759` → cumple / completado
- Naranja `#FF9500` → parcial / advertencia
- Rojo `destructive` → no cumple / ausente
- Índigo `#5856D6` y púrpura `#AF52DE` → orbes decorativos y gradiente
- Gradiente de marca: `from-[#007AFF] via-[#5856D6] to-[#AF52DE]` (`.text-gradient`)

## Tipografía

Stack de sistema: `-apple-system, BlinkMacSystemFont, SF Pro Display, SF Pro Text, Segoe UI,
Roboto, Inter, sans-serif`. Antialiased. Tamaños: 15px texto de chat, 13px filas y texto
secundario, 11–12px metadatos, `tabular-nums` para puntajes.

## Utilidades clave (replicar en `index.css`)

- `.glass`: `bg-white/80 backdrop-blur-md border-white/60 shadow suave`
  (dark: `bg-zinc-900/70 border-white/10`). Es la superficie principal de tarjetas,
  burbujas del asistente, input y paneles.
- `.text-gradient`: gradiente azul→índigo→púrpura con `bg-clip-text`.
- `.prose-informe`: estilos de markdown para informes (tablas GFM con scroll-x,
  blockquote con borde primary, código sobre `bg-muted`).
- Animaciones: `shimmer` (barra de carga degradada), `float-slow`, `orb-pulse`,
  `progreso-indeterminado` (barra 1/3 que se desliza).
- Scrollbar fino de 8px translúcido.

## Patrones de componentes a replicar

- **FondoLiquido**: 3 orbes estáticos con `blur(110–120px)` en primary/25, `#AF52DE`/20 y
  `#5856D6`/20, `-z-10`. Estáticos a propósito (rendimiento); prop `intenso` sube brillo
  mientras se ejecuta la evaluación.
- **MessageBubble**: usuario = `bg-primary text-primary-foreground rounded-3xl rounded-br-lg
  max-w-[78%]` alineado a la derecha; asistente = avatar circular (icono en `text-primary`
  sobre `bg-card` con borde) + burbuja `.glass rounded-3xl rounded-tl-lg max-w-[85%]` con
  `.prose-informe`. Botones de acción como chips `rounded-full h-8 text-xs` bajo un
  separador `border-t border-border/60`.
- **UploadZone**: tarjeta `.glass rounded-3xl px-8 py-10` con drag&drop, icono `FileUp`,
  ring primary al arrastrar, y en carga: `Loader2` girando + barra shimmer + texto de etapa.
- **ChatInput**: contenedor `.glass rounded-3xl` con textarea auto-resize (48–160px) sin
  borde, fila inferior con clip (adjuntar) + selector dropdown (patrón del menú de
  profundidad: panel `rounded-2xl` flotante con check en la opción activa — reutilizar para
  el selector de rúbrica y modo) y botón enviar `rounded-full` con sombra primary
  (o botón cuadrado de detener durante la ejecución).
- **ProgressTimeline**: lista de pasos con check verde en píldora `#34C759/15` para
  completados y `Loader2` girando para el activo; encabezado con icono `Bot`. Se muestra
  dentro de una burbuja `.glass` mientras corre el grafo.
- **Panel de resultados a pantalla completa** (patrón de RevisionCompletaPanel):
  `absolute inset-0 z-30 bg-background`, header sticky `bg-card/60 backdrop-blur-xl` con
  flecha de volver, título y el TOTAL a la derecha (grande, `tabular-nums`, coloreado por
  ratio: ≥0.8 verde, ≥0.5 naranja, resto rojo). Cuerpo `max-w-4xl` con secciones
  `.glass rounded-3xl p-5`.
- **Fila de ítem**: chip numerado `w-8 h-8 rounded-xl bg-muted` + criterio 13px + razón en
  `muted-foreground` + estado a la derecha (icono + etiqueta coloreada) y puntaje
  `x/max` en `tabular-nums`.
- **Estado vacío del chat**: título centrado grande ("¿Qué evaluamos hoy?" en el ECM),
  subtítulo muted, UploadZone + ChatInput apilados `max-w-2xl`, chips de acción rápida
  `rounded-full` con icono primary.
- **Sidebar** (`w-72`, `bg-white/55 backdrop-blur-xl border-r`): en el ECM se simplifica —
  sin historial de conversaciones ni recursos de usuario. Conservar: marca arriba,
  ThemeToggle y, si aplica, tarjeta de biblioteca metodológica (RAG) con conteo de
  fragmentos por libro.
- **ThemeToggle + `theme.ts`**: clase `dark` en `<html>`, persistencia en localStorage,
  fallback a `prefers-color-scheme`.
- **button.tsx / textarea.tsx**: primitivas estilo shadcn con CVA (variants: default,
  outline, ghost, secondary, destructive, link; sizes: default, sm, lg, icon).
- **Tarjeta de auth** (patrón de Auth.tsx, para la puerta de acceso opcional del ECM):
  `.glass rounded-3xl p-8 max-w-md` centrada con orbe de fondo, inputs `rounded-xl
  border-input bg-card` con focus ring, errores en `bg-destructive/10 rounded-xl`.

## Qué se elimina de la interfaz en el ECM

Selección de universidad, subida de rúbrica por el usuario, botones y flujos de mejora de
texto, historial de asesorías, selector de iteraciones/profundidad (se reemplaza por el
selector de rúbrica y modo), LoRA, MCP, recursos del usuario, Supabase/auth con cuentas,
heartbeat de uso. La landing se elimina: la app abre directo en la vista principal
(con puerta de clave simple solo si `APP_ACCESS_KEY` está configurada).

## Identidad del ECM

Nombre visible: **Evaluador de Calidad Metodológica**. Misma paleta y superficies glass.
Todo el texto de la interfaz en español. Vista principal tipo chat + vista de detalle de
resultados imprimible (el patrón de panel a pantalla completa ya es la base adecuada).
