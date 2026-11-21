import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server forwards every /api request to FastAPI on port 8000,
// so the browser never has to deal with CORS during development.
// 127.0.0.1 (not "localhost") avoids an IPv6 issue on some Windows laptops.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
