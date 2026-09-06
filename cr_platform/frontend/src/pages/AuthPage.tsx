import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, Lock, Loader2 } from 'lucide-react'
import { supabase } from '../utils/supabaseClient'
import { useAuth } from '../contexts/AuthContext'
import Backdrop from '../components/Backdrop'

type Mode = 'signin' | 'signup'

/**
 * Real sign-up / log-in, one page with a mode toggle (2026-09-02) -- same
 * tab-toggle convention used elsewhere (Synergy's Card Lookup/Deck Network,
 * Rankings' Players/Tournaments) rather than two separate routes for what's
 * fundamentally one flow. Talks directly to Supabase's Auth API via
 * utils/supabaseClient.ts -- no backend round-trip, no custom password/JWT
 * handling in this codebase at all.
 */
export default function AuthPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checkEmail, setCheckEmail] = useState(false)
  const [resetSent, setResetSent] = useState(false)

  if (user) {
    return (
      <div className="relative z-10 max-w-md mx-auto px-4 py-6">
        <Backdrop density={6} />
        <div className="bg-bg-surface border border-border rounded-xl p-6 text-center">
          <p className="text-text-primary font-semibold mb-1">You're signed in</p>
          <p className="text-text-secondary text-sm mb-4">{user.email}</p>
          <button onClick={() => navigate('/')}
            className="bg-accent hover:bg-accent-hover text-bg-primary font-bold px-5 py-2 rounded-xl text-sm">
            Go home
          </button>
        </div>
      </div>
    )
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'signin') {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password })
        if (err) throw err
        navigate('/')
      } else {
        const { error: err } = await supabase.auth.signUp({ email, password })
        if (err) throw err
        // Real Supabase default: a confirmation email is sent before the
        // account can actually sign in -- an honest "check your email"
        // state instead of assuming immediate login worked.
        setCheckEmail(true)
      }
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong -- try again.')
    } finally {
      setLoading(false)
    }
  }

  const forgotPassword = async () => {
    if (!email) { setError('Enter your email above first.'); return }
    setError(null)
    setLoading(true)
    try {
      const { error: err } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      })
      if (err) throw err
      setResetSent(true)
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong -- try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative z-10 max-w-md mx-auto px-4 py-6">
      <Backdrop density={6} />
      <h1 className="text-2xl font-bold text-accent mb-1">👤 Account</h1>
      <p className="text-text-secondary text-sm mb-4">
        {mode === 'signin' ? 'Sign in to your Royale IQ account.' : 'Create a Royale IQ account.'}
      </p>

      <div className="flex gap-1 mb-5">
        {([['signin', 'Sign In'], ['signup', 'Create Account']] as const).map(([m, label]) => (
          <button key={m} onClick={() => { setMode(m); setError(null); setCheckEmail(false); setResetSent(false) }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${mode === m ? 'bg-accent text-bg-primary' : 'bg-bg-card text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      {checkEmail ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 text-sm text-text-secondary">
          📬 Check <strong className="text-text-primary">{email}</strong> for a confirmation link to finish
          creating your account.
        </div>
      ) : resetSent ? (
        <div className="bg-bg-surface border border-cyan-400/30 rounded-xl p-4 text-sm text-text-secondary">
          📬 Check <strong className="text-text-primary">{email}</strong> for a password reset link.
        </div>
      ) : (
        <form onSubmit={submit} className="bg-bg-surface border border-border rounded-xl p-4 space-y-3">
          <div className="relative">
            <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
              placeholder="Email" autoComplete="email"
              className="w-full bg-bg-card border border-border rounded-xl pl-9 pr-4 py-2.5 text-text-primary text-sm
                         placeholder:text-text-muted focus:outline-none focus:border-accent" />
          </div>
          <div className="relative">
            <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Password" autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              className="w-full bg-bg-card border border-border rounded-xl pl-9 pr-4 py-2.5 text-text-primary text-sm
                         placeholder:text-text-muted focus:outline-none focus:border-accent" />
          </div>

          {error && (
            <div className="text-xs text-danger bg-danger/10 rounded-lg p-2.5">{error}</div>
          )}

          <button type="submit" disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50
                       text-bg-primary font-bold px-5 py-2.5 rounded-xl text-sm">
            {loading && <Loader2 size={15} className="animate-spin" />}
            {mode === 'signin' ? 'Sign In' : 'Create Account'}
          </button>

          {mode === 'signin' && (
            <button type="button" onClick={forgotPassword} disabled={loading}
              className="w-full text-center text-xs text-text-muted hover:text-text-secondary transition-colors">
              Forgot password?
            </button>
          )}
        </form>
      )}

      <p className="text-center text-text-muted text-xs mt-4">
        <Link to="/" className="hover:text-text-secondary transition-colors">← Back to Royale IQ</Link>
      </p>
    </div>
  )
}
