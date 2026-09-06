import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock, Loader2 } from 'lucide-react'
import { supabase } from '../utils/supabaseClient'
import Backdrop from '../components/Backdrop'

/**
 * Landing page for the real password-reset email link (2026-09-02) --
 * AuthPage's "Forgot password?" sends the user here via
 * resetPasswordForEmail's redirectTo. Supabase's client parses the recovery
 * token out of the URL itself and fires a real PASSWORD_RECOVERY auth
 * event; this page just needs to be ready to accept a new password once
 * that's happened, not parse anything from the URL by hand.
 */
export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [ready, setReady] = useState(false)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'PASSWORD_RECOVERY') setReady(true)
    })
    // If the recovery token was already processed by the time this mounts
    // (real timing race with Supabase's own URL-fragment parsing), a
    // session existing at all on this specific route is enough to proceed.
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) setReady(true)
    })
    return () => subscription.unsubscribe()
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { error: err } = await supabase.auth.updateUser({ password })
      if (err) throw err
      setDone(true)
      setTimeout(() => navigate('/'), 2000)
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong -- try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative z-10 max-w-md mx-auto px-4 py-6">
      <Backdrop density={6} />
      <h1 className="text-2xl font-bold text-accent mb-4">🔑 Reset Password</h1>

      {done ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 text-sm text-text-secondary">
          ✅ Password updated -- taking you home...
        </div>
      ) : !ready ? (
        <div className="bg-bg-surface border border-border rounded-xl p-4 text-sm text-text-secondary">
          Open this page from the link in your password reset email.
        </div>
      ) : (
        <form onSubmit={submit} className="bg-bg-surface border border-border rounded-xl p-4 space-y-3">
          <div className="relative">
            <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)}
              placeholder="New password" autoComplete="new-password"
              className="w-full bg-bg-card border border-border rounded-xl pl-9 pr-4 py-2.5 text-text-primary text-sm
                         placeholder:text-text-muted focus:outline-none focus:border-accent" />
          </div>
          {error && <div className="text-xs text-danger bg-danger/10 rounded-lg p-2.5">{error}</div>}
          <button type="submit" disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50
                       text-bg-primary font-bold px-5 py-2.5 rounded-xl text-sm">
            {loading && <Loader2 size={15} className="animate-spin" />}
            Update Password
          </button>
        </form>
      )}
    </div>
  )
}
