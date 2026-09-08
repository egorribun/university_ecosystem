/**
 * Test-only console integrity guard.
 *
 * React (and the browser platform) report actionable diagnostics through
 * console.error/console.warn.  A global substring allow-list makes those
 * diagnostics invisible and turns a passing test into false evidence.  This
 * helper keeps the original methods observable, fails on every unexpected
 * call, and provides a narrowly-scoped escape hatch for a test that is
 * intentionally exercising a diagnostic.
 */

export type StrictConsoleMethod = "error" | "warn"
export type StrictConsoleMatcher = string | RegExp | ((args: readonly unknown[]) => boolean)

export type StrictConsoleDiagnostic = {
  method: StrictConsoleMethod
  args: readonly unknown[]
  stack: string | undefined
}

type Expectation = {
  matcher: StrictConsoleMatcher
  expectedCount: number
  actualCount: number
}

type StrictConsoleState = {
  installed: boolean
  originals: Record<StrictConsoleMethod, (...args: unknown[]) => void>
  expectations: Record<StrictConsoleMethod, Expectation[]>
  diagnostics: StrictConsoleDiagnostic[]
}

const STATE_KEY = "__universityEcosystemStrictConsoleState__"

type GlobalWithStrictConsoleState = typeof globalThis & {
  [STATE_KEY]?: StrictConsoleState
}

function getState(): StrictConsoleState {
  const globalWithState = globalThis as GlobalWithStrictConsoleState
  const existing = globalWithState[STATE_KEY]
  if (existing) return existing

  const state: StrictConsoleState = {
    installed: false,
    originals: {
      error: console.error.bind(console),
      warn: console.warn.bind(console),
    },
    expectations: { error: [], warn: [] },
    diagnostics: [],
  }
  globalWithState[STATE_KEY] = state
  return state
}

function matches(matcher: StrictConsoleMatcher, args: readonly unknown[]): boolean {
  if (typeof matcher === "function") return matcher(args)
  const first = String(args[0] ?? "")
  if (typeof matcher === "string") return first.includes(matcher)
  // Reset a global/sticky matcher for each call so its mutable `lastIndex`
  // cannot leak between diagnostics and accidentally alternate match results.
  const previousLastIndex = matcher.lastIndex
  matcher.lastIndex = 0
  const matched = matcher.test(first)
  matcher.lastIndex = previousLastIndex
  return matched
}

function formatDiagnostic(args: readonly unknown[]): string {
  const first = args[0]
  if (typeof first === "string") return first
  try {
    return JSON.stringify(first)
  } catch {
    return String(first)
  }
}

/** Install strict wrappers once per Vitest worker. */
export function installStrictConsole(): void {
  const state = getState()
  if (state.installed) return

  const consoleTarget = globalThis.console
  for (const method of ["error", "warn"] as const) {
    const original = state.originals[method]
    consoleTarget[method] = (...args: unknown[]) => {
      const diagnostic: StrictConsoleDiagnostic = {
        method,
        args: [...args],
        stack: new Error().stack,
      }
      state.diagnostics.push(diagnostic)

      const expectation = state.expectations[method].find((candidate) => {
        return candidate.actualCount < candidate.expectedCount && matches(candidate.matcher, args)
      })

      if (expectation) {
        expectation.actualCount += 1
        return
      }

      original(...args)
      throw new Error(
        `Unexpected console.${method} call (${formatDiagnostic(args)})\n${diagnostic.stack ?? ""}`
      )
    }
  }
  state.installed = true
}

/** Return an immutable snapshot useful for strict-console regression tests. */
export function getStrictConsoleDiagnostics(): readonly StrictConsoleDiagnostic[] {
  return getState().diagnostics.map((diagnostic) => ({
    ...diagnostic,
    args: [...diagnostic.args],
  }))
}

/**
 * Execute a callback while allowing exactly `count` matching diagnostics.
 * Any other diagnostic still fails immediately.  The expectation is removed
 * even when the callback rejects, so one test cannot leak an allow-list into
 * a later test.
 */
export async function withExpectedConsole<T>(
  method: StrictConsoleMethod,
  matcher: StrictConsoleMatcher,
  callback: () => T | Promise<T>,
  count = 1
): Promise<T> {
  if (!Number.isInteger(count) || count < 1) {
    throw new RangeError("withExpectedConsole count must be a positive integer")
  }

  const state = getState()
  const expectation: Expectation = { matcher, expectedCount: count, actualCount: 0 }
  state.expectations[method].push(expectation)
  let callbackError: unknown
  let callbackThrew = false
  let result!: T
  try {
    result = await callback()
  } catch (error) {
    callbackThrew = true
    callbackError = error
  } finally {
    const expectations = state.expectations[method]
    const index = expectations.indexOf(expectation)
    if (index >= 0) expectations.splice(index, 1)
  }

  if (callbackThrew) throw callbackError
  if (expectation.actualCount !== expectation.expectedCount) {
    throw new Error(
      `Expected ${expectation.expectedCount} console.${method} call(s), received ${expectation.actualCount}`
    )
  }
  return result
}

/** Convenience alias for warning-specific expectations. */
export function expectConsoleWarning<T>(
  matcher: StrictConsoleMatcher,
  callback: () => T | Promise<T>,
  count = 1
): Promise<T> {
  return withExpectedConsole("warn", matcher, callback, count)
}

/** Clear diagnostics between tests without restoring the strict wrappers. */
export function resetStrictConsoleDiagnostics(): void {
  getState().diagnostics.length = 0
}
