#!/usr/bin/env node
'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

const frontendDir = path.join(__dirname, '..');
const binDir = path.join(frontendDir, 'node_modules', '.bin');
const wrapper = path.join(__dirname, 'google-chrome-stable.cjs');
const localCandidates = ['google-chrome-stable', 'google-chrome', 'chromium', 'chromium-browser'];
const globalCandidates = [
  '/usr/bin/google-chrome-stable',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
];

async function ensureLocalSymlink(targetName) {
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

async function ensureGlobalSymlink(targetPath) {
  try {
    const stats = await fs.lstat(targetPath);
    if (!stats.isSymbolicLink()) {
      return;
    }

    const existing = await fs.readlink(targetPath);
    if (existing === wrapper) {
      return;
    }

    return;
  } catch (error) {
    if (!error || error.code !== 'ENOENT') {
      return;
    }
  }

  try {
    await fs.symlink(wrapper, targetPath);
  } catch (error) {
    if (!error) {
      return;
    }

    if (error.code === 'EEXIST' || error.code === 'EACCES' || error.code === 'EPERM') {
      return;
    }

    throw error;
  }
}

async function main() {
  await fs.mkdir(binDir, { recursive: true });
  await Promise.all(localCandidates.map(ensureLocalSymlink));
  await Promise.all(globalCandidates.map(ensureGlobalSymlink));
}

main().catch(error => {
  const message = error && typeof error === 'object' && 'message' in error ? error.message : String(error);
  console.error('Failed to set up Lighthouse Chromium wrapper binaries:', message);
  process.exit(1);
});
