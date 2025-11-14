#!/usr/bin/env node
'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

const frontendDir = path.join(__dirname, '..');
const binDir = path.join(frontendDir, 'node_modules', '.bin');
const wrapper = path.join(__dirname, 'google-chrome-stable.cjs');
const candidates = ['google-chrome-stable', 'google-chrome', 'chromium', 'chromium-browser'];

async function ensureSymlink(targetName) {
  const destination = path.join(binDir, targetName);
  try {
    const existing = await fs.readlink(destination);
    if (existing === wrapper) {
      return;
    }
    await fs.unlink(destination);
  } catch (error) {
    if (error && error.code !== 'ENOENT') {
      throw error;
    }
  }

  await fs.symlink(wrapper, destination);
}

async function main() {
  await fs.mkdir(binDir, { recursive: true });
  await Promise.all(candidates.map(ensureSymlink));
}

main().catch(error => {
  const message = error && typeof error === 'object' && 'message' in error ? error.message : String(error);
  console.error('Failed to set up Lighthouse Chromium wrapper binaries:', message);
  process.exit(1);
});
