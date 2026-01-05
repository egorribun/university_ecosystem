const {execSync} = require('node:child_process');
const path = require('node:path');

const frontendDir = path.join(__dirname, 'frontend');
const chromePath = path.join(frontendDir, 'node_modules', '.bin', 'google-chrome-stable');
const buildEnv = {...process.env, FORCE_COLOR: '0', CI: '1'};

if (!process.env.LHCI_SKIP_PREPARE) {
  execSync('npx playwright install-deps chromium', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
  execSync('npm run build -- --logLevel error', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
  execSync('node scripts/prepare-lhci-routes.mjs', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
}

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      staticDistDir: 'dist',
      chromePath,
      settings: {
        chromeFlags:
          '--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type',
        chromePath,
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
    assert: {
      assertions: {
        'categories:performance': ['error', {minScore: 0.8}],
        'categories:accessibility': ['error', {minScore: 0.8}],
        'categories:best-practices': ['error', {minScore: 0.8}],
        'categories:seo': ['error', {minScore: 0.8}],
        'total-blocking-time': ['warn', {maxNumericValue: 435, aggregationMethod: 'median'}],
      },
    },
  },
};
