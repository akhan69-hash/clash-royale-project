import { createClient } from '@supabase/supabase-js'

/**
 * Real user accounts (2026-09-02) -- Supabase Auth, not a hand-rolled
 * password/JWT system (the backend has no password-hashing or JWT library
 * at all, and Supabase is already this project's Postgres provider). This
 * client talks DIRECTLY to Supabase's own Auth API from the browser --
 * sign-up/login/logout/password-reset never round-trip through our own
 * FastAPI backend, which is why there's no new /api/auth/* router.
 *
 * VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are baked in at BUILD time
 * (Vite inlines import.meta.env.VITE_* into the bundle) from
 * cr_platform/frontend/.env -- gitignored, same treatment the backend's own
 * .env already gets. The anon key is safe to ship in the built JS bundle by
 * design (Supabase's Row Level Security protects real data, not secrecy of
 * this key) -- unlike CR_API_KEY, this one is meant to be public.
 */
const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!url || !anonKey) {
  // Real, loud failure instead of a silent broken client -- easy to miss a
  // missing .env on a fresh clone/deploy otherwise, and every auth call
  // would fail with a confusing network error instead of this clear one.
  console.error('Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY -- see cr_platform/frontend/.env')
}

export const supabase = createClient(url ?? '', anonKey ?? '')
