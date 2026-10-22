import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";

const MAX_REPORT_BYTES = 128 * 1024 * 1024;
const GIT_COMMAND_TIMEOUT_MS = 30_000;
const require = createRequire(
  path.join(process.cwd(), "frontend", "package.json"),
);
const { createCoverageMap } = require("istanbul-lib-coverage");
const micromatch = require("micromatch");

function fail(message) {
  throw new Error(message);
}

function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function readBounded(filePath, label, repoRoot) {
  const actualPath = fs.realpathSync(filePath);
  const relative = path.relative(repoRoot, actualPath);
  if (
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    fail(`${label} resolves outside the repository`);
  }
  const stat = fs.statSync(actualPath);
  if (!stat.isFile() || stat.size > MAX_REPORT_BYTES) {
    fail(`${label} is not a regular file within the report-size limit`);
  }
  const bytes = fs.readFileSync(actualPath);
  if (bytes.length !== stat.size || bytes.length > MAX_REPORT_BYTES) {
    fail(`${label} changed while it was being read`);
  }
  return bytes;
}
function repoRelativeSource(rawSource, repoRoot, label) {
  if (
    typeof rawSource !== "string" ||
    rawSource.length === 0 ||
    /[\u0000-\u001f]/u.test(rawSource)
  ) {
    fail(`${label} has an invalid source path`);
  }
  const source = rawSource.replaceAll("\\", "/");
  if (!path.posix.isAbsolute(source) && source.split("/").includes("..")) {
    fail(`${label} source contains a parent traversal`);
  }
  let relative;
  if (path.posix.isAbsolute(source) || path.win32.isAbsolute(source)) {
    const absolute = path.resolve(source);
    relative = path.relative(repoRoot, absolute).replaceAll("\\", "/");
    if (
      relative === ".." ||
      relative.startsWith("../") ||
      path.isAbsolute(relative)
    ) {
      fail(`${label} source is outside the repository`);
    }
  } else if (source.startsWith("frontend/")) {
    relative = path.posix.normalize(source);
  } else if (source.startsWith("src/")) {
    // Vitest writes LCOV paths relative to frontend/, while Git diffs are repo-root-relative.
    relative = path.posix.normalize(`frontend/${source}`);
  } else {
    fail(`${label} source is not rooted at frontend/`);
  }
  if (
    !relative.startsWith("frontend/") ||
    relative === ".." ||
    relative.startsWith("../") ||
    relative.startsWith("/")
  ) {
    fail(`${label} source escapes the repository`);
  }
  return relative;
}

function policyFor(policyBytes) {
  let document;
  try {
    document = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(policyBytes),
    );
  } catch {
    fail("frontend source policy is not valid UTF-8 JSON");
  }
  if (
    document === null ||
    typeof document !== "object" ||
    Array.isArray(document) ||
    Object.keys(document).length !== 1 ||
    !Object.hasOwn(document, "frontend")
  ) {
    fail("frontend source policy has an unexpected root shape");
  }
  const frontend = document.frontend;
  if (
    frontend === null ||
    typeof frontend !== "object" ||
    Array.isArray(frontend) ||
    Object.keys(frontend).length !== 2 ||
    !Array.isArray(frontend.include) ||
    !Array.isArray(frontend.exclude) ||
    frontend.include.length === 0 ||
    frontend.exclude.length === 0
  ) {
    fail("frontend source policy has an unexpected frontend shape");
  }
  for (const pattern of [...frontend.include, ...frontend.exclude]) {
    if (
      typeof pattern !== "string" ||
      pattern.length === 0 ||
      pattern.includes("\\") ||
      pattern.startsWith("/") ||
      pattern.split("/").includes("..") ||
      /[\u0000-\u001f]/u.test(pattern)
    ) {
      fail("frontend source policy contains an unsafe glob");
    }
  }
  return frontend;
}

function isEligibleFrontendSource(repoPath, policy) {
  if (!repoPath.startsWith("frontend/")) return false;
  const relative = repoPath.slice("frontend/".length);
  const options = process.platform === "win32" ? { nocase: true } : undefined;
  return (
    micromatch.isMatch(relative, policy.include, options) &&
    !micromatch.isMatch(relative, policy.exclude, options)
  );
}

function git(repoRoot, args, encoding = "utf8") {
  return execFileSync("git", ["-C", repoRoot, ...args], {
    encoding,
    maxBuffer: 32 * 1024 * 1024,
    stdio: ["ignore", "pipe", "pipe"],
    timeout: GIT_COMMAND_TIMEOUT_MS,
  });
}

function changedFiles(repoRoot, baseRef) {
  if (
    typeof baseRef !== "string" ||
    !/^[A-Za-z0-9._/-]+$/u.test(baseRef) ||
    baseRef.includes("..") ||
    baseRef.startsWith("-") ||
    baseRef.endsWith("/")
  ) {
    fail("comparison base is not a valid ref token");
  }
  const raw = git(
    repoRoot,
    [
      "diff",
      "--no-ext-diff",
      "--no-textconv",
      "--name-only",
      "--diff-filter=AMT",
      "--no-renames",
      "-z",
      `${baseRef}...HEAD`,
      "--",
    ],
    "buffer",
  );
  return raw
    .toString("utf8")
    .split("\0")
    .filter(Boolean)
    .map((item) => {
      if (
        item.includes("\\") ||
        item.startsWith("/") ||
        item.split("/").includes("..")
      ) {
        fail("Git returned an unsafe changed path");
      }
      return item;
    });
}

function parseLcov(bytes, repoRoot) {
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    fail("frontend LCOV report is not valid UTF-8");
  }
  const records = new Map();
  const normalizedLines = [];
  let source = null;
  let lineHits = null;
  let branchHits = null;
  for (const line of text.split(/\r?\n/u)) {
    if (line.startsWith("SF:")) {
      if (source !== null)
        fail("LCOV source record has more than one SF field");
      source = repoRelativeSource(line.slice(3), repoRoot, "LCOV");
      lineHits = new Map();
      branchHits = new Map();
      normalizedLines.push(`SF:${source}`);
      continue;
    }
    normalizedLines.push(line);
    if (line.startsWith("DA:")) {
      if (source === null || lineHits === null)
        fail("LCOV DA field precedes SF");
      const match = /^DA:([1-9][0-9]*),(0|[1-9][0-9]*)(?:,.*)?$/u.exec(line);
      if (!match) fail("LCOV DA field is malformed");
      const number = Number(match[1]);
      const hits = Number(match[2]);
      if (
        !Number.isSafeInteger(number) ||
        !Number.isSafeInteger(hits) ||
        lineHits.has(number)
      ) {
        fail("LCOV DA field is duplicated or exceeds the safe integer range");
      }
      lineHits.set(number, hits);
    }
    if (line.startsWith("BRDA:")) {
      if (source === null || branchHits === null)
        fail("LCOV BRDA field precedes SF");
      const match =
        /^BRDA:([1-9][0-9]*),([A-Za-z0-9._-]+),(0|[1-9][0-9]*),(-|0|[1-9][0-9]*)$/u.exec(
          line,
        );
      if (!match) fail("LCOV BRDA field is malformed");
      const lineNumber = Number(match[1]);
      const branch = Number(match[3]);
      const hits = match[4] === "-" ? null : Number(match[4]);
      if (
        !Number.isSafeInteger(lineNumber) ||
        !Number.isSafeInteger(branch) ||
        (hits !== null && !Number.isSafeInteger(hits))
      ) {
        fail("LCOV BRDA field exceeds the safe integer range");
      }
      const key = `${lineNumber}\0${match[2]}\0${branch}`;
      if (branchHits.has(key)) fail("LCOV BRDA field is duplicated");
      branchHits.set(key, { line: lineNumber, block: match[2], branch, hits });
    }
    if (line === "end_of_record") {
      if (source === null || lineHits === null || branchHits === null) {
        fail("LCOV record has no source");
      }
      if (records.has(source))
        fail("LCOV contains duplicate normalized source records");
      records.set(source, { lines: lineHits, branches: branchHits });
      source = null;
      lineHits = null;
      branchHits = null;
    }
  }
  if (source !== null || lineHits !== null || branchHits !== null) {
    fail("LCOV report ends inside a source record");
  }
  if (records.size === 0) fail("LCOV report contains no source records");
  return { records, normalized: `${normalizedLines.join("\n")}` };
}

function istanbulCoverageMaps(bytes, repoRoot) {
  let document;
  try {
    document = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(bytes),
    );
  } catch {
    fail("Istanbul report is not valid UTF-8 JSON");
  }
  if (
    document === null ||
    typeof document !== "object" ||
    Array.isArray(document) ||
    Object.keys(document).length === 0
  ) {
    fail("Istanbul report contains no source records");
  }
  let coverageMap;
  try {
    coverageMap = createCoverageMap(document);
  } catch {
    fail("Istanbul report cannot be parsed by istanbul-lib-coverage");
  }
  const files = new Map();
  for (const key of coverageMap.files()) {
    const fileCoverage = coverageMap.fileCoverageFor(key);
    const source = repoRelativeSource(
      fileCoverage.path || key,
      repoRoot,
      "Istanbul",
    );
    if (files.has(source))
      fail("Istanbul contains duplicate normalized source records");
    const lineCoverage = fileCoverage.getLineCoverage();
    const lines = new Map();
    for (const [rawLine, rawHits] of Object.entries(lineCoverage)) {
      const number = Number(rawLine);
      if (
        !Number.isSafeInteger(number) ||
        number < 1 ||
        !Number.isSafeInteger(rawHits) ||
        rawHits < 0
      ) {
        fail("Istanbul line coverage has an invalid line or hit count");
      }
      lines.set(number, rawHits);
    }
    const rawBranches = fileCoverage.b;
    const rawBranchMap = fileCoverage.branchMap;
    if (
      rawBranches === null ||
      typeof rawBranches !== "object" ||
      Array.isArray(rawBranches) ||
      rawBranchMap === null ||
      typeof rawBranchMap !== "object" ||
      Array.isArray(rawBranchMap)
    ) {
      fail("Istanbul branch coverage has an invalid shape");
    }
    const branches = new Map();
    const branchKeys = Object.keys(rawBranches);
    const metadataKeys = Object.keys(rawBranchMap);
    if (
      branchKeys.length !== metadataKeys.length ||
      metadataKeys.some((key) => !Object.hasOwn(rawBranches, key))
    ) {
      fail("Istanbul branch counters and metadata disagree");
    }
    for (const key of branchKeys) {
      const hits = rawBranches[key];
      const metadata = rawBranchMap[key];
      if (
        !metadata ||
        typeof metadata !== "object" ||
        !metadata.loc?.start ||
        !Array.isArray(metadata.locations) ||
        !Array.isArray(hits) ||
        metadata.locations.length !== hits.length
      ) {
        fail("Istanbul branch metadata and counters disagree");
      }
      const line = metadata.loc.start.line;
      if (
        !Number.isSafeInteger(line) ||
        line < 1 ||
        !/^[A-Za-z0-9._-]+$/u.test(key)
      ) {
        fail("Istanbul branch metadata has an invalid line or identifier");
      }
      for (let branch = 0; branch < hits.length; branch += 1) {
        const count = hits[branch];
        if (!Number.isSafeInteger(count) || count < 0) {
          fail("Istanbul branch coverage has an invalid hit count");
        }
        const branchKey = `${line}\0${key}\0${branch}`;
        if (branches.has(branchKey))
          fail("Istanbul branch coverage is duplicated");
        branches.set(branchKey, { line, block: key, branch, hits: count });
      }
    }
    files.set(source, { lines, branches });
  }
  return files;
}

export function prepareDiffCoverage({ repoRoot, baseRef, outputPath }) {
  const root = fs.realpathSync(repoRoot);
  const requestedOutput = path.resolve(outputPath);
  const outputParent = fs.realpathSync(path.dirname(requestedOutput));
  const output = path.join(outputParent, path.basename(requestedOutput));
  const relativeOutput = path.relative(root, output);
  if (
    relativeOutput === ".." ||
    relativeOutput.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativeOutput)
  ) {
    // The normalized copy is temporary evidence, never an artifact/provenance input.
  } else {
    fail("normalized LCOV output must be outside the repository");
  }
  const lcovPath = path.join(root, "frontend", "coverage", "lcov.info");
  const istanbulPath = path.join(
    root,
    "frontend",
    "coverage",
    "coverage-final.json",
  );
  const policyPath = path.join(root, "quality", "coverage-source-policy.json");
  const lcovBytes = readBounded(lcovPath, "LCOV report", root);
  const istanbulBytes = readBounded(istanbulPath, "Istanbul report", root);
  const policyBytes = readBounded(policyPath, "frontend source policy", root);
  const policy = policyFor(policyBytes);
  const lcov = parseLcov(lcovBytes, root);
  const istanbul = istanbulCoverageMaps(istanbulBytes, root);
  const candidates = changedFiles(root, baseRef).filter((source) =>
    isEligibleFrontendSource(source, policy),
  );
  for (const source of candidates) {
    const fileCoverage = istanbul.get(source);
    if (!fileCoverage)
      fail(`Istanbul report is missing changed eligible source: ${source}`);
    const lcovCoverage = lcov.records.get(source);
    if (!lcovCoverage)
      fail(`LCOV report is missing changed eligible source: ${source}`);
    for (const [line, hits] of fileCoverage.lines) {
      if (!lcovCoverage.lines.has(line)) {
        fail(`LCOV is missing an Istanbul executable line for ${source}`);
      }
      if (lcovCoverage.lines.get(line) !== hits) {
        fail(`LCOV and Istanbul line counts disagree for ${source}`);
      }
    }
    for (const line of lcovCoverage.lines.keys()) {
      if (!fileCoverage.lines.has(line))
        fail(`LCOV reports a line absent from Istanbul for ${source}`);
    }
    for (const [key, branch] of fileCoverage.branches) {
      if (!lcovCoverage.branches.has(key)) {
        fail(`LCOV is missing an Istanbul branch outcome for ${source}`);
      }
      if (lcovCoverage.branches.get(key).hits !== branch.hits) {
        fail(`LCOV and Istanbul branch counts disagree for ${source}`);
      }
    }
    for (const key of lcovCoverage.branches.keys()) {
      if (!fileCoverage.branches.has(key)) {
        fail(`LCOV reports a branch absent from Istanbul for ${source}`);
      }
    }
  }
  if (
    digest(readBounded(lcovPath, "LCOV report", root)) !== digest(lcovBytes) ||
    digest(readBounded(istanbulPath, "Istanbul report", root)) !==
      digest(istanbulBytes) ||
    digest(readBounded(policyPath, "frontend source policy", root)) !==
      digest(policyBytes)
  ) {
    fail("coverage inputs changed during differential verification");
  }
  fs.writeFileSync(output, lcov.normalized, { flag: "wx" });
  return {
    eligibleFiles: candidates.length,
    lcovSha256: digest(lcovBytes),
    istanbulSha256: digest(istanbulBytes),
    policySha256: digest(policyBytes),
    outputPath: output,
  };
}

function parseArguments(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (!flag?.startsWith("--") || !value || Object.hasOwn(parsed, flag))
      fail("invalid helper arguments");
    parsed[flag] = value;
  }
  if (
    Object.keys(parsed).length !== 3 ||
    !parsed["--repo-root"] ||
    !parsed["--base-ref"] ||
    !parsed["--output"]
  ) {
    fail("expected --repo-root, --base-ref, and --output");
  }
  return parsed;
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const args = parseArguments(process.argv.slice(2));
    const result = prepareDiffCoverage({
      repoRoot: args["--repo-root"],
      baseRef: args["--base-ref"],
      outputPath: args["--output"],
    });
    console.log(
      JSON.stringify({
        eligible_changed_files: result.eligibleFiles,
        lcov_sha256: result.lcovSha256,
        istanbul_sha256: result.istanbulSha256,
        source_policy_sha256: result.policySha256,
      }),
    );
  } catch (error) {
    console.error(
      error instanceof Error
        ? error.message
        : "frontend diff coverage preflight failed",
    );
    process.exitCode = 1;
  }
}
