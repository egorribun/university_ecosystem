// For more info, see https://github.com/storybookjs/eslint-plugin-storybook#configuration-flat-config-format
import storybook from "eslint-plugin-storybook"

import js from "@eslint/js"
import globals from "globals"
import tseslint from "typescript-eslint"
import reactPlugin from "eslint-plugin-react"
import reactHooks from "eslint-plugin-react-hooks"
import jsxA11y from "eslint-plugin-jsx-a11y"
import prettier from "eslint-config-prettier"
import i18nextPlugin from "eslint-plugin-i18next"
import boundaries from "eslint-plugin-boundaries"
import reactCompiler from "eslint-plugin-react-compiler"
import security from "eslint-plugin-security"

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "public",
      "vite.config.mts",
      ".storybook",
      "src/api/generated",
      "rust-crypto/pkg",
      "wasm-sanitizer/pkg",
    ],
  },
  js.configs.recommended,
  {
    files: ["scripts/**/*.{js,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.node,
    },
  },
  {
    files: ["scripts/**/*.cjs"],
    languageOptions: {
      sourceType: "commonjs",
    },
  },
  ...tseslint.configs.recommended,
  reactPlugin.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    settings: {
      react: { version: "detect" },
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        // TypeScript type-checking is a separate blocking gate (`npm run
        // typecheck`). Keeping ESLint syntax-aware avoids constructing the
        // entire 1,300+ file TS project for every lint invocation; the full
        // run exceeded 2.5 GB and a one-file probe exhausted 768 MB.
        projectService: false,
        tsconfigRootDir: import.meta.dirname,
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        navigator: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        Notification: "readonly",
        ResizeObserver: "readonly",
        crypto: "readonly",
        Request: "readonly",
        RequestInit: "readonly",
        Headers: "readonly",
        FormData: "readonly",
        Response: "readonly",
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      i18next: i18nextPlugin,
      boundaries: boundaries,
      "react-compiler": reactCompiler,
      security,
    },
    settings: {
      "boundaries/elements": [
        { type: "shared", pattern: "src/components/*" },
        { type: "feature", pattern: "src/features/*" },
        { type: "page", pattern: "src/pages/*" },
        { type: "app", pattern: "src/app/*" },
      ],
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-debugger": "error",
      "@typescript-eslint/no-unused-expressions": "warn",
      "@typescript-eslint/triple-slash-reference": "error",
      "@typescript-eslint/no-empty-object-type": "error",

      "no-extra-boolean-cast": "error",
      "no-useless-escape": "warn",
      "jsx-a11y/click-events-have-key-events": "warn",
      "jsx-a11y/no-noninteractive-element-interactions": "warn",
      "jsx-a11y/no-redundant-roles": "warn",
      "jsx-a11y/no-autofocus": "warn",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",

      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",

      "no-restricted-syntax": [
        "off",
        {
          selector: "JSXAttribute[name.name='className'] Literal[value=/-\\[.*\\]/]",
          message:
            "Arbitrary values (magic numbers) in Tailwind classes are discouraged. Please use design tokens from the theme.",
        },
      ],
      // Wave 119 SW4 — eslint-plugin-boundaries v6 migration:
      //   - rule renamed: boundaries/element-types → boundaries/dependencies
      //   - selector form: ["shared"] → { type: "shared" }
      //   - disallow shape: ["feature"] → { to: { type: ["feature"] } }
      // See https://www.jsboundaries.dev/docs/releases/migration-guides/v5-to-v6/
      "boundaries/dependencies": [
        "error",
        {
          default: "allow",
          rules: [
            {
              from: { type: "shared" },
              disallow: { to: { type: ["feature", "page", "app"] } },
              message: "Shared components cannot import from features, pages, or app layer.",
            },
            {
              from: { type: "feature" },
              disallow: { to: { type: ["page", "app"] } },
              message: "Features cannot import from pages or app layer.",
            },
          ],
        },
      ],
      "react-compiler/react-compiler": "error",
      // MOD-43-02: eslint-plugin-security — static analysis for common vulnerability patterns
      // detect-object-injection disabled: >95% false positives on array[i] and Map lookups
      "security/detect-object-injection": "off",
      "security/detect-non-literal-regexp": "warn",
      "security/detect-unsafe-regex": "error",
      "security/detect-buffer-noassert": "error",
      "security/detect-eval-with-expression": "error",
      "security/detect-no-csrf-before-method-override": "error",
      "security/detect-pseudoRandomBytes": "warn",
      "no-restricted-imports": [
        "error",
        {
          paths: [
            // Wave 191 SW3 — close W189 polish-v1 Tier 4 deferral (hook migration
            // regression test). framer-motion's `useReducedMotion()` is jsdom-
            // incompatible (W184 SW6 lesson — touches window.matchMedia(...)
            // .addEventListener via initPrefersReducedMotion through a code
            // path jsdom's polyfill doesn't fully cover, producing TypeError as
            // vitest unhandled errors). W190 broader migration sweep closed all
            // 25/25 component+hook source-level imports; this rule prevents
            // regression. Belt-and-suspenders with vitest fs-grep guard at
            // src/tests/hookMigrationRegression.test.ts.
            {
              name: "framer-motion",
              importNames: ["useReducedMotion"],
              message:
                'framer-motion useReducedMotion is jsdom-incompatible (W184 SW6 + W190 broader migration sweep). Use `useMediaQuery("(prefers-reduced-motion: reduce)")` from `@/hooks/useMediaQuery` (DEFAULT export) instead. See CLAUDE.md ## Gotchas for full rationale.',
            },
          ],
        },
      ],
    },
  },
  {
    files: [
      "src/App.tsx",
      "src/components/Footer.tsx",
      "src/components/MobileBottomNav.tsx",
      "src/components/Navbar.tsx",
      "src/pages/Dashboard.tsx",
      "src/pages/Login.tsx",
      "src/pages/Register.tsx",
      "src/pages/ForgotPassword.tsx",
      "src/pages/ResetPassword.tsx",
    ],
    rules: {
      "i18next/no-literal-string": [
        "warn",
        {
          mode: "jsx-text-only",
          "jsx-components": {
            include: [],
            exclude: ["Trans"],
          },
          "jsx-attributes": {
            include: [],
            exclude: [
              "className",
              "styleName",
              "style",
              "type",
              "key",
              "id",
              "width",
              "height",
              "data-testid",
              "data-track",
              "data-cy",
              "aria-label",
              "aria-describedby",
              "aria-labelledby",
              "role",
              "to",
              "href",
              "target",
              "rel",
            ],
          },
        },
      ],
    },
  },
  {
    files: ["src/**/*.{test,spec}.{ts,tsx}", "src/tests/**/*.{ts,tsx}"],
    rules: {
      "i18next/no-literal-string": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-function-type": "off",
    },
  },
  {
    files: ["scripts/**/*.{js,mjs,cjs}"],
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: ["scripts/**/*.cjs"],
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
  prettier,
  storybook.configs["flat/recommended"],
  {
    files: ["src/routes/**/*.{ts,tsx}"],
    rules: {
      "storybook/default-exports": "off",
    },
  }
)
