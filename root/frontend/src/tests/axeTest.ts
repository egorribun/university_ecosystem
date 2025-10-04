import { render } from "@testing-library/react";
import { configureAxe } from "jest-axe";
import type { ReactElement } from "react";
import type { RunOptions } from "axe-core";

const axe = configureAxe({
  rules: {
    "document-title": { enabled: false },
    "html-has-lang": { enabled: false },
    "landmark-one-main": { enabled: false },
  },
});

type RenderConfig = Parameters<typeof render>[1];
type RenderWrapper = RenderConfig extends { wrapper?: infer W } ? W : never;

type RenderWithAxeOptions = {
  axeOptions?: RunOptions;
  wrapper?: RenderWrapper;
};

export async function checkA11y(
  container: HTMLElement,
  options?: RunOptions,
) {
  const results = await axe(container, options);
  expect(results).toHaveNoViolations();
  return results;
}

export async function renderWithA11y(
  ui: ReactElement,
  options: RenderWithAxeOptions = {},
) {
  const renderResult = render(ui, { wrapper: options.wrapper });
  await checkA11y(renderResult.container, options.axeOptions);
  return renderResult;
}
