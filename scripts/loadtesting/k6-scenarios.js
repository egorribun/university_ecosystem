import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';
const GROUP_ID = __ENV.GROUP_ID || '1';
const CHAT_ID = __ENV.CHAT_ID || '1';
const CACHE_PROFILE = __ENV.CACHE_PROFILE || 'redis';

const defaultHeaders = {
  'Accept-Encoding': 'br,gzip',
  'X-Cache-Profile': CACHE_PROFILE,
};

if (AUTH_TOKEN) {
  defaultHeaders.Authorization = `Bearer ${AUTH_TOKEN}`;
}

export const options = {
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
  scenarios: {
    schedule: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 10,
      stages: [
        { target: 20, duration: '30s' },
        { target: 40, duration: '30s' },
        { target: 0, duration: '10s' },
      ],
      exec: 'hitSchedule',
    },
    news: {
      executor: 'constant-arrival-rate',
      rate: 15,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 10,
      exec: 'hitNews',
    },
    events: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 10,
      stages: [
        { target: 25, duration: '30s' },
        { target: 50, duration: '45s' },
        { target: 0, duration: '15s' },
      ],
      exec: 'hitEvents',
    },
    chat: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 8,
      exec: 'hitChat',
    },
  },
};

function httpGet(path, tags) {
  const res = http.get(`${BASE_URL}${path}`, { headers: defaultHeaders, tags });
  check(res, {
    'status is ok or cached': (r) => r.status === 200 || r.status === 304,
  });
  return res;
}

export function hitSchedule() {
  httpGet(`/schedule/${GROUP_ID}`, { endpoint: 'schedule', cache: CACHE_PROFILE });
  sleep(1);
}

export function hitNews() {
  httpGet('/news?limit=20', { endpoint: 'news', cache: CACHE_PROFILE });
  sleep(0.5);
}

export function hitEvents() {
  httpGet('/events?limit=25&is_active=true', { endpoint: 'events', cache: CACHE_PROFILE });
  sleep(1);
}

export function hitChat() {
  httpGet(`/chat/${CHAT_ID}/messages?limit=25`, { endpoint: 'chat', cache: CACHE_PROFILE });
  sleep(1);
}

export default function () {
  hitSchedule();
  hitNews();
  hitEvents();
  hitChat();
}
