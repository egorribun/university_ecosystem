import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { axe } from 'jest-axe';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Login from '../Login';
import { server } from '@/tests/mocks/server';
import { routerFutureFlags } from '../../App';
import { AuthProvider } from '@/contexts/AuthContext';
import { LanguageProvider } from '@/contexts/LanguageContext';

const clients: QueryClient[] = [];

const createClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });

const renderLogin = () => {
  const client = createClient();
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <AuthProvider>
          <MemoryRouter future={routerFutureFlags} initialEntries={['/login']}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/dashboard" element={<div>Добро пожаловать!</div>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  );
};

describe('Login page', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('ue:language', 'ru');
  });

  afterEach(() => {
    localStorage.clear();
    clients.splice(0).forEach((client) => client.clear());
  });

  it('blocks submission for invalid email', async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/e-mail|email|почта/i, {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'invalid');
    await user.type(
      screen.getByLabelText(/^(пароль|password)/i, { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByRole('button', { name: /войти/i }));

    expect(await screen.findByText('Введите корректный email')).toBeInTheDocument();
  });

  it('submits credentials and redirects on success', async () => {
    const captured: Array<{ username: string | null; password: string | null }> = [];
    server.use(
      http.post('*/auth/login', async ({ request }) => {
        const body = await request.text();
        const params = new URLSearchParams(body);
        captured.push({ username: params.get('username'), password: params.get('password') });
        return HttpResponse.json({ access_token: 'token-123' });
      }),
    );

    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/e-mail|email|почта/i, {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'user@example.com');
    await user.type(
      screen.getByLabelText(/^(пароль|password)/i, { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByLabelText('Показать пароль'));
    await user.click(screen.getByLabelText('Показать пароль'));
    await user.click(screen.getByRole('button', { name: /войти/i }));

    await waitFor(() => expect(screen.getByText('Добро пожаловать!')).toBeInTheDocument());
    expect(captured).toEqual([{ username: 'user@example.com', password: 'secret123' }]);
  });

  it('returns server errors to the user', async () => {
    server.use(
      http.post('*/auth/login', () => HttpResponse.json({ detail: 'Неверные данные для входа' }, { status: 401 })),
    );

    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/e-mail|email|почта/i, {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'user@example.com');
    await user.type(
      screen.getByLabelText(/^(пароль|password)/i, { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByRole('button', { name: /войти/i }));

    expect(await screen.findByText('Неверные данные для входа')).toBeInTheDocument();
  });

  it('meets basic accessibility requirements', async () => {
    const { container } = renderLogin();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
