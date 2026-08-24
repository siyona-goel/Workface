import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/** Returns null when the public keys are missing so fixture replay still works. */
export function tryGetSupabase(): SupabaseClient | null {
  if (!url || !anon) return null;
  return createClient(url, anon);
}

export function getSupabase() {
  const client = tryGetSupabase();
  if (!client) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY",
    );
  }
  return client;
}

export const AGENT_CHANNEL = "workface-agent";
export const AGENT_STEP_EVENT = "step";
