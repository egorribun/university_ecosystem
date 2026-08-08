import type { SsrAuthState } from "@/ssrAuth"

/**
 * @fileoverview Wave 128 SW1 — Strategy A bridge for AuthProvider.
 *
 * Reads the per-request SSR auth state injected by `src/server.ts` via
 * `globalThis.__ssrAuthGetter__` (W126 SW4 pattern). Server-only utility:
 * client-side `globalThis.__ssrAuthGetter__` is undefined (server.ts is
 * server-only per Vite environments build), so returns undefined and
 * AuthProvider falls back to the existing localStorage/Zustand path.
 *
 * NOT a React Hook — this is a plain function (no `use` prefix). The
 * value must be read at `useState` initFn time (or any non-render time)
 * — never inside the component body where the React Compiler would
 * mistake it for a hook.
 *
 * Defensive try/catch around the getter invocation: any unexpected
 * throw (extremely unlikely — getter just calls AsyncLocalStorage
 * `getStore()`) returns undefined so the AuthProvider initFn falls
 * back to the safe `null` user state.
 */
export function readSsrAuthHint(): SsrAuthState | undefined {
  try {
    return globalThis.__ssrAuthGetter__?.()
  } catch {
    return undefined
  }
}
