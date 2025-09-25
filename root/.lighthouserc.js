const base = process.env.LHCI_URL || 'http://127.0.0.1:4173';

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: [`${base}/`, `${base}/login`],
      settings: { preset: 'desktop' }
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.82, aggregationMethod: 'median' }],
        'total-blocking-time': ['error', { maxNumericValue: 450, aggregationMethod: 'median' }],
        'categories:pwa': ['warn', { minScore: 0.8 }]
      },
      assertMatrix: [
        {
          matchingUrlPattern: '/login',
          assertions: {
            'categories:performance': ['warn', { minScore: 0.75, aggregationMethod: 'median' }],
            'total-blocking-time': ['warn', { maxNumericValue: 600, aggregationMethod: 'median' }]
          }
        }
      ]
    },
    upload: { target: 'temporary-public-storage' }
  }
};
