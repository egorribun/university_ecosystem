"use strict"

// First-party adapter for one operation in @rollup/plugin-node-resolve 16.0.3.
// This is not a general-purpose deepmerge implementation.
const expectedDefaults = {
  dedupe: [],
  extensions: [".mjs", ".js", ".json", ".node"],
  resolveOnly: [],
  moduleDirectories: ["node_modules"],
  modulePaths: [],
  ignoreSideEffectsForRoot: false,
  allowExportsFolderMapping: true,
}

function reject() {
  throw new TypeError("Unsupported node-resolve defaults clone contract")
}

function assertExactData(actual, expected) {
  if (expected === null || typeof expected !== "object") {
    if (!Object.is(actual, expected)) reject()
    return
  }
  if (
    actual === null ||
    typeof actual !== "object" ||
    Object.getPrototypeOf(actual) !== Object.getPrototypeOf(expected)
  ) reject()
  const keys = Reflect.ownKeys(expected)
  const actualKeys = Reflect.ownKeys(actual)
  if (actualKeys.length !== keys.length) reject()
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(actual, key)
    const expectedDescriptor = Object.getOwnPropertyDescriptor(expected, key)
    if (
      !descriptor ||
      !("value" in descriptor) ||
      descriptor.enumerable !== expectedDescriptor.enumerable
    ) reject()
    assertExactData(descriptor.value, expectedDescriptor.value)
  }
}

module.exports = function cloneNodeResolveDefaults(target, source) {
  if (arguments.length !== 2) reject()
  assertExactData(target, {})
  assertExactData(source, expectedDefaults)
  return structuredClone(source)
}
