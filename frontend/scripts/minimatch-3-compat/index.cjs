"use strict"

// eslint-plugin-react@7.37.5 and eslint-plugin-jsx-a11y@6.10.2 call the
// CommonJS default function export of minimatch@3 as minimatch(path, pattern, options).
// minimatch@3 has no release outside GHSA-g3hv-75wg-m249 (<11.0.1), so this adapter
// keeps that call shape and delegates matching to the patched minimatch@11 engine.
// It exposes only the function; the ESLint rules use no other minimatch member.
const { minimatch: engine } = require("minimatch")

function minimatch(path, pattern, options) {
  return engine(path, pattern, options ?? {})
}

module.exports = minimatch
