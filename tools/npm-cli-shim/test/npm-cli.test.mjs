import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const shimPath = fileURLToPath(new URL("../bin/npm-cli.js", import.meta.url));

function invokeShim(args = [], environment = {}) {
  return spawnSync(process.execPath, [shimPath, ...args], {
    encoding: "utf8",
    env: { ...process.env, ...environment },
    windowsHide: true,
  });
}

test("forwards arguments and the target exit status", () => {
  const temporaryDirectory = mkdtempSync(
    path.join(os.tmpdir(), "npm-cli-shim-"),
  );
  const targetPath = path.join(temporaryDirectory, "npm-cli.js");
  writeFileSync(
    targetPath,
    "console.log(JSON.stringify(process.argv.slice(2))); process.exit(23);",
    "utf8",
  );

  try {
    const result = invokeShim(["version", "1.2.3"], {
      npm_execpath: targetPath,
    });
    assert.equal(result.status, 23);
    assert.equal(result.stdout.trim(), '["version","1.2.3"]');
    assert.equal(result.stderr, "");
  } finally {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
});

test("fails closed without npm_execpath", () => {
  const environment = { ...process.env };
  delete environment.npm_execpath;
  const result = spawnSync(process.execPath, [shimPath, "--version"], {
    encoding: "utf8",
    env: environment,
    windowsHide: true,
  });

  assert.equal(result.status, 1);
  assert.match(result.stderr, /npm_execpath is missing/u);
});

test("rejects recursive invocation", () => {
  const result = invokeShim([], { npm_execpath: shimPath });

  assert.equal(result.status, 1);
  assert.match(result.stderr, /refusing to invoke itself recursively/u);
});
