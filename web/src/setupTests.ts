import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// vite.config.ts sets `globals: false`, so testing-library's own automatic
// cleanup registration (which relies on a global `afterEach`) is a no-op —
// without this, one test's rendered tree leaks into the next.
afterEach(() => {
  cleanup()
})

// jsdom doesn't implement matchMedia — MUI's useMediaQuery (dark-mode
// system-preference detection, breakpoint checks) calls it unconditionally,
// so every test needs this stub even if it doesn't touch theming directly.
// Defaults to "no match"; individual tests override via
// vi.stubGlobal('matchMedia', ...) when they need a specific query to match.
window.matchMedia =
  window.matchMedia ||
  function matchMediaStub(query: string): MediaQueryList {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    } as MediaQueryList
  }
