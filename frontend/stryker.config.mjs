import os from "node:os"
import path from "node:path"
import process from "node:process"

import coverageSourcePolicy from "../quality/coverage-source-policy.json" with { type: "json" }

const strykerTempRoot =
  process.env.STRYKER_TEMP_DIR ?? path.join(os.tmpdir(), "university-ecosystem-stryker-unscoped")
const jsonReport = process.env.STRYKER_JSON_REPORT ?? "reports/mutation/mutation.json"
const htmlReport = process.env.STRYKER_HTML_REPORT ?? "reports/mutation/mutation.html"
const canonicalMutationScope = [
  ...coverageSourcePolicy.frontend.include,
  ...coverageSourcePolicy.frontend.exclude.map((pattern) => `!${pattern}`),
]
const mutationScope = process.env.STRYKER_MUTATE_JSON
  ? JSON.parse(process.env.STRYKER_MUTATE_JSON)
  : canonicalMutationScope
if (
  process.env.STRYKER_MUTATE_JSON &&
  (!Array.isArray(mutationScope) ||
    mutationScope.length === 0 ||
    mutationScope.some(
      (entry) =>
        typeof entry !== "string" ||
        entry === "" ||
        entry.startsWith("!") ||
        entry.includes("..") ||
        path.isAbsolute(entry)
    ))
) {
  throw new Error("STRYKER_MUTATE_JSON must contain canonical relative source paths")
}

/**
 * Full authored-frontend mutation gate. The source universe is shared with
 * coverage and the post-run inventory proves that every denominator file was
 * either mutated or explicitly accounted for as generating zero mutants.
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
    // Each shard mutates a bounded source assignment. Vitest's related mode
    // resolves the complete dependency graph for that assignment, preserving
    // the full mutation denominator while avoiding the full suite for every
    // shard. A missing relation remains fail-closed: Stryker reports no
    // coverage and the inventory gate rejects the resulting non-100% score.
    related: true,
  },
  coverageAnalysis: "perTest",
  // Mutation and coverage must describe the same authored source universe.
  // Deriving the patterns from the canonical policy prevents a narrow manual
  // allow-list from reporting 100% while most production files are unmutated.
  mutate: mutationScope,
  mutator: {
    plugins: null,
    excludedMutations: [],
  },
  ignorers: [],
  // Canonical release evidence is always a fresh run. Incremental reports are
  // useful for local feedback only and must never enter this evidence path.
  incremental: false,
  reporters:
    process.env.STRYKER_SHARD_RUN === "1"
      ? ["clear-text", "progress", "json"]
      : ["clear-text", "progress", "html", "json"],
  jsonReporter: { fileName: jsonReport },
  htmlReporter: { fileName: htmlReport },
  thresholds: {
    high: 100,
    low: 100,
    break: 100,
  },
  // Keep the mutation runner bounded on Windows and CI hosts where Vitest's
  // jsdom workers can retain native handles between mutations. The threshold
  // remains 100%; this only serializes execution and recycles workers.
  concurrency: Number.parseInt(process.env.STRYKER_CONCURRENCY ?? "2", 10),
  maxTestRunnerReuse: 4,
  cleanTempDir: "always",
  // Keep an explicit bounded deadline for the related-mode discovery pass.
  // Mutation thresholds remain fail-closed at 100%; the outer shard timeout is
  // still enforced by the canonical runner.
  dryRunTimeoutMinutes: 15,
  timeoutFactor: 2,
}
