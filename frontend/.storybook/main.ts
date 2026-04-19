import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  // Wave 115 polish — restrict to `src/components/` so the glob doesn't
  // pick up TanStack Router files that happen to match `*.stories.tsx`
  // (e.g. `src/routes/_admin/admin.stories.tsx` — a route file, not a
  // Storybook story). The eslint `storybook/default-exports` rule is
  // also off for `src/routes/` per CLAUDE.md for the same reason.
  "stories": [
    "../src/components/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  "addons": [
    "@chromatic-com/storybook",
    "@storybook/addon-vitest",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-onboarding"
  ],
  "framework": "@storybook/react-vite"
};
export default config;
