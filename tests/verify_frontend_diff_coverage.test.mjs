import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { prepareDiffCoverage } from "../scripts/quality/verify_frontend_diff_coverage.mjs";

const repositoryRoot = process.cwd();
const require = createRequire(
  path.join(repositoryRoot, "frontend", "package.json"),
);
const { createCoverageMap } = require("istanbul-lib-coverage");
const { createContext } = require("istanbul-lib-report");
const reports = require("istanbul-reports");
const sourcePolicy = fs.readFileSync(
  path.join(repositoryRoot, "quality/coverage-source-policy.json"),
);

function git(root, args) {
  execFileSync("git", ["-C", root, ...args], { stdio: "ignore" });
}

function makeFixture({
  baseSource,
  changedSource,
  hits = 1,
  includeLcovLine = true,
  includeIstanbul = true,
  emptyCoverage = false,
  typeChange = false,
  branches = [],
}) {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "frontend-diff-cover-contract-"),
  );
  const sourcePath = path.join(root, "frontend", "src", "module.ts");
  fs.mkdirSync(path.dirname(sourcePath), { recursive: true });
  fs.mkdirSync(path.join(root, "frontend", "coverage"), { recursive: true });
  fs.mkdirSync(path.join(root, "quality"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "quality", "coverage-source-policy.json"),
    sourcePolicy,
  );
  fs.writeFileSync(sourcePath, baseSource);
  git(root, ["init", "--quiet"]);
  git(root, ["checkout", "--quiet", "-b", "base"]);
  git(root, ["config", "user.name", "Coverage Contract"]);
  git(root, ["config", "user.email", "coverage-contract@example.invalid"]);
  git(root, [
    "add",
    "frontend/src/module.ts",
    "quality/coverage-source-policy.json",
  ]);
  git(root, ["commit", "--quiet", "-m", "base"]);
  git(root, ["checkout", "--quiet", "-b", "candidate"]);
  if (typeChange) {
    const linkTargetHash = execFileSync(
      "git",
      ["-C", root, "hash-object", "-w", "--stdin"],
      {
        input: "module.ts\n",
        encoding: "utf8",
        stdio: ["pipe", "pipe", "pipe"],
      },
    ).trim();
    git(root, [
      "update-index",
      "--add",
      "--cacheinfo",
      `120000,${linkTargetHash},frontend/src/module.ts`,
    ]);
  } else {
    fs.writeFileSync(sourcePath, changedSource);
    git(root, ["add", "frontend/src/module.ts"]);
  }
  git(root, ["commit", "--quiet", "-m", "candidate"]);

  const reportPath = path.join(root, "frontend", "coverage", "lcov.info");
  const records = [];
  if (!includeLcovLine) {
    records.push("TN:\nSF:src/other.ts\nDA:1,1\nLF:1\nLH:1\nend_of_record\n");
  }
  fs.writeFileSync(reportPath, records.join(""));
  const coveragePath = path.join(
    root,
    "frontend",
    "coverage",
    "coverage-final.json",
  );
  const fileKey = path.join(root, "frontend", "src", "module.ts");
  const branchMap = Object.fromEntries(
    branches.map(({ line, hits: branchHits }, index) => [
      String(index),
      {
        loc: {
          start: { line, column: 0 },
          end: { line, column: 1 },
        },
        type: "if",
        locations: branchHits.map(() => ({
          start: { line, column: 0 },
          end: { line, column: 1 },
        })),
        line,
      },
    ]),
  );
  const branchCounters = Object.fromEntries(
    branches.map(({ hits: branchHits }, index) => [String(index), branchHits]),
  );
  const document = includeIstanbul
    ? {
        [fileKey]: {
          path: fileKey,
          statementMap: emptyCoverage
            ? {}
            : {
                0: {
                  start: { line: 1, column: 0 },
                  end: { line: 1, column: 18 },
                },
              },
          fnMap: {},
          branchMap,
          s: emptyCoverage ? {} : { 0: hits },
          f: {},
          b: branchCounters,
        },
      }
    : {
        [path.join(root, "frontend", "src", "other.ts")]: {
          path: path.join(root, "frontend", "src", "other.ts"),
          statementMap: {
            0: { start: { line: 1, column: 0 }, end: { line: 1, column: 5 } },
          },
          fnMap: {},
          branchMap: {},
          s: { 0: 1 },
          f: {},
          b: {},
        },
      };
  fs.writeFileSync(coveragePath, JSON.stringify(document));
  if (includeLcovLine) {
    const coverageMap = createCoverageMap(document);
    reports
      .create("lcovonly", { projectRoot: path.join(root, "frontend") })
      .execute(createContext({ coverageMap, dir: path.dirname(reportPath) }));
  } else {
    fs.writeFileSync(reportPath, records.join(""));
  }
  const outputDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "frontend-diff-cover-output-"),
  );
  const normalizedPath = path.join(outputDirectory, "lcov.info");
  return { root, reportPath, coveragePath, normalizedPath };
}

function runRealDiffCover(fixture) {
  const executable =
    process.platform === "win32"
      ? path.join(repositoryRoot, ".venv", "Scripts", "diff-cover.exe")
      : path.join(repositoryRoot, ".venv", "bin", "diff-cover");
  return execFileSync(
    executable,
    [fixture.normalizedPath, "--compare-branch=base", "--fail-under=100"],
    {
      cwd: fixture.root,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
}

function withFixture(options, callback) {
  const fixture = makeFixture(options);
  try {
    return callback(fixture);
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
    fs.rmSync(path.dirname(fixture.normalizedPath), {
      recursive: true,
      force: true,
    });
  }
}

test("normalizes LCOV paths, preserves raw artifacts, and passes covered changed lines", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      branches: [{ line: 1, hits: [2, 1] }],
    },
    (fixture) => {
      const rawBefore = createHash("sha256")
        .update(fs.readFileSync(fixture.reportPath))
        .digest("hex");
      const istanbulBefore = createHash("sha256")
        .update(fs.readFileSync(fixture.coveragePath))
        .digest("hex");
      const result = prepareDiffCoverage({
        repoRoot: fixture.root,
        baseRef: "base",
        outputPath: fixture.normalizedPath,
      });
      assert.equal(result.eligibleFiles, 1);
      assert.match(
        fs.readFileSync(fixture.normalizedPath, "utf8"),
        /^TN:\nSF:frontend\/src\/module\.ts\n/m,
      );
      assert.match(
        fs.readFileSync(fixture.normalizedPath, "utf8"),
        /BRDA:1,0,0,2\nBRDA:1,0,1,1\n/u,
      );
      assert.equal(
        createHash("sha256")
          .update(fs.readFileSync(fixture.reportPath))
          .digest("hex"),
        rawBefore,
      );
      assert.equal(
        createHash("sha256")
          .update(fs.readFileSync(fixture.coveragePath))
          .digest("hex"),
        istanbulBefore,
      );
      runRealDiffCover(fixture);
    },
  );
});

test("fails closed when LCOV omits an Istanbul branch outcome", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      branches: [{ line: 1, hits: [2, 1] }],
    },
    (fixture) => {
      const original = fs.readFileSync(fixture.reportPath, "utf8");
      fs.writeFileSync(
        fixture.reportPath,
        original.replace("BRDA:1,0,1,1\n", ""),
      );
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /LCOV is missing an Istanbul branch outcome/u,
      );
    },
  );
});

test("fails closed when an LCOV branch counter differs from Istanbul", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      branches: [{ line: 1, hits: [2, 1] }],
    },
    (fixture) => {
      const original = fs.readFileSync(fixture.reportPath, "utf8");
      fs.writeFileSync(
        fixture.reportPath,
        original.replace("BRDA:1,0,1,1\n", "BRDA:1,0,1,0\n"),
      );
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /LCOV and Istanbul branch counts disagree/u,
      );
    },
  );
});

test("keeps an uncovered executable changed line blocking", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      hits: 0,
    },
    (fixture) => {
      const result = prepareDiffCoverage({
        repoRoot: fixture.root,
        baseRef: "base",
        outputPath: fixture.normalizedPath,
      });
      assert.equal(result.eligibleFiles, 1);
      assert.throws(() => runRealDiffCover(fixture), /Command failed/u);
    },
  );
});

test("fails closed when a changed eligible source is absent from LCOV", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      includeLcovLine: false,
    },
    (fixture) => {
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /LCOV report is missing changed eligible source/u,
      );
    },
  );
});

test("keeps an eligible regular-to-symlink type change in coverage verification", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      includeIstanbul: false,
      typeChange: true,
    },
    (fixture) => {
      const change = execFileSync(
        "git",
        [
          "-C",
          fixture.root,
          "diff",
          "--name-status",
          "--no-renames",
          "base...HEAD",
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      );
      assert.match(change, /^T\s+frontend\/src\/module\.ts$/mu);
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /Istanbul report is missing changed eligible source/u,
      );
    },
  );
});

test("fails closed when LCOV omits a reportable Istanbul line", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      includeLcovLine: false,
    },
    (fixture) => {
      fs.writeFileSync(
        fixture.reportPath,
        "TN:\nSF:src/module.ts\nLF:0\nLH:0\nend_of_record\n",
      );
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /LCOV is missing an Istanbul executable line/u,
      );
    },
  );
});

test("allows a comment-only change only after both source reports are verified", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n// old note\n",
      changedSource: "const value = 1;\n// revised note\n",
    },
    (fixture) => {
      const result = prepareDiffCoverage({
        repoRoot: fixture.root,
        baseRef: "base",
        outputPath: fixture.normalizedPath,
      });
      assert.equal(result.eligibleFiles, 1);
      assert.match(
        runRealDiffCover(fixture),
        /No lines with coverage information/u,
      );
    },
  );
});

test("accepts a changed TypeScript source with matching empty report records", () => {
  withFixture(
    {
      baseSource: "export type ModuleValue = string;\n",
      changedSource: "export type ModuleValue = number;\n",
      emptyCoverage: true,
    },
    (fixture) => {
      const istanbul = JSON.parse(
        fs.readFileSync(fixture.coveragePath, "utf8"),
      );
      const report = fs.readFileSync(fixture.reportPath, "utf8");
      assert.equal(Object.keys(istanbul).length, 1);
      assert.deepEqual(
        istanbul[path.join(fixture.root, "frontend", "src", "module.ts")].s,
        {},
      );
      assert.match(report, /^SF:src[\\/]module\.ts$/mu);
      assert.doesNotMatch(report, /^DA:/mu);

      const result = prepareDiffCoverage({
        repoRoot: fixture.root,
        baseRef: "base",
        outputPath: fixture.normalizedPath,
      });
      assert.equal(result.eligibleFiles, 1);
      assert.match(
        fs.readFileSync(fixture.normalizedPath, "utf8"),
        /^SF:frontend\/src\/module\.ts$/mu,
      );
      assert.match(
        runRealDiffCover(fixture),
        /No lines with coverage information/u,
      );
    },
  );
});

test("fails closed when line-level LCOV counters disagree with Istanbul", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      hits: 1,
    },
    (fixture) => {
      fs.writeFileSync(
        fixture.reportPath,
        "TN:\nSF:src/module.ts\nDA:1,0\nLF:1\nLH:0\nend_of_record\n",
      );
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /LCOV and Istanbul line counts disagree/u,
      );
    },
  );
});
test("fails closed when a changed eligible source is absent from Istanbul", () => {
  withFixture(
    {
      baseSource: "const value = 1;\n",
      changedSource: "const value = 2;\n",
      includeIstanbul: false,
    },
    (fixture) => {
      assert.throws(
        () =>
          prepareDiffCoverage({
            repoRoot: fixture.root,
            baseRef: "base",
            outputPath: fixture.normalizedPath,
          }),
        /Istanbul report is missing changed eligible source/u,
      );
    },
  );
});

test("CI runs the preflight before strict diff-cover and keeps provenance on raw reports", () => {
  const candidateWorkflow = process.env.FRONTEND_DIFF_COVERAGE_WORKFLOW;
  const workflowPath =
    candidateWorkflow ||
    path.join(
      repositoryRoot,
      ".github",
      "workflows",
      "reusable-frontend-tests.yml",
    );
  const workflow = fs.readFileSync(workflowPath, "utf8");
  const preflight = workflow.indexOf(
    "node scripts/quality/verify_frontend_diff_coverage.mjs",
  );
  const diffCover = workflow.indexOf('uv run diff-cover "$normalizedLcov"');
  assert.notEqual(preflight, -1);
  assert.ok(diffCover > preflight);
  assert.match(workflow, /--fail-under=100/u);
  assert.match(workflow, /frontend\/coverage\/lcov\.info/u);
  assert.match(workflow, /frontend\/coverage\/coverage-final\.json/u);
  assert.match(
    workflow,
    /finally \{[\s\S]*Remove-Item -LiteralPath \$normalizedLcov/u,
  );
});

test("bounds the changed-file query and disables external diff and textconv", () => {
  const helperPath = path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "..",
    "scripts",
    "quality",
    "verify_frontend_diff_coverage.mjs",
  );
  const helper = fs.readFileSync(helperPath, "utf8");
  assert.match(helper, /const GIT_COMMAND_TIMEOUT_MS = 30_000/u);
  assert.match(helper, /timeout: GIT_COMMAND_TIMEOUT_MS/u);
  assert.equal((helper.match(/"--no-ext-diff"/gu) || []).length, 1);
  assert.equal((helper.match(/"--no-textconv"/gu) || []).length, 1);
  assert.match(helper, /"--diff-filter=AMT"/u);
});

test("checks dependency and fetch status and reserves a fresh normalized path before cleanup", () => {
  const candidateWorkflow = process.env.FRONTEND_DIFF_COVERAGE_WORKFLOW;
  const workflowPath =
    candidateWorkflow ||
    path.join(
      repositoryRoot,
      ".github",
      "workflows",
      "reusable-frontend-tests.yml",
    );
  const workflow = fs.readFileSync(workflowPath, "utf8");
  const coverageStart = workflow.indexOf(
    "- name: Check differential frontend coverage",
  );
  const coverageStep = workflow.slice(
    coverageStart,
    workflow.indexOf("- name:", coverageStart + 1),
  );
  assert.match(
    coverageStep,
    /uv sync --frozen\r?\n\s+if \(\$LASTEXITCODE -ne 0\) \{ throw "Frontend diff coverage dependency sync failed\." \}/u,
  );
  const fetch = workflow.indexOf("git fetch origin $env:COMPARE_BRANCH");
  const fetchCheck = workflow.indexOf(
    'if ($LASTEXITCODE -ne 0) { throw "Failed to fetch frontend diff coverage comparison branch." }',
    fetch,
  );
  const target = workflow.indexOf("$normalizedLcov = Join-Path", fetchCheck);
  const guid = workflow.indexOf('[guid]::NewGuid().ToString("N")', target);
  const collisionCheck = workflow.indexOf(
    'if (Test-Path -LiteralPath $normalizedLcov) { throw "Refusing to overwrite a pre-existing normalized LCOV path." }',
    target,
  );
  const cleanupScope = workflow.indexOf("try {", collisionCheck);
  const cleanup = workflow.indexOf(
    "Remove-Item -LiteralPath $normalizedLcov -Force",
    cleanupScope,
  );
  assert.notEqual(fetch, -1);
  assert.ok(fetchCheck > fetch);
  assert.ok(target > fetchCheck);
  assert.ok(guid > target);
  assert.ok(collisionCheck > guid);
  assert.ok(cleanupScope > collisionCheck);
  assert.ok(cleanup > cleanupScope);
});
