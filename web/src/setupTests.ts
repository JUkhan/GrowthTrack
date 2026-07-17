import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// vite.config.ts sets `globals: false`, so testing-library's own automatic
// cleanup registration (which relies on a global `afterEach`) is a no-op —
// without this, one test's rendered tree leaks into the next.
afterEach(() => {
  cleanup()
})
