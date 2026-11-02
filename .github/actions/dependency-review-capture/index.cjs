"use strict";

const path = require("node:path");
const { spawnSync } = require("node:child_process");

if (process.env.INPUT_MODE === "test") {
  const result = spawnSync(process.execPath, [
    "--test", "--experimental-test-coverage",
    "--test-coverage-include=" + path.join(__dirname, "capture.cjs"),
    "--test-coverage-include=" + path.join(__dirname, "index.cjs"),
    "--test-coverage-lines=100", "--test-coverage-branches=100",
    "--test-coverage-functions=100",
    path.join(__dirname, "capture.test.cjs"),
  ], { stdio: "inherit", env: process.env });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} else if (process.env.INPUT_MODE === "capture") {
  // Do not catch or replace original action exceptions or asynchronous work.
  require("./capture.cjs").install();
} else {
  throw new Error("Dependency Review capture mode is invalid");
}
