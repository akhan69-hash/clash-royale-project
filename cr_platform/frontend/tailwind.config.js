/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Gold/crown-first palette -- primary interactive color moved from
        // Season 85's torii red to gold (the game's own crown/trophy color),
        // so the app reads as "Clash Royale" broadly rather than one red
        // season skin. `crimson` keeps that season red available as a
        // deliberate, secondary seasonal accent (Backdrop tint, badges)
        // instead of it being the default button/nav/active-state color.
        bg: { primary: '#120D0D', surface: '#1E1414', card: '#2B1C1C' },
        border: { DEFAULT: '#4A2E2E', strong: '#6B4242' },
        accent: { DEFAULT: '#D4AF37', hover: '#B8952C' },
        gold: { DEFAULT: '#D4AF37', hover: '#B8952C' },
        crimson: { DEFAULT: '#C23B3B', hover: '#A32E2E' },
        royale: { DEFAULT: '#4A6FE0', hover: '#3A57C2' },
        // Formalizes the cyan accent already used ad-hoc (arbitrary
        // `cyan-400`/`cyan-300` classes) all over the app for real-data
        // callouts (win rates, live stats) -- one named token instead of a
        // scattered literal, and the anchor color for the 2026-09-07
        // "futuristic 3D" pass's glow/glass effects.
        neon: { DEFAULT: '#22D3EE', hover: '#0EA5C4' },
        text: { primary: '#FFFFFF', secondary: '#C9B8A8', muted: '#8A7568' },
        rarity: {
          common: '#8B7355', rare: '#5B87C2',
          epic: '#9B59B6', legendary: '#F39C12', champion: '#E74C3C'
        },
        elixir: '#7B2FBE',
        success: '#4CAF50', danger: '#E53935',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Luckiest Guy"', 'cursive'],
        pro: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"', 'Inter', 'sans-serif'],
      },
      borderRadius: { xl: '12px', '2xl': '16px' },
      boxShadow: {
        card: '0 4px 20px rgba(0,0,0,0.4)',
        glow: '0 0 20px rgba(212,175,55,0.35)',
        'neon-glow': '0 0 24px rgba(34,211,238,0.4)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-glow': 'pulseGlow 2s infinite',
        'shimmer': 'shimmer 3.5s ease-in-out infinite',
        'drift-slow': 'driftSlow 14s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(16px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        pulseGlow: { '0%,100%': { boxShadow: '0 0 10px rgba(212,175,55,0.35)' }, '50%': { boxShadow: '0 0 25px rgba(74,111,224,0.5)' } },
        // Slow diagonal light sweep across a heading/badge -- the
        // "futuristic" holographic-sheen effect, subtle and infinite.
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        // Gentle depth-layer drift for background/glow orbs -- distinct
        // from Backdrop's existing per-card `float` keyframe (faster,
        // per-bubble); this is a slower whole-layer breathing motion.
        driftSlow: { '0%,100%': { transform: 'translate(0,0) scale(1)' }, '50%': { transform: 'translate(2%,-3%) scale(1.05)' } },
      }
    }
  },
  plugins: [],
}
