-- ECM: esquema de Supabase para acceso, historial de chats y calificaciones.
--
-- Cómo usar:
--   1. Crea un proyecto NUEVO en https://supabase.com (no reutilizar el de MentorIA).
--   2. SQL Editor → pega este archivo completo → Run.
--   3. Authentication → Users → Add user (así se crean los usuarios; la app
--      no tiene registro, solo inicio de sesión).
--   4. Project Settings → API: copia Project URL y anon public key a los .env
--      (SUPABASE_URL / SUPABASE_ANON_KEY en la raíz, y VITE_SUPABASE_URL /
--      VITE_SUPABASE_ANON_KEY en web/.env).
--
-- RLS: cada usuario solo ve y modifica sus propias filas.

create table if not exists public.conversaciones (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  titulo text not null,
  project_id text,
  proyecto jsonb,
  creada_en timestamptz not null default now()
);

create table if not exists public.mensajes (
  id uuid primary key default gen_random_uuid(),
  conversacion_id uuid not null references public.conversaciones (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  rol text not null check (rol in ('user', 'assistant')),
  tipo text not null default 'texto',
  contenido text,
  metadata jsonb,
  creado_en timestamptz not null default now()
);

create table if not exists public.evaluaciones (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  conversacion_id uuid references public.conversaciones (id) on delete set null,
  project_id text,
  rubric_id text,
  mode text,
  total numeric,
  nivel text,
  nota_vigesimal integer,
  resultado jsonb,
  creado_en timestamptz not null default now()
);

create index if not exists mensajes_conversacion_idx
  on public.mensajes (conversacion_id, creado_en);
create index if not exists conversaciones_usuario_idx
  on public.conversaciones (user_id, creada_en desc);

alter table public.conversaciones enable row level security;
alter table public.mensajes enable row level security;
alter table public.evaluaciones enable row level security;

drop policy if exists "conversaciones propias" on public.conversaciones;
create policy "conversaciones propias" on public.conversaciones
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "mensajes propios" on public.mensajes;
create policy "mensajes propios" on public.mensajes
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "evaluaciones propias" on public.evaluaciones;
create policy "evaluaciones propias" on public.evaluaciones
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
