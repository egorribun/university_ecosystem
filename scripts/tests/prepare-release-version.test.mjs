import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { prepareReleaseVersion } from "../prepare-release-version.mjs";

function createFixture() {
  const root = mkdtempSync(path.join(os.tmpdir(), "prepare-release-version-"));
  mkdirSync(path.join(root, "frontend"), { recursive: true });
  mkdirSync(path.join(root, "app", "core"), { recursive: true });
  writeFileSync(
    path.join(root, "frontend", "package.json"),
    `${JSON.stringify({ name: "frontend", version: "1.0.0" }, null, 2)}\n`,
  );
  writeFileSync(
    path.join(root, "frontend", "package-lock.json"),
    `${JSON.stringify(
      {
        name: "frontend",
        version: "1.0.0",
        lockfileVersion: 3,
        packages: { "": { name: "frontend", version: "1.0.0" } },
      },
      null,
      2,
    )}\n`,
  );
  writeFileSync(
    path.join(root, "pyproject.toml"),
    '[project]\nversion = "1.0.0"\n',
  );
  writeFileSync(
    path.join(root, "app", "core", "versioning.py"),
    'from typing import Final\n\nAPI_VERSION: Final[str] = "1.0.0"\n',
  );
  return root;
}

test("updates every release version source consistently", () => {
  const root = createFixture();
  try {
    prepareReleaseVersion(root, "2.3.4-rc.1");

    const packageDocument = JSON.parse(
      readFileSync(path.join(root, "frontend", "package.json"), "utf8"),
    );
    const lockDocument = JSON.parse(
      readFileSync(path.join(root, "frontend", "package-lock.json"), "utf8"),
    );
    assert.equal(packageDocument.version, "2.3.4-rc.1");
    assert.equal(lockDocument.version, "2.3.4-rc.1");
    assert.equal(lockDocument.packages[""].version, "2.3.4-rc.1");
    assert.match(
      readFileSync(path.join(root, "pyproject.toml"), "utf8"),
      /^version = "2\.3\.4-rc\.1"$/mu,
    );
    assert.match(
      readFileSync(path.join(root, "app", "core", "versioning.py"), "utf8"),
      /^API_VERSION: Final\[str\] = "2\.3\.4-rc\.1"$/mu,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("rejects invalid semantic versions before touching files", () => {
  const root = createFixture();
  const originalPackage = readFileSync(
    path.join(root, "frontend", "package.json"),
    "utf8",
  );
  try {
    assert.throws(
      () => prepareReleaseVersion(root, "2.3"),
      /Invalid semantic version/u,
    );
    assert.equal(
      readFileSync(path.join(root, "frontend", "package.json"), "utf8"),
      originalPackage,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("fails before writing when a version declaration is ambiguous", () => {
  const root = createFixture();
  const packagePath = path.join(root, "frontend", "package.json");
  const originalPackage = readFileSync(packagePath, "utf8");
  writeFileSync(
    path.join(root, "pyproject.toml"),
    '[project]\nversion = "1.0.0"\nversion = "1.0.1"\n',
  );
  try {
    assert.throws(
      () => prepareReleaseVersion(root, "2.3.4"),
      /pyproject\.toml: expected exactly one version declaration/u,
    );
    assert.equal(readFileSync(packagePath, "utf8"), originalPackage);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
