/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string
  readonly VITE_SUPABASE_ANON_KEY: string
  /** Absolute backend URL (e.g. https://royaleiq.com/api) -- only needed
   * when the frontend is deployed separately from the backend (Vercel).
   * Unset in the production Docker image, which serves both from one
   * origin and uses the default relative '/api' instead. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
