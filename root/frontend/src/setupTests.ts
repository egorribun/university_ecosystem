/// <reference types="vitest" />
import '@testing-library/jest-dom';
import { TextEncoder, TextDecoder } from 'node:util';
import { webcrypto } from 'node:crypto';
import { vi } from 'vitest';
if (!(globalThis as any).TextEncoder) (globalThis as any).TextEncoder = TextEncoder;
if (!(globalThis as any).TextDecoder) (globalThis as any).TextDecoder = TextDecoder as any;
if (!(globalThis as any).crypto) (globalThis as any).crypto = webcrypto;
if (!('matchMedia' in window)) {
Object.defineProperty(window, 'matchMedia', {
writable: true,
value: (query: string) => ({
matches: false,
media: query,
onchange: null,
addListener: () => {},
removeListener: () => {},
addEventListener: () => {},
removeEventListener: () => {},
dispatchEvent: () => false,
}),
});
}
if (!window.scrollTo) {
// @ts-expect-error jsdom polyfill
window.scrollTo = () => {};
}
vi.mock('qrcode.react', () => ({
QRCodeSVG: () => null,
}));
