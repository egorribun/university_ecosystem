/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

export function isOnline(): boolean {
  if (typeof self.navigator === "undefined") return true;
  return self.navigator.onLine !== false;
}

export async function broadcastMessage(message: any): Promise<void> {
  const clients = await self.clients.matchAll({ type: "window" });
  for (const client of clients) {
    client.postMessage(message);
  }
}

export function sanitizeValue(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined) return value;
  if (depth > 5) return undefined;

  const type = typeof value;
  if (type === "string" || type === "number" || type === "boolean") return value;
  if (value instanceof Date) return value.toISOString();

  if (Array.isArray(value)) {
    return value
      .map((entry) => sanitizeValue(entry, depth + 1))
      .filter((entry) => entry !== undefined);
  }

  if (type === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      const sanitized = sanitizeValue(nested, depth + 1);
      if (sanitized !== undefined) result[key] = sanitized;
    }
    return result;
  }

  return undefined;
}
