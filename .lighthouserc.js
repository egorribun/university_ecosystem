module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: ['http://127.0.0.1:4174/'],
      beforeAllScript: 'npm --prefix root/frontend run build',
      startServerCommand: 'node root/frontend/scripts/lhci-preview.mjs',
      startServerReadyPattern: 'LHCI_READY',
      startServerReadyTimeout: 120000,
      settings: {
        budgetsPath: 'budget.json',
        chromeFlags: '--no-sandbox --disable-dev-shm-usage',
      },
    },
    upload: {
      target: 'filesystem',
      outputDir: 'root/frontend/.lighthouseci',
      reportFilenamePattern: '%%DATETIME%%-%%PATHNAME%%.report.html',
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.9 }],
        budgets: ['error', { budgetPath: 'budget.json' }],
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
}
