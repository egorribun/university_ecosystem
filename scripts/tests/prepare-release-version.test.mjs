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

for (const version of ["2.3.4-nightly.1", "2.3.4-feature-x"]) {
  test(`rejects Python-incompatible ${version} before writing any target`, () => {
    const root = createFixture();
    try {
      const targets = [
        path.join(root, "frontend", "package.json"),
        path.join(root, "frontend", "package-lock.json"),
        path.join(root, "pyproject.toml"),
        path.join(root, "app", "core", "versioning.py"),
      ];
      const originals = targets.map((target) => readFileSync(target, "utf8"));

      assert.throws(() => prepareReleaseVersion(root, version));

      for (const [index, target] of targets.entries()) {
        assert.equal(readFileSync(target, "utf8"), originals[index]);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
}

test("preserves stable release versions across all four targets", () => {
  const root = createFixture();
  try {
    prepareReleaseVersion(root, "2.3.4");

    const packageDocument = JSON.parse(
      readFileSync(path.join(root, "frontend", "package.json"), "utf8"),
    );
    const lockDocument = JSON.parse(
      readFileSync(path.join(root, "frontend", "package-lock.json"), "utf8"),
    );
    assert.equal(packageDocument.version, "2.3.4");
    assert.equal(lockDocument.version, "2.3.4");
    assert.equal(lockDocument.packages[""].version, "2.3.4");
    assert.match(
      readFileSync(path.join(root, "pyproject.toml"), "utf8"),
      /^version = "2\.3\.4"$/mu,
    );
    assert.match(
      readFileSync(path.join(root, "app", "core", "versioning.py"), "utf8"),
      /^API_VERSION: Final\[str\] = "2\.3\.4"$/mu,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

for (const version of [
  "2.3.4-alpha",
  "2.3.4-alpha.1",
  "2.3.4-a1",
  "2.3.4-beta.2",
  "2.3.4-b2",
  "2.3.4-RC.1",
  "2.3.4-preview.1",
  "2.3.4-pre.1",
  "2.3.4-c1",
  "2.3.4-post.2",
  "2.3.4-rev.2",
  "2.3.4-r2",
  "2.3.4-1",
  "2.3.4-dev.3",
  "2.3.4-rc.1.post.2.dev.3",
  "2.3.4+build.7",
  "2.3.4+linux-x86.7",
  "2.3.4-rc.1+build.7",
]) {
  test(`preserves compatible release form ${version} without normalization`, () => {
    const root = createFixture();
    try {
      prepareReleaseVersion(root, version);

      const packageDocument = JSON.parse(
        readFileSync(path.join(root, "frontend", "package.json"), "utf8"),
      );
      const lockDocument = JSON.parse(
        readFileSync(path.join(root, "frontend", "package-lock.json"), "utf8"),
      );
      assert.equal(packageDocument.version, version);
      assert.equal(lockDocument.version, version);
      assert.equal(lockDocument.packages[""].version, version);
      assert.equal(
        readFileSync(path.join(root, "pyproject.toml"), "utf8"),
        `[project]\nversion = "${version}"\n`,
      );
      assert.equal(
        readFileSync(path.join(root, "app", "core", "versioning.py"), "utf8"),
        `from typing import Final\n\nAPI_VERSION: Final[str] = "${version}"\n`,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
}

for (const [version, message] of [
  ["2.3.4-rc.foo", "Python package metadata"],
  ["2.3.4-alpha.1.extra", "Python package metadata"],
  ["2.3.4-dev.1.post.2", "Python package metadata"],
  ["2.3.4+-build", "Python package metadata"],
  ["2.3.4+build-", "Python package metadata"],
  ["2.3.4+build--7", "Python package metadata"],
  ["2.3.4+build.-7", "Python package metadata"],
  ["2.3.4\n", "Invalid semantic version"],
  ["2.3", "Invalid semantic version"],
  ["v2.3.4", "Invalid semantic version"],
  ["1!2.3.4", "Invalid semantic version"],
  ["2.3.4rc1", "Invalid semantic version"],
  ["2.3.4+build_7", "Invalid semantic version"],
  ["02.3.4", "Invalid semantic version"],
  ["2.3.4+build..7", "Invalid semantic version"],
]) {
  test(`rejects incompatible version ${JSON.stringify(version)} before any write`, () => {
    const root = createFixture();
    try {
      const targets = [
        path.join(root, "frontend", "package.json"),
        path.join(root, "frontend", "package-lock.json"),
        path.join(root, "pyproject.toml"),
        path.join(root, "app", "core", "versioning.py"),
      ];
      const originals = targets.map((target) => readFileSync(target, "utf8"));

      assert.throws(
        () => prepareReleaseVersion(root, version),
        (error) => error instanceof Error && error.message.includes(message),
      );

      for (const [index, target] of targets.entries()) {
        assert.equal(readFileSync(target, "utf8"), originals[index]);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
}
