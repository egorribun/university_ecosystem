import depcheck from "depcheck"
import path from "path"
import { fileURLToPath } from "url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectDir = path.resolve(__dirname, "..")

const options = {
  ignoreBinPackage: false,
  skipMissing: true,
  ignoreMatches: [
    // Storybook and documentation tools
    "@storybook/*",
    "storybook",
    "@chromatic-com/*",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-onboarding",
    "@storybook/addon-vitest",
    "@storybook/react-vite",
    // Browser-mode runtime consumed by the Storybook Vitest addon rather than
    // imported directly from application source.
    "@vitest/browser",
    // Sentry integration
    "@sentry/vite-plugin",
    // CSS / Tailwind
    "tailwindcss",
    "@tailwindcss/postcss",
    "autoprefixer",
    "postcss",
    // Build and tooling dependencies
    "cross-env",
    "husky",
    "prettier-plugin-organize-imports",
    "@lhci/cli",
    // Peer runtimes consumed by the active API mock generator and Lighthouse.
    "openapi-types",
    "proxy-agent",
    "@vitest/coverage-v8",
    "typescript",
    "typescript-eslint",
    "eslint-config-prettier",
    "@eslint/js",
    "eslint",
    "eslint-plugin-*",
    "eslint-plugin-boundaries",
    "eslint-plugin-i18next",
    "eslint-plugin-jsx-a11y",
    "eslint-plugin-react",
    "eslint-plugin-react-compiler",
    "eslint-plugin-react-hooks",
    "eslint-plugin-security",
    "eslint-plugin-storybook",
    // Testing / Tools
    "@axe-core/playwright",
    "@babel/core",
    "@rolldown/plugin-babel",
    "@testing-library/react",
    "@testing-library/user-event",
    "@vitejs/plugin-react",
    "ajv",
    "ajv-formats",
    "babel-plugin-react-compiler",
    "fake-indexeddb",
    "jest-axe",
    "rollup-plugin-visualizer",
    "sharp",
    "vite-plugin-wasm",
    "workbox-cacheable-response",
    "workbox-core",
    "workbox-expiration",
    "workbox-routing",
    "workbox-strategies",
    "web-vitals",
    "wasm-sanitizer",
    "@types/*",
    "@types/qrcode",
    "@types/react",
    "@types/react-dom",
    "@types/node",
    "@types/trusted-types",
    "@types/jest-axe",
    "@types/jsdom",
    "zod",
    "@tanstack/react-router-devtools",
    "@tanstack/query-sync-storage-persister",
    "i18next-browser-languagedetector",
    "i18next-http-backend",
    "brace-expansion",
    "@testing-library/jest-dom",
    "vite-plugin-pwa",
    "workbox-build",
    "workbox-window",
    "@zxcvbn-ts/core",
    "@zxcvbn-ts/language-common",
    "html-to-image",
    "jspdf",
    "qrcode",
    "depcheck",
    "@stryker-mutator/*",
  ],
  parsers: {
    // Supplying this map replaces depcheck's defaults. Keep Node ESM tooling
    // visible so dependencies owned by scripts/*.mjs are not misclassified.
    "**/*.mjs": depcheck.parser.es6,
    "**/*.ts": depcheck.parser.typescript,
    "**/*.tsx": depcheck.parser.typescript,
  },
  detectors: [
    depcheck.detector.requireCallExpression,
    depcheck.detector.importDeclaration,
    depcheck.detector.importCallExpression,
  ],
  specials: [
    depcheck.special.eslint,
    depcheck.special.webpack,
    depcheck.special.babel,
    depcheck.special.bin,
  ],
}

depcheck(projectDir, options, (unused) => {
  const unusedDeps = unused.dependencies || []
  const unusedDevDeps = unused.devDependencies || []

  if (unusedDeps.length > 0 || unusedDevDeps.length > 0) {
    console.log("Unused dependencies:")
    unusedDeps.forEach((dep) => console.log(`* ${dep}`))
    console.log("Unused devDependencies:")
    unusedDevDeps.forEach((dep) => console.log(`* ${dep}`))

    // On Windows, we treat this check as advisory due to Windows backslash matching bugs in depcheck
    if (process.platform === "win32") {
      console.warn(
        "\n[Warning] Unused dependencies check failed, but running on Windows where path matching is buggy. Treating as advisory."
      )
      process.exit(0)
    } else {
      process.exit(1)
    }
  } else {
    console.log("✅ No unused dependencies found!")
    process.exit(0)
  }
})
