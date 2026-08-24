import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SEMVER_PATTERN =
  /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/u;

function replaceExactlyOnce(content, pattern, replacement, label) {
  const matches = [...content.matchAll(pattern)];
  if (matches.length !== 1) {
    throw new Error(
      `${label}: expected exactly one version declaration, found ${matches.length}`,
    );
  }
  return content.replace(pattern, replacement);
}

function updatePackageDocument(
  content,
  version,
  label,
  includeLockRoot = false,
) {
  const document = JSON.parse(content);
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error(`${label}: expected a JSON object`);
  }
  if (typeof document.version !== "string") {
    throw new Error(`${label}: top-level version is missing`);
  }
  document.version = version;

  if (includeLockRoot) {
    const lockRoot = document.packages?.[""];
    if (!lockRoot || typeof lockRoot.version !== "string") {
      throw new Error(`${label}: packages[\"\"].version is missing`);
    }
    lockRoot.version = version;
  }

  return `${JSON.stringify(document, null, 2)}\n`;
}

export function prepareReleaseVersion(repositoryRoot, version) {
  if (!SEMVER_PATTERN.test(version)) {
    throw new Error(`Invalid semantic version: ${version}`);
  }

  const targets = {
    frontendPackage: path.join(repositoryRoot, "frontend", "package.json"),
    frontendLock: path.join(repositoryRoot, "frontend", "package-lock.json"),
    pythonProject: path.join(repositoryRoot, "pyproject.toml"),
    apiVersion: path.join(repositoryRoot, "app", "core", "versioning.py"),
  };
  const original = Object.fromEntries(
    Object.entries(targets).map(([name, targetPath]) => [
      name,
      readFileSync(targetPath, "utf8"),
    ]),
  );

  const updated = {
    frontendPackage: updatePackageDocument(
      original.frontendPackage,
      version,
      "frontend/package.json",
    ),
    frontendLock: updatePackageDocument(
      original.frontendLock,
      version,
      "frontend/package-lock.json",
      true,
    ),
    pythonProject: replaceExactlyOnce(
      original.pythonProject,
      /^version = "[^"\r\n]+"$/gmu,
      `version = "${version}"`,
      "pyproject.toml",
    ),
    apiVersion: replaceExactlyOnce(
      original.apiVersion,
      /^API_VERSION: Final\[str\] = "[^"\r\n]+"$/gmu,
      `API_VERSION: Final[str] = "${version}"`,
      "app/core/versioning.py",
    ),
  };

  for (const [name, targetPath] of Object.entries(targets)) {
    writeFileSync(targetPath, updated[name], "utf8");
  }
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : null;
if (invokedPath === fileURLToPath(import.meta.url)) {
  const version = process.argv[2];
  if (!version) {
    console.error("Usage: node scripts/prepare-release-version.mjs <semver>");
    process.exit(2);
  }
  prepareReleaseVersion(process.cwd(), version);
  console.log(`Prepared release version ${version}.`);
}
