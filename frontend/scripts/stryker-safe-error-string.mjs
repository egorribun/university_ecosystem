/*
 * Stryker/Vitest child compatibility preload.
 *
 * Vitest serializes unhandled errors for worker transport as null-prototype
 * records.  Stryker 9.6 calls String(error) while formatting those records;
 * the native conversion throws because the record has no Object.prototype.
 * This module is loaded only in Stryker shard children through NODE_OPTIONS.
 */

const nativeString = globalThis.String

function hasNullPrototype(value) {
  if (value === null || typeof value !== "object") return false
  try {
    return Object.getPrototypeOf(value) === null
  } catch {
    return false
  }
}

function readStringProperty(value, key) {
  try {
    const property = Reflect.get(value, key)
    return typeof property === "string" ? property : ""
  } catch {
    return ""
  }
}

/**
 * Convert Vitest's serialized error record into a useful diagnostic without
 * invoking the record's missing prototype conversion hooks.
 */
export function formatSerializedError(value) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return nativeString(value)
  }

  const stack = readStringProperty(value, "stack")
  if (stack) return stack

  const name = readStringProperty(value, "name")
  const message = readStringProperty(value, "message")
  if (name && message) return `${name}: ${message}`
  if (message) return message
  if (name) return name

  // Preserve native String semantics for ordinary objects.  Only the
  // conversion failure handled by safeStringValue reaches this branch for a
  // non-null-prototype object, where a diagnostic placeholder is safer than
  // rethrowing the serializer crash.
  if (!hasNullPrototype(value)) {
    try {
      return nativeString(value)
    } catch {
      return "<unserializable error object>"
    }
  }
  return "<unserializable error object>"
}

function safeStringValue(value) {
  try {
    return nativeString(value)
  } catch (error) {
    // Vitest may materialize the native TypeError in a worker/VM realm, so
    // `instanceof TypeError` is not reliable across the transport boundary.
    // Restrict the fallback to the exact null-prototype record shape that
    // causes the Stryker serializer crash; ordinary conversion errors must
    // retain their native behavior.
    const errorName =
      error !== null && typeof error === "object" ? readStringProperty(error, "name") : ""
    const errorMessage = readStringProperty(error, "message")
    const isPrimitiveConversionError =
      (error instanceof TypeError || errorName === "TypeError") &&
      errorMessage.includes("Cannot convert object to primitive value")
    if (isPrimitiveConversionError) {
      return formatSerializedError(value)
    }
    throw error
  }
}

/**
 * A String-compatible callable/constructor.  All ordinary conversions are
 * delegated to the native implementation; only null-prototype conversion
 * failures receive the Vitest error-record fallback.
 */
export function safeString(value) {
  if (new.target) {
    const converted = arguments.length === 0 ? nativeString() : safeStringValue(value)
    return Reflect.construct(nativeString, [converted], new.target)
  }
  return arguments.length === 0 ? nativeString() : safeStringValue(value)
}

Object.setPrototypeOf(safeString, nativeString)
safeString.prototype = nativeString.prototype
Object.defineProperty(safeString, "name", {
  configurable: true,
  value: "String",
})
for (const key of Reflect.ownKeys(nativeString)) {
  if (key === "length" || key === "name" || key === "prototype") continue
  const descriptor = Object.getOwnPropertyDescriptor(nativeString, key)
  if (descriptor) Object.defineProperty(safeString, key, descriptor)
}
Object.defineProperty(safeString, "prototype", { writable: false })

export function installSafeString() {
  const current = Object.getOwnPropertyDescriptor(globalThis, "String")
  if (!current || current.configurable !== true || current.writable !== true) return false
  Object.defineProperty(globalThis, "String", {
    ...current,
    value: safeString,
  })
  return true
}

if (process.env.STRYKER_SHARD_RUN === "1") {
  installSafeString()
}
