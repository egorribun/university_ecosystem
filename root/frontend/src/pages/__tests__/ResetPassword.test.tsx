import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResetPassword from '../ResetPassword';
import { server } from '@/tests/mocks/server';
import { routerFutureFlags } from '../../App';

vi.mock('zxcvbn', () => ({
  default: () => ({ score: 3, feedback: { warning: '', suggestions: [] } }),
}));

const renderWithToken = () =>
  render(
    <MemoryRouter future={routerFutureFlags} initialEntries={['/reset/token123']}>
      <Routes>
        <Route path="/reset/:token" element={<ResetPassword />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ResetPassword page', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('propagates API errors to the user', async () => {
    server.use(
      http.post('*/password/reset', () => HttpResponse.json({ detail: 'Ссылка устарела' }, { status: 400 })),
    );

    const user = userEvent.setup();
    renderWithToken();

    await user.type(screen.getByLabelText(/^пароль$/i), 'Password123!');
    await user.type(screen.getByLabelText(/повторите пароль/i), 'Password123!');
    await user.click(screen.getByRole('button', { name: /сохранить пароль/i }));

    expect(await screen.findByText('Ссылка устарела')).toBeInTheDocument();
  });

  it('submits the new password and shows success state', async () => {
    const payloads: unknown[] = [];
    server.use(
      http.post('*/password/reset', async ({ request }) => {
        const body = await request.json();
        payloads.push(body);
        return HttpResponse.json({ ok: true });
      }),
    );

    const user = userEvent.setup();
    renderWithToken();

    await user.type(screen.getByLabelText(/^пароль$/i), 'Password123!');
    await user.type(screen.getByLabelText(/повторите пароль/i), 'Password123!');

    const submitButton = screen.getByRole('button', { name: /сохранить пароль/i });
    await user.click(submitButton);

    await waitFor(() => expect(screen.getByText(/пароль обновлён/i)).toBeInTheDocument());
    expect(payloads).toEqual([{ password: 'Password123!', token: 'token123' }]);
  });
});
