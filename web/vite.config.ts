/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forwards /auth to the API so the browser only ever talks to origin
    // 5173 — keeps the httpOnly session cookie same-origin in dev too
    // (docker/nginx/nginx.conf does the equivalent in staging/production).
    proxy: {
      '/auth': 'http://localhost:8000',
      '/dashboard/summary': 'http://localhost:8000',
      '/dashboard/brand-performance': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: false,
  },
})
