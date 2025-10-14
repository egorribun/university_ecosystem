import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { axe } from 'jest-axe';
import Register from '../Register';
import { server } from '@/tests/mocks/server';
import { routerFutureFlags } from '../../App';
import i18n from '../../i18n/config';

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options);
const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const labelRegex = (value: string) => new RegExp(`^${escapeRegExp(value)}`, 'i');

const renderRegister = () =>
  render(
    <MemoryRouter future={routerFutureFlags} initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<div>Sign in page</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe('Register page', () => {
  it('surfaces API error messages', async () => {
    server.use(
      http.post('*/users', () => HttpResponse.json({ detail: 'Email already used' }, { status: 400 })),
    );

    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.name'))), 'Test User');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.email'))), 'user@example.com');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.password'))), 'password123');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.confirmPassword'))), 'password123');
    await user.click(screen.getByRole('button', { name: tAuth('actions.signUp') }));

    expect(await screen.findByText('Email already used')).toBeInTheDocument();
  });

  it('sends registration payload and navigates to login', async () => {
    const payloads: unknown[] = [];
    server.use(
      http.post('*/users', async ({ request }) => {
        const body = await request.json();
        payloads.push(body);
        return HttpResponse.json({ ok: true }, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.name'))), 'Test User');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.email'))), 'user@example.com');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.password'))), 'password123');
    await user.type(screen.getByLabelText(labelRegex(tAuth('fields.confirmPassword'))), 'password123');

    const submitButton = screen.getByRole('button', { name: tAuth('actions.signUp') });
    await user.click(submitButton);

    await waitFor(() => expect(screen.getByText('Sign in page')).toBeInTheDocument());
    expect(payloads).toEqual([
      {
        email: 'user@example.com',
        full_name: 'Test User',
        invite_code: '',
        password: 'password123',
        role: 'student',
      },
    ]);
  });

  it('passes automated accessibility checks', async () => {
    const { container } = renderRegister();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
