# Wave 4 Execution Checklist

- [x] Critical Utilities & Workers
  - [x] Write `src/push/__tests__/registerSw.test.ts` to cover `register-sw.ts`
  - [x] Write `src/push/__tests__/subscribe.test.ts` to cover `subscribe.ts`
  - [x] Write `src/utils/__tests__/cryptoWorker.test.ts` to cover `cryptoWorker.ts`
  - [x] Write `src/utils/__tests__/scrollUtils.test.ts` to cover `scrollUtils.ts`
  - [x] Write `src/utils/__tests__/spotify.test.ts` to cover `spotify.ts`
- [x] Lazy Routes Loader & Integration Tests
  - [x] Write `src/routes/__tests__/routeLoaders.test.tsx` to cover loaders & validateSearch
  - [x] Write `src/routes/__tests__/__root.test.tsx` to cover RootShell & RootComponent
- [x] Bump Vitest Coverage Thresholds
  - [x] Update thresholds in `vitest.config.ts`
- [x] Verification
  - [x] Run `npm run test:ci` to verify overall and component coverage metrics
  - [x] Run `npm run typecheck` and `npm run lint` to verify codebase soundness
