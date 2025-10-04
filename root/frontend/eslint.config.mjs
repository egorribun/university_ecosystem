import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettier from "eslint-config-prettier";
import security from "eslint-plugin-security";

const securityRecommended = security.configs.recommended;
const securityRules = Object.fromEntries(
  Object.keys(securityRecommended.rules ?? {}).map((rule) => [rule, "error"])
);
const securityConfig = {
  ...securityRecommended,
  rules: securityRules,
};

export default tseslint.config(
  {
    ignores: ["dist", "node_modules", "public", "vite.config.mts"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactPlugin.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  securityConfig,
  {
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
      "react-hooks": reactHooks
    },
    settings: {
      react: { version: "detect" }
    },
    rules: {
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off"
    }
  },
  prettier
);
