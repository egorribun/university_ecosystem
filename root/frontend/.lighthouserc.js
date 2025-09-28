const base = process.env.PREVIEW_URL || process.env.LHCI_URL || ''
const urls = base ? [base, `${base}/login`] : undefined

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      url: urls,
      staticDistDir: urls ? undefined : 'dist',
      settings: {
        preset: 'desktop',
        chromeFlags: '--no-sandbox --disable-dev-shm-usage',
      },
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.8 }],
        'categories:accessibility': ['error', { minScore: 0.8 }],
        'categories:best-practices': ['error', { minScore: 0.8 }],
        'categories:seo': ['error', { minScore: 0.8 }],
        'total-blocking-time': ['warn', { maxNumericValue: 435, aggregationMethod: 'median' }],
      },
    },
    upload: { target: 'temporary-public-storage' },
  },
}
