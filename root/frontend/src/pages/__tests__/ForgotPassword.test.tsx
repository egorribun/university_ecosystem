import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { axe } from 'jest-axe';
import ForgotPassword from '../ForgotPassword';
import { routerFutureFlags } from '../../App';

const renderForgot = () =>
  render(
    <MemoryRouter future={routerFutureFlags}>
      <ForgotPassword />
    </MemoryRouter>,
  );

describe('ForgotPassword page', () => {
  it('shows validation message for malformed email', async () => {
    const user = userEvent.setup();
    renderForgot();

    const emailInput = screen.getByLabelText(/e-mail/i);
    await user.type(emailInput, 'invalid');
    await user.tab();

    expect(screen.getByText('Неверный формат email')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /отправить ссылку/i })).toBeDisabled();
  });

  it('confirms submission and starts cooldown', async () => {
    const user = userEvent.setup();
    renderForgot();

    await user.type(screen.getByLabelText(/e-mail/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /отправить ссылку/i }));

    expect(await screen.findByText(/если аккаунт с адресом/i)).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: /ввести другой адрес/i });
    expect(retryButton).toBeDisabled();
    expect(retryButton.textContent).toMatch(/\d+s/);
  });

  it('is accessible for assistive technologies', async () => {
    const { container } = renderForgot();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
