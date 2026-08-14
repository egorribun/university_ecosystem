#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const shimPath = realpathSync(fileURLToPath(import.meta.url));
const configuredPath = process.env.npm_execpath?.trim();

if (!configuredPath) {
  console.error(
    "npm-cli-shim: npm_execpath is missing; run semantic-release through `npm run release`.",
  );
  process.exit(1);
}

if (!path.isAbsolute(configuredPath)) {
  console.error("npm-cli-shim: npm_execpath must be an absolute path.");
  process.exit(1);
}

let targetPath;
try {
  targetPath = realpathSync(configuredPath);
} catch (error) {
  console.error(`npm-cli-shim: cannot resolve npm_execpath: ${error.message}`);
  process.exit(1);
}

if (targetPath === shimPath) {
  console.error("npm-cli-shim: refusing to invoke itself recursively.");
  process.exit(1);
}

if (!/^npm-cli\.(?:c?js)$/u.test(path.basename(targetPath))) {
  console.error(
    "npm-cli-shim: npm_execpath does not identify an npm CLI entrypoint.",
  );
  process.exit(1);
}

const result = spawnSync(
  process.execPath,
  [targetPath, ...process.argv.slice(2)],
  {
    stdio: "inherit",
    env: process.env,
    windowsHide: true,
  },
);

if (result.error) {
  console.error(`npm-cli-shim: failed to start npm: ${result.error.message}`);
  process.exit(1);
}

if (result.signal) {
  console.error(`npm-cli-shim: npm terminated by signal ${result.signal}.`);
  process.exit(1);
}

process.exit(result.status ?? 1);
