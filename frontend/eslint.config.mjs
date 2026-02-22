// For more info, see https://github.com/storybookjs/eslint-plugin-storybook#configuration-flat-config-format
import storybook from "eslint-plugin-storybook";

import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettier from "eslint-config-prettier";
import i18nextPlugin from "eslint-plugin-i18next";
import boundaries from "eslint-plugin-boundaries";


export default tseslint.config({
  ignores: ["dist", "node_modules", "public", "vite.config.mts", "src/api/generated"],
}, js.configs.recommended, ...tseslint.configs.recommended, reactPlugin.configs.flat.recommended, jsxA11y.flatConfigs.recommended, {
  files: ["**/*.{ts,tsx}"],
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: {
      projectService: true,
      tsconfigRootDir: import.meta.dirname,
      ecmaVersion: 2022,
      sourceType: "module",
      ecmaFeatures: { jsx: true }
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
      Response: "readonly"
    }
  },
  plugins: {
    "react-hooks": reactHooks,
    i18next: i18nextPlugin,
    boundaries: boundaries
  },
  settings: {
    react: { version: "detect" },
    "boundaries/elements": [
      { "type": "shared", "pattern": "src/components/*" },
      { "type": "feature", "pattern": "src/features/*" },
      { "type": "page", "pattern": "src/pages/*" },
      { "type": "app", "pattern": "src/app/*" }
    ]
  },
  rules: {
    "@typescript-eslint/no-unused-vars": ["error", {
      "argsIgnorePattern": "^_",
      "varsIgnorePattern": "^_",
      "caughtErrorsIgnorePattern": "^_"
    }],
    "@typescript-eslint/no-explicit-any": "error",
    "no-console": ["warn", { "allow": ["warn", "error"] }],
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

    "react/prop-types": "off",
    "react/react-in-jsx-scope": "off",

    "no-restricted-syntax": [
      "off",
      {
        "selector": "JSXAttribute[name.name='className'] Literal[value=/-\\[.*\\]/]",
        "message": "Arbitrary values (magic numbers) in Tailwind classes are discouraged. Please use design tokens from the theme."
      }
    ],
    "boundaries/element-types": [
      "error",
      {
        "default": "allow",
        "rules": [
          {
            "from": ["shared"],
            "disallow": ["feature", "page", "app"],
            "message": "Shared components cannot import from features, pages, or app layer."
          },
          {
            "from": ["feature"],
            "disallow": ["page", "app"],
            "message": "Features cannot import from pages or app layer."
          }
        ]
      }
    ]
  }
}, {
  files: [
    "src/App.tsx",
    "src/components/Footer.tsx",
    "src/components/MobileBottomNav.tsx",
    "src/components/Navbar.tsx",
    "src/pages/Dashboard.tsx",
    "src/pages/Login.tsx",
    "src/pages/Register.tsx",
    "src/pages/ForgotPassword.tsx",
    "src/pages/ResetPassword.tsx"
  ],
  rules: {
    "i18next/no-literal-string": [
      "warn",
      {
        mode: "jsx-text-only",
        "jsx-components": {
          include: [],
          exclude: ["Trans"]
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
            "rel"
          ]
        }
      }
    ]
  }
}, {
  files: ["src/**/*.{test,spec}.{ts,tsx}", "src/tests/**/*.{ts,tsx}"],
  rules: {
    "i18next/no-literal-string": "off"
  }
}, prettier, storybook.configs["flat/recommended"]);
