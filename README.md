# ECM — Evaluador de Calidad Metodológica

Instrumento de medición para tesis de pregrado: evalúa de forma automática la
calidad metodológica de proyectos de tesis de Ingeniería de la UPAO aplicando
una rúbrica, mediante un panel de 3 jueces LLM orquestado con LangGraph.

No es un asistente de mentoría: **no mejora textos, no conversa libremente**.
Su única función es evaluar documentos y reportar puntajes, evidencias y
métricas. Los resultados se validan contra calificaciones de jurados humanos,
por lo que el determinismo, la trazabilidad y la exportación de datos son
requisitos de primer orden.

## Cómo funciona

1. Se sube un proyecto (PDF o DOCX). El sistema lo **anonimiza** (doble ciego:
   nombres, DNI, correos, asesor, ORCID) y lo **segmenta** por las secciones de
   la rúbrica (heurísticas de encabezados; respaldo LLM solo si fallan). El
   mapeo de anonimización se guarda localmente y nunca viaja al LLM.
2. Tres **jueces LLM** (temperature 0, top_p 1, seed fija) califican cada
   sección por lotes: una llamada por par juez-sección que devuelve TODOS los
   ítems en JSON estricto, con evidencia textual (≤ 25 palabras) y observación
   diagnóstica (≤ 30 palabras). Roles de enfoque: rigor metodológico,
   coherencia y trazabilidad, forma académica.
3. Un **agregador determinista** consolida por mediana ordinal, marca
   `discrepancia` cuando el rango entre jueces es 2, calcula subtotales, total
   y nivel de calidad, y sintetiza la observación final sin inventar contenido.
4. Se reportan además **dimensiones transversales** (coherencia interna,
   formalidad, claridad; escala 1 a 5 por mediana del panel) y **métricas
   determinísticas** de texto (Fernández-Huerta, Szigriszt-Pazos, TTR, MTLD,
   citas APA vs referencias, completitud estructural), que nunca alteran los
   puntajes de rúbrica.

## Requisitos (Windows)

- Python 3.11 o superior (`py -3.11`)
- Node.js 18 o superior (para el frontend)
- Una clave de OpenAI para evaluar (los tests no la necesitan)

## Instalación

```powershell
# Backend: crea .venv e instala dependencias
.\scripts\dev.ps1 setup

# Frontend
cd web
npm install
cd ..

# Variables de entorno
Copy-Item .env.example .env   # y completa OPENAI_API_KEY
```

## Ejecución

```powershell
.\scripts\dev.ps1 rubrics   # regenera los JSON de rúbricas desde docs/
.\scripts\dev.ps1 api       # FastAPI en http://localhost:8000
.\scripts\dev.ps1 web       # frontend en http://localhost:5173
```

Abre http://localhost:5173: sube el proyecto, revisa el reporte de indexación,
elige rúbrica y modo (por defecto `especifica_v1` + `completo`) y evalúa. Desde
la interfaz puedes exportar JSON/CSV por proyecto, descargar el consolidado y
preguntar sobre el informe (el chat responde SOLO sobre el informe generado).

## Rúbricas y modos

- `especifica_v1`: rúbrica de calidad metodológica, 15 secciones, 100 puntos,
  3 niveles por ítem con el valor de "parcial" literal de la tabla fuente
  (`docs/rubrica_especifica.md`).
- `ficha_upao_v1`: ficha institucional, 33 ítems en 7 bloques, escala 0 a 3
  (Excelente 3, Bueno 2, Regular 1, Insuficiente 0), con conversión oficial a
  nota vigesimal (`docs/ficha_upao.md`). Es el perfil del modo concordancia:
  produce calificaciones comparables ítem a ítem con las fichas de los jurados.
  Con `incluir_administrativos: false` se excluyen los ítems 28 a 31 y se
  reporta el total crudo sobre 87 más el normalizado a escala 100 (la nota
  vigesimal solo aparece con la ficha completa).
- Modo `completo`: las 15 secciones cuentan; una ausente puntúa 0.
- Modo `progresivo` (uso semanal longitudinal): solo puntúan las secciones de
  las semanas activas (`backend/rubrics/config_semanas.json`, editable) y el
  total se reporta crudo y normalizado sobre el máximo activo.

## CLIs (ejecutar desde `backend\`)

```powershell
..\.venv\Scripts\python.exe -m cli.index_report ruta\proyecto.pdf     # inspección sin evaluar
..\.venv\Scripts\python.exe -m cli.batch_eval carpeta\con\pdfs        # lote → CSV consolidado
..\.venv\Scripts\python.exe -m cli.ingest_library libro.pdf           # biblioteca RAG opcional
..\.venv\Scripts\python.exe -m cli.validate --jurados ..\gold\jurados.csv
..\.venv\Scripts\python.exe -m cli.retest carpeta\con\pdfs --k 3      # estabilidad test-retest
```

- `batch_eval` usa el nombre de archivo como `project_id`: usa los mismos
  nombres en `gold/jurados.csv` (columnas: `proyecto_id, jurado_id, item_id,
  puntaje` con enteros 0 a 3).
- `validate` genera `data/validation/reporte.md` con QWK humano-humano, QWK
  sistema-humano (ítems y totales), acuerdo exacto/adyacente, MAE, Pearson,
  Spearman, ICC(2,1), intervalos bootstrap al 95 % e interpretación de Landis
  y Koch, además del acuerdo interno del panel.

## Tests

```powershell
.\scripts\dev.ps1 test
```

Los tests NUNCA llaman a la API de OpenAI: el panel de jueces se inyecta con
dobles deterministas. Cubren el parser de rúbricas, el anonimizador, el
segmentador, el agregador (mediana y discrepancias), la normalización del modo
progresivo, la API completa, los exportadores, el QWK con fixtures de valor
conocido, la validación psicométrica y el test-retest.

## Determinismo y trazabilidad

- `EVAL_TEMPERATURE=0`, top_p 1 y `EVAL_SEED=42` (si el proveedor lo soporta).
- Cada resultado registra versión de rúbrica, modo, modelos por juez, hash
  SHA-256 de los prompts, timestamp, tokens y costo estimado.
- Reintentos con backoff exponencial; si un juez falla de forma persistente en
  una sección se registra el hueco y se agrega con los jueces disponibles
  (`panel_incompleto = true`).
- Por defecto los tres jueces usan `gpt-4o-mini`. Para el ciclo longitudinal se
  recomienda **diversificar las familias de modelos del panel** (por ejemplo
  OpenAI, Anthropic y Google) para mitigar el sesgo de auto-preferencia
  (Panickssery, Bowman y Feng, 2024): basta cambiar `JUDGE1_MODEL`,
  `JUDGE2_MODEL` y `JUDGE3_MODEL` en el `.env`.
- Trazado opcional con LangSmith: `LANGSMITH_API_KEY` y
  `LANGCHAIN_TRACING_V2=true`.

## Biblioteca metodológica (RAG opcional)

`python -m cli.ingest_library` indexa libros de metodología (por ejemplo
Hernández-Sampieri 2018) en ChromaDB con `intfloat/multilingual-e5-small`. En
la evaluación, cada juez puede recibir 1 o 2 pasajes normativos por sección
como contexto de criterio: el pasaje jamás modifica puntajes, solo enriquece
la justificación. Sin libros ingresados, el sistema funciona igual.

## Estructura

```
backend/
  app/        FastAPI, persistencia (JSON + SQLite), exportadores, chat acotado
  graph/      nodos LangGraph: segmentador, jueces, agregador
  rubrics/    JSON versionados de rúbricas + configuración de semanas
  prompts/    prompts versionados en español (hash registrado por evaluación)
  metrics/    métricas determinísticas y psicométricas
  anonymizer/ anonimización doble ciego
  ingest/     extracción PDF/DOCX
  library/    biblioteca RAG opcional
  cli/        batch_eval, validate, retest, ingest_library, index_report
  tests/      pytest (sin llamadas a OpenAI)
web/          frontend React + Vite (una vista tipo chat + informe imprimible)
docs/         rúbricas fuente y justificación metodológica
data/         resultados, chroma y validación (fuera del repo)
gold/         calificaciones de jurados humanos para la validación
```

## Acceso e historial (Supabase opcional)

Con Supabase configurado, la app exige inicio de sesión y guarda en la nube el
historial de chats y cada calificación:

1. Crea un proyecto NUEVO en supabase.com (no reutilizar el de otros sistemas).
2. SQL Editor → ejecuta `supabase/schema.sql` (tablas `conversaciones`,
   `mensajes` y `evaluaciones` con RLS por usuario).
3. Authentication → Users → Add user: así se crean las cuentas. La app NO
   tiene registro, solo inicio de sesión.
4. Copia Project URL y anon key a los dos `.env`:
   - raíz: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (el backend valida el token
     Bearer de cada petición contra Supabase Auth).
   - `web/.env`: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (pantalla de
     login, sidebar con historial, guardado de mensajes y evaluaciones).

El historial guarda cada conversación (reporte de indexación, calificaciones
con su JSON completo y las preguntas sobre el informe); al reabrirla se
restauran las tarjetas y se puede seguir preguntando o reevaluar. Sin Supabase
configurado, la app funciona en modo local: sin login (o con la clave simple
`APP_ACCESS_KEY` si se define) y sin historial en la nube; la persistencia
local en `data/` existe siempre.

## Fuera de alcance (por diseño)

Sin mejora ni reescritura de textos, sin LoRA, sin MCP, sin subida de rúbricas
desde la interfaz y sin registro de usuarios en la app (las cuentas se
administran desde Supabase).
