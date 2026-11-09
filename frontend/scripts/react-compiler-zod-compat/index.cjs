// ADR-048: tooling-only facade for eslint-plugin-react-compiler@19.1.0-rc.2.
// This is not a general Zod 3 replacement. The original plugin is not modified.
const metadata = require("patched-zod/package.json")
if (metadata.name !== "zod" || metadata.version !== "4.6.7") {
  throw new Error("React compiler compatibility requires the verified Zod 4.6.7 engine")
}
const { z: engine } = require("patched-zod")

const z = Object.freeze({
  array: engine.array,
  boolean: engine.boolean,
  enum: engine.enum,
  function() {
    const schema = engine.function()
    // Legacy args() accepts additional arguments and validates the fixed prefix.
    schema.args = (...items) => schema.input(items, engine.unknown())
    return schema
  },
  lazy: engine.lazy,
  literal: engine.literal,
  map(key, value) {
    const schema = engine.map(key, value)
    // Zod 3 parses and clones defaults; Zod 4 default() intentionally bypasses it.
    schema.default = (fallback) => schema.prefault(fallback)
    return schema
  },
  nativeEnum: engine.nativeEnum,
  nullable: engine.nullable,
  number: engine.number,
  object: engine.object,
  record: engine.record,
  string: engine.string,
  tuple: engine.tuple,
  union: engine.union,
})

module.exports = { z }
