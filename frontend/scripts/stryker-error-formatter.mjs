import { types } from "node:util"

function ownString(value, key) {
  // Serialized records contain data properties. Never invoke accessor getters
  // or proxy traps while recovering from a failed diagnostic conversion.
  if (types.isProxy(value)) return ""
  const property = Object.getOwnPropertyDescriptor(value, key)
  return property && typeof property.value === "string" ? property.value : ""
}

export function formatStrykerErrorValue(value) {
  try {
    return String(value)
  } catch {
    // This function is called only by Stryker's error formatter. Coercion is
    // attempted once; fallback reads the transported diagnostic as inert data.
    const stack = ownString(value, "stack")
    if (stack) return stack
    const name = ownString(value, "name")
    const message = ownString(value, "message")
    if (name && message) return `${name}: ${message}`
    return message || name || "<unserializable error object>"
  }
}
