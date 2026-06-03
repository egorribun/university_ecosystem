const {execSync} = require('node:child_process');
const path = require('node:path');

const frontendDir = path.join(__dirname, 'frontend');
const chromePath = path.join(frontendDir, 'node_modules', '.bin', 'google-chrome-stable');
const buildEnv = {...process.env, FORCE_COLOR: '0', CI: '1', VITE_LHCI: 'true'};

if (!process.env.LHCI_SKIP_PREPARE) {
  execSync('npx playwright install-deps chromium', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
  execSync('npm run build -- --logLevel error', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
  execSync('node scripts/prepare-lhci-routes.mjs', {cwd: frontendDir, stdio: 'inherit', env: buildEnv});
}

module.exports = {
  ci: {
    collect: {
      url: ['/'],
      numberOfRuns: 3,
      staticDistDir: path.join(__dirname, 'frontend/dist'),
      isSinglePageApplication: true,
      chromePath,
      settings: {
        budgetsPath: path.join(__dirname, 'budget.json'),
        chromeFlags:
          '--no-sandbox --disable-dev-shm-usage --allow-insecure-localhost --ignore-certificate-errors --test-type --disable-gpu --headless=new',
        chromePath,
        maxWaitForFcp: 45000,
        maxWaitForLoad: 60000,
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
    assert: {
      assertMatrix: [
        {
          matchingUrlPattern: '.*',
          assertions: {
            budgets: ['error', {budgetPath: 'budget.json'}],
            'largest-contentful-paint': [
              'error',
              {maxNumericValue: 3500, aggregationMethod: 'median'},
            ],
            'total-blocking-time': [
              'error',
              {maxNumericValue: 300, aggregationMethod: 'median'},
            ],
            'cumulative-layout-shift': [
              'error',
              {maxNumericValue: 0.1, aggregationMethod: 'median'},
            ],
            'categories:accessibility': ['error', {minScore: 0.90}],
          },
        },
        {
          matchingUrlPattern: '.*/(schedule|messenger|news)($|\\?|/)',
          assertions: {
            'categories:accessibility': ['error', {minScore: 0.95}],
            'categories:performance': [
              process.env.CI ? 'warn' : 'error',
              {minScore: 0.90},
            ],
          },
        },
      ],
    },
  },
};
