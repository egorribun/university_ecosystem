/**
 * Mutation scope for the frontend's deterministic, security-sensitive utility
 * layer. The 100% threshold is intentional: a green result means every
 * viable mutant in this Tier-0 slice is killed by an executable test.
 */
export default {
  testRunner: "vitest",
  // Windows Vitest/ESBuild cannot reliably resolve configs from Stryker's
  // hidden default `.stryker-tmp`; keep the sandbox visible as recommended
  // by Stryker's Windows troubleshooting guidance.
  tempDirName: "stryker-tmp",
  // Never copy generated caches or a previous interrupted sandbox into the
  // next mutation run. Besides wasting I/O, nested Cargo caches can amplify
  // Stryker's memory use into the gigabyte range on Windows.
  ignorePatterns: ["/stryker-tmp/**", "**/.codex_*/**", "**/target/**", "/reports/**"],
  vitest: {
    configFile: "vitest.config.ts",
    related: false,
  },
  coverageAnalysis: "off",
  mutate: [
    // Initial security Tier-0 slice: address/Telegram URL boundaries. Keep
    // the scope explicit so a green gate represents a complete mutation run,
    // not a partial score over an untestable application-wide universe.
    "src/utils/sanitize.ts:86:1-92:2",
    // `safe === null` is followed by a defensive URL parse catch that returns
    // the same empty value; line 97 therefore has no independently observable
    // mutant and remains covered by the direct invalid-host test below.
    "src/utils/sanitize.ts:94:1-96:2",
    "src/utils/sanitize.ts:105:1-112:2",
  ],
  testFiles: [
    "src/utils/__tests__/sanitize*.test.ts",
    "src/utils/__tests__/propertyBased.test.ts",
    "src/i18n/__tests__/formatters.test.ts",
  ],
  incremental: true,
  incrementalFile: "reports/stryker-incremental.json",
  reporters: ["clear-text", "progress", "html", "json"],
  thresholds: {
    high: 100,
    low: 100,
    break: 100,
  },
  // Keep the mutation runner bounded on Windows and CI hosts where Vitest's
  // jsdom workers can retain native handles between mutations. The threshold
  // remains 100%; this only serializes execution and recycles workers.
  concurrency: 1,
  maxTestRunnerReuse: 4,
  timeoutFactor: 2,
}
