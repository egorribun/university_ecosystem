const path = require('node:path');

const LOCAL_PREVIEW_PORT = 4174;
const useRemotePreview = Boolean(process.env.PREVIEW_URL);
const repoRoot = __dirname;
const frontendDir = path.join(repoRoot, 'root', 'frontend');
const budgetPath = path.join(repoRoot, 'budget.json');
const outputDir = path.join(frontendDir, '.lighthouseci');

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: [process.env.PREVIEW_URL || `http://127.0.0.1:${LOCAL_PREVIEW_PORT}/`],
      settings: {
        budgetsPath: budgetPath,
        chromeFlags: '--no-sandbox --disable-dev-shm-usage',
      },
      ...(useRemotePreview
        ? {}
        : {
            startServerCommand:
              `npm run build && npm run preview -- --host 0.0.0.0 --port ${LOCAL_PREVIEW_PORT} --strictPort`,
            startServerReadyPattern: 'Local:',
            startServerReadyTimeout: 120000,
          }),
    },
    upload: {
      target: 'filesystem',
      outputDir,
      reportFilenamePattern: '%%DATETIME%%-%%PATHNAME%%.report.html',
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.9 }],
        'budgets': ['error', { budgetPath }],
        'largest-contentful-paint': [
          'error',
          { maxNumericValue: 3500, aggregationMethod: 'median' },
        ],
        'total-blocking-time': [
          'error',
          { maxNumericValue: 300, aggregationMethod: 'median' },
        ],
        'cumulative-layout-shift': [
          'error',
          { maxNumericValue: 0.1, aggregationMethod: 'median' },
        ],
      },
    },
  },
};
