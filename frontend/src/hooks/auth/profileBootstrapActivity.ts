import type { QueryClient } from "@tanstack/react-query"

// A QueryClient can serve multiple providers. Each in-flight bootstrap owns one
// lease, so one provider cannot clear another provider's guard.
const active = new WeakMap<QueryClient, Set<symbol>>()

export const hasActiveProfileBootstrap = (client: QueryClient): boolean =>
  (active.get(client)?.size ?? 0) > 0

export const startProfileBootstrap = (client: QueryClient) => {
  const token = Symbol()
  let held = false
  let finished = false
  const resume = () => {
    if (finished || held) return
    const tokens = active.get(client) ?? new Set<symbol>()
    tokens.add(token)
    active.set(client, tokens)
    held = true
  }
  const suspend = () => {
    if (!held) return
    const tokens = active.get(client)
    tokens?.delete(token)
    if (tokens?.size === 0) active.delete(client)
    held = false
  }
  const finish = () => {
    finished = true
    suspend()
  }
  resume()
  return { resume, suspend, finish }
}
