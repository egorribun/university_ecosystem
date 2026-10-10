export const canonicalTypeScriptCheckerConfig = Object.freeze({
  checkers: Object.freeze(["typescript"]),
  tsconfigFile: "tsconfig.json",
  typescriptChecker: Object.freeze({
    prioritizePerformanceOverAccuracy: false,
    experimentalNativePreview: false,
  }),
})

export const canonicalTypeScriptCheckerToolchain = Object.freeze({
  checkerPackageName: "@stryker-mutator/typescript-checker",
  checkerPluginName: "typescript",
  checkerDependencySpec: "10.0.0",
  checkerPackageVersion: "10.0.0",
  checkerLockVersion: "10.0.0",
  typescriptDependencySpec: "npm:@typescript/typescript6@^6.0.2",
  typescriptPackageName: "@typescript/typescript6",
  typescriptPackageVersion: "6.0.2",
  typescriptLockVersion: "6.0.2",
  typescriptRuntimeVersion: "6.0.3",
})

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function hasExactKeys(value, keys) {
  return (
    isRecord(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort())
  )
}

export function assertCanonicalTypeScriptCheckerConfig(config) {
  const expected = canonicalTypeScriptCheckerConfig
  if (
    !isRecord(config) ||
    JSON.stringify(config.checkers) !== JSON.stringify(expected.checkers) ||
    config.tsconfigFile !== expected.tsconfigFile ||
    !hasExactKeys(config.typescriptChecker, Object.keys(expected.typescriptChecker)) ||
    config.typescriptChecker.prioritizePerformanceOverAccuracy !==
      expected.typescriptChecker.prioritizePerformanceOverAccuracy ||
    config.typescriptChecker.experimentalNativePreview !==
      expected.typescriptChecker.experimentalNativePreview
  ) {
    throw new Error("Stryker report does not use the canonical TypeScript checker configuration")
  }
  return true
}

function checkerProvenanceRecord(value, requiredFields) {
  return (
    hasExactKeys(value, requiredFields) &&
    requiredFields.every((field) => typeof value[field] === "string" && value[field] !== "")
  )
}

export function assertCanonicalCheckerToolchain(toolchain) {
  const checkerFields = [
    "packageName",
    "pluginName",
    "dependencySpec",
    "packageVersion",
    "lockVersion",
    "lockIntegrity",
  ]
  const typescriptFields = [
    "dependencySpec",
    "packageName",
    "packageVersion",
    "lockVersion",
    "runtimeVersion",
  ]
  const checker = toolchain?.typescriptChecker
  const typescript = toolchain?.typescript
  if (
    !checkerProvenanceRecord(checker, checkerFields) ||
    checker.packageName !== canonicalTypeScriptCheckerToolchain.checkerPackageName ||
    checker.pluginName !== canonicalTypeScriptCheckerToolchain.checkerPluginName ||
    checker.dependencySpec !== canonicalTypeScriptCheckerToolchain.checkerDependencySpec ||
    checker.packageVersion !== canonicalTypeScriptCheckerToolchain.checkerPackageVersion ||
    checker.lockVersion !== canonicalTypeScriptCheckerToolchain.checkerLockVersion ||
    !/^sha512-[A-Za-z0-9+/]{86}==$/.test(checker.lockIntegrity) ||
    !checkerProvenanceRecord(typescript, typescriptFields) ||
    typescript.dependencySpec !== canonicalTypeScriptCheckerToolchain.typescriptDependencySpec ||
    typescript.packageName !== canonicalTypeScriptCheckerToolchain.typescriptPackageName ||
    typescript.packageVersion !== canonicalTypeScriptCheckerToolchain.typescriptPackageVersion ||
    typescript.lockVersion !== canonicalTypeScriptCheckerToolchain.typescriptLockVersion ||
    typescript.runtimeVersion !== canonicalTypeScriptCheckerToolchain.typescriptRuntimeVersion
  ) {
    throw new Error("Stryker checker toolchain provenance is missing or noncanonical")
  }
  return true
}
