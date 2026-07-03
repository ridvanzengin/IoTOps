import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // react-draggable (via react-grid-layout) reads process.env.NODE_ENV at
  // runtime; Vite doesn't polyfill `process` for the browser by default.
  define: {
    'process.env.NODE_ENV': JSON.stringify(mode),
  },
}))
