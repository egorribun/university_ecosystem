/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig({
plugins: [react()],
resolve: {
alias: {
'@': path.resolve(__dirname, 'src'),
},
},
test: {
environment: 'jsdom',
setupFiles: ['src/setupTests.ts'],
globals: true,
css: true,
reporters: ['default'],
cache: { dir: path.resolve(__dirname, '.vitest') },
},
});
