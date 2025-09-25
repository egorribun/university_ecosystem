const isLocal = (process.env.PREVIEW_URL || '').startsWith('http://127.0.0.1');

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: [process.env.PREVIEW_URL].filter(Boolean),
      settings: {
        preset: 'desktop',
      },
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.82 }],
        'categories:pwa': isLocal ? 'off' : ['warn', { minScore: 0.8 }],
        'first-contentful-paint': [
          'error',
          { maxNumericValue: 2500, aggregationMethod: 'optimistic' },
        ],
        'largest-contentful-paint': [
          'error',
          { maxNumericValue: 4000, aggregationMethod: 'optimistic' },
        ],
        'total-blocking-time': [
          'error',
          { maxNumericValue: 300, aggregationMethod: 'median' },
        ],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
