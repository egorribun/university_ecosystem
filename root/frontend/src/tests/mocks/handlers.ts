import { HttpResponse, http } from 'msw';
import type { User } from '@/types/User';

type NewUserPayload = {
  email?: string;
  [key: string]: unknown;
};

type ResetPasswordPayload = {
  token?: string;
  [key: string]: unknown;
};

export const testUser: User = {
  id: 1,
  email: 'user@example.com',
  full_name: 'Тестовый Пользователь',
  role: 'student',
  group_id: null,
  avatar_url: null,
  cover_url: null,
  about: null,
  record_book_number: null,
  status: null,
  institute: null,
  course: null,
  education_level: null,
  track: null,
  program: null,
  telegram: null,
  achievements: null,
  department: null,
  position: null,
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: true,
};

export const handlers = [
  http.get('*/users/me', () => HttpResponse.json(testUser)),
  http.post('*/users', async ({ request }) => {
    const body = (await request.json()) as NewUserPayload;
    if (body.email === 'taken@example.com') {
      return HttpResponse.json({ detail: 'Email already used' }, { status: 400 });
    }
    return HttpResponse.json({ id: 2, ...body }, { status: 201 });
  }),
  http.post('*/auth/login', async ({ request }) => {
    const raw = await request.text();
    const payload = new URLSearchParams(raw);
    const username = payload.get('username') || '';
    const password = payload.get('password') || '';

    if (!username || !password || username === 'blocked@example.com') {
      return HttpResponse.json({ detail: 'Неверные данные для входа' }, { status: 401 });
    }

    return HttpResponse.json({ access_token: 'test-access-token', username });
  }),
  http.post('*/password/forgot', async () => HttpResponse.json({ ok: true })),
  http.post('*/password/reset', async ({ request }) => {
    const body = (await request.json()) as ResetPasswordPayload;
    if (body.token === 'expired-token') {
      return HttpResponse.json({ detail: 'Ссылка устарела' }, { status: 400 });
    }
    return HttpResponse.json({ ok: true });
  }),
  http.get('*/spotify/auth-url', () => HttpResponse.json({ url: 'https://spotify.example/connect' })),
  http.post('*/spotify/disconnect', () => HttpResponse.json({ ok: true })),
  http.get('*/spotify/now-playing', () =>
    HttpResponse.json({
      is_playing: false,
      item: null,
      progress_ms: 0,
    }),
  ),
  http.get('https://api.pwnedpasswords.com/range/:prefix', () => HttpResponse.text('0000000000000000000000000000000000000:2')),
];
