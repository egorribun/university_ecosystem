const base = process.env.PREVIEW_URL || process.env.LHCI_URL || '';
const urls = base ? [base, `${base}/login`] : undefined;

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: urls,
      staticDistDir: urls ? undefined : 'dist',
      settings: {
        preset: 'desktop',
        chromeFlags: '--no-sandbox --disable-dev-shm-usage'
      }
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.82 }],
        'total-blocking-time': ['warn', { maxNumericValue: 435, aggregationMethod: 'median' }]
      }
    },
    upload: { target: 'temporary-public-storage' }
  }
};
