/** Turns a raw fetch/axios error (previously shown to users verbatim as
 * e.g. "Error: Request failed with status code 404") into plain language.
 * User feedback (2026-08-20): "Rather than showing error 404 why not say
 * user not found try again or something simple." Player/Coach lookups are
 * the only place raw errors surfaced today, so this is scoped to that --
 * a generic "not found" reads oddly for anything else this app might
 * someday show an error for. */
export function friendlyPlayerError(error: unknown): string {
  const status = (error as any)?.response?.status
  if (status === 404) return "We couldn't find a player with that tag."
  if (status === 429) return "Too many lookups right now -- give it a moment and try again."
  if (status != null && status >= 500) return "Something went wrong on our end. Try again in a bit."
  return "Couldn't load that player right now. Try again."
}
