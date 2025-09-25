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
        'categories:performance': ['error', { minScore: 0.9 }],
        'categories:pwa': ['error', { minScore: 0.8 }],
        'first-contentful-paint': [
          'error',
          { maxNumericValue: 2000, aggregationMethod: 'optimistic' },
        ],
        'largest-contentful-paint': [
          'error',
          { maxNumericValue: 3500, aggregationMethod: 'optimistic' },
        ],
        'total-blocking-time': [
          'error',
          { maxNumericValue: 250, aggregationMethod: 'median' },
        ],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
