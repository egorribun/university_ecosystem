import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

function readJson(relativePath) {
  return JSON.parse(
    readFileSync(path.join(repositoryRoot, relativePath), "utf8"),
  );
}

test("release plugins are explicit, resolvable, and exclude npm publishing", () => {
  const releaseConfig = readJson(".releaserc.json");
  const plugins = releaseConfig.plugins.map((entry) =>
    Array.isArray(entry) ? entry[0] : entry,
  );

  assert.deepEqual(plugins, [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    "@semantic-release/changelog",
    "@semantic-release/exec",
    "@semantic-release/github",
  ]);
  assert.ok(!plugins.includes("@semantic-release/npm"));
  for (const plugin of plugins) {
    assert.doesNotThrow(() => import.meta.resolve(plugin));
  }
});

test("the npm transitive dependency resolves only to the audited local shim", () => {
  const packageDocument = readJson("package.json");
  const lockDocument = readJson("package-lock.json");

  assert.equal(packageDocument.devDependencies.npm, "file:tools/npm-cli-shim");
  assert.equal(packageDocument.overrides.npm, "$npm");
  assert.deepEqual(lockDocument.packages["node_modules/npm"], {
    resolved: "tools/npm-cli-shim",
    link: true,
  });
  assert.equal(
    Object.keys(lockDocument.packages).some((entry) =>
      entry.startsWith("node_modules/npm/node_modules/"),
    ),
    false,
  );
});

test("the token-bearing release step bypasses npm and verifies the toolchain first", () => {
  const workflow = readFileSync(
    path.join(repositoryRoot, ".github", "workflows", "release.yml"),
    "utf8",
  );
  const verifyIndex = workflow.indexOf("run: npm run test:release-toolchain");
  const releaseIndex = workflow.indexOf(
    "run: node node_modules/semantic-release/bin/semantic-release.js",
  );

  assert.ok(
    verifyIndex >= 0,
    "release workflow must verify its local toolchain",
  );
  assert.ok(releaseIndex > verifyIndex, "release must run after verification");
  assert.doesNotMatch(workflow, /run:\s+npx\s+semantic-release/u);
});
