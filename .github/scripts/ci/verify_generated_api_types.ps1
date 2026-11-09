git diff --exit-code -- `
  frontend/openapi.json `
  frontend/src/api/generated/ `
  frontend/src/tests/mocks/generated/
if ($LASTEXITCODE -ne 0) {
  echo "::error::Generated OpenAPI, TypeScript SDK, or MSW mocks are not up to date. Run 'npm run generate:api'."
  exit 1
}
