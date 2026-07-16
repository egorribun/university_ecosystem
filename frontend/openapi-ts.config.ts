import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "src/api/generated",
    postProcess: ["prettier"],
  },
  plugins: ["@hey-api/client-axios"],
})
