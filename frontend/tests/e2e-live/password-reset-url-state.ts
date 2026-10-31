export interface PasswordResetUrlState {
  resetRoute: boolean
  tokenQueryAbsent: boolean
  tokenFragmentAbsent: boolean
  tokenUrlAbsent: boolean
}

export type ResetUrlPhase = "history" | "reopen"
type ReadPasswordResetUrlState = () => Promise<PasswordResetUrlState>

const emittedPhases = new Set<string>()
const STATE_KEYS = ["resetRoute", "tokenQueryAbsent", "tokenFragmentAbsent", "tokenUrlAbsent"]

/** Self-contained for page.evaluate; only fixed booleans leave the browser. */
export function readPasswordResetUrlState(candidate: string): PasswordResetUrlState {
  const current = new URL(window.location.href)
  return {
    resetRoute: current.pathname === "/reset-password",
    tokenQueryAbsent: !current.searchParams.has("token"),
    tokenFragmentAbsent: !current.hash.includes(candidate),
    tokenUrlAbsent: !window.location.href.includes(candidate),
  }
}

function reportPasswordResetUrlState(
  project: string,
  phase: ResetUrlPhase,
  snapshot: PasswordResetUrlState
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (phase !== "history" && phase !== "reopen") ||
    snapshot === null ||
    typeof snapshot !== "object" ||
    Reflect.ownKeys(snapshot).length !== STATE_KEYS.length ||
    !STATE_KEYS.every((key) => Object.hasOwn(snapshot, key))
  ) {
    return
  }
  const { resetRoute, tokenQueryAbsent, tokenFragmentAbsent, tokenUrlAbsent } = snapshot
  if (
    typeof resetRoute !== "boolean" ||
    typeof tokenQueryAbsent !== "boolean" ||
    typeof tokenFragmentAbsent !== "boolean" ||
    typeof tokenUrlAbsent !== "boolean"
  ) {
    return
  }
  const key = project + "/" + phase
  if (emittedPhases.has(key) || emittedPhases.size >= 4) return
  emittedPhases.add(key)
  const record =
    `UE_LIVE_RESET_URL_V1 project=${project} phase=${phase} ` +
    `reset_route=${resetRoute} token_query_absent=${tokenQueryAbsent} ` +
    `token_fragment_absent=${tokenFragmentAbsent} token_url_absent=${tokenUrlAbsent}\n`
  process.stdout.write(record)
}

/** Observe the existing assertion without changing its timing or rejection. */
export async function withPasswordResetUrlDiagnostic(
  project: string,
  phase: ResetUrlPhase,
  read: ReadPasswordResetUrlState,
  assertion: (observe: ReadPasswordResetUrlState) => Promise<void>
): Promise<void> {
  let snapshot: PasswordResetUrlState | undefined
  try {
    await assertion(async () => {
      snapshot = undefined
      const observed = await read()
      snapshot = observed
      return observed
    })
  } catch (error) {
    try {
      if (snapshot !== undefined) reportPasswordResetUrlState(project, phase, snapshot)
    } catch {
      // A diagnostic must never replace the original acceptance failure.
    }
    throw error
  }
}
