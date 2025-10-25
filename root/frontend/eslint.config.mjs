import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettier from "eslint-config-prettier";
import i18nextPlugin from "eslint-plugin-i18next";

export default tseslint.config(
  {
    ignores: ["dist", "node_modules", "public", "vite.config.mts", "src/api/generated"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactPlugin.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
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
      "react-hooks": reactHooks,
      i18next: i18nextPlugin
    },
    settings: {
      react: { version: "detect" }
    },
    rules: {
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-expressions": "off",
      "@typescript-eslint/triple-slash-reference": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "no-empty": "off",
      "no-extra-boolean-cast": "off",
      "no-useless-escape": "off",
      "jsx-a11y/click-events-have-key-events": "off",
      "jsx-a11y/no-noninteractive-element-interactions": "off",
      "jsx-a11y/no-redundant-roles": "off",
      "jsx-a11y/no-autofocus": "off",
      "react-hooks/rules-of-hooks": "off",
      "react-hooks/exhaustive-deps": "off",
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off"
    }
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
  },
  {
    files: ["src/**/*.{test,spec}.{ts,tsx}", "src/tests/**/*.{ts,tsx}"],
    rules: {
      "i18next/no-literal-string": "off"
    }
  },
  prettier
);
