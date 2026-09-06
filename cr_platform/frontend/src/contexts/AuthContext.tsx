import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../utils/supabaseClient'

/**
 * Real user account state (2026-09-02), mounted once at the App root --
 * same "survives client-side navigation" placement as CardDetailProvider.
 * Supabase's own client already persists the session to its own
 * localStorage key and silently refreshes the access token before it
 * expires; this context just makes that reactive across the React tree via
 * supabase.auth.onAuthStateChange(), instead of every component re-deriving
 * it from supabase.auth.getSession() (a promise, not synchronous state).
 */
interface AuthState {
  user: User | null
  session: Session | null
  loading: boolean
}

const AuthContext = createContext<AuthState>({ user: null, session: null, loading: true })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, session: null, loading: true })

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setState({ session, user: session?.user ?? null, loading: false })
    })

    // Fires on sign-in, sign-out, token refresh, AND password-recovery
    // (the PASSWORD_RECOVERY event ResetPasswordPage.tsx listens for
    // separately) -- one subscription keeps this context correct through
    // all of them without polling.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setState({ session, user: session?.user ?? null, loading: false })
    })

    return () => subscription.unsubscribe()
  }, [])

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
