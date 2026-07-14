// Cliente de Supabase (opcional). Con VITE_SUPABASE_URL/ANON_KEY configuradas
// la app exige inicio de sesión (los usuarios se crean desde el panel de
// Supabase) y guarda historial de chats y calificaciones. Sin configurar,
// supabase = null y la app funciona en modo local como siempre.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabaseHabilitado = Boolean(url && anonKey);

export const supabase: SupabaseClient | null = supabaseHabilitado
  ? createClient(url!, anonKey!)
  : null;
