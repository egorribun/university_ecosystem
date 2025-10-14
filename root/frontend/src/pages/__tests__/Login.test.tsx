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
import i18n from '../../i18n/config';

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options);
const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const labelRegex = (value: string) => new RegExp(`^${escapeRegExp(value)}`, 'i');

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
              <Route path="/dashboard" element={<div>Welcome!</div>} />
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
    localStorage.setItem('ue:language', 'en');
  });

  afterEach(() => {
    localStorage.clear();
    clients.splice(0).forEach((client) => client.clear());
  });

  it('blocks submission for invalid email', async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(labelRegex(tAuth('fields.email')), {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'invalid');
    await user.type(
      screen.getByLabelText(labelRegex(tAuth('fields.password')), { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByRole('button', { name: tAuth('actions.signIn') }));

    expect(await screen.findByText(tAuth('messages.invalidEmail'))).toBeInTheDocument();
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

    const emailInput = screen.getByLabelText(labelRegex(tAuth('fields.email')), {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'user@example.com');
    await user.type(
      screen.getByLabelText(labelRegex(tAuth('fields.password')), { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByLabelText(tAuth('actions.showPassword')));
    await user.click(screen.getByLabelText(tAuth('actions.showPassword')));
    await user.click(screen.getByRole('button', { name: tAuth('actions.signIn') }));

    await waitFor(() => expect(screen.getByText('Welcome!')).toBeInTheDocument());
    expect(captured).toEqual([{ username: 'user@example.com', password: 'secret123' }]);
  });

  it('returns server errors to the user', async () => {
    server.use(
      http.post('*/auth/login', () => HttpResponse.json({ detail: tAuth('login.error') }, { status: 401 })),
    );

    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(labelRegex(tAuth('fields.email')), {
      selector: 'input[type="email"]',
    });

    await user.type(emailInput, 'user@example.com');
    await user.type(
      screen.getByLabelText(labelRegex(tAuth('fields.password')), { selector: 'input[type="password"]' }),
      'secret123',
    );
    await user.click(screen.getByRole('button', { name: tAuth('actions.signIn') }));

    expect(await screen.findByText(tAuth('login.error'))).toBeInTheDocument();
  });

  it('meets basic accessibility requirements', async () => {
    const { container } = renderLogin();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
