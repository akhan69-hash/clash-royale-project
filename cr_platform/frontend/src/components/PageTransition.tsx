import { ReactNode } from 'react'
import { motion } from 'framer-motion'

/**
 * Wraps a route's page element so AnimatePresence (in App.tsx, keyed by
 * location.pathname) has something with a declared `exit` animation to
 * crossfade -- without this, page swaps happen instantly with no transition.
 */
export default function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.22, ease: 'easeInOut' }}
    >
      {children}
    </motion.div>
  )
}
