#!/usr/bin/env node
'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');

const frontendDir = path.join(__dirname, '..');

const resolveChromiumExecutable = () => {
  try {
    const playwrightPath = require.resolve('playwright', { paths: [frontendDir] });
    const { chromium } = require(playwrightPath);
    return chromium.executablePath();
  } catch (error) {
    const message = error && typeof error === 'object' && 'message' in error ? error.message : String(error);
    console.error('Unable to locate the Playwright Chromium binary required for Lighthouse runs.');
    console.error('Install it locally by running `npx playwright install chromium` and try again.');
    console.error(message);
    process.exit(1);
  }
};

const chromeExecutable = resolveChromiumExecutable();

const child = spawn(chromeExecutable, process.argv.slice(2), {
  stdio: 'inherit',
  env: process.env,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

child.on('error', error => {
  const message = error && typeof error === 'object' && 'message' in error ? error.message : String(error);
  console.error('Failed to launch Chromium through Playwright:', message);
  process.exit(1);
});
