export function registerSeoReadinessInstance(
  current: ReadonlySet<string>,
  instanceId: string
): ReadonlySet<string> {
  if (current.has(instanceId)) return current
  const next = new Set(current)
  next.add(instanceId)
  return next
}

export function unregisterSeoReadinessInstance(
  current: ReadonlySet<string>,
  instanceId: string
): ReadonlySet<string> {
  if (!current.has(instanceId)) return current
  const next = new Set(current)
  next.delete(instanceId)
  return next
}
