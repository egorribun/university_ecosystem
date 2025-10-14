import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { axe } from 'jest-axe';
import ForgotPassword from '../ForgotPassword';
import { routerFutureFlags } from '../../App';
import i18n from '../../i18n/config';

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options);

const renderForgot = () =>
  render(
    <MemoryRouter future={routerFutureFlags}>
      <ForgotPassword />
    </MemoryRouter>,
  );

const escapeRegExp = (value: string) => value.replace(/[\^$*+?.()|[\]{}-]/g, '\\$&');
const labelRegex = (value: string) => new RegExp(`^${escapeRegExp(value)}`, 'i');

describe('ForgotPassword page', () => {
  it('shows validation message for malformed email', async () => {
    const user = userEvent.setup();
    renderForgot();

    const emailInput = screen.getByLabelText(labelRegex(tAuth('fields.email')));
    await user.type(emailInput, 'invalid');
    await user.tab();

    expect(screen.getByText(tAuth('messages.invalidFormat'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: tAuth('forgot.sendLink') })).toBeDisabled();
  });

  it('confirms submission and starts cooldown', async () => {
    const user = userEvent.setup();
    renderForgot();

    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.email'))), 'user@example.com');
    await user.click(screen.getByRole('button', { name: tAuth('forgot.sendLink') }));

    const successText = tAuth('forgot.success', { email: 'user@example.com' }).replace(/<[^>]+>/g, '');
    const successMessages = await screen.findAllByText((_, element) =>
      element?.textContent?.includes(successText) ?? false,
    );
    expect(successMessages.length).toBeGreaterThan(0);
    const retryButton = screen.getByRole('button', {
      name: new RegExp(`^${escapeRegExp(tAuth('forgot.enterAnother'))}`),
    });
    expect(retryButton).toBeDisabled();
    expect(retryButton.textContent).toMatch(/\d+s/);
  });

  it('is accessible for assistive technologies', async () => {
    const { container } = renderForgot();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
