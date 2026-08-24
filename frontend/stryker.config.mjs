import os from "node:os"
import path from "node:path"

const strykerTempRoot = path.join(os.tmpdir(), "university-ecosystem-stryker")

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
  // Keep the sandbox outside the repository. On Windows, the workspace ACL
  // can deny esbuild reads from nested mutation directories; an OS-temp root
  // preserves isolation without broadening the mutation scope.
  tempDirName: strykerTempRoot,
  // Never copy generated caches or a previous interrupted sandbox into the
  // next mutation run. Besides wasting I/O, nested Cargo caches can amplify
  // Stryker's memory use into the gigabyte range on Windows.
  ignorePatterns: ["**/.codex_*/**", "**/target/**", "/reports/**"],
  vitest: {
    configFile: "vitest.config.ts",
    related: false,
  },
  coverageAnalysis: "off",
  mutate: [
    // Initial security Tier-0 slice: address/Telegram URL boundaries. Keep
    // the scope explicit so a green gate represents a complete mutation run,
    // not a partial score over an untestable application-wide universe.
    "src/utils/sanitize.ts:90:1-96:2",
    // `safe === null` is followed by a defensive URL parse catch that returns
    // the same empty value; line 101 therefore has no independently observable
    // mutant and remains covered by the direct invalid-host test below.
    "src/utils/sanitize.ts:98:1-100:2",
    "src/utils/sanitize.ts:109:1-116:2",
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
  cleanTempDir: "always",
  timeoutFactor: 2,
}
